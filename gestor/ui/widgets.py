"""Controles reutilizáveis com visual "flat" moderno (em vez dos widgets
nativos do Tk, que destoam do resto da interface). Usado nas telas de
Configurações, Montar documento e Exportação."""
import math
import os
import tkinter as tk
import tkinter.font as tkfont

from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageTk

from gestor.ui import theme


def _fonte_pil(negrito, tamanho_pt, escala):
    nome = "segoeuib.ttf" if negrito else "segoeui.ttf"
    try:
        return ImageFont.truetype(nome, int(tamanho_pt * escala))
    except Exception:
        return ImageFont.load_default()


def _construir_pill(texto, cor_fundo, cor_texto, altura=25, padding_h=13, negrito=True,
                     fonte_pt=9, escala=6):
    e = escala
    fonte = _fonte_pil(negrito, fonte_pt, e)
    tmp = Image.new("RGBA", (10, 10))
    d_tmp = ImageDraw.Draw(tmp)
    bbox = d_tmp.textbbox((0, 0), texto, font=fonte)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    w = tw + padding_h * 2 * e
    h = altura * e
    img = Image.new("RGBA", (int(w), int(h)), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.rounded_rectangle([0, 0, w - 1, h - 1], radius=h // 2, fill=cor_fundo)
    draw.text(((w - tw) / 2 - bbox[0], (h - th) / 2 - bbox[1]), texto, font=fonte, fill=cor_texto)
    largura_final = int(w / e)
    return img.resize((largura_final, altura), Image.LANCZOS)


class Pill(tk.Label):
    """Pílula com cantos totalmente arredondados (via PIL + downscale), pra
    filtros e chips — o tk.Button nativo não faz border-radius."""

    def __init__(self, parent, texto, dark=False, bg=None, ativo=False, comando=None,
                 altura=28, fonte_pt=None):
        fonte_pt = theme.FS_EYEBROW if fonte_pt is None else fonte_pt
        self.t = theme.get(dark)
        bg = bg or self.t["bg_panel"]
        super().__init__(parent, bg=bg, bd=0, highlightthickness=0)
        self._bg = bg
        self._altura = altura
        self._fonte_pt = fonte_pt
        self._comando = comando
        if comando:
            self.config(cursor="hand2")
            self.bind("<Button-1>", lambda e: self._comando())
        self.definir(texto, ativo)

    def definir(self, texto, ativo):
        cor_fundo = self.t["accent"] if ativo else self.t["pill_bg"]
        cor_texto = "#ffffff" if ativo else self.t["text_secondary"]
        img = _construir_pill(texto, cor_fundo, cor_texto, altura=self._altura,
                               negrito=ativo, fonte_pt=self._fonte_pt)
        self._photo = ImageTk.PhotoImage(img)
        self.config(image=self._photo)


def _construir_bloco_ferramenta(desenhar_icone, rotulo, cor_fundo, cor_texto, largura=56, altura=50,
                                 raio=12, escala=6):
    e = escala
    w, h = largura * e, altura * e
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.rounded_rectangle([0, 0, w - 1, h - 1], radius=raio * e, fill=cor_fundo)

    # Ícone em vetor, não caractere: os glifos Unicode equivalentes
    # (↖ ▭ ▮ ☺ ① ▩ ⬚ ⌫) não existem no segoeui.ttf e cairiam no "tofu".
    desenhar_icone(draw, w / 2, h * 0.34, 7.5 * e, cor_texto, max(1, int(e * 1.3)))

    fonte_rotulo = _fonte_pil(True, 9, e)
    bbox_r = draw.textbbox((0, 0), rotulo, font=fonte_rotulo)
    rw, rh = bbox_r[2] - bbox_r[0], bbox_r[3] - bbox_r[1]
    draw.text((w / 2 - rw / 2 - bbox_r[0], h * 0.78 - rh / 2 - bbox_r[1]),
              rotulo, font=fonte_rotulo,
              fill=cor_texto)

    return img.resize((largura, altura), Image.LANCZOS)


class BlocoFerramenta(tk.Label):
    """Botão da coluna de ferramentas do editor.

    Ícone e rótulo num bloco arredondado, com fundo destacado quando ativo.
    """

    def __init__(self, parent, desenhar_icone, rotulo, dark, comando,
                 bg=None, largura=56, altura=50):
        self.dark = dark
        self.desenhar_icone = desenhar_icone
        self.rotulo = rotulo
        self.largura = largura
        self.altura = altura
        t = theme.get(dark)
        self._bg = bg or t["bg_footer"]
        super().__init__(parent, bg=self._bg, bd=0, highlightthickness=0, cursor="hand2")
        self.bind("<Button-1>", lambda e: comando())
        self.definir_ativo(False)

    def definir_ativo(self, ativo):
        t = theme.get(self.dark)
        cor_fundo = t["accent"] if ativo else self._bg
        cor_texto = "#ffffff" if ativo else t["text_secondary"]
        img = _construir_bloco_ferramenta(self.desenhar_icone, self.rotulo, cor_fundo, cor_texto,
                                           self.largura, self.altura)
        self._photo = ImageTk.PhotoImage(img)
        self.config(image=self._photo, bg=self._bg)


def marca_selecao(dark, selecionada, tamanho=18, escala=8):
    """Pequeno círculo de seleção (contorno quando vazio, preenchido com
    check quando marcado) — como no design original."""
    t = theme.get(dark)
    e = escala
    w = tamanho * e
    margem = e * 2
    img = Image.new("RGBA", (w + margem * 2, w + margem * 2), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    cx = cy = img.width // 2
    r = w // 2
    if selecionada:
        draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=t["accent"], outline=t["accent"])
        largura_check = max(2, e // 2)
        draw.line([(cx - r * 0.5, cy), (cx - r * 0.08, cy + r * 0.42)], fill="#ffffff",
                   width=largura_check, joint="curve")
        draw.line([(cx - r * 0.08, cy + r * 0.42), (cx + r * 0.55, cy - r * 0.42)], fill="#ffffff",
                   width=largura_check, joint="curve")
    else:
        draw.ellipse([cx - r, cy - r, cx + r, cy + r],
                     fill="#ffffff", outline="#C3D0D8", width=max(1, e // 3))
    return img.resize((tamanho, tamanho), Image.LANCZOS)

_ESCALA_ICONE = 8  # desenha bem maior e reduz depois (antialiasing via LANCZOS)


def _construir_icone_botao(desenhar_fn, tamanho, cor_icone, cor_fundo_botao, cor_borda):
    """Desenha um botão circular (fundo + borda + sombra suave + ícone) em
    alta resolução via PIL e reduz com LANCZOS — evita o serrilhado que o
    Canvas do Tk produz em linhas finas."""
    e = _ESCALA_ICONE
    grande = tamanho * e
    margem = e * 4
    tela = Image.new("RGBA", (grande + margem * 2, grande + margem * 2), (0, 0, 0, 0))
    cx = cy = tela.width // 2
    r = grande // 2

    sombra = Image.new("RGBA", tela.size, (0, 0, 0, 0))
    ImageDraw.Draw(sombra).ellipse([cx - r, cy - r + e, cx + r, cy + r + e], fill=(15, 25, 35, 60))
    sombra = sombra.filter(ImageFilter.GaussianBlur(e * 0.9))
    tela = Image.alpha_composite(tela, sombra)

    draw = ImageDraw.Draw(tela)
    draw.ellipse([cx - r, cy - r, cx + r, cy + r],
                 fill=cor_fundo_botao, outline=cor_borda, width=e // 3)

    desenhar_fn(draw, cx, cy, r, cor_icone, cor_fundo_botao)

    return tela.resize((tela.width // e, tela.height // e), Image.LANCZOS)


class IconButton(tk.Frame):
    """Botão redondo com ícone vetorial renderizado via PIL (antialiased),
    fundo, borda sutil e sombra suave — em vez de emoji (visual inconsistente
    no Windows) ou linhas cruas de Canvas (ficam serrilhadas em telas pequenas)."""

    def __init__(self, parent, desenhar_fn, comando, dark=False, bg=None, tamanho=30,
                 ativo=False):
        t = theme.get(dark)
        bg = bg or t["bg_header"]
        super().__init__(parent, bg=bg)
        self._t = t
        self._desenhar_fn = desenhar_fn
        self._tamanho = tamanho
        self.lbl = tk.Label(self, bg=bg, cursor="hand2", bd=0, highlightthickness=0)
        self.lbl.pack()
        self.lbl.bind("<Button-1>", lambda e: comando())
        self.definir_ativo(ativo)

    def definir_ativo(self, ativo):
        """Marca o botão como o estado vigente (usado pelo seletor de
        visualização, onde um dos três está sempre em vigor)."""
        t = self._t
        img = _construir_icone_botao(
            self._desenhar_fn, self._tamanho,
            t["accent"] if ativo else t["text_secondary"],
            t["accent_bg"] if ativo else t["bg_panel"],
            t["accent"] if ativo else t["border_soft"])
        self._photo = ImageTk.PhotoImage(img)
        self.lbl.config(image=self._photo)


def icone_lixeira(draw, cx, cy, r, cor, cor_fundo):
    """Lixeira em vetor — o emoji 🗑 caía na fonte monocromática do Windows e
    destoava dos outros ícones, que são desenhados."""
    lw = max(2, int(r * 0.11))
    largura = r * 0.62
    topo = cy - r * 0.42
    base = cy + r * 0.66
    draw.line([cx - largura * 1.25, topo, cx + largura * 1.25, topo], fill=cor, width=lw)
    draw.line([cx - largura * 0.42, topo - r * 0.2, cx + largura * 0.42, topo - r * 0.2],
              fill=cor, width=lw)
    draw.line([cx - largura, topo, cx - largura * 0.78, base], fill=cor, width=lw)
    draw.line([cx + largura, topo, cx + largura * 0.78, base], fill=cor, width=lw)
    draw.line([cx - largura * 0.78, base, cx + largura * 0.78, base], fill=cor, width=lw)
    for dx in (-largura * 0.36, 0, largura * 0.36):
        draw.line([cx + dx, topo + r * 0.16, cx + dx, base - r * 0.16], fill=cor, width=lw)


def icone_lista(draw, cx, cy, r, cor, cor_fundo):
    """Visão de detalhes: linhas com miniatura à esquerda e texto ao lado."""
    lw = max(1, int(r * 0.1))
    passo = r * 0.52
    for k in (-1, 0, 1):
        y = cy + k * passo
        draw.rectangle([cx - r * 0.66, y - r * 0.17, cx - r * 0.28, y + r * 0.17],
                       outline=cor, width=lw)
        draw.line([cx - r * 0.12, y, cx + r * 0.66, y], fill=cor, width=lw)


def icone_blocos(draw, cx, cy, r, cor, cor_fundo):
    """Visão em blocos: dois por linha, miniatura e legenda lado a lado."""
    lw = max(1, int(r * 0.1))
    for ly in (-1, 1):
        for lx in (-1, 1):
            x0 = cx + (0.08 if lx > 0 else -0.72) * r
            y0 = cy + (0.1 if ly > 0 else -0.72) * r
            draw.rectangle([x0, y0, x0 + r * 0.64, y0 + r * 0.62], outline=cor, width=lw)
            draw.line([x0 + r * 0.14, y0 + r * 0.31, x0 + r * 0.5, y0 + r * 0.31],
                      fill=cor, width=lw)


def icone_grade(draw, cx, cy, r, cor, cor_fundo):
    """Visão em grade: só as miniaturas, com a legenda embaixo."""
    lw = max(1, int(r * 0.1))
    lado = r * 0.38
    passo = r * 0.56
    for ly in (-1, 0, 1):
        for lx in (-1, 0, 1):
            x0 = cx + lx * passo - lado / 2
            y0 = cy + ly * passo - lado / 2
            draw.rectangle([x0, y0, x0 + lado, y0 + lado], outline=cor, width=lw)


def icone_configuracoes(draw, cx, cy, r, cor, cor_fundo):
    """Três controles deslizantes (ícone universal de 'ajustes')."""
    largura = max(2, int(r * 0.11))
    raio_bola = r * 0.16
    linhas = ((-0.32, 0.22), (0, -0.28), (0.32, 0.08))
    for dy, dx in linhas:
        y = cy + r * dy
        xk = cx + r * dx
        draw.line([cx - r * 0.52, y, cx + r * 0.52, y], fill=cor, width=largura)
        draw.ellipse([xk - raio_bola, y - raio_bola, xk + raio_bola, y + raio_bola], fill=cor)


def icone_tema(draw, cx, cy, r, cor, cor_fundo, escuro=False):
    raio_sol = r * 0.34
    largura = max(2, int(r * 0.11))
    if escuro:
        draw.ellipse([cx - raio_sol, cy - raio_sol, cx + raio_sol, cy + raio_sol],
                     outline=cor, width=largura)
        for ang in range(0, 360, 45):
            rad = math.radians(ang)
            x1, y1 = cx + math.cos(rad) * raio_sol * 1.45, cy + math.sin(rad) * raio_sol * 1.45
            x2, y2 = cx + math.cos(rad) * raio_sol * 1.9, cy + math.sin(rad) * raio_sol * 1.9
            draw.line([x1, y1, x2, y2], fill=cor, width=largura)
    else:
        draw.ellipse([cx - raio_sol, cy - raio_sol, cx + raio_sol, cy + raio_sol], fill=cor)
        deslocamento = raio_sol * 0.6
        draw.ellipse([cx - raio_sol + deslocamento, cy - raio_sol - deslocamento * 0.2,
                      cx + raio_sol + deslocamento, cy + raio_sol - deslocamento * 0.2],
                     fill=cor_fundo)


class Deslizante(tk.Canvas):
    """Slider desenhado no Canvas.

    O tk.Scale nativo não permite colorir o puxador separado do fundo (o
    -background vale pros dois), então ou o puxador some no trilho ou o
    widget inteiro vira um bloco colorido no meio da barra. Aqui trilho,
    trecho preenchido e puxador têm cor própria.
    """

    def __init__(self, parent, minimo, maximo, valor, dark=False, bg=None,
                 largura=130, altura=24, on_change=None):
        self.t = theme.get(dark)
        bg = bg or self.t["bg_panel"]
        super().__init__(parent, width=largura, height=altura, bg=bg,
                          highlightthickness=0, cursor="hand2")
        self.minimo = minimo
        self.maximo = maximo
        self.valor = valor
        self.largura = largura
        self.altura = altura
        self.on_change = on_change
        self.bind("<Button-1>", self._no_clique)
        self.bind("<B1-Motion>", self._no_clique)
        self._desenhar()

    def _raio(self):
        return 9

    def _x_do_valor(self, valor):
        faixa = max(1, self.maximo - self.minimo)
        frac = (valor - self.minimo) / faixa
        r = self._raio()
        return r + frac * (self.largura - 2 * r)

    def _no_clique(self, event):
        r = self._raio()
        util = max(1, self.largura - 2 * r)
        frac = min(1.0, max(0.0, (event.x - r) / util))
        novo = int(round(self.minimo + frac * (self.maximo - self.minimo)))
        if novo != self.valor:
            self.valor = novo
            self._desenhar()
            if self.on_change:
                self.on_change(novo)

    def definir(self, valor):
        self.valor = max(self.minimo, min(self.maximo, int(valor)))
        self._desenhar()

    def _desenhar(self):
        self.delete("all")
        cy = self.altura / 2
        r = self._raio()
        x = self._x_do_valor(self.valor)
        self.create_line(r, cy, self.largura - r, cy, fill=self.t["border"], width=4,
                          capstyle="round")
        self.create_line(r, cy, x, cy, fill=self.t["accent"], width=4, capstyle="round")
        # anel claro + contorno escuro: só o anel na cor do fundo fazia o
        # puxador se confundir com o trilho, era difícil enxergar onde ele está
        self.create_oval(x - r, cy - r, x + r, cy + r, fill=self.t["bg_input"],
                          outline=self.t["text_tertiary"], width=2)
        self.create_oval(x - r * 0.45, cy - r * 0.45, x + r * 0.45, cy + r * 0.45,
                          fill=self.t["accent"], outline="")


class Checkbox(tk.Frame):
    """Caixa de seleção quadrada com marca de check, no mesmo estilo flat
    do resto da interface (em vez do tk.Checkbutton nativo)."""

    def __init__(self, parent, variable, dark=False, bg=None, on_change=None, tamanho=18,
                 altura_linha=None):
        """`altura_linha` faz o canvas ter a altura de uma linha de texto, com
        o quadrado centrado dentro dela. Assim, alinhando o topo do controle
        com o topo do rótulo, o quadrado cai na altura visual das letras — os
        glifos ficam baixos dentro da caixa de linha, então deslocar só o
        controle pra baixo nunca acertava o alinhamento."""
        t = theme.get(dark)
        bg = bg or t["bg_panel"]
        super().__init__(parent, bg=bg)
        self.t = t
        self.variable = variable
        self.on_change = on_change
        self.tamanho = tamanho
        self.altura = max(tamanho, altura_linha or tamanho)
        self.canvas = tk.Canvas(self, width=tamanho, height=self.altura, bg=bg,
                                 highlightthickness=0, cursor="hand2")
        self.canvas.pack()
        self.canvas.bind("<Button-1>", self._alternar)
        self._desenhar()

    def _alternar(self, event=None):
        self.variable.set(not self.variable.get())
        self._desenhar()
        if self.on_change:
            self.on_change(self.variable.get())

    def _desenhar(self):
        self.canvas.delete("all")
        marcado = bool(self.variable.get())
        s = self.tamanho
        dy = (self.altura - s) / 2  # centra o quadrado na altura da linha
        if marcado:
            self.canvas.create_rectangle(1, dy + 1, s - 1, dy + s - 1,
                                          fill=self.t["accent"], outline=self.t["accent"])
            self.canvas.create_line(s * 0.24, dy + s * 0.52, s * 0.42, dy + s * 0.72,
                                     fill="#ffffff", width=2)
            self.canvas.create_line(s * 0.42, dy + s * 0.72, s * 0.78, dy + s * 0.28,
                                     fill="#ffffff", width=2)
        else:
            self.canvas.create_rectangle(1, dy + 1, s - 1, dy + s - 1,
                                          fill=self.t["bg_panel"], outline=self.t["border"])


def _altura_linha(fonte_pt=None):
    """Altura de uma linha de texto na fonte da interface."""
    try:
        return tkfont.Font(family=theme.FONT, size=fonte_pt or theme.FS_BODY).metrics("linespace")
    except Exception:
        return int((fonte_pt or theme.FS_BODY) * 1.8)


def linha_checkbox(parent, texto, variable, dark=False, subtitulo=None, on_change=None):
    t = theme.get(dark)
    linha = tk.Frame(parent, bg=t["bg_panel"])
    linha.pack(fill="x", pady=6)
    # A caixa é centrada na PRIMEIRA LINHA do rótulo, não no topo da linha
    # inteira: ancorada só no topo ela ficava opticamente alta (18px de caixa
    # contra ~10px de altura de maiúscula), e centrada na linha inteira ia
    # parar ao lado do subtítulo nos itens que têm um.
    cb = Checkbox(linha, variable, dark=dark, bg=t["bg_panel"], on_change=on_change,
                  altura_linha=_altura_linha())
    cb.pack(side="left", padx=(0, 10), anchor="n")
    info = tk.Frame(linha, bg=t["bg_panel"])
    info.pack(side="left", fill="x", expand=True)
    lbl = texto_fluido(info, texto, dark, cor="text_primary", fonte=(theme.FONT, theme.FS_BODY))
    lbl.config(cursor="hand2")
    lbl.pack(fill="x")
    lbl.bind("<Button-1>", lambda e: cb._alternar())
    if subtitulo:
        texto_fluido(info, subtitulo, dark).pack(fill="x", pady=(2, 0))
    return linha, cb


def titulo_secao(parent, texto, dark=False, pady=(18, 8)):
    t = theme.get(dark)
    tk.Label(parent, text=texto.upper(), bg=t["bg_panel"], fg=t["text_muted"],
             font=(theme.FONT, theme.FS_EYEBROW, "bold")).pack(anchor="w", pady=pady)


def campo_rotulado(parent, rotulo, dark=False, valor_inicial="", **entry_kwargs):
    t = theme.get(dark)
    bloco = tk.Frame(parent, bg=t["bg_panel"])
    bloco.pack(fill="x", pady=6)
    tk.Label(bloco, text=rotulo, bg=t["bg_panel"], fg=t["text_tertiary"],
              font=(theme.FONT, theme.FS_CAPTION)).pack(anchor="w", pady=(0, 4))
    # bg_input, não "white": no tema escuro o token white continua #FFFFFF e o
    # texto digitado (text_primary, quase branco) sumia dentro do campo.
    caixa = tk.Frame(bloco, bg=t["bg_input"],
                     highlightbackground=t["border_input"], highlightthickness=1)
    caixa.pack(fill="x")
    entry = tk.Entry(caixa, bg=t["bg_input"], fg=t["text_primary"], relief="flat",
                       insertbackground=t["text_primary"],
                       readonlybackground=t["bg_input"], disabledbackground=t["bg_input"],
                       font=(theme.FONT, theme.FS_BODY), **entry_kwargs)
    entry.pack(fill="x", padx=10, pady=8)
    if valor_inicial:
        entry.insert(0, valor_inicial)
    return bloco, entry


def caminho_icone():
    """Caminho do icon.ico, funcionando tanto rodando do fonte quanto no .exe.

    No executável do PyInstaller os dados ficam extraídos em sys._MEIPASS; no
    fonte, na raiz do projeto — três pastas acima deste módulo, que vive em
    gestor/ui/.
    """
    import sys
    raiz = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    base = getattr(sys, "_MEIPASS", None) or raiz
    caminho = os.path.join(base, "icon.ico")
    return caminho if os.path.exists(caminho) else None


_GCLP_HICON = -14
_GCLP_HICONSM = -34
_IMAGE_ICON = 1
_LR_LOADFROMFILE = 0x0010


def aplicar_icone(janela):
    """Define o ícone da aplicação a partir de uma janela já existente.

    O `iconbitmap` do Tk troca o ícone apenas daquela janela. A classe de
    janela que o Tk registra continua com a pena do Tcl/Tk, e é a classe que
    o Windows consulta na barra de tarefas, no Alt+Tab e em qualquer Toplevel
    sem ícone próprio. Definir o ícone na classe cobre a janela atual, as já
    abertas e as futuras de uma vez, o que dispensa repetir a chamada em cada
    tela.
    """
    caminho = caminho_icone()
    if not caminho:
        return
    try:
        janela.iconbitmap(caminho)
    except Exception:
        pass
    try:
        _definir_icone_da_classe(janela, caminho)
    except Exception:
        pass


def _definir_icone_da_classe(janela, caminho):
    import ctypes

    user32 = ctypes.windll.user32
    user32.SetClassLongPtrW.restype = ctypes.c_void_p
    user32.SetClassLongPtrW.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p]

    janela.update_idletasks()
    hwnd = janela.winfo_id()
    hwnd = user32.GetParent(hwnd) or hwnd
    for indice, lado in ((_GCLP_HICON, 32), (_GCLP_HICONSM, 16)):
        icone = user32.LoadImageW(None, caminho, _IMAGE_ICON, lado, lado,
                                   _LR_LOADFROMFILE)
        if icone:
            user32.SetClassLongPtrW(ctypes.c_void_p(hwnd), indice,
                                     ctypes.c_void_p(icone))


class Botao(tk.Frame):
    """Botão padrão da aplicação.

    É Frame+Label em vez de tk.Button porque no Windows o tk.Button ignora
    highlightbackground (sem borda de verdade) e não deixa controlar a
    altura em pixels. E é texto de verdade, não imagem PIL como as pílulas:
    imagem não estica, então botão desenhado em PIL nunca acompanha a
    largura do container — que é justamente o que faz os botões ficarem
    minúsculos num painel largo ou espremidos num estreito.

    Empacotado com fill="x" (sozinho ou com expand=True entre irmãos), ele
    ocupa a largura disponível e mantém o texto centralizado; sem fill, ele
    se ajusta ao próprio texto. Nos dois casos a altura é a mesma, que é o
    que faz os botões alinharem entre si.
    """

    VARIANTES = ("primario", "secundario", "ghost", "perigo")

    def __init__(self, parent, texto, comando, dark=False, variante="secundario",
                 tamanho="md", bg=None):
        self.t = theme.get(dark)
        self.variante = variante
        self._comando = comando
        self._cores = self._paleta(variante, bg)
        pady = 8 if tamanho == "md" else 5
        super().__init__(parent, bg=self._cores["fundo"],
                          highlightbackground=self._cores["borda"],
                          highlightcolor=self._cores["borda"],
                          highlightthickness=1 if self._cores["borda"] else 0)
        # padding horizontal enxuto: o rótulo é o que deve preencher o botão,
        # não a margem — com padx grande o texto ficava pequeno no meio de um
        # botão largo.
        self.lbl = tk.Label(self, text=texto, bg=self._cores["fundo"], fg=self._cores["texto"],
                             font=(theme.FONT, theme.FS_BUTTON, "bold"), cursor="hand2",
                             padx=theme.SP_SM, pady=pady, justify="center")
        self.lbl.pack(fill="both", expand=True)
        for w in (self, self.lbl):
            w.bind("<Button-1>", lambda e: self._comando())
            w.bind("<Enter>", self._hover_entra)
            w.bind("<Leave>", self._hover_sai)
        # O rótulo quebra na largura que o botão realmente recebeu. Sem isso,
        # quando o container dá menos espaço do que o texto pede (fonte grande
        # num rodapé estreito), o Label mantém a largura natural e o texto
        # invade o botão vizinho.
        self._minimo_quebra = self._largura_maior_palavra(texto)
        self.bind("<Configure>", self._ajustar_quebra, add="+")

    def _largura_maior_palavra(self, texto):
        """Piso pra quebra: a maior palavra do rótulo.

        Mudar o wraplength altera a largura que o Label pede, o que faz o
        container recalcular e disparar outro <Configure> — sem esse piso a
        largura encolhia a cada volta até quebrar palavra no meio
        ("document" / "o").
        """
        try:
            fonte = tkfont.Font(family=theme.FONT, size=theme.FS_BUTTON, weight="bold")
            return max((fonte.measure(p) for p in (texto or "").split()), default=40)
        except Exception:
            return 40

    def _ajustar_quebra(self, event):
        largura = max(self._minimo_quebra, event.width - 2 * theme.SP_SM)
        if self.lbl.cget("wraplength") != largura:
            self.lbl.config(wraplength=largura)

    def _paleta(self, variante, bg):
        t = self.t
        if variante == "primario":
            return dict(fundo=t["accent"], texto="#ffffff", borda=None, hover=t["accent_hover"])
        if variante == "perigo":
            return dict(fundo=t["danger_bg"], texto=t["danger_text"], borda=t["danger_text"],
                        hover=t["danger_text"])
        if variante == "ghost":
            base = bg or t["bg_panel"]
            return dict(fundo=base, texto=t["text_secondary"], borda=None, hover=t["pill_bg"])
        return dict(fundo=bg or t["bg_panel"], texto=t["text_secondary"], borda=t["border"],
                    hover=t["pill_bg"])

    def _hover_entra(self, event=None):
        cor = self._cores["hover"]
        self.config(bg=cor)
        self.lbl.config(bg=cor, fg="#ffffff" if self.variante == "perigo" else self.lbl["fg"])

    def _hover_sai(self, event=None):
        self.config(bg=self._cores["fundo"])
        self.lbl.config(bg=self._cores["fundo"], fg=self._cores["texto"])

    def definir_texto(self, texto):
        self.lbl.config(text=texto)


def texto_fluido(parent, texto, dark=False, bg=None, cor="text_muted", fonte=None):
    """Label que quebra linha na largura real do container.

    Um tk.Label comum guarda a largura natural do texto: num painel estreito
    ele não quebra, ele transborda — e como fica centralizado no espaço que
    tem, aparece cortado dos dois lados. Aqui o wraplength é recalculado a
    cada resize do container, então o texto acompanha o painel (inclusive
    quando o usuário arrasta a divisa).
    """
    t = theme.get(dark)
    bg = bg or t["bg_panel"]
    lbl = tk.Label(parent, text=texto, bg=bg, fg=t[cor],
                    font=fonte or (theme.FONT, theme.FS_CAPTION),
                    anchor="w", justify="left", wraplength=180)

    def ajustar(event):
        # mede a largura do PRÓPRIO rótulo, não a do container: quando ele
        # divide a linha com outros widgets (miniatura, botões), a largura do
        # container é bem maior que a fatia que sobra pro texto, e usar a do
        # container fazia o texto continuar vazando.
        largura = max(40, event.width - 2)
        if lbl.cget("wraplength") != largura:
            lbl.config(wraplength=largura)

    lbl.bind("<Configure>", ajustar, add="+")
    return lbl


def botao_primario(parent, texto, comando, dark=False):
    return Botao(parent, texto, comando, dark, variante="primario")


def botao_secundario(parent, texto, comando, dark=False, bg=None):
    return Botao(parent, texto, comando, dark, variante="secundario", bg=bg)


def escolha_checkbox(parent, opcoes, variable, dark=False, on_change=None):
    """Lista vertical de opções com caixa de seleção quadrada, escolha única
    (marcar uma desmarca as outras) — usada nas Configurações em vez das
    pílulas, que pareciam radio button."""
    t = theme.get(dark)
    container = tk.Frame(parent, bg=t["bg_panel"])
    linhas = {}

    def selecionar(v):
        variable.set(v)
        atualizar()
        if on_change:
            on_change(v)

    def atualizar():
        for v, (cb, lbl) in linhas.items():
            cb.variable.set(v == variable.get())
            cb._desenhar()

    for v, rotulo in opcoes:
        linha = tk.Frame(container, bg=t["bg_panel"])
        linha.pack(fill="x", anchor="w", pady=2)
        var_local = tk.BooleanVar(value=(v == variable.get()))
        cb = Checkbox(linha, var_local, dark=dark, bg=t["bg_panel"], tamanho=16,
                      altura_linha=_altura_linha(),
                      on_change=lambda marcado, vv=v: selecionar(vv) if marcado else atualizar())
        cb.pack(side="left", padx=(0, 8), anchor="n")
        lbl = tk.Label(linha, text=rotulo, bg=t["bg_panel"], fg=t["text_primary"],
                       font=(theme.FONT, theme.FS_BODY), cursor="hand2", anchor="w")
        lbl.pack(side="left", fill="x", expand=True)
        lbl.bind("<Button-1>", lambda e, vv=v: selecionar(vv))
        linhas[v] = (cb, lbl)

    atualizar()
    return container


def campo_com_botao(parent, rotulo, dark, valor_inicial, texto_botao, comando_botao):
    """Campo somente-leitura + botão de ação na mesma linha, alinhados
    (ex.: caminho de pasta + "Alterar…")."""
    t = theme.get(dark)
    bloco = tk.Frame(parent, bg=t["bg_panel"])
    bloco.pack(fill="x", pady=6)
    tk.Label(bloco, text=rotulo, bg=t["bg_panel"], fg=t["text_tertiary"],
              font=(theme.FONT, theme.FS_CAPTION)).pack(anchor="w", pady=(0, 4))
    linha = tk.Frame(bloco, bg=t["bg_panel"])
    linha.pack(fill="x")
    caixa = tk.Frame(linha, bg=t["bg_input"],
                     highlightbackground=t["border_input"], highlightthickness=1)
    caixa.pack(side="left", fill="x", expand=True, padx=(0, 8))
    entry = tk.Entry(caixa, bg=t["bg_input"], fg=t["text_primary"], relief="flat",
                      insertbackground=t["text_primary"],
                      font=(theme.FONT, theme.FS_BODY))
    entry.pack(fill="both", expand=True, padx=10, pady=8)
    if valor_inicial:
        entry.insert(0, valor_inicial)
    # readonlybackground é o que vale no estado readonly; sem definir, o Tk usa
    # uma cor de sistema clara e o campo fica branco no tema escuro.
    entry.config(state="readonly", readonlybackground=t["bg_input"],
                 disabledbackground=t["bg_input"])
    botao = botao_secundario(linha, texto_botao, comando_botao, dark)
    botao.pack(side="left")
    return bloco, entry


def escolha_pills(parent, opcoes, variable, dark=False, on_change=None):
    """Linha de pílulas de escolha única. opcoes: lista de (valor, rotulo)."""
    t = theme.get(dark)
    linha = tk.Frame(parent, bg=t["bg_panel"])
    botoes = {}

    def selecionar(v):
        variable.set(v)
        atualizar()
        if on_change:
            on_change(v)

    def atualizar():
        for v, (pill, rotulo) in botoes.items():
            pill.definir(rotulo, v == variable.get())

    for v, rotulo in opcoes:
        pill = Pill(linha, rotulo, dark, bg=t["bg_panel"], altura=30, fonte_pt=theme.FS_EYEBROW,
                    comando=lambda vv=v: selecionar(vv))
        pill.pack(side="left", padx=3)
        botoes[v] = (pill, rotulo)
    atualizar()
    return linha
