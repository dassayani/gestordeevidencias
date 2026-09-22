"""Overlay de seleção de área da tela.

Saiu do `workspace` porque era a maior função que restava lá: 164 linhas com
oito tratadores de evento aninhados, todos existindo só para compartilhar o
mesmo punhado de variáveis. Como classe, esse estado compartilhado vira
atributo e cada tratador vira um método com nome — o mesmo comportamento, sem
a escada de closures.

O caminho é sensível a tempo: o painel já está escondido quando isto roda, a
tela já foi fotografada, e o overlay precisa ser realizado pelo Tk antes de
receber foco. Os comentários que explicam cada armadilha vieram junto.
"""
import tkinter as tk
from tkinter import Toplevel

from PIL import ImageGrab
from screeninfo import get_monitors

import captura_utils
import deteccao_bordas
import deteccao_janelas
import theme

# Quanto o cursor precisa andar para a sugestão ser recalculada. A leitura de
# bordas é barata, mas não a ponto de rodar a cada pixel.
_PASSO_RECALCULO = 6
# Retângulos que diferem menos que isto em todos os cantos são o mesmo.
_TOLERANCIA_DUPLICATA = 8
# Arrasto menor que isto conta como clique, não como seleção.
_MINIMO_ARRASTO = 10


def _area(retangulo):
    return max(0, retangulo[2] - retangulo[0]) * max(0, retangulo[3] - retangulo[1])


class SeletorDeArea:
    """Cobre o desktop inteiro e devolve a área escolhida para o app."""

    def __init__(self, app):
        self.app = app
        self.tema = theme.get(app.modo_escuro)

        monitores = get_monitors()
        self.mx = min(m.x for m in monitores)
        self.my = min(m.y for m in monitores)
        self.lw = max(m.x + m.width for m in monitores) - self.mx
        self.lh = max(m.y + m.height for m in monitores) - self.my

        # O inventário de janelas é levantado ANTES do overlay existir: o
        # overlay cobre o desktop inteiro, então depois dele o Windows
        # responderia que a janela sob o cursor é o próprio overlay.
        try:
            limites = (self.mx, self.my, self.mx + self.lw, self.my + self.lh)
            self.regioes = deteccao_janelas.listar_regioes(limites)
        except Exception:
            self.regioes = []

        self.print_tela = ImageGrab.grab(all_screens=True)
        try:
            self.cinza = deteccao_bordas.preparar(self.print_tela)
        except Exception:
            self.cinza = None

        # estado da interação
        self.sugestao = None
        self.candidatos = []
        self.indice = 0
        self.arrastando = False
        self.ultimo_ponto = None
        self.origem = (0, 0)

        self._montar()

    # ------------------------------------------------------------- montagem

    def _montar(self):
        self.janela = Toplevel(self.app.root)
        self.janela.attributes("-alpha", 0.3, "-topmost", True)
        self.janela.overrideredirect(True)
        self.janela.geometry(f"{self.lw}x{self.lh}+{self.mx}+{self.my}")
        self.canvas = tk.Canvas(self.janela, cursor="cross", bg="grey",
                                highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)

        self.canvas.bind("<Motion>", self._ao_mover)
        self.canvas.bind("<MouseWheel>", self._ao_roda)
        self.canvas.bind("<ButtonPress-1>", self._ao_pressionar)
        self.canvas.bind("<B1-Motion>", self._ao_arrastar)
        self.canvas.bind("<ButtonRelease-1>", self._ao_soltar)
        self.canvas.bind("<Button-3>", self.cancelar)
        self.janela.bind("<Escape>", self.cancelar)

        # Obrigatório: o Tk só realiza uma Toplevel cujo mestre está
        # `withdrawn` ao processar as tarefas ociosas. Sem esta chamada o
        # seletor fica com a geometria inicial 1x1+0+0 e nunca é mapeado, que
        # é o caso do atalho acionado com o painel recolhido na bandeja.
        self.janela.update_idletasks()
        self.janela.focus_force()

    # ------------------------------------------------------------ sugestão

    def _listar_candidatos(self, cx, cy):
        """Pilha de regiões plausíveis no ponto, da menor para a maior.

        As duas fontes entram juntas em vez de uma servir de reserva da outra:
        o Windows conhece as janelas e controles, a leitura de bordas enxerga
        dentro de navegador e emulador, e nenhuma das duas sozinha acerta em
        todo lugar. O usuário escolhe na roda do mouse qual nível quer —
        cartão, painel ou janela.

        As coordenadas do canvas são relativas à origem do desktop virtual e
        coincidem com os pixels do print; as regiões vêm em coordenadas
        absolutas, daí o deslocamento por (mx, my).
        """
        lista = [(r[0] - self.mx, r[1] - self.my, r[2] - self.mx, r[3] - self.my)
                 for r in deteccao_janelas.candidatos_sob_ponto(
                     self.regioes, cx + self.mx, cy + self.my)]
        moldura = lista[-1] if lista else (0, 0, self.lw, self.lh)
        preferida = None
        if self.cinza is not None:
            try:
                lista.extend(deteccao_bordas.candidatos(self.cinza, cx, cy))
                # A coluna verificada na altura inteira da janela é a única com
                # evidência forte o bastante pra ser o palpite inicial: as
                # demais podem estar cortadas no realce ou na divisória que por
                # acaso passa sob o cursor.
                preferida = deteccao_bordas.coluna_no_ponto(self.cinza, cx, moldura)
                if preferida:
                    lista.append(preferida)
            except Exception:
                pass
        # a tela inteira não é sugestão útil: pra isso basta arrastar
        lista = [r for r in lista if _area(r) <= 0.92 * self.lw * self.lh]
        unicos = []
        for r in sorted(lista, key=_area):
            if not any(all(abs(a - b) <= _TOLERANCIA_DUPLICATA for a, b in zip(r, u))
                       for u in unicos):
                unicos.append(r)
        inicial = unicos.index(preferida) if preferida in unicos else 0
        return unicos, inicial

    def _desenhar_sugestao(self):
        self.canvas.delete("sugestao")
        if not self.candidatos:
            self.sugestao = None
            return
        self.indice = max(0, min(self.indice, len(self.candidatos) - 1))
        self.sugestao = self.candidatos[self.indice]
        self.canvas.create_rectangle(*self.sugestao, outline=self.tema["accent"],
                                     width=3, tags="sugestao")
        if len(self.candidatos) > 1:
            self.canvas.create_text(
                self.sugestao[0] + 6, max(14, self.sugestao[1] - 14),
                text=f"{self.indice + 1}/{len(self.candidatos)} · "
                     f"roda do mouse ajusta a área",
                fill=self.tema["accent"], anchor="w",
                font=(theme.FONT, theme.FS_CAPTION, "bold"), tags="sugestao")

    # ------------------------------------------------------------ tratadores

    def _ao_mover(self, e):
        if self.arrastando:
            return
        anterior = self.ultimo_ponto
        if anterior and (abs(e.x - anterior[0]) < _PASSO_RECALCULO
                         and abs(e.y - anterior[1]) < _PASSO_RECALCULO):
            return
        self.ultimo_ponto = (e.x, e.y)
        lista, inicial = self._listar_candidatos(e.x, e.y)
        if lista == self.candidatos:
            return
        self.candidatos = lista
        self.indice = inicial
        self._desenhar_sugestao()

    def _ao_roda(self, e):
        """Roda pra cima aperta a sugestão, pra baixo abre."""
        if self.arrastando or len(self.candidatos) < 2:
            return
        self.indice += -1 if e.delta > 0 else 1
        self._desenhar_sugestao()

    def _ao_pressionar(self, e):
        self.origem = (e.x, e.y)
        self.arrastando = False

    def _ao_arrastar(self, e):
        ox, oy = self.origem
        if abs(e.x - ox) > 4 or abs(e.y - oy) > 4:
            self.arrastando = True
            self.canvas.delete("sugestao")
        self.canvas.delete("rect")
        self.canvas.create_rectangle(ox, oy, e.x, e.y, outline="red", width=2,
                                     tags="rect")

    def _ao_soltar(self, e):
        ox, oy = self.origem
        x1, y1 = min(ox, e.x), min(oy, e.y)
        x2, y2 = max(ox, e.x), max(oy, e.y)
        # Clique sem arrastar captura a área sugerida; arrastar mantém a
        # seleção manual. As duas dimensões são validadas, senão uma faixa de
        # 1 px de altura passaria como seleção.
        if not self.arrastando and self.sugestao:
            self._finalizar(self.sugestao)
        elif (x2 - x1) > _MINIMO_ARRASTO and (y2 - y1) > _MINIMO_ARRASTO:
            self._finalizar((x1, y1, x2, y2))
        else:
            self._finalizar(None)

    def cancelar(self, _=None):
        self.janela.destroy()
        self.app._capturando = False
        self.app.mostrar_janela()

    # ------------------------------------------------------------- conclusão

    def _finalizar(self, area_canvas):
        """`area_canvas` é (x1, y1, x2, y2) no referencial do canvas."""
        self.janela.destroy()
        self.app._capturando = False
        if area_canvas is None:
            self.app.mostrar_janela()
            return
        x1, y1, x2, y2 = area_canvas
        recorte = self.print_tela.crop((x1, y1, x2, y2))
        if self.app.config.get("incluir_cursor", False):
            recorte = captura_utils.colar_cursor(
                recorte, offset=(x1 + self.mx, y1 + self.my))
        self.app._guardar_ultima_area((x1 + self.mx, y1 + self.my,
                                       x2 + self.mx, y2 + self.my))
        self.app._salvar_captura(recorte)
