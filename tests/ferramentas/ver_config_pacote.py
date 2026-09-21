# -*- coding: utf-8 -*-
"""No exe empacotado: clica no icone de ajustes e fotografa Configuracoes.

Prova que o modulo extraido para configuracoes.py foi junto no pacote e que a
tela abre de verdade, nao so que o import resolveu.
"""

import os as _os
import sys as _sys

# Raiz do projeto a partir deste arquivo: tests/ferramentas/x.py -> duas pastas acima
RAIZ = _os.path.dirname(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
_sys.path.insert(0, RAIZ)
_os.chdir(RAIZ)
SAIDA = _os.path.join(RAIZ, "tests", "_saida")
_os.makedirs(SAIDA, exist_ok=True)

import os, sys, time, subprocess, ctypes
if not ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4)):
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
import win32gui, win32con, win32api
from PIL import ImageGrab
from screeninfo import get_monitors

SP = SAIDA
EXE = r"C:\projeto_evidencias\dist\GestorEvidencias\GestorEvidencias.exe"
TAG = time.strftime("%H%M%S")


def janela(titulo_parcial):
    achadas = []

    def visita(h, _):
        if win32gui.IsWindowVisible(h) and titulo_parcial in win32gui.GetWindowText(h):
            achadas.append(h)
    win32gui.EnumWindows(visita, None)
    return achadas[0] if achadas else None


def foto(h, nome):
    mons = get_monitors()
    mx, my = min(m.x for m in mons), min(m.y for m in mons)
    l, t, r, b = win32gui.GetWindowRect(h)
    tela = ImageGrab.grab(all_screens=True)
    caminho = os.path.join(SP, nome)
    tela.crop((l - mx, t - my, r - mx, b - my)).save(caminho)
    print("ARQUIVO:", caminho)


proc = subprocess.Popen([EXE], cwd=os.path.dirname(EXE))
principal = None
for _ in range(60):
    time.sleep(1.0)
    principal = janela("Gestor de Evid")
    if principal:
        break
if not principal:
    print("FALHAS: painel nao apareceu")
    proc.terminate()
    sys.exit(1)

win32gui.SetWindowPos(principal, win32con.HWND_TOPMOST, 0, 0, 0, 0,
                      win32con.SWP_NOMOVE | win32con.SWP_NOSIZE | win32con.SWP_SHOWWINDOW)
time.sleep(1.5)

# icone de ajustes: ultimo da fileira do cabecalho, canto direito
l, t, r, b = win32gui.GetWindowRect(principal)
x = r - 45
y = t + 71
win32api.SetCursorPos((x, y))
time.sleep(0.4)
win32api.mouse_event(win32con.MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
win32api.mouse_event(win32con.MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)

cfg = None
for _ in range(20):
    time.sleep(0.5)
    cfg = janela("Configura")
    if cfg:
        break

falhas = []
if not cfg:
    falhas.append("a janela de Configuracoes nao abriu no pacote")
else:
    win32gui.SetWindowPos(cfg, win32con.HWND_TOPMOST, 0, 0, 0, 0,
                          win32con.SWP_NOMOVE | win32con.SWP_NOSIZE | win32con.SWP_SHOWWINDOW)
    time.sleep(1.5)
    foto(cfg, f"pkg_config_{TAG}.png")

proc.terminate()
time.sleep(1.0)
print("\nFALHAS:", "nenhuma" if not falhas else "")
for f in falhas:
    print(" -", f)
sys.stdout.flush()
os._exit(0)
