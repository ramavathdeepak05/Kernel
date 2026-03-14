import { useState } from "react";
import { Outlet, useLocation, useNavigate } from "react-router-dom";
import Header from "@/components/layout/Header";
import ChatPanel from "@/components/layout/ChatPanel";

const MODULE_LABELS: Record<string, string> = {
  "/admissions": "Admissions",
  "/academics": "Academics",
  "/examinations": "Examinations",
  "/finance": "Finance",
  "/hr": "HR & Staff",
  "/students": "Student Services",
  "/communications": "Communication Hub",
  "/reports": "Reporting",
  "/alumni": "Alumni",
  "/dashboard": "Dashboard",
};

export default function AppLayout() {
  const [chatOpen, setChatOpen] = useState(true);
  const location = useLocation();
  const navigate = useNavigate();

  const currentModule = MODULE_LABELS[location.pathname] ?? "ALIS";
  const moduleContext = location.pathname.replace("/", "") || "dashboard";

  return (
    <div
      className="flex flex-col h-screen overflow-hidden bg-grid"
      style={{ background: "var(--color-bg)" }}
    >
      {/* Top header */}
      <Header
        currentModule={currentModule}
        onModuleChange={(path) => navigate(path)}
      />

      {/* Main content: left panel + divider + right chat */}
      <div className="flex flex-1 min-h-0">
        {/* Main module content (left panel) */}
        <main className="flex-1 min-w-0 overflow-hidden flex flex-col">
          <div className="flex-1 overflow-y-auto px-8 py-6">
            <Outlet />
          </div>
        </main>

        {/* Glass divider */}
        <div className="panel-divider" />

        {/* AI chat panel (right) */}
        <ChatPanel
          isOpen={chatOpen}
          onToggle={() => setChatOpen(!chatOpen)}
          moduleContext={moduleContext}
        />
      </div>
    </div>
  );
}
