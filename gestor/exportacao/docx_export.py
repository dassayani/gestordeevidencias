"""Exportação em DOCX (Word), com os mesmos 3 modelos do `pdf_export.py`.
DOCX é um formato de fluxo (não de páginas fixas como o PDF), então aqui a
paginação e as faixas de cor são aproximadas — não pixel a pixel iguais ao
PDF, mas seguindo a mesma estrutura e paleta."""
import os

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Mm, Pt, RGBColor

TEXTO = RGBColor(0x17, 0x26, 0x2E)
MUTED = RGBColor(0x6B, 0x81, 0x90)
MUTED_CLARO = RGBColor(0x8E, 0xA2, 0xAD)

_TWIPS_POR_CM = 1440 / 2.54  # o Word mede largura de tabela em twips (1/1440")


def _opcoes_padrao(opcoes):
    o = dict(opcoes or {})
    o.setdefault("cor_destaque", "#0B7285")
    o.setdefault("fonte_legenda", "Arial")
    o.setdefault("numerar_passos", True)
    # faltavam aqui: a borda era escolhida na tela e simplesmente ignorada
    # na geração do DOCX (o PDF já tratava, em pdf_export._opcoes_padrao)
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


def _hex_limpo(hexcolor, padrao="0B7285"):
    """Normaliza pra 6 dígitos hex sem '#'; devolve o padrão se vier inválido."""
    texto = (hexcolor or "").lstrip("#").strip()
    if len(texto) == 6:
        try:
            int(texto, 16)
            return texto.upper()
        except ValueError:
            pass
    return padrao


def _rgb(hexcolor):
    # tolerante a hex inválido, como pdf_export._cor — antes um valor
    # quebrado levantava ValueError e derrubava a exportação inteira
    texto = _hex_limpo(hexcolor)
    return RGBColor(int(texto[0:2], 16), int(texto[2:4], 16), int(texto[4:6], 16))


def _sombrear_celula(celula, hexcolor):
    tcPr = celula._tc.get_or_add_tcPr()
    shd = OxmlElement("w:shd")
    # os três atributos são necessários: só com w:fill o Word ignora o
    # sombreamento e a célula sai sem cor nenhuma
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), _hex_limpo(hexcolor))
    tcPr.append(shd)


def _largura_fixa(tabela, larguras_cm):
    """Fixa a largura das colunas de uma tabela.

    Definir só `cell.width` não basta: sem `w:tblLayout` fixo o Word recalcula
    as colunas pelo conteúdo e pode encolher uma delas bem abaixo do pedido —
    era o que espremia a lateral do Relatório QA a ponto de quebrar as
    palavras no meio ("Relatóri / o de teste").
    """
    tabela.autofit = False
    tblPr = tabela._tbl.tblPr

    layout = OxmlElement("w:tblLayout")
    layout.set(qn("w:type"), "fixed")
    tblPr.append(layout)

    largura_total = OxmlElement("w:tblW")
    largura_total.set(qn("w:type"), "dxa")
    largura_total.set(qn("w:w"), str(int(sum(larguras_cm) * _TWIPS_POR_CM)))
    tblPr.append(largura_total)

    for idx, cm in enumerate(larguras_cm):
        if idx >= len(tabela.columns):
            break
        tabela.columns[idx].width = Cm(cm)
        for celula in tabela.columns[idx].cells:
            celula.width = Cm(cm)


def _sem_bordas(tabela):
    tbl = tabela._tbl
    tblPr = tbl.tblPr
    borders = OxmlElement("w:tblBorders")
    for nome in ("top", "left", "bottom", "right", "insideH", "insideV"):
        el = OxmlElement(f"w:{nome}")
        el.set(qn("w:val"), "none")
        borders.append(el)
    tblPr.append(borders)


def _configurar_pagina(document, fonte):
    secao = document.sections[0]
    secao.page_width = Mm(210)
    secao.page_height = Mm(297)
    document.styles["Normal"].font.name = fonte
    document.styles["Normal"].font.size = Pt(10.5)


def _borda_paragrafo(paragrafo, hexcolor):
    """Desenha um quadro em volta do parágrafo (w:pBdr).

    É como a borda das imagens é feita no DOCX: o python-docx não expõe
    contorno de imagem, então o quadro vai no parágrafo que contém a figura.
    Mesma técnica de injeção de OOXML já usada em `_sem_bordas`.
    """
    pPr = paragrafo._p.get_or_add_pPr()
    bordas = OxmlElement("w:pBdr")
    for nome in ("top", "left", "bottom", "right"):
        el = OxmlElement(f"w:{nome}")
        el.set(qn("w:val"), "single")
        el.set(qn("w:sz"), "8")        # 8 oitavos de ponto = 1pt
        el.set(qn("w:space"), "4")     # respiro entre a borda e a imagem
        el.set(qn("w:color"), _hex_limpo(hexcolor))
        bordas.append(el)
    pPr.append(bordas)


def _faixa_colorida(document, hexcolor, altura_pt=6):
    """Faixa fina na cor de destaque, no topo da página."""
    tabela = document.add_table(rows=1, cols=1)
    _sem_bordas(tabela)
    celula = tabela.rows[0].cells[0]
    _sombrear_celula(celula, hexcolor)
    p = celula.paragraphs[0]
    p.paragraph_format.space_before = Pt(0)
    p.paragraph_format.space_after = Pt(0)
    for run in p.runs:
        run.font.size = Pt(altura_pt)
    if not p.runs:
        p.add_run("").font.size = Pt(altura_pt)
    return tabela


def _imagem_com_largura(paragrafo, caminho, largura_cm, opcoes=None):
    if caminho and os.path.exists(caminho):
        run = paragrafo.add_run()
        try:
            run.add_picture(caminho, width=Cm(largura_cm))
        except Exception:
            pass
    o = opcoes or {}
    if o.get("borda_ativada"):
        _borda_paragrafo(paragrafo, o.get("borda_cor"))


def _rodape_simples(document, texto):
    rodape = document.sections[0].footer
    p = rodape.paragraphs[0] if rodape.paragraphs else rodape.add_paragraph()
    p.text = texto
    p.style = document.styles["Normal"]
    for run in p.runs:
        run.font.size = Pt(8)
        run.font.color.rgb = MUTED_CLARO


# ---------------------------------------------------------------- 1f
def exportar_passo_a_passo(destino, capa, passos, opcoes=None):
    o = _opcoes_padrao(opcoes)
    c = _capa_dados(capa)
    cor = _rgb(o["cor_destaque"])
    fonte = o["fonte_legenda"]

    document = Document()
    _configurar_pagina(document, fonte)
    secao = document.sections[0]
    secao.left_margin = secao.right_margin = Cm(1)
    secao.top_margin = secao.bottom_margin = Cm(1.2)

    # Faixa colorida no topo, equivalente ao pdf.rect(0, 0, PAGE_W, 3) do PDF.
    # Sem ela este modelo não tinha nenhum bloco na cor escolhida, e a cor
    # "sumia" mesmo estando aplicada nos textos.
    _faixa_colorida(document, o["cor_destaque"])

    eyebrow = document.add_paragraph()
    r = eyebrow.add_run("MANUAL DE OPERAÇÃO")
    r.font.size = Pt(9)
    r.font.bold = True
    r.font.color.rgb = cor

    titulo = document.add_paragraph()
    rt = titulo.add_run(c["titulo"])
    rt.font.size = Pt(22)
    rt.font.bold = True
    rt.font.color.rgb = TEXTO

    meta = document.add_paragraph()
    meta.alignment = WD_ALIGN_PARAGRAPH.LEFT
    # caso e ambiente entram aqui: eram preenchidos na tela e não saíam
    # em lugar nenhum deste modelo. Vazios são omitidos.
    campos = [v for v in (c["caso"], c["ambiente"], c["autor"], c["data"]) if v]
    rm = meta.add_run(" · ".join(campos))
    rm.font.size = Pt(9)
    rm.font.color.rgb = MUTED
    document.add_paragraph()

    for idx, passo in enumerate(passos):
        p = document.add_paragraph()
        if o["numerar_passos"]:
            rn = p.add_run(f"{idx + 1}.  ")
            rn.font.bold = True
            rn.font.color.rgb = cor
        rl = p.add_run(passo.get("legenda") or "Sem legenda")
        rl.font.bold = True
        rl.font.size = Pt(12)
        rl.font.color.rgb = TEXTO

        img_p = document.add_paragraph()
        _imagem_com_largura(img_p, passo.get("caminho"), 19, o)
        if idx < len(passos) - 1:
            document.add_paragraph()

    _rodape_simples(document, "Gestor de Evidências")
    document.save(destino)


# ---------------------------------------------------------------- 1g
def exportar_ficha_evidencia(destino, capa, passos, opcoes=None):
    o = _opcoes_padrao(opcoes)
    c = _capa_dados(capa)
    cor = _rgb(o["cor_destaque"])
    fonte = o["fonte_legenda"]

    document = Document()
    _configurar_pagina(document, fonte)

    header = document.add_table(rows=1, cols=1)
    _sem_bordas(header)
    cel = header.rows[0].cells[0]
    _sombrear_celula(cel, o["cor_destaque"])
    p1 = cel.paragraphs[0]
    r1 = p1.add_run("REGISTRO DE EVIDÊNCIAS")
    r1.font.size = Pt(9)
    r1.font.color.rgb = RGBColor(0xE6, 0xF2, 0xF5)
    p2 = cel.add_paragraph()
    titulo_caso = c["titulo"] + (f" · {c['caso']}" if c["caso"] else "")
    r2 = p2.add_run(titulo_caso)
    r2.font.size = Pt(16)
    r2.font.bold = True
    r2.font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF)
    p3 = cel.add_paragraph()
    r3 = p3.add_run(f"{c['ambiente']} · {c['data']} · {c['autor']}")
    r3.font.size = Pt(8.5)
    r3.font.color.rgb = RGBColor(0xCF, 0xE8, 0xEE)

    document.add_paragraph()

    for idx, passo in enumerate(passos):
        tabela = document.add_table(rows=1, cols=1)
        tabela.style = "Table Grid"
        cel = tabela.rows[0].cells[0]
        p_cab = cel.paragraphs[0]
        r_ev = p_cab.add_run(f"EV-{idx + 1:02d}  ")
        r_ev.font.bold = True
        r_ev.font.size = Pt(8)
        r_ev.font.color.rgb = cor
        r_leg = p_cab.add_run(passo.get("legenda") or "Sem legenda")
        r_leg.font.bold = True
        r_leg.font.size = Pt(11)
        r_leg.font.color.rgb = TEXTO
        p_img = cel.add_paragraph()
        _imagem_com_largura(p_img, passo.get("caminho"), 17, o)
        document.add_paragraph()

    _rodape_simples(document, "Gestor de Evidências")
    document.save(destino)


# ---------------------------------------------------------------- 1h
def exportar_relatorio_qa(destino, capa, passos, opcoes=None):
    o = _opcoes_padrao(opcoes)
    c = _capa_dados(capa)
    cor = _rgb(o["cor_destaque"])
    fonte = o["fonte_legenda"]

    document = Document()
    _configurar_pagina(document, fonte)
    # margens estreitas como no modelo "passo": a tabela lateral+conteúdo tem
    # 19cm e não caberia na área de texto das margens padrão (15,9cm), que é
    # justamente o que fazia o Word encolher as colunas por conta própria.
    secao = document.sections[0]
    secao.left_margin = secao.right_margin = Cm(1)
    secao.top_margin = secao.bottom_margin = Cm(1.2)

    resumo = document.add_table(rows=1, cols=2)
    _sem_bordas(resumo)
    _largura_fixa(resumo, (5.5, 13.5))
    cel_lateral, cel_principal = resumo.rows[0].cells
    _sombrear_celula(cel_lateral, "0F3B45")

    p = cel_lateral.paragraphs[0]
    r = p.add_run("Relatório de teste")
    r.font.bold = True
    r.font.size = Pt(12)
    r.font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF)
    p2 = cel_lateral.add_paragraph()
    # mesmo conjunto de campos da lateral no PDF, que agora inclui o caso
    contexto = [v for v in (c["titulo"], c["caso"], c["ambiente"]) if v]
    r2 = p2.add_run("\n".join(contexto))
    r2.font.size = Pt(8.5)
    r2.font.color.rgb = RGBColor(0x9F, 0xC4, 0xCC)
    p3 = cel_lateral.add_paragraph()
    r3 = p3.add_run(f"\n{len(passos)}")
    r3.font.bold = True
    r3.font.size = Pt(20)
    r3.font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF)
    p4 = cel_lateral.add_paragraph()
    r4 = p4.add_run("capturas neste relatório")
    r4.font.size = Pt(8)
    r4.font.color.rgb = RGBColor(0x9F, 0xC4, 0xCC)
    p5 = cel_lateral.add_paragraph()
    r5 = p5.add_run(f"\n{c['autor']}\n{c['data']}")
    r5.font.size = Pt(7.5)
    r5.font.color.rgb = RGBColor(0x9F, 0xC4, 0xCC)

    pp = cel_principal.paragraphs[0]
    rp = pp.add_run("EVIDÊNCIAS")
    rp.font.size = Pt(9)
    rp.font.bold = True
    rp.font.color.rgb = cor

    for idx, passo in enumerate(passos):
        pn = cel_principal.add_paragraph()
        rn = pn.add_run(f"{idx + 1}.  ")
        rn.font.bold = True
        rn.font.size = Pt(13)
        rn.font.color.rgb = cor
        rl = pn.add_run(passo.get("legenda") or "Sem legenda")
        rl.font.bold = True
        rl.font.size = Pt(10.5)
        rl.font.color.rgb = TEXTO
        pim = cel_principal.add_paragraph()
        _imagem_com_largura(pim, passo.get("caminho"), 13, o)

    _rodape_simples(document, "Gestor de Evidências")
    document.save(destino)


MODELOS = {
    "passo": exportar_passo_a_passo,
    "ficha": exportar_ficha_evidencia,
    "qa": exportar_relatorio_qa,
}


def exportar(modelo, destino, capa, passos, opcoes=None):
    funcao = MODELOS.get(modelo, MODELOS["passo"])
    funcao(destino, capa, passos, opcoes)
