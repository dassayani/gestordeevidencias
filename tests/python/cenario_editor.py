# -*- coding: utf-8 -*-
"""Editor: desenhar com cada ferramenta, apagar, legendar e gravar.

Desenha acionando os mesmos tratadores que o mouse dispara (on_press, on_drag,
on_release), para o caminho exercitado ser o do usuario e nao um atalho interno.
Depois fecha e reabre o editor para conferir que o que foi gravado voltou.
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
from gestor.dados import capture_store
from gestor.dados import config
from gestor.ui.workspace import AppEvidencias

falhas = []
erros_tk = []


def checar(condicao, descricao):
    print(("OK:     " if condicao else "FALHOU: ") + descricao)
    if not condicao:
        falhas.append(descricao)


class Evento:
    """O minimo que os tratadores do canvas leem de um evento de mouse."""

    def __init__(self, x, y):
        self.x = x
        self.y = y
        self.state = 0
        self.num = 1


def desenhar(ed, ferramenta, x1, y1, x2, y2):
    """Um traco completo: seleciona a ferramenta, pressiona, arrasta e solta."""
    ed._selecionar_ferramenta(ferramenta)
    ed.update()
    ed.on_press(Evento(x1, y1))
    passos = 5
    for i in range(1, passos + 1):
        ed.on_drag(Evento(x1 + (x2 - x1) * i // passos,
                          y1 + (y2 - y1) * i // passos))
    ed.on_release(Evento(x2, y2))
    ed.update()


tmp = tempfile.mkdtemp(prefix="ge_editor_")
capturas = os.path.join(tmp, "Capturas")
os.makedirs(capturas)
alvo = os.path.join(capturas, "print_100000.png")
Image.new("RGB", (900, 600), (245, 248, 250)).save(alvo)

cfg = config.load(tmp)
cfg["pasta_capturas"] = capturas
config.save(tmp, cfg)

root = TkinterDnD.Tk()
root.report_callback_exception = lambda *a: erros_tk.append(
    "".join(traceback.format_exception(*a)))
app = AppEvidencias(root, capturas, os.path.join(tmp, "PDF"), RAIZ, tmp)
app.pausar_timer = True
root.deiconify()
root.update()

LEGENDA = "Tela de confirmacao do fechamento"
CASO = "CT-9090"

try:
    ed = app.abrir_editor(alvo)
    ed.update()
    checar(ed is not None, "o editor abriu")
    checar(hasattr(ed, "txt_legenda") and hasattr(ed, "entry_caso"),
           "os campos de legenda e caso existem")

    # ---- desenhar com cada ferramenta de forma ----
    formas = [("seta", 120, 120, 300, 220),
              ("retangulo", 150, 260, 380, 380),
              ("elipse", 420, 120, 600, 260),
              ("marcador", 120, 420, 420, 430),
              ("passo", 650, 150, 650, 150),
              ("borrao", 480, 320, 640, 400)]
    for ferramenta, x1, y1, x2, y2 in formas:
        antes = len(ed.shapes)
        desenhar(ed, ferramenta, x1, y1, x2, y2)
        checar(len(ed.shapes) == antes + 1,
               "a ferramenta '%s' criou uma anotacao" % ferramenta)

    tipos = [s.get("tool") for s in ed.shapes]
    print("        anotacoes na tela:", tipos)

    # ---- legenda e caso ----
    ed.txt_legenda.delete("1.0", "end")
    ed.txt_legenda.insert("1.0", LEGENDA)
    ed.entry_caso.delete(0, "end")
    ed.entry_caso.insert(0, CASO)
    ed.update()

    # ---- so gravar: a janela continua aberta ----
    ed.gravar()
    ed.update()
    checar(bool(ed.winfo_exists()), "'Gravar' mantem o editor aberto")
    checar(ed.sujo is False, "depois de gravar, o editor fica marcado como gravado")

    meta = capture_store.load_meta(alvo)
    checar(meta.get("caption") == LEGENDA, "a legenda foi gravada")
    checar(meta.get("caso") == CASO, "o caso/projeto foi gravado")
    gravadas = len(meta.get("shapes", []))
    checar(gravadas == len(formas),
           "as %d anotacoes foram gravadas (gravou %d)" % (len(formas), gravadas))

    # ---- apagar uma anotacao ----
    ed._selecionar_ferramenta("mover")
    ed.update()
    ed.selected_id = ed.shapes[-1]["id"]
    antes = len(ed.shapes)
    ed._apagar_selecionado_tecla()
    ed.update()
    checar(len(ed.shapes) == antes - 1, "apagar remove a anotacao selecionada")

    # ---- gravar e fechar ----
    ed.gravar_e_fechar()
    root.update()
    checar(not ed.winfo_exists(), "'Gravar e fechar' fecha o editor")

    meta2 = capture_store.load_meta(alvo)
    checar(len(meta2.get("shapes", [])) == len(formas) - 1,
           "a exclusao foi gravada junto")

    # ---- reabrir: o que foi gravado esta la ----
    ed2 = app.abrir_editor(alvo)
    ed2.update()
    checar(ed2.txt_legenda.get("1.0", "end").strip() == LEGENDA,
           "ao reabrir, a legenda voltou")
    checar(ed2.entry_caso.get().strip() == CASO,
           "ao reabrir, o caso/projeto voltou")
    checar(len(ed2.shapes) == len(formas) - 1,
           "ao reabrir, as anotacoes voltaram")
    # abrir um print ja legendado nao pode nascer como "nao gravado", senao
    # fechar sempre pergunta se e pra sair sem gravar
    checar(ed2.sujo is False,
           "reabrir um print legendado nao marca alteracao pendente")

    # ---- fechar sem ter mexido: nao pode perguntar nada ----
    ed2.fechar_e_voltar()
    root.update()
    checar(not ed2.winfo_exists(), "fechar volta para o painel")

    checar(not erros_tk, "nenhum erro silencioso do Tk durante a edicao")
    if erros_tk:
        print(erros_tk[0][:600])
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
