import { QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Navigate, Outlet, Route, Routes } from "react-router-dom";
// Outlet used by ProtectedRoute
import { queryClient } from "./lib/queryClient";
import { useAuthStore } from "./store/authStore";
import { useEffect } from "react";

import AppLayout from "./layouts/AppLayout";
import PortalLayout from "./layouts/PortalLayout";

import LoginPage from "./pages/auth/LoginPage";
import DashboardPage from "./pages/dashboard/DashboardPage";
import AdmissionsPage from "./pages/admissions/AdmissionsPage";
import AcademicsPage from "./pages/academics/AcademicsPage";
import ExaminationsPage from "./pages/examinations/ExaminationsPage";
import FinancePage from "./pages/finance/FinancePage";
import HRPage from "./pages/hr/HRPage";

import PortalHomePage from "./pages/portal/PortalHomePage";
import ApplicationWizardPage from "./pages/portal/ApplicationWizardPage";
import ApplicationStatusPage from "./pages/portal/ApplicationStatusPage";
import OfferLetterPage from "./pages/portal/OfferLetterPage";

import StudentServicesPage from "./pages/student-services/StudentServicesPage";
import { MessageSquare, BarChart3, GraduationCap, Shield } from "lucide-react";

function PlaceholderPage({ icon: Icon, code, title, desc, tags }: {
  icon: React.ElementType; code: string; title: string; desc: string; tags?: string;
}) {
  return (
    <div className="flex flex-col items-center justify-center h-full text-center fade-up-1">
      <div className="w-14 h-14 rounded-2xl flex items-center justify-center mb-5"
        style={{ background: "rgba(29,158,117,0.08)", border: "0.5px solid rgba(29,158,117,0.2)" }}>
        <Icon className="w-7 h-7" style={{ color: "#1D9E75" }} />
      </div>
      <div className="text-[9px] font-medium uppercase tracking-[0.15em] mb-2" style={{ color: "#1D9E75" }}>{code}</div>
      <h1 className="text-xl font-medium mb-2" style={{ color: "#e2e8f0" }}>{title}</h1>
      <p className="text-[13px]" style={{ color: "#64748b" }}>{desc}</p>
      {tags && (
        <div className="mt-4 px-4 py-2 rounded-lg text-[11px]"
          style={{ background: "rgba(29,158,117,0.05)", border: "0.5px solid rgba(29,158,117,0.12)", color: "#475569" }}>
          {tags}
        </div>
      )}
    </div>
  );
}

function CommunicationHubPage() {
  return <PlaceholderPage icon={MessageSquare} code="E10" title="Communication Hub" desc="Backend complete · Frontend in next sprint" tags="Bulk email · SMS · WhatsApp · Templates · Campaigns" />;
}
function ReportingPage() {
  return <PlaceholderPage icon={BarChart3} code="E11" title="Reports & Analytics" desc="Backend complete · Frontend in next sprint" tags="Dashboards · Exports · Scheduled · NAAC · Custom" />;
}
function AlumniPage() {
  return <PlaceholderPage icon={GraduationCap} code="E12" title="Alumni & Placement" desc="Backend complete · Frontend in next sprint" tags="Alumni DB · Job board · Placement stats · Events" />;
}
function SecurityPage() {
  return <PlaceholderPage icon={Shield} code="SEC" title="Security & audit" desc="Audit ledger active" tags="RBAC · Sessions · Audit log · Compliance · 2FA" />;
}

function ProtectedRoute() {
  const { isAuthenticated, hydrate } = useAuthStore();

  useEffect(() => {
    hydrate();
  }, [hydrate]);

  if (!isAuthenticated) {
    return <Navigate to="/login" replace />;
  }
  return <Outlet />;
}

export default function App() {
  const { hydrate } = useAuthStore();

  useEffect(() => {
    hydrate();
  }, [hydrate]);

  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <Routes>
          {/* Public auth */}
          <Route path="/login" element={<LoginPage />} />

          {/* Public portal */}
          <Route path="/apply" element={<PortalLayout />}>
            <Route index element={<PortalHomePage />} />
            <Route path="application" element={<ApplicationWizardPage />} />
            <Route path="status" element={<ApplicationStatusPage />} />
            <Route path="offer" element={<OfferLetterPage />} />
          </Route>

          {/* Protected app */}
          <Route element={<ProtectedRoute />}>
            <Route element={<AppLayout />}>
              <Route path="/" element={<Navigate to="/admissions" replace />} />
              <Route path="/dashboard" element={<DashboardPage />} />
              <Route path="/admissions" element={<AdmissionsPage />} />
              <Route path="/academics" element={<AcademicsPage />} />
              <Route path="/examinations" element={<ExaminationsPage />} />
              <Route path="/finance" element={<FinancePage />} />
              <Route path="/hr" element={<HRPage />} />
              <Route path="/students" element={<StudentServicesPage />} />

              <Route path="/communications" element={<CommunicationHubPage />} />
              <Route path="/reports" element={<ReportingPage />} />
              <Route path="/alumni" element={<AlumniPage />} />
              <Route path="/security" element={<SecurityPage />} />
            </Route>
          </Route>

          {/* Fallback */}
          <Route path="*" element={<Navigate to="/admissions" replace />} />
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  );
}
