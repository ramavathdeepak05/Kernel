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
  return response.json();
}

// ── Types ────────────────────────────────────────────────────

export type MaterialType =
  | "LECTURE_NOTES"
  | "QUIZ"
  | "ASSIGNMENT_BRIEF"
  | "LESSON_PLAN"
  | "SLIDES"
  | "REFERENCE"
  | "OTHER";

export type MaterialStatus = "DRAFT" | "PUBLISHED" | "ARCHIVED";
export type AssignmentStatus = "DRAFT" | "PUBLISHED" | "CLOSED" | "ARCHIVED";
export type SubmissionStatus =
  | "DRAFT"
  | "SUBMITTED"
  | "UNDER_REVIEW"
  | "GRADED"
  | "RETURNED";

export interface CourseMaterial {
  id: string;
  org_id: string;
  course_id: string;
  co_id?: string;
  title: string;
  material_type: MaterialType;
  content_body?: string;
  file_url?: string;
  is_ai_generated: boolean;
  status: MaterialStatus;
  visible_to_students: boolean;
  week_number?: number;
  created_by: string;
  created_at: string;
  published_at?: string;
}

export interface Assignment {
  id: string;
  org_id: string;
  course_id: string;
  co_id?: string;
  title: string;
  description?: string;
  max_marks: number;
  passing_marks?: number;
  due_date: string;
  allow_late: boolean;
  late_penalty_pct: number;
  is_ai_generated: boolean;
  status: AssignmentStatus;
  created_by: string;
  created_at: string;
}

export interface AssignmentSubmission {
  id: string;
  org_id: string;
  assignment_id: string;
  student_id: string;
  enrollment_id?: string;
  content_text?: string;
  file_url?: string;
  submitted_at?: string;
  is_late: boolean;
  status: SubmissionStatus;
  marks_awarded?: number;
  late_deduction?: number;
  effective_marks?: number;
  feedback?: string;
  graded_by?: string;
  graded_at?: string;
}

export type GenerationType =
  | "lecture_notes"
  | "quiz_questions"
  | "assignment_questions"
  | "lesson_plan";

export interface GenerateMaterialRequest {
  generation_type: GenerationType;
  co_id?: string;
  week_number?: number;
  auto_publish?: boolean;
  generation_params?: {
    lecture_duration_minutes?: number;
    num_questions?: number;
    question_type?: string;
    difficulty?: string;
    num_weeks?: number;
    teaching_method?: string;
  };
}

export interface GenerateAssignmentRequest {
  co_id?: string;
  title?: string;
  due_date: string;
  max_marks?: number;
  auto_publish?: boolean;
  generation_params?: {
    num_questions?: number;
    marks_per_q?: number;
  };
}

// ── API ──────────────────────────────────────────────────────

export const learningApi = {
  // Materials
  listMaterials(
    courseId: string,
    params?: { week?: number; type?: string }
  ): Promise<{ materials: CourseMaterial[]; total: number }> {
    const qs = new URLSearchParams();
    if (params?.week) qs.set("week", String(params.week));
    if (params?.type) qs.set("type", params.type);
    const q = qs.toString();
    return apiFetch(`/learning/courses/${courseId}/materials${q ? `?${q}` : ""}`);
  },

  getMaterial(materialId: string): Promise<CourseMaterial> {
    return apiFetch(`/learning/materials/${materialId}`);
  },

  createMaterial(
    courseId: string,
    body: {
      title: string;
      material_type: MaterialType;
      content_body?: string;
      file_url?: string;
      co_id?: string;
      week_number?: number;
    }
  ): Promise<CourseMaterial> {
    return apiFetch(`/learning/courses/${courseId}/materials`, {
      method: "POST",
      body: JSON.stringify(body),
    });
  },

  generateMaterial(
    courseId: string,
    body: GenerateMaterialRequest
  ): Promise<{ material: CourseMaterial; ai_confidence: number | null; ai_confidence_tier: string | null }> {
    return apiFetch(`/learning/courses/${courseId}/materials/generate`, {
      method: "POST",
      body: JSON.stringify(body),
    });
  },

  publishMaterial(materialId: string): Promise<CourseMaterial> {
    return apiFetch(`/learning/materials/${materialId}/publish`, { method: "PATCH" });
  },

  archiveMaterial(materialId: string): Promise<CourseMaterial> {
    return apiFetch(`/learning/materials/${materialId}/archive`, { method: "PATCH" });
  },

  // Assignments
  listAssignments(
    courseId: string
  ): Promise<{ assignments: Assignment[]; total: number }> {
    return apiFetch(`/learning/courses/${courseId}/assignments`);
  },

  getAssignment(assignmentId: string): Promise<Assignment> {
    return apiFetch(`/learning/assignments/${assignmentId}`);
  },

  createAssignment(
    courseId: string,
    body: {
      title: string;
      description: string;
      max_marks?: number;
      due_date: string;
      co_id?: string;
      passing_marks?: number;
      allow_late?: boolean;
      late_penalty_pct?: number;
    }
  ): Promise<Assignment> {
    return apiFetch(`/learning/courses/${courseId}/assignments`, {
      method: "POST",
      body: JSON.stringify(body),
    });
  },

  generateAssignment(
    courseId: string,
    body: GenerateAssignmentRequest
  ): Promise<{ assignment: Assignment; ai_confidence: number | null }> {
    return apiFetch(`/learning/courses/${courseId}/assignments/generate`, {
      method: "POST",
      body: JSON.stringify(body),
    });
  },

  publishAssignment(assignmentId: string): Promise<Assignment> {
    return apiFetch(`/learning/assignments/${assignmentId}/publish`, { method: "PATCH" });
  },

  closeAssignment(assignmentId: string): Promise<Assignment> {
    return apiFetch(`/learning/assignments/${assignmentId}/close`, { method: "PATCH" });
  },

  // Submissions (student)
  saveDraft(
    assignmentId: string,
    body: { content_text?: string; file_url?: string }
  ): Promise<AssignmentSubmission> {
    return apiFetch(`/learning/assignments/${assignmentId}/my-submission`, {
      method: "PUT",
      body: JSON.stringify(body),
    });
  },

  submitAssignment(assignmentId: string): Promise<AssignmentSubmission> {
    return apiFetch(`/learning/assignments/${assignmentId}/my-submission/submit`, {
      method: "POST",
    });
  },

  getMySubmission(assignmentId: string): Promise<AssignmentSubmission> {
    return apiFetch(`/learning/assignments/${assignmentId}/my-submission`);
  },

  // Submissions (faculty)
  listSubmissions(
    assignmentId: string,
    status?: string
  ): Promise<{ submissions: AssignmentSubmission[]; total: number }> {
    const qs = status ? `?status=${status}` : "";
    return apiFetch(`/learning/assignments/${assignmentId}/submissions${qs}`);
  },

  beginReview(submissionId: string): Promise<AssignmentSubmission> {
    return apiFetch(`/learning/submissions/${submissionId}/begin-review`, { method: "PATCH" });
  },

  gradeSubmission(
    submissionId: string,
    body: { marks_awarded: number; feedback?: string }
  ): Promise<AssignmentSubmission> {
    return apiFetch(`/learning/submissions/${submissionId}/grade`, {
      method: "PATCH",
      body: JSON.stringify(body),
    });
  },

  returnSubmission(submissionId: string): Promise<AssignmentSubmission> {
    return apiFetch(`/learning/submissions/${submissionId}/return`, { method: "PATCH" });
  },
};
