# -*- coding: utf-8 -*-
"""Duplo clique no Montar documento, com eventos de mouse de verdade.

O cenario_editar_do_documento chama os metodos direto. Este aciona os mesmos
caminhos pelo que o usuario faz - apertar, mover e soltar o botao num widget -,
porque foi no gesto, e nao na logica, que os defeitos se escondiam: uma tremida
entre os dois cliques virava arraste e reconstruia a coluna, o clique no cartao
inteiro disputava com o arraste, e a imagem corrompida deixava uma janela vazia
na tela.

Cobre:
  * duplo clique real na miniatura da sequencia e da coluna central, com tremida
  * o botao de lapis e o link "Editar imagem"
  * clique simples e duplo clique fora da miniatura nao abrem o editor
  * arraste real reordena; tremida real nao
  * duplo clique repetido nao abre dois editores
  * editar depois de reordenar abre a captura certa
  * imagem corrompida: espaco reservado, aviso e nenhuma janela vazia sobrando
  * legenda colada pelo mouse chega ao disco e a fechar sem gravar nao se perde
  * trocar o tema com o editor aberto e fechar o Montar com o editor aberto
"""

import os as _os
import sys as _sys

RAIZ = _os.path.dirname(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
_sys.path.insert(0, RAIZ)
_os.chdir(RAIZ)

import os, sys, ctypes, tempfile, shutil, traceback, time
import tkinter as tk

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

tmp = tempfile.mkdtemp(prefix="ge_dclick_")
capturas = os.path.join(tmp, "Capturas")
os.makedirs(capturas)
nomes = []
for i in range(4):
    nome = "print_41%04d.png" % i
    caminho = os.path.join(capturas, nome)
    Image.new("RGB", (900, 560), (30 + i * 40, 90, 150)).save(caminho)
    capture_store.save_meta(caminho, {"caption": "Passo %d" % i, "caso": "", "shapes": []},
                            marcar_editada=False)
    nomes.append(nome)
# Arquivo que parece uma captura mas nao e uma imagem
corrompida = "print_420000.png"
with open(os.path.join(capturas, corrompida), "wb") as f:
    f.write(b"isto nao e um png")

cfg = config.load(tmp)
cfg["pasta_capturas"] = capturas
config.save(tmp, cfg)

root = TkinterDnD.Tk()
root.report_callback_exception = lambda *a: erros_tk.append(a)
app = AppEvidencias(root, capturas, os.path.join(tmp, "PDF"), RAIZ, tmp)
app.pausar_timer = True
root.deiconify()
root.update()


# ------------------------------------------------------------------ gestos

def descendentes(w):
    for f in w.winfo_children():
        yield f
        yield from descendentes(f)


def rotulos_com_imagem(w):
    return [x for x in descendentes(w) if x.winfo_class() == "Label" and str(x.cget("image"))]


# Relogio virtual, em ms. Sem -time o evento gerado nao traz horario, e o Tk
# decide "duplo clique" comparando horarios: todo clique no mesmo ponto passava
# a contar como duplo, por mais que o teste esperasse entre eles.
_relogio = [10_000]


def evento(w, tipo, dx=0, dy=0):
    """Gera o evento no centro do widget, deslocado de (dx, dy), com as
    coordenadas de tela que o Montar usa para decidir se foi arraste."""
    w.update_idletasks()
    x = w.winfo_width() // 2 + dx
    y = w.winfo_height() // 2 + dy
    _relogio[0] += 40
    w.event_generate(tipo, x=x, y=y, rootx=w.winfo_rootx() + x, rooty=w.winfo_rooty() + y,
                     time=_relogio[0])


def clique(w, dx=0, dy=0):
    evento(w, "<ButtonPress-1>", dx, dy)
    evento(w, "<ButtonRelease-1>", dx, dy)


def separar_gestos():
    """Avanca o relogio virtual alem do intervalo de duplo clique do Tk (500 ms).

    Sem isso, um arraste logo apos um clique no mesmo ponto virava duplo clique
    e abria o editor. Nao precisa dormir: o que o Tk compara sao os horarios
    dos eventos, e nao o relogio da parede.
    """
    root.update()
    _relogio[0] += 1500
    time.sleep(0.05)


def clique_isolado(w):
    separar_gestos()
    clique(w)
    root.update()


def duplo_clique(w, tremida=0):
    separar_gestos()
    clique(w)
    clique(w, dx=tremida)
    root.update()


def arrastar(w, dy_total, passo=6):
    separar_gestos()
    evento(w, "<ButtonPress-1>")
    sinal = 1 if dy_total >= 0 else -1
    for d in range(passo, abs(dy_total) + 1, passo):
        evento(w, "<B1-Motion>", dy=sinal * d)
    evento(w, "<B1-Motion>", dy=dy_total)
    evento(w, "<ButtonRelease-1>", dy=dy_total)
    root.update()


def miniaturas_sequencia(j):
    return [rotulos_com_imagem(c)[0] for c in j.frame_sequencia.winfo_children()]


def miniaturas_centro(j):
    return rotulos_com_imagem(j.col_central)


def fechar_editor(j):
    ed = j._editor
    if ed is not None and ed.winfo_exists():
        ed.fechar_e_voltar()
    j.update()
    root.update()


def desbloqueado(j):
    return not int(j.attributes("-disabled"))


def toplevels(pai):
    return [w for w in pai.winfo_children() if isinstance(w, tk.Toplevel)]


try:
    janela = document_builder.MontarDocumento(app, nomes)
    janela.update()
    root.update()
    ordem0 = [p["nome"] for p in janela.passos]
    checar(len(janela.passos) == 4, "4 capturas no documento")
    checar("estimadas" in janela.lbl_paginas.cget("text"),
           "o rodape de paginas estimadas ja aparece na abertura (%r)"
           % janela.lbl_paginas.cget("text"))

    # ---- duplo clique real, com tremida de 2 px entre os cliques ----
    cartoes = list(janela._cards)
    duplo_clique(miniaturas_sequencia(janela)[0], tremida=2)
    checar(janela._editor is not None and bool(janela._editor.winfo_exists()),
           "duplo clique real na miniatura da sequencia abre o editor")
    checar(janela._cards == cartoes,
           "a tremida entre os cliques nao reconstruiu a coluna (mesmos cartoes)")
    checar(janela._editor.caminho_img == janela.passos[0]["caminho"],
           "abriu a captura do cartao clicado")
    checar(not desbloqueado(janela), "o Montar ficou bloqueado")

    # ---- duplo clique repetido nao abre outro editor ----
    duplo_clique(miniaturas_sequencia(janela)[1])
    checar(len(toplevels(janela)) == 1,
           "duplo clique com o editor aberto nao abre um segundo")
    fechar_editor(janela)
    checar(desbloqueado(janela) and janela._editor is None, "fechar o editor libera o Montar")

    # ---- coluna central ----
    duplo_clique(miniaturas_centro(janela)[1], tremida=2)
    checar(janela._editor is not None
           and janela._editor.caminho_img == janela.passos[1]["caminho"],
           "duplo clique real na miniatura da coluna central abre a captura certa")
    fechar_editor(janela)

    # ---- lapis e link ----
    lapis = [w for w in descendentes(janela.frame_sequencia.winfo_children()[2])
             if w.winfo_class() == "Label" and w.cget("text") == "✎"]
    checar(len(lapis) == 1, "cada cartao da sequencia tem o botao de lapis")
    if lapis:
        clique_isolado(lapis[0])
        checar(janela._editor is not None
               and janela._editor.caminho_img == janela.passos[2]["caminho"],
               "o botao de lapis abre a captura do cartao")
        fechar_editor(janela)
    links = [w for w in descendentes(janela.col_central)
             if w.winfo_class() == "Label" and "Editar imagem" in str(w.cget("text"))]
    checar(len(links) == 4, "cada passo da coluna central tem o link 'Editar imagem'")
    if links:
        clique_isolado(links[3])
        checar(janela._editor is not None
               and janela._editor.caminho_img == janela.passos[3]["caminho"],
               "o link abre a captura do passo, com um clique so")
        fechar_editor(janela)

    # ---- o que NAO deve abrir o editor ----
    mini0 = miniaturas_sequencia(janela)[0]
    clique_isolado(mini0)
    checar(janela._editor is None, "clique simples na miniatura nao abre o editor")
    duplo_clique(janela._cards[0])
    duplo_clique(mini0.master)          # a moldura em volta da miniatura
    checar(janela._editor is None,
           "duplo clique no cartao (fora da imagem) nao abre o editor")
    checar(not toplevels(janela), "nenhuma janela de edicao aberta antes do arraste")

    # ---- arrastar de verdade reordena; tremida de verdade nao ----
    cartoes = list(janela._cards)
    ordem = [p["nome"] for p in janela.passos]
    arrastar(miniaturas_sequencia(janela)[0], 3)
    checar([p["nome"] for p in janela.passos] == ordem and janela._cards == cartoes,
           "tremida real de 3 px nao reordena nem reconstrui")

    alvo = janela._cards[2]
    thumb = miniaturas_sequencia(janela)[0]
    y_destino = alvo.winfo_rooty() + int(alvo.winfo_height() * 0.8)
    y_origem = thumb.winfo_rooty() + thumb.winfo_height() // 2
    arrastar(thumb, y_destino - y_origem)
    esperado = [ordem[1], ordem[2], ordem[0], ordem[3]]
    if [p["nome"] for p in janela.passos] != esperado:
        print("   diagnostico: estado=%s arraste=%s editor=%s toplevels=%s"
              % (janela.state(), janela._arraste, janela._editor, toplevels(janela)))
        print("   diagnostico: y_origem=%s y_destino=%s cartoes=%s"
              % (y_origem, y_destino,
                 [(c.winfo_rooty(), c.winfo_height()) for c in janela._cards]))
    checar([p["nome"] for p in janela.passos] == esperado,
           "arraste real do primeiro cartao ate abaixo do terceiro reordena (%s)"
           % [n[-8:-4] for n in (p["nome"] for p in janela.passos)])
    checar(len(miniaturas_sequencia(janela)) == 4 and len(miniaturas_centro(janela)) == 4,
           "depois do arraste todas as miniaturas continuam na tela")

    # ---- editar depois de reordenar abre a captura certa ----
    janela._mover(2, -1)
    janela.update()
    duplo_clique(miniaturas_sequencia(janela)[1])
    checar(janela._editor is not None
           and janela._editor.caminho_img == janela.passos[1]["caminho"],
           "apos reordenar, o duplo clique abre a captura da posicao atual")
    fechar_editor(janela)

    # ---- legenda colada pelo mouse nao dispara KeyRelease ----
    caixa = janela.entries_legenda[2]
    caixa.delete("1.0", "end")
    caixa.insert("1.0", "Colada com o botao direito")     # sem _on_legenda_change
    janela.update()
    checar(janela.passos[2]["legenda"] != "Colada com o botao direito",
           "pre-condicao: o passo ainda nao viu a legenda colada")
    janela._pre_visualizar()
    root.update()
    previa = next((w for w in root.winfo_children()
                   if isinstance(w, export_preview.PreVisualizarExportar)), None)
    checar(janela.passos[2]["legenda"] == "Colada com o botao direito",
           "pre-visualizar le a legenda colada pelo mouse")
    checar(capture_store.load_meta(janela.passos[2]["caminho"]).get("caption")
           == "Colada com o botao direito",
           "e a grava no .json da captura")
    if previa:
        previa.fechar()
        root.update()

    # ---- fechar sem gravar nao perde a legenda do Montar ----
    caixa = janela.entries_legenda[0]
    caixa.delete("1.0", "end")
    caixa.insert("1.0", "Legenda so no Montar")
    janela._on_legenda_change(0, caixa)
    duplo_clique(miniaturas_sequencia(janela)[0])
    ed = janela._editor
    checar(ed is not None and ed.txt_legenda.get("1.0", "end").strip() == "Legenda so no Montar",
           "o editor abre com a legenda do Montar")
    fechar_editor(janela)
    checar(janela.passos[0]["legenda"] == "Legenda so no Montar"
           and janela.entries_legenda[0].get("1.0", "end").strip() == "Legenda so no Montar",
           "fechar o editor sem gravar nao descarta a legenda do Montar")
    checar(capture_store.load_meta(janela.passos[0]["caminho"]).get("caption")
           != "Legenda so no Montar",
           "e tambem nao grava nada em disco")

    # ---- trocar o tema com o editor aberto ----
    duplo_clique(miniaturas_sequencia(janela)[0])
    ed = janela._editor
    app.alternar_tema()
    root.update()
    checar(bool(ed.winfo_exists()) and not desbloqueado(janela),
           "trocar o tema nao derruba o editor nem libera o Montar")
    app.alternar_tema()
    root.update()
    ed.destroy()
    janela.update()
    checar(desbloqueado(janela) and janela._editor is None,
           "destruir o editor depois de trocar o tema libera o Montar")

    # ---- fechar o Montar com o editor aberto ----
    duplo_clique(miniaturas_sequencia(janela)[0])
    ed = janela._editor
    janela.destroy()
    root.update()
    checar(not ed.winfo_exists(), "fechar o Montar leva o editor junto")
    checar(not [w for w in toplevels(root) if isinstance(w, editor.EditorImagem)],
           "nao sobra editor orfao na raiz")

    # ---- imagem corrompida ----
    janela2 = document_builder.MontarDocumento(app, [corrompida, nomes[0]])
    janela2.update()
    root.update()
    idx = [p["nome"] for p in janela2.passos].index(corrompida)
    marcadores = [w for w in descendentes(janela2)
                  if w.winfo_class() == "Label" and w.cget("text") == "imagem indisponível"]
    checar(len(marcadores) == 2,
           "a captura corrompida mostra o espaco reservado na sequencia e no centro (%d)"
           % len(marcadores))
    antes = len(avisos)
    candidatos = [m for m in marcadores if m.winfo_manager()]
    seq_marcador = next(m for m in marcadores
                        if str(m).startswith(str(janela2.frame_sequencia)))
    duplo_clique(seq_marcador)
    checar(janela2._editor is None, "imagem corrompida: nao abre o editor")
    checar(any(a[0] == "erro" for a in avisos[antes:]),
           "imagem corrompida: o usuario e avisado")
    checar(toplevels(janela2) == [],
           "imagem corrompida: nao sobra janela vazia na tela")
    checar(desbloqueado(janela2), "imagem corrompida: o Montar nao fica travado")
    del candidatos, idx

    # o mesmo vale para o duplo clique da lista do painel principal
    antes_raiz = len(toplevels(root))
    try:
        app.abrir_editor(os.path.join(capturas, corrompida))
        levantou = False
    except Exception:
        levantou = True
    root.update()
    checar(levantou, "abrir uma imagem corrompida pelo painel falha de forma explicita")
    checar(len(toplevels(root)) == antes_raiz,
           "e tambem nao deixa janela vazia para tras")
    janela2.destroy()
    root.update()

    checar(not [a for a in avisos if a[0] == "aviso"], "nenhum aviso inesperado")
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
