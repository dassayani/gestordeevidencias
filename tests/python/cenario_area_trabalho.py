# -*- coding: utf-8 -*-
"""Area de trabalho: selecao, limpeza, tema, visualizacoes e o botao de captura.

Aciona o painel pelos mesmos metodos que os botoes chamam e confere o estado
real dos widgets — nao o estado interno apenas.
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
import win32gui
import capture_store
import config
import theme
from workspace import AppEvidencias

falhas = []


def checar(condicao, descricao):
    print(("OK:     " if condicao else "FALHOU: ") + descricao)
    if not condicao:
        falhas.append(descricao)


def celulas_posicionadas(app):
    """Itens da lista que estao realmente colocados na tela."""
    return sum(1 for w in app.frame_lista.winfo_children() if w.winfo_manager())


def textos(widget, achados=None):
    achados = [] if achados is None else achados
    for filho in widget.winfo_children():
        try:
            valor = str(filho.cget("text"))
            if valor:
                achados.append(valor)
        except Exception:
            pass
        textos(filho, achados)
    return achados


tmp = tempfile.mkdtemp(prefix="ge_area_")
capturas = os.path.join(tmp, "Capturas")
os.makedirs(capturas)
for i in range(4):
    Image.new("RGB", (400 + i * 40, 300), (50 + i * 30, 100, 150)).save(
        os.path.join(capturas, "print_10000%d.png" % i))

cfg = config.load(tmp)
cfg["pasta_capturas"] = capturas
config.save(tmp, cfg)

root = TkinterDnD.Tk()
app = AppEvidencias(root, capturas, os.path.join(tmp, "PDF"), RAIZ, tmp)
app.pausar_timer = True
root.deiconify()
root.update()

try:
    total = len(capture_store.list_captures(capturas))
    checar(total == 4, "as 4 capturas da pasta aparecem na lista (achou %d)" % total)

    # ---- selecionar tudo / limpar selecao ----
    app.selecionar_tudo()
    root.update()
    checar(len(app.arquivos_selecionados) == 4,
           "Selecionar tudo marca as 4 capturas")
    checar(any("4 capturas selecionadas" in t for t in textos(root)),
           "o rodape mostra '4 capturas selecionadas'")

    app.limpar_selecao()
    root.update()
    checar(len(app.arquivos_selecionados) == 0, "Limpar selecao desmarca tudo")
    checar(any("0 capturas selecionadas" in t for t in textos(root)),
           "o rodape volta para '0 capturas selecionadas'")

    # ---- modos de visualizacao ----
    for modo in ("detalhes", "blocos", "grade"):
        app._definir_modo_visualizacao(modo)
        root.update()
        for _ in range(6):          # da tempo do recolunamento acontecer
            root.update_idletasks()
            root.update()
            time.sleep(0.05)
        n = celulas_posicionadas(app)
        checar(app.modo_visualizacao == modo and n > 0,
               "visualizacao '%s' monta a lista (%d itens na tela)" % (modo, n))
        checar(config.load(tmp).get("modo_visualizacao") == modo,
               "a visualizacao '%s' fica gravada no config" % modo)

    # ---- modo claro <-> escuro, nas tres visualizacoes ----
    for modo in ("detalhes", "blocos", "grade"):
        app._definir_modo_visualizacao(modo)
        root.update()
        antes = celulas_posicionadas(app)
        escuro_antes = app.modo_escuro
        app.alternar_tema()
        for _ in range(8):
            root.update_idletasks()
            root.update()
            time.sleep(0.05)
        depois = celulas_posicionadas(app)
        checar(app.modo_escuro != escuro_antes, "o tema alterna em '%s'" % modo)
        checar(depois == antes and depois > 0,
               "trocar o tema em '%s' mantem os %d itens na tela (ficou %d)"
               % (modo, antes, depois))
        fundo = str(app.frame_lista.cget("bg")).lower()
        esperado = theme.get(app.modo_escuro)["bg_panel"].lower()
        checar(fundo == esperado,
               "a cor de fundo em '%s' acompanha o tema" % modo)
        app.alternar_tema()          # volta ao claro
        for _ in range(4):
            root.update_idletasks()
            root.update()

    # ---- botao de captura: abre o seletor cobrindo a tela ----
    app.iniciar_seletor()
    root.update()
    time.sleep(0.6)
    root.update()

    visiveis = []

    def visita(h, _):
        if win32gui.IsWindowVisible(h):
            visiveis.append(win32gui.GetWindowRect(h))

    win32gui.EnumWindows(visita, None)
    largura_tela = root.winfo_screenwidth()
    cobre = any((r[2] - r[0]) >= largura_tela * 0.9 for r in visiveis)
    checar(cobre, "o botao de captura abre o seletor cobrindo a tela")

    for w in root.winfo_children():
        if isinstance(w, tk.Toplevel):
            w.destroy()
    root.update()

    # ---- limpar dados: tudo vai para a Lixeira ----
    restantes_antes = len(os.listdir(capturas))
    import utils
    alvos = [os.path.join(capturas, f) for f in os.listdir(capturas)
             if os.path.isfile(os.path.join(capturas, f))]
    checar(utils.mover_para_lixeira(alvos), "limpar a pasta manda tudo para a Lixeira")
    app.atualizar_galeria()
    root.update()
    checar(len(os.listdir(capturas)) == 0,
           "a pasta fica vazia depois de limpar (tinha %d)" % restantes_antes)
    checar(any("Nenhuma captura encontrada" in t for t in textos(root)),
           "a lista vazia mostra o aviso de nenhuma captura")
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
