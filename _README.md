Table of contents
=================

<!--ts-->
   * [PT]
   * [Introdução](#Introdução)
      * [O que são fontes de dados?](#O-que-são-fontes-de-dados?)
      * [De que maneira posso categorizar as transações?](#De-que-maneira-posso-categorizar-as-transações?)
      * [O que são repositórios de dados?](#O-que-são-repositórios-de-dados?)
      * [O que posso fazer com este fluxo de dados?](#O-que-posso-fazer-com-este-fluxo-de-dados?)
   * [Como posso utilizar?](#Como-posso-utilizar?)
      * [Remote files](#remote-files)
      * [Multiple files](#multiple-files)
      * [Combo](#combo)
      * [Auto insert and update TOC](#auto-insert-and-update-toc)
      * [GitHub token](#github-token)
<!--te-->


# Introdução

Com esta shell, consegues configurar fontes de dados das quais obténs as tuas transações - sejam elas despesas
ou rendimentos - para que as possas categorizar e guardá-las em diferentes repositórios de dados.

## O que são fontes de dados?

Neste contexto, fontes de dados das quais obténs as tuas transações podem ser:
- Um ficheiro csv, que exportaste da app do teu banco
- O próprio site do teu banco, para que possas obter diretamente as transações
- Uma base de dados onde tenhas as tuas transações já guardadas

Isto permite obter as transações para que as possas enriquecer com categorias nesta aplicação.

Neste momento, as fontes de dados implementadas são:
- ActivoBank - cartão conta à ordem
- ActivoBank - cartão pré-pago
- MyEdenred

## De que maneira posso categorizar as transações?

A aplicação considera sempre que uma dada transação pode ser de dois tipos:
- Despesa
- Rendimento

Para além do tipo de transação, tu podes também associar uma transação a uma categoria.

Dado que todas as transações têm uma descrição, há neste momento 3 maneiras de associar uma categoria a uma transação:

### Definir manualmente

Para uma dada transação, és tu quem escolhes a categoria

### Definir uma expressão regular para uma dada descrição

Sempre que a expressão regular combinar com a descrição de uma transação, esta transação fica com uma determinada
categoria associada.

### Obter o valor através de outras transações

A aplicação vai à procura de outras transações com a mesma descrição, e associa a categoria.

## O que são repositórios de dados?

Um repositório de dados é um local onde vais guardar as tuas transações processadas.

Actualmente, os repositórios suportados são:
- Google Sheet

## O que posso fazer com este fluxo de dados?

Eu comecei por usar este fluxo de dados para fazer associação de categorias e visualizações no Google Sheets.

O processo que eu utilizo é:
1. Obtenho as novas transações (as que ainda não foram para o repositório)
2. Aplico as categorias por expressão regular e por valores a outras associadas
3. Envio para o Google Sheets.

O projecto de Google Sheets que tenho é identico a este que
[partilho aqui](https://docs.google.com/spreadsheets/d/1A5YeNDhnj03jKcJWAfoVrEBWd-2CjTN0HkDJ6yO0oRk/edit?usp=sharing)

# Como posso utilizar?

1. Fazer setup dum projecto numa conta da google (para poderes aceder a uma google sheet na tua conta)
2. Clonar o repo
3. Criar um python virtual env e instalar os requisitos

## Criar as credenciais do Google Oauth

Para que a aplicação possa ter autorização para editar um ficheiro Google Sheet na tua conta da Google, temos que criar
credenciais.

Para criares estas credenciais:

1. Acede a https://console.developers.google.com/apis/ e cria um novo projeto
    1.1 Para o nome do projecto, escolhe o que quiseres. Por exemplo, "Transaction Monitor" ou "Transaction Fetcher"
2. Abrindo o projecto acabado de criar, temos que ativar a API do serviço Google Sheet
3. Com a API ativa, vamos criar credenciais para a mesma
    - *Qual API você usa?* Google Sheet API
    - *De onde você chamará a API?* Outra UI (por exemplo, Windows, ferramenta CLI)
    - *Que dados você acessará?* Dados do aplicativo
    - *Papel*: Editor
4. Continuar e fazer download das credenciais. Vais precisar de as referir mais tarde na configuração da aplicação.

## Duplicar a folha Google Sheet modelo para a tua conta

[Bootstrap Expenses Repository](https://docs.google.com/spreadsheets/d/1A5YeNDhnj03jKcJWAfoVrEBWd-2CjTN0HkDJ6yO0oRk/edit?usp=sharing)


## Criar um python virtualenv e instalar os requisitos

Num terminal, muda de diretório para o local onde clonaste o repositório.

Assumindo que o nome `python` está a apontar para um python >= 3.5:

```bash
python -m venv venv
venv/bin/python -m pip install -r requirements.txt
```

## Configurar a aplicação

No diretório da aplicação, podes encontrar um ficheiro `config/accounts_cfg_example.yaml`.
Duplica-o nessa mesma pasta para outro nome, e faz o setup das tuas contas, e do teu repositório.


## Correr a aplicação

```bash
venv/bin/python main.py --config-file config/$CONFIG_FILE_NAME.yaml
```

Troca `$CONFIG_FILE_NAME` pelo nome do teu ficheiro de configuração.
