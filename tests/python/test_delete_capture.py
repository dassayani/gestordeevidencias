# -*- coding: utf-8 -*-
"""delete_capture manda png + raw + json para a Lixeira, juntos."""

import os as _os
import sys as _sys

# Raiz do projeto a partir deste arquivo: tests/python/x.py -> duas pastas acima
RAIZ = _os.path.dirname(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
_sys.path.insert(0, RAIZ)
_os.chdir(RAIZ)
SAIDA = _os.path.join(RAIZ, "tests", "_saida")
_os.makedirs(SAIDA, exist_ok=True)

import sys, os, time, json, tempfile
from PIL import Image
import capture_store

falhas = []
marca = "captura_teste_%d" % int(time.time())
pasta = tempfile.mkdtemp(prefix="delcap_")
png = os.path.join(pasta, marca + ".png")
Image.new("RGB", (60, 40), (20, 60, 90)).save(png)
Image.new("RGB", (60, 40), (90, 60, 20)).save(capture_store.raw_path(png))
with open(capture_store.json_path(png), "w", encoding="utf-8") as f:
    json.dump({"caption": "teste"}, f)

irmaos = [png, capture_store.raw_path(png), capture_store.json_path(png)]
print("criados:", [os.path.basename(p) for p in irmaos])

def na_lixeira(padrao):
    import win32com.client
    sh = win32com.client.Dispatch("Shell.Application")
    return [it.Name for it in sh.NameSpace(10).Items() if padrao in it.Name]

ok = capture_store.delete_capture(png)
time.sleep(1.0)
print("delete_capture:", ok)
if not ok:
    falhas.append("delete_capture devolveu False")

sobraram = [p for p in irmaos if os.path.exists(p)]
print("sobraram na pasta:", len(sobraram))
if sobraram:
    falhas.append(f"{len(sobraram)} arquivo(s) nao foram removidos")

achados = na_lixeira(marca)
print("na Lixeira:", len(achados), achados)
if len(achados) != 3:
    falhas.append(f"esperava 3 itens na Lixeira, achei {len(achados)}")

# captura inexistente nao pode dar erro
if capture_store.delete_capture(os.path.join(pasta, "nao_existe.png")) is not True:
    falhas.append("captura inexistente devia devolver True")

# Os itens ficam na Lixeira de proposito: InvokeVerb("delete") abre a
# confirmacao modal do Explorer e trava o processo sem ninguem para clicar.
print("deixados na Lixeira (identificaveis por '%s')" % marca)

if not os.listdir(pasta):
    os.rmdir(pasta)
print("\nFALHAS:", "nenhuma" if not falhas else "")
for f in falhas:
    print(" -", f)

# COM carregado no processo as vezes segura o desligamento do interpretador.
sys.stdout.flush()
os._exit(0)
