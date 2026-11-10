# Projeto Apache Hop — Radar da Secretaria

## Conteúdo

| Arquivo | Função |
|---|---|
| `pipelines/consolidar_aluno.hpl` | Junta as 3 fontes por aluno e grava `staging/aluno_consolidado_hop.csv` |
| `workflows/carga_completa.hwf` | Orquestra: pipeline → `python -m backend.etl` (carga no DuckDB) → sucesso |
| `metadata/rdbms/academico_sqlite.json` | Conexão SQLite → `fontes/academico.db` |
| `metadata/mongodb-connection/atendimentos_mongo.json` | Conexão MongoDB `localhost:27017 / secretaria_unifeob` |

## Passo a passo

1. Instale o Java 17+ e baixe o Apache Hop (2.10 ou mais recente). Abra o `hop-gui.bat`.
2. Rode antes `python dados/gerar_fontes.py` com o MongoDB ligado, para a coleção `atendimentos` existir.
3. No Hop: **File → Projects → Add project**, nome `radar_secretaria`, pasta: esta pasta `hop/`.
4. Abra `workflows/carga_completa.hwf` e clique em **Run**.
   - Para rodar só a consolidação, abra `pipelines/consolidar_aluno.hpl` e clique em **Run** (depois rode `python -m backend.etl`).
5. Confirme que `staging/aluno_consolidado_hop.csv` foi criado. O painel passa a mostrar "consolidação via Apache Hop".

## O que o pipeline faz

```
Acadêmico - SQLite ───────────────────────────────────────────┐
                                                              ▼
Financeiro - CSV → Normaliza CPF → Só parcelas atrasadas → Agrega por CPF → Junta financeiro (CPF)
                                                                              ▼
Protocolos - MongoDB (pipeline de agregação $group por RA) ──────────────▶ Junta protocolos (RA) → Saída (staging)
```

- **Table input (SQLite)**: SQL que calcula frequência média, média geral e disciplinas em risco por aluno.
- **CSV file input**: lê o CSV com `;`, vírgula decimal e datas `dd/MM/yyyy`.
- **Replace in string**: regex `[^0-9]` transforma o CPF formatado em só dígitos (mesmo formato do acadêmico).
- **Filter rows** + **Memory group by**: conta as parcelas `ATRASADO` e soma o valor em aberto por CPF.
- **MongoDB input** (com *query is aggregation pipeline*): `$group` por RA conta os protocolos de saída/reclamação e os protocolos em aberto.
- **Stream lookup** ×2: junta pelo CPF (financeiro) e pelo RA (MongoDB), com padrão 0 quando o aluno não tem registro.
- **Text file output**: grava o consolidado em `staging/`, que o carregador lê e envia ao DuckDB.

## Se algo não abrir

Os arquivos `.hpl`/`.hwf` foram escritos à mão e **ainda não foram testados em uma instalação do Hop**. Se algum transform aparecer com erro:

- **Conexão MongoDB**: crie em *Metadata → MongoDB Connection* com o nome `atendimentos_mongo` (host `localhost`, porta `27017`, banco `secretaria_unifeob`).
- **Conexão SQLite**: crie em *Metadata → Relational Database Connection* com o nome `academico_sqlite`, tipo SQLite, banco `${PROJECT_HOME}/../fontes/academico.db`.
- **Transform com erro**: recrie seguindo a descrição acima. Os nomes das colunas de saída precisam ser exatamente: `ra;nome;cpf;curso;periodo;cep;frequencia_media;media_geral;disciplinas_em_risco;parcelas_atrasadas;valor_em_aberto;protocolos_sinal_evasao;protocolos_abertos`.

Para comparar, rode `python -m backend.etl --python`. Ele gera `staging/aluno_consolidado_python.csv`, que deve ter os mesmos números da saída do Hop.
