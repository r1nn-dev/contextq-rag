// Common response envelope (docs/specs/api-spec.md > 0.3 공통 성공·에러 응답)

export interface ApiSuccess<T> {
  success: true
  message: string | null
  data: T
}

export interface ApiErrorDetail {
  field: string
  reason: string
}

export interface ApiErrorBody {
  code: string
  message: string
  details: ApiErrorDetail[]
}

export interface ApiFailure {
  success: false
  error: ApiErrorBody
}

export interface CursorPage<T> {
  items: T[]
  cursor: string | null
  hasNext: boolean
}

export function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}
