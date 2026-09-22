"""Testa as pastas derivadas e a escala de fonte.

Roda num DATA_DIR temporario, entao nao encosta no config.json do usuario.
"""

import os as _os
import sys as _sys

# Raiz do projeto a partir deste arquivo: tests/python/x.py -> duas pastas acima
RAIZ = _os.path.dirname(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
_sys.path.insert(0, RAIZ)
_os.chdir(RAIZ)
SAIDA = _os.path.join(RAIZ, "tests", "_saida")
_os.makedirs(SAIDA, exist_ok=True)

import os
import shutil
import sys
import tempfile

from tkinterdnd2 import TkinterDnD
from gestor.dados import config
from gestor.ui import theme
from gestor.ui.workspace import AppEvidencias

falhas = []


def checar(cond, msg):
    print(("OK: " if cond else "FALHOU: ") + msg)
    if not cond:
        falhas.append(msg)


# ---------- 1. escala de fonte (puro, sem UI) ----------
base_body, base_botao, base_ctrl = theme.FS_BODY, theme.FS_BUTTON, theme.CTRL_H
theme.aplicar_escala(1.0, 1.0)
padrao = (theme.FS_BODY, theme.FS_BUTTON, theme.CTRL_H)
checar(padrao == (base_body, base_botao, base_ctrl),
       "escala 1.0 devolve os valores originais %s" % (padrao,))

theme.aplicar_escala(1.3, 1.0)
checar(theme.FS_BODY > base_body and theme.CTRL_H > base_ctrl,
       "escala 1.3 aumenta texto E altura do controle (%d/%d)" % (theme.FS_BODY, theme.CTRL_H))

theme.aplicar_escala(0.9, 1.0)
checar(theme.FS_BODY < base_body, "escala 0.9 diminui o texto (%d)" % theme.FS_BODY)

theme.aplicar_escala(1.0, 1.3)
checar(theme.FS_BUTTON > base_botao and theme.FS_BODY == base_body,
       "ajuste dos botoes mexe SO no botao (botao=%d, corpo=%d)"
       % (theme.FS_BUTTON, theme.FS_BODY))

theme.aplicar_escala(1.3, 1.3)
checar(all(isinstance(v, int) for v in (theme.FS_BODY, theme.FS_BUTTON, theme.CTRL_H)),
       "os tamanhos saem inteiros (o Tk recusa fracionario)")

theme.aplicar_escala(1.0, 1.0)   # devolve ao padrao

# ---------- 2. pastas derivadas ----------
tmp = tempfile.mkdtemp(prefix="ge_teste_")
capturas = os.path.join(tmp, "Capturas")
os.makedirs(capturas, exist_ok=True)

root = TkinterDnD.Tk()
root.withdraw()
app = AppEvidencias(root, capturas, os.path.join(capturas, "PDF"), RAIZ, tmp)
app.pausar_timer = True

pdf = app.pasta_documentos("pdf")
docx = app.pasta_documentos("docx")
print("   PDF  ->", pdf)
print("   DOCX ->", docx)
checar(pdf == os.path.join(capturas, "PDF"), "PDF vai pra subpasta PDF da pasta de capturas")
checar(docx == os.path.join(capturas, "DOCX"), "DOCX vai pra subpasta DOCX da pasta de capturas")
checar(os.path.isdir(pdf) and os.path.isdir(docx), "as duas subpastas sao criadas sozinhas")

# trocar a pasta de capturas deve arrastar as subpastas junto
nova = os.path.join(tmp, "OutraPasta")
os.makedirs(nova, exist_ok=True)
app.pasta_capturas = nova
checar(app.pasta_documentos("pdf") == os.path.join(nova, "PDF"),
       "ao trocar a pasta de capturas, o PDF acompanha")
checar(os.path.isdir(os.path.join(nova, "PDF")), "a subpasta nova tambem e criada")

# ---------- 3. persistencia da escala ----------
app.config["escala_fonte"] = "grande"
config.save(tmp, app.config)
recarregado = config.load(tmp)
checar(recarregado.get("escala_fonte") == "grande", "a escala escolhida persiste no config")
checar(theme.escala_por_chave("grande") == 1.15, "a chave 'grande' vira o fator 1.15")
checar(theme.escala_por_chave("inexistente") == 1.0, "chave desconhecida cai no padrao")

try:
    # A bandeja roda numa thread com laco de mensagens nativo. Parar antes de
    # encerrar evita derrubar o processo na saida.
    app.icon.stop()
except Exception:
    pass
root.destroy()
shutil.rmtree(tmp, ignore_errors=True)

print()
print("FALHAS:", falhas if falhas else "nenhuma")
sys.exit(1 if falhas else 0)
