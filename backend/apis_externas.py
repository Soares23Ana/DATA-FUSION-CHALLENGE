"""
Consumo das APIs externas, com cache local (para não sobrecarregar as APIs e funcionar offline na apresentação).

  - BrasilAPI  /api/feriados/v1/{ano}  -> feriados nacionais (usados no cálculo de prazo em dias úteis)
  - ViaCEP     /ws/{cep}/json/          -> cidade, bairro e UF do aluno (enriquecimento geográfico)
"""
from __future__ import annotations

import json
import threading
from datetime import date

import httpx

from .config import CACHE_APIS, FERIADOS_MUNICIPAIS

_lock = threading.Lock()


def _ler_cache() -> dict:
    if CACHE_APIS.exists():
        return json.loads(CACHE_APIS.read_text(encoding="utf-8"))
    return {"feriados": {}, "cep": {}}


def _salvar_cache(cache: dict) -> None:
    CACHE_APIS.parent.mkdir(exist_ok=True)
    CACHE_APIS.write_text(json.dumps(cache, ensure_ascii=False, indent=1), encoding="utf-8")


def feriados(ano: int) -> list[dict]:
    """Feriados nacionais (BrasilAPI) + municipais de São João da Boa Vista."""
    with _lock:
        cache = _ler_cache()
        lista = cache["feriados"].get(str(ano))
        if lista is None:
            try:
                r = httpx.get(f"https://brasilapi.com.br/api/feriados/v1/{ano}", timeout=10)
                r.raise_for_status()
                lista = [{"data": f["date"], "nome": f["name"], "tipo": "nacional"} for f in r.json()]
                cache["feriados"][str(ano)] = lista
                _salvar_cache(cache)
            except Exception as e:  # noqa: BLE001
                print(f"[BrasilAPI] indisponível ({e}); seguindo só com feriados municipais")
                lista = []
    municipais = [{"data": f"{ano}-{md}", "nome": nome, "tipo": "municipal"} for md, nome in FERIADOS_MUNICIPAIS.items()]
    return sorted(lista + municipais, key=lambda f: f["data"])


def consultar_cep(cep: str, cache: dict | None = None) -> dict:
    """Retorna {cep, cidade, uf, bairro, logradouro} via ViaCEP (com cache)."""
    cep = "".join(ch for ch in str(cep) if ch.isdigit()).zfill(8)
    proprio = cache is None
    if proprio:
        cache = _ler_cache()
    if cep in cache["cep"]:
        return cache["cep"][cep]
    try:
        r = httpx.get(f"https://viacep.com.br/ws/{cep}/json/", timeout=10)
        j = r.json()
        if j.get("erro"):
            info = {"cep": cep, "cidade": None, "uf": None, "bairro": None, "logradouro": None}
        else:
            info = {"cep": cep, "cidade": j["localidade"], "uf": j["uf"], "bairro": j.get("bairro"), "logradouro": j.get("logradouro")}
    except Exception as e:  # noqa: BLE001
        print(f"[ViaCEP] falha para {cep}: {e}")
        return {"cep": cep, "cidade": None, "uf": None, "bairro": None, "logradouro": None}
    cache["cep"][cep] = info
    if proprio:
        _salvar_cache(cache)
    return info


def enriquecer_ceps(ceps: list[str]) -> dict[str, dict]:
    """Consulta vários CEPs de uma vez reaproveitando o cache (usado no ETL)."""
    with _lock:
        cache = _ler_cache()
        unicos = sorted({"".join(c for c in str(x) if c.isdigit()).zfill(8) for x in ceps if x})
        novos = [c for c in unicos if c not in cache["cep"]]
        if novos:
            print(f"[ViaCEP] consultando {len(novos)} CEPs novos (demais vêm do cache)...")
        for c in novos:
            consultar_cep(c, cache)
        _salvar_cache(cache)
        return {c: cache["cep"].get(c, {"cep": c, "cidade": None, "uf": None}) for c in unicos}


def hoje() -> date:
    return date.today()
