import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api, pct, type Metrics } from '../api'

const ERROR_LABELS: Record<string, string> = {
  missing: 'Missing',
  wrong_value: 'Wrong value',
  format_error: 'Format error',
  hallucinated: 'Hallucinated',
}

export default function MetricsPage() {
  const [m, setM] = useState<Metrics | null>(null)
  const [error, setError] = useState('')

  useEffect(() => {
    api.metrics().then(setM).catch((e) => setError(e.message))
  }, [])

  if (error) return <div className="page"><div className="alert">{error}</div></div>
  if (!m) return <div className="page"><p className="muted">Loading…</p></div>

  const o = m.overall
  return (
    <div className="page">
      <div className="page-head">
        <div>
          <h1>Extraction accuracy</h1>
          <p className="muted">
            Every extracted field is scored against ground truth (synthetic bills) or the reviewer's
            decision (uploaded bills).
          </p>
        </div>
      </div>

      {o.fields_scored === 0 ? (
        <div className="empty">Nothing scored yet. Seed synthetic bills or review a document.</div>
      ) : (
        <>
          <div className="tiles">
            <Tile label="Field accuracy" value={pct(o.accuracy)} sub={`${o.fields_scored} fields, ${o.documents_scored} documents`} />
            <Tile label="Errors" value={String(o.errors)} sub="fields the extractor got wrong" />
            <Tile
              label="Flag recall"
              value={pct(o.flag_recall)}
              sub="of errors were flagged for review"
              emphasis
            />
            <Tile label="Flagged for review" value={String(o.fields_flagged_for_review)} sub="fields routed to a human" />
          </div>

          <div className="grid-2">
            <div className="card">
              <h2>Accuracy by field</h2>
              <div className="bars">
                {m.per_field.map((f) => (
                  <div className="bar-row" key={f.field} title={`${f.label}: ${f.correct}/${f.scored} correct`}>
                    <span className="bar-label">{f.label}</span>
                    <span className="bar-track">
                      <span className="bar-fill" style={{ width: `${(f.accuracy ?? 0) * 100}%` }} />
                    </span>
                    <span className="bar-value">{pct(f.accuracy)}</span>
                  </div>
                ))}
              </div>
            </div>

            <div className="card">
              <h2>Accuracy by layout</h2>
              <div className="bars">
                {m.per_layout.map((l) => (
                  <div className="bar-row" key={l.layout} title={`${l.scored} fields scored`}>
                    <span className="bar-label">
                      {l.layout === 'uploaded' ? 'Uploaded' : `Layout ${l.layout}`}
                    </span>
                    <span className="bar-track">
                      <span className="bar-fill" style={{ width: `${(l.accuracy ?? 0) * 100}%` }} />
                    </span>
                    <span className="bar-value">{pct(l.accuracy)}</span>
                  </div>
                ))}
              </div>
              <p className="muted small">
                Different bill layouts use different labels for the same field. That variation is
                where a rules baseline breaks down.
              </p>
            </div>
          </div>

          <div className="card">
            <h2>Errors by type</h2>
            <table className="table table-compact">
              <thead>
                <tr>
                  <th>Field</th>
                  {Object.keys(ERROR_LABELS).map((k) => (
                    <th key={k} className="num">{ERROR_LABELS[k]}</th>
                  ))}
                  <th className="num">Correct</th>
                </tr>
              </thead>
              <tbody>
                {m.per_field.map((f) => (
                  <tr key={f.field}>
                    <td>{f.label}</td>
                    {Object.keys(ERROR_LABELS).map((k) => (
                      <td key={k} className={`num ${f.errors[k] ? 'err' : 'muted'}`}>{f.errors[k] || '—'}</td>
                    ))}
                    <td className="num">{f.correct}/{f.scored}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div className="card">
            <h2>By document</h2>
            <table className="table table-compact">
              <thead>
                <tr>
                  <th>Document</th>
                  <th>Layout</th>
                  <th>Extractor</th>
                  <th className="num">Accuracy</th>
                </tr>
              </thead>
              <tbody>
                {m.per_document.map((d) => (
                  <tr key={d.id}>
                    <td><Link to={`/documents/${d.id}`}>{d.name}</Link></td>
                    <td>{d.layout}</td>
                    <td className="muted">{d.extractor}</td>
                    <td className="num">{pct(d.accuracy)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </div>
  )
}

function Tile({ label, value, sub, emphasis }: { label: string; value: string; sub: string; emphasis?: boolean }) {
  return (
    <div className={`tile ${emphasis ? 'tile-emphasis' : ''}`}>
      <div className="tile-label">{label}</div>
      <div className="tile-value">{value}</div>
      <div className="tile-sub">{sub}</div>
    </div>
  )
}
