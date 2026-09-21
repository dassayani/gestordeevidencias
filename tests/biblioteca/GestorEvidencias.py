# -*- coding: utf-8 -*-
"""Palavras-chave do Gestor de Evidências para o Robot Framework.

Duas famílias, e a divisão tem motivo técnico:

* **Motores** (PDF, DOCX, Lixeira, quebra de legenda) rodam dentro deste mesmo
  processo. Não envolvem interface, então são rápidos e determinísticos.
* **Telas** rodam num processo separado, um por cenário. O Tkinter guarda
  estado global do interpretador (a raiz, as fontes, as imagens), e criar e
  destruir várias raízes no mesmo processo deixa o resultado instável — foi o
  que levou a isolar cada cenário quando esta suíte era só um lote de scripts.

Não há palavra-chave que clique em botão por nome: o Tkinter não expõe os
próprios widgets ao UI Automation do Windows (veja tests/ferramentas/sonda_uia.py),
então o caminho confiável é acionar o app pelo código e conferir o widget real.
"""
import os
import shutil
import subprocess
import sys
import tempfile

from robot.api import logger
from robot.api.deco import keyword, library

RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if RAIZ not in sys.path:
    sys.path.insert(0, RAIZ)

CENARIOS = os.path.join(RAIZ, "tests", "python")
SAIDA = os.path.join(RAIZ, "tests", "_saida")

LEGENDA_LONGA = ("Ao clicar no botao Confirmar da tela de fechamento, o sistema deve "
                 "validar o saldo disponivel, conferir a data de competencia, registrar "
                 "o log de auditoria e so entao apresentar a mensagem de sucesso ao "
                 "usuario, mantendo o botao desabilitado durante o processamento.")
CAPA = {"titulo": "Validacao de fechamento", "caso": "CT-4471",
        "autor": "QA - Dasayani", "data": "21/09/2026", "ambiente": "Homologacao"}


@library(scope="SUITE")
class GestorEvidencias:
    """Biblioteca de teste do Gestor de Evidências."""

    def __init__(self):
        self._temporarias = []
        os.makedirs(SAIDA, exist_ok=True)

    # ------------------------------------------------------------------ apoio

    def _pasta(self):
        caminho = tempfile.mkdtemp(prefix="ge_robot_")
        self._temporarias.append(caminho)
        return caminho

    def _amostra(self, pasta, nome="captura.png"):
        from PIL import Image, ImageDraw
        caminho = os.path.join(pasta, nome)
        img = Image.new("RGB", (1000, 640), (246, 249, 251))
        d = ImageDraw.Draw(img)
        d.rectangle([0, 0, 999, 639], outline=(30, 90, 120), width=5)
        for i in range(4):
            d.rectangle([40, 40 + i * 140, 960, 150 + i * 140],
                        outline=(120, 140, 160), width=3)
        img.save(caminho)
        return caminho

    # ------------------------------------------------------------- documentos

    @keyword("Gerar documento do modelo")
    def gerar_documento(self, modelo, legenda=LEGENDA_LONGA, cor="#0B7285",
                        borda=False, passos=2):
        """Gera o PDF de `modelo` (passo, ficha ou qa) e devolve o caminho."""
        import pdf_export
        geradores = {"passo": pdf_export.exportar_passo_a_passo,
                     "ficha": pdf_export.exportar_ficha_evidencia,
                     "qa": pdf_export.exportar_relatorio_qa}
        if modelo not in geradores:
            raise AssertionError("modelo desconhecido: %s" % modelo)
        pasta = self._pasta()
        amostra = self._amostra(pasta)
        lista = [{"caminho": amostra, "legenda": legenda}]
        lista += [{"caminho": amostra, "legenda": "Passo %d" % (i + 2)}
                  for i in range(int(passos) - 1)]
        opcoes = {"cor_destaque": cor, "borda_cor": cor,
                  "borda_ativada": str(borda).lower() in ("true", "sim", "1"),
                  "numerar_passos": True, "fonte_legenda": "Arial"}
        destino = os.path.join(pasta, "%s.pdf" % modelo)
        geradores[modelo](destino, CAPA, lista, opcoes)
        logger.info("documento gerado: %s" % destino)
        return destino

    @keyword("Gerar DOCX do modelo")
    def gerar_docx(self, modelo, legenda=LEGENDA_LONGA, cor="#0B7285"):
        """Gera o DOCX de `modelo` e devolve o caminho."""
        import docx_export
        geradores = {"passo": docx_export.exportar_passo_a_passo,
                     "ficha": docx_export.exportar_ficha_evidencia,
                     "qa": docx_export.exportar_relatorio_qa}
        pasta = self._pasta()
        amostra = self._amostra(pasta)
        passos = [{"caminho": amostra, "legenda": legenda}]
        opcoes = {"cor_destaque": cor, "borda_cor": cor, "borda_ativada": False,
                  "numerar_passos": True, "fonte_legenda": "Arial"}
        destino = os.path.join(pasta, "%s.docx" % modelo)
        geradores[modelo](destino, CAPA, passos, opcoes)
        return destino

    @keyword("O documento deve conter o texto")
    def documento_contem(self, caminho, texto):
        """Lê o texto do PDF e confere que `texto` aparece nele."""
        import pymupdf
        with pymupdf.open(caminho) as doc:
            conteudo = "\n".join(pagina.get_text() for pagina in doc)
        if texto not in conteudo:
            raise AssertionError("o documento não contém %r.\nTexto lido:\n%s"
                                 % (texto, conteudo[:600]))
        logger.info("encontrado no documento: %r" % texto)

    @keyword("O documento deve ter")
    def documento_paginas(self, caminho, paginas):
        """Confere o número de páginas do PDF."""
        import pymupdf
        with pymupdf.open(caminho) as doc:
            total = doc.page_count
        if total != int(paginas):
            raise AssertionError("esperava %s página(s), o documento tem %d"
                                 % (paginas, total))

    @keyword("A legenda deve caber na largura do cartão da Ficha")
    def legenda_cabe(self, legenda):
        """Nenhuma linha da legenda pode passar da área útil do cartão.

        É o defeito que fazia uma URL ou um caminho de arquivo sair para fora
        do documento: a quebra só acontecia em espaços.
        """
        import pdf_export
        largura = pdf_export.PAGE_W - 2 * pdf_export.MARGEM - 28
        pdf = pdf_export.FPDF(format="A4", unit="mm")
        pdf.add_page()
        pdf.set_font("Arial", "B", 11)
        linhas = pdf_export._quebrar(pdf, legenda, largura)
        estouros = [(l, pdf.get_string_width(l)) for l in linhas
                    if pdf.get_string_width(l) > largura + 0.5]
        logger.info("a legenda ocupou %d linha(s) em %.1f mm" % (len(linhas), largura))
        if estouros:
            raise AssertionError(
                "linha(s) fora da área de %.1f mm: %s"
                % (largura, ", ".join("%.1f mm em %r" % (w, l[:40]) for l, w in estouros)))

    @keyword("Trocar a cor de destaque deve mudar o modelo")
    def cor_muda_modelo(self, modelo):
        """Gera o mesmo documento em duas cores e exige que saiam diferentes.

        Vale para a página inteira, renderizada em imagem: é assim que se
        percebe que a cor não estava chegando na faixa lateral do relatório QA.
        """
        import pymupdf
        um = self.gerar_documento(modelo, cor="#0B7285")
        outro = self.gerar_documento(modelo, cor="#E8590C")
        imagens = []
        for caminho in (um, outro):
            with pymupdf.open(caminho) as doc:
                imagens.append(doc[0].get_pixmap(dpi=60).tobytes("png"))
        if imagens[0] == imagens[1]:
            raise AssertionError(
                "o modelo %s saiu idêntico nas duas cores — a cor de destaque "
                "não está chegando nele" % modelo)
        logger.info("o modelo %s responde à cor de destaque" % modelo)

    # ------------------------------------------------------------------ lixeira

    @keyword("Mandar arquivos para a Lixeira")
    def mandar_para_lixeira(self, quantidade=3):
        """Cria arquivos, manda para a Lixeira e confere que saíram da pasta."""
        import utils
        pasta = self._pasta()
        criados = []
        for i in range(int(quantidade)):
            caminho = os.path.join(pasta, "evidencia_%d.txt" % i)
            with open(caminho, "w", encoding="utf-8") as f:
                f.write("conteudo")
            criados.append(caminho)
        # um com acento, que é onde a API costuma tropeçar
        acento = os.path.join(pasta, "evidência_ação.txt")
        with open(acento, "w", encoding="utf-8") as f:
            f.write("ção")
        criados.append(acento)

        if not utils.mover_para_lixeira(criados):
            raise AssertionError("mover_para_lixeira devolveu False")
        restantes = [c for c in criados if os.path.exists(c)]
        if restantes:
            raise AssertionError("%d arquivo(s) não saíram da pasta" % len(restantes))
        logger.info("%d arquivo(s) foram para a Lixeira" % len(criados))

    # -------------------------------------------------------------------- telas

    @keyword("Executar cenário de tela")
    def cenario_de_tela(self, nome, tempo_limite=150):
        """Roda `tests/python/<nome>.py` num processo próprio e exige sucesso.

        O cenário imprime "FALHAS: nenhuma" quando passa; qualquer linha depois
        de FALHAS vira a mensagem de erro aqui.
        """
        script = os.path.join(CENARIOS, "%s.py" % nome)
        if not os.path.exists(script):
            raise AssertionError("cenário não encontrado: %s" % script)
        proc = subprocess.run([sys.executable, "-u", script], capture_output=True,
                              text=True, encoding="utf-8", errors="replace",
                              timeout=float(tempo_limite), cwd=RAIZ)
        saida = (proc.stdout or "") + (proc.stderr or "")
        logger.info("<pre>%s</pre>" % saida.replace("<", "&lt;"), html=True)
        if "FALHAS: nenhuma" in saida:
            return
        if "FALHAS:" in saida:
            detalhe = saida.split("FALHAS:", 1)[1].strip()
            raise AssertionError("o cenário %s falhou:\n%s" % (nome, detalhe or "(sem detalhe)"))
        raise AssertionError(
            "o cenário %s não relatou resultado (codigo de saida %s).\nSaída:\n%s"
            % (nome, proc.returncode, saida[-800:] or "(vazia)"))

    # ------------------------------------------------------------------ limpeza

    @keyword("Limpar arquivos temporários do teste")
    def limpar(self):
        for caminho in self._temporarias:
            shutil.rmtree(caminho, ignore_errors=True)
        self._temporarias = []
