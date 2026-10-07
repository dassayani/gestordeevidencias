"""Painel/área de trabalho principal (tela '1a' do design): busca, filtros,
lista de capturas, seleção para documento e disparo da captura de tela."""
import os
import queue
import threading
from datetime import datetime
from tkinter import messagebox
import tkinter as tk
import tkinter.font as tkfont

import pystray
from PIL import Image, ImageTk, ImageGrab
from pystray import MenuItem as item
from tkinterdnd2 import COPY, DND_FILES

from gestor.dados import capture_store
from gestor.captura import captura_utils
from gestor.dados import config
from gestor.ui import configuracoes
from gestor.captura import deteccao_janelas
from gestor.ui import editor
from gestor.captura import hotkey
from gestor.ui import seletor
from gestor.ui import theme
from gestor.sistema import utils
from gestor.ui import widgets

FILTROS = (("hoje", "Hoje"), ("marcadas", "Marcadas"), ("editadas", "Editadas"), ("tudo", "Tudo"))

# Visualizações da lista. As células têm largura fixa, como no Explorer: com
# coluna elástica, uma legenda longa empurra a largura da coluna e a lista
# ganha rolagem horizontal.
MODOS_VISUALIZACAO = (
    ("detalhes", widgets.icone_lista),
    ("blocos", widgets.icone_blocos),
    ("grade", widgets.icone_grade),
)
# A largura sai medida do texto que a celula precisa mostrar: o nome do
# arquivo muda de tamanho com o padrao escolhido nas Configuracoes
# ("captura-HHMMSS" contra "captura-AAAAMMDD-HHMMSS") e com a escala da fonte.
# Os limites evitam tanto a celula minuscula quanto uma legenda longa virando
# uma celula que ocupa a lista inteira.
LARGURA_BLOCO_MIN, LARGURA_BLOCO_MAX = 170, 300
LARGURA_ICONE_MIN, LARGURA_ICONE_MAX = 96, 180
LADO_MINIATURA_BLOCO = 70
ALTURA_MINIATURA_ICONE = 66
ESPACO_CELULA = 6

MESES_PT = [
    "janeiro", "fevereiro", "março", "abril", "maio", "junho",
    "julho", "agosto", "setembro", "outubro", "novembro", "dezembro",
]

# de quanto em quanto tempo insistir num atalho que estava ocupado
_INTERVALO_RETENTATIVA_MS = 20000
# de quanto em quanto tempo o Tk atende os pedidos do menu da bandeja
_INTERVALO_BANDEJA_MS = 150
# quantas vezes insistir no posicionamento da grade enquanto o canvas nao tem
# largura util (25 ms cada: o suficiente para o Tk realizar os widgets)
MAX_TENTATIVAS_GRADE = 40


def _data_pt(dt):
    return f"{dt.day} de {MESES_PT[dt.month - 1]}"


def _area(retangulo):
    return max(0, retangulo[2] - retangulo[0]) * max(0, retangulo[3] - retangulo[1])


class AppEvidencias:
    def __init__(self, root, pasta_capturas, pasta_pdfs, base_dir, data_dir):
        self.root = root
        self.pasta_capturas_padrao = pasta_capturas
        self.pasta_pdfs = pasta_pdfs
        self.base_dir = base_dir
        self.data_dir = data_dir
        self.config = config.load(data_dir)
        self.pasta_capturas = self._resolver_pasta_capturas()
        self.modo_escuro = False
        self.tempo_limite = self.config.get("tempo_inatividade_ms", 10000)
        self.pausar_timer = False
        self.arquivos_selecionados = set()
        self.imagens_tk = []
        self.filtro_atual = "hoje"
        self.modo_visualizacao = self.config.get("modo_visualizacao", "detalhes")
        self._celulas_grade = []
        self._colunas_grade = 0
        self._tentativas_grade = 0
        self._job_grade = None
        self._capturando = False
        self.cards = {}

        self._aplicar_escala_fonte()

        t = theme.get(self.modo_escuro)
        self.root.title("Gestor de Evidências")
        self.root.geometry("460x820")
        self._ajustar_minsize()
        self.root.configure(bg=t["bg_panel"])
        widgets.aplicar_icone(self.root)

        self._montar_ui(t)

        # Ctrl+Insert é o sinônimo histórico de copiar, ainda usado por quem
        # vem de ferramentas antigas.
        self.root.bind("<Control-c>", self.copiar_selecionadas)
        self.root.bind("<Control-C>", self.copiar_selecionadas)
        self.root.bind("<Control-Insert>", self.copiar_selecionadas)
        self.root.bind("<Any-KeyPress>", lambda e: self.resetar_timer())
        self.root.bind("<Any-Button>", lambda e: self.resetar_timer())
        self.root.protocol("WM_DELETE_WINDOW", self.esconder_janela)

        self.job_inatividade = None
        self.criar_icone_bandeja()
        self.resetar_timer()
        self.atualizar_galeria()
        if self.pasta_indisponivel:
            self.root.after(600, self._avisar_pasta_indisponivel)

        try:
            removidos = captura_utils.limpar_capturas_antigas(
                self.pasta_capturas, self.config.get("retencao_dias", 0))
            if removidos:
                self.atualizar_galeria()
        except Exception:
            pass

        self.hotkeys = None
        self.erros_atalhos = []
        try:
            self.hotkeys = hotkey.HotkeyManager(self.root)
            self.erros_atalhos = self._registrar_atalhos()
        except Exception as e:
            self.erros_atalhos = [f"não foi possível inicializar os atalhos: {e}"]
            print(f"[atalho global] {self.erros_atalhos[0]}")

    def _registrar_atalhos(self):
        erros = []
        if not self.hotkeys:
            return erros

        chave_area = self.config.get("atalho_captura_area", "printscreen")
        combo = next((c for c in hotkey.COMBOS_CAPTURA_AREA if c[0] == chave_area),
                     hotkey.COMBOS_CAPTURA_AREA[0])
        try:
            self.hotkeys.registrar("captura_area", combo[3], combo[2], self.iniciar_seletor)
        except Exception as e:
            erros.append(f"Captura de área ({combo[1]}): {e}")

        chave_janela = self.config.get("atalho_janela_ativa", "nenhum")
        combo_j = next((c for c in hotkey.COMBOS_JANELA_ATIVA if c[0] == chave_janela),
                       hotkey.COMBOS_JANELA_ATIVA[0])
        if combo_j[3] is not None:
            try:
                self.hotkeys.registrar("janela_ativa", combo_j[3], combo_j[2],
                                       self.iniciar_captura_janela_ativa)
            except Exception as e:
                erros.append(f"Janela ativa ({combo_j[1]}): {e}")
        else:
            self.hotkeys.remover("janela_ativa")

        # Shift+PrintScreen repete a última área. O Windows trata (modificador,
        # tecla) como combinação distinta, então isso convive com o PrintScreen
        # puro registrado acima.
        try:
            self.hotkeys.registrar("recapturar", hotkey.VK_SNAPSHOT, hotkey.MOD_SHIFT,
                                    self.recapturar_ultima_area)
        except Exception as e:
            erros.append(f"Repetir última área (Shift+Print Screen): {e}")

        self.erros_atalhos = erros
        for msg in erros:
            print(f"[atalho global] {msg}")
        self._agendar_retentativa_atalhos()
        return erros

    def _agendar_retentativa_atalhos(self):
        """Reagenda o registro enquanto houver combinação ocupada.

        Uma combinação tomada por outro programa no momento da inicialização
        fica livre depois; sem a retentativa o atalho só voltaria a funcionar
        reiniciando o app.
        """
        if getattr(self, "_job_retentativa", None):
            try:
                self.root.after_cancel(self._job_retentativa)
            except Exception:
                pass
            self._job_retentativa = None
        if not self.erros_atalhos:
            return
        try:
            self._job_retentativa = self.root.after(_INTERVALO_RETENTATIVA_MS,
                                                     self._retentar_atalhos)
        except Exception:
            pass

    def _retentar_atalhos(self):
        self._job_retentativa = None
        if not self.erros_atalhos or not self.hotkeys:
            return
        antes = list(self.erros_atalhos)
        self._registrar_atalhos()
        if antes and not self.erros_atalhos:
            print("[atalho global] atalhos registrados com sucesso na retentativa")

    def _aplicar_escala_fonte(self):
        """Lê a escala escolhida nas Configurações e aplica nos tokens do tema."""
        geral = theme.escala_por_chave(self.config.get("escala_fonte", "padrao"))
        botao = theme.escala_por_chave(self.config.get("escala_fonte_botao", "padrao"))
        theme.aplicar_escala(geral, botao)

    def _ajustar_minsize(self):
        """A largura mínima acompanha a escala: com fonte maior o rodapé
        (dois botões + lixeira) precisa de mais espaço pra não cortar rótulo."""
        geral = theme.escala_por_chave(self.config.get("escala_fonte", "padrao"))
        self.root.minsize(int(400 * geral), int(520 * geral))

    def _reconstruir_ui(self):
        """Destrói e remonta a interface principal.

        É como a troca de tema já funcionava; a mudança de tamanho de fonte usa
        o mesmo caminho, porque os widgets do Tk não reagem sozinhos a uma
        mudança nos tokens — só quem é construído depois pega o valor novo.

        Só os widgets do próprio painel são destruídos. As outras janelas
        (Configurações, editor, montar documento) são Toplevel e também
        aparecem como filhas da raiz: destruí-las aqui matava a janela de
        Configurações no meio da troca de fonte, e como o `destroy` não
        dispara o WM_DELETE_WINDOW dela, o `pausar_timer` ficava ligado pra
        sempre — que foi o que fez o botão fechar parar de responder.
        """
        for w in self.root.winfo_children():
            if isinstance(w, tk.Toplevel):
                continue
            w.destroy()
        t = theme.get(self.modo_escuro)
        self.root.configure(bg=t["bg_panel"])
        self._montar_ui(t)
        # Realiza os widgets recém-criados antes de montar a lista: sem isso o
        # canvas ainda mede 1 pixel e a grade não teria como calcular as
        # colunas. Só tarefas ociosas (geometria), não eventos de usuário.
        try:
            self.root.update_idletasks()
        except Exception:
            pass
        self.atualizar_galeria()

    def pasta_documentos(self, formato="pdf"):
        """Pasta de saída dos documentos: PDF/ ou DOCX/ dentro da pasta de
        capturas vigente.

        Deriva sempre da pasta de capturas atual, então acompanha sozinha quem
        trocar a pasta nas Configurações.
        """
        destino = os.path.join(self.pasta_capturas, (formato or "pdf").upper())
        try:
            os.makedirs(destino, exist_ok=True)
        except Exception:
            return self.pasta_capturas
        return destino

    def _resolver_pasta_capturas(self):
        self.pasta_indisponivel = None
        pasta = self.config.get("pasta_capturas")
        if pasta and os.path.isdir(pasta):
            return pasta
        if pasta:
            try:
                os.makedirs(pasta, exist_ok=True)
                return pasta
            except Exception:
                # Pendrive fora, unidade de rede caída: as capturas passam a ir
                # para a pasta padrão. Sem avisar, quem conta com a pasta
                # compartilhada só descobre depois, procurando a evidência.
                self.pasta_indisponivel = pasta
        return self.pasta_capturas_padrao

    def _avisar_pasta_indisponivel(self):
        if not self.pasta_indisponivel:
            return
        messagebox.showwarning(
            "Pasta de capturas indisponível",
            f"A pasta configurada não está acessível:\n{self.pasta_indisponivel}\n\n"
            f"Enquanto isso, as capturas serão salvas em:\n{self.pasta_capturas}\n\n"
            "Quando a pasta voltar, reabra o app ou escolha-a de novo em "
            "Configurações.", parent=self.root)

    # ---------- construção da UI ----------

    def _ajustar_titulo_painel(self):
        """Reduz a fonte do título até caber no espaço que os ícones deixam.

        Com o painel estreito (ou a fonte da interface aumentada) o título
        cortava no meio da palavra; uma fonte menor inteira lê melhor.
        """
        titulo = getattr(self, "_titulo_painel", None)
        if titulo is None:
            return
        try:
            disponivel = titulo.winfo_width() - 6     # a borda interna do rótulo
        except tk.TclError:
            return
        if disponivel <= 1:
            return
        for tamanho in (theme.FS_TITLE, theme.FS_SUBTITLE, theme.FS_BODY):
            fonte = tkfont.Font(family=theme.FONT, size=tamanho, weight="bold")
            if fonte.measure(titulo.cget("text")) <= disponivel:
                break
        if titulo.cget("font") != str((theme.FONT, tamanho, "bold")):
            titulo.config(font=(theme.FONT, tamanho, "bold"))

    def _montar_ui(self, t):
        header = tk.Frame(self.root, bg=t["bg_header"], height=52)
        header.pack(fill="x")
        header.pack_propagate(False)
        # Os ícones são empacotados ANTES do título: o pack dá espaço na ordem
        # de empacotamento, e com o título primeiro, num painel estreito, eram
        # os botões (o que se clica) que saíam cortados.
        widgets.IconButton(header, widgets.icone_configuracoes, self.abrir_configuracoes,
                            self.modo_escuro, bg=t["bg_header"]).pack(side="right", padx=(4, 14))
        widgets.IconButton(
            header,
            lambda draw, cx, cy, r, cor, cor_fundo: widgets.icone_tema(
                draw, cx, cy, r, cor, cor_fundo, escuro=self.modo_escuro),
            self.alternar_tema, self.modo_escuro, bg=t["bg_header"]).pack(side="right", padx=4)

        # Empacotados na ordem inversa porque `side="right"` empilha da direita
        # para a esquerda; assim a sequência na tela fica lista, blocos, grade.
        self.botoes_visao = {}
        for chave, icone in reversed(MODOS_VISUALIZACAO):
            botao = widgets.IconButton(header, icone,
                                        lambda c=chave: self._definir_modo_visualizacao(c),
                                        self.modo_escuro, bg=t["bg_header"],
                                        ativo=(chave == self.modo_visualizacao))
            botao.pack(side="right", padx=2)
            self.botoes_visao[chave] = botao

        titulo = tk.Label(header, text="Área de Trabalho", bg=t["bg_header"],
                          fg=t["text_primary"], anchor="w",
                          font=(theme.FONT, theme.FS_TITLE, "bold"))
        titulo.pack(side="left", fill="x", expand=True, padx=(14, 6))
        self._titulo_painel = titulo
        # no próprio título: é o espaço dele que muda quando a janela muda de
        # largura (o cabeçalho tem altura fixa e quase nunca dispara)
        titulo.bind("<Configure>", lambda e: self._ajustar_titulo_painel(), add="+")

        busca_frame = tk.Frame(self.root, bg=t["bg_panel"])
        busca_frame.pack(fill="x", padx=14, pady=(12, 8))
        caixa = tk.Frame(busca_frame, bg=t["bg_input"], highlightbackground=t["border_input"],
                          highlightthickness=1)
        caixa.pack(fill="x")
        tk.Label(caixa, text="⌕", bg=t["bg_input"], fg=t["text_muted"]).pack(
            side="left", padx=(8, 4), pady=6)
        self.entrada_busca = tk.Entry(caixa, bg=t["bg_input"], fg=t["text_primary"], relief="flat",
                                       insertbackground=t["text_primary"],
                                       font=(theme.FONT, theme.FS_BODY))
        self.entrada_busca.pack(side="left", fill="x", expand=True, padx=(0, 8), pady=6)
        self.entrada_busca.bind("<KeyRelease>", lambda e: self.atualizar_galeria())

        pills_frame = tk.Frame(self.root, bg=t["bg_panel"])
        pills_frame.pack(fill="x", padx=14, pady=(0, 8))
        self.botoes_filtro = {}
        for chave, rotulo in FILTROS:
            texto = f"{rotulo} · {self._contagem_filtro(chave)}" if chave == "hoje" else rotulo
            pill = widgets.Pill(pills_frame, texto, self.modo_escuro, bg=t["bg_panel"],
                                 ativo=(chave == self.filtro_atual), altura=32,
                                 fonte_pt=theme.FS_BODY,
                                 comando=lambda c=chave: self._definir_filtro(c))
            pill.pack(side="left", padx=3)
            self.botoes_filtro[chave] = pill
        self._atualizar_botoes_filtro()

        # O rodapé precisa ser empacotado antes da lista: o `pack` distribui o
        # espaço na ordem de chamada, e a lista usa expand=True. Invertendo,
        # ela consome a altura toda e o rodapé some ao encolher a janela.
        self._montar_rodape(t)

        lista_wrap = tk.Frame(self.root, bg=t["bg_panel"])
        lista_wrap.pack(fill="both", expand=True)
        self.canvas_lista = tk.Canvas(lista_wrap, bg=t["bg_panel"], highlightthickness=0)
        self.scrollbar = tk.Scrollbar(lista_wrap, orient="vertical",
                                      command=self.canvas_lista.yview)
        self.frame_lista = tk.Frame(self.canvas_lista, bg=t["bg_panel"])
        self.canvas_lista.create_window((0, 0), window=self.frame_lista, anchor="nw")
        self.canvas_lista.configure(yscrollcommand=self.scrollbar.set)
        self.canvas_lista.pack(side="left", fill="both", expand=True, padx=(14, 0))
        self.scrollbar.pack(side="right", fill="y")
        self.frame_lista.bind("<Configure>",
                               lambda e: self.canvas_lista.config(
                                   scrollregion=self.canvas_lista.bbox("all")))
        self.canvas_lista.bind("<Configure>", self._ao_redimensionar_lista)
        self.canvas_lista.bind("<Enter>",
            lambda e: self.canvas_lista.bind_all("<MouseWheel>", self._on_mousewheel))
        self.canvas_lista.bind("<Leave>", lambda e: self.canvas_lista.unbind_all("<MouseWheel>"))

    def _montar_rodape(self, t):
        rodape = tk.Frame(self.root, bg=t["bg_footer"])
        rodape.pack(fill="x", side="bottom")

        # linha_info e acoes_selecao ficam em linhas separadas (em vez de
        # side="left"/side="right" na mesma linha) porque numa janela estreita
        # ("Selecionar tudo · Limpar seleção" + a contagem) não cabiam juntos
        # e os textos se sobrepunham.
        linha_info = tk.Frame(rodape, bg=t["bg_footer"])
        linha_info.pack(fill="x", padx=14, pady=(10, 2))
        self.lbl_selecionadas = tk.Label(linha_info, text="0 capturas selecionadas",
                                         bg=t["bg_footer"],
                                          fg=t["accent"], font=(theme.FONT, theme.FS_BODY, "bold"),
                                          anchor="w")
        self.lbl_selecionadas.pack(fill="x")

        acoes_selecao = tk.Frame(rodape, bg=t["bg_footer"])
        acoes_selecao.pack(fill="x", padx=14, pady=(0, 8))
        lbl_limpar = tk.Label(acoes_selecao, text="Limpar seleção", bg=t["bg_footer"],
                              fg=t["text_tertiary"],
                               font=(theme.FONT, theme.FS_BODY), cursor="hand2")
        lbl_limpar.pack(side="right")
        lbl_limpar.bind("<Button-1>", lambda e: self.limpar_selecao())
        tk.Label(acoes_selecao, text=" · ", bg=t["bg_footer"], fg=t["text_muted"],
                 font=(theme.FONT, theme.FS_BODY)).pack(side="right")
        lbl_selecionar_tudo = tk.Label(acoes_selecao, text="Selecionar tudo", bg=t["bg_footer"],
                                       fg=t["accent"],
                                        font=(theme.FONT, theme.FS_BODY), cursor="hand2")
        lbl_selecionar_tudo.pack(side="right")
        lbl_selecionar_tudo.bind("<Button-1>", lambda e: self.selecionar_tudo())

        # Grid em vez de pack: com pack(expand=True) o espaço extra é dividido
        # igualmente, mas cada botão soma a largura natural do próprio rótulo —
        # como "Nova captura" e "Criar documento" têm tamanhos diferentes, eles
        # terminavam com larguras diferentes. As colunas com o mesmo `uniform`
        # ficam exatamente iguais em qualquer redimensionamento.
        #
        # A linha também precisa de peso, e as células de `sticky="nsew"`: numa
        # janela estreita "Criar documento" quebra em duas linhas e cresce, e
        # sem isso o botão ao lado continuava na altura de uma linha, deixando
        # os dois visivelmente diferentes. Assim ambos assumem a altura da
        # linha, que é a do maior.
        linha_botoes = tk.Frame(rodape, bg=t["bg_footer"])
        linha_botoes.pack(fill="x", padx=14, pady=(0, 12))
        linha_botoes.grid_columnconfigure(0, weight=1, uniform="acao")
        linha_botoes.grid_columnconfigure(1, weight=1, uniform="acao")
        linha_botoes.grid_rowconfigure(0, weight=1)

        # Rótulos sem emoji/seta decorativa: além de renderizarem diferente
        # em cada Windows, ocupavam largura que faz falta numa janela estreita.
        # O padding precisa ser simétrico entre as duas células: com margens
        # diferentes as colunas ficam iguais mas os botões dentro delas não.
        widgets.botao_secundario(linha_botoes, "Nova captura", self.iniciar_seletor,
                                 self.modo_escuro,
                                  bg=t["bg_footer"]).grid(
                                      row=0, column=0, sticky="nsew", padx=(0, 3))
        widgets.botao_primario(linha_botoes, "Criar documento", self.abrir_montar_documento,
                                self.modo_escuro).grid(row=0, column=1, sticky="nsew", padx=(3, 0))

        # o botão de excluir fica fora do `uniform`, com largura fixa
        btn_excluir = tk.Frame(linha_botoes, bg=t["bg_panel"], highlightbackground=t["border"],
                                highlightcolor=t["border"], highlightthickness=1,
                                width=theme.CTRL_H, height=theme.CTRL_H)
        btn_excluir.grid_propagate(False)
        btn_excluir.grid(row=0, column=2, sticky="nse", padx=(6, 0))
        self._img_lixeira = ImageTk.PhotoImage(
            widgets._construir_icone_botao(widgets.icone_lixeira, 18, t["text_secondary"],
                                            t["bg_panel"], t["bg_panel"]))
        lbl_excluir = tk.Label(btn_excluir, image=self._img_lixeira, bg=t["bg_panel"],
                                cursor="hand2", bd=0, highlightthickness=0)
        lbl_excluir.pack(expand=True)
        lbl_excluir.bind("<Button-1>", lambda e: self.excluir_selecionadas_ou_tudo())

    def _ao_redimensionar_lista(self, event):
        self.canvas_lista.itemconfig("all", width=event.width)
        self._reposicionar_grade()

    def _on_mousewheel(self, event):
        self.canvas_lista.yview_scroll(int(-1 * (event.delta / 120)), "units")

    # ---------- filtros / busca / seleção ----------

    def _definir_filtro(self, chave):
        self.filtro_atual = chave
        self._atualizar_botoes_filtro()
        self.atualizar_galeria()

    def _atualizar_botoes_filtro(self, itens=None):
        for chave, rotulo in FILTROS:
            pill = self.botoes_filtro.get(chave)
            if not pill:
                continue
            texto = f"{rotulo} · {self._contagem_filtro('hoje', itens)}" if chave == "hoje" else rotulo
            pill.definir(texto, chave == self.filtro_atual)

    def _contagem_filtro(self, chave, itens=None):
        if itens is None:
            itens = capture_store.list_captures(self.pasta_capturas)
        if chave == "hoje":
            return sum(1 for i in itens
                       if datetime.fromtimestamp(i["mtime"]).date() == datetime.now().date())
        return len(itens)

    def limpar_selecao(self):
        self.arquivos_selecionados.clear()
        self.atualizar_galeria()

    def selecionar_tudo(self):
        for i in self._itens_filtrados():
            self.arquivos_selecionados.add(i["name"])
        self.atualizar_galeria()

    def _itens_filtrados(self, itens=None):
        if itens is None:
            itens = capture_store.list_captures(self.pasta_capturas)
        termo = self.entrada_busca.get().strip().lower() if hasattr(self, "entrada_busca") else ""

        def procurado(i):
            """O termo aparece no nome, na legenda ou no caso/projeto.

            O caso entrou aqui porque é justamente por ele que se procura uma
            evidência semanas depois — pelo número do teste, não pelo horário
            que o arquivo recebeu no nome.
            """
            return any(termo in (i.get(campo) or "").lower()
                       for campo in ("name", "caption", "caso"))

        def passa_filtro(i):
            if termo and not procurado(i):
                return False
            if self.filtro_atual == "hoje":
                return datetime.fromtimestamp(i["mtime"]).date() == datetime.now().date()
            if self.filtro_atual == "marcadas":
                return i["name"] in self.arquivos_selecionados
            if self.filtro_atual == "editadas":
                return i["edited"]
            return True

        return [i for i in itens if passa_filtro(i)]

    def _alternar_selecao(self, nome):
        if nome in self.arquivos_selecionados:
            self.arquivos_selecionados.remove(nome)
        else:
            self.arquivos_selecionados.add(nome)
        if self.filtro_atual == "marcadas" and nome not in self.arquivos_selecionados:
            # o item some da lista nesse filtro especifico — precisa reconstruir
            self.atualizar_galeria()
        else:
            self._atualizar_aparencia_card(nome)
        self._atualizar_contador()

    # ---------- galeria / lista ----------

    def _definir_modo_visualizacao(self, chave):
        if chave == self.modo_visualizacao:
            return
        self.modo_visualizacao = chave
        self.config["modo_visualizacao"] = chave
        config.save(self.data_dir, self.config)
        for outra, botao in self.botoes_visao.items():
            botao.definir_ativo(outra == chave)
        self.atualizar_galeria()

    def atualizar_galeria(self):
        """Mostra as capturas, reaproveitando os cartões que não mudaram.

        Recriar todos os cartões a cada atualização (depois de cada captura,
        edição ou clique no filtro "Marcadas") levava segundos com uma centena
        de prints. Cada cartão guarda uma assinatura do que mostra; só o que
        mudou é recriado, e o resto apenas troca de lugar.
        """
        t = theme.get(self.modo_escuro)
        for w in getattr(self, "_efemeros", ()):
            try:
                w.destroy()            # cabeçalhos de data e o aviso de lista vazia
            except tk.TclError:
                pass
        self._efemeros = []
        self.imagens_tk = []
        self.cards = {}
        self._celulas_grade = []
        # O número de colunas memorizado descreve o arranjo anterior. Sem zerar
        # aqui, o recolunamento saía por "continua com o mesmo número de
        # colunas" e a lista ficava vazia.
        self._colunas_grade = 0

        # Uma listagem só por atualização: o contador do filtro "Hoje" listava a
        # pasta de novo (lendo cada .json), dobrando o custo.
        todos = capture_store.list_captures(self.pasta_capturas)
        itens = self._itens_filtrados(todos)
        if self.modo_visualizacao != "detalhes" and itens:
            self._medir_celula(itens)
        cartoes = self._cartoes_reaproveitados(itens, t)

        if not itens:
            vazio = tk.Label(self.frame_lista, text="Nenhuma captura encontrada.",
                             bg=t["bg_panel"], fg=t["text_muted"],
                             font=(theme.FONT, theme.FS_BODY))
            vazio.pack(pady=30)
            self._efemeros.append(vazio)
        elif self.modo_visualizacao == "detalhes":
            self._montar_detalhes(itens, t, cartoes)
        else:
            self._montar_grade(itens, t, cartoes)

        self.frame_lista.update_idletasks()
        self.canvas_lista.config(scrollregion=self.canvas_lista.bbox("all"))
        self._atualizar_contador()
        if hasattr(self, "botoes_filtro"):
            self._atualizar_botoes_filtro(todos)

    def _assinatura_card(self, item):
        """O que o cartão mostra. Mudou, recria; igual, reaproveita."""
        celula = ((getattr(self, "_larg_celula", 0), getattr(self, "_alt_celula", 0))
                  if self.modo_visualizacao != "detalhes" else None)
        return (item["mtime"], item["caption"], item.get("caso", ""), item["shape_count"],
                item["edited"], tuple(item["dims"]), celula, theme.FS_BODY, theme.FS_CAPTION)

    def _cartoes_reaproveitados(self, itens, t):
        """Os cartões dos itens, recriando só os que mudaram. Devolve {nome: cartão}."""
        visao = (self.modo_visualizacao, self.modo_escuro, str(self.frame_lista))
        cache = self.__dict__.setdefault("_cache_cards", {})
        if getattr(self, "_visao_cache", None) != visao:
            # Outra visão (ou o painel foi remontado): nada serve. Destruir
            # ANTES de criar, porque detalhes usa pack e as grades usam grid, e
            # o Tk não admite os dois no mesmo contêiner.
            for _, card, _ in cache.values():
                try:
                    card.destroy()
                except tk.TclError:
                    pass
            cache.clear()
            self._visao_cache = visao
        criar = {"detalhes": self._criar_card, "blocos": self._criar_bloco}.get(
            self.modo_visualizacao, self._criar_icone)
        novos, reaproveitados = {}, []
        for captura in itens:
            nome = captura["name"]
            assinatura = self._assinatura_card(captura)
            guardado = cache.pop(nome, None)
            if guardado and guardado[0] == assinatura and guardado[1].winfo_exists():
                self.cards[nome] = guardado[2]
                novos[nome] = guardado
                reaproveitados.append(nome)
                continue
            if guardado:
                try:
                    guardado[1].destroy()
                except tk.TclError:
                    pass
            card = criar(captura, t)
            novos[nome] = (assinatura, card, self.cards[nome])
        for _, card, _ in cache.values():       # o que saiu da lista
            try:
                card.destroy()
            except tk.TclError:
                pass
        self._cache_cards = novos
        for nome in reaproveitados:
            # a seleção pode ter mudado desde que o cartão foi criado
            self._atualizar_aparencia_card(nome)
        return {nome: entrada[1] for nome, entrada in novos.items()}

    def _empacotar_em_ordem(self, sequencia):
        """Põe os widgets (com as opções de pack de cada um) na ordem dada,
        movendo os que já estão na lista em vez de desmontá-los — desmapear e
        remapear a subárvore de cada cartão custava mais que criá-lo."""
        anterior = None
        for w, opcoes in sequencia:
            escravos = self.frame_lista.pack_slaves()
            if w.winfo_manager() != "pack":
                if anterior is not None:
                    w.pack(after=anterior, **opcoes)
                elif escravos:
                    w.pack(before=escravos[0], **opcoes)
                else:
                    w.pack(**opcoes)
            elif anterior is None:
                if escravos[0] is not w:
                    w.pack_configure(before=escravos[0], **opcoes)
            else:
                i = escravos.index(anterior)
                if i + 1 >= len(escravos) or escravos[i + 1] is not w:
                    w.pack_configure(after=anterior, **opcoes)
            anterior = w

    def _cabecalho_data(self, texto, t):
        rotulo = tk.Label(self.frame_lista, text=texto.upper(), bg=t["bg_panel"],
                          fg=t["text_muted"], anchor="w",
                          font=(theme.FONT, theme.FS_CAPTION, "bold"))
        self._efemeros.append(rotulo)
        return rotulo

    def _agrupado_por_data(self, itens):
        """Percorre os itens avisando quando vira o dia."""
        grupo = None
        for i in itens:
            data_item = _data_pt(datetime.fromtimestamp(i["mtime"]))
            virou = data_item != grupo
            grupo = data_item
            yield i, (data_item if virou else None)

    def _montar_detalhes(self, itens, t, cartoes):
        sequencia = []
        for i, cabecalho in self._agrupado_por_data(itens):
            if cabecalho:
                sequencia.append((self._cabecalho_data(cabecalho, t),
                                  {"anchor": "w", "padx": 4, "pady": (10, 4)}))
            sequencia.append((cartoes[i["name"]], {"fill": "x", "pady": 4, "padx": (0, 12)}))
        self._empacotar_em_ordem(sequencia)

    def _montar_grade(self, itens, t, cartoes):
        """Junta as celulas e deixa o posicionamento com o recolunador.

        As celulas ficam guardadas em `_celulas_grade` porque mudar a largura
        da janela so reposiciona: refazer as miniaturas a cada arrasto de borda
        deixaria o redimensionamento travado.
        """
        for i, cabecalho in self._agrupado_por_data(itens):
            if cabecalho:
                self._celulas_grade.append(("cabecalho", self._cabecalho_data(cabecalho, t)))
            self._celulas_grade.append(("celula", cartoes[i["name"]]))
        self._reposicionar_grade(forcar=True)

    def _reposicionar_grade(self, forcar=False):
        if not self._celulas_grade or self.modo_visualizacao == "detalhes":
            return
        largura = self.canvas_lista.winfo_width()
        if largura <= 1:
            self._tentar_grade_depois()
            return
        passo = getattr(self, "_larg_celula", LARGURA_ICONE_MIN)
        colunas = max(1, int((largura - 8) // (passo + ESPACO_CELULA)))
        if colunas == self._colunas_grade and not forcar:
            return
        self._colunas_grade = colunas
        self._tentativas_grade = 0

        linha = coluna = 0
        for tipo, w in self._celulas_grade:
            if tipo == "cabecalho":
                if coluna:
                    linha += 1
                    coluna = 0
                w.grid(row=linha, column=0, columnspan=colunas, sticky="w",
                       padx=4, pady=(10, 4))
                linha += 1
                continue
            w.grid(row=linha, column=coluna, sticky="nw",
                   padx=ESPACO_CELULA // 2, pady=ESPACO_CELULA // 2)
            coluna += 1
            if coluna >= colunas:
                coluna = 0
                linha += 1
        self._agendar_scrollregion()

    def _tentar_grade_depois(self):
        """Repete o posicionamento enquanto o canvas não tiver largura útil.

        Logo depois de remontar a interface (troca de tema ou de tamanho de
        fonte) o canvas ainda não foi mapeado e `winfo_width()` devolve 1.
        Esperar só pelo <Configure> não basta: ele nem sempre chega, e a lista
        ficava montada porém com nada posicionado — as capturas sumiam até o
        próximo clique num filtro. O teto de tentativas evita ficar insistindo
        para sempre com a janela escondida.
        """
        if getattr(self, "_job_grade", None):
            return
        if self._tentativas_grade >= MAX_TENTATIVAS_GRADE:
            return
        self._tentativas_grade += 1
        try:
            self._job_grade = self.root.after(25, self._retomar_grade)
        except Exception:
            self._job_grade = None

    def _retomar_grade(self):
        self._job_grade = None
        try:
            self._reposicionar_grade(forcar=True)
        except Exception:
            pass          # a tentativa pode cair depois de a janela ser fechada

    def _agendar_scrollregion(self):
        """Recalcula a area rolavel fora do tratador do evento.

        O recolunamento roda dentro de um <Configure>, e forcar o Tk a
        processar pendencias ali dentro reentra no laco de eventos dele.
        Adiar para o proximo ocioso mantem o calculo sem essa reentrancia.
        """
        if getattr(self, "_job_scroll", None):
            return
        try:
            self._job_scroll = self.root.after_idle(self._aplicar_scrollregion)
        except Exception:
            self._job_scroll = None

    def _aplicar_scrollregion(self):
        self._job_scroll = None
        try:
            self.canvas_lista.config(scrollregion=self.canvas_lista.bbox("all"))
        except Exception:
            pass

    # ---------- pecas comuns as tres visualizacoes ----------

    def _moldura_card(self, selecionada, t, largura=None, altura=None):
        card = tk.Frame(self.frame_lista,
                        bg=t["accent_bg"] if selecionada else t["bg_panel"],
                        highlightbackground=t["accent"] if selecionada else t["border_soft"],
                        highlightthickness=1)
        if largura:
            card.config(width=largura, height=altura)
            card.grid_propagate(False)
            card.pack_propagate(False)
        return card

    def _medir_celula(self, itens):
        """Define largura e altura da celula a partir do maior rotulo visivel."""
        fonte = tkfont.Font(family=theme.FONT, size=theme.FS_CAPTION, weight="bold")
        linha = fonte.metrics("linespace")
        maior = max((fonte.measure(self._rotulo_item(i)) for i in itens), default=0)
        if self.modo_visualizacao == "blocos":
            # o texto divide a celula com a miniatura e os espacamentos
            reserva = LADO_MINIATURA_BLOCO + 24
            self._larg_celula = max(LARGURA_BLOCO_MIN,
                                    min(LARGURA_BLOCO_MAX, maior + reserva))
            self._alt_celula = max(2 * linha + 24, LADO_MINIATURA_BLOCO - 8)
        else:
            self._larg_celula = max(LARGURA_ICONE_MIN,
                                    min(LARGURA_ICONE_MAX, maior + 14))
            self._alt_celula = ALTURA_MINIATURA_ICONE + 18 + linha

    def _rotulo_item(self, item):
        """Legenda do card, ou o nome do arquivo sem a extensao.

        O ".png" nao informa nada e e justamente o que faz o nome quebrar
        linha nas celulas estreitas das visoes em bloco e em grade.
        """
        return item["caption"] or os.path.splitext(item["name"])[0]

    def _miniatura(self, pai, item, tamanho, t):
        try:
            # do cache: decodificar o PNG inteiro a cada atualização congelava
            # a lista por segundos quando havia muitas capturas
            img_tk = ImageTk.PhotoImage(capture_store.miniatura(item["path"], tamanho))
            lbl = tk.Label(pai, image=img_tk, bg=t["bg_input"])
            # a referência mora no rótulo: o cartão é reaproveitado entre
            # atualizações, e a imagem precisa viver enquanto ele viver
            lbl.image = img_tk
        except Exception:
            lbl = tk.Label(pai, text="?", bg=t["bg_input"], fg=t["text_muted"])
        lbl.pack(expand=True)
        return lbl

    def _imagem_marca(self, selecionada):
        """A marca de seleção é a mesma em todos os cartões: uma PhotoImage
        por estado basta, em vez de desenhar uma por cartão a cada atualização."""
        cache = self.__dict__.setdefault("_marcas_tk", {})
        chave = (self.modo_escuro, selecionada)
        if chave not in cache:
            cache[chave] = ImageTk.PhotoImage(widgets.marca_selecao(self.modo_escuro, selecionada))
        return cache[chave]

    def _marca_selecao(self, pai, selecionada, t):
        img = self._imagem_marca(selecionada)
        marca = tk.Label(pai, image=img, bg=t["bg_input"], bd=0, highlightthickness=0)
        marca.place(x=2, y=2)
        return marca

    def _finalizar_card(self, nome, item, card, clicaveis, arrastaveis, refs):
        """Liga selecao, edicao, copia e arrasto - igual nas tres visoes."""
        refs["selecionada"] = nome in self.arquivos_selecionados   # como foi pintado
        self.cards[nome] = refs
        for widget in clicaveis:
            widget.bind("<Button-1>", lambda e, n=nome: self._alternar_selecao(n))
            widget.bind("<Double-Button-1>", lambda e, p=item["path"]: self.abrir_editor(p))
            widget.bind("<Button-3>", lambda e, p=item["path"]: self.copiar_clipboard(p))
        # Arrastar a captura pra fora do app (ex.: soltar num navegador/chat).
        # O tkdnd so dispara o drag de verdade quando o mouse se move alem de
        # um limiar com o botao pressionado - um clique simples continua
        # caindo nos binds de selecao acima, sem conflito.
        for widget in arrastaveis:
            widget.drag_source_register(1, DND_FILES)
            widget.dnd_bind("<<DragInitCmd>>",
                             lambda e, p=item["path"]: (COPY, DND_FILES, "{%s}" % p))

    def _criar_bloco(self, i, t):
        """Bloco: miniatura a esquerda, legenda e dimensoes a direita."""
        nome = i["name"]
        selecionada = nome in self.arquivos_selecionados
        card = self._moldura_card(selecionada, t, self._larg_celula, self._alt_celula)

        thumb_wrap = tk.Frame(card, bg=t["bg_input"],
                              width=LADO_MINIATURA_BLOCO, height=self._alt_celula - 12)
        thumb_wrap.pack_propagate(False)
        thumb_wrap.pack(side="left", padx=6, pady=6)
        lbl_img = self._miniatura(thumb_wrap, i,
                                  (LADO_MINIATURA_BLOCO - 2, self._alt_celula - 14), t)
        marca = self._marca_selecao(thumb_wrap, selecionada, t)

        info = tk.Frame(card, bg=card["bg"])
        info.pack(side="left", fill="both", expand=True, pady=6, padx=(0, 6))
        lbl_titulo = tk.Label(info, text=self._rotulo_item(i), bg=card["bg"],
                               fg=t["text_primary"], anchor="w",
                               font=(theme.FONT, theme.FS_CAPTION, "bold"))
        lbl_titulo.pack(fill="x")
        lbl_sub = tk.Label(info, text="{0}x{1}".format(i["dims"][0], i["dims"][1]),
                            bg=card["bg"], fg=t["text_tertiary"], anchor="w",
                            font=(theme.FONT, theme.FS_CAPTION))
        lbl_sub.pack(fill="x")

        self._finalizar_card(nome, i, card,
                             (card, thumb_wrap, lbl_img, info, lbl_titulo, lbl_sub),
                             (card, thumb_wrap, lbl_img),
                             {"card": card, "marca": marca, "fundos": (info,),
                              "info_labels": (lbl_titulo, lbl_sub)})
        return card

    def _criar_icone(self, i, t):
        """Grade: so a miniatura, com a legenda compacta embaixo."""
        nome = i["name"]
        selecionada = nome in self.arquivos_selecionados
        card = self._moldura_card(selecionada, t, self._larg_celula, self._alt_celula)

        thumb_wrap = tk.Frame(card, bg=t["bg_input"], width=self._larg_celula - 16,
                              height=ALTURA_MINIATURA_ICONE)
        thumb_wrap.pack_propagate(False)
        thumb_wrap.pack(padx=8, pady=(8, 4))
        lbl_img = self._miniatura(thumb_wrap, i,
                                  (self._larg_celula - 20, ALTURA_MINIATURA_ICONE - 4), t)
        marca = self._marca_selecao(thumb_wrap, selecionada, t)

        # wraplength fixo e altura travada no card: a legenda ocupa ate duas
        # linhas e o que passar disso fica cortado, como no Explorer.
        lbl_titulo = tk.Label(card, text=self._rotulo_item(i), bg=card["bg"],
                               fg=t["text_primary"], justify="center",
                               wraplength=self._larg_celula - 12,
                               font=(theme.FONT, theme.FS_CAPTION, "bold"))
        lbl_titulo.pack(fill="x", padx=4)

        self._finalizar_card(nome, i, card,
                             (card, thumb_wrap, lbl_img, lbl_titulo),
                             (card, thumb_wrap, lbl_img),
                             {"card": card, "marca": marca, "fundos": (),
                              "info_labels": (lbl_titulo,)})
        return card

    def _criar_card(self, i, t):
        nome = i["name"]
        selecionada = nome in self.arquivos_selecionados
        card = self._moldura_card(selecionada, t)

        thumb_wrap = tk.Frame(card, bg=t["bg_input"], width=118, height=74)
        thumb_wrap.pack_propagate(False)
        thumb_wrap.pack(side="left", padx=9, pady=9)
        lbl_img = self._miniatura(thumb_wrap, i, (116, 72), t)
        marca = self._marca_selecao(thumb_wrap, selecionada, t)

        info = tk.Frame(card, bg=card["bg"])
        info.pack(side="left", fill="both", expand=True, pady=9, padx=(0, 10))
        titulo = self._rotulo_item(i)
        lbl_titulo = widgets.texto_fluido(info, titulo, self.modo_escuro, bg=card["bg"],
                                           cor="text_primary",
                                           fonte=(theme.FONT, theme.FS_BODY, "bold"))
        lbl_titulo.pack(fill="x")
        hora = datetime.fromtimestamp(i["mtime"]).strftime("%H:%M")
        sub = f"{hora} · {i['dims'][0]}×{i['dims'][1]}" + (" · editada" if i["edited"] else "")
        lbl_sub = tk.Label(info, text=sub, bg=card["bg"], fg=t["text_tertiary"],
                           font=(theme.FONT, theme.FS_CAPTION), anchor="w")
        lbl_sub.pack(fill="x")
        if i.get("caso") or i["shape_count"]:
            chips = tk.Frame(info, bg=card["bg"])
            chips.pack(anchor="w", pady=(3, 0))
            if i.get("caso"):
                tk.Label(chips, text=i["caso"], bg=t["accent_bg_strong"], fg=t["accent"],
                         font=(theme.FONT, theme.FS_CAPTION, "bold")).pack(side="left", padx=(0, 4))
            if i["shape_count"]:
                tk.Label(chips, text=f"{i['shape_count']} anotações",
                         bg=t["success_bg"], fg=t["success_text"],
                         font=(theme.FONT, theme.FS_CAPTION, "bold")).pack(side="left")

        self._finalizar_card(nome, i, card,
                             (card, thumb_wrap, lbl_img, info, lbl_titulo, lbl_sub),
                             (card, thumb_wrap, lbl_img),
                             {"card": card, "marca": marca, "fundos": (info,),
                              "info_labels": (lbl_titulo, lbl_sub)})
        return card

    def _atualizar_aparencia_card(self, nome):
        ref = self.cards.get(nome)
        if not ref:
            return
        t = theme.get(self.modo_escuro)
        selecionada = nome in self.arquivos_selecionados
        if ref.get("selecionada") == selecionada:
            return            # já está pintado assim (cartão reaproveitado)
        ref["selecionada"] = selecionada
        bg = t["accent_bg"] if selecionada else t["bg_panel"]
        ref["card"].config(bg=bg,
                           highlightbackground=t["accent"] if selecionada else t["border_soft"])
        for widget in ref.get("fundos", ()):
            widget.config(bg=bg)
        for lbl in ref["info_labels"]:
            lbl.config(bg=bg)
        ref["marca"].config(image=self._imagem_marca(selecionada))

    def abrir_editor(self, caminho):
        return editor.EditorImagem(self.root, caminho, self.atualizar_galeria,
                                    self.modo_escuro, app=self)

    def _atualizar_contador(self):
        self.lbl_selecionadas.config(
            text=f"{len(self.arquivos_selecionados)} capturas selecionadas")

    def _avisar_rodape(self, texto, ms=2500):
        """Recado curto no lugar do contador, em vez de caixa de diálogo.

        Copiar é uma ação frequente: um modal para cada Ctrl+C atrapalharia
        mais do que informaria.
        """
        if getattr(self, "_job_aviso", None):
            try:
                self.root.after_cancel(self._job_aviso)
            except Exception:
                pass
        self.lbl_selecionadas.config(text=texto)
        self._job_aviso = self.root.after(ms, self._encerrar_aviso)

    def _encerrar_aviso(self):
        self._job_aviso = None
        self._atualizar_contador()

    def copiar_clipboard(self, caminho):
        """Manda uma captura para a área de transferência (botão direito)."""
        self._copiar_caminhos([caminho])

    def copiar_selecionadas(self, event=None):
        """Ctrl+C no painel: copia as capturas marcadas.

        Dentro de um campo de texto o Ctrl+C pertence ao campo — sequestrá-lo
        quebraria copiar o termo digitado na busca.
        """
        try:
            foco = self.root.focus_get()
        except Exception:
            foco = None
        if isinstance(foco, (tk.Entry, tk.Text)):
            return None

        caminhos = [os.path.join(self.pasta_capturas, nome)
                    for nome in sorted(self.arquivos_selecionados)]
        caminhos = [c for c in caminhos if os.path.exists(c)]
        if not caminhos:
            self._avisar_rodape("Selecione uma captura")
            return "break"
        self._copiar_caminhos(caminhos)
        return "break"

    def _copiar_caminhos(self, caminhos):
        """Publica as capturas como imagem e como arquivo ao mesmo tempo.

        A imagem só acompanha quando é uma só, porque a área de transferência
        do Windows guarda um bitmap de cada vez; com várias, o que serve é a
        lista de arquivos (colar no Explorer, anexar no e-mail).
        """
        try:
            imagem = Image.open(caminhos[0]) if len(caminhos) == 1 else None
            utils.copy_to_clipboard(image=imagem, paths=caminhos)
        except Exception:
            self._avisar_rodape("Não foi possível copiar")
            return
        if len(caminhos) == 1:
            self._avisar_rodape("Captura copiada")
        else:
            self._avisar_rodape(f"{len(caminhos)} capturas copiadas")

    # ---------- captura de tela ----------

    def iniciar_seletor(self):
        if self._capturando:
            return
        self._capturando = True
        self.root.withdraw()
        self.root.after(200, self.executar_captura)

    def executar_captura(self):
        seletor.SeletorDeArea(self)

    def iniciar_captura_janela_ativa(self):
        if self._capturando:
            return
        self._capturando = True
        self.root.after(50, self._executar_captura_janela_ativa)

    def _executar_captura_janela_ativa(self):
        import win32gui
        self._capturando = False
        try:
            hwnd_alvo = win32gui.GetForegroundWindow()
            # medida sem a moldura invisível do Windows, senão a captura sai
            # com uma tira a mais em volta da janela
            retangulo = deteccao_janelas.retangulo_visivel(hwnd_alvo)
            if not retangulo:
                return
            x1, y1, x2, y2 = retangulo
        except Exception:
            return
        if x2 - x1 < 10 or y2 - y1 < 10:
            return
        imagem = ImageGrab.grab(bbox=(x1, y1, x2, y2), all_screens=True)
        if self.config.get("incluir_cursor", False):
            imagem = captura_utils.colar_cursor(imagem, offset=(x1, y1))
        self._guardar_ultima_area((x1, y1, x2, y2))
        self._salvar_captura(imagem)

    def _guardar_ultima_area(self, area):
        """Guarda a área em coordenadas ABSOLUTAS, que é o referencial que o
        ImageGrab.grab(bbox=...) espera — inclusive com valores negativos em
        monitor à esquerda do principal."""
        self.config["ultima_area"] = list(area)
        config.save(self.data_dir, self.config)

    def recapturar_ultima_area(self):
        """Shift+PrintScreen: repete exatamente o último recorte."""
        if self._capturando:
            return
        area = self.config.get("ultima_area")
        if not area or len(area) != 4:
            # nada pra repetir ainda: cai no seletor normal em vez de não
            # fazer nada, que pareceria que o atalho está quebrado
            self.iniciar_seletor()
            return
        x1, y1, x2, y2 = area
        if x2 - x1 < 10 or y2 - y1 < 10:
            self.iniciar_seletor()
            return
        try:
            imagem = ImageGrab.grab(bbox=(x1, y1, x2, y2), all_screens=True)
        except Exception:
            self.iniciar_seletor()
            return
        if self.config.get("incluir_cursor", False):
            imagem = captura_utils.colar_cursor(imagem, offset=(x1, y1))
        self._salvar_captura(imagem)

    def _salvar_captura(self, imagem):
        nome = captura_utils.nome_livre(self.pasta_capturas,
                                        self.config.get("padrao_nome", "data_hora"))
        caminho = os.path.join(self.pasta_capturas, nome)
        imagem.save(caminho)
        try:
            # o instante da captura ordena o documento; o nome só tem HHMMSS no
            # padrão `hora`, e o mtime muda quando o print é editado
            capture_store.registrar_captura(caminho)
        except Exception as e:
            print(f"[captura] não foi possível gravar o instante: {e}")
        if self.config.get("copiar_apos_captura", True):
            # deixa a captura pronta pra colar com Ctrl+V em qualquer programa,
            # sem precisar arrastar o card nem usar o botão direito
            try:
                utils.copy_image_to_clipboard(imagem)
            except Exception as e:
                print(f"[captura] não foi possível copiar pra área de transferência: {e}")
        if self.config.get("som_captura", True):
            captura_utils.tocar_som_captura()
        if self.config.get("abrir_apos_captura", True):
            self.mostrar_janela()
        self.atualizar_galeria()

    # ---------- documento / limpeza ----------

    def abrir_montar_documento(self):
        if not self.arquivos_selecionados:
            messagebox.showinfo("Criar documento", "Selecione ao menos uma captura antes.")
            return
        from gestor.ui import document_builder
        document_builder.MontarDocumento(self, set(self.arquivos_selecionados))

    def excluir_selecionadas_ou_tudo(self):
        """Botão de lixeira do painel: exclui só as capturas selecionadas.
        Sem nada selecionado, pergunta se quer apagar a pasta inteira."""
        if self.arquivos_selecionados:
            n = len(self.arquivos_selecionados)
            alvo = "1 captura selecionada" if n == 1 else f"{n} capturas selecionadas"
            if not messagebox.askyesno(
                    "Excluir", f"Mover {alvo} para a Lixeira do Windows?"):
                return
            falharam = 0
            for nome in list(self.arquivos_selecionados):
                if not capture_store.delete_capture(
                        os.path.join(self.pasta_capturas, nome)):
                    falharam += 1
            self.arquivos_selecionados.clear()
            self.atualizar_galeria()
            if falharam:
                messagebox.showwarning(
                    "Excluir",
                    f"{falharam} captura(s) não puderam ir para a Lixeira e "
                    "foram mantidas.")
        else:
            self.limpar_pasta_completa()

    def limpar_pasta_completa(self):
        """Esvazia a pasta de capturas, mandando tudo para a Lixeira.

        Os arquivos vao numa operacao so: restaurar depois e um comando
        unico na Lixeira, e nao item por item.
        """
        if not messagebox.askyesno(
                "Limpar", "Mover todas as capturas da pasta para a Lixeira "
                          "do Windows?"):
            return
        # Só as capturas e os arquivos irmãos delas (o que a galeria mostra e o
        # que a pergunta promete). Antes ia tudo o que estivesse na pasta —
        # uma planilha ou anotação guardada ali junto ia para a Lixeira também.
        alvos = []
        for nome in os.listdir(self.pasta_capturas):
            baixo = nome.lower()
            caminho = os.path.join(self.pasta_capturas, nome)
            if (not os.path.isfile(caminho) or not baixo.endswith(".png")
                    or baixo.endswith(".raw.png")):
                continue
            alvos.extend(p for p in (caminho, capture_store.raw_path(caminho),
                                     capture_store.json_path(caminho),
                                     capture_store.txt_path(caminho))
                         if os.path.exists(p))
        if alvos and not utils.mover_para_lixeira(alvos):
            messagebox.showwarning(
                "Limpar", "Não foi possível mover as capturas para a Lixeira. "
                          "Nada foi apagado.")
            return
        self.arquivos_selecionados.clear()
        self.atualizar_galeria()

    # ---------- configurações ----------

    def abrir_configuracoes(self):
        configuracoes.abrir(self)

    # ---------- tema / bandeja / inatividade ----------

    def alternar_tema(self):
        self.modo_escuro = not self.modo_escuro
        self._reconstruir_ui()

    def criar_icone_bandeja(self):
        caminho_ico = widgets.caminho_icone()
        if caminho_ico:
            img_bandeja = Image.open(caminho_ico)
        else:
            img_bandeja = Image.new("RGB", (64, 64), (11, 114, 133))
        # O pystray chama o menu na thread DELE, e o Tkinter só pode ser usado
        # da thread do Tk — a mesma regra que o hotkey.py segue. O menu apenas
        # enfileira o pedido; quem executa é a drenagem, na thread do Tk.
        self._pedidos_bandeja = queue.Queue()
        menu = (item("Abrir Gestor",
                     lambda icone, it: self._pedidos_bandeja.put(self.mostrar_janela),
                     default=True),
                item("Sair", lambda icone, it: self._pedidos_bandeja.put(self.sair_total)))
        self.icon = pystray.Icon("GestorEvidencias", img_bandeja, "Gestor de Evidências", menu)
        threading.Thread(target=self.icon.run, daemon=True).start()
        self.root.after(_INTERVALO_BANDEJA_MS, self._drenar_bandeja)

    def _drenar_bandeja(self):
        """Executa, na thread do Tk, o que foi pedido pelo menu da bandeja."""
        while True:
            try:
                pedido = self._pedidos_bandeja.get_nowait()
            except queue.Empty:
                break
            try:
                pedido()
            except Exception as e:
                print(f"[bandeja] falha ao executar o pedido: {e}")
        try:
            self.root.after(_INTERVALO_BANDEJA_MS, self._drenar_bandeja)
        except Exception:
            pass          # a janela já foi encerrada

    def resetar_timer(self, event=None):
        if self.job_inatividade:
            self.root.after_cancel(self.job_inatividade)
        if not self.pausar_timer:
            self.job_inatividade = self.root.after(
                self.tempo_limite, self._esconder_por_inatividade)

    def _esconder_por_inatividade(self):
        """Esconder automático. Respeita a pausa e não some com o painel
        enquanto o editor está aberto."""
        if self.pausar_timer:
            return
        # Qualquer janela auxiliar aberta (editor, Montar documento, prévia)
        # segura o painel: com a raiz escondida o Tk não mapeia as Toplevels
        # filhas dela, e o trabalho em andamento sumiria da tela.
        if any(isinstance(c, tk.Toplevel) for c in self.root.winfo_children()):
            return
        self.root.withdraw()

    def esconder_janela(self):
        """Fecha a pedido do usuário (botão X): esconde incondicionalmente.

        Separado de `_esconder_por_inatividade` de propósito — este não pode
        respeitar `pausar_timer`, ou uma janela auxiliar que não reponha a
        pausa deixa o X sem resposta.
        """
        self.root.withdraw()

    def mostrar_janela(self, icon=None, item=None):
        self.root.deiconify()
        self.root.lift()
        self.root.focus_set()
        self.resetar_timer()

    def sair_total(self, icon=None, item=None):
        if self.hotkeys:
            self.hotkeys.parar()
        self.icon.stop()
        self.root.quit()
