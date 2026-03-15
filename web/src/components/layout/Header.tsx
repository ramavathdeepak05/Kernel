import { useState } from "react";
import { Bell, ChevronDown, Search, LogOut } from "lucide-react";
import { useAuthStore } from "@/store/authStore";
import { cn } from "@/lib/utils";

const MODULE_OPTIONS = [
  { id: "admissions", label: "Admissions", path: "/admissions", badge: "E04" },
  { id: "academics", label: "Academics", path: "/academics", badge: "E05" },
  { id: "examinations", label: "Examinations", path: "/examinations", badge: "E06" },
  { id: "finance", label: "Finance", path: "/finance", badge: "E07" },
  { id: "hr",            label: "HR & Staff",         path: "/hr",            badge: "E08" },
  { id: "students",      label: "Student Services",   path: "/students",      badge: "E09" },
  { id: "communications",label: "Communication Hub",  path: "/communications",badge: "E10" },
  { id: "reports",       label: "Reports & Analytics",path: "/reports",       badge: "E11" },
  { id: "alumni",        label: "Alumni & Placement", path: "/alumni",        badge: "E12" },
];

interface HeaderProps {
  currentModule?: string;
  onModuleChange?: (path: string) => void;
}

export default function Header({ currentModule = "Admissions", onModuleChange }: HeaderProps) {
  const { user, logout } = useAuthStore();
  const [showUserMenu, setShowUserMenu] = useState(false);
  const [showModuleMenu, setShowModuleMenu] = useState(false);
  const [notifCount] = useState(3);

  return (
    <header
      className="flex items-center justify-between px-6 py-3 flex-shrink-0"
      style={{
        borderBottom: "1px solid rgba(255,255,255,0.06)",
        background: "rgba(255,255,255,0.02)",
        height: 56,
      }}
    >
      {/* Left: Logo + module selector */}
      <div className="flex items-center gap-4">
        {/* ALIS wordmark */}
        <div className="flex items-center gap-2.5">
          <div
            className="w-7 h-7 rounded-lg flex items-center justify-center font-bold text-[13px]"
            style={{
              background: "#1D9E75",
              border: "0.5px solid rgba(29,158,117,0.4)",
              color: "#fff",
              fontFamily: "var(--font-family-sans)",
              
            }}
          >
            A
          </div>
          <span
            className="text-[14px] font-semibold tracking-tight"
            style={{ fontFamily: "var(--font-family-sans)", color: "#e2e8f0" }}
          >
            ALIS
          </span>
        </div>

        {/* Separator */}
        <div className="w-px h-4" style={{ background: "rgba(255,255,255,0.08)" }} />

        {/* Module selector */}
        <div className="relative">
          <button
            onClick={() => setShowModuleMenu(!showModuleMenu)}
            className="flex items-center gap-2 px-3 py-1.5 rounded-lg transition-all"
            style={{
              background: showModuleMenu ? "rgba(129,140,248,0.1)" : "transparent",
              border: "1px solid transparent",
            }}
            onMouseEnter={(e) => { e.currentTarget.style.background = "rgba(255,255,255,0.04)"; }}
            onMouseLeave={(e) => { if (!showModuleMenu) e.currentTarget.style.background = "transparent"; }}
          >
            <span className="text-[12px] font-semibold" style={{ color: "#94a3b8" }}>
              {currentModule}
            </span>
            <ChevronDown className="w-3 h-3" style={{ color: "#475569" }} />
          </button>

          {showModuleMenu && (
            <div
              className="absolute top-full left-0 mt-1 py-1 rounded-xl z-50 min-w-[180px]"
              style={{
                background: "#111127",
                border: "1px solid rgba(255,255,255,0.1)",
                boxShadow: "0 8px 32px rgba(0,0,0,0.5)",
              }}
            >
              {MODULE_OPTIONS.map((mod) => (
                <button
                  key={mod.id}
                  onClick={() => {
                    setShowModuleMenu(false);
                    onModuleChange?.(mod.path);
                  }}
                  className="w-full flex items-center justify-between px-4 py-2 text-left transition-colors"
                  style={{ color: "#94a3b8" }}
                  onMouseEnter={(e) => { e.currentTarget.style.background = "rgba(255,255,255,0.04)"; e.currentTarget.style.color = "#e2e8f0"; }}
                  onMouseLeave={(e) => { e.currentTarget.style.background = "transparent"; e.currentTarget.style.color = "#94a3b8"; }}
                >
                  <span className="text-[12px] font-medium">{mod.label}</span>
                  <span className="text-[9px] font-bold px-1.5 py-0.5 rounded"
                    style={{ background: "rgba(129,140,248,0.1)", color: "#fff", border: "1px solid rgba(129,140,248,0.2)" }}>
                    {mod.badge}
                  </span>
                </button>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Center: Search */}
      <div className="flex-1 max-w-xs mx-8">
        <div className="relative">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5" style={{ color: "#475569" }} />
          <input
            type="text"
            placeholder="Search applicants, IDs, status…"
            className="w-full h-8 pl-9 pr-4 rounded-lg text-[12px] outline-none transition-all"
            style={{
              background: "rgba(255,255,255,0.04)",
              border: "1px solid rgba(255,255,255,0.07)",
              color: "#e2e8f0",
              fontFamily: "var(--font-family-mono)",
            }}
            onFocus={(e) => { e.currentTarget.style.borderColor = "rgba(129,140,248,0.3)"; }}
            onBlur={(e) => { e.currentTarget.style.borderColor = "rgba(255,255,255,0.07)"; }}
          />
          <kbd className="absolute right-3 top-1/2 -translate-y-1/2 text-[9px] px-1.5 py-0.5 rounded"
            style={{ background: "rgba(255,255,255,0.05)", color: "#475569", border: "1px solid rgba(255,255,255,0.08)" }}>
            ⌘K
          </kbd>
        </div>
      </div>

      {/* Right: Notifications + User */}
      <div className="flex items-center gap-3">
        {/* Notifications */}
        <button className="relative w-8 h-8 rounded-lg flex items-center justify-center transition-all"
          style={{ background: "rgba(255,255,255,0.03)", border: "1px solid rgba(255,255,255,0.07)" }}
          onMouseEnter={(e) => { e.currentTarget.style.background = "rgba(255,255,255,0.07)"; }}
          onMouseLeave={(e) => { e.currentTarget.style.background = "rgba(255,255,255,0.03)"; }}
        >
          <Bell className="w-3.5 h-3.5" style={{ color: "#94a3b8" }} />
          {notifCount > 0 && (
            <span className="absolute -top-0.5 -right-0.5 w-4 h-4 rounded-full text-[9px] font-bold flex items-center justify-center"
              style={{ background: "#fb7185", color: "white" }}>
              {notifCount}
            </span>
          )}
        </button>

        {/* Role chip */}
        {user?.role && (
          <div className="px-2 py-1 rounded text-[9px] font-bold uppercase tracking-wider"
            style={{ background: "rgba(129,140,248,0.08)", color: "#fff", border: "1px solid rgba(129,140,248,0.15)" }}>
            {user.role.replace(/_/g, " ")}
          </div>
        )}

        {/* User menu */}
        <div className="relative">
          <button
            onClick={() => setShowUserMenu(!showUserMenu)}
            className="flex items-center gap-2 px-2 py-1 rounded-lg transition-all"
            style={{ border: "1px solid transparent" }}
            onMouseEnter={(e) => { e.currentTarget.style.background = "rgba(255,255,255,0.04)"; }}
            onMouseLeave={(e) => { e.currentTarget.style.background = "transparent"; }}
          >
            <div className="w-6 h-6 rounded-full flex items-center justify-center text-[10px] font-bold"
              style={{ background: "rgba(129,140,248,0.2)", color: "#818cf8" }}>
              {user?.full_name?.charAt(0).toUpperCase() ?? "U"}
            </div>
            <span className="text-[12px] font-medium hidden sm:block" style={{ color: "#94a3b8" }}>
              {user?.full_name?.split(" ")[0] ?? "User"}
            </span>
          </button>

          {showUserMenu && (
            <div
              className="absolute top-full right-0 mt-1 py-1 rounded-xl z-50 min-w-[160px]"
              style={{
                background: "#111127",
                border: "1px solid rgba(255,255,255,0.1)",
                boxShadow: "0 8px 32px rgba(0,0,0,0.5)",
              }}
            >
              <div className="px-4 py-2" style={{ borderBottom: "1px solid rgba(255,255,255,0.06)" }}>
                <div className="text-[12px] font-semibold" style={{ color: "#e2e8f0" }}>{user?.full_name}</div>
                <div className="text-[10px] mt-0.5" style={{ color: "#64748b" }}>{user?.email}</div>
              </div>
              <button
                onClick={logout}
                className="w-full flex items-center gap-2 px-4 py-2 text-[12px] transition-colors"
                style={{ color: "#94a3b8" }}
                onMouseEnter={(e) => { e.currentTarget.style.background = "rgba(251,113,133,0.06)"; e.currentTarget.style.color = "#fb7185"; }}
                onMouseLeave={(e) => { e.currentTarget.style.background = "transparent"; e.currentTarget.style.color = "#94a3b8"; }}
              >
                <LogOut className="w-3.5 h-3.5" />
                Sign out
              </button>
            </div>
          )}
        </div>
      </div>
    </header>
  );
}
