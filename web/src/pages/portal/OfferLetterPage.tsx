import { useState } from "react";
import { useSearchParams } from "react-router-dom";
import { CheckCircle, Download, Clock, AlertTriangle } from "lucide-react";
import { offersApi } from "@/services/admissions";

export default function OfferLetterPage() {
  const [params] = useSearchParams();
  const offerId = params.get("id") ?? "OFFER-2025-000089";
  const [accepted, setAccepted] = useState(false);
  const [declined, setDeclined] = useState(false);
  const [declining, setDeclining] = useState(false);
  const [declineReason, setDeclineReason] = useState("");
  const [showDeclineModal, setShowDeclineModal] = useState(false);
  const [loading, setLoading] = useState(false);

  const handleAccept = async () => {
    setLoading(true);
    try {
      await offersApi.accept(offerId);
    } catch {
      /* handle gracefully */
    }
    setLoading(false);
    setAccepted(true);
  };

  const handleDecline = async () => {
    setDeclining(true);
    try {
      await offersApi.decline(offerId, declineReason);
    } catch { /* */ }
    setDeclining(false);
    setDeclined(true);
    setShowDeclineModal(false);
  };

  if (accepted) {
    return (
      <div className="max-w-lg mx-auto px-6 py-20 text-center">
        <div className="w-16 h-16 rounded-full bg-emerald-50 flex items-center justify-center mx-auto mb-6">
          <CheckCircle className="w-8 h-8 text-emerald-500" />
        </div>
        <h2 className="text-2xl font-bold text-slate-900 mb-3" style={{ fontFamily: "var(--font-family-sans)" }}>
          Offer Accepted!
        </h2>
        <p className="text-[14px] text-slate-500 mb-6">
          Welcome to the institution, Sarah! Your seat is confirmed. You will receive onboarding details at your registered email.
        </p>
        <div className="portal-card p-5 text-left">
          <p className="text-[12px] font-semibold text-slate-700 mb-3">Next steps:</p>
          <ul className="space-y-2">
            {["Pay seat confirmation fee (₹25,000)", "Report on July 14, 2025 with original documents", "Collect Student ID and portal credentials"].map((step) => (
              <li key={step} className="flex items-start gap-2 text-[12px] text-slate-500">
                <CheckCircle className="w-4 h-4 text-emerald-400 flex-shrink-0 mt-0.5" />{step}
              </li>
            ))}
          </ul>
        </div>
      </div>
    );
  }

  if (declined) {
    return (
      <div className="max-w-lg mx-auto px-6 py-20 text-center">
        <div className="w-16 h-16 rounded-full bg-slate-100 flex items-center justify-center mx-auto mb-6">
          <AlertTriangle className="w-8 h-8 text-slate-400" />
        </div>
        <h2 className="text-2xl font-bold text-slate-900 mb-3" style={{ fontFamily: "var(--font-family-sans)" }}>
          Offer Declined
        </h2>
        <p className="text-[14px] text-slate-500">Your decision has been recorded. We wish you all the best in your future endeavours.</p>
      </div>
    );
  }

  return (
    <div className="max-w-2xl mx-auto px-6 py-12">
      {/* Offer letter display */}
      <div className="portal-card overflow-hidden mb-6">
        {/* Letterhead */}
        <div className="px-10 py-8" style={{ background: "linear-gradient(135deg, #1e3a8a 0%, #1d4ed8 100%)" }}>
          <div className="flex items-center justify-between text-white">
            <div>
              <div className="text-xl font-bold mb-0.5" style={{ fontFamily: "var(--font-family-sans)" }}>ALIS University</div>
              <div className="text-blue-200 text-[11px]">Autonomous Institutional Management System</div>
            </div>
            <div className="text-right">
              <div className="text-[11px] text-blue-200">Ref: {offerId}</div>
              <div className="text-[11px] text-blue-200 mt-0.5">Date: {new Date().toLocaleDateString("en-IN", { day: "2-digit", month: "long", year: "numeric" })}</div>
            </div>
          </div>
        </div>

        <div className="px-10 py-8">
          <h2 className="text-xl font-bold text-slate-900 mb-6" style={{ fontFamily: "var(--font-family-sans)" }}>
            Offer of Admission
          </h2>

          <div className="grid grid-cols-2 gap-6 mb-6">
            {[
              { label: "Student Name", value: "Sarah Jenkins" },
              { label: "Application ID", value: "APP-2025-000089" },
              { label: "Programme", value: "B.Tech Computer Engineering" },
              { label: "Intake", value: "July 2025 · 4 Years" },
            ].map((item) => (
              <div key={item.label}>
                <div className="text-[10px] uppercase tracking-wider font-semibold text-slate-400 mb-1">{item.label}</div>
                <div className="text-[14px] font-semibold text-slate-800">{item.value}</div>
              </div>
            ))}
          </div>

          <div className="border-t border-slate-100 pt-6 mb-6">
            <h3 className="font-semibold text-slate-800 mb-3 text-[13px]">Fee Structure</h3>
            <table className="w-full text-[13px]">
              <tbody>
                {[
                  { item: "Tuition Fee (per semester)", amount: "₹75,000" },
                  { item: "Hostel (optional)", amount: "₹35,000" },
                  { item: "Admission / Seat Confirmation Fee", amount: "₹25,000" },
                ].map((row) => (
                  <tr key={row.item} className="border-b border-slate-50">
                    <td className="py-2 text-slate-600">{row.item}</td>
                    <td className="py-2 text-right font-semibold text-slate-800">{row.amount}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div className="flex items-center gap-2 px-4 py-3 rounded-lg bg-amber-50 border border-amber-100">
            <Clock className="w-4 h-4 text-amber-500 flex-shrink-0" />
            <p className="text-[12px] text-amber-700">
              <strong>Acceptance Deadline: June 30, 2025.</strong> This offer expires if not accepted by midnight IST.
            </p>
          </div>
        </div>
      </div>

      {/* Actions */}
      <div className="flex gap-4">
        <button
          onClick={handleAccept}
          disabled={loading}
          className="flex-1 h-12 rounded-xl font-semibold text-[14px] text-white transition-all"
          style={{ background: loading ? "#6b7280" : "#16a34a", boxShadow: loading ? "none" : "0 4px 16px rgba(22,163,74,0.3)" }}
        >
          {loading ? "Processing…" : "Accept Offer & Confirm Seat"}
        </button>
        <button
          onClick={() => {}}
          className="h-12 px-5 rounded-xl border border-slate-200 text-[13px] font-semibold text-slate-600 flex items-center gap-2 hover:bg-slate-50 transition-all"
        >
          <Download className="w-4 h-4" /> Download
        </button>
        <button
          onClick={() => setShowDeclineModal(true)}
          className="h-12 px-5 rounded-xl border border-rose-200 text-[13px] font-semibold text-rose-600 hover:bg-rose-50 transition-all"
        >
          Decline
        </button>
      </div>

      {/* Decline modal */}
      {showDeclineModal && (
        <div className="fixed inset-0 flex items-center justify-center z-50 p-4" style={{ background: "rgba(0,0,0,0.4)" }}>
          <div className="portal-card w-full max-w-sm p-6">
            <h3 className="font-bold text-slate-900 mb-4" style={{ fontFamily: "var(--font-family-sans)" }}>Decline Offer</h3>
            <p className="text-[13px] text-slate-500 mb-4">Please let us know why you are declining (optional).</p>
            <textarea
              value={declineReason}
              onChange={(e) => setDeclineReason(e.target.value)}
              placeholder="Reason for declining…"
              rows={3}
              className="w-full px-3 py-2 rounded-lg border border-slate-200 text-[13px] outline-none focus:border-rose-400 transition-all mb-4"
            />
            <div className="flex gap-3">
              <button onClick={handleDecline} disabled={declining}
                className="flex-1 h-10 rounded-lg text-[13px] font-semibold text-white bg-rose-500 hover:bg-rose-600 transition-all">
                {declining ? "Processing…" : "Confirm Decline"}
              </button>
              <button onClick={() => setShowDeclineModal(false)}
                className="flex-1 h-10 rounded-lg text-[13px] font-semibold text-slate-600 border border-slate-200 hover:bg-slate-50 transition-all">
                Cancel
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
