"""
ETL da Secretaria: Extrai das 3 fontes -> Transforma/Consolida -> Carrega no Data Warehouse DuckDB.

    SQLite (acadêmico) ─┐
    CSV (financeiro)  ──┼─> [Apache Hop: consolidar_aluno.hpl]  ─> staging/aluno_consolidado_hop.csv ─┐
    MongoDB (protocolos)┘   (ou o equivalente em Python abaixo) ─> staging/aluno_consolidado_python.csv ┤
                                                                                                        ├─> DuckDB (dw/)
    ViaCEP (cidade do aluno) + BrasilAPI (feriados -> prazos em dias úteis) ───────────────────────────────┘

Uso:
    python -m backend.etl            # usa a saída do Apache Hop se existir; senão consolida em Python
    python -m backend.etl --python   # força a consolidação em Python
"""
from __future__ import annotations

import argparse
import csv
import time
from collections import defaultdict
from datetime import date, datetime

import duckdb

from . import calendario
from .apis_externas import enriquecer_ceps, feriados
from .config import (CSV_FINANCEIRO, DUCKDB_DW, DW_DIR, HOP_SAIDA_ALUNO, PRAZOS_DIAS_UTEIS, STAGING,
                     TIPOS_SINAL_EVASAO)
from .fontes import mongo_atendimentos, sqlite_academico

COLUNAS_CONSOLIDADO = ["ra", "nome", "cpf", "curso", "periodo", "cep", "frequencia_media", "media_geral",
                       "disciplinas_em_risco", "parcelas_atrasadas", "valor_em_aberto",
                       "protocolos_sinal_evasao", "protocolos_abertos"]

# Mesmo SQL usado no transform "Table input" do Apache Hop
SQL_ACADEMICO = """
SELECT a.ra, a.nome, a.cpf, c.nome AS curso, a.periodo, a.cep,
       ROUND(AVG(100.0 * (1.0 - CAST(m.faltas AS REAL) / m.aulas_dadas)), 1) AS frequencia_media,
       ROUND(AVG((m.nota_p1 + m.nota_p2) / 2.0), 2)                         AS media_geral,
       SUM(CASE WHEN (m.nota_p1 + m.nota_p2) / 2.0 < 6
                  OR (1.0 - CAST(m.faltas AS REAL) / m.aulas_dadas) < 0.75 THEN 1 ELSE 0 END) AS disciplinas_em_risco
FROM alunos a
JOIN cursos c ON c.id = a.curso_id
JOIN matriculas m ON m.ra = a.ra
WHERE a.situacao = 'ATIVO'
GROUP BY a.ra, a.nome, a.cpf, c.nome, a.periodo, a.cep
"""


def so_digitos(s: str) -> str:
    return "".join(ch for ch in str(s) if ch.isdigit())


def br_data(s: str) -> str | None:
    return datetime.strptime(s, "%d/%m/%Y").date().isoformat() if s else None


# ---------------------------------------------------------------- EXTRAÇÃO
def extrair_academico() -> list[dict]:
    con = sqlite_academico()
    linhas = [dict(r) for r in con.execute(SQL_ACADEMICO)]
    alunos = [dict(r) for r in con.execute("SELECT a.*, c.nome AS curso FROM alunos a JOIN cursos c ON c.id=a.curso_id")]
    con.close()
    return linhas, alunos


def extrair_financeiro() -> list[dict]:
    with open(CSV_FINANCEIRO, encoding="utf-8") as f:
        return [{
            "cpf": so_digitos(r["CPF_ALUNO"]),                      # 123.456.789-00 -> 12345678900
            "competencia": r["COMPETENCIA"],
            "vencimento": br_data(r["VENCIMENTO"]),                 # dd/mm/aaaa -> ISO
            "valor": float(r["VALOR"].replace(".", "").replace(",", ".")),  # 1.290,00 -> 1290.00
            "data_pagamento": br_data(r["DATA_PAGAMENTO"]),
            "status": r["STATUS"].strip().upper(),
        } for r in csv.DictReader(f, delimiter=";")]


def extrair_atendimentos() -> list[dict]:
    return list(mongo_atendimentos().find({}, {"_id": 0}))


# ---------------------------------------------------------------- TRANSFORMAÇÃO
def consolidar_aluno_python(academico, financeiro, atendimentos) -> list[dict]:
    """Equivalente Python do pipeline Apache Hop (consolidar_aluno.hpl)."""
    fin = defaultdict(lambda: {"parcelas_atrasadas": 0, "valor_em_aberto": 0.0})
    for p in financeiro:
        if p["status"] == "ATRASADO":
            fin[p["cpf"]]["parcelas_atrasadas"] += 1
            fin[p["cpf"]]["valor_em_aberto"] += p["valor"]
    atd = defaultdict(lambda: {"protocolos_sinal_evasao": 0, "protocolos_abertos": 0})
    for a in atendimentos:
        if a["tipo"] in TIPOS_SINAL_EVASAO:
            atd[a["ra"]]["protocolos_sinal_evasao"] += 1
        if a["status"] != "CONCLUIDO":
            atd[a["ra"]]["protocolos_abertos"] += 1
    saida = []
    for r in academico:
        linha = dict(r)
        linha.update(fin[so_digitos(r["cpf"])])            # junção acadêmico x financeiro pelo CPF
        linha.update(atd[r["ra"]])                         # junção acadêmico x MongoDB pelo RA
        linha["valor_em_aberto"] = round(linha["valor_em_aberto"], 2)
        saida.append(linha)
    return saida


def ler_saida_hop() -> list[dict]:
    with open(HOP_SAIDA_ALUNO, encoding="utf-8") as f:
        linhas = list(csv.DictReader(f, delimiter=";"))
    for l in linhas:
        for k in ("frequencia_media", "media_geral", "valor_em_aberto"):
            l[k] = float(str(l[k] or 0).replace(",", "."))
        for k in ("periodo", "disciplinas_em_risco", "parcelas_atrasadas", "protocolos_sinal_evasao", "protocolos_abertos"):
            l[k] = int(float(str(l[k] or 0).replace(",", ".")))
        l["cpf"] = so_digitos(l["cpf"])
    return linhas


def transformar_atendimentos(atendimentos) -> list[dict]:
    """Calcula prazo regimental em DIAS ÚTEIS (feriados BrasilAPI) e situação de SLA."""
    hoje = date.today()
    saida = []
    for a in atendimentos:
        aberto = datetime.fromisoformat(a["aberto_em"])
        prazo_dias = PRAZOS_DIAS_UTEIS.get(a["tipo"], 10)
        prazo = calendario.somar_dias_uteis(aberto.date(), prazo_dias)
        concluido = datetime.fromisoformat(a["concluido_em"]) if a.get("concluido_em") else None
        referencia = concluido.date() if concluido else hoje
        usados = calendario.dias_uteis_entre(aberto.date(), referencia)
        if concluido:
            sla = "NO PRAZO" if concluido.date() <= prazo else "FORA DO PRAZO"
        else:
            restantes = calendario.dias_uteis_entre(hoje, prazo)
            sla = "ATRASADO" if restantes < 0 else ("VENCE EM BREVE" if restantes <= 1 else "NO PRAZO")
        saida.append({
            "protocolo": a["protocolo"], "ra": a["ra"], "tipo": a["tipo"], "canal": a["canal"], "status": a["status"],
            "aberto_em": aberto.isoformat(sep=" "), "concluido_em": concluido.isoformat(sep=" ") if concluido else None,
            "prazo_dias_uteis": prazo_dias, "prazo_final": prazo.isoformat(), "dias_uteis_decorridos": usados,
            "situacao_sla": sla, "avaliacao_atendimento": a.get("avaliacao_atendimento"),
        })
    return saida


# ---------------------------------------------------------------- CARGA
def _gravar_csv(nome: str, linhas: list[dict], colunas: list[str]) -> str:
    STAGING.mkdir(exist_ok=True)
    caminho = STAGING / nome
    with open(caminho, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=colunas, delimiter=";", extrasaction="ignore")
        w.writeheader()
        w.writerows(linhas)
    return caminho.as_posix()


def carregar_dw(consolidado, alunos, financeiro, atendimentos_t, ceps, feriados_lista, origem: str, t0: float):
    DW_DIR.mkdir(exist_ok=True)
    for a in alunos:
        info = ceps.get(so_digitos(a["cep"]).zfill(8), {})
        a["cidade"], a["uf"], a["bairro"] = info.get("cidade") or "Não localizado", info.get("uf"), info.get("bairro")

    arq = {
        "consolidado": _gravar_csv("aluno_consolidado_python.csv" if origem == "Python" else "_carga_consolidado.csv",
                                   consolidado, COLUNAS_CONSOLIDADO),
        "alunos": _gravar_csv("_carga_dim_aluno.csv", alunos,
                              ["ra", "nome", "cpf", "email", "telefone", "curso", "periodo", "ano_ingresso", "cep", "cidade", "uf", "bairro"]),
        "financeiro": _gravar_csv("_carga_fato_mensalidade.csv", financeiro,
                                  ["cpf", "competencia", "vencimento", "valor", "data_pagamento", "status"]),
        "atendimentos": _gravar_csv("_carga_fato_atendimento.csv", atendimentos_t, list(atendimentos_t[0].keys())),
        "feriados": _gravar_csv("_carga_dim_feriado.csv", feriados_lista, ["data", "nome", "tipo"]),
    }
    tmp = DUCKDB_DW.with_suffix(".tmp.duckdb")
    if tmp.exists():
        tmp.unlink()
    con = duckdb.connect(str(tmp))
    opts = "delim=';', header=true, all_varchar=false"
    con.execute(f"CREATE TABLE dim_aluno AS SELECT * FROM read_csv('{arq['alunos']}', {opts}, types={{'cpf':'VARCHAR','cep':'VARCHAR','ra':'VARCHAR'}})")
    con.execute(f"CREATE TABLE fato_mensalidade AS SELECT * FROM read_csv('{arq['financeiro']}', {opts}, types={{'cpf':'VARCHAR','competencia':'VARCHAR'}})")
    con.execute(f"CREATE TABLE fato_atendimento AS SELECT * FROM read_csv('{arq['atendimentos']}', {opts}, types={{'ra':'VARCHAR','avaliacao_atendimento':'INTEGER'}})")
    con.execute(f"CREATE TABLE dim_feriado AS SELECT * FROM read_csv('{arq['feriados']}', {opts})")
    con.execute(f"CREATE TABLE aluno_consolidado AS SELECT * FROM read_csv('{arq['consolidado']}', {opts}, types={{'cpf':'VARCHAR','cep':'VARCHAR','ra':'VARCHAR'}})")

    # Modelo de risco de evasão (transparente e explicável): 0 a 100 pontos
    con.execute("""
    CREATE VIEW vw_risco_evasao AS
    WITH base AS (
      SELECT c.*, d.cidade, d.email, d.telefone,
        ROUND(GREATEST(0, LEAST(1, (85 - frequencia_media) / 25.0)) * 35, 1) AS pts_frequencia,
        ROUND(GREATEST(0, LEAST(1, (7 - media_geral) / 3.0)) * 25, 1)       AS pts_notas,
        ROUND(LEAST(parcelas_atrasadas, 3) / 3.0 * 25, 1)                   AS pts_financeiro,
        ROUND(LEAST(protocolos_sinal_evasao, 2) / 2.0 * 15, 1)              AS pts_protocolos
      FROM aluno_consolidado c LEFT JOIN dim_aluno d USING (ra))
    SELECT *,
      ROUND(pts_frequencia + pts_notas + pts_financeiro + pts_protocolos, 1) AS score_risco,
      CASE WHEN pts_frequencia + pts_notas + pts_financeiro + pts_protocolos >= 55 THEN 'ALTO'
           WHEN pts_frequencia + pts_notas + pts_financeiro + pts_protocolos >= 30 THEN 'MÉDIO'
           ELSE 'BAIXO' END AS nivel_risco,
      CASE WHEN pts_frequencia + pts_notas + pts_financeiro + pts_protocolos < 30 THEN 'Acompanhamento regular'
           ELSE CASE GREATEST(pts_frequencia, pts_notas, pts_financeiro, pts_protocolos)
           WHEN pts_financeiro THEN 'Encaminhar ao Financeiro para negociação / bolsa'
           WHEN pts_frequencia THEN 'Contato da coordenação sobre frequência'
           WHEN pts_notas THEN 'Encaminhar à monitoria / apoio pedagógico'
           ELSE 'Entrevista de permanência (protocolos de saída/reclamação)' END END AS acao_sugerida
    FROM base
    """)
    con.execute("CREATE TABLE etl_execucao (executado_em TIMESTAMP, origem_consolidacao VARCHAR, alunos INTEGER, "
                "parcelas INTEGER, protocolos INTEGER, ceps_enriquecidos INTEGER, feriados INTEGER, duracao_s DOUBLE)")
    con.execute("INSERT INTO etl_execucao VALUES (now(), ?, ?, ?, ?, ?, ?, ?)",
                [origem, len(consolidado), len(financeiro), len(atendimentos_t),
                 sum(1 for v in ceps.values() if v.get("cidade")), len(feriados_lista), round(time.time() - t0, 2)])
    con.close()
    tmp.replace(DUCKDB_DW)  # troca atômica: o dashboard nunca lê um DW pela metade


def executar(forcar_python: bool = False) -> dict:
    t0 = time.time()
    print("[ETL] Extraindo fontes...")
    academico, alunos = extrair_academico()
    financeiro = extrair_financeiro()
    atendimentos = extrair_atendimentos()

    if HOP_SAIDA_ALUNO.exists() and not forcar_python:
        print(f"[ETL] Usando consolidação do Apache Hop: {HOP_SAIDA_ALUNO.name}")
        consolidado, origem = ler_saida_hop(), "Apache Hop"
    else:
        print("[ETL] Consolidando em Python (equivalente ao pipeline Hop)")
        consolidado, origem = consolidar_aluno_python(academico, financeiro, atendimentos), "Python"

    print("[ETL] Enriquecendo com APIs externas (ViaCEP, BrasilAPI)...")
    ceps = enriquecer_ceps([a["cep"] for a in alunos])
    anos = sorted({int(a["aberto_em"][:4]) for a in atendimentos} | {date.today().year, date.today().year + 1})
    fer = [f for ano in anos for f in feriados(ano)]
    atendimentos_t = transformar_atendimentos(atendimentos)

    print("[ETL] Carregando Data Warehouse DuckDB...")
    carregar_dw(consolidado, alunos, financeiro, atendimentos_t, ceps, fer, origem, t0)
    resumo = {"origem_consolidacao": origem, "alunos": len(consolidado), "parcelas": len(financeiro),
              "protocolos": len(atendimentos_t), "feriados": len(fer), "duracao_s": round(time.time() - t0, 2)}
    print(f"[ETL] Concluído: {resumo}")
    return resumo


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--python", action="store_true", help="ignora a saída do Apache Hop")
    executar(ap.parse_args().python)
