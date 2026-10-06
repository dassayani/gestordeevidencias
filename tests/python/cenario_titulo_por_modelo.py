# -*- coding: utf-8 -*-
"""Montar documento: o titulo da capa acompanha o modelo escolhido.

Troca de modelo pelo mesmo caminho da tela (`_linha_modelo` -> `selecionar`) e
confere que:
  * o titulo inicial e o do modelo Passo a passo e a lista traz os nomes novos
  * o titulo padrao acompanha cada modelo
  * um titulo digitado a mao NAO e sobrescrito ao trocar de modelo
  * mover (reordena sem refazer a coluna central) e remover (refaz) nao perdem
    nem revertem o titulo, e nao trocam o modelo por tras do usuario
A regra em si e testada sem janela em test_titulo_por_modelo.
"""

import os as _os
import sys as _sys

# Raiz do projeto a partir deste arquivo: tests/python/x.py -> duas pastas acima
RAIZ = _os.path.dirname(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
_sys.path.insert(0, RAIZ)
_os.chdir(RAIZ)

import os, sys, ctypes, tempfile, shutil, traceback

if not ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4)):
    ctypes.windll.shcore.SetProcessDpiAwareness(2)

from tkinterdnd2 import TkinterDnD
from PIL import Image
from gestor.dados import config
from gestor.ui import document_builder
from gestor.ui import export_preview
from gestor.ui.workspace import AppEvidencias

falhas = []
avisos = []


def checar(condicao, descricao):
    print(("OK:     " if condicao else "FALHOU: ") + descricao)
    if not condicao:
        falhas.append(descricao)


class DialogoFalso:
    """Substitui o messagebox: guarda o que seria mostrado, sem travar."""

    @staticmethod
    def showinfo(titulo, mensagem, **kw):
        avisos.append(("info", titulo, mensagem))

    @staticmethod
    def showerror(titulo, mensagem, **kw):
        avisos.append(("erro", titulo, mensagem))

    @staticmethod
    def showwarning(titulo, mensagem, **kw):
        avisos.append(("aviso", titulo, mensagem))

    @staticmethod
    def askyesno(titulo, mensagem, **kw):
        avisos.append(("pergunta", titulo, mensagem))
        return True


export_preview.messagebox = DialogoFalso
document_builder.messagebox = DialogoFalso
export_preview.os.startfile = lambda caminho: avisos.append(("pasta", caminho, ""))

PADRAO = document_builder.TITULOS_PADRAO

tmp = tempfile.mkdtemp(prefix="ge_titulo_")
capturas = os.path.join(tmp, "Capturas")
os.makedirs(capturas)
nomes = []
for i in range(3):
    nome = "print_40000%d.png" % i
    Image.new("RGB", (900, 560), (40 + i * 50, 100, 150)).save(os.path.join(capturas, nome))
    nomes.append(nome)

cfg = config.load(tmp)
cfg["pasta_capturas"] = capturas
config.save(tmp, cfg)

root = TkinterDnD.Tk()
app = AppEvidencias(root, capturas, os.path.join(tmp, "PDF"), RAIZ, tmp)
app.pausar_timer = True
root.deiconify()
root.update()


def titulo(janela):
    return janela.entries_capa["titulo"].get()


def escolher(janela, modelo):
    """Clica na linha do modelo: dispara o mesmo `selecionar` da tela."""
    linha = janela._card_modelo_widgets[modelo][0]
    linha.event_generate("<Button-1>")
    janela.update()


try:
    janela = document_builder.MontarDocumento(app, nomes)
    janela.update()

    checar([n for _, n, _ in document_builder.MODELOS_UI]
           == ["Passo a passo", "Ficha", "Relatório"],
           "a lista de modelos mostra Passo a passo, Ficha e Relatório")
    checar(janela.var_modelo.get() == "passo", "o modelo inicial e o passo a passo")
    checar(titulo(janela) == PADRAO["passo"],
           "o titulo inicial e o do passo a passo (%r)" % titulo(janela))

    # ---- o padrao acompanha o modelo ----
    for modelo in ("ficha", "qa", "passo"):
        escolher(janela, modelo)
        checar(janela.var_modelo.get() == modelo, "o modelo %s foi escolhido" % modelo)
        checar(titulo(janela) == PADRAO[modelo],
               "o titulo acompanha o modelo %s (%r)" % (modelo, titulo(janela)))

    # ---- o padrao sobrevive a reconstrucao da coluna central ----
    escolher(janela, "ficha")
    janela._atualizar_coluna_central()
    janela.update()
    checar(titulo(janela) == PADRAO["ficha"],
           "refazer a coluna central mantem o titulo padrao da Ficha")
    escolher(janela, "qa")
    checar(titulo(janela) == PADRAO["qa"],
           "depois de refazer a coluna, trocar de modelo ainda acompanha")
    checar(janela.var_modelo.get() == "qa", "refazer a coluna nao trocou o modelo")

    # ---- titulo digitado a mao nao e sobrescrito ----
    entry = janela.entries_capa["titulo"]
    entry.delete(0, "end")
    entry.insert(0, "Fechamento de setembro")
    for modelo in ("passo", "ficha", "qa"):
        escolher(janela, modelo)
        checar(titulo(janela) == "Fechamento de setembro",
               "o titulo digitado fica ao escolher %s (%r)" % (modelo, titulo(janela)))

    # ---- mover (sem refazer a coluna) e remover (refazendo) ----
    janela._mover(0, 1)
    janela.update()
    checar(titulo(janela) == "Fechamento de setembro",
           "mover um passo nao perde o titulo digitado")
    checar(janela.var_modelo.get() == "qa", "mover um passo nao trocou o modelo")

    janela._remover(2)
    janela.update()
    checar(len(janela.passos) == 2, "o passo foi removido")
    checar(titulo(janela) == "Fechamento de setembro",
           "remover um passo nao perde o titulo digitado")
    checar(janela.var_modelo.get() == "qa", "remover um passo nao trocou o modelo")

    # com o titulo ainda padrao, as mesmas operacoes tambem o preservam
    entry = janela.entries_capa["titulo"]
    entry.delete(0, "end")
    entry.insert(0, PADRAO["qa"])
    janela._mover(0, 1)
    janela.update()
    checar(titulo(janela) == PADRAO["qa"],
           "mover um passo mantem o titulo padrao do modelo")
    janela._remover(1)
    janela.update()
    checar(titulo(janela) == PADRAO["qa"],
           "remover um passo mantem o titulo padrao do modelo")
    escolher(janela, "ficha")
    checar(titulo(janela) == PADRAO["ficha"],
           "o titulo padrao, depois de mover e remover, ainda acompanha o modelo")

    # ---- vazio de proposito ----
    entry = janela.entries_capa["titulo"]
    entry.delete(0, "end")
    escolher(janela, "qa")
    checar(titulo(janela) == "", "titulo apagado de proposito continua vazio ao trocar")
    janela._atualizar_coluna_central()
    janela.update()
    checar(titulo(janela) == "", "titulo apagado continua vazio depois de refazer a coluna")

    # ---- a previa mostra o nome novo do modelo e o titulo da capa ----
    # O campo ja esta vazio (apagado de proposito acima): escreve-se o padrao do
    # modelo a cada volta, como faria quem comeca de novo.
    for modelo, nome_esperado in (("passo", "Passo a passo"), ("ficha", "Ficha"),
                                  ("qa", "Relatório")):
        escolher(janela, modelo)
        campo = janela.entries_capa["titulo"]       # a coluna pode ter sido refeita
        campo.delete(0, "end")
        campo.insert(0, PADRAO[modelo])
        janela._pre_visualizar()
        root.update()
        previa = next((w for w in root.winfo_children()
                       if isinstance(w, export_preview.PreVisualizarExportar)), None)
        checar(previa is not None, "[%s] a previa abriu" % modelo)
        if previa is None:
            continue
        texto = previa.lbl_pagina.cget("text")
        checar(texto.endswith("modelo: " + nome_esperado),
               "[%s] a previa diz 'modelo: %s' (%r)" % (modelo, nome_esperado, texto))
        checar(previa.capa.get("titulo") == PADRAO[modelo],
               "[%s] a previa recebeu o titulo padrao do modelo" % modelo)
        previa.fechar()
        root.update()

    checar(not [a for a in avisos if a[0] == "erro"], "nenhuma mensagem de erro")
    janela.destroy()
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
os._exit(1 if falhas else 0)
