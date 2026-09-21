# -*- coding: utf-8 -*-

import os as _os
import sys as _sys

# Raiz do projeto a partir deste arquivo: tests/python/x.py -> duas pastas acima
RAIZ = _os.path.dirname(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
_sys.path.insert(0, RAIZ)
_os.chdir(RAIZ)
SAIDA = _os.path.join(RAIZ, "tests", "_saida")
_os.makedirs(SAIDA, exist_ok=True)

import os
from PIL import Image
import pdf_export, docx_export

img = os.path.join(SAIDA, "amostra.png")
Image.new("RGB", (800, 500), (40, 90, 110)).save(img)

casos = [
    ("acento comum", "Configuracao de validacao: nao ha erro (ç ã é ô)"),
    ("travessao", "Passo 1 \u2014 abrir a tela"),
    ("aspas curvas", "Clicou em \u201cSalvar\u201d"),
    ("reticencias", "Carregando\u2026"),
    ("emoji", "Resultado \u2705 aprovado"),
]
falhas = []
for nome, legenda in casos:
    capa = {"titulo": legenda, "caso": "CT-01", "autor": "QA",
            "data": "18/09/2026", "ambiente": "QA"}
    passos = [{"caminho": img, "legenda": legenda}]
    for motor, fn, ext in (("PDF ", pdf_export.exportar_passo_a_passo, "pdf"),
                            ("DOCX", docx_export.exportar_passo_a_passo, "docx")):
        destino = os.path.join(SAIDA, f"t.{ext}")
        try:
            fn(destino, capa, passos)
            print(f"OK    {motor} {nome:15s}")
        except Exception as e:
            print(f"FALHA {motor} {nome:15s}: {type(e).__name__}: {e}")
            falhas.append(f"{motor.strip()} {nome}: {type(e).__name__}: {e}")

# mesma linha final de todos os cenarios: e o que a suite le como resultado
print("\nFALHAS:", "nenhuma" if not falhas else "")
for f in falhas:
    print(" -", f)
