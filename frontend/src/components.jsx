export function Kpi({ rotulo, valor, detalhe, tom }) {
  return (
    <div className={`kpi ${tom || ''}`}>
      <span className="kpi-rotulo">{rotulo}</span>
      <strong className="kpi-valor">{valor}</strong>
      {detalhe && <span className="kpi-detalhe">{detalhe}</span>}
    </div>
  )
}

export function Cartao({ titulo, fonte, children, acoes }) {
  return (
    <section className="cartao">
      {(titulo || fonte || acoes) && (
        <div className="cartao-topo">
          <h2>{titulo}</h2>
          <div className="cartao-acoes">
            {fonte && <span className="fonte">{fonte}</span>}
            {acoes}
          </div>
        </div>
      )}
      {children}
    </section>
  )
}

const CORES_NIVEL = { ALTO: 'perigo', 'MÉDIO': 'alerta', BAIXO: 'ok' }
const CORES_SLA = { ATRASADO: 'perigo', 'VENCE EM BREVE': 'alerta', 'NO PRAZO': 'ok', 'FORA DO PRAZO': 'perigo' }

export const Nivel = ({ v }) => (v ? <span className={`selo ${CORES_NIVEL[v]}`}>{v}</span> : '—')
export const Sla = ({ v }) => (v ? <span className={`selo ${CORES_SLA[v] || ''}`}>{v}</span> : '—')

// Barra empilhada mostrando de onde vem cada ponto do score (explicabilidade)
export function BarraScore({ r }) {
  const partes = [
    ['Frequência', r.pts_frequencia, 'c1'],
    ['Notas', r.pts_notas, 'c2'],
    ['Financeiro', r.pts_financeiro, 'c3'],
    ['Protocolos', r.pts_protocolos, 'c4'],
  ]
  return (
    <div className="score">
      <div className="score-barra" title={partes.map(([n, v]) => `${n}: ${v}`).join(' · ')}>
        {partes.map(([n, v, c]) => v > 0 && <span key={n} className={c} style={{ width: `${v}%` }} />)}
      </div>
      <b>{r.score_risco}</b>
    </div>
  )
}

export const LegendaScore = () => (
  <div className="legenda">
    <span><i className="c1" />Frequência (SQLite)</span>
    <span><i className="c2" />Notas (SQLite)</span>
    <span><i className="c3" />Financeiro (CSV)</span>
    <span><i className="c4" />Protocolos (MongoDB)</span>
  </div>
)

export const Carregando = () => <div className="carregando">Carregando…</div>
export const Erro = ({ msg }) => <div className="erro">⚠ {msg}</div>
