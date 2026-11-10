"""
Gera as TRÊS FONTES DE DADOS simuladas da Secretaria (dados fictícios, porém realistas).

  1. fontes/academico.db              -> SQLite  (sistema acadêmico: alunos, disciplinas, matrículas, notas, faltas)
  2. fontes/atendimentos.json         -> MongoDB (protocolos da secretaria, documentos com campos flexíveis)
  3. fontes/financeiro_mensalidades.csv -> CSV exportado do ERP financeiro (formato "brasileiro", chave = CPF)

As fontes foram propositalmente criadas com "problemas do mundo real" para o ETL resolver:
  - O financeiro identifica o aluno por CPF formatado (123.456.789-00); o acadêmico guarda só dígitos e usa RA.
  - O CSV usa ';' como separador, vírgula decimal e datas dd/mm/aaaa.
  - Cada tipo de protocolo no MongoDB tem campos diferentes em "detalhes".

Uso:
    python dados/gerar_fontes.py            # gera arquivos e (se houver MongoDB) carrega a coleção
    python dados/gerar_fontes.py --sem-mongo
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import random
import sqlite3
from datetime import date, datetime, timedelta
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
FONTES = RAIZ / "fontes"
random.seed(2026)
HOJE = date.today()
ANO = HOJE.year

# CEPs reais da região (coletados no ViaCEP) — o ETL consulta o ViaCEP para descobrir cidade/bairro.
CEPS = {
    "São João da Boa Vista": ["13875-570", "13874-885", "13875-043", "13877-097", "13876-781", "13876-441", "13870-220", "13874-000"],
    "Aguaí": ["13864-310", "13866-526", "13860-710", "13860-690"],
    "Vargem Grande do Sul": ["13880-232", "13882-606", "13882-614", "13884-496"],
    "Espírito Santo do Pinhal": ["13992-002", "13992-034", "13990-107", "13990-017"],
    "Mococa": ["13750-104", "13734-542", "13739-079", "13731-040"],
    "Casa Branca": ["13703-034", "13703-606", "13708-030"],
    "Águas da Prata": ["13893-207", "13896-032", "13899-006"],
    "São Sebastião da Grama": ["13792-044", "13796-168", "13792-082"],
    "Divinolândia": ["13782-044", "13781-046", "13782-040"],
    "Itapira": ["13973-865", "13988-034"],
    "Mogi Guaçu": ["13846-435", "13848-430", "13841-083"],
    "Poços de Caldas": ["37706-236", "37716-022", "37701-326", "37704-390", "37701-000"],
    "Andradas": ["37841-240", "37840-124", "37841-060"],
}
PESO_CIDADE = {"São João da Boa Vista": 40, "Poços de Caldas": 9, "Vargem Grande do Sul": 8, "Espírito Santo do Pinhal": 7,
               "Aguaí": 7, "Mococa": 6, "Casa Branca": 4, "Águas da Prata": 4, "São Sebastião da Grama": 3,
               "Divinolândia": 3, "Andradas": 4, "Itapira": 2, "Mogi Guaçu": 3}

CURSOS = {
    "Ciência da Computação": ["Algoritmos", "Banco de Dados", "Integração de Dados", "Redes de Computadores", "Engenharia de Software", "Cálculo"],
    "Direito": ["Direito Civil", "Direito Penal", "Direito Constitucional", "Processo Civil", "Filosofia do Direito"],
    "Administração": ["Contabilidade", "Marketing", "Gestão de Pessoas", "Finanças", "Estatística"],
    "Medicina Veterinária": ["Anatomia Animal", "Fisiologia", "Clínica de Pequenos Animais", "Parasitologia", "Bioquímica"],
    "Engenharia Civil": ["Cálculo", "Resistência dos Materiais", "Topografia", "Hidráulica", "Física"],
    "Psicologia": ["Psicologia do Desenvolvimento", "Neurociência", "Psicopatologia", "Estatística", "Teorias da Personalidade"],
    "Enfermagem": ["Anatomia", "Farmacologia", "Saúde Coletiva", "Semiologia", "Microbiologia"],
    "Agronomia": ["Solos", "Fitotecnia", "Química", "Topografia", "Irrigação"],
}
MENSALIDADE = {"Ciência da Computação": 1290.0, "Direito": 1490.0, "Administração": 990.0, "Medicina Veterinária": 2390.0,
               "Engenharia Civil": 1590.0, "Psicologia": 1390.0, "Enfermagem": 1190.0, "Agronomia": 1490.0}

NOMES = ["Ana", "Bruno", "Carla", "Diego", "Eduarda", "Felipe", "Gabriela", "Henrique", "Isabela", "João", "Larissa", "Lucas",
         "Mariana", "Matheus", "Natália", "Otávio", "Paula", "Rafael", "Sofia", "Thiago", "Vitória", "Gustavo", "Beatriz",
         "Leonardo", "Camila", "Pedro", "Júlia", "Vinícius", "Letícia", "Rodrigo", "Amanda", "Caio", "Fernanda", "Murilo",
         "Helena", "Enzo", "Lívia", "Daniel", "Yasmin", "André"]
SOBRENOMES = ["Silva", "Santos", "Oliveira", "Souza", "Rodrigues", "Ferreira", "Alves", "Pereira", "Lima", "Gomes", "Costa",
              "Ribeiro", "Martins", "Carvalho", "Almeida", "Lopes", "Soares", "Fernandes", "Vieira", "Barbosa", "Rocha",
              "Dias", "Nascimento", "Andrade", "Moreira", "Nunes", "Marques", "Machado", "Mendes", "Freitas"]

# Tipos de protocolo da secretaria -> prazo (em dias úteis) definido no regimento fictício
TIPOS = {
    "Declaração de matrícula": 2,
    "Histórico escolar": 5,
    "Revisão de nota": 7,
    "Trancamento de matrícula": 10,
    "Cancelamento de matrícula": 10,
    "Transferência externa": 15,
    "Aproveitamento de disciplinas": 20,
    "Segunda via de diploma": 30,
    "Reclamação / ouvidoria": 5,
}
CANAIS = ["Balcão", "Portal do aluno", "WhatsApp", "E-mail"]
ATENDENTES = ["Cláudia", "Marcos", "Renata", "Sérgio"]


def gerar_cpf() -> str:
    n = [random.randint(0, 9) for _ in range(9)]
    for _ in range(2):
        s = sum(v * p for v, p in zip(n, range(len(n) + 1, 1, -1)))
        d = 11 - s % 11
        n.append(0 if d >= 10 else d)
    return "".join(map(str, n))


def fmt_cpf(c: str) -> str:
    return f"{c[:3]}.{c[3:6]}.{c[6:9]}-{c[9:]}"


def gerar_academico(qtd: int = 620):
    FONTES.mkdir(exist_ok=True)
    caminho = FONTES / "academico.db"
    if caminho.exists():
        caminho.unlink()
    con = sqlite3.connect(caminho)
    con.executescript("""
        CREATE TABLE cursos (id INTEGER PRIMARY KEY, nome TEXT NOT NULL, mensalidade REAL NOT NULL);
        CREATE TABLE disciplinas (id INTEGER PRIMARY KEY, curso_id INTEGER REFERENCES cursos(id), nome TEXT NOT NULL);
        CREATE TABLE alunos (
            ra TEXT PRIMARY KEY, nome TEXT NOT NULL, cpf TEXT NOT NULL UNIQUE, email TEXT, telefone TEXT,
            curso_id INTEGER REFERENCES cursos(id), periodo INTEGER, ano_ingresso INTEGER,
            cep TEXT, situacao TEXT DEFAULT 'ATIVO');
        CREATE TABLE matriculas (
            id INTEGER PRIMARY KEY, ra TEXT REFERENCES alunos(ra), disciplina_id INTEGER REFERENCES disciplinas(id),
            semestre TEXT, nota_p1 REAL, nota_p2 REAL, aulas_dadas INTEGER, faltas INTEGER);
    """)
    disc_ids = {}
    for i, (curso, discs) in enumerate(CURSOS.items(), start=1):
        con.execute("INSERT INTO cursos VALUES (?,?,?)", (i, curso, MENSALIDADE[curso]))
        disc_ids[i] = []
        for d in discs:
            cur = con.execute("INSERT INTO disciplinas (curso_id, nome) VALUES (?,?)", (i, d))
            disc_ids[i].append(cur.lastrowid)

    alunos = []
    cidades = list(PESO_CIDADE)
    pesos = [PESO_CIDADE[c] for c in cidades]
    semestre = f"{ANO}/{1 if HOJE.month <= 6 else 2}"
    for k in range(qtd):
        curso_id = random.randint(1, len(CURSOS))
        periodo = random.randint(1, 10 if curso_id == 4 else 8)
        ingresso = ANO - (periodo - 1) // 2
        ra = f"{ingresso}{k + 1:05d}"
        nome = f"{random.choice(NOMES)} {random.choice(SOBRENOMES)} {random.choice(SOBRENOMES)}"
        cidade = random.choices(cidades, pesos)[0]
        cep = random.choice(CEPS[cidade]).replace("-", "")
        cpf = gerar_cpf()
        # "perfil" oculto: alguns alunos estão em situação de risco (correlação entre as fontes)
        perfil = random.choices(["ok", "atencao", "risco"], [72, 16, 12])[0]
        alunos.append({"ra": ra, "cpf": cpf, "curso_id": curso_id, "perfil": perfil, "cidade": cidade})
        email = f"{nome.split()[0].lower()}.{ra}@sou.unifeob.edu.br"
        tel = f"(19) 9{random.randint(7000, 9999)}-{random.randint(1000, 9999)}"
        con.execute("INSERT INTO alunos VALUES (?,?,?,?,?,?,?,?,?,?)",
                    (ra, nome, cpf, email, tel, curso_id, periodo, ingresso, cep, "ATIVO"))

        for disc in random.sample(disc_ids[curso_id], k=min(4, len(disc_ids[curso_id]))):
            aulas = 72
            if perfil == "ok":
                p1, p2, faltas = random.uniform(5.5, 10), random.uniform(5.5, 10), random.randint(0, 10)
            elif perfil == "atencao":
                p1, p2, faltas = random.uniform(3.5, 8), random.uniform(3.5, 8), random.randint(6, 20)
            else:
                p1, p2, faltas = random.uniform(0.5, 6), random.uniform(0, 6), random.randint(14, 34)
            con.execute("INSERT INTO matriculas (ra, disciplina_id, semestre, nota_p1, nota_p2, aulas_dadas, faltas) VALUES (?,?,?,?,?,?,?)",
                        (ra, disc, semestre, round(p1, 1), round(p2, 1), aulas, faltas))
    con.commit()
    con.close()
    print(f"[SQLite]  {caminho.relative_to(RAIZ)}  ->  {qtd} alunos")
    return alunos


def gerar_financeiro(alunos):
    caminho = FONTES / "financeiro_mensalidades.csv"
    linhas = 0
    with open(caminho, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(["CPF_ALUNO", "COMPETENCIA", "VENCIMENTO", "VALOR", "DATA_PAGAMENTO", "STATUS"])
        curso_nome = list(CURSOS)
        for a in alunos:
            valor = MENSALIDADE[curso_nome[a["curso_id"] - 1]]
            prob_atraso = {"ok": 0.03, "atencao": 0.18, "risco": 0.45}[a["perfil"]]
            for mes in range(1, HOJE.month + 1):
                venc = date(ANO, mes, 10)
                if venc > HOJE:
                    status, pag = "A VENCER", ""
                elif random.random() < prob_atraso and mes >= HOJE.month - 4:
                    status, pag = "ATRASADO", ""
                else:
                    status = "PAGO"
                    pag = (venc + timedelta(days=random.randint(-8, 6))).strftime("%d/%m/%Y")
                desconto = random.choice([1, 1, 1, 0.9, 0.8])  # bolsas / descontos
                w.writerow([fmt_cpf(a["cpf"]), f"{mes:02d}/{ANO}", venc.strftime("%d/%m/%Y"),
                            f"{valor * desconto:.2f}".replace(".", ","), pag, status])
                linhas += 1
    print(f"[CSV]     {caminho.relative_to(RAIZ)}  ->  {linhas} parcelas")


def peso_mes(m: int) -> float:
    # sazonalidade: matrícula (fev), fim de semestre (jun/jul), rematrícula (ago), provas (nov/dez)
    return {1: 0.7, 2: 2.0, 3: 1.2, 4: 0.8, 5: 0.9, 6: 1.5, 7: 1.6, 8: 1.9, 9: 0.9, 10: 0.9, 11: 1.4, 12: 1.2}[m]


def detalhes_por_tipo(tipo: str, curso: str):
    d = random.choice(CURSOS[curso])
    if tipo == "Declaração de matrícula":
        return {"finalidade": random.choice(["Estágio", "Transporte (passe escolar)", "Empresa", "Plano de saúde"]), "vias": random.randint(1, 2)}
    if tipo == "Histórico escolar":
        return {"formato": random.choice(["Digital", "Impresso"]), "finalidade": random.choice(["Estágio", "Intercâmbio", "Concurso"])}
    if tipo == "Revisão de nota":
        return {"disciplina": d, "avaliacao": random.choice(["P1", "P2", "Exame"]), "nota_atual": round(random.uniform(2, 6.9), 1)}
    if tipo in ("Trancamento de matrícula", "Cancelamento de matrícula"):
        return {"motivo": random.choice(["Financeiro", "Trabalho", "Saúde", "Mudança de cidade", "Insatisfação com o curso"])}
    if tipo == "Transferência externa":
        return {"instituicao_destino": random.choice(["Universidade A", "Faculdade B", "Centro Universitário C"])}
    if tipo == "Aproveitamento de disciplinas":
        return {"instituicao_origem": random.choice(["ETEC", "Universidade X", "Faculdade Y"]),
                "disciplinas": random.sample(CURSOS[curso], k=2)}
    if tipo == "Segunda via de diploma":
        return {"motivo": random.choice(["Extravio", "Dano"]), "ano_conclusao": ANO - random.randint(1, 10)}
    return {"assunto": random.choice(["Demora no atendimento", "Problema no portal", "Cobrança indevida", "Falta de professor"]),
            "descricao": "Registro feito pelo canal de ouvidoria."}


def somar_dias_uteis_simples(inicio: date, n: int) -> date:
    d = inicio
    while n > 0:
        d += timedelta(days=1)
        if d.weekday() < 5:
            n -= 1
    return d


def gerar_atendimentos(alunos, qtd: int = 1700):
    curso_nome = list(CURSOS)
    docs = []
    inicio = date(ANO, 1, 5)
    dias = [inicio + timedelta(days=i) for i in range((HOJE - inicio).days + 1)]
    dias = [d for d in dias if d.weekday() < 6]
    pesos_dia = [peso_mes(d.month) for d in dias]
    for i in range(qtd):
        a = random.choice(alunos)
        curso = curso_nome[a["curso_id"] - 1]
        if a["perfil"] == "risco" and random.random() < 0.35:
            tipo = random.choice(["Trancamento de matrícula", "Cancelamento de matrícula", "Reclamação / ouvidoria", "Revisão de nota"])
        else:
            tipo = random.choices(list(TIPOS), [30, 14, 12, 3, 2, 2, 8, 2, 5])[0]
        aberto = random.choices(dias, pesos_dia)[0]
        aberto_dt = datetime.combine(aberto, datetime.min.time()) + timedelta(hours=random.randint(8, 20), minutes=random.randint(0, 59))
        prazo = TIPOS[tipo]
        # duração real: a maioria dentro do prazo, alguns estouram
        duracao = max(0, int(random.gauss(prazo * 0.8, prazo * 0.5)))
        fim = somar_dias_uteis_simples(aberto, duracao)
        historico = [{"status": "ABERTO", "em": aberto_dt.isoformat(), "por": "sistema"}]
        if fim <= HOJE - timedelta(days=1) and random.random() > 0.04:
            status = "CONCLUIDO"
            concluido = datetime.combine(fim, datetime.min.time()) + timedelta(hours=random.randint(9, 17))
            historico.append({"status": "EM_ANDAMENTO", "em": (aberto_dt + timedelta(hours=3)).isoformat(), "por": random.choice(ATENDENTES)})
            historico.append({"status": "CONCLUIDO", "em": concluido.isoformat(), "por": random.choice(ATENDENTES)})
        else:
            status = random.choice(["ABERTO", "EM_ANDAMENTO"])
            concluido = None
            if status == "EM_ANDAMENTO":
                historico.append({"status": "EM_ANDAMENTO", "em": (aberto_dt + timedelta(hours=5)).isoformat(), "por": random.choice(ATENDENTES)})
        doc = {
            "protocolo": f"SEC-{ANO}-{i + 1:05d}",
            "ra": a["ra"],
            "tipo": tipo,
            "canal": random.choices(CANAIS, [35, 35, 20, 10])[0],
            "status": status,
            "aberto_em": aberto_dt.isoformat(),
            "concluido_em": concluido.isoformat() if concluido else None,
            "detalhes": detalhes_por_tipo(tipo, curso),
            "historico": historico,
        }
        if status == "CONCLUIDO" and random.random() < 0.5:
            doc["avaliacao_atendimento"] = random.choices([1, 2, 3, 4, 5], [5, 7, 15, 35, 38])[0]
        docs.append(doc)
    docs.sort(key=lambda d: d["aberto_em"])
    caminho = FONTES / "atendimentos.json"
    caminho.write_text(json.dumps(docs, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"[MongoDB] {caminho.relative_to(RAIZ)}  ->  {len(docs)} protocolos (formato de importação)")
    return docs


def carregar_mongo(docs):
    uri = os.getenv("MONGO_URI", "mongodb://localhost:27017")
    try:
        import pymongo
        cli = pymongo.MongoClient(uri, serverSelectionTimeoutMS=2500)
        cli.admin.command("ping")
    except Exception as e:  # noqa: BLE001
        print(f"[MongoDB] servidor não encontrado em {uri} ({type(e).__name__}). "
              "O backend usará o modo embutido (mongomock) a partir do JSON.")
        return
    col = cli[os.getenv("MONGO_DB", "secretaria_unifeob")]["atendimentos"]
    col.drop()
    col.insert_many([dict(d) for d in docs])
    col.create_index("protocolo", unique=True)
    col.create_index("ra")
    print(f"[MongoDB] {len(docs)} documentos carregados em {uri}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--sem-mongo", action="store_true")
    args = ap.parse_args()
    alunos = gerar_academico()
    gerar_financeiro(alunos)
    docs = gerar_atendimentos(alunos)
    if not args.sem_mongo:
        carregar_mongo(docs)
    print("Fontes geradas com sucesso.")
