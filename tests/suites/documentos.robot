*** Settings ***
Documentation     Motores de geração do documento: PDF e DOCX nos três modelos.
...               Roda no mesmo processo — não envolve interface, então é rápido.
Library           ../biblioteca/GestorEvidencias.py
Library           OperatingSystem
Suite Teardown    Limpar arquivos temporários do teste
Test Tags         documentos


*** Variables ***
${URL LONGA}      https://portal.empresa.com.br/fechamento/validacao/competencia/2026/09/relatorio-consolidado-final
${CAMINHO LONGO}  C:\\Usuarios\\dasayani\\Documentos\\Evidencias\\Fechamento\\2026-09\\captura-da-tela.png


*** Test Cases ***
Passo a passo sai com a capa preenchida
    [Documentation]    Os campos da capa precisam aparecer no documento, não só na tela.
    ${pdf}=    Gerar documento do modelo    passo
    O documento deve conter o texto    ${pdf}    Validacao de fechamento
    O documento deve conter o texto    ${pdf}    CT-4471
    O documento deve conter o texto    ${pdf}    Homologacao

Ficha de evidência sai com a capa preenchida
    ${pdf}=    Gerar documento do modelo    ficha
    O documento deve conter o texto    ${pdf}    Validacao de fechamento
    O documento deve conter o texto    ${pdf}    QA - Dasayani

Relatório QA sai com o caso e o ambiente na lateral
    [Documentation]    O caso era preenchido na tela e não saía neste modelo.
    ${pdf}=    Gerar documento do modelo    qa
    O documento deve conter o texto    ${pdf}    CT-4471
    O documento deve conter o texto    ${pdf}    Homologacao

O rodapé é o mesmo nos três modelos
    [Documentation]    Cada modelo trazia uma frase diferente, o que confundia.
    FOR    ${modelo}    IN    passo    ficha    qa
        ${pdf}=    Gerar documento do modelo    ${modelo}
        O documento deve conter o texto    ${pdf}    Gestor de Evidências
    END

Legenda comprida quebra dentro do cartão da Ficha
    [Documentation]    Uma URL ou um caminho de arquivo não tem espaço para quebrar,
    ...                e saía para fora do documento numa linha só.
    A legenda deve caber na largura do cartão da Ficha    ${URL LONGA}
    A legenda deve caber na largura do cartão da Ficha    ${CAMINHO LONGO}
    A legenda deve caber na largura do cartão da Ficha
    ...    validacaodofechamentocomsaldodisponivelelogdeauditoriaregistrado

Legenda colada do Word não derruba a geração
    [Documentation]    Travessão, aspas curvas e reticências não cabem em latin-1,
    ...                que é o que o fpdf grava.
    ${legenda}=    Set Variable
    ...    Ao clicar em “Confirmar” — na tela de fechamento — o sistema valida o saldo…
    ${pdf}=    Gerar documento do modelo    ficha    legenda=${legenda}
    O documento deve conter o texto    ${pdf}    "Confirmar" - na tela

A cor de destaque muda os três modelos
    [Documentation]    No relatório QA a faixa lateral era fixa e a escolha não
    ...                mudava nada visível.
    FOR    ${modelo}    IN    passo    ficha    qa
        Trocar a cor de destaque deve mudar o modelo    ${modelo}
    END

DOCX sai nos três modelos
    FOR    ${modelo}    IN    passo    ficha    qa
        ${docx}=    Gerar DOCX do modelo    ${modelo}
        Should Exist    ${docx}
    END
