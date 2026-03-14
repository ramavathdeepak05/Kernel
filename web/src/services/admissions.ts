import type {
  Applicant,
  Application,
  ApplicationDocument,
  EligibilityResult,
  EnrollmentRecord,
  EntranceTest,
  FinalVerification,
  Interview,
  Lead,
  LeadActivity,
  MeritList,
  OfferLetter,
  PaymentRecord,
  PipelineStage,
  ReviewItem,
  SeatMatrix,
  TestRegistration,
  TestSlot,
} from "../types/admissions";

const API_BASE = import.meta.env.VITE_API_URL || "http://localhost:8000/api/v1";

async function apiFetch<T>(endpoint: string, options: RequestInit = {}): Promise<T> {
  const token = localStorage.getItem("token");
  const isFormData = options.body instanceof FormData;
  const contentHeader = isFormData ? {} : { "Content-Type": "application/json" };
  const headers = {
    ...contentHeader,
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
    ...(options.headers as object | undefined),
  };
  const response = await fetch(`${API_BASE}${endpoint}`, { ...options, headers });
  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: "Unknown error" }));
    throw new Error(error.detail || `API error ${response.status}`);
  }
  return response.json();
}

// ─── Leads ──────────────────────────────────────────────────

export const leadsApi = {
  list: (params: { skip?: number; limit?: number; status?: string } = {}) => {
    const q = new URLSearchParams(params as Record<string, string>).toString();
    return apiFetch<Lead[]>(`/admissions/leads${q ? `?${q}` : ""}`);
  },
  get: (id: string) => apiFetch<Lead>(`/admissions/leads/${id}`),
  create: (data: Partial<Lead>) =>
    apiFetch<Lead>("/admissions/leads", { method: "POST", body: JSON.stringify(data) }),
  update: (id: string, data: Partial<Lead>) =>
    apiFetch<Lead>(`/admissions/leads/${id}`, { method: "PATCH", body: JSON.stringify(data) }),
  transition: (id: string, new_status: string, notes?: string) =>
    apiFetch<Lead>(`/admissions/leads/${id}/transition`, {
      method: "POST",
      body: JSON.stringify({ new_status, notes }),
    }),
  assign: (id: string, counselor_id: string) =>
    apiFetch<Lead>(`/admissions/leads/${id}/assign`, {
      method: "POST",
      body: JSON.stringify({ counselor_id }),
    }),
  activities: (id: string) =>
    apiFetch<LeadActivity[]>(`/admissions/leads/${id}/activities`),
  addActivity: (id: string, activity_type: string, description: string) =>
    apiFetch<LeadActivity>(`/admissions/leads/${id}/activities`, {
      method: "POST",
      body: JSON.stringify({ activity_type, description }),
    }),
  convertToApplication: (id: string) =>
    apiFetch<Application>(`/admissions/leads/${id}/convert`, { method: "POST" }),
};

// ─── Applications ────────────────────────────────────────────

export const applicationsApi = {
  list: (params: { skip?: number; limit?: number; status?: string; program?: string } = {}) => {
    const q = new URLSearchParams(params as Record<string, string>).toString();
    return apiFetch<Application[]>(`/admissions/applications${q ? `?${q}` : ""}`);
  },
  get: (id: string) => apiFetch<Application>(`/admissions/applications/${id}`),
  create: (data: Partial<Application>) =>
    apiFetch<Application>("/admissions/applications", {
      method: "POST",
      body: JSON.stringify(data),
    }),
  update: (id: string, data: Partial<Application>) =>
    apiFetch<Application>(`/admissions/applications/${id}`, {
      method: "PATCH",
      body: JSON.stringify(data),
    }),
  submit: (id: string) =>
    apiFetch<Application>(`/admissions/applications/${id}/submit`, { method: "POST" }),
  withdraw: (id: string, reason: string) =>
    apiFetch<Application>(`/admissions/applications/${id}/withdraw`, {
      method: "POST",
      body: JSON.stringify({ reason }),
    }),
  // Legacy compat
  getApplicants: (params: { limit?: number; skip?: number } = {}) =>
    apiFetch<Applicant[]>(`/admissions/applicants?limit=${params.limit || 50}`),
  getReviewQueue: () => apiFetch<ReviewItem[]>("/admissions/review-queue"),
  getPipelineSummary: () => apiFetch<PipelineStage[]>("/admissions/pipeline-summary"),
};

// ─── Documents ───────────────────────────────────────────────

export const documentsApi = {
  list: (application_id: string) =>
    apiFetch<ApplicationDocument[]>(`/admissions/applications/${application_id}/documents`),
  upload: (application_id: string, document_type: string, file: File) => {
    const form = new FormData();
    form.append("document_type", document_type);
    form.append("file", file);
    return apiFetch<ApplicationDocument>(
      `/admissions/applications/${application_id}/documents/upload`,
      { method: "POST", body: form }
    );
  },
  review: (application_id: string, document_id: string, status: string, rejection_reason?: string) =>
    apiFetch<ApplicationDocument>(
      `/admissions/applications/${application_id}/documents/${document_id}/review`,
      { method: "POST", body: JSON.stringify({ status, rejection_reason }) }
    ),
  reviewQueue: (params: { skip?: number; limit?: number } = {}) => {
    const q = new URLSearchParams(params as Record<string, string>).toString();
    return apiFetch<ApplicationDocument[]>(`/admissions/documents/review-queue${q ? `?${q}` : ""}`);
  },
};

// ─── Eligibility ─────────────────────────────────────────────

export const eligibilityApi = {
  check: (application_id: string, criteria_set_id?: string) =>
    apiFetch<EligibilityResult>(`/admissions/eligibility/check/${application_id}`, {
      method: "POST",
      body: JSON.stringify({ criteria_set_id }),
    }),
  get: (application_id: string) =>
    apiFetch<EligibilityResult>(`/admissions/eligibility/${application_id}`),
  override: (application_id: string, verdict: string, reason: string) =>
    apiFetch<EligibilityResult>(`/admissions/eligibility/${application_id}/override`, {
      method: "POST",
      body: JSON.stringify({ verdict, override_reason: reason }),
    }),
  batchCheck: (application_ids: string[]) =>
    apiFetch<EligibilityResult[]>("/admissions/eligibility/batch-check", {
      method: "POST",
      body: JSON.stringify({ application_ids }),
    }),
};

// ─── Entrance Tests ──────────────────────────────────────────

export const testsApi = {
  list: () => apiFetch<EntranceTest[]>("/admissions/entrance-tests"),
  get: (test_id: string) => apiFetch<EntranceTest>(`/admissions/entrance-tests/${test_id}`),
  create: (data: Partial<EntranceTest>) =>
    apiFetch<EntranceTest>("/admissions/entrance-tests", {
      method: "POST",
      body: JSON.stringify(data),
    }),
  slots: (test_id: string) =>
    apiFetch<TestSlot[]>(`/admissions/entrance-tests/${test_id}/slots`),
  addSlot: (test_id: string, data: Partial<TestSlot>) =>
    apiFetch<TestSlot>(`/admissions/entrance-tests/${test_id}/slots`, {
      method: "POST",
      body: JSON.stringify(data),
    }),
  register: (test_id: string, slot_id: string, application_id: string) =>
    apiFetch<TestRegistration>(`/admissions/entrance-tests/${test_id}/register`, {
      method: "POST",
      body: JSON.stringify({ slot_id, application_id }),
    }),
  registrations: (test_id: string) =>
    apiFetch<TestRegistration[]>(`/admissions/entrance-tests/${test_id}/registrations`),
  recordScore: (test_id: string, application_id: string, score: number) =>
    apiFetch<TestRegistration>(`/admissions/entrance-tests/${test_id}/scores`, {
      method: "POST",
      body: JSON.stringify({ application_id, score }),
    }),
  generateAdmitCards: (test_id: string) =>
    apiFetch<{ generated: number }>(`/admissions/entrance-tests/${test_id}/admit-cards`, {
      method: "POST",
    }),
};

// ─── Interviews ──────────────────────────────────────────────

export const interviewsApi = {
  panels: () => apiFetch<{ id: string; name: string; program: string }[]>("/admissions/interview-panels"),
  list: (params: { status?: string } = {}) => {
    const q = new URLSearchParams(params as Record<string, string>).toString();
    return apiFetch<Interview[]>(`/admissions/interviews${q ? `?${q}` : ""}`);
  },
  get: (id: string) => apiFetch<Interview>(`/admissions/interviews/${id}`),
  schedule: (data: Partial<Interview>) =>
    apiFetch<Interview>("/admissions/interviews", {
      method: "POST",
      body: JSON.stringify(data),
    }),
  submitScorecard: (id: string, scorecard: Record<string, number | string | undefined>) =>
    apiFetch<Interview>(`/admissions/interviews/${id}/scorecard`, {
      method: "POST",
      body: JSON.stringify(scorecard),
    }),
  markCompleted: (id: string) =>
    apiFetch<Interview>(`/admissions/interviews/${id}/complete`, { method: "POST" }),
  markNoShow: (id: string) =>
    apiFetch<Interview>(`/admissions/interviews/${id}/no-show`, { method: "POST" }),
};

// ─── Merit List ──────────────────────────────────────────────

export const meritApi = {
  lists: () => apiFetch<MeritList[]>("/admissions/merit-lists"),
  get: (id: string) => apiFetch<MeritList>(`/admissions/merit-lists/${id}`),
  generate: (program: string, category: string, round: number, policy_id?: string) =>
    apiFetch<MeritList>("/admissions/merit-lists/generate", {
      method: "POST",
      body: JSON.stringify({ program, category, round, policy_id }),
    }),
  approve: (id: string) =>
    apiFetch<MeritList>(`/admissions/merit-lists/${id}/approve`, { method: "POST" }),
  publish: (id: string) =>
    apiFetch<MeritList>(`/admissions/merit-lists/${id}/publish`, { method: "POST" }),
  seatMatrix: () => apiFetch<SeatMatrix[]>("/admissions/seat-matrix"),
};

// ─── Offer Letters ───────────────────────────────────────────

export const offersApi = {
  list: (params: { status?: string } = {}) => {
    const q = new URLSearchParams(params as Record<string, string>).toString();
    return apiFetch<OfferLetter[]>(`/admissions/offer-letters${q ? `?${q}` : ""}`);
  },
  get: (id: string) => apiFetch<OfferLetter>(`/admissions/offer-letters/${id}`),
  getByApplication: (application_id: string) =>
    apiFetch<OfferLetter>(`/admissions/offer-letters/application/${application_id}`),
  generate: (application_id: string) =>
    apiFetch<OfferLetter>("/admissions/offer-letters/generate", {
      method: "POST",
      body: JSON.stringify({ application_id }),
    }),
  batchGenerate: (application_ids: string[]) =>
    apiFetch<{ generated: number }>("/admissions/offer-letters/batch-generate", {
      method: "POST",
      body: JSON.stringify({ application_ids }),
    }),
  accept: (id: string) =>
    apiFetch<OfferLetter>(`/admissions/offer-letters/${id}/accept`, { method: "POST" }),
  decline: (id: string, reason?: string) =>
    apiFetch<OfferLetter>(`/admissions/offer-letters/${id}/decline`, {
      method: "POST",
      body: JSON.stringify({ reason }),
    }),
  countersign: (id: string) =>
    apiFetch<OfferLetter>(`/admissions/offer-letters/${id}/countersign`, { method: "POST" }),
};

// ─── Payments ────────────────────────────────────────────────

export const paymentsApi = {
  list: (params: { application_id?: string; status?: string } = {}) => {
    const q = new URLSearchParams(params as Record<string, string>).toString();
    return apiFetch<PaymentRecord[]>(`/admissions/payments${q ? `?${q}` : ""}`);
  },
  get: (id: string) => apiFetch<PaymentRecord>(`/admissions/payments/${id}`),
  initiate: (application_id: string, fee_type: string) =>
    apiFetch<{ payment_id: string; gateway_order_id: string; amount: string; gateway_url?: string }>(
      "/admissions/payments/initiate",
      { method: "POST", body: JSON.stringify({ application_id, fee_type }) }
    ),
  verify: (payment_id: string, gateway_response: Record<string, string>) =>
    apiFetch<PaymentRecord>(`/admissions/payments/${payment_id}/verify`, {
      method: "POST",
      body: JSON.stringify(gateway_response),
    }),
  requestRefund: (payment_id: string, reason: string) =>
    apiFetch<PaymentRecord>(`/admissions/payments/${payment_id}/refund`, {
      method: "POST",
      body: JSON.stringify({ reason }),
    }),
};

// ─── Final Verification ──────────────────────────────────────

export const verificationApi = {
  get: (application_id: string) =>
    apiFetch<FinalVerification>(`/admissions/final-verification/${application_id}`),
  initiate: (application_id: string) =>
    apiFetch<FinalVerification>(`/admissions/final-verification/${application_id}/initiate`, {
      method: "POST",
    }),
  checkDocument: (application_id: string, document_type: string, original_status: string, notes?: string) =>
    apiFetch<FinalVerification>(
      `/admissions/final-verification/${application_id}/check-document`,
      { method: "POST", body: JSON.stringify({ document_type, original_status, notes }) }
    ),
  clear: (application_id: string) =>
    apiFetch<FinalVerification>(`/admissions/final-verification/${application_id}/clear`, {
      method: "POST",
    }),
};

// ─── Enrollment ──────────────────────────────────────────────

export const enrollmentApi = {
  list: (params: { status?: string } = {}) => {
    const q = new URLSearchParams(params as Record<string, string>).toString();
    return apiFetch<EnrollmentRecord[]>(`/admissions/enrollment${q ? `?${q}` : ""}`);
  },
  get: (application_id: string) =>
    apiFetch<EnrollmentRecord>(`/admissions/enrollment/${application_id}`),
  provision: (application_id: string) =>
    apiFetch<EnrollmentRecord>(`/admissions/enrollment/${application_id}/provision`, {
      method: "POST",
    }),
  batchProvision: (application_ids: string[]) =>
    apiFetch<{ provisioned: number; failed: number }>(
      "/admissions/enrollment/batch-provision",
      { method: "POST", body: JSON.stringify({ application_ids }) }
    ),
};

// ─── Legacy compat ───────────────────────────────────────────

export const admissionsApi = {
  getApplicants: applicationsApi.getApplicants,
  getApplicant: applicationsApi.get,
  getReviewQueue: applicationsApi.getReviewQueue,
  getPipelineSummary: applicationsApi.getPipelineSummary,
  runEligibilityCheck: (applicantId: string, criteriaSetId: string) =>
    eligibilityApi.check(applicantId, criteriaSetId),
};
