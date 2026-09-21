# -*- coding: utf-8 -*-
"""mover_para_lixeira: os arquivos saem da pasta E aparecem na Lixeira.

Usa arquivos de teste com nome unico, e os remove da Lixeira no fim para nao
deixar sujeira no computador.
"""

import os as _os
import sys as _sys

# Raiz do projeto a partir deste arquivo: tests/python/x.py -> duas pastas acima
RAIZ = _os.path.dirname(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
_sys.path.insert(0, RAIZ)
_os.chdir(RAIZ)
SAIDA = _os.path.join(RAIZ, "tests", "_saida")
_os.makedirs(SAIDA, exist_ok=True)

import sys, os, time, tempfile
import utils

falhas = []
marca = "lixeira_teste_%d" % int(time.time())
pasta = tempfile.mkdtemp(prefix="lix_")
criados = []
for i in range(3):
    p = os.path.join(pasta, f"{marca}_{i}.txt")
    with open(p, "w", encoding="utf-8") as f:
        f.write("conteudo de teste")
    criados.append(p)
# um com acento, que e onde a API costuma tropecar
acento = os.path.join(pasta, f"{marca}_acentuação.txt")
with open(acento, "w", encoding="utf-8") as f:
    f.write("ção")
criados.append(acento)

print("criados:", len(criados), "em", pasta)

def na_lixeira(padrao):
    import win32com.client
    sh = win32com.client.Dispatch("Shell.Application")
    lixo = sh.NameSpace(10)
    return [it.Name for it in lixo.Items() if padrao in it.Name]

antes_lixo = len(na_lixeira(marca))
ok = utils.mover_para_lixeira(criados)
time.sleep(1.0)
print("mover_para_lixeira:", ok)
if not ok:
    falhas.append("a funcao devolveu False")

restantes = [c for c in criados if os.path.exists(c)]
print("ainda na pasta:", len(restantes))
if restantes:
    falhas.append(f"{len(restantes)} arquivo(s) nao sairam da pasta")

achados = na_lixeira(marca)
print("encontrados na Lixeira:", len(achados))
for n in achados:
    print("   -", n)
if len(achados) < len(criados):
    falhas.append(f"esperava {len(criados)} na Lixeira, achei {len(achados)}")

# lista vazia nao pode dar erro
if utils.mover_para_lixeira([]) is not True:
    falhas.append("lista vazia devia devolver True")
if utils.mover_para_lixeira([os.path.join(pasta, "nao_existe.txt")]) is not True:
    falhas.append("caminho inexistente devia ser ignorado sem erro")

# Os 4 arquivos de teste ficam na Lixeira de proposito. Apaga-los daqui
# exigiria InvokeVerb("delete"), que abre a confirmacao modal do Explorer e
# trava o processo sem ninguem para clicar. Sao ~40 bytes com nome marcado.
print("deixados na Lixeira (identificaveis por '%s'): %d" % (marca, len(achados)))

os.rmdir(pasta) if not os.listdir(pasta) else None
print("\nFALHAS:", "nenhuma" if not falhas else "")
for f in falhas:
    print(" -", f)

# COM carregado no processo as vezes segura o desligamento do interpretador.
sys.stdout.flush()
os._exit(0)
