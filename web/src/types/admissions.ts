// ─── Lead / CRM ──────────────────────────────────────────────────────────────
export type LeadStatus = "NEW" | "CONTACTED" | "INTERESTED" | "READY_TO_APPLY" | "CONVERTED" | "LOST";

export interface Lead {
  id: string;
  name: string;
  email: string;
  phone?: string;
  status: LeadStatus;
  programme_interest?: string;
  source?: string;
  consultant_id?: string;
  created_at: string;
  updated_at: string;
}

export interface LeadActivity {
  id: string;
  lead_id: string;
  type: string;
  notes?: string;
  created_at: string;
}

// ─── Application ─────────────────────────────────────────────────────────────
export type ApplicationStatus =
  | "DRAFT"
  | "SUBMITTED"
  | "UNDER_REVIEW"
  | "DOCUMENTS_PENDING"
  | "DOCUMENTS_RECEIVED"
  | "ELIGIBILITY_CHECK"
  | "ELIGIBLE"
  | "INELIGIBLE"
  | "TEST_SCHEDULED"
  | "TEST_COMPLETED"
  | "INTERVIEW_SCHEDULED"
  | "INTERVIEW_COMPLETED"
  | "MERIT_EVALUATED"
  | "OFFER_ISSUED"
  | "OFFER_ACCEPTED"
  | "OFFER_DECLINED"
  | "PAYMENT_PENDING"
  | "PAYMENT_RECEIVED"
  | "VERIFICATION_PENDING"
  | "VERIFICATION_COMPLETE"
  | "ENROLLED"
  | "REJECTED"
  | "WITHDRAWN";

export interface Application {
  id: string;
  application_id: string;
  lead_id?: string;
  applicant_name: string;
  email: string;
  phone?: string;
  programme: string;
  status: ApplicationStatus;
  step: number;
  form_data: Record<string, unknown>;
  submitted_at?: string;
  created_at: string;
  updated_at: string;
}

// ─── Documents ───────────────────────────────────────────────────────────────
export type DocumentStatus = "PENDING" | "UNDER_REVIEW" | "APPROVED" | "REJECTED" | "REUPLOAD_REQUESTED";
export type DocumentType =
  | "PHOTO"
  | "SIGNATURE"
  | "ID_PROOF"
  | "ADDRESS_PROOF"
  | "CLASS_10_CERTIFICATE"
  | "CLASS_10_MARKSHEET"
  | "CLASS_12_CERTIFICATE"
  | "CLASS_12_MARKSHEET"
  | "ENTRANCE_SCORE_CARD"
  | "CATEGORY_CERTIFICATE"
  | "INCOME_CERTIFICATE"
  | "TRANSFER_CERTIFICATE"
  | "OTHER";

export const DOCUMENT_LABELS: Record<DocumentType, string> = {
  PHOTO: "Passport Photo",
  SIGNATURE: "Signature",
  ID_PROOF: "ID Proof",
  ADDRESS_PROOF: "Address Proof",
  CLASS_10_CERTIFICATE: "10th Certificate",
  CLASS_10_MARKSHEET: "10th Marksheet",
  CLASS_12_CERTIFICATE: "12th Certificate",
  CLASS_12_MARKSHEET: "12th Marksheet",
  ENTRANCE_SCORE_CARD: "Entrance Score Card",
  CATEGORY_CERTIFICATE: "Category Certificate",
  INCOME_CERTIFICATE: "Income Certificate",
  TRANSFER_CERTIFICATE: "Transfer Certificate",
  OTHER: "Other",
};

export interface ApplicationDocument {
  id: string;
  application_id: string;
  type: DocumentType;
  status: DocumentStatus;
  file_url?: string;
  reviewer_notes?: string;
  uploaded_at?: string;
  reviewed_at?: string;
}

// ─── Eligibility ─────────────────────────────────────────────────────────────
export interface EligibilityResult {
  application_id: string;
  is_eligible: boolean;
  checked_at: string;
  criteria: Array<{ label: string; passed: boolean; detail?: string }>;
  override?: boolean;
  override_reason?: string;
}

// ─── Entrance Tests ──────────────────────────────────────────────────────────
export interface EntranceTest {
  id: string;
  name: string;
  programme: string;
  date: string;
  duration_mins: number;
  max_score: number;
  status: "SCHEDULED" | "ONGOING" | "COMPLETED" | "CANCELLED";
}

export interface TestSlot {
  id: string;
  test_id: string;
  venue: string;
  start_time: string;
  capacity: number;
  registered: number;
}

export interface TestRegistration {
  id: string;
  application_id: string;
  slot_id: string;
  admit_card_url?: string;
  score?: number;
  rank?: number;
  status: "REGISTERED" | "APPEARED" | "ABSENT" | "DISQUALIFIED";
}

// ─── Interviews ──────────────────────────────────────────────────────────────
export interface Interview {
  id: string;
  application_id: string;
  panel_id: string;
  scheduled_at: string;
  mode: "IN_PERSON" | "ONLINE";
  score?: number;
  remarks?: string;
  status: "SCHEDULED" | "COMPLETED" | "CANCELLED" | "NO_SHOW";
}

// ─── Merit List ───────────────────────────────────────────────────────────────
export interface SeatMatrix {
  id: string;
  programme: string;
  category: string;
  total_seats: number;
  filled_seats: number;
}

export interface MeritEntry {
  rank: number;
  application_id: string;
  applicant_name: string;
  score: number;
  category: string;
  status: "SELECTED" | "WAITLISTED" | "REJECTED";
}

export interface MeritList {
  id: string;
  programme: string;
  batch: string;
  status: "DRAFT" | "PUBLISHED";
  generated_at: string;
  entries: MeritEntry[];
}

// ─── Offer Letter ─────────────────────────────────────────────────────────────
export interface OfferLetter {
  id: string;
  application_id: string;
  applicant_name: string;
  programme: string;
  batch: string;
  fee_amount: string;
  issued_at: string;
  expires_at: string;
  status: "ISSUED" | "ACCEPTED" | "DECLINED" | "EXPIRED" | "COUNTERSIGNED";
  pdf_url?: string;
}

// ─── Payments ─────────────────────────────────────────────────────────────────
export interface PaymentRecord {
  id: string;
  application_id: string;
  amount: string;
  currency: string;
  status: "PENDING" | "INITIATED" | "SUCCESS" | "FAILED" | "REFUNDED";
  gateway: string;
  gateway_ref?: string;
  paid_at?: string;
  created_at: string;
}

// ─── Final Verification ───────────────────────────────────────────────────────
export interface FinalVerification {
  id: string;
  application_id: string;
  status: "PENDING" | "IN_PROGRESS" | "APPROVED" | "REJECTED";
  doc_check: boolean;
  background_check?: boolean;
  approved_by?: string;
  approved_at?: string;
}

// ─── Enrollment ───────────────────────────────────────────────────────────────
export interface EnrollmentRecord {
  id: string;
  application_id: string;
  student_id: string;
  programme: string;
  batch: string;
  lms_provisioned: boolean;
  hostel_allocated?: boolean;
  library_id?: string;
  enrolled_at: string;
}

// ─── UI helpers ───────────────────────────────────────────────────────────────
export type PipelineStage =
  | "leads"
  | "applications"
  | "documents"
  | "eligibility"
  | "tests"
  | "merit"
  | "offers"
  | "payment"
  | "verification"
  | "enrolled";

export interface ReviewItem {
  id: string;
  type: "ai_action" | "alert" | "exception";
  title: string;
  subtitle?: string;
  confidence?: number;
  urgency?: "low" | "medium" | "high";
  application_id?: string;
  created_at: string;
}

export interface WizardStep {
  n: number;
  title: string;
}

export const STATUS_LABELS: Record<ApplicationStatus, string> = {
  DRAFT: "Draft",
  SUBMITTED: "Submitted",
  UNDER_REVIEW: "Under Review",
  DOCUMENTS_PENDING: "Docs Pending",
  DOCUMENTS_RECEIVED: "Docs Received",
  ELIGIBILITY_CHECK: "Eligibility Check",
  ELIGIBLE: "Eligible",
  INELIGIBLE: "Ineligible",
  TEST_SCHEDULED: "Test Scheduled",
  TEST_COMPLETED: "Test Done",
  INTERVIEW_SCHEDULED: "Interview Scheduled",
  INTERVIEW_COMPLETED: "Interview Done",
  MERIT_EVALUATED: "Merit Evaluated",
  OFFER_ISSUED: "Offer Issued",
  OFFER_ACCEPTED: "Offer Accepted",
  OFFER_DECLINED: "Offer Declined",
  PAYMENT_PENDING: "Payment Pending",
  PAYMENT_RECEIVED: "Payment Received",
  VERIFICATION_PENDING: "Verification Pending",
  VERIFICATION_COMPLETE: "Verified",
  ENROLLED: "Enrolled",
  REJECTED: "Rejected",
  WITHDRAWN: "Withdrawn",
};

export const STATUS_COLORS: Record<ApplicationStatus, { bg: string; text: string; border: string }> = {
  DRAFT:                { bg: "rgba(100,116,139,0.12)", text: "#94a3b8", border: "rgba(100,116,139,0.2)" },
  SUBMITTED:            { bg: "rgba(99,102,241,0.12)",  text: "#818cf8", border: "rgba(99,102,241,0.2)" },
  UNDER_REVIEW:         { bg: "rgba(99,102,241,0.12)",  text: "#818cf8", border: "rgba(99,102,241,0.2)" },
  DOCUMENTS_PENDING:    { bg: "rgba(251,191,36,0.12)",  text: "#fbbf24", border: "rgba(251,191,36,0.2)" },
  DOCUMENTS_RECEIVED:   { bg: "rgba(52,211,153,0.12)",  text: "#34d399", border: "rgba(52,211,153,0.2)" },
  ELIGIBILITY_CHECK:    { bg: "rgba(167,139,250,0.12)", text: "#a78bfa", border: "rgba(167,139,250,0.2)" },
  ELIGIBLE:             { bg: "rgba(52,211,153,0.12)",  text: "#34d399", border: "rgba(52,211,153,0.2)" },
  INELIGIBLE:           { bg: "rgba(248,113,113,0.12)", text: "#f87171", border: "rgba(248,113,113,0.2)" },
  TEST_SCHEDULED:       { bg: "rgba(99,102,241,0.12)",  text: "#818cf8", border: "rgba(99,102,241,0.2)" },
  TEST_COMPLETED:       { bg: "rgba(52,211,153,0.12)",  text: "#34d399", border: "rgba(52,211,153,0.2)" },
  INTERVIEW_SCHEDULED:  { bg: "rgba(99,102,241,0.12)",  text: "#818cf8", border: "rgba(99,102,241,0.2)" },
  INTERVIEW_COMPLETED:  { bg: "rgba(52,211,153,0.12)",  text: "#34d399", border: "rgba(52,211,153,0.2)" },
  MERIT_EVALUATED:      { bg: "rgba(167,139,250,0.12)", text: "#a78bfa", border: "rgba(167,139,250,0.2)" },
  OFFER_ISSUED:         { bg: "rgba(167,139,250,0.12)", text: "#a78bfa", border: "rgba(167,139,250,0.2)" },
  OFFER_ACCEPTED:       { bg: "rgba(52,211,153,0.12)",  text: "#34d399", border: "rgba(52,211,153,0.2)" },
  OFFER_DECLINED:       { bg: "rgba(248,113,113,0.12)", text: "#f87171", border: "rgba(248,113,113,0.2)" },
  PAYMENT_PENDING:      { bg: "rgba(251,191,36,0.12)",  text: "#fbbf24", border: "rgba(251,191,36,0.2)" },
  PAYMENT_RECEIVED:     { bg: "rgba(52,211,153,0.12)",  text: "#34d399", border: "rgba(52,211,153,0.2)" },
  VERIFICATION_PENDING: { bg: "rgba(251,191,36,0.12)",  text: "#fbbf24", border: "rgba(251,191,36,0.2)" },
  VERIFICATION_COMPLETE:{ bg: "rgba(52,211,153,0.12)",  text: "#34d399", border: "rgba(52,211,153,0.2)" },
  ENROLLED:             { bg: "rgba(52,211,153,0.12)",  text: "#34d399", border: "rgba(52,211,153,0.2)" },
  REJECTED:             { bg: "rgba(248,113,113,0.12)", text: "#f87171", border: "rgba(248,113,113,0.2)" },
  WITHDRAWN:            { bg: "rgba(100,116,139,0.12)", text: "#94a3b8", border: "rgba(100,116,139,0.2)" },
};
