import { useEffect, useState } from 'react'
import { api } from './api.js'
import VisaoGeral from './pages/VisaoGeral.jsx'
import RadarEvasao from './pages/RadarEvasao.jsx'
import FilaAtendimento from './pages/FilaAtendimento.jsx'
import OrigemAlunos from './pages/OrigemAlunos.jsx'
import Aluno360 from './pages/Aluno360.jsx'

const ABAS = [
  { id: 'geral', rotulo: 'Visão geral' },
  { id: 'risco', rotulo: 'Radar de evasão' },
  { id: 'fila', rotulo: 'Fila e prazos' },
  { id: 'origem', rotulo: 'Origem dos alunos' },
  { id: 'aluno', rotulo: 'Aluno 360°' },
]

export default function App() {
  const [aba, setAba] = useState('geral')
  const [raSelecionado, setRaSelecionado] = useState('')
  const [status, setStatus] = useState(null)
  const [versao, setVersao] = useState(0) // incrementa após uma nova carga para recarregar as páginas

  useEffect(() => { api.status().then(setStatus).catch(() => setStatus(null)) }, [versao])

  const abrirAluno = (ra) => { setRaSelecionado(ra); setAba('aluno') }

  return (
    <div className="app">
      <header className="topo">
        <div className="marca">
          <span className="logo">R</span>
          <div>
            <h1>Radar da Secretaria</h1>
            <small>Secretaria Acadêmica · UNIFEOB</small>
          </div>
        </div>
        <nav>
          {ABAS.map((a) => (
            <button key={a.id} className={aba === a.id ? 'ativa' : ''} onClick={() => setAba(a.id)}>{a.rotulo}</button>
          ))}
        </nav>
      </header>

      {status?.mongo?.includes('embutido') && (
        <div className="aviso">MongoDB em modo embutido (mongomock). Para a apresentação, inicie um MongoDB real e defina <code>MONGO_URI</code>.</div>
      )}

      <main>
        {aba === 'geral' && <VisaoGeral key={versao} status={status} aoRecarregar={() => setVersao((v) => v + 1)} />}
        {aba === 'risco' && <RadarEvasao key={versao} abrirAluno={abrirAluno} />}
        {aba === 'fila' && <FilaAtendimento key={versao} abrirAluno={abrirAluno} />}
        {aba === 'origem' && <OrigemAlunos key={versao} />}
        {aba === 'aluno' && <Aluno360 key={raSelecionado + versao} raInicial={raSelecionado} />}
      </main>
    </div>
  )
}
