import { FileText } from "lucide-react";
export default function ExaminationsPage() {
  return (
    <div className="flex flex-col items-center justify-center h-full text-center fade-up-1">
      <div className="w-14 h-14 rounded-2xl flex items-center justify-center mb-5"
        style={{ background: "rgba(52,211,153,0.1)", border: "1px solid rgba(52,211,153,0.2)" }}>
        <FileText className="w-7 h-7" style={{ color: "#34d399" }} />
      </div>
      <div className="text-[9px] font-bold uppercase tracking-[0.15em] mb-2" style={{ color: "#34d399" }}>E06</div>
      <h1 className="text-2xl font-bold mb-2" style={{ fontFamily: "var(--font-family-sans)", color: "#e2e8f0" }}>Examinations</h1>
      <p className="text-[13px]" style={{ color: "#64748b" }}>Module complete · Frontend in next sprint</p>
      <div className="mt-4 px-4 py-2 rounded-lg text-[11px]"
        style={{ background: "rgba(52,211,153,0.06)", border: "1px solid rgba(52,211,153,0.12)", color: "#475569" }}>
        Hall Tickets · Seating · Evaluation · Results · Grade Cards
      </div>
    </div>
  );
}
