# -*- coding: utf-8 -*-
"""Arrastar para reordenar a Sequencia: o que o usuario ve e o que sai.

Eventos de mouse reais (apertar, mover, soltar), como em
cenario_duplo_clique_documento. O que se confere aqui e o contrato da interface:

  * durante o arraste ha um fantasma e um vao, e o vao esta onde o destino diz
  * os outros cartoes mudam de numero ao vivo, e o fantasma e o vao mostram o
    numero que o passo vai ter
  * o item sai EXATAMENTE onde o vao estava - para qualquer par origem/destino
  * a lista rola sozinha perto das bordas, nos dois sentidos, e mais rapido
    quanto mais perto da borda; o destino acompanha a rolagem
  * Esc cancela e tudo volta como estava
  * soltar nao reconstroi nada: nenhuma imagem e relida do disco, os mesmos
    widgets (legendas digitadas inclusive) apenas trocam de lugar, a rolagem
    das duas colunas nao muda, e e rapido
  * os botoes e a legenda de um cartao continuam acertando o passo certo depois
    de ele mudar de posicao (nada guarda o indice de quando foi criado)
  * desfazer (link e Ctrl+Z), aviso que some sozinho, Alt+seta no cartao
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
from PIL import Image, ImageDraw
import PIL.Image
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

tmp = tempfile.mkdtemp(prefix="ge_arraste_")
capturas = os.path.join(tmp, "Capturas")
os.makedirs(capturas)


def criar(prefixo, quantidade, tamanho):
    nomes = []
    for i in range(quantidade):
        nome = "print_%s%04d.png" % (prefixo, i)
        caminho = os.path.join(capturas, nome)
        img = Image.new("RGB", tamanho, (248, 250, 252))
        d = ImageDraw.Draw(img)
        d.rectangle([0, 0, tamanho[0], 70], fill=(20 + i * 12, 100, 150))
        for k in range(30):
            d.rectangle([40, 110 + k * 30, tamanho[0] - 40, 130 + k * 30],
                        outline=(206, 214, 222))
        img.save(caminho)
        capture_store.save_meta(caminho, {"caption": "Passo %s%d" % (prefixo, i),
                                          "caso": "", "shapes": []}, marcar_editada=False)
        nomes.append(nome)
    return nomes


pequenas = criar("1", 4, (900, 560))
grandes = criar("2", 14, (1920, 1080))

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

_relogio = [10_000]


def evento(w, tipo, x_root, y_root):
    """Evento com coordenadas de TELA absolutas. As de tela e que o Montar usa;
    nao dependem de onde o widget esta (ele some do layout durante o arraste)."""
    _relogio[0] += 40
    w.event_generate(tipo, x=int(x_root - w.winfo_rootx()), y=int(y_root - w.winfo_rooty()),
                     rootx=int(x_root), rooty=int(y_root), time=_relogio[0])


def separar_gestos():
    root.update()
    _relogio[0] += 1500
    time.sleep(0.03)


def descendentes(w):
    for f in w.winfo_children():
        yield f
        yield from descendentes(f)


def clicar_botao(w):
    """Clique num botao do cartao. Eles agem ja no pressionar (<Button-1>), e o
    ✕ reconstroi a coluna: o widget pode nao existir mais quando o botao e solto."""
    separar_gestos()
    x, y = w.winfo_rootx() + 3, w.winfo_rooty() + 3
    evento(w, "<ButtonPress-1>", x, y)
    try:
        evento(w, "<ButtonRelease-1>", x, y)
    except tk.TclError:
        pass
    root.update()


def miniatura_do_cartao(card):
    return next(x for x in descendentes(card)
                if x.winfo_class() == "Label" and str(x.cget("image")))


class Arraste:
    """Um gesto de arraste: aperta no centro da miniatura e vai movendo."""

    def __init__(self, j, indice):
        separar_gestos()
        self.j = j
        self.w = miniatura_do_cartao(j._cards[indice])
        self.x = self.w.winfo_rootx() + self.w.winfo_width() // 2
        self.y = self.w.winfo_rooty() + self.w.winfo_height() // 2
        evento(self.w, "<ButtonPress-1>", self.x, self.y)

    def ir_para(self, y_alvo, passo=7, atualizar=False):
        sinal = 1 if y_alvo >= self.y else -1
        while abs(y_alvo - self.y) > passo:
            self.y += sinal * passo
            evento(self.w, "<B1-Motion>", self.x, self.y)
            if atualizar:
                root.update()
        self.y = y_alvo
        evento(self.w, "<B1-Motion>", self.x, self.y)

    def soltar(self):
        evento(self.w, "<ButtonRelease-1>", self.x, self.y)
        root.update()

    @property
    def estado(self):
        return self.j._arraste


def exibida(j):
    """Os passos na ordem em que estao empacotados na tela."""
    rec_por_frame = {id(r["frame"]): c for c, r in j._cartoes.items()}
    return [rec_por_frame[id(f)] for f in j.frame_sequencia.pack_slaves()
            if id(f) in rec_por_frame]


def nomes_da_ordem(j):
    return [p["caminho"] for p in j.passos]


def y_do_destino(j, estado, d):
    """Altura de TELA em que o ponteiro deve estar para o destino ser `d`."""
    mids, m = estado["mids"], estado["margem"]
    if d == 0:
        yc = mids[0] - 2 * m
    elif d == len(mids):
        yc = mids[-1] + 2 * m
    else:
        yc = (mids[d - 1] + mids[d]) / 2
    cv = j._canvas_sequencia
    return cv.winfo_rooty() + (yc - cv.canvasy(0))


def toplevels(pai):
    return [w for w in pai.winfo_children() if isinstance(w, tk.Toplevel)]


def abrir(nomes):
    j = document_builder.MontarDocumento(app, nomes)
    j.update()
    root.update()
    return j


try:
    # =================================================================
    # Lista curta: contrato do arraste
    # =================================================================
    # A lista curta nao e para testar a rolagem automatica (ha secao propria, mais
    # adiante): aqui ela so atrapalharia. O cartao 3 tem a miniatura abaixo da
    # area visivel, o ponteiro de teste comecaria dentro da faixa de rolagem e a
    # lista andaria sozinha durante o gesto, deslocando o alvo calculado.
    _autoscroll_ms = document_builder._AUTOSCROLL_MS
    document_builder._AUTOSCROLL_MS = 10 ** 9

    j = abrir(pequenas)
    original = nomes_da_ordem(j)
    checar(len(original) == 4, "4 capturas no documento")
    checar(all(w.cget("text") for w in descendentes(j._cards[0])
               if w.winfo_class() == "Label" and w.cget("text") == "⋮⋮"),
           "cada cartao tem a alca de arraste")

    # ---- o fantasma e o vao aparecem; os outros se afastam ao vivo ----
    a = Arraste(j, 3)                       # o ultimo cartao
    a.ir_para(a.y - 20, atualizar=True)
    e = a.estado
    checar(bool(e and e["ativo"]), "o arraste ativa depois de mover")
    checar(j._fantasma is not None and bool(j._fantasma.winfo_ismapped()),
           "um fantasma da miniatura segue o ponteiro")
    checar(bool(e["vao"].winfo_ismapped()), "ha um vao do tamanho do cartao levado")
    checar(abs(e["vao"].winfo_height() - e["altura"]) <= 2 and e["altura"] > 100,
           "o vao tem a altura do cartao levado (%d px x %d px)"
           % (e["vao"].winfo_height(), e["altura"]))

    # Os pontos medios contra a geometria REAL, calculada so a partir das alturas
    # dos cartoes: sem isto o teste de todos os pares usaria os mesmos numeros
    # que o codigo calculou, e concordaria com qualquer valor errado.
    esperado_mids, topo_c = [], 4
    for rec in e["recs_outros"]:
        altura_c = rec["frame"].winfo_height()
        esperado_mids.append(topo_c + altura_c / 2)
        topo_c += altura_c + 8
    checar(len(e["mids"]) == 3 and all(abs(m - x) <= 1 for m, x in zip(e["mids"], esperado_mids)),
           "os pontos medios batem com o layout sem o cartao levado (%s x %s)"
           % ([round(m) for m in e["mids"]], [round(x) for x in esperado_mids]))

    # percorre todas as posicoes de baixo para cima, devagar
    vistos = []
    erros_de_vao = []
    erros_de_numero = []
    destino_antes = e["destino"]
    topo_alvo = y_do_destino(j, e, 0)
    while a.y > topo_alvo:
        a.ir_para(a.y - 9, passo=9, atualizar=True)
        e = a.estado
        d = e["destino"]
        slaves = j.frame_sequencia.pack_slaves()
        if slaves.index(e["vao"]) != d:
            erros_de_vao.append((d, slaves.index(e["vao"])))
        for k, rec in enumerate(e["recs_outros"]):
            esperado = k + 1 if k < d else k + 2
            if rec["numero"] != esperado:
                erros_de_numero.append((d, k, rec["numero"], esperado))
        if e["lbl_vao"].cget("text") != "Posição %d" % (d + 1):
            erros_de_numero.append((d, "vao", e["lbl_vao"].cget("text")))
        if e["numero_fantasma"] != d + 1:
            erros_de_numero.append((d, "fantasma", e["numero_fantasma"]))
        vistos.append(d)
    checar(not erros_de_vao, "o vao esta sempre na posicao que o destino indica %s"
           % (erros_de_vao[:3],))
    checar(not erros_de_numero,
           "os numeros dos cartoes, do vao e do fantasma acompanham o destino ao vivo %s"
           % (erros_de_numero[:3],))
    checar(vistos == sorted(vistos, reverse=True) and vistos[-1] == 0,
           "subindo, o destino so diminui e chega a 0 (%s)" % sorted(set(vistos), reverse=True))
    checar(set(vistos) >= {0, 1, 2},
           "passou por todas as posicoes pelo caminho, sem pular nenhuma")

    # desce de volta: o destino so aumenta
    descida = []
    fundo = y_do_destino(j, a.estado, 3)
    while a.y < fundo:
        a.ir_para(a.y + 9, passo=9, atualizar=True)
        descida.append(a.estado["destino"])
    checar(descida == sorted(descida) and descida[-1] == 3,
           "descendo, o destino so aumenta e chega ao fim (%s)" % sorted(set(descida)))
    a.soltar()
    checar(nomes_da_ordem(j) == original, "voltou ao fim: a ordem e a original")
    checar(j._arraste is None and j._fantasma is None,
           "soltar encerra o arraste e remove o fantasma")
    checar(exibida(j) == original, "e a tela mostra a ordem original")

    # ---- o numero acompanhou: apos soltar, cada cartao tem o seu ----
    checar([j._cartoes[c]["numero"] for c in nomes_da_ordem(j)] == [1, 2, 3, 4],
           "os numeros das miniaturas voltam a 1..4")

    # ---- TODOS os pares origem/destino: o item sai onde o vao estava ----
    falhas_par = []
    for origem in range(4):
        for destino in range(4):
            antes = nomes_da_ordem(j)
            item = antes[origem]
            b = Arraste(j, origem)
            b.ir_para(b.y + (12 if origem < 3 else -12), atualizar=True)
            # pontos medios contra a geometria real: para origens acima de outros
            # cartoes e que o desconto do cartao levado entra em jogo
            esperado_m, topo_m = [], 4
            for rec_m in b.estado["recs_outros"]:
                h_m = rec_m["frame"].winfo_height()
                esperado_m.append(topo_m + h_m / 2)
                topo_m += h_m + 8
            if not all(abs(m - x) <= 1 for m, x in zip(b.estado["mids"], esperado_m)):
                falhas_par.append((origem, destino, "mids",
                                   [round(m) for m in b.estado["mids"]],
                                   [round(x) for x in esperado_m]))
            alvo = y_do_destino(j, b.estado, destino)
            b.ir_para(alvo, atualizar=True)
            mostrado = b.estado["destino"]
            vao_em = j.frame_sequencia.pack_slaves().index(b.estado["vao"])
            b.soltar()
            depois = nomes_da_ordem(j)
            sem_o_item_antes = [c for c in antes if c != item]
            sem_o_item_depois = [c for c in depois if c != item]
            if not (depois.index(item) == destino == mostrado == vao_em
                    and sem_o_item_antes == sem_o_item_depois
                    and exibida(j) == depois):
                falhas_par.append((origem, destino, mostrado, vao_em, depois.index(item)))
    checar(not falhas_par,
           "16 de 16 pares origem/destino: o item sai exatamente onde o vao estava %s"
           % (falhas_par[:4],))

    # ---- soltar sem ter chegado a mover (clique simples) nao muda nada ----
    antes = nomes_da_ordem(j)
    c = Arraste(j, 1)
    c.ir_para(c.y + 3)
    c.soltar()
    checar(nomes_da_ordem(j) == antes and j._fantasma is None,
           "tremida de 3 px nao ativa o arraste")

    # ---- ponteiro parado sobre a fronteira entre dois cartoes: o vao nao oscila ----
    antes = nomes_da_ordem(j)
    k = Arraste(j, 0)
    k.ir_para(k.y + 12, atualizar=True)
    cvs = j._canvas_sequencia
    meio_tela = int(cvs.winfo_rooty() + (k.estado["mids"][0] - cvs.canvasy(0)))
    k.ir_para(meio_tela, atualizar=True)
    destinos = []
    for delta in (3, -3, 4, -4, 2, -2, 3, -3, 4, -4, 3, -3):
        k.ir_para(meio_tela + delta, passo=50)
        root.update()
        destinos.append(k.estado["destino"])
    checar(len(set(destinos)) == 1,
           "tremendo 4 px em volta do meio de um cartao o vao fica onde esta (%s)"
           % sorted(set(destinos)))
    j.focus_force()
    j.update()
    j.event_generate("<Escape>")
    k.soltar()
    checar(nomes_da_ordem(j) == antes, "pre-condicao: o teste da fronteira nao mexeu na ordem")

    # ---- Esc cancela e tudo volta como estava ----
    j._esconder_aviso()          # o aviso dos movimentos acima ainda estaria na tela
    root.update()
    antes = nomes_da_ordem(j)
    d_ = Arraste(j, 0)
    d_.ir_para(d_.y + 12, atualizar=True)
    d_.ir_para(y_do_destino(j, d_.estado, 3), atualizar=True)
    checar(d_.estado["destino"] == 3, "pre-condicao: arrastado ate o fim")
    j.focus_force()
    j.update()
    j.event_generate("<Escape>")
    root.update()
    checar(j._arraste is None and j._fantasma is None,
           "Esc encerra o arraste e remove o fantasma")
    checar(nomes_da_ordem(j) == antes and exibida(j) == antes,
           "Esc devolve cada cartao ao lugar de origem")
    checar([j._cartoes[c]["numero"] for c in antes] == [1, 2, 3, 4],
           "e os numeros voltam ao que eram")
    checar(len(j.frame_sequencia.pack_slaves()) == 4,
           "nao sobra vao nenhum na lista")
    d_.soltar()                             # o botao ainda estava apertado
    checar(nomes_da_ordem(j) == antes, "soltar o botao depois do Esc nao reordena")
    checar(not j._aviso_seq.winfo_ismapped(), "cancelar nao mostra o aviso de movimento")

    # =================================================================
    # Nada e reconstruido: mesmos widgets, legenda no cartao certo
    # =================================================================
    centro_antes = {c: r["txt"] for c, r in j._cartoes_centro.items()}
    frames_antes = {c: r["frame"] for c, r in j._cartoes.items()}
    j._canvas_central.yview_moveto(0.0)
    primeiro = nomes_da_ordem(j)[0]
    caixa = j._cartoes_centro[primeiro]["txt"]
    caixa.delete("1.0", "end")
    caixa.insert("1.0", "Colada sem evento de teclado")      # como colar pelo mouse
    abertos = []
    original_open = PIL.Image.open
    PIL.Image.open = lambda *a, **k: (abertos.append(a), original_open(*a, **k))[1]
    try:
        f = Arraste(j, 0)
        f.ir_para(f.y + 12, atualizar=True)
        f.ir_para(y_do_destino(j, f.estado, 3), atualizar=True)
        f.soltar()
    finally:
        PIL.Image.open = original_open
    checar(not abertos, "arrastar e soltar nao le nenhuma imagem do disco (%d aberturas)"
           % len(abertos))
    checar(all(j._cartoes[c]["frame"] is frames_antes[c] for c in frames_antes),
           "os cartoes da sequencia sao os mesmos widgets, so mudaram de lugar")
    checar(all(j._cartoes_centro[c]["txt"] is centro_antes[c] for c in centro_antes),
           "o mesmo vale para a coluna central")
    checar(nomes_da_ordem(j)[-1] == primeiro, "o primeiro passo foi para o fim")
    j._sincronizar_legendas()
    checar(j.passos[-1]["legenda"] == "Colada sem evento de teclado",
           "a legenda digitada sem evento acompanha o passo ao mudar de posicao")
    checar(all(j.entries_legenda[i].get("1.0", "end").strip() == p["legenda"]
               for i, p in enumerate(j.passos)),
           "cada caixa de legenda corresponde ao passo da sua posicao")
    checar([j._cartoes_centro[p["caminho"]]["selo"].cget("text") for p in j.passos]
           == ["1", "2", "3", "4"], "a numeracao da coluna central acompanha")

    # ---- botoes de um cartao que mudou de posicao acertam o passo certo ----
    ordem = nomes_da_ordem(j)
    alvo_cartao = j._cartoes[ordem[0]]["frame"]          # o que era o 2o, agora e o 1o
    seta_baixo = next(w for w in descendentes(alvo_cartao)
                      if w.winfo_class() == "Label" and w.cget("text") == "↓")
    clicar_botao(seta_baixo)
    checar(nomes_da_ordem(j) == [ordem[1], ordem[0], ordem[2], ordem[3]],
           "o botao ↓ de um cartao que ja mudou de lugar move o passo certo")
    ordem = nomes_da_ordem(j)
    x_btn = next(w for w in descendentes(j._cartoes[ordem[2]]["frame"])
                 if w.winfo_class() == "Label" and w.cget("text") == "✕")
    clicar_botao(x_btn)
    checar(nomes_da_ordem(j) == [ordem[0], ordem[1], ordem[3]],
           "o botao ✕ de um cartao que ja mudou de lugar remove o passo certo")
    checar(len(j.frame_sequencia.pack_slaves()) == 3 and len(j._cartoes) == 3,
           "e a lista ficou com 3 cartoes, sem restos")
    j.destroy()
    root.update()

    # =================================================================
    # Desfazer, aviso e teclado
    # =================================================================
    j = abrir(pequenas)
    original = nomes_da_ordem(j)
    g = Arraste(j, 0)
    g.ir_para(g.y + 12, atualizar=True)
    g.ir_para(y_do_destino(j, g.estado, 2), atualizar=True)
    g.soltar()
    movida = nomes_da_ordem(j)
    checar(movida != original and bool(j._aviso_seq.winfo_ismapped()),
           "depois de mover aparece o aviso com 'Desfazer'")
    checar("posição 3" in j._lbl_aviso_seq.cget("text"),
           "o aviso diz a nova posicao (%r)" % j._lbl_aviso_seq.cget("text"))
    j._desfazer_movimento()
    root.update()
    checar(nomes_da_ordem(j) == original and exibida(j) == original,
           "Desfazer devolve a ordem anterior, na tela tambem")
    checar(not j._aviso_seq.winfo_ismapped(), "e o aviso some")

    g = Arraste(j, 0)
    g.ir_para(g.y + 12, atualizar=True)
    g.ir_para(y_do_destino(j, g.estado, 3), atualizar=True)
    g.soltar()
    j.focus_force()
    j.event_generate("<Control-z>")
    root.update()
    checar(nomes_da_ordem(j) == original, "Ctrl+Z desfaz a ultima movimentacao")

    document_builder._AVISO_MS = 600
    g = Arraste(j, 1)
    g.ir_para(g.y + 12, atualizar=True)
    g.ir_para(y_do_destino(j, g.estado, 3), atualizar=True)
    g.soltar()
    antes_ctrlz = nomes_da_ordem(j)
    caixa = j._cartoes_centro[antes_ctrlz[0]]["txt"]
    caixa.focus_force()
    j.update()
    resultado = j._atalho_desfazer()
    checar(resultado is None and nomes_da_ordem(j) == antes_ctrlz,
           "Ctrl+Z dentro de uma caixa de texto nao desfaz a ordem")
    deadline = time.time() + 3
    while j._aviso_seq.winfo_ismapped() and time.time() < deadline:
        root.update()
        time.sleep(0.05)
    checar(not j._aviso_seq.winfo_ismapped(), "o aviso some sozinho depois de uns segundos")
    document_builder._AVISO_MS = 6000
    j.focus_force()
    j.update()
    j.event_generate("<Control-z>")
    root.update()
    checar(nomes_da_ordem(j) == antes_ctrlz,
           "sem o aviso na tela, Ctrl+Z nao desfaz um movimento antigo")

    # Clicar num cartao NAO pode mexer no foco do Tk nem no tamanho dele: era
    # isso que fazia o duplo clique da miniatura falhar de forma intermitente com
    # o mouse de verdade (o foco gerava FocusOut/FocusIn entre os dois cliques).
    j.focus_force()
    j.update()
    ordem = nomes_da_ordem(j)
    cartao = j._cartoes[ordem[2]]["frame"]
    foco_antes = j.focus_get()
    tamanho_antes = (cartao.winfo_width(), cartao.winfo_height(), cartao.winfo_y())
    miniatura = miniatura_do_cartao(cartao)
    separar_gestos()
    evento(miniatura, "<ButtonPress-1>", miniatura.winfo_rootx() + 5, miniatura.winfo_rooty() + 5)
    evento(miniatura, "<ButtonRelease-1>", miniatura.winfo_rootx() + 5, miniatura.winfo_rooty() + 5)
    root.update()
    checar(j.focus_get() is foco_antes,
           "clicar num cartao nao muda o foco do Tk (causa da falha intermitente do duplo clique)")
    checar((cartao.winfo_width(), cartao.winfo_height(), cartao.winfo_y()) == tamanho_antes,
           "e nao mexe no tamanho nem na posicao do cartao")
    checar(j._selecionado == ordem[2], "mas o cartao fica selecionado")
    from gestor.ui import theme as _tema
    _t = _tema.get(app.modo_escuro)
    checar(str(cartao.cget("highlightbackground")) == _t["accent"],
           "e destacado pela cor da borda")
    checar(str(j._cartoes[ordem[1]]["frame"].cget("highlightbackground")) == _t["border_soft"],
           "enquanto os outros seguem com a borda comum")

    # Alt+seta age sobre o cartao selecionado
    cartao.event_generate("<Alt-Up>")
    root.update()
    checar(nomes_da_ordem(j) == [ordem[0], ordem[2], ordem[1], ordem[3]],
           "Alt+↑ sobe o cartao selecionado uma posicao")
    checar(j._selecionado == ordem[2], "e ele continua selecionado")
    cartao.event_generate("<Alt-Down>")
    root.update()
    checar(nomes_da_ordem(j) == ordem, "Alt+↓ desce de volta")
    for _ in range(3):
        cartao.event_generate("<Alt-Up>")
    root.update()
    checar(nomes_da_ordem(j)[0] == ordem[2], "no topo, Alt+↑ nao passa do primeiro")
    # dentro de uma caixa de texto, Alt+seta nao e do cartao
    antes_alt = nomes_da_ordem(j)
    caixa = j._cartoes_centro[antes_alt[1]]["txt"]
    caixa.focus_force()
    j.update()
    caixa.event_generate("<Alt-Down>")
    root.update()
    checar(nomes_da_ordem(j) == antes_alt, "Alt+↓ dentro de uma caixa de texto nao move cartao")
    j.destroy()
    root.update()

    # =================================================================
    # Lista longa: rolagem automatica e velocidade
    # =================================================================
    document_builder._AUTOSCROLL_MS = _autoscroll_ms
    j = abrir(grandes)
    cv = j._canvas_sequencia
    original = nomes_da_ordem(j)
    cv.yview_moveto(1.0)
    j.update()
    fim = cv.yview()[0]
    checar(fim > 0.5 and len(original) == 14,
           "pre-condicao: 14 cartoes e a lista rolada ate o fim (%.2f)" % fim)

    # Preso no ultimo cartao, leva o ponteiro para ACIMA da borda de cima
    h = Arraste(j, 13)
    h.ir_para(h.y - 20, atualizar=True)
    h.ir_para(cv.winfo_rooty() - 25, atualizar=True)
    e = h.estado
    rolagem_a = cv.yview()[0]
    destino_a = e["destino"]
    t0 = time.time()
    while time.time() - t0 < 6 and not (e["destino"] == 0 and cv.yview()[0] <= 0.0):
        root.update()
        time.sleep(0.02)
    checar(cv.yview()[0] < rolagem_a - 0.3,
           "segurando acima da borda, a lista rola sozinha para cima (%.2f -> %.2f)"
           % (rolagem_a, cv.yview()[0]))
    checar(e["destino"] < destino_a and e["destino"] == 0,
           "e o destino acompanha: chega ao topo da lista (%d -> %d)" % (destino_a, e["destino"]))
    checar(cv.yview()[0] <= 0.001, "ate o topo")
    slaves = j.frame_sequencia.pack_slaves()
    checar(slaves.index(e["vao"]) == 0, "o vao esta no topo da lista")

    # velocidade proporcional: perto da zona x alem da borda, mesma janela de tempo
    def px_rolados(y_screen, segundos=0.5):
        cv.yview_moveto(0.5)
        root.update()
        antes = cv.canvasy(0)
        h.ir_para(y_screen)
        fim_ = time.time() + segundos
        while time.time() < fim_:
            root.update()
            time.sleep(0.01)
        return abs(cv.canvasy(0) - antes)

    topo = cv.winfo_rooty()
    suave = px_rolados(topo + 55)          # logo depois de entrar na faixa
    rapido = px_rolados(topo - 30)         # alem da borda
    checar(rapido > suave * 3 and suave > 0,
           "quanto mais perto da borda, mais rapido rola (%d px x %d px em 0,5 s)"
           % (suave, rapido))
    parado = px_rolados(topo + cv.winfo_height() // 2)
    checar(parado == 0, "no meio da lista nao rola nada (%d px)" % parado)

    # para baixo, ate o fim
    cv.yview_moveto(0.0)
    root.update()
    h.ir_para(cv.winfo_rooty() + cv.winfo_height() + 25, atualizar=True)
    t0 = time.time()
    while time.time() - t0 < 8 and not (e["destino"] == 13 and cv.yview()[1] >= 0.999):
        root.update()
        time.sleep(0.02)
    checar(e["destino"] == 13 and cv.yview()[1] >= 0.999,
           "segurando abaixo da borda, rola ate o fim e o destino chega ao ultimo (%d)"
           % e["destino"])

    # volta ao topo e solta: o item vai para a posicao 0, a rolagem nao e mexida
    cv.yview_moveto(0.0)
    h.ir_para(cv.winfo_rooty() - 25, atualizar=True)
    t0 = time.time()
    while time.time() - t0 < 6 and e["destino"] != 0:
        root.update()
        time.sleep(0.02)
    rolagem_antes_de_soltar = cv.yview()[0]
    h.soltar()
    checar(nomes_da_ordem(j)[0] == original[13] and nomes_da_ordem(j)[1:] == original[:13],
           "soltar no topo manda o ultimo passo para a posicao 1 sem mexer nos outros")
    checar(abs(cv.yview()[0] - rolagem_antes_de_soltar) < 0.02,
           "e soltar nao mexe na rolagem")
    timer_vivo = j._arraste is not None
    checar(not timer_vivo, "o temporizador de rolagem para ao soltar")

    # ---- velocidade: soltar e ↑↓ nao esperam por nada ----
    centro_y = j._canvas_central.yview()[0]
    abertos.clear()
    PIL.Image.open = lambda *a, **k: (abertos.append(a), original_open(*a, **k))[1]
    try:
        k = Arraste(j, 5)
        k.ir_para(k.y + 12, atualizar=True)
        k.ir_para(y_do_destino(j, k.estado, 2), atualizar=True)
        t0 = time.perf_counter()
        k.soltar()
        tempo_soltar = (time.perf_counter() - t0) * 1000
        t0 = time.perf_counter()
        j._mover(4, 1)
        j.update()
        tempo_seta = (time.perf_counter() - t0) * 1000
    finally:
        PIL.Image.open = original_open
    checar(tempo_soltar < 400,
           "soltar com 14 capturas de tela cheia leva %d ms (antes: ate 6000 ms)" % tempo_soltar)
    checar(tempo_seta < 400, "o botao ↓ leva %d ms" % tempo_seta)
    checar(not abertos, "nenhuma das duas leu imagem do disco (%d aberturas)" % len(abertos))

    # trocar o numero das miniaturas nao pode perder imagem: tudo ainda existe no Tk
    vivas = 0
    for p in j.passos:
        foto = j._cartoes[p["caminho"]]["foto"]
        try:
            j.tk.call("image", "width", str(foto))
            vivas += 1
        except Exception:
            pass
    checar(vivas == 14 and len(j.imagens_sequencia) == 14 and len(j.imagens_passos) == 14,
           "as 14 miniaturas de cada coluna continuam vivas")
    checar([j._cartoes[p["caminho"]]["numero"] for p in j.passos] == list(range(1, 15)),
           "e numeradas de 1 a 14")
    checar(abs(j._canvas_central.yview()[0] - centro_y) < 0.02,
           "a rolagem da coluna central nao mudou")
    j.destroy()
    root.update()

    checar(not toplevels(root), "nenhuma janela sobrando")
    checar(not [a for a in avisos if a[0] in ("erro", "aviso")], "nenhum aviso ou erro")
    checar(not erros_tk, "nenhum erro silencioso do Tk")
    for erro in erros_tk:
        print("   erro Tk:", "".join(traceback.format_exception(*erro))[-600:])
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
