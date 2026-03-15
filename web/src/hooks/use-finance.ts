import { useQuery } from "@tanstack/react-query";
import { feeStructuresApi, scholarshipsApi, waiversApi, financeReportsApi } from "@/services/finance";

const CURRENT_YEAR = "2024-25";

export const useFeeStructures = (academic_year?: string, program_id?: string) =>
  useQuery({
    queryKey: ["finance", "fee-structures", academic_year, program_id],
    queryFn: () => feeStructuresApi.list(academic_year, program_id),
    staleTime: 120_000,
  });

export const useScholarships = () =>
  useQuery({
    queryKey: ["finance", "scholarships"],
    queryFn: () => scholarshipsApi.list(),
    staleTime: 120_000,
  });

export const usePendingWaivers = () =>
  useQuery({
    queryKey: ["finance", "waivers", "pending"],
    queryFn: () => waiversApi.pending(),
    staleTime: 30_000,
  });

export const useCollectionReport = (academic_year = CURRENT_YEAR, semester?: number) =>
  useQuery({
    queryKey: ["finance", "reports", "collection", academic_year, semester],
    queryFn: () => financeReportsApi.collection(academic_year, semester),
    staleTime: 60_000,
    retry: 1,
  });

export const useDefaultRisk = (academic_year?: string) =>
  useQuery({
    queryKey: ["finance", "analytics", "default-risk", academic_year],
    queryFn: () => financeReportsApi.defaultRisk(academic_year),
    staleTime: 60_000,
    retry: 1,
  });

export const useMonthlyCollection = (academic_year = CURRENT_YEAR) =>
  useQuery({
    queryKey: ["finance", "reports", "monthly", academic_year],
    queryFn: () => financeReportsApi.monthly(academic_year),
    staleTime: 60_000,
    retry: 1,
  });
