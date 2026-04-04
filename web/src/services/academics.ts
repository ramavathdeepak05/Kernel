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
  return response.json();
}

// ── Types ────────────────────────────────────────────────────

export interface Program {
  id: string;
  org_id: string;
  name: string;
  code: string;
  degree_type: string;
  duration_years: number;
  total_semesters: number;
  total_credits: number;
  status: string;
  created_at?: string;
}

export interface Course {
  id: string;
  org_id: string;
  program_id: string;
  name: string;
  code: string;
  semester: number;
  credits: number;
  lecture_hours: number;
  tutorial_hours: number;
  practical_hours: number;
  course_type: string;
  status: string;
  faculty_id?: string;
  faculty_name?: string;
}

export interface TimetableSlot {
  id: string;
  org_id: string;
  course_id: string;
  course_name?: string;
  course_code?: string;
  faculty_id: string;
  section: string;
  day_of_week: number;
  start_time: string;
  end_time: string;
  room: string;
  slot_type: string;
  academic_year: string;
}

export interface AttendanceSummary {
  student_id: string;
  student_name?: string;
  course_id: string;
  course_name?: string;
  total_sessions: number;
  attended: number;
  percentage: number;
  status: "ON_TRACK" | "AT_RISK" | "CRITICAL" | "INELIGIBLE";
}

export interface AtRiskStudent {
  student_id: string;
  student_name: string;
  roll_number?: string;
  program?: string;
  risk_level: "GREEN" | "AMBER" | "RED";
  attendance_pct: number;
  courses_at_risk: number;
  mentor_name?: string;
  last_alert?: string;
}

export interface AcademicsInsight {
  total_enrolled: number;
  total_courses: number;
  avg_attendance_pct: number;
  at_risk_count: number;
  critical_count: number;
  ineligible_count: number;
  courses_below_75: number;
  top_absent_courses: { course_name: string; avg_pct: number }[];
  insights?: string[];
}

// ── Programs ─────────────────────────────────────────────────

export const programsApi = {
  list: () => apiFetch<{ programs: Program[]; total: number }>("/academics/programs"),
  get: (id: string) => apiFetch<Program>(`/academics/programs/${id}`),
  create: (data: Partial<Program>) =>
    apiFetch<Program>("/academics/programs", { method: "POST", body: JSON.stringify(data) }),
};

// ── Courses ──────────────────────────────────────────────────

export const coursesApi = {
  list: (params: { program_id?: string; semester?: number } = {}) => {
    const q = new URLSearchParams(params as Record<string, string>).toString();
    return apiFetch<{ courses: Course[]; total: number }>(`/academics/courses${q ? `?${q}` : ""}`);
  },
  get: (id: string) => apiFetch<Course>(`/academics/courses/${id}`),
  create: (data: Partial<Course>) =>
    apiFetch<Course>("/academics/courses", { method: "POST", body: JSON.stringify(data) }),
};

// ── Timetable ────────────────────────────────────────────────

export const timetableApi = {
  get: (params: { academic_year?: string; course_id?: string; faculty_id?: string } = {}) => {
    const q = new URLSearchParams(params as Record<string, string>).toString();
    return apiFetch<{ slots: TimetableSlot[]; total: number }>(`/academics/timetable${q ? `?${q}` : ""}`);
  },
  addSlot: (data: Partial<TimetableSlot>) =>
    apiFetch<TimetableSlot>("/academics/timetable", { method: "POST", body: JSON.stringify(data) }),
  deleteSlot: (slot_id: string) =>
    apiFetch<void>(`/academics/timetable/${slot_id}`, { method: "DELETE" }),
};

// ── Attendance ───────────────────────────────────────────────

export const attendanceApi = {
  forStudent: (student_id: string, course_id = "", academic_year = "") => {
    const q = new URLSearchParams({ course_id, academic_year }).toString();
    return apiFetch<AttendanceSummary>(`/academics/attendance/student/${student_id}?${q}`);
  },
  forCourse: (course_id: string, academic_year = "") =>
    apiFetch<{ summary: AttendanceSummary[]; total: number }>(
      `/academics/attendance/course/${course_id}?academic_year=${academic_year}`
    ),
  mark: (data: {
    course_id: string; session_date: string; session_type: string;
    records: { student_id: string; status: string }[];
  }) => apiFetch<object>("/academics/attendance", { method: "POST", body: JSON.stringify(data) }),
};

// ── Analytics ────────────────────────────────────────────────

export const academicsAnalyticsApi = {
  atRisk: (params: { academic_year?: string; course_id?: string } = {}) => {
    const q = new URLSearchParams(params as Record<string, string>).toString();
    return apiFetch<{ at_risk: AtRiskStudent[]; total: number }>(`/academics/analytics/at-risk${q ? `?${q}` : ""}`);
  },
  insights: (params: { academic_year?: string; course_id?: string } = {}) => {
    const q = new URLSearchParams(params as Record<string, string>).toString();
    return apiFetch<AcademicsInsight>(`/academics/analytics/insights${q ? `?${q}` : ""}`);
  },
};
