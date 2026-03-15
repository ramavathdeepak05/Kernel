import { useQuery } from "@tanstack/react-query";
import {
  examSchedulesApi,
  examAnalyticsApi,
  reevalApi,
} from "@/services/examinations";

export const useExamSchedules = (
  academic_year: string,
  semester?: number,
  exam_type?: string
) =>
  useQuery({
    queryKey: ["exams", "schedules", academic_year, semester, exam_type],
    queryFn: () => examSchedulesApi.list(academic_year, semester, exam_type),
    enabled: !!academic_year,
    staleTime: 60_000,
  });

export const useSemesterAnalytics = (academic_year: string, semester: number) =>
  useQuery({
    queryKey: ["exams", "analytics", "semester", academic_year, semester],
    queryFn: () => examAnalyticsApi.semester(academic_year, semester),
    enabled: !!academic_year && !!semester,
    staleTime: 60_000,
  });

export const useExamAiInsights = (academic_year: string, semester: number) =>
  useQuery({
    queryKey: ["exams", "analytics", "ai-insights", academic_year, semester],
    queryFn: () => examAnalyticsApi.aiInsights(academic_year, semester),
    enabled: !!academic_year && !!semester,
    staleTime: 30_000,
    retry: 1,
  });

export const usePendingReeval = () =>
  useQuery({
    queryKey: ["exams", "reeval", "pending"],
    queryFn: () => reevalApi.pending(),
    staleTime: 30_000,
  });
