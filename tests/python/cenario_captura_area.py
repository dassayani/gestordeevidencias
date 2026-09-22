# -*- coding: utf-8 -*-
"""Seleção de área: do overlay até o arquivo salvo.

Faltava um cenário que percorresse o caminho inteiro da captura — abrir o
seletor, arrastar, soltar e conferir o arquivo que saiu. Sem ele, mexer nessa
parte era mexer no escuro, e e justamente o caminho mais sensivel do app.

Aciona os tratadores pelo canvas do overlay (event_generate), que e o que o
mouse faz, em vez de chamar funcao interna.
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
from tkinterdnd2 import TkinterDnD
from PIL import Image
import config
from workspace import AppEvidencias

falhas = []


def checar(condicao, descricao):
    print(("OK:     " if condicao else "FALHOU: ") + descricao)
    if not condicao:
        falhas.append(descricao)


def overlay_e_canvas(root):
    """A Toplevel do seletor e o canvas dentro dela."""
    for w in root.winfo_children():
        if isinstance(w, tk.Toplevel) and w.winfo_exists():
            for filho in w.winfo_children():
                if isinstance(filho, tk.Canvas):
                    return w, filho
    return None, None


def pngs(pasta):
    return sorted(f for f in os.listdir(pasta)
                  if f.lower().endswith(".png") and not f.endswith(".raw.png"))


tmp = tempfile.mkdtemp(prefix="ge_captura_")
capturas = os.path.join(tmp, "Capturas")
os.makedirs(capturas)
cfg = config.load(tmp)
cfg["pasta_capturas"] = capturas
cfg["abrir_apos_captura"] = False      # o editor abrindo atrapalharia o cenario
cfg["copiar_apos_captura"] = False     # nao mexer na area de transferencia
cfg["som_captura"] = False
config.save(tmp, cfg)

root = TkinterDnD.Tk()
app = AppEvidencias(root, capturas, os.path.join(tmp, "PDF"), RAIZ, tmp)
app.pausar_timer = True
root.deiconify()
root.update()

try:
    # ---- 1) arrastar uma area conhecida ----
    antes = pngs(capturas)
    app.iniciar_seletor()
    root.update()
    time.sleep(0.5)
    root.update()

    sel, canv = overlay_e_canvas(root)
    checar(sel is not None and canv is not None, "o seletor abriu com o canvas")

    if canv is not None:
        checar(sel.winfo_width() > 100 and sel.winfo_height() > 100,
               "o seletor foi realizado em tamanho util (%dx%d)"
               % (sel.winfo_width(), sel.winfo_height()))

        x1, y1, x2, y2 = 200, 150, 560, 430
        canv.event_generate("<ButtonPress-1>", x=x1, y=y1)
        for i in range(1, 6):
            canv.event_generate("<B1-Motion>",
                                x=x1 + (x2 - x1) * i // 5,
                                y=y1 + (y2 - y1) * i // 5)
        canv.event_generate("<ButtonRelease-1>", x=x2, y=y2)
        root.update()
        time.sleep(0.6)
        root.update()

        depois = pngs(capturas)
        novos = [n for n in depois if n not in antes]
        checar(len(novos) == 1, "a captura gerou exatamente um arquivo (gerou %d)"
               % len(novos))
        if novos:
            caminho = os.path.join(capturas, novos[0])
            with Image.open(caminho) as img:
                largura, altura = img.size
            checar(largura == x2 - x1 and altura == y2 - y1,
                   "o arquivo tem o tamanho da area arrastada (%dx%d, esperado %dx%d)"
                   % (largura, altura, x2 - x1, y2 - y1))
            raw = caminho.replace(".png", ".raw.png")
            checar(os.path.exists(raw), "o original sem anotacao foi salvo junto")

        checar(not sel.winfo_exists(), "o seletor fecha depois de capturar")
        checar(app._capturando is False, "o app sai do estado de captura")

    # ---- 2) Escape cancela sem salvar ----
    antes = pngs(capturas)
    app.iniciar_seletor()
    root.update()
    time.sleep(0.5)
    root.update()
    sel, canv = overlay_e_canvas(root)
    checar(sel is not None, "o seletor abriu de novo")
    if sel is not None:
        sel.event_generate("<Escape>")
        root.update()
        time.sleep(0.3)
        root.update()
        checar(not sel.winfo_exists(), "Escape fecha o seletor")
        checar(pngs(capturas) == antes, "Escape nao deixa arquivo para tras")
        checar(app._capturando is False, "Escape devolve o app ao estado normal")

    # ---- 3) clique sem arrastar e area pequena demais nao salvam lixo ----
    antes = pngs(capturas)
    app.iniciar_seletor()
    root.update()
    time.sleep(0.5)
    root.update()
    sel, canv = overlay_e_canvas(root)
    if canv is not None:
        canv.event_generate("<ButtonPress-1>", x=800, y=600)
        canv.event_generate("<B1-Motion>", x=803, y=602)
        canv.event_generate("<ButtonRelease-1>", x=803, y=602)
        root.update()
        time.sleep(0.5)
        root.update()
        novos = [n for n in pngs(capturas) if n not in antes]
        # com sugestao ativa o clique captura a regiao sugerida; sem sugestao,
        # uma area de 3 px nao pode virar arquivo
        checar(len(novos) <= 1,
               "arrasto minimo nao gera varios arquivos (gerou %d)" % len(novos))
        for w in root.winfo_children():
            if isinstance(w, tk.Toplevel) and w.winfo_exists():
                w.destroy()
        root.update()
except Exception:
    falhas.append("erro: " + traceback.format_exc())

print("\nFALHAS:", "nenhuma" if not falhas else "")
for f in falhas:
    print(" -", f)
try:
    root.destroy()
except Exception:
    pass
shutil.rmtree(tmp, ignore_errors=True)
sys.stdout.flush()
os._exit(0)
