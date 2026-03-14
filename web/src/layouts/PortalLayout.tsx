import { Outlet } from "react-router-dom";

export default function PortalLayout() {
  return (
    <div className="portal-bg min-h-screen flex flex-col" style={{ overflowY: "auto", overflowX: "hidden" }}>
      {/* Portal header */}
      <header className="bg-white border-b border-slate-200 px-6 py-4 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 rounded-lg flex items-center justify-center font-bold text-sm"
            style={{ background: "#2563eb", color: "white", fontFamily: "var(--font-family-sans)" }}>
            A
          </div>
          <div>
            <div className="text-[14px] font-bold text-slate-900" style={{ fontFamily: "var(--font-family-sans)" }}>
              ALIS Admissions Portal
            </div>
            <div className="text-[10px] text-slate-500">Admission Cycle 2025–26</div>
          </div>
        </div>
        <div className="flex items-center gap-3">
          <span className="text-[11px] font-semibold px-3 py-1.5 rounded-full bg-emerald-50 text-emerald-600 border border-emerald-100">
            Applications Open
          </span>
          <a href="/apply/status" className="text-[12px] font-semibold text-slate-600 hover:text-slate-900 transition-colors">
            Track Application
          </a>
        </div>
      </header>

      {/* Content */}
      <main className="flex-1">
        <Outlet />
      </main>

      {/* Footer */}
      <footer className="border-t border-slate-200 bg-white px-6 py-5 text-center">
        <p className="text-[11px] text-slate-400">
          Powered by ALIS · admissions@institution.edu.in · © 2025 Institution Name
        </p>
      </footer>
    </div>
  );
}
