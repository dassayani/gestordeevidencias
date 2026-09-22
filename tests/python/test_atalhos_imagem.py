# -*- coding: utf-8 -*-
"""Com o foco na imagem, os atalhos da janela seguem valendo."""

import os as _os
import sys as _sys

# Raiz do projeto a partir deste arquivo: tests/python/x.py -> duas pastas acima
RAIZ = _os.path.dirname(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
_sys.path.insert(0, RAIZ)
_os.chdir(RAIZ)
SAIDA = _os.path.join(RAIZ, "tests", "_saida")
_os.makedirs(SAIDA, exist_ok=True)

import os, ctypes, time, copy
if not ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4)):
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
import win32clipboard
from tkinterdnd2 import TkinterDnD
from gestor.ui import workspace

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


falhas = []
root = TkinterDnD.Tk()
app = workspace.AppEvidencias(root, _capturas, os.path.join(_tmp, "PDF"), RAIZ, _tmp)
app.pausar_timer = True
root.deiconify(); root.update()
pngs = sorted(f for f in os.listdir(app.pasta_capturas)
              if f.lower().endswith(".png") and not f.endswith(".raw.png"))
caminho = os.path.join(app.pasta_capturas, pngs[0])
ed = app.abrir_editor(caminho)
ed.update(); time.sleep(0.4); ed.update()
shapes_originais = copy.deepcopy(ed.shapes)
print("anotacoes iniciais:", len(ed.shapes))

def clipboard():
    win32clipboard.OpenClipboard()
    try:
        return (bool(win32clipboard.IsClipboardFormatAvailable(win32clipboard.CF_DIB)),
                bool(win32clipboard.IsClipboardFormatAvailable(win32clipboard.CF_UNICODETEXT)))
    finally:
        win32clipboard.CloseClipboard()

# ---------- 1) Ctrl+C com foco na imagem copia a IMAGEM
win32clipboard.OpenClipboard(); win32clipboard.EmptyClipboard(); win32clipboard.CloseClipboard()
ed.canvas.focus_force()
ed.update()
ed.canvas.event_generate("<Control-c>")
ed.update(); time.sleep(0.4)
img, txt = clipboard()
print("[imagem] Ctrl+C -> imagem:", img, "| texto:", txt)
if not img:
    falhas.append("com foco na imagem, o Ctrl+C NAO copiou a imagem")

# ---------- 2) Delete apaga a anotacao selecionada
if ed.shapes:
    alvo = ed.shapes[-1]["id"]
    ed.ferramenta = "mover"      # _apagar_selecionado_tecla so age nessa ferramenta
    ed.selected_id = alvo
    ed.canvas.focus_force()
    ed.update()
    n_antes = len(ed.shapes)
    ed.canvas.event_generate("<Delete>")
    ed.update(); time.sleep(0.2)
    print("[imagem] Delete -> anotacoes", n_antes, "->", len(ed.shapes))
    if len(ed.shapes) != n_antes - 1:
        falhas.append("com foco na imagem, o Delete NAO apagou a anotacao")

    # ---------- 3) Ctrl+Z desfaz
    n_antes = len(ed.shapes)
    ed.canvas.focus_force()
    ed.update()
    ed.canvas.event_generate("<Control-z>")
    ed.update(); time.sleep(0.2)
    print("[imagem] Ctrl+Z -> anotacoes", n_antes, "->", len(ed.shapes))
    if len(ed.shapes) <= n_antes:
        falhas.append("com foco na imagem, o Ctrl+Z NAO desfez")
else:
    print("sem anotacoes nesta captura: Delete/Ctrl+Z nao testados")

# devolve o estado original sem gravar
ed.shapes = shapes_originais
ed._sujo = False
print("\nFALHAS:", "nenhuma" if not falhas else "")
for f in falhas:
    print(" -", f)
try:
    # A bandeja roda numa thread com laco de mensagens nativo. Parar antes de
    # encerrar evita derrubar o processo na saida.
    app.icon.stop()
except Exception:
    pass
ed.destroy(); root.destroy()

shutil.rmtree(_tmp, ignore_errors=True)
