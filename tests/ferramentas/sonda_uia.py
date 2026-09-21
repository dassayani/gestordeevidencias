# -*- coding: utf-8 -*-
"""O UI Automation do Windows enxerga os widgets de uma janela Tkinter?

E a pergunta que decide se da para automatizar este app com as ferramentas
usuais de E2E de desktop (FlaUI, RPA.Windows, WinAppDriver, AutoIt), que todas
falam UIA por baixo. Abre uma janela Tk com controles conhecidos e pergunta ao
UIA quantos elementos ele encontra la dentro.
"""

import os as _os
import sys as _sys

# Raiz do projeto a partir deste arquivo: tests/ferramentas/x.py -> duas pastas acima
RAIZ = _os.path.dirname(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
_sys.path.insert(0, RAIZ)
_os.chdir(RAIZ)
SAIDA = _os.path.join(RAIZ, "tests", "_saida")
_os.makedirs(SAIDA, exist_ok=True)

import os, sys, ctypes, subprocess, time, textwrap

if not ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4)):
    ctypes.windll.shcore.SetProcessDpiAwareness(2)

SP = SAIDA
JANELA = os.path.join(SP, "_janela_tk_sonda.py")
with open(JANELA, "w", encoding="utf-8") as f:
    f.write(textwrap.dedent('''
        import tkinter as tk
        r = tk.Tk()
        r.title("SONDA TK UIA")
        r.geometry("360x220+120+120")
        tk.Label(r, text="Rotulo de teste").pack(pady=6)
        e = tk.Entry(r); e.insert(0, "texto no campo"); e.pack(pady=6)
        tk.Button(r, text="Botao Confirmar").pack(pady=6)
        tk.Checkbutton(r, text="Uma opcao").pack(pady=6)
        r.mainloop()
    '''))

proc = subprocess.Popen([sys.executable, JANELA])
time.sleep(3.0)

import comtypes.client
import win32gui

uia = comtypes.client.CreateObject(
    "{ff48dba4-60ef-4201-aa87-54103eef594e}",
    interface=comtypes.client.GetModule("UIAutomationCore.dll").IUIAutomation)

hwnd = win32gui.FindWindow(None, "SONDA TK UIA")
print("janela encontrada pelo win32:", bool(hwnd))

elemento = uia.ElementFromHandle(hwnd)
print("UIA ve a janela como:", elemento.CurrentName, "| tipo:", elemento.CurrentControlType)

cond = uia.CreateTrueCondition()
TreeScope_Descendants = 4
filhos = elemento.FindAll(TreeScope_Descendants, cond)
print("elementos UIA dentro da janela:", filhos.Length)
for i in range(filhos.Length):
    it = filhos.GetElement(i)
    print("   tipo=%s nome=%r classe=%r" % (it.CurrentControlType, it.CurrentName,
                                            it.CurrentClassName))

print()
print("--- comparacao: o mesmo teste no Bloco de Notas (app Win32 comum) ---")
bloco = subprocess.Popen(["notepad.exe"])
time.sleep(2.0)
h2 = win32gui.FindWindow("Notepad", None)
if h2:
    el2 = uia.ElementFromHandle(h2)
    f2 = el2.FindAll(TreeScope_Descendants, cond)
    print("elementos UIA dentro do Bloco de Notas:", f2.Length)
else:
    print("nao achei a janela do Bloco de Notas")
bloco.terminate()
proc.terminate()
sys.stdout.flush()
os._exit(0)
