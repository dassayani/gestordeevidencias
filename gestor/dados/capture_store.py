"""Leitura/escrita das capturas em disco.

Cada captura passa a ter até 3 arquivos:
  captura.png       -> composição atual (raw + formas visíveis), usada pela
                        galeria, pelo PDF e por "Copiar".
  captura.raw.png    -> a captura original, imutável (só muda com Recorte).
  captura.json       -> {"caption": str, "edited_at": iso|None,
                         "captured_at": iso, "shapes": [...]}

`captured_at` é o instante em que o print foi tirado. É ele — e não a data de
modificação do arquivo — que ordena o documento: o editor regrava o PNG, então
o mtime de um print editado passa a ser o da edição, e ordenar por ele jogaria
o passo 2 para o fim só porque alguém anotou nele.

Capturas antigas (só .png + .txt opcional, de antes desta mudança) são
migradas na primeira leitura: a própria .png vira a base "raw" e a legenda
do .txt (se existir) é importada para o .json.
"""
import json
import os
import re
from datetime import datetime, timedelta

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


def _descartar(tmp):
    try:
        os.remove(tmp)
    except Exception:
        pass


def _substituir(tmp, destino):
    """Troca o destino pelo temporário; limpa o temporário se a troca falhar."""
    try:
        os.replace(tmp, destino)
    except Exception:
        _descartar(tmp)
        raise


def save_png(imagem, destino):
    """Grava a imagem sem deixar o arquivo pela metade em caso de falha.

    Escreve num temporário ao lado e só então troca: disco cheio ou arquivo
    bloqueado no meio da gravação não destroem a versão que já existia, e o
    temporário parcial não fica para trás.
    """
    tmp = destino + ".tmp"
    try:
        imagem.save(tmp, format="PNG")
    except Exception:
        _descartar(tmp)
        raise
    _substituir(tmp, destino)


def _ler_json(png_path):
    """O .json da captura, sem efeito colateral (load_meta cria o .raw.png)."""
    try:
        with open(json_path(png_path), "r", encoding="utf-8") as f:
            dados = json.load(f)
        return dados if isinstance(dados, dict) else {}
    except Exception:
        return {}


def save_meta(png_path, meta, marcar_editada=True):
    meta = dict(meta)
    if marcar_editada:
        meta["edited_at"] = datetime.now().isoformat()
    if not meta.get("captured_at"):
        # Quem grava costuma montar o dicionário do zero (o editor, por
        # exemplo) e não sabe que este campo existe: sem isto, a primeira
        # edição apagaria o instante da captura e o print perderia o lugar
        # na ordem do documento.
        anterior = _ler_json(png_path).get("captured_at")
        if anterior:
            meta["captured_at"] = anterior
    destino = json_path(png_path)
    tmp = destino + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False)
    except Exception:
        _descartar(tmp)
        raise
    _substituir(tmp, destino)
    tp = txt_path(png_path)
    if os.path.exists(tp):
        try:
            os.remove(tp)
        except Exception:
            pass


def save_caption(png_path, legenda):
    """Grava só a legenda, sem tratar a captura como editada.

    Digitar a legenda ao montar o documento não é editar a imagem: o filtro
    "Editadas" e a limpeza por retenção olham `edited_at`, então ele fica
    como estava. Devolve True quando a legenda mudou de fato.
    """
    meta = load_meta(png_path)
    if meta.get("caption", "") == legenda:
        return False
    meta["caption"] = legenda
    save_meta(png_path, meta, marcar_editada=False)
    return True


def load_raw_image(png_path):
    rp = raw_path(png_path)
    if os.path.exists(rp):
        return Image.open(rp).convert("RGBA")
    return Image.open(png_path).convert("RGBA")


# ---------------------------------------------------------------- ordem cronológica

_NOME_DATA_HORA = re.compile(r"^print_(\d{8})_(\d{6})")
_NOME_HORA = re.compile(r"^print_(\d{6})(?!\d)")


def _do_nome(png_path):
    """O que o nome do arquivo conta sobre quando o print foi tirado.

    Devolve (datetime, tem_data). Com o padrão `hora` o nome só traz HHMMSS: o
    datetime volta com data fictícia e `tem_data` falso.
    """
    nome = os.path.basename(png_path)
    achou = _NOME_DATA_HORA.match(nome)
    try:
        if achou:
            return datetime.strptime(achou.group(1) + achou.group(2), "%Y%m%d%H%M%S"), True
        achou = _NOME_HORA.match(nome)
        if achou:
            return datetime.strptime(achou.group(1), "%H%M%S"), False
    except ValueError:
        pass
    return None, False


def instante_da_captura(png_path, meta=None):
    """Quando o print foi tirado, em segundos desde a época.

    A ordem de preferência vai do mais fiel ao menos:
      1. `captured_at`, gravado na hora da captura — não muda ao editar;
      2. a data e a hora do nome, quando ele as traz (padrão `data_hora`);
      3. o mtime do arquivo, se o print nunca foi editado;
      4. print antigo e já editado: o mtime é o da EDIÇÃO. A hora do dia vem do
         nome e o dia, do mtime (o dia anterior, se a hora do nome for depois da
         da edição). Sem hora no nome não há o que fazer além do mtime.
    Vale a pena gravar o resultado (`garantir_captured_at`): daí em diante uma
    nova edição não o altera.
    """
    if meta is None:
        meta = _ler_json(png_path)
    quando = meta.get("captured_at")
    if quando:
        try:
            return datetime.fromisoformat(quando).timestamp()
        except (ValueError, TypeError):
            pass
    do_nome, tem_data = _do_nome(png_path)
    if do_nome is not None and tem_data:
        return do_nome.timestamp()
    try:
        mtime = os.path.getmtime(png_path)
    except OSError:
        return 0.0
    if meta.get("edited_at") and do_nome is not None:
        edicao = datetime.fromtimestamp(mtime)
        captura = edicao.replace(hour=do_nome.hour, minute=do_nome.minute,
                                 second=do_nome.second, microsecond=0)
        if captura > edicao:
            captura -= timedelta(days=1)
        return captura.timestamp()
    return mtime


def ordenar_instantes(pares, decrescente=False):
    """Caminhos ordenados por instante, a partir de pares (caminho, instante).

    Empate (dois prints no mesmo segundo) se desfaz pelo nome e depois pelo
    caminho, para a ordem ser a mesma sempre — a seleção da galeria é um set e
    não guarda ordem nenhuma.
    """
    ordenados = sorted(pares, key=lambda p: (p[1], os.path.basename(p[0]).lower(), p[0]),
                       reverse=decrescente)
    return [caminho for caminho, _ in ordenados]


def ordenar_por_captura(caminhos, decrescente=False):
    return ordenar_instantes([(c, instante_da_captura(c)) for c in caminhos], decrescente)


def registrar_captura(png_path, quando=None):
    """Grava o instante de uma captura recém-tirada, sem marcá-la como editada."""
    quando = quando or datetime.now()
    save_meta(png_path, {"caption": "", "caso": "", "edited_at": None, "shapes": [],
                         "captured_at": quando.isoformat()}, marcar_editada=False)


def garantir_captured_at(png_path, meta=None):
    """Dá `captured_at` a um print antigo, uma vez só. Devolve True se gravou.

    Sem isto, a data do print antigo seria reestimada a cada uso e mudaria na
    primeira vez que ele fosse editado.
    """
    if meta is None:
        meta = load_meta(png_path)
    if meta.get("captured_at"):
        return False
    instante = instante_da_captura(png_path, meta)
    if instante <= 0:
        return False
    meta = dict(meta)
    meta["captured_at"] = datetime.fromtimestamp(instante).isoformat()
    save_meta(png_path, meta, marcar_editada=False)
    return True


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
