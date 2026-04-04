import { QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Navigate, Outlet, Route, Routes } from "react-router-dom";
import { queryClient } from "./lib/queryClient";
import { useAuthStore } from "./store/authStore";
import { useEffect } from "react";
import { ErrorBoundary } from "./components/ErrorBoundary";

// Rebuilt shell + dashboard per ALIS_FRONTEND_SPEC.md
import { NewALISShell } from "./components/shell/NewALISShell";
import { RoleDashboard } from "./components/dashboard/RoleDashboard";

// Public layouts (unchanged)
import PortalLayout from "./layouts/PortalLayout";

// Auth
import LoginPage from "./pages/auth/LoginPage";

// Public portal pages
import PortalHomePage from "./pages/portal/PortalHomePage";
import ApplicationWizardPage from "./pages/portal/ApplicationWizardPage";
import ApplicationStatusPage from "./pages/portal/ApplicationStatusPage";
import OfferLetterPage from "./pages/portal/OfferLetterPage";

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
import { OnboardingWizardPage } from './pages/admin/OnboardingWizardPage';
import { AdmissionsModulePage } from './pages/admissions/AdmissionsModulePage';
import { PhDPage } from './pages/phd/PhDPage';
import { ReadmissionPage } from './pages/admissions/ReadmissionPage';
import { ConvocationPage } from './pages/convocation/ConvocationPage';
import { OBEPage } from './pages/academics/OBEPage';
import { LearningPage } from './pages/academics/LearningPage';
import { GuardianPortalPage } from './pages/portal/GuardianPortalPage';

// P23 new pages
import { WorkflowsPage } from './pages/workflows/WorkflowsPage';
import { ProcessEnginePage } from './pages/process-engine/ProcessEnginePage';
import { ConsentPage } from './pages/consent/ConsentPage';
import { TeamManagementPage } from './pages/admin/TeamManagementPage';

// Settings
import { SettingsPage } from './pages/settings/SettingsPage';

// P28 — Offline PWA attendance (standalone, no shell — loads as installable page)
import { OfflineAttendancePage } from './pages/attendance/OfflineAttendancePage';

import { MyCoursesPage } from './pages/student/MyCoursesPage';
import { MyExamsPage } from './pages/student/MyExamsPage';
import { MyFeesPage } from './pages/student/MyFeesPage';
import { MyLibraryPage } from './pages/student/MyLibraryPage';
import { ClubsEventsPage } from './pages/clubs/ClubsEventsPage';
import { TrainingPage } from './pages/hr/TrainingPage';
import { RecruitmentPage } from './pages/hr/RecruitmentPage';
import { BudgetPage } from './pages/finance/BudgetPage';
import { VendorsPage } from './pages/finance/VendorsPage';

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
    <ErrorBoundary>
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
            <Route element={<NewALISShell />}>
              <Route path="/" element={<Navigate to="/dashboard" replace />} />

              {/* Role dashboard — auto-selects by role per ALIS_FRONTEND_SPEC.md §6 */}
              <Route path="/dashboard" element={<RoleDashboard />} />

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
              <Route path="/admin/onboarding" element={<OnboardingWizardPage />} />
              <Route path="/admissions/pipeline" element={<AdmissionsModulePage />} />
              <Route path="/admissions/readmission" element={<ReadmissionPage />} />
              <Route path="/phd" element={<PhDPage />} />
              <Route path="/convocation" element={<ConvocationPage />} />
              <Route path="/academics/obe" element={<OBEPage />} />
              <Route path="/academics/learning" element={<LearningPage />} />  {/* P40 In-house LMS */}

              {/* P23 new pages */}
              <Route path="/workflows" element={<WorkflowsPage />} />
              <Route path="/process-engine" element={<ProcessEnginePage />} />
              <Route path="/consent" element={<ConsentPage />} />

              {/* Team management */}
              <Route path="/admin/team" element={<TeamManagementPage />} />

              {/* Student self-service routes */}
              <Route path="/my/courses" element={<MyCoursesPage />} />
              <Route path="/my/exams" element={<MyExamsPage />} />
              <Route path="/my/fees" element={<MyFeesPage />} />
              <Route path="/my/library" element={<MyLibraryPage />} />

              {/* New module routes */}
              <Route path="/clubs" element={<ClubsEventsPage />} />
              <Route path="/training" element={<TrainingPage />} />
              <Route path="/recruitment" element={<RecruitmentPage />} />
              <Route path="/budget" element={<BudgetPage />} />
              <Route path="/vendors" element={<VendorsPage />} />

              {/* Settings — SUPER_ADMIN / Admin */}
              <Route path="/settings" element={<SettingsPage />} />
            </Route>
          </Route>

          {/* Guardian portal — standalone, no shell */}
          <Route path="/guardian" element={<GuardianPortalPage />} />

          {/* Offline PWA attendance — standalone, installable (feature flag: academics.offline_attendance_pwa) */}
          <Route path="/attendance/mark/:sessionId" element={<OfflineAttendancePage />} />

          {/* Fallback */}
          <Route path="*" element={<Navigate to="/dashboard" replace />} />
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
    </ErrorBoundary>
  );
}
