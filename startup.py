"""Integração com o Windows: início automático e atalho no menu Iniciar.

O início automático usa a chave Run do usuário atual (HKCU) — não precisa de
admin e é facilmente reversível. O atalho do menu Iniciar é o que faz o
programa aparecer na pesquisa do Windows.
"""
import os
import sys
import winreg

CHAVE = r"Software\Microsoft\Windows\CurrentVersion\Run"
NOME = "GestorEvidencias"
NOME_ATALHO = "Gestor de Evidencias.lnk"


def _comando_execucao():
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}"'
    pasta_scripts = os.path.dirname(sys.executable)
    pythonw = os.path.join(pasta_scripts, "pythonw.exe")
    script = os.path.abspath(sys.argv[0])
    interpretador = pythonw if os.path.exists(pythonw) else sys.executable
    return f'"{interpretador}" "{script}"'


# ---------- início automático (chave Run) ----------

def esta_habilitado():
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, CHAVE, 0, winreg.KEY_READ) as k:
            winreg.QueryValueEx(k, NOME)
        return True
    except FileNotFoundError:
        return False
    except OSError:
        return False


def habilitar():
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, CHAVE) as k:
        winreg.SetValueEx(k, NOME, 0, winreg.REG_SZ, _comando_execucao())


def desabilitar():
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, CHAVE, 0, winreg.KEY_SET_VALUE) as k:
            winreg.DeleteValue(k, NOME)
    except FileNotFoundError:
        pass
    except OSError:
        pass


def comando_registrado():
    """O comando gravado hoje na chave Run, ou None se não houver."""
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, CHAVE, 0, winreg.KEY_READ) as k:
            valor, _ = winreg.QueryValueEx(k, NOME)
            return valor
    except OSError:
        return None


def sincronizar():
    """Faz o início automático apontar para esta cópia do app.

    Um atalho gravado por uma instalação anterior (ou pela versão em
    código-fonte) continuaria abrindo aquela cópia no login, e a trava de
    instância única impediria a atual de subir — sem nada na tela explicando
    o motivo. Devolve True quando precisou corrigir.
    """
    if not esta_habilitado():
        return False
    atual = _comando_execucao()
    if comando_registrado() == atual:
        return False
    try:
        habilitar()
        return True
    except OSError:
        return False


# ---------- atalho do menu Iniciar (pesquisa do Windows) ----------

def _alvo_do_atalho():
    """(executável, argumentos, pasta de trabalho) para o atalho."""
    if getattr(sys, "frozen", False):
        return sys.executable, "", os.path.dirname(sys.executable)
    pasta_scripts = os.path.dirname(sys.executable)
    pythonw = os.path.join(pasta_scripts, "pythonw.exe")
    script = os.path.abspath(sys.argv[0])
    interpretador = pythonw if os.path.exists(pythonw) else sys.executable
    return interpretador, f'"{script}"', os.path.dirname(script)


def caminho_atalho_menu():
    """Onde fica o atalho do menu Iniciar deste usuário."""
    base = os.environ.get("APPDATA") or os.path.expanduser("~")
    return os.path.join(base, "Microsoft", "Windows", "Start Menu",
                        "Programs", NOME_ATALHO)


def no_menu_iniciar():
    return os.path.exists(caminho_atalho_menu())


def adicionar_ao_menu_iniciar():
    """Cria o atalho que faz o app aparecer na pesquisa do Windows.

    A pesquisa do menu Iniciar indexa os atalhos desta pasta. Sem um .lnk
    ali, o programa só é encontrado navegando até o executável — que é
    justamente o incômodo do formato em pasta.
    """
    import win32com.client

    destino = caminho_atalho_menu()
    os.makedirs(os.path.dirname(destino), exist_ok=True)
    alvo, argumentos, trabalho = _alvo_do_atalho()
    shell = win32com.client.Dispatch("WScript.Shell")
    atalho = shell.CreateShortCut(destino)
    atalho.Targetpath = alvo
    atalho.Arguments = argumentos
    atalho.WorkingDirectory = trabalho
    atalho.Description = "Gestor de Evidencias - capturas de tela para evidencia"
    if getattr(sys, "frozen", False):
        atalho.IconLocation = alvo
    else:
        icone = os.path.join(trabalho, "icon.ico")
        if os.path.exists(icone):
            atalho.IconLocation = icone
    atalho.save()
    return destino


def remover_do_menu_iniciar():
    try:
        os.remove(caminho_atalho_menu())
        return True
    except OSError:
        return False


def atalho_menu_aponta_para_aqui():
    """False quando o atalho existe mas aponta para outra cópia do app."""
    if not no_menu_iniciar():
        return True
    try:
        import win32com.client
        shell = win32com.client.Dispatch("WScript.Shell")
        atalho = shell.CreateShortCut(caminho_atalho_menu())
        alvo, _, _ = _alvo_do_atalho()
        return os.path.normcase(atalho.Targetpath) == os.path.normcase(alvo)
    except Exception:
        return True


def sincronizar_menu_iniciar():
    """Reaponta o atalho do menu Iniciar quando a pasta do app foi movida.

    O .lnk guarda um caminho absoluto: mover a pasta deixaria a pesquisa do
    Windows abrindo um caminho que não existe mais.
    """
    if not no_menu_iniciar() or atalho_menu_aponta_para_aqui():
        return False
    try:
        adicionar_ao_menu_iniciar()
        return True
    except Exception:
        return False
