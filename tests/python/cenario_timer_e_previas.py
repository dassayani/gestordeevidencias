# -*- coding: utf-8 -*-
"""Timer de inatividade, janelas auxiliares e previas simultaneas.

Defeitos que passavam sem ninguem notar:
  * o editor gravava `pausar_timer` na raiz Tk, e nao no AppEvidencias que o
    timer le: a pausa durante o seletor de emoji e o de cor nao tinha efeito
  * o painel se escondia com o Montar documento (ou a previa) aberto, e o Tk nao
    mapeia Toplevel cuja raiz esta escondida: o trabalho sumia da tela
  * duas previas abertas disputavam o mesmo PDF temporario, e a segunda falhava
  * a previa nao acompanhava uma edicao, nem se recuperava de uma falha ao gerar

Cobre:
  * a pausa do timer durante o seletor de emoji e o de cor, e o editor sem `app`
  * o painel se esconde sozinho quando nao ha nada aberto, e so entao
  * com `pausar_timer` ligado nunca se esconde
  * previas simultaneas, cada uma com o proprio arquivo, e a limpeza ao fechar
  * regerar() recupera uma previa depois de uma falha na geracao
"""

import os as _os
import sys as _sys

RAIZ = _os.path.dirname(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
_sys.path.insert(0, RAIZ)
_os.chdir(RAIZ)

import os, sys, ctypes, tempfile, shutil, traceback
import tkinter as tk

if not ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4)):
    ctypes.windll.shcore.SetProcessDpiAwareness(2)

from tkinterdnd2 import TkinterDnD
from PIL import Image
from gestor.dados import config
from gestor.exportacao import pdf_export
from gestor.ui import document_builder, editor, export_preview
from gestor.ui.workspace import AppEvidencias

falhas = []
avisos = []
erros_tk = []


def checar(condicao, descricao):
    print(("OK:     " if condicao else "FALHOU: ") + descricao)
    if not condicao:
        falhas.append(descricao)


class DialogoFalso:
    @staticmethod
    def showerror(titulo, mensagem, **kw):
        avisos.append(("erro", titulo, mensagem))

    @staticmethod
    def showwarning(titulo, mensagem, **kw):
        avisos.append(("aviso", titulo, mensagem))

    @staticmethod
    def showinfo(titulo, mensagem, **kw):
        avisos.append(("info", titulo, mensagem))

    @staticmethod
    def askyesno(titulo, mensagem, **kw):
        avisos.append(("pergunta", titulo, mensagem))
        return True


editor.messagebox = DialogoFalso
document_builder.messagebox = DialogoFalso
export_preview.messagebox = DialogoFalso

tmp = tempfile.mkdtemp(prefix="ge_timer_")
capturas = os.path.join(tmp, "Capturas")
os.makedirs(capturas)
nomes = []
for i in range(3):
    nome = "print_60%04d.png" % i
    Image.new("RGB", (900, 560), (30 + i * 50, 100, 150)).save(os.path.join(capturas, nome))
    nomes.append(nome)
cfg = config.load(tmp)
cfg["pasta_capturas"] = capturas
config.save(tmp, cfg)

root = TkinterDnD.Tk()
root.report_callback_exception = lambda *a: erros_tk.append(a)
app = AppEvidencias(root, capturas, os.path.join(tmp, "PDF"), RAIZ, tmp)
app.pausar_timer = True
root.deiconify()
root.update()


def toplevels():
    return [w for w in root.winfo_children() if isinstance(w, tk.Toplevel)]


def tenta_esconder():
    """Dispara o esconder-por-inatividade como o timer faria."""
    app.pausar_timer = False
    root.deiconify()
    root.update()
    app._esconder_por_inatividade()
    root.update()
    escondeu = root.state() == "withdrawn"
    root.deiconify()
    root.update()
    app.pausar_timer = True
    return escondeu


try:
    # ---------------- pausa do timer no editor ----------------
    ed = app.abrir_editor(os.path.join(capturas, nomes[0]))
    ed.update()
    visto = {}

    original_cor = editor.colorchooser.askcolor
    editor.colorchooser.askcolor = lambda **kw: (visto.__setitem__("cor", app.pausar_timer)
                                                  or (None, None))
    app.pausar_timer = False
    try:
        ed.escolher_cor()
    finally:
        editor.colorchooser.askcolor = original_cor
    checar(visto.get("cor") is True,
           "o timer fica pausado enquanto o seletor de cor esta aberto")
    checar(app.pausar_timer is False, "e a pausa e desfeita quando ele fecha")

    class EmojiFalso:
        def __init__(self, *a, **kw):
            visto["emoji"] = app.pausar_timer

    original_emoji = editor.emoji_picker.SeletorEmoji
    editor.emoji_picker.SeletorEmoji = EmojiFalso
    try:
        ed._abrir_seletor_emoji()
    finally:
        editor.emoji_picker.SeletorEmoji = original_emoji
    checar(visto.get("emoji") is True,
           "o timer fica pausado enquanto o seletor de emoji esta aberto")
    checar(app.pausar_timer is False, "e a pausa e desfeita quando ele fecha")

    # a pausa nao pode ficar ligada se o seletor falhar
    class EmojiQuebrado:
        def __init__(self, *a, **kw):
            raise RuntimeError("falha ao abrir")

    editor.emoji_picker.SeletorEmoji = EmojiQuebrado
    try:
        try:
            ed._abrir_seletor_emoji()
        except RuntimeError:
            pass
    finally:
        editor.emoji_picker.SeletorEmoji = original_emoji
    checar(app.pausar_timer is False,
           "falha ao abrir o seletor nao deixa o timer pausado para sempre")
    app.pausar_timer = True
    ed.destroy()
    root.update()

    # editor aberto sem `app` (como era antes) nao quebra
    solto = editor.EditorImagem(root, os.path.join(capturas, nomes[1]), lambda: None, False)
    solto.update()
    editor.colorchooser.askcolor = lambda **kw: (None, None)
    try:
        solto.escolher_cor()
        sem_app = True
    except Exception:
        sem_app = False
    finally:
        editor.colorchooser.askcolor = original_cor
    checar(sem_app, "o editor sem `app` continua funcionando")
    solto.destroy()
    root.update()

    # ---------------- o painel e as janelas auxiliares ----------------
    checar(toplevels() == [], "pre-condicao: nenhuma janela auxiliar aberta")
    checar(tenta_esconder() is True,
           "sem nada aberto, o painel se esconde por inatividade")

    ed = app.abrir_editor(os.path.join(capturas, nomes[0]))
    ed.update()
    checar(tenta_esconder() is False, "com o editor aberto o painel nao se esconde")
    ed.destroy()
    root.update()

    janela = document_builder.MontarDocumento(app, nomes)
    janela.update()
    root.update()
    checar(tenta_esconder() is False, "com o Montar documento aberto o painel nao se esconde")

    janela._pre_visualizar()
    root.update()
    previa_a = next(w for w in toplevels() if isinstance(w, export_preview.PreVisualizarExportar))
    checar(tenta_esconder() is False, "com a previa aberta o painel nao se esconde")

    # ---------------- duas previas ao mesmo tempo ----------------
    janela._pre_visualizar()
    root.update()
    previas = [w for w in toplevels() if isinstance(w, export_preview.PreVisualizarExportar)]
    checar(len(previas) == 2, "duas previas abertas ao mesmo tempo")
    previa_b = next(p for p in previas if p is not previa_a)
    checar(all(p._documento is not None for p in previas),
           "as duas geraram o documento (a segunda nao falhou por causa da primeira)")
    checar(not any(getattr(p, "_erro_previa", "") for p in previas),
           "nenhuma das duas mostra erro")
    checar(previa_a._arquivo_previa != previa_b._arquivo_previa,
           "cada previa usa o seu proprio arquivo temporario")
    arquivo_a, arquivo_b = previa_a._arquivo_previa, previa_b._arquivo_previa
    previa_a.regerar()
    previa_b.regerar()
    checar(previa_a._documento is not None and previa_b._documento is not None,
           "as duas sobrevivem a regerar")

    previa_a.fechar()
    root.update()
    checar(not os.path.exists(arquivo_a), "fechar uma previa apaga o arquivo temporario dela")
    checar(os.path.exists(arquivo_b) and previa_b._documento is not None
           and previa_b.imagem_da_pagina(0) is not None,
           "e nao mexe no da outra")

    # ---------------- previa que falha ao gerar e se recupera ----------------
    exportar_original = pdf_export.exportar

    def exportar_falha(*a, **kw):
        raise RuntimeError("imagem ilegivel")

    pdf_export.exportar = exportar_falha
    try:
        previa_b.regerar()
    finally:
        pdf_export.exportar = exportar_original
    root.update()
    textos = [w.cget("text") for w in previa_b.moldura.winfo_children()
              if w.winfo_class() == "Label"]
    checar(previa_b._documento is None and any("imagem ilegivel" in str(t) for t in textos),
           "falha ao regerar mostra o motivo na propria previa")
    checar(bool(previa_b.winfo_exists()) and bool(previa_b.btn_exportar.winfo_exists()),
           "e a previa segue de pe, com a exportacao disponivel")
    previa_b.regerar()
    root.update()
    checar(previa_b._documento is not None and not previa_b._erro_previa,
           "passada a falha, regerar() recupera a previa")
    previa_b.fechar()
    root.update()
    checar(not os.path.exists(arquivo_b), "e fechar tambem limpa o arquivo dela")

    # ---------------- pausar_timer ligado: nunca esconde ----------------
    janela.destroy()
    root.update()
    app.pausar_timer = True
    root.deiconify()
    app._esconder_por_inatividade()
    root.update()
    checar(root.state() != "withdrawn", "com pausar_timer ligado o painel nunca se esconde")

    checar(not [a for a in avisos if a[0] == "erro"], "nenhuma mensagem de erro")
    checar(not erros_tk, "nenhum erro silencioso do Tk")
    for e in erros_tk:
        print("   erro Tk:", "".join(traceback.format_exception(*e))[-500:])
except Exception:
    falhas.append("erro: " + traceback.format_exc())

print("\nFALHAS:", "nenhuma" if not falhas else "")
for f in falhas:
    print(" -", f)
try:
    try:
        app.icon.stop()
    except Exception:
        pass
    root.destroy()
except Exception:
    pass
shutil.rmtree(tmp, ignore_errors=True)
sys.stdout.flush()
os._exit(1 if falhas else 0)
