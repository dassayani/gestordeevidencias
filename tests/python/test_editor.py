# -*- coding: utf-8 -*-
"""O editor abre e grava normalmente sem o bloco de metadados?"""

import os as _os
import sys as _sys

# Raiz do projeto a partir deste arquivo: tests/python/x.py -> duas pastas acima
RAIZ = _os.path.dirname(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
_sys.path.insert(0, RAIZ)
_os.chdir(RAIZ)
SAIDA = _os.path.join(RAIZ, "tests", "_saida")
_os.makedirs(SAIDA, exist_ok=True)

import sys, os, ctypes, time, traceback
if not ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4)):
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
from tkinterdnd2 import TkinterDnD
from gestor.ui import workspace
from gestor.dados import capture_store

# Pasta propria com capturas criadas agora: antes este teste abria o app sobre
# a pasta real da maquina, o que o amarrava a existir captura la (e do dia de
# hoje, por causa do filtro inicial) e mexia em evidencia de verdade.
import tempfile, shutil
from PIL import Image as _Image
from gestor.dados import config as _config

_tmp = tempfile.mkdtemp(prefix="ge_teste_")
_capturas = os.path.join(_tmp, "Capturas")
os.makedirs(_capturas)
for _i in range(3):
    _Image.new("RGB", (900, 600), (40 + _i * 40, 100, 150)).save(
        os.path.join(_capturas, "print_1100%02d.png" % _i))
_cfg = _config.load(_tmp)
_cfg["pasta_capturas"] = _capturas
_config.save(_tmp, _cfg)


falhas, erros = [], []
root = TkinterDnD.Tk()
root.report_callback_exception = lambda *a: erros.append("".join(traceback.format_exception(*a)))
app = workspace.AppEvidencias(root, _capturas, os.path.join(_tmp, "PDF"), RAIZ, _tmp)
app.pausar_timer = True
root.update()

pngs = sorted(f for f in os.listdir(app.pasta_capturas)
              if f.lower().endswith(".png") and not f.endswith(".raw.png"))
caminho = os.path.join(app.pasta_capturas, pngs[0])
meta_antes = capture_store.load_meta(caminho)
legenda_antes = meta_antes.get("caption", "")
print("legenda original:", repr(legenda_antes))

try:
    ed = app.abrir_editor(caminho)
    ed.update()
except Exception:
    print("FALHA ao abrir:", traceback.format_exc()); sys.exit(1)
print("editor abriu")

for attr in ("txt_legenda", "entry_caso"):
    if not hasattr(ed, attr): falhas.append(f"sumiu o campo {attr}")
if hasattr(ed, "_linhas_metadados"): falhas.append("_linhas_metadados ainda existe")

MARCA = "teste de gravacao %d" % int(time.time())
ed.txt_legenda.delete("1.0", "end"); ed.txt_legenda.insert("1.0", MARCA)
ed.update()
try:
    ed.gravar()
    ed.update()
except Exception:
    falhas.append("gravar() levantou:\n" + traceback.format_exc())

meta = capture_store.load_meta(caminho)
if meta.get("caption") != MARCA:
    falhas.append(f"a legenda nao persistiu: {meta.get('caption')!r}")
else:
    print("gravou e persistiu a legenda")

# devolve como estava
ed.txt_legenda.delete("1.0", "end"); ed.txt_legenda.insert("1.0", legenda_antes)
ed.gravar(); ed.update()
print("legenda restaurada:", repr(capture_store.load_meta(caminho).get("caption", "")))

ed.destroy(); root.update()
if erros: falhas.append("excecoes engolidas pelo Tk:\n" + "\n".join(erros))
print("\nFALHAS:", "nenhuma" if not falhas else "")
for f in falhas: print(" -", f)
try:
    # A bandeja roda numa thread com laco de mensagens nativo. Parar antes de
    # encerrar evita derrubar o processo na saida.
    app.icon.stop()
except Exception:
    pass
root.destroy()

shutil.rmtree(_tmp, ignore_errors=True)
