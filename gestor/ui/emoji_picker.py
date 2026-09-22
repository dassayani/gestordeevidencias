"""Seletor de emojis do editor.

Os emojis são apresentados numa grade clicável, com busca por nome em
português e escolha de tamanho, para não depender do painel do Windows
(Win+.).

A renderização é feita com PIL sobre a fonte colorida do Windows
(seguiemj.ttf) e exibida como imagem: o Tk desenha emoji em preto e branco,
então uma prévia em `create_text`/`Label` não corresponderia ao PNG gravado.
"""
import tkinter as tk
from tkinter import Toplevel

from PIL import Image, ImageDraw, ImageFont, ImageTk

from gestor.ui import theme
from gestor.ui import widgets

# Tamanhos oferecidos, em pixels na imagem final.
TAMANHOS = (("P", 32), ("M", 48), ("G", 72))
TAMANHO_PADRAO = 48

_TAM_GRADE = 30      # tamanho de cada emoji dentro da grade
# 7 colunas: com a célula dimensionada pela medida real do glifo (~45px), 8
# colunas estouravam a largura do painel e a última ficava cortada.
_COLUNAS = 7
_MAX_RESULTADOS = 96  # teto pra busca não travar a interface

# Conjunto curado, pensado em evidência/QA. A busca alcança a lista completa.
CATEGORIAS = (
    ("Marcações", "✅ ❌ ⚠️ ❗ ❓ ✔️ ✖️ 🔴 🟡 🟢 🔵 ⭐"),
    ("Setas e foco", "➡️ ⬅️ ⬆️ ⬇️ ↩️ 🔁 👉 👈 👆 👇 🔍 🎯"),
    ("Status", "🔒 🔓 🔑 💡 🔔 ⏰ ⏳ 📌 📎 🏁 🚫 ♻️"),
    ("Reações", "👍 👎 👏 🙂 😐 🙁 😀 😅 😕 😡 🤔 💬"),
    ("Objetos", "🖥️ 💻 📱 🖱️ ⌨️ 🗂️ 📄 📊 📈 🐞 ⚙️ 🧪"),
)


def _fonte(tamanho):
    try:
        return ImageFont.truetype("seguiemj.ttf", tamanho)
    except Exception:
        return ImageFont.load_default()


def normalizar(caractere):
    """Remove seletores de variação e o joiner de largura zero.

    O U+FE0F ("apresentação como emoji") é contado como um glifo próprio pela
    fonte: com ele, ⚠️ e ➡️ medem exatamente o DOBRO da largura e acabavam
    desenhados fora do centro e cortados. O caractere base já renderiza
    colorido na Segoe UI Emoji.
    """
    return "".join(c for c in caractere if c not in ("️", "︎", "‍"))


def renderizar(caractere, tamanho, fundo=None):
    """Desenha o emoji colorido e devolve uma imagem PIL quadrada."""
    texto = normalizar(caractere) or caractere
    fonte = _fonte(tamanho)
    # dimensiona pela medida real do glifo, não por um fator fixo, pra nenhum
    # emoji sair cortado
    try:
        medida = ImageDraw.Draw(Image.new("RGBA", (8, 8))).textbbox(
            (0, 0), texto, font=fonte, embedded_color=True)
        lado = max(int(medida[2] - medida[0]), int(medida[3] - medida[1]), tamanho) + 4
    except Exception:
        lado = int(tamanho * 1.35)
    img = Image.new("RGBA", (lado, lado), (0, 0, 0, 0) if fundo is None else fundo)
    draw = ImageDraw.Draw(img)
    try:
        draw.text((lado / 2, lado / 2), texto, font=fonte, embedded_color=True, anchor="mm")
    except Exception:
        pass
    return img


def _nomes_do_emoji(dados):
    """Nomes de busca: português quando existe, inglês sempre como reserva."""
    partes = []
    for chave in ("pt", "en"):
        valor = dados.get(chave)
        if valor:
            partes.append(valor.strip(":").replace("_", " "))
    return " ".join(partes)


def _carregar_indice():
    """Índice {caractere: nomes} da biblioteca `emoji`, se disponível.

    A busca é um extra: sem o pacote instalado, a grade curada continua
    funcionando normalmente.
    """
    try:
        import emoji as lib_emoji
    except ImportError:
        return {}
    try:
        # uma chamada já carrega a tabela inteira de nomes em português
        lib_emoji.demojize("👍", language="pt")
    except Exception:
        pass
    indice = {}
    for caractere, dados in lib_emoji.EMOJI_DATA.items():
        if len(caractere) > 8:
            continue  # sequências muito compostas renderizam mal
        nomes = _nomes_do_emoji(dados)
        if nomes:
            indice[caractere] = nomes.lower()
    return indice


class SeletorEmoji(Toplevel):
    def __init__(self, parent, dark, ao_escolher, tamanho_inicial=TAMANHO_PADRAO):
        super().__init__(parent)
        self.t = theme.get(dark)
        self.dark = dark
        self.ao_escolher = ao_escolher
        self._imagens = []          # segura as referências das PhotoImage
        self._cache = {}
        self._indice = _carregar_indice()

        self.title("Escolher emoji")
        self.configure(bg=self.t["bg_panel"])
        self.geometry("440x560")
        self.minsize(400, 440)
        self.transient(parent)

        self.var_tamanho = tk.IntVar(value=tamanho_inicial)
        self._montar()
        self._mostrar_curados()
        self.bind("<Escape>", lambda e: self.destroy())

    # ---------- construção ----------

    def _montar(self):
        t = self.t
        topo = tk.Frame(self, bg=t["bg_panel"])
        topo.pack(fill="x", padx=theme.SP_LG, pady=(theme.SP_LG, theme.SP_SM))

        caixa = tk.Frame(topo, bg=t["bg_input"], highlightbackground=t["border_input"],
                          highlightthickness=1)
        caixa.pack(fill="x")
        tk.Label(caixa, text="⌕", bg=t["bg_input"], fg=t["text_muted"]).pack(
            side="left", padx=(8, 4), pady=6)
        self.entrada = tk.Entry(caixa, bg=t["bg_input"], fg=t["text_primary"], relief="flat",
                                 insertbackground=t["text_primary"],
                                 font=(theme.FONT, theme.FS_BODY))
        self.entrada.pack(side="left", fill="x", expand=True, padx=(0, 8), pady=6)
        self.entrada.bind("<KeyRelease>", lambda e: self._ao_buscar())
        dica = "Buscar por nome (ex.: certo, alerta, cadeado)"
        if not self._indice:
            dica = "Busca indisponível — usando a seleção abaixo"
        widgets.texto_fluido(topo, dica, self.dark).pack(fill="x", pady=(4, 0))

        linha_tam = tk.Frame(topo, bg=t["bg_panel"])
        linha_tam.pack(fill="x", pady=(theme.SP_SM, 0))
        tk.Label(linha_tam, text="Tamanho", bg=t["bg_panel"], fg=t["text_tertiary"],
                 font=(theme.FONT, theme.FS_CAPTION)).pack(side="left", padx=(0, theme.SP_SM))
        self._pills_tamanho = {}
        for rotulo, valor in TAMANHOS:
            pill = widgets.Pill(linha_tam, rotulo, self.dark, bg=t["bg_panel"],
                                 ativo=(valor == self.var_tamanho.get()),
                                 comando=lambda v=valor: self._definir_tamanho(v))
            pill.pack(side="left", padx=2)
            self._pills_tamanho[valor] = (pill, rotulo)

        # corpo rolável
        wrap = tk.Frame(self, bg=t["bg_panel"])
        wrap.pack(fill="both", expand=True, padx=theme.SP_MD, pady=(theme.SP_SM, theme.SP_MD))
        self.canvas = tk.Canvas(wrap, bg=t["bg_panel"], highlightthickness=0, width=1)
        barra = tk.Scrollbar(wrap, orient="vertical", command=self.canvas.yview)
        self.corpo = tk.Frame(self.canvas, bg=t["bg_panel"])
        janela = self.canvas.create_window((0, 0), window=self.corpo, anchor="nw")
        self.canvas.configure(yscrollcommand=barra.set)
        self.canvas.pack(side="left", fill="both", expand=True)
        barra.pack(side="right", fill="y")
        self.corpo.bind("<Configure>",
                         lambda e: self.canvas.config(scrollregion=self.canvas.bbox("all")))
        self.canvas.bind("<Configure>", lambda e: self.canvas.itemconfig(janela, width=e.width))
        self.canvas.bind("<Enter>", lambda e: self.canvas.bind_all(
            "<MouseWheel>",
            lambda ev: self.canvas.yview_scroll(int(-1 * (ev.delta / 120)), "units")))
        self.canvas.bind("<Leave>", lambda e: self.canvas.unbind_all("<MouseWheel>"))

    def _definir_tamanho(self, valor):
        self.var_tamanho.set(valor)
        for v, (pill, rotulo) in self._pills_tamanho.items():
            pill.definir(rotulo, v == valor)

    # ---------- conteúdo ----------

    def _limpar_corpo(self):
        for w in self.corpo.winfo_children():
            w.destroy()
        self._imagens = []

    def _imagem_grade(self, caractere):
        if caractere not in self._cache:
            img = renderizar(caractere, _TAM_GRADE)
            self._cache[caractere] = ImageTk.PhotoImage(img)
        return self._cache[caractere]

    def _celula(self, parent, caractere, coluna, linha):
        try:
            imagem = self._imagem_grade(caractere)
        except Exception:
            return
        self._imagens.append(imagem)
        lbl = tk.Label(parent, image=imagem, bg=self.t["bg_panel"], cursor="hand2",
                        bd=0, highlightthickness=0)
        lbl.grid(row=linha, column=coluna, padx=3, pady=3)
        lbl.bind("<Button-1>", lambda e, c=caractere: self._escolher(c))
        lbl.bind("<Enter>", lambda e, w=lbl: w.config(bg=self.t["pill_bg"]))
        lbl.bind("<Leave>", lambda e, w=lbl: w.config(bg=self.t["bg_panel"]))

    def _mostrar_curados(self):
        self._limpar_corpo()
        for titulo, sequencia in CATEGORIAS:
            tk.Label(self.corpo, text=titulo.upper(), bg=self.t["bg_panel"],
                     fg=self.t["text_muted"],
                     font=(theme.FONT, theme.FS_CAPTION, "bold")).pack(anchor="w", pady=(10, 2))
            grade = tk.Frame(self.corpo, bg=self.t["bg_panel"])
            grade.pack(anchor="w")
            for i, caractere in enumerate(sequencia.split()):
                self._celula(grade, caractere, i % _COLUNAS, i // _COLUNAS)

    def _mostrar_resultados(self, caracteres):
        self._limpar_corpo()
        if not caracteres:
            widgets.texto_fluido(self.corpo, "Nenhum emoji encontrado com esse nome.",
                                  self.dark).pack(fill="x", pady=12)
            return
        grade = tk.Frame(self.corpo, bg=self.t["bg_panel"])
        grade.pack(anchor="w", pady=(10, 0))
        for i, caractere in enumerate(caracteres):
            self._celula(grade, caractere, i % _COLUNAS, i // _COLUNAS)

    def _ao_buscar(self):
        termo = self.entrada.get().strip().lower()
        if not termo:
            self._mostrar_curados()
            return
        achados = [c for c, nomes in self._indice.items() if termo in nomes]
        self._mostrar_resultados(achados[:_MAX_RESULTADOS])

    def _escolher(self, caractere):
        tamanho = self.var_tamanho.get()
        self.destroy()
        self.ao_escolher(caractere, tamanho)
