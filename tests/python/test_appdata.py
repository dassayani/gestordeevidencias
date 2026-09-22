# -*- coding: utf-8 -*-
"""Pasta de dados em %APPDATA%, migracao do local antigo e falha visivel."""

import os as _os
import sys as _sys

# Raiz do projeto a partir deste arquivo: tests/python/x.py -> duas pastas acima
RAIZ = _os.path.dirname(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
_sys.path.insert(0, RAIZ)
_os.chdir(RAIZ)
SAIDA = _os.path.join(RAIZ, "tests", "_saida")
_os.makedirs(SAIDA, exist_ok=True)

import sys, os, json, tempfile, shutil
from gestor.dados import config
from gestor.sistema import diagnostico
import main

falhas = []

# ---------- 1) a pasta escolhida fica em %APPDATA% e existe
destino = main._pasta_de_dados()
print("pasta de dados:", destino)
esperado = os.path.join(os.environ.get("APPDATA", ""), "GestorEvidencias")
if os.path.normcase(destino) != os.path.normcase(esperado):
    falhas.append(f"esperava {esperado}, veio {destino}")
if not os.path.isdir(destino):
    falhas.append("a pasta de dados nao foi criada")

# ---------- 2) migracao: config ao lado do "executavel" e trazido
sandbox = tempfile.mkdtemp(prefix="ge_mig_")
exe_falso = os.path.join(sandbox, "programa", "GestorEvidencias.exe")
os.makedirs(os.path.dirname(exe_falso), exist_ok=True)
antigo = os.path.join(os.path.dirname(exe_falso), "config.json")
with open(antigo, "w", encoding="utf-8") as f:
    json.dump({"escala_fonte": "grande", "marca_do_teste": True}, f)

novo_destino = os.path.join(sandbox, "appdata")
os.makedirs(novo_destino, exist_ok=True)
exe_real = sys.executable
sys.executable = exe_falso
try:
    main._migrar_dados_antigos(novo_destino)
finally:
    sys.executable = exe_real

migrado = os.path.join(novo_destino, "config.json")
print("migrou:", os.path.exists(migrado))
if not os.path.exists(migrado):
    falhas.append("o config.json antigo nao foi migrado")
else:
    dados = json.load(open(migrado, encoding="utf-8"))
    if not dados.get("marca_do_teste"):
        falhas.append("o conteudo migrado nao confere")
    else:
        print("   conteudo preservado:", dados)

# ---------- 3) migracao nao sobrescreve o que ja existe
with open(migrado, "w", encoding="utf-8") as f:
    json.dump({"marca_do_teste": False, "ja_existia": True}, f)
sys.executable = exe_falso
try:
    main._migrar_dados_antigos(novo_destino)
finally:
    sys.executable = exe_real
dados = json.load(open(migrado, encoding="utf-8"))
print("preservou o existente:", dados.get("ja_existia") is True)
if not dados.get("ja_existia"):
    falhas.append("a migracao sobrescreveu um config ja existente")

# ---------- 4) gravacao bem-sucedida devolve True
if config.save(novo_destino, {"a": 1}) is not True:
    falhas.append("save() devia devolver True quando grava")

# ---------- 5) gravacao impossivel devolve False e vai para o log
log = os.path.join(tempfile.gettempdir(), "ge_log_teste")
shutil.rmtree(log, ignore_errors=True)
caminho_log = diagnostico.instalar(log)
antes = os.path.getsize(caminho_log) if caminho_log and os.path.exists(caminho_log) else 0
r = config.save(os.path.join(sandbox, "pasta", "que", "nao", "existe"), {"a": 1})
depois = os.path.getsize(caminho_log) if caminho_log and os.path.exists(caminho_log) else 0
print("save em pasta invalida ->", r, "| log cresceu:", depois > antes)
if r is not False:
    falhas.append("save() devia devolver False quando nao grava")
if depois <= antes:
    falhas.append("a falha de gravacao nao foi registrada no log")
else:
    conteudo = open(caminho_log, encoding="utf-8").read()
    if "config.json" not in conteudo:
        falhas.append("o log nao identifica que era o config.json")

shutil.rmtree(sandbox, ignore_errors=True)
print("\nFALHAS:", "nenhuma" if not falhas else "")
for f in falhas:
    print(" -", f)
