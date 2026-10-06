# -*- coding: utf-8 -*-
"""Protecao de dados com o app de verdade.

Complementa test_protecao_dados (sem janela) nos caminhos que passam pela
interface:
  * uma captura com o mesmo nome de outra (padrao `hora`) nao a sobrescreve
  * "Limpar pasta" leva so as capturas, e nao outros arquivos da pasta
  * pasta de capturas indisponivel: o usuario e avisado, e nao fica sem saber
    que as capturas foram para outro lugar
  * exportar com uma imagem faltando avisa quais passos ficaram sem imagem
  * a galeria nao decodifica os PNG de novo a cada atualizacao
"""

import os as _os
import sys as _sys

RAIZ = _os.path.dirname(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
_sys.path.insert(0, RAIZ)
_os.chdir(RAIZ)

import os, sys, ctypes, tempfile, shutil, traceback, hashlib

if not ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4)):
    ctypes.windll.shcore.SetProcessDpiAwareness(2)

import PIL.ImageFile
from tkinterdnd2 import TkinterDnD
from PIL import Image
from gestor.captura import captura_utils
from gestor.dados import capture_store, config
from gestor.ui import document_builder, export_preview, workspace
from gestor.ui.workspace import AppEvidencias

falhas = []
avisos = []
erros_tk = []


def checar(condicao, descricao):
    print(("OK:     " if condicao else "FALHOU: ") + descricao)
    if not condicao:
        falhas.append(descricao)


class DialogoFalso:
    @staticmethod
    def showinfo(titulo, mensagem, **kw):
        avisos.append(("info", titulo, mensagem))

    @staticmethod
    def showerror(titulo, mensagem, **kw):
        avisos.append(("erro", titulo, mensagem))

    @staticmethod
    def showwarning(titulo, mensagem, **kw):
        avisos.append(("aviso", titulo, mensagem))

    @staticmethod
    def askyesno(titulo, mensagem, **kw):
        avisos.append(("pergunta", titulo, mensagem))
        return True


workspace.messagebox = DialogoFalso
document_builder.messagebox = DialogoFalso
export_preview.messagebox = DialogoFalso
export_preview.os.startfile = lambda caminho: None


def hash_arquivo(caminho):
    with open(caminho, "rb") as f:
        return hashlib.md5(f.read()).hexdigest()


tmp = tempfile.mkdtemp(prefix="ge_protecao_app_")
capturas = os.path.join(tmp, "Capturas")
os.makedirs(capturas)
cfg = config.load(tmp)
cfg["pasta_capturas"] = capturas
cfg["copiar_apos_captura"] = False
cfg["som_captura"] = False
cfg["abrir_apos_captura"] = False
config.save(tmp, cfg)

root = TkinterDnD.Tk()
root.report_callback_exception = lambda *a: erros_tk.append(a)
app = AppEvidencias(root, capturas, os.path.join(tmp, "PDF"), RAIZ, tmp)
app.pausar_timer = True
root.deiconify()
root.update()

try:
    # ================= captura com nome repetido =================
    antiga = os.path.join(capturas, "print_143052.png")
    Image.new("RGB", (300, 200), (0, 0, 255)).save(antiga)
    capture_store.save_meta(antiga, {"caption": "Evidencia de ontem", "caso": "CT-1",
                                     "shapes": [{"id": 1, "tool": "seta", "coords": [1, 1, 50, 50],
                                                 "color": "#E8590C", "width": 3, "dash": False,
                                                 "visible": True}]})
    capture_store.load_meta(antiga)                        # cria o .raw.png da antiga
    png_antes = hash_arquivo(antiga)
    raw_antes = hash_arquivo(capture_store.raw_path(antiga))
    padrao_original = captura_utils.PADROES_NOME["hora"]
    # forca o mesmo HHMMSS: e o que acontece com prints de dias diferentes
    captura_utils.PADROES_NOME["hora"] = lambda dt, sufixo: "print_143052%s.png" % sufixo
    try:
        app._salvar_captura(Image.new("RGB", (300, 200), (255, 0, 0)))
    finally:
        captura_utils.PADROES_NOME["hora"] = padrao_original
    root.update()
    nova = os.path.join(capturas, "print_143052_2.png")
    checar(hash_arquivo(antiga) == png_antes, "a captura antiga com o mesmo nome NAO foi sobrescrita")
    checar(hash_arquivo(capture_store.raw_path(antiga)) == raw_antes,
           "nem o original (.raw.png) dela")
    meta_antiga = capture_store.load_meta(antiga)
    checar(meta_antiga["caption"] == "Evidencia de ontem" and len(meta_antiga["shapes"]) == 1,
           "e a legenda e as anotacoes dela continuam")
    checar(os.path.exists(nova), "a captura nova foi salva com sufixo (print_143052_2.png)")
    if os.path.exists(nova):
        checar(capture_store.load_raw_image(nova).convert("RGB").getpixel((5, 5)) == (255, 0, 0),
               "e no editor ela abre a propria imagem, nao a da antiga")
        checar(capture_store.load_meta(nova)["shapes"] == [] and
               capture_store.load_meta(nova)["caption"] == "",
               "sem herdar a legenda e as anotacoes da antiga")

    # ================= a galeria usa o cache =================
    for i in range(6):
        Image.new("RGB", (1600, 900), (20 * i, 80, 120)).save(
            os.path.join(capturas, "print_15000%d.png" % i))
    app.filtro_atual = "tudo"
    app.atualizar_galeria()
    root.update()
    decodificados = []
    original_load = PIL.ImageFile.ImageFile.load

    def load_contado(self, *a, **k):
        decodificados.append(getattr(self, "filename", ""))
        return original_load(self, *a, **k)

    PIL.ImageFile.ImageFile.load = load_contado
    try:
        app.atualizar_galeria()
        root.update()
    finally:
        PIL.ImageFile.ImageFile.load = original_load
    checar(not [d for d in decodificados if str(d).lower().endswith(".png")],
           "atualizar a galeria de novo nao decodifica nenhum PNG (%d decodificacoes)"
           % len(decodificados))

    # ================= exportar com uma imagem faltando =================
    nomes = ["print_150000.png", "print_150001.png", "print_150002.png"]
    janela = document_builder.MontarDocumento(app, nomes)
    janela.update()
    os.remove(os.path.join(capturas, "print_150001.png"))     # some depois de montar
    janela._pre_visualizar()
    root.update()
    previa = next((w for w in root.winfo_children()
                   if isinstance(w, export_preview.PreVisualizarExportar)), None)
    checar(previa is not None, "a previa abre mesmo com a imagem faltando")
    if previa is not None:
        destino = os.path.join(tmp, "saida")
        os.makedirs(destino)
        for formato in ("pdf", "docx"):
            previa.var_formato.set(formato)
            previa._entry_destino.config(state="normal")
            previa._entry_destino.delete(0, "end")
            previa._entry_destino.insert(0, destino)
            antes = len(avisos)
            previa._exportar()
            root.update()
            novos = avisos[antes:]
            checar(any(a[0] == "aviso" and "print_150001.png" in a[2] and "SEM IMAGEM" in a[2]
                       for a in novos),
                   "[%s] exportar avisa qual passo ficou sem imagem" % formato)
            checar(not any(a[0] == "info" for a in novos),
                   "[%s] e nao diz apenas 'documento gerado'" % formato)
        previa.fechar()
        root.update()
    janela.destroy()
    root.update()

    # ================= Limpar pasta leva so as capturas =================
    with open(os.path.join(capturas, "planilha_do_teste.xlsx"), "wb") as f:
        f.write(b"conteudo do usuario")
    with open(os.path.join(capturas, "anotacoes.txt"), "w") as f:
        f.write("nao e de captura nenhuma")
    with open(capture_store.txt_path(os.path.join(capturas, "print_150000.png")), "w") as f:
        f.write("legenda antiga")                          # .txt irmao: e da captura
    enviados = []
    original_lixeira = workspace.utils.mover_para_lixeira
    workspace.utils.mover_para_lixeira = lambda alvos: (enviados.extend(alvos), True)[1]
    try:
        app.limpar_pasta_completa()
    finally:
        workspace.utils.mover_para_lixeira = original_lixeira
    root.update()
    nomes_enviados = sorted(os.path.basename(p) for p in enviados)
    checar("planilha_do_teste.xlsx" not in nomes_enviados and "anotacoes.txt" not in nomes_enviados,
           "Limpar pasta nao leva arquivos que nao sao capturas (%s)" % nomes_enviados[:4])
    checar("print_143052.png" in nomes_enviados and "print_143052.raw.png" in nomes_enviados
           and "print_143052.json" in nomes_enviados,
           "mas leva cada captura com o original e os metadados")
    checar("print_150000.txt" in nomes_enviados, "e o .txt de legenda antiga de uma captura")

    # ================= pasta indisponivel =================
    livre = next(letra for letra in "QRSTUVWXYZ" if not os.path.exists("%s:\\" % letra))
    inacessivel = "%s:\\Evidencias\\Projeto" % livre
    app.config["pasta_capturas"] = inacessivel
    resolvida = app._resolver_pasta_capturas()
    checar(resolvida == app.pasta_capturas_padrao and app.pasta_indisponivel == inacessivel,
           "pasta configurada inacessivel: usa a padrao e anota qual era")
    app.pasta_capturas = resolvida
    antes = len(avisos)
    app._avisar_pasta_indisponivel()
    novos = avisos[antes:]
    checar(any(a[0] == "aviso" and inacessivel in a[2] and resolvida in a[2] for a in novos),
           "e avisa as duas: a que nao esta acessivel e para onde as capturas vao")
    app.config["pasta_capturas"] = capturas
    app.pasta_capturas = app._resolver_pasta_capturas()
    checar(app.pasta_indisponivel is None, "com a pasta de volta, nao ha o que avisar")
    antes = len(avisos)
    app._avisar_pasta_indisponivel()
    checar(len(avisos) == antes, "e o aviso nao aparece")

    checar(not [a for a in avisos if a[0] == "erro"], "nenhuma mensagem de erro")
    checar(not erros_tk, "nenhum erro silencioso do Tk")
    for e in erros_tk:
        print("   erro Tk:", "".join(traceback.format_exception(*e))[-500:])
except Exception:
    falhas.append("erro: " + traceback.format_exc())

print("\nFALHAS:", "nenhuma" if not falhas else "")
for f in falhas:
    print(" -", f)
try:
    try:
        app.icon.stop()
    except Exception:
        pass
    root.destroy()
except Exception:
    pass
shutil.rmtree(tmp, ignore_errors=True)
sys.stdout.flush()
os._exit(1 if falhas else 0)
