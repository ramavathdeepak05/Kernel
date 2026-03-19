import { useQuery } from "@tanstack/react-query";
import { alumniProfilesApi, placementApi, jobBoardApi, drivesApi, mentorsApi } from "@/services/alumni";

export function useAlumniStats() {
  return useQuery({
    queryKey: ["alumni", "stats"],
    queryFn: () => alumniProfilesApi.stats(),
    staleTime: 120_000,
  });
}

export function useAlumniProfiles(params?: { batch_year?: number; program?: string }) {
  return useQuery({
    queryKey: ["alumni", "profiles", params],
    queryFn: () => alumniProfilesApi.list(params),
    staleTime: 120_000,
  });
}

export function usePlacementStats() {
  return useQuery({
    queryKey: ["alumni", "placement", "stats"],
    queryFn: () => placementApi.stats(),
    staleTime: 300_000,
  });
}

export function usePlacements(params?: { year?: number; program?: string }) {
  return useQuery({
    queryKey: ["alumni", "placements", params],
    queryFn: () => placementApi.list(params),
    staleTime: 120_000,
  });
}

export function useJobBoard(status?: string) {
  return useQuery({
    queryKey: ["alumni", "jobs", status],
    queryFn: () => jobBoardApi.list({ status }),
    staleTime: 60_000,
  });
}

export function useRecruitmentDrives() {
  return useQuery({
    queryKey: ["alumni", "drives"],
    queryFn: () => drivesApi.list(),
    staleTime: 60_000,
  });
}

export function useMentors() {
  return useQuery({
    queryKey: ["alumni", "mentors"],
    queryFn: () => mentorsApi.list(),
    staleTime: 300_000,
  });
}
