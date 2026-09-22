"""Tokens de cor/fonte usados em toda a interface, extraídos da paleta do
design "Gestor de Evidencias.dc.html" (telas 1a e 1b)."""

FONT = "Segoe UI"

# ---------------------------------------------------------------------------
# Escala tipográfica
#
# Escala fechada e semântica: o nome diz o papel do texto, não o tamanho.
# Nenhuma tela deve definir tamanho de fonte na mão — é o que mantém a
# proporção entre elas e faz o ajuste de escala das Configurações valer para
# a aplicação inteira.
#
# Em 96 DPI: pt * 4/3 = px. Corpo em 11pt = ~15px, que é a faixa confortável
# de apps desktop modernos (VS Code/Slack ficam em 13-15px).
#
# IMPORTANTE: o Tk exige inteiro no tamanho da fonte — 9.5 levanta TclError.
# ---------------------------------------------------------------------------
FS_CAPTION = 9    # dicas, metadados secundários, texto de apoio
FS_BODY = 11      # texto padrão, campos, itens de lista
FS_BUTTON = 12    # rótulo de botão (sempre bold)
FS_EYEBROW = 10   # títulos de seção em CAIXA ALTA
FS_SUBTITLE = 13  # título de card / cabeçalho de painel
FS_TITLE = 15     # título de janela
FS_DISPLAY = 20   # números grandes / destaque

# Escala de espaçamento (base 4) — usar no lugar de padx/pady arbitrários.
SP_XS = 4
SP_SM = 8
SP_MD = 12
SP_LG = 16
SP_XL = 24

# Dimensões de controle: todo botão/campo cai numa dessas alturas, que é o
# que faz as coisas alinharem entre si.
CTRL_H = 36
CTRL_H_SM = 30
RADIUS = 8

# ---------------------------------------------------------------------------
# Escala ajustável pelo usuário (Configurações)
#
# Os valores acima são a base; `aplicar_escala` reescreve os FS_*/CTRL_H deste
# módulo a partir deles. Funciona porque todo o app lê como `theme.FS_BODY`
# (busca de atributo na hora de montar o widget) e ninguém faz
# `from theme import FS_BODY` — então basta remontar a interface depois de
# mudar a escala pra ela valer.
# ---------------------------------------------------------------------------
_BASE = {
    "FS_CAPTION": FS_CAPTION, "FS_BODY": FS_BODY, "FS_BUTTON": FS_BUTTON,
    "FS_EYEBROW": FS_EYEBROW, "FS_SUBTITLE": FS_SUBTITLE, "FS_TITLE": FS_TITLE,
    "FS_DISPLAY": FS_DISPLAY, "CTRL_H": CTRL_H, "CTRL_H_SM": CTRL_H_SM,
}

ESCALAS = (("pequena", "Pequena", 0.9), ("padrao", "Padrão", 1.0),
           ("grande", "Grande", 1.15), ("muito_grande", "Muito grande", 1.3))


def escala_por_chave(chave, padrao=1.0):
    for c, _rotulo, valor in ESCALAS:
        if c == chave:
            return valor
    return padrao


def aplicar_escala(geral=1.0, botao=1.0):
    """Reescreve os tamanhos deste módulo. `botao` multiplica em cima do geral,
    só pro rótulo dos botões."""
    globals_ = globals()
    for nome, base in _BASE.items():
        if nome.startswith("CTRL_"):
            # a caixa acompanha o texto, senão a fonte cresce e o botão não
            globals_[nome] = max(24, int(round(base * geral)))
        else:
            globals_[nome] = max(7, int(round(base * geral)))
    globals_["FS_BUTTON"] = max(7, int(round(_BASE["FS_BUTTON"] * geral * botao)))

LIGHT = dict(
    bg_app="#E9EEF2",
    bg_panel="#FBFDFE",
    bg_header="#F1F6F8",
    bg_footer="#F7FAFB",
    bg_content="#EDF1F4",
    bg_input="#FFFFFF",
    border="#D3DCE2",
    border_soft="#E1E8EC",
    border_input="#DCE4E9",
    text_primary="#17262E",
    text_secondary="#4A5F6B",
    text_tertiary="#6B8190",
    text_muted="#8EA2AD",
    accent="#0B7285",
    accent_hover="#08606F",
    accent_bg="#F0F8FA",
    accent_bg_strong="#E6F2F5",
    danger_bg="#FDECE6",
    danger_text="#B2280E",
    success="#0CA678",
    success_bg="#E2F5EE",
    success_text="#0A7A5A",
    pill_bg="#EDF2F5",
    white="#FFFFFF",
)

DARK = dict(
    bg_app="#12181B",
    bg_panel="#1C2529",
    bg_header="#212B30",
    bg_footer="#1E282C",
    bg_content="#171F22",
    bg_input="#212B30",
    border="#333F45",
    border_soft="#2B363B",
    border_input="#37444A",
    text_primary="#E7EEF1",
    text_secondary="#AFC0C7",
    text_tertiary="#8CA0A8",
    text_muted="#6B7D84",
    accent="#22A6BF",
    accent_hover="#3DB8CF",
    accent_bg="#183338",
    accent_bg_strong="#1B3B41",
    danger_bg="#3A2420",
    danger_text="#F2937B",
    success="#33C793",
    success_bg="#173A30",
    success_text="#5FE0B4",
    pill_bg="#232E33",
    white="#FFFFFF",
)

# Paleta fixa de cores de anotação (5 pré-definidas do design), além do
# seletor de cor customizado que já existia no app original.
PALETTE = ["#E8590C", "#0B7285", "#0CA678", "#FFC53D", "#17262E"]


def get(dark):
    return DARK if dark else LIGHT
