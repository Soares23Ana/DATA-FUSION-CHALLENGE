import { useEffect, useState } from 'react'
import { Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { api } from '../api.js'
import { Cartao, Carregando, Erro } from '../components.jsx'

export default function OrigemAlunos() {
  const [dados, setDados] = useState(null)
  const [erro, setErro] = useState('')
  useEffect(() => { api.origem().then(setDados).catch((e) => setErro(e.message)) }, [])

  if (erro) return <Erro msg={erro} />
  if (!dados) return <Carregando />
  const total = dados.reduce((s, d) => s + d.alunos, 0)
  const sede = dados.find((d) => d.cidade === 'São João da Boa Vista')
  const fora = total - (sede?.alunos || 0)
  const maiorRisco = [...dados].filter((d) => d.alunos >= 15).sort((a, b) => b.pct_risco_alto - a.pct_risco_alto)[0]

  return (
    <>
      <div className="grade-kpi">
        <div className="kpi"><span className="kpi-rotulo">Cidades atendidas</span><strong className="kpi-valor">{dados.length}</strong><span className="kpi-detalhe">identificadas pelo CEP (ViaCEP)</span></div>
        <div className="kpi alerta"><span className="kpi-rotulo">Alunos de fora da sede</span><strong className="kpi-valor">{Math.round((100 * fora) / total)}%</strong><span className="kpi-detalhe">{fora} alunos se deslocam até a sede</span></div>
        {maiorRisco && <div className="kpi perigo"><span className="kpi-rotulo">Cidade com mais risco</span><strong className="kpi-valor">{maiorRisco.cidade}</strong><span className="kpi-detalhe">{maiorRisco.pct_risco_alto}% dos alunos em risco alto</span></div>}
      </div>
      <Cartao titulo="Alunos por cidade de origem" fonte="SQLite (CEP) + ViaCEP → DuckDB">
        <ResponsiveContainer width="100%" height={420}>
          <BarChart data={dados} layout="vertical" margin={{ left: 60, right: 20 }}>
            <CartesianGrid horizontal={false} stroke="var(--grade)" />
            <XAxis type="number" tick={{ fontSize: 12 }} />
            <YAxis type="category" dataKey="cidade" width={170} tick={{ fontSize: 12 }} />
            <Tooltip formatter={(v, n, p) => (n === 'Em risco alto' ? `${v} (${p.payload.pct_risco_alto}%)` : v)} />
            <Legend />
            <Bar dataKey="alunos" name="Alunos" fill="var(--primaria)" />
            <Bar dataKey="risco_alto" name="Em risco alto" fill="var(--perigo)" />
          </BarChart>
        </ResponsiveContainer>
        <p className="nota">
          Esses dados ajudam a decidir onde fazer parcerias de transporte, atendimento on-line da secretaria (para quem mora longe) e onde concentrar a captação de alunos.
        </p>
      </Cartao>
    </>
  )
}
