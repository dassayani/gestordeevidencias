# -*- coding: utf-8 -*-
"""Abre o exe recem compilado, fotografa a janela principal e encerra."""

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
import win32gui, win32con
from PIL import ImageGrab
from screeninfo import get_monitors

SP = SAIDA
EXE = r"C:\projeto_evidencias\dist\GestorEvidencias\GestorEvidencias.exe"
TAG = time.strftime("%H%M%S")

proc = subprocess.Popen([EXE], cwd=os.path.dirname(EXE))
print("pid:", proc.pid)

# O app pode migrar para outro processo (instancia unica), entao procuro a
# janela pelo titulo, nao pelo pid.
alvo = None
for _ in range(60):
    time.sleep(1.0)
    achadas = []

    def visita(h, _):
        if win32gui.IsWindowVisible(h):
            t = win32gui.GetWindowText(h)
            if "Gestor de Evid" in t:
                achadas.append((h, t))
    win32gui.EnumWindows(visita, None)
    if achadas:
        alvo, titulo = achadas[0]
        print("janela encontrada:", titulo, "apos", _ + 1, "s")
        break

if not alvo:
    print("FALHAS: a janela principal nao apareceu em 60s")
    proc.terminate()
    sys.exit(1)

win32gui.SetWindowPos(alvo, win32con.HWND_TOPMOST, 0, 0, 0, 0,
                      win32con.SWP_NOMOVE | win32con.SWP_NOSIZE | win32con.SWP_SHOWWINDOW)
time.sleep(2.0)
mons = get_monitors()
mx, my = min(m.x for m in mons), min(m.y for m in mons)
l, t, r, b = win32gui.GetWindowRect(alvo)
tela = ImageGrab.grab(all_screens=True)
arq = os.path.join(SP, f"pacote_{TAG}.png")
tela.crop((l - mx, t - my, r - mx, b - my)).save(arq)
print("ARQUIVO:", arq)

# fecha pelo caminho normal, para exercitar o encerramento do app
win32gui.PostMessage(alvo, win32con.WM_CLOSE, 0, 0)
time.sleep(3.0)
try:
    proc.wait(timeout=10)
    print("encerrou com codigo:", proc.returncode)
except Exception:
    proc.terminate()
    print("precisou de terminate()")

print("\nFALHAS: nenhuma")
sys.stdout.flush()
os._exit(0)
