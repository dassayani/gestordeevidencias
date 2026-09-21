# -*- coding: utf-8 -*-
"""Reordenar os passos nao pode apagar as miniaturas que ja estao na tela.

Complementa test_reordenar.py: aquele confere a ORDEM com widgets falsos (e por
isso nao via este defeito, que so aparece com as colunas reconstruidas de
verdade). Aqui as imagens sao reais e o teste pergunta ao Tk se cada uma ainda
existe depois de reordenar pelas setas e pelo arraste.
"""

import os as _os
import sys as _sys

# Raiz do projeto a partir deste arquivo: tests/python/x.py -> duas pastas acima
RAIZ = _os.path.dirname(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
_sys.path.insert(0, RAIZ)
_os.chdir(RAIZ)
SAIDA = _os.path.join(RAIZ, "tests", "_saida")
_os.makedirs(SAIDA, exist_ok=True)

import os, sys, ctypes, tempfile, shutil, traceback

if not ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4)):
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
from tkinterdnd2 import TkinterDnD
from PIL import Image
import config, document_builder
from workspace import AppEvidencias

tmp = tempfile.mkdtemp(prefix="ge_reord_")
capturas = os.path.join(tmp, "Capturas")
os.makedirs(capturas)
nomes = []
for i in range(3):
    nome = "print_20000%d.png" % i
    Image.new("RGB", (500, 320), (40 + i * 40, 90, 130)).save(os.path.join(capturas, nome))
    nomes.append(nome)
cfg = config.load(tmp)
cfg["pasta_capturas"] = capturas
config.save(tmp, cfg)

falhas = []
root = TkinterDnD.Tk()
app = AppEvidencias(root, capturas, os.path.join(tmp, "PDF"), RAIZ, tmp)
app.pausar_timer = True
app.tempo_limite = 10 ** 9
root.deiconify()
root.update()


def rotulos_com_imagem(widget, achados=None):
    """(nome da imagem, ela ainda existe no Tk?) de cada rotulo que mostra uma."""
    achados = [] if achados is None else achados
    for filho in widget.winfo_children():
        try:
            nome_img = str(filho.cget("image"))
        except Exception:
            nome_img = ""
        if nome_img:
            try:
                # se a PhotoImage foi coletada, o Tk nao conhece mais o nome
                filho.tk.call("image", "width", nome_img)
                existe = True
            except Exception:
                existe = False
            achados.append((nome_img, existe))
        rotulos_com_imagem(filho, achados)
    return achados


try:
    janela = document_builder.MontarDocumento(app, nomes)
    janela.update()
    root.update()

    def estado(rotulo):
        seq = rotulos_com_imagem(janela.frame_sequencia)
        centro = rotulos_com_imagem(janela.col_central)
        vivas_seq = sum(1 for _, ok in seq if ok)
        vivas_centro = sum(1 for _, ok in centro if ok)
        print("%-30s sequencia=%d/%d  passos=%d/%d"
              % (rotulo, vivas_seq, len(seq), vivas_centro, len(centro)))
        return vivas_seq, len(seq), vivas_centro, len(centro)

    vs, ts, vc, tc = estado("inicial")
    if tc == 0:
        falhas.append("nenhuma miniatura de passo foi criada no inicio")

    janela._mover(0, 1)
    janela.update()
    root.update()
    vs, ts, vc, tc = estado("depois da seta para baixo")
    if vc < tc or tc == 0:
        falhas.append("setas: %d de %d miniaturas de passo sumiram" % (tc - vc, tc))
    if vs < ts or ts == 0:
        falhas.append("setas: %d de %d miniaturas da sequencia sumiram" % (ts - vs, ts))

    # mesma sequencia de chamadas que o soltar do arraste faz (centro e depois
    # sequencia) — a ordem inversa da das setas, que e onde estava o defeito
    item = janela.passos.pop(0)
    janela.passos.insert(2, item)
    janela._atualizar_coluna_central()
    janela._atualizar_sequencia()
    janela.update()
    root.update()
    vs, ts, vc, tc = estado("depois do arraste")
    if vc < tc or tc == 0:
        falhas.append("arraste: %d de %d miniaturas de passo sumiram" % (tc - vc, tc))
    if vs < ts or ts == 0:
        falhas.append("arraste: %d de %d miniaturas da sequencia sumiram" % (ts - vs, ts))

    # O teste consegue enxergar uma miniatura morta? Solta as referencias de
    # proposito — que e exatamente o que a lista compartilhada fazia — e
    # confere que a contagem cai. Sem isto, um teste que so passa nao prova
    # nada.
    janela.imagens_passos = []
    janela.update()
    root.update()
    vs, ts, vc, tc = estado("com as referencias soltas (deve cair)")
    if vc == tc:
        falhas.append("o teste nao percebe miniatura morta — nao serve como prova")

    janela.destroy()
except Exception:
    falhas.append("erro: " + traceback.format_exc())

print("\nFALHAS:", "nenhuma" if not falhas else "")
for f in falhas:
    print(" -", f)
try:
    root.destroy()
except Exception:
    pass
shutil.rmtree(tmp, ignore_errors=True)
sys.stdout.flush()
os._exit(0)
