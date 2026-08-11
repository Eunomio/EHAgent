export type RuntimeMode =
  | 'UNINITIALIZED'
  | 'COMMISSIONING'
  | 'ACTIVE'
  | 'MAINTENANCE'
  | 'SUSPENDED'

export type TaskStatus =
  | 'OPEN'
  | 'DEFERRED'
  | 'RESCAN_PENDING'
  | 'RESOLVED'
  | 'DISPUTED'
  | 'PAUSED'

export type FeedbackAction = 'DONE' | 'DEFER' | 'NOT_A_RISK' | 'PAUSE'

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

export interface RiskTask {
  task_id: string
  title: string
  location: string
  risk_type: string
  risk_level: number
  explanation: string
  suggested_action: string
  status: TaskStatus
  source_type: 'REPLAY' | 'MANUAL' | 'REAL_DEVICE'
  runtime_mode: RuntimeMode
  evidence_url: string | null
  evidence_label: string
  is_demo: boolean
  created_at: string
  updated_at: string
  deferred_until: string | null
}

export interface CurrentTaskResponse {
  task: RiskTask | null
  message: string
  checked_at: string
}

export interface DemoMaterial {
  case_id: 'corridor_clutter' | 'corridor_clear' | 'quality_insufficient'
  name: string
  description: string
  thumbnail_url: string
  expected_outcome: string
}

export interface AgentStage {
  key: string
  label: string
  detail: string
  status: 'complete' | 'blocked'
}

export interface DemoAnalysis {
  analysis_id: string
  outcome: 'TASK_CREATED' | 'NO_ACTION' | 'EVIDENCE_INSUFFICIENT' | 'RESOLVED'
  source_type: 'REPLAY' | 'MANUAL'
  material_name: string
  summary: string
  stages: AgentStage[]
  task: RiskTask | null
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
    throw new Error(`${response.status}: ${body || 'Request failed'}`)
  }
  return response.json() as Promise<T>
}

const engineeringHeaders = (key: string): HeadersInit => ({ 'X-Engineering-Key': key })

export const api = {
  health: () => request<HealthResponse>('/api/v1/health'),
  runtime: () => request<RuntimeState>('/api/v1/runtime'),
  currentTask: () => request<CurrentTaskResponse>('/api/v1/tasks/current'),
  submitFeedback: (taskId: string, action: FeedbackAction) =>
    request<{ task: RiskTask; message: string; duplicate: boolean }>(
      `/api/v1/tasks/${taskId}/feedback`,
      {
        method: 'POST',
        headers: { 'Idempotency-Key': crypto.randomUUID() },
        body: JSON.stringify({ action }),
      },
    ),
  transitionRuntime: (key: string, target: RuntimeMode) =>
    request<RuntimeState>('/api/v1/engineering/runtime/transition', {
      method: 'POST',
      headers: engineeringHeaders(key),
      body: JSON.stringify({
        target,
        reason: 'Start interactive vertical-slice demonstration',
        actor: 'engineering-console',
      }),
    }),
  demoMaterials: (key: string) =>
    request<DemoMaterial[]>('/api/v1/engineering/demo-materials', {
      headers: engineeringHeaders(key),
    }),
  runDemoAnalysis: (
    key: string,
    payload: {
      case_id: DemoMaterial['case_id']
      file_name?: string
      preview_data_url?: string
    },
  ) =>
    request<DemoAnalysis>('/api/v1/engineering/demo-analyses', {
      method: 'POST',
      headers: engineeringHeaders(key),
      body: JSON.stringify(payload),
    }),
}
