# -*- coding: utf-8 -*-
"""O titulo padrao da capa acompanha o modelo, sem pisar no que o usuario escreveu.

A regra e pura (`titulo_ao_trocar_modelo`), por isso se testa aqui sem janela;
o que a tela faz com ela e conferido em cenario_titulo_por_modelo.

O que importa para quem usa:
  * cada modelo tem o seu titulo padrao e os nomes na interface sao os novos
  * trocar de modelo so troca o titulo se ele ainda e o padrao do modelo anterior
  * um titulo digitado a mao nao e sobrescrito, nem um titulo apagado de proposito
"""

import os as _os
import sys as _sys

# Raiz do projeto a partir deste arquivo: tests/python/x.py -> duas pastas acima
RAIZ = _os.path.dirname(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
_sys.path.insert(0, RAIZ)
_os.chdir(RAIZ)

import sys

from gestor.ui.document_builder import (MODELOS_UI, TITULOS_PADRAO, titulo_padrao,
                                        titulo_ao_trocar_modelo)

falhas = []


def checar(condicao, descricao):
    print(("OK: " if condicao else "FALHOU: ") + descricao)
    if not condicao:
        falhas.append(descricao)


MODELOS = ["passo", "ficha", "qa"]

# ---- o mapeamento ----
checar(TITULOS_PADRAO == {"passo": "Evidências passo a passo",
                          "ficha": "Evidências de Testes",
                          "qa": "Relatório de Evidências"},
       "os tres modelos tem o titulo padrao pedido")
checar([v for v, _, _ in MODELOS_UI] == MODELOS,
       "os identificadores internos dos modelos nao mudaram")
checar([n for _, n, _ in MODELOS_UI] == ["Passo a passo", "Ficha", "Relatório"],
       "os nomes dos modelos na interface sao Passo a passo, Ficha e Relatório")
checar(titulo_padrao("modelo_que_nao_existe") == TITULOS_PADRAO["passo"],
       "modelo desconhecido cai no padrao do passo a passo")

# ---- titulo ainda padrao: acompanha, em todos os pares de modelos ----
for antes in MODELOS:
    for depois in MODELOS:
        checar(titulo_ao_trocar_modelo(TITULOS_PADRAO[antes], antes, depois)
               == TITULOS_PADRAO[depois],
               "padrao de %s vira o padrao de %s" % (antes, depois))

# ---- titulo do usuario: nunca e sobrescrito ----
for antes in MODELOS:
    for depois in MODELOS:
        checar(titulo_ao_trocar_modelo("Fechamento de setembro", antes, depois)
               == "Fechamento de setembro",
               "titulo digitado fica ao trocar de %s para %s" % (antes, depois))

# o padrao de OUTRO modelo, que o usuario digitou nesse, tambem e dele
checar(titulo_ao_trocar_modelo(TITULOS_PADRAO["qa"], "passo", "ficha")
       == TITULOS_PADRAO["qa"],
       "texto igual ao padrao de um modelo que nao e o anterior nao e trocado")

# ---- vazio digitado de proposito vale ----
for antes in MODELOS:
    checar(titulo_ao_trocar_modelo("", antes, "ficha") == "",
           "titulo apagado de proposito continua vazio ao sair de %s" % antes)

# ---- ida e volta ----
t = TITULOS_PADRAO["passo"]
for ant, nov in (("passo", "ficha"), ("ficha", "qa"), ("qa", "passo")):
    t = titulo_ao_trocar_modelo(t, ant, nov)
checar(t == TITULOS_PADRAO["passo"], "dar a volta nos tres modelos devolve o titulo inicial")

# titulo editado no meio do caminho: a partir dali nada mexe nele
t = titulo_ao_trocar_modelo(TITULOS_PADRAO["passo"], "passo", "ficha")
t = t + " - rev 2"
for ant, nov in (("ficha", "qa"), ("qa", "passo")):
    t = titulo_ao_trocar_modelo(t, ant, nov)
checar(t == TITULOS_PADRAO["ficha"] + " - rev 2",
       "titulo editado depois de trocar de modelo nao e mais trocado")

print("\nFALHAS:", "nenhuma" if not falhas else "")
for f in falhas:
    print(" -", f)
sys.exit(1 if falhas else 0)
