"""Tela de Configurações.

Vive fora do `workspace` porque era o maior bloco isolado dele: 330 linhas que
só montam widgets e gravam no config, sem participar da lista de capturas nem
do disparo da captura. Recebe a instância do app (`app`) em vez de herdar dela,
então a dependência anda num sentido só — `workspace` importa daqui, nunca o
contrário.
"""
from tkinter import Toplevel, messagebox, filedialog
import tkinter as tk

from gestor.captura import captura_utils
from gestor.dados import config
from gestor.captura import hotkey
from gestor.sistema import startup
from gestor.ui import theme
from gestor.ui import widgets

FONTES_PDF = [("Arial", "Arial / Helvetica"), ("Times", "Times"), ("Courier", "Courier")]


def abrir(app):
    """Abre a janela de Configurações do `app`."""
    app.pausar_timer = True
    t = theme.get(app.modo_escuro)
    win = Toplevel(app.root)
    win.title("Configurações")
    win.configure(bg=t["bg_panel"])
    # 780 em vez de 900: numa janela muito larga as linhas de texto das
    # opções ficam longas demais pra ler com conforto.
    win.geometry("780x800")
    win.minsize(620, 520)

    def ao_fechar():
        app.pausar_timer = False
        app.resetar_timer()
        win.destroy()

    win.protocol("WM_DELETE_WINDOW", ao_fechar)

    cabecalho = tk.Frame(win, bg=t["bg_header"], height=56)
    cabecalho.pack(fill="x")
    cabecalho.pack_propagate(False)
    tk.Label(cabecalho, text="Configurações", bg=t["bg_header"], fg=t["text_primary"],
             font=(theme.FONT, theme.FS_TITLE, "bold")).pack(side="left", padx=20)

    # A tela cresceu bastante (vários blocos) — sem scroll, os campos
    # de baixo (tempo de inatividade, retenção...) ficavam cortados
    # fora da janela e pareciam simplesmente não existir.
    corpo_wrap = tk.Frame(win, bg=t["bg_panel"])
    corpo_wrap.pack(fill="both", expand=True)
    canvas_cfg = tk.Canvas(corpo_wrap, bg=t["bg_panel"], highlightthickness=0)
    scrollbar_cfg = tk.Scrollbar(corpo_wrap, orient="vertical", command=canvas_cfg.yview)
    corpo = tk.Frame(canvas_cfg, bg=t["bg_panel"])
    janela_scroll = canvas_cfg.create_window((0, 0), window=corpo, anchor="nw")
    canvas_cfg.configure(yscrollcommand=scrollbar_cfg.set)
    canvas_cfg.pack(side="left", fill="both", expand=True)
    scrollbar_cfg.pack(side="right", fill="y")
    corpo.bind("<Configure>",
               lambda e: canvas_cfg.config(scrollregion=canvas_cfg.bbox("all")))
    canvas_cfg.bind("<Configure>",
                    lambda e: canvas_cfg.itemconfig(janela_scroll, width=e.width))
    canvas_cfg.bind("<Enter>", lambda e: canvas_cfg.bind_all(
        "<MouseWheel>",
        lambda ev: canvas_cfg.yview_scroll(int(-1 * (ev.delta / 120)), "units")))
    canvas_cfg.bind("<Leave>", lambda e: canvas_cfg.unbind_all("<MouseWheel>"))

    conteudo = tk.Frame(corpo, bg=t["bg_panel"])
    conteudo.pack(fill="x", padx=36, pady=(20, 24))

    def secao(titulo, primeira=False):
        if not primeira:
            tk.Frame(conteudo, bg=t["border_soft"], height=1).pack(fill="x", pady=(22, 0))
        widgets.titulo_secao(conteudo, titulo, app.modo_escuro,
                             pady=(18 if not primeira else 0, 12))
    _secao_captura(app, conteudo, t, secao, win)
    _secao_nomeacao(app, conteudo, t, secao)
    _secao_janela(app, conteudo, t, secao, win)
    _secao_aparencia(app, conteudo, t, secao)
    _secao_documento(app, conteudo, t, secao, ao_fechar)


def _secao_captura(app, conteudo, t, secao, win):
    """Seção Captura da tela de Configurações."""
    secao("Captura", primeira=True)

    var_abrir = tk.BooleanVar(value=app.config.get("abrir_apos_captura", True))

    def salvar_abrir(valor):
        app.config["abrir_apos_captura"] = valor
        config.save(app.data_dir, app.config)

    widgets.linha_checkbox(conteudo, "Abrir automaticamente após capturar", var_abrir,
                           app.modo_escuro,
                           subtitulo="Quando desligado, a captura só fica salva; você abre "
                                     "o painel manualmente pelo ícone da bandeja.",
                           on_change=salvar_abrir)

    def _aplicar_atalhos():
        erros = app._registrar_atalhos()
        config.save(app.data_dir, app.config)
        _atualizar_estado_atalhos()
        if erros:
            messagebox.showwarning("Atalhos", "Não deu pra registrar:\n" + "\n".join(erros),
                                   parent=win)

    tk.Label(conteudo, text="Atalho de captura de área", bg=t["bg_panel"],
             fg=t["text_tertiary"],
             font=(theme.FONT, theme.FS_CAPTION)).pack(anchor="w", pady=(12, 4))
    var_atalho_area = tk.StringVar(value=app.config.get("atalho_captura_area", "printscreen"))

    def salvar_atalho_area(valor):
        app.config["atalho_captura_area"] = valor
        _aplicar_atalhos()

    widgets.escolha_checkbox(conteudo, [(c[0], c[1]) for c in hotkey.COMBOS_CAPTURA_AREA],
                             var_atalho_area, app.modo_escuro,
                             on_change=salvar_atalho_area).pack(fill="x", pady=(0, 10))

    tk.Label(conteudo, text="Atalho de captura da janela ativa", bg=t["bg_panel"],
             fg=t["text_tertiary"],
             font=(theme.FONT, theme.FS_CAPTION)).pack(anchor="w", pady=(0, 4))
    var_atalho_janela = tk.StringVar(value=app.config.get("atalho_janela_ativa", "nenhum"))

    def salvar_atalho_janela(valor):
        app.config["atalho_janela_ativa"] = valor
        _aplicar_atalhos()

    widgets.escolha_checkbox(conteudo, [(c[0], c[1]) for c in hotkey.COMBOS_JANELA_ATIVA],
                             var_atalho_janela, app.modo_escuro,
                             on_change=salvar_atalho_janela).pack(fill="x", pady=(0, 6))

    # Estado dos atalhos na própria tela: uma combinação ocupada por outro
    # programa não tem sintoma visível, a tecla apenas não responde.
    lbl_estado_atalhos = widgets.texto_fluido(conteudo, "", app.modo_escuro)
    lbl_estado_atalhos.pack(fill="x", pady=(0, 10))

    def _atualizar_estado_atalhos():
        erros = getattr(app, "erros_atalhos", [])
        if erros:
            lbl_estado_atalhos.config(
                text="Em uso por outro programa: " + " · ".join(erros)
                     + ". Escolha outra combinação acima.",
                fg=t["danger_text"])
            return
        rivais = (hotkey.concorrentes_printscreen()
                  if var_atalho_area.get() == "printscreen" else [])
        if rivais:
            plural = len(rivais) > 1
            capturam = "capturam" if plural else "captura"
            podem = "podem" if plural else "pode"
            programas = "nesses programas" if plural else "nesse programa"
            lbl_estado_atalhos.config(
                text=f"Atalhos ativos. Atenção: {' e '.join(rivais)} também "
                     f"{capturam} tela pelo Print Screen e {podem} ficar com a "
                     f"tecla antes do Gestor. Se o Print Screen não responder, "
                     f"desative o atalho {programas} ou escolha outra combinação "
                     f"acima.",
                fg=t["accent"])
        else:
            lbl_estado_atalhos.config(text="Atalhos ativos.", fg=t["success"])

    _atualizar_estado_atalhos()

    var_cursor = tk.BooleanVar(value=app.config.get("incluir_cursor", False))

    def salvar_cursor(valor):
        app.config["incluir_cursor"] = valor
        config.save(app.data_dir, app.config)

    widgets.linha_checkbox(conteudo, "Incluir cursor do mouse", var_cursor, app.modo_escuro,
                           on_change=salvar_cursor)

    var_copiar = tk.BooleanVar(value=app.config.get("copiar_apos_captura", True))

    def salvar_copiar(valor):
        app.config["copiar_apos_captura"] = valor
        config.save(app.data_dir, app.config)

    widgets.linha_checkbox(conteudo, "Copiar a captura para a área de transferência",
                           var_copiar, app.modo_escuro,
                           subtitulo="Assim que a captura é feita, ela já pode ser colada "
                                     "com Ctrl+V em qualquer programa.",
                           on_change=salvar_copiar)

    var_som = tk.BooleanVar(value=app.config.get("som_captura", True))

    def salvar_som(valor):
        app.config["som_captura"] = valor
        config.save(app.data_dir, app.config)

    widgets.linha_checkbox(conteudo, "Som ao capturar", var_som, app.modo_escuro,
                           on_change=salvar_som)

    def alterar_pasta():
        nova = filedialog.askdirectory(parent=win, initialdir=app.pasta_capturas,
                                       title="Escolher pasta para salvar os prints")
        if not nova:
            return
        app.config["pasta_capturas"] = nova
        config.save(app.data_dir, app.config)
        app.pasta_capturas = nova
        entry_pasta.config(state="normal")
        entry_pasta.delete(0, "end")
        entry_pasta.insert(0, nova)
        entry_pasta.config(state="readonly")
        app.atualizar_galeria()

    _, entry_pasta = widgets.campo_com_botao(conteudo, "Pasta onde salvar os prints",
                                             app.modo_escuro, app.pasta_capturas,
                                             "Alterar…", alterar_pasta)


def _secao_nomeacao(app, conteudo, t, secao):
    """Seção Nomeação e retenção da tela de Configurações."""
    secao("Nomeação e retenção")

    tk.Label(conteudo, text="Padrão de nome do arquivo", bg=t["bg_panel"],
             fg=t["text_tertiary"],
             font=(theme.FONT, theme.FS_CAPTION)).pack(anchor="w", pady=(0, 4))
    var_padrao_nome = tk.StringVar(value=app.config.get("padrao_nome", "hora"))

    def salvar_padrao_nome(valor):
        app.config["padrao_nome"] = valor
        config.save(app.data_dir, app.config)

    widgets.escolha_checkbox(conteudo, captura_utils.PADROES_NOME_UI, var_padrao_nome,
                             app.modo_escuro,
                             on_change=salvar_padrao_nome).pack(fill="x", pady=(0, 12))

    dias_atuais = app.config.get("retencao_dias", 0)
    var_retencao_ativa = tk.BooleanVar(value=dias_atuais > 0)

    def salvar_dias_retencao(event=None):
        texto = entry_retencao.get().strip()
        try:
            dias = max(1, int(texto))
        except ValueError:
            dias = app.config.get("retencao_dias") or 30
        entry_retencao.delete(0, "end")
        entry_retencao.insert(0, str(dias))
        if var_retencao_ativa.get():
            app.config["retencao_dias"] = dias
            config.save(app.data_dir, app.config)

    def salvar_retencao_ativa(ativa):
        entry_retencao.config(state="normal" if ativa else "disabled")
        app.config["retencao_dias"] = int(entry_retencao.get() or 30) if ativa else 0
        config.save(app.data_dir, app.config)

    widgets.linha_checkbox(conteudo, "Limpar prints automaticamente", var_retencao_ativa,
                           app.modo_escuro,
                           subtitulo="Ao abrir o app, apaga capturas mais antigas que o prazo "
                                     "abaixo e que nunca foram editadas (mantém as que têm "
                                     "legenda ou anotação) — ajuda a economizar espaço.",
                           on_change=salvar_retencao_ativa)

    _, entry_retencao = widgets.campo_rotulado(conteudo, "Apagar depois de quantos dias",
                                               app.modo_escuro,
                                               valor_inicial=str(dias_atuais or 30))
    entry_retencao.bind("<FocusOut>", salvar_dias_retencao)
    entry_retencao.bind("<Return>", salvar_dias_retencao)
    if not var_retencao_ativa.get():
        entry_retencao.config(state="disabled")


def _secao_janela(app, conteudo, t, secao, win):
    """Seção Janela da tela de Configurações."""
    secao("Janela")

    var_iniciar = tk.BooleanVar(value=startup.esta_habilitado())

    def salvar_iniciar(valor):
        try:
            if valor:
                startup.habilitar()
            else:
                startup.desabilitar()
        except Exception as e:
            messagebox.showerror("Iniciar com o Windows", f"Não foi possível alterar: {e}",
                                 parent=win)
            var_iniciar.set(startup.esta_habilitado())

    widgets.linha_checkbox(conteudo, "Iniciar com o Windows", var_iniciar, app.modo_escuro,
                           on_change=salvar_iniciar)

    var_menu = tk.BooleanVar(value=startup.no_menu_iniciar())

    def salvar_menu(valor):
        try:
            if valor:
                startup.adicionar_ao_menu_iniciar()
            else:
                startup.remover_do_menu_iniciar()
        except Exception as e:
            messagebox.showerror("Menu Iniciar", f"Não foi possível alterar: {e}", parent=win)
            var_menu.set(startup.no_menu_iniciar())

    widgets.linha_checkbox(
        conteudo, "Adicionar ao menu Iniciar", var_menu, app.modo_escuro,
        subtitulo="Cria um atalho para o app aparecer na pesquisa do Windows.",
        on_change=salvar_menu)

    def salvar_tempo(event=None):
        texto = entry_tempo.get().strip()
        try:
            segundos = max(2, int(texto))
        except ValueError:
            segundos = app.tempo_limite // 1000
        entry_tempo.delete(0, "end")
        entry_tempo.insert(0, str(segundos))
        app.tempo_limite = segundos * 1000
        app.config["tempo_inatividade_ms"] = app.tempo_limite
        config.save(app.data_dir, app.config)
        if not app.pausar_timer:
            app.resetar_timer()

    _, entry_tempo = widgets.campo_rotulado(
        conteudo, "Tempo de inatividade até esconder o painel (segundos)", app.modo_escuro,
        valor_inicial=str(app.tempo_limite // 1000))
    entry_tempo.bind("<FocusOut>", salvar_tempo)
    entry_tempo.bind("<Return>", salvar_tempo)


def _secao_aparencia(app, conteudo, t, secao):
    """Seção Aparência da tela de Configurações."""
    secao("Aparência")

    opcoes_escala = [(c, rotulo) for c, rotulo, _ in theme.ESCALAS]

    def salvar_escala(chave_config, valor):
        app.config[chave_config] = valor
        config.save(app.data_dir, app.config)
        app._aplicar_escala_fonte()
        app._ajustar_minsize()
        # a interface principal é remontada pra mudança valer na hora; as
        # outras janelas já nascem com o tamanho novo quando forem abertas
        app._reconstruir_ui()

    tk.Label(conteudo, text="Tamanho do texto da aplicação", bg=t["bg_panel"],
             fg=t["text_tertiary"],
             font=(theme.FONT, theme.FS_CAPTION)).pack(anchor="w", pady=(0, 4))
    var_escala = tk.StringVar(value=app.config.get("escala_fonte", "padrao"))
    widgets.escolha_checkbox(conteudo, opcoes_escala, var_escala, app.modo_escuro,
                             on_change=lambda v: salvar_escala("escala_fonte", v)).pack(
        fill="x", pady=(0, 10))

    tk.Label(conteudo, text="Texto dos botões (em cima do tamanho acima)", bg=t["bg_panel"],
             fg=t["text_tertiary"],
             font=(theme.FONT, theme.FS_CAPTION)).pack(anchor="w", pady=(0, 4))
    var_escala_botao = tk.StringVar(value=app.config.get("escala_fonte_botao", "padrao"))
    widgets.escolha_checkbox(conteudo, opcoes_escala, var_escala_botao, app.modo_escuro,
                             on_change=lambda v: salvar_escala("escala_fonte_botao", v)).pack(
        fill="x", pady=(0, 6))

    widgets.texto_fluido(conteudo, "Vale imediatamente no painel; as demais telas "
                                   "adotam o novo tamanho ao serem abertas.",
                         app.modo_escuro).pack(fill="x")


def _secao_documento(app, conteudo, t, secao, ao_fechar):
    """Seção Documento da tela de Configurações."""
    secao("Documento")

    var_borda = tk.BooleanVar(value=app.config.get("borda_ativada", False))

    def salvar_borda(valor):
        app.config["borda_ativada"] = valor
        config.save(app.data_dir, app.config)

    widgets.linha_checkbox(conteudo, "Adicionar borda nas imagens do documento", var_borda,
                           app.modo_escuro,
                           subtitulo="Aplicada só na hora de gerar o documento, não altera "
                                     "a captura original.",
                           on_change=salvar_borda)

    tk.Label(conteudo, text="Fonte da legenda no documento", bg=t["bg_panel"],
             fg=t["text_tertiary"],
             font=(theme.FONT, theme.FS_CAPTION)).pack(anchor="w", pady=(12, 4))
    var_fonte = tk.StringVar(value=app.config.get("fonte_legenda", "Arial"))

    def salvar_fonte(valor):
        app.config["fonte_legenda"] = valor
        config.save(app.data_dir, app.config)

    widgets.escolha_checkbox(conteudo, FONTES_PDF, var_fonte, app.modo_escuro,
                             on_change=salvar_fonte).pack(fill="x", pady=(0, 4))

    widgets.botao_secundario(conteudo, "Limpar pasta de capturas",
                             lambda: (app.limpar_pasta_completa(), ao_fechar()),
                             app.modo_escuro).pack(anchor="w", pady=(24, 4))
