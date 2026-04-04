import { useState, useCallback, useEffect } from "react";
import { CheckCircle, ArrowRight, ArrowLeft, Save, Loader2, CreditCard } from "lucide-react";
import {
  Stepper,
  StepperList,
  StepperItem,
  StepperTrigger,
  StepperIndicator,
  StepperSeparator
} from "@/components/ui/steps";
import { Progress } from "@/components/ui/interfaces-progress";
import { useUpdateApplication, useSubmitApplication, useCreateApplication } from "@/hooks/use-admissions";
import { alisApi } from "@/lib/alis-api";

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
    <div className="grid grid-cols-2 gap-6">
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
    <div className="grid grid-cols-2 gap-6">
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

function GenericStep({ stepNum, data, setData }: { stepNum: number; data: Record<string, string>; setData: (d: Record<string, string>) => void }) {
  const labels: Record<number, { fields: string[] }> = {
    2: { fields: ["Permanent_Address", "City", "State", "Pincode", "Emergency_Contact_Name", "Emergency_Contact_Phone"] },
    3: { fields: ["Board_Name", "School_Name", "Year_of_Passing", "Total_Marks", "Marks_Obtained", "Percentage"] },
    4: { fields: ["Board_Name", "School_College", "Year_of_Passing", "Subjects_comma_separated", "Aggregate_Pct", "Status_Passed_Appearing"] },
    5: { fields: ["Exam_Name_JEE_NEET_CAT_etc", "Roll_Number", "Score_Percentile", "Rank", "Year_of_Exam"] },
    7: { fields: ["Aadhar_Card_Number", "PAN_Card"] },
    8: { fields: ["Hear_about_us", "Work_Experience_months", "Special_Needs"] },
  };
  const step = labels[stepNum];
  if (!step) return (
    <div className="flex flex-col items-center py-12 text-slate-400">
      <Save className="w-8 h-8 mb-3 opacity-40" />
      <p className="text-[13px] font-medium">Pending Configuration</p>
      <p className="text-[11px] mt-1">Fields for Step {stepNum} are not currently active.</p>
    </div>
  );
  return (
    <div className="grid grid-cols-2 gap-6">
      {step.fields.map((f) => {
        const humanLabel = f.replace(/_/g, " ");
        return (
          <FieldGroup key={f} label={humanLabel}>
            <input 
              className={inputCls} 
              placeholder={humanLabel} 
              value={data[f] ?? ""}
              onChange={(e) => setData({ ...data, [f]: e.target.value })}
            />
          </FieldGroup>
        );
      })}
    </div>
  );
}

function ReviewStep({ data }: { data: Record<string, string> }) {
  return (
    <div className="space-y-5">
      <p className="text-[13px] text-slate-500">Please review your information before final submission. AI pre-processing checks will run upon submit.</p>
      <div className="portal-card p-6 grid grid-cols-2 gap-5 border border-slate-200 rounded-xl bg-slate-50/50">
        {Object.entries(data).filter(([, v]) => v).map(([k, v]) => (
          <div key={k}>
            <div className="text-[10px] uppercase tracking-wider font-semibold text-slate-400 mb-0.5">{k.replace(/_/g, " ")}</div>
            <div className="text-[13px] text-slate-700 font-semibold">{v}</div>
          </div>
        ))}
      </div>
      <label className="flex items-start gap-3 cursor-pointer mt-4 p-3 rounded-lg hover:bg-slate-50">
        <input type="checkbox" className="mt-1 w-4 h-4 rounded border-slate-300 text-blue-600 focus:ring-blue-500" />
        <span className="text-[13px] text-slate-600 font-medium">I solemnly declare that all information and documents provided are authentic and accurate to the best of my knowledge.</span>
      </label>
    </div>
  );
}

function PaymentStep({ applicantId }: { applicantId: string }) {
  const [paying, setPaying] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handlePay = async () => {
    setPaying(true);
    setError(null);
    try {
      const result = await alisApi.post<{ payment_url?: string; order_id?: string }>(
        "/admissions/payments/initiate",
        { application_id: applicantId, fee_type: "application" }
      );
      if (result.payment_url) {
        window.location.href = result.payment_url;
      } else {
         // mock success if running locally without gateway
         setTimeout(() => {
           window.location.href = "/apply/status";
         }, 1000);
      }
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Payment initiation failed.");
    } finally {
      setPaying(false);
    }
  };

  return (
    <div className="max-w-md mx-auto">
      <div className="portal-card p-6 mb-5 border border-slate-200 shadow-sm rounded-2xl bg-white">
        <h3 className="font-bold text-slate-900 mb-5 text-[16px] tracking-tight">Application Processing Fee</h3>
        <div className="flex justify-between items-center mb-4">
          <span className="text-[14px] text-slate-600 font-medium">Application Standard Fee</span>
          <span className="text-[16px] font-bold text-slate-900">₹1,000.00</span>
        </div>
        <div className="border-t border-slate-100 mt-4 pt-4 flex justify-between items-center">
          <span className="text-[13px] font-bold text-slate-500 uppercase tracking-wide">Total Payable</span>
          <span className="text-xl font-black text-blue-600">₹1,000.00</span>
        </div>
      </div>
      {error && <p className="text-[13px] text-red-500 font-medium mb-3 text-center">{error}</p>}
      <button
        onClick={handlePay}
        disabled={paying}
        className="w-full h-12 rounded-xl font-bold text-[14px] text-white transition-all disabled:opacity-60 flex items-center justify-center gap-2"
        style={{ background: "#2563eb", boxShadow: "0 4px 14px rgba(37,99,235,0.3)" }}
      >
        {paying ? <><Loader2 className="w-4 h-4 animate-spin" /> Processing Secure Gateway…</> : <><CreditCard className="w-4 h-4" /> Proceed to Pay via Razorpay</>}
      </button>
      <div className="text-center mt-4 text-[11px] font-medium text-slate-400 flex items-center justify-center gap-1.5">
         <span>Secured by ALIS Enterprise Payment Gateway</span>
      </div>
    </div>
  );
}

export default function ApplicationWizardPage() {
  const [step, setStep] = useState(1);
  const [data, setData] = useState<Record<string, string>>({});
  const [applicantId, setApplicantId] = useState<string | null>(null);
  const [submitted, setSubmitted] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);

  const { mutateAsync: updateApplication, isPending: isUpdating } = useUpdateApplication();
  const { mutateAsync: submitApplication, isPending: isSubmitting } = useSubmitApplication();
  const { mutateAsync: createApplication } = useCreateApplication();

  const canPrev = step > 1;
  const canNext = step < 10;
  const saving = isUpdating || isSubmitting;

  useEffect(() => {
    const stored = sessionStorage.getItem("alis_applicant_id");
    if (stored) {
      setApplicantId(stored);
    } else {
      // Simulate creating a new application ID for the stepper
      createApplication({}).then(res => {
         // Extract ID if the endpoint returns standard Application model, fallback safely.
         const id = (res as any).id || `APP-${Math.floor(Math.random()*1000000)}`;
         setApplicantId(id);
         sessionStorage.setItem("alis_applicant_id", id);
      }).catch(() => {
         // Fallback local ID 
         const id = `APP-${Math.floor(Math.random()*1000000)}`;
         setApplicantId(id);
      });
    }
  }, [createApplication]);

  const handleNext = useCallback(async () => {
    if (!canNext) return;
    if (!applicantId) { setStep((s) => s + 1); return; }

    setSaveError(null);
    try {
      // In the new TanStack architecture, we merge the partial data updates
      await updateApplication({ 
        id: applicantId, 
        data: { 
           // Convert flat Map to partial object structure as required by backend (simplified here to pass all values)
           first_name: data.first_name, 
           last_name: data.last_name,
           program: data.program,
           ...data 
        } as any 
      });

      if (step === 9) {
        await submitApplication(applicantId);
        setSubmitted(true);
      }
      setStep((s) => s + 1);
    } catch (err: unknown) {
      setSaveError(err instanceof Error ? err.message : "Validation failed. Please review your entries.");
    }
  }, [step, canNext, applicantId, data, updateApplication, submitApplication]);

  const handleSaveDraft = useCallback(async () => {
    if (!applicantId) return;
    setSaveError(null);
    try {
      await updateApplication({ 
        id: applicantId, 
        data: { ...data } as any 
      });
    } catch (err: unknown) {
      setSaveError(err instanceof Error ? err.message : "Draft save failed.");
    }
  }, [applicantId, data, updateApplication]);

  if (submitted && step < 10) {
    return (
      <div className="max-w-xl mx-auto px-6 py-20 text-center">
        <div className="w-16 h-16 rounded-full bg-emerald-100 flex items-center justify-center mx-auto mb-5 shadow-sm">
          <CheckCircle className="w-8 h-8 text-emerald-500" />
        </div>
        <h2 className="text-2xl font-bold text-slate-900 mb-2 tracking-tight">Application Submitted Successfully</h2>
        <p className="text-[14px] text-slate-500 max-w-sm mx-auto leading-relaxed">
          Your profile has been locked for pre-processing. Please proceed to application fee payment to finalize your intake.
        </p>
        <button onClick={() => setStep(10)} className="mt-8 px-6 py-2.5 bg-blue-600 text-white rounded-xl font-semibold shadow-md hover:bg-blue-700 transition">
          Proceed to Payment
        </button>
      </div>
    );
  }

  return (
    <div className="max-w-[1000px] mx-auto px-6 py-12">
      <div className="mb-10 text-center">
        <h1 className="text-3xl font-bold text-slate-900 mb-2 tracking-tight">
          Admissions Intake 2025
        </h1>
        <p className="text-[14px] font-medium text-slate-500 flex items-center justify-center gap-2">
          Step {step} of 10
          <span className="w-1 h-1 rounded-full bg-slate-300" />
          {saving ? <span className="text-blue-500 animate-pulse">Syncing…</span> : "Securely Drafted"}
        </p>
        <div className="max-w-md mx-auto mt-4">
          <Progress value={(step / 10) * 100} className="h-1.5" />
        </div>
      </div>

      <div className="flex gap-12">
        {/* Left Side: Ark UI Stepper */}
        <div className="w-64 flex-shrink-0">
          <Stepper count={10} step={step} onStepChange={(details) => setStep(details.step)} orientation="vertical" className="w-full relative h-[600px] flex gap-0">
             <StepperList className="flex flex-col justify-start items-start gap-0 w-full h-full relative">
                {STEPS.map((s, idx) => (
                  <StepperItem
                    key={s.n}
                    index={idx}
                    className="relative flex flex-col items-start w-full group"
                  >
                    <StepperTrigger className="w-full flex items-center justify-start gap-4 text-left rounded-xl p-3 hover:bg-slate-50 transition-colors">
                      <StepperIndicator className="w-8 h-8 rounded-full border-2 flex items-center justify-center shrink-0 z-10 transition-all font-bold text-[12px]" />
                      <div className="flex-1 min-w-0">
                        <span className="text-[13px] font-semibold text-slate-700 group-data-[complete]:text-blue-600 group-data-[current]:text-blue-600 group-data-[incomplete]:text-slate-400 block truncate">
                          {s.title}
                        </span>
                        <span className="text-[10px] font-medium text-slate-400 group-data-[complete]:text-blue-400 uppercase tracking-widest">
                          Section 0{s.n}
                        </span>
                      </div>
                    </StepperTrigger>
                    {/* Vertical Line via Ark */}
                    <StepperSeparator className="absolute left-[26px] top-11 bottom-[-10px] w-0.5 h-auto mx-0 my-0" />
                  </StepperItem>
                ))}
            </StepperList>
          </Stepper>
        </div>

        {/* Right Side: Form content */}
        <div className="flex-1 max-w-xl">
          <div className="portal-card p-8 mb-6 border border-slate-200 shadow-[0_4px_24px_-8px_rgba(0,0,0,0.05)] rounded-2xl bg-white min-h-[460px]">
            <div className="flex items-center gap-3 mb-8 pb-4 border-b border-slate-100">
               <div className="w-10 h-10 rounded-full bg-blue-50 text-blue-600 flex items-center justify-center font-bold text-lg">
                  {step}
               </div>
               <div>
                  <h2 className="text-xl font-bold text-slate-900 tracking-tight">
                    {STEPS[step - 1].title}
                  </h2>
                  <p className="text-[12px] text-slate-500 font-medium">Please enter your true and verified credentials.</p>
               </div>
            </div>
            
            <div className="mb-4">
              {step === 1 && <Step1 data={data} setData={setData} />}
              {step === 6 && <Step6 data={data} setData={setData} />}
              {step === 9 && <ReviewStep data={data} />}
              {step === 10 && <PaymentStep applicantId={applicantId ?? ""} />}
              {![1, 6, 9, 10].includes(step) && <GenericStep stepNum={step} data={data} setData={setData} />}
            </div>
          </div>

          {saveError && (
            <div className="p-3 mb-5 bg-red-50 border border-red-200 text-red-600 rounded-xl text-[13px] font-medium flex items-center gap-2">
              <span className="w-1.5 h-1.5 rounded-full bg-red-500" />
              {saveError}
            </div>
          )}

          {/* Navigation */}
          {step < 10 && (
            <div className="flex items-center justify-between pt-2">
              <button
                onClick={() => canPrev && setStep(step - 1)}
                disabled={!canPrev || saving}
                className="flex items-center gap-2 px-5 py-2.5 rounded-xl text-[13px] font-bold border border-slate-200 text-slate-600 hover:bg-slate-50 hover:text-slate-900 disabled:opacity-40 transition-all shadow-sm"
              >
                <ArrowLeft className="w-4 h-4" /> Prev
              </button>
              
              <button
                onClick={handleSaveDraft}
                disabled={saving || !applicantId}
                className="flex items-center gap-1.5 text-[12px] font-semibold text-slate-400 hover:text-blue-500 transition-colors disabled:opacity-40"
              >
                {saving ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Save className="w-3.5 h-3.5" />}
                Auto-save
              </button>
              
              <button
                onClick={handleNext}
                disabled={saving}
                className="flex items-center gap-2 px-6 py-2.5 rounded-xl text-[14px] font-bold text-white transition-all disabled:opacity-60 shadow-md hover:shadow-lg hover:-translate-y-0.5 active:translate-y-0"
                style={{ background: step === 9 ? "#059669" : "#2563eb" }}
              >
                {saving ? <Loader2 className="w-4 h-4 animate-spin" /> : null}
                {step === 9 ? "Lock & Submit" : "Continue"} {!saving && step !== 9 && <ArrowRight className="w-4 h-4" />}
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
