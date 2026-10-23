import { useEffect, useState } from 'react'
import { NavLink, Outlet } from 'react-router-dom'
import { api } from './api'

export default function App() {
  const [extractor, setExtractor] = useState<string | null>(null)
  const [apiDown, setApiDown] = useState(false)

  useEffect(() => {
    api
      .health()
      .then((h) => setExtractor(h.extractor))
      .catch(() => setApiDown(true))
  }, [])

  return (
    <div className="shell">
      <header className="topbar">
        <div className="brand">
          <span className="brand-mark" aria-hidden>
            ◧
          </span>
          LienLens
        </div>
        <nav>
          <NavLink to="/" end>
            Documents
          </NavLink>
          <NavLink to="/accuracy">Accuracy</NavLink>
        </nav>
        <div className="topbar-meta">
          {apiDown ? (
            <span className="pill pill-failed">API offline</span>
          ) : extractor ? (
            <span className="pill pill-neutral" title="Which extractor new uploads use">
              Extractor: {extractor === 'llm' ? 'LLM' : 'Rules (offline)'}
            </span>
          ) : null}
        </div>
      </header>
      <main>
        <Outlet />
      </main>
      <footer className="footer">Synthetic data only. No real PHI is stored or processed.</footer>
    </div>
  )
}
