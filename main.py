"""Ponto de entrada: DPI, pastas de dados, ícone de bandeja e a janela principal."""
import ctypes
import os
import shutil
import sys

from tkinterdnd2 import TkinterDnD

# DPI por monitor (PER_MONITOR_AWARE_V2). Com o modo anterior (SYSTEM_DPI_AWARE)
# o Windows virtualizava as coordenadas em monitor com escala diferente da
# principal: o app calculava a área da tela como 5760x1620 enquanto o ImageGrab
# devolvia 3840x1147, e o recorte da captura saía deslocado nesse monitor.
# Os valores vêm de DPI_AWARENESS_CONTEXT (ponteiros sentinela negativos).
_PER_MONITOR_V2 = ctypes.c_void_p(-4)
try:
    if not ctypes.windll.user32.SetProcessDpiAwarenessContext(_PER_MONITOR_V2):
        raise OSError("contexto de DPI recusado")
except Exception:
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)   # Windows 8.1 a 10 1607
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()    # anteriores
        except Exception:
            pass

# Sem uma identidade própria o Windows agrupa as janelas sob o python.exe e usa
# o ícone dele na barra de tarefas, ignorando o iconbitmap das janelas. Precisa
# ser chamado antes de qualquer janela existir.
try:
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("GestorEvidencias.App")
except Exception:
    pass

def _migrar_dados_antigos(destino):
    """Traz o config.json de versoes que gravavam ao lado do executavel."""
    novo = os.path.join(destino, "config.json")
    if os.path.exists(novo):
        return
    antigo = os.path.join(os.path.dirname(sys.executable), "config.json")
    try:
        if os.path.exists(antigo):
            shutil.copy2(antigo, novo)
    except Exception:
        pass


def _pasta_de_dados():
    """Onde ficam config.json e erros.log quando o app roda empacotado.

    Ao lado do executavel so funciona se a pasta do programa for gravavel.
    Numa instalacao em "Program Files" a escrita falha e cada preferencia
    ajustada desaparece no proximo inicio, sem aviso. %APPDATA% e gravavel
    por definicao e e onde o Windows espera esse tipo de arquivo.
    """
    raiz = os.environ.get("APPDATA") or os.path.expanduser("~")
    pasta = os.path.join(raiz, "GestorEvidencias")
    try:
        os.makedirs(pasta, exist_ok=True)
    except Exception:
        return os.path.dirname(sys.executable)
    _migrar_dados_antigos(pasta)
    return pasta


if getattr(sys, "frozen", False):
    BASE_DIR = sys._MEIPASS
    DATA_DIR = _pasta_de_dados()
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    DATA_DIR = BASE_DIR

def _pasta_imagens():
    """Pasta "Imagens" do usuário.

    Usa a API do Windows em vez de montar o caminho na mão: ela respeita o
    nome localizado e o redirecionamento (Imagens apontando pro OneDrive, por
    exemplo). Cai no ~/Pictures se a chamada falhar.
    """
    try:
        import ctypes.wintypes
        buf = ctypes.create_unicode_buffer(ctypes.wintypes.MAX_PATH)
        CSIDL_MYPICTURES = 0x27
        if ctypes.windll.shell32.SHGetFolderPathW(None, CSIDL_MYPICTURES, None, 0, buf) == 0:
            if buf.value:
                return buf.value
    except Exception:
        pass
    return os.path.join(os.path.expanduser("~"), "Pictures")


# Padrão de instalação: as capturas vão pra Imagens\Capturas, não pra dentro da
# pasta do programa. Quem já escolheu outra pasta nas Configurações continua com
# a dela (workspace._resolver_pasta_capturas decide). Os documentos gerados vão
# pra subpastas PDF/ e DOCX/ dentro da pasta de capturas vigente — quem monta
# esse caminho é workspace.pasta_documentos().
PASTA_CAPTURAS = os.path.join(_pasta_imagens(), "Capturas")
PASTA_PDFS = os.path.join(PASTA_CAPTURAS, "PDF")

try:
    os.makedirs(PASTA_CAPTURAS, exist_ok=True)
except Exception:
    # Reserva ao lado do programa quando "Imagens" não aceita. O segundo
    # makedirs também é protegido: numa instalação em pasta somente-leitura
    # a exceção ocorreria na importação, sem janela para relatar o erro.
    PASTA_CAPTURAS = os.path.join(DATA_DIR, "Capturas")
    PASTA_PDFS = os.path.join(PASTA_CAPTURAS, "PDF")
    try:
        os.makedirs(PASTA_CAPTURAS, exist_ok=True)
    except Exception:
        pass

import diagnostico  # noqa: E402
import instancia  # noqa: E402
import startup  # noqa: E402
from workspace import AppEvidencias  # noqa: E402  (precisa vir depois do ajuste de sys.path/DPI)

if __name__ == "__main__":
    diagnostico.instalar(DATA_DIR)

    # Se a inicializacao automatica aponta para outra copia, reaponta para
    # esta - senao o login abriria a copia antiga e esta nao subiria.
    try:
        if startup.sincronizar():
            print("[inicializacao] atalho de inicio automatico atualizado")
        if startup.sincronizar_menu_iniciar():
            print("[inicializacao] atalho do menu Iniciar atualizado")
    except Exception:
        pass

    # Uma cópia só: a segunda perderia os atalhos globais em silêncio, porque
    # o Windows entrega a tecla a quem registrou primeiro.
    if not instancia.reivindicar():
        instancia.pedir_para_mostrar()
        sys.exit(0)

    root = TkinterDnD.Tk()
    diagnostico.proteger_tk(root)
    app = AppEvidencias(root, PASTA_CAPTURAS, PASTA_PDFS, BASE_DIR, DATA_DIR)
    instancia.escutar(root, app.mostrar_janela)
    root.mainloop()
