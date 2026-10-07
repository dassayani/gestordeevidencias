# -*- coding: utf-8 -*-
"""A ordem do documento: nasce do inicio ao fim, e o usuario pode mudar.

O usuario tira os prints de um processo ate o fim; ao selecionar todos, o
primeiro passo do documento era o ULTIMO print. A galeria mostra o mais novo
primeiro (convencao certa para uma galeria), mas o documento herdava essa
ordem - por outra chave, o nome do arquivo em ordem decrescente.

Cobre:
  * o documento abre em ordem cronologica, mesmo com os nomes dizendo o
    contrario (dois dias, virada de meia-noite, padroes de nome misturados)
  * a ordem nao depende da ordem da selecao (a selecao da galeria e um set)
  * editar um print nao o tira do lugar, e nao altera o captured_at
  * o seletor: "Mais novos" inverte, "Cronologica" volta, mexer a mao vira
    "ordem manual"; desfazer devolve a ordem E o rotulo
  * a galeria continua com o mais novo primeiro
  * um print capturado de verdade recebe o instante e entra no fim
"""

import os as _os
import sys as _sys

RAIZ = _os.path.dirname(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
_sys.path.insert(0, RAIZ)
_os.chdir(RAIZ)

import os, sys, ctypes, tempfile, shutil, traceback, random, time
from datetime import datetime

if not ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4)):
    ctypes.windll.shcore.SetProcessDpiAwareness(2)

from tkinterdnd2 import TkinterDnD
from PIL import Image
from gestor.dados import capture_store, config
from gestor.ui import document_builder, editor
from gestor.ui.workspace import AppEvidencias

falhas = []
avisos = []
erros_tk = []


def checar(condicao, descricao):
    print(("OK:     " if condicao else "FALHOU: ") + descricao)
    if not condicao:
        falhas.append(descricao)


class DialogoFalso:
    @staticmethod
    def showinfo(titulo, mensagem, **kw):
        avisos.append(("info", titulo, mensagem))

    @staticmethod
    def showerror(titulo, mensagem, **kw):
        avisos.append(("erro", titulo, mensagem))

    @staticmethod
    def showwarning(titulo, mensagem, **kw):
        avisos.append(("aviso", titulo, mensagem))

    @staticmethod
    def askyesno(titulo, mensagem, **kw):
        avisos.append(("pergunta", titulo, mensagem))
        return True


document_builder.messagebox = DialogoFalso
editor.messagebox = DialogoFalso

tmp = tempfile.mkdtemp(prefix="ge_ordem_doc_")
capturas = os.path.join(tmp, "Capturas")
os.makedirs(capturas)


def ts(texto):
    return datetime.strptime(texto, "%Y-%m-%d %H:%M:%S")


# (nome, captured_at ou None, mtime) - o instante REAL de cada print
PRINTS = [
    ("print_20260920_100000.png", None, "2026-09-25 08:00:00"),     # antigo, data no nome
    ("print_235900.png", "2026-09-21 23:59:00", "2026-09-21 23:59:00"),
    ("print_000200.png", "2026-09-22 00:02:00", "2026-09-22 00:02:00"),
    ("print_091500.png", "2026-09-22 09:15:00", "2026-09-22 09:15:00"),
    ("captura_manual.png", None, "2026-09-22 12:00:00"),              # antigo, so o mtime
    ("print_083000.png", "2026-09-23 08:30:00", "2026-09-23 08:30:00"),
]
CRONOLOGICA = [n for n, _, _ in PRINTS]
for nome, quando, mtime in PRINTS:
    caminho = os.path.join(capturas, nome)
    Image.new("RGB", (900, 560), (40 + len(nome) * 5 % 200, 100, 150)).save(caminho)
    if quando:
        capture_store.registrar_captura(caminho, ts(quando))
    stamp = ts(mtime).timestamp()
    os.utime(caminho, (stamp, stamp))

cfg = config.load(tmp)
cfg["pasta_capturas"] = capturas
cfg["copiar_apos_captura"] = False
cfg["som_captura"] = False
cfg["abrir_apos_captura"] = False
config.save(tmp, cfg)

root = TkinterDnD.Tk()
root.report_callback_exception = lambda *a: erros_tk.append(a)
app = AppEvidencias(root, capturas, os.path.join(tmp, "PDF"), RAIZ, tmp)
app.pausar_timer = True
root.deiconify()
root.update()

_relogio = [10_000]


def evento(w, tipo):
    _relogio[0] += 1500
    w.event_generate(tipo, x=4, y=4, rootx=w.winfo_rootx() + 4, rooty=w.winfo_rooty() + 4,
                     time=_relogio[0])


def clicar(w):
    evento(w, "<ButtonPress-1>")
    evento(w, "<ButtonRelease-1>")
    root.update()


def nomes_da(j):
    return [p["nome"] for p in j.passos]


def exibida(j):
    por_frame = {id(r["frame"]): c for c, r in j._cartoes.items()}
    return [os.path.basename(por_frame[id(f)]) for f in j.frame_sequencia.pack_slaves()
            if id(f) in por_frame]


def abrir(selecao):
    j = document_builder.MontarDocumento(app, selecao)
    j.update()
    root.update()
    # o seletor so tem imagem; registra o que `definir` recebeu
    j._pintado = {}
    for chave, pill in (("cron", j._pill_cron), ("rec", j._pill_rec)):
        original = pill.definir

        def gravar(texto, ativo, _o=original, _c=chave, _j=j):
            _j._pintado[_c] = ativo
            return _o(texto, ativo)
        pill.definir = gravar
    j._atualizar_pills_ordem()
    return j


try:
    selecao = set(CRONOLOGICA)
    j = abrir(selecao)

    # ---- nasce do inicio ao fim ----
    por_nome_desc = sorted(CRONOLOGICA, reverse=True)
    checar(por_nome_desc != CRONOLOGICA,
           "pre-condicao: pelo nome em ordem decrescente (a ordem antiga) o resultado seria outro")
    checar(nomes_da(j) == CRONOLOGICA,
           "o documento abre em ordem cronologica, apesar dos nomes (%s)"
           % [n[6:12] for n in nomes_da(j)])
    checar(exibida(j) == CRONOLOGICA, "e a sequencia na tela mostra a mesma ordem")
    checar([p["nome"] for p in j.passos][0] == "print_20260920_100000.png",
           "o primeiro passo e o print mais antigo")
    checar([j._cartoes[p["caminho"]]["numero"] for p in j.passos] == [1, 2, 3, 4, 5, 6],
           "numerados de 1 a 6")
    checar([j._cartoes_centro[p["caminho"]]["selo"].cget("text") for p in j.passos]
           == ["1", "2", "3", "4", "5", "6"], "e a coluna central tambem")
    checar(j._modo_ordem == "cronologica", "o modo inicial e cronologica")
    checar(j._pintado == {"cron": True, "rec": False}, "e o seletor mostra 'Cronologica' ativo")
    checar(not j._lbl_ordem_manual.winfo_ismapped(), "sem o texto 'ordem manual'")

    # ---- ordem independe da ordem da selecao ----
    resultados = set()
    gerador = random.Random(3)
    for _ in range(6):
        embaralhado = list(CRONOLOGICA)
        gerador.shuffle(embaralhado)
        outra = document_builder.MontarDocumento(app, embaralhado)
        outra.update()
        resultados.add(tuple(nomes_da(outra)))
        outra.destroy()
    root.update()
    checar(resultados == {tuple(CRONOLOGICA)},
           "6 selecoes embaralhadas abrem exatamente na mesma ordem")

    # ---- prints antigos ganham o instante, sem virar "editados" ----
    antigo = os.path.join(capturas, "print_20260920_100000.png")
    meta = capture_store.load_meta(antigo)
    checar(bool(meta.get("captured_at")), "o print antigo recebeu captured_at ao entrar no documento")
    checar(meta["captured_at"] == ts("2026-09-20 10:00:00").isoformat(),
           "calculado a partir do nome (%s)" % meta.get("captured_at"))
    checar(not meta.get("edited_at"), "sem ser marcado como editado")
    manual = capture_store.load_meta(os.path.join(capturas, "captura_manual.png"))
    checar(manual.get("captured_at") == ts("2026-09-22 12:00:00").isoformat(),
           "o que so tinha o mtime usou o mtime")

    # ---- a galeria nao mudou: mais novo primeiro ----
    galeria = [i["name"] for i in capture_store.list_captures(capturas)]
    checar(galeria[0] == "print_20260920_100000.png",
           "a galeria segue por mtime decrescente (%s primeiro): so o documento mudou"
           % galeria[0])

    # ---- seletor: Mais novos ----
    antes = nomes_da(j)
    clicar(j._pill_rec)
    checar(nomes_da(j) == list(reversed(antes)) and exibida(j) == list(reversed(antes)),
           "'Mais novos' inverte a ordem, na tela tambem")
    checar(j._modo_ordem == "recentes" and j._pintado == {"cron": False, "rec": True},
           "e o seletor passa a mostrar 'Mais novos'")
    checar(bool(j._aviso_seq.winfo_ismapped()) and "novo" in j._lbl_aviso_seq.cget("text"),
           "com o aviso 'Desfazer' (%r)" % j._lbl_aviso_seq.cget("text"))
    checar([j._cartoes[p["caminho"]]["numero"] for p in j.passos] == [1, 2, 3, 4, 5, 6],
           "e os numeros seguem 1..6 na nova ordem")
    j._desfazer_movimento()
    root.update()
    checar(nomes_da(j) == antes and j._modo_ordem == "cronologica"
           and j._pintado == {"cron": True, "rec": False},
           "Desfazer devolve a ordem E o rotulo do seletor")

    # ---- reaplicar a ordem em vigor nao faz nada ----
    j._esconder_aviso()
    clicar(j._pill_cron)
    checar(nomes_da(j) == antes and not j._aviso_seq.winfo_ismapped(),
           "'Cronologica' quando ja esta cronologica: nada muda e nao ha aviso")

    # ---- mexer a mao: ordem manual ----
    j._mover(0, 1)
    root.update()
    checar(j._modo_ordem == "manual" and bool(j._lbl_ordem_manual.winfo_ismapped()),
           "mover um passo a mao passa para 'ordem manual'")
    checar(j._pintado == {"cron": False, "rec": False},
           "e nenhuma das duas opcoes fica ativa")
    # o texto cabia ao lado das pilulas? Nao: aparecia cortado ("em ma"). Precisa
    # receber toda a largura que pede, dentro da coluna.
    j.update()
    etiqueta = j._lbl_ordem_manual
    limite_direito = j._wrap_seq.winfo_rootx() + j._wrap_seq.winfo_width()
    checar(etiqueta.winfo_width() >= etiqueta.winfo_reqwidth()
           and etiqueta.winfo_rootx() + etiqueta.winfo_reqwidth() <= limite_direito,
           "o texto 'ordem manual' aparece inteiro dentro da coluna (%d de %d px)"
           % (etiqueta.winfo_width(), etiqueta.winfo_reqwidth()))
    checar(all(p.winfo_rootx() + p.winfo_width() <= limite_direito
               for p in (j._pill_cron, j._pill_rec)),
           "e as duas pilulas tambem")
    manual_ordem = nomes_da(j)
    clicar(j._pill_cron)
    checar(nomes_da(j) == antes and j._modo_ordem == "cronologica"
           and not j._lbl_ordem_manual.winfo_ismapped(),
           "'Cronologica' desfaz a ordem manual e o texto some")
    j._desfazer_movimento()
    root.update()
    checar(nomes_da(j) == manual_ordem and j._modo_ordem == "manual",
           "e Desfazer volta a ordem manual, com o rotulo manual")
    j._aplicar_ordem([p["caminho"] for p in j.passos], avisar=False)
    checar(j._modo_ordem == "manual", "soltar um arraste sem mover nada nao muda o rotulo")
    clicar(j._pill_cron)

    # ---- legenda digitada sem evento sobrevive a reordenar pelo seletor ----
    alvo = j.passos[2]
    caixa = j._cartoes_centro[alvo["caminho"]]["txt"]
    caixa.delete("1.0", "end")
    caixa.insert("1.0", "Colada sem evento")
    clicar(j._pill_rec)
    j._sincronizar_legendas()
    checar(next(p for p in j.passos if p["caminho"] == alvo["caminho"])["legenda"]
           == "Colada sem evento", "a legenda digitada acompanha o passo ao reordenar pelo seletor")
    checar(all(j.entries_legenda[i].get("1.0", "end").strip() == p["legenda"]
               for i, p in enumerate(j.passos)),
           "cada caixa de legenda continua no passo certo")
    clicar(j._pill_cron)
    j._esconder_aviso()

    # ---- editar um print nao o tira do lugar ----
    posicao = CRONOLOGICA.index("print_000200.png")
    caminho_b = os.path.join(capturas, "print_000200.png")
    captured_antes = capture_store.load_meta(caminho_b)["captured_at"]
    j._editar_passo(posicao)
    j.update()
    ed = j._editor
    ed.shapes.append({"id": 1, "tool": "retangulo", "coords": [50, 50, 300, 200],
                      "color": "#E8590C", "width": 4, "dash": False, "visible": True})
    ed._marcar_sujo()
    ed.gravar_e_fechar()
    j.update()
    root.update()
    checar(os.path.getmtime(caminho_b) > ts("2026-09-25 00:00:00").timestamp(),
           "pre-condicao: o print editado agora tem o mtime mais novo de todos")
    checar(nomes_da(j) == CRONOLOGICA and exibida(j) == CRONOLOGICA,
           "o print editado continua no mesmo lugar do documento")
    checar(capture_store.load_meta(caminho_b)["captured_at"] == captured_antes,
           "e o editor nao alterou o captured_at")
    checar(bool(capture_store.load_meta(caminho_b).get("edited_at")),
           "mas ele passou a constar como editado")
    galeria = [i["name"] for i in capture_store.list_captures(capturas)]
    checar(galeria[0] == "print_000200.png",
           "ja na galeria (mtime) ele sobe para o topo: e por isso o mtime nao serve para ordenar")

    # ---- coluna espremida ao maximo: botoes e aviso continuam inteiros ----
    j._paineis.sash_place(0, 1, 300)          # divisoria arrastada ate a esquerda
    j.update()
    root.update()
    largura_col = j._col_sequencia.winfo_width()
    checar(largura_col >= 170, "a coluna para no minimo, nao some (%d px)" % largura_col)
    cartao = j._cards[0]
    botoes = [w for w in j._cartoes[j.passos[0]["caminho"]]["topo"].winfo_children()[0].winfo_children()]
    direita = cartao.winfo_rootx() + cartao.winfo_width()
    checar(len(botoes) == 4 and all(b.winfo_width() >= b.winfo_reqwidth()
                                    and b.winfo_rootx() + b.winfo_width() <= direita
                                    for b in botoes),
           "com a coluna no minimo, os 4 botoes (inclusive o ✕) aparecem inteiros: %s"
           % [(b.cget("text"), b.winfo_width(), b.winfo_reqwidth()) for b in botoes])
    larguras = {b.winfo_width() for b in botoes}
    checar(len(larguras) == 1, "e todos com o mesmo tamanho (%s)" % sorted(larguras))
    j._esconder_aviso()
    clicar(j._pill_rec)
    j.update()
    rotulo_aviso = j._lbl_aviso_seq
    desfazer = [w for w in j._aviso_seq.winfo_children() if w is not rotulo_aviso][0]
    checar(bool(j._aviso_seq.winfo_ismapped())
           and rotulo_aviso.winfo_reqwidth() <= rotulo_aviso.winfo_width() + 2,
           "o aviso 'Mais novos primeiro' cabe inteiro (%d de %d px; mapeado=%s, modo=%s, texto=%r)"
           % (rotulo_aviso.winfo_reqwidth(), rotulo_aviso.winfo_width(),
              j._aviso_seq.winfo_ismapped(), j._modo_ordem, rotulo_aviso.cget("text")))
    # uma mensagem mais comprida que a coluna tem de quebrar linha, nao cortar
    j._registrar_movimento([p["caminho"] for p in j.passos], None, "cronologica",
                           texto="Um aviso bem mais comprido do que cabe na coluna estreita")
    j.update()
    j.update()
    checar(rotulo_aviso.winfo_reqwidth() <= rotulo_aviso.winfo_width() + 2
           and rotulo_aviso.winfo_height() >= rotulo_aviso.winfo_reqheight(),
           "um aviso comprido quebra linha em vez de sair cortado (%d de %d px)"
           % (rotulo_aviso.winfo_reqwidth(), rotulo_aviso.winfo_width()))
    checar(desfazer.winfo_width() >= desfazer.winfo_reqwidth()
           and desfazer.winfo_rootx() + desfazer.winfo_width()
           <= j._aviso_seq.winfo_rootx() + j._aviso_seq.winfo_width(),
           "e o 'Desfazer' aparece inteiro")
    clicar(j._pill_cron)

    # ---- o temporizador de um aviso antigo nao esconde o aviso novo ----
    # mover -> Desfazer -> mover de novo, tudo antes de o primeiro aviso vencer:
    # o temporizador do primeiro continuava agendado e sumia com o segundo
    # (e com o "Desfazer" dele) antes da hora.
    aviso_ms = document_builder._AVISO_MS
    document_builder._AVISO_MS = 900
    try:
        inicio = time.time()
        j._mover(0, 1)                   # aviso 1: venceria em 0,9 s
        root.update()
        j._desfazer_movimento()          # esconde o aviso 1
        root.update()
        time.sleep(0.4)
        j._mover(1, -1)                  # aviso 2: vence em ~1,3 s desde o inicio
        root.update()
        while time.time() - inicio < 1.05:   # passa do prazo do aviso 1
            root.update()
            time.sleep(0.02)
        checar(bool(j._aviso_seq.winfo_ismapped()) and j._ordem_antes_mover is not None,
               "o aviso novo (e o Desfazer dele) continua na tela depois do prazo do antigo")
    finally:
        document_builder._AVISO_MS = aviso_ms
    j._esconder_aviso()

    j.destroy()
    root.update()

    # ---- reabrir depois da edicao: mesma ordem, de qualquer selecao ----
    embaralhado = list(CRONOLOGICA)
    random.Random(11).shuffle(embaralhado)
    k = document_builder.MontarDocumento(app, embaralhado)
    k.update()
    checar(nomes_da(k) == CRONOLOGICA,
           "reabrir o documento apos a edicao mantem a ordem cronologica")
    k.destroy()
    root.update()

    # ---- uma captura de verdade recebe o instante e entra no fim ----
    antes_pngs = set(os.listdir(capturas))
    time.sleep(1.1)                   # outro segundo, para o nome `hora` ser novo
    app._salvar_captura(Image.new("RGB", (400, 300), (1, 2, 3)))
    root.update()
    novos = [n for n in set(os.listdir(capturas)) - antes_pngs
             if n.lower().endswith(".png") and not n.lower().endswith(".raw.png")]
    checar(len(novos) == 1, "a captura gerou um arquivo")
    if novos:
        caminho_novo = os.path.join(capturas, novos[0])
        meta_novo = capture_store._ler_json(caminho_novo)
        # Sem o campo gravado, o nome e o mtime de "agora" dariam uma hora quase
        # certa e o teste passaria sem provar nada: exige-se o campo.
        checar(bool(meta_novo.get("captured_at")),
               "o .json da captura nova traz captured_at (%r)" % meta_novo.get("captured_at"))
        checar(abs(capture_store.instante_da_captura(caminho_novo, meta_novo)
                   - datetime.now().timestamp()) < 10,
               "com captured_at igual ao momento da captura")
        checar(meta_novo.get("edited_at") is None, "sem constar como editada")
        # e e o campo que ordena, nao o mtime: envelhecendo o arquivo, o print
        # recem-tirado continua sendo o ultimo passo
        velho = ts("2020-01-01 00:00:00").timestamp()
        os.utime(caminho_novo, (velho, velho))
        m = document_builder.MontarDocumento(app, set(CRONOLOGICA) | {novos[0]})
        m.update()
        checar(nomes_da(m)[-1] == novos[0] and nomes_da(m)[:-1] == CRONOLOGICA,
               "no documento, o print recem-tirado e o ultimo passo")
        m.destroy()
        root.update()

    checar(not [a for a in avisos if a[0] in ("erro", "aviso")], "nenhum aviso ou erro")
    checar(not erros_tk, "nenhum erro silencioso do Tk")
    for e in erros_tk:
        print("   erro Tk:", "".join(traceback.format_exception(*e))[-500:])
except Exception:
    falhas.append("erro: " + traceback.format_exc())

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
os._exit(1 if falhas else 0)
