export type RuntimeMode =
  | 'UNINITIALIZED'
  | 'COMMISSIONING'
  | 'ACTIVE'
  | 'MAINTENANCE'
  | 'SUSPENDED'

export interface HealthResponse {
  status: string
  version: string
  environment: string
  database: string
  runtime_mode: RuntimeMode
  checked_at: string
}

export interface RuntimeState {
  mode: RuntimeMode
  reason: string
  changed_by: string
  changed_at: string
  version: number
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    ...init,
    headers: {
      'Content-Type': 'application/json',
      ...init?.headers,
    },
  })
  if (!response.ok) {
    const body = await response.text()
    throw new Error(body || `Request failed with status ${response.status}`)
  }
  return response.json() as Promise<T>
}

export const api = {
  health: () => request<HealthResponse>('/api/v1/health'),
  runtime: () => request<RuntimeState>('/api/v1/runtime'),
}
