const API = import.meta.env.VITE_API_URL || "/api/v1";

function headers() {
  const token = sessionStorage.getItem("token");
  return {
    "Content-Type": "application/json",
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
  };
}

export const studentServicesAPI = {
  // Clubs & Events (SS-6)
  listClubs: () =>
    fetch(`${API}/student-services/clubs`, { headers: headers() }).then(r => r.json()),
  proposeClub: (data: Record<string, unknown>) =>
    fetch(`${API}/student-services/clubs`, {
      method: "POST", headers: headers(), body: JSON.stringify(data),
    }).then(r => r.json()),
  listEvents: () =>
    fetch(`${API}/student-services/events`, { headers: headers() }).then(r => r.json()),
  proposeEvent: (data: Record<string, unknown>) =>
    fetch(`${API}/student-services/events`, {
      method: "POST", headers: headers(), body: JSON.stringify(data),
    }).then(r => r.json()),

  // Grievance (SS-5)
  listGrievances: () =>
    fetch(`${API}/student-services/grievances`, { headers: headers() }).then(r => r.json()),
  submitGrievance: (data: Record<string, unknown>) =>
    fetch(`${API}/student-services/grievances`, {
      method: "POST", headers: headers(), body: JSON.stringify(data),
    }).then(r => r.json()),
  getSLABreaches: () =>
    fetch(`${API}/student-services/grievances/sla-breaches`, { headers: headers() }).then(r => r.json()),

  // Hostel (SS-1)
  checkHostelEligibility: (studentId: string) =>
    fetch(`${API}/student-services/hostel/eligibility/${studentId}`, { headers: headers() }).then(r => r.json()),

  // Library (SS-2)
  checkLibraryNoDues: (studentId: string) =>
    fetch(`${API}/student-services/library/no-dues/${studentId}`, { headers: headers() }).then(r => r.json()),

  // Health (SS-7)
  triggerEmergency: (studentId: string, details: string) =>
    fetch(`${API}/student-services/health/emergency`, {
      method: "POST", headers: headers(),
      body: JSON.stringify({ student_id: studentId, details }),
    }).then(r => r.json()),
};
