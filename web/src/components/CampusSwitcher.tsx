/**
 * CampusSwitcher — lets staff switch between campuses/tenants they are linked to.
 *
 * Fetches GET /organizations/my-campuses → list of tenants the current user
 * is authorised for. Switching updates X-Tenant-ID in localStorage and
 * triggers a full page reload to re-fetch all tenant-scoped data.
 */

import { useState, useEffect, useRef } from "react";
import { alisApi } from "@/lib/alis-api";

interface Campus {
  tenant_id: string;
  name: string;
  type?: string;
}

interface CampusSwitcherProps {
  compact?: boolean; // true = icon-only (for 52px nav), false = label visible
}

export function CampusSwitcher({ compact = false }: CampusSwitcherProps) {
  const [campuses, setCampuses] = useState<Campus[]>([]);
  const [current, setCurrent] = useState<string>(
    sessionStorage.getItem("tenant_id") ?? "demo"
  );
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    alisApi
      .get<{ campuses: Campus[] }>("/organizations/my-campuses")
      .then((r) => setCampuses(r.campuses ?? []))
      .catch(() => null);
  }, []);

  // Close on outside click
  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

  const handleSelect = (tenantId: string) => {
    if (tenantId === current) { setOpen(false); return; }
    sessionStorage.setItem("tenant_id", tenantId);
    setCurrent(tenantId);
    setOpen(false);
    // Full reload so all API calls pick up new tenant
    window.location.reload();
  };

  const currentLabel = campuses.find((c) => c.tenant_id === current)?.name ?? current;

  if (campuses.length <= 1) return null; // Only show if user has multiple campuses

  return (
    <div ref={ref} style={{ position: "relative" }}>
      <button
        onClick={() => setOpen((v) => !v)}
        title={compact ? `Campus: ${currentLabel}` : undefined}
        style={{
          display: "flex",
          alignItems: "center",
          gap: compact ? 0 : 6,
          padding: compact ? "6px" : "6px 10px",
          background: open ? "rgba(29,158,117,0.15)" : "rgba(255,255,255,0.04)",
          border: "1px solid rgba(29,158,117,0.3)",
          borderRadius: 8,
          cursor: "pointer",
          color: "#1D9E75",
          fontSize: 12,
          fontWeight: 600,
          whiteSpace: "nowrap",
          transition: "background 0.15s",
        }}
      >
        {/* Campus icon */}
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" style={{ flexShrink: 0 }}>
          <path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z" />
          <polyline points="9 22 9 12 15 12 15 22" />
        </svg>
        {!compact && (
          <>
            <span style={{ maxWidth: 100, overflow: "hidden", textOverflow: "ellipsis" }}>
              {currentLabel}
            </span>
            <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5"
              style={{ transform: open ? "rotate(180deg)" : "rotate(0)", transition: "transform 0.15s" }}>
              <polyline points="6 9 12 15 18 9" />
            </svg>
          </>
        )}
      </button>

      {open && (
        <div style={{
          position: "absolute",
          top: "calc(100% + 4px)",
          left: compact ? 0 : "auto",
          right: compact ? "auto" : 0,
          minWidth: 200,
          background: "#11131F",
          border: "1px solid #1E2235",
          borderRadius: 10,
          boxShadow: "0 8px 24px rgba(0,0,0,0.4)",
          zIndex: 500,
          overflow: "hidden",
        }}>
          <div style={{ padding: "8px 12px 4px", fontSize: 10, fontWeight: 700, color: "#7B82A8", textTransform: "uppercase", letterSpacing: "0.08em" }}>
            Switch Campus
          </div>
          {campuses.map((c) => (
            <button
              key={c.tenant_id}
              onClick={() => handleSelect(c.tenant_id)}
              style={{
                display: "flex",
                alignItems: "center",
                width: "100%",
                padding: "9px 12px",
                background: c.tenant_id === current ? "rgba(29,158,117,0.12)" : "transparent",
                border: "none",
                borderLeft: c.tenant_id === current ? "3px solid #1D9E75" : "3px solid transparent",
                cursor: "pointer",
                fontSize: 13,
                color: c.tenant_id === current ? "#1D9E75" : "#C9D1E9",
                fontWeight: c.tenant_id === current ? 600 : 400,
                textAlign: "left",
                gap: 8,
                transition: "background 0.1s",
              }}
            >
              <span style={{ flex: 1 }}>{c.name}</span>
              {c.tenant_id === current && (
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="#1D9E75" strokeWidth="2.5">
                  <polyline points="20 6 9 17 4 12" />
                </svg>
              )}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
