import { useState } from "react";
import { CheckCircle, ArrowRight, ArrowLeft, Save } from "lucide-react";

const STEPS = [
  { n: 1, title: "Personal Details" },
  { n: 2, title: "Contact" },
  { n: 3, title: "Academic — 10th" },
  { n: 4, title: "Academic — 12th" },
  { n: 5, title: "Entrance Exam" },
  { n: 6, title: "Programme" },
  { n: 7, title: "Documents" },
  { n: 8, title: "Other Info" },
  { n: 9, title: "Review" },
  { n: 10, title: "Payment" },
];

function FieldGroup({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <label className="block text-[11px] font-semibold text-slate-500 uppercase tracking-wide mb-1.5">{label}</label>
      {children}
    </div>
  );
}

const inputCls = "w-full h-10 px-3 rounded-lg border border-slate-200 text-[13px] outline-none focus:border-blue-400 focus:ring-2 focus:ring-blue-50 transition-all";
const selectCls = inputCls + " bg-white";

function Step1({ data, setData }: { data: Record<string, string>; setData: (d: Record<string, string>) => void }) {
  return (
    <div className="grid grid-cols-2 gap-5">
      <FieldGroup label="First Name"><input className={inputCls} value={data.first_name ?? ""} onChange={(e) => setData({ ...data, first_name: e.target.value })} /></FieldGroup>
      <FieldGroup label="Last Name"><input className={inputCls} value={data.last_name ?? ""} onChange={(e) => setData({ ...data, last_name: e.target.value })} /></FieldGroup>
      <FieldGroup label="Date of Birth"><input type="date" className={inputCls} value={data.dob ?? ""} onChange={(e) => setData({ ...data, dob: e.target.value })} /></FieldGroup>
      <FieldGroup label="Gender">
        <select className={selectCls} value={data.gender ?? ""} onChange={(e) => setData({ ...data, gender: e.target.value })}>
          <option value="">Select</option><option>Male</option><option>Female</option><option>Non-binary</option><option>Prefer not to say</option>
        </select>
      </FieldGroup>
      <FieldGroup label="Nationality"><input className={inputCls} value={data.nationality ?? "Indian"} onChange={(e) => setData({ ...data, nationality: e.target.value })} /></FieldGroup>
      <FieldGroup label="Category">
        <select className={selectCls} value={data.category ?? ""} onChange={(e) => setData({ ...data, category: e.target.value })}>
          <option value="">Select</option><option>General</option><option>SC</option><option>ST</option><option>OBC-NCL</option><option>EWS</option><option>PwD</option>
        </select>
      </FieldGroup>
    </div>
  );
}

function Step6({ data, setData }: { data: Record<string, string>; setData: (d: Record<string, string>) => void }) {
  return (
    <div className="grid grid-cols-2 gap-5">
      <div className="col-span-2">
        <FieldGroup label="Programme">
          <select className={selectCls} value={data.program ?? ""} onChange={(e) => setData({ ...data, program: e.target.value })}>
            <option value="">Select programme</option><option>B.Tech</option><option>MBA</option><option>BBA</option><option>M.Tech</option><option>B.Sc</option><option>MCA</option>
          </select>
        </FieldGroup>
      </div>
      <FieldGroup label="Specialization"><input className={inputCls} value={data.specialization ?? ""} onChange={(e) => setData({ ...data, specialization: e.target.value })} /></FieldGroup>
      <FieldGroup label="Intake Batch"><input className={inputCls} placeholder="e.g. July 2025" value={data.intake_batch ?? ""} onChange={(e) => setData({ ...data, intake_batch: e.target.value })} /></FieldGroup>
      <FieldGroup label="Hostel Required">
        <select className={selectCls} value={data.hostel ?? ""} onChange={(e) => setData({ ...data, hostel: e.target.value })}>
          <option value="">Select</option><option value="yes">Yes</option><option value="no">No</option>
        </select>
      </FieldGroup>
      <FieldGroup label="Scholarship Consideration">
        <select className={selectCls} value={data.scholarship ?? ""} onChange={(e) => setData({ ...data, scholarship: e.target.value })}>
          <option value="">Select</option><option value="yes">Yes</option><option value="no">No</option>
        </select>
      </FieldGroup>
    </div>
  );
}

function GenericStep({ stepNum }: { stepNum: number }) {
  const labels: Record<number, { fields: string[] }> = {
    2: { fields: ["Permanent Address", "City", "State", "Pincode", "Emergency Contact Name", "Emergency Contact Phone"] },
    3: { fields: ["Board Name", "School Name", "Year of Passing", "Total Marks", "Marks Obtained", "Percentage"] },
    4: { fields: ["Board Name", "School/College", "Year of Passing", "Subjects (comma-separated)", "Aggregate %", "Status (Passed/Appearing)"] },
    5: { fields: ["Exam Name (JEE/NEET/CAT/etc.)", "Roll Number", "Score / Percentile", "Rank", "Year of Exam"] },
    8: { fields: ["How did you hear about us?", "Work Experience (months, if any)", "Any disability or special needs?"] },
  };
  const step = labels[stepNum];
  if (!step) return (
    <div className="flex flex-col items-center py-10 text-slate-400">
      <Save className="w-8 h-8 mb-2 opacity-40" />
      <p className="text-[13px]">Step {stepNum} content</p>
    </div>
  );
  return (
    <div className="grid grid-cols-2 gap-5">
      {step.fields.map((f) => (
        <FieldGroup key={f} label={f}><input className={inputCls} placeholder={f} /></FieldGroup>
      ))}
    </div>
  );
}

function ReviewStep({ data }: { data: Record<string, string> }) {
  return (
    <div className="space-y-4">
      <p className="text-[13px] text-slate-500">Please review your information before submitting.</p>
      <div className="portal-card p-5 grid grid-cols-2 gap-3">
        {Object.entries(data).filter(([, v]) => v).map(([k, v]) => (
          <div key={k}>
            <div className="text-[10px] uppercase tracking-wide font-semibold text-slate-400">{k.replace(/_/g, " ")}</div>
            <div className="text-[13px] text-slate-700 font-medium">{v}</div>
          </div>
        ))}
      </div>
      <label className="flex items-start gap-3 cursor-pointer">
        <input type="checkbox" className="mt-0.5" />
        <span className="text-[12px] text-slate-600">I confirm that all information provided is accurate and complete.</span>
      </label>
    </div>
  );
}

function PaymentStep() {
  return (
    <div className="max-w-sm">
      <div className="portal-card p-6 mb-5">
        <h3 className="font-bold text-slate-900 mb-3" style={{ fontFamily: "var(--font-family-sans)" }}>Application Fee</h3>
        <div className="flex justify-between items-center">
          <span className="text-[13px] text-slate-600">Application Processing Fee</span>
          <span className="text-lg font-bold text-slate-900">₹1,000</span>
        </div>
        <div className="border-t border-slate-100 mt-3 pt-3 flex justify-between">
          <span className="text-[13px] font-semibold text-slate-700">Total</span>
          <span className="text-lg font-bold text-blue-600">₹1,000</span>
        </div>
      </div>
      <button className="w-full h-12 rounded-xl font-semibold text-[14px] text-white transition-all"
        style={{ background: "#2563eb", boxShadow: "0 4px 14px rgba(37,99,235,0.3)" }}>
        Pay ₹1,000 via Razorpay
      </button>
    </div>
  );
}

export default function ApplicationWizardPage() {
  const [step, setStep] = useState(1);
  const [data, setData] = useState<Record<string, string>>({});

  const canPrev = step > 1;
  const canNext = step < 10;

  return (
    <div className="max-w-4xl mx-auto px-6 py-10">
      <div className="mb-8">
        <h1 className="text-2xl font-bold text-slate-900" style={{ fontFamily: "var(--font-family-sans)", letterSpacing: "-0.02em" }}>
          Application Form
        </h1>
        <p className="text-[13px] text-slate-500 mt-1">Step {step} of 10 · Draft auto-saved</p>
      </div>

      <div className="flex gap-8">
        {/* Step indicator */}
        <div className="flex-shrink-0 w-48">
          <div className="space-y-1">
            {STEPS.map((s) => (
              <button
                key={s.n}
                onClick={() => setStep(s.n)}
                className="w-full flex items-center gap-3 px-3 py-2 rounded-lg text-left transition-all"
                style={{
                  background: step === s.n ? "rgba(37,99,235,0.06)" : "transparent",
                  border: `1px solid ${step === s.n ? "rgba(37,99,235,0.15)" : "transparent"}`,
                }}
              >
                <div className={`w-5 h-5 rounded-full flex items-center justify-center flex-shrink-0 text-[10px] font-bold ${
                  s.n < step ? "bg-emerald-100" : s.n === step ? "bg-blue-100" : "bg-slate-100"
                }`} style={{ color: s.n < step ? "#16a34a" : s.n === step ? "#2563eb" : "#94a3b8" }}>
                  {s.n < step ? <CheckCircle className="w-3 h-3" /> : s.n}
                </div>
                <span className="text-[11px] font-medium" style={{ color: s.n === step ? "#2563eb" : s.n < step ? "#16a34a" : "#94a3b8" }}>
                  {s.title}
                </span>
              </button>
            ))}
          </div>
        </div>

        {/* Form content */}
        <div className="flex-1">
          {/* Progress bar */}
          <div className="h-1 bg-slate-100 rounded-full mb-6">
            <div className="h-full rounded-full bg-blue-500 transition-all" style={{ width: `${(step / 10) * 100}%` }} />
          </div>

          <div className="portal-card p-7 mb-5">
            <h2 className="text-[16px] font-bold text-slate-900 mb-5" style={{ fontFamily: "var(--font-family-sans)" }}>
              {STEPS[step - 1].title}
            </h2>
            {step === 1 && <Step1 data={data} setData={setData} />}
            {step === 6 && <Step6 data={data} setData={setData} />}
            {step === 9 && <ReviewStep data={data} />}
            {step === 10 && <PaymentStep />}
            {![1, 6, 9, 10].includes(step) && <GenericStep stepNum={step} />}
          </div>

          {/* Navigation */}
          <div className="flex items-center justify-between">
            <button
              onClick={() => canPrev && setStep(step - 1)}
              disabled={!canPrev}
              className="flex items-center gap-2 px-5 py-2.5 rounded-xl text-[13px] font-semibold border border-slate-200 text-slate-600 hover:bg-slate-50 disabled:opacity-40 transition-all"
            >
              <ArrowLeft className="w-4 h-4" /> Back
            </button>
            <button className="flex items-center gap-1.5 text-[12px] text-slate-400 hover:text-slate-600 transition-colors">
              <Save className="w-3.5 h-3.5" /> Save draft
            </button>
            {canNext && (
              <button
                onClick={() => setStep(step + 1)}
                className="flex items-center gap-2 px-5 py-2.5 rounded-xl text-[13px] font-semibold text-white transition-all"
                style={{ background: "#2563eb" }}
              >
                Next <ArrowRight className="w-4 h-4" />
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
