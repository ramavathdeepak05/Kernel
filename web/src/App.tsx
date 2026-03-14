import { QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Navigate, Outlet, Route, Routes } from "react-router-dom";
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

import { Users, MessageSquare, BarChart3, GraduationCap, Shield } from "lucide-react";

function PlaceholderPage({ icon: Icon, code, title, desc, tags }: {
  icon: React.ElementType; code: string; title: string; desc: string; tags?: string;
}) {
  return (
    <div className="flex flex-col items-center justify-center h-full text-center fade-up-1">
      <div className="w-14 h-14 rounded-2xl flex items-center justify-center mb-5"
        style={{ background: "rgba(129,140,248,0.1)", border: "1px solid rgba(129,140,248,0.2)" }}>
        <Icon className="w-7 h-7" style={{ color: "#818cf8" }} />
      </div>
      <div className="text-[9px] font-bold uppercase tracking-[0.15em] mb-2" style={{ color: "#818cf8" }}>{code}</div>
      <h1 className="text-2xl font-bold mb-2" style={{ fontFamily: "var(--font-family-sans)", color: "#e2e8f0" }}>{title}</h1>
      <p className="text-[13px]" style={{ color: "#64748b" }}>{desc}</p>
      {tags && (
        <div className="mt-4 px-4 py-2 rounded-lg text-[11px]"
          style={{ background: "rgba(129,140,248,0.06)", border: "1px solid rgba(129,140,248,0.12)", color: "#475569" }}>
          {tags}
        </div>
      )}
    </div>
  );
}

function StudentServicesPage() {
  return <PlaceholderPage icon={Users} code="E09" title="Student Services" desc="Module complete · Frontend in next sprint" tags="Hostel · Library · Grievances · Events · Counselling" />;
}
function CommunicationHubPage() {
  return <PlaceholderPage icon={MessageSquare} code="E10" title="Communication Hub" desc="Module complete · Frontend in next sprint" tags="Bulk Email · SMS · WhatsApp · Templates · Campaigns" />;
}
function ReportingPage() {
  return <PlaceholderPage icon={BarChart3} code="E11" title="Reports & Analytics" desc="Module complete · Frontend in next sprint" tags="Dashboards · Exports · Scheduled · NAAC · Custom" />;
}
function AlumniPage() {
  return <PlaceholderPage icon={GraduationCap} code="E12" title="Alumni & Placement" desc="Module complete · Frontend in next sprint" tags="Alumni DB · Job Board · Placement Stats · Events" />;
}
function SecurityPage() {
  return <PlaceholderPage icon={Shield} code="SEC" title="Security & Audit" desc="Module complete · Audit ledger active" tags="RBAC · Sessions · Audit Log · Compliance · 2FA" />;
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

function AppShell() {
  return (
    <AppLayout>
      <Outlet />
    </AppLayout>
  );
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
            <Route element={<AppShell />}>
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
