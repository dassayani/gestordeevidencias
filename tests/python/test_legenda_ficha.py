# -*- coding: utf-8 -*-
"""Que tipo de legenda escapa da quebra de linha na Ficha?

Mede cada linha produzida por _quebrar e denuncia a que passa da largura
disponivel — que e a que sai para fora do cartao no documento.
"""

import os as _os
import sys as _sys

# Raiz do projeto a partir deste arquivo: tests/python/x.py -> duas pastas acima
RAIZ = _os.path.dirname(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
_sys.path.insert(0, RAIZ)
_os.chdir(RAIZ)
SAIDA = _os.path.join(RAIZ, "tests", "_saida")
_os.makedirs(SAIDA, exist_ok=True)

from gestor.exportacao import pdf_export
from gestor.exportacao.pdf_export import FPDF, MARGEM, PAGE_W

LARGURA = PAGE_W - 2 * MARGEM - 28

CASOS = {
    "frase normal longa":
        "Ao clicar no botao Confirmar da tela de fechamento o sistema deve validar "
        "o saldo disponivel e registrar o log de auditoria antes de concluir",
    "com acentos":
        "Após clicar em Confirmar, o sistema válida o saldo disponível, confere a "
        "data de competência e só então apresenta a mensagem de sucesso",
    "colada do Word (travessao e aspas curvas)":
        "Ao clicar em \u201cConfirmar\u201d \u2014 na tela de fechamento \u2014 o sistema "
        "valida o saldo\u2026 e registra o log de auditoria antes de concluir a operacao",
    # Os dois casos abaixo sao um token unico de proposito — e o que faz a
    # quebra por espaco falhar. As aspas ficam coladas: literais adjacentes se
    # juntam sem inserir espaco nenhum.
    "uma palavra enorme (URL)":
        "https://portal.empresa.com.br/fechamento/validacao/competencia/2026/09/"
        "relatorio-consolidado-final",
    "caminho de arquivo longo":
        r"C:\Usuarios\dasayani\Documentos\Evidencias\Fechamento\2026-09"
        r"\captura-da-tela-de-confirmacao.png",
    "sem espaco algum":
        "validacaodofechamentocomsaldodisponivelelogdeauditoriaregistradoantesdeconcluir",
    "com quebra de linha":
        "Primeira parte da legenda\nSegunda parte que tambem e bem comprida e precisa quebrar",
    "espaco fino/nao separavel (colado de web)":
        "Ao\u00a0clicar\u00a0no\u00a0botao\u00a0Confirmar\u00a0o\u00a0sistema"
        "\u00a0valida\u00a0o\u00a0saldo\u00a0disponivel\u00a0e\u00a0registra"
        "\u00a0o\u00a0log\u00a0de\u00a0auditoria",
}

pdf = FPDF(format="A4", unit="mm")
pdf.add_page()
pdf.set_font("Arial", "B", 11)

falhas = []
print("largura disponivel para a legenda: %.1f mm\n" % LARGURA)
for nome, texto in CASOS.items():
    linhas = pdf_export._quebrar(pdf, texto, LARGURA)
    larguras = [pdf.get_string_width(l) for l in linhas]
    estourou = [(l, w) for l, w in zip(linhas, larguras) if w > LARGURA + 0.5]
    print("%-42s -> %d linha(s), maior %.1f mm %s"
          % (nome, len(linhas), max(larguras) if larguras else 0,
             "ESTOUROU" if estourou else "ok"))
    for l, w in estourou:
        print("      %.1f mm: %s" % (w, l[:70]))
        falhas.append("%s: linha de %.1f mm numa area de %.1f mm" % (nome, w, LARGURA))

print("\nFALHAS:", "nenhuma" if not falhas else "")
for f in falhas:
    print(" -", f)
