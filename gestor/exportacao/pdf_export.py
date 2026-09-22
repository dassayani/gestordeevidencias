"""Motor de geração do documento final (PDF), com os 3 modelos do design
original ('1f' Passo a passo, '1g' Ficha de evidência, '1h' Relatório QA).

Cada `passo` é um dict: {"caminho": str, "legenda": str}. `capa` é um dict
com título/caso/autor/data/ambiente. `opcoes` controla cor de destaque,
numeração, borda e fonte — vem das Configurações e da tela Montar documento.
"""
import os
import unicodedata

from PIL import Image
from fpdf import FPDF as _FPDFBase

from gestor.sistema import utils

# O fpdf 1.7 escreve o texto em latin-1. Acento comum cabe, mas os caracteres
# tipográficos que o Word, o Teams e o Chat inserem sozinhos (travessão no
# lugar do hífen, aspas curvas no lugar das retas, reticências de um caractere
# só) NÃO cabem: colar uma legenda dessas fazia a geração do PDF morrer com
# UnicodeEncodeError. Como quem escreve a legenda é o usuário, isso não é caso
# raro — é o caminho comum.
_EQUIVALENTES = {
    "—": "-", "–": "-", "−": "-",      # travessão, meia-risca, menos
    "‘": "'", "’": "'", "‚": "'",      # aspas simples curvas
    "“": '"', "”": '"', "„": '"',      # aspas duplas curvas
    "…": "...",                                   # reticências
    " ": " ", " ": " ", " ": " ",      # espaços especiais
    "•": "-",                                    # marcador de lista
    "→": "->", "←": "<-",                    # setas
    "✓": "v", "✔": "v", "✗": "x", "✘": "x",
}


def texto_seguro(valor):
    """Devolve o texto em algo que o fpdf 1.7 consegue gravar.

    Primeiro troca os tipográficos pelo equivalente ASCII, que é o que o leitor
    espera ver. O que sobrar fora do latin-1 (emoji, símbolos, outros
    alfabetos) é decomposto — 'ﬁ' vira 'fi' — e só então descartado, para o
    documento sair com o texto todo em vez de não sair.
    """
    if valor is None:
        return ""
    texto = str(valor)
    for origem, destino in _EQUIVALENTES.items():
        if origem in texto:
            texto = texto.replace(origem, destino)
    try:
        texto.encode("latin-1")
        return texto
    except UnicodeEncodeError:
        pass
    normalizado = unicodedata.normalize("NFKD", texto)
    return "".join(c for c in normalizado if _cabe_em_latin1(c))


def _cabe_em_latin1(caractere):
    try:
        caractere.encode("latin-1")
        return True
    except UnicodeEncodeError:
        return False


class FPDF(_FPDFBase):
    """FPDF que saneia o texto na porta de entrada.

    Fica na classe, e não em cada chamada, porque são 26 pontos que escrevem
    texto: um `cell` novo esquecido traria o erro de volta.
    """

    def cell(self, w, h=0, txt="", *args, **kwargs):
        return super().cell(w, h, texto_seguro(txt), *args, **kwargs)

    def multi_cell(self, w, h, txt="", *args, **kwargs):
        return super().multi_cell(w, h, texto_seguro(txt), *args, **kwargs)

    def text(self, x, y, txt=""):
        return super().text(x, y, texto_seguro(txt))

    def write(self, h, txt="", *args, **kwargs):
        return super().write(h, texto_seguro(txt), *args, **kwargs)

PAGE_W, PAGE_H = 210.0, 297.0
# Teto de linhas da legenda na Ficha: o cartao tem altura fixa, entao a
# legenda precisa de limite para sobrar area util de imagem.
LINHAS_LEGENDA_FICHA = 4
MARGEM = 20.0
# Geometria do relatorio QA: a previa precisa das mesmas medidas para quebrar
# a legenda onde o documento quebra.
LARGURA_LATERAL_QA = 55.0
X0_QA = LARGURA_LATERAL_QA + 14
TEAL = (11, 114, 133)
TEXTO = (23, 38, 46)
MUTED = (107, 129, 144)
MUTED_CLARO = (142, 162, 173)


def _cor(hexcolor, padrao=TEAL):
    try:
        return utils.hex_to_rgb(hexcolor)
    except Exception:
        return padrao


def _opcoes_padrao(opcoes):
    o = dict(opcoes or {})
    o.setdefault("cor_destaque", "#0B7285")
    o.setdefault("fonte_legenda", "Arial")
    o.setdefault("numerar_passos", True)
    o.setdefault("borda_ativada", False)
    o.setdefault("borda_cor", "#0B7285")
    return o


def _capa_dados(capa):
    capa = capa or {}
    return {
        "titulo": capa.get("titulo") or "Evidências de teste",
        "caso": capa.get("caso", ""),
        "autor": capa.get("autor", ""),
        "data": capa.get("data", ""),
        "ambiente": capa.get("ambiente", ""),
    }


def _imagem_ajustada(pdf, caminho, x, y, w, h, borda=False, cor_borda=TEAL):
    if caminho and os.path.exists(caminho):
        try:
            with Image.open(caminho) as img:
                iw, ih = img.size
            escala = min(w / iw, h / ih)
            dw, dh = iw * escala, ih * escala
            ox = x + (w - dw) / 2
            oy = y + (h - dh) / 2
            pdf.image(caminho, x=ox, y=oy, w=dw, h=dh)
        except Exception:
            pass
    if borda:
        pdf.set_draw_color(*cor_borda)
        pdf.set_line_width(0.5)
        pdf.rect(x, y, w, h)


def _cabe_ate(pdf, texto, largura):
    """Quantos caracteres de `texto` cabem em `largura` — no minimo um.

    O minimo de um evita laco infinito quando nem um caractere cabe.
    """
    corte = 1
    while corte < len(texto) and pdf.get_string_width(texto[:corte + 1]) <= largura:
        corte += 1
    return corte


def _quebrar(pdf, texto, largura):
    """Divide o texto nas linhas que cabem em `largura`, como o multi_cell faz.

    Existe porque o fpdf nao informa quantas linhas vai gastar antes de
    desenhar, e a Ficha precisa saber disso para posicionar a imagem abaixo
    da legenda em vez de por cima dela.

    Mede o texto ja saneado porque e ele que vai ser desenhado: o travessao
    vira hifen e as reticencias viram tres pontos, entao medir o original
    daria uma largura menor do que a que aparece no papel.
    """
    linhas = []
    for paragrafo in texto_seguro(texto).split("\n"):
        atual = ""
        for palavra in paragrafo.split():
            teste = f"{atual} {palavra}".strip()
            if atual and pdf.get_string_width(teste) > largura:
                linhas.append(atual)
                atual = palavra
            else:
                atual = teste
            # Uma palavra sozinha pode ser mais larga que a linha inteira: URL,
            # caminho de arquivo, texto colado sem espaco. Sem partir no meio
            # dela, a legenda saia para fora do cartao numa linha so.
            while pdf.get_string_width(atual) > largura:
                corte = _cabe_ate(pdf, atual, largura)
                linhas.append(atual[:corte])
                atual = atual[corte:]
        linhas.append(atual)
    return linhas or [""]


def _legenda_limitada(pdf, texto, largura, altura_linha, max_linhas):
    """Desenha a legenda em no maximo `max_linhas` e devolve o Y final.

    O que nao couber vira reticencias: numa ficha de tamanho fixo, deixar a
    legenda crescer sem limite empurraria a imagem para fora do cartao.
    """
    linhas = _quebrar(pdf, texto, largura)
    cortou = len(linhas) > max_linhas
    if cortou:
        linhas = linhas[:max_linhas]
        linhas[-1] = linhas[-1].rstrip() + "..."
    x, y = pdf.get_x(), pdf.get_y()
    for i, linha in enumerate(linhas):
        pdf.set_xy(x, y + i * altura_linha)
        pdf.cell(largura, altura_linha, linha)
    return y + len(linhas) * altura_linha


def _circulo_numerado(pdf, cx, cy, r, texto, fonte, tamanho_pt, cor_fundo,
                      cor_texto=(255, 255, 255)):
    """Desenha um círculo preenchido com o número centralizado (horizontal
    e vertical) dentro dele — pdf.cell() sozinho não centraliza na vertical."""
    pdf.set_fill_color(*cor_fundo)
    pdf.ellipse(cx - r, cy - r, r * 2, r * 2, style="F")
    pdf.set_font(fonte, "B", tamanho_pt)
    pdf.set_text_color(*cor_texto)
    largura_txt = pdf.get_string_width(texto)
    altura_txt = tamanho_pt * 0.3528  # pt -> mm
    pdf.text(cx - largura_txt / 2, cy + altura_txt * 0.32, texto)


def contar_paginas(passos, modelo):
    n = max(1, len(passos))
    if modelo == "ficha":
        return max(1, (n + 1) // 2)
    if modelo == "qa":
        return max(1, (n + 1) // 2)
    return max(1, (n + 1) // 2)


# ---------------------------------------------------------------- 1f
MARGEM_PASSO = 10.0  # 1cm — margem menor pra imagem ficar maior nesse modelo


def exportar_passo_a_passo(destino, capa, passos, opcoes=None):
    o = _opcoes_padrao(opcoes)
    c = _capa_dados(capa)
    cor = _cor(o["cor_destaque"])
    cor_borda = _cor(o["borda_cor"])
    fonte = o["fonte_legenda"]
    total_paginas = contar_paginas(passos, "passo")
    m = MARGEM_PASSO

    pdf = FPDF(format="A4", unit="mm")
    pdf.set_auto_page_break(False)

    pagina = 0
    for idx in range(0, max(1, len(passos)), 2):
        pagina += 1
        pdf.add_page()
        pdf.set_fill_color(*cor)
        pdf.rect(0, 0, PAGE_W, 3, style="F")

        if idx == 0:
            pdf.set_xy(m, 12)
            pdf.set_font(fonte, "", 9)
            pdf.set_text_color(*cor)
            pdf.cell(0, 5, "MANUAL DE OPERAÇÃO")
            pdf.set_xy(m, 18)
            pdf.set_font(fonte, "B", 18)
            pdf.set_text_color(*TEXTO)
            pdf.cell(120, 9, c["titulo"])
            pdf.set_xy(130, 12)
            pdf.set_font(fonte, "", 9)
            pdf.set_text_color(*MUTED)
            # Caso e Ambiente entram aqui: eram preenchidos na tela e não
            # apareciam em lugar nenhum deste modelo. Campos vazios são
            # omitidos pra não sobrar linha em branco no cabeçalho.
            meta = [v for v in (c["caso"], c["ambiente"], c["autor"], c["data"]) if v]
            pdf.multi_cell(PAGE_W - m - 130, 5, "\n".join(meta), align="R")
            # A divisória acompanha o bloco de metadados: com 4 campos
            # preenchidos ele passa de y=30, onde a linha ficava fixa antes.
            y_divisoria = max(30, pdf.get_y() + 2)
            pdf.set_draw_color(220, 226, 230)
            pdf.line(m, y_divisoria, PAGE_W - m, y_divisoria)
            y = y_divisoria + 6
        else:
            y = 14

        for j in (idx, idx + 1):
            if j >= len(passos):
                break
            passo = passos[j]
            r = 4.5
            if o["numerar_passos"]:
                _circulo_numerado(pdf, m + r, y + r, r, str(j + 1), fonte, 10, cor)
                texto_x = m + r * 2 + 4
                fim_numero = y + r * 2
            else:
                texto_x = m
                fim_numero = y
            pdf.set_xy(texto_x, y)
            pdf.set_font(fonte, "B", 12)
            pdf.set_text_color(*TEXTO)
            pdf.multi_cell(PAGE_W - m - texto_x, 6,
                           passo.get("legenda") or "Sem legenda", align="L")
            # A imagem começa abaixo do que terminar mais baixo: a legenda ou o
            # círculo do número. Considerar só a legenda (1 linha = 6mm) fazia a
            # borda da imagem encostar no círculo (9mm de altura).
            y = max(pdf.get_y(), fim_numero) + 5
            img_h = 82
            _imagem_ajustada(pdf, passo.get("caminho"), m, y, PAGE_W - 2 * m, img_h,
                              o["borda_ativada"], cor_borda)
            y += img_h + 9

        pdf.set_xy(m, PAGE_H - 14)
        pdf.set_font(fonte, "", 8)
        pdf.set_text_color(*MUTED_CLARO)
        pdf.cell(120, 5, "Gestor de Evidências")
        pdf.set_xy(PAGE_W - m - 40, PAGE_H - 14)
        pdf.cell(40, 5, f"Página {pagina} de {total_paginas}", align="R")

    pdf.output(destino)


# ---------------------------------------------------------------- 1g
def exportar_ficha_evidencia(destino, capa, passos, opcoes=None):
    o = _opcoes_padrao(opcoes)
    c = _capa_dados(capa)
    cor = _cor(o["cor_destaque"])
    cor_borda = _cor(o["borda_cor"])
    fonte = o["fonte_legenda"]
    total_paginas = contar_paginas(passos, "ficha")

    pdf = FPDF(format="A4", unit="mm")
    pdf.set_auto_page_break(False)

    pagina = 0
    for idx in range(0, max(1, len(passos)), 2):
        pagina += 1
        pdf.add_page()
        pdf.set_fill_color(*cor)
        pdf.rect(0, 0, PAGE_W, 32, style="F")
        pdf.set_xy(MARGEM, 10)
        pdf.set_font(fonte, "", 8)
        pdf.set_text_color(230, 240, 242)
        pdf.cell(0, 5, "REGISTRO DE EVIDÊNCIAS")
        pdf.set_xy(MARGEM, 16)
        pdf.set_font(fonte, "B", 15)
        pdf.set_text_color(255, 255, 255)
        titulo_caso = c["titulo"] + (f" · {c['caso']}" if c["caso"] else "")
        pdf.cell(130, 8, titulo_caso)
        pdf.set_xy(140, 10)
        pdf.set_font(fonte, "", 8)
        pdf.set_text_color(207, 232, 238)
        pdf.multi_cell(50, 4.5, f"{c['ambiente']}\n{c['data']}\n{c['autor']}", align="R")

        y = 40
        for j in (idx, idx + 1):
            if j >= len(passos):
                break
            passo = passos[j]
            altura_card = 118
            pdf.set_draw_color(225, 232, 238)
            pdf.set_line_width(0.3)
            pdf.rect(MARGEM, y, PAGE_W - 2 * MARGEM, altura_card)

            pdf.set_fill_color(230, 242, 245)
            pdf.rect(MARGEM + 4, y + 4, 16, 7, style="F")
            pdf.set_xy(MARGEM + 4, y + 5.3)
            pdf.set_font(fonte, "B", 8)
            pdf.set_text_color(*cor)
            pdf.cell(16, 5, f"EV-{j + 1:02d}", align="C")

            pdf.set_xy(MARGEM + 24, y + 4)
            pdf.set_font(fonte, "B", 11)
            pdf.set_text_color(*TEXTO)
            legenda = passo.get("legenda") or "Sem legenda"
            fim_legenda = _legenda_limitada(
                pdf, legenda, PAGE_W - 2 * MARGEM - 28, 5.5, LINHAS_LEGENDA_FICHA)

            # A imagem comeca abaixo de onde a legenda terminou de verdade. Com
            # o deslocamento fixo que havia aqui, uma legenda de tres linhas ou
            # mais era coberta pela imagem.
            img_y = max(y + 24, fim_legenda + 2)
            img_h = (y + altura_card - 8) - img_y
            _imagem_ajustada(pdf, passo.get("caminho"), MARGEM + 4, img_y,
                             PAGE_W - 2 * MARGEM - 8, img_h,
                             o["borda_ativada"], cor_borda)

            y += altura_card + 8

        pdf.set_xy(MARGEM, PAGE_H - 14)
        pdf.set_font(fonte, "", 8)
        pdf.set_text_color(*MUTED_CLARO)
        pdf.cell(140, 5, "Gestor de Evidências")
        pdf.set_xy(PAGE_W - MARGEM - 40, PAGE_H - 14)
        pdf.cell(40, 5, f"Página {pagina} de {total_paginas}", align="R")

    pdf.output(destino)


# ---------------------------------------------------------------- 1h
def exportar_relatorio_qa(destino, capa, passos, opcoes=None):
    o = _opcoes_padrao(opcoes)
    c = _capa_dados(capa)
    cor = _cor(o["cor_destaque"])
    cor_borda = _cor(o["borda_cor"])
    fonte = o["fonte_legenda"]
    total_paginas = contar_paginas(passos, "qa")
    largura_lateral = LARGURA_LATERAL_QA
    # A faixa lateral é o elemento dominante deste modelo. Com o azul fixo que
    # havia aqui, trocar a cor de destaque não mudava nada visível — só o
    # rótulo "EVIDÊNCIAS" e os números. Os tons claros saem da própria faixa
    # para o contraste do texto acompanhar qualquer cor escolhida.
    faixa = utils.escurecer(cor)
    faixa_texto = utils.clarear(faixa, 0.72)
    faixa_rotulo = utils.clarear(faixa, 0.58)
    faixa_linha = utils.clarear(faixa, 0.22)

    pdf = FPDF(format="A4", unit="mm")
    pdf.set_auto_page_break(False)

    pagina = 0
    for idx in range(0, max(1, len(passos)), 2):
        pagina += 1
        pdf.add_page()

        pdf.set_fill_color(*faixa)
        pdf.rect(0, 0, largura_lateral, PAGE_H, style="F")
        pdf.set_xy(8, 14)
        pdf.set_font(fonte, "B", 13)
        pdf.set_text_color(255, 255, 255)
        pdf.multi_cell(largura_lateral - 16, 6, "Relatório de teste", align="L")
        pdf.set_xy(8, 28)
        pdf.set_font(fonte, "", 8)
        pdf.set_text_color(*faixa_texto)
        # inclui o caso, que era preenchido na tela e não saía neste modelo
        contexto = [v for v in (c["titulo"], c["caso"], c["ambiente"]) if v]
        pdf.multi_cell(largura_lateral - 16, 4.2, "\n".join(contexto), align="L")

        pdf.set_draw_color(*faixa_linha)
        pdf.line(8, 46, largura_lateral - 8, 46)

        pdf.set_xy(8, 52)
        pdf.set_font(fonte, "", 7.5)
        pdf.set_text_color(*faixa_rotulo)
        pdf.cell(0, 4, "RESUMO")
        pdf.set_xy(8, 58)
        pdf.set_font(fonte, "B", 18)
        pdf.set_text_color(255, 255, 255)
        pdf.cell(0, 8, str(len(passos)))
        pdf.set_xy(8, 66)
        pdf.set_font(fonte, "", 7.5)
        pdf.set_text_color(*faixa_texto)
        pdf.cell(0, 4, "capturas neste relatório")

        pdf.set_xy(8, PAGE_H - 30)
        pdf.set_font(fonte, "", 7)
        pdf.set_text_color(*faixa_rotulo)
        pdf.multi_cell(largura_lateral - 16, 4, f"{c['autor']}\n{c['data']}", align="L")

        x0 = X0_QA
        y = 16
        pdf.set_xy(x0, y)
        pdf.set_font(fonte, "", 8)
        pdf.set_text_color(*cor)
        pdf.cell(0, 5, "EVIDÊNCIAS")
        y += 10

        for j in (idx, idx + 1):
            if j >= len(passos):
                break
            passo = passos[j]
            altura_numero = 6
            pdf.set_xy(x0, y)
            pdf.set_font(fonte, "B", 11)
            pdf.set_text_color(*cor)
            pdf.cell(10, altura_numero, str(j + 1))
            pdf.set_xy(x0 + 10, y)
            pdf.set_font(fonte, "B", 10.5)
            pdf.set_text_color(*TEXTO)
            largura_txt = PAGE_W - MARGEM - x0 - 10
            pdf.multi_cell(largura_txt, 5, passo.get("legenda") or "Sem legenda", align="L")
            # mesma folga do modelo "passo": a borda da imagem não pode
            # encostar no número, que fica na mesma coluna (x0)
            y = max(pdf.get_y(), y + altura_numero) + 5
            img_h = 78
            _imagem_ajustada(pdf, passo.get("caminho"), x0, y, PAGE_W - MARGEM - x0, img_h,
                              o["borda_ativada"], cor_borda)
            y += img_h + 10

        pdf.set_xy(x0, PAGE_H - 14)
        pdf.set_font(fonte, "", 8)
        pdf.set_text_color(*MUTED_CLARO)
        pdf.cell(100, 5, "Gestor de Evidências")
        pdf.set_xy(PAGE_W - MARGEM - 30, PAGE_H - 14)
        pdf.cell(30, 5, f"{pagina} / {total_paginas}", align="R")

    pdf.output(destino)


MODELOS = {
    "passo": ("Passo a passo", exportar_passo_a_passo),
    "ficha": ("Ficha de evidência", exportar_ficha_evidencia),
    "qa": ("Relatório QA", exportar_relatorio_qa),
}


def exportar(modelo, destino, capa, passos, opcoes=None):
    _, funcao = MODELOS.get(modelo, MODELOS["passo"])
    funcao(destino, capa, passos, opcoes)
