"""Leitura/escrita das capturas em disco.

Cada captura passa a ter até 3 arquivos:
  captura.png       -> composição atual (raw + formas visíveis), usada pela
                        galeria, pelo PDF e por "Copiar".
  captura.raw.png    -> a captura original, imutável (só muda com Recorte).
  captura.json       -> {"caption": str, "edited_at": iso|None, "shapes": [...]}

Capturas antigas (só .png + .txt opcional, de antes desta mudança) são
migradas na primeira leitura: a própria .png vira a base "raw" e a legenda
do .txt (se existir) é importada para o .json.
"""
import json
import os
from datetime import datetime

from PIL import Image


def _stem(png_path):
    return png_path[:-4] if png_path.lower().endswith(".png") else png_path


def raw_path(png_path):
    return _stem(png_path) + ".raw.png"


def json_path(png_path):
    return _stem(png_path) + ".json"


def txt_path(png_path):
    return _stem(png_path) + ".txt"


def load_meta(png_path):
    jp = json_path(png_path)
    meta = {"caption": "", "caso": "", "edited_at": None, "shapes": []}
    if os.path.exists(jp):
        try:
            with open(jp, "r", encoding="utf-8") as f:
                meta.update(json.load(f))
        except Exception:
            pass
    else:
        tp = txt_path(png_path)
        if os.path.exists(tp):
            try:
                with open(tp, "r", encoding="utf-8") as f:
                    meta["caption"] = f.read().strip()
            except Exception:
                pass

    rp = raw_path(png_path)
    if not os.path.exists(rp) and os.path.exists(png_path):
        try:
            Image.open(png_path).convert("RGBA").save(rp)
        except Exception:
            pass

    return meta


def save_meta(png_path, meta):
    meta = dict(meta)
    meta["edited_at"] = datetime.now().isoformat()
    with open(json_path(png_path), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False)
    tp = txt_path(png_path)
    if os.path.exists(tp):
        try:
            os.remove(tp)
        except Exception:
            pass


def load_raw_image(png_path):
    rp = raw_path(png_path)
    if os.path.exists(rp):
        return Image.open(rp).convert("RGBA")
    return Image.open(png_path).convert("RGBA")


def delete_capture(png_path):
    """Manda a captura e seus arquivos irmaos para a Lixeira.

    Vao juntos numa unica operacao para virarem um item so ao restaurar.
    Devolve False quando a Lixeira recusou - nesse caso nada e apagado, em
    vez de destruir a evidencia em silencio.
    """
    from gestor.sistema import utils

    alvos = [p for p in (png_path, raw_path(png_path), json_path(png_path),
                         txt_path(png_path)) if os.path.exists(p)]
    if not alvos:
        return True
    return utils.mover_para_lixeira(alvos)


def list_captures(pasta):
    itens = []
    if not os.path.isdir(pasta):
        return itens
    for nome in os.listdir(pasta):
        baixo = nome.lower()
        if not baixo.endswith(".png") or baixo.endswith(".raw.png"):
            continue
        caminho = os.path.join(pasta, nome)
        try:
            meta = load_meta(caminho)
            with Image.open(caminho) as im:
                dims = im.size
            itens.append({
                "name": nome,
                "path": caminho,
                "mtime": os.path.getmtime(caminho),
                "dims": dims,
                "caption": meta.get("caption", ""),
                "caso": meta.get("caso", ""),
                "edited": bool(meta.get("edited_at")),
                "shape_count": len(meta.get("shapes", [])),
            })
        except Exception:
            continue
    itens.sort(key=lambda i: i["mtime"], reverse=True)
    return itens
