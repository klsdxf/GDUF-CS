export let csrf = ''

export interface ApiErrorBody {
  code: string
  message: string
  details?: unknown
  request_id?: string
}

export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly code: string,
    message: string,
    readonly details: unknown,
    readonly requestId: string | null,
  ) {
    super(message)
    this.name = 'ApiError'
  }
}

interface Envelope<T> {
  data: T
  error?: ApiErrorBody
}

interface Page<T> extends Envelope<T[]> {
  meta: { next_cursor: string | null }
}

async function request<T extends Envelope<unknown>>(
  path: string, method: string, body?: unknown, extraHeaders: Record<string, string> = {},
): Promise<T> {
  const headers: Record<string, string> = { 'X-CSRF-Token': csrf, ...extraHeaders }
  if (body !== undefined && !(body instanceof FormData)) headers['Content-Type'] = 'application/json'
  const response = await fetch('/api/v1' + path, {
    method, headers, credentials: 'same-origin',
    body: body instanceof FormData ? body : body === undefined ? undefined : JSON.stringify(body),
  })
  const result = await response.json().catch(() => null) as T | null
  if (!response.ok || !result || !('data' in result)) {
    const error = result?.error
    throw new ApiError(response.status, error?.code || 'HTTP_ERROR', error?.message || '请求失败，请稍后重试',
      error?.details, error?.request_id || response.headers.get('X-Request-ID'))
  }
  return result
}

export async function api<T = any>(
  path: string, method = 'GET', body?: unknown, extraHeaders: Record<string, string> = {},
): Promise<T> {
  const { data } = await request<Envelope<T>>(path, method, body, extraHeaders)
  if (data && typeof data === 'object' && 'csrf' in data && typeof data.csrf === 'string') csrf = data.csrf
  return data
}

export function apiPage<T>(path: string): Promise<Page<T>> {
  return request<Page<T>>(path, 'GET')
}
