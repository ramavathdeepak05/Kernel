const API_BASE = import.meta.env.VITE_API_URL || "http://localhost:8000/api/v1";

async function apiFetch<T>(endpoint: string, options: RequestInit = {}): Promise<T> {
  const token = localStorage.getItem("token");
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

export interface FeeStructure {
  id: string;
  org_id: string;
  program_id: string;
  program_name?: string;
  academic_year: string;
  semester: number;
  tuition_fee: number;
  lab_fee: number;
  exam_fee: number;
  misc_fee: number;
  total_fee: number;
  due_date: string;
  late_fee_per_day: number;
  is_active: boolean;
}

export interface Invoice {
  id: string;
  student_id: string;
  student_name?: string;
  roll_number?: string;
  fee_structure_id: string;
  academic_year: string;
  semester: number;
  total_amount: number;
  discount_amount: number;
  net_amount: number;
  paid_amount: number;
  balance: number;
  status: "PENDING" | "PARTIAL" | "PAID" | "OVERDUE" | "WAIVED" | "CANCELLED";
  due_date: string;
  created_at: string;
}

export interface Payment {
  id: string;
  student_id: string;
  invoice_id: string;
  amount: number;
  payment_method: "ONLINE" | "CASH" | "DD" | "CHEQUE" | "NEFT" | "UPI";
  transaction_id?: string;
  status: "SUCCESS" | "PENDING" | "FAILED" | "REFUNDED";
  paid_at: string;
}

export interface Scholarship {
  id: string;
  name: string;
  type: "MERIT" | "NEED" | "SPORTS" | "GOVERNMENT" | "MANAGEMENT";
  discount_type: "PERCENTAGE" | "FIXED";
  discount_value: number;
  applicable_fee_heads: string[];
  is_active: boolean;
}

export interface Waiver {
  id: string;
  student_id: string;
  student_name?: string;
  invoice_id: string;
  requested_amount: number;
  approved_amount?: number;
  reason: string;
  status: "PENDING" | "APPROVED" | "REJECTED";
  requested_at: string;
  decided_at?: string;
  decided_by?: string;
}

export interface CollectionReport {
  total_invoiced: number;
  total_collected: number;
  total_pending: number;
  collection_rate: number;
  overdue_count: number;
  overdue_amount: number;
}

export interface DefaultRisk {
  student_id: string;
  student_name: string;
  roll_number?: string;
  balance: number;
  days_overdue: number;
  risk_level: "LOW" | "MEDIUM" | "HIGH" | "CRITICAL";
}

// ── Fee Structures ─────────────────────────────────────────────

export const feeStructuresApi = {
  list: (academic_year?: string, program_id?: string) => {
    const p = new URLSearchParams();
    if (academic_year) p.set("academic_year", academic_year);
    if (program_id) p.set("program_id", program_id);
    return apiFetch<{ fee_structures: FeeStructure[]; total: number }>(
      `/finance/fee-structures${p.toString() ? `?${p}` : ""}`
    );
  },
};

// ── Invoices ───────────────────────────────────────────────────

export const invoicesApi = {
  forStudent: (student_id: string, academic_year?: string) => {
    const p = academic_year ? `?academic_year=${academic_year}` : "";
    return apiFetch<{ invoices: Invoice[]; total: number }>(`/finance/invoices/student/${student_id}${p}`);
  },
};

// ── Payments ───────────────────────────────────────────────────

export const paymentsApi = {
  forStudent: (student_id: string) =>
    apiFetch<{ payments: Payment[]; total: number }>(`/finance/payments/student/${student_id}`),
};

// ── Scholarships ───────────────────────────────────────────────

export const scholarshipsApi = {
  list: () => apiFetch<{ scholarships: Scholarship[]; total: number }>("/finance/scholarships"),
};

// ── Waivers ────────────────────────────────────────────────────

export const waiversApi = {
  pending: () => apiFetch<{ waivers: Waiver[]; total: number }>("/finance/waivers/pending"),
};

// ── Reports ────────────────────────────────────────────────────

export const financeReportsApi = {
  collection: (academic_year: string, semester?: number) => {
    const p = new URLSearchParams({ academic_year });
    if (semester) p.set("semester", String(semester));
    return apiFetch<CollectionReport>(`/finance/reports/collection?${p}`);
  },
  defaultRisk: (academic_year?: string) => {
    const p = academic_year ? `?academic_year=${academic_year}` : "";
    return apiFetch<{ students: DefaultRisk[]; total: number }>(`/finance/analytics/default-risk${p}`);
  },
  monthly: (academic_year: string) =>
    apiFetch<{ months: { month: string; collected: number; invoiced: number }[] }>(
      `/finance/reports/monthly?academic_year=${academic_year}`
    ),
};
