import { alisApi } from "@/lib/alis-api";

// ── Types ──────────────────────────────────────────────────────

export interface AlumniProfile {
  id: string;
  tenant_id: string;
  student_id: string;
  full_name: string;
  batch_year: number;
  program: string;
  current_employer?: string;
  current_designation?: string;
  linkedin_url?: string;
  is_verified: boolean;
  is_mentor: boolean;
  location?: string;
  created_at: string;
}

export interface PlacementRecord {
  id: string;
  student_id: string;
  student_name: string;
  program: string;
  company: string;
  role: string;
  package_lpa: number;
  offer_type: "CAMPUS" | "OFF_CAMPUS" | "LATERAL" | "HIGHER_STUDIES";
  offer_date: string;
  status: "OFFERED" | "ACCEPTED" | "JOINED" | "DECLINED" | "RESCINDED";
}

export interface PlacementStats {
  total_placed: number;
  placement_pct: number;
  avg_package_lpa: number;
  highest_package_lpa: number;
  total_companies: number;
  offers_this_year: number;
  by_program: { program: string; placed: number; total: number; avg_lpa: number }[];
  top_recruiters: { company: string; offers: number; avg_lpa: number }[];
}

export interface JobPosting {
  id: string;
  title: string;
  company: string;
  location: string;
  type: "FULL_TIME" | "PART_TIME" | "INTERNSHIP" | "CONTRACT";
  min_package_lpa?: number;
  max_package_lpa?: number;
  experience_years?: number;
  deadline: string;
  applications_count: number;
  status: "OPEN" | "CLOSED" | "DRAFT";
  posted_by_alumni?: string;
  created_at: string;
}

export interface RecruitmentDrive {
  id: string;
  company: string;
  drive_date: string;
  venue: string;
  roles: string[];
  package_range: string;
  eligible_programs: string[];
  registered_count: number;
  shortlisted_count: number;
  selected_count: number;
  status: "ANNOUNCED" | "REGISTRATION_OPEN" | "IN_PROGRESS" | "COMPLETED" | "CANCELLED";
}

export interface AlumniStats {
  total_alumni: number;
  verified: number;
  active_mentors: number;
  placements_ytd: number;
  open_jobs: number;
  drives_this_month: number;
}

// ── API clients ────────────────────────────────────────────────

export const alumniProfilesApi = {
  list: (params?: { batch_year?: number; program?: string; verified?: boolean }) =>
    alisApi.get<AlumniProfile[]>("/alumni/profiles", { params }),
  stats: () =>
    alisApi.get<AlumniStats>("/alumni/profiles/stats"),
  verify: (id: string) =>
    alisApi.post<{ ok: boolean }>(`/alumni/profiles/${id}/verify`),
};

export const placementApi = {
  list: (params?: { year?: number; program?: string }) =>
    alisApi.get<PlacementRecord[]>("/alumni/placements", { params }),
  stats: () =>
    alisApi.get<PlacementStats>("/alumni/placements/stats"),
  create: (data: Partial<PlacementRecord>) =>
    alisApi.post<PlacementRecord>("/alumni/placements", data),
};

export const jobBoardApi = {
  list: (params?: { status?: string; type?: string }) =>
    alisApi.get<JobPosting[]>("/alumni/jobs", { params }),
  close: (id: string) =>
    alisApi.post<{ ok: boolean }>(`/alumni/jobs/${id}/close`),
};

export const drivesApi = {
  list: () =>
    alisApi.get<RecruitmentDrive[]>("/alumni/drives"),
  updateStatus: (id: string, status: string) =>
    alisApi.patch<RecruitmentDrive>(`/alumni/drives/${id}/status`, { status }),
};

export const mentorsApi = {
  list: () =>
    alisApi.get<AlumniProfile[]>("/alumni/network/mentors"),
};
