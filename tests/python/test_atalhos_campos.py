# -*- coding: utf-8 -*-
"""Ctrl+C/Ctrl+V e Delete dentro dos campos do editor.

A leitura do clipboard e feita pela API do Tk, e nao por win32clipboard:
quando o Ctrl+C parte de um widget de texto, quem assume a posse da area de
transferencia e o proprio Tk, e abrir por win32 no mesmo processo devolve
"acesso negado".
"""

import os as _os
import sys as _sys

# Raiz do projeto a partir deste arquivo: tests/python/x.py -> duas pastas acima
RAIZ = _os.path.dirname(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
_sys.path.insert(0, RAIZ)
_os.chdir(RAIZ)
SAIDA = _os.path.join(RAIZ, "tests", "_saida")
_os.makedirs(SAIDA, exist_ok=True)

import os, ctypes, time
if not ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4)):
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
import tkinter as tk
from tkinterdnd2 import TkinterDnD
import workspace

# Pasta propria com capturas criadas agora: antes este teste abria o app sobre
# a pasta real da maquina, o que o amarrava a existir captura la (e do dia de
# hoje, por causa do filtro inicial) e mexia em evidencia de verdade.
import tempfile, shutil
from PIL import Image as _Image
import config as _config

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
ed = app.abrir_editor(os.path.join(app.pasta_capturas, pngs[0]))
ed.update(); time.sleep(0.4); ed.update()

TEXTO = "abcdef teste de copia"

def texto_no_clipboard():
    """Texto na area de transferencia, ou None quando nao ha texto nenhum."""
    try:
        return ed.clipboard_get()
    except tk.TclError:
        return None

def limpar():
    ed.clipboard_clear()
    ed.update()


def esperar(condicao, limite=2.0, passo=0.05):
    """Espera a condicao virar verdadeira, ate `limite` segundos.

    Substitui a espera fixa: a area de transferencia pertence ao Windows
    inteiro, e outro programa pode estar com ela no instante do teste. Com
    tempo fixo, este teste falhava de vez em quando sem defeito nenhum no app.
    """
    fim = time.time() + limite
    while time.time() < fim:
        ed.update()
        if condicao():
            return True
        time.sleep(passo)
    return bool(condicao())


def copiar_e_confirmar(widget):
    """Ctrl+C no widget, insistindo se a area de transferencia foi tomada."""
    for _ in range(3):
        widget.focus_force()
        widget.event_generate("<Control-c>")
        if esperar(lambda: texto_no_clipboard() == TEXTO):
            return True
        limpar()
    return False

# ---------- 1) Ctrl+C na LEGENDA (tk.Text)
limpar()
ed.txt_legenda.delete("1.0", "end")
ed.txt_legenda.insert("1.0", TEXTO)
ed.txt_legenda.focus_force()
ed.txt_legenda.tag_add("sel", "1.0", "end-1c")
ed.update()
copiou = copiar_e_confirmar(ed.txt_legenda)
lido = texto_no_clipboard()
print("[legenda] Ctrl+C ->", repr(lido))
if not copiou:
    # se o atalho da janela tivesse rodado, a imagem teria tomado o lugar do
    # texto e a leitura voltaria None
    falhas.append(f"legenda: o Ctrl+C nao deixou o texto no clipboard ({lido!r})")

# ---------- 2) Ctrl+V na LEGENDA
ed.txt_legenda.delete("1.0", "end")
ed.update()
ed.txt_legenda.focus_force()
ed.txt_legenda.event_generate("<Control-v>")
esperar(lambda: TEXTO in ed.txt_legenda.get("1.0", "end-1c"))
colado = ed.txt_legenda.get("1.0", "end-1c")
print("[legenda] Ctrl+V -> colou:", repr(colado))
if TEXTO not in colado:
    falhas.append("legenda: o Ctrl+V nao colou o texto")

# ---------- 3) Ctrl+C no CASO (tk.Entry)
limpar()
ed.entry_caso.delete(0, "end")
ed.entry_caso.insert(0, TEXTO)
ed.entry_caso.focus_force()
ed.entry_caso.select_range(0, "end")
ed.update()
copiou = copiar_e_confirmar(ed.entry_caso)
lido = texto_no_clipboard()
print("[caso] Ctrl+C ->", repr(lido))
if not copiou:
    falhas.append(f"caso: o Ctrl+C nao deixou o texto no clipboard ({lido!r})")

# ---------- 4) Ctrl+V no CASO
ed.entry_caso.delete(0, "end")
ed.update()
ed.entry_caso.focus_force()
ed.entry_caso.event_generate("<Control-v>")
esperar(lambda: TEXTO in ed.entry_caso.get())
colado = ed.entry_caso.get()
print("[caso] Ctrl+V -> colou:", repr(colado))
if TEXTO not in colado:
    falhas.append("caso: o Ctrl+V nao colou o texto")

# ---------- 5) Delete no campo nao pode apagar anotacao
ed.ferramenta = "mover"
if ed.shapes:
    ed.selected_id = ed.shapes[-1]["id"]
n_antes = len(ed.shapes)
ed.txt_legenda.focus_force()
ed.txt_legenda.delete("1.0", "end")
ed.txt_legenda.insert("1.0", "xyz")
ed.txt_legenda.mark_set("insert", "1.0")
ed.update()
ed.txt_legenda.event_generate("<Delete>")
ed.update(); time.sleep(0.2)
print("[legenda] Delete -> anotacoes", n_antes, "->", len(ed.shapes),
      "| texto:", repr(ed.txt_legenda.get("1.0", "end-1c")))
if len(ed.shapes) != n_antes:
    falhas.append("legenda: o Delete apagou uma ANOTACAO em vez do caractere")
if ed.txt_legenda.get("1.0", "end-1c") != "yz":
    falhas.append("legenda: o Delete nao apagou o caractere")

ed.txt_legenda.delete("1.0", "end")
ed.entry_caso.delete(0, "end")
ed._sujo = False
print("\nFALHAS:", "nenhuma" if not falhas else "")
for f in falhas:
    print(" -", f)
ed.destroy(); root.destroy()

shutil.rmtree(_tmp, ignore_errors=True)
