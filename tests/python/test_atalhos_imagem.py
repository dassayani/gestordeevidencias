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
import main as m, workspace

falhas = []
root = TkinterDnD.Tk()
app = workspace.AppEvidencias(root, m.PASTA_CAPTURAS, m.PASTA_PDFS, m.BASE_DIR, m.DATA_DIR)
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
ed.destroy(); root.destroy()
