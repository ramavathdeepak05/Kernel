import { alisApi } from "@/lib/alis-api";

// ── Types ──────────────────────────────────────────────────────

export interface DashboardKPIs {
  total_students: number;
  active_faculty: number;
  fee_collected_month: number;
  fee_collected_ytd: number;
  pending_approvals: number;
  at_risk_students: number;
  avg_attendance_pct: number;
  exams_this_week: number;
}

export interface AdmissionsFunnel {
  stage: string;
  count: number;
  conversion_rate: number;
}

export interface AcademicsAttendanceStat {
  department: string;
  avg_attendance: number;
  below_75_count: number;
  total_students: number;
}

export interface FinanceYoY {
  year: string;
  collected: number;
  target: number;
  defaulters: number;
}

export interface SavedReport {
  id: string;
  name: string;
  module: string;
  query_config: Record<string, unknown>;
  last_run_at?: string;
  created_at: string;
}

export interface ExportRecord {
  id: string;
  report_name: string;
  format: "CSV" | "XLSX" | "PDF";
  status: "PENDING" | "PROCESSING" | "READY" | "FAILED";
  file_url?: string;
  rows_exported?: number;
  created_at: string;
}

export interface AIInsight {
  category: string;
  insight: string;
  severity: "info" | "warning" | "critical";
  suggested_action?: string;
}

// ── API clients ────────────────────────────────────────────────

export const dashboardApi = {
  kpis: () =>
    alisApi.get<DashboardKPIs>("/reports/dashboard/kpis"),
  trend: (key: string) =>
    alisApi.get<{ date: string; value: number }[]>(`/reports/dashboard/trend/${key}`),
};

export const admissionsReportApi = {
  funnel: () =>
    alisApi.get<AdmissionsFunnel[]>("/reports/admissions/funnel"),
  programs: () =>
    alisApi.get<{ program: string; applied: number; enrolled: number; target: number }[]>(
      "/reports/admissions/programs"
    ),
  monthly: () =>
    alisApi.get<{ month: string; applications: number; enrollments: number }[]>(
      "/reports/admissions/monthly"
    ),
};

export const academicsReportApi = {
  attendance: () =>
    alisApi.get<AcademicsAttendanceStat[]>("/reports/academics/attendance"),
  facultyWorkload: () =>
    alisApi.get<{ name: string; courses: number; students: number; hours_per_week: number }[]>(
      "/reports/academics/faculty-workload"
    ),
  aiInsights: () =>
    alisApi.get<AIInsight[]>("/reports/academics/ai-insights"),
};

export const financeReportApi = {
  yoy: () =>
    alisApi.get<FinanceYoY[]>("/reports/finance/year-over-year"),
  aging: () =>
    alisApi.get<{ bucket: string; count: number; amount: number }[]>(
      "/reports/finance/aging"
    ),
  aiInsights: () =>
    alisApi.get<AIInsight[]>("/reports/finance/ai-insights"),
};

export const savedReportsApi = {
  list: () =>
    alisApi.get<SavedReport[]>("/reports/saved"),
  create: (data: Partial<SavedReport>) =>
    alisApi.post<SavedReport>("/reports/saved", data),
  run: (id: string) =>
    alisApi.post<{ export_id: string }>(`/reports/saved/${id}/run`),
  delete: (id: string) =>
    alisApi.delete<{ ok: boolean }>(`/reports/saved/${id}`),
};

export const exportApi = {
  list: () =>
    alisApi.get<ExportRecord[]>("/reports/exports"),
  create: (data: { report_name: string; format: string; module?: string }) =>
    alisApi.post<ExportRecord>("/reports/exports", data),
};

export const aiReportApi = {
  summary: () =>
    alisApi.get<AIInsight[]>("/reports/ai/institution-summary"),
};
