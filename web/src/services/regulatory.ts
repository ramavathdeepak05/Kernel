const API = import.meta.env.VITE_API_URL || "/api/v1";

function headers() {
  const token = sessionStorage.getItem("token");
  return {
    "Content-Type": "application/json",
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
  };
}

export const regulatoryService = {
  // NAAC
  getNAACDashboard: () =>
    fetch(`${API}/regulatory/naac/dashboard`, { headers: headers() }).then(r => r.json()),
  getSSRData: (year: string) =>
    fetch(`${API}/regulatory/naac/ssr?year=${year}`, { headers: headers() }).then(r => r.json()),
  addEvidence: (criterion: string, data: Record<string, string>) =>
    fetch(`${API}/regulatory/naac/evidence`, {
      method: "POST", headers: headers(),
      body: JSON.stringify({ criterion, ...data }),
    }).then(r => r.json()),

  // NIRF
  getNIRFData: (year: string) =>
    fetch(`${API}/regulatory/nirf/compute?year=${year}`, { headers: headers() }).then(r => r.json()),

  // UGC
  getUGCReturn: (year: string) =>
    fetch(`${API}/regulatory/ugc/annual-return?year=${year}`, { headers: headers() }).then(r => r.json()),
  getFacultyCompliance: () =>
    fetch(`${API}/regulatory/ugc/faculty-compliance`, { headers: headers() }).then(r => r.json()),

  // AICTE
  getAICTEDashboard: () =>
    fetch(`${API}/regulatory/aicte/dashboard`, { headers: headers() }).then(r => r.json()),

  // IQAC
  getIQACReadiness: () =>
    fetch(`${API}/regulatory/iqac/readiness`, { headers: headers() }).then(r => r.json()),
  getAQARData: (year: string) =>
    fetch(`${API}/regulatory/iqac/aqar?year=${year}`, { headers: headers() }).then(r => r.json()),
};
