*** Settings ***
Documentation     Integração com o Windows: Lixeira, menu Iniciar e pasta de dados.
...               Os arquivos criados aqui ficam na Lixeira de propósito — apagá-los
...               de lá exige a confirmação modal do Explorer, que trava um teste
...               sem ninguém para clicar.
Library           ../biblioteca/GestorEvidencias.py
Suite Teardown    Limpar arquivos temporários do teste
Test Tags         sistema


*** Test Cases ***
Excluir manda para a Lixeira, e não apaga de vez
    [Documentation]    Numa ferramenta de evidência, exclusão sem volta é perigosa.
    Mandar arquivos para a Lixeira    3

Apagar uma captura leva o png, o raw e o json juntos
    Executar cenário de tela    test_delete_capture

Acentos no PDF não derrubam a exportação
    Executar cenário de tela    test_pdf_acentos

O atalho do menu Iniciar aponta para este app
    Executar cenário de tela    test_menu_iniciar

Os dados ficam em %APPDATA% quando empacotado
    Executar cenário de tela    test_appdata

A Lixeira aceita nome com acento
    Executar cenário de tela    test_lixeira
