import type { DocStatus, Score } from './api'

const STATUS_LABELS: Record<DocStatus, string> = {
  queued: 'Queued',
  processing: 'Processing',
  needs_review: 'Needs review',
  reviewed: 'Reviewed',
  failed: 'Failed',
}

export function StatusPill({ status }: { status: DocStatus }) {
  return <span className={`pill pill-${status}`}>{STATUS_LABELS[status]}</span>
}

const SCORE_LABELS: Record<string, string> = {
  correct: '✓ Matches truth',
  missing: '✕ Missed (truth has a value)',
  wrong_value: '✕ Wrong value',
  format_error: '✕ Format error',
  hallucinated: '✕ Hallucinated',
}

export function ScoreTag({ score }: { score: Score }) {
  if (!score) return null
  const ok = score === 'correct'
  return <span className={`score ${ok ? 'score-ok' : 'score-bad'}`}>{SCORE_LABELS[score]}</span>
}

export function ConfidenceMeter({ value }: { value: number }) {
  const level = value >= 0.9 ? 'high' : value >= 0.75 ? 'mid' : 'low'
  return (
    <span className="confidence" title={`Model confidence ${Math.round(value * 100)}%`}>
      <span className="confidence-track">
        <span className={`confidence-fill conf-${level}`} style={{ width: `${value * 100}%` }} />
      </span>
      <span className="confidence-num">{Math.round(value * 100)}%</span>
    </span>
  )
}
