// Typed fetch wrapper over the kernel REST API. Injects the bearer token, scopes tenant-pathed
// endpoints, and parses the kernel's { error, code, detail } envelope into a typed ApiError.

import { getSession } from "../state/auth";
import type {
  ApprovalList,
  ApprovalRecord,
  CheckoutRequest,
  CheckoutResponse,
  DashboardOverview,
  DecisionTimeline,
  Entitlements,
  HitlQueue,
  ImpactReportBody,
  LedgerTrail,
  PolicyListResponse,
  PolicyRegisterBody,
  PolicyResponse,
  SignupBody,
  SignupResponse,
  SimulateResponse,
  TopActions,
} from "./types";

export class ApiError extends Error {
  status: number;
  code: string;
  detail: unknown;
  constructor(status: number, code: string, message: string, detail: unknown) {
    super(message);
    this.status = status;
    this.code = code;
    this.detail = detail;
  }
}

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  const { token, tenant, apiBase } = getSession();
  const headers: Record<string, string> = {};
  if (token) headers["Authorization"] = `Bearer ${token}`;
  // Shared-plane routing reads the tenant from the JWT claim when present, else from this header.
  // An API key (qk_…) isn't a JWT, so without X-Tenant-Id the kernel can't route the request
  // (TENANT_UNRESOLVED). Sending it is harmless for JWT sessions (the verified claim wins).
  if (tenant) headers["X-Tenant-Id"] = tenant;
  if (body !== undefined) headers["Content-Type"] = "application/json";

  let resp: Response;
  try {
    resp = await fetch(`${apiBase}${path}`, {
      method,
      headers,
      body: body !== undefined ? JSON.stringify(body) : undefined,
    });
  } catch (e) {
    throw new ApiError(0, "NETWORK_ERROR", `Cannot reach the kernel API (${String(e)})`, null);
  }

  const text = await resp.text();
  const data = text ? JSON.parse(text) : null;
  if (!resp.ok) {
    const d = (data && data.detail) || data || {};
    const code = d.code || data?.code || `HTTP_${resp.status}`;
    const message = d.error || data?.error || resp.statusText;
    throw new ApiError(resp.status, code, message, d.detail ?? d);
  }
  return data as T;
}

function tenant(): string {
  return encodeURIComponent(getSession().tenant);
}

export const api = {
  // ── Signup (unauthenticated self-serve onboarding) ─────────────────────────
  signup: (b: SignupBody) => request<SignupResponse>("POST", "/v1/signup", b),

  // ── Entitlements (per-tier UI gating) ──────────────────────────────────────
  entitlements: () => request<Entitlements>("GET", "/v1/me/entitlements"),

  // ── Billing (self-serve upgrade) ────────────────────────────────────────────
  checkout: (b: CheckoutRequest) => request<CheckoutResponse>("POST", "/v1/billing/checkout", b),

  // ── Policies ──────────────────────────────────────────────────────────────
  listPolicies: (lifecycle?: string) =>
    request<PolicyListResponse>(
      "GET",
      `/v1/policies${lifecycle ? `?lifecycle=${encodeURIComponent(lifecycle)}` : ""}`,
    ),
  listVersions: (id: string) =>
    request<PolicyListResponse>("GET", `/v1/policies/${encodeURIComponent(id)}`),
  registerPolicy: (b: PolicyRegisterBody) => request<PolicyResponse>("POST", "/v1/policies", b),
  submitPolicy: (id: string, v: number) =>
    request<PolicyResponse>("POST", `/v1/policies/${encodeURIComponent(id)}/versions/${v}/submit`),
  uploadImpactReport: (id: string, v: number, b: ImpactReportBody) =>
    request("PUT", `/v1/policies/${encodeURIComponent(id)}/versions/${v}/impact-report`, b),
  simulatePolicy: (id: string, v: number, b: { reviewed_by: string; group_key?: string; auto_store?: boolean }) =>
    request<SimulateResponse>("POST", `/v1/policies/${encodeURIComponent(id)}/versions/${v}/simulate`, b),
  activatePolicy: (id: string, v: number, impact_report?: ImpactReportBody) =>
    request<PolicyResponse>(
      "POST",
      `/v1/policies/${encodeURIComponent(id)}/versions/${v}/activate`,
      { impact_report: impact_report ?? null },
    ),
  deprecatePolicy: (id: string, v: number) =>
    request<PolicyResponse>("POST", `/v1/policies/${encodeURIComponent(id)}/versions/${v}/deprecate`),

  // ── Dashboard ─────────────────────────────────────────────────────────────
  overview: () => request<DashboardOverview>("GET", `/v1/dashboard/${tenant()}/overview`),
  decisions: (windowDays = 7) =>
    request<DecisionTimeline>("GET", `/v1/dashboard/${tenant()}/decisions?window_days=${windowDays}`),
  topActions: (limit = 10) =>
    request<TopActions>("GET", `/v1/dashboard/${tenant()}/actions/top?limit=${limit}`),
  hitlQueue: () => request<HitlQueue>("GET", `/v1/dashboard/${tenant()}/hitl/queue`),

  // ── Audit trail ───────────────────────────────────────────────────────────
  ledgerTrail: () => request<LedgerTrail>("GET", `/v1/ledger/${tenant()}/trail`),

  // ── Approvals ─────────────────────────────────────────────────────────────
  listApprovals: () => request<ApprovalList>("GET", "/v1/approvals"),
  approve: (handleId: string) =>
    request<ApprovalRecord>("POST", `/v1/approvals/${encodeURIComponent(handleId)}/approve`),
  reject: (handleId: string) =>
    request<ApprovalRecord>("POST", `/v1/approvals/${encodeURIComponent(handleId)}/reject`),
};
