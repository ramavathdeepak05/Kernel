import { useQuery } from "@tanstack/react-query";
import { templatesApi, logsApi, announcementsApi, bulkApi, commsStatsApi } from "@/services/communication";

export function useCommsStats() {
  return useQuery({
    queryKey: ["comms", "stats"],
    queryFn: () => commsStatsApi.get(),
    staleTime: 60_000,
  });
}

export function useTemplates(channel?: string) {
  return useQuery({
    queryKey: ["comms", "templates", channel],
    queryFn: () => templatesApi.list({ channel }),
    staleTime: 120_000,
  });
}

export function useFailedLogs() {
  return useQuery({
    queryKey: ["comms", "logs", "failed"],
    queryFn: () => logsApi.listFailed({ limit: 50 }),
    staleTime: 30_000,
  });
}

export function useAnnouncements() {
  return useQuery({
    queryKey: ["comms", "announcements"],
    queryFn: () => announcementsApi.list(),
    staleTime: 60_000,
  });
}

export function useBulkCampaigns() {
  return useQuery({
    queryKey: ["comms", "bulk"],
    queryFn: () => bulkApi.list(),
    staleTime: 60_000,
  });
}
