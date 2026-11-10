import { useEffect, useState } from 'react'
import { api, dataBR } from '../api.js'
import { Cartao, Carregando, Erro, Nivel, Sla } from '../components.jsx'

function NovoProtocolo({ tipos }) {
  const [form, setForm] = useState({ ra: '', tipo: 'Histórico escolar', canal: 'Balcão', obs: '' })
  const [res, setRes] = useState(null)
  const [erro, setErro] = useState('')
  const set = (c) => (e) => setForm({ ...form, [c]: e.target.value })

  const enviar = async (e) => {
    e.preventDefault(); setErro(''); setRes(null)
    try {
      setRes(await api.abrirProtocolo({ ra: form.ra.trim(), tipo: form.tipo, canal: form.canal, detalhes: form.obs ? { observacao: form.obs } : {} }))
    } catch (er) { setErro(er.message) }
  }

  return (
    <Cartao titulo="Abrir novo protocolo" fonte="grava no MongoDB · prazo via BrasilAPI">
      <form className="form" onSubmit={enviar}>
        <label>RA do aluno<input required value={form.ra} onChange={set('ra')} placeholder="ex.: 202400510" /></label>
        <label>Tipo
          <select value={form.tipo} onChange={set('tipo')}>
            {tipos.map((t) => <option key={t.tipo} value={t.tipo}>{t.tipo} ({t.prazo_dias_uteis} dias úteis)</option>)}
          </select>
        </label>
        <label>Canal
          <select value={form.canal} onChange={set('canal')}>{['Balcão', 'Portal do aluno', 'WhatsApp', 'E-mail'].map((c) => <option key={c}>{c}</option>)}</select>
        </label>
        <label>Observação<input value={form.obs} onChange={set('obs')} placeholder="opcional" /></label>
        <button className="botao">Abrir protocolo</button>
      </form>
      {erro && <Erro msg={erro} />}
      {res && (
        <div className="resultado">
          <b>{res.protocolo}</b> criado. Prazo regimental: <b>{res.prazo_dias_uteis} dias úteis</b> → entrega até <b>{dataBR(res.prazo_final)}</b>.
          {res.feriados_considerados.length > 0 && (
            <div>Feriados descontados: {res.feriados_considerados.map((f) => `${dataBR(f.data)} (${f.nome})`).join(', ')}</div>
          )}
          <small>{res.aviso}</small>
        </div>
      )}
    </Cartao>
  )
}

export default function FilaAtendimento({ abrirAluno }) {
  const [situacao, setSituacao] = useState('')
  const [fila, setFila] = useState(null)
  const [ind, setInd] = useState(null)
  const [tipos, setTipos] = useState([])
  const [erro, setErro] = useState('')

  useEffect(() => {
    api.indicadores().then(setInd).catch((e) => setErro(e.message))
    api.filtros().then((f) => setTipos(f.tipos_protocolo)).catch(() => {})
  }, [])
  useEffect(() => { api.fila({ situacao }).then(setFila).catch((e) => setErro(e.message)) }, [situacao])

  if (erro) return <Erro msg={erro} />
  return (
    <>
      <div className="grade-2">
        <Cartao titulo="Cumprimento de prazo por tipo" fonte="DuckDB · fato_atendimento">
          {!ind ? <Carregando /> : (
            <table>
              <thead><tr><th>Tipo</th><th className="num">Qtd.</th><th className="num">Prazo</th><th className="num">Média real</th><th>No prazo</th></tr></thead>
              <tbody>
                {ind.por_tipo.map((t) => (
                  <tr key={t.tipo}>
                    <td>{t.tipo}</td><td className="num">{t.total}</td><td className="num">{t.prazo} d.u.</td>
                    <td className={`num ${t.media_dias_uteis > t.prazo ? 'txt-perigo' : ''}`}>{t.media_dias_uteis ?? '—'} d.u.</td>
                    <td><div className="mini"><span style={{ width: `${t.pct_no_prazo || 0}%` }} className={t.pct_no_prazo < 80 ? 'ruim' : ''} /></div>{t.pct_no_prazo ?? '—'}%</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
          <p className="nota">d.u. = dias úteis, descontando sábados, domingos e feriados nacionais (BrasilAPI) e municipais.</p>
        </Cartao>
        <NovoProtocolo tipos={tipos} />
      </div>

      <Cartao titulo="Fila de protocolos em aberto" fonte="priorizada por prazo" acoes={
        <select value={situacao} onChange={(e) => setSituacao(e.target.value)}>
          <option value="">Todas as situações</option><option>ATRASADO</option><option>VENCE EM BREVE</option><option>NO PRAZO</option>
        </select>
      }>
        {!fila ? <Carregando /> : (
          <div className="tabela-rolagem">
            <table>
              <thead><tr><th>Protocolo</th><th>Aluno</th><th>Tipo</th><th>Canal</th><th>Aberto em</th><th>Prazo final</th><th>Situação</th><th>Risco do aluno</th></tr></thead>
              <tbody>
                {fila.map((p) => (
                  <tr key={p.protocolo} className="clicavel" onClick={() => abrirAluno(p.ra)}>
                    <td><code>{p.protocolo}</code></td>
                    <td><b>{p.nome}</b><br /><small>{p.curso}</small></td>
                    <td>{p.tipo}</td><td>{p.canal}</td>
                    <td>{dataBR(p.aberto_em)}</td><td>{dataBR(p.prazo_final)}</td>
                    <td><Sla v={p.situacao_sla} /></td>
                    <td><Nivel v={p.nivel_risco} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
            <p className="nota">{fila.length} protocolos. A coluna "Risco do aluno" ajuda a priorizar: um trancamento de um aluno em risco alto é uma chance de reter esse aluno.</p>
          </div>
        )}
      </Cartao>
    </>
  )
}
