import { DollarSign } from "lucide-react";
export default function FinancePage() {
  return (
    <div className="flex flex-col items-center justify-center h-full text-center fade-up-1">
      <div className="w-14 h-14 rounded-2xl flex items-center justify-center mb-5"
        style={{ background: "rgba(251,191,36,0.1)", border: "1px solid rgba(251,191,36,0.2)" }}>
        <DollarSign className="w-7 h-7" style={{ color: "#fbbf24" }} />
      </div>
      <div className="text-[9px] font-bold uppercase tracking-[0.15em] mb-2" style={{ color: "#fbbf24" }}>E07</div>
      <h1 className="text-2xl font-bold mb-2" style={{ fontFamily: "var(--font-family-sans)", color: "#e2e8f0" }}>Finance</h1>
      <p className="text-[13px]" style={{ color: "#64748b" }}>Module complete · Frontend in next sprint</p>
    </div>
  );
}
