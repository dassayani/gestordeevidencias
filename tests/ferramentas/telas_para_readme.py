# -*- coding: utf-8 -*-
"""Gera as imagens das telas usadas no README, em docs/images.

Usa uma pasta de capturas temporaria com imagens sinteticas de proposito: as
capturas reais da maquina podem conter dado de cliente, e o README vai para o
repositorio.
"""

import os as _os
import sys as _sys

# Raiz do projeto a partir deste arquivo: tests/ferramentas/x.py -> duas pastas acima
RAIZ = _os.path.dirname(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
_sys.path.insert(0, RAIZ)
_os.chdir(RAIZ)

import os, sys, ctypes, tempfile, shutil, traceback, time

if not ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4)):
    ctypes.windll.shcore.SetProcessDpiAwareness(2)

import tkinter as tk
from tkinterdnd2 import TkinterDnD
from PIL import Image, ImageDraw, ImageGrab
from gestor.dados import capture_store
from gestor.dados import config
from gestor.ui import configuracoes
from gestor.ui import document_builder
from gestor.ui.workspace import AppEvidencias

DESTINO = os.path.join(RAIZ, "docs", "images")
os.makedirs(DESTINO, exist_ok=True)


def captura_sintetica(caminho, titulo, cor):
    """Uma 'tela de sistema' inventada, para ilustrar sem expor dado real."""
    img = Image.new("RGB", (1200, 760), (248, 250, 252))
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, 1199, 70], fill=cor)
    d.text((28, 30), titulo, fill=(255, 255, 255))
    for i in range(6):
        y = 110 + i * 100
        d.rectangle([40, y, 1160, y + 70], outline=(206, 214, 222), width=2)
        d.text((60, y + 30), "campo %d" % (i + 1), fill=(110, 125, 140))
    d.rectangle([900, 690, 1160, 740], fill=cor)
    d.text((960, 710), "Confirmar", fill=(255, 255, 255))
    img.save(caminho)


def foto(janela, nome):
    janela.attributes("-topmost", True)
    janela.lift()
    janela.update_idletasks()
    janela.update()
    time.sleep(0.5)
    janela.update()
    x, y = janela.winfo_rootx(), janela.winfo_rooty()
    w, h = janela.winfo_width(), janela.winfo_height()
    if w < 50 or h < 50:
        print("  janela pequena demais para %s (%dx%d)" % (nome, w, h))
        return
    caminho = os.path.join(DESTINO, nome)
    ImageGrab.grab(bbox=(x, y, x + w, y + h)).save(caminho)
    janela.attributes("-topmost", False)
    print("  gerado:", caminho)


tmp = tempfile.mkdtemp(prefix="ge_readme_")
capturas = os.path.join(tmp, "Capturas")
os.makedirs(capturas)
amostras = [("Tela de login do sistema", (11, 114, 133)),
            ("Cadastro de competencia", (232, 89, 12)),
            ("Confirmacao do fechamento", (12, 133, 90))]
for i, (titulo, cor) in enumerate(amostras):
    caminho = os.path.join(capturas, "print_15%02d00.png" % i)
    captura_sintetica(caminho, titulo, cor)
    capture_store.save_meta(caminho, {"caption": titulo, "caso": "CT-100%d" % i,
                                      "shapes": []})

cfg = config.load(tmp)
cfg["pasta_capturas"] = capturas
cfg["modo_visualizacao"] = "blocos"
config.save(tmp, cfg)

root = TkinterDnD.Tk()
app = AppEvidencias(root, capturas, os.path.join(tmp, "PDF"), RAIZ, tmp)
app.pausar_timer = True
root.deiconify()
root.update()

try:
    foto(root, "painel.png")

    itens = capture_store.list_captures(capturas)
    ed = app.abrir_editor(itens[0]["path"])
    ed.update()
    time.sleep(0.4)
    foto(ed, "editor.png")
    ed.destroy()
    root.update()

    nomes = [i["name"] for i in itens]
    doc = document_builder.MontarDocumento(app, nomes)
    doc.update()
    time.sleep(0.4)
    foto(doc, "documento.png")
    doc.destroy()
    root.update()

    configuracoes.abrir(app)
    root.update()
    for w in root.winfo_children():
        if isinstance(w, tk.Toplevel) and "Configura" in w.title():
            time.sleep(0.3)
            foto(w, "configuracoes.png")
            w.destroy()
    root.update()
except Exception:
    traceback.print_exc()

try:
    root.destroy()
except Exception:
    pass
shutil.rmtree(tmp, ignore_errors=True)
sys.stdout.flush()
os._exit(0)
