"""Uma cópia do app por vez, e a segunda traz a primeira pra frente.

Sem isso, duas cópias rodam ao mesmo tempo e só a PRIMEIRA fica com os atalhos
globais: o Windows entrega o Print Screen a quem registrou antes, e o registro
da segunda falha calado. O efeito pra quem usa é o pior possível — a janela
aberta na frente é a que NÃO responde à tecla, e nada na tela explica por quê.
Isso acontece com facilidade porque o app se esconde na bandeja e pode estar
ligado na inicialização do Windows: dar dois cliques no atalho já cria a
segunda cópia.

A conversa entre as cópias usa um mutex nomeado (pra saber quem chegou antes) e
um evento nomeado (pra pedir "mostra a sua janela"). Não se mexe no WNDPROC do
Tk: uma thread espera no evento e publica numa fila, que o lado Tk drena com um
`after`, do mesmo jeito que o hotkey.py faz — é o que mantém toda chamada do
Tkinter na thread dele.
"""
import ctypes
import queue
import threading

_k32 = ctypes.WinDLL("kernel32", use_last_error=True)

# "Local\" limita ao usuário da sessão: duas pessoas logadas na mesma máquina
# continuam podendo usar o app cada uma na sua sessão.
_NOME_MUTEX = "Local\\GestorEvidencias.Instancia"
_NOME_EVENTO = "Local\\GestorEvidencias.Mostrar"

_ERROR_ALREADY_EXISTS = 183
_EVENT_MODIFY_STATE = 0x0002
_INFINITO = 0xFFFFFFFF
_INTERVALO_DRENAGEM_MS = 300

# O mutex precisa viver enquanto o processo viver: se o handle for coletado, a
# trava some e a próxima cópia se acha a primeira.
_mutex = None


def reivindicar():
    """True se esta é a primeira cópia; False se já existe outra rodando."""
    global _mutex
    try:
        _mutex = _k32.CreateMutexW(None, False, _NOME_MUTEX)
        if not _mutex:
            return True   # sem conseguir a trava, é melhor abrir do que travar
        return ctypes.get_last_error() != _ERROR_ALREADY_EXISTS
    except Exception:
        return True


def pedir_para_mostrar():
    """Pede pra cópia que já está rodando aparecer. Silencioso se não houver."""
    try:
        h = _k32.OpenEventW(_EVENT_MODIFY_STATE, False, _NOME_EVENTO)
        if not h:
            return False
        try:
            return bool(_k32.SetEvent(h))
        finally:
            _k32.CloseHandle(h)
    except Exception:
        return False


def escutar(root, ao_pedir):
    """Atende os pedidos das outras cópias, chamando `ao_pedir` no Tk.

    Devolve a fila usada, ou None se não der pra criar o evento — nesse caso o
    app segue funcionando normalmente, só sem o atalho de trazer pra frente.
    """
    try:
        # auto-reset: cada SetEvent libera exatamente uma espera
        evento = _k32.CreateEventW(None, False, False, _NOME_EVENTO)
    except Exception:
        evento = None
    if not evento:
        return None

    pedidos = queue.Queue()

    def laco():
        while True:
            try:
                if _k32.WaitForSingleObject(evento, _INFINITO) == 0:
                    pedidos.put(True)
            except Exception:
                return

    threading.Thread(target=laco, daemon=True).start()

    def drenar():
        try:
            while True:
                pedidos.get_nowait()
                ao_pedir()
        except queue.Empty:
            pass
        except Exception:
            pass
        try:
            root.after(_INTERVALO_DRENAGEM_MS, drenar)
        except Exception:
            pass

    root.after(_INTERVALO_DRENAGEM_MS, drenar)
    return pedidos
