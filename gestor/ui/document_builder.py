"""Tela 'Montar documento' (design '1c'): reordena as capturas selecionadas,
preenche a capa, edita a legenda de cada uma, escolhe o modelo e as opções,
e segue pra pré-visualização/exportação."""
import os
from datetime import datetime
from tkinter import Toplevel, messagebox
import tkinter as tk

from PIL import Image, ImageDraw, ImageFont, ImageOps, ImageTk

from gestor.dados import capture_store
from gestor.dados import config
from gestor.ui import editor
from gestor.ui import theme
from gestor.ui import widgets

# Miniatura da coluna de sequência: cabe na largura do card (coluna de ~230px
# menos a barra de rolagem e os espaçamentos) e é alta o bastante pra dar pra
# reconhecer o print.
_LARGURA_MINIATURA = 168
_ALTURA_MINIATURA = 112
# Deslocamento (px) a partir do qual o movimento do mouse deixa de ser clique e
# passa a ser arraste de reordenação.
_LIMIAR_ARRASTE = 5
# Margem (fração da altura do cartão) que o ponteiro precisa passar do meio de
# um cartão para o vão trocar de lugar. Sem ela, com o ponteiro parado sobre o
# meio, o vão ficaria pulando entre duas posições.
_FOLGA_TROCA = 0.15
# pady de cima e de baixo de cada cartão da sequência (4 + 4)
_FOLGA_CARTAO = 8
# Rolagem automática: faixa junto às bordas (px), velocidade em px por tick e
# intervalo do tick (ms).
_ZONA_AUTOSCROLL = 70
_AUTOSCROLL_MIN = 4
_AUTOSCROLL_MAX = 34
_AUTOSCROLL_MS = 20
# Quanto tempo o aviso "Movido para a posição N · Desfazer" fica na tela.
_AVISO_MS = 6000


def calcular_destino(y, mids, atual, margem):
    """Posição de inserção (0..len(mids)) para um ponteiro na altura `y`.

    `mids` são os pontos médios dos cartões que NÃO estão sendo levados, no
    layout sem o vão. A posição só muda depois que o ponteiro passa do meio do
    cartão por `margem`, nos dois sentidos: é essa folga que impede o vão de
    oscilar quando o ponteiro para exatamente sobre o meio.
    """
    d = atual
    while d > 0 and y < mids[d - 1] - margem:
        d -= 1
    while d < len(mids) and y > mids[d] + margem:
        d += 1
    return d


_FONTE_NUMERO = []


def _fonte_numero():
    """A fonte do número, carregada uma vez só.

    `ImageFont.truetype` procura o arquivo pelas pastas de fontes do Windows e
    leva ~20 ms por chamada. Com o número sendo redesenhado a cada passo do
    arraste, carregar a fonte toda vez custava mais que todo o resto.
    """
    if not _FONTE_NUMERO:
        try:
            _FONTE_NUMERO.append(ImageFont.truetype("segoeuib.ttf", 13))
        except Exception:
            _FONTE_NUMERO.append(ImageFont.load_default())
    return _FONTE_NUMERO[0]


def _posicionar_em_ordem(mestre, frames, depois_de=None, **opcoes):
    """Põe `frames` na ordem dada dentro de `mestre`, sem desmapeá-los.

    `pack_forget` seguido de `pack` desmonta e remonta a subárvore inteira de
    cada cartão (dezenas de janelas do Windows) e custava centenas de ms por
    reordenação; reposicionar com before/after apenas move o que já está lá.
    `depois_de` é o widget que deve ficar antes de todos (a capa, na coluna
    central).
    """
    anterior = depois_de
    for f in frames:
        slaves = mestre.pack_slaves()
        if f.winfo_manager() != "pack":
            if anterior is not None:
                f.pack(after=anterior, **opcoes)
            elif slaves:
                f.pack(before=slaves[0], **opcoes)
            else:
                f.pack(**opcoes)
        elif anterior is None:
            if slaves[0] is not f:
                f.pack_configure(before=slaves[0], **opcoes)
        else:
            i = slaves.index(anterior)
            if i + 1 >= len(slaves) or slaves[i + 1] is not f:
                f.pack_configure(after=anterior, **opcoes)
        anterior = f


def _com_numero(imagem, numero, cor_hex):
    """Desenha o número do passo no canto da própria miniatura.

    Desenhar no bitmap em vez de sobrepor um Label com `place`: sobre um
    Label de imagem o posicionamento depende de como o widget centraliza o
    conteúdo, e o badge acabava fora do canto em imagens mais estreitas.
    """
    desenho = ImageDraw.Draw(imagem)
    fonte = _fonte_numero()
    texto = str(numero)
    caixa = desenho.textbbox((0, 0), texto, font=fonte)
    larg = (caixa[2] - caixa[0]) + 12
    alt = (caixa[3] - caixa[1]) + 10
    desenho.rectangle([0, 0, larg, alt], fill=cor_hex)
    desenho.text((larg / 2, alt / 2), texto, font=fonte, fill="#ffffff", anchor="mm")
    return imagem


MODELOS_UI = [
    ("passo", "Passo a passo", "1 imagem por passo, legenda acima"),
    ("ficha", "Ficha", "2 por página, com metadados"),
    ("qa", "Relatório", "coluna lateral com contexto"),
]

# Título que a capa traz quando o usuário ainda não escreveu o dele, por modelo.
TITULOS_PADRAO = {
    "passo": "Evidências passo a passo",
    "ficha": "Evidências de Testes",
    "qa": "Relatório de Evidências",
}


def titulo_padrao(modelo):
    return TITULOS_PADRAO.get(modelo, TITULOS_PADRAO["passo"])


def titulo_ao_trocar_modelo(atual, modelo_anterior, modelo_novo):
    """O texto que o campo Título deve ter depois de trocar de modelo.

    Só acompanha o modelo quem ainda mostra o padrão do modelo ANTERIOR; um
    título digitado pelo usuário (inclusive vazio, apagado de propósito) fica
    como está, senão trocar de modelo desfaria o que ele escreveu.
    """
    if atual == titulo_padrao(modelo_anterior):
        return titulo_padrao(modelo_novo)
    return atual


class MontarDocumento(Toplevel):
    def __init__(self, parent_app, nomes_selecionados):
        super().__init__(parent_app.root)
        self.parent_app = parent_app
        self.title("Montar documento")
        self.state("zoomed")
        t = theme.get(parent_app.modo_escuro)
        self.configure(bg=t["bg_content"])

        # Uma lista de referências por coluna, e não uma só para as duas: as
        # colunas são reconstruídas separadamente e em ordens diferentes (as
        # setas fazem sequência→centro, o arraste faz centro→sequência). Com a
        # lista compartilhada, quem reconstruía por último zerava as
        # referências da outra e as miniaturas sumiam da tela.
        self.imagens_sequencia = []
        self.imagens_passos = []
        self._capa_digitada = {}
        self.passos = []
        carregados, instantes = {}, []
        for nome in nomes_selecionados:
            caminho = os.path.join(parent_app.pasta_capturas, nome)
            if not os.path.exists(caminho):
                continue
            meta = capture_store.load_meta(caminho)
            instante = capture_store.instante_da_captura(caminho, meta)
            try:
                # print antigo recebe o instante agora: depois de uma edição o
                # mtime deixa de servir, e a ordem do documento mudaria
                capture_store.garantir_captured_at(caminho, meta)
            except Exception:
                pass          # arquivo bloqueado: o instante estimado serve por agora
            carregados[caminho] = {"nome": nome, "caminho": caminho,
                                   "legenda": meta.get("caption", ""), "instante": instante}
            instantes.append((caminho, instante))
        # O documento é uma sequência de passos: nasce do início ao fim do
        # processo. Antes ordenava pelo nome em ordem decrescente — a ordem da
        # galeria, que mostra o mais novo primeiro — e o último print virava o
        # passo 1. A seleção da galeria é um set: sem esta ordenação, ela não
        # teria ordem nenhuma.
        self.passos = [carregados[c] for c in capture_store.ordenar_instantes(instantes)]
        self._modo_ordem = "cronologica"      # cronologica | recentes | manual

        self.var_modelo = tk.StringVar(value="passo")
        self.var_cor = tk.StringVar(value="#0B7285")
        self.var_numerar = tk.BooleanVar(value=True)
        self.var_borda = tk.BooleanVar(value=parent_app.config.get("borda_ativada", False))

        self.entries_capa = {}
        self.frame_passos = None
        self.lbl_paginas = None
        self._cards = []
        self._arraste = None
        self._editor = None          # editor de imagem aberto a partir daqui
        self._previas = []           # prévias abertas, para regerar após editar
        self._canvas_central = None
        self.entries_legenda = {}
        self._cartoes = {}           # cartões da sequência, por caminho
        self._cartoes_centro = {}    # cartões da coluna central, por caminho
        self._caminhos_fotos_centro = []   # a quem pertence cada item de imagens_passos
        self._cache_thumbs = {}      # miniaturas em PIL, por arquivo
        self._fantasma = None
        self._selecionado = None           # caminho do cartão alvo do Alt+seta
        self._ordem_antes_mover = None     # para o "Desfazer"
        self._modo_antes_mover = "cronologica"   # e o modo de ordem de antes
        self._aviso_job = None

        self._montar_ui(t)
        self.protocol("WM_DELETE_WINDOW", self.destroy)
        # Esc cancela o arraste em curso; Ctrl+Z desfaz a última movimentação.
        self.bind("<Escape>", self._arraste_cancelar, add="+")
        self.bind("<Control-z>", self._atalho_desfazer, add="+")
        # Alt+↑ / Alt+↓ movem o cartão selecionado (o último em que se clicou).
        self.bind("<Alt-Up>", lambda e: self._mover_pelo_teclado(-1, e), add="+")
        self.bind("<Alt-Down>", lambda e: self._mover_pelo_teclado(1, e), add="+")

    # ---------- UI ----------

    def _montar_ui(self, t):
        titlebar = tk.Frame(self, bg=t["bg_header"], height=42)
        titlebar.pack(fill="x")
        titlebar.pack_propagate(False)
        tk.Label(titlebar, text=f"Novo documento · {len(self.passos)} capturas", bg=t["bg_header"],
                 fg=t["text_secondary"], font=(theme.FONT, theme.FS_BODY)).pack(
                     side="left", padx=(14, 0))

        # As três colunas ficam num PanedWindow em vez de larguras fixas:
        # dá pra arrastar as divisas e dar mais espaço pra coluna central
        # (onde se edita de fato), que é o conteúdo principal da tela.
        corpo = tk.PanedWindow(self, orient="horizontal", bg=t["border_soft"],
                                sashwidth=6, sashrelief="flat", bd=0, opaqueresize=True)
        corpo.pack(fill="both", expand=True)

        self._montar_coluna_sequencia(corpo, t)
        self._montar_coluna_central(corpo, t)
        self._montar_coluna_direita(corpo, t)

    def _montar_coluna_sequencia(self, corpo, t):
        col = tk.Frame(corpo, bg=t["bg_footer"])
        corpo.add(col, minsize=170, width=230, stretch="never")
        tk.Label(col, text="SEQUÊNCIA", bg=t["bg_footer"], fg=t["text_muted"],
                 font=(theme.FONT, theme.FS_EYEBROW, "bold")).pack(
                     anchor="w", padx=14, pady=(14, 0))
        widgets.texto_fluido(col, "arraste pra reordenar · duplo clique na imagem edita · ✕ remove",
                              self.parent_app.modo_escuro,
                              bg=t["bg_footer"]).pack(fill="x", padx=14, pady=(0, 8))

        # Seletor de ordem. O documento nasce do início ao fim; "Mais novos"
        # inverte, e mexer à mão troca ambos por "ordem manual". Os rótulos
        # dizem o que acontece, e não a chave técnica por trás.
        seletor = tk.Frame(col, bg=t["bg_footer"])
        seletor.pack(fill="x", padx=14, pady=(0, 10))
        escuro = self.parent_app.modo_escuro
        pilulas = tk.Frame(seletor, bg=t["bg_footer"])
        pilulas.pack(anchor="w")
        self._pill_cron = widgets.Pill(pilulas, "Cronológica", escuro, bg=t["bg_footer"],
                                       ativo=True, altura=26, fonte_pt=9,
                                       comando=lambda: self._ordenar_por_captura(False))
        self._pill_cron.pack(side="left", padx=(0, 6))
        self._pill_rec = widgets.Pill(pilulas, "Mais novos", escuro, bg=t["bg_footer"],
                                      ativo=False, altura=26, fonte_pt=9,
                                      comando=lambda: self._ordenar_por_captura(True))
        self._pill_rec.pack(side="left")
        # Numa linha própria: ao lado das duas pílulas o texto não cabe nos
        # 230 px da coluna e aparecia cortado.
        self._lbl_ordem_manual = tk.Label(seletor, text="ordem manual", bg=t["bg_footer"],
                                          fg=t["text_muted"], anchor="w",
                                          font=(theme.FONT, theme.FS_CAPTION))
        self._atualizar_pills_ordem()

        # Aviso de movimento com "Desfazer", preso embaixo da coluna. Só é
        # mostrado depois de uma reordenação e some sozinho.
        self._aviso_seq = tk.Frame(col, bg=t["accent_bg"])
        self._lbl_aviso_seq = tk.Label(self._aviso_seq, text="", bg=t["accent_bg"],
                                       fg=t["text_primary"], anchor="w",
                                       font=(theme.FONT, theme.FS_CAPTION))
        self._lbl_aviso_seq.pack(side="left", padx=(10, 4), pady=7)
        desfazer = tk.Label(self._aviso_seq, text="Desfazer", bg=t["accent_bg"], fg=t["accent"],
                            font=(theme.FONT, theme.FS_CAPTION, "bold"), cursor="hand2")
        desfazer.pack(side="right", padx=10)
        desfazer.bind("<Button-1>", lambda e: self._desfazer_movimento())

        wrap = tk.Frame(col, bg=t["bg_footer"])
        wrap.pack(fill="both", expand=True)
        self._wrap_seq = wrap
        canvas = tk.Canvas(wrap, bg=t["bg_footer"], highlightthickness=0, width=1)
        scrollbar = tk.Scrollbar(wrap, orient="vertical", command=canvas.yview)
        self.frame_sequencia = tk.Frame(canvas, bg=t["bg_footer"])
        janela_seq = canvas.create_window((0, 0), window=self.frame_sequencia, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side="left", fill="both", expand=True, padx=(12, 0))
        scrollbar.pack(side="right", fill="y")
        self.frame_sequencia.bind(
            "<Configure>", lambda e: canvas.config(scrollregion=canvas.bbox("all")))
        # prende a largura do conteúdo à do canvas; sem isso os cards mantêm
        # a largura natural e vazam pra fora da coluna em vez de quebrar
        canvas.bind("<Configure>", lambda e: canvas.itemconfig(janela_seq, width=e.width))

        def roda(ev):
            canvas.yview_scroll(int(-1 * (ev.delta / 120)), "units")
            self._arraste_atualizar()      # o conteúdo andou sob o ponteiro
        canvas.bind("<Enter>", lambda e: canvas.bind_all("<MouseWheel>", roda))
        canvas.bind("<Leave>", lambda e: canvas.unbind_all("<MouseWheel>"))
        self._canvas_sequencia = canvas

        self._atualizar_sequencia()

    # ---------- miniaturas (com cache) ----------

    def _miniatura_pil(self, caminho, tamanho):
        """Miniatura em PIL, decodificada do disco só quando o arquivo muda.

        Decodificar o PNG é o custo que importa: reconstruir uma coluna relia
        todas as imagens, e com 14 capturas de tela cheia isso congelava a
        interface por segundos a cada reordenação. Guarda-se o PIL pequeno, e
        não a PhotoImage — essa continua a viver só nas listas de referências.
        """
        st = os.stat(caminho)
        assinatura = (st.st_mtime_ns, st.st_size)
        chave = (caminho, tamanho)
        guardado = self._cache_thumbs.get(chave)
        if guardado and guardado[0] == assinatura:
            return guardado[1]
        grande = (_LARGURA_MINIATURA, _ALTURA_MINIATURA)
        if tamanho == grande:
            with Image.open(caminho) as im:
                img = im.convert("RGB")
            img.thumbnail(grande)
        else:
            img = self._miniatura_pil(caminho, grande).copy()
            img.thumbnail(tamanho)
        self._cache_thumbs[chave] = (assinatura, img)
        return img

    def _indice_de(self, caminho):
        """Posição atual do passo. Os botões e o arraste guardam o caminho, e não
        o índice: com os cartões se movendo no lugar, o índice de quando o
        botão foi criado ficaria velho."""
        for i, passo in enumerate(self.passos):
            if passo["caminho"] == caminho:
                return i
        return -1

    # ---------- coluna Sequência ----------

    def _atualizar_sequencia(self):
        """Reconstrói a coluna do zero (abertura, remoção, volta do editor).

        Reordenar não passa por aqui: ver `_reordenar_em_lugar`.
        """
        t = theme.get(self.parent_app.modo_escuro)
        rolagem = self._canvas_sequencia.yview()[0]
        for w in self.frame_sequencia.winfo_children():
            w.destroy()
        self._cartoes = {}
        for idx, passo in enumerate(self.passos):
            self._cartoes[passo["caminho"]] = self._criar_cartao_seq(passo, idx + 1, t)
        self._empacotar_sequencia()
        self._sincronizar_fotos_seq()
        self._restaurar_rolagem(self._canvas_sequencia, rolagem)
        self._atualizar_paginas()

    def _criar_cartao_seq(self, passo, numero, t):
        caminho = passo["caminho"]
        linha = tk.Frame(self.frame_sequencia, bg=t["bg_input"], cursor="fleur",
                         highlightbackground=t["border_soft"], highlightthickness=2)
        rec = {"frame": linha, "caminho": caminho, "numero": numero,
               "foto": None, "miniatura": None}

        # A miniatura ocupa a largura inteira do card, porque é por ela
        # que o passo é reconhecido: número e controles ficam na linha de
        # cima, e a imagem vem abaixo, sem disputar espaço horizontal.
        topo = tk.Frame(linha, bg=t["bg_input"])
        topo.pack(fill="x", padx=6, pady=(4, 0))

        # Alça de arraste: o cartão inteiro arrasta, mas sem ela ninguém
        # descobre que dá.
        alca = tk.Label(topo, text="⋮⋮", bg=t["bg_input"], fg=t["text_muted"],
                        font=(theme.FONT, theme.FS_SUBTITLE), cursor="fleur", padx=4)
        alca.pack(side="left")

        # Área de clique maior nos controles: eram 5px de padding e ficavam
        # difíceis de acertar. O arraste do card é o caminho principal;
        # estes seguem como ajuste fino de uma posição por vez.
        controles = tk.Frame(topo, bg=t["bg_input"])
        controles.pack(side="right")
        for rotulo, acao in (
                ("✎", lambda c=caminho: self._editar_passo(self._indice_de(c))),
                ("↑", lambda c=caminho: self._mover(self._indice_de(c), -1)),
                ("↓", lambda c=caminho: self._mover(self._indice_de(c), 1)),
                ("✕", lambda c=caminho: self._remover(self._indice_de(c)))):
            alvo = tk.Label(controles, text=rotulo, bg=t["bg_input"],
                             fg=t["danger_text"] if rotulo == "✕" else t["text_tertiary"],
                             font=(theme.FONT, theme.FS_SUBTITLE), cursor="hand2",
                             padx=9, pady=4)
            alvo.pack(side="left")
            alvo.bind("<Button-1>", lambda e, a=acao: a())
            alvo.bind("<Enter>", lambda e, w=alvo: w.config(bg=t["pill_bg"]))
            alvo.bind("<Leave>", lambda e, w=alvo: w.config(bg=t["bg_input"]))

        arrastaveis = [linha, topo, alca]
        # A moldura abraça a imagem em vez de ocupar a largura toda:
        # com prints verticais a miniatura fica estreita e o resto
        # virava um bloco cinza em volta dela.
        moldura = tk.Frame(linha, bg=t["border_soft"])
        moldura.pack(padx=6, pady=(4, 0))
        try:
            base = self._miniatura_pil(caminho, (_LARGURA_MINIATURA, _ALTURA_MINIATURA))
            foto = ImageTk.PhotoImage(_com_numero(base.copy(), numero, t["accent"]))
            rec["foto"] = foto
            miniatura = tk.Label(moldura, image=foto, bg=t["bg_input"], cursor="fleur")
        except Exception:
            # Sem miniatura não há onde dar o duplo clique: o espaço
            # reservado mantém o caminho para o editor (que explica o erro
            # se o arquivo sumiu) e avisa que a imagem não carregou.
            miniatura = tk.Label(moldura, text="imagem indisponível", bg=t["bg_input"],
                                 fg=t["text_muted"], font=(theme.FONT, theme.FS_CAPTION),
                                 width=22, height=4, cursor="fleur")
        miniatura.pack(padx=1, pady=1)
        rec["miniatura"] = miniatura
        arrastaveis.extend((moldura, miniatura))
        # Duplo clique só na imagem, e não no cartão inteiro: o resto do
        # cartão é área de arraste e não deve competir com ele.
        miniatura.bind("<Double-Button-1>",
                       lambda e, c=caminho: self._editar_passo(self._indice_de(c)))

        texto = (passo["legenda"] or passo["nome"])[:60]
        rotulo_texto = widgets.texto_fluido(linha, texto, self.parent_app.modo_escuro,
                                             bg=t["bg_input"], cor="text_primary")
        rotulo_texto.config(cursor="fleur")
        rotulo_texto.pack(fill="x", padx=8, pady=(5, 8))
        arrastaveis.append(rotulo_texto)

        for w in arrastaveis:
            w.bind("<ButtonPress-1>",
                   lambda e, c=caminho: self._arraste_iniciar(self._indice_de(c), e))
            w.bind("<B1-Motion>", self._arraste_mover)
            w.bind("<ButtonRelease-1>", self._arraste_soltar)

        return rec

    def _empacotar_sequencia(self):
        """(Re)posiciona os cartões na ordem de `self.passos`, sem recriá-los
        nem desmapeá-los."""
        recs = [self._cartoes.get(p["caminho"]) for p in self.passos]
        self._cards = [r["frame"] for r in recs if r is not None]
        _posicionar_em_ordem(self.frame_sequencia, self._cards,
                             fill="x", pady=4, padx=(0, 10))
        for passo in self.passos:
            self._estilo_borda(passo["caminho"])

    def _estilo_borda(self, caminho):
        """Borda do cartão: acento no primeiro passo e no cartão selecionado.

        Só a cor muda, nunca a espessura: mexer no tamanho do cartão entre os
        dois cliques de um duplo clique desloca o layout sob o ponteiro.
        """
        rec = self._cartoes.get(caminho)
        if rec is None:
            return
        t = theme.get(self.parent_app.modo_escuro)
        primeiro = bool(self.passos) and self.passos[0]["caminho"] == caminho
        destaque = primeiro or caminho == self._selecionado
        try:
            rec["frame"].config(highlightbackground=t["accent"] if destaque else t["border_soft"])
        except tk.TclError:
            pass

    def _selecionar(self, caminho):
        """Marca um cartão como o alvo de Alt+↑ / Alt+↓.

        É um estado próprio, e não o foco do Tk. Dar foco ao cartão no
        primeiro clique gerava uma cadeia de FocusOut/FocusIn entre os dois
        cliques, e o duplo clique da miniatura passava a falhar de forma
        intermitente com o mouse de verdade.
        """
        anterior, self._selecionado = self._selecionado, caminho
        for c in (anterior, caminho):
            if c is not None:
                self._estilo_borda(c)

    def _sincronizar_fotos_seq(self):
        """As PhotoImage precisam de uma referência viva, senão o Tk as descarta."""
        self.imagens_sequencia = [self._cartoes[p["caminho"]]["foto"] for p in self.passos
                                  if p["caminho"] in self._cartoes
                                  and self._cartoes[p["caminho"]]["foto"] is not None]

    def _numerar(self, rec, numero):
        """Troca o número desenhado na miniatura, só se mudou."""
        if rec["numero"] == numero:
            return
        rec["numero"] = numero
        if rec["foto"] is None:
            return
        t = theme.get(self.parent_app.modo_escuro)
        try:
            base = self._miniatura_pil(rec["caminho"], (_LARGURA_MINIATURA, _ALTURA_MINIATURA))
            foto = ImageTk.PhotoImage(_com_numero(base.copy(), numero, t["accent"]))
        except Exception:
            return
        rec["miniatura"].config(image=foto)
        rec["foto"] = foto

    def _restaurar_rolagem(self, canvas, fracao):
        """Devolve a rolagem de uma coluna reconstruída.

        Reconstruir a coluna recria o conteúdo do zero e a rolagem voltaria ao
        topo: quem edita o passo 9 de 12 acharia que a lista foi perdida. O
        scrollregion só é recalculado no próximo <Configure>, então é
        refeito aqui antes de rolar.
        """
        if fracao <= 0:
            return
        try:
            canvas.update_idletasks()
            canvas.config(scrollregion=canvas.bbox("all"))
            canvas.yview_moveto(fracao)
        except tk.TclError:
            pass

    # ---------- reordenar arrastando ----------
    #
    # Como em qualquer lista de arrastar-e-soltar: um fantasma da miniatura
    # segue o ponteiro, os outros cartões se afastam abrindo um vão do tamanho
    # do cartão levado, e o vão é o destino. O que se vê durante o arraste é
    # exatamente o que sai ao soltar. Perto das bordas a lista rola sozinha.
    # Nada é reconstruído durante nem depois: os mesmos cartões trocam de lugar.

    def _arraste_iniciar(self, idx, event=None):
        if not (0 <= idx < len(self.passos)):
            return
        caminho = self.passos[idx]["caminho"]
        self._selecionar(caminho)
        x0 = getattr(event, "x_root", 0)
        y0 = getattr(event, "y_root", 0)
        self._arraste = {"origem": idx, "caminho": caminho, "destino": idx, "ativo": False,
                         "x0": x0, "y0": y0, "x_root": x0, "y_root": y0, "job": None}

    def _arraste_mover(self, event):
        estado = getattr(self, "_arraste", None)
        if not estado:
            return
        estado["x_root"], estado["y_root"] = event.x_root, event.y_root
        if not estado["ativo"]:
            # Só vira arraste depois de um deslocamento mínimo. Sem o limiar,
            # uma tremida de 1 px entre os dois cliques de um duplo clique
            # contava como arraste, e o gesto do duplo clique falhava.
            if max(abs(event.x_root - estado["x0"]),
                   abs(event.y_root - estado["y0"])) < _LIMIAR_ARRASTE:
                return
            self._arraste_ativar(estado)
        self._arraste_atualizar()

    def _arraste_ativar(self, estado):
        t = theme.get(self.parent_app.modo_escuro)
        self.update_idletasks()
        rec = self._cartoes[estado["caminho"]]
        card = rec["frame"]
        altura = card.winfo_height()
        origem = estado["origem"]

        # Pontos médios dos outros cartões no layout SEM o cartão levado e sem
        # o vão: é contra eles que o ponteiro decide, e por serem fixos a troca
        # não oscila quando o vão muda de lugar.
        recs_outros = [self._cartoes[p["caminho"]] for p in self.passos
                       if p["caminho"] != estado["caminho"]]
        outros = [r["frame"] for r in recs_outros]
        mids = []
        for k, c in enumerate(outros):
            topo = c.winfo_y()
            if k >= origem:                       # estava abaixo do cartão levado
                topo -= altura + _FOLGA_CARTAO
            mids.append(topo + c.winfo_height() / 2)

        vao = tk.Frame(self.frame_sequencia, bg=t["accent_bg"], height=altura,
                       highlightbackground=t["accent"], highlightcolor=t["accent"],
                       highlightthickness=2, cursor="fleur")
        vao.pack_propagate(False)
        lbl_vao = tk.Label(vao, text="", bg=t["accent_bg"], fg=t["accent"],
                           font=(theme.FONT, theme.FS_BODY, "bold"))
        lbl_vao.pack(expand=True)
        vao.pack(fill="x", pady=4, padx=(0, 10), before=card)
        vao.update_idletasks()
        falta = altura - vao.winfo_reqheight()    # o Tk soma a borda ao height
        if falta:
            vao.config(height=altura + falta)
        card.pack_forget()

        try:
            base = self._miniatura_pil(estado["caminho"],
                                       (_LARGURA_MINIATURA, _ALTURA_MINIATURA))
        except Exception:
            base = Image.new("RGB", (_LARGURA_MINIATURA, _ALTURA_MINIATURA), (200, 205, 210))
        fantasma = tk.Label(self, bd=0, bg=t["accent"], cursor="fleur")
        self._fantasma = fantasma

        estado.update({
            "ativo": True, "vao": vao, "lbl_vao": lbl_vao, "fantasma": fantasma,
            "base": base, "foto_fantasma": None, "numero_fantasma": None,
            "outros": outros, "recs_outros": recs_outros, "mids": mids,
            "altura": altura, "margem": _FOLGA_TROCA * altura, "destino": origem,
        })
        self._renumerar_arraste(estado)
        estado["job"] = self.after(_AUTOSCROLL_MS, self._autoscroll_tick)

    def _arraste_atualizar(self):
        estado = getattr(self, "_arraste", None)
        if not estado or not estado.get("ativo"):
            return
        self._posicionar_fantasma(estado)
        cv = self._canvas_sequencia
        y = cv.canvasy(estado["y_root"] - cv.winfo_rooty())
        novo = calcular_destino(y, estado["mids"], estado["destino"], estado["margem"])
        if novo != estado["destino"]:
            estado["destino"] = novo
            outros, vao = estado["outros"], estado["vao"]
            if novo < len(outros):
                vao.pack_configure(before=outros[novo])
            else:
                vao.pack_forget()
                vao.pack(fill="x", pady=4, padx=(0, 10))
            self._renumerar_arraste(estado)

    def _posicionar_fantasma(self, estado):
        fantasma = estado["fantasma"]
        fantasma.update_idletasks()
        x = estado["x_root"] - self.winfo_rootx() - fantasma.winfo_reqwidth() // 2
        y = estado["y_root"] - self.winfo_rooty() - fantasma.winfo_reqheight() // 2
        fantasma.place(x=x, y=y)
        fantasma.lift()

    def _renumerar_arraste(self, estado):
        """Os números mostram, durante o arraste, como a lista vai ficar."""
        d = estado["destino"]
        for k, rec in enumerate(estado["recs_outros"]):
            self._numerar(rec, k + 1 if k < d else k + 2)
        self._sincronizar_fotos_seq()
        estado["lbl_vao"].config(text="Posição %d" % (d + 1))
        numero = d + 1
        if estado["numero_fantasma"] != numero:
            t = theme.get(self.parent_app.modo_escuro)
            img = ImageOps.expand(_com_numero(estado["base"].copy(), numero, t["accent"]),
                                  border=3, fill=t["accent"])
            estado["foto_fantasma"] = ImageTk.PhotoImage(img)
            estado["numero_fantasma"] = numero
            estado["fantasma"].config(image=estado["foto_fantasma"])
        self._posicionar_fantasma(estado)

    def _autoscroll_tick(self):
        """Rola a coluna sozinha quando o ponteiro chega perto da borda.

        Roda num temporizador e não nos eventos do mouse: segurando o ponteiro
        parado na borda não chega evento nenhum, e a lista tem de continuar
        andando. A velocidade cresce com a proximidade da borda, e passa dela
        no máximo. Depois de rolar, o destino é recalculado: o conteúdo andou
        sob o ponteiro.
        """
        estado = getattr(self, "_arraste", None)
        if not estado or not estado.get("ativo"):
            return
        estado["job"] = None
        cv = self._canvas_sequencia
        try:
            topo, altura = cv.winfo_rooty(), cv.winfo_height()
            zona = max(30, min(_ZONA_AUTOSCROLL, altura // 4))
            y = estado["y_root"]
            sinal, prox = 0, 0.0
            if y < topo + zona:
                sinal, prox = -1, (topo + zona - y) / zona
            elif y > topo + altura - zona:
                sinal, prox = 1, (y - (topo + altura - zona)) / zona
            if sinal:
                velocidade = _AUTOSCROLL_MIN + (_AUTOSCROLL_MAX - _AUTOSCROLL_MIN) * min(prox, 1.0) ** 2
                caixa = cv.bbox("all")
                total = caixa[3] - caixa[1] if caixa else 0
                atual = cv.canvasy(0)
                novo = max(0, min(total - altura, atual + sinal * int(velocidade)))
                if total > 0 and novo != atual:
                    cv.yview_moveto(novo / total)
                    self._arraste_atualizar()
            estado["job"] = self.after(_AUTOSCROLL_MS, self._autoscroll_tick)
        except tk.TclError:
            pass          # a janela foi fechada no meio do arraste

    def _arraste_limpar(self, estado):
        """Desfaz o que só existe durante o arraste: temporizador, fantasma e vão."""
        if estado.get("job"):
            try:
                self.after_cancel(estado["job"])
            except tk.TclError:
                pass
            estado["job"] = None
        for chave in ("fantasma", "vao"):
            w = estado.get(chave)
            if w is not None:
                try:
                    w.destroy()
                except tk.TclError:
                    pass
        self._fantasma = None

    def _arraste_soltar(self, event):
        estado = getattr(self, "_arraste", None)
        self._arraste = None
        if not estado or not estado["ativo"]:
            return  # foi um clique simples, não um arraste
        self._arraste_limpar(estado)
        d = estado["destino"]
        recs = estado["recs_outros"]
        nova = ([r["caminho"] for r in recs[:d]] + [estado["caminho"]]
                + [r["caminho"] for r in recs[d:]])
        self._aplicar_ordem(nova, estado["caminho"])

    def _arraste_cancelar(self, event=None):
        """Esc durante o arraste: tudo volta como estava."""
        estado = getattr(self, "_arraste", None)
        if not estado or not estado.get("ativo"):
            return None
        self._arraste = None
        self._arraste_limpar(estado)
        self._reordenar_em_lugar()
        return "break"

    # ---------- aplicar uma ordem ----------

    def _aplicar_ordem(self, caminhos, movido=None, avisar=True, modo=None, texto=None):
        """Põe os passos na ordem dada, movendo os mesmos widgets de lugar.

        `modo` é o rótulo da ordem resultante. Sem ele, mexer na ordem à mão
        passa o documento para "manual" e não mexer em nada deixa como está.
        """
        antes = [p["caminho"] for p in self.passos]
        modo_antes = self._modo_ordem
        if caminhos != antes:
            por_caminho = {p["caminho"]: p for p in self.passos}
            self.passos[:] = [por_caminho[c] for c in caminhos]
        self._modo_ordem = modo or ("manual" if caminhos != antes else modo_antes)
        self._reordenar_em_lugar()
        self._atualizar_pills_ordem()
        if avisar and caminhos != antes:
            self._registrar_movimento(antes, movido, modo_antes, texto)

    def _reordenar_em_lugar(self):
        self._empacotar_sequencia()
        for idx, passo in enumerate(self.passos):
            rec = self._cartoes.get(passo["caminho"])
            if rec is not None:
                self._numerar(rec, idx + 1)
        self._sincronizar_fotos_seq()
        self._reordenar_central()
        self._atualizar_paginas()

    def _mover(self, idx, delta):
        novo = idx + delta
        if 0 <= novo < len(self.passos):
            ordem = [p["caminho"] for p in self.passos]
            movido = ordem[idx]
            ordem[idx], ordem[novo] = ordem[novo], ordem[idx]
            self._aplicar_ordem(ordem, movido)

    def _mover_pelo_teclado(self, delta, event=None):
        """Alt+↑ / Alt+↓: move o cartão selecionado — menos dentro de um campo
        de texto, onde essas teclas pertencem ao campo."""
        try:
            foco = self.focus_get()
        except Exception:
            foco = None
        if isinstance(foco, (tk.Entry, tk.Text)) or self._selecionado is None:
            return None
        self._mover(self._indice_de(self._selecionado), delta)
        return "break"

    def _remover(self, idx):
        if 0 <= idx < len(self.passos):
            # a legenda digitada vale antes de as caixas serem recriadas
            self._sincronizar_legendas()
            self.passos.pop(idx)
            self._ordem_antes_mover = None
            self._esconder_aviso()
            self._atualizar_sequencia()
            self._atualizar_coluna_central()

    # ---------- aviso de movimento e desfazer ----------

    def _registrar_movimento(self, antes, caminho, modo_antes="manual", texto=None):
        self._ordem_antes_mover = antes
        self._modo_antes_mover = modo_antes
        posicao = self._indice_de(caminho) + 1 if caminho else 0
        texto = texto or ("Movido para a posição %d" % posicao if posicao else "Ordem alterada")
        self._lbl_aviso_seq.config(text=texto)
        self._aviso_seq.pack(side="bottom", fill="x", before=self._wrap_seq)
        if self._aviso_job:
            try:
                self.after_cancel(self._aviso_job)
            except tk.TclError:
                pass
        self._aviso_job = self.after(_AVISO_MS, self._esconder_aviso)

    def _esconder_aviso(self):
        """O desfazer vale enquanto o aviso está na tela: sem ele, um Ctrl+Z
        minutos depois desfaria um movimento antigo sem ninguém ver."""
        self._aviso_job = None
        self._ordem_antes_mover = None
        try:
            self._aviso_seq.pack_forget()
        except tk.TclError:
            pass

    def _desfazer_movimento(self):
        antes = self._ordem_antes_mover
        modo_antes = self._modo_antes_mover
        self._esconder_aviso()
        if not antes or set(antes) != {p["caminho"] for p in self.passos}:
            return
        # desfazer devolve também o rótulo da ordem: voltar de "Mais recentes"
        # para a ordem de antes não pode deixar o seletor mentindo
        self._aplicar_ordem(antes, avisar=False, modo=modo_antes)

    # ---------- ordenar pelo instante da captura ----------

    def _ordenar_por_captura(self, decrescente):
        """Seletor de ordem: do início ao fim (padrão) ou do mais novo ao mais
        antigo. Reaplicar sobrescreve a ordem manual, e entra no Desfazer."""
        self._sincronizar_legendas()
        modo = "recentes" if decrescente else "cronologica"
        nova = capture_store.ordenar_instantes(
            [(p["caminho"], p["instante"]) for p in self.passos], decrescente)
        texto = ("Ordenado do mais novo ao mais antigo" if decrescente
                 else "Ordenado do início ao fim")
        self._aplicar_ordem(nova, None, True, modo, texto)

    def _atualizar_pills_ordem(self):
        """O seletor mostra a ordem em vigor; depois de mexer à mão, nenhuma das
        duas fica ativa e aparece "ordem manual"."""
        if not hasattr(self, "_pill_cron"):
            return
        self._pill_cron.definir("Cronológica", self._modo_ordem == "cronologica")
        self._pill_rec.definir("Mais novos", self._modo_ordem == "recentes")
        if self._modo_ordem == "manual":
            self._lbl_ordem_manual.pack(anchor="w", pady=(4, 0))
        else:
            self._lbl_ordem_manual.pack_forget()

    def _atalho_desfazer(self, event=None):
        """Ctrl+Z desfaz a última movimentação — menos dentro de um campo de
        texto, onde ele pertence ao campo."""
        try:
            foco = self.focus_get()
        except Exception:
            foco = None
        if isinstance(foco, (tk.Entry, tk.Text)) or not self._ordem_antes_mover:
            return None
        self._desfazer_movimento()
        return "break"

    def destroy(self):
        # Cancela o que ainda está agendado: um `after` que dispara depois de a
        # janela morrer age sobre widgets destruídos e vira erro silencioso.
        estado = getattr(self, "_arraste", None)
        for job in ((estado or {}).get("job"), getattr(self, "_aviso_job", None)):
            if job:
                try:
                    self.after_cancel(job)
                except Exception:
                    pass
        super().destroy()

    def _montar_coluna_central(self, corpo, t):
        self.col_central = tk.Frame(corpo, bg=t["bg_content"])
        corpo.add(self.col_central, minsize=380, stretch="always")
        self._montar_coluna_central_conteudo(t)

    def _montar_coluna_central_conteudo(self, t):
        # Guarda o que está digitado na capa ANTES de destruir os widgets. Esta
        # coluna é remontada ao reordenar a sequência, e a leitura de um widget
        # já destruído falha calada — era assim que o título voltava ao padrão
        # e o caso, o autor e o ambiente ficavam em branco depois de mover um
        # print de lugar.
        self._capa_digitada = self._capa_atual()
        rolagem = 0.0
        if self._canvas_central is not None:
            try:
                rolagem = self._canvas_central.yview()[0]
            except tk.TclError:
                pass          # canvas já destruído
        for w in self.col_central.winfo_children():
            w.destroy()
        self.imagens_passos = []

        canvas = tk.Canvas(self.col_central, bg=t["bg_content"], highlightthickness=0, width=1)
        self._canvas_central = canvas
        scrollbar = tk.Scrollbar(self.col_central, orient="vertical", command=canvas.yview)
        frame = tk.Frame(canvas, bg=t["bg_content"])
        janela_central = canvas.create_window((0, 0), window=frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side="left", fill="both", expand=True, padx=24, pady=20)
        scrollbar.pack(side="right", fill="y")
        frame.bind("<Configure>", lambda e: canvas.config(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>", lambda e: canvas.itemconfig(janela_central, width=e.width))
        canvas.bind("<Enter>", lambda e: canvas.bind_all("<MouseWheel>",
                    lambda ev: canvas.yview_scroll(int(-1 * (ev.delta / 120)), "units")))
        canvas.bind("<Leave>", lambda e: canvas.unbind_all("<MouseWheel>"))

        capa_card = tk.Frame(frame, bg=t["bg_panel"],
                             highlightbackground=t["border_soft"], highlightthickness=1)
        capa_card.pack(fill="x", pady=(0, 16))
        self._capa_card = capa_card
        tk.Label(capa_card, text="CAPA DO DOCUMENTO", bg=t["bg_panel"], fg=t["accent"],
                 font=(theme.FONT, theme.FS_EYEBROW, "bold")).pack(
                     anchor="w", padx=16, pady=(14, 8))

        linha1 = tk.Frame(capa_card, bg=t["bg_panel"])
        linha1.pack(fill="x", padx=16)
        for chave, rotulo, largura in (("titulo", "Título", 2), ("caso", "Caso / projeto", 1)):
            bloco = tk.Frame(linha1, bg=t["bg_panel"])
            bloco.pack(side="left", fill="x", expand=True, padx=(0, 10))
            _, entry = widgets.campo_rotulado(bloco, rotulo, self.parent_app.modo_escuro,
                                                valor_inicial=self._valor_capa_inicial(chave))
            self.entries_capa[chave] = entry

        linha2 = tk.Frame(capa_card, bg=t["bg_panel"])
        linha2.pack(fill="x", padx=16, pady=(0, 16))
        for chave, rotulo in (("autor", "Autor"), ("data", "Data"), ("ambiente", "Ambiente")):
            bloco = tk.Frame(linha2, bg=t["bg_panel"])
            bloco.pack(side="left", fill="x", expand=True, padx=(0, 10))
            _, entry = widgets.campo_rotulado(bloco, rotulo, self.parent_app.modo_escuro,
                                                valor_inicial=self._valor_capa_inicial(chave))
            self.entries_capa[chave] = entry

        self.entries_legenda = {}
        self._cartoes_centro = {}
        self._caminhos_fotos_centro = []
        for idx, passo in enumerate(self.passos):
            # Tudo o que reage a clique guarda o CAMINHO e resolve a posição na
            # hora: os cartões trocam de lugar sem serem recriados, e o índice
            # de quando foram construídos ficaria velho.
            caminho = passo["caminho"]
            card = tk.Frame(frame, bg=t["bg_panel"],
                            highlightbackground=t["border_soft"], highlightthickness=1)
            card.pack(fill="x", pady=6)
            linha = tk.Frame(card, bg=t["bg_panel"])
            linha.pack(fill="x", padx=16, pady=14)

            selo = tk.Label(linha, text=str(idx + 1), bg=t["accent"], fg="#ffffff", width=2,
                            font=(theme.FONT, theme.FS_BODY, "bold"))
            selo.pack(side="left", anchor="n")

            meio = tk.Frame(linha, bg=t["bg_panel"])
            meio.pack(side="left", fill="both", expand=True, padx=12)
            tk.Label(meio, text="Legenda do passo", bg=t["bg_panel"], fg=t["text_tertiary"],
                     font=(theme.FONT, theme.FS_CAPTION)).pack(anchor="w")
            txt = tk.Text(meio, height=3, font=(theme.FONT, theme.FS_BODY), wrap="word",
                           bd=0, relief="flat", bg=t["bg_input"], fg=t["text_primary"],
                           insertbackground=t["text_primary"],
                           highlightbackground=t["border_input"], highlightcolor=t["border_input"],
                           highlightthickness=1)
            txt.pack(fill="x", pady=4)
            txt.insert("1.0", passo["legenda"])
            txt.bind("<KeyRelease>",
                     lambda e, c=caminho, w=txt: self._on_legenda_change(self._indice_de(c), w))
            self.entries_legenda[idx] = txt
            self._cartoes_centro[caminho] = {"frame": card, "selo": selo, "txt": txt}

            lado_imagem = tk.Frame(linha, bg=t["bg_panel"])
            lado_imagem.pack(side="left")
            try:
                img_tk = ImageTk.PhotoImage(self._miniatura_pil(caminho, (160, 110)))
                self.imagens_passos.append(img_tk)
                self._caminhos_fotos_centro.append(caminho)
                miniatura = tk.Label(lado_imagem, image=img_tk, bg=t["bg_input"], cursor="hand2")
            except Exception:
                miniatura = tk.Label(lado_imagem, text="imagem indisponível", bg=t["bg_input"],
                                     fg=t["text_muted"], font=(theme.FONT, theme.FS_CAPTION),
                                     width=22, height=6, cursor="hand2")
            miniatura.pack()
            miniatura.bind("<Double-Button-1>",
                           lambda e, c=caminho: self._editar_passo(self._indice_de(c)))
            # O duplo clique não se descobre sozinho nem é fácil pra todo
            # mundo: o link dá o mesmo caminho com um clique só.
            link = tk.Label(lado_imagem, text="✎ Editar imagem", bg=t["bg_panel"], fg=t["accent"],
                            font=(theme.FONT, theme.FS_CAPTION), cursor="hand2")
            link.pack(pady=(4, 0))
            link.bind("<Button-1>", lambda e, c=caminho: self._editar_passo(self._indice_de(c)))

        self._restaurar_rolagem(canvas, rolagem)

    def _reordenar_central(self):
        """Põe os cartões da coluna central na ordem de `self.passos`, no lugar.

        São os mesmos widgets: as legendas digitadas, o cursor e a rolagem
        ficam como estavam, e as imagens não são relidas do disco.
        """
        recs = self._cartoes_centro
        if len(recs) != len(self.passos) or any(p["caminho"] not in recs for p in self.passos):
            self._atualizar_coluna_central()      # fora de sincronia: refaz do zero
            return
        frames = [recs[p["caminho"]]["frame"] for p in self.passos]
        _posicionar_em_ordem(self._capa_card.master, frames, self._capa_card,
                             fill="x", pady=6)
        entries = {}
        for idx, passo in enumerate(self.passos):
            rec = recs[passo["caminho"]]
            rec["selo"].config(text=str(idx + 1))
            entries[idx] = rec["txt"]
        self.entries_legenda = entries
        # As PhotoImage só vivem nesta lista; reordena-a junto, em vez de criar
        # uma segunda referência que esconderia uma imagem perdida.
        por_caminho = dict(zip(self._caminhos_fotos_centro, self.imagens_passos))
        self._caminhos_fotos_centro = [p["caminho"] for p in self.passos
                                       if p["caminho"] in por_caminho]
        self.imagens_passos = [por_caminho[c] for c in self._caminhos_fotos_centro]

    def _capa_atual(self):
        """O que está nos campos da capa agora, enquanto os widgets existem."""
        valores = dict(getattr(self, "_capa_digitada", {}))
        for chave, entry in getattr(self, "entries_capa", {}).items():
            try:
                valores[chave] = entry.get()
            except Exception:
                pass          # widget já destruído: mantém o valor anterior
        return valores

    def _valor_capa_inicial(self, chave):
        guardado = getattr(self, "_capa_digitada", {}).get(chave)
        if guardado is not None:
            return guardado     # string vazia também vale: o usuário apagou
        if chave == "titulo":
            return titulo_padrao(self.var_modelo.get())
        if chave == "data":
            return datetime.now().strftime("%d/%m/%Y")
        if chave == "autor":
            # último autor usado, pra não ter que redigitar a cada documento
            return self.parent_app.config.get("autor_padrao", "")
        return ""

    def _on_legenda_change(self, idx, widget):
        if 0 <= idx < len(self.passos):
            self.passos[idx]["legenda"] = widget.get("1.0", "end").strip()

    def _atualizar_coluna_central(self):
        t = theme.get(self.parent_app.modo_escuro)
        self._montar_coluna_central_conteudo(t)

    # ---------- editar a imagem sem sair do documento ----------

    def _sincronizar_legendas(self):
        """Copia o que está nas caixas de legenda para os passos.

        O <KeyRelease> cobre quem digita, mas não colar pelo mouse. Só vale
        enquanto as caixas e `self.passos` estão na mesma ordem — por isso não
        é chamado logo após reordenar, quando as caixas ainda são as antigas.
        """
        for idx, caixa in self.entries_legenda.items():
            if 0 <= idx < len(self.passos):
                try:
                    self.passos[idx]["legenda"] = caixa.get("1.0", "end").strip()
                except tk.TclError:
                    pass      # caixa já destruída

    def _gravar_legendas(self):
        """Persiste a legenda de todos os passos no .json de cada captura.

        A legenda digitada aqui vivia só na memória e se perdia ao fechar a
        janela; o editor, por sua vez, lê do .json. Gravar em todos os passos
        mantém as duas telas contando a mesma história.
        """
        mudou = False
        for passo in self.passos:
            try:
                mudou |= capture_store.save_caption(passo["caminho"], passo["legenda"])
            except Exception:
                pass          # captura apagada ou bloqueada: o documento usa a da memória
        if mudou:
            self.parent_app.atualizar_galeria()

    def _editar_passo(self, idx):
        """Abre o editor de imagem do passo; ao gravar, o documento se atualiza."""
        # Um editor por vez: com dois abertos sobre a mesma imagem, o último a
        # gravar apagaria o trabalho do outro.
        if self._editor is not None and self._editor.winfo_exists():
            self._editor.deiconify()
            self._editor.lift()
            self._editor.focus_force()
            return
        if not (0 <= idx < len(self.passos)):
            return
        self._sincronizar_legendas()
        passo = self.passos[idx]
        caminho = passo["caminho"]
        if not os.path.exists(caminho):
            messagebox.showwarning(
                "Editar imagem",
                "O arquivo desta captura não foi encontrado — ele pode ter sido "
                "movido ou apagado.", parent=self)
            return
        try:
            ed = editor.EditorImagem(
                self, caminho, lambda c=caminho: self._ao_gravar(c),
                self.parent_app.modo_escuro, app=self.parent_app, janela_retorno=self,
                legenda_inicial=passo["legenda"])
        except Exception as e:
            messagebox.showerror("Editar imagem",
                                 f"Não foi possível abrir o editor:\n{e}", parent=self)
            return
        self._editor = ed
        # Só o Montar fica bloqueado. grab_set travaria também o overlay do
        # Print Screen, que é outra janela, e impediria capturar com o editor
        # aberto.
        self.attributes("-disabled", True)
        # O desbloqueio vem do <Destroy> do editor, e não dos botões dele: o
        # editor pode ser destruído por outro caminho (erro, troca de tema), e
        # o Montar ficaria travado para sempre.
        ed.bind("<Destroy>", lambda e, w=ed: self._editor_fechado(w, e), add="+")
        ed.lift()
        ed.focus_force()

    def _editor_fechado(self, ed, evento):
        if str(evento.widget) != str(ed):
            return            # <Destroy> de um widget interno do editor
        if self._editor is ed:
            self._editor = None
        try:
            self.attributes("-disabled", False)
            self.deiconify()
            self.focus_force()
        except tk.TclError:
            pass              # o Montar também foi fechado

    def _ao_gravar(self, caminho):
        """Roda a cada gravação do editor: traz a imagem e a legenda do disco."""
        if not self.winfo_exists():
            return
        passo = next((p for p in self.passos if p["caminho"] == caminho), None)
        if passo is None:
            return
        # A fonte da verdade passa a ser o disco: o editor pode ter mudado a
        # legenda além da imagem.
        passo["legenda"] = capture_store.load_meta(caminho).get("caption", "")
        self._atualizar_sequencia()
        self._atualizar_coluna_central()
        self.parent_app.atualizar_galeria()
        for previa in list(self._previas):
            if previa.winfo_exists():
                previa.regerar()
            else:
                self._previas.remove(previa)

    def _montar_coluna_direita(self, corpo, t):
        col = tk.Frame(corpo, bg=t["bg_panel"])
        corpo.add(col, minsize=220, width=290, stretch="never")

        bloco = tk.Frame(col, bg=t["bg_panel"])
        bloco.pack(fill="x", padx=16, pady=14)
        tk.Label(bloco, text="MODELO", bg=t["bg_panel"], fg=t["text_muted"],
                 font=(theme.FONT, theme.FS_EYEBROW, "bold")).pack(anchor="w", pady=(0, 8))

        for valor, nome, desc in MODELOS_UI:
            linha = tk.Frame(bloco, bg=t["bg_panel"], cursor="hand2")
            linha.pack(fill="x", pady=3)
            self._linha_modelo(linha, valor, nome, desc, t)

        widgets.titulo_secao(bloco, "Opções", self.parent_app.modo_escuro)
        widgets.linha_checkbox(bloco, "Numerar os passos", self.var_numerar,
                               self.parent_app.modo_escuro)
        widgets.linha_checkbox(bloco, "Adicionar borda nas imagens", self.var_borda,
                               self.parent_app.modo_escuro)

        tk.Label(bloco, text="Cor de destaque", bg=t["bg_panel"], fg=t["text_tertiary"],
                 font=(theme.FONT, theme.FS_CAPTION)).pack(anchor="w", pady=(10, 4))
        self._cores_frame = tk.Frame(bloco, bg=t["bg_panel"])
        self._cores_frame.pack(anchor="w")
        self._swatches_cor = {}
        for cor in theme.PALETTE:
            wrap = tk.Frame(self._cores_frame, bg=t["bg_panel"])
            wrap.pack(side="left", padx=3, pady=3)
            q = tk.Frame(wrap, bg=cor, width=24, height=24, cursor="hand2")
            q.pack_propagate(False)
            q.pack()
            q.bind("<Button-1>", lambda e, c=cor: self._selecionar_cor(c))
            self._swatches_cor[cor] = wrap
        self._atualizar_cores_destaque()

        rodape = tk.Frame(col, bg=t["bg_footer"])
        rodape.pack(fill="x", side="bottom")
        self.lbl_paginas = tk.Label(rodape, text="", bg=t["bg_footer"], fg=t["text_tertiary"],
                                     font=(theme.FONT, theme.FS_CAPTION))
        self.lbl_paginas.pack(anchor="w", padx=16, pady=(12, 4))
        widgets.botao_primario(rodape, "Pré-visualizar", self._pre_visualizar,
                                self.parent_app.modo_escuro).pack(fill="x", padx=16, pady=(0, 14))
        # A sequência é montada antes deste rótulo existir, e a contagem
        # daquela primeira rodada não tinha onde aparecer.
        self._atualizar_paginas()

    def _linha_modelo(self, linha, valor, nome, desc, t):
        def selecionar(v=valor):
            self._trocar_modelo(v)

        linha.bind("<Button-1>", lambda e: selecionar())
        self._card_modelo_widgets = getattr(self, "_card_modelo_widgets", {})
        lbl = widgets.texto_fluido(linha, nome, self.parent_app.modo_escuro, cor="text_primary",
                                    fonte=(theme.FONT, theme.FS_BODY, "bold"))
        lbl.config(cursor="hand2")
        lbl.pack(fill="x", padx=8, pady=(6, 0))
        lbl.bind("<Button-1>", lambda e: selecionar())
        sub = widgets.texto_fluido(linha, desc, self.parent_app.modo_escuro)
        sub.config(cursor="hand2")
        sub.pack(fill="x", padx=8, pady=(0, 6))
        sub.bind("<Button-1>", lambda e: selecionar())
        self._card_modelo_widgets[valor] = (linha, lbl, sub)
        self._atualizar_modelos_visual()

    def _trocar_modelo(self, novo):
        anterior = self.var_modelo.get()
        self.var_modelo.set(novo)
        self._atualizar_modelos_visual()
        entry = self.entries_capa.get("titulo")
        if entry is None:
            return
        try:
            atual = entry.get()
            titulo = titulo_ao_trocar_modelo(atual, anterior, novo)
            if titulo != atual:
                entry.delete(0, "end")
                entry.insert(0, titulo)
        except tk.TclError:
            pass          # campo já destruído: a coluna refaz com o modelo novo

    def _atualizar_modelos_visual(self):
        t = theme.get(self.parent_app.modo_escuro)
        for valor, (linha, lbl, sub) in getattr(self, "_card_modelo_widgets", {}).items():
            ativo = valor == self.var_modelo.get()
            bg = t["accent_bg"] if ativo else t["bg_panel"]
            linha.config(bg=bg, highlightbackground=t["accent"] if ativo else t["border_soft"],
                         highlightthickness=1)
            lbl.config(bg=bg)
            sub.config(bg=bg)

    def _selecionar_cor(self, cor):
        self.var_cor.set(cor)
        self._atualizar_cores_destaque()

    def _atualizar_cores_destaque(self):
        t = theme.get(self.parent_app.modo_escuro)
        for cor, wrap in self._swatches_cor.items():
            selecionada = cor == self.var_cor.get()
            contorno = t["accent"] if selecionada else t["border"]
            wrap.config(highlightbackground=contorno, highlightcolor=contorno,
                        highlightthickness=2)

    def _atualizar_paginas(self):
        from gestor.exportacao import pdf_export
        n = pdf_export.contar_paginas(self.passos, self.var_modelo.get())
        if self.lbl_paginas:
            self.lbl_paginas.config(text=f"{len(self.passos)} passos · {n} páginas estimadas")

    # ---------- avançar ----------

    def _pre_visualizar(self):
        if not self.passos:
            messagebox.showinfo("Montar documento", "Adicione ao menos uma captura.", parent=self)
            return
        self._sincronizar_legendas()
        self._gravar_legendas()
        capa = {chave: entry.get().strip() for chave, entry in self.entries_capa.items()}
        # guarda o autor pro próximo documento já vir preenchido
        if capa.get("autor") != self.parent_app.config.get("autor_padrao", ""):
            self.parent_app.config["autor_padrao"] = capa.get("autor", "")
            config.save(self.parent_app.data_dir, self.parent_app.config)
        opcoes = {
            "cor_destaque": self.var_cor.get(),
            "numerar_passos": self.var_numerar.get(),
            "borda_ativada": self.var_borda.get(),
            "borda_cor": self.var_cor.get(),
            "fonte_legenda": self.parent_app.config.get("fonte_legenda", "Arial"),
        }
        from gestor.ui import export_preview
        previa = export_preview.PreVisualizarExportar(
            self.parent_app, self, self.var_modelo.get(), capa, list(self.passos), opcoes)
        self._previas = [p for p in self._previas if p.winfo_exists()] + [previa]
