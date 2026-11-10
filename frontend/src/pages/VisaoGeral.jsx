import { useEffect, useState } from 'react'
import { Bar, BarChart, CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { api, brl } from '../api.js'
import { Cartao, Carregando, Erro, Kpi } from '../components.jsx'

const MESES = ['jan', 'fev', 'mar', 'abr', 'mai', 'jun', 'jul', 'ago', 'set', 'out', 'nov', 'dez']

export default function VisaoGeral({ status, aoRecarregar }) {
  const [k, setK] = useState(null)
  const [ind, setInd] = useState(null)
  const [erro, setErro] = useState('')
  const [rodando, setRodando] = useState(false)

  useEffect(() => {
    Promise.all([api.kpis(), api.indicadores()]).then(([a, b]) => { setK(a); setInd(b) }).catch((e) => setErro(e.message))
  }, [])

  const rodarEtl = async () => {
    setRodando(true)
    try { await api.executarEtl(); aoRecarregar() } catch (e) { setErro(e.message) } finally { setRodando(false) }
  }

  if (erro) return <Erro msg={erro} />
  if (!k) return <Carregando />
  const carga = status?.ultima_carga
  const porMes = ind.por_mes.map((m) => ({ ...m, rotulo: MESES[Number(m.mes.slice(5)) - 1] }))

  return (
    <>
      <div className="grade-kpi">
        <Kpi rotulo="Alunos ativos" valor={k.alunos_ativos} detalhe="sistema acadêmico" />
        <Kpi rotulo="Risco alto de evasão" valor={k.alunos_risco_alto} detalhe={`+${k.alunos_risco_medio} em risco médio`} tom="perigo" />
        <Kpi rotulo="Receita em risco" valor={brl(k.receita_em_risco)} detalhe="em aberto de alunos em risco alto" tom="alerta" />
        <Kpi rotulo="Protocolos abertos" valor={k.protocolos_abertos} detalhe={`${k.protocolos_atrasados} fora do prazo`} tom={k.protocolos_atrasados ? 'perigo' : ''} />
        <Kpi rotulo="Concluídos no prazo" valor={`${k.pct_sla_cumprido}%`} detalhe="prazo em dias úteis" />
        <Kpi rotulo="Satisfação" valor={`${k.satisfacao_media} / 5`} detalhe="avaliação dos atendimentos" />
      </div>

      <div className="grade-2">
        <Cartao titulo="Risco de evasão por curso" fonte="DuckDB · vw_risco_evasao">
          <ResponsiveContainer width="100%" height={280}>
            <BarChart data={k.por_curso} layout="vertical" margin={{ left: 40, right: 16 }}>
              <CartesianGrid horizontal={false} stroke="var(--grade)" />
              <XAxis type="number" unit="%" tick={{ fontSize: 12 }} />
              <YAxis type="category" dataKey="curso" width={150} tick={{ fontSize: 12 }} />
              <Tooltip formatter={(v, n) => (n === 'pct_risco_alto' ? `${v}%` : v)} />
              <Bar dataKey="pct_risco_alto" name="% alunos em risco alto" fill="var(--perigo)" radius={[0, 4, 4, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </Cartao>

        <Cartao titulo="Demanda da secretaria por mês" fonte="MongoDB → DuckDB">
          <ResponsiveContainer width="100%" height={280}>
            <LineChart data={porMes} margin={{ right: 16 }}>
              <CartesianGrid vertical={false} stroke="var(--grade)" />
              <XAxis dataKey="rotulo" tick={{ fontSize: 12 }} />
              <YAxis tick={{ fontSize: 12 }} />
              <Tooltip />
              <Legend />
              <Line dataKey="total" name="Total" stroke="var(--primaria)" strokeWidth={2.5} dot={false} />
              <Line dataKey="declaracoes" name="Declarações" stroke="var(--c2)" strokeWidth={2} dot={false} />
              <Line dataKey="saidas" name="Tranc./Cancel./Transf." stroke="var(--perigo)" strokeWidth={2} dot={false} />
            </LineChart>
          </ResponsiveContainer>
          <p className="nota">Os picos de fevereiro e agosto (matrícula e rematrícula) mostram quando reforçar a equipe do balcão.</p>
        </Cartao>
      </div>

      <Cartao titulo="Integração de dados" fonte="etl_execucao" acoes={
        <button className="botao" onClick={rodarEtl} disabled={rodando}>{rodando ? 'Executando carga…' : 'Executar carga agora'}</button>
      }>
        <div className="fluxo">
          <div className="no"><b>SQLite</b><span>Sistema acadêmico</span><small>alunos, notas, faltas</small></div>
          <div className="no"><b>CSV</b><span>ERP financeiro</span><small>mensalidades (chave CPF)</small></div>
          <div className="no"><b>MongoDB</b><span>Protocolos</span><small>{status?.mongo?.includes('embutido') ? 'modo embutido' : 'servidor real'}</small></div>
          <div className="seta">→</div>
          <div className="no destaque"><b>Apache Hop</b><span>consolidar_aluno.hpl</span><small>+ ViaCEP · BrasilAPI</small></div>
          <div className="seta">→</div>
          <div className="no destaque"><b>DuckDB</b><span>Data warehouse</span><small>risco, SLA, origem</small></div>
        </div>
        {carga && (
          <p className="nota">
            Última carga: {new Date(carga.executado_em).toLocaleString('pt-BR')} · consolidação via <b>{carga.origem_consolidacao}</b> ·{' '}
            {carga.alunos} alunos · {carga.parcelas} parcelas · {carga.protocolos} protocolos · {carga.ceps_enriquecidos} CEPs (ViaCEP) ·{' '}
            {carga.feriados} feriados (BrasilAPI) · {carga.duracao_s}s
          </p>
        )}
      </Cartao>
    </>
  )
}
