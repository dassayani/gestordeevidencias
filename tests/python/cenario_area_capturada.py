"""Alvo colorido nos DOIS monitores, com o mesmo modo de DPI do main.py.

Se a captura estiver deslocada num deles, as cores dos cantos nao batem.
"""

import os as _os
import sys as _sys

# Raiz do projeto a partir deste arquivo: tests/python/x.py -> duas pastas acima
RAIZ = _os.path.dirname(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
_sys.path.insert(0, RAIZ)
_os.chdir(RAIZ)
SAIDA = _os.path.join(RAIZ, "tests", "_saida")
_os.makedirs(SAIDA, exist_ok=True)

import ctypes
import sys
import tkinter as tk

# EXATAMENTE o que o main.py faz
_PER_MONITOR_V2 = ctypes.c_void_p(-4)
try:
    if not ctypes.windll.user32.SetProcessDpiAwarenessContext(_PER_MONITOR_V2):
        raise OSError("recusado")
    print("modo de DPI: PER_MONITOR_V2")
except Exception:
    ctypes.windll.shcore.SetProcessDpiAwareness(1)
    print("modo de DPI: SYSTEM (reserva)")

from PIL import ImageGrab
from screeninfo import get_monitors

u = ctypes.windll.user32
vx, vy = u.GetSystemMetrics(76), u.GetSystemMetrics(77)
vw, vh = u.GetSystemMetrics(78), u.GetSystemMetrics(79)
img_total = ImageGrab.grab(all_screens=True)
print("area virtual: origem=(%d,%d) %dx%d | ImageGrab: %dx%d"
      % (vx, vy, vw, vh, img_total.size[0], img_total.size[1]))

falhas = []


def checar(cond, msg):
    print(("OK: " if cond else "FALHOU: ") + msg)
    if not cond:
        falhas.append(msg)


checar((vw, vh) == img_total.size,
       "a area calculada bate com a imagem capturada (base de tudo)")

L, A = 400, 300
CORES = {"ne": ("#FF0000", (255, 0, 0)), "nd": ("#00FF00", (0, 255, 0)),
         "se": ("#0000FF", (0, 0, 255)), "sd": ("#FFFF00", (255, 255, 0))}

# um ponto em cada monitor, dentro da area util
monitores = get_monitors()
print("monitores:", [(m.name, m.width, m.height, m.x, m.y) for m in monitores])
pontos = [("principal", vx + 200, vy + 200)]
if vw > 2200:
    pontos.append(("secundario", vx + vw - L - 200, vy + 250))


def testar(nome, X, Y):
    root = tk.Tk()
    root.overrideredirect(True)
    root.geometry("%dx%d+%d+%d" % (L, A, X, Y))
    root.attributes("-topmost", True)
    cv = tk.Canvas(root, width=L, height=A, highlightthickness=0, bd=0)
    cv.pack()
    cv.create_rectangle(0, 0, L // 2, A // 2, fill=CORES["ne"][0], outline="")
    cv.create_rectangle(L // 2, 0, L, A // 2, fill=CORES["nd"][0], outline="")
    cv.create_rectangle(0, A // 2, L // 2, A, fill=CORES["se"][0], outline="")
    cv.create_rectangle(L // 2, A // 2, L, A, fill=CORES["sd"][0], outline="")

    resultado = {}

    def medir():
        root.update_idletasks()
        root.update()
        img = ImageGrab.grab(bbox=(X, Y, X + L, Y + A), all_screens=True).convert("RGB")
        resultado["size"] = img.size
        resultado["cantos"] = {
            "ne": img.getpixel((3, 3)),
            "nd": img.getpixel((L - 4, 3)),
            "se": img.getpixel((3, A - 4)),
            "sd": img.getpixel((L - 4, A - 4)),
        }
        root.quit()

    root.after(700, medir)
    root.after(6000, root.quit)
    root.mainloop()
    root.destroy()

    print("\n--- monitor %s, alvo em (%d,%d) ---" % (nome, X, Y))
    checar(resultado.get("size") == (L, A),
           "%s: captura tem o tamanho pedido (%s)" % (nome, resultado.get("size")))
    for canto, obtido in (resultado.get("cantos") or {}).items():
        esperado = CORES[canto][1]
        ok = all(abs(a - b) <= 14 for a, b in zip(obtido, esperado))
        checar(ok, "%s: canto %s correto (esperado %s, obtido %s)"
               % (nome, canto, esperado, obtido))


for nome, X, Y in pontos:
    testar(nome, X, Y)

print()
print("FALHAS:", falhas if falhas else "nenhuma")
sys.exit(1 if falhas else 0)
