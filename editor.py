"""Editor de anotações (tela '1b' do design).

As anotações são guardadas como dados (self.shapes), não mais "queimadas"
direto no PNG ao salvar — isso é o que permite o painel de camadas, o
esconder/mostrar por anotação e um desfazer/refazer que sobrevive a reabrir
a captura. `render_composite` é a única função que transforma
raw + shapes -> imagem final, usada tanto para gravar quanto para
copiar/exportar, então a prévia nunca diverge do resultado salvo.
"""
import copy
import math
import os
from tkinter import Toplevel, colorchooser, filedialog, messagebox
import tkinter as tk

from PIL import Image, ImageTk, ImageDraw, ImageFont

import capture_store
import emoji_picker
import theme
import utils
import widgets

TAMANHO_EMOJI_PADRAO = emoji_picker.TAMANHO_PADRAO

TOOL_LABELS = {
    "mover": "Mover",
    "seta": "Seta",
    "retangulo": "Quadro",
    "elipse": "Elipse",
    "marcador": "Marcador",
    "texto": "Texto",
    "emoji": "Emoji",
    "passo": "Passo",
    "borrao": "Borrar",
    "recorte": "Recorte",
    "apagar": "Apagar",
}

# ---------------------------------------------------------------------------
# Ícones da coluna de ferramentas, desenhados em vetor com PIL.
#
# São vetores, e não caracteres Unicode, porque o segoeui.ttf não traz os
# glifos correspondentes (↖ ▭ ▮ ☺ ① ▩ ⬚ ⌫) e a maioria das ferramentas cairia
# no glifo de substituição. Cada função recebe o ImageDraw já em alta
# resolução — a redução final com LANCZOS é o que produz o antialiasing —,
# o centro, um raio de referência, a cor e a espessura do traço.
# ---------------------------------------------------------------------------

def _ic_mover(d, cx, cy, r, cor, lw):
    """Ponteiro de seleção."""
    pontos = [(0.0, -1.0), (0.0, 0.62), (0.30, 0.28), (0.52, 0.95),
              (0.78, 0.82), (0.55, 0.18), (0.95, 0.10)]
    d.polygon([(cx + px * r, cy + py * r) for px, py in pontos], fill=cor)


def _ic_seta(d, cx, cy, r, cor, lw):
    x1, y1 = cx - r * 0.85, cy + r * 0.85
    x2, y2 = cx + r * 0.8, cy - r * 0.8
    d.line([x1, y1, x2, y2], fill=cor, width=lw)
    d.polygon([(x2 + r * 0.2, y2 - r * 0.2), (x2 - r * 0.55, y2 + r * 0.05),
               (x2 - r * 0.05, y2 + r * 0.55)], fill=cor)


def _ic_retangulo(d, cx, cy, r, cor, lw):
    d.rectangle([cx - r, cy - r * 0.72, cx + r, cy + r * 0.72], outline=cor, width=lw)


def _ic_elipse(d, cx, cy, r, cor, lw):
    d.ellipse([cx - r, cy - r * 0.85, cx + r, cy + r * 0.85], outline=cor, width=lw)


def _ic_marcador(d, cx, cy, r, cor, lw):
    """Traço de marca-texto: barra grossa inclinada."""
    d.line([cx - r * 0.85, cy + r * 0.55, cx + r * 0.85, cy - r * 0.55],
           fill=cor, width=int(lw * 3.2))
    d.line([cx - r * 0.9, cy + r * 0.95, cx + r * 0.9, cy + r * 0.95], fill=cor, width=lw)


def _ic_texto(d, cx, cy, r, cor, lw):
    d.line([cx - r * 0.8, cy - r * 0.8, cx + r * 0.8, cy - r * 0.8], fill=cor, width=lw)
    d.line([cx, cy - r * 0.8, cx, cy + r * 0.85], fill=cor, width=lw)


def _ic_emoji(d, cx, cy, r, cor, lw):
    d.ellipse([cx - r, cy - r, cx + r, cy + r], outline=cor, width=lw)
    olho = r * 0.16
    for dx in (-r * 0.38, r * 0.38):
        d.ellipse([cx + dx - olho, cy - r * 0.32 - olho, cx + dx + olho, cy - r * 0.32 + olho],
                  fill=cor)
    d.arc([cx - r * 0.55, cy - r * 0.35, cx + r * 0.55, cy + r * 0.6], start=20, end=160,
          fill=cor, width=lw)


def _ic_passo(d, cx, cy, r, cor, lw):
    """Círculo numerado. Contorno em vez de preenchido porque na ferramenta
    ativa o ícone fica branco: círculo cheio deixaria o número invisível."""
    d.ellipse([cx - r, cy - r, cx + r, cy + r], outline=cor, width=lw)
    try:
        fonte = ImageFont.truetype("segoeuib.ttf", int(r * 1.15))
    except Exception:
        fonte = ImageFont.load_default()
    d.text((cx, cy), "1", font=fonte, fill=cor, anchor="mm")


def _ic_borrao(d, cx, cy, r, cor, lw):
    """Mosaico de pixels, que é o efeito que a ferramenta aplica."""
    passo = r * 0.66
    for ix in range(-1, 2):
        for iy in range(-1, 2):
            if (ix + iy) % 2:
                continue
            x, y = cx + ix * passo, cy + iy * passo
            d.rectangle([x - passo * 0.44, y - passo * 0.44, x + passo * 0.44, y + passo * 0.44],
                        fill=cor)


def _ic_recorte(d, cx, cy, r, cor, lw):
    """Marcas de corte em L, como no ícone clássico de crop."""
    d.line([cx - r * 0.45, cy - r, cx - r * 0.45, cy + r * 0.62], fill=cor, width=lw)
    d.line([cx - r, cy + r * 0.45, cx + r * 0.62, cy + r * 0.45], fill=cor, width=lw)
    d.line([cx + r * 0.45, cy - r * 0.62, cx + r * 0.45, cy + r], fill=cor, width=lw)
    d.line([cx - r * 0.62, cy - r * 0.45, cx + r, cy - r * 0.45], fill=cor, width=lw)


def _ic_apagar(d, cx, cy, r, cor, lw):
    d.line([cx - r * 0.7, cy - r * 0.7, cx + r * 0.7, cy + r * 0.7], fill=cor, width=lw)
    d.line([cx + r * 0.7, cy - r * 0.7, cx - r * 0.7, cy + r * 0.7], fill=cor, width=lw)


FERRAMENTAS_COLUNA = [
    ("mover", _ic_mover, "Mover"),
    ("seta", _ic_seta, "Seta"),
    ("retangulo", _ic_retangulo, "Quadro"),
    ("elipse", _ic_elipse, "Elipse"),
    ("marcador", _ic_marcador, "Marcador"),
    ("texto", _ic_texto, "Texto"),
    ("emoji", _ic_emoji, "Emoji"),
    ("passo", _ic_passo, "Passo"),
    ("borrao", _ic_borrao, "Borrar"),
    ("recorte", _ic_recorte, "Recorte"),
]


def _ordenado(c):
    x1, y1, x2, y2 = c
    return [min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2)]


def render_composite(raw_img, shapes):
    img = raw_img.convert("RGBA").copy()
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    draw_ov = ImageDraw.Draw(overlay)
    draw_nm = ImageDraw.Draw(img)

    # A fonte é cacheada por tamanho, e não criada uma vez fora do laço, para
    # que cada emoji saia no tamanho que o usuário escolheu.
    fontes_emoji = {}

    def fonte_emoji(tamanho):
        if tamanho not in fontes_emoji:
            try:
                fontes_emoji[tamanho] = ImageFont.truetype("seguiemj.ttf", tamanho)
            except Exception:
                fontes_emoji[tamanho] = ImageFont.load_default()
        return fontes_emoji[tamanho]

    try:
        font_text = ImageFont.truetype("segoeui.ttf", 22)
        font_step = ImageFont.truetype("segoeuib.ttf", 15)
    except Exception:
        font_text = ImageFont.load_default()
        font_step = font_text

    for shp in shapes:
        tool = shp["tool"]
        c = shp["coords"]
        rgb = utils.hex_to_rgb(shp.get("color", "#E8590C"))
        w = max(1, int(shp.get("width", 4)))
        dash = shp.get("dash", False)

        if tool == "retangulo":
            if dash:
                utils.draw_dashed_rect(draw_nm, c, rgb, w)
            else:
                draw_nm.rectangle(_ordenado(c), outline=rgb, width=w)
        elif tool == "elipse":
            if dash:
                utils.draw_dashed_ellipse(draw_nm, c, rgb, w)
            else:
                draw_nm.ellipse(_ordenado(c), outline=rgb, width=w)
        elif tool == "seta":
            utils.draw_arrow(draw_nm, c, rgb, w)
        elif tool == "marcador":
            draw_ov.rectangle(_ordenado(c), fill=rgb + (128,))
        elif tool == "texto":
            draw_nm.text((c[0], c[1]), shp.get("text", ""), font=font_text, fill=rgb)
        elif tool == "emoji":
            # normaliza pelo mesmo motivo do seletor: com o seletor de variação
            # o glifo mede o dobro e sai deslocado do ponto clicado
            draw_nm.text((c[0], c[1]), emoji_picker.normalizar(shp.get("text", "✅")) or "✅",
                         font=fonte_emoji(int(shp.get("tamanho", TAMANHO_EMOJI_PADRAO))),
                         embedded_color=True, anchor="mm")
        elif tool == "passo":
            r = 14
            cx, cy = c[0], c[1]
            draw_nm.ellipse([cx - r, cy - r, cx + r, cy + r], fill=rgb)
            draw_nm.text((cx, cy), str(shp.get("step_n", 1)),
                         font=font_step, fill=(255, 255, 255), anchor="mm")
        elif tool == "borrao":
            utils.pixelate_region(img, c)

    return Image.alpha_composite(img, overlay).convert("RGB")


class EditorImagem(Toplevel):
    def __init__(self, parent, caminho_img, callback_atualizar, modo_escuro):
        super().__init__(parent)
        self.parent = parent
        self.caminho_img = caminho_img
        self.callback_atualizar = callback_atualizar
        self.modo_escuro = modo_escuro

        t = theme.get(modo_escuro)
        self.title("Editor de Evidência")
        self.state("zoomed")
        self.configure(bg=t["bg_panel"])

        meta = capture_store.load_meta(caminho_img)
        self.legenda_inicial = meta.get("caption", "")
        self.caso_inicial = meta.get("caso", "")
        self.shapes = meta.get("shapes", [])
        self._shape_seq = max([s.get("id", 0) for s in self.shapes], default=0)
        self.img_raw = capture_store.load_raw_image(caminho_img)

        self.ferramenta = "seta"
        self.cor_selecionada = theme.PALETTE[0]
        self.espessura = 4
        self.tracejado = False
        self.texto_atual = ""
        self.emoji_atual = "✅"
        self.tamanho_emoji = TAMANHO_EMOJI_PADRAO
        self.zoom_mode = "fit"
        self.escala = 1.0
        self.ox = 0
        self.oy = 0
        self.selected_id = None
        self.undo_stack = []
        self.redo_stack = []
        self.sujo = False
        self._shape_em_progresso = None
        self._crop_rect_item = None
        self._crop_start = None
        self._drag_origem = None
        self._drag_coords_ini = None
        self._editor_texto = None
        self._bbox_texto = {}

        self._montar_ui(t)

        self.canvas.bind("<ButtonPress-1>", self.on_press)
        self.canvas.bind("<Double-Button-1>", self._on_duplo_clique)
        self.canvas.bind("<B1-Motion>", self.on_drag)
        self.canvas.bind("<ButtonRelease-1>", self.on_release)
        self.canvas.bind("<Motion>", self._on_mouse_move)
        # Ligados na janela para valerem com o foco em qualquer parte da
        # imagem, mas filtrados por `_atalho_da_imagem`: dentro da legenda ou
        # do caso essas teclas pertencem ao campo.
        self.bind("<Control-z>", self._atalho_da_imagem(self.desfazer))
        self.bind("<Control-y>", self._atalho_da_imagem(self.refazer))
        self.bind("<Control-c>", self._atalho_da_imagem(self.copiar))
        self.bind("<Delete>", self._atalho_da_imagem(self._apagar_selecionado_tecla,
                                                      passa_evento=True))
        self.protocol("WM_DELETE_WINDOW", self.fechar_e_voltar)

        self._definir_ferramenta_ativa("seta")
        self._atualizar_lista_camadas()
        self._atualizar_status()
        self.after(120, self._redraw_canvas)

    # ---------- construção da UI ----------

    def _montar_ui(self, t):
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(2, weight=1)

        titlebar = tk.Frame(self, bg=t["bg_header"], height=42)
        titlebar.grid(row=0, column=0, columnspan=2, sticky="ew")
        titlebar.grid_propagate(False)
        nome_base = os.path.splitext(os.path.basename(self.caminho_img))[0]
        tk.Label(titlebar, text=nome_base, bg=t["bg_header"], fg=t["text_secondary"],
                 font=(theme.FONT, theme.FS_BODY)).pack(side="left", padx=(14, 0))

        self._montar_barra_superior(t)
        self._montar_coluna_ferramentas(t)

        # Canvas e painel direito num PanedWindow: o divisor arrastável deixa
        # o painel encolher e mantém a imagem como elemento principal da tela.
        self.paned = tk.PanedWindow(self, orient="horizontal", bg=t["border_soft"],
                                     sashwidth=6, sashrelief="flat", bd=0, opaqueresize=True)
        self.paned.grid(row=2, column=1, sticky="nsew")

        frame_canvas = tk.Frame(self.paned, bg=t["bg_content"])
        self.canvas = tk.Canvas(frame_canvas, bg=t["bg_content"], highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)

        barra_zoom = tk.Frame(self.canvas, bg=t["bg_panel"], highlightbackground=t["border"],
                               highlightthickness=1)
        widgets.Botao(barra_zoom, "−", lambda: self._ajustar_zoom(-10), self.modo_escuro,
                       variante="ghost", tamanho="sm").pack(side="left")
        self.lbl_zoom = tk.Label(barra_zoom, text="100%", bg=t["bg_panel"], fg=t["text_primary"],
                                  font=(theme.FONT, theme.FS_BODY, "bold"), width=8)
        self.lbl_zoom.pack(side="left")
        widgets.Botao(barra_zoom, "＋", lambda: self._ajustar_zoom(10), self.modo_escuro,
                       variante="ghost", tamanho="sm").pack(side="left")
        widgets.Botao(barra_zoom, "Ajustar", self._zoom_ajustar, self.modo_escuro,
                       variante="ghost", tamanho="sm").pack(side="left")
        barra_zoom.place(relx=0.5, rely=1.0, anchor="s", y=-14)

        painel = tk.Frame(self.paned, bg=t["bg_panel"])
        self._painel_direito = painel
        self._montar_painel_direito(painel, t)

        self.paned.add(frame_canvas, minsize=360, stretch="always")
        self.paned.add(painel, minsize=250, width=300, stretch="never")
        # A divisa é posicionada por proporção, não por pixels fixos (largura
        # fixa vira "metade da tela" num monitor menor). Só dá pra calcular
        # depois que o layout do state("zoomed") assenta, então espera-se o
        # primeiro <Configure> com largura real — e depois disso a divisa fica
        # por conta do usuário, que pode arrastar como quiser.
        self._divisao_aplicada = False
        self.paned.bind("<Configure>", self._ao_redimensionar_paned)

        self._montar_barra_status(t)

    def _montar_barra_superior(self, t):
        barra = tk.Frame(self, bg=t["bg_panel"], height=58)
        barra.grid(row=1, column=0, columnspan=2, sticky="ew")
        barra.grid_propagate(False)

        tk.Label(barra, text="Cor", bg=t["bg_panel"], fg=t["text_tertiary"],
                 font=(theme.FONT, theme.FS_BODY)).pack(side="left", padx=(16, 8))
        self._swatches_cor = {}
        for cor in theme.PALETTE:
            wrap = tk.Frame(barra, bg=t["bg_panel"])
            wrap.pack(side="left", padx=3)
            q = tk.Frame(wrap, bg=cor, width=22, height=22, cursor="hand2")
            q.pack_propagate(False)
            q.pack(padx=2, pady=2)
            q.bind("<Button-1>", lambda e, c=cor: self._escolher_cor_predefinida(c))
            self._swatches_cor[cor] = wrap
        # Amostra da cor personalizada, no mesmo formato das pré-definidas.
        wrap_custom = tk.Frame(barra, bg=t["bg_panel"], highlightbackground=t["border"],
                                highlightcolor=t["border"], highlightthickness=1)
        wrap_custom.pack(side="left", padx=(theme.SP_SM, theme.SP_LG))
        self.btn_cor_custom = tk.Frame(wrap_custom, bg=self.cor_selecionada, width=26, height=22,
                                        cursor="hand2")
        self.btn_cor_custom.pack_propagate(False)
        self.btn_cor_custom.pack(padx=2, pady=2)
        self.btn_cor_custom.bind("<Button-1>", lambda e: self.escolher_cor())
        self._atualizar_swatches_cor()

        tk.Frame(barra, bg=t["border_soft"], width=1, height=28).pack(side="left", padx=8)

        # O rótulo vira "Tamanho" quando há um emoji selecionado: "espessura"
        # não significa nada pra emoji, e é o mesmo controle que regula os dois.
        self.lbl_rotulo_espessura = tk.Label(barra, text="Espessura", bg=t["bg_panel"],
                                              fg=t["text_tertiary"],
                                              font=(theme.FONT, theme.FS_BODY))
        self.lbl_rotulo_espessura.pack(side="left", padx=(8, 8))
        self.slider_espessura = widgets.Deslizante(barra, 2, 14, self.espessura, self.modo_escuro,
                                                    bg=t["bg_panel"],
                                                    on_change=self._on_espessura_change)
        self.slider_espessura.pack(side="left")
        self.lbl_espessura = tk.Label(barra, text=f"{self.espessura} px", bg=t["bg_panel"],
                                       fg=t["text_primary"],
                                       font=(theme.FONT, theme.FS_BODY, "bold"))
        self.lbl_espessura.pack(side="left", padx=8)

        tk.Frame(barra, bg=t["border_soft"], width=1, height=28).pack(side="left", padx=8)

        tk.Label(barra, text="Estilo", bg=t["bg_panel"], fg=t["text_tertiary"],
                 font=(theme.FONT, theme.FS_BODY)).pack(side="left", padx=(8, 6))
        self.pill_solido = widgets.Pill(barra, "Sólido", self.modo_escuro, bg=t["bg_panel"],
                                         ativo=not self.tracejado, altura=30, fonte_pt=10,
                                         comando=lambda: self._definir_estilo(False))
        self.pill_solido.pack(side="left", padx=2)
        self.pill_tracejado = widgets.Pill(barra, "Tracejado", self.modo_escuro, bg=t["bg_panel"],
                                            ativo=self.tracejado, altura=30, fonte_pt=10,
                                            comando=lambda: self._definir_estilo(True))
        self.pill_tracejado.pack(side="left", padx=2)

        widgets.botao_secundario(barra, "↷ Refazer", self.refazer, self.modo_escuro).pack(
            side="right", padx=(4, 16))
        widgets.botao_secundario(barra, "↶ Desfazer", self.desfazer, self.modo_escuro).pack(
            side="right", padx=4)

    def _montar_coluna_ferramentas(self, t):
        coluna = tk.Frame(self, bg=t["bg_footer"], width=72)
        coluna.grid(row=2, column=0, sticky="ns")
        coluna.grid_propagate(False)
        self.botoes_ferramenta = {}
        for nome, desenhar, rotulo in FERRAMENTAS_COLUNA:
            b = widgets.BlocoFerramenta(coluna, desenhar, rotulo, self.modo_escuro,
                                         comando=lambda n=nome: self._selecionar_ferramenta(n),
                                         bg=t["bg_footer"])
            b.pack(pady=2, padx=8)
            self.botoes_ferramenta[nome] = b
        tk.Frame(coluna, bg=t["border_soft"], height=1).pack(fill="x", pady=8, padx=10)
        b_apagar = widgets.BlocoFerramenta(coluna, _ic_apagar, "Apagar", self.modo_escuro,
                                            comando=lambda: self._selecionar_ferramenta("apagar"),
                                            bg=t["bg_footer"])
        b_apagar.pack(pady=2, padx=8)
        self.botoes_ferramenta["apagar"] = b_apagar

    def _montar_painel_direito(self, painel, t):
        # O rodapé é empacotado primeiro, preso embaixo e FORA da área de
        # rolagem: as ações principais continuam visíveis mesmo com a janela
        # baixa ou o painel cheio de anotações.
        self._montar_rodape_painel(painel, t)

        # Corpo rolável. O itemconfig no <Configure> prende a largura do
        # conteúdo à largura do canvas — sem isso os blocos mantêm a largura
        # natural deles e vazam pra fora do painel (era o que cortava
        # "LEGENDA DA CAPTURA" e os metadados) em vez de quebrar linha.
        corpo_wrap = tk.Frame(painel, bg=t["bg_panel"])
        corpo_wrap.pack(fill="both", expand=True)
        canvas_painel = tk.Canvas(corpo_wrap, bg=t["bg_panel"], highlightthickness=0, width=1)
        barra_painel = tk.Scrollbar(corpo_wrap, orient="vertical", command=canvas_painel.yview)
        conteudo = tk.Frame(canvas_painel, bg=t["bg_panel"])
        janela_conteudo = canvas_painel.create_window((0, 0), window=conteudo, anchor="nw")
        canvas_painel.configure(yscrollcommand=barra_painel.set)
        canvas_painel.pack(side="left", fill="both", expand=True)
        barra_painel.pack(side="right", fill="y")
        conteudo.bind("<Configure>",
                       lambda e: canvas_painel.config(scrollregion=canvas_painel.bbox("all")))
        canvas_painel.bind("<Configure>",
                            lambda e: canvas_painel.itemconfig(janela_conteudo, width=e.width))
        canvas_painel.bind("<Enter>", lambda e: canvas_painel.bind_all(
            "<MouseWheel>",
            lambda ev: canvas_painel.yview_scroll(int(-1 * (ev.delta / 120)), "units")))
        canvas_painel.bind("<Leave>", lambda e: canvas_painel.unbind_all("<MouseWheel>"))

        painel = conteudo  # os blocos abaixo vão pro corpo rolável

        bloco_camadas = tk.Frame(painel, bg=t["bg_panel"])
        bloco_camadas.pack(fill="x", padx=14, pady=(14, 10))
        widgets.texto_fluido(bloco_camadas, "ANOTAÇÕES", self.modo_escuro,
                              fonte=(theme.FONT, theme.FS_EYEBROW, "bold")).pack(fill="x")
        self.frame_camadas = tk.Frame(bloco_camadas, bg=t["bg_panel"])
        self.frame_camadas.pack(fill="x", pady=(8, 0))

        tk.Frame(painel, bg=t["border_soft"], height=1).pack(fill="x")

        bloco_legenda = tk.Frame(painel, bg=t["bg_panel"])
        bloco_legenda.pack(fill="x", padx=14, pady=10)
        widgets.texto_fluido(bloco_legenda, "LEGENDA DA CAPTURA", self.modo_escuro,
                              fonte=(theme.FONT, theme.FS_EYEBROW, "bold")).pack(fill="x")
        self.txt_legenda = tk.Text(bloco_legenda, height=4, font=(theme.FONT, theme.FS_BODY),
                                    wrap="word", bd=0, relief="flat",
                                    bg=t["bg_input"], fg=t["text_primary"],
                                    insertbackground=t["text_primary"],
                                    highlightbackground=t["border_input"],
                                    highlightcolor=t["border_input"], highlightthickness=1)
        self.txt_legenda.pack(fill="x", pady=6)
        self.txt_legenda.insert("1.0", self.legenda_inicial)
        # O próprio `insert` acima liga a marca de "modificado" do widget. Sem
        # desligá-la aqui, abrir um print que já tem legenda nascia como
        # "Alterações não gravadas", e fechar sempre perguntava se era pra sair
        # sem gravar — mesmo sem ninguém ter digitado nada.
        self.txt_legenda.edit_modified(False)
        self.txt_legenda.bind("<<Modified>>", self._on_legenda_change)
        widgets.texto_fluido(bloco_legenda, "Usada como título no documento",
                              self.modo_escuro).pack(fill="x")

        tk.Frame(painel, bg=t["border_soft"], height=1).pack(fill="x")

        bloco_caso = tk.Frame(painel, bg=t["bg_panel"])
        bloco_caso.pack(fill="x", padx=14, pady=10)
        widgets.texto_fluido(bloco_caso, "CASO / PROJETO", self.modo_escuro,
                              fonte=(theme.FONT, theme.FS_EYEBROW, "bold")).pack(fill="x")
        caixa_caso = tk.Frame(bloco_caso, bg=t["bg_input"], highlightbackground=t["border_input"],
                               highlightthickness=1)
        caixa_caso.pack(fill="x", pady=6)
        self.entry_caso = tk.Entry(caixa_caso, bg=t["bg_input"], fg=t["text_primary"],
                                   relief="flat",
                                    insertbackground=t["text_primary"],
                                    font=(theme.FONT, theme.FS_BODY))
        self.entry_caso.pack(fill="x", padx=8, pady=6)
        self.entry_caso.insert(0, self.caso_inicial)
        self.entry_caso.bind("<KeyRelease>", lambda e: self._marcar_sujo())
        widgets.texto_fluido(bloco_caso, "Opcional — aparece como marcador no painel",
                              self.modo_escuro).pack(fill="x")

    def _ao_redimensionar_paned(self, event):
        """Aplica a proporção imagem/painel uma única vez, quando a largura
        real da janela já existe. Depois disso não mexe mais, pra não desfazer
        o ajuste que o usuário fizer arrastando a divisa."""
        if self._divisao_aplicada or event.width < 600:
            return
        self._divisao_aplicada = True
        painel_alvo = max(280, min(440, int(event.width * 0.30)))
        try:
            # paneconfigure, não sash_place: o painel foi adicionado com
            # largura própria e stretch="never", então o Tk reimpõe essa
            # largura no relayout e desfaz o sash_place.
            self.paned.paneconfigure(self._painel_direito, width=painel_alvo)
        except Exception:
            pass

    def _montar_rodape_painel(self, painel, t):
        """Ações do painel, presas no rodapé.

        Hierarquia em vez de 4 botões iguais lado a lado: num painel estreito
        4 colunas deixam cada rótulo sem largura pra ficar legível. A ação
        principal ocupa a linha inteira e as secundárias ficam agrupadas.
        """
        rodape = tk.Frame(painel, bg=t["bg_footer"])
        rodape.pack(fill="x", side="bottom")
        tk.Frame(rodape, bg=t["border_soft"], height=1).pack(fill="x")
        widgets.Botao(rodape, "Gravar", self.gravar, self.modo_escuro,
                       variante="primario").pack(
                           fill="x", padx=theme.SP_MD, pady=(theme.SP_MD, theme.SP_SM))
        widgets.Botao(rodape, "Gravar e fechar", self.gravar_e_fechar, self.modo_escuro,
                       bg=t["bg_footer"]).pack(fill="x", padx=theme.SP_MD, pady=(0, theme.SP_SM))
        # "Copiar" saiu do rodapé a pedido — com 3 botões empilhados sobra
        # largura pra cada rótulo. A ação continua disponível no Ctrl+C.
        widgets.Botao(rodape, "Salvar cópia", self.salvar_copia, self.modo_escuro,
                       bg=t["bg_footer"]).pack(
            fill="x", padx=theme.SP_MD, pady=(0, theme.SP_MD))

    def _montar_barra_status(self, t):
        status = tk.Frame(self, bg=t["bg_header"], height=30)
        status.grid(row=3, column=0, columnspan=2, sticky="ew")
        status.grid_propagate(False)
        self.lbl_status_ferramenta = tk.Label(status, text="Ferramenta: Seta", bg=t["bg_header"],
                                               fg=t["text_tertiary"],
                                               font=(theme.FONT, theme.FS_CAPTION))
        self.lbl_status_ferramenta.pack(side="left", padx=14)
        self.lbl_status_pos = tk.Label(status, text="x 0 · y 0", bg=t["bg_header"],
                                       fg=t["text_tertiary"],
                                        font=(theme.FONT, theme.FS_CAPTION))
        self.lbl_status_pos.pack(side="left", padx=14)
        self.lbl_status_sujo = tk.Label(status, text="Gravado", bg=t["bg_header"], fg=t["success"],
                                         font=(theme.FONT, theme.FS_CAPTION, "bold"))
        self.lbl_status_sujo.pack(side="right", padx=14)

    # ---------- ferramentas / cor / estilo ----------

    def _selecionar_ferramenta(self, nome):
        # "texto" não pergunta mais nada aqui: o texto é digitado direto na
        # imagem, no ponto clicado (ver _abrir_editor_texto).
        self._encerrar_editor_texto(gravar=True)
        if nome == "emoji":
            # abre a grade de emojis; a ferramenta só fica ativa depois da
            # escolha, senão o usuário ficaria com a ferramenta armada sem
            # saber qual emoji seria inserido
            self._abrir_seletor_emoji()
            return
        self.ferramenta = nome
        self.selected_id = None
        self._definir_ferramenta_ativa(nome)
        self._atualizar_status()
        self._redraw_canvas()

    def _abrir_seletor_emoji(self):
        def escolhido(caractere, tamanho):
            self.emoji_atual = caractere
            self.tamanho_emoji = tamanho
            self.ferramenta = "emoji"
            self.selected_id = None
            self._definir_ferramenta_ativa("emoji")
            self._atualizar_status()
            self._redraw_canvas()

        self.parent.pausar_timer = True
        try:
            emoji_picker.SeletorEmoji(self, self.modo_escuro, escolhido,
                                       tamanho_inicial=self.tamanho_emoji)
        finally:
            self.parent.pausar_timer = False

    def _definir_ferramenta_ativa(self, nome):
        for n, b in self.botoes_ferramenta.items():
            b.definir_ativo(n == nome)

    def _escolher_cor_predefinida(self, c):
        self.cor_selecionada = c
        self.btn_cor_custom.config(bg=c)
        self._atualizar_swatches_cor()
        if self.selected_id is not None:
            shp = self._get_shape(self.selected_id)
            if shp:
                self._push_undo()
                shp["color"] = c
                self._marcar_sujo()
                self._redraw_canvas()
                self._atualizar_lista_camadas()

    def escolher_cor(self):
        self.parent.pausar_timer = True
        cores = colorchooser.askcolor(color=self.cor_selecionada, parent=self)
        self.parent.pausar_timer = False
        if cores[1]:
            self._escolher_cor_predefinida(cores[1])

    def _on_espessura_change(self, val):
        valor = int(float(val))
        shp = self._get_shape(self.selected_id) if self.selected_id is not None else None

        if shp and shp["tool"] == "emoji":
            # com emoji selecionado o mesmo controle regula o TAMANHO dele:
            # 2..14 do slider vira 20..104px, que cobre do discreto ao grande
            tamanho = 20 + (valor - 2) * 7
            shp["tamanho"] = tamanho
            self.tamanho_emoji = tamanho
            self._marcar_sujo()
            self._atualizar_rotulo_espessura()
            self._redraw_canvas()
            return

        self.espessura = valor
        self._atualizar_rotulo_espessura()
        if shp:
            shp["width"] = self.espessura
            self._marcar_sujo()
            self._redraw_canvas()

    def _atualizar_rotulo_espessura(self):
        """Mostra 'Tamanho' e o valor em px do emoji quando há um selecionado."""
        shp = self._get_shape(self.selected_id) if self.selected_id is not None else None
        if shp and shp["tool"] == "emoji":
            self.lbl_rotulo_espessura.config(text="Tamanho")
            self.lbl_espessura.config(text=f"{int(shp.get('tamanho', TAMANHO_EMOJI_PADRAO))} px")
            valor_slider = max(2,
                min(14, round((shp.get("tamanho", TAMANHO_EMOJI_PADRAO) - 20) / 7) + 2))
            self.slider_espessura.definir(valor_slider)
        else:
            self.lbl_rotulo_espessura.config(text="Espessura")
            self.lbl_espessura.config(text=f"{self.espessura} px")
            self.slider_espessura.definir(self.espessura)

    def _definir_estilo(self, tracejado):
        self.tracejado = tracejado
        self._atualizar_botoes_estilo()
        if self.selected_id is not None:
            shp = self._get_shape(self.selected_id)
            if shp:
                self._push_undo()
                shp["dash"] = tracejado
                self._marcar_sujo()
                self._redraw_canvas()

    def _atualizar_botoes_estilo(self):
        self.pill_solido.definir("Sólido", not self.tracejado)
        self.pill_tracejado.definir("Tracejado", self.tracejado)

    def _atualizar_swatches_cor(self):
        t = theme.get(self.modo_escuro)
        for cor, wrap in self._swatches_cor.items():
            selecionada = cor == self.cor_selecionada
            # Espessura fixa e só a cor muda: além de não deslocar as amostras
            # a cada seleção, garante contorno nas cores escuras, que no tema
            # noturno somem contra o fundo quando não têm borda.
            contorno = t["accent"] if selecionada else t["border"]
            wrap.config(highlightbackground=contorno, highlightcolor=contorno,
                        highlightthickness=2)

    def _ajustar_zoom(self, delta):
        atual = 100 if self.zoom_mode == "fit" else self.zoom_mode
        self.zoom_mode = max(10, min(400, atual + delta))
        self._redraw_canvas()

    def _zoom_ajustar(self):
        self.zoom_mode = "fit"
        self._redraw_canvas()

    # ---------- desfazer / refazer ----------

    def _next_shape_id(self):
        self._shape_seq += 1
        return self._shape_seq

    def _get_shape(self, sid):
        for s in self.shapes:
            if s["id"] == sid:
                return s
        return None

    def _push_undo(self):
        self.undo_stack.append(copy.deepcopy(self.shapes))
        self.redo_stack.clear()
        if len(self.undo_stack) > 60:
            self.undo_stack.pop(0)

    def _foco_em_campo_de_texto(self):
        try:
            foco = self.focus_get()
        except Exception:
            return False
        return isinstance(foco, (tk.Entry, tk.Text))

    def _atalho_da_imagem(self, acao, passa_evento=False):
        """Atalho que so vale fora dos campos de texto.

        Sem esse filtro o Ctrl+C da janela rodava logo depois do Ctrl+C do
        campo e trocava o texto copiado pela imagem - o colar seguinte vinha
        vazio. Vale igual para desfazer, refazer e Delete, que mexeriam nas
        anotacoes enquanto o usuario digita a legenda.
        """
        def tratar(event=None):
            if self._foco_em_campo_de_texto():
                return None
            if passa_evento:
                acao(event)
            else:
                acao()
            return "break"
        return tratar

    def desfazer(self):
        if not self.undo_stack:
            return
        self.redo_stack.append(copy.deepcopy(self.shapes))
        self.shapes = self.undo_stack.pop()
        self.selected_id = None
        self._marcar_sujo()
        self._redraw_canvas()
        self._atualizar_lista_camadas()

    def refazer(self):
        if not self.redo_stack:
            return
        self.undo_stack.append(copy.deepcopy(self.shapes))
        self.shapes = self.redo_stack.pop()
        self.selected_id = None
        self._marcar_sujo()
        self._redraw_canvas()
        self._atualizar_lista_camadas()

    # ---------- camadas ----------

    def _atualizar_lista_camadas(self):
        for w in self.frame_camadas.winfo_children():
            w.destroy()
        t = theme.get(self.modo_escuro)
        if not self.shapes:
            tk.Label(self.frame_camadas, text="Nenhuma anotação ainda", bg=t["bg_panel"],
                     fg=t["text_muted"],
                     font=(theme.FONT, theme.FS_BODY)).pack(anchor="w", pady=6)
            return
        for shp in reversed(self.shapes):
            selecionado = shp["id"] == self.selected_id
            cor_fundo = t["accent_bg"] if selecionado else t["bg_panel"]
            linha = tk.Frame(self.frame_camadas, bg=cor_fundo)
            linha.pack(fill="x", pady=2)
            sw = tk.Frame(linha, bg=shp.get("color", "#999999"), width=14, height=14)
            sw.pack_propagate(False)
            sw.pack(side="left", padx=(6, 8), pady=6)
            rotulo = TOOL_LABELS.get(shp["tool"], shp["tool"])
            if shp["tool"] == "texto" and shp.get("text"):
                rotulo += f" · {shp['text'][:16]}"
            if shp["tool"] == "passo":
                rotulo += f" {shp.get('step_n', '')}"
            lbl = tk.Label(linha, text=rotulo, bg=cor_fundo,
                           fg=t["text_primary"] if selecionado else t["text_secondary"],
                           font=(theme.FONT, theme.FS_BODY, "bold" if selecionado else "normal"),
                           anchor="w")
            lbl.pack(side="left", fill="x", expand=True)
            olho = tk.Label(linha, text=("👁" if shp.get("visible", True) else "⊘"), bg=cor_fundo,
                            fg=t["text_tertiary"], cursor="hand2")
            olho.pack(side="right", padx=8)
            for widget in (linha, lbl):
                widget.bind("<Button-1>", lambda e, sid=shp["id"]: self._selecionar_camada(sid))
            olho.bind("<Button-1>", lambda e, sid=shp["id"]: self._alternar_visibilidade(sid))

    def _selecionar_camada(self, sid):
        self.ferramenta = "mover"
        self._definir_ferramenta_ativa("mover")
        self.selected_id = sid
        self._atualizar_status()
        self._redraw_canvas()
        self._atualizar_lista_camadas()

    def _alternar_visibilidade(self, sid):
        shp = self._get_shape(sid)
        if shp:
            shp["visible"] = not shp.get("visible", True)
            self._marcar_sujo()
            self._redraw_canvas()
            self._atualizar_lista_camadas()

    # ---------- status ----------

    def _atualizar_status(self):
        self.lbl_status_ferramenta.config(
            text=f"Ferramenta: {TOOL_LABELS.get(self.ferramenta, self.ferramenta)}")
        if hasattr(self, "lbl_rotulo_espessura"):
            # a barra superior acompanha a seleção (espessura x tamanho do emoji)
            self._atualizar_rotulo_espessura()
        t = theme.get(self.modo_escuro)
        if self.sujo:
            self.lbl_status_sujo.config(text="Alterações não gravadas", fg=t["danger_text"])
        else:
            self.lbl_status_sujo.config(text="Gravado", fg=t["success"])

    def _marcar_sujo(self):
        self.sujo = True
        self._atualizar_status()

    def _on_mouse_move(self, e):
        ix, iy = self._canvas_to_img(e.x, e.y)
        self.lbl_status_pos.config(text=f"x {int(ix)} · y {int(iy)}")

    def _on_legenda_change(self, event=None):
        if self.txt_legenda.edit_modified():
            self._marcar_sujo()
            self.txt_legenda.edit_modified(False)

    # ---------- conversão de coordenadas ----------

    def _img_to_canvas(self, x, y):
        return self.ox + x * self.escala, self.oy + y * self.escala

    def _canvas_to_img(self, x, y):
        if self.escala == 0:
            return 0, 0
        return (x - self.ox) / self.escala, (y - self.oy) / self.escala

    # ---------- desenho no canvas ----------

    def _redraw_canvas(self):
        self.canvas.delete("all")
        lw, lh = self.canvas.winfo_width(), self.canvas.winfo_height()
        if lw < 2 or lh < 2:
            self.after(80, self._redraw_canvas)
            return
        if self.zoom_mode == "fit":
            self.escala = min(lw / self.img_raw.width, lh / self.img_raw.height) * 0.95
        else:
            self.escala = self.zoom_mode / 100
        self.escala = max(self.escala, 0.02)
        nw = max(1, int(self.img_raw.width * self.escala))
        nh = max(1, int(self.img_raw.height * self.escala))
        self.img_view = self.img_raw.resize((nw, nh), Image.Resampling.LANCZOS)
        self.tk_img = ImageTk.PhotoImage(self.img_view)
        self.ox = (lw - nw) // 2
        self.oy = (lh - nh) // 2
        self.canvas.create_image(self.ox, self.oy, image=self.tk_img, anchor="nw", tags="bg_img")
        self._imagens_borrao = []
        self._bbox_texto = {}
        for shp in self.shapes:
            if shp.get("visible", True):
                self._draw_shape_on_canvas(shp)
        if hasattr(self, "lbl_zoom"):
            # Sempre a porcentagem real, inclusive no modo "ajustar": repetir
            # a palavra do botão ao lado não informaria o zoom atual.
            self.lbl_zoom.config(text=f"{int(round(self.escala * 100))}%")

    def _draw_shape_on_canvas(self, shp):
        x1, y1, x2, y2 = shp["coords"]
        cx1, cy1 = self._img_to_canvas(x1, y1)
        cx2, cy2 = self._img_to_canvas(x2, y2)
        cor = shp.get("color", "#E8590C")
        largura = max(1, int(shp.get("width", 4) * self.escala))
        destaque = shp["id"] == self.selected_id
        if destaque:
            largura += 2
        dash = (6, 4) if shp.get("dash") else None
        tool = shp["tool"]

        if tool == "retangulo":
            self.canvas.create_rectangle(cx1, cy1, cx2, cy2, outline=cor, width=largura, dash=dash)
        elif tool == "elipse":
            self.canvas.create_oval(cx1, cy1, cx2, cy2, outline=cor, width=largura, dash=dash)
        elif tool == "seta":
            self.canvas.create_line(cx1, cy1, cx2, cy2, fill=cor, width=largura, arrow=tk.LAST,
                                     arrowshape=(18, 22, 10))
        elif tool == "marcador":
            self.canvas.create_rectangle(cx1, cy1, cx2, cy2, fill=cor, stipple="gray50", outline="")
        elif tool == "texto":
            item = self.canvas.create_text(cx1, cy1, text=shp.get("text", ""), fill=cor,
                                            font=(theme.FONT, max(10, int(20 * self.escala))),
                                            anchor="nw")
            caixa = self.canvas.bbox(item)
            if caixa:
                xa, ya = self._canvas_to_img(caixa[0], caixa[1])
                xb, yb = self._canvas_to_img(caixa[2], caixa[3])
                self._bbox_texto[shp["id"]] = (xa, ya, xb, yb)
        elif tool == "emoji":
            # Desenhado em PIL e colado como imagem, não com create_text: o Tk
            # renderiza emoji em preto e branco, então a prévia divergia do PNG
            # gravado, que sai colorido. Mesmo recurso usado na prévia do Borrar.
            tamanho = int(shp.get("tamanho", TAMANHO_EMOJI_PADRAO))
            tamanho_tela = max(8, int(tamanho * self.escala))
            try:
                img_emoji = emoji_picker.renderizar(shp.get("text", "✅"), tamanho_tela)
                foto = ImageTk.PhotoImage(img_emoji)
                self._imagens_borrao.append(foto)  # mesma lista que segura as refs
                self.canvas.create_image(cx1, cy1, image=foto)
                meio = tamanho / 2
                self._bbox_texto[shp["id"]] = (x1 - meio, y1 - meio, x1 + meio, y1 + meio)
            except Exception:
                self.canvas.create_text(cx1, cy1, text=shp.get("text", "✅"),
                                         font=("Segoe UI Emoji", max(12, tamanho_tela)))
        elif tool == "passo":
            r = max(9, int(14 * self.escala))
            self.canvas.create_oval(cx1 - r, cy1 - r, cx1 + r, cy1 + r,
                                    fill=cor, outline="#ffffff", width=2)
            self.canvas.create_text(cx1, cy1, text=str(shp.get("step_n", 1)), fill="#ffffff",
                                     font=(theme.FONT, max(9, int(13 * self.escala)), "bold"))
        elif tool == "borrao":
            xa, xb = sorted((x1, x2))
            ya, yb = sorted((y1, y2))
            mostrado = False
            if xb - xa >= 2 and yb - ya >= 2:
                try:
                    recorte = self.img_raw.crop((int(xa), int(ya), int(xb), int(yb))).convert("RGB")
                    utils.pixelate_region(recorte, [0, 0, recorte.width, recorte.height], block=10)
                    largura_view = max(1, int((xb - xa) * self.escala))
                    altura_view = max(1, int((yb - ya) * self.escala))
                    recorte_view = recorte.resize((largura_view, altura_view), Image.NEAREST)
                    img_tk_borrao = ImageTk.PhotoImage(recorte_view)
                    self._imagens_borrao.append(img_tk_borrao)
                    xc1, yc1 = self._img_to_canvas(xa, ya)
                    self.canvas.create_image(xc1, yc1, image=img_tk_borrao, anchor="nw")
                    mostrado = True
                except Exception:
                    mostrado = False
            if not mostrado:
                self.canvas.create_rectangle(cx1, cy1, cx2, cy2,
                                             outline="#8EA2AD", width=2, dash=(4, 3),
                                              fill="#B8C4CB", stipple="gray25")
            self.canvas.create_rectangle(cx1, cy1, cx2, cy2,
                                         outline="#8EA2AD", width=1, dash=(3, 2))

        if destaque:
            t = theme.get(self.modo_escuro)
            xa, xb = sorted((cx1, cx2))
            ya, yb = sorted((cy1, cy2))
            self.canvas.create_rectangle(xa - 4, ya - 4, xb + 4, yb + 4,
                                         outline=t["accent"], dash=(2, 2))

    # ---------- hit test (mover / apagar) ----------

    def _hit_test(self, ix, iy):
        tol_img = 8 / max(self.escala, 0.01)
        for shp in reversed(self.shapes):
            if not shp.get("visible", True):
                continue
            x1, y1, x2, y2 = shp["coords"]
            if shp["tool"] == "texto":
                # O texto é desenhado a partir do canto (anchor="nw"), então
                # ele se estende pra direita/baixo do ponto clicado. Testar só
                # um raio em volta do canto fazia o clique no meio da frase
                # não pegar — por isso não dava pra arrastar o texto. Usa-se a
                # caixa real medida no desenho.
                caixa = self._bbox_texto.get(shp["id"])
                if caixa:
                    if (caixa[0] - tol_img <= ix <= caixa[2] + tol_img
                            and caixa[1] - tol_img <= iy <= caixa[3] + tol_img):
                        return shp["id"]
                    continue
                if math.hypot(ix - x1, iy - y1) <= 24 / max(self.escala, 0.01):
                    return shp["id"]
                continue
            if shp["tool"] == "emoji":
                # usa o tamanho real do emoji: com raio fixo, um emoji grande
                # só respondia ao clique perto do centro
                meio = max(12, int(shp.get("tamanho", TAMANHO_EMOJI_PADRAO)) / 2)
                if abs(ix - x1) <= meio and abs(iy - y1) <= meio:
                    return shp["id"]
                continue
            if shp["tool"] == "passo":
                if math.hypot(ix - x1, iy - y1) <= 24 / max(self.escala, 0.01):
                    return shp["id"]
                continue
            if shp["tool"] == "seta":
                if utils.dist_point_segment(ix, iy, x1, y1, x2, y2) <= tol_img:
                    return shp["id"]
                continue
            xa, xb = sorted((x1, x2))
            ya, yb = sorted((y1, y2))
            dentro = (xa - tol_img <= ix <= xb + tol_img) and (ya - tol_img <= iy <= yb + tol_img)
            if not dentro:
                continue
            if shp["tool"] in ("marcador", "borrao"):
                return shp["id"]
            borda = not (xa + tol_img < ix < xb - tol_img and ya + tol_img < iy < yb - tol_img)
            if borda:
                return shp["id"]
        return None

    def _abrir_editor_texto(self, ix, iy, sid=None):
        """Caixa de texto na própria imagem, como no Paint.

        A edição acontece no ponto clicado para que o usuário veja onde o
        texto cai enquanto digita. Enter, ou clicar fora, converte o que foi
        digitado numa anotação, que continua movível pela ferramenta Mover.
        Esc cancela.
        """
        self._encerrar_editor_texto(gravar=True)
        t = theme.get(self.modo_escuro)
        shp = self._get_shape(sid) if sid is not None else None
        inicial = shp.get("text", "") if shp else ""
        cor = shp.get("color", self.cor_selecionada) if shp else self.cor_selecionada

        entrada = tk.Entry(self.canvas, bd=0, relief="flat", bg=t["bg_input"], fg=cor,
                            insertbackground=cor, highlightbackground=t["accent"],
                            highlightcolor=t["accent"], highlightthickness=2,
                            font=(theme.FONT, max(10, int(20 * self.escala))))
        entrada.insert(0, inicial)
        cx, cy = self._img_to_canvas(ix, iy)
        entrada.place(x=cx, y=cy, width=max(160, int(240 * self.escala)))
        entrada.focus_set()
        entrada.select_range(0, "end")
        entrada.bind("<Return>", lambda e: self._encerrar_editor_texto(gravar=True))
        entrada.bind("<Escape>", lambda e: self._encerrar_editor_texto(gravar=False))
        entrada.bind("<FocusOut>", lambda e: self._encerrar_editor_texto(gravar=True))
        self._editor_texto = {"widget": entrada, "ix": ix, "iy": iy, "sid": sid}

    def _encerrar_editor_texto(self, gravar=True):
        dados = getattr(self, "_editor_texto", None)
        if not dados:
            return
        # Zerar antes de destruir: destruir dispara FocusOut, que reentra aqui
        self._editor_texto = None
        entrada = dados["widget"]
        try:
            texto = entrada.get().strip()
            entrada.destroy()
        except Exception:
            return
        if not gravar:
            return

        sid = dados["sid"]
        if sid is not None:
            shp = self._get_shape(sid)
            if shp:
                self._push_undo()
                if texto:
                    shp["text"] = texto
                else:
                    self.shapes = [s for s in self.shapes if s["id"] != sid]
                self._marcar_sujo()
        elif texto:
            self._push_undo()
            novo_id = self._next_shape_id()
            ix, iy = dados["ix"], dados["iy"]
            self.shapes.append({
                "id": novo_id, "tool": "texto", "coords": [ix, iy, ix, iy],
                "color": self.cor_selecionada, "width": self.espessura, "dash": False,
                "visible": True, "text": texto,
            })
            self.texto_atual = texto
            self._marcar_sujo()
            self._concluir_criacao(novo_id)

        self._redraw_canvas()
        self._atualizar_lista_camadas()

    def _on_duplo_clique(self, event):
        """Duplo clique num texto existente reabre a edição no lugar."""
        ix, iy = self._canvas_to_img(event.x, event.y)
        sid = self._hit_test(ix, iy)
        shp = self._get_shape(sid) if sid is not None else None
        if shp and shp["tool"] == "texto":
            self._abrir_editor_texto(shp["coords"][0], shp["coords"][1], sid=sid)

    def _concluir_criacao(self, sid):
        """Depois de criar uma forma nova, já deixa ela selecionada com a
        ferramenta Mover ativa — dá pra ajustar a posição na hora, sem
        precisar trocar de ferramenta manualmente antes de gravar."""
        self.selected_id = sid
        self.ferramenta = "mover"
        self._definir_ferramenta_ativa("mover")
        self._atualizar_status()

    def _apagar_selecionado_tecla(self, event=None):
        if self.ferramenta == "mover" and self.selected_id is not None:
            self._push_undo()
            self.shapes = [s for s in self.shapes if s["id"] != self.selected_id]
            self.selected_id = None
            self._marcar_sujo()
            self._redraw_canvas()
            self._atualizar_lista_camadas()

    # ---------- eventos do mouse no canvas ----------

    def on_press(self, e):
        # Clicar no canvas com uma caixa de texto aberta confirma o texto —
        # o <FocusOut> sozinho não cobre isso porque o canvas não rouba o
        # foco no clique.
        if getattr(self, "_editor_texto", None):
            self._encerrar_editor_texto(gravar=True)
            return

        ix, iy = self._canvas_to_img(e.x, e.y)
        ferramenta = self.ferramenta

        if ferramenta == "mover":
            sid = self._hit_test(ix, iy)
            self.selected_id = sid
            if sid is not None:
                self._push_undo()
                self._drag_origem = (ix, iy)
                self._drag_coords_ini = list(self._get_shape(sid)["coords"])
            self._redraw_canvas()
            self._atualizar_lista_camadas()
            return

        if ferramenta == "apagar":
            sid = self._hit_test(ix, iy)
            if sid is not None:
                self._push_undo()
                self.shapes = [s for s in self.shapes if s["id"] != sid]
                self.selected_id = None
                self._marcar_sujo()
                self._redraw_canvas()
                self._atualizar_lista_camadas()
            return

        if ferramenta == "recorte":
            self._crop_start = (ix, iy)
            t = theme.get(self.modo_escuro)
            self._crop_rect_item = self.canvas.create_rectangle(e.x, e.y, e.x, e.y,
                                                                outline=t["accent"],
                                                                  width=2, dash=(5, 3))
            return

        if ferramenta == "passo":
            self._push_undo()
            n = sum(1 for s in self.shapes if s["tool"] == "passo") + 1
            novo_id = self._next_shape_id()
            self.shapes.append({
                "id": novo_id, "tool": "passo", "coords": [ix, iy, ix, iy],
                "color": self.cor_selecionada, "width": self.espessura, "dash": False,
                "visible": True, "step_n": n,
            })
            self._marcar_sujo()
            self._concluir_criacao(novo_id)
            self._redraw_canvas()
            self._atualizar_lista_camadas()
            return

        if ferramenta == "texto":
            self._abrir_editor_texto(ix, iy)
            return

        if ferramenta == "emoji":
            texto = self.emoji_atual
            if not texto:
                return
            self._push_undo()
            novo_id = self._next_shape_id()
            self.shapes.append({
                "id": novo_id, "tool": ferramenta, "coords": [ix, iy, ix, iy],
                "color": self.cor_selecionada, "width": self.espessura, "dash": False,
                "visible": True, "text": texto, "tamanho": self.tamanho_emoji,
            })
            self._marcar_sujo()
            self._concluir_criacao(novo_id)
            self._redraw_canvas()
            self._atualizar_lista_camadas()
            return

        # ferramentas de arraste: retangulo, elipse, seta, marcador, borrao
        self._push_undo()
        novo = {
            "id": self._next_shape_id(), "tool": ferramenta, "coords": [ix, iy, ix, iy],
            "color": self.cor_selecionada, "width": self.espessura,
            "dash": self.tracejado, "visible": True,
        }
        self.shapes.append(novo)
        self._shape_em_progresso = novo["id"]
        self._redraw_canvas()

    def on_drag(self, e):
        ix, iy = self._canvas_to_img(e.x, e.y)
        self.lbl_status_pos.config(text=f"x {int(ix)} · y {int(iy)}")

        if self.ferramenta == "recorte" and self._crop_rect_item is not None:
            cx, cy = self._img_to_canvas(*self._crop_start)
            self.canvas.coords(self._crop_rect_item, cx, cy, e.x, e.y)
            return

        if (self.ferramenta == "mover" and self.selected_id is not None
                and self._drag_origem is not None):
            dx = ix - self._drag_origem[0]
            dy = iy - self._drag_origem[1]
            x1, y1, x2, y2 = self._drag_coords_ini
            shp = self._get_shape(self.selected_id)
            if shp:
                shp["coords"] = [x1 + dx, y1 + dy, x2 + dx, y2 + dy]
                self._redraw_canvas()
            return

        if self._shape_em_progresso is not None:
            shp = self._get_shape(self._shape_em_progresso)
            if shp:
                shp["coords"][2] = ix
                shp["coords"][3] = iy
                self._redraw_canvas()

    def on_release(self, e):
        ix, iy = self._canvas_to_img(e.x, e.y)

        if self.ferramenta == "recorte" and self._crop_rect_item is not None:
            self.canvas.delete(self._crop_rect_item)
            self._crop_rect_item = None
            coords = [self._crop_start[0], self._crop_start[1], ix, iy]
            self._crop_start = None
            if abs(coords[2] - coords[0]) > 5 and abs(coords[3] - coords[1]) > 5:
                self._aplicar_recorte(coords)
            return

        if (self.ferramenta == "mover" and self.selected_id is not None
                and self._drag_coords_ini is not None):
            shp = self._get_shape(self.selected_id)
            if shp and shp["coords"] == self._drag_coords_ini:
                if self.undo_stack:
                    self.undo_stack.pop()
            elif shp:
                self._marcar_sujo()
            self._drag_coords_ini = None
            self._drag_origem = None
            return

        if self._shape_em_progresso is not None:
            shp = self._get_shape(self._shape_em_progresso)
            if shp:
                x1, y1, x2, y2 = shp["coords"]
                if abs(x2 - x1) < 3 and abs(y2 - y1) < 3:
                    self.shapes = [s for s in self.shapes if s["id"] != shp["id"]]
                    if self.undo_stack:
                        self.undo_stack.pop()
                else:
                    self._marcar_sujo()
                    self._concluir_criacao(shp["id"])
            self._shape_em_progresso = None
            self._redraw_canvas()
            self._atualizar_lista_camadas()

    def _aplicar_recorte(self, coords):
        if not messagebox.askyesno("Recortar", "Recortar a imagem para a área selecionada?",
                                   parent=self):
            return
        x1, y1, x2, y2 = [int(round(v)) for v in coords]
        x1, x2 = sorted((max(0, x1), max(0, x2)))
        y1, y2 = sorted((max(0, y1), max(0, y2)))
        x2 = min(x2, self.img_raw.width)
        y2 = min(y2, self.img_raw.height)
        if x2 - x1 < 5 or y2 - y1 < 5:
            return

        self._push_undo()
        self.img_raw = self.img_raw.crop((x1, y1, x2, y2)).convert("RGBA")

        # As formas continuam como dados editáveis — só desloca as
        # coordenadas pro novo referencial (0,0 = canto do recorte) em vez
        # de "queimar" tudo em pixel, que é o que fazia um elemento existente
        # sumir/desconfigurar depois de recortar.
        novas_formas = []
        for shp in self.shapes:
            c = shp["coords"]
            nc = [c[0] - x1, c[1] - y1, c[2] - x1, c[3] - y1]
            xa, xb = sorted((nc[0], nc[2]))
            ya, yb = sorted((nc[1], nc[3]))
            if xb < 0 or yb < 0 or xa > (x2 - x1) or ya > (y2 - y1):
                continue  # ficou totalmente fora da nova área
            nova = dict(shp)
            nova["coords"] = nc
            novas_formas.append(nova)
        self.shapes = novas_formas

        self.selected_id = None
        self._shape_em_progresso = None
        self.zoom_mode = "fit"
        self._marcar_sujo()
        self._redraw_canvas()
        self._atualizar_lista_camadas()

    # ---------- ações do rodapé ----------

    def gravar(self):
        meta = {
            "caption": self.txt_legenda.get("1.0", "end").strip(),
            "caso": self.entry_caso.get().strip(),
            "shapes": self.shapes,
        }
        capture_store.save_meta(self.caminho_img, meta)
        self.img_raw.convert("RGBA").save(capture_store.raw_path(self.caminho_img))
        composto = render_composite(self.img_raw,
                                    [s for s in self.shapes if s.get("visible", True)])
        composto.save(self.caminho_img)
        # zera junto a marca do campo de legenda: um evento de modificação
        # ainda na fila voltaria a acender "Alterações não gravadas" logo
        # depois de gravar
        self.txt_legenda.edit_modified(False)
        self.sujo = False
        self._atualizar_status()
        self.callback_atualizar()

    def gravar_e_fechar(self):
        self.gravar()
        self.parent.deiconify()
        self.destroy()

    def salvar_copia(self):
        composto = render_composite(self.img_raw,
                                    [s for s in self.shapes if s.get("visible", True)])
        destino = filedialog.asksaveasfilename(
            defaultextension=".png", filetypes=[("PNG", "*.png")],
            initialfile=os.path.basename(self.caminho_img), parent=self)
        if destino:
            composto.convert("RGB").save(destino)

    def copiar(self):
        composto = render_composite(self.img_raw,
                                    [s for s in self.shapes if s.get("visible", True)])
        utils.copy_image_to_clipboard(composto)

    def fechar_e_voltar(self):
        if self.sujo and not messagebox.askyesno(
                "Sair sem gravar", "Existem edições não gravadas. Sair mesmo assim?", parent=self):
            return
        self.parent.deiconify()
        self.destroy()
