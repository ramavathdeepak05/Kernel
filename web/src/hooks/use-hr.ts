import { useQuery } from "@tanstack/react-query";
import { staffApi, leaveApi, payrollApi, performanceApi, hrAttendanceApi, hrAnalyticsApi } from "@/services/hr";

export const useStaff = (department?: string, status?: string) =>
  useQuery({
    queryKey: ["hr", "staff", department, status],
    queryFn: () => staffApi.list(department, status),
    staleTime: 60_000,
  });

export const usePendingLeave = () =>
  useQuery({
    queryKey: ["hr", "leave", "pending"],
    queryFn: () => leaveApi.pending(),
    staleTime: 30_000,
  });

export const usePayrollSummary = (month?: string) =>
  useQuery({
    queryKey: ["hr", "payroll", "summary", month],
    queryFn: () => payrollApi.summary(month),
    staleTime: 60_000,
    retry: 1,
  });

export const usePendingReviews = () =>
  useQuery({
    queryKey: ["hr", "reviews", "pending"],
    queryFn: () => performanceApi.pending(),
    staleTime: 30_000,
  });

export const useDeptAttendance = (date?: string) =>
  useQuery({
    queryKey: ["hr", "attendance", "dept", date],
    queryFn: () => hrAttendanceApi.deptSummary(date),
    staleTime: 60_000,
    retry: 1,
  });

export const useHRInsights = () =>
  useQuery({
    queryKey: ["hr", "analytics", "insights"],
    queryFn: () => hrAnalyticsApi.insights(),
    staleTime: 60_000,
    retry: 1,
  });

export const useWorkloadAnalytics = () =>
  useQuery({
    queryKey: ["hr", "analytics", "workload"],
    queryFn: () => hrAnalyticsApi.workload(),
    staleTime: 60_000,
    retry: 1,
  });
