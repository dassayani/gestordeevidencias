"""Helpers pequenos e sem estado, usados pelo editor e pelo painel principal."""
import ctypes
import io
import math
import os
import struct
import time
from ctypes import wintypes

import win32clipboard
from PIL import Image, ImageDraw, ImageFilter

# O pywin32 não expõe esta constante; é o formato de "lista de arquivos" que o
# Explorer usa ao copiar/colar e que os clientes de e-mail leem como anexo.
CF_HDROP = 15


def hex_to_rgb(hex_color):
    hex_color = hex_color.lstrip("#")
    return tuple(int(hex_color[i:i + 2], 16) for i in (0, 2, 4))


def escurecer(rgb, fator=0.42):
    """Tom escuro derivado de uma cor, para faixa com texto branco em cima.

    A faixa lateral do relatório QA segue a cor de destaque escolhida, mas
    usá-la crua deixaria o texto branco ilegível nas opções claras (amarelo,
    verde). Escurecer mantém o contraste em qualquer uma delas.
    """
    return tuple(max(0, min(255, int(round(c * fator)))) for c in rgb)


def clarear(rgb, fator):
    """Mistura a cor com branco: `fator` 0 devolve a própria cor, 1 devolve branco."""
    fator = max(0.0, min(1.0, fator))
    return tuple(int(round(c + (255 - c) * fator)) for c in rgb)


def _dib(pil_img):
    """Bytes no formato CF_DIB (BMP sem os 14 bytes de cabeçalho de arquivo)."""
    out = io.BytesIO()
    pil_img.convert("RGB").save(out, "BMP")
    dados = out.getvalue()[14:]
    out.close()
    return dados


def _hdrop(caminhos):
    """Bloco DROPFILES: cabeçalho de 20 bytes + caminhos em UTF-16.

    Cada caminho termina em NUL e a lista inteira em NUL duplo, que é como o
    Windows delimita. `fWide=1` avisa que a lista é Unicode — sem isso,
    caminho com acento chega corrompido do outro lado.
    """
    lista = "".join(os.path.abspath(c) + "\0" for c in caminhos) + "\0"
    cabecalho = struct.pack("<IiiII", 20, 0, 0, 0, 1)
    return cabecalho + lista.encode("utf-16-le")


def _abrir_clipboard(tentativas=10, espera=0.05):
    """Abre a area de transferencia, insistindo por meio segundo.

    O Windows so admite um dono por vez: gerenciador de clipboard, Office e
    sessao remota seguram o recurso por alguns milissegundos e a chamada volta
    com "acesso negado". Sem insistir, um Ctrl+C falharia de vez em quando sem
    motivo aparente para quem esta usando.
    """
    for tentativa in range(tentativas):
        try:
            win32clipboard.OpenClipboard()
            return
        except Exception:
            if tentativa == tentativas - 1:
                raise
            time.sleep(espera)


def copy_to_clipboard(image=None, paths=()):
    """Publica a imagem e/ou os arquivos na área de transferência.

    Os dois formatos convivem de propósito: quem cola esperando imagem (Word,
    Paint, Teams) lê o CF_DIB, e quem espera arquivo (Explorer, anexo de
    e-mail) lê o CF_HDROP. Precisa ser uma única sessão de clipboard, porque
    cada `EmptyClipboard` descarta o que foi publicado antes.
    """
    _abrir_clipboard()
    try:
        win32clipboard.EmptyClipboard()
        if image is not None:
            win32clipboard.SetClipboardData(win32clipboard.CF_DIB, _dib(image))
        if paths:
            win32clipboard.SetClipboardData(CF_HDROP, _hdrop(paths))
    finally:
        win32clipboard.CloseClipboard()


def copy_image_to_clipboard(pil_img):
    copy_to_clipboard(image=pil_img)


# --- lixeira do Windows -----------------------------------------------------
# Excluir com os.remove apaga de vez. Numa ferramenta de evidencia isso e
# perigoso: um clique no botao de lixeira sem selecao oferece apagar a pasta
# inteira, e nao haveria volta. O SHFileOperation com FOF_ALLOWUNDO manda para
# a Lixeira, de onde da para restaurar.
_FO_DELETE = 0x0003
_FOF_SILENT = 0x0004
_FOF_NOCONFIRMATION = 0x0010
_FOF_ALLOWUNDO = 0x0040
_FOF_NOERRORUI = 0x0400
_FOF_NOCONFIRMMKDIR = 0x0200
_FOF_WANTNUKEWARNING = 0x4000


class _SHFILEOPSTRUCTW(ctypes.Structure):
    _fields_ = [
        ("hwnd", wintypes.HWND),
        ("wFunc", wintypes.UINT),
        ("pFrom", wintypes.LPCWSTR),
        ("pTo", wintypes.LPCWSTR),
        ("fFlags", ctypes.c_uint16),
        ("fAnyOperationsAborted", wintypes.BOOL),
        ("hNameMappings", ctypes.c_void_p),
        ("lpszProgressTitle", wintypes.LPCWSTR),
    ]


def mover_para_lixeira(caminhos):
    """Manda os arquivos para a Lixeira. Devolve False se nao deu.

    Recebe varios de uma vez porque o Windows agrupa a operacao: apagar uma
    captura (png + raw + json) fica como um unico item para restaurar.
    """
    existentes = [os.path.abspath(c) for c in caminhos if c and os.path.exists(c)]
    if not existentes:
        return True
    # a lista vai terminada em NUL duplo, como a API espera
    lista = "\0".join(existentes) + "\0\0"
    op = _SHFILEOPSTRUCTW()
    op.hwnd = None
    op.wFunc = _FO_DELETE
    op.pFrom = lista
    op.pTo = None
    # Sem confirmacao do Windows: o app ja perguntou. A excecao e o arquivo
    # grande demais para a Lixeira, que seria apagado em definitivo — para esse
    # caso o WANTNUKEWARNING traz o aviso de volta.
    op.fFlags = (_FOF_ALLOWUNDO | _FOF_NOCONFIRMATION | _FOF_SILENT
                 | _FOF_NOERRORUI | _FOF_NOCONFIRMMKDIR | _FOF_WANTNUKEWARNING)
    try:
        resultado = ctypes.windll.shell32.SHFileOperationW(ctypes.byref(op))
    except Exception:
        return False
    return resultado == 0 and not op.fAnyOperationsAborted


def dist_point_segment(px, py, x1, y1, x2, y2):
    dx, dy = x2 - x1, y2 - y1
    if dx == 0 and dy == 0:
        return math.hypot(px - x1, py - y1)
    t = max(0, min(1, ((px - x1) * dx + (py - y1) * dy) / (dx * dx + dy * dy)))
    proj_x, proj_y = x1 + t * dx, y1 + t * dy
    return math.hypot(px - proj_x, py - proj_y)


def draw_arrow(draw, coords, rgb, width):
    x1, y1, x2, y2 = coords
    draw.line([x1, y1, x2, y2], fill=rgb, width=width)
    angle = math.atan2(y2 - y1, x2 - x1)
    length = 14 + width * 3
    p1 = (x2 - length * math.cos(angle - 0.5), y2 - length * math.sin(angle - 0.5))
    p2 = (x2 - length * math.cos(angle + 0.5), y2 - length * math.sin(angle + 0.5))
    draw.polygon([(x2, y2), p1, p2], fill=rgb)


def draw_dashed_line(draw, xy, fill, width, dash_len=10, gap_len=6):
    x1, y1, x2, y2 = xy
    total = math.hypot(x2 - x1, y2 - y1)
    if total == 0:
        return
    dx, dy = (x2 - x1) / total, (y2 - y1) / total
    d = 0
    on = True
    while d < total:
        seg = dash_len if on else gap_len
        nd = min(d + seg, total)
        if on:
            draw.line([x1 + dx * d, y1 + dy * d, x1 + dx * nd, y1 + dy * nd],
                      fill=fill, width=width)
        d = nd
        on = not on


def draw_dashed_rect(draw, xy, fill, width):
    x1, y1, x2, y2 = xy
    x1, x2 = sorted((x1, x2))
    y1, y2 = sorted((y1, y2))
    for seg in [(x1, y1, x2, y1), (x2, y1, x2, y2), (x2, y2, x1, y2), (x1, y2, x1, y1)]:
        draw_dashed_line(draw, seg, fill, width)


def draw_dashed_ellipse(draw, xy, fill, width, steps=72):
    x1, y1, x2, y2 = xy
    cx, cy = (x1 + x2) / 2, (y1 + y2) / 2
    rx, ry = abs(x2 - x1) / 2, abs(y2 - y1) / 2
    pts = [
        (cx + rx * math.cos(2 * math.pi * i / steps), cy + ry * math.sin(2 * math.pi * i / steps))
        for i in range(steps + 1)
    ]
    for i in range(0, steps, 2):
        draw.line([pts[i], pts[i + 1]], fill=fill, width=width)


def mascara_seta_afinada(coords, largura, superamostra=4):
    """Máscara (modo L) da seta moderna e o canto onde ela vai.

    Corpo que afina da cabeça para a cauda (a cauda tem um quarto da
    largura) e cabeça grande. O PIL desenha polígono sem antialias, então o
    desenho é feito `superamostra` vezes maior e reduzido com LANCZOS — é o
    que tira o serrilhado das bordas inclinadas. Só a caixa da seta é
    desenhada, não a imagem inteira.

    Devolve (mascara, (x0, y0)); o editor usa a mesma máscara na tela e no
    PNG gravado, então a prévia é o que sai.
    """
    x1, y1, x2, y2 = coords
    larg = max(1.0, float(largura)) * 1.6
    comp = math.hypot(x2 - x1, y2 - y1)
    ang = math.atan2(y2 - y1, x2 - x1)
    ux, uy = math.cos(ang), math.sin(ang)
    px, py = -uy, ux
    cabeca = min(4.2 * larg, comp * 0.55)
    meia_cabeca = 3.4 * larg / 2
    bx, by = x2 - ux * cabeca, y2 - uy * cabeca
    cauda, corpo = larg * 0.25 / 2, larg / 2

    margem = meia_cabeca + 2
    x0 = int(math.floor(min(x1, x2) - margem))
    y0 = int(math.floor(min(y1, y2) - margem))
    largura_caixa = int(math.ceil(max(x1, x2) + margem)) - x0
    altura_caixa = int(math.ceil(max(y1, y2) + margem)) - y0
    s = superamostra

    def p(x, y):
        return ((x - x0) * s, (y - y0) * s)

    grande = Image.new("L", (largura_caixa * s, altura_caixa * s), 0)
    d = ImageDraw.Draw(grande)
    d.polygon([p(x1 + px * cauda, y1 + py * cauda), p(bx + px * corpo, by + py * corpo),
               p(bx - px * corpo, by - py * corpo), p(x1 - px * cauda, y1 - py * cauda)],
              fill=255)
    cx, cy = p(x1, y1)
    d.ellipse([cx - cauda * s, cy - cauda * s, cx + cauda * s, cy + cauda * s], fill=255)
    d.polygon([p(x2, y2), p(bx + px * meia_cabeca, by + py * meia_cabeca),
               p(bx - px * meia_cabeca, by - py * meia_cabeca)], fill=255)
    return grande.resize((largura_caixa, altura_caixa), Image.LANCZOS), (x0, y0)


def desenhar_seta_afinada(img, coords, rgb, largura):
    """Pinta a seta moderna na imagem (in-place)."""
    mascara, (x0, y0) = mascara_seta_afinada(coords, largura)
    cor = tuple(rgb) + ((255,) if img.mode == "RGBA" else ())
    img.paste(Image.new(img.mode, mascara.size, cor), (x0, y0), mascara)


def raio_desfoque(intensidade):
    """Raio do desfoque do Borrar para a intensidade do controle (2 a 14)."""
    return 3 + 2 * max(1, int(intensidade))


def desfocar_regiao(img, box, intensidade):
    """Desfoque forte na região (in-place) — o Borrar dos prints novos.

    Duas passadas de gaussiano: uma só, mesmo com raio grande, ainda deixa
    a silhueta das letras. O recorte leva uma margem em volta para a borda
    do borrão não sair clara (o gaussiano completaria com a própria borda).
    Para dado sensível de verdade a Tarja continua sendo a indicada.
    """
    x1, y1, x2, y2 = [int(round(v)) for v in box]
    x1, x2 = sorted((max(0, x1), max(0, x2)))
    y1, y2 = sorted((max(0, y1), max(0, y2)))
    x2 = min(x2, img.width)
    y2 = min(y2, img.height)
    if x2 - x1 < 2 or y2 - y1 < 2:
        return
    raio = raio_desfoque(intensidade)
    margem = raio * 2
    ma, mb = max(0, x1 - margem), max(0, y1 - margem)
    mc, md = min(img.width, x2 + margem), min(img.height, y2 + margem)
    recorte = img.crop((ma, mb, mc, md))
    for _ in range(2):
        recorte = recorte.filter(ImageFilter.GaussianBlur(raio))
    img.paste(recorte.crop((x1 - ma, y1 - mb, x2 - ma, y2 - mb)), (x1, y1))


def pixelate_region(img, box, block=12):
    """Pixeliza uma região da imagem in-place — usado pela ferramenta Borrar
    para redigir conteúdo sensível (mais confiável que blur para esconder texto)."""
    x1, y1, x2, y2 = [int(round(v)) for v in box]
    x1, x2 = sorted((max(0, x1), max(0, x2)))
    y1, y2 = sorted((max(0, y1), max(0, y2)))
    x2 = min(x2, img.width)
    y2 = min(y2, img.height)
    if x2 - x1 < 2 or y2 - y1 < 2:
        return
    region = img.crop((x1, y1, x2, y2))
    w, h = region.size
    small = region.resize((max(1, w // block), max(1, h // block)), Image.NEAREST)
    region = small.resize((w, h), Image.NEAREST)
    img.paste(region, (x1, y1))
