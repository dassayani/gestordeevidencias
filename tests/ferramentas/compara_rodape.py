# -*- coding: utf-8 -*-
"""Previa x documento, lado a lado, depois do rodape unificado.

Nomes de saida com marca de tempo: leitura de imagem velha ja me enganou antes.
"""

import os as _os
import sys as _sys

# Raiz do projeto a partir deste arquivo: tests/ferramentas/x.py -> duas pastas acima
RAIZ = _os.path.dirname(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
_sys.path.insert(0, RAIZ)
_os.chdir(RAIZ)
SAIDA = _os.path.join(RAIZ, "tests", "_saida")
_os.makedirs(SAIDA, exist_ok=True)

import sys, os, ctypes, time
if not ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4)):
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
import win32gui, win32con
from tkinterdnd2 import TkinterDnD
from PIL import Image, ImageDraw, ImageGrab
from screeninfo import get_monitors
import main as m, workspace, export_preview, pdf_export
import fitz

SP = SAIDA
TAG = time.strftime("%H%M%S")
amostra = os.path.join(SP, f"amostra_{TAG}.png")
im = Image.new("RGB", (1200, 700), (246, 249, 251))
d = ImageDraw.Draw(im)
d.rectangle([0, 0, 1199, 699], outline=(30, 90, 120), width=6)
for i in range(6):
    d.rectangle([40, 40 + i * 100, 1160, 110 + i * 100], outline=(120, 140, 160), width=3)
im.save(amostra)

LONGA = ("Ao clicar no botao Confirmar da tela de fechamento, o sistema deve "
         "validar o saldo disponivel, conferir a data de competencia, registrar "
         "o log de auditoria e so entao apresentar a mensagem de sucesso ao "
         "usuario, mantendo o botao desabilitado durante o processamento.")
CAPA = {"titulo": "Validacao de fechamento", "caso": "CT-4471",
        "autor": "QA - Dasayani", "data": "21/09/2026", "ambiente": "Homologacao"}
# tres passos: garante mais de uma pagina, para conferir a numeracao do rodape
PASSOS = [{"caminho": amostra, "legenda": LONGA},
          {"caminho": amostra, "legenda": "Tela inicial do modulo"},
          {"caminho": amostra, "legenda": "Confirmacao apresentada ao usuario"}]
OPCOES = {"borda_ativada": True, "borda_cor": "#0B7285", "cor_destaque": "#0B7285",
          "numerar_passos": True, "fonte_legenda": "Arial"}

root = TkinterDnD.Tk()
app = workspace.AppEvidencias(root, m.PASTA_CAPTURAS, m.PASTA_PDFS, m.BASE_DIR, m.DATA_DIR)
app.pausar_timer = True
root.deiconify(); root.update()
mons = get_monitors(); mx = min(a.x for a in mons); my = min(a.y for a in mons)

geradores = {"passo": pdf_export.exportar_passo_a_passo,
             "ficha": pdf_export.exportar_ficha_evidencia,
             "qa": pdf_export.exportar_relatorio_qa}

for modelo in ("passo", "ficha", "qa"):
    pdf = os.path.join(SP, f"rod_{modelo}_{TAG}.pdf")
    geradores[modelo](pdf, CAPA, PASSOS, OPCOES)
    doc = fitz.open(pdf)
    doc[0].get_pixmap(dpi=96).save(os.path.join(SP, f"rod_{modelo}_doc_{TAG}.png"))
    doc.close()

    prev = export_preview.PreVisualizarExportar(app, None, modelo, CAPA, PASSOS, OPCOES)
    prev.update(); time.sleep(1.0); prev.update()
    h = prev.winfo_id(); h = ctypes.windll.user32.GetParent(h) or h
    win32gui.SetWindowPos(h, win32con.HWND_TOPMOST, 0, 0, 0, 0,
                          win32con.SWP_NOMOVE | win32con.SWP_NOSIZE | win32con.SWP_SHOWWINDOW)
    prev.update(); time.sleep(1.0); prev.update()
    mold = prev.moldura
    x0 = mold.winfo_rootx() - mx
    y0 = mold.winfo_rooty() - my
    tela = ImageGrab.grab(all_screens=True)
    tela.crop((x0, y0, x0 + mold.winfo_width(), y0 + mold.winfo_height())).save(
        os.path.join(SP, f"rod_{modelo}_prev_{TAG}.png"))
    prev.destroy(); root.update()

    a = Image.open(os.path.join(SP, f"rod_{modelo}_prev_{TAG}.png"))
    b = Image.open(os.path.join(SP, f"rod_{modelo}_doc_{TAG}.png"))
    alt = 700
    a = a.resize((int(a.width * alt / a.height), alt), Image.LANCZOS)
    b = b.resize((int(b.width * alt / b.height), alt), Image.LANCZOS)
    par = Image.new("RGB", (a.width + b.width + 24, alt + 26), (235, 238, 241))
    par.paste(a, (0, 26)); par.paste(b, (a.width + 24, 26))
    dd = ImageDraw.Draw(par)
    dd.text((6, 8), "PREVIA", fill=(20, 40, 60))
    dd.text((a.width + 30, 8), "DOCUMENTO GERADO", fill=(20, 40, 60))
    par.save(os.path.join(SP, f"rod_{modelo}_par_{TAG}.png"))
    print("ARQUIVO:", os.path.join(SP, f"rod_{modelo}_par_{TAG}.png"))

root.destroy()
sys.stdout.flush()
os._exit(0)
