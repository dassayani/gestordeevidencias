"""Inventário das janelas e controles visíveis na tela, para sugerir a área de
captura enquanto o mouse passa por cima.

O inventário é tirado **antes** do overlay de seleção aparecer. Isso não é
detalhe: o overlay cobre o desktop inteiro, então perguntar ao Windows "qual
janela está sob o cursor" enquanto ele está visível devolveria o próprio
overlay. Com a lista pronta em memória, o hit-test durante o movimento do mouse
é só comparação de retângulos — instantâneo e sem chamar a API a cada pixel.
"""
import ctypes
import time
from ctypes import wintypes

import win32con
import win32gui

# Orçamento total gasto consultando acessibilidade ao montar o inventário. Isso
# roda ANTES do seletor aparecer, então cada décimo aqui é espera que o usuário
# sente entre apertar o atalho e poder escolher a área.
_ORCAMENTO_UIA_S = 0.6

# Margem máxima que aceitamos como "borda invisível" ao confiar no DWM.
_FOLGA_MAXIMA_DWM = 24
_DWMWA_EXTENDED_FRAME_BOUNDS = 9


def retangulo_visivel(hwnd):
    """Retângulo do que aparece na tela, sem a moldura invisível.

    `GetWindowRect` inclui a borda de redimensionamento e a sombra do DWM —
    no Windows 11 isso dá cerca de 7 a 11 px sobrando de cada lado, que
    apareciam na captura como uma tira a mais em volta da janela.

    O `DwmGetWindowAttribute` devolve a moldura real, mas em monitor com
    escala diferente da principal ele responde em outro espaço de
    coordenadas (chega a divergir centenas de pixels). Por isso a medida do
    DWM só é aceita quando é levemente MENOR que a do GetWindowRect, que é o
    formato de uma borda invisível de verdade; fora disso, mantém-se a
    medida original.
    """
    try:
        bruto = win32gui.GetWindowRect(hwnd)
    except Exception:
        return None
    try:
        r = wintypes.RECT()
        erro = ctypes.windll.dwmapi.DwmGetWindowAttribute(
            wintypes.HWND(hwnd), ctypes.c_uint(_DWMWA_EXTENDED_FRAME_BOUNDS),
            ctypes.byref(r), ctypes.sizeof(r))
        if erro != 0:
            return bruto
        dwm = (r.left, r.top, r.right, r.bottom)
    except Exception:
        return bruto

    folgas = (dwm[0] - bruto[0], dwm[1] - bruto[1], bruto[2] - dwm[2], bruto[3] - dwm[3])
    if all(0 <= f <= _FOLGA_MAXIMA_DWM for f in folgas):
        return dwm
    return bruto

# Descarta regiões que não servem como sugestão de captura.
LARGURA_MINIMA = 40
ALTURA_MINIMA = 24
# Acima disso a região é praticamente a tela toda (área de trabalho, wallpaper)
# e sugerir isso não ajuda ninguém.
FRACAO_MAXIMA_DA_TELA = 0.92


def _visivel_e_util(hwnd):
    if not win32gui.IsWindowVisible(hwnd):
        return False
    try:
        if win32gui.IsIconic(hwnd):  # minimizada
            return False
        estilo = win32gui.GetWindowLong(hwnd, win32con.GWL_EXSTYLE)
        # janelas-ferramenta e camadas transparentes costumam ser overlays
        # invisíveis que atrapalhariam a sugestão
        if estilo & win32con.WS_EX_TRANSPARENT:
            return False
    except Exception:
        return False
    return True


def _retangulo(hwnd):
    r = retangulo_visivel(hwnd)
    if not r:
        return None
    x1, y1, x2, y2 = r
    if x2 - x1 < LARGURA_MINIMA or y2 - y1 < ALTURA_MINIMA:
        return None
    return (x1, y1, x2, y2)


def _filhos(hwnd, limite=120):
    """Controles internos (painéis, barras, listas), pra sugestão mais fina."""
    encontrados = []

    def visitar(filho, _):
        if len(encontrados) >= limite:
            return False
        if _visivel_e_util(filho):
            r = _retangulo(filho)
            if r:
                encontrados.append(r)
        return True

    try:
        win32gui.EnumChildWindows(hwnd, visitar, None)
    except Exception:
        pass  # EnumChildWindows levanta se a janela morrer no meio da varredura
    return encontrados


def _recortar(rect, area_desktop, area_total):
    """Recorta contra o desktop e descarta o que não serve como sugestão."""
    dx1, dy1, dx2, dy2 = area_desktop
    x1, y1 = max(rect[0], dx1), max(rect[1], dy1)
    x2, y2 = min(rect[2], dx2), min(rect[3], dy2)
    larg, alt = x2 - x1, y2 - y1
    if larg < LARGURA_MINIMA or alt < ALTURA_MINIMA:
        return None
    if (larg * alt) / area_total > FRACAO_MAXIMA_DA_TELA:
        return None
    return (x1, y1, x2, y2)


_UIA_CLSID = "{ff48dba4-60ef-4201-aa87-54103eef594e}"
_PROFUNDIDADE_UIA = 5
_MAX_ELEMENTOS_UIA = 250
_TREESCOPE_CHILDREN = 2


def _criar_uia():
    """Cliente de UI Automation, ou None se não der.

    É opcional de propósito: sem comtypes (ou se a chamada falhar) a detecção
    continua funcionando só com janelas/controles e leitura de bordas.
    """
    try:
        import comtypes.client
        modulo = comtypes.client.GetModule("UIAutomationCore.dll")
        return comtypes.client.CreateObject(_UIA_CLSID, interface=modulo.IUIAutomation)
    except Exception:
        return None


def _elementos_acessibilidade(uia, hwnd, limite=_MAX_ELEMENTOS_UIA):
    """Retângulos dos elementos internos que a janela expõe por acessibilidade.

    É o que enxerga dentro de navegador e Electron, que não têm HWND filho.
    A varredura é limitada em profundidade e em quantidade porque a árvore de
    uma página pesada é enorme e isso roda antes do seletor aparecer.
    """
    if uia is None:
        return []
    retangulos = []
    try:
        raiz = uia.ElementFromHandle(hwnd)
        condicao = uia.CreateTrueCondition()
    except Exception:
        return []

    fila = [(raiz, 0)]
    visitados = 0
    while fila and visitados < limite:
        elemento, nivel = fila.pop(0)
        if nivel >= _PROFUNDIDADE_UIA:
            continue
        try:
            filhos = elemento.FindAll(_TREESCOPE_CHILDREN, condicao)
            total = filhos.Length
        except Exception:
            continue
        for i in range(min(total, 40)):
            if visitados >= limite:
                break
            try:
                filho = filhos.GetElement(i)
                visitados += 1
                r = filho.CurrentBoundingRectangle
                if r.right - r.left >= LARGURA_MINIMA and r.bottom - r.top >= ALTURA_MINIMA:
                    retangulos.append((int(r.left), int(r.top), int(r.right), int(r.bottom)))
                fila.append((filho, nivel + 1))
            except Exception:
                continue
    return retangulos


def listar_regioes(area_desktop, ignorar_hwnds=()):
    """Janelas candidatas em coordenadas absolutas, **em ordem de z-order**
    (da frente para o fundo), cada uma com seus controles internos.

    A ordem importa: sem ela, uma janela de outro app que só encoste no ponto
    poderia ganhar de quem está de fato visível ali.

    Devolve: [(retangulo_da_janela, [retangulos_dos_filhos]), ...]
    """
    dx1, dy1, dx2, dy2 = area_desktop
    area_total = max(1, (dx2 - dx1) * (dy2 - dy1))
    ignorar = set(ignorar_hwnds)
    janelas = []
    uia = _criar_uia()
    prazo_uia = time.time() + _ORCAMENTO_UIA_S

    def visitar(hwnd, _):
        if hwnd in ignorar or not _visivel_e_util(hwnd):
            return True
        if not win32gui.GetWindowText(hwnd) and not _filhos(hwnd, limite=1):
            return True  # sem título e sem conteúdo: provavelmente janela fantasma
        r = _retangulo(hwnd)
        if not r:
            return True
        recortada = _recortar(r, area_desktop, area_total)
        if not recortada:
            return True
        brutos = _filhos(hwnd)
        if not brutos and time.time() < prazo_uia:
            # Janela que não expõe controle nenhum (navegador, Electron,
            # emulador): tenta a árvore de acessibilidade, que é a única
            # forma de enxergar o que existe lá dentro. Só enquanto houver
            # orçamento — com muitas janelas abertas isso somaria segundos.
            brutos = _elementos_acessibilidade(uia, hwnd)
        filhos = []
        for f in brutos:
            f_ok = _recortar(f, area_desktop, area_total)
            if f_ok:
                filhos.append(f_ok)
        janelas.append((recortada, filhos))
        return True

    try:
        # EnumWindows entrega em z-order, da janela da frente para o fundo
        win32gui.EnumWindows(visitar, None)
    except Exception:
        pass
    return janelas


def _contem(rect, x, y):
    return rect[0] <= x <= rect[2] and rect[1] <= y <= rect[3]


# Piso do que vale como sugestão de captura. Sem isto, "o menor controle que
# contém o ponto" quase sempre era um botão, um rótulo ou um avatar: a
# acessibilidade expõe dezenas desses elementos minúsculos dentro de um
# painel, e o menor deles ganhava sempre — o painel e a coluna lateral nunca
# chegavam a ser sugeridos.
AREA_MINIMA_SUGESTAO = 20000      # ~ um cartão de 180x110
LADO_MINIMO_SUGESTAO = 48
# Barra de ferramentas e régua de status são tiras: largas demais pra altura.
PROPORCAO_MAXIMA_SUGESTAO = 20.0


def _serve_como_sugestao(rect):
    larg, alt = rect[2] - rect[0], rect[3] - rect[1]
    if larg < LADO_MINIMO_SUGESTAO or alt < LADO_MINIMO_SUGESTAO:
        return False
    if larg * alt < AREA_MINIMA_SUGESTAO:
        return False
    return max(larg / alt, alt / larg) <= PROPORCAO_MAXIMA_SUGESTAO


def candidatos_sob_ponto(janelas, x, y):
    """Regiões plausíveis no ponto, da menor para a maior.

    Sai da primeira janela em z-order que contém o ponto — a que está de fato
    visível ali — e devolve os controles aninhados que servem como captura,
    mais a janela inteira ao final. Devolver a pilha toda, em vez de um único
    palpite, é o que permite alternar entre o cartão, o painel e a janela.
    """
    for rect_janela, filhos in janelas:
        if not _contem(rect_janela, x, y):
            continue
        achados = []
        for f in filhos:
            if _contem(f, x, y) and _serve_como_sugestao(f):
                achados.append(f)
        achados.sort(key=lambda r: (r[2] - r[0]) * (r[3] - r[1]))
        achados.append(rect_janela)
        # remove aninhados quase idênticos (o mesmo painel visto como HWND e
        # como elemento de acessibilidade)
        unicos = []
        for r in achados:
            if not any(all(abs(a - b) <= 8 for a, b in zip(r, u)) for u in unicos):
                unicos.append(r)
        return unicos
    return []
