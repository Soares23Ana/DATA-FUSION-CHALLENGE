"""Configurações centrais do projeto (caminhos e variáveis de ambiente)."""
import os
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
FONTES = RAIZ / "fontes"
STAGING = RAIZ / "staging"
DW_DIR = RAIZ / "dw"

SQLITE_ACADEMICO = FONTES / "academico.db"
CSV_FINANCEIRO = FONTES / "financeiro_mensalidades.csv"
JSON_ATENDIMENTOS = FONTES / "atendimentos.json"
DUCKDB_DW = DW_DIR / "secretaria_dw.duckdb"
CACHE_APIS = STAGING / "cache_apis.json"

# Saída do pipeline do Apache Hop (se existir, o ETL usa este arquivo como consolidado do aluno)
HOP_SAIDA_ALUNO = STAGING / "aluno_consolidado_hop.csv"

MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
MONGO_DB = os.getenv("MONGO_DB", "secretaria_unifeob")

# Município-sede (feriados municipais não vêm da BrasilAPI)
FERIADOS_MUNICIPAIS = {  # São João da Boa Vista - SP
    "06-24": "Padroeiro São João Batista (municipal)",
    "04-05": "Aniversário de São João da Boa Vista (municipal)",
}

# Prazos regimentais (dias úteis) por tipo de protocolo
PRAZOS_DIAS_UTEIS = {
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
TIPOS_SINAL_EVASAO = ["Trancamento de matrícula", "Cancelamento de matrícula", "Transferência externa", "Reclamação / ouvidoria"]
