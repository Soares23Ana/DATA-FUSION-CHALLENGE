# Radar da Secretaria — UNIFEOB

**Data Fusion Challenge · Integração de Dados · Ciência da Computação**

Uma solução de dados para a **Secretaria Acadêmica**. Ela junta três sistemas que hoje não conversam entre si (o acadêmico, o financeiro e o de protocolos de atendimento) e entrega à equipe da secretaria:

| Funcionalidade | Pergunta que responde | Fontes cruzadas |
|---|---|---|
| **Radar de evasão** | Quais alunos estão prestes a desistir, e o que fazer com cada um? | SQLite + CSV + MongoDB |
| **Fila e prazos (SLA)** | Quais protocolos estão atrasados, considerando dias úteis e feriados? | MongoDB + BrasilAPI |
| **Abertura de protocolo** | Qual o prazo legal de entrega deste pedido? | SQLite (valida o RA) + MongoDB + BrasilAPI |
| **Origem dos alunos** | De onde vêm os alunos, e onde o risco é maior? | SQLite (CEP) + ViaCEP |
| **Aluno 360°** | Tudo sobre um aluno em uma só tela | as 4 fontes, consultadas ao vivo |

## O problema

A secretaria atende pedidos de declarações, históricos, revisões de nota, trancamentos e outros. Cada informação está em um sistema diferente:

- **Notas e faltas** ficam no sistema acadêmico, identificadas pelo **RA**.
- **Mensalidades** ficam no ERP financeiro, que só exporta uma planilha CSV identificada pelo **CPF** (com pontos e traço, vírgula decimal e datas dd/mm/aaaa).
- **Protocolos de atendimento** ficam em um banco de documentos, e cada tipo de pedido tem campos diferentes.

Por isso ninguém percebe que um aluno com **frequência caindo**, **3 mensalidades atrasadas** e um **pedido de trancamento aberto** está prestes a sair da faculdade. Cada sistema sozinho mostra só um pedaço. Os prazos também são controlados "de cabeça", sem descontar feriados.

## Arquitetura

```
 FONTES OPERACIONAIS                 INTEGRAÇÃO                         ANÁLISE / USO
 ┌──────────────────────┐
 │ SQLite  academico.db │──┐
 │ alunos, notas, faltas│  │   ┌─────────────────────────────┐
 └──────────────────────┘  │   │ Apache Hop                  │    ┌──────────────────────┐
 ┌──────────────────────┐  ├──▶│ consolidar_aluno.hpl        │──▶ │ staging/*.csv        │
 │ CSV  ERP financeiro  │──┤   │ · normaliza CPF (regex)     │    └──────────┬───────────┘
 │ chave = CPF formatado│  │   │ · filtra parcelas atrasadas │               │
 └──────────────────────┘  │   │ · agregação no MongoDB      │               ▼
 ┌──────────────────────┐  │   │ · junções por CPF e por RA  │    ┌──────────────────────┐    ┌───────────────┐
 │ MongoDB atendimentos │──┘   └─────────────────────────────┘    │ DuckDB (DW)          │◀───│ FastAPI       │◀── React
 │ protocolos (JSON)    │                                         │ dim_aluno            │    │ (Python)      │
 └──────────────────────┘      ┌─────────────────────────────┐    │ fato_atendimento     │    └───────┬───────┘
                               │ APIs externas               │──▶ │ fato_mensalidade     │            │ consulta
                               │ · ViaCEP  (cidade do aluno) │    │ vw_risco_evasao      │            │ ao vivo
                               │ · BrasilAPI (feriados)      │    └──────────────────────┘            ▼
                               └─────────────────────────────┘                          SQLite + MongoDB (Aluno 360°)
```

**Por que cada banco foi escolhido:**

- **SQLite**: simula o sistema acadêmico legado. Os dados são relacionais, com integridade entre aluno, matrícula e disciplina.
- **MongoDB**: os protocolos têm estrutura variável. Uma *revisão de nota* tem `disciplina` e `nota_atual`, e um *aproveitamento* tem uma lista de disciplinas. Em tabelas relacionais isso viraria dezenas de colunas vazias.
- **DuckDB**: data warehouse analítico (colunar). Roda as agregações do painel em milissegundos sem precisar de servidor.

**Processo ETL** ([backend/etl.py](backend/etl.py) e [hop/](hop/)):

1. **Extração**: SQL agregado no SQLite, leitura do CSV e pipeline de agregação no MongoDB.
2. **Transformação**: normaliza o CPF (`123.456.789-00` → `12345678900`), converte valores (`1.290,00` → `1290.00`) e datas, junta as fontes por CPF e por RA, calcula prazos em dias úteis e enriquece o endereço pelo CEP.
3. **Carga**: grava no DuckDB com troca atômica do arquivo, para o painel nunca ler uma carga pela metade, e registra cada execução na tabela `etl_execucao`.

**Modelo de risco de evasão** (view `vw_risco_evasao`, 0 a 100 pontos e explicável):

| Fator | Fonte | Peso |
|---|---|---|
| Frequência média abaixo de 85% (máximo em 60%) | SQLite | até 35 |
| Média geral abaixo de 7 (máximo em 4) | SQLite | até 25 |
| Mensalidades atrasadas (máximo em 3) | CSV financeiro | até 25 |
| Protocolos de trancamento, cancelamento, transferência ou reclamação | MongoDB | até 15 |

Níveis: **ALTO** a partir de 55 pontos e **MÉDIO** a partir de 30. A *ação sugerida* é escolhida pelo fator que mais pesou: financeiro, coordenação, monitoria ou entrevista de permanência.

## Requisitos do desafio

| Requisito | Onde está |
|---|---|
| 3+ tecnologias de armazenamento | SQLite, MongoDB e DuckDB |
| Ferramenta de integração | Apache Hop: [hop/pipelines/consolidar_aluno.hpl](hop/pipelines/consolidar_aluno.hpl) e [hop/workflows/carga_completa.hwf](hop/workflows/carga_completa.hwf) |
| API externa | ViaCEP e BrasilAPI (feriados), em [backend/apis_externas.py](backend/apis_externas.py) |
| Backend Python | FastAPI, em [backend/app.py](backend/app.py) |
| Frontend React | Vite + React + Recharts, em [frontend/src](frontend/src) |
| Integração / consolidação | Junções por CPF e por RA, staging e DW |
| Interface | 5 telas: visão geral, radar, fila, origem e aluno 360° |

## Como executar

Pré-requisitos: Python 3.10+, Node 18+ e (recomendado) MongoDB Community ou MongoDB Atlas. Para o Hop é preciso Java 17+ e o [Apache Hop](https://hop.apache.org/download/).

```bash
pip install -r requirements.txt
```

```bash
python dados/gerar_fontes.py
```

O comando acima gera as 3 fontes e, se houver um MongoDB rodando, já carrega a coleção. Para usar o MongoDB Atlas, defina antes a variável `MONGO_URI` (no PowerShell: `$env:MONGO_URI="mongodb+srv://..."`).

```bash
python -m backend.etl
```

Esse é o ETL. Ele usa a saída do Apache Hop se ela existir; se não, faz a consolidação equivalente em Python.

```bash
python -m uvicorn backend.app:app --port 8000
```

```bash
npm --prefix frontend install
```

```bash
npm --prefix frontend run dev
```

Abra http://localhost:5173. A documentação da API fica em http://localhost:8000/docs.

> **Sem MongoDB instalado?** O backend entra automaticamente em **modo embutido** (mongomock, carregado do `fontes/atendimentos.json`) e o painel mostra um aviso. Para a apresentação, use um MongoDB real.

### Executando a integração pelo Apache Hop

Veja [hop/README.md](hop/README.md). Resumo: abra o projeto `hop/` no Hop GUI e execute o workflow `carga_completa.hwf`. Ele roda o pipeline de consolidação e depois chama `python -m backend.etl`, que carrega o DuckDB. No rodapé da *Visão geral* aparece "consolidação via **Apache Hop**".

## Estrutura

```
backend/        API FastAPI, ETL, conexões e APIs externas
dados/          gerador das fontes simuladas (dados fictícios)
fontes/         SQLite, CSV financeiro e JSON de importação do MongoDB
hop/            projeto Apache Hop (pipeline, workflow, conexões)
staging/        área intermediária (saídas do Hop/Python e cache das APIs)
dw/             data warehouse DuckDB (gerado pelo ETL)
frontend/       aplicação React
docs/           roteiro da apresentação
```

## Endpoints principais

| Método | Rota | Descrição |
|---|---|---|
| GET | `/api/kpis` | Indicadores gerais e risco por curso |
| GET | `/api/risco?nivel=&curso=&cidade=&busca=` | Radar de evasão |
| GET | `/api/atendimentos/fila` | Protocolos abertos, priorizados por prazo |
| GET | `/api/atendimentos/indicadores` | Demanda mensal, SLA por tipo, canais |
| POST | `/api/atendimentos` | Abre protocolo no MongoDB com prazo em dias úteis |
| GET | `/api/alunos/{ra}` | Visão 360° (SQLite + MongoDB + DuckDB + ViaCEP) |
| GET | `/api/origem` | Alunos e risco por cidade |
| POST | `/api/etl/executar` | Executa a carga |

> Todos os dados de alunos são **fictícios**, gerados por `dados/gerar_fontes.py`. Só os CEPs são reais, para que o ViaCEP responda.
