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

São 29 casos ao todo.

## Ao escrever um cenário novo

Quatro regras que saíram de defeitos reais desta suíte, e não de preferência:

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
| `test_legenda_ficha` | legenda sem espaços (URL, caminho) saía para fora do cartão |
| `cenario_area_capturada` | recorte deslocado no monitor em 150% |
| `cenario_area_trabalho` | a busca não alcançava o campo Caso/Projeto |

## O que ainda depende de teste manual

O Print Screen de verdade, com o executável empacotado. Tecla sintetizada dá
falso negativo: o Windows só entrega `WM_HOTKEY` para entrada real de teclado,
e isso já levou a diagnóstico errado. O cenário
`cenario_printscreen_oculto` cobre o resto do caminho — o registro do atalho e o
seletor aparecendo com o painel escondido, que é onde o defeito estava.
