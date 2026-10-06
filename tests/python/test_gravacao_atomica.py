# -*- coding: utf-8 -*-
"""Gravacao das capturas: atomica, sem sobras e sem fingir que gravou.

Antes, o editor escrevia o .json, o .raw.png e o .png um apos o outro, direto
no destino. Uma falha no meio (disco cheio, arquivo bloqueado pelo Explorer ou
por um antivirus) deixava a captura pela metade, e o editor fechava como se
tivesse gravado.

Cobre:
  * save_png / save_meta: falha na escrita ou na troca preserva a versao
    anterior e nao deixa .tmp para tras
  * save_caption: so grava quando a legenda muda e nao marca como editada
  * o editor diante de uma falha: avisa, continua aberto, mantem a alteracao
    pendente, nao notifica o chamador e nao muda nada em disco
  * list_captures ignora um .tmp esquecido
"""

import os as _os
import sys as _sys

RAIZ = _os.path.dirname(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
_sys.path.insert(0, RAIZ)
_os.chdir(RAIZ)

import os, sys, ctypes, tempfile, shutil, traceback, hashlib, time

if not ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4)):
    ctypes.windll.shcore.SetProcessDpiAwareness(2)

from tkinterdnd2 import TkinterDnD
from PIL import Image
from gestor.dados import capture_store, config
from gestor.ui import editor
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


def hash_arquivo(caminho):
    with open(caminho, "rb") as f:
        return hashlib.md5(f.read()).hexdigest()


def sobras(pasta):
    return sorted(n for n in os.listdir(pasta) if n.endswith(".tmp"))


tmp = tempfile.mkdtemp(prefix="ge_atomica_")
pasta = os.path.join(tmp, "Capturas")
os.makedirs(pasta)
caminho = os.path.join(pasta, "print_500000.png")
Image.new("RGB", (400, 300), (10, 120, 160)).save(caminho)
capture_store.save_meta(caminho, {"caption": "Original", "caso": "CT-1", "shapes": []})
capture_store.load_meta(caminho)       # cria o .raw.png de uma captura antiga
png0 = hash_arquivo(caminho)
json0 = hash_arquivo(capture_store.json_path(caminho))


class ImagemQueFalha:
    """Escreve parte do arquivo e falha: o disco enchendo no meio da gravacao."""

    def save(self, destino, format=None):
        with open(destino, "wb") as f:
            f.write(b"\x89PNG parcial")
        raise OSError("disco cheio")


try:
    # ---------------- save_png ----------------
    nova = Image.new("RGB", (50, 50), (200, 0, 0))
    capture_store.save_png(nova, caminho)
    checar(Image.open(caminho).size == (50, 50), "save_png grava a imagem nova")
    checar(not sobras(pasta), "save_png bem-sucedido nao deixa .tmp")
    Image.new("RGB", (400, 300), (10, 120, 160)).save(caminho)
    png0 = hash_arquivo(caminho)

    try:
        capture_store.save_png(ImagemQueFalha(), caminho)
        levantou = False
    except OSError:
        levantou = True
    checar(levantou, "falha na escrita do PNG e propagada, nao engolida")
    checar(hash_arquivo(caminho) == png0, "falha na escrita preserva a versao anterior")
    checar(not sobras(pasta), "falha na escrita nao deixa o .tmp parcial para tras")

    original_replace = os.replace
    capture_store.os.replace = lambda a, b: (_ for _ in ()).throw(PermissionError("em uso"))
    try:
        try:
            capture_store.save_png(nova, caminho)
            levantou = False
        except PermissionError:
            levantou = True
    finally:
        capture_store.os.replace = original_replace
    checar(levantou, "falha na troca (arquivo em uso) e propagada")
    checar(hash_arquivo(caminho) == png0, "falha na troca preserva a versao anterior")
    checar(not sobras(pasta), "falha na troca nao deixa o .tmp para tras")

    # ---------------- save_meta ----------------
    try:
        capture_store.save_meta(caminho, {"caption": "Nova", "shapes": [{"x": {1, 2}}]})
        levantou = False
    except TypeError:
        levantou = True
    checar(levantou, "metadado nao serializavel e propagado")
    checar(hash_arquivo(capture_store.json_path(caminho)) == json0,
           "falha ao gravar o JSON preserva o anterior")
    checar(not sobras(pasta), "falha ao gravar o JSON nao deixa .tmp parcial")

    # ---------------- save_caption ----------------
    meta = capture_store.load_meta(caminho)
    editada_em = meta["edited_at"]
    checar(bool(editada_em), "pre-condicao: a captura ja esta marcada como editada")
    mtime = os.path.getmtime(capture_store.json_path(caminho))
    time.sleep(0.05)
    checar(capture_store.save_caption(caminho, "Original") is False,
           "save_caption com a mesma legenda devolve False")
    checar(os.path.getmtime(capture_store.json_path(caminho)) == mtime,
           "e nao reescreve o arquivo")
    checar(capture_store.save_caption(caminho, "Outra legenda") is True,
           "save_caption com legenda nova devolve True")
    meta = capture_store.load_meta(caminho)
    checar(meta["caption"] == "Outra legenda" and meta["caso"] == "CT-1",
           "grava a legenda e preserva o resto do metadado")
    checar(meta["edited_at"] == editada_em, "nao altera o horario de edicao")

    virgem = os.path.join(pasta, "print_500001.png")
    Image.new("RGB", (40, 40)).save(virgem)
    checar(capture_store.save_caption(virgem, "") is False
           and not os.path.exists(capture_store.json_path(virgem)),
           "legenda vazia numa captura sem metadado nao cria .json")
    capture_store.save_caption(virgem, "Primeira")
    checar(capture_store.load_meta(virgem)["caption"] == "Primeira"
           and not capture_store.load_meta(virgem)["edited_at"],
           "legenda numa captura nunca editada nao a marca como editada")

    # captura antiga: a legenda estava num .txt
    antiga = os.path.join(pasta, "print_500002.png")
    Image.new("RGB", (40, 40)).save(antiga)
    with open(capture_store.txt_path(antiga), "w", encoding="utf-8") as f:
        f.write("Legenda do txt")
    checar(capture_store.load_meta(antiga)["caption"] == "Legenda do txt",
           "pre-condicao: legenda importada do .txt")
    capture_store.save_caption(antiga, "Legenda nova")
    checar(capture_store.load_meta(antiga)["caption"] == "Legenda nova"
           and not os.path.exists(capture_store.txt_path(antiga)),
           "regravar a legenda de uma captura antiga migra o .txt para o .json")

    # ---------------- list_captures ignora .tmp esquecido ----------------
    with open(os.path.join(pasta, "print_500003.png.tmp"), "wb") as f:
        f.write(b"resto de uma gravacao interrompida")
    nomes_listados = [i["name"] for i in capture_store.list_captures(pasta)]
    checar(not any(n.endswith(".tmp") for n in nomes_listados),
           "um .tmp esquecido nao aparece como captura")
    os.remove(os.path.join(pasta, "print_500003.png.tmp"))

    # ---------------- o editor diante da falha ----------------
    cfg = config.load(tmp)
    cfg["pasta_capturas"] = pasta
    config.save(tmp, cfg)
    root = TkinterDnD.Tk()
    root.report_callback_exception = lambda *a: erros_tk.append(a)
    app = AppEvidencias(root, pasta, os.path.join(tmp, "PDF"), RAIZ, tmp)
    app.pausar_timer = True
    root.deiconify()
    root.update()

    chamadas = []
    ed = editor.EditorImagem(root, caminho, lambda: chamadas.append(1), False, app=app)
    ed.update()
    ed.shapes.append({"id": 1, "tool": "retangulo", "coords": [20, 20, 200, 150],
                      "color": "#E8590C", "width": 4, "dash": False, "visible": True})
    ed._marcar_sujo()
    png1 = hash_arquivo(caminho)
    json1 = hash_arquivo(capture_store.json_path(caminho))
    raw1 = hash_arquivo(capture_store.raw_path(caminho))

    original_save_png = capture_store.save_png

    def save_png_falha(imagem, destino):
        raise OSError("disco cheio")

    capture_store.save_png = save_png_falha
    try:
        resultado = ed.gravar()
        ed.gravar_e_fechar()
    finally:
        capture_store.save_png = original_save_png
    root.update()

    checar(resultado is False, "gravar() devolve False quando falha")
    checar(any(a[0] == "erro" and "disco cheio" in a[2] for a in avisos),
           "o usuario e avisado, com o motivo")
    checar(bool(ed.winfo_exists()), "o editor continua aberto depois da falha")
    checar(ed.sujo is True, "a alteracao continua marcada como pendente")
    checar(chamadas == [], "o chamador nao e avisado de uma gravacao que nao houve")
    checar(hash_arquivo(caminho) == png1 and hash_arquivo(capture_store.json_path(caminho)) == json1
           and hash_arquivo(capture_store.raw_path(caminho)) == raw1,
           "PNG, original e JSON seguem intactos em disco")
    checar(len(ed.shapes) == 1, "a anotacao nao e perdida na tela")
    checar(not sobras(pasta), "nenhum .tmp sobrou")

    checar(ed.gravar() is True and chamadas == [1],
           "passada a falha, gravar() funciona e avisa o chamador uma vez")
    checar(ed.sujo is False, "e a alteracao deixa de estar pendente")
    checar(len(capture_store.load_meta(caminho)["shapes"]) == 1,
           "a anotacao foi para o disco")
    checar(not erros_tk, "nenhum erro silencioso do Tk")
    for e in erros_tk:
        print("   erro Tk:", "".join(traceback.format_exception(*e))[-500:])
    ed.destroy()
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
