import { useCallback, useEffect, useRef, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { api, pct, type DocumentSummary } from '../api'
import { StatusPill } from '../components'

export default function DocumentsPage() {
  const [docs, setDocs] = useState<DocumentSummary[] | null>(null)
  const [error, setError] = useState('')
  const [uploading, setUploading] = useState(false)
  const [dragging, setDragging] = useState(false)
  const inputRef = useRef<HTMLInputElement>(null)
  const navigate = useNavigate()

  const load = useCallback(() => {
    api
      .listDocuments()
      .then(setDocs)
      .catch((e) => setError(e.message))
  }, [])

  useEffect(load, [load])

  async function upload(file: File) {
    setError('')
    setUploading(true)
    try {
      const doc = await api.uploadDocument(file)
      navigate(`/documents/${doc.id}`)
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setUploading(false)
    }
  }

  const toReview = docs?.filter((d) => d.status === 'needs_review').length ?? 0

  return (
    <div className="page">
      <div className="page-head">
        <div>
          <h1>Medical bills</h1>
          <p className="muted">
            Upload a bill, let the extractor pull the billing fields, then confirm or correct them.
          </p>
        </div>
      </div>

      <div
        className={`dropzone ${dragging ? 'dropzone-active' : ''}`}
        onDragOver={(e) => {
          e.preventDefault()
          setDragging(true)
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={(e) => {
          e.preventDefault()
          setDragging(false)
          const f = e.dataTransfer.files[0]
          if (f) upload(f)
        }}
        onClick={() => inputRef.current?.click()}
        role="button"
        tabIndex={0}
        onKeyDown={(e) => e.key === 'Enter' && inputRef.current?.click()}
      >
        <input
          ref={inputRef}
          type="file"
          accept="application/pdf"
          hidden
          onChange={(e) => {
            const f = e.target.files?.[0]
            if (f) upload(f)
            e.target.value = ''
          }}
        />
        {uploading ? (
          <strong>Uploading and extracting…</strong>
        ) : (
          <>
            <strong>Drop a PDF bill here</strong>
            <span className="muted"> or click to choose a file</span>
          </>
        )}
      </div>

      {error && <div className="alert">{error}</div>}

      <div className="section-head">
        <h2>Documents</h2>
        {docs && (
          <span className="muted">
            {docs.length} total · {toReview} awaiting review
          </span>
        )}
      </div>

      {docs === null ? (
        <p className="muted">Loading…</p>
      ) : docs.length === 0 ? (
        <div className="empty">
          No documents yet. Upload a PDF above, or run <code>python manage.py seed_demo</code> to
          load synthetic bills.
        </div>
      ) : (
        <table className="table">
          <thead>
            <tr>
              <th>Document</th>
              <th>Status</th>
              <th>Extractor</th>
              <th className="num">To review</th>
              <th className="num">Field accuracy</th>
            </tr>
          </thead>
          <tbody>
            {docs.map((d) => (
              <tr key={d.id} onClick={() => navigate(`/documents/${d.id}`)} className="row-link">
                <td>
                  <Link to={`/documents/${d.id}`} onClick={(e) => e.stopPropagation()}>
                    {d.original_name}
                  </Link>
                  {d.layout && <span className="tag">Layout {d.layout}</span>}
                </td>
                <td>
                  <StatusPill status={d.status} />
                </td>
                <td className="muted">{d.extractor === 'llm' ? 'LLM' : d.extractor ?? '—'}</td>
                <td className="num">{d.fields_to_review || '—'}</td>
                <td className="num">{pct(d.accuracy)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  )
}
