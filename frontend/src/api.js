// Cliente da API FastAPI (o Vite faz proxy de /api para http://localhost:8000)
async function req(caminho, opcoes = {}) {
  const r = await fetch(`/api${caminho}`, {
    headers: { 'Content-Type': 'application/json' },
    ...opcoes,
  })
  const corpo = await r.json().catch(() => ({}))
  if (!r.ok) throw new Error(corpo.detail || `Erro ${r.status}`)
  return corpo
}

const qs = (obj) => {
  const p = new URLSearchParams(Object.entries(obj).filter(([, v]) => v !== '' && v != null))
  return p.toString() ? `?${p}` : ''
}

export const api = {
  status: () => req('/status'),
  kpis: () => req('/kpis'),
  filtros: () => req('/filtros'),
  risco: (f) => req(`/risco${qs(f)}`),
  fila: (f) => req(`/atendimentos/fila${qs(f)}`),
  indicadores: () => req('/atendimentos/indicadores'),
  origem: () => req('/origem'),
  aluno: (ra) => req(`/alunos/${encodeURIComponent(ra)}`),
  feriados: (ano) => req(`/feriados/${ano}`),
  abrirProtocolo: (dados) => req('/atendimentos', { method: 'POST', body: JSON.stringify(dados) }),
  executarEtl: () => req('/etl/executar', { method: 'POST' }),
}

export const brl = (v) => (v ?? 0).toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' })
export const dataBR = (iso) => (iso ? new Date(iso.length === 10 ? iso + 'T12:00' : iso).toLocaleDateString('pt-BR') : '—')
