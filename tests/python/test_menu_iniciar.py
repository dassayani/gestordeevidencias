# -*- coding: utf-8 -*-
"""Atalho do menu Iniciar: cria, aponta certo, detecta desatualizado, remove.

O estado inicial e restaurado no fim, mesmo se o teste falhar.
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
import startup

falhas = []
existia = startup.no_menu_iniciar()
caminho = startup.caminho_atalho_menu()
print("atalho ja existia:", existia)
print("caminho:", caminho)
print("pasta indexada pela pesquisa:", os.path.dirname(caminho))

def ler_alvo():
    import win32com.client
    shell = win32com.client.Dispatch("WScript.Shell")
    lnk = shell.CreateShortCut(caminho)
    return lnk.Targetpath, lnk.Arguments, lnk.WorkingDirectory

try:
    # 1) criar
    if existia:
        startup.remover_do_menu_iniciar()
    destino = startup.adicionar_ao_menu_iniciar()
    print("\ncriado em:", destino)
    if not startup.no_menu_iniciar():
        falhas.append("o atalho nao foi criado")
    else:
        alvo, args, trabalho = ler_alvo()
        esperado = startup._alvo_do_atalho()
        print("   alvo:", alvo)
        print("   argumentos:", repr(args))
        print("   pasta de trabalho:", trabalho)
        if os.path.normcase(alvo) != os.path.normcase(esperado[0]):
            falhas.append(f"alvo errado: {alvo!r} != {esperado[0]!r}")
        if not os.path.exists(alvo):
            falhas.append(f"o alvo do atalho nao existe: {alvo}")

    # 2) reconhece que aponta para aqui
    if not startup.atalho_menu_aponta_para_aqui():
        falhas.append("nao reconheceu o proprio atalho como atual")

    # 3) atalho apontando para outro lugar e detectado e corrigido
    import win32com.client
    shell = win32com.client.Dispatch("WScript.Shell")
    lnk = shell.CreateShortCut(caminho)
    lnk.Targetpath = r"C:\copia\antiga\GestorEvidencias.exe"
    lnk.save()
    print("\napontei o atalho para uma copia inexistente")
    if startup.atalho_menu_aponta_para_aqui():
        falhas.append("nao detectou que o atalho aponta para outra copia")
    corrigiu = startup.sincronizar_menu_iniciar()
    alvo_depois = ler_alvo()[0]
    print("   sincronizar_menu_iniciar():", corrigiu, "| alvo agora:", alvo_depois)
    if not corrigiu:
        falhas.append("sincronizar_menu_iniciar() nao corrigiu")
    if os.path.normcase(alvo_depois) != os.path.normcase(startup._alvo_do_atalho()[0]):
        falhas.append("o atalho nao voltou a apontar para esta copia")

    # 4) remover
    startup.remover_do_menu_iniciar()
    print("\napos remover, existe:", startup.no_menu_iniciar())
    if startup.no_menu_iniciar():
        falhas.append("o atalho nao foi removido")

finally:
    # devolve como estava
    if existia and not startup.no_menu_iniciar():
        try:
            startup.adicionar_ao_menu_iniciar()
        except Exception:
            pass
    elif not existia and startup.no_menu_iniciar():
        startup.remover_do_menu_iniciar()
    print("estado final igual ao inicial:", startup.no_menu_iniciar() == existia)
    if startup.no_menu_iniciar() != existia:
        falhas.append("nao restaurou o estado inicial do menu Iniciar")

print("\nFALHAS:", "nenhuma" if not falhas else "")
for f in falhas:
    print(" -", f)
