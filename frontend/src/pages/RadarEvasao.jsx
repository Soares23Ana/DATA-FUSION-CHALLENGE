import { useEffect, useState } from 'react'
import { api, brl } from '../api.js'
import { BarraScore, Cartao, Carregando, Erro, LegendaScore, Nivel } from '../components.jsx'

export default function RadarEvasao({ abrirAluno }) {
  const [f, setF] = useState({ nivel: 'ALTO', curso: '', cidade: '', busca: '' })
  const [opcoes, setOpcoes] = useState({ cursos: [], cidades: [] })
  const [linhas, setLinhas] = useState(null)
  const [erro, setErro] = useState('')

  useEffect(() => { api.filtros().then(setOpcoes).catch(() => {}) }, [])
  useEffect(() => {
    const t = setTimeout(() => api.risco(f).then(setLinhas).catch((e) => setErro(e.message)), 250)
    return () => clearTimeout(t)
  }, [f])

  const set = (campo) => (e) => setF({ ...f, [campo]: e.target.value })

  return (
    <Cartao titulo="Radar de evasão" fonte="SQLite + CSV + MongoDB → DuckDB">
      <p className="nota">
        Score de 0 a 100 que soma <b>frequência</b> (até 35 pts), <b>notas</b> (25), <b>mensalidades atrasadas</b> (25) e{' '}
        <b>protocolos de saída/reclamação</b> (15). Nenhuma fonte sozinha mostra esse aluno; o risco só aparece quando juntamos as três.
      </p>
      <div className="filtros">
        <select value={f.nivel} onChange={set('nivel')}>
          <option value="">Todos os níveis</option><option>ALTO</option><option>MÉDIO</option><option>BAIXO</option>
        </select>
        <select value={f.curso} onChange={set('curso')}>
          <option value="">Todos os cursos</option>{opcoes.cursos.map((c) => <option key={c}>{c}</option>)}
        </select>
        <select value={f.cidade} onChange={set('cidade')}>
          <option value="">Todas as cidades</option>{opcoes.cidades.map((c) => <option key={c}>{c}</option>)}
        </select>
        <input placeholder="Buscar nome ou RA" value={f.busca} onChange={set('busca')} />
        <LegendaScore />
      </div>
      {erro && <Erro msg={erro} />}
      {!linhas ? <Carregando /> : (
        <div className="tabela-rolagem">
          <table>
            <thead>
              <tr><th>Aluno</th><th>Curso</th><th>Cidade</th><th className="num">Freq.</th><th className="num">Média</th>
                <th className="num">Parc. atras.</th><th className="num">Em aberto</th><th>Score</th><th>Nível</th><th>Ação sugerida</th></tr>
            </thead>
            <tbody>
              {linhas.map((r) => (
                <tr key={r.ra} className="clicavel" onClick={() => abrirAluno(r.ra)}>
                  <td><b>{r.nome}</b><br /><small>RA {r.ra} · {r.periodo}º período</small></td>
                  <td>{r.curso}</td>
                  <td>{r.cidade}</td>
                  <td className={`num ${r.frequencia_media < 75 ? 'txt-perigo' : ''}`}>{r.frequencia_media}%</td>
                  <td className={`num ${r.media_geral < 6 ? 'txt-perigo' : ''}`}>{r.media_geral.toFixed(1)}</td>
                  <td className="num">{r.parcelas_atrasadas}</td>
                  <td className="num">{brl(r.valor_em_aberto)}</td>
                  <td><BarraScore r={r} /></td>
                  <td><Nivel v={r.nivel_risco} /></td>
                  <td className="acao">{r.acao_sugerida}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="nota">{linhas.length} alunos · clique em um aluno para ver a visão 360°</p>
        </div>
      )}
    </Cartao>
  )
}
