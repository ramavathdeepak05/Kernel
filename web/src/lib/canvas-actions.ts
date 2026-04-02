/**
 * Canvas action types — the complete set of instructions the agent
 * can send to the primary canvas.
 *
 * Reference: ALIS-skills/references/frontend.md §5
 */

export type ALISModule =
  | 'dashboard'
  | 'tasks'
  | 'students'
  | 'admissions'
  | 'academics'
  | 'examinations'
  | 'finance'
  | 'hr'
  | 'student_services'
  | 'communications'
  | 'alumni'
  | 'phd'
  | 'convocation'
  | 'obe'
  | 'workflows'
  | 'process_engine'
  | 'consent'
  | 'regulatory'
  | 'reports'
  | 'settings'
  | 'onboarding'
  | 'team'

export type CanvasView =
  | 'approval_queue'
  | 'student_risk'
  | 'exam_management'
  | 'fee_dashboard'
  | 'my_courses'
  | 'my_academics'
  | 'admissions_pipeline'
  | 'regulatory_dashboard'
  | 'hr_dashboard'
  | 'reports_dashboard'
  | 'student_services_dashboard'
  | 'communications_dashboard'
  | 'alumni_dashboard'
  | 'phd_dashboard'
  | 'workflows_dashboard'
  | 'consent_dashboard'
  | 'home'

export type CanvasAction =
  | { type: 'NAVIGATE'; view: CanvasView; module: ALISModule; filters?: Record<string, unknown> }
  | { type: 'HIGHLIGHT'; itemId: string; scrollTo: boolean }
  | { type: 'HIGHLIGHT_MULTIPLE'; itemIds: string[] }
  | { type: 'FILTER'; filters: Record<string, unknown> }
  | { type: 'OPEN_DETAIL'; itemId: string }
  | { type: 'EXECUTE'; action: 'approve' | 'reject' | 'escalate'; itemId: string }
  | { type: 'EXECUTE_MODULE'; module: string; actionEndpoint: string;
      payload: Record<string, unknown>; is_batch?: boolean; chips?: string[] }
  | { type: 'CLEAR_HIGHLIGHT' }

export interface AgentResponse {
  message: string
  canvasAction: CanvasAction | null
  quickActions?: string[]
  chips?: string[]
  agentContext?: string
}
