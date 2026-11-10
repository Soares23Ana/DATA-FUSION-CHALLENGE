"""Cálculo de prazos em DIAS ÚTEIS considerando fins de semana e feriados (BrasilAPI + municipais)."""
from __future__ import annotations

from datetime import date, timedelta
from functools import lru_cache

from .apis_externas import feriados


@lru_cache(maxsize=16)
def _dias_nao_uteis(ano: int) -> frozenset[date]:
    return frozenset(date.fromisoformat(f["data"]) for f in feriados(ano))


def eh_dia_util(d: date) -> bool:
    return d.weekday() < 5 and d not in _dias_nao_uteis(d.year)


def somar_dias_uteis(inicio: date, n: int) -> date:
    d = inicio
    while n > 0:
        d += timedelta(days=1)
        if eh_dia_util(d):
            n -= 1
    return d


def dias_uteis_entre(inicio: date, fim: date) -> int:
    """Quantidade de dias úteis em (inicio, fim]. Negativo se fim < inicio."""
    if fim < inicio:
        return -dias_uteis_entre(fim, inicio)
    n, d = 0, inicio
    while d < fim:
        d += timedelta(days=1)
        if eh_dia_util(d):
            n += 1
    return n
