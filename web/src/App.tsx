import { QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Navigate, Outlet, Route, Routes } from "react-router-dom";
import { queryClient } from "./lib/queryClient";
import { useAuthStore } from "./store/authStore";
import { useEffect } from "react";

// New three-column ALIS shell (FE-1)
import { ALISShell } from "./shell/ALISShell";

// Public layouts (unchanged)
import PortalLayout from "./layouts/PortalLayout";

// Auth
import LoginPage from "./pages/auth/LoginPage";

// Public portal pages
import PortalHomePage from "./pages/portal/PortalHomePage";
import ApplicationWizardPage from "./pages/portal/ApplicationWizardPage";
import ApplicationStatusPage from "./pages/portal/ApplicationStatusPage";
import OfferLetterPage from "./pages/portal/OfferLetterPage";

// Role dashboards (new views layer)
import { RegistrarDashboard } from "./views/RegistrarDashboard";
import { FacultyDashboard } from "./views/FacultyDashboard";
import { StudentDashboard } from "./views/StudentDashboard";
import { FinanceDashboard } from "./views/FinanceDashboard";
import { HODDashboard } from "./views/HODDashboard";
import { ExamControllerDashboard } from "./views/ExamControllerDashboard";
import { SeatMatrixPage } from "./pages/admissions/SeatMatrixPage";

// Module pages (existing)
import AdmissionsPage from "./pages/admissions/AdmissionsPage";
import AcademicsPage from "./pages/academics/AcademicsPage";
import ExaminationsPage from "./pages/examinations/ExaminationsPage";
import FinancePage from "./pages/finance/FinancePage";
import HRPage from "./pages/hr/HRPage";
import StudentServicesPage from "./pages/student-services/StudentServicesPage";
import CommunicationHubPage from "./pages/communications/CommunicationHubPage";
import ReportsPage from "./pages/reports/ReportsPage";
import AlumniPage from "./pages/alumni/AlumniPage";

// P22 new pages
import { RegulatoryPage } from './pages/regulatory/RegulatoryPage';
import { PolicyStudioPage } from './pages/admin/PolicyStudioPage';
import { AdmissionsModulePage } from './pages/admissions/AdmissionsModulePage';
import { PhDPage } from './pages/phd/PhDPage';
import { ReadmissionPage } from './pages/admissions/ReadmissionPage';
import { ConvocationPage } from './pages/convocation/ConvocationPage';
import { OBEPage } from './pages/academics/OBEPage';
import { GuardianPortalPage } from './pages/portal/GuardianPortalPage';

// P23 new pages
import { WorkflowsPage } from './pages/workflows/WorkflowsPage';
import { ProcessEnginePage } from './pages/process-engine/ProcessEnginePage';
import { ConsentPage } from './pages/consent/ConsentPage';

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

          {/* Protected app — three-column ALIS shell */}
          <Route element={<ProtectedRoute />}>
            <Route element={<ALISShell />}>
              <Route path="/" element={<Navigate to="/dashboard" replace />} />

              {/* Role dashboards */}
              <Route path="/dashboard" element={<RegistrarDashboard />} />
              <Route path="/dashboard/faculty" element={<FacultyDashboard />} />
              <Route path="/dashboard/student" element={<StudentDashboard />} />
              <Route path="/dashboard/finance" element={<FinanceDashboard />} />
              <Route path="/dashboard/hod" element={<HODDashboard />} />
              <Route path="/dashboard/exam-controller" element={<ExamControllerDashboard />} />

              {/* Module pages */}
              <Route path="/admissions" element={<AdmissionsPage />} />
              <Route path="/admissions/seat-matrix" element={<SeatMatrixPage />} />
              <Route path="/academics" element={<AcademicsPage />} />
              <Route path="/examinations" element={<ExaminationsPage />} />
              <Route path="/finance" element={<FinancePage />} />
              <Route path="/hr" element={<HRPage />} />
              <Route path="/students" element={<StudentServicesPage />} />
              <Route path="/communications" element={<CommunicationHubPage />} />
              <Route path="/reports" element={<ReportsPage />} />
              <Route path="/alumni" element={<AlumniPage />} />
              <Route path="/regulatory" element={<RegulatoryPage />} />
              <Route path="/admin/policies" element={<PolicyStudioPage />} />
              <Route path="/admissions/pipeline" element={<AdmissionsModulePage />} />
              <Route path="/admissions/readmission" element={<ReadmissionPage />} />
              <Route path="/phd" element={<PhDPage />} />
              <Route path="/convocation" element={<ConvocationPage />} />
              <Route path="/academics/obe" element={<OBEPage />} />

              {/* P23 new pages */}
              <Route path="/workflows" element={<WorkflowsPage />} />
              <Route path="/process-engine" element={<ProcessEnginePage />} />
              <Route path="/consent" element={<ConsentPage />} />
            </Route>
          </Route>

          {/* Guardian portal — standalone, no shell */}
          <Route path="/guardian" element={<GuardianPortalPage />} />

          {/* Fallback */}
          <Route path="*" element={<Navigate to="/dashboard" replace />} />
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  );
}
