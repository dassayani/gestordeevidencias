# -*- coding: utf-8 -*-
"""Editar a imagem a partir do Montar documento (duplo clique na miniatura).

Percorre o caminho do usuario: monta um documento com varias capturas, digita
legenda sem gravar, abre o editor de um passo, anota e recorta, grava e fecha,
e confere que o documento voltou com tudo persistido: imagem nova na miniatura,
legenda, capa, ordem, rolagem e a previa que estava aberta.

Cobre tambem os caminhos de falha: fechar sem gravar, editor destruido a forca
(o Montar nao pode ficar travado), arquivo que sumiu e o painel que nao pode se
esconder com o Montar aberto.

As caixas de dialogo sao substituidas: modal sem ninguem para clicar trava o
processo.
"""

import os as _os
import sys as _sys

# Raiz do projeto a partir deste arquivo: tests/python/x.py -> duas pastas acima
RAIZ = _os.path.dirname(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
_sys.path.insert(0, RAIZ)
_os.chdir(RAIZ)

import os, sys, ctypes, tempfile, shutil, traceback, hashlib

if not ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4)):
    ctypes.windll.shcore.SetProcessDpiAwareness(2)

from tkinterdnd2 import TkinterDnD
from PIL import Image
from gestor.dados import capture_store, config
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


document_builder.messagebox = DialogoFalso
editor.messagebox = DialogoFalso
export_preview.messagebox = DialogoFalso

N = 14   # o bastante para a coluna central rolar em qualquer tela
tmp = tempfile.mkdtemp(prefix="ge_edit_")
capturas = os.path.join(tmp, "Capturas")
os.makedirs(capturas)
nomes = []
for i in range(N):
    nome = "print_40%04d.png" % i
    Image.new("RGB", (900, 560), (20 + i * 15, 100, 150)).save(os.path.join(capturas, nome))
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

# O editor nao pode trazer o painel principal de volta: conta as chamadas.
chamadas_raiz = []
_deiconify_original = root.deiconify
root.deiconify = lambda: (chamadas_raiz.append(1), _deiconify_original())[1]


galeria = []
_galeria_original = app.atualizar_galeria
app.atualizar_galeria = lambda *a, **k: (galeria.append(1), _galeria_original(*a, **k))[1]


def hash_arquivo(caminho):
    with open(caminho, "rb") as f:
        return hashlib.md5(f.read()).hexdigest()


def editores_abertos():
    return [w for w in root.winfo_children() + janela.winfo_children()
            if isinstance(w, editor.EditorImagem)]


def desbloqueado(j):
    return not int(j.attributes("-disabled"))


try:
    janela = document_builder.MontarDocumento(app, nomes)
    janela.update()
    checar(len(janela.passos) == N, "os %d prints entraram no documento" % N)

    # ---- estado digitado antes de editar: capa e legendas sem gravar ----
    janela.entries_capa["titulo"].delete(0, "end")
    janela.entries_capa["titulo"].insert(0, "Titulo do teste")
    LEG_ZERO = "Legenda do passo zero"
    LEG_ALVO = "Legenda digitada no Montar"
    ALVO = 9
    def digitar_legenda(idx, texto):
        caixa = janela.entries_legenda[idx]
        caixa.delete("1.0", "end")
        caixa.insert("1.0", texto)
        janela._on_legenda_change(idx, caixa)

    digitar_legenda(0, LEG_ZERO)
    janela.update()

    passo_alvo = janela.passos[ALVO]
    caminho_alvo = passo_alvo["caminho"]
    nome_alvo = passo_alvo["nome"]
    ordem_antes = [p["nome"] for p in janela.passos]
    png_antes = hash_arquivo(caminho_alvo)
    altura_antes = janela.imagens_passos[ALVO].height()

    # ---- rolagem: so da pra conferir se a coluna realmente rola ----
    janela._canvas_central.yview_moveto(0.6)
    janela.update()
    rola = janela._canvas_central.yview()[1] < 1.0
    pos_central = janela._canvas_central.yview()[0]
    checar(rola, "a coluna central rola com %d passos" % N)

    # ---- previa aberta ANTES da edicao ----
    janela._pre_visualizar()
    root.update()
    previa = next((w for w in root.winfo_children()
                   if isinstance(w, export_preview.PreVisualizarExportar)), None)
    checar(previa is not None, "a previa abriu")
    checar(len(janela._previas) == 1, "o Montar guardou a referencia da previa")

    meta_zero = capture_store.load_meta(janela.passos[0]["caminho"])
    checar(meta_zero.get("caption") == LEG_ZERO,
           "a legenda digitada foi gravada no .json de um passo que nao foi editado")
    checar(not meta_zero.get("edited_at"),
           "gravar so a legenda nao marca a captura como editada")

    def assinatura_previa():
        return [hashlib.md5(previa.imagem_da_pagina(i).tobytes()).hexdigest()
                for i in range(previa.total_paginas)]

    paginas_antes = assinatura_previa()

    # Legenda digitada DEPOIS da previa: o disco ainda tem a antiga, que e o
    # caso em que o editor precisa preferir a do Montar.
    digitar_legenda(ALVO, LEG_ALVO)
    janela.update()
    checar(capture_store.load_meta(caminho_alvo).get("caption", "") != LEG_ALVO,
           "pre-condicao: a legenda nova ainda nao esta no disco")

    # ---- duplo clique: abre o editor do passo ----
    janela._editar_passo(ALVO)
    janela.update()
    ed = janela._editor
    checar(ed is not None and bool(ed.winfo_exists()), "o editor abriu")
    checar(isinstance(ed, editor.EditorImagem), "e o editor de imagem")
    checar(bool(ed.winfo_ismapped()), "o editor esta visivel na tela")
    checar(ed.txt_legenda.get("1.0", "end").strip() == LEG_ALVO,
           "o editor abre com a legenda digitada no Montar, nao a do disco")
    checar(ed.sujo is True,
           "legenda ainda nao gravada abre como alteracao pendente")
    checar(not desbloqueado(janela), "o Montar fica bloqueado enquanto edita")

    # ---- um editor por vez ----
    janela._editar_passo(0)
    janela.update()
    checar(janela._editor is ed and len(editores_abertos()) == 1,
           "pedir outra edicao nao abre um segundo editor")

    # O <Destroy> do editor tambem dispara para cada widget filho dele. A lista
    # de camadas se reconstrói o tempo todo; isso nao pode liberar o Montar.
    ed._atualizar_lista_camadas()
    janela.update()
    checar(not desbloqueado(janela) and janela._editor is ed,
           "destruir widgets internos do editor nao libera o Montar no meio da edicao")

    # ---- anotar, recortar e gravar ----
    ed.shapes.append({"id": 1, "tool": "retangulo", "coords": [150, 150, 400, 300],
                      "color": "#E8590C", "width": 4, "dash": False, "visible": True})
    ed._marcar_sujo()
    ed._aplicar_recorte([100, 100, 600, 400])
    # A legenda tambem muda dentro do editor: o disco passa a ser a verdade, e o
    # Montar tem de acompanha-la ao voltar.
    LEG_FINAL = "Legenda ajustada dentro do editor"
    ed.txt_legenda.delete("1.0", "end")
    ed.txt_legenda.insert("1.0", LEG_FINAL)
    galeria_antes = len(galeria)
    ed.gravar_e_fechar()
    janela.update()
    root.update()

    checar(not ed.winfo_exists(), "o editor fechou ao gravar")
    checar(janela._editor is None, "o Montar esqueceu o editor")
    checar(desbloqueado(janela), "o Montar foi desbloqueado")
    checar(not chamadas_raiz, "fechar o editor nao traz o painel principal de volta")
    checar(bool(janela.winfo_viewable()), "a tela do documento continua visivel")

    checar(len(galeria) > galeria_antes,
           "gravar no editor atualiza tambem a lista do painel principal")
    meta = capture_store.load_meta(caminho_alvo)
    checar(meta.get("caption") == LEG_FINAL, "a legenda do editor foi gravada no .json")
    checar(len(meta.get("shapes", [])) == 1, "a anotacao foi gravada")
    checar(bool(meta.get("edited_at")), "a captura editada fica marcada como editada")
    with Image.open(caminho_alvo) as im:
        checar(im.size == (500, 300), "o recorte foi aplicado ao PNG (%s)" % (im.size,))
    checar(hash_arquivo(caminho_alvo) != png_antes, "o PNG mudou em disco")
    checar(os.path.exists(capture_store.raw_path(caminho_alvo)), "o original continua ao lado")

    # ---- o documento reflete tudo ----
    checar(janela.passos[ALVO]["legenda"] == LEG_FINAL,
           "o passo guarda a legenda que o editor gravou, e nao a que estava no Montar")
    checar(janela.entries_legenda[ALVO].get("1.0", "end").strip() == LEG_FINAL,
           "a caixa de legenda mostra a legenda gravada")
    checar(janela.imagens_passos[ALVO].height() != altura_antes,
           "a miniatura da coluna central foi refeita (%d -> %d px)"
           % (altura_antes, janela.imagens_passos[ALVO].height()))
    checar(len(janela.imagens_sequencia) == N and len(janela.imagens_passos) == N,
           "todas as miniaturas continuam na tela")
    checar(janela.entries_capa["titulo"].get() == "Titulo do teste",
           "a capa digitada sobreviveu")
    checar([p["nome"] for p in janela.passos] == ordem_antes, "a ordem dos passos nao mudou")
    checar(janela.passos[ALVO]["nome"] == nome_alvo, "o passo editado continua na mesma posicao")
    if rola:
        checar(abs(janela._canvas_central.yview()[0] - pos_central) < 0.15,
               "a rolagem da coluna central foi preservada (%.2f -> %.2f)"
               % (pos_central, janela._canvas_central.yview()[0]))

    # ---- a previa que estava aberta acompanhou ----
    checar(bool(previa.winfo_exists()), "a previa continua aberta")
    checar(assinatura_previa() != paginas_antes,
           "a previa aberta foi regerada com a imagem editada")
    checar(str(previa.total_paginas) in previa.lbl_resumo.cget("text"),
           "o resumo da previa mostra o total de paginas")
    previa.destroy()
    root.update()

    # ---- fechar sem gravar nao muda nada ----
    png_3 = hash_arquivo(janela.passos[3]["caminho"])
    janela._editar_passo(3)
    janela.update()
    ed3 = janela._editor
    ed3.shapes.append({"id": 1, "tool": "seta", "coords": [10, 10, 200, 200],
                       "color": "#E8590C", "width": 4, "dash": False, "visible": True})
    ed3._marcar_sujo()
    ed3.fechar_e_voltar()
    janela.update()
    checar(not ed3.winfo_exists() and desbloqueado(janela),
           "fechar sem gravar fecha o editor e desbloqueia o Montar")
    checar(hash_arquivo(janela.passos[3]["caminho"]) == png_3,
           "fechar sem gravar nao altera a imagem em disco")
    checar(any(a[0] == "pergunta" for a in avisos),
           "fechar com alteracao pendente pergunta antes")

    # ---- editor destruido por outro caminho nao pode travar o Montar ----
    janela._editar_passo(4)
    janela.update()
    ed4 = janela._editor
    checar(not desbloqueado(janela), "o Montar esta bloqueado com o editor aberto")
    ed4.destroy()
    janela.update()
    checar(desbloqueado(janela) and janela._editor is None,
           "destruir o editor a forca desbloqueia o Montar")

    # ---- arquivo que sumiu ----
    alvo5 = janela.passos[5]["caminho"]
    os.rename(alvo5, alvo5 + ".bak")
    try:
        antes = len(avisos)
        janela._editar_passo(5)
        janela.update()
        checar(janela._editor is None and desbloqueado(janela),
               "arquivo ausente: nao abre o editor nem trava o Montar")
        checar(any(a[0] == "aviso" for a in avisos[antes:]),
               "arquivo ausente: o usuario e avisado")
    finally:
        os.rename(alvo5 + ".bak", alvo5)

    # ---- o painel nao se esconde com o Montar aberto ----
    app.pausar_timer = False
    app._esconder_por_inatividade()
    root.update()
    checar(bool(root.winfo_viewable()),
           "o painel principal nao se esconde enquanto o Montar esta aberto")
    app.pausar_timer = True

    checar(not [a for a in avisos if a[0] == "erro"], "nenhuma mensagem de erro")
    checar(not erros_tk, "nenhum erro silencioso do Tk")
    for e in erros_tk:
        print("   erro Tk:", "".join(traceback.format_exception(*e))[-400:])
    janela.destroy()
    root.update()
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
