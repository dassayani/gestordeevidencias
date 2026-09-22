*** Settings ***
Documentation     Cenários de interface. Cada um roda num processo próprio, porque
...               o Tkinter guarda estado global e várias raízes no mesmo processo
...               deixam o resultado instável.
...
...               Nenhum cenário clica em botão por nome: o Tkinter não expõe os
...               widgets ao UI Automation do Windows (tests/ferramentas/sonda_uia.py
...               mostra isso), então o app é acionado pelo próprio código e a
...               verificação é feita no widget real.
Library           ../biblioteca/GestorEvidencias.py
Test Tags         telas


*** Test Cases ***
Configurações espelham o que está gravado
    [Documentation]    Cada opção da tela precisa mostrar o valor do config, e o
    ...                que muda na tela precisa voltar para o disco.
    Executar cenário de tela    cenario_configuracoes

Área de trabalho responde a todos os comandos
    [Documentation]    Selecionar tudo, limpar seleção, as três visualizações, a
    ...                troca de tema, o botão de captura e limpar a pasta.
    Executar cenário de tela    cenario_area_trabalho

Trocar o tema não pode esvaziar a lista de capturas
    [Documentation]    Nas visualizações em blocos e grade as capturas sumiam até
    ...                alguém clicar num filtro.
    [Tags]    regressao
    Executar cenário de tela    test_tema_lista

As três visualizações montam a lista
    Executar cenário de tela    test_visoes

Editor desenha, grava, apaga e reabre com tudo no lugar
    [Documentation]    Todas as ferramentas, legenda, caso/projeto, Gravar,
    ...                Gravar e fechar, e exclusão de anotação.
    Executar cenário de tela    cenario_editor

O editor já abre marcado como gravado
    [Documentation]    Abrir um print que já tem legenda marcava alteração
    ...                pendente, e fechar sempre perguntava se era pra sair sem
    ...                gravar.
    [Tags]    regressao
    Executar cenário de tela    test_editor

Documento: campos, sequência, prévia e geração nos três modelos
    [Documentation]    Vários prints, capa inteira preenchida, legendas por passo,
    ...                reordenação, PDF e DOCX nos três modelos, conteúdo conferido
    ...                contra o que foi configurado, e a prévia seguindo aberta
    ...                depois de gerar.
    Executar cenário de tela    cenario_documento    tempo_limite=240

Reordenar os passos mantém as miniaturas na tela
    [Documentation]    Pelo arraste as miniaturas dos passos sumiam; pelas setas não.
    [Tags]    regressao
    Executar cenário de tela    test_reordenar_miniaturas

Reordenar coloca os passos na posição certa
    Executar cenário de tela    test_reordenar

Ctrl+C e Ctrl+V funcionam nos campos do editor
    [Tags]    regressao
    Executar cenário de tela    test_atalhos_campos

Ctrl+C copia a captura selecionada no painel
    Executar cenário de tela    test_atalhos_imagem

Tamanho de fonte e pastas padrão
    [Documentation]    A escala vale no texto e na altura do controle, e os
    ...                documentos vão para PDF/ e DOCX/ dentro da pasta de capturas.
    Executar cenário de tela    test_pastas_fonte

Selecionar uma área salva o arquivo com o tamanho certo
    [Documentation]    Caminho inteiro da captura: abrir o seletor, arrastar,
    ...                soltar e conferir o arquivo. Cobre também Escape e
    ...                arrasto mínimo demais.
    [Tags]    regressao
    Executar cenário de tela    cenario_captura_area

A captura traz exatamente a área pedida
    [Documentation]    Alvo colorido em posição conhecida, conferido canto a canto,
    ...                nos dois monitores — inclusive o que está em 150%, onde o
    ...                recorte já saiu deslocado por diferença de DPI.
    [Tags]    regressao
    Executar cenário de tela    cenario_area_capturada

O atalho de captura funciona com o painel escondido
    [Documentation]    Com a janela principal escondida o seletor não era realizado
    ...                pelo Tk e nunca aparecia. A tecla não é sintetizada: contra o
    ...                executável isso dá falso negativo.
    [Tags]    regressao
    Executar cenário de tela    cenario_printscreen_oculto
