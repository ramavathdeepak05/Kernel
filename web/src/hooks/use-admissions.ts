import { useQuery, useMutation } from "@tanstack/react-query";
import {
  leadsApi,
  applicationsApi,
  documentsApi,
  eligibilityApi,
  testsApi,
  interviewsApi,
  meritApi,
  offersApi,
  paymentsApi,
  enrollmentApi,
  admissionsApi,
} from "../services/admissions";
import { queryClient } from "../lib/queryClient";

// ── Leads ────────────────────────────────────────────────────

export function useLeads(params?: { skip?: number; limit?: number; status?: string }) {
  return useQuery({
    queryKey: ["leads", params],
    queryFn: () => leadsApi.list(params),
  });
}

export function useLead(id?: string) {
  return useQuery({
    queryKey: ["lead", id],
    queryFn: () => leadsApi.get(id!),
    enabled: !!id,
  });
}

export function useCreateLead() {
  return useMutation({
    mutationFn: leadsApi.create,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["leads"] }),
  });
}

export function useTransitionLead() {
  return useMutation({
    mutationFn: ({ id, status, notes }: { id: string; status: string; notes?: string }) =>
      leadsApi.transition(id, status, notes),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["leads"] });
      queryClient.invalidateQueries({ queryKey: ["pipeline-summary"] });
    },
  });
}

export function useLeadActivities(id?: string) {
  return useQuery({
    queryKey: ["lead-activities", id],
    queryFn: () => leadsApi.activities(id!),
    enabled: !!id,
  });
}

// ── Applications ─────────────────────────────────────────────

export function useApplications(params?: { skip?: number; limit?: number; status?: string; program?: string }) {
  return useQuery({
    queryKey: ["applications", params],
    queryFn: () => applicationsApi.list(params),
  });
}

export function useApplication(id?: string) {
  return useQuery({
    queryKey: ["application", id],
    queryFn: () => applicationsApi.get(id!),
    enabled: !!id,
  });
}

export function useCreateApplication() {
  return useMutation({
    mutationFn: applicationsApi.create,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["applications"] }),
  });
}

export function useUpdateApplication() {
  return useMutation({
    mutationFn: ({ id, data }: { id: string; data: Parameters<typeof applicationsApi.update>[1] }) =>
      applicationsApi.update(id, data),
    onSuccess: (_data, { id }) => {
      queryClient.invalidateQueries({ queryKey: ["application", id] });
      queryClient.invalidateQueries({ queryKey: ["applications"] });
    },
  });
}

export function useSubmitApplication() {
  return useMutation({
    mutationFn: (id: string) => applicationsApi.submit(id),
    onSuccess: (_data, id) => {
      queryClient.invalidateQueries({ queryKey: ["application", id] });
      queryClient.invalidateQueries({ queryKey: ["applications"] });
      queryClient.invalidateQueries({ queryKey: ["pipeline-summary"] });
    },
  });
}

// ── Documents ────────────────────────────────────────────────

export function useDocuments(application_id?: string) {
  return useQuery({
    queryKey: ["documents", application_id],
    queryFn: () => documentsApi.list(application_id!),
    enabled: !!application_id,
  });
}

export function useUploadDocument() {
  return useMutation({
    mutationFn: ({ application_id, document_type, file }: { application_id: string; document_type: string; file: File }) =>
      documentsApi.upload(application_id, document_type, file),
    onSuccess: (_data, { application_id }) =>
      queryClient.invalidateQueries({ queryKey: ["documents", application_id] }),
  });
}

export function useReviewDocument() {
  return useMutation({
    mutationFn: ({
      application_id,
      document_id,
      status,
      rejection_reason,
    }: { application_id: string; document_id: string; status: string; rejection_reason?: string }) =>
      documentsApi.review(application_id, document_id, status, rejection_reason),
    onSuccess: (_data, { application_id }) => {
      queryClient.invalidateQueries({ queryKey: ["documents", application_id] });
      queryClient.invalidateQueries({ queryKey: ["doc-review-queue"] });
    },
  });
}

export function useDocumentReviewQueue(params?: { skip?: number; limit?: number }) {
  return useQuery({
    queryKey: ["doc-review-queue", params],
    queryFn: () => documentsApi.reviewQueue(params),
    refetchInterval: 30_000,
  });
}

// ── Eligibility ──────────────────────────────────────────────

export function useEligibilityResult(application_id?: string) {
  return useQuery({
    queryKey: ["eligibility", application_id],
    queryFn: () => eligibilityApi.get(application_id!),
    enabled: !!application_id,
  });
}

export function useRunEligibilityCheck() {
  return useMutation({
    mutationFn: ({ application_id, criteria_set_id }: { application_id: string; criteria_set_id?: string }) =>
      eligibilityApi.check(application_id, criteria_set_id),
    onSuccess: (_data, { application_id }) => {
      queryClient.invalidateQueries({ queryKey: ["eligibility", application_id] });
      queryClient.invalidateQueries({ queryKey: ["applications"] });
    },
  });
}

export function useOverrideEligibility() {
  return useMutation({
    mutationFn: ({ application_id, verdict, reason }: { application_id: string; verdict: string; reason: string }) =>
      eligibilityApi.override(application_id, verdict, reason),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["eligibility"] }),
  });
}

// ── Tests ────────────────────────────────────────────────────

export function useEntranceTests() {
  return useQuery({
    queryKey: ["entrance-tests"],
    queryFn: testsApi.list,
  });
}

export function useTestSlots(test_id?: string) {
  return useQuery({
    queryKey: ["test-slots", test_id],
    queryFn: () => testsApi.slots(test_id!),
    enabled: !!test_id,
  });
}

export function useTestRegistrations(test_id?: string) {
  return useQuery({
    queryKey: ["test-registrations", test_id],
    queryFn: () => testsApi.registrations(test_id!),
    enabled: !!test_id,
  });
}

// ── Interviews ───────────────────────────────────────────────

export function useInterviews(params?: { status?: string }) {
  return useQuery({
    queryKey: ["interviews", params],
    queryFn: () => interviewsApi.list(params),
  });
}

export function useScheduleInterview() {
  return useMutation({
    mutationFn: interviewsApi.schedule,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["interviews"] }),
  });
}

// ── Merit ────────────────────────────────────────────────────

export function useMeritLists() {
  return useQuery({
    queryKey: ["merit-lists"],
    queryFn: meritApi.lists,
  });
}

export function useMeritList(id?: string) {
  return useQuery({
    queryKey: ["merit-list", id],
    queryFn: () => meritApi.get(id!),
    enabled: !!id,
  });
}

export function useSeatMatrix() {
  return useQuery({
    queryKey: ["seat-matrix"],
    queryFn: meritApi.seatMatrix,
  });
}

export function useGenerateMeritList() {
  return useMutation({
    mutationFn: ({ program, category, round, policy_id }: { program: string; category: string; round: number; policy_id?: string }) =>
      meritApi.generate(program, category, round, policy_id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["merit-lists"] }),
  });
}

export function usePublishMeritList() {
  return useMutation({
    mutationFn: (id: string) => meritApi.publish(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["merit-lists"] }),
  });
}

// ── Offers ───────────────────────────────────────────────────

export function useOffers(params?: { status?: string }) {
  return useQuery({
    queryKey: ["offers", params],
    queryFn: () => offersApi.list(params),
  });
}

export function useOffer(id?: string) {
  return useQuery({
    queryKey: ["offer", id],
    queryFn: () => offersApi.get(id!),
    enabled: !!id,
  });
}

export function useOfferByApplication(application_id?: string) {
  return useQuery({
    queryKey: ["offer-by-app", application_id],
    queryFn: () => offersApi.getByApplication(application_id!),
    enabled: !!application_id,
  });
}

export function useAcceptOffer() {
  return useMutation({
    mutationFn: (id: string) => offersApi.accept(id),
    onSuccess: (_data, id) => {
      queryClient.invalidateQueries({ queryKey: ["offer", id] });
      queryClient.invalidateQueries({ queryKey: ["offers"] });
    },
  });
}

export function useDeclineOffer() {
  return useMutation({
    mutationFn: ({ id, reason }: { id: string; reason?: string }) => offersApi.decline(id, reason),
    onSuccess: (_data, { id }) => {
      queryClient.invalidateQueries({ queryKey: ["offer", id] });
      queryClient.invalidateQueries({ queryKey: ["offers"] });
    },
  });
}

export function useGenerateOffer() {
  return useMutation({
    mutationFn: (application_id: string) => offersApi.generate(application_id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["offers"] }),
  });
}

// ── Payments ─────────────────────────────────────────────────

export function usePayments(params?: { application_id?: string; status?: string }) {
  return useQuery({
    queryKey: ["payments", params],
    queryFn: () => paymentsApi.list(params),
  });
}

export function useInitiatePayment() {
  return useMutation({
    mutationFn: ({ application_id, fee_type }: { application_id: string; fee_type: string }) =>
      paymentsApi.initiate(application_id, fee_type),
  });
}

// ── Enrollment ───────────────────────────────────────────────

export function useEnrollmentList(params?: { status?: string }) {
  return useQuery({
    queryKey: ["enrollment-list", params],
    queryFn: () => enrollmentApi.list(params),
  });
}

export function useProvisionEnrollment() {
  return useMutation({
    mutationFn: (application_id: string) => enrollmentApi.provision(application_id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["enrollment-list"] }),
  });
}

// ── Legacy compat ─────────────────────────────────────────────

export function useApplicants(params?: { limit?: number; skip?: number }) {
  return useQuery({
    queryKey: ["applicants", params],
    queryFn: () => admissionsApi.getApplicants(params),
  });
}

export function useReviewQueue() {
  return useQuery({
    queryKey: ["review-queue"],
    queryFn: admissionsApi.getReviewQueue,
    refetchInterval: 15_000,
  });
}

export function usePipelineSummary() {
  return useQuery({
    queryKey: ["pipeline-summary"],
    queryFn: admissionsApi.getPipelineSummary,
    refetchInterval: 60_000,
  });
}
