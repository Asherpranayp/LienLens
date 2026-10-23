// Typed client for the LienLens Django REST API.

export type DocStatus = 'queued' | 'processing' | 'needs_review' | 'reviewed' | 'failed'
export type ReviewState = 'pending' | 'accepted' | 'edited' | 'flagged'
export type Score = 'correct' | 'missing' | 'wrong_value' | 'format_error' | 'hallucinated' | null

export interface DocumentSummary {
  id: number
  original_name: string
  status: DocStatus
  created_at: string
  extractor: 'llm' | 'rules' | null
  fields_to_review: number
  accuracy: number | null
  layout: string | null
}

export interface ExtractedField {
  id: number
  name: string
  label: string
  value: string
  final_value: string
  confidence: number
  is_valid: boolean
  validation_message: string
  needs_review: boolean
  review_state: ReviewState
  score: Score
}

export interface LineItem {
  code: string
  description: string
  amount: string
}

export interface ExtractionRun {
  id: number
  extractor: string
  model_name: string
  prompt_version: string
  latency_ms: number
  status: string
  line_items: LineItem[]
  validation_issues: string[]
}

export interface DocumentDetail extends DocumentSummary {
  error_message: string
  run: ExtractionRun | null
  extracted_fields: ExtractedField[]
  has_ground_truth: boolean
}

export interface FieldMetric {
  field: string
  label: string
  scored: number
  correct: number
  accuracy: number | null
  errors: Record<string, number>
}

export interface Metrics {
  overall: {
    documents_scored: number
    fields_scored: number
    accuracy: number | null
    fields_flagged_for_review: number
    errors: number
    flag_recall: number | null
  }
  per_field: FieldMetric[]
  per_layout: { layout: string; scored: number; accuracy: number | null }[]
  per_document: {
    id: number
    name: string
    layout: string
    extractor: string
    accuracy: number
    scored: number
  }[]
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, init)
  if (!res.ok) {
    let detail = `${res.status} ${res.statusText}`
    try {
      const body = await res.json()
      detail = typeof body === 'object' ? Object.values(body).flat().join(' ') : String(body)
    } catch {
      /* non-JSON error body */
    }
    throw new Error(detail)
  }
  return res.status === 204 ? (undefined as T) : res.json()
}

export const api = {
  listDocuments: () => request<DocumentSummary[]>('/api/documents/'),
  getDocument: (id: number) => request<DocumentDetail>(`/api/documents/${id}/`),
  uploadDocument: (file: File) => {
    const form = new FormData()
    form.append('file', file)
    return request<DocumentDetail>('/api/documents/', { method: 'POST', body: form })
  },
  deleteDocument: (id: number) => request<void>(`/api/documents/${id}/`, { method: 'DELETE' }),
  reextract: (id: number) =>
    request<DocumentDetail>(`/api/documents/${id}/reextract/`, { method: 'POST' }),
  reviewField: (
    id: number,
    decision: 'accept' | 'edit' | 'flag',
    corrected_value = '',
  ) =>
    request<ExtractedField>(`/api/fields/${id}/review/`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ decision, corrected_value }),
    }),
  metrics: () => request<Metrics>('/api/metrics/'),
  health: () => request<{ status: string; extractor: string }>('/api/health/'),
  fileUrl: (id: number) => `/api/documents/${id}/file/`,
  previewUrl: (id: number) => `/api/documents/${id}/preview/`,
}

export const pct = (v: number | null | undefined) =>
  v === null || v === undefined ? '—' : `${Math.round(v * 100)}%`
