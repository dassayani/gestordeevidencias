# -*- coding: utf-8 -*-
"""Configuracoes: cada opcao, clicada na tela, muda o que o app FAZ.

O cenario_configuracoes confere que a tela espelha o config gravado. Este vai
alem: clica na opcao como o usuario (no rotulo, que e onde se clica) e confere
o efeito no app, nao so no arquivo:

- atalhos: a combinacao escolhida fica registrada no Windows (outro registro
  da mesma tecla e recusado) e a anterior e liberada; uma combinacao tomada
  por outro programa aparece como "Em uso" na tela;
- padrao de nome: o arquivo da proxima captura sai com o nome escolhido;
- incluir cursor, copiar, som e abrir apos capturar: a captura chama (ou nao)
  cada uma dessas acoes;
- autor: o campo grava mesmo fechando pelo X com o cursor dentro dele, chega
  na capa do documento, e o autor trocado num documento nao vira o padrao;
- fonte e borda do documento chegam nas opcoes de exportacao;
- inatividade, retencao, iniciar com o Windows, menu Iniciar e tamanho do
  texto;
- as caixinhas ficam na altura do texto (medido na tela).

Iniciar com o Windows e menu Iniciar sao interceptados: o teste nao mexe no
registro nem no atalho de verdade da maquina.
"""

import os as _os
import sys as _sys

RAIZ = _os.path.dirname(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
_sys.path.insert(0, RAIZ)
_os.chdir(RAIZ)

import os, re, sys, ctypes, tempfile, shutil, traceback, time

if not ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4)):
    ctypes.windll.shcore.SetProcessDpiAwareness(2)

import tkinter as tk
import tkinter.font as tkfont
from tkinter import messagebox
import win32gui
from tkinterdnd2 import TkinterDnD
from PIL import Image, ImageGrab
from gestor.captura import captura_utils, hotkey
from gestor.dados import config
from gestor.sistema import startup, utils
from gestor.ui import configuracoes, document_builder, export_preview, theme, widgets
from gestor.ui.workspace import AppEvidencias

falhas = []
erros_tk = []


def checar(condicao, descricao):
    print(("OK:     " if condicao else "FALHOU: ") + descricao)
    if not condicao:
        falhas.append(descricao)


def janela_config(root):
    for w in root.winfo_children():
        if isinstance(w, tk.Toplevel) and "Configura" in w.title():
            return w
    return None


def fechar_pelo_x(win):
    comando = win.protocol("WM_DELETE_WINDOW")
    win.tk.call(comando) if comando else win.destroy()


def todos(widget):
    for filho in widget.winfo_children():
        yield filho
        yield from todos(filho)


def rotulo(win, texto):
    for w in todos(win):
        if isinstance(w, tk.Label) and str(w.cget("text")) == texto:
            return w
    raise LookupError("rotulo nao encontrado: %r" % texto)


def clicar(win, texto):
    """Clica no rotulo da opcao, como o usuario faz."""
    lbl = rotulo(win, texto)
    lbl.event_generate("<Button-1>", x=3, y=3)
    win.update()


def caixa_de(win, texto):
    """A caixinha da mesma linha do rotulo."""
    lbl = rotulo(win, texto)
    w = lbl.master
    for _ in range(3):
        for f in w.winfo_children():
            if isinstance(f, widgets.Checkbox):
                return f
        w = w.master
    raise LookupError("caixa nao encontrada: %r" % texto)


def campo_abaixo(win, texto):
    """O Entry do bloco rotulado com `texto`."""
    lbl = rotulo(win, texto)
    for w in todos(lbl.master):
        if isinstance(w, tk.Entry):
            return w
    raise LookupError("campo nao encontrado: %r" % texto)


def disco():
    return config.load(tmp)


def livre_no_windows(mods, vk):
    """True se a combinacao NAO esta registrada (este teste consegue pega-la)."""
    try:
        win32gui.RegisterHotKey(None, 0xBEEF, mods | hotkey.MOD_NOREPEAT, vk)
    except Exception:
        return False
    win32gui.UnregisterHotKey(None, 0xBEEF)
    return True


def esperar(condicao, segundos=3.0):
    limite = time.monotonic() + segundos
    while time.monotonic() < limite:
        root.update()
        if condicao():
            return True
        time.sleep(0.03)
    return condicao()


tmp = tempfile.mkdtemp(prefix="ge_cfgef_")
capturas = os.path.join(tmp, "Capturas")
os.makedirs(capturas)
for i in range(2):
    Image.new("RGB", (400, 300), (60 + i * 40, 100, 140)).save(
        os.path.join(capturas, "print_10000%d.png" % i))

cfg = config.load(tmp)
cfg.update({"pasta_capturas": capturas, "autor_padrao": "QA - Antigo",
            "atalho_captura_area": "ctrl_alt_s", "atalho_janela_ativa": "nenhum",
            "incluir_cursor": False, "copiar_apos_captura": True, "som_captura": True,
            "abrir_apos_captura": True, "padrao_nome": "data_hora"})
config.save(tmp, cfg)

# --- intercepta o que sai do processo (registro, atalho, som, clipboard) ---
chamadas = []
originais = {}


def interceptar(modulo, nome, falso):
    originais[(modulo, nome)] = getattr(modulo, nome)
    setattr(modulo, nome, falso)


estado_iniciar = {"on": False, "menu": False}
interceptar(startup, "esta_habilitado", lambda: estado_iniciar["on"])
interceptar(startup, "habilitar", lambda: (chamadas.append("habilitar"),
                                           estado_iniciar.update(on=True)))
interceptar(startup, "desabilitar", lambda: (chamadas.append("desabilitar"),
                                             estado_iniciar.update(on=False)))
interceptar(startup, "no_menu_iniciar", lambda: estado_iniciar["menu"])
interceptar(startup, "adicionar_ao_menu_iniciar",
            lambda: (chamadas.append("menu+"), estado_iniciar.update(menu=True)))
interceptar(startup, "remover_do_menu_iniciar",
            lambda: (chamadas.append("menu-"), estado_iniciar.update(menu=False)))
interceptar(startup, "sincronizar", lambda: False)
interceptar(startup, "sincronizar_menu_iniciar", lambda: False)
interceptar(utils, "copy_image_to_clipboard", lambda img: chamadas.append("copiar"))
interceptar(captura_utils, "tocar_som_captura", lambda: chamadas.append("som"))
avisos = []
interceptar(messagebox, "showwarning", lambda *a, **k: avisos.append(a))

previas = []


class PreviaFalsa:
    def __init__(self, app, montar, modelo, capa, passos, opcoes):
        previas.append({"capa": capa, "opcoes": opcoes})

    def winfo_exists(self):
        return False


interceptar(export_preview, "PreVisualizarExportar", PreviaFalsa)

root = TkinterDnD.Tk()
root.report_callback_exception = lambda *a: erros_tk.append(
    "".join(traceback.format_exception(*a)))
app = AppEvidencias(root, capturas, os.path.join(tmp, "PDF"), RAIZ, tmp)
app.pausar_timer = True
root.deiconify()
root.update()
aberturas = []
_mostrar = app.mostrar_janela
app.mostrar_janela = lambda *a, **k: (aberturas.append(1), _mostrar(*a, **k))

tomada_pelo_teste = None
try:
    configuracoes.abrir(app)
    root.update()
    win = janela_config(root)
    checar(win is not None, "a janela de Configuracoes abriu")

    # ---------------- atalhos ----------------
    S, P = hotkey.vk_letra("S"), hotkey.vk_letra("P")
    CS = hotkey.MOD_CONTROL | hotkey.MOD_SHIFT
    CA = hotkey.MOD_CONTROL | hotkey.MOD_ALT
    checar(not livre_no_windows(CA, S), "o atalho gravado (Ctrl+Alt+S) esta registrado no Windows")

    clicar(win, "Ctrl+Shift+S")
    checar(disco()["atalho_captura_area"] == "ctrl_shift_s",
           "escolher Ctrl+Shift+S grava no config")
    checar(not livre_no_windows(CS, S), "Ctrl+Shift+S passou a estar registrado no Windows")
    checar(livre_no_windows(CA, S), "o atalho anterior (Ctrl+Alt+S) foi liberado")
    reg = app.hotkeys._registros.get("captura_area")
    checar(reg is not None and app.hotkeys._callbacks.get(reg[0]) == app.iniciar_seletor,
           "a tecla nova abre o seletor de area")
    checar(caixa_de(win, "Ctrl+Shift+S").variable.get()
           and not caixa_de(win, "Ctrl+Alt+S").variable.get(),
           "na tela so a opcao escolhida fica marcada")

    clicar(win, "Ctrl+Alt+W")
    checar(disco()["atalho_janela_ativa"] == "ctrl_alt_w"
           and not livre_no_windows(CA, hotkey.vk_letra("W")),
           "atalho da janela ativa: Ctrl+Alt+W gravado e registrado")
    clicar(win, "Desativado")
    checar(disco()["atalho_janela_ativa"] == "nenhum"
           and livre_no_windows(CA, hotkey.vk_letra("W")),
           "Desativado solta a tecla da janela ativa")

    # combinacao tomada por "outro programa" (este teste) aparece na tela
    win32gui.RegisterHotKey(None, 0xBEE0, CS | hotkey.MOD_NOREPEAT, P)
    tomada_pelo_teste = 0xBEE0
    clicar(win, "Ctrl+Shift+P")
    checar(avisos and "Ctrl+Shift+P" in str(avisos[-1]),
           "combinacao ocupada: avisa qual nao deu para registrar")
    checar(any("Em uso por outro programa" in str(w.cget("text"))
               for w in todos(win) if isinstance(w, tk.Label)),
           "combinacao ocupada: a tela mostra 'Em uso por outro programa'")
    win32gui.UnregisterHotKey(None, 0xBEE0)
    tomada_pelo_teste = None
    clicar(win, "Ctrl+Shift+S")
    checar(any(str(w.cget("text")).startswith("Atalhos ativos")
               for w in todos(win) if isinstance(w, tk.Label)),
           "voltando a uma combinacao livre, a tela volta a 'Atalhos ativos'")

    # ---------------- captura: cursor, copiar, som, abrir, nome ----------------
    colados = []
    interceptar(captura_utils, "colar_cursor",
                lambda img, offset=(0, 0): (colados.append(offset), img)[1])

    def capturar():
        """O caminho comum das capturas: area -> cursor -> salvar."""
        antes = set(os.listdir(capturas))
        chamadas.clear(); aberturas.clear(); colados.clear()
        img = Image.new("RGB", (120, 80), (200, 210, 220))
        if app.config.get("incluir_cursor", False):
            img = captura_utils.colar_cursor(img, offset=(0, 0))
        app._salvar_captura(img)
        root.update()
        novos = [n for n in set(os.listdir(capturas)) - antes if n.endswith(".png")
                 and not n.endswith(".raw.png")]
        return novos[0] if len(novos) == 1 else novos

    nome = capturar()
    checar(re.fullmatch(r"print_\d{8}_\d{6}(_\d+)?\.png", str(nome)) is not None,
           "padrao data_hora: a captura sai com data e hora no nome (%s)" % nome)
    checar("copiar" in chamadas and "som" in chamadas and aberturas,
           "com tudo ligado: copia, toca o som e abre o painel")

    clicar(win, "captura-HHMMSS")
    checar(disco()["padrao_nome"] == "hora", "escolher captura-HHMMSS grava no config")
    nome = capturar()
    checar(re.fullmatch(r"print_\d{6}(_\d+)?\.png", str(nome)) is not None,
           "padrao hora: a proxima captura sai so com a hora no nome (%s)" % nome)
    clicar(win, "captura-AAAAMMDD-HHMMSS")

    for texto, chave, acao in (
            ("Copiar a captura para a área de transferência", "copiar_apos_captura", "copiar"),
            ("Som ao capturar", "som_captura", "som")):
        clicar(win, texto)
        checar(disco()[chave] is False, "desmarcar %r grava False" % texto)
        capturar()
        checar(acao not in chamadas, "desmarcado, a captura nao faz '%s'" % acao)
        clicar(win, texto)
        checar(disco()[chave] is True, "marcar de novo %r grava True" % texto)
        capturar()
        checar(acao in chamadas, "marcado, a captura volta a fazer '%s'" % acao)

    clicar(win, "Abrir automaticamente após capturar")
    checar(disco()["abrir_apos_captura"] is False, "desmarcar 'Abrir apos capturar' grava")
    capturar()
    checar(not aberturas, "desmarcado, a captura nao abre o painel")
    clicar(win, "Abrir automaticamente após capturar")
    capturar()
    checar(bool(aberturas), "marcado, a captura abre o painel")

    clicar(win, "Incluir cursor do mouse")
    checar(disco()["incluir_cursor"] is True and caixa_de(win, "Incluir cursor do mouse").variable.get(),
           "marcar 'Incluir cursor' grava True e marca a caixa")
    capturar()
    checar(len(colados) == 1, "com cursor ligado, a captura cola o cursor")
    clicar(win, "Incluir cursor do mouse")
    capturar()
    checar(not colados, "com cursor desligado, a captura nao cola o cursor")
    setattr(captura_utils, "colar_cursor", originais.pop((captura_utils, "colar_cursor")))

    # o cursor colado e o de verdade: com o mouse dentro da area, a imagem muda
    pos_antes = win32gui.GetCursorPos()
    try:
        x0, y0 = win32gui.GetCursorPos()
        base = Image.new("RGB", (80, 80), (255, 0, 255))
        com_cursor = captura_utils.colar_cursor(base, offset=(x0 - 20, y0 - 20))
        cores = {cor: n for n, cor in com_cursor.getcolors(80 * 80)}
        mudou = 80 * 80 - cores.get((255, 0, 255), 0)
        checar(mudou > 20, "colar_cursor desenha o cursor real na imagem (%d px)" % mudou)
    finally:
        ctypes.windll.user32.SetCursorPos(*pos_antes)

    # ---------------- janela: iniciar com o Windows, menu, inatividade ----------------
    clicar(win, "Iniciar com o Windows")
    checar(chamadas[-1:] == ["habilitar"], "marcar 'Iniciar com o Windows' liga o inicio automatico")
    clicar(win, "Iniciar com o Windows")
    checar(chamadas[-1:] == ["desabilitar"], "desmarcar desliga o inicio automatico")
    clicar(win, "Adicionar ao menu Iniciar")
    checar(chamadas[-1:] == ["menu+"], "marcar 'menu Iniciar' cria o atalho")
    clicar(win, "Adicionar ao menu Iniciar")
    checar(chamadas[-1:] == ["menu-"], "desmarcar remove o atalho")

    campo_tempo = campo_abaixo(win, "Tempo de inatividade até esconder o painel (segundos)")
    campo_tempo.delete(0, "end"); campo_tempo.insert(0, "33")
    campo_retencao = campo_abaixo(win, "Apagar depois de quantos dias")
    clicar(win, "Limpar prints automaticamente")
    campo_retencao.delete(0, "end"); campo_retencao.insert(0, "12")

    # ---------------- documento: autor, borda, fonte ----------------
    campo_autor = campo_abaixo(win, "Autor (vai na capa de cada documento)")
    checar(campo_autor.get() == "QA - Antigo", "o campo Autor mostra o autor gravado")
    # sair do campo (clicar em outro) ja grava
    campo_autor.focus_force()
    campo_autor.delete(0, "end")
    campo_autor.insert(0, "Joana Lima")
    win.focus_force()
    esperar(lambda: disco()["autor_padrao"] == "Joana Lima", 2.0)
    checar(disco()["autor_padrao"] == "Joana Lima", "sair do campo Autor grava o autor")
    campo_autor.focus_force()
    campo_autor.delete(0, "end")
    campo_autor.insert(0, "Maria Souza")
    clicar(win, "Times")
    clicar(win, "Adicionar borda nas imagens do documento")

    # fecha pelo X com o cursor ainda no campo do autor: sem <FocusOut>
    fechar_pelo_x(win)
    root.update()
    gravado = disco()
    checar(gravado["autor_padrao"] == "Maria Souza",
           "o autor digitado grava mesmo fechando pelo X dentro do campo")
    checar(gravado["tempo_inatividade_ms"] == 33000 and app.tempo_limite == 33000,
           "a inatividade digitada vale ao fechar (33 s)")
    checar(gravado["retencao_dias"] == 12, "a retencao digitada vale ao fechar (12 dias)")
    checar(gravado["fonte_legenda"] == "Times" and gravado["borda_ativada"] is True,
           "fonte Times e borda gravadas")

    nomes = sorted(n for n in os.listdir(capturas) if n.endswith(".png")
                   and not n.endswith(".raw.png"))[:2]
    doc = document_builder.MontarDocumento(app, nomes)
    root.update()
    checar(doc.entries_capa["autor"].get() == "Maria Souza",
           "o documento novo ja vem com o autor das Configuracoes")
    checar(doc.var_borda.get() is True, "o documento novo ja vem com a borda das Configuracoes")
    doc.entries_capa["autor"].delete(0, "end")
    doc.entries_capa["autor"].insert(0, "Outra Pessoa")
    doc._pre_visualizar()
    root.update()
    checar(previas and previas[-1]["capa"]["autor"] == "Outra Pessoa",
           "o autor trocado no documento vai na capa desse documento")
    checar(previas and previas[-1]["opcoes"]["fonte_legenda"] == "Times"
           and previas[-1]["opcoes"]["borda_ativada"] is True,
           "fonte e borda das Configuracoes chegam na exportacao")
    checar(disco()["autor_padrao"] == "Maria Souza" and app.config["autor_padrao"] == "Maria Souza",
           "trocar o autor num documento nao muda o autor padrao")
    doc.destroy()
    root.update()

    # ---------------- alinhamento das caixinhas (medido na tela) ----------------
    configuracoes.abrir(app)
    root.update()
    win = janela_config(root)
    win.attributes("-topmost", True)
    win.lift()
    win.update()
    time.sleep(0.5)
    win.update()
    ox = -ctypes.windll.user32.GetSystemMetrics(76)
    oy = -ctypes.windll.user32.GetSystemMetrics(77)
    tela = ImageGrab.grab(all_screens=True)
    medidos = []
    for texto in ("Print Screen", "Ctrl+Shift+S", "Desativado", "Ctrl+Alt+W",
                  "Incluir cursor do mouse", "Som ao capturar"):
        lbl = rotulo(win, texto)
        cb = caixa_de(win, texto)
        if lbl.winfo_rooty() + lbl.winfo_height() > win.winfo_rooty() + win.winfo_height():
            continue     # fora da area visivel da rolagem
        c = cb.canvas
        x0, y0 = c.winfo_rootx() + ox, c.winfo_rooty() + oy
        reg = tela.crop((x0, y0, x0 + c.winfo_width(), y0 + c.winfo_height())).convert("L")
        fundo = reg.getpixel((0, 0))
        linhas_caixa = [y for y in range(reg.height)
                        if any(abs(reg.getpixel((x, y)) - fundo) > 12 for x in range(reg.width))]
        lx, ly = lbl.winfo_rootx() + ox, lbl.winfo_rooty() + oy
        reg2 = tela.crop((lx, ly, lx + lbl.winfo_width(), ly + lbl.winfo_height())).convert("L")
        fundo2 = reg2.getpixel((0, 0))
        tinta = [y for y in range(reg2.height)
                 if any(reg2.getpixel((x, y)) < fundo2 - 60 for x in range(reg2.width))]
        if linhas_caixa and tinta:
            centro_caixa = y0 + (linhas_caixa[0] + linhas_caixa[-1]) / 2
            centro_texto = ly + (tinta[0] + tinta[-1]) / 2
            medidos.append((texto, centro_caixa - centro_texto, lbl.winfo_rootx()))
    checar(len(medidos) >= 4, "deu para medir as caixinhas na tela (%d)" % len(medidos))
    for texto, desvio, _ in medidos:
        checar(abs(desvio) <= 1.5,
               "a caixinha de %r fica na altura do texto (desvio %+.1f px)" % (texto, desvio))
    colunas = {x for _, _, x in medidos}
    checar(len(colunas) == 1,
           "o texto de todas as opcoes comeca na mesma coluna (%s)" % sorted(colunas))
    tamanho = tkfont.Font(font=rotulo(win, "Print Screen").cget("font")).actual("size")
    checar(tamanho == theme.FS_BODY - 1,
           "o texto das opcoes e um ponto menor que o do app (%s pt)" % tamanho)

    # ---------------- tamanho do texto da aplicacao ----------------
    corpo_antes = theme.FS_BODY
    clicar(win, "Grande")
    root.update()
    checar(disco()["escala_fonte"] != "padrao" and theme.FS_BODY > corpo_antes,
           "escolher um tamanho maior grava e aumenta o texto do app (%s -> %s)"
           % (corpo_antes, theme.FS_BODY))
    win = janela_config(root)
    if win is not None:
        clicar(win, "Padrão")
        root.update()
    checar(theme.FS_BODY == corpo_antes, "voltar ao Padrao restaura o tamanho")
    win = janela_config(root)
    if win is not None:
        fechar_pelo_x(win)
        root.update()

    checar(not erros_tk, "nenhum erro silencioso do Tk")
    if erros_tk:
        print(erros_tk[0][:1500])
except Exception:
    falhas.append("erro: " + traceback.format_exc())
finally:
    if tomada_pelo_teste:
        try:
            win32gui.UnregisterHotKey(None, tomada_pelo_teste)
        except Exception:
            pass
    for (modulo, nome), valor in originais.items():
        setattr(modulo, nome, valor)

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
