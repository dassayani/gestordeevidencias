# Testes do Gestor de Evidências

## Como rodar

```bat
tests\executar.bat                  :: tudo, e abre o relatório no fim
tests\executar.bat documentos       :: só uma suíte (documentos, telas, sistema)
tests\executar.bat -i regressao      :: só os casos marcados como regressão
```

O relatório sai em `tests\_saida\relatorio\report.html`, com `log.html` ao lado
trazendo a saída completa de cada cenário.

Um cenário isolado também roda sozinho, sem o Robot:

```bat
venv\Scripts\python.exe tests\python\cenario_editor.py
```

Antes da primeira execução:

```bat
venv\Scripts\python.exe -m pip install -r tests\requirements-dev.txt
```

## Como está organizado

| Pasta | O que tem |
|---|---|
| `suites/` | os casos em Robot, em português, agrupados por área |
| `biblioteca/` | as palavras-chave (Python) que os casos usam |
| `python/` | os cenários; cada um roda sozinho e imprime `FALHAS:` no fim |
| `ferramentas/` | utilitários de conferência visual, não são testes |
| `_saida/` | relatórios e arquivos gerados durante a execução |

As suítes:

- **documentos** — geração de PDF e DOCX nos três modelos, conteúdo, quebra de
  legenda, cor de destaque. Roda no mesmo processo: é rápido.
- **telas** — Configurações, área de trabalho, editor, montar documento, seleção
  de área e atalho com o painel escondido.
- **sistema** — Lixeira, menu Iniciar, pasta de dados em `%APPDATA%`.

São 39 casos ao todo.

## Ao escrever um cenário novo

Sete regras que saíram de defeitos reais desta suíte, e não de preferência:

1. **Crie a própria pasta temporária de capturas.** Três cenários abriam o app
   sobre a pasta real da máquina; o do editor chegava a gravar legenda nas
   evidências de verdade. Além disso, um deles dependia de haver captura *do
   dia* — o filtro inicial do painel é "Hoje" — e falhou sozinho quando virou
   a meia-noite.
2. **Encerre o ícone da bandeja antes de sair** (`app.icon.stop()`). Ele roda um
   laço de mensagens nativo numa thread própria; terminar o processo com ela em
   pleno voo derrubava o cenário, às vezes antes de imprimir a primeira linha.
3. **Espere pela condição, nunca por tempo fixo.** O overlay da captura nasce de
   um `after` e precisa ser realizado pelo Tk; `sleep(0.5)` fazia o cenário
   falhar numa máquina ocupada, sem defeito algum no app. O mesmo vale para a
   área de transferência, que pertence ao Windows inteiro e pode estar com
   outro programa no exato instante do teste.
4. **Termine imprimindo `FALHAS:`**, com `nenhuma` ou a lista. É esse contrato
   que a palavra-chave `Executar cenário de tela` lê — e ela também relata o
   código de saída do processo, que foi o que permitiu descobrir que os
   "resultados vazios" eram, na verdade, o processo morrendo.
5. **Evento de mouse sintético precisa de horário.** `event_generate` sem
   `time=` não carrega horário, e o Tk decide "duplo clique" comparando
   horários: todo clique no mesmo ponto passava a contar como duplo, por mais que
   o teste esperasse entre eles — um arraste logo depois de um clique abria o
   editor. Os cenários de gesto usam um relógio virtual que avança entre os
   gestos, e passam coordenadas de tela absolutas (`rootx`/`rooty`), porque o
   widget que recebeu o clique pode sair do layout durante o arraste.
6. **Confira a ordem exibida, não a de criação.** Os cartões trocam de lugar sem
   ser recriados, então `winfo_children()` (ordem de criação) deixou de dizer o
   que está na tela; use `pack_slaves()` ou a lista de cartões do próprio Montar.
7. **Um teste que só passa não prova nada: faça-o falhar.** Desfaça a correção
   que o teste diz cobrir (numa cópia do repositório) e confira que ele falha.
   Foi assim que apareceram testes que concordavam com qualquer valor errado —
   por exemplo, um que calculava o alvo do ponteiro com os mesmos números que o
   código tinha calculado — e um que passava mesmo sem o campo `captured_at`
   gravado, porque o nome e o mtime davam quase a mesma hora.

## Por que os cenários de tela rodam em processos separados

O Tkinter guarda estado global do interpretador (a raiz, as fontes, as imagens).
Criar e destruir várias raízes no mesmo processo deixa o resultado instável, com
falhas que mudam de lugar a cada execução. Por isso a palavra-chave
`Executar cenário de tela` dispara um processo por cenário e lê o resultado da
saída dele.

## Por que não há clique em botão por nome

As ferramentas usuais de automação de desktop (FlaUI, RPA.Windows,
WinAppDriver, AutoIt e as bibliotecas de desktop do Robot) conversam com a
aplicação pelo UI Automation do Windows. O Tkinter **não expõe os próprios
widgets** por ali: `tests/ferramentas/sonda_uia.py` abre uma janela Tk com
rótulo, campo, botão e checkbox, e o UIA devolve caixas anônimas, sem nenhum
dos textos — só a moldura da janela tem nome.

Um localizador como `Click Button    Confirmar` não teria como encontrar nada, e
sobraria clicar em coordenada fixa, que quebra assim que o tamanho da fonte
muda (e o app deixa isso configurável). Por isso os cenários acionam o app pelo
código e conferem o widget real: é o que pega defeito de verdade, como os desta
lista.

## Defeitos que esta suíte já pegou

| Cenário | O que estava errado |
|---|---|
| `test_tema_lista` | trocar o tema esvaziava a lista nas visualizações em blocos e grade |
| `test_reordenar_miniaturas` | arrastar um passo apagava as miniaturas dos outros |
| `cenario_editor` | abrir um print legendado já marcava "alterações não gravadas" |
| `cenario_documento` | reordenar a sequência apagava a capa inteira (título, caso, autor, ambiente) |
| `test_titulo_por_modelo` / `cenario_titulo_por_modelo` | trocar de modelo desfazia o título que o usuário escreveu, ou deixava o título do modelo anterior |
| `test_legenda_ficha` | legenda sem espaços (URL, caminho) saía para fora do cartão |
| `cenario_area_capturada` | recorte deslocado no monitor em 150% |
| `cenario_area_trabalho` | a busca não alcançava o campo Caso/Projeto |
| `cenario_editar_do_documento` | voltar do editor trazia o painel principal por cima; a legenda digitada no Montar se perdia ao gravar |
| `cenario_duplo_clique_documento` | uma tremida entre os cliques virava arraste; imagem corrompida deixava uma janela vazia na tela |
| `cenario_arraste_sequencia` / `test_reordenar` | arraste sem mostrar o destino, sem rolagem automática e com o item saindo fora do ponto indicado; soltar travava a tela por segundos |
| `test_gravacao_atomica` | falha no meio da gravação deixava `.tmp` e o editor fechava como se tivesse gravado |
| `cenario_timer_e_previas` | o painel se escondia com o Montar aberto; a pausa do timer não tinha efeito; duas prévias disputavam o mesmo arquivo |
| `test_ordem_capturas` / `cenario_ordem_documento` | o último print virava o passo 1; ordenar por modificação jogaria para o fim o print editado; o texto "ordem manual" aparecia cortado |

## O que ainda depende de teste manual

O Print Screen de verdade, com o executável empacotado. Tecla sintetizada dá
falso negativo: o Windows só entrega `WM_HOTKEY` para entrada real de teclado,
e isso já levou a diagnóstico errado. O cenário
`cenario_printscreen_oculto` cobre o resto do caminho — o registro do atalho e o
seletor aparecendo com o painel escondido, que é onde o defeito estava.

Também vale uma passada com o **mouse de verdade** depois de mexer em gesto
(arrastar, duplo clique): o evento sintético do Tk não reproduz a cadeia de
foco e de cruzamento de janelas que o Windows gera. O duplo clique na miniatura
passava em todos os cenários e falhava uma vez em cada duas com o mouse real,
porque o primeiro clique movia o foco. Dá para conferir com `SetCursorPos` e
`mouse_event` (user32), que injetam entrada real — mas o cursor da máquina se
mexe sozinho enquanto roda, então não entra na suíte automática.
