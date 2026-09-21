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
- **telas** — Configurações, área de trabalho, editor, montar documento, captura
  e atalho com o painel escondido.
- **sistema** — Lixeira, menu Iniciar, pasta de dados em `%APPDATA%`.

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

## O que ainda depende de teste manual

O Print Screen de verdade, com o executável empacotado. Tecla sintetizada dá
falso negativo: o Windows só entrega `WM_HOTKEY` para entrada real de teclado,
e isso já levou a diagnóstico errado. O cenário
`cenario_printscreen_oculto` cobre o resto do caminho — o registro do atalho e o
seletor aparecendo com o painel escondido, que é onde o defeito estava.
