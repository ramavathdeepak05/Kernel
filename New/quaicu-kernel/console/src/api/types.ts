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

export interface Entitlements {
  tenant: string;
  tier: string | null; // null = dedicated single-kernel deploy (not tier-limited)
  status: string | null; // plan status, "NO_ACTIVE_PLAN", or null (dedicated)
  features: Record<string, boolean>;
  quotas: Record<string, number>;
  billing_providers?: string[]; // checkout-capable providers wired on this deployment
}

export interface CheckoutRequest {
  provider: string; // "stripe" | "razorpay"
  tier: string; // "BUSINESS" | "ENTERPRISE"
  success_url?: string;
  cancel_url?: string;
  customer_email?: string;
}

export interface CheckoutResponse {
  provider: string;
  tenant: string;
  tier: string;
  url: string; // redirect the user here to pay
  reference: string | null;
}

// ── Authorize (pure policy decision — the "try it" surface) ──────────────────
// POST /v1/authorize evaluates policy/consent/identity for an action type and returns a verdict
// WITHOUT executing anything. Always HTTP 200 — read `allowed`/`decision` from the body.
export interface AuthorizeRequest {
  type: string; // action type, e.g. "demo.payment"
  payload?: Record<string, unknown>;
  idempotency_key?: string | null;
  record?: boolean | null; // override ledger sealing for this decision
}

export interface AuthorizeResponse {
  decision: string; // "allow" | "deny" | "require_approval"
  allowed: boolean;
  actor_id: string;
  reason?: string | null;
  policy_versions: string[];
  approvers: string[];
  enforced_layers: string[];
  sealed: boolean;
  ledger_seq?: number | null;
}

// ── AI gateway (BYO upstream connection) ─────────────────────────────────────
export interface AIConnectionStatus {
  connected: boolean;
  provider?: string;
  base_url?: string;
  default_model?: string;
  key_hint?: string;
  mask_pii?: boolean;
  api_version?: string;
  updated_at?: string | null;
}

export interface AIConnectionBody {
  provider: string;
  base_url: string;
  api_key: string;
  default_model: string;
  mask_pii?: boolean;
  api_version?: string;
}

// ── Starter policy packs (import a regulatory baseline as DRAFTs) ─────────────
export interface PolicyPackPolicy {
  id: string;
  title: string;
  description: string;
  governs: string;
  condition: string;
  decision: string;
  approvers: string[];
  regulatory_refs: string[];
}

export interface PolicyPackActionType {
  name: string;
  use_case: string;
  payload: string;
  example: string;
}

export interface PolicyPack {
  id: string;
  name: string;
  regulation: string;
  description: string;
  summary: string;
  usage: string;
  action_types: string[];
  action_specs: PolicyPackActionType[];
  policy_count: number;
  policies: PolicyPackPolicy[];
}

export interface PolicyPackList {
  packs: PolicyPack[];
  count: number;
}

export interface PolicyPackImportResult {
  pack_id: string;
  imported: string[];
  skipped: { id: string; reason: string }[];
  count: number;
}

// ── Self-serve verified signup (unauthenticated) ─────────────────────────────
// Two steps: POST /v1/signup/start (collect details → email OTP) then
// POST /v1/signup/verify (OTP → provisioned tenant + key).
export interface SignupStartBody {
  full_name: string;
  email: string; // company email (free/personal providers rejected)
  company_name: string;
  password: string; // console login password (min 8)
  job_title: string;
  phone: string;
  use_case: string;
  industry: string;
  company_size: string;
  regulations: string[]; // >= 1
}

// ── Console login (email + password → session token) ─────────────────────────
export interface LoginBody {
  email: string;
  password: string;
}

export interface LoginResponse {
  session_token: string; // JWT — used as the Bearer token
  tenant_id: string;
  expires_in: number;
}

// ── Password reset (forgot → email OTP → new password) ───────────────────────
export interface ForgotBody {
  email: string;
}
export interface ForgotResponse {
  reset_token: string;
  expires_in: number;
}
export interface ResetBody {
  reset_token: string;
  otp: string;
  new_password: string;
}

export interface SignupStartResponse {
  verification_token: string; // opaque; returned with the OTP on /verify
  email: string;
  expires_in: number; // seconds
}

export interface SignupVerifyBody {
  verification_token: string;
  otp: string;
  coupon_code?: string;
}

// Verify either provisions + returns a session (free / post-payment), or — when a signup fee is
// configured — returns a Razorpay order to pay before the account is created.
export interface SignupVerifyResponse {
  requires_payment: boolean;
  // provisioned (free path, or after /complete):
  account_id?: string;
  tenant_id?: string;
  tier?: string;
  session_token?: string;
  expires_in?: number;
  // fee path — open Razorpay Checkout with these, then call completeSignup:
  order_id?: string;
  razorpay_key_id?: string;
  amount_paise?: number;
  currency?: string;
  payment_token?: string;
  coupon_code?: string | null;
  discount_paise?: number | null;
}

export interface SignupCompleteBody {
  payment_token: string;
  razorpay_order_id: string;
  razorpay_payment_id: string;
  razorpay_signature: string;
}

// ── Business / Enterprise consultation (₹50,000 → talk to integrations team) ──
export interface ConsultLeadBody {
  tier: string; // BUSINESS | ENTERPRISE
  full_name: string;
  email: string;
  company_name: string;
  phone: string;
  coupon_code?: string;
}
export interface ConsultStartResponse {
  order_id: string;
  razorpay_key_id: string;
  amount_paise: number;
  currency: string;
  coupon_code?: string | null;
  discount_paise?: number | null;
}
export interface ConsultCompleteBody extends ConsultLeadBody {
  razorpay_order_id: string;
  razorpay_payment_id: string;
  razorpay_signature: string;
}

// ── API keys (programmatic access — managed from the API Keys page) ───────────
export interface ApiKeyInfo {
  key_id: string;
  created_at: string;
  revoked: boolean;
  scopes: string[];
}
export interface ApiKeyList {
  keys: ApiKeyInfo[];
}
export interface CreatedApiKey {
  key_id: string;
  api_key: string; // plaintext — shown ONCE
  created_at: string;
}

// ── Team members (W6-1) ──────────────────────────────────────────────────────
export interface MemberInfo {
  member_id: string;
  email: string;
  display_name: string;
  role: string;
  status: string; // "ACTIVE" | "DEACTIVATED"
  external_id: string;
  created_at: string;
}
export interface MemberList {
  members: MemberInfo[];
  roles: string[]; // assignable roles (OWNER/ADMIN/COMPLIANCE/VIEWER)
}
export interface InviteMemberBody {
  email: string;
  role: string;
  display_name?: string;
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
