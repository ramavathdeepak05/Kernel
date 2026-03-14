import { ShieldCheck } from "lucide-react";
export default function SecurityPage() {
  return (
    <div className="flex flex-col items-center justify-center h-full text-center fade-up-1">
      <div className="w-14 h-14 rounded-2xl flex items-center justify-center mb-5"
        style={{ background: "rgba(52,211,153,0.1)", border: "1px solid rgba(52,211,153,0.2)" }}>
        <ShieldCheck className="w-7 h-7" style={{ color: "#34d399" }} />
      </div>
      <h1 className="text-2xl font-bold mb-2" style={{ fontFamily: "var(--font-family-sans)", color: "#e2e8f0" }}>Security & Governance</h1>
      <div className="flex items-center gap-2 justify-center">
        <span className="w-2 h-2 rounded-full" style={{ background: "#34d399", boxShadow: "0 0 8px #34d399" }} />
        <p className="text-[13px]" style={{ color: "#34d399" }}>All systems operational</p>
      </div>
    </div>
  );
}
