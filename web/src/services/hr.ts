const API_BASE = import.meta.env.VITE_API_URL || "http://localhost:8000/api/v1";

async function apiFetch<T>(endpoint: string, options: RequestInit = {}): Promise<T> {
  const token = sessionStorage.getItem("token");
  const headers = {
    "Content-Type": "application/json",
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
    ...(options.headers as object | undefined),
  };
  const response = await fetch(`${API_BASE}${endpoint}`, { ...options, headers });
  if (!response.ok) {
    const err = await response.json().catch(() => ({ detail: "Unknown error" }));
    throw new Error(err.detail || err.message || `API error ${response.status}`);
  }
  if (response.status === 204) return undefined as T;
  return response.json();
}

// ── Types ──────────────────────────────────────────────────────

export interface StaffMember {
  id: string;
  user_id: string;
  org_id: string;
  employee_code: string;
  display_name?: string;
  email?: string;
  department: string;
  designation: string;
  employment_type: "FULL_TIME" | "PART_TIME" | "CONTRACT" | "VISITING";
  join_date: string;
  status: "ACTIVE" | "ON_LEAVE" | "INACTIVE" | "TERMINATED";
  reporting_to?: string;
  reporting_name?: string;
}

export interface LeaveRequest {
  id: string;
  staff_id: string;
  staff_name?: string;
  leave_type_name?: string;
  from_date: string;
  to_date: string;
  days: number;
  reason: string;
  status: "PENDING" | "APPROVED" | "REJECTED" | "CANCELLED";
  applied_at: string;
  decided_at?: string;
}

export interface PayrollSummary {
  total_staff: number;
  total_gross: number;
  total_deductions: number;
  total_net: number;
  paid_count: number;
  pending_count: number;
  month: string;
}

export interface PerformanceReview {
  id: string;
  staff_id: string;
  staff_name?: string;
  reviewer_id: string;
  reviewer_name?: string;
  review_period: string;
  overall_rating: number;
  status: "DRAFT" | "SUBMITTED" | "ACKNOWLEDGED" | "CLOSED";
  submitted_at?: string;
}

export interface DeptAttendanceSummary {
  department: string;
  total_staff: number;
  present_count: number;
  absent_count: number;
  leave_count: number;
  attendance_pct: number;
}

export interface HRInsight {
  total_staff: number;
  active_staff: number;
  avg_leave_utilization: number;
  pending_reviews: number;
  departments: number;
  insights?: string[];
}

// ── Staff ──────────────────────────────────────────────────────

export const staffApi = {
  list: (department?: string, status?: string) => {
    const p = new URLSearchParams();
    if (department) p.set("department", department);
    if (status) p.set("status", status);
    return apiFetch<{ staff: StaffMember[]; total: number }>(
      `/hr/staff${p.toString() ? `?${p}` : ""}`
    );
  },
  get: (id: string) => apiFetch<StaffMember>(`/hr/staff/${id}`),
};

// ── Leave ──────────────────────────────────────────────────────

export const leaveApi = {
  pending: () => apiFetch<{ leave_requests: LeaveRequest[]; total: number }>("/hr/leave/pending"),
};

// ── Payroll ────────────────────────────────────────────────────

export const payrollApi = {
  summary: (month?: string) => {
    const p = month ? `?month=${month}` : "";
    return apiFetch<PayrollSummary>(`/hr/payroll/summary${p}`);
  },
};

// ── Performance ────────────────────────────────────────────────

export const performanceApi = {
  pending: () =>
    apiFetch<{ reviews: PerformanceReview[]; total: number }>("/hr/reviews/pending"),
};

// ── Attendance ─────────────────────────────────────────────────

export const hrAttendanceApi = {
  deptSummary: (date?: string) => {
    const p = date ? `?date=${date}` : "";
    return apiFetch<{ departments: DeptAttendanceSummary[] }>(`/hr/attendance/department/summary${p}`);
  },
};

// ── Analytics ──────────────────────────────────────────────────

export const hrAnalyticsApi = {
  insights: () => apiFetch<HRInsight>("/hr/analytics/ai-insights"),
  workload: () => apiFetch<{ staff: { staff_id: string; staff_name: string; workload_score: number; courses: number }[] }>("/hr/analytics/workload"),
  leavePatterns: () => apiFetch<{ patterns: { department: string; avg_days: number; peak_month: string }[] }>("/hr/analytics/leave-patterns"),
};
