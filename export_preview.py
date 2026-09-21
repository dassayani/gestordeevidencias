"""Tela 'Pré-visualização e exportação' (design '1d'): mostra uma prévia
aproximada (montada com widgets do Tk, não um PDF rasterizado) do modelo
escolhido, permite navegar entre páginas e exporta o PDF de verdade via
`pdf_export.py`."""
import os
from datetime import datetime
from tkinter import Toplevel, messagebox, filedialog
import tkinter as tk
import tkinter.font as tkfont

from PIL import Image, ImageTk

import config
import docx_export
import pdf_export
import theme
import utils
import widgets

PAGINA_W, PAGINA_H = 480, 678  # aproxima a proporção A4

# A previa desenhava com medidas proprias (fonte 10pt, larguras em pixel
# escolhidas a olho) enquanto o documento usa milimetros numa A4. O resultado
# e que uma legenda longa ocupava a pagina inteira aqui e cabia la. Estas duas
# funcoes convertem as medidas reais do gerador para a escala da previa, entao
# o que se ve e o que sai.
_ESCALA = PAGINA_W / pdf_export.PAGE_W          # pixels por milimetro


def _px(mm):
    """Milimetros do documento -> pixels da previa."""
    return max(1, int(round(mm * _ESCALA)))


def _pt(pontos):
    """Corpo de fonte do documento -> altura em pixels na previa.

    O valor volta NEGATIVO de proposito: no Tk, tamanho negativo significa
    pixels, e positivo significa pontos ajustados pelo DPI da tela. Numa tela
    a 150% o mesmo "10pt" saia quase o dobro do tamanho do PDF, e era isso que
    fazia a legenda quebrar em muito mais linhas na previa do que no arquivo.
    """
    return -max(5, int(round(pontos * 0.3528 * _ESCALA)))


def _limitar_linhas(texto, largura_px, fonte, max_linhas):
    """Corta o texto nas linhas que cabem, como o gerador faz na Ficha."""
    try:
        medidor = tkfont.Font(font=fonte)
    except Exception:
        return texto
    linhas, atual = [], ""
    for palavra in str(texto).split():
        teste = f"{atual} {palavra}".strip()
        if atual and medidor.measure(teste) > largura_px:
            linhas.append(atual)
            atual = palavra
        else:
            atual = teste
        # mesma regra do gerador: palavra maior que a linha (URL, caminho de
        # arquivo) é partida no meio, senão a contagem de linhas daqui não
        # bate com a do documento
        while medidor.measure(atual) > largura_px:
            corte = 1
            while corte < len(atual) and medidor.measure(atual[:corte + 1]) <= largura_px:
                corte += 1
            linhas.append(atual[:corte])
            atual = atual[corte:]
    if atual:
        linhas.append(atual)
    if len(linhas) <= max_linhas:
        return texto
    return " ".join(linhas[:max_linhas]).rstrip() + "..."


# Caracteres que o Windows não aceita em nome de arquivo.
_PROIBIDOS = '<>:"/\\|?*'


def _higienizar(texto):
    """Deixa o texto utilizável como nome de arquivo."""
    limpo = "".join(" " if c in _PROIBIDOS else c for c in (texto or ""))
    limpo = " ".join(limpo.split())          # colapsa espaços
    return limpo.strip(" .")                  # Windows rejeita ponto/espaço no fim


class PreVisualizarExportar(Toplevel):
    def __init__(self, parent_app, janela_anterior, modelo, capa, passos, opcoes):
        super().__init__(parent_app.root)
        self.parent_app = parent_app
        self.janela_anterior = janela_anterior
        self.modelo = modelo
        self.capa = capa
        self.passos = passos
        self.opcoes = opcoes
        self.pagina_atual = 0
        self.imagens_tk = []

        self.title("Pré-visualização e exportação")
        self.state("zoomed")
        t = theme.get(parent_app.modo_escuro)
        self.configure(bg=t["bg_content"])

        self.paginas = [self.passos[i:i + 2] for i in range(0, max(1, len(self.passos)), 2)] or [[]]

        self._montar_ui(t)
        self.protocol("WM_DELETE_WINDOW", self.destroy)

    def _montar_ui(self, t):
        titlebar = tk.Frame(self, bg=t["bg_header"], height=42)
        titlebar.pack(fill="x")
        titlebar.pack_propagate(False)
        titulo = self.capa.get("titulo") or "Documento"
        tk.Label(titlebar, text=f"{titulo} · pré-visualização",
                 bg=t["bg_header"], fg=t["text_secondary"],
                 font=(theme.FONT, theme.FS_BODY)).pack(side="left", padx=(14, 0))

        corpo = tk.Frame(self, bg=t["bg_content"])
        corpo.pack(fill="both", expand=True)

        # O painel de exportação tem largura fixa e é empacotado antes do
        # centro para reservar o próprio espaço: na ordem inversa, uma janela
        # estreita o espreme contra a prévia.
        self._montar_painel_exportacao(corpo, t)

        centro = tk.Frame(corpo, bg=t["bg_content"])
        centro.pack(side="left", fill="both", expand=True, padx=30, pady=24)
        self.moldura = tk.Frame(centro, bg="#ffffff", width=PAGINA_W, height=PAGINA_H)
        self.moldura.pack(anchor="center")
        self.moldura.pack_propagate(False)

        nav = tk.Frame(centro, bg=t["bg_content"])
        nav.pack(pady=10)
        widgets.Botao(nav, "‹ Anterior", self._pagina_anterior, self.parent_app.modo_escuro,
                       variante="ghost", tamanho="sm", bg=t["bg_content"]).pack(side="left", padx=6)
        self.lbl_pagina = tk.Label(nav, text="", bg=t["bg_content"], fg=t["text_primary"],
                                   font=(theme.FONT, theme.FS_BODY, "bold"))
        self.lbl_pagina.pack(side="left", padx=6)
        widgets.Botao(nav, "Próxima ›", self._proxima_pagina, self.parent_app.modo_escuro,
                       variante="ghost", tamanho="sm", bg=t["bg_content"]).pack(side="left", padx=6)

        self._render_pagina()

    # ---------- navegação ----------

    def _pagina_anterior(self):
        if self.pagina_atual > 0:
            self.pagina_atual -= 1
            self._render_pagina()

    def _proxima_pagina(self):
        if self.pagina_atual < len(self.paginas) - 1:
            self.pagina_atual += 1
            self._render_pagina()

    # ---------- prévia (aproximada, via widgets Tk) ----------
    #
    # Os tamanhos de fonte daqui pra baixo são literais de propósito: esta é
    # uma miniatura da página impressa (A4 reduzido a ~480x678), então eles
    # imitam a proporção do PDF gerado, não a escala tipográfica da
    # interface. Trocar por theme.FS_* deixaria a prévia fora de escala.

    def _render_pagina(self):
        for w in self.moldura.winfo_children():
            w.destroy()
        self.imagens_tk = []
        nomes = dict((valor, nome) for valor, nome, _ in _MODELOS_NOMES)
        self.lbl_pagina.config(
            text=f"Página {self.pagina_atual + 1} de {len(self.paginas)} · "
                 f"modelo: {nomes.get(self.modelo, self.modelo)}")

        itens = self.paginas[self.pagina_atual]
        cor = self.opcoes.get("cor_destaque", "#0B7285")

        # O rodapé vem antes do conteúdo porque no `pack` quem chega primeiro
        # reserva o espaço: o corpo da página se expande no que sobra.
        no_qa = self.modelo == "qa"
        self._rodape(compacto=no_qa,
                     recuo_esquerda=_px(pdf_export.X0_QA) if no_qa else None)

        if self.modelo == "ficha":
            self._render_ficha(itens, cor)
        elif self.modelo == "qa":
            self._render_qa(itens, cor)
        else:
            self._render_passo(itens, cor)

    def _thumb(self, caminho, max_w, max_h):
        try:
            img = Image.open(caminho)
            img.thumbnail((max_w, max_h))
            tk_img = ImageTk.PhotoImage(img)
            self.imagens_tk.append(tk_img)
            return tk_img
        except Exception:
            return None

    def _rodape(self, compacto=False, recuo_esquerda=None):
        """Assinatura à esquerda e paginação à direita, como no documento.

        O gerador desenha esta linha nos três modelos; a prévia só tinha no
        passo a passo. O modelo QA numera "1 / 3" em vez de "Página 1 de 3" e
        começa a assinatura depois da faixa lateral.
        """
        rodape = tk.Frame(self.moldura, bg="#ffffff")
        rodape.pack(fill="x", side="bottom", pady=10,
                    padx=(recuo_esquerda if recuo_esquerda is not None else 26, 26))
        tk.Label(rodape, text="Gestor de Evidências", bg="#ffffff", fg="#8EA2AD",
                 font=(theme.FONT, _pt(8))).pack(side="left")
        atual, total = self.pagina_atual + 1, len(self.paginas)
        tk.Label(rodape, text=f"{atual} / {total}" if compacto else f"Página {atual} de {total}",
                 bg="#ffffff", fg="#8EA2AD", font=(theme.FONT, _pt(8))).pack(side="right")

    def _render_passo(self, itens, cor):
        tk.Frame(self.moldura, bg=cor, height=5).pack(fill="x")
        if self.pagina_atual == 0:
            topo = tk.Frame(self.moldura, bg="#ffffff")
            topo.pack(fill="x", padx=26, pady=(18, 10))
            tk.Label(topo, text="MANUAL DE OPERAÇÃO", bg="#ffffff", fg=cor,
                     font=(theme.FONT, _pt(9), "bold")).pack(anchor="w")
            linha_titulo = tk.Frame(topo, bg="#ffffff")
            linha_titulo.pack(fill="x")
            tk.Label(linha_titulo, text=self.capa.get("titulo") or "Documento", bg="#ffffff",
                     fg="#17262E", font=(theme.FONT, _pt(18), "bold"), anchor="w",
                     justify="left").pack(side="left", fill="x", expand=True)
            # mesma disposição do documento: os campos empilhados à direita
            campos = [self.capa.get(k, "") for k in ("caso", "ambiente", "autor", "data")]
            resumo = "\n".join(v for v in campos if v)
            if resumo:
                tk.Label(linha_titulo, text=resumo, bg="#ffffff", fg="#8EA2AD",
                         font=(theme.FONT, _pt(9)), justify="right",
                         anchor="ne").pack(side="right")
            tk.Frame(self.moldura, bg="#E4EAEE", height=1).pack(fill="x", padx=26, pady=(0, 10))
        corpo = tk.Frame(self.moldura, bg="#ffffff")
        corpo.pack(fill="both", expand=True, padx=26)
        for idx, passo in enumerate(itens):
            linha = tk.Frame(corpo, bg="#ffffff")
            linha.pack(fill="x", pady=8)
            cabeca = tk.Frame(linha, bg="#ffffff")
            cabeca.pack(fill="x")
            if self.opcoes.get("numerar_passos", True):
                tk.Label(cabeca, text=str(self.pagina_atual * 2 + idx + 1),
                         bg=cor, fg="#ffffff", width=2,
                         font=(theme.FONT, _pt(10), "bold")).pack(side="left", padx=(0, 8))
            # mesma largura util e mesmo corpo de fonte do PDF deste modelo
            larg_legenda = _px(pdf_export.PAGE_W - pdf_export.MARGEM_PASSO * 2 - 13)
            tk.Label(cabeca, text=passo.get("legenda") or "Sem legenda", bg="#ffffff", fg="#17262E",
                     font=(theme.FONT, _pt(12), "bold"),
                     anchor="w",
                     wraplength=larg_legenda, justify="left").pack(
                side="left", fill="x", expand=True)
            img_tk = self._thumb(passo.get("caminho"), 420, 150)
            wrap = tk.Frame(linha, bg="#DCE4E9",
                            highlightbackground=cor
                            if self.opcoes.get("borda_ativada") else "#DCE4E9",
                             highlightthickness=2 if self.opcoes.get("borda_ativada") else 1)
            wrap.pack(fill="x", pady=(6, 0))
            if img_tk:
                tk.Label(wrap, image=img_tk, bg="#ffffff").pack()

    def _render_ficha(self, itens, cor):
        header = tk.Frame(self.moldura, bg=cor)
        header.pack(fill="x")
        tk.Label(header, text="REGISTRO DE EVIDÊNCIAS", bg=cor, fg="#CFE8EE",
                 font=(theme.FONT, _pt(8))).pack(anchor="w", padx=20, pady=(12, 0))
        titulo = self.capa.get("titulo") or "Documento"
        caso = self.capa.get("caso", "")
        linha_topo = tk.Frame(header, bg=cor)
        linha_topo.pack(fill="x", padx=20, pady=(0, 12))
        tk.Label(linha_topo, text=f"{titulo}" + (f" · {caso}" if caso else ""), bg=cor,
                 fg="#ffffff", font=(theme.FONT, _pt(15), "bold"), anchor="w",
                 justify="left").pack(side="left", fill="x", expand=True)
        # ambiente, data e autor apareciam no documento e nao na previa
        direita = "\n".join(v for v in (self.capa.get("ambiente", ""),
                                        self.capa.get("data", ""),
                                        self.capa.get("autor", "")) if v)
        if direita:
            tk.Label(linha_topo, text=direita, bg=cor, fg="#CFE8EE",
                     font=(theme.FONT, _pt(8)), justify="right", anchor="e").pack(side="right")
        corpo = tk.Frame(self.moldura, bg="#ffffff")
        corpo.pack(fill="both", expand=True, padx=18, pady=14)
        for idx, passo in enumerate(itens):
            n = self.pagina_atual * 2 + idx + 1
            card = tk.Frame(corpo, bg="#ffffff",
                            highlightbackground="#E1E8EC", highlightthickness=1)
            card.pack(fill="x", pady=6)
            cabeca = tk.Frame(card, bg="#ffffff")
            cabeca.pack(fill="x", padx=12, pady=(10, 6))
            tk.Label(cabeca, text=f"EV-{n:02d}", bg="#E6F2F5", fg=cor,
                     font=(theme.FONT, _pt(8), "bold")).pack(
                side="left", padx=(0, 8))
            larg_legenda = _px(pdf_export.PAGE_W - pdf_export.MARGEM * 2 - 28)
            fonte_legenda = (theme.FONT, _pt(11), "bold")
            texto_legenda = _limitar_linhas(
                passo.get("legenda") or "Sem legenda", larg_legenda, fonte_legenda,
                pdf_export.LINHAS_LEGENDA_FICHA)
            tk.Label(cabeca, text=texto_legenda, bg="#ffffff", fg="#17262E",
                     font=fonte_legenda, anchor="w", wraplength=larg_legenda,
                     justify="left").pack(side="left", fill="x", expand=True)
            img_tk = self._thumb(passo.get("caminho"), 400, 110)
            if img_tk:
                tk.Label(card, image=img_tk, bg="#ffffff").pack(padx=12, pady=(0, 10))

    def _render_qa(self, itens, cor):
        linha = tk.Frame(self.moldura, bg="#ffffff")
        linha.pack(fill="both", expand=True)
        # o documento recua 8 mm dentro da faixa e escreve na largura restante
        recuo = _px(8)
        texto_lateral = _px(pdf_export.LARGURA_LATERAL_QA - 16)
        # a faixa segue a cor de destaque, escurecida como no gerador
        rgb = utils.escurecer(utils.hex_to_rgb(cor))
        faixa = utils.rgb_to_hex(rgb)
        faixa_texto = utils.rgb_to_hex(utils.clarear(rgb, 0.72))
        faixa_rotulo = utils.rgb_to_hex(utils.clarear(rgb, 0.58))
        lateral = tk.Frame(linha, bg=faixa, width=_px(pdf_export.LARGURA_LATERAL_QA))
        lateral.pack(side="left", fill="y")
        lateral.pack_propagate(False)
        tk.Label(lateral, text="Relatório de teste", bg=faixa, fg="#ffffff",
                 font=(theme.FONT, _pt(13), "bold"), wraplength=texto_lateral,
                 justify="left", anchor="w").pack(anchor="w", padx=recuo, pady=(16, 6))
        # o documento lista titulo, caso e ambiente aqui; a previa mostrava so o titulo
        contexto = "\n".join(v for v in (self.capa.get("titulo", ""),
                                        self.capa.get("caso", ""),
                                        self.capa.get("ambiente", "")) if v)
        tk.Label(lateral, text=contexto, bg=faixa, fg=faixa_texto,
                 font=(theme.FONT, _pt(8)), wraplength=texto_lateral, justify="left",
                 anchor="w").pack(anchor="w", padx=recuo)
        tk.Label(lateral, text="RESUMO", bg=faixa, fg=faixa_rotulo,
                 font=(theme.FONT, _pt(7.5), "bold")).pack(anchor="w", padx=recuo, pady=(20, 2))
        tk.Label(lateral, text=str(len(self.passos)), bg=faixa, fg="#ffffff",
                 font=(theme.FONT, _pt(18), "bold")).pack(anchor="w", padx=recuo)
        tk.Label(lateral, text="capturas", bg=faixa, fg=faixa_texto,
                 font=(theme.FONT, _pt(7))).pack(anchor="w", padx=recuo)
        assinatura = "\n".join(v for v in (self.capa.get("autor", ""),
                                          self.capa.get("data", "")) if v)
        if assinatura:
            tk.Label(lateral, text=assinatura, bg=faixa, fg=faixa_rotulo,
                     font=(theme.FONT, _pt(8)), wraplength=texto_lateral, justify="left",
                     anchor="w").pack(anchor="w", padx=recuo, pady=(14, 0))

        principal = tk.Frame(linha, bg="#ffffff")
        principal.pack(side="left", fill="both", expand=True, padx=16, pady=16)
        tk.Label(principal, text="EVIDÊNCIAS", bg="#ffffff", fg=cor,
                 font=(theme.FONT, _pt(8), "bold")).pack(anchor="w")
        for idx, passo in enumerate(itens):
            n = self.pagina_atual * 2 + idx + 1
            item = tk.Frame(principal, bg="#ffffff")
            item.pack(fill="x", pady=8)
            cabeca = tk.Frame(item, bg="#ffffff")
            cabeca.pack(fill="x")
            tk.Label(cabeca, text=str(n), bg="#ffffff", fg=cor,
                     font=(theme.FONT, _pt(11), "bold")).pack(side="left")
            larg_legenda = _px(pdf_export.PAGE_W - pdf_export.MARGEM - pdf_export.X0_QA - 10)
            tk.Label(cabeca, text=passo.get("legenda") or "Sem legenda", bg="#ffffff", fg="#17262E",
                     font=(theme.FONT, _pt(10.5), "bold"), anchor="w",
                     wraplength=larg_legenda, justify="left").pack(
                side="left", padx=8, fill="x", expand=True)
            img_tk = self._thumb(passo.get("caminho"), 300, 110)
            if img_tk:
                tk.Label(item, image=img_tk, bg="#ffffff").pack(pady=(4, 0))

    # ---------- painel de exportação ----------

    def _montar_painel_exportacao(self, corpo, t):
        col = tk.Frame(corpo, bg=t["bg_panel"], width=290)
        col.pack(side="right", fill="y")
        col.pack_propagate(False)

        bloco = tk.Frame(col, bg=t["bg_panel"])
        bloco.pack(fill="x", padx=16, pady=16)
        widgets.titulo_secao(bloco, "Exportar", self.parent_app.modo_escuro, pady=(0, 8))

        self.var_formato = tk.StringVar(value="pdf")
        widgets.escolha_pills(bloco, [("pdf", "PDF"), ("docx", "DOCX")], self.var_formato,
                               self.parent_app.modo_escuro, on_change=self._on_formato_change).pack(
            anchor="w", pady=(0, 8))

        # Sem pasta escolhida à mão, o destino é a subpasta do formato dentro da
        # pasta de capturas (PDF/ ou DOCX/), e acompanha a troca de formato.
        bloco_destino, entry_destino = widgets.campo_rotulado(
            bloco, "Salvar em", self.parent_app.modo_escuro,
            valor_inicial=self._pasta_padrao(self.var_formato.get()))
        entry_destino.config(state="readonly")
        self._entry_destino = entry_destino

        def alterar_destino():
            nova = filedialog.askdirectory(parent=self, initialdir=entry_destino.get(),
                                            title="Pasta para salvar o documento")
            if not nova:
                return
            self._definir_destino(nova)
            self.parent_app.config["pasta_pdfs_custom"] = nova
            config.save(self.parent_app.data_dir, self.parent_app.config)

        widgets.botao_secundario(bloco, "Alterar pasta…",
                                 alterar_destino, self.parent_app.modo_escuro).pack(
            anchor="w", pady=(2, 4))

        rodape = tk.Frame(col, bg=t["bg_footer"])
        rodape.pack(fill="x", side="bottom")
        tk.Label(rodape, text=f"{len(self.passos)} capturas · {len(self.paginas)} páginas",
                 bg=t["bg_footer"],
                 fg=t["text_tertiary"], font=(theme.FONT, theme.FS_CAPTION)).pack(
                     anchor="w", padx=16, pady=(12, 6))
        self.btn_exportar = widgets.botao_primario(rodape, "Exportar PDF", self._exportar,
                                                     self.parent_app.modo_escuro)
        self.btn_exportar.pack(fill="x", padx=16, pady=(0, 14))

    def _caminho_destino(self, pasta, formato):
        """Nome do arquivo a partir do Título e do Caso/Projeto informados.

        Com os dois campos vazios, recorre ao nome com horário para nunca
        gerar arquivo sem nome. Acrescenta sufixo quando o nome já existe,
        para não sobrescrever o documento anterior em silêncio.
        """
        partes = [_higienizar(self.capa.get("titulo", "")), _higienizar(self.capa.get("caso", ""))]
        base = " - ".join(p for p in partes if p)
        if not base:
            base = f"Relatorio_{datetime.now().strftime('%H%M%S')}"
        base = base[:120]
        caminho = os.path.join(pasta, f"{base}.{formato}")
        n = 2
        while os.path.exists(caminho):
            caminho = os.path.join(pasta, f"{base} ({n}).{formato}")
            n += 1
        return caminho

    def _pasta_padrao(self, formato):
        """Pasta sugerida pro formato. Uma pasta escolhida à mão tem prioridade."""
        escolhida = self.parent_app.config.get("pasta_pdfs_custom")
        if escolhida:
            return escolhida
        return self.parent_app.pasta_documentos(formato)

    def _definir_destino(self, caminho):
        self._entry_destino.config(state="normal")
        self._entry_destino.delete(0, "end")
        self._entry_destino.insert(0, caminho)
        self._entry_destino.config(state="readonly")

    def _on_formato_change(self, valor):
        self.btn_exportar.definir_texto(f"Exportar {valor.upper()}")
        # o destino acompanha o formato (PDF/ ou DOCX/), a menos que o usuário
        # tenha fixado uma pasta pelo "Alterar pasta…"
        self._definir_destino(self._pasta_padrao(valor))

    def _exportar(self):
        formato = self.var_formato.get()
        destino_pasta = (self._entry_destino.get().strip()
                         or self.parent_app.pasta_documentos(formato))
        try:
            os.makedirs(destino_pasta, exist_ok=True)
        except Exception as e:
            messagebox.showerror("Exportar", f"Não foi possível usar essa pasta: {e}", parent=self)
            return
        destino = self._caminho_destino(destino_pasta, formato)
        try:
            if formato == "docx":
                docx_export.exportar(self.modelo, destino, self.capa, self.passos, self.opcoes)
            else:
                pdf_export.exportar(self.modelo, destino, self.capa, self.passos, self.opcoes)
        except Exception as e:
            messagebox.showerror("Exportar", f"Falha ao gerar o documento: {e}", parent=self)
            return
        messagebox.showinfo("Exportar", f"Documento gerado:\n{destino}", parent=self)
        os.startfile(destino_pasta)
        # A prévia continua aberta de propósito: é dela que se gera o outro
        # formato, ou o outro modelo, sem remontar o documento. Gerar de novo
        # não sobrescreve nada — `_caminho_destino` acrescenta sufixo quando o
        # nome já existe.


_MODELOS_NOMES = [
    ("passo", "Passo a passo", None),
    ("ficha", "Ficha de evidência", None),
    ("qa", "Relatório QA", None),
]
