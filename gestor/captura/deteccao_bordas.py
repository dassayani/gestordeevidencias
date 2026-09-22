"""Detecção de retângulos pela imagem, para sugerir a área de captura dentro
de janelas que o Windows não descreve.

Navegador, Electron e emuladores desenham a interface por conta própria: não
expõem controles ao Windows e nem sempre montam a árvore de acessibilidade.
Nesses casos a única fonte de verdade é o que está na tela — e a captura do
desktop inteiro já está congelada na memória quando o seletor abre, então dá
pra analisá-la sem custo extra de captura.

A ideia é simples e barata: a partir do ponto sob o cursor, procurar para cada
lado a primeira linha/coluna em que a imagem "muda" de forma marcante (borda de
card, moldura de painel, troca de fundo) e devolver esse retângulo.
"""
import numpy as np

# Quanto a média de uma linha/coluna precisa mudar pra ser considerada borda.
# Em tom de 0 a 255; valor baixo demais pega ruído de texto, alto demais só
# enxerga bordas muito fortes.
LIMIAR_BORDA = 18

# Área máxima varrida em volta do cursor. Segura o custo: a varredura é O(n)
# na janela analisada, não na tela inteira.
ALCANCE = 700

LARGURA_MINIMA = 40
ALTURA_MINIMA = 28

# Uma sugestão precisa parecer uma REGIÃO, não uma tira. Sobre texto (editor de
# código, terminal, e-mail) a primeira borda pra cima e pra baixo é a linha
# vizinha, e sem estes limites a sugestão virava uma faixa de ~40px de altura
# atravessando a janela.
LARGURA_UTIL_MINIMA = 120
ALTURA_UTIL_MINIMA = 80
PROPORCAO_MAXIMA = 8.0

# Limiares tentados em ordem: o mais alto ignora a variação fraca do texto e só
# enxerga moldura de painel/card.
LIMIARES = (LIMIAR_BORDA, 45, 80)


def _cinza(imagem):
    """Imagem PIL -> matriz 2D de luminância, em float pra subtrair sem estourar."""
    arr = np.asarray(imagem.convert("L"), dtype=np.float32)
    return arr


def preparar(imagem):
    """Luminância da tela inteira, calculada UMA vez ao abrir o seletor.

    A detecção roda a cada movimento do mouse e em vários limiares; converter
    o recorte a cada chamada custava mais que a própria análise. Com a matriz
    pronta, cada recorte vira fatia de numpy — de graça.
    """
    return _cinza(imagem)


def _matriz(fonte):
    return fonte if isinstance(fonte, np.ndarray) else _cinza(fonte)


def _primeira_quebra(perfil, limiar):
    """Índice da primeira mudança forte ao longo de `perfil` (já ordenado do
    cursor para fora). Devolve None se a imagem for uniforme demais."""
    if perfil.size < 3:
        return None
    referencia = perfil[0]
    diferenca = np.abs(perfil - referencia)
    fortes = np.nonzero(diferenca > limiar)[0]
    if fortes.size == 0:
        return None
    return int(fortes[0])


def retangulo_no_ponto(imagem, x, y, limiar=LIMIAR_BORDA, alcance=ALCANCE):
    """Retângulo sugerido em volta de (x, y), em coordenadas da `imagem`.

    `imagem` é a captura congelada do desktop; (x, y) é o ponto sob o cursor
    no mesmo referencial. Devolve (x1, y1, x2, y2) ou None quando a região é
    uniforme demais pra afirmar qualquer coisa.
    """
    mat = _matriz(imagem)
    altura, largura = mat.shape
    if not (0 <= x < largura and 0 <= y < altura):
        return None

    x1_corte = max(0, x - alcance)
    y1_corte = max(0, y - alcance)
    x2_corte = min(largura, x + alcance)
    y2_corte = min(altura, y + alcance)
    recorte = mat[y1_corte:y2_corte, x1_corte:x2_corte]

    cx = x - x1_corte
    cy = y - y1_corte
    if not (0 <= cy < recorte.shape[0] and 0 <= cx < recorte.shape[1]):
        return None

    linha = recorte[cy, :]
    coluna = recorte[:, cx]

    # varre pra cada lado a partir do cursor
    esq = _primeira_quebra(linha[:cx + 1][::-1], limiar)
    dir_ = _primeira_quebra(linha[cx:], limiar)
    cima = _primeira_quebra(coluna[:cy + 1][::-1], limiar)
    baixo = _primeira_quebra(coluna[cy:], limiar)

    x1 = x - esq if esq is not None else x1_corte
    x2 = x + dir_ if dir_ is not None else x2_corte
    y1 = y - cima if cima is not None else y1_corte
    y2 = y + baixo if baixo is not None else y2_corte

    if x2 - x1 < LARGURA_MINIMA or y2 - y1 < ALTURA_MINIMA:
        return None
    return (int(x1), int(y1), int(x2), int(y2))


def _parece_regiao(retangulo):
    """Descarta tiras finas: linha de texto não é uma área de captura útil."""
    larg = retangulo[2] - retangulo[0]
    alt = retangulo[3] - retangulo[1]
    if larg < LARGURA_UTIL_MINIMA or alt < ALTURA_UTIL_MINIMA:
        return False
    return max(larg / alt, alt / larg) <= PROPORCAO_MAXIMA


def retangulo_util(imagem, x, y, alcance=ALCANCE):
    """Sugestão aproveitável para o ponto, ou None.

    Tenta limiares crescentes: o primeiro que devolver algo com cara de região
    vence. Sobre texto, os limiares baixos só enxergam a linha vizinha, e é o
    limiar alto que acha a moldura do painel em volta.
    """
    for limiar in LIMIARES:
        caixa = retangulo_no_ponto(imagem, x, y, limiar=limiar, alcance=alcance)
        if caixa and _parece_regiao(caixa):
            refinada = refinar(imagem, caixa)
            return refinada if _parece_regiao(refinada) else caixa
    return None


def refinar(imagem, retangulo, margem=3):
    """Encolhe o retângulo até encostar no conteúdo.

    Depois da varredura sobra uma faixa da cor de fundo nas beiradas; isto
    apara essas faixas pra sugestão encostar no que interessa.
    """
    x1, y1, x2, y2 = retangulo
    recorte = _matriz(imagem)[y1:y2, x1:x2]
    if recorte.size == 0:
        return retangulo

    fundo = float(np.median(recorte))
    diferente = np.abs(recorte - fundo) > LIMIAR_BORDA / 2
    linhas = np.nonzero(diferente.any(axis=1))[0]
    colunas = np.nonzero(diferente.any(axis=0))[0]
    if linhas.size == 0 or colunas.size == 0:
        return retangulo

    novo = (x1 + max(0, int(colunas[0]) - margem),
            y1 + max(0, int(linhas[0]) - margem),
            x1 + min(recorte.shape[1], int(colunas[-1]) + 1 + margem),
            y1 + min(recorte.shape[0], int(linhas[-1]) + 1 + margem))
    if novo[2] - novo[0] < LARGURA_MINIMA or novo[3] - novo[1] < ALTURA_MINIMA:
        return retangulo
    return novo


# ---------------------------------------------------------------------------
# Detecção estrutural
# ---------------------------------------------------------------------------
# A varredura acima olha UMA linha e UMA coluna e compara com o pixel sob o
# cursor. Isso não distingue moldura de conteúdo: a lateral de um glifo de
# texto ou a borda de um ícone dá um salto de luminância tão forte quanto a
# moldura de um painel — e, estando mais perto do cursor, ganha sempre. Era
# por isso que a sugestão caía em qualquer detalhe pequeno e nunca achava a
# moldura da janela ou a coluna lateral.
#
# O que separa os dois é a PERSISTÊNCIA: uma borda de verdade é uma linha
# longa, o mesmo salto repetido por centenas de pixels seguidos; o glifo
# aparece só na própria linha. Aqui a pontuação de cada coluna é a fração das
# linhas da faixa em que o salto acontece — perto de 1 numa moldura, perto de
# zero em texto.

# Altura/largura da faixa examinada em volta do cursor ao pontuar uma borda.
MEIA_BANDA = 140
# Fração da faixa que precisa concordar pra valer como borda estrutural.
FRACAO_MINIMA = 0.6
# Salto de luminância, por pixel, que conta como transição.
LIMIARES_ESTRUTURAIS = (12, 28, 55)
# Pixels ignorados junto ao cursor: se ele estiver em cima da própria borda,
# a região sairia com largura zero.
ZONA_MORTA = 3


def _perfil(faixa, limiar, eixo):
    """Fração de linhas (ou colunas) da faixa com transição em cada posição.

    A diferença é medida com salto de 2 px porque as bordas vêm suavizadas:
    numa moldura antisserrilhada a transição se espalha por dois pixels e
    nenhum dos dois passaria sozinho no limiar.
    """
    if faixa.shape[eixo] < 3 or faixa.shape[1 - eixo] == 0:
        return None
    if eixo == 1:
        grad = np.abs(faixa[:, 2:] - faixa[:, :-2])
        return (grad > limiar).mean(axis=0)
    grad = np.abs(faixa[2:, :] - faixa[:-2, :])
    return (grad > limiar).mean(axis=1)


def _busca(escores, inicio, sentido, fracao=FRACAO_MINIMA):
    """Primeira posição forte a partir de `inicio` no sentido dado."""
    if escores is None or inicio < 0 or inicio >= escores.size:
        return None
    if sentido < 0:
        trecho = escores[:inicio + 1][::-1]
        achados = np.nonzero(trecho >= fracao)[0]
        return None if achados.size == 0 else inicio - int(achados[0])
    trecho = escores[inicio:]
    achados = np.nonzero(trecho >= fracao)[0]
    return None if achados.size == 0 else inicio + int(achados[0])


def retangulo_estrutural(imagem, x, y, limiar=LIMIARES_ESTRUTURAIS[1], alcance=ALCANCE):
    """Retângulo delimitado pelas linhas longas mais próximas do ponto."""
    mat = _matriz(imagem)
    altura, largura = mat.shape
    if not (0 <= x < largura and 0 <= y < altura):
        return None

    x1c, y1c = max(0, x - alcance), max(0, y - alcance)
    x2c, y2c = min(largura, x + alcance), min(altura, y + alcance)
    recorte = mat[y1c:y2c, x1c:x2c]
    alt, larg = recorte.shape
    cx, cy = x - x1c, y - y1c
    if not (0 <= cx < larg and 0 <= cy < alt):
        return None

    faixa_v = recorte[max(0, cy - MEIA_BANDA):min(alt, cy + MEIA_BANDA + 1), :]
    faixa_h = recorte[:, max(0, cx - MEIA_BANDA):min(larg, cx + MEIA_BANDA + 1)]
    # índice i do perfil corresponde à fronteira no pixel i + 1 do recorte
    esc_col = _perfil(faixa_v, limiar, 1)
    esc_lin = _perfil(faixa_h, limiar, 0)

    esq = _busca(esc_col,
                 min(cx - ZONA_MORTA, (esc_col.size - 1) if esc_col is not None else 0),
                 -1)
    dire = _busca(esc_col, max(cx + ZONA_MORTA, 0), +1)
    cima = _busca(esc_lin,
                  min(cy - ZONA_MORTA, (esc_lin.size - 1) if esc_lin is not None else 0),
                  -1)
    baixo = _busca(esc_lin, max(cy + ZONA_MORTA, 0), +1)

    x1 = x1c + (esq + 2) if esq is not None else x1c
    x2 = x1c + (dire + 1) if dire is not None else x2c
    y1 = y1c + (cima + 2) if cima is not None else y1c
    y2 = y1c + (baixo + 1) if baixo is not None else y2c
    if x2 - x1 < LARGURA_MINIMA or y2 - y1 < ALTURA_MINIMA:
        return None
    return (int(x1), int(y1), int(x2), int(y2))


def candidatos(imagem, x, y, alcance=ALCANCE):
    """Regiões plausíveis no ponto, da menor para a maior, sem repetições.

    Limiares diferentes enxergam estruturas aninhadas: o baixo pega o cartão,
    o alto pega a moldura do painel em volta. Devolver todas permite o usuário
    alternar entre elas em vez de depender de um único palpite.
    """
    achados = []
    for limiar in LIMIARES_ESTRUTURAIS:
        try:
            caixa = retangulo_estrutural(imagem, x, y, limiar=limiar, alcance=alcance)
        except Exception:
            caixa = None
        if caixa and _parece_regiao(caixa) and not _repetida(caixa, achados):
            achados.append(caixa)
    if not achados:
        # nenhuma linha longa por perto (conteúdo solto sobre fundo liso):
        # a varredura simples ainda serve de palpite
        caixa = retangulo_util(imagem, x, y, alcance=alcance)
        if caixa:
            achados.append(caixa)
    achados.sort(key=lambda r: (r[2] - r[0]) * (r[3] - r[1]))
    return achados


def _repetida(caixa, existentes, folga=8):
    return any(all(abs(a - b) <= folga for a, b in zip(caixa, outra)) for outra in existentes)


# --- colunas verificadas na janela inteira ---------------------------------
# Uma barra lateral, uma régua de numeração ou um painel de navegação têm uma
# marca que nenhum conteúdo tem: a borda vertical atravessa a janela de cima a
# baixo. Verificar isso na altura TODA da janela, e não numa faixa em volta do
# cursor, separa a coluna de verdade de uma tira de texto que por acaso tem as
# laterais alinhadas — e é o que permite baixar o limiar o bastante pra achar
# divisória clara (régua do Notepad++, separador de painel em tema claro) sem
# passar a aceitar ruído.
LIMIAR_COLUNA = 6
FRACAO_COLUNA = 0.7


# Só uma linha a cada N é examinada: a persistência de uma borda ao longo de
# mil pixels não muda por olhar um terço deles, e isso mantém a sugestão
# respondendo enquanto o mouse se move.
AMOSTRAGEM_COLUNA = 3


def coluna_no_ponto(fonte, x, moldura, limiar=LIMIAR_COLUNA, alcance=ALCANCE):
    """Coluna que contém x dentro de `moldura`, com a altura inteira dela."""
    mat = _matriz(fonte)
    altura, largura = mat.shape
    mx1 = max(0, min(moldura[0], largura - 1), x - alcance)
    my1 = max(0, min(moldura[1], altura - 1))
    mx2 = min(max(mx1 + 1, min(moldura[2], largura)), x + alcance)
    my2 = max(my1 + 1, min(moldura[3], altura))
    faixa = mat[my1:my2:AMOSTRAGEM_COLUNA, mx1:mx2]
    if faixa.shape[1] < 3 or faixa.shape[0] < 3:
        return None

    escores = (np.abs(faixa[:, 2:] - faixa[:, :-2]) > limiar).mean(axis=0)
    cx = x - mx1
    esq = _busca(escores, cx - ZONA_MORTA, -1, FRACAO_COLUNA)
    dire = _busca(escores, cx + ZONA_MORTA, +1, FRACAO_COLUNA)
    if esq is None and dire is None:
        return None

    x1 = mx1 + (esq + 2) if esq is not None else mx1
    x2 = mx1 + (dire + 1) if dire is not None else mx2
    if x2 - x1 < LARGURA_MINIMA or (x2 - x1) >= 0.96 * (moldura[2] - moldura[0]):
        return None  # a "coluna" é a janela inteira: não acrescenta nada
    return (int(x1), int(my1), int(x2), int(my2))
