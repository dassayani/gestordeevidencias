# -*- coding: utf-8 -*-
"""Os pontos que ficaram da revisao critica, com o app de verdade.

  * menu da bandeja: o pystray chama na thread DELE; o Tk so pode ser usado na
    thread do Tk - o pedido e enfileirado e executado la
  * atalho global: uma resposta atrasada de um registro anterior nao pode ser
    lida como se fosse do registro atual
  * instalacao nova grava o nome com data (padrao data_hora)
  * cabecalho do painel: os icones nunca cortados e o titulo inteiro
  * ferramenta Tarja: solida, opaca, gravada na imagem
  * galeria: os cartoes que nao mudaram sao reaproveitados, com a miniatura
    viva, e so o que mudou e recriado
  * pre-visualizacao: duplo clique numa imagem da pagina abre o editor dela,
    e a pagina e o Montar voltam atualizados
"""

import os as _os
import sys as _sys

RAIZ = _os.path.dirname(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
_sys.path.insert(0, RAIZ)
_os.chdir(RAIZ)

import os, sys, ctypes, tempfile, shutil, traceback, threading, hashlib, re, time

if not ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4)):
    ctypes.windll.shcore.SetProcessDpiAwareness(2)

import tkinter.font as tkfont
from tkinterdnd2 import TkinterDnD
from PIL import Image, ImageDraw
from gestor.captura import hotkey
from gestor.dados import capture_store, config
from gestor.ui import document_builder, editor, export_preview, theme, workspace
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


for modulo in (workspace, document_builder, editor, export_preview):
    modulo.messagebox = DialogoFalso

tmp = tempfile.mkdtemp(prefix="ge_pendencias_")
capturas = os.path.join(tmp, "Capturas")
os.makedirs(capturas)
nomes = []
for i in range(3):
    nome = "print_2026092%d_1000%02d.png" % (1, i)
    img = Image.new("RGB", (1200, 760), (248, 250, 252))
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, 1199, 80], fill=(30 + 60 * i, 110, 150))
    img.save(os.path.join(capturas, nome))
    capture_store.registrar_captura(os.path.join(capturas, nome))
    capture_store.save_caption(os.path.join(capturas, nome), "Passo %d" % (i + 1))
    nomes.append(nome)

cfg = config.load(tmp)                      # sem config.json: e uma instalacao nova
cfg["pasta_capturas"] = capturas
cfg["copiar_apos_captura"] = False
cfg["som_captura"] = False
cfg["abrir_apos_captura"] = False
config.save(tmp, cfg)

root = TkinterDnD.Tk()
root.report_callback_exception = lambda *a: erros_tk.append(a)
app = AppEvidencias(root, capturas, os.path.join(tmp, "PDF"), RAIZ, tmp)
app.pausar_timer = True
root.deiconify()
root.update()


_relogio = [10_000]


def duplo_clique(w, x, y):
    """Dois cliques no mesmo ponto, com horario (o Tk nao gera Double direto)."""
    for _ in range(2):
        for tipo in ("<ButtonPress-1>", "<ButtonRelease-1>"):
            _relogio[0] += 40
            w.event_generate(tipo, x=x, y=y, time=_relogio[0])
    _relogio[0] += 1500                      # o proximo gesto e outro gesto


def bombear(segundos):
    fim = time.time() + segundos
    while time.time() < fim:
        root.update()
        time.sleep(0.01)


try:
    # ================= bandeja =================
    executado = {}
    app.mostrar_janela = lambda *a: executado.setdefault("abrir", threading.get_ident())
    app.sair_total = lambda *a: executado.setdefault("sair", threading.get_ident())
    principal = threading.get_ident()
    itens_menu = list(app.icon.menu.items)

    def clicar_no_menu():                      # como o pystray faz: na thread dele
        for item in itens_menu:
            item(app.icon)

    t = threading.Thread(target=clicar_no_menu)
    t.start()
    t.join()
    checar(not executado, "o menu da bandeja nao executa nada na thread do pystray")
    bombear(0.5)
    checar(executado.get("abrir") == principal and executado.get("sair") == principal,
           "'Abrir Gestor' e 'Sair' rodam na thread do Tk, pela fila")

    # ================= atalho: resposta atrasada =================
    gerente = hotkey.HotkeyManager(root)
    gerente._respostas.put((999, None))       # resposta velha de um registro que desistiu
    chamados = []
    try:
        gerente.registrar("teste", 0x7B, hotkey.MOD_CONTROL | hotkey.MOD_ALT | hotkey.MOD_SHIFT,
                          lambda: chamados.append(1))
        meu_id = gerente._registros["teste"][0]
        checar(meu_id != 999 and meu_id in gerente._callbacks and 999 not in gerente._callbacks,
               "a resposta atrasada (id 999) nao e confundida com a do registro atual")
    except RuntimeError as e:
        # combinacao tomada por outro programa nesta maquina: o que importa e
        # nao ter usado a resposta velha (que dizia "sucesso")
        checar("em uso" in str(e), "registro recusado de verdade, nao pela resposta velha")
    gerente.parar()
    bombear(0.2)

    # ================= nome com data em instalacao nova =================
    checar(config.PADRAO["padrao_nome"] == "data_hora", "o padrao de fabrica e data_hora")
    antes = set(os.listdir(capturas))
    app._salvar_captura(Image.new("RGB", (200, 120), (5, 5, 5)))
    root.update()
    novos = [n for n in set(os.listdir(capturas)) - antes
             if n.endswith(".png") and not n.endswith(".raw.png")]
    checar(len(novos) == 1 and re.match(r"^print_\d{8}_\d{6}(_\d+)?\.png$", novos[0]),
           "uma captura nova numa instalacao nova leva a data no nome (%s)" % novos)
    nova_captura = novos[0] if novos else None

    # ================= cabecalho do painel =================
    root.geometry("460x820")
    bombear(0.4)
    titulo = app._titulo_painel
    fonte = tkfont.Font(font=titulo.cget("font"))
    checar(fonte.measure(titulo.cget("text")) <= titulo.winfo_width(),
           "o titulo do painel cabe inteiro (%d px de texto em %d px)"
           % (fonte.measure(titulo.cget("text")), titulo.winfo_width()))
    cabecalho = titulo.master
    direita = cabecalho.winfo_rootx() + cabecalho.winfo_width()
    icones = [w for w in cabecalho.winfo_children() if w is not titulo]
    checar(all(w.winfo_rootx() >= titulo.winfo_rootx() + titulo.winfo_width() - 1
               and w.winfo_rootx() + w.winfo_width() <= direita
               and w.winfo_width() >= w.winfo_reqwidth()
               for w in icones),
           "nenhum icone sai cortado nem invade o titulo (%d icones)" % len(icones))

    # ================= Tarja =================
    checar("tarja" in [n for n, _, _ in editor.FERRAMENTAS_COLUNA],
           "a Tarja esta na coluna de ferramentas")
    base = Image.new("RGBA", (300, 200), (250, 250, 250, 255))
    d = ImageDraw.Draw(base)
    d.text((60, 90), "CPF 123.456.789-00", fill=(0, 0, 0))
    composto = editor.render_composite(base, [{"id": 1, "tool": "tarja",
                                               "coords": [50, 80, 250, 120], "color": "#E8590C",
                                               "width": 4, "dash": False, "visible": True}])
    regiao = composto.crop((50, 80, 250, 120))
    checar({cor for _, cor in regiao.getcolors(1 << 16)} == {editor.COR_TARJA},
           "a Tarja cobre a regiao com uma cor so, sem resto do texto por baixo")
    checar(composto.getpixel((10, 10)) == (250, 250, 250), "e nao mexe fora dela")
    caminho_ed = os.path.join(capturas, nomes[0])
    ed = app.abrir_editor(caminho_ed)
    ed.update()
    bombear(0.3)
    ed._selecionar_ferramenta("tarja")
    x1, y1 = ed._img_to_canvas(100, 300)
    x2, y2 = ed._img_to_canvas(500, 420)
    ed.canvas.event_generate("<ButtonPress-1>", x=int(x1), y=int(y1))
    ed.canvas.event_generate("<B1-Motion>", x=int(x2), y=int(y2))
    ed.canvas.event_generate("<ButtonRelease-1>", x=int(x2), y=int(y2))
    ed.update()
    tarjas = [s for s in ed.shapes if s["tool"] == "tarja"]
    checar(len(tarjas) == 1, "arrastar com a Tarja cria uma tarja")
    checar(ed._hit_test(300, 360) == (tarjas[0]["id"] if tarjas else None),
           "clicar no meio da tarja a seleciona (para mover ou apagar)")
    ed.gravar_e_fechar()
    root.update()
    with Image.open(caminho_ed) as im:
        checar(im.convert("RGB").getpixel((300, 360)) == editor.COR_TARJA,
               "a tarja vai para o PNG gravado")

    # ================= galeria: reaproveitamento =================
    app.filtro_atual = "tudo"
    app.modo_visualizacao = "detalhes"
    app.atualizar_galeria()
    root.update()
    antes_cards = {n: e[1] for n, e in app._cache_cards.items()}
    app.atualizar_galeria()
    root.update()
    mesmos = [n for n, e in app._cache_cards.items() if antes_cards.get(n) is e[1]]
    checar(len(mesmos) == len(antes_cards) and mesmos,
           "atualizar sem mudar nada reaproveita todos os cartoes (%d/%d)"
           % (len(mesmos), len(antes_cards)))
    vivas = 0
    for n, (_, card, refs) in app._cache_cards.items():
        # so a miniatura (empacotada com pack); a marca de selecao usa place e
        # a imagem dela e compartilhada, sempre viva - conta-la mascarava a falha
        rotulos = [w for w in card.winfo_children()[0].winfo_children()
                   if w.winfo_class() == "Label" and str(w.cget("image"))
                   and w.winfo_manager() == "pack"]
        for r in rotulos:
            try:
                root.tk.call("image", "width", str(r.cget("image")))
                vivas += 1
            except Exception:
                pass
    checar(vivas == len(app._cache_cards),
           "cada cartao reaproveitado continua com a miniatura viva (%d de %d)"
           % (vivas, len(app._cache_cards)))
    capture_store.save_caption(os.path.join(capturas, nomes[1]), "Legenda trocada")
    app.atualizar_galeria()
    root.update()
    checar(app._cache_cards[nomes[1]][1] is not antes_cards[nomes[1]],
           "o cartao cuja legenda mudou e recriado")
    checar(all(app._cache_cards[n][1] is antes_cards[n] for n in antes_cards if n != nomes[1]
               and n != nomes[0]),
           "e os outros continuam os mesmos")
    item = next(i for i in capture_store.list_captures(capturas) if i["name"] == nomes[1])
    checar(item["caption"] == "Legenda trocada",
           "a listagem enxerga a legenda nova (o cache de leitura se invalida pelo .json)")
    app.arquivos_selecionados.add(nomes[2])
    app.atualizar_galeria()
    root.update()
    t_ = theme.get(app.modo_escuro)
    checar(str(app._cache_cards[nomes[2]][1].cget("bg")) == t_["accent_bg"],
           "um cartao reaproveitado mostra a selecao atual")
    app.arquivos_selecionados.clear()
    for modo in ("grade", "blocos", "detalhes"):
        app.modo_visualizacao = modo
        app.atualizar_galeria()
        root.update()
        app.atualizar_galeria()
        root.update()
    checar(not erros_tk, "trocar de visao (pack <-> grid) nao gera erro")
    checar(nova_captura in app._cache_cards, "a captura nova aparece na galeria")

    # ================= duplo clique na pagina da previa =================
    janela = document_builder.MontarDocumento(app, nomes)
    janela.update()
    janela._pre_visualizar()
    root.update()
    previa = next(w for w in root.winfo_children()
                  if isinstance(w, export_preview.PreVisualizarExportar))
    bombear(0.3)
    alvo = janela.passos[1]["caminho"]
    entrada = next(e for e in previa._mapa if e[5] == alvo)
    previa.pagina_atual = entrada[0]
    previa._render_pagina()
    bombear(0.2)
    rotulo = previa.lbl_imagem_pagina
    escala_x = previa.pagina_w / export_preview.pdf_export.PAGE_W
    escala_y = previa.pagina_h / export_preview.pdf_export.PAGE_H
    dx = (rotulo.winfo_width() - previa.pagina_w) / 2
    dy = (rotulo.winfo_height() - previa.pagina_h) / 2
    cx = int(dx + (entrada[1] + entrada[3] / 2) * escala_x)
    cy = int(dy + (entrada[2] + entrada[4] / 2) * escala_y)
    checar(previa._imagem_em(cx, cy) == alvo, "o centro da imagem na tela aponta o passo certo")
    checar(previa._imagem_em(3, 3) is None, "a margem da pagina nao aponta imagem nenhuma")
    rotulo.event_generate("<Motion>", x=cx, y=cy)
    root.update()
    checar(str(rotulo.cget("cursor")) == "hand2", "sobre a imagem o cursor vira mao")
    rotulo.event_generate("<Motion>", x=3, y=3)
    root.update()
    checar(str(rotulo.cget("cursor")) == "", "fora dela volta ao normal")
    duplo_clique(rotulo, 3, 3)
    root.update()
    checar(previa._editor is None, "duplo clique fora das imagens nao abre nada")

    pagina_antes = hashlib.md5(previa.imagem_da_pagina(previa.pagina_atual).tobytes()).hexdigest()
    duplo_clique(rotulo, cx, cy)
    root.update()
    ed = previa._editor
    checar(ed is not None and ed.caminho_img == alvo,
           "duplo clique na imagem abre o editor dela")
    checar(int(previa.attributes("-disabled")) == 1 and int(janela.attributes("-disabled")) == 1,
           "a previa e o Montar ficam bloqueados enquanto edita")
    duplo_clique(rotulo, cx, cy)
    root.update()
    checar(previa._editor is ed, "e nao abre um segundo editor")
    ed.txt_legenda.delete("1.0", "end")
    ed.txt_legenda.insert("1.0", "Legenda editada pela previa")
    ed.shapes.append({"id": 77, "tool": "tarja", "coords": [100, 200, 900, 400],
                      "color": "#E8590C", "width": 4, "dash": False, "visible": True})
    ed._marcar_sujo()
    ed.gravar_e_fechar()
    bombear(0.3)
    pagina_depois = hashlib.md5(previa.imagem_da_pagina(previa.pagina_atual).tobytes()).hexdigest()
    checar(pagina_antes != pagina_depois, "a pagina da previa volta com a imagem editada")
    checar(janela.passos[1]["legenda"] == "Legenda editada pela previa"
           and janela.entries_legenda[1].get("1.0", "end").strip() == "Legenda editada pela previa",
           "o Montar por tras recebe a legenda gravada")
    checar(int(previa.attributes("-disabled")) == 0 and int(janela.attributes("-disabled")) == 0,
           "previa e Montar desbloqueados ao fechar o editor")
    # editor destruido a forca tambem desbloqueia
    rotulo = previa.lbl_imagem_pagina
    duplo_clique(rotulo, cx, cy)
    root.update()
    previa._editor.destroy()
    root.update()
    checar(previa._editor is None and int(previa.attributes("-disabled")) == 0
           and int(janela.attributes("-disabled")) == 0,
           "editor destruido a forca tambem desbloqueia a previa e o Montar")
    previa.fechar()
    janela.destroy()
    root.update()

    checar(not [a for a in avisos if a[0] == "erro"], "nenhuma mensagem de erro")
    checar(not erros_tk, "nenhum erro silencioso do Tk")
    for e in erros_tk:
        print("   erro Tk:", "".join(traceback.format_exception(*e))[-600:])
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
