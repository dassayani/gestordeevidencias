"""Tela 'Montar documento' (design '1c'): reordena as capturas selecionadas,
preenche a capa, edita a legenda de cada uma, escolhe o modelo e as opções,
e segue pra pré-visualização/exportação."""
import os
from datetime import datetime
from tkinter import Toplevel, messagebox
import tkinter as tk

from PIL import Image, ImageDraw, ImageFont, ImageTk

import capture_store
import config
import theme
import widgets

# Miniatura da coluna de sequência: cabe na largura do card (coluna de ~230px
# menos a barra de rolagem e os espaçamentos) e é alta o bastante pra dar pra
# reconhecer o print.
_LARGURA_MINIATURA = 168
_ALTURA_MINIATURA = 112

def _com_numero(imagem, numero, cor_hex):
    """Desenha o número do passo no canto da própria miniatura.

    Desenhar no bitmap em vez de sobrepor um Label com `place`: sobre um
    Label de imagem o posicionamento depende de como o widget centraliza o
    conteúdo, e o badge acabava fora do canto em imagens mais estreitas.
    """
    desenho = ImageDraw.Draw(imagem)
    try:
        fonte = ImageFont.truetype("segoeuib.ttf", 13)
    except Exception:
        fonte = ImageFont.load_default()
    texto = str(numero)
    caixa = desenho.textbbox((0, 0), texto, font=fonte)
    larg = (caixa[2] - caixa[0]) + 12
    alt = (caixa[3] - caixa[1]) + 10
    desenho.rectangle([0, 0, larg, alt], fill=cor_hex)
    desenho.text((larg / 2, alt / 2), texto, font=fonte, fill="#ffffff", anchor="mm")
    return imagem


MODELOS_UI = [
    ("passo", "Passo a passo", "1 imagem por passo, legenda acima"),
    ("ficha", "Ficha de evidência", "2 por página, com metadados"),
    ("qa", "Relatório QA", "coluna lateral com contexto"),
]


class MontarDocumento(Toplevel):
    def __init__(self, parent_app, nomes_selecionados):
        super().__init__(parent_app.root)
        self.parent_app = parent_app
        self.title("Montar documento")
        self.state("zoomed")
        t = theme.get(parent_app.modo_escuro)
        self.configure(bg=t["bg_content"])

        # Uma lista de referências por coluna, e não uma só para as duas: as
        # colunas são reconstruídas separadamente e em ordens diferentes (as
        # setas fazem sequência→centro, o arraste faz centro→sequência). Com a
        # lista compartilhada, quem reconstruía por último zerava as
        # referências da outra e as miniaturas sumiam da tela.
        self.imagens_sequencia = []
        self.imagens_passos = []
        self._capa_digitada = {}
        self.passos = []
        for nome in sorted(nomes_selecionados, reverse=True):
            caminho = os.path.join(parent_app.pasta_capturas, nome)
            if not os.path.exists(caminho):
                continue
            meta = capture_store.load_meta(caminho)
            self.passos.append({
                "nome": nome, "caminho": caminho,
                "legenda": meta.get("caption", ""),
            })

        self.var_modelo = tk.StringVar(value="passo")
        self.var_cor = tk.StringVar(value="#0B7285")
        self.var_numerar = tk.BooleanVar(value=True)
        self.var_borda = tk.BooleanVar(value=parent_app.config.get("borda_ativada", False))

        self.entries_capa = {}
        self.frame_passos = None
        self.lbl_paginas = None
        self._cards = []
        self._arraste = None

        self._montar_ui(t)
        self.protocol("WM_DELETE_WINDOW", self.destroy)

    # ---------- UI ----------

    def _montar_ui(self, t):
        titlebar = tk.Frame(self, bg=t["bg_header"], height=42)
        titlebar.pack(fill="x")
        titlebar.pack_propagate(False)
        tk.Label(titlebar, text=f"Novo documento · {len(self.passos)} capturas", bg=t["bg_header"],
                 fg=t["text_secondary"], font=(theme.FONT, theme.FS_BODY)).pack(
                     side="left", padx=(14, 0))

        # As três colunas ficam num PanedWindow em vez de larguras fixas:
        # dá pra arrastar as divisas e dar mais espaço pra coluna central
        # (onde se edita de fato), que é o conteúdo principal da tela.
        corpo = tk.PanedWindow(self, orient="horizontal", bg=t["border_soft"],
                                sashwidth=6, sashrelief="flat", bd=0, opaqueresize=True)
        corpo.pack(fill="both", expand=True)

        self._montar_coluna_sequencia(corpo, t)
        self._montar_coluna_central(corpo, t)
        self._montar_coluna_direita(corpo, t)

    def _montar_coluna_sequencia(self, corpo, t):
        col = tk.Frame(corpo, bg=t["bg_footer"])
        corpo.add(col, minsize=170, width=230, stretch="never")
        tk.Label(col, text="SEQUÊNCIA", bg=t["bg_footer"], fg=t["text_muted"],
                 font=(theme.FONT, theme.FS_EYEBROW, "bold")).pack(
                     anchor="w", padx=14, pady=(14, 0))
        widgets.texto_fluido(col, "arraste os cartões pra reordenar · ✕ remove",
                              self.parent_app.modo_escuro,
                              bg=t["bg_footer"]).pack(fill="x", padx=14, pady=(0, 10))

        wrap = tk.Frame(col, bg=t["bg_footer"])
        wrap.pack(fill="both", expand=True)
        canvas = tk.Canvas(wrap, bg=t["bg_footer"], highlightthickness=0, width=1)
        scrollbar = tk.Scrollbar(wrap, orient="vertical", command=canvas.yview)
        self.frame_sequencia = tk.Frame(canvas, bg=t["bg_footer"])
        janela_seq = canvas.create_window((0, 0), window=self.frame_sequencia, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side="left", fill="both", expand=True, padx=(12, 0))
        scrollbar.pack(side="right", fill="y")
        self.frame_sequencia.bind(
            "<Configure>", lambda e: canvas.config(scrollregion=canvas.bbox("all")))
        # prende a largura do conteúdo à do canvas; sem isso os cards mantêm
        # a largura natural e vazam pra fora da coluna em vez de quebrar
        canvas.bind("<Configure>", lambda e: canvas.itemconfig(janela_seq, width=e.width))
        self._canvas_sequencia = canvas

        self._atualizar_sequencia()

    def _atualizar_sequencia(self):
        t = theme.get(self.parent_app.modo_escuro)
        for w in self.frame_sequencia.winfo_children():
            w.destroy()
        self.imagens_sequencia = []
        self._cards = []
        for idx, passo in enumerate(self.passos):
            linha = tk.Frame(self.frame_sequencia, bg=t["bg_input"],
                              highlightbackground=t["accent"] if idx == 0 else t["border_soft"],
                              highlightthickness=1 if idx == 0 else 1, cursor="fleur")
            linha.pack(fill="x", pady=4, padx=(0, 10))
            self._cards.append(linha)

            # A miniatura ocupa a largura inteira do card, porque é por ela
            # que o passo é reconhecido: número e controles ficam na linha de
            # cima, e a imagem vem abaixo, sem disputar espaço horizontal.
            topo = tk.Frame(linha, bg=t["bg_input"])
            topo.pack(fill="x", padx=6, pady=(4, 0))

            # Área de clique maior nos controles: eram 5px de padding e ficavam
            # difíceis de acertar. O arraste do card é o caminho principal;
            # estes seguem como ajuste fino de uma posição por vez.
            controles = tk.Frame(topo, bg=t["bg_input"])
            controles.pack(side="right")
            for rotulo, acao in (("↑", lambda i=idx: self._mover(i, -1)),
                                  ("↓", lambda i=idx: self._mover(i, 1)),
                                  ("✕", lambda i=idx: self._remover(i))):
                alvo = tk.Label(controles, text=rotulo, bg=t["bg_input"],
                                 fg=t["danger_text"] if rotulo == "✕" else t["text_tertiary"],
                                 font=(theme.FONT, theme.FS_SUBTITLE), cursor="hand2",
                                 padx=9, pady=4)
                alvo.pack(side="left")
                alvo.bind("<Button-1>", lambda e, a=acao: a())
                alvo.bind("<Enter>", lambda e, w=alvo: w.config(bg=t["pill_bg"]))
                alvo.bind("<Leave>", lambda e, w=alvo: w.config(bg=t["bg_input"]))

            arrastaveis = [linha, topo]
            try:
                img = Image.open(passo["caminho"]).convert("RGB")
                img.thumbnail((_LARGURA_MINIATURA, _ALTURA_MINIATURA))
                img = _com_numero(img, idx + 1, t["accent"])
                img_tk = ImageTk.PhotoImage(img)
                self.imagens_sequencia.append(img_tk)
                # A moldura abraça a imagem em vez de ocupar a largura toda:
                # com prints verticais a miniatura fica estreita e o resto
                # virava um bloco cinza em volta dela.
                moldura = tk.Frame(linha, bg=t["border_soft"])
                moldura.pack(padx=6, pady=(4, 0))
                miniatura = tk.Label(moldura, image=img_tk, bg=t["bg_input"], cursor="fleur")
                miniatura.pack(padx=1, pady=1)
                arrastaveis.extend((moldura, miniatura))
            except Exception:
                pass

            texto = (passo["legenda"] or passo["nome"])[:60]
            rotulo_texto = widgets.texto_fluido(linha, texto, self.parent_app.modo_escuro,
                                                 bg=t["bg_input"], cor="text_primary")
            rotulo_texto.config(cursor="fleur")
            rotulo_texto.pack(fill="x", padx=8, pady=(5, 8))
            arrastaveis.append(rotulo_texto)

            for w in arrastaveis:
                w.bind("<ButtonPress-1>", lambda e, i=idx: self._arraste_iniciar(i))
                w.bind("<B1-Motion>", self._arraste_mover)
                w.bind("<ButtonRelease-1>", self._arraste_soltar)

        self._atualizar_paginas()

    # ---------- reordenar arrastando ----------

    def _indice_sob_y(self, y_tela):
        """Posição de inserção correspondente à altura da tela informada."""
        for i, card in enumerate(self._cards):
            try:
                topo = card.winfo_rooty()
                meio = topo + card.winfo_height() / 2
            except Exception:
                continue
            if y_tela < meio:
                return i
        return len(self._cards)

    def _arraste_iniciar(self, idx):
        self._arraste = {"origem": idx, "destino": idx, "ativo": False}

    def _arraste_mover(self, event):
        estado = getattr(self, "_arraste", None)
        if not estado:
            return
        t = theme.get(self.parent_app.modo_escuro)
        if not estado["ativo"]:
            estado["ativo"] = True
            # o card que está sendo levado fica apagado
            self._cards[estado["origem"]].config(bg=t["accent_bg"])
        destino = self._indice_sob_y(event.y_root)
        estado["destino"] = destino
        # marca onde vai entrar: borda de acento no card de destino
        for i, card in enumerate(self._cards):
            alvo = i == destino or (destino == len(self._cards) and i == len(self._cards) - 1)
            card.config(highlightbackground=t["accent"] if alvo else t["border_soft"],
                        highlightthickness=2 if alvo else 1)

    def _arraste_soltar(self, event):
        estado = getattr(self, "_arraste", None)
        self._arraste = None
        if not estado or not estado["ativo"]:
            return  # foi um clique simples, não um arraste
        origem = estado["origem"]
        destino = estado["destino"]
        if destino > origem:
            destino -= 1   # o próprio item sai da lista antes de ser reinserido
        destino = max(0, min(len(self.passos) - 1, destino))
        if destino != origem:
            item = self.passos.pop(origem)
            self.passos.insert(destino, item)
            self._atualizar_coluna_central()
        # reconstrói só no fim: rebuildar durante o arraste destruiria o widget
        # que está recebendo os eventos de movimento
        self._atualizar_sequencia()

    def _mover(self, idx, delta):
        novo = idx + delta
        if 0 <= novo < len(self.passos):
            self.passos[idx], self.passos[novo] = self.passos[novo], self.passos[idx]
            self._atualizar_sequencia()
            self._atualizar_coluna_central()

    def _remover(self, idx):
        if 0 <= idx < len(self.passos):
            self.passos.pop(idx)
            self._atualizar_sequencia()
            self._atualizar_coluna_central()

    def _montar_coluna_central(self, corpo, t):
        self.col_central = tk.Frame(corpo, bg=t["bg_content"])
        corpo.add(self.col_central, minsize=380, stretch="always")
        self._montar_coluna_central_conteudo(t)

    def _montar_coluna_central_conteudo(self, t):
        # Guarda o que está digitado na capa ANTES de destruir os widgets. Esta
        # coluna é remontada ao reordenar a sequência, e a leitura de um widget
        # já destruído falha calada — era assim que o título voltava ao padrão
        # e o caso, o autor e o ambiente ficavam em branco depois de mover um
        # print de lugar.
        self._capa_digitada = self._capa_atual()
        for w in self.col_central.winfo_children():
            w.destroy()
        self.imagens_passos = []

        canvas = tk.Canvas(self.col_central, bg=t["bg_content"], highlightthickness=0, width=1)
        scrollbar = tk.Scrollbar(self.col_central, orient="vertical", command=canvas.yview)
        frame = tk.Frame(canvas, bg=t["bg_content"])
        janela_central = canvas.create_window((0, 0), window=frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side="left", fill="both", expand=True, padx=24, pady=20)
        scrollbar.pack(side="right", fill="y")
        frame.bind("<Configure>", lambda e: canvas.config(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>", lambda e: canvas.itemconfig(janela_central, width=e.width))
        canvas.bind("<Enter>", lambda e: canvas.bind_all("<MouseWheel>",
                    lambda ev: canvas.yview_scroll(int(-1 * (ev.delta / 120)), "units")))
        canvas.bind("<Leave>", lambda e: canvas.unbind_all("<MouseWheel>"))

        capa_card = tk.Frame(frame, bg=t["bg_panel"],
                             highlightbackground=t["border_soft"], highlightthickness=1)
        capa_card.pack(fill="x", pady=(0, 16))
        tk.Label(capa_card, text="CAPA DO DOCUMENTO", bg=t["bg_panel"], fg=t["accent"],
                 font=(theme.FONT, theme.FS_EYEBROW, "bold")).pack(
                     anchor="w", padx=16, pady=(14, 8))

        linha1 = tk.Frame(capa_card, bg=t["bg_panel"])
        linha1.pack(fill="x", padx=16)
        for chave, rotulo, largura in (("titulo", "Título", 2), ("caso", "Caso / projeto", 1)):
            bloco = tk.Frame(linha1, bg=t["bg_panel"])
            bloco.pack(side="left", fill="x", expand=True, padx=(0, 10))
            _, entry = widgets.campo_rotulado(bloco, rotulo, self.parent_app.modo_escuro,
                                                valor_inicial=self._valor_capa_inicial(chave))
            self.entries_capa[chave] = entry

        linha2 = tk.Frame(capa_card, bg=t["bg_panel"])
        linha2.pack(fill="x", padx=16, pady=(0, 16))
        for chave, rotulo in (("autor", "Autor"), ("data", "Data"), ("ambiente", "Ambiente")):
            bloco = tk.Frame(linha2, bg=t["bg_panel"])
            bloco.pack(side="left", fill="x", expand=True, padx=(0, 10))
            _, entry = widgets.campo_rotulado(bloco, rotulo, self.parent_app.modo_escuro,
                                                valor_inicial=self._valor_capa_inicial(chave))
            self.entries_capa[chave] = entry

        self.entries_legenda = {}
        for idx, passo in enumerate(self.passos):
            card = tk.Frame(frame, bg=t["bg_panel"],
                            highlightbackground=t["border_soft"], highlightthickness=1)
            card.pack(fill="x", pady=6)
            linha = tk.Frame(card, bg=t["bg_panel"])
            linha.pack(fill="x", padx=16, pady=14)

            tk.Label(linha, text=str(idx + 1), bg=t["accent"], fg="#ffffff", width=2,
                     font=(theme.FONT, theme.FS_BODY, "bold")).pack(side="left", anchor="n")

            meio = tk.Frame(linha, bg=t["bg_panel"])
            meio.pack(side="left", fill="both", expand=True, padx=12)
            tk.Label(meio, text="Legenda do passo", bg=t["bg_panel"], fg=t["text_tertiary"],
                     font=(theme.FONT, theme.FS_CAPTION)).pack(anchor="w")
            txt = tk.Text(meio, height=3, font=(theme.FONT, theme.FS_BODY), wrap="word",
                           bd=0, relief="flat", bg=t["bg_input"], fg=t["text_primary"],
                           insertbackground=t["text_primary"],
                           highlightbackground=t["border_input"], highlightcolor=t["border_input"],
                           highlightthickness=1)
            txt.pack(fill="x", pady=4)
            txt.insert("1.0", passo["legenda"])
            txt.bind("<KeyRelease>", lambda e, i=idx, w=txt: self._on_legenda_change(i, w))
            self.entries_legenda[idx] = txt

            try:
                img = Image.open(passo["caminho"])
                img.thumbnail((160, 110))
                img_tk = ImageTk.PhotoImage(img)
                self.imagens_passos.append(img_tk)
                tk.Label(linha, image=img_tk, bg=t["bg_input"]).pack(side="left")
            except Exception:
                pass

    def _capa_atual(self):
        """O que está nos campos da capa agora, enquanto os widgets existem."""
        valores = dict(getattr(self, "_capa_digitada", {}))
        for chave, entry in getattr(self, "entries_capa", {}).items():
            try:
                valores[chave] = entry.get()
            except Exception:
                pass          # widget já destruído: mantém o valor anterior
        return valores

    def _valor_capa_inicial(self, chave):
        guardado = getattr(self, "_capa_digitada", {}).get(chave)
        if guardado is not None:
            return guardado     # string vazia também vale: o usuário apagou
        if chave == "titulo":
            return "Evidências de teste"
        if chave == "data":
            return datetime.now().strftime("%d/%m/%Y")
        if chave == "autor":
            # último autor usado, pra não ter que redigitar a cada documento
            return self.parent_app.config.get("autor_padrao", "")
        return ""

    def _on_legenda_change(self, idx, widget):
        if 0 <= idx < len(self.passos):
            self.passos[idx]["legenda"] = widget.get("1.0", "end").strip()

    def _atualizar_coluna_central(self):
        t = theme.get(self.parent_app.modo_escuro)
        self._montar_coluna_central_conteudo(t)

    def _montar_coluna_direita(self, corpo, t):
        col = tk.Frame(corpo, bg=t["bg_panel"])
        corpo.add(col, minsize=220, width=290, stretch="never")

        bloco = tk.Frame(col, bg=t["bg_panel"])
        bloco.pack(fill="x", padx=16, pady=14)
        tk.Label(bloco, text="MODELO", bg=t["bg_panel"], fg=t["text_muted"],
                 font=(theme.FONT, theme.FS_EYEBROW, "bold")).pack(anchor="w", pady=(0, 8))

        for valor, nome, desc in MODELOS_UI:
            linha = tk.Frame(bloco, bg=t["bg_panel"], cursor="hand2")
            linha.pack(fill="x", pady=3)
            self._linha_modelo(linha, valor, nome, desc, t)

        widgets.titulo_secao(bloco, "Opções", self.parent_app.modo_escuro)
        widgets.linha_checkbox(bloco, "Numerar os passos", self.var_numerar,
                               self.parent_app.modo_escuro)
        widgets.linha_checkbox(bloco, "Adicionar borda nas imagens", self.var_borda,
                               self.parent_app.modo_escuro)

        tk.Label(bloco, text="Cor de destaque", bg=t["bg_panel"], fg=t["text_tertiary"],
                 font=(theme.FONT, theme.FS_CAPTION)).pack(anchor="w", pady=(10, 4))
        self._cores_frame = tk.Frame(bloco, bg=t["bg_panel"])
        self._cores_frame.pack(anchor="w")
        self._swatches_cor = {}
        for cor in theme.PALETTE:
            wrap = tk.Frame(self._cores_frame, bg=t["bg_panel"])
            wrap.pack(side="left", padx=3, pady=3)
            q = tk.Frame(wrap, bg=cor, width=24, height=24, cursor="hand2")
            q.pack_propagate(False)
            q.pack()
            q.bind("<Button-1>", lambda e, c=cor: self._selecionar_cor(c))
            self._swatches_cor[cor] = wrap
        self._atualizar_cores_destaque()

        rodape = tk.Frame(col, bg=t["bg_footer"])
        rodape.pack(fill="x", side="bottom")
        self.lbl_paginas = tk.Label(rodape, text="", bg=t["bg_footer"], fg=t["text_tertiary"],
                                     font=(theme.FONT, theme.FS_CAPTION))
        self.lbl_paginas.pack(anchor="w", padx=16, pady=(12, 4))
        widgets.botao_primario(rodape, "Pré-visualizar", self._pre_visualizar,
                                self.parent_app.modo_escuro).pack(fill="x", padx=16, pady=(0, 14))

    def _linha_modelo(self, linha, valor, nome, desc, t):
        def selecionar(v=valor):
            self.var_modelo.set(v)
            self._atualizar_modelos_visual()

        linha.bind("<Button-1>", lambda e: selecionar())
        self._card_modelo_widgets = getattr(self, "_card_modelo_widgets", {})
        lbl = widgets.texto_fluido(linha, nome, self.parent_app.modo_escuro, cor="text_primary",
                                    fonte=(theme.FONT, theme.FS_BODY, "bold"))
        lbl.config(cursor="hand2")
        lbl.pack(fill="x", padx=8, pady=(6, 0))
        lbl.bind("<Button-1>", lambda e: selecionar())
        sub = widgets.texto_fluido(linha, desc, self.parent_app.modo_escuro)
        sub.config(cursor="hand2")
        sub.pack(fill="x", padx=8, pady=(0, 6))
        sub.bind("<Button-1>", lambda e: selecionar())
        self._card_modelo_widgets[valor] = (linha, lbl, sub)
        self._atualizar_modelos_visual()

    def _atualizar_modelos_visual(self):
        t = theme.get(self.parent_app.modo_escuro)
        for valor, (linha, lbl, sub) in getattr(self, "_card_modelo_widgets", {}).items():
            ativo = valor == self.var_modelo.get()
            bg = t["accent_bg"] if ativo else t["bg_panel"]
            linha.config(bg=bg, highlightbackground=t["accent"] if ativo else t["border_soft"],
                         highlightthickness=1)
            lbl.config(bg=bg)
            sub.config(bg=bg)

    def _selecionar_cor(self, cor):
        self.var_cor.set(cor)
        self._atualizar_cores_destaque()

    def _atualizar_cores_destaque(self):
        t = theme.get(self.parent_app.modo_escuro)
        for cor, wrap in self._swatches_cor.items():
            selecionada = cor == self.var_cor.get()
            contorno = t["accent"] if selecionada else t["border"]
            wrap.config(highlightbackground=contorno, highlightcolor=contorno,
                        highlightthickness=2)

    def _atualizar_paginas(self):
        import pdf_export
        n = pdf_export.contar_paginas(self.passos, self.var_modelo.get())
        if self.lbl_paginas:
            self.lbl_paginas.config(text=f"{len(self.passos)} passos · {n} páginas estimadas")

    # ---------- avançar ----------

    def _pre_visualizar(self):
        if not self.passos:
            messagebox.showinfo("Montar documento", "Adicione ao menos uma captura.", parent=self)
            return
        capa = {chave: entry.get().strip() for chave, entry in self.entries_capa.items()}
        # guarda o autor pro próximo documento já vir preenchido
        if capa.get("autor") != self.parent_app.config.get("autor_padrao", ""):
            self.parent_app.config["autor_padrao"] = capa.get("autor", "")
            config.save(self.parent_app.data_dir, self.parent_app.config)
        opcoes = {
            "cor_destaque": self.var_cor.get(),
            "numerar_passos": self.var_numerar.get(),
            "borda_ativada": self.var_borda.get(),
            "borda_cor": self.var_cor.get(),
            "fonte_legenda": self.parent_app.config.get("fonte_legenda", "Arial"),
        }
        import export_preview
        export_preview.PreVisualizarExportar(self.parent_app, self, self.var_modelo.get(), capa,
                                              list(self.passos), opcoes)
