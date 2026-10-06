"""Configurações persistidas do app, em um JSON pequeno na pasta de dados
(a mesma onde ficam 'Capturas' e 'Documentos PDF')."""
import json
import os

PADRAO = {
    "abrir_apos_captura": True,
    "tempo_inatividade_ms": 10000,
    "pasta_capturas": None,
    "borda_ativada": False,
    "borda_cor": "#0B7285",
    "fonte_legenda": "Arial",
    "atalho_captura_area": "printscreen",
    "atalho_janela_ativa": "nenhum",
    "incluir_cursor": False,
    # deixa a captura recém-feita pronta pra colar com Ctrl+V
    "copiar_apos_captura": True,
    "som_captura": True,
    "padrao_nome": "hora",
    # detalhes | blocos | grade
    "modo_visualizacao": "detalhes",
    "retencao_dias": 0,
    "autor_padrao": "",
    # tamanho da fonte da interface; "botao" multiplica só o texto dos botões
    "escala_fonte": "padrao",
    "escala_fonte_botao": "padrao",
    # última área capturada, em coordenadas absolutas, pro Shift+PrintScreen
    "ultima_area": None,
}


def _caminho(data_dir):
    return os.path.join(data_dir, "config.json")


def load(data_dir):
    """As preferências gravadas, sobre os valores padrão.

    Um config.json ilegível (gravação interrompida, edição à mão) não pode
    simplesmente virar "tudo padrão": a pasta de capturas voltaria para a de
    fábrica sem aviso, e a próxima gravação apagaria de vez o que havia. O
    arquivo é guardado ao lado, com o horário no nome, e o caso vai para o log.
    """
    cfg = dict(PADRAO)
    caminho = _caminho(data_dir)
    if os.path.exists(caminho):
        try:
            with open(caminho, "r", encoding="utf-8") as f:
                dados = json.load(f)
            if not isinstance(dados, dict):
                raise ValueError("config.json não contém um objeto")
            cfg.update(dados)
        except Exception:
            _guardar_ilegivel(caminho)
    return cfg


def _guardar_ilegivel(caminho):
    import sys
    import time
    copia = "%s.ilegivel-%s" % (caminho, time.strftime("%Y%m%d-%H%M%S"))
    try:
        os.replace(caminho, copia)
    except Exception:
        copia = None
    try:
        from gestor.sistema import diagnostico
        diagnostico.registrar(*sys.exc_info(),
                              contexto="config.json ilegível; guardado em %s" % copia)
    except Exception:
        pass


def save(data_dir, cfg):
    """Grava as preferencias. Devolve False quando nao conseguiu.

    A falha vai para o log em vez de sumir: uma pasta sem permissao de
    escrita fazia cada ajuste parecer aplicado e voltar atras no reinicio,
    sem nada que indicasse o motivo.
    """
    caminho = _caminho(data_dir)
    tmp = caminho + ".tmp"
    try:
        # temporário + troca: um desligamento no meio da gravação deixava o
        # config.json pela metade, e no próximo início tudo voltava ao padrão
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
        os.replace(tmp, caminho)
        return True
    except Exception:
        try:
            os.remove(tmp)
        except Exception:
            pass
        try:
            import sys
            from gestor.sistema import diagnostico
            diagnostico.registrar(*sys.exc_info(), contexto="gravando config.json")
        except Exception:
            pass
        return False
