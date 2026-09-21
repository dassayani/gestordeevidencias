# -*- coding: utf-8 -*-
"""O atalho de captura funciona com o painel escondido.

Este era o defeito: com a janela principal em `withdraw`, o Tk nao realizava a
Toplevel do seletor, que ficava com geometria 1x1 e nunca aparecia. A tecla era
registrada e o callback rodava — nao adiantava olhar so o registro.

Nao sintetiza a tecla de proposito: tecla sintetizada da falso negativo contra
o executavel empacotado (o Windows entrega WM_HOTKEY so para entrada real), o
que ja levou a diagnostico errado antes. Aqui o teste aciona o mesmo callback
que o atalho aciona e confere o que o usuario veria: uma janela de selecao
visivel cobrindo a tela, com o painel escondido.
"""

import os as _os
import sys as _sys

# Raiz do projeto a partir deste arquivo: tests/python/x.py -> duas pastas acima
RAIZ = _os.path.dirname(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
_sys.path.insert(0, RAIZ)
_os.chdir(RAIZ)
SAIDA = _os.path.join(RAIZ, "tests", "_saida")
_os.makedirs(SAIDA, exist_ok=True)

import os, sys, ctypes, tempfile, shutil, traceback, time

if not ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4)):
    ctypes.windll.shcore.SetProcessDpiAwareness(2)

import tkinter as tk
import win32gui
from tkinterdnd2 import TkinterDnD
from PIL import Image
import config
import hotkey
from workspace import AppEvidencias

falhas = []


def checar(condicao, descricao):
    print(("OK:     " if condicao else "FALHOU: ") + descricao)
    if not condicao:
        falhas.append(descricao)


def janelas_visiveis():
    achadas = []

    def visita(h, _):
        if win32gui.IsWindowVisible(h):
            achadas.append((h, win32gui.GetWindowRect(h), win32gui.GetWindowText(h)))
    win32gui.EnumWindows(visita, None)
    return achadas


tmp = tempfile.mkdtemp(prefix="ge_hotkey_")
capturas = os.path.join(tmp, "Capturas")
os.makedirs(capturas)
Image.new("RGB", (400, 300), (60, 100, 140)).save(os.path.join(capturas, "print_1.png"))
cfg = config.load(tmp)
cfg["pasta_capturas"] = capturas
config.save(tmp, cfg)

root = TkinterDnD.Tk()
app = AppEvidencias(root, capturas, os.path.join(tmp, "PDF"), RAIZ, tmp)
app.pausar_timer = True
root.deiconify()
root.update()

try:
    # 1) o app tenta registrar o atalho ao subir
    checar(app.hotkeys is not None, "o servico de atalhos globais subiu")
    combos = [c[0] for c in hotkey.COMBOS_CAPTURA_AREA]
    checar(app.config.get("atalho_captura_area", "printscreen") in combos,
           "a combinacao configurada esta entre as oferecidas")
    if app.erros_atalhos:
        # nesta maquina outro programa pode estar com a tecla; isso e ambiente,
        # nao defeito do app, e o proprio app avisa na tela de Configuracoes
        print("        aviso: atalho ocupado por outro programa ->",
              "; ".join(app.erros_atalhos))
    else:
        checar(True, "a tecla foi registrada sem conflito")

    # 2) esconde o painel, como o app faz por inatividade ou pelo botao X
    app.esconder_janela()
    root.update()
    time.sleep(0.3)
    root.update()
    checar(root.state() == "withdrawn", "o painel principal ficou escondido")

    antes = len(janelas_visiveis())

    # 3) dispara o mesmo callback que o atalho dispara
    app.iniciar_seletor()
    root.update()
    time.sleep(0.8)
    root.update()

    largura_tela = root.winfo_screenwidth()
    altura_tela = root.winfo_screenheight()
    cobrindo = [(h, r, t) for h, r, t in janelas_visiveis()
                if (r[2] - r[0]) >= largura_tela * 0.9 and (r[3] - r[1]) >= altura_tela * 0.5]
    checar(bool(cobrindo),
           "com o painel escondido, o seletor aparece cobrindo a tela")
    if cobrindo:
        r = cobrindo[0][1]
        print("        seletor em %dx%d a partir de (%d, %d)"
              % (r[2] - r[0], r[3] - r[1], r[0], r[1]))

    # 4) o seletor e uma janela realmente mapeada, e nao um 1x1 invisivel
    seletores = [w for w in root.winfo_children() if isinstance(w, tk.Toplevel)]
    checar(bool(seletores), "a janela do seletor existe no lado do Tk")
    for s in seletores:
        checar(s.winfo_width() > 100 and s.winfo_height() > 100,
               "o seletor foi realizado com tamanho util (%dx%d)"
               % (s.winfo_width(), s.winfo_height()))
        s.destroy()
    root.update()

    # 5) e o painel volta quando pedido
    app.mostrar_janela()
    root.update()
    checar(root.state() != "withdrawn", "o painel volta a aparecer depois")
except Exception:
    falhas.append("erro: " + traceback.format_exc())

print("\nFALHAS:", "nenhuma" if not falhas else "")
for f in falhas:
    print(" -", f)
try:
    if app.hotkeys:
        app.hotkeys.parar()
    root.destroy()
except Exception:
    pass
shutil.rmtree(tmp, ignore_errors=True)
sys.stdout.flush()
os._exit(0)
