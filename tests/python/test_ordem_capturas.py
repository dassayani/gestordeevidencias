# -*- coding: utf-8 -*-
"""A ordem cronologica dos prints: de onde vem o instante e como se ordena.

Sem janela. O defeito de origem: o documento ordenava pelo NOME do arquivo em
ordem decrescente e a galeria, pelo mtime decrescente - o ultimo print virava o
passo 1. Ordenar por mtime nao serve de conserto: o editor regrava o PNG, e o
mtime de um print editado passa a ser o da edicao.

Cobre:
  * a precedencia das fontes: captured_at, nome com data, mtime, e o caso do
    print antigo ja editado
  * o instante nao muda ao editar (o print editado mantem o lugar)
  * nenhuma gravacao - editor, legenda, garantir - perde o captured_at
  * dois dias com o padrao `hora`, virada de meia-noite e padroes misturados
  * a ordenacao e deterministica, ate com empate e entrada embaralhada
  * a galeria continua em mtime decrescente
"""

import os as _os
import sys as _sys

RAIZ = _os.path.dirname(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
_sys.path.insert(0, RAIZ)
_os.chdir(RAIZ)

import os, sys, tempfile, shutil, random
from datetime import datetime

from PIL import Image
from gestor.dados import capture_store as cs

falhas = []


def checar(condicao, descricao):
    print(("OK: " if condicao else "FALHOU: ") + descricao)
    if not condicao:
        falhas.append(descricao)


tmp = tempfile.mkdtemp(prefix="ge_ordem_")


def ts(texto):
    """'2026-09-21 14:30:05' -> segundos desde a epoca (hora local)."""
    return datetime.strptime(texto, "%Y-%m-%d %H:%M:%S").timestamp()


def criar(nome, mtime=None, meta=None, editado=False):
    """Um print de verdade em disco, com mtime e metadados controlados."""
    caminho = os.path.join(tmp, nome)
    Image.new("RGB", (8, 8), (10, 20, 30)).save(caminho)
    if meta is not None:
        cs.save_meta(caminho, meta, marcar_editada=False)
    if editado:
        dados = cs._ler_json(caminho)
        dados["edited_at"] = "2026-09-21T18:00:00"
        cs.save_meta(caminho, dados, marcar_editada=False)
    if mtime is not None:
        os.utime(caminho, (mtime, mtime))
    return caminho


try:
    # ---------------- precedencia das fontes ----------------
    c = criar("print_20260101_080000.png", mtime=ts("2026-09-30 10:00:00"),
              meta={"captured_at": "2026-09-21T14:30:05"})
    checar(cs.instante_da_captura(c) == ts("2026-09-21 14:30:05"),
           "captured_at vence o nome e o mtime, mesmo contraditorios")

    c = criar("print_20260921_143005.png", mtime=ts("2026-10-05 09:00:00"))
    checar(cs.instante_da_captura(c) == ts("2026-09-21 14:30:05"),
           "sem captured_at, a data e a hora do nome (padrao data_hora) vencem o mtime")

    c = criar("print_143005.png", mtime=ts("2026-09-21 14:30:06"))
    checar(cs.instante_da_captura(c) == ts("2026-09-21 14:30:06"),
           "print nunca editado com nome so de hora: vale o mtime")

    c = criar("print_143005.png", mtime=ts("2026-09-21 14:30:06"),
              meta={"captured_at": "lixo que nao e data"})
    checar(cs.instante_da_captura(c) == ts("2026-09-21 14:30:06"),
           "captured_at ilegivel nao quebra: cai para o proximo criterio")

    checar(cs.instante_da_captura(os.path.join(tmp, "nao_existe.png")) == 0.0,
           "arquivo inexistente da instante 0 em vez de levantar erro")

    # ---------------- print antigo, ja editado ----------------
    c = criar("print_093000.png", mtime=ts("2026-09-21 16:45:00"), editado=True)
    checar(cs.instante_da_captura(c) == ts("2026-09-21 09:30:00"),
           "antigo e editado: hora do nome com o dia do mtime (editado as 16:45)")

    c = criar("print_233000.png", mtime=ts("2026-09-22 00:10:00"), editado=True)
    checar(cs.instante_da_captura(c) == ts("2026-09-21 23:30:00"),
           "antigo e editado depois da meia-noite: a captura e do dia anterior")

    c = criar("captura qualquer.png", mtime=ts("2026-09-21 16:45:00"), editado=True)
    checar(cs.instante_da_captura(c) == ts("2026-09-21 16:45:00"),
           "antigo, editado e sem hora no nome: nao ha o que fazer alem do mtime")

    # ---------------- garantir_captured_at ----------------
    c = criar("print_150000.png", mtime=ts("2026-09-21 15:00:03"),
              meta={"caption": "Tela de login", "caso": "CT-9", "shapes": [{"id": 1}]})
    antes_editada = cs.load_meta(c).get("edited_at")
    checar(cs.garantir_captured_at(c) is True, "garantir grava o campo num print antigo")
    meta = cs.load_meta(c)
    checar(meta["captured_at"] == datetime.fromtimestamp(ts("2026-09-21 15:00:03")).isoformat(),
           "e grava o instante calculado")
    checar(meta.get("edited_at") == antes_editada,
           "sem marcar o print como editado")
    checar(meta["caption"] == "Tela de login" and meta["caso"] == "CT-9"
           and meta["shapes"] == [{"id": 1}], "e sem perder legenda, caso nem anotacoes")
    os.utime(c, (ts("2026-10-30 12:00:00"),) * 2)
    checar(cs.garantir_captured_at(c) is False, "uma segunda vez nao faz nada")
    checar(cs.instante_da_captura(c) == ts("2026-09-21 15:00:03"),
           "e o instante nao acompanha mais o mtime")
    checar(cs.garantir_captured_at(os.path.join(tmp, "nao_existe.png")) is False,
           "arquivo inexistente: devolve False")

    # ---------------- nenhuma gravacao perde o campo ----------------
    c = criar("print_160000.png", mtime=ts("2026-09-21 16:00:00"),
              meta={"captured_at": "2026-09-21T16:00:00", "caption": ""})
    cs.save_meta(c, {"caption": "Editado", "caso": "", "shapes": []})      # como o editor
    checar(cs.load_meta(c)["captured_at"] == "2026-09-21T16:00:00",
           "save_meta sem o campo (como o editor) nao o apaga")
    checar(bool(cs.load_meta(c)["edited_at"]), "e marca a edicao normalmente")
    cs.save_caption(c, "Outra legenda")
    checar(cs.load_meta(c)["captured_at"] == "2026-09-21T16:00:00",
           "save_caption nao apaga o campo")
    cs.save_meta(c, {"caption": "x", "captured_at": "2020-01-01T00:00:00"})
    checar(cs.load_meta(c)["captured_at"] == "2020-01-01T00:00:00",
           "mas quem passa um valor explicito consegue troca-lo")

    # ---------------- registrar_captura ----------------
    c = os.path.join(tmp, "print_170000.png")
    Image.new("RGB", (8, 8)).save(c)
    fixo = datetime(2026, 9, 21, 17, 0, 0)
    cs.registrar_captura(c, quando=fixo)
    meta = cs._ler_json(c)
    checar(meta["captured_at"] == fixo.isoformat() and meta["edited_at"] is None,
           "registrar_captura grava o instante e nao marca como editada")
    checar(not os.path.exists(cs.raw_path(c)),
           "e nao cria o .raw.png (a captura nao pode ficar mais lenta)")
    c2 = os.path.join(tmp, "print_170001.png")
    Image.new("RGB", (8, 8)).save(c2)
    cs.registrar_captura(c2)
    agora = datetime.now().timestamp()
    checar(abs(cs.instante_da_captura(c2) - agora) < 5, "sem `quando`, usa o momento atual")

    # ---------------- ordenar: o print editado mantem o lugar ----------------
    base = datetime(2026, 9, 21, 9, 0, 0).timestamp()
    cinco = []
    for i in range(5):
        cinco.append(criar("print_%02d0000.png" % (9 + i), mtime=base + i * 60,
                           meta={"captured_at": datetime.fromtimestamp(base + i * 60).isoformat()}))
    cs.save_meta(cinco[1], {"caption": "anotado", "shapes": [{"id": 1}]})   # edita o 2o
    os.utime(cinco[1], (base + 9999, base + 9999))                           # mtime mais novo
    ordem = cs.ordenar_por_captura(cinco)
    checar(ordem == cinco, "editar o 2o print nao o joga para o fim: a ordem segue a captura")
    checar(cs.ordenar_por_captura(cinco, decrescente=True) == list(reversed(cinco)),
           "decrescente e o inverso exato")
    por_mtime = sorted(cinco, key=os.path.getmtime)
    checar(por_mtime != cinco, "pre-condicao: ordenar por mtime teria errado")

    # ---------------- dois dias, padrao `hora`, meia-noite ----------------
    ontem = criar("print_091500.png", mtime=ts("2026-09-20 09:15:00"),
                  meta={"captured_at": "2026-09-20T09:15:00"})
    hoje = criar("print_083000.png", mtime=ts("2026-09-21 08:30:00"),
                 meta={"captured_at": "2026-09-21T08:30:00"})
    checar(sorted([hoje, ontem], key=os.path.basename) == [hoje, ontem],
           "pre-condicao: pelo nome, o print de hoje viria antes do de ontem")
    checar(cs.ordenar_por_captura([hoje, ontem]) == [ontem, hoje],
           "dois dias com o padrao hora: ordena pelo instante, nao pelo nome")
    tarde = criar("print_235900.png", mtime=ts("2026-09-21 23:59:00"),
                  meta={"captured_at": "2026-09-21T23:59:00"})
    cedo = criar("print_000200.png", mtime=ts("2026-09-22 00:02:00"),
                 meta={"captured_at": "2026-09-22T00:02:00"})
    checar(cs.ordenar_por_captura([cedo, tarde]) == [tarde, cedo],
           "passando da meia-noite, 00:02 vem depois de 23:59")

    # ---------------- padroes misturados ----------------
    a = criar("print_20260921_100000.png", mtime=ts("2026-09-21 10:00:01"))
    b = criar("print_103000.png", mtime=ts("2026-09-21 10:30:01"))
    d = criar("print_20260921_110000.png", mtime=ts("2026-09-21 11:00:01"))
    checar(cs.ordenar_por_captura([d, b, a]) == [a, b, d],
           "padroes data_hora e hora na mesma selecao: ordem por instante")

    # ---------------- determinismo ----------------
    mesmo = ts("2026-09-21 12:00:00")
    iguais = [criar("print_12%04d.png" % n, mtime=mesmo,
                    meta={"captured_at": datetime.fromtimestamp(mesmo).isoformat()})
              for n in (30, 10, 20)]
    esperado = sorted(iguais, key=lambda p: os.path.basename(p).lower())
    resultados = set()
    gerador = random.Random(7)
    for _ in range(100):
        embaralhado = list(iguais)
        gerador.shuffle(embaralhado)
        resultados.add(tuple(cs.ordenar_por_captura(embaralhado)))
    checar(resultados == {tuple(esperado)},
           "empate no mesmo segundo: 100 entradas embaralhadas dao a mesma saida (desempate pelo nome)")
    checar(cs.ordenar_por_captura(set(iguais)) == esperado,
           "entrada em set (como a selecao da galeria) tambem")
    checar(cs.ordenar_instantes([]) == [], "lista vazia")

    # ---------------- a galeria nao regrediu ----------------
    pasta = os.path.join(tmp, "galeria")
    os.makedirs(pasta)
    for i, nome in enumerate(("print_a.png", "print_b.png", "print_c.png")):
        p = os.path.join(pasta, nome)
        Image.new("RGB", (8, 8)).save(p)
        os.utime(p, (1000 + i, 1000 + i))
    cs.registrar_captura(os.path.join(pasta, "print_a.png"),
                         quando=datetime(2030, 1, 1))           # captura "futura"
    nomes = [i["name"] for i in cs.list_captures(pasta)]
    checar(nomes == ["print_c.png", "print_b.png", "print_a.png"],
           "list_captures segue em mtime decrescente: a galeria nao mudou")
except Exception:
    import traceback
    falhas.append("erro: " + traceback.format_exc())

shutil.rmtree(tmp, ignore_errors=True)
print()
print("FALHAS:", falhas if falhas else "nenhuma")
sys.exit(1 if falhas else 0)
