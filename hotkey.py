"""Atalhos de teclado globais (funcionam com a janela escondida/sem foco).

O Tkinter não recebe teclas fora da própria janela em foco, então isso usa o
RegisterHotKey do Windows.

A implementação anterior substituía o WNDPROC da janela do Tk por uma função
Python (SetWindowLong + GWL_WNDPROC). Funcionava pra registrar, mas na hora em
que a tecla era realmente apertada o processo morria com
"PyEval_RestoreThread: the GIL is released (thread state is NULL)" — o Windows
chamava o código Python de dentro do despacho de mensagens sem estado de
thread válido. Ou seja: o atalho derrubava o app.

Aqui não se toca na janela do Tk. Uma thread própria registra os atalhos com
hwnd nulo (o Windows então entrega WM_HOTKEY na fila de mensagens da PRÓPRIA
thread) e roda seu laço de mensagens. Quando a tecla chega, o id vai pra uma
fila; o lado Tk drena essa fila com um `after` periódico e executa o callback
na thread do Tkinter. Nenhuma chamada do Tk acontece fora da thread dele, que
é o que torna isso seguro.
"""
import queue
import threading
import time

import win32con
import win32gui

WM_HOTKEY = 0x0312
MOD_NOREPEAT = 0x4000
MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_WIN = 0x0008

VK_SNAPSHOT = 0x2C  # tecla "Print Screen"

_INTERVALO_DRENAGEM_MS = 60   # com que frequência o Tk verifica a fila
_INTERVALO_LACO_S = 0.02      # espera entre varreduras da fila de mensagens


def vk_letra(letra):
    return ord(letra.upper())


# Combinações oferecidas nas Configurações. Cada item é
# (chave no config, rótulo na tela, modificadores, tecla virtual).
COMBOS_CAPTURA_AREA = [
    ("printscreen", "Print Screen", 0, VK_SNAPSHOT),
    ("ctrl_shift_s", "Ctrl+Shift+S", MOD_CONTROL | MOD_SHIFT, vk_letra("S")),
    ("ctrl_shift_p", "Ctrl+Shift+P", MOD_CONTROL | MOD_SHIFT, vk_letra("P")),
    ("ctrl_alt_s", "Ctrl+Alt+S", MOD_CONTROL | MOD_ALT, vk_letra("S")),
]
COMBOS_JANELA_ATIVA = [
    ("nenhum", "Desativado", None, None),
    ("ctrl_shift_w", "Ctrl+Shift+W", MOD_CONTROL | MOD_SHIFT, vk_letra("W")),
    ("ctrl_alt_w", "Ctrl+Alt+W", MOD_CONTROL | MOD_ALT, vk_letra("W")),
]

# Programas de captura prendem o Print Screen por gancho de teclado, não por
# RegisterHotKey. O registro do app continua válido e sem erro, mas a tecla é
# consumida antes do despacho do atalho — situação que o app não tem como
# detectar sozinho, daí o aviso baseado nos processos em execução.
PROGRAMAS_QUE_DISPUTAM_PRINTSCREEN = {
    "lightshot.exe": "Lightshot",
    "sharex.exe": "ShareX",
    "greenshot.exe": "Greenshot",
    "snagit32.exe": "Snagit",
    "snagiteditor.exe": "Snagit",
    "picpick.exe": "PicPick",
    "flameshot.exe": "Flameshot",
}
# O OneDrive ficou de fora de propósito: ele só fica com a tecla quando a opção
# "salvar capturas no OneDrive" está ligada, e está em praticamente toda
# máquina Windows. Avisar sobre ele sempre ensinaria a ignorar o aviso — que
# aí não serviria pro caso em que ele importa.


def concorrentes_printscreen():
    """Nomes amigáveis dos programas em execução que disputam o Print Screen."""
    import ctypes
    from ctypes import wintypes

    class ENTRADA(ctypes.Structure):
        _fields_ = [("dwSize", wintypes.DWORD), ("cntUsage", wintypes.DWORD),
                    ("th32ProcessID", wintypes.DWORD),
                    ("th32DefaultHeapID", ctypes.POINTER(ctypes.c_ulong)),
                    ("th32ModuleID", wintypes.DWORD), ("cntThreads", wintypes.DWORD),
                    ("th32ParentProcessID", wintypes.DWORD),
                    ("pcPriClassBase", ctypes.c_long), ("dwFlags", wintypes.DWORD),
                    ("szExeFile", ctypes.c_char * 260)]

    achados = []
    try:
        k32 = ctypes.windll.kernel32
        snap = k32.CreateToolhelp32Snapshot(0x00000002, 0)
        if snap == -1:
            return achados
        entrada = ENTRADA()
        entrada.dwSize = ctypes.sizeof(ENTRADA)
        try:
            ok = k32.Process32First(snap, ctypes.byref(entrada))
            while ok:
                nome = entrada.szExeFile.decode("latin-1", "ignore").lower()
                amigavel = PROGRAMAS_QUE_DISPUTAM_PRINTSCREEN.get(nome)
                if amigavel and amigavel not in achados:
                    achados.append(amigavel)
                ok = k32.Process32Next(snap, ctypes.byref(entrada))
        finally:
            k32.CloseHandle(snap)
    except Exception:
        pass
    achados.sort()
    return achados


class HotkeyManager:
    def __init__(self, root):
        self.root = root
        self._comandos = queue.Queue()     # pedidos de registrar/remover
        self._eventos = queue.Queue()      # ids de atalho acionados
        self._respostas = queue.Queue()    # resultado de cada registro
        self._callbacks = {}
        self._registros = {}
        self._proximo_id = 1
        self._parar = threading.Event()

        self._thread = threading.Thread(target=self._laco, daemon=True)
        self._thread.start()
        self._job = self.root.after(_INTERVALO_DRENAGEM_MS, self._drenar)

    # ---------- thread dos atalhos ----------

    def _laco(self):
        """Registra e escuta os atalhos, tudo na mesma thread.

        O RegisterHotKey com hwnd nulo é ligado à thread que o chamou, então
        registrar e receber precisam acontecer aqui dentro.
        """
        while not self._parar.is_set():
            while True:
                try:
                    acao, dados = self._comandos.get_nowait()
                except queue.Empty:
                    break
                if acao == "registrar":
                    hotkey_id, vk, modifiers = dados
                    try:
                        win32gui.RegisterHotKey(None, hotkey_id, modifiers | MOD_NOREPEAT, vk)
                        self._respostas.put((hotkey_id, None))
                    except Exception as e:
                        self._respostas.put((hotkey_id, e))
                elif acao == "remover":
                    try:
                        win32gui.UnregisterHotKey(None, dados)
                    except Exception:
                        pass

            try:
                msg = win32gui.PeekMessage(None, 0, 0, win32con.PM_REMOVE)
            except Exception:
                msg = None
            if msg and msg[0]:
                # msg = (retorno, (hwnd, mensagem, wparam, lparam, tempo, ponto))
                dados_msg = msg[1]
                if dados_msg[1] == WM_HOTKEY:
                    self._eventos.put(dados_msg[2])
                continue   # pode ter mais mensagens enfileiradas
            time.sleep(_INTERVALO_LACO_S)

        for hotkey_id in list(self._callbacks):
            try:
                win32gui.UnregisterHotKey(None, hotkey_id)
            except Exception:
                pass

    # ---------- lado Tkinter ----------

    def _drenar(self):
        """Roda na thread do Tk: executa os callbacks das teclas acionadas."""
        try:
            while True:
                hotkey_id = self._eventos.get_nowait()
                cb = self._callbacks.get(hotkey_id)
                if cb:
                    try:
                        cb()
                    except Exception as e:
                        print(f"[atalho global] falha ao executar o atalho: {e}")
        except queue.Empty:
            pass
        if not self._parar.is_set():
            try:
                self._job = self.root.after(_INTERVALO_DRENAGEM_MS, self._drenar)
            except Exception:
                pass

    def registrar(self, nome, vk, modifiers, callback, timeout=2.0):
        """Registra (ou substitui) o atalho `nome`. Levanta RuntimeError se a
        combinação já estiver em uso por outro programa."""
        self.remover(nome)
        if vk is None:
            return
        hotkey_id = self._proximo_id
        self._proximo_id += 1
        self._comandos.put(("registrar", (hotkey_id, vk, modifiers)))
        try:
            respondido, erro = self._respostas.get(timeout=timeout)
        except queue.Empty:
            raise RuntimeError("o serviço de atalhos não respondeu")
        if erro is not None:
            raise RuntimeError("combinação já em uso por outro programa")
        self._registros[nome] = (respondido, vk, modifiers)
        self._callbacks[respondido] = callback

    def remover(self, nome):
        reg = self._registros.pop(nome, None)
        if reg:
            hotkey_id = reg[0]
            self._callbacks.pop(hotkey_id, None)
            self._comandos.put(("remover", hotkey_id))

    def parar(self):
        for nome in list(self._registros.keys()):
            self.remover(nome)
        self._parar.set()
        if self._job is not None:
            try:
                self.root.after_cancel(self._job)
            except Exception:
                pass
            self._job = None
