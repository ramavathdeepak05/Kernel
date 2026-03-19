import { useQuery } from "@tanstack/react-query";
import {
  dashboardApi, admissionsReportApi, academicsReportApi,
  financeReportApi, savedReportsApi, exportApi, aiReportApi,
} from "@/services/reporting";

export function useDashboardKPIs() {
  return useQuery({
    queryKey: ["reports", "kpis"],
    queryFn: () => dashboardApi.kpis(),
    staleTime: 60_000,
  });
}

export function useAdmissionsFunnel() {
  return useQuery({
    queryKey: ["reports", "admissions", "funnel"],
    queryFn: () => admissionsReportApi.funnel(),
    staleTime: 300_000,
  });
}

export function useAdmissionsPrograms() {
  return useQuery({
    queryKey: ["reports", "admissions", "programs"],
    queryFn: () => admissionsReportApi.programs(),
    staleTime: 300_000,
  });
}

export function useAcademicsAttendance() {
  return useQuery({
    queryKey: ["reports", "academics", "attendance"],
    queryFn: () => academicsReportApi.attendance(),
    staleTime: 300_000,
  });
}

export function useFacultyWorkload() {
  return useQuery({
    queryKey: ["reports", "academics", "workload"],
    queryFn: () => academicsReportApi.facultyWorkload(),
    staleTime: 300_000,
  });
}

export function useFinanceYoY() {
  return useQuery({
    queryKey: ["reports", "finance", "yoy"],
    queryFn: () => financeReportApi.yoy(),
    staleTime: 300_000,
  });
}

export function useFinanceAging() {
  return useQuery({
    queryKey: ["reports", "finance", "aging"],
    queryFn: () => financeReportApi.aging(),
    staleTime: 300_000,
  });
}

export function useSavedReports() {
  return useQuery({
    queryKey: ["reports", "saved"],
    queryFn: () => savedReportsApi.list(),
    staleTime: 120_000,
  });
}

export function useExports() {
  return useQuery({
    queryKey: ["reports", "exports"],
    queryFn: () => exportApi.list(),
    staleTime: 30_000,
  });
}

export function useAISummary() {
  return useQuery({
    queryKey: ["reports", "ai", "summary"],
    queryFn: () => aiReportApi.summary(),
    staleTime: 300_000,
  });
}
