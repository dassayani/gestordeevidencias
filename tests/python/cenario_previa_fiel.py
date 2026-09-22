# -*- coding: utf-8 -*-
"""A previa mostra exatamente a pagina que vai ser gerada.

Compara pixel a pixel o que a tela de previa desenha com a pagina do PDF
exportado logo em seguida, nos tres modelos. Enquanto a previa era montada com
widgets imitando o layout, esta comparacao era impossivel — e foi por isso que
rodape, quebra de legenda, tamanho de imagem e cor de destaque divergiram, um
de cada vez.
"""

import os as _os
import sys as _sys

# Raiz do projeto a partir deste arquivo: tests/python/x.py -> duas pastas acima
RAIZ = _os.path.dirname(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
_sys.path.insert(0, RAIZ)
_os.chdir(RAIZ)
SAIDA = _os.path.join(RAIZ, "tests", "_saida")
_os.makedirs(SAIDA, exist_ok=True)

import os, sys, ctypes, tempfile, shutil, traceback, time

if not ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4)):
    ctypes.windll.shcore.SetProcessDpiAwareness(2)

from tkinterdnd2 import TkinterDnD
from PIL import Image, ImageChops
import pymupdf
from gestor.dados import config
from gestor.exportacao import pdf_export
from gestor.ui import export_preview
from gestor.ui.workspace import AppEvidencias

falhas = []


def checar(condicao, descricao):
    print(("OK:     " if condicao else "FALHOU: ") + descricao)
    if not condicao:
        falhas.append(descricao)


LEGENDA_LONGA = ("Ao clicar no botao Confirmar da tela de fechamento o sistema valida "
                 "o saldo disponivel, confere a data de competencia e registra o log "
                 "de auditoria antes de apresentar a mensagem de sucesso ao usuario.")
CAPA = {"titulo": "Validacao de fechamento", "caso": "CT-4471",
        "autor": "QA - Dasayani", "data": "22/09/2026", "ambiente": "Homologacao"}

tmp = tempfile.mkdtemp(prefix="ge_fiel_")
capturas = os.path.join(tmp, "Capturas")
os.makedirs(capturas)
amostra = os.path.join(capturas, "print_170000.png")
img = Image.new("RGB", (1300, 820), (246, 249, 251))
img.save(amostra)

PASSOS = [{"caminho": amostra, "legenda": LEGENDA_LONGA},
          {"caminho": amostra, "legenda": "Tela inicial do modulo"},
          {"caminho": amostra, "legenda": "Confirmacao apresentada"}]
OPCOES = {"cor_destaque": "#E8590C", "borda_cor": "#E8590C", "borda_ativada": True,
          "numerar_passos": True, "fonte_legenda": "Arial"}

cfg = config.load(tmp)
cfg["pasta_capturas"] = capturas
config.save(tmp, cfg)

root = TkinterDnD.Tk()
app = AppEvidencias(root, capturas, os.path.join(tmp, "PDF"), RAIZ, tmp)
app.pausar_timer = True
root.deiconify()
root.update()


def pagina_do_pdf(caminho, indice, largura, altura):
    """Uma pagina do PDF na mesma resolucao em que a previa a exibe."""
    dpi = int(round(export_preview._SUPERAMOSTRAGEM * largura
                    / (pdf_export.PAGE_W / 25.4)))
    with pymupdf.open(caminho) as doc:
        pix = doc[indice].get_pixmap(dpi=dpi)
        pagina = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
    return pagina.resize((largura, altura), Image.LANCZOS)


try:
    for modelo in ("passo", "ficha", "qa"):
        prev = export_preview.PreVisualizarExportar(app, None, modelo, CAPA,
                                                    PASSOS, OPCOES)
        prev.update()
        time.sleep(0.3)
        prev.update()

        checar(prev._documento is not None, "[%s] a previa gerou o documento" % modelo)
        if prev._documento is None:
            prev.fechar()
            continue

        # o documento exportado agora, pelo mesmo caminho do botao Exportar
        destino = os.path.join(tmp, "exportado_%s.pdf" % modelo)
        pdf_export.exportar(modelo, destino, CAPA, PASSOS, OPCOES)

        with pymupdf.open(destino) as doc:
            paginas_exportadas = doc.page_count
        checar(prev.total_paginas == paginas_exportadas,
               "[%s] a previa conta %d paginas e o documento tem %d"
               % (modelo, prev.total_paginas, paginas_exportadas))

        # Compara o que a tela realmente exibe com a pagina do documento
        # exportado, no mesmo tamanho: sao a mesma imagem ou ha divergencia.
        for indice in range(min(prev.total_paginas, paginas_exportadas)):
            da_previa = prev.imagem_da_pagina(indice)
            do_documento = pagina_do_pdf(destino, indice,
                                         da_previa.width, da_previa.height)
            diferenca = ImageChops.difference(da_previa, do_documento)
            caixa = diferenca.getbbox()
            iguais = caixa is None
            checar(iguais, "[%s] pagina %d da previa e identica a do documento"
                   % (modelo, indice + 1))
            if not iguais:
                comparacao = os.path.join(SAIDA, "fiel_%s_p%d.png" % (modelo, indice + 1))
                largura, altura = da_previa.size
                lado = Image.new("RGB", (largura * 2 + 10, altura), (235, 238, 241))
                lado.paste(da_previa, (0, 0))
                lado.paste(do_documento, (largura + 10, 0))
                lado.save(comparacao)
                print("        comparacao salva em", comparacao)

        prev.fechar()
        root.update()
except Exception:
    falhas.append("erro: " + traceback.format_exc())

print("\nFALHAS:", "nenhuma" if not falhas else "")
for f in falhas:
    print(" -", f)
try:
    try:
        app.icon.stop()
    except Exception:
        pass
    root.destroy()
except Exception:
    pass
shutil.rmtree(tmp, ignore_errors=True)
sys.stdout.flush()
os._exit(0)
