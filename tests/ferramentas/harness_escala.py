"""Fotografa as telas com a fonte no menor e no maior tamanho.

Usa um DATA_DIR temporario: nao encosta no config.json do usuario.
"""

import os as _os
import sys as _sys

# Raiz do projeto a partir deste arquivo: tests/ferramentas/x.py -> duas pastas acima
RAIZ = _os.path.dirname(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
_sys.path.insert(0, RAIZ)
_os.chdir(RAIZ)
SAIDA = _os.path.join(RAIZ, "tests", "_saida")
_os.makedirs(SAIDA, exist_ok=True)

import os
import shutil
import sys
import tempfile
import traceback

import ctypes
try:
    if not ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4)):
        raise OSError
except Exception:
    ctypes.windll.shcore.SetProcessDpiAwareness(1)

SAIDA = SAIDA
LOG = open(os.path.join(SAIDA, "escala.log"), "w", buffering=1)

from PIL import ImageGrab
from tkinterdnd2 import TkinterDnD
from gestor.dados import capture_store
from gestor.dados import config
from gestor.ui import document_builder
from gestor.ui import theme
from gestor.ui.workspace import AppEvidencias

ESCALA = sys.argv[1] if len(sys.argv) > 1 else "padrao"
SUFIXO = sys.argv[2] if len(sys.argv) > 2 else ESCALA

tmp = tempfile.mkdtemp(prefix="ge_escala_")
cfg = config.load(tmp)
cfg["escala_fonte"] = ESCALA
cfg["escala_fonte_botao"] = ESCALA
# Capturas sinteticas numa pasta temporaria: apontar para a pasta real da
# maquina exporia evidencia de verdade nas telas geradas por este utilitario.
from PIL import Image as _Image, ImageDraw as _ImageDraw

_capturas = os.path.join(tmp, "Capturas")
os.makedirs(_capturas, exist_ok=True)
for _i in range(3):
    _img = _Image.new("RGB", (1000, 640), (248, 250, 252))
    _d = _ImageDraw.Draw(_img)
    _d.rectangle([0, 0, 999, 60], fill=(11, 114, 133))
    _d.text((24, 26), "Tela de exemplo %d" % (_i + 1), fill=(255, 255, 255))
    _img.save(os.path.join(_capturas, "print_1600%02d.png" % _i))
cfg["pasta_capturas"] = _capturas
config.save(tmp, cfg)


def foto(janela, nome):
    """Forca a janela pro primeiro plano antes de capturar.

    Sem isso o ImageGrab pega o que estiver na frente naquele retangulo —
    numa tentativa anterior a foto saiu com o navegador no lugar do app.
    """
    try:
        janela.attributes("-topmost", True)
        janela.lift()
        janela.focus_force()
        janela.update_idletasks()
        janela.update()
        janela.after(250)
        janela.update()
        x, y = janela.winfo_rootx(), janela.winfo_rooty()
        w, h = janela.winfo_width(), janela.winfo_height()
        if w < 50 or h < 50:
            LOG.write("janela %s pequena: %dx%d\n" % (nome, w, h)); return
        ImageGrab.grab(bbox=(x, y, x + w, y + h)).save(os.path.join(SAIDA, nome))
        LOG.write("foto %s (%dx%d)\n" % (nome, w, h))
        janela.attributes("-topmost", False)
    except Exception:
        LOG.write(traceback.format_exc())


try:
    root = TkinterDnD.Tk()
    app = AppEvidencias(root, os.path.join(tmp, "Capturas"), os.path.join(tmp, "PDF"),
                        RAIZ, tmp)
    app.pausar_timer = True
    app.tempo_limite = 10 ** 9
    LOG.write("escala=%s -> FS_BODY=%d FS_BUTTON=%d CTRL_H=%d\n"
              % (ESCALA, theme.FS_BODY, theme.FS_BUTTON, theme.CTRL_H))
    estado = {}

    def p1():
        app.mostrar_janela(); app.pausar_timer = True
        foto(root, "esc_%s_1_painel.png" % SUFIXO)

    def p2():
        itens = capture_store.list_captures(app.pasta_capturas)
        if itens:
            estado["ed"] = app.abrir_editor(itens[0]["path"])

    def p3():
        if estado.get("ed"):
            foto(estado["ed"], "esc_%s_2_editor.png" % SUFIXO)
            estado["ed"].destroy()

    def p4():
        app.pausar_timer = True
        app.abrir_configuracoes()

    def p5():
        for f in root.winfo_children():
            try:
                if f.winfo_class() == "Toplevel" and f.title() == "Configurações":
                    foto(f, "esc_%s_3_config.png" % SUFIXO); f.destroy(); return
            except Exception:
                pass

    def p6():
        nomes = [i["name"] for i in capture_store.list_captures(app.pasta_capturas)][:2]
        if nomes:
            estado["doc"] = document_builder.MontarDocumento(app, nomes)

    def p7():
        if estado.get("doc"):
            foto(estado["doc"], "esc_%s_4_documento.png" % SUFIXO)
        root.quit()

    for ms, fn in ((900, p1), (2200, p2), (4200, p3), (5000, p4),
                    (7000, p5), (7800, p6), (10000, p7)):
        root.after(ms, fn)
    root.after(20000, root.quit)
    root.mainloop()
    LOG.write("fim\n")
except Exception:
    LOG.write(traceback.format_exc())
finally:
    shutil.rmtree(tmp, ignore_errors=True)
