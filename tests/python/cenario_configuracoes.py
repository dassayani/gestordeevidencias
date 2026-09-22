# -*- coding: utf-8 -*-
"""Configuracoes: a tela espelha o que esta gravado, e o que muda volta pro disco.

Le os rotulos e os campos da tela montada de verdade e compara com o config em
disco. Fecha pelo mesmo caminho do botao X (o callback registrado em
WM_DELETE_WINDOW), porque `destroy()` puro nao dispara esse tratador.
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

import tkinter as tk
from tkinterdnd2 import TkinterDnD
from PIL import Image
from gestor.dados import config
from gestor.ui import configuracoes
from gestor.ui.workspace import AppEvidencias

falhas = []


def checar(condicao, descricao):
    print(("OK:     " if condicao else "FALHOU: ") + descricao)
    if not condicao:
        falhas.append(descricao)


def textos(widget, achados=None):
    """Todo texto visivel dentro de um widget, recursivamente."""
    achados = [] if achados is None else achados
    for filho in widget.winfo_children():
        try:
            valor = str(filho.cget("text"))
            if valor:
                achados.append(valor)
        except Exception:
            pass
        textos(filho, achados)
    return achados


def entradas(widget, achados=None):
    """Conteudo de todos os campos de texto de uma tela."""
    achados = [] if achados is None else achados
    for filho in widget.winfo_children():
        if isinstance(filho, tk.Entry):
            try:
                achados.append(filho.get())
            except Exception:
                pass
        entradas(filho, achados)
    return achados


def janela_config(root):
    for w in root.winfo_children():
        if isinstance(w, tk.Toplevel) and "Configura" in w.title():
            return w
    return None


def fechar_pelo_x(win):
    """Executa o mesmo tratador que o botao X da janela dispara."""
    comando = win.protocol("WM_DELETE_WINDOW")
    if comando:
        win.tk.call(comando)
    else:
        win.destroy()


tmp = tempfile.mkdtemp(prefix="ge_cfg_")
capturas = os.path.join(tmp, "Capturas")
os.makedirs(capturas)
Image.new("RGB", (400, 300), (60, 100, 140)).save(os.path.join(capturas, "print_1.png"))

# Estado inicial de proposito diferente do padrao: se a tela mostrar o padrao
# em vez disto, e porque nao esta espelhando o que esta gravado.
cfg = config.load(tmp)
cfg.update({"pasta_capturas": capturas,
            "abrir_apos_captura": False,
            "incluir_cursor": True,
            "som_captura": False,
            "copiar_apos_captura": False,
            "atalho_captura_area": "ctrl_shift_s",
            "atalho_janela_ativa": "ctrl_alt_w",
            "padrao_nome": "data_hora",
            "retencao_dias": 45,
            "borda_ativada": True,
            "fonte_legenda": "Times",
            "tempo_inatividade_ms": 25000})
config.save(tmp, cfg)

root = TkinterDnD.Tk()
app = AppEvidencias(root, capturas, os.path.join(tmp, "PDF"), RAIZ, tmp)
# `pausar_timer` ja impede o painel de se esconder sozinho. Mexer em
# `tempo_limite` aqui falsearia o campo de inatividade que este teste confere.
app.pausar_timer = True
root.deiconify()
root.update()

try:
    configuracoes.abrir(app)
    root.update()
    win = janela_config(root)
    checar(win is not None, "a janela de Configuracoes abriu")

    if win:
        na_tela = textos(win)
        valores = entradas(win)

        for rotulo in ("Captura", "Nomeação e retenção", "Janela", "Aparência",
                       "Documento",
                       "Abrir automaticamente após capturar",
                       "Incluir cursor do mouse",
                       "Copiar a captura para a área de transferência",
                       "Som ao capturar",
                       "Pasta onde salvar os prints",
                       "Padrão de nome do arquivo",
                       "Limpar prints automaticamente",
                       "Iniciar com o Windows",
                       "Adicionar ao menu Iniciar",
                       "Tempo de inatividade até esconder o painel (segundos)",
                       "Tamanho do texto da aplicação",
                       "Adicionar borda nas imagens do documento",
                       "Fonte da legenda no documento",
                       "Limpar pasta de capturas"):
            # sem diferenciar maiuscula: os titulos de secao saem em caixa alta
            alvo = rotulo.upper()
            checar(any(alvo in t.upper() for t in na_tela), "a tela mostra %r" % rotulo)

        # os campos trazem o que esta gravado, e nao o padrao
        checar(any(capturas in v for v in valores),
               "o campo da pasta mostra a pasta gravada")
        checar(any(v.strip() == "45" for v in valores),
               "o campo de retencao mostra os 45 dias gravados")
        checar(any(v.strip() == "25" for v in valores),
               "o campo de inatividade mostra os 25 segundos gravados")

        # as combinacoes de atalho gravadas estao entre as opcoes oferecidas
        checar(any("Ctrl+Shift+S" in t for t in na_tela),
               "a combinacao de captura gravada aparece na lista")
        checar(any("Ctrl+Alt+W" in t for t in na_tela),
               "a combinacao da janela ativa aparece na lista")
        checar(any("Times" in t for t in na_tela),
               "a fonte de legenda gravada aparece na lista")
        checar(any("captura-AAAAMMDD" in t for t in na_tela),
               "o padrao de nome gravado aparece na lista")

        # a tela informa se o atalho esta valendo ou tomado por outro programa
        checar(any("Atalhos ativos" in t or "Em uso por outro programa" in t
                   for t in na_tela),
               "a tela informa o estado dos atalhos")

        checar(app.pausar_timer is True,
               "com Configuracoes aberta, a inatividade fica pausada")

        # mudar uma opcao grava no arquivo
        app.config["som_captura"] = True
        config.save(app.data_dir, app.config)
        checar(config.load(tmp).get("som_captura") is True,
               "mudar uma opcao grava no config em disco")

        fechar_pelo_x(win)
        root.update()
        checar(janela_config(root) is None, "o X fecha a janela")
        checar(app.pausar_timer is False,
               "fechar Configuracoes volta a contar a inatividade")

        # reabrir carrega o valor novo
        configuracoes.abrir(app)
        root.update()
        win2 = janela_config(root)
        checar(win2 is not None, "a tela reabre depois de fechada")
        if win2:
            checar(app.config.get("som_captura") is True,
                   "a tela reaberta carrega o valor gravado")
            fechar_pelo_x(win2)
            root.update()
except Exception:
    falhas.append("erro: " + traceback.format_exc())

print("\nFALHAS:", "nenhuma" if not falhas else "")
for f in falhas:
    print(" -", f)
try:
    try:
        # A bandeja roda numa thread com laco de mensagens nativo. Parar antes de
        # encerrar evita derrubar o processo na saida.
        app.icon.stop()
    except Exception:
        pass
    root.destroy()
except Exception:
    pass
shutil.rmtree(tmp, ignore_errors=True)
sys.stdout.flush()
os._exit(0)
