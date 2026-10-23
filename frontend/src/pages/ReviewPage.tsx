import { useCallback, useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { api, type DocumentDetail, type ExtractedField } from '../api'
import { ConfidenceMeter, ScoreTag, StatusPill } from '../components'

const MONEY_FIELDS = new Set(['total_billed', 'adjustments', 'balance_due'])

function display(field: Pick<ExtractedField, 'name'>, value: string) {
  if (!value) return ''
  if (MONEY_FIELDS.has(field.name)) {
    const n = Number(value)
    return Number.isFinite(n) ? n.toLocaleString('en-US', { style: 'currency', currency: 'USD' }) : value
  }
  return value
}

export default function ReviewPage() {
  const { id } = useParams()
  const docId = Number(id)
  const navigate = useNavigate()
  const [doc, setDoc] = useState<DocumentDetail | null>(null)
  const [error, setError] = useState('')
  const [onlyFlagged, setOnlyFlagged] = useState(false)
  const [busy, setBusy] = useState(false)

  const load = useCallback(() => {
    api
      .getDocument(docId)
      .then(setDoc)
      .catch((e) => setError(e.message))
  }, [docId])

  useEffect(load, [load])

  async function review(field: ExtractedField, decision: 'accept' | 'edit' | 'flag', value = '') {
    setError('')
    try {
      await api.reviewField(field.id, decision, value)
      load()
    } catch (e) {
      setError((e as Error).message)
    }
  }

  async function acceptAllUnflagged() {
    if (!doc) return
    setBusy(true)
    const targets = doc.extracted_fields.filter((f) => !f.needs_review && f.review_state === 'pending')
    for (const f of targets) await api.reviewField(f.id, 'accept')
    setBusy(false)
    load()
  }

  async function reextract() {
    setBusy(true)
    try {
      setDoc(await api.reextract(docId))
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setBusy(false)
    }
  }

  async function nextDocument() {
    const all = await api.listDocuments()
    const next = all.find((d) => d.id !== docId && d.status === 'needs_review')
    navigate(next ? `/documents/${next.id}` : '/')
  }

  if (error && !doc) return <div className="page"><div className="alert">{error}</div></div>
  if (!doc) return <div className="page"><p className="muted">Loading…</p></div>

  const fields = doc.extracted_fields
  const decided = fields.filter((f) => f.review_state !== 'pending').length
  const flagged = fields.filter((f) => f.needs_review).length
  const visible = onlyFlagged ? fields.filter((f) => f.needs_review) : fields
  const unflaggedPending = fields.filter((f) => !f.needs_review && f.review_state === 'pending').length
  const run = doc.run

  return (
    <div className="review">
      <section className="review-doc">
        <div className="doc-bar">
          <span>Original document</span>
          <a href={api.fileUrl(doc.id)} target="_blank" rel="noreferrer">
            Open PDF ↗
          </a>
        </div>
        <div className="doc-scroll">
          <img src={api.previewUrl(doc.id)} alt={`Page 1 of ${doc.original_name}`} />
        </div>
      </section>

      <section className="review-panel">
        <div className="crumbs">
          <Link to="/">← Documents</Link>
        </div>
        <div className="review-head">
          <h1 className="doc-title">{doc.original_name}</h1>
          <StatusPill status={doc.status} />
        </div>

        {run && (
          <div className="run-meta">
            <span>
              Extractor <strong>{run.extractor === 'llm' ? `LLM · ${run.model_name}` : 'Rules'}</strong>
            </span>
            <span>
              Latency <strong>{run.latency_ms} ms</strong>
            </span>
            <span>
              Reviewed <strong>{decided}/{fields.length}</strong>
            </span>
            <button className="btn btn-ghost btn-sm" onClick={reextract} disabled={busy}>
              Re-run extraction
            </button>
          </div>
        )}

        {doc.status === 'failed' && <div className="alert">Extraction failed: {doc.error_message}</div>}
        {error && <div className="alert">{error}</div>}

        <div className="progress" aria-label={`${decided} of ${fields.length} fields reviewed`}>
          <div className="progress-fill" style={{ width: `${fields.length ? (decided / fields.length) * 100 : 0}%` }} />
        </div>

        <div className="toolbar">
          <label className="toggle">
            <input type="checkbox" checked={onlyFlagged} onChange={(e) => setOnlyFlagged(e.target.checked)} />
            Show only flagged ({flagged})
          </label>
          <button className="btn btn-sm" onClick={acceptAllUnflagged} disabled={busy || unflaggedPending === 0}>
            Accept {unflaggedPending} unflagged
          </button>
        </div>

        <div className="fields">
          {visible.map((f) => (
            <FieldCard key={f.id} field={f} showScore={doc.has_ground_truth} onReview={review} />
          ))}
        </div>

        {run && run.validation_issues.length > 0 && (
          <div className="issues">
            <h3>Validation issues</h3>
            <ul>
              {run.validation_issues.map((issue) => (
                <li key={issue}>{issue}</li>
              ))}
            </ul>
          </div>
        )}

        {run && (
          <div className="line-items">
            <h3>Line items ({run.line_items.length})</h3>
            {run.line_items.length === 0 ? (
              <p className="muted">No line items found.</p>
            ) : (
              <table className="table table-compact">
                <thead>
                  <tr>
                    <th>Code</th>
                    <th>Description</th>
                    <th className="num">Amount</th>
                  </tr>
                </thead>
                <tbody>
                  {run.line_items.map((li, i) => (
                    <tr key={i}>
                      <td className="mono">{li.code}</td>
                      <td>{li.description}</td>
                      <td className="num mono">{li.amount}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        )}

        {doc.status === 'reviewed' && (
          <div className="done">
            All fields reviewed.{' '}
            <button className="btn btn-sm" onClick={nextDocument}>
              Next document →
            </button>
          </div>
        )}
      </section>
    </div>
  )
}

function FieldCard({
  field,
  showScore,
  onReview,
}: {
  field: ExtractedField
  showScore: boolean
  onReview: (f: ExtractedField, d: 'accept' | 'edit' | 'flag', v?: string) => void
}) {
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState(field.final_value || field.value)
  const decided = field.review_state !== 'pending'
  const edited = field.review_state === 'edited'

  return (
    <div className={`field ${field.needs_review ? 'field-flagged' : ''} field-${field.review_state}`}>
      <div className="field-top">
        <span className="field-label">{field.label}</span>
        <ConfidenceMeter value={field.confidence} />
      </div>

      {editing ? (
        <form
          className="field-edit"
          onSubmit={(e) => {
            e.preventDefault()
            onReview(field, 'edit', draft)
            setEditing(false)
          }}
        >
          <input autoFocus value={draft} onChange={(e) => setDraft(e.target.value)} />
          <button className="btn btn-sm btn-primary" type="submit">Save</button>
          <button className="btn btn-sm btn-ghost" type="button" onClick={() => setEditing(false)}>
            Cancel
          </button>
        </form>
      ) : (
        <div className="field-value">
          {edited ? (
            <>
              <s className="muted">{display(field, field.value) || 'Not found'}</s>{' '}
              <strong>{display(field, field.final_value)}</strong>
            </>
          ) : field.value ? (
            display(field, field.value)
          ) : (
            <span className="not-found">Not found</span>
          )}
        </div>
      )}

      <div className="field-bottom">
        <div className="field-notes">
          {field.validation_message && field.validation_message !== 'Missing' && (
            <span className="warn">⚠ {field.validation_message}</span>
          )}
          {field.needs_review && field.value && !field.validation_message && (
            <span className="warn">⚠ Low confidence</span>
          )}
          {showScore && <ScoreTag score={field.score} />}
          {decided && <span className={`state state-${field.review_state}`}>{field.review_state}</span>}
        </div>
        {!editing && (
          <div className="field-actions">
            <button
              className="btn btn-sm"
              onClick={() => onReview(field, 'accept')}
              disabled={!field.value || field.review_state === 'accepted'}
              title={field.value ? 'Value is correct' : 'Nothing to accept; edit instead'}
            >
              Accept
            </button>
            <button className="btn btn-sm" onClick={() => setEditing(true)}>
              Edit
            </button>
            <button
              className="btn btn-sm btn-ghost"
              onClick={() => onReview(field, 'flag')}
              disabled={field.review_state === 'flagged'}
            >
              Flag
            </button>
          </div>
        )}
      </div>
    </div>
  )
}
