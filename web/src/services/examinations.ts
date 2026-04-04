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

export interface ExamSchedule {
  id: string;
  org_id: string;
  course_id: string;
  course_name?: string;
  course_code?: string;
  academic_year: string;
  semester: number;
  exam_type: "INTERNAL" | "MID_TERM" | "SEMESTER_END" | "SUPPLEMENTARY" | "REAPPEAR";
  exam_date: string;
  start_time: string;
  end_time: string;
  venue: string;
  max_marks: number;
  pass_marks: number;
  status: "DRAFT" | "PUBLISHED" | "ONGOING" | "COMPLETED" | "CANCELLED";
  created_at?: string;
}

export interface HallTicket {
  id: string;
  student_id: string;
  student_name?: string;
  roll_number?: string;
  exam_schedule_id: string;
  course_name?: string;
  exam_date?: string;
  venue?: string;
  seat_number?: string;
  issued_at: string;
  is_valid: boolean;
}

export interface StudentGrade {
  id: string;
  student_id: string;
  student_name?: string;
  course_id: string;
  course_name?: string;
  course_code?: string;
  credits?: number;
  academic_year: string;
  semester: number;
  exam_type: string;
  marks_obtained: number;
  max_marks: number;
  grade?: string;
  grade_points?: number;
  is_pass: boolean;
  entered_by?: string;
  entered_at?: string;
}

export interface SemesterResult {
  id: string;
  student_id: string;
  academic_year: string;
  semester: number;
  sgpa: number;
  cgpa: number;
  total_credits: number;
  credits_earned: number;
  status: "PASS" | "FAIL" | "DETAINED" | "WITHHELD";
  published_at?: string;
}

export interface Transcript {
  id: string;
  student_id: string;
  student_name?: string;
  generated_at: string;
  is_official: boolean;
  file_url?: string;
  semesters?: SemesterResult[];
}

export interface ReEvalRequest {
  id: string;
  student_id: string;
  student_name?: string;
  course_id: string;
  course_name?: string;
  academic_year: string;
  semester: number;
  exam_type: string;
  reason: string;
  status: "PENDING" | "UNDER_REVIEW" | "REVISED" | "REJECTED" | "CLOSED";
  original_marks?: number;
  revised_marks?: number;
  submitted_at: string;
  decided_at?: string;
}

export interface SemesterAnalytics {
  total_students: number;
  total_courses: number;
  pass_count: number;
  fail_count: number;
  pass_percentage: number;
  avg_sgpa: number;
  top_sgpa: number;
  grade_distribution: Record<string, number>;
  insights?: string[];
}

export interface CourseAnalytics {
  course_name: string;
  course_code: string;
  total_appeared: number;
  pass_count: number;
  fail_count: number;
  avg_marks: number;
  highest_marks: number;
  lowest_marks: number;
  grade_distribution: Record<string, number>;
}

// ── Exam Schedules ─────────────────────────────────────────────

export const examSchedulesApi = {
  list: (academic_year: string, semester?: number, exam_type?: string) => {
    const p = new URLSearchParams({ academic_year });
    if (semester) p.set("semester", String(semester));
    if (exam_type) p.set("exam_type", exam_type);
    return apiFetch<{ schedules: ExamSchedule[]; total: number }>(`/exams/schedules?${p}`);
  },
  get: (id: string) => apiFetch<ExamSchedule>(`/exams/schedules/${id}`),
  create: (data: Partial<ExamSchedule>) =>
    apiFetch<ExamSchedule>("/exams/schedules", { method: "POST", body: JSON.stringify(data) }),
  updateStatus: (id: string, status: string) =>
    apiFetch<ExamSchedule>(`/exams/schedules/${id}/status`, {
      method: "PATCH",
      body: JSON.stringify({ status }),
    }),
};

// ── Hall Tickets ───────────────────────────────────────────────

export const hallTicketsApi = {
  issue: (academic_year: string, semester: number, exam_type?: string) =>
    apiFetch<{ issued: number }>("/exams/hall-tickets/issue", {
      method: "POST",
      body: JSON.stringify({ academic_year, semester, exam_type }),
    }),
  forStudent: (student_id: string, academic_year: string) =>
    apiFetch<{ hall_tickets: HallTicket[] }>(
      `/exams/hall-tickets/student/${student_id}?academic_year=${academic_year}`
    ),
};

// ── Grades ─────────────────────────────────────────────────────

export const gradesApi = {
  forStudent: (student_id: string, academic_year: string, semester?: number) => {
    const p = new URLSearchParams({ academic_year });
    if (semester) p.set("semester", String(semester));
    return apiFetch<{ grades: StudentGrade[]; total: number }>(
      `/exams/grades/student/${student_id}?${p}`
    );
  },
  bulkEntry: (data: {
    exam_schedule_id: string;
    grades: { student_id: string; marks_obtained: number }[];
  }) => apiFetch<{ saved: number }>("/exams/grades/bulk", { method: "POST", body: JSON.stringify(data) }),
};

// ── Results ────────────────────────────────────────────────────

export const resultsApi = {
  forStudent: (student_id: string) =>
    apiFetch<{ results: SemesterResult[]; total: number }>(`/exams/results/student/${student_id}`),
  compute: (student_id: string, academic_year: string, semester: number) =>
    apiFetch<SemesterResult>("/exams/results/compute", {
      method: "POST",
      body: JSON.stringify({ student_id, academic_year, semester }),
    }),
  publish: (academic_year: string, semester: number) =>
    apiFetch<{ published: number }>("/exams/results/publish", {
      method: "POST",
      body: JSON.stringify({ academic_year, semester }),
    }),
};

// ── Transcripts ────────────────────────────────────────────────

export const transcriptsApi = {
  forStudent: (student_id: string) =>
    apiFetch<{ transcripts: Transcript[] }>(`/exams/transcripts/student/${student_id}`),
  generate: (student_id: string, is_official = false) =>
    apiFetch<Transcript>("/exams/transcripts/generate", {
      method: "POST",
      body: JSON.stringify({ student_id, is_official }),
    }),
};

// ── Re-evaluation ──────────────────────────────────────────────

export const reevalApi = {
  pending: () => apiFetch<{ reeval_requests: ReEvalRequest[]; total: number }>("/exams/reeval/pending"),
  forStudent: (student_id: string) =>
    apiFetch<{ reeval_requests: ReEvalRequest[] }>(`/exams/reeval/student/${student_id}`),
};

// ── Analytics ──────────────────────────────────────────────────

export const examAnalyticsApi = {
  semester: (academic_year: string, semester: number) => {
    const p = new URLSearchParams({ academic_year, semester: String(semester) });
    return apiFetch<SemesterAnalytics>(`/exams/analytics/semester?${p}`);
  },
  aiInsights: (academic_year: string, semester: number) => {
    const p = new URLSearchParams({ academic_year, semester: String(semester) });
    return apiFetch<SemesterAnalytics>(`/exams/analytics/semester/ai-insights?${p}`);
  },
  studentTrend: (student_id: string) =>
    apiFetch<{ trend: { semester: number; sgpa: number; cgpa: number }[] }>(
      `/exams/analytics/student/${student_id}/trend`
    ),
};
