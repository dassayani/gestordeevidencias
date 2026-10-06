"""Helpers específicos de captura: desenhar o cursor real na imagem, tocar um
som ao capturar, e limpar capturas antigas não usadas (retenção)."""
import os
import time
import winsound

import win32api
import win32con
import win32gui
import win32ui
from PIL import Image

from gestor.dados import capture_store

COR_CHAVE = (255, 0, 255)


def obter_cursor_pil(tamanho=32):
    """Retorna (imagem RGBA do cursor do mouse ou None, posição (x, y) na tela)."""
    try:
        flags, hcursor, pos = win32gui.GetCursorInfo()
        if flags == 0 or not hcursor:
            return None, pos

        info = win32gui.GetIconInfo(hcursor)
        hotspot_x, hotspot_y = info[1], info[2]
        if info[3]:
            win32gui.DeleteObject(info[3])
        if info[4]:
            win32gui.DeleteObject(info[4])

        hdc_tela = win32gui.GetDC(0)
        hdc = win32ui.CreateDCFromHandle(hdc_tela)
        hdc_mem = hdc.CreateCompatibleDC()
        hbmp = win32ui.CreateBitmap()
        hbmp.CreateCompatibleBitmap(hdc, tamanho, tamanho)
        hdc_mem.SelectObject(hbmp)
        hdc_mem.FillSolidRect((0, 0, tamanho, tamanho), win32api.RGB(*COR_CHAVE))
        win32gui.DrawIconEx(hdc_mem.GetHandleOutput(), 0, 0, hcursor,
                            tamanho, tamanho, 0, None, win32con.DI_NORMAL)

        bmpinfo = hbmp.GetInfo()
        bmpstr = hbmp.GetBitmapBits(True)
        img = Image.frombuffer("RGB", (bmpinfo["bmWidth"], bmpinfo["bmHeight"]),
                               bmpstr, "raw", "BGRX", 0, 1)
        img = img.convert("RGBA")
        pixels = img.load()
        for y in range(img.height):
            for x in range(img.width):
                if pixels[x, y][:3] == COR_CHAVE:
                    pixels[x, y] = (0, 0, 0, 0)

        win32gui.DeleteObject(hbmp.GetHandle())
        hdc_mem.DeleteDC()
        hdc.DeleteDC()
        win32gui.ReleaseDC(0, hdc_tela)

        return img, (pos[0] - hotspot_x, pos[1] - hotspot_y)
    except Exception:
        return None, None


def colar_cursor(imagem, offset=(0, 0)):
    """Cola o cursor real do mouse na imagem capturada (offset = canto
    superior-esquerdo da captura, em coordenadas de tela)."""
    cursor_img, pos = obter_cursor_pil()
    if cursor_img is None or pos is None:
        return imagem
    x = pos[0] - offset[0]
    y = pos[1] - offset[1]
    resultado = imagem.convert("RGBA")
    resultado.paste(cursor_img, (x, y), cursor_img)
    return resultado.convert("RGB")


def tocar_som_captura():
    try:
        winsound.MessageBeep(winsound.MB_ICONASTERISK)
    except Exception:
        pass


PADROES_NOME = {
    "hora": lambda dt, sufixo: f"print_{dt.strftime('%H%M%S')}{sufixo}.png",
    "data_hora": lambda dt, sufixo: f"print_{dt.strftime('%Y%m%d_%H%M%S')}{sufixo}.png",
}
# Os mesmos padrões como a tela de Configurações os oferece: (chave, exemplo).
PADROES_NOME_UI = [("hora", "captura-HHMMSS"),
                   ("data_hora", "captura-AAAAMMDD-HHMMSS")]


def nome_livre(pasta, padrao, agora=None):
    """Nome para uma captura nova que não pisa em nenhuma que já existe.

    Com o padrão `hora` o nome só tem HHMMSS: o print de hoje às 14:30:52
    recebia o mesmo nome do de qualquer outro dia nesse horário, e salvar
    sobrescrevia a evidência antiga. Pior: o .raw.png e o .json da antiga
    continuavam ao lado, e a imagem nova passava a abrir no editor com o
    original e as anotações da velha. Também cobre dois prints no mesmo
    segundo (Shift+Print Screen repetido). Um .json ou .raw.png órfão conta
    como ocupado, pelo mesmo motivo.
    """
    from datetime import datetime
    agora = agora or datetime.now()
    fn = PADROES_NOME.get(padrao, PADROES_NOME["hora"])
    n = 1
    while True:
        nome = fn(agora, "" if n == 1 else "_%d" % n)
        caminho = os.path.join(pasta, nome)
        irmaos = (caminho, capture_store.raw_path(caminho), capture_store.json_path(caminho),
                  capture_store.txt_path(caminho))
        if not any(os.path.exists(p) for p in irmaos):
            return nome
        n += 1


def limpar_capturas_antigas(pasta, dias):
    """Remove capturas com mais de `dias` dias que ninguém usou: sem edição,
    sem legenda, sem caso/projeto e sem anotação — uma forma simples de
    'retenção' sem precisar lembrar seleção entre reinícios do app.

    Olhar só `edited_at` não basta: a legenda digitada ao montar um documento
    é gravada sem marcar a captura como editada (ela não foi editada), e uma
    captura que já entrou num documento não pode sumir sozinha.
    """
    if not dias or not os.path.isdir(pasta):
        return 0
    limite = time.time() - dias * 86400
    removidos = 0
    for item in capture_store.list_captures(pasta):
        usada = (item["edited"] or item["caption"] or item["caso"]
                 or item["shape_count"])
        if item["mtime"] < limite and not usada:
            # só conta o que a Lixeira realmente aceitou: o retorno passou a
            # ser significativo quando a exclusão deixou de ser definitiva
            if capture_store.delete_capture(item["path"]):
                removidos += 1
    return removidos
