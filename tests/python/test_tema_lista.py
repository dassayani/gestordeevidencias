# -*- coding: utf-8 -*-
"""Reproduz: ao trocar o tema, a lista de capturas fica vazia.

Conta quantas celulas ficaram realmente posicionadas (grid/pack) depois da
troca, nas tres visualizacoes.
"""

import os as _os
import sys as _sys

# Raiz do projeto a partir deste arquivo: tests/python/x.py -> duas pastas acima
RAIZ = _os.path.dirname(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
_sys.path.insert(0, RAIZ)
_os.chdir(RAIZ)
SAIDA = _os.path.join(RAIZ, "tests", "_saida")
_os.makedirs(SAIDA, exist_ok=True)

import os, sys, ctypes, tempfile, shutil, traceback

if not ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4)):
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
from tkinterdnd2 import TkinterDnD
from PIL import Image
from gestor.dados import config
from gestor.ui.workspace import AppEvidencias

tmp = tempfile.mkdtemp(prefix="ge_tema_")
capturas = os.path.join(tmp, "Capturas")
os.makedirs(capturas)
for i in range(5):
    Image.new("RGB", (400, 260), (30 + i * 20, 80, 120)).save(
        os.path.join(capturas, "print_10000%d.png" % i))

cfg = config.load(tmp)
cfg["pasta_capturas"] = capturas
config.save(tmp, cfg)

falhas = []
root = TkinterDnD.Tk()
app = AppEvidencias(root, capturas, os.path.join(tmp, "PDF"), RAIZ, tmp)
app.pausar_timer = True
app.tempo_limite = 10 ** 9
root.deiconify()
root.update()


def visiveis():
    """Celulas com geometria aplicada dentro do frame da lista."""
    n = 0
    for w in app.frame_lista.winfo_children():
        if w.winfo_manager():            # "grid", "pack" ou "" se nao posicionado
            n += 1
    return n


try:
    for modo in ("detalhes", "blocos", "grade"):
        app.modo_visualizacao = modo
        app._colunas_grade = 0
        app.atualizar_galeria()
        root.update()
        antes = visiveis()

        app.alternar_tema()          # é o que o usuário faz: clica na lua
        root.update()
        depois_imediato = visiveis()

        # dá ao Tk a chance de mapear os widgets, como acontece na prática
        for _ in range(5):
            root.update()
            root.update_idletasks()
        depois_ocioso = visiveis()

        print("%-9s antes=%d  logo apos a troca=%d  apos ocioso=%d"
              % (modo, antes, depois_imediato, depois_ocioso))
        if antes and depois_ocioso == 0:
            falhas.append("%s: a lista ficou vazia depois de trocar o tema" % modo)

        # o que devolve as imagens hoje: clicar num filtro
        app._ao_trocar_filtro("tudo") if hasattr(app, "_ao_trocar_filtro") else None
        root.update()
        print("          depois de clicar no filtro=%d" % visiveis())
        app.alternar_tema()          # volta ao tema claro para o proximo modo
        root.update()
except Exception:
    falhas.append("erro: " + traceback.format_exc())

print("\nFALHAS:", "nenhuma" if not falhas else "")
for f in falhas:
    print(" -", f)
try:
    try:
        # A bandeja roda numa thread com laco de mensagens nativo. Parar antes de
        # encerrar evita derrubar o processo na saida.
        app.icon.stop()
    except Exception:
        pass
    root.destroy()
except Exception:
    pass
shutil.rmtree(tmp, ignore_errors=True)
sys.stdout.flush()
os._exit(0)
