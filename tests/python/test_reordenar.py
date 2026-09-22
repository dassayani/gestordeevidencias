"""Testa a reordenacao por arraste e o nome do arquivo exportado."""

import os as _os
import sys as _sys

# Raiz do projeto a partir deste arquivo: tests/python/x.py -> duas pastas acima
RAIZ = _os.path.dirname(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
_sys.path.insert(0, RAIZ)
_os.chdir(RAIZ)
SAIDA = _os.path.join(RAIZ, "tests", "_saida")
_os.makedirs(SAIDA, exist_ok=True)

import sys

from gestor.ui import document_builder

falhas = []


def checar(cond, msg):
    print(("OK: " if cond else "FALHOU: ") + msg)
    if not cond:
        falhas.append(msg)


class CardFalso:
    """Imita o retangulo de um card na tela: 100px de altura, empilhados."""

    def __init__(self, indice):
        self.indice = indice

    def winfo_rooty(self):
        return 1000 + self.indice * 100

    def winfo_height(self):
        return 100

    def config(self, **kw):
        pass


class EventoFalso:
    def __init__(self, y):
        self.y_root = y


def montar(n):
    """Instancia a tela sem construir a UI de verdade."""
    doc = document_builder.MontarDocumento.__new__(document_builder.MontarDocumento)
    doc.passos = [{"nome": chr(ord("A") + i), "caminho": "", "legenda": ""} for i in range(n)]
    doc._cards = [CardFalso(i) for i in range(n)]
    doc._arraste = None
    doc._atualizar_sequencia = lambda: None
    doc._atualizar_coluna_central = lambda: None
    doc.parent_app = type("P", (), {"modo_escuro": False})()
    return doc


def nomes(doc):
    return "".join(p["nome"] for p in doc.passos)


def arrastar(doc, origem, y_solta):
    doc._arraste_iniciar(origem)
    doc._arraste_mover(EventoFalso(y_solta))
    doc._arraste_soltar(EventoFalso(y_solta))
    return nomes(doc)


# cards: A=1000-1100 (meio 1050), B=1100-1200 (1150), C=1200-1300 (1250),
#        D=1300-1400 (1350)
checar(arrastar(montar(4), 0, 1360) == "BCDA", "arrastar o primeiro pro fim -> BCDA")
checar(arrastar(montar(4), 3, 1010) == "DABC", "arrastar o ultimo pro topo -> DABC")
checar(arrastar(montar(4), 0, 1160) == "BACD", "descer um item uma posicao -> BACD")
checar(arrastar(montar(4), 2, 1040) == "CABD", "subir o terceiro pro topo -> CABD")
checar(arrastar(montar(4), 1, 1140) == "ABCD", "soltar no mesmo lugar nao muda nada")

# clique simples (sem movimento) nao pode reordenar
d = montar(4)
d._arraste_iniciar(0)
d._arraste_soltar(EventoFalso(1010))
checar(nomes(d) == "ABCD", "clique sem arrastar nao reordena")

# lista de 1 item nao quebra
d1 = montar(1)
checar(arrastar(d1, 0, 5000) == "A", "lista com 1 item aguenta arraste sem quebrar")

# soltar muito abaixo do ultimo card
checar(arrastar(montar(3), 0, 9999) == "BCA", "soltar bem abaixo manda pro fim")

print()
print("FALHAS:", falhas if falhas else "nenhuma")
sys.exit(1 if falhas else 0)
