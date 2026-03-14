import { useQuery } from "@tanstack/react-query";
import {
  programsApi,
  coursesApi,
  timetableApi,
  academicsAnalyticsApi,
} from "@/services/academics";

export const usePrograms = () =>
  useQuery({
    queryKey: ["academics", "programs"],
    queryFn: () => programsApi.list(),
    staleTime: 60_000,
  });

export const useCourses = (params: { program_id?: string; semester?: number } = {}) =>
  useQuery({
    queryKey: ["academics", "courses", params],
    queryFn: () => coursesApi.list(params),
    staleTime: 60_000,
  });

export const useTimetable = (params: { academic_year?: string; course_id?: string } = {}) =>
  useQuery({
    queryKey: ["academics", "timetable", params],
    queryFn: () => timetableApi.get(params),
    staleTime: 60_000,
  });

export const useAtRiskStudents = (params: { academic_year?: string; course_id?: string } = {}) =>
  useQuery({
    queryKey: ["academics", "at-risk", params],
    queryFn: () => academicsAnalyticsApi.atRisk(params),
    staleTime: 30_000,
    retry: 1,
  });

export const useAcademicsInsights = (params: { academic_year?: string } = {}) =>
  useQuery({
    queryKey: ["academics", "insights", params],
    queryFn: () => academicsAnalyticsApi.insights(params),
    staleTime: 30_000,
    retry: 1,
  });
