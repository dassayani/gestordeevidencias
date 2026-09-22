"""Tela 'Pré-visualização e exportação' (design '1d').

A prévia é a página do documento de verdade: gera o PDF num arquivo
temporário e mostra a página renderizada. Antes ela era montada com widgets
do Tk imitando o layout, e manter os dois em sincronia à mão custou uma
sequência de defeitos — rodapé que faltava num modelo, legenda que quebrava
em número diferente de linhas, imagem sobre o texto, cor de destaque que não
chegava. Sendo o próprio documento, não há o que divergir.
"""
import os
import tempfile
from datetime import datetime
from tkinter import Toplevel, messagebox, filedialog
import tkinter as tk

from PIL import Image, ImageTk

from gestor.dados import config
from gestor.exportacao import docx_export
from gestor.exportacao import pdf_export
from gestor.ui import theme
from gestor.ui import widgets

PAGINA_W, PAGINA_H = 480, 678  # tamanho de reserva, na proporção da A4

# Fração da altura da tela que a página ocupa. A janela abre maximizada, e a
# prévia agora é o documento de verdade: vale ocupar o espaço para dar pra ler.
_FRACAO_ALTURA = 0.72
# A4 tem 8,27 polegadas de largura. Renderiza no dobro do tamanho de exibição
# e reduz com LANCZOS, senão o texto sai serrilhado.
_SUPERAMOSTRAGEM = 2

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
        self._documento = None
        self._arquivo_previa = None
        self.total_paginas = 1

        self.title("Pré-visualização e exportação")
        self.state("zoomed")
        t = theme.get(parent_app.modo_escuro)
        self.configure(bg=t["bg_content"])

        try:
            self._gerar_previa()
        except Exception as e:
            # A tela continua útil sem a prévia: dá pra escolher pasta e
            # exportar. Sem isto, uma falha aqui fecharia a janela inteira.
            self._erro_previa = str(e)

        self._montar_ui(t)
        self.protocol("WM_DELETE_WINDOW", self.fechar)

    def fechar(self):
        self._fechar_documento()
        self.destroy()

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
        self.pagina_h = max(PAGINA_H, int(self.winfo_screenheight() * _FRACAO_ALTURA))
        self.pagina_w = int(round(self.pagina_h * pdf_export.PAGE_W / pdf_export.PAGE_H))
        self.moldura = tk.Frame(centro, bg="#ffffff",
                                width=self.pagina_w, height=self.pagina_h)
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
        if self.pagina_atual < self.total_paginas - 1:
            self.pagina_atual += 1
            self._render_pagina()

    # ---------- prévia: a página do documento de verdade ----------
    #
    # A prévia gera o PDF e mostra a página renderizada. Antes ela era montada
    # com widgets do Tk imitando o layout, e o preço disso era manter dois
    # layouts em sincronia na mão — rodapé, tamanho de imagem, quebra de
    # legenda e cor de destaque já divergiram, um de cada vez. Sendo o próprio
    # documento, não há o que divergir.

    def _gerar_previa(self):
        """Gera o documento num arquivo temporário e abre para leitura."""
        import pymupdf

        self._fechar_documento()
        destino = os.path.join(tempfile.gettempdir(),
                               "ge_previa_%d.pdf" % os.getpid())
        pdf_export.exportar(self.modelo, destino, self.capa, self.passos,
                            self.opcoes)
        self._arquivo_previa = destino
        self._documento = pymupdf.open(destino)
        self.total_paginas = self._documento.page_count
        if self.pagina_atual >= self.total_paginas:
            self.pagina_atual = max(0, self.total_paginas - 1)

    def _fechar_documento(self):
        doc = getattr(self, "_documento", None)
        if doc is not None:
            try:
                doc.close()
            except Exception:
                pass
        self._documento = None
        arquivo = getattr(self, "_arquivo_previa", None)
        if arquivo and os.path.exists(arquivo):
            try:
                os.remove(arquivo)
            except Exception:
                pass          # o Windows pode segurar o arquivo por um instante
        self._arquivo_previa = None

    def _render_pagina(self):
        for w in self.moldura.winfo_children():
            w.destroy()
        self.imagens_tk = []
        nomes = dict((valor, nome) for valor, nome, _ in _MODELOS_NOMES)
        self.lbl_pagina.config(
            text=f"Página {self.pagina_atual + 1} de {self.total_paginas} · "
                 f"modelo: {nomes.get(self.modelo, self.modelo)}")

        if self._documento is None:
            motivo = getattr(self, "_erro_previa", "")
            tk.Label(self.moldura, bg="#ffffff", fg="#8B1E1E",
                     wraplength=getattr(self, "pagina_w", PAGINA_W) - 40,
                     justify="left",
                     text="Não foi possível montar a prévia.\n\n"
                          + (motivo or "")
                          + "\n\nA exportação continua disponível ao lado.").pack(
                expand=True, padx=20)
            return

        img = self.imagem_da_pagina(self.pagina_atual)
        tk_img = ImageTk.PhotoImage(img)
        self.imagens_tk.append(tk_img)
        tk.Label(self.moldura, image=tk_img, bg="#ffffff",
                 borderwidth=0).pack(expand=True)

    def imagem_da_pagina(self, indice):
        """A página `indice` do documento, no tamanho em que é exibida."""
        largura = getattr(self, "pagina_w", PAGINA_W)
        altura = getattr(self, "pagina_h", PAGINA_H)
        dpi = int(round(_SUPERAMOSTRAGEM * largura / (pdf_export.PAGE_W / 25.4)))
        pix = self._documento[indice].get_pixmap(dpi=dpi)
        img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
        return img.resize((largura, altura), Image.LANCZOS)

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
        # a contagem vem do documento gerado, e não de uma estimativa
        tk.Label(rodape, text=f"{len(self.passos)} capturas · {self.total_paginas} páginas",
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
