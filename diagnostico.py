"""Erro que aparece, em vez de app que não abre.

Compilado com `--windowed` o executável não tem console: qualquer exceção que
escape vai pro nada. Pra quem usa, o sintoma é dar dois cliques no atalho e não
acontecer absolutamente nada — sem janela, sem mensagem, sem pista. O mesmo
vale pros erros dentro de callback do Tk, que o Tkinter imprime no stderr
inexistente e engole.

Aqui todo erro não tratado vira duas coisas: uma linha no arquivo de log (pra
poder investigar depois) e uma janela dizendo o que houve e onde está o log.
"""
import os
import sys
import tempfile
import traceback
from datetime import datetime

NOME_LOG = "erros.log"
_caminho_log = None
_ja_avisou = False


def _definir_log(data_dir):
    """Escolhe onde gravar, preferindo a pasta de dados e caindo no temp.

    A pasta do executável pode não ser gravável (instalação em Program Files),
    e um log que não grava é pior que log nenhum: esconde justamente o erro que
    a gente queria ver.
    """
    candidatos = [data_dir, os.path.join(tempfile.gettempdir(), "GestorEvidencias")]
    for pasta in candidatos:
        if not pasta:
            continue
        try:
            os.makedirs(pasta, exist_ok=True)
            caminho = os.path.join(pasta, NOME_LOG)
            with open(caminho, "a", encoding="utf-8"):
                pass
            return caminho
        except Exception:
            continue
    return None


def registrar(exc_type, exc_value, exc_tb, contexto=""):
    """Grava o erro no log. Devolve o texto do traceback."""
    texto = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
    if _caminho_log:
        try:
            with open(_caminho_log, "a", encoding="utf-8") as f:
                f.write(f"\n===== {datetime.now():%d/%m/%Y %H:%M:%S} {contexto}\n")
                f.write(texto)
        except Exception:
            pass
    return texto


def _avisar(texto):
    """Mostra o erro uma vez por execução.

    Uma só: um erro dentro de um callback que repete (um `after`, o redesenho
    de um canvas) abriria uma caixa por repetição e prenderia a máquina.
    """
    global _ja_avisou
    if _ja_avisou:
        return
    _ja_avisou = True
    onde = f"\n\nDetalhes gravados em:\n{_caminho_log}" if _caminho_log else ""
    resumo = texto.strip().splitlines()[-1] if texto.strip() else "erro desconhecido"
    try:
        from tkinter import messagebox
        messagebox.showerror(
            "Gestor de Evidências",
            f"Ocorreu um erro inesperado.\n\n{resumo}{onde}")
    except Exception:
        try:
            import ctypes
            ctypes.windll.user32.MessageBoxW(
                None, f"Ocorreu um erro inesperado.\n\n{resumo}{onde}",
                "Gestor de Evidências", 0x10)
        except Exception:
            pass


def instalar(data_dir):
    """Liga a captura de erros não tratados do processo."""
    global _caminho_log
    _caminho_log = _definir_log(data_dir)

    def excecao_nao_tratada(exc_type, exc_value, exc_tb):
        if issubclass(exc_type, KeyboardInterrupt):
            return
        _avisar(registrar(exc_type, exc_value, exc_tb, "não tratada"))

    sys.excepthook = excecao_nao_tratada
    return _caminho_log


def proteger_tk(root):
    """Faz os erros dentro de callback do Tk chegarem ao log e à tela."""
    def erro_em_callback(exc_type, exc_value, exc_tb):
        _avisar(registrar(exc_type, exc_value, exc_tb, "callback do Tk"))

    try:
        root.report_callback_exception = erro_em_callback
    except Exception:
        pass
