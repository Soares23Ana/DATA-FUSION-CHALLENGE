"""
Conexões com as fontes operacionais.

MongoDB: usa o servidor real definido em MONGO_URI. Se não houver servidor disponível,
cai para um MongoDB embutido em memória (mongomock) carregado do fontes/atendimentos.json,
e grava de volta no JSON a cada inserção — assim a demonstração funciona em qualquer máquina.
"""
from __future__ import annotations

import json
import sqlite3
import threading

from .config import JSON_ATENDIMENTOS, MONGO_DB, MONGO_URI, SQLITE_ACADEMICO

_mongo_col = None
_mongo_modo = None
_lock = threading.Lock()


def sqlite_academico() -> sqlite3.Connection:
    con = sqlite3.connect(SQLITE_ACADEMICO, check_same_thread=False)
    con.row_factory = sqlite3.Row
    return con


def mongo_atendimentos():
    """Retorna a coleção 'atendimentos' (pymongo ou mongomock)."""
    global _mongo_col, _mongo_modo
    with _lock:
        if _mongo_col is not None:
            return _mongo_col
        try:
            import pymongo
            cli = pymongo.MongoClient(MONGO_URI, serverSelectionTimeoutMS=2000)
            cli.admin.command("ping")
            _mongo_col = cli[MONGO_DB]["atendimentos"]
            _mongo_modo = f"MongoDB real ({MONGO_URI})"
            if _mongo_col.estimated_document_count() == 0 and JSON_ATENDIMENTOS.exists():
                _mongo_col.insert_many(json.loads(JSON_ATENDIMENTOS.read_text(encoding="utf-8")))
        except Exception:  # noqa: BLE001
            import mongomock
            _mongo_col = mongomock.MongoClient()[MONGO_DB]["atendimentos"]
            if JSON_ATENDIMENTOS.exists():
                _mongo_col.insert_many(json.loads(JSON_ATENDIMENTOS.read_text(encoding="utf-8")))
            _mongo_modo = "MongoDB embutido (mongomock) — inicie um MongoDB real e defina MONGO_URI"
        print(f"[MongoDB] {_mongo_modo}")
        return _mongo_col


def modo_mongo() -> str:
    mongo_atendimentos()
    return _mongo_modo


def persistir_se_embutido() -> None:
    """No modo mongomock, salva a coleção no JSON para não perder protocolos criados na demo."""
    if _mongo_modo and _mongo_modo.startswith("MongoDB embutido"):
        docs = list(_mongo_col.find({}, {"_id": 0}).sort("aberto_em", 1))
        JSON_ATENDIMENTOS.write_text(json.dumps(docs, ensure_ascii=False, indent=1), encoding="utf-8")
