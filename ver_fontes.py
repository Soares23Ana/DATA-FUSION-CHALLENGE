"""
Mostra, lado a lado, o que existe em cada fonte de dados do Radar da Secretaria
para um mesmo aluno: SQLite, CSV financeiro, MongoDB e DuckDB (data warehouse).
Só LÊ os dados; não altera nada.

Uso (na pasta do projeto):
    py -3.14 ver_fontes.py              -> usa o RA 202400510
    py -3.14 ver_fontes.py 202200086    -> usa outro RA
"""
from __future__ import annotations

import csv
import json
import re
import sqlite3
import sys

from backend.config import CSV_FINANCEIRO, DUCKDB_DW, MONGO_DB, MONGO_URI, SQLITE_ACADEMICO

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

RA = sys.argv[1] if len(sys.argv) > 1 else "202400510"


def titulo(txt: str) -> None:
    print("\n" + "=" * 78)
    print(txt)
    print("=" * 78)


def tabela(linhas: list[dict], colunas: list[str]) -> None:
    if not linhas:
        print("  (nenhum registro)")
        return
    larg = {c: max(len(c), *(len(str(l.get(c, ""))) for l in linhas)) for c in colunas}
    print("  " + " | ".join(c.ljust(larg[c]) for c in colunas))
    print("  " + "-+-".join("-" * larg[c] for c in colunas))
    for l in linhas:
        print("  " + " | ".join(str(l.get(c, "")).ljust(larg[c]) for c in colunas))


# ---------------------------------------------------------------- 1) SQLite
titulo(f"1) SQLite - sistema academico (chave: RA)   [{SQLITE_ACADEMICO.name}]")
con = sqlite3.connect(SQLITE_ACADEMICO)
con.row_factory = sqlite3.Row
aluno = con.execute(
    "SELECT a.ra, a.nome, a.cpf, c.nome AS curso, a.periodo, a.cep, a.situacao "
    "FROM alunos a JOIN cursos c ON c.id = a.curso_id WHERE a.ra = ?", (RA,)
).fetchone()
if aluno is None:
    sys.exit(f"RA {RA} nao encontrado no SQLite.")
aluno = dict(aluno)
tabela([aluno], ["ra", "nome", "cpf", "curso", "periodo", "cep", "situacao"])
print("\n  Disciplinas cursadas (notas e faltas):")
mats = [dict(r) for r in con.execute(
    "SELECT d.nome AS disciplina, m.nota_p1, m.nota_p2, m.aulas_dadas, m.faltas "
    "FROM matriculas m JOIN disciplinas d ON d.id = m.disciplina_id WHERE m.ra = ?", (RA,))]
tabela(mats, ["disciplina", "nota_p1", "nota_p2", "aulas_dadas", "faltas"])
cpf_digitos = re.sub(r"\D", "", aluno["cpf"])

# ---------------------------------------------------------------- 2) CSV
titulo(f"2) CSV - ERP financeiro (chave: CPF)   [{CSV_FINANCEIRO.name}]")
with open(CSV_FINANCEIRO, encoding="utf-8", newline="") as f:
    todas = list(csv.DictReader(f, delimiter=";"))
parcelas = [p for p in todas if re.sub(r"\D", "", p["CPF_ALUNO"]) == cpf_digitos]
print(f"  No CSV o CPF aparece formatado: {parcelas[0]['CPF_ALUNO'] if parcelas else '-'}"
      f"  (no SQLite: {aluno['cpf']}) -> o Hop normaliza com regex")
tabela(parcelas, ["COMPETENCIA", "VENCIMENTO", "VALOR", "DATA_PAGAMENTO", "STATUS"])

# ---------------------------------------------------------------- 3) MongoDB
titulo(f"3) MongoDB - protocolos de atendimento (chave: RA)   [{MONGO_URI}/{MONGO_DB}]")
try:
    import pymongo

    cli = pymongo.MongoClient(MONGO_URI, serverSelectionTimeoutMS=2000)
    cli.admin.command("ping")
    col = cli[MONGO_DB]["atendimentos"]
    print(f"  Servidor real conectado. Total de protocolos na colecao: {col.estimated_document_count()}")
    docs = list(col.find({"ra": RA}, {"_id": 0}).sort("aberto_em", 1))
    print(f"  Protocolos do RA {RA}: {len(docs)}")
    for d in docs:
        print(f"\n  - {d['protocolo']} | {d['tipo']} | {d['status']} | aberto em {d['aberto_em']}")
        print(f"    detalhes (campos mudam conforme o tipo): "
              f"{json.dumps(d.get('detalhes', {}), ensure_ascii=False)}")
except Exception as e:  # noqa: BLE001
    print(f"  Nao consegui conectar no MongoDB ({type(e).__name__}). O servico 'MongoDB Server' esta em execucao?")

# ---------------------------------------------------------------- 4) DuckDB
titulo(f"4) DuckDB - data warehouse (resultado da integracao)   [{DUCKDB_DW.name}]")
try:
    import duckdb

    dw = duckdb.connect(str(DUCKDB_DW), read_only=True)
    cols = ["ra", "nome", "curso", "cidade", "frequencia_media", "media_geral", "parcelas_atrasadas",
            "valor_em_aberto", "protocolos_sinal_evasao", "protocolos_abertos", "score_risco", "nivel_risco"]
    cur = dw.execute(f"SELECT {', '.join(cols)}, acao_sugerida FROM vw_risco_evasao WHERE ra = ?", [RA])
    nomes = [d[0] for d in cur.description]
    linha = cur.fetchone()
    if linha:
        reg = dict(zip(nomes, linha))
        print("  O mesmo aluno, ja com as 3 fontes juntas (view vw_risco_evasao):\n")
        for k, v in reg.items():
            print(f"    {k:<24}: {v}")
    ult = dw.execute("SELECT executado_em, origem_consolidacao, alunos, parcelas, protocolos, duracao_s "
                     "FROM etl_execucao ORDER BY executado_em DESC LIMIT 1").fetchone()
    if ult:
        print(f"\n  Ultima carga: {ult[0]} | consolidacao via {ult[1]} | {ult[2]} alunos, "
              f"{ult[3]} parcelas, {ult[4]} protocolos | {ult[5]}s")
except Exception as e:  # noqa: BLE001
    print(f"  Nao consegui ler o DuckDB ({type(e).__name__}: {e})")

print("\nPronto. As 4 tecnologias acima sao as que o Apache Hop e o ETL juntam para o painel.")
