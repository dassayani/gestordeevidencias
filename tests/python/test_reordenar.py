# -*- coding: utf-8 -*-
"""A regra que decide para onde o item arrastado vai: `calcular_destino`.

E uma funcao pura (altura do ponteiro + pontos medios dos outros cartoes ->
posicao de insercao), por isso se testa aqui sem janela nenhuma; o que a tela
faz com ela e conferido em cenario_arraste_sequencia.

Propriedades que importam para quem arrasta:
  * o destino sempre existe (0..N) e cresce junto com a altura do ponteiro
  * e coerente nos dois sentidos: nao ha posicao inalcancavel
  * a folga impede o vao de oscilar com o ponteiro parado sobre o meio de um
    cartao - o defeito que tornaria o arraste "nervoso"
"""

import os as _os
import sys as _sys

# Raiz do projeto a partir deste arquivo: tests/python/x.py -> duas pastas acima
RAIZ = _os.path.dirname(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
_sys.path.insert(0, RAIZ)
_os.chdir(RAIZ)

import sys

from gestor.ui.document_builder import calcular_destino

falhas = []


def checar(condicao, descricao):
    print(("OK: " if condicao else "FALHOU: ") + descricao)
    if not condicao:
        falhas.append(descricao)


# quatro cartoes de 213 px + 8 de folga, o primeiro comecando em 4
ALTURA, FOLGA = 213, 8
MIDS = [4 + i * (ALTURA + FOLGA) + ALTURA / 2 for i in range(4)]
MARGEM = 0.15 * ALTURA


def varrer(ys, atual):
    """Destino em cada altura, partindo de `atual`, como no arraste de verdade:
    cada passo parte do destino anterior."""
    d, caminho = atual, []
    for y in ys:
        d = calcular_destino(y, MIDS, d, MARGEM)
        caminho.append(d)
    return caminho


# ---- extremos ----
checar(calcular_destino(-500, MIDS, 2, MARGEM) == 0, "bem acima de tudo -> posicao 0")
checar(calcular_destino(5000, MIDS, 1, MARGEM) == 4, "bem abaixo de tudo -> fim da lista")
checar(calcular_destino(MIDS[0], [], 0, MARGEM) == 0, "lista sem outros cartoes -> 0")

# ---- cada posicao e alcancavel, descendo e subindo ----
descendo = varrer(range(-50, 1000, 3), 0)
subindo = varrer(range(1000, -50, -3), 4)
checar(sorted(set(descendo)) == [0, 1, 2, 3, 4], "descendo passa por 0, 1, 2, 3 e 4")
checar(sorted(set(subindo)) == [0, 1, 2, 3, 4], "subindo passa por 4, 3, 2, 1 e 0")
checar(descendo == sorted(descendo), "descendo, o destino nunca diminui")
checar(subindo == sorted(subindo, reverse=True), "subindo, o destino nunca aumenta")

# ---- so troca depois de passar do meio por mais que a folga ----
checar(calcular_destino(MIDS[1] + MARGEM - 1, MIDS, 1, MARGEM) == 1,
       "ainda dentro da folga do meio: nao troca")
checar(calcular_destino(MIDS[1] + MARGEM + 1, MIDS, 1, MARGEM) == 2,
       "passou da folga do meio: troca")
checar(calcular_destino(MIDS[1] - MARGEM + 1, MIDS, 2, MARGEM) == 2,
       "voltando, ainda dentro da folga: nao troca de volta")
checar(calcular_destino(MIDS[1] - MARGEM - 1, MIDS, 2, MARGEM) == 1,
       "voltando, passou da folga: troca de volta")

# ---- sem oscilacao: ponteiro parado sobre o meio de qualquer cartao ----
for i, meio in enumerate(MIDS):
    for atual in range(5):
        d = calcular_destino(meio, MIDS, atual, MARGEM)
        estavel = all(calcular_destino(meio, MIDS, d, MARGEM) == d for _ in range(5))
        if not estavel:
            checar(False, "ponteiro parado no meio do cartao %d oscila (partindo de %d)" % (i, atual))
            break
    else:
        continue
    break
else:
    checar(True, "ponteiro parado sobre o meio de qualquer cartao nao faz o vao oscilar")

# ---- pequenas tremidas perto de uma fronteira nao fazem o vao pular ----
fronteira = MIDS[2]
d0 = calcular_destino(fronteira + MARGEM + 2, MIDS, 2, MARGEM)       # acabou de trocar
tremida = [fronteira + MARGEM + delta for delta in (2, -3, 4, -5, 3, -4, 5, -2)]
checar(len(set(varrer(tremida, d0))) == 1,
       "tremer 5 px em volta da fronteira depois de trocar nao devolve o vao")

# ---- a folga e simetrica ----
sobe = calcular_destino(MIDS[2] - MARGEM - 1, MIDS, 3, MARGEM)
desce = calcular_destino(MIDS[2] + MARGEM + 1, MIDS, 2, MARGEM)
checar(sobe == 2 and desce == 3, "a folga e a mesma nos dois sentidos")

print()
print("FALHAS:", falhas if falhas else "nenhuma")
sys.exit(1 if falhas else 0)
