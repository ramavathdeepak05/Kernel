import { useState, FormEvent } from "react";
import { ArrowRight, BookOpen, Clock, Users } from "lucide-react";
import { leadsApi } from "@/services/admissions";
import { MorphingTextReveal } from "@/components/ui/morphing-text-reveal";

const PROGRAMS = [
  { name: "B.Tech", specializations: ["Computer Engineering", "Electronics", "Mechanical", "Civil"], seats: 120 },
  { name: "MBA", specializations: ["General Management", "Finance", "HR", "Marketing"], seats: 60 },
  { name: "BBA", specializations: ["General", "International Business"], seats: 90 },
  { name: "M.Tech", specializations: ["Computer Science", "VLSI", "Structural"], seats: 30 },
  { name: "B.Sc", specializations: ["Physics", "Chemistry", "Mathematics", "Biotechnology"], seats: 60 },
  { name: "MCA", specializations: ["General"], seats: 40 },
];

export default function PortalHomePage() {
  const [trackId, setTrackId] = useState("");
  const [showLeadForm, setShowLeadForm] = useState(false);
  const [leadSubmitted, setLeadSubmitted] = useState(false);
  const [leadForm, setLeadForm] = useState({ first_name: "", last_name: "", email: "", mobile: "", course_interest: "" });
  const [submitting, setSubmitting] = useState(false);

  const handleLeadSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setSubmitting(true);
    try {
      await leadsApi.create({ ...leadForm, source_channel: "WEB_PORTAL" });
      setLeadSubmitted(true);
    } catch {
      // Show form anyway on error
      setLeadSubmitted(true);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="max-w-5xl mx-auto px-6 py-12">
      {/* Hero */}
      <div className="text-center mb-12">
        <div className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full bg-blue-50 border border-blue-100 mb-6">
          <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" />
          <span className="text-[11px] font-semibold text-blue-700">Applications Open · Intake 2025–26</span>
        </div>
        <h1 className="text-4xl font-bold text-slate-900 mb-4" style={{ fontFamily: "var(--font-family-sans)", letterSpacing: "-0.03em" }}>
          Shape Your Future.
          <br />Apply Today.
        </h1>
        <div className="h-6 mb-2 flex justify-center">
          <MorphingTextReveal
            texts={[
              "AI-assisted admissions process.",
              "Apply online, track in real time.",
              "Get decisions faster.",
              "Fully automated. Fully transparent.",
            ]}
            className="text-[15px] text-slate-500"
            interval={3500}
            glitchOnHover={false}
          />
        </div>

        {/* CTA */}
        <div className="flex flex-col sm:flex-row items-center justify-center gap-4 mt-8">
          <a
            href="/apply/application"
            className="flex items-center gap-2 px-6 py-3 rounded-xl font-semibold text-[14px] text-white transition-all"
            style={{ background: "#2563eb", boxShadow: "0 4px 16px rgba(37,99,235,0.3)" }}
            onMouseEnter={(e) => { e.currentTarget.style.boxShadow = "0 6px 24px rgba(37,99,235,0.4)"; e.currentTarget.style.transform = "translateY(-1px)"; }}
            onMouseLeave={(e) => { e.currentTarget.style.boxShadow = "0 4px 16px rgba(37,99,235,0.3)"; e.currentTarget.style.transform = "none"; }}
          >
            Start Application <ArrowRight className="w-4 h-4" />
          </a>
          <button
            onClick={() => setShowLeadForm(true)}
            className="flex items-center gap-2 px-6 py-3 rounded-xl font-semibold text-[14px] text-slate-700 border border-slate-200 bg-white transition-all hover:bg-slate-50"
          >
            Request Information
          </button>
        </div>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-3 gap-4 mb-12">
        {[
          { icon: Users, label: "Applications received", end: 2847, suffix: "" },
          { icon: BookOpen, label: "Programs available", end: 6, suffix: "" },
          { icon: Clock, label: "Avg. processing time", end: 48, suffix: "h" },
        ].map((stat) => {
          const Icon = stat.icon;
          return (
            <div key={stat.label} className="portal-card p-5 text-center group hover:shadow-lg transition-all">
              <Icon className="w-5 h-5 text-blue-500 mx-auto mb-2 group-hover:scale-110 transition-transform" />
              <div className="flex items-baseline justify-center gap-0.5 mb-1">
                <span className="text-2xl font-bold text-slate-900">{stat.end}</span>
                {stat.suffix && <span className="text-2xl font-bold text-slate-900">{stat.suffix}</span>}
              </div>
              <div className="text-[11px] text-slate-500">{stat.label}</div>
            </div>
          );
        })}
      </div>

      {/* Track application */}
      <div className="portal-card p-6 mb-8">
        <h3 className="font-bold text-slate-900 mb-4" style={{ fontFamily: "var(--font-family-sans)" }}>
          Track Your Application
        </h3>
        <div className="flex gap-3">
          <input
            type="text"
            value={trackId}
            onChange={(e) => setTrackId(e.target.value)}
            placeholder="Enter Application ID (e.g. APP-2025-000001)"
            className="flex-1 h-11 px-4 rounded-xl border border-slate-200 text-[13px] outline-none focus:border-blue-400 focus:ring-2 focus:ring-blue-50 transition-all"
            style={{ fontFamily: "var(--font-family-mono)" }}
          />
          <a
            href={trackId ? `/apply/status?id=${trackId}` : "#"}
            className="h-11 px-5 rounded-xl flex items-center gap-2 font-semibold text-[13px] text-white transition-all"
            style={{ background: "#2563eb" }}
          >
            Track <ArrowRight className="w-3.5 h-3.5" />
          </a>
        </div>
      </div>

      {/* Programs grid */}
      <div>
        <h2 className="text-xl font-bold text-slate-900 mb-4" style={{ fontFamily: "var(--font-family-sans)", letterSpacing: "-0.02em" }}>
          Available Programs
        </h2>
        <div className="grid grid-cols-3 gap-4">
          {PROGRAMS.map((prog) => (
            <div key={prog.name} className="portal-card p-5 hover:shadow-lg transition-all cursor-pointer group">
              <div className="flex items-start justify-between mb-3">
                <h3 className="text-lg font-bold text-slate-900" style={{ fontFamily: "var(--font-family-sans)" }}>
                  {prog.name}
                </h3>
                <span className="text-[10px] font-semibold text-emerald-600 bg-emerald-50 border border-emerald-100 px-2 py-0.5 rounded-full">
                  {prog.seats} seats
                </span>
              </div>
              <ul className="space-y-1 mb-4">
                {prog.specializations.map((s) => (
                  <li key={s} className="text-[11px] text-slate-500 flex items-center gap-1.5">
                    <span className="w-1 h-1 rounded-full bg-blue-400" />
                    {s}
                  </li>
                ))}
              </ul>
              <a
                href="/apply/application"
                className="flex items-center gap-1.5 text-[12px] font-semibold text-blue-600 group-hover:gap-2.5 transition-all"
              >
                Apply now <ArrowRight className="w-3.5 h-3.5" />
              </a>
            </div>
          ))}
        </div>
      </div>

      {/* Lead form modal */}
      {showLeadForm && (
        <div
          className="fixed inset-0 flex items-center justify-center z-50 p-4"
          style={{ background: "rgba(0,0,0,0.5)" }}
          onClick={(e) => { if (e.target === e.currentTarget) setShowLeadForm(false); }}
        >
          <div className="portal-card w-full max-w-md p-8">
            {leadSubmitted ? (
              <div className="text-center py-4">
                <div className="w-12 h-12 rounded-full bg-emerald-50 flex items-center justify-center mx-auto mb-4">
                  <span className="text-2xl">✓</span>
                </div>
                <h3 className="font-bold text-slate-900 mb-2" style={{ fontFamily: "var(--font-family-sans)" }}>
                  Thank you!
                </h3>
                <p className="text-[13px] text-slate-500">
                  We'll send programme details and application links to your email within 24 hours.
                </p>
                <button onClick={() => setShowLeadForm(false)} className="mt-4 text-[13px] font-semibold text-blue-600">
                  Close
                </button>
              </div>
            ) : (
              <>
                <h3 className="font-bold text-slate-900 mb-6" style={{ fontFamily: "var(--font-family-sans)" }}>
                  Request Information
                </h3>
                <form onSubmit={handleLeadSubmit} className="space-y-4">
                  <div className="grid grid-cols-2 gap-3">
                    <div>
                      <label className="block text-[11px] font-semibold text-slate-500 mb-1.5 uppercase tracking-wide">First Name</label>
                      <input required value={leadForm.first_name} onChange={(e) => setLeadForm({ ...leadForm, first_name: e.target.value })}
                        className="w-full h-10 px-3 rounded-lg border border-slate-200 text-[13px] outline-none focus:border-blue-400 transition-all" />
                    </div>
                    <div>
                      <label className="block text-[11px] font-semibold text-slate-500 mb-1.5 uppercase tracking-wide">Last Name</label>
                      <input required value={leadForm.last_name} onChange={(e) => setLeadForm({ ...leadForm, last_name: e.target.value })}
                        className="w-full h-10 px-3 rounded-lg border border-slate-200 text-[13px] outline-none focus:border-blue-400 transition-all" />
                    </div>
                  </div>
                  <div>
                    <label className="block text-[11px] font-semibold text-slate-500 mb-1.5 uppercase tracking-wide">Email</label>
                    <input required type="email" value={leadForm.email} onChange={(e) => setLeadForm({ ...leadForm, email: e.target.value })}
                      className="w-full h-10 px-3 rounded-lg border border-slate-200 text-[13px] outline-none focus:border-blue-400 transition-all" />
                  </div>
                  <div>
                    <label className="block text-[11px] font-semibold text-slate-500 mb-1.5 uppercase tracking-wide">Mobile</label>
                    <input required value={leadForm.mobile} onChange={(e) => setLeadForm({ ...leadForm, mobile: e.target.value })}
                      className="w-full h-10 px-3 rounded-lg border border-slate-200 text-[13px] outline-none focus:border-blue-400 transition-all" />
                  </div>
                  <div>
                    <label className="block text-[11px] font-semibold text-slate-500 mb-1.5 uppercase tracking-wide">Programme Interest</label>
                    <select value={leadForm.course_interest} onChange={(e) => setLeadForm({ ...leadForm, course_interest: e.target.value })}
                      className="w-full h-10 px-3 rounded-lg border border-slate-200 text-[13px] outline-none focus:border-blue-400 transition-all bg-white">
                      <option value="">Select programme</option>
                      {PROGRAMS.map((p) => <option key={p.name} value={p.name}>{p.name}</option>)}
                    </select>
                  </div>
                  <button type="submit" disabled={submitting}
                    className="w-full h-11 rounded-xl font-semibold text-[13px] text-white transition-all"
                    style={{ background: "#2563eb" }}>
                    {submitting ? "Submitting…" : "Send Request"}
                  </button>
                </form>
              </>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
