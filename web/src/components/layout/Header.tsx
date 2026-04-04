import { useState, useEffect } from "react";
import { Bell, ChevronDown, Search, LogOut, Check, CheckCheck } from "lucide-react";
import { useAuthStore } from "@/store/authStore";
import { cn } from "@/lib/utils";
import { Popover, PopoverTrigger, PopoverContent } from "@/components/ui/popover";
import { AnimatePresence, motion } from "framer-motion";

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

interface Notification {
  id: number;
  user: string;
  action: string;
  target: string;
  timestamp: string;
  unread: boolean;
}

const INITIAL_NOTIFICATIONS: Notification[] = [
  { id: 1, user: "Dr. Anand Rao", action: "submitted leave application", target: "4-day medical leave", timestamp: "2 min ago", unread: true },
  { id: 2, user: "Finance Dept", action: "flagged fee waiver", target: "Priya Sharma — ₹18,400", timestamp: "15 min ago", unread: true },
  { id: 3, user: "AI Agent", action: "auto-approved batch", target: "Bonafide — 12 students", timestamp: "1 hr ago", unread: true },
  { id: 4, user: "Exam Controller", action: "dispatched hall tickets", target: "B.Tech CSE Sem 5", timestamp: "2 hrs ago", unread: false },
  { id: 5, user: "System", action: "completed backup", target: "Daily snapshot", timestamp: "5 hrs ago", unread: false },
];

interface HeaderProps {
  currentModule?: string;
  onModuleChange?: (path: string) => void;
}

export default function Header({ currentModule = "Admissions", onModuleChange }: HeaderProps) {
  const { user, logout } = useAuthStore();
  const [showUserMenu, setShowUserMenu] = useState(false);
  const [showModuleMenu, setShowModuleMenu] = useState(false);
  const [notifications, setNotifications] = useState(INITIAL_NOTIFICATIONS);

  const unreadCount = notifications.filter(n => n.unread).length;

  function markRead(id: number) {
    setNotifications(prev => prev.map(n => n.id === id ? { ...n, unread: false } : n));
  }

  function markAllRead() {
    setNotifications(prev => prev.map(n => ({ ...n, unread: false })));
  }

  return (
    <header
      className="flex items-center justify-between px-6 py-3 flex-shrink-0"
      style={{
        borderBottom: "0.5px solid rgba(0,0,0,0.08)",
        background: "rgba(255,255,255,0.92)",
        backdropFilter: "blur(16px)",
        WebkitBackdropFilter: "blur(16px)",
        height: 52,
      }}
    >
      {/* Left: Logo + module selector */}
      <div className="flex items-center gap-4">
        {/* ALIS wordmark */}
        <div className="flex items-center gap-2.5">
          <div
            className="w-6 h-6 rounded flex items-center justify-center font-bold text-[12px]"
            style={{
              background: "#1D9E75",
              color: "#fff",
              fontFamily: "var(--font-family-display)",
              boxShadow: "0 0 10px rgba(29,158,117,0.3)",
            }}
          >
            A
          </div>
          <span
            className="text-[13px] font-bold tracking-widest uppercase"
            style={{ fontFamily: "var(--font-family-display)", color: "#0a0a0a", letterSpacing: "0.14em" }}
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
            className="flex items-center gap-2 px-3 py-1.5 rounded-lg transition-all duration-150"
            style={{
              background: showModuleMenu ? "rgba(29,158,117,0.08)" : "transparent",
              border: `1px solid ${showModuleMenu ? "rgba(29,158,117,0.2)" : "transparent"}`,
            }}
            onMouseEnter={(e) => { e.currentTarget.style.background = "rgba(255,255,255,0.04)"; }}
            onMouseLeave={(e) => { if (!showModuleMenu) { e.currentTarget.style.background = "transparent"; e.currentTarget.style.border = "1px solid transparent"; } }}
          >
            <span className="text-[11px] font-semibold tracking-wide uppercase" style={{ color: "#888", letterSpacing: "0.06em" }}>
              {currentModule}
            </span>
            <ChevronDown className="w-3 h-3" style={{ color: "#bbb" }} />
          </button>

          {showModuleMenu && (
            <div
              className="absolute top-full left-0 mt-1 py-1 rounded-xl z-50 min-w-[180px]"
              style={{
                background: "#ffffff",
                border: "0.5px solid rgba(0,0,0,0.09)",
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
                  style={{ color: "#555" }}
                  onMouseEnter={(e) => { e.currentTarget.style.background = "rgba(255,255,255,0.04)"; e.currentTarget.style.color = "#e2e8f0"; }}
                  onMouseLeave={(e) => { e.currentTarget.style.background = "transparent"; e.currentTarget.style.color = "#94a3b8"; }}
                >
                  <span className="text-[12px] font-medium">{mod.label}</span>
                  <span className="text-[9px] font-bold px-1.5 py-0.5 rounded"
                    style={{ background: "rgba(29,158,117,0.10)", color: "#1D9E75", border: "0.5px solid rgba(29,158,117,0.25)" }}>
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
            className="w-full h-8 pl-9 pr-4 rounded-lg text-[12px] outline-none transition-all duration-200"
            style={{
              background: "rgba(255,255,255,0.04)",
              border: "1px solid rgba(255,255,255,0.07)",
              color: "#e2e8f0",
              fontFamily: "var(--font-family-mono)",
            }}
            onFocus={(e) => { e.currentTarget.style.borderColor = "rgba(29,158,117,0.35)"; e.currentTarget.style.boxShadow = "0 0 0 3px rgba(29,158,117,0.06)"; }}
            onBlur={(e) => { e.currentTarget.style.borderColor = "rgba(255,255,255,0.07)"; e.currentTarget.style.boxShadow = "none"; }}
          />
          <kbd className="absolute right-3 top-1/2 -translate-y-1/2 text-[9px] px-1.5 py-0.5 rounded"
            style={{ background: "rgba(255,255,255,0.05)", color: "#475569", border: "1px solid rgba(255,255,255,0.08)" }}>
            ⌘K
          </kbd>
        </div>
      </div>

      {/* Right: Notifications + User */}
      <div className="flex items-center gap-3">
        {/* Notifications popover */}
        <Popover>
          <PopoverTrigger asChild>
            <button
              className="relative w-8 h-8 rounded-lg flex items-center justify-center transition-all duration-150"
              style={{ background: "rgba(0,0,0,0.04)", border: "0.5px solid rgba(0,0,0,0.09)" }}
              onMouseEnter={(e) => { e.currentTarget.style.background = "rgba(255,255,255,0.07)"; }}
              onMouseLeave={(e) => { e.currentTarget.style.background = "rgba(255,255,255,0.03)"; }}
            >
              <Bell className="w-3.5 h-3.5" style={{ color: "#555" }} />
              <AnimatePresence>
                {unreadCount > 0 && (
                  <motion.span
                    initial={{ scale: 0 }}
                    animate={{ scale: 1 }}
                    exit={{ scale: 0 }}
                    className="absolute -top-0.5 -right-0.5 w-4 h-4 rounded-full text-[9px] font-bold flex items-center justify-center"
                    style={{ background: "#1D9E75", color: "#fff", boxShadow: "0 0 8px rgba(29,158,117,0.5)" }}
                  >
                    {unreadCount > 99 ? "99+" : unreadCount}
                  </motion.span>
                )}
              </AnimatePresence>
            </button>
          </PopoverTrigger>
          <PopoverContent
            align="end"
            sideOffset={8}
            className="w-80 p-0"
            style={{
              background: "#ffffff",
              border: "0.5px solid rgba(0,0,0,0.09)",
              borderRadius: 12,
              boxShadow: "0 8px 32px rgba(0,0,0,0.10), 0 0 0 1px rgba(29,158,117,0.08)",
            }}
          >
            {/* Header */}
            <div className="flex items-center justify-between px-4 py-3" style={{ borderBottom: "0.5px solid rgba(0,0,0,0.07)" }}>
              <span className="text-[12px] font-semibold" style={{ color: "#0a0a0a" }}>
                Notifications
              </span>
              {unreadCount > 0 && (
                <button
                  onClick={markAllRead}
                  className="flex items-center gap-1 text-[10px] font-medium transition-colors duration-150"
                  style={{ color: "#1D9E75", background: "none", border: "none", cursor: "pointer" }}
                >
                  <CheckCheck className="w-3 h-3" />
                  Mark all read
                </button>
              )}
            </div>

            {/* Notification list */}
            <div className="max-h-72 overflow-y-auto" style={{ scrollbarWidth: "thin" }}>
              {notifications.map((notif) => (
                <button
                  key={notif.id}
                  onClick={() => markRead(notif.id)}
                  className="w-full flex items-start gap-3 px-4 py-3 text-left transition-colors duration-100"
                  style={{
                    borderBottom: "1px solid rgba(255,255,255,0.04)",
                    background: notif.unread ? "rgba(29,158,117,0.04)" : "transparent",
                    border: "none",
                    borderBlockEnd: "0.5px solid rgba(0,0,0,0.06)",
                    cursor: "pointer",
                  }}
                  onMouseEnter={(e) => { e.currentTarget.style.background = "rgba(255,255,255,0.04)"; }}
                  onMouseLeave={(e) => { e.currentTarget.style.background = notif.unread ? "rgba(29,158,117,0.04)" : "transparent"; }}
                >
                  {/* Unread dot */}
                  <div className="mt-1.5 flex-shrink-0">
                    {notif.unread ? (
                      <div className="w-2 h-2 rounded-full" style={{ background: "#1D9E75", boxShadow: "0 0 4px rgba(29,158,117,0.6)" }} />
                    ) : (
                      <Check className="w-2 h-2" style={{ color: "#ccc" }} />
                    )}
                  </div>

                  <div className="flex-1 min-w-0">
                    <p className="text-[11px] leading-relaxed" style={{ color: "#e2e8f0", margin: 0 }}>
                      <strong style={{ fontWeight: 600 }}>{notif.user}</strong>{" "}
                      <span style={{ color: "#555" }}>{notif.action}</span>
                    </p>
                    <p className="text-[11px] mt-0.5 truncate" style={{ color: "#999", margin: 0 }}>
                      {notif.target}
                    </p>
                    <p className="text-[10px] mt-1" style={{ color: "#bbb", margin: 0 }}>
                      {notif.timestamp}
                    </p>
                  </div>
                </button>
              ))}
            </div>

            {/* Footer */}
            <div className="px-4 py-2.5 text-center" style={{ borderTop: "0.5px solid rgba(0,0,0,0.07)" }}>
              <button
                className="text-[11px] font-medium transition-colors duration-150"
                style={{ color: "#1D9E75", background: "none", border: "none", cursor: "pointer" }}
              >
                View all notifications
              </button>
            </div>
          </PopoverContent>
        </Popover>

        {/* Role chip */}
        {user?.role && (
          <div className="px-2 py-1 rounded text-[9px] font-bold uppercase tracking-wider"
            style={{ background: "rgba(29,158,117,0.08)", color: "#1D9E75", border: "0.5px solid rgba(29,158,117,0.22)" }}>
            {user.role.replace(/_/g, " ")}
          </div>
        )}

        {/* User menu */}
        <div className="relative">
          <button
            onClick={() => setShowUserMenu(!showUserMenu)}
            className="flex items-center gap-2 px-2 py-1 rounded-lg transition-all duration-150"
            style={{ border: "1px solid transparent" }}
            onMouseEnter={(e) => { e.currentTarget.style.background = "rgba(255,255,255,0.04)"; }}
            onMouseLeave={(e) => { e.currentTarget.style.background = "transparent"; }}
          >
            <div className="w-6 h-6 rounded-full flex items-center justify-center text-[10px] font-bold"
              style={{ background: "rgba(129,140,248,0.2)", color: "#818cf8" }}>
              {user?.full_name?.charAt(0).toUpperCase() ?? "U"}
            </div>
            <span className="text-[12px] font-medium hidden sm:block" style={{ color: "#555" }}>
              {user?.full_name?.split(" ")[0] ?? "User"}
            </span>
          </button>

          {showUserMenu && (
            <div
              className="absolute top-full right-0 mt-1 py-1 rounded-xl z-50 min-w-[160px]"
              style={{
                background: "#ffffff",
                border: "0.5px solid rgba(0,0,0,0.09)",
                boxShadow: "0 8px 32px rgba(0,0,0,0.5)",
              }}
            >
              <div className="px-4 py-2" style={{ borderBottom: "0.5px solid rgba(0,0,0,0.07)" }}>
                <div className="text-[12px] font-semibold" style={{ color: "#0a0a0a" }}>{user?.full_name}</div>
                <div className="text-[10px] mt-0.5" style={{ color: "#64748b" }}>{user?.email}</div>
              </div>
              <button
                onClick={logout}
                className="w-full flex items-center gap-2 px-4 py-2 text-[12px] transition-colors"
                style={{ color: "#555" }}
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
