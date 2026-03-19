import { alisApi } from "@/lib/alis-api";

// ── Types ──────────────────────────────────────────────────────

export interface NotifTemplate {
  id: string;
  tenant_id: string;
  name: string;
  code: string;
  channel: "EMAIL" | "SMS" | "WHATSAPP" | "IN_APP" | "PUSH";
  subject?: string;
  body: string;
  variables: string[];
  is_active: boolean;
  created_at: string;
}

export interface NotifLog {
  id: string;
  tenant_id: string;
  template_id?: string;
  channel: string;
  recipient: string;
  subject?: string;
  status: "SENT" | "FAILED" | "PENDING" | "BOUNCED" | "RETRYING";
  error_message?: string;
  sent_at?: string;
  created_at: string;
}

export interface Announcement {
  id: string;
  tenant_id: string;
  title: string;
  body: string;
  target_roles: string[];
  priority: "LOW" | "NORMAL" | "HIGH" | "URGENT";
  expires_at?: string;
  created_by: string;
  read_count: number;
  created_at: string;
}

export interface BulkCampaign {
  id: string;
  tenant_id: string;
  name: string;
  channel: string;
  template_id: string;
  recipient_filter: Record<string, unknown>;
  total_recipients: number;
  sent_count: number;
  failed_count: number;
  status: "DRAFT" | "QUEUED" | "RUNNING" | "COMPLETED" | "FAILED" | "PAUSED";
  scheduled_at?: string;
  completed_at?: string;
  created_at: string;
}

export interface CommsStats {
  templates_active: number;
  sent_today: number;
  failed_today: number;
  delivery_rate: number;
  announcements_active: number;
  campaigns_running: number;
  channel_breakdown: { channel: string; count: number; rate: number }[];
}

// ── API clients ────────────────────────────────────────────────

export const templatesApi = {
  list: (params?: { channel?: string; active?: boolean }) =>
    alisApi.get<NotifTemplate[]>("/comms/templates", { params }),
  get: (id: string) =>
    alisApi.get<NotifTemplate>(`/comms/templates/${id}`),
};

export const logsApi = {
  listFailed: (params?: { channel?: string; limit?: number }) =>
    alisApi.get<NotifLog[]>("/comms/logs/failed", { params }),
  retry: (id: string) =>
    alisApi.post<{ ok: boolean }>(`/comms/logs/${id}/retry`),
};

export const announcementsApi = {
  list: () =>
    alisApi.get<Announcement[]>("/comms/announcements"),
  create: (data: Partial<Announcement>) =>
    alisApi.post<Announcement>("/comms/announcements", data),
  delete: (id: string) =>
    alisApi.delete<{ ok: boolean }>(`/comms/announcements/${id}`),
};

export const bulkApi = {
  list: () =>
    alisApi.get<BulkCampaign[]>("/comms/bulk"),
  get: (id: string) =>
    alisApi.get<BulkCampaign>(`/comms/bulk/${id}`),
  create: (data: Partial<BulkCampaign>) =>
    alisApi.post<BulkCampaign>("/comms/bulk", data),
};

export const commsStatsApi = {
  get: () =>
    alisApi.get<CommsStats>("/comms/stats"),
};
