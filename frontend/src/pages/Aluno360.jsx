import { useEffect, useState } from 'react'
import { api, brl, dataBR } from '../api.js'
import { BarraScore, Cartao, Carregando, Erro, LegendaScore, Nivel, Sla } from '../components.jsx'

export default function Aluno360({ raInicial }) {
  const [ra, setRa] = useState(raInicial || '')
  const [d, setD] = useState(null)
  const [erro, setErro] = useState('')
  const [carregando, setCarregando] = useState(false)

  const buscar = async (valor) => {
    if (!valor) return
    setErro(''); setCarregando(true)
    try { setD(await api.aluno(valor.trim())) } catch (e) { setErro(e.message); setD(null) } finally { setCarregando(false) }
  }
  useEffect(() => { if (raInicial) buscar(raInicial) }, [raInicial])

  return (
    <>
      <Cartao titulo="Visão 360° do aluno" fonte="consulta ao vivo em 4 fontes">
        <form className="filtros" onSubmit={(e) => { e.preventDefault(); buscar(ra) }}>
          <input value={ra} onChange={(e) => setRa(e.target.value)} placeholder="Digite o RA (ou clique em um aluno no Radar)" />
          <button className="botao">Consultar</button>
        </form>
        {erro && <Erro msg={erro} />}
        {carregando && <Carregando />}
      </Cartao>

      {d && (
        <>
          <div className="grade-2">
            <Cartao titulo={d.aluno.nome} fonte="SQLite · ViaCEP">
              <dl className="ficha">
                <dt>RA</dt><dd>{d.aluno.ra}</dd>
                <dt>Curso</dt><dd>{d.aluno.curso} · {d.aluno.periodo}º período</dd>
                <dt>Ingresso</dt><dd>{d.aluno.ano_ingresso}</dd>
                <dt>E-mail</dt><dd>{d.aluno.email}</dd>
                <dt>Telefone</dt><dd>{d.aluno.telefone}</dd>
                <dt>Endereço</dt><dd>{d.endereco.logradouro ? `${d.endereco.logradouro}, ${d.endereco.bairro} — ` : ''}{d.endereco.cidade ?? 'CEP não localizado'}/{d.endereco.uf} · CEP {d.aluno.cep}</dd>
              </dl>
            </Cartao>
            <Cartao titulo="Risco de evasão" fonte="DuckDB · vw_risco_evasao">
              {d.risco ? (
                <>
                  <div className="risco-topo"><Nivel v={d.risco.nivel_risco} /><BarraScore r={d.risco} /></div>
                  <LegendaScore />
                  <ul className="fatores">
                    <li>Frequência média <b>{d.risco.frequencia_media}%</b> → {d.risco.pts_frequencia} pts</li>
                    <li>Média geral <b>{d.risco.media_geral}</b> ({d.risco.disciplinas_em_risco} disciplinas em risco) → {d.risco.pts_notas} pts</li>
                    <li><b>{d.risco.parcelas_atrasadas}</b> parcelas atrasadas ({brl(d.risco.valor_em_aberto)}) → {d.risco.pts_financeiro} pts</li>
                    <li><b>{d.risco.protocolos_sinal_evasao}</b> protocolos de saída/reclamação → {d.risco.pts_protocolos} pts</li>
                  </ul>
                  <div className="resultado"><b>Ação sugerida:</b> {d.risco.acao_sugerida}</div>
                </>
              ) : <p>Sem dados no DW.</p>}
            </Cartao>
          </div>

          <div className="grade-2">
            <Cartao titulo="Desempenho no semestre" fonte="SQLite">
              <table>
                <thead><tr><th>Disciplina</th><th className="num">P1</th><th className="num">P2</th><th className="num">Média</th><th className="num">Freq.</th></tr></thead>
                <tbody>{d.disciplinas.map((x) => (
                  <tr key={x.disciplina}><td>{x.disciplina}</td><td className="num">{x.nota_p1}</td><td className="num">{x.nota_p2}</td>
                    <td className={`num ${x.media < 6 ? 'txt-perigo' : ''}`}>{x.media}</td>
                    <td className={`num ${x.frequencia < 75 ? 'txt-perigo' : ''}`}>{x.frequencia}%</td></tr>
                ))}</tbody>
              </table>
            </Cartao>
            <Cartao titulo="Mensalidades" fonte="CSV financeiro → DuckDB">
              <div className="parcelas">
                {d.mensalidades.map((m) => (
                  <span key={m.competencia} className={`parcela ${m.status === 'ATRASADO' ? 'atrasada' : m.status === 'PAGO' ? 'paga' : ''}`} title={`${brl(m.valor)} · venc. ${dataBR(m.vencimento)}`}>
                    {m.competencia.slice(0, 2)}
                  </span>
                ))}
              </div>
              <div className="legenda"><span><i className="paga" />Pago</span><span><i className="atrasada" />Atrasado</span><span><i />A vencer</span></div>
            </Cartao>
          </div>

          <Cartao titulo={`Protocolos na secretaria (${d.protocolos.length})`} fonte={d.fontes.protocolos.startsWith('MongoDB real') ? 'MongoDB' : 'MongoDB (embutido)'}>
            {d.protocolos.length === 0 ? <p>Nenhum protocolo.</p> : (
              <table>
                <thead><tr><th>Protocolo</th><th>Tipo</th><th>Aberto em</th><th>Status</th><th>Prazo</th><th>Detalhes (campos variam por tipo)</th></tr></thead>
                <tbody>{d.protocolos.map((p) => (
                  <tr key={p.protocolo}>
                    <td><code>{p.protocolo}</code></td><td>{p.tipo}</td><td>{dataBR(p.aberto_em)}</td><td>{p.status}</td>
                    <td><Sla v={p.situacao_sla} /></td>
                    <td className="detalhes">{Object.entries(p.detalhes || {}).map(([k, v]) => <span key={k}><b>{k}:</b> {Array.isArray(v) ? v.join(', ') : String(v)}</span>)}</td>
                  </tr>
                ))}</tbody>
              </table>
            )}
          </Cartao>
        </>
      )}
    </>
  )
}
