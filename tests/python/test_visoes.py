# -*- coding: utf-8 -*-
"""Os tres modos montam, selecionam, recolunam e persistem a escolha."""

import os as _os
import sys as _sys

# Raiz do projeto a partir deste arquivo: tests/python/x.py -> duas pastas acima
RAIZ = _os.path.dirname(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
_sys.path.insert(0, RAIZ)
_os.chdir(RAIZ)
SAIDA = _os.path.join(RAIZ, "tests", "_saida")
_os.makedirs(SAIDA, exist_ok=True)

import ctypes, traceback
if not ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4)):
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
from tkinterdnd2 import TkinterDnD
import main as m, workspace, config

falhas, erros = [], []
root = TkinterDnD.Tk()
root.report_callback_exception = lambda *a: erros.append("".join(traceback.format_exception(*a)))
app = workspace.AppEvidencias(root, m.PASTA_CAPTURAS, m.PASTA_PDFS, m.BASE_DIR, m.DATA_DIR)
modo_original = app.modo_visualizacao
root.deiconify(); root.geometry("460x820"); root.update()

def celulas_visiveis():
    return [w for w in app.frame_lista.winfo_children() if w.winfo_manager()]

for modo in ("detalhes", "blocos", "grade"):
    app._definir_modo_visualizacao(modo)
    root.update_idletasks(); root.update()
    n_cards = len(app.cards)
    gerenciador = {w.winfo_manager() for w in celulas_visiveis()}
    print(f"\n[{modo}] cards={n_cards}  colunas={app._colunas_grade}  layout={gerenciador}")
    if n_cards == 0:
        falhas.append(f"{modo}: nenhum card montado")
    esperado = "pack" if modo == "detalhes" else "grid"
    if gerenciador and esperado not in gerenciador:
        falhas.append(f"{modo}: esperava layout {esperado}, veio {gerenciador}")
    if modo != "detalhes" and app._colunas_grade < 1:
        falhas.append(f"{modo}: colunas invalidas")

    # selecao continua funcionando neste modo
    algum = next(iter(app.cards))
    antes = algum in app.arquivos_selecionados
    app._alternar_selecao(algum)
    root.update()
    if (algum in app.arquivos_selecionados) == antes:
        falhas.append(f"{modo}: clicar nao alterou a selecao")
    app._alternar_selecao(algum)
    root.update()

    # a escolha foi gravada
    if config.load(m.DATA_DIR).get("modo_visualizacao") != modo:
        falhas.append(f"{modo}: nao persistiu na configuracao")

# recolunamento ao estreitar/alargar
app._definir_modo_visualizacao("grade")
root.update_idletasks(); root.update()
larguras = {}
for larg in (460, 700, 980):
    root.geometry(f"{larg}x820")
    root.update_idletasks(); root.update()
    larguras[larg] = app._colunas_grade
print("\ncolunas por largura (grade):", larguras)
if not (larguras[460] < larguras[700] < larguras[980]):
    falhas.append(f"a grade nao recolunou ao alargar: {larguras}")

app._definir_modo_visualizacao("blocos")
root.update_idletasks(); root.update()
lb = {}
for larg in (460, 980):
    root.geometry(f"{larg}x820")
    root.update_idletasks(); root.update()
    lb[larg] = app._colunas_grade
print("colunas por largura (blocos):", lb)
if lb[460] >= lb[980]:
    falhas.append(f"blocos nao recolunou: {lb}")

# devolve o modo original
app._definir_modo_visualizacao(modo_original)
root.update()
if erros:
    falhas.append("excecoes engolidas pelo Tk:\n" + "\n".join(erros))
print("\nFALHAS:", "nenhuma" if not falhas else "")
for f in falhas:
    print(" -", f)
root.destroy()
