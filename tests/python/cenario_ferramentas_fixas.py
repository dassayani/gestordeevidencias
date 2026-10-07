# -*- coding: utf-8 -*-
"""Editor: ferramenta continua ativa, seta afinada, Borrar com desfoque.

- desenhar varias setas seguidas sem voltar ao botao; cor e espessura valem
  para as proximas, e so o Mover mexe numa forma ja feita;
- Apagar continua ativo, apaga uma atras da outra e marca de vermelho o alvo;
- Texto edita o texto clicado, Passo numera em sequencia, Esc volta ao Mover,
  Recorte volta ao Mover;
- seta nova afina para a cauda, Borrar novo e desfoque regulado pela
  intensidade, e as formas antigas (sem a marca de estilo) saem como antes,
  mesmo depois de gravar de novo.
"""

import os as _os
import sys as _sys

RAIZ = _os.path.dirname(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
_sys.path.insert(0, RAIZ)
_os.chdir(RAIZ)

import os, sys, ctypes, tempfile, shutil, traceback

if not ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4)):
    ctypes.windll.shcore.SetProcessDpiAwareness(2)

from tkinterdnd2 import TkinterDnD
from tkinter import messagebox
from PIL import Image, ImageChops, ImageDraw, ImageFont, ImageStat
from gestor.dados import capture_store
from gestor.dados import config
from gestor.sistema import utils
from gestor.ui import editor as mod_editor
from gestor.ui.workspace import AppEvidencias

falhas = []
erros_tk = []


def checar(condicao, descricao):
    print(("OK:     " if condicao else "FALHOU: ") + descricao)
    if not condicao:
        falhas.append(descricao)


class Evento:
    def __init__(self, x, y):
        self.x = x
        self.y = y
        self.state = 0
        self.num = 1


def tela(ed, ix, iy):
    cx, cy = ed._img_to_canvas(ix, iy)
    return Evento(int(round(cx)), int(round(cy)))


def arrastar(ed, x1, y1, x2, y2):
    """Traco com a ferramenta que estiver ativa (sem clicar no botao)."""
    ed.on_press(tela(ed, x1, y1))
    for i in range(1, 6):
        ed.on_drag(tela(ed, x1 + (x2 - x1) * i / 5, y1 + (y2 - y1) * i / 5))
    ed.on_release(tela(ed, x2, y2))
    ed.update()


def clicar(ed, ix, iy):
    ed.on_press(tela(ed, ix, iy))
    ed.on_release(tela(ed, ix, iy))
    ed.update()


def imagem_com_texto(tamanho=(900, 600)):
    img = Image.new("RGB", tamanho, (245, 248, 250))
    d = ImageDraw.Draw(img)
    try:
        fonte = ImageFont.truetype("segoeui.ttf", 22)
    except Exception:
        fonte = ImageFont.load_default()
    for i in range(6):
        d.text((480, 330 + i * 28), "CPF 123.456.789-0%d" % i, font=fonte, fill=(20, 20, 20))
    return img


tmp = tempfile.mkdtemp(prefix="ge_fixas_")
capturas = os.path.join(tmp, "Capturas")
os.makedirs(capturas)
alvo = os.path.join(capturas, "print_100000.png")
imagem_com_texto().save(alvo)
antigo = os.path.join(capturas, "print_100100.png")
imagem_com_texto().save(antigo)

# print "de antes": seta e borrao gravados sem a marca de estilo
FORMAS_ANTIGAS = [
    {"id": 1, "tool": "seta", "coords": [100, 100, 380, 220], "color": "#E8590C",
     "width": 6, "dash": False, "visible": True},
    {"id": 2, "tool": "borrao", "coords": [470, 320, 760, 500], "color": "#E8590C",
     "width": 4, "dash": False, "visible": True},
]
capture_store.save_meta(antigo, {"caption": "", "caso": "", "shapes": FORMAS_ANTIGAS})

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

askyesno_original = messagebox.askyesno
try:
    ed = app.abrir_editor(alvo)
    ed.update()
    ed._redraw_canvas()
    ed.update()

    # ---- seta: tres seguidas sem voltar ao botao ----
    ed._selecionar_ferramenta("seta")
    ed.update()
    for i in range(3):
        arrastar(ed, 60, 60 + i * 60, 300, 90 + i * 60)
    setas = [s for s in ed.shapes if s["tool"] == "seta"]
    checar(len(setas) == 3, "tres setas seguidas com um clique so no botao (%d)" % len(setas))
    checar(ed.ferramenta == "seta", "depois de desenhar a ferramenta continua Seta")
    checar(ed.selected_id is None, "a seta recem-feita nao fica selecionada")
    checar(all(s.get("estilo") == mod_editor.ESTILO_SETA for s in setas),
           "setas novas levam a marca do estilo afinado")

    # ---- cor/espessura sem selecao valem para as proximas ----
    cor_nova = "#1C7ED6"
    ed._escolher_cor_predefinida(cor_nova)
    ed._on_espessura_change(9)
    checar(all(s["color"] != cor_nova and s["width"] != 9 for s in setas),
           "trocar cor/espessura sem selecao nao mexe nas setas ja feitas")
    arrastar(ed, 60, 300, 300, 330)
    ultima = ed.shapes[-1]
    checar(ultima["color"] == cor_nova and ultima["width"] == 9,
           "a proxima seta sai com a cor e a espessura escolhidas")

    # ---- Mover: so ele ajusta uma forma ja feita ----
    ed._selecionar_ferramenta("mover")
    ed.update()
    checar(str(ed.canvas.cget("cursor")) == "fleur", "no Mover o cursor e o de mover")
    primeira = setas[0]
    clicar(ed, 180, 75)
    checar(ed.selected_id == primeira["id"], "o Mover seleciona a seta clicada")
    ed._escolher_cor_predefinida("#2F9E44")
    ed._on_espessura_change(12)
    checar(primeira["color"] == "#2F9E44" and primeira["width"] == 12,
           "com a seta selecionada no Mover, cor e espessura mudam nela")

    # ---- Esc volta ao Mover ----
    ed._selecionar_ferramenta("elipse")
    ed.update()
    ed.canvas.focus_set()
    ed.update()
    ed.event_generate("<Escape>")
    ed.update()
    checar(ed.ferramenta == "mover", "Esc volta para o Mover")

    # ---- Passo numera em sequencia ----
    ed._selecionar_ferramenta("passo")
    for i in range(3):
        clicar(ed, 820, 60 + i * 50)
    numeros = [s.get("step_n") for s in ed.shapes if s["tool"] == "passo"]
    checar(numeros == [1, 2, 3] and ed.ferramenta == "passo",
           "Passo continua ativo e numera 1, 2, 3 (%s)" % numeros)

    # ---- Texto: clicar num texto existente edita, nao cria outro ----
    ed._selecionar_ferramenta("texto")
    ed.update()
    clicar(ed, 60, 420)
    ed._editor_texto["widget"].insert(0, "Primeiro")
    ed._encerrar_editor_texto(gravar=True)
    ed.update()
    textos = [s for s in ed.shapes if s["tool"] == "texto"]
    checar(len(textos) == 1 and ed.ferramenta == "texto", "Texto criado e ferramenta continua Texto")
    clicar(ed, 70, 432)
    checar(ed._editor_texto is not None and ed._editor_texto["sid"] == textos[0]["id"],
           "com o Texto ativo, clicar no texto existente abre ele para editar")
    ed._editor_texto["widget"].event_generate("<Escape>")
    ed.update()
    checar(ed._editor_texto is None and ed.ferramenta == "texto",
           "Esc na caixa de texto cancela o texto sem trocar a ferramenta")
    checar(len([s for s in ed.shapes if s["tool"] == "texto"]) == 1, "nenhum texto a mais")

    # ---- Emoji repete ----
    ed._ativar_ferramenta("emoji")
    checar(ed.lbl_rotulo_espessura.cget("text") == "Tamanho",
           "com a ferramenta Emoji o controle vira 'Tamanho'")
    ed._on_espessura_change(10)
    clicar(ed, 700, 60)
    clicar(ed, 760, 60)
    emojis = [s for s in ed.shapes if s["tool"] == "emoji"]
    checar(len(emojis) == 2 and ed.ferramenta == "emoji", "dois emojis seguidos")
    checar(all(s["tamanho"] == 20 + (10 - 2) * 7 for s in emojis),
           "o tamanho escolhido sem selecao vale para os proximos emojis")

    # ---- Borrar: desfoque com intensidade ----
    ed._selecionar_ferramenta("borrao")
    checar(ed.lbl_rotulo_espessura.cget("text") == "Intensidade",
           "no Borrar o controle se chama 'Intensidade'")
    ed._selecionar_ferramenta("seta")
    checar(ed.lbl_rotulo_espessura.cget("text") == "Espessura",
           "na Seta o controle volta a ser 'Espessura'")
    ed._selecionar_ferramenta("borrao")
    ed._on_espessura_change(3)
    arrastar(ed, 470, 320, 760, 500)
    borrao = ed.shapes[-1]
    checar(borrao["tool"] == "borrao" and borrao.get("estilo") == mod_editor.ESTILO_BORRAO
           and borrao["width"] == 3, "borrao novo leva a marca do desfoque e a intensidade")
    checar(ed.ferramenta == "borrao", "Borrar continua ativo depois de desenhar")

    base = Image.open(alvo).convert("RGB")
    caixa = (480, 330, 750, 490)

    def desvio(img):
        return sum(ImageStat.Stat(img.crop(caixa).convert("L")).stddev)

    fraco = mod_editor.render_composite(base, [dict(borrao, width=2)])
    forte = mod_editor.render_composite(base, [dict(borrao, width=14)])
    pixelado = mod_editor.render_composite(base, [dict(borrao, estilo=None)])
    checar(desvio(forte) < desvio(fraco) < desvio(base),
           "mais intensidade, mais desfoque (desvio %.1f < %.1f < %.1f)"
           % (desvio(forte), desvio(fraco), desvio(base)))
    esperado = base.copy()
    utils.desfocar_regiao(esperado, borrao["coords"], 2)
    checar(ImageChops.difference(fraco.crop(caixa), esperado.crop(caixa)).getbbox() is None,
           "o PNG sai com o desfoque da intensidade gravada")
    # pixelado = blocos de 12px de cor unica; desfocado nao tem esses blocos
    bloco = fraco.crop((482, 332, 494, 344)).convert("L")
    checar(len(bloco.getcolors()) > 1, "o borrao novo nao e pixelado (sem quadradinhos)")
    bloco_px = pixelado.crop((486, 336, 490, 340)).convert("L")
    checar(len(bloco_px.getcolors()) == 1, "sem a marca, o borrao continua pixelado")

    # prévia na tela = o que vai para o PNG
    ed._redraw_canvas()
    ed.update()
    previa = ed._desfoque_da_previa(borrao)
    no_png = mod_editor.render_composite(ed.img_raw, [borrao]).crop(
        tuple(int(round(v)) for v in mod_editor._ordenado(borrao["coords"])))
    checar(ImageChops.difference(previa.convert("RGB"), no_png).getbbox() is None,
           "a previa do desfoque na tela e a mesma do PNG")

    # ---- seta afinada: cauda fina, perto da cabeca grossa, cabeca larga ----
    fundo = Image.new("RGB", (600, 200), (255, 255, 255))
    seta = {"id": 1, "tool": "seta", "coords": [40, 100, 560, 100], "color": "#000000",
            "width": 6, "dash": False, "visible": True, "estilo": mod_editor.ESTILO_SETA}

    def espessura_em(img, x):
        coluna = [img.getpixel((x, y))[0] for y in range(200)]
        return sum(1 for v in coluna if v < 128)

    nova = mod_editor.render_composite(fundo, [seta])
    cauda, perto, cabeca = espessura_em(nova, 60), espessura_em(nova, 480), espessura_em(nova, 535)
    checar(0 < cauda < perto < cabeca,
           "a seta afina para a cauda e a cabeca e a parte mais larga (%d < %d < %d)"
           % (cauda, perto, cabeca))
    checar(cabeca >= 6 * 3, "a cabeca e grande (%d px para espessura 6)" % cabeca)
    sem_marca = dict(seta)
    del sem_marca["estilo"]
    velha = mod_editor.render_composite(fundo, [sem_marca])
    ref = fundo.copy()
    utils.draw_arrow(ImageDraw.Draw(ref), sem_marca["coords"], (0, 0, 0), 6)
    checar(ImageChops.difference(velha, ref).getbbox() is None,
           "seta sem a marca sai exatamente como a seta antiga")
    checar(espessura_em(velha, 60) == espessura_em(velha, 400),
           "a seta antiga continua com a linha reta (mesma espessura)")

    # ---- Apagar: continua ativo, um atras do outro, com marca do alvo ----
    ed._selecionar_ferramenta("retangulo")
    arrastar(ed, 100, 440, 400, 580)
    quadro = ed.shapes[-1]
    ed._selecionar_ferramenta("seta")
    arrastar(ed, 150, 500, 350, 520)
    seta_dentro = ed.shapes[-1]
    ed._selecionar_ferramenta("apagar")
    ed.update()
    checar(str(ed.canvas.cget("cursor")) == "X_cursor", "no Apagar o cursor e o X")
    ed._on_mouse_move(tela(ed, 250, 510))
    checar(ed._sob_o_apagar == seta_dentro["id"] and ed.canvas.find_withtag("sob_apagar"),
           "passar o mouse marca de vermelho o que o clique vai apagar")
    clicar(ed, 250, 510)
    checar(ed._get_shape(seta_dentro["id"]) is None and ed._get_shape(quadro["id"]) is not None,
           "clicar na seta dentro do quadro apaga a seta, nao o quadro")
    clicar(ed, 250, 470)
    checar(ed._get_shape(quadro["id"]) is None,
           "clicar no meio do quadro (longe da borda) apaga o quadro")
    checar(ed.ferramenta == "apagar", "o Apagar continua ativo depois de apagar")
    antes = len(ed.shapes)
    clicar(ed, 5, 595)
    checar(len(ed.shapes) == antes, "clicar no vazio com o Apagar nao apaga nada")
    ed._on_mouse_move(tela(ed, 5, 595))
    checar(not ed.canvas.find_withtag("sob_apagar"), "longe das formas a marca vermelha some")

    # ---- Recorte volta ao Mover ----
    messagebox.askyesno = lambda *a, **k: True
    ed._selecionar_ferramenta("recorte")
    arrastar(ed, 10, 10, 880, 590)
    checar(ed.img_raw.size == (870, 580), "o recorte foi aplicado (%s)" % (ed.img_raw.size,))
    checar(ed.ferramenta == "mover" and ed.botoes_ferramenta["mover"] is not None,
           "depois de recortar o editor volta ao Mover")
    messagebox.askyesno = askyesno_original

    ed.gravar()
    ed.update()
    gravadas = capture_store.load_meta(alvo)["shapes"]
    checar(any(s.get("estilo") == mod_editor.ESTILO_SETA for s in gravadas)
           and any(s.get("estilo") == mod_editor.ESTILO_BORRAO for s in gravadas),
           "a marca de estilo vai para o .json")
    ed.fechar_e_voltar()
    root.update()

    # ---- print antigo: reabrir e gravar nao muda a aparencia ----
    ed2 = app.abrir_editor(antigo)
    ed2.update()
    ed2.txt_legenda.insert("1.0", "legenda nova")
    ed2.gravar()
    ed2.update()
    meta_antiga = capture_store.load_meta(antigo)
    checar(all("estilo" not in s for s in meta_antiga["shapes"]),
           "gravar de novo um print antigo nao marca as formas antigas")
    ref_antiga = Image.open(antigo).convert("RGB")
    raw = capture_store.load_raw_image(antigo)
    esperado_antigo = raw.convert("RGB")
    d = ImageDraw.Draw(esperado_antigo)
    utils.draw_arrow(d, FORMAS_ANTIGAS[0]["coords"], utils.hex_to_rgb("#E8590C"), 6)
    utils.pixelate_region(esperado_antigo, FORMAS_ANTIGAS[1]["coords"])
    checar(ImageChops.difference(ref_antiga, esperado_antigo).getbbox() is None,
           "o print antigo regravado tem a seta e o borrao de antes, pixel a pixel")
    ed2.fechar_e_voltar()
    root.update()

    checar(not erros_tk, "nenhum erro silencioso do Tk")
    if erros_tk:
        print(erros_tk[0][:1500])
except Exception:
    falhas.append("erro: " + traceback.format_exc())
finally:
    messagebox.askyesno = askyesno_original

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
os._exit(0)
