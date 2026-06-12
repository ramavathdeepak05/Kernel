// TypeScript mirrors of the kernel's Pydantic response schemas (delivery/api/schemas.py).

export interface PolicyResponse {
  id: string;
  version: number;
  governs: string;
  scope: Record<string, string>;
  condition: string;
  decision: string;
  approvers: string[];
  regulatory_refs: string[];
  lifecycle: string;
}

export interface PolicyListResponse {
  policies: PolicyResponse[];
  count: number;
}

export interface ImpactReportResponse {
  policy_id: string;
  policy_version: number;
  reviewed_by: string;
  reviewed_at: string;
  decision_distribution: Record<string, number>;
  flip_count: number;
  fairness_delta: number;
  acknowledged: boolean;
}

export interface SimulateResponse {
  impact_report: ImpactReportResponse;
  run_id: string;
  ledger_entries_evaluated: number;
  decisions_flipped: number;
  flip_rate: number;
  fairness_delta: number | null;
  stored: boolean;
}

export interface DashboardOverview {
  tenant: string;
  total_governed: number;
  decision_counts: Record<string, number>;
  denial_rate: number;
  last_ledger_seq: number | null;
}

export interface DayBucket {
  date: string;
  decision_counts: Record<string, number>;
  total: number;
}

export interface DecisionTimeline {
  tenant: string;
  window_days: number;
  buckets: DayBucket[];
}

export interface TopActionEntry {
  action_type: string;
  total: number;
  denials: number;
}

export interface TopActions {
  tenant: string;
  by_volume: TopActionEntry[];
  by_denials: TopActionEntry[];
}

export interface HitlQueue {
  tenant: string;
  pending: number;
}

export interface LedgerEntryResponse {
  ledger_seq: number;
  action_id: string;
  action_type: string;
  actor_id: string;
  decision: string;
  policy_versions: string[];
  sealed_at: string;
  approver: string | null;
}

export interface LedgerTrail {
  tenant: string;
  entries: LedgerEntryResponse[];
  count: number;
}

export interface ApprovalRecord {
  handle_id: string;
  action_id: string;
  tenant: string;
  required_approvers: string[];
  requested_at: string;
  decision: string;
  decided_by: string | null;
  decided_at: string | null;
  expires_at: string | null;
  proposed_by: string | null;
}

export interface ApprovalList {
  approvals: ApprovalRecord[];
  count: number;
}

// Request bodies
export interface PolicyRegisterBody {
  id: string;
  version: number;
  governs: string;
  scope: Record<string, string>;
  condition: string;
  decision: string;
  approvers: string[];
  regulatory_refs: string[];
}

export interface ImpactReportBody {
  reviewed_by: string;
  reviewed_at: string;
  decision_distribution: Record<string, number>;
  flip_count: number;
  fairness_delta: number;
  acknowledged: boolean;
}
