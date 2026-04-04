const API = import.meta.env.VITE_API_URL || "/api/v1";

export const guardianService = {
  sendOTP: (phone: string, tenantId: string) =>
    fetch(`${API}/guardian/send-otp`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ phone, tenant_id: tenantId }),
    }).then(r => r.json()),

  verifyOTP: (phone: string, otp: string, tenantId: string) =>
    fetch(`${API}/guardian/verify-otp`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ phone, otp, tenant_id: tenantId }),
    }).then(r => r.json()),

  getStudentDashboard: (studentId: string, sessionToken: string) =>
    fetch(`${API}/guardian/dashboard/${studentId}`, {
      headers: { Authorization: `Bearer ${sessionToken}` },
    }).then(r => r.json()),
};
