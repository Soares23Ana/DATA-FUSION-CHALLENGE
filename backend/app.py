"""
API do Radar da Secretaria UNIFEOB (FastAPI).

Leituras analíticas  -> DuckDB (Data Warehouse gerado pelo ETL)
Visão 360 do aluno   -> consulta AO VIVO o SQLite, o MongoDB e o DW, juntando as três fontes
Novo protocolo       -> grava no MongoDB com prazo calculado em dias úteis (feriados da BrasilAPI)

Rodar:  python -m uvicorn backend.app:app --reload --port 8000
Docs:   http://localhost:8000/docs
"""
from __future__ import annotations

import threading
from datetime import date, datetime

import duckdb
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from . import calendario, etl
from .apis_externas import consultar_cep, feriados
from .config import DUCKDB_DW, PRAZOS_DIAS_UTEIS
from .fontes import modo_mongo, mongo_atendimentos, persistir_se_embutido, sqlite_academico

app = FastAPI(title="Radar da Secretaria UNIFEOB", version="1.0",
              description="Integração de dados acadêmicos, financeiros e de atendimento da Secretaria.")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
_etl_lock = threading.Lock()


def dw():
    if not DUCKDB_DW.exists():
        raise HTTPException(503, "Data Warehouse ainda não foi gerado. Rode: python -m backend.etl")
    return duckdb.connect(str(DUCKDB_DW), read_only=True)


def consulta(sql: str, params: list | None = None) -> list[dict]:
    con = dw()
    try:
        cur = con.execute(sql, params or [])
        cols = [c[0] for c in cur.description]
        return [dict(zip(cols, (v.isoformat() if isinstance(v, (date, datetime)) else v for v in linha)))
                for linha in cur.fetchall()]
    finally:
        con.close()


@app.get("/api/status")
def status():
    ultima = consulta("SELECT * FROM etl_execucao ORDER BY executado_em DESC LIMIT 1")
    return {"mongo": modo_mongo(), "ultima_carga": ultima[0] if ultima else None}


@app.get("/api/kpis")
def kpis():
    k = consulta("""
      SELECT
        (SELECT count(*) FROM aluno_consolidado) AS alunos_ativos,
        (SELECT count(*) FROM vw_risco_evasao WHERE nivel_risco = 'ALTO') AS alunos_risco_alto,
        (SELECT count(*) FROM vw_risco_evasao WHERE nivel_risco = 'MÉDIO') AS alunos_risco_medio,
        (SELECT count(*) FROM fato_atendimento WHERE status <> 'CONCLUIDO') AS protocolos_abertos,
        (SELECT count(*) FROM fato_atendimento WHERE situacao_sla = 'ATRASADO') AS protocolos_atrasados,
        (SELECT round(100.0 * avg(CASE WHEN situacao_sla = 'NO PRAZO' THEN 1 ELSE 0 END), 1)
           FROM fato_atendimento WHERE status = 'CONCLUIDO') AS pct_sla_cumprido,
        (SELECT round(avg(avaliacao_atendimento), 2) FROM fato_atendimento) AS satisfacao_media,
        (SELECT round(sum(valor), 2) FROM fato_mensalidade WHERE status = 'ATRASADO') AS valor_inadimplente,
        (SELECT round(sum(valor_em_aberto), 2) FROM vw_risco_evasao WHERE nivel_risco = 'ALTO') AS receita_em_risco
    """)[0]
    k["por_curso"] = consulta("""
      SELECT curso, count(*) AS alunos,
             sum(CASE WHEN nivel_risco='ALTO' THEN 1 ELSE 0 END) AS risco_alto,
             round(100.0 * sum(CASE WHEN nivel_risco='ALTO' THEN 1 ELSE 0 END) / count(*), 1) AS pct_risco_alto,
             round(avg(frequencia_media), 1) AS frequencia, round(avg(media_geral), 2) AS media
      FROM vw_risco_evasao GROUP BY curso ORDER BY pct_risco_alto DESC""")
    return k


@app.get("/api/risco")
def risco(nivel: str | None = None, curso: str | None = None, cidade: str | None = None,
          busca: str | None = None, limite: int = Query(200, le=1000)):
    filtros, params = [], []
    if nivel:
        filtros.append("nivel_risco = ?"); params.append(nivel)
    if curso:
        filtros.append("curso = ?"); params.append(curso)
    if cidade:
        filtros.append("cidade = ?"); params.append(cidade)
    if busca:
        filtros.append("(lower(nome) LIKE ? OR ra LIKE ?)"); params += [f"%{busca.lower()}%", f"%{busca}%"]
    where = ("WHERE " + " AND ".join(filtros)) if filtros else ""
    return consulta(f"""SELECT ra, nome, curso, periodo, cidade, frequencia_media, media_geral, disciplinas_em_risco,
                               parcelas_atrasadas, valor_em_aberto, protocolos_sinal_evasao, protocolos_abertos,
                               pts_frequencia, pts_notas, pts_financeiro, pts_protocolos, score_risco, nivel_risco, acao_sugerida
                        FROM vw_risco_evasao {where} ORDER BY score_risco DESC LIMIT {int(limite)}""", params)


@app.get("/api/filtros")
def filtros():
    return {"cursos": [r["curso"] for r in consulta("SELECT DISTINCT curso FROM dim_aluno ORDER BY 1")],
            "cidades": [r["cidade"] for r in consulta("SELECT DISTINCT cidade FROM dim_aluno ORDER BY 1")],
            "tipos_protocolo": [{"tipo": t, "prazo_dias_uteis": p} for t, p in PRAZOS_DIAS_UTEIS.items()]}


@app.get("/api/atendimentos/fila")
def fila(situacao: str | None = None, tipo: str | None = None):
    filtros, params = ["f.status <> 'CONCLUIDO'"], []
    if situacao:
        filtros.append("f.situacao_sla = ?"); params.append(situacao)
    if tipo:
        filtros.append("f.tipo = ?"); params.append(tipo)
    return consulta(f"""
      SELECT f.protocolo, f.ra, d.nome, d.curso, f.tipo, f.canal, f.status, f.aberto_em, f.prazo_dias_uteis,
             f.prazo_final, f.dias_uteis_decorridos, f.situacao_sla, r.nivel_risco
      FROM fato_atendimento f LEFT JOIN dim_aluno d USING (ra) LEFT JOIN vw_risco_evasao r USING (ra)
      WHERE {' AND '.join(filtros)}
      ORDER BY CASE f.situacao_sla WHEN 'ATRASADO' THEN 0 WHEN 'VENCE EM BREVE' THEN 1 ELSE 2 END, f.prazo_final""", params)


@app.get("/api/atendimentos/indicadores")
def indicadores_atendimento():
    return {
        "por_mes": consulta("""
          SELECT strftime(CAST(aberto_em AS TIMESTAMP), '%Y-%m') AS mes, count(*) AS total,
                 sum(CASE WHEN tipo='Declaração de matrícula' THEN 1 ELSE 0 END) AS declaracoes,
                 sum(CASE WHEN tipo IN ('Trancamento de matrícula','Cancelamento de matrícula','Transferência externa') THEN 1 ELSE 0 END) AS saidas,
                 sum(CASE WHEN tipo='Revisão de nota' THEN 1 ELSE 0 END) AS revisoes
          FROM fato_atendimento GROUP BY 1 ORDER BY 1"""),
        "por_tipo": consulta("""
          SELECT tipo, count(*) AS total, any_value(prazo_dias_uteis) AS prazo,
                 round(avg(CASE WHEN status='CONCLUIDO' THEN dias_uteis_decorridos END), 1) AS media_dias_uteis,
                 round(100.0 * avg(CASE WHEN status='CONCLUIDO' THEN (situacao_sla='NO PRAZO')::INT END), 1) AS pct_no_prazo
          FROM fato_atendimento GROUP BY tipo ORDER BY total DESC"""),
        "por_canal": consulta("SELECT canal, count(*) AS total FROM fato_atendimento GROUP BY 1 ORDER BY 2 DESC"),
    }


@app.get("/api/origem")
def origem():
    return consulta("""
      SELECT d.cidade, d.uf, count(*) AS alunos,
             sum(CASE WHEN r.nivel_risco='ALTO' THEN 1 ELSE 0 END) AS risco_alto,
             round(100.0 * sum(CASE WHEN r.nivel_risco='ALTO' THEN 1 ELSE 0 END) / count(*), 1) AS pct_risco_alto,
             round(avg(r.frequencia_media), 1) AS frequencia
      FROM dim_aluno d JOIN vw_risco_evasao r USING (ra) GROUP BY 1, 2 ORDER BY alunos DESC""")


@app.get("/api/alunos/{ra}")
def aluno_360(ra: str):
    """Visão 360°: junta em tempo real SQLite (acadêmico) + MongoDB (protocolos) + DuckDB (financeiro/risco) + ViaCEP."""
    con = sqlite_academico()
    a = con.execute("SELECT a.*, c.nome AS curso FROM alunos a JOIN cursos c ON c.id=a.curso_id WHERE a.ra=?", [ra]).fetchone()
    if not a:
        raise HTTPException(404, "Aluno não encontrado")
    disciplinas = [dict(r) for r in con.execute("""
        SELECT d.nome AS disciplina, m.nota_p1, m.nota_p2, round((m.nota_p1+m.nota_p2)/2.0, 1) AS media,
               m.faltas, m.aulas_dadas, round(100.0*(1.0 - CAST(m.faltas AS REAL)/m.aulas_dadas), 1) AS frequencia
        FROM matriculas m JOIN disciplinas d ON d.id = m.disciplina_id WHERE m.ra=? ORDER BY d.nome""", [ra])]
    con.close()
    aluno = dict(a)
    protocolos = list(mongo_atendimentos().find({"ra": ra}, {"_id": 0}).sort("aberto_em", -1))
    risco_ = consulta("SELECT * FROM vw_risco_evasao WHERE ra = ?", [ra])
    mensalidades = consulta("SELECT competencia, vencimento, valor, data_pagamento, status FROM fato_mensalidade "
                            "WHERE cpf = ? ORDER BY vencimento", [aluno["cpf"]])
    sla = {p["protocolo"]: p for p in consulta("SELECT protocolo, prazo_final, situacao_sla FROM fato_atendimento WHERE ra=?", [ra])}
    for p in protocolos:
        p.update({k: v for k, v in sla.get(p["protocolo"], {}).items() if k != "protocolo"})
    return {"aluno": aluno, "endereco": consultar_cep(aluno["cep"]), "disciplinas": disciplinas,
            "mensalidades": mensalidades, "protocolos": protocolos, "risco": risco_[0] if risco_ else None,
            "fontes": {"academico": "SQLite", "protocolos": modo_mongo(), "financeiro_risco": "DuckDB (DW)", "endereco": "ViaCEP"}}


class NovoProtocolo(BaseModel):
    ra: str
    tipo: str
    canal: str = "Balcão"
    detalhes: dict = Field(default_factory=dict)


@app.post("/api/atendimentos", status_code=201)
def abrir_protocolo(p: NovoProtocolo):
    if p.tipo not in PRAZOS_DIAS_UTEIS:
        raise HTTPException(400, "Tipo de protocolo inválido")
    con = sqlite_academico()
    existe = con.execute("SELECT 1 FROM alunos WHERE ra=?", [p.ra]).fetchone()
    con.close()
    if not existe:
        raise HTTPException(404, "RA não encontrado no sistema acadêmico")
    col = mongo_atendimentos()
    agora = datetime.now().replace(microsecond=0)
    ultimo = col.find_one({"protocolo": {"$regex": f"^SEC-{agora.year}-"}}, sort=[("protocolo", -1)])
    seq = int(ultimo["protocolo"].split("-")[-1]) + 1 if ultimo else 1
    prazo = calendario.somar_dias_uteis(agora.date(), PRAZOS_DIAS_UTEIS[p.tipo])
    doc = {"protocolo": f"SEC-{agora.year}-{seq:05d}", "ra": p.ra, "tipo": p.tipo, "canal": p.canal,
           "status": "ABERTO", "aberto_em": agora.isoformat(), "concluido_em": None, "detalhes": p.detalhes,
           "historico": [{"status": "ABERTO", "em": agora.isoformat(), "por": "Portal Radar"}]}
    col.insert_one(dict(doc))
    persistir_se_embutido()
    feriados_no_caminho = [f for f in feriados(agora.year) + feriados(prazo.year)
                           if agora.date().isoformat() < f["data"] <= prazo.isoformat()
                           and date.fromisoformat(f["data"]).weekday() < 5]  # só os que caem em dia de semana
    return {**doc, "prazo_final": prazo.isoformat(), "prazo_dias_uteis": PRAZOS_DIAS_UTEIS[p.tipo],
            "feriados_considerados": feriados_no_caminho,
            "aviso": "Protocolo gravado no MongoDB. Execute a carga (ETL) para refletir nos painéis."}


@app.get("/api/feriados/{ano}")
def listar_feriados(ano: int):
    return feriados(ano)


@app.post("/api/etl/executar")
def executar_etl(forcar_python: bool = False):
    if not _etl_lock.acquire(blocking=False):
        raise HTTPException(409, "Uma carga já está em execução")
    try:
        return etl.executar(forcar_python)
    finally:
        _etl_lock.release()
