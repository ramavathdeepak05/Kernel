import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { CheckCircle, Circle, Clock, AlertTriangle, ArrowRight, Loader2 } from "lucide-react";
import { STATUS_LABELS, STATUS_COLORS } from "@/types/admissions";
import { cn } from "@/lib/utils";
import { alisApi } from "@/lib/alis-api";

const PIPELINE_STAGES = [
  { key: "SUBMITTED", label: "Application Submitted", icon: CheckCircle },
  { key: "DOCUMENTS_VERIFIED", label: "Documents Verified", icon: CheckCircle },
  { key: "ELIGIBLE", label: "Eligibility Cleared", icon: CheckCircle },
  { key: "ASSESSMENT_COMPLETE", label: "Assessment Complete", icon: CheckCircle },
  { key: "MERIT_LIST_GENERATED", label: "Merit List Published", icon: CheckCircle },
  { key: "OFFER_ISSUED", label: "Offer Letter Issued", icon: CheckCircle },
  { key: "SEAT_CONFIRMED", label: "Seat Confirmed", icon: CheckCircle },
  { key: "ENROLLED", label: "Enrolled", icon: CheckCircle },
];

const STAGE_ORDER = PIPELINE_STAGES.map((s) => s.key);

interface Application {
  applicant_id: string;
  application_id?: string;
  status: string;
  applicant_name?: string;
  program_name?: string;
  offer_expiry?: string;
}

export default function ApplicationStatusPage() {
  const [params] = useSearchParams();
  const appId = params.get("id") ?? "";

  const [application, setApplication] = useState<Application | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!appId) {
      setError("No application ID provided.");
      setLoading(false);
      return;
    }
    setLoading(true);
    alisApi
      .get<Application>(`/admissions/applications/${appId}`)
      .then((data) => {
        setApplication(data);
        setError(null);
      })
      .catch((err: Error) => {
        setError(err.message || "Failed to load application.");
      })
      .finally(() => setLoading(false));
  }, [appId]);

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-[300px]">
        <Loader2 className="w-6 h-6 animate-spin text-blue-500" />
      </div>
    );
  }

  if (error || !application) {
    return (
      <div className="max-w-2xl mx-auto px-6 py-12">
        <div className="portal-card p-6 text-center text-slate-500 text-[14px]">
          {error ?? "Application not found."}
        </div>
      </div>
    );
  }

  const currentStatus = application.status;
  const currentStageIdx = STAGE_ORDER.indexOf(currentStatus);
  const displayId = application.application_id ?? appId;
  const displayName = application.applicant_name ?? "—";
  const displayProgram = application.program_name ?? "—";

  return (
    <div className="max-w-2xl mx-auto px-6 py-12">
      {/* Header */}
      <div className="portal-card p-6 mb-6">
        <div className="flex items-start justify-between">
          <div>
            <p className="text-[11px] text-slate-500 mb-1 uppercase tracking-wide font-semibold">Application Status</p>
            <h1 className="text-2xl font-bold text-slate-900" style={{ fontFamily: "var(--font-family-sans)", letterSpacing: "-0.02em" }}>
              {displayId}
            </h1>
            <p className="text-[13px] text-slate-500 mt-1">{displayName} · {displayProgram}</p>
          </div>
          {currentStatus && (
            <span className={cn("status-badge text-[10px]", STATUS_COLORS[currentStatus] ?? "bg-slate-100 text-slate-600")}>
              {STATUS_LABELS[currentStatus] ?? currentStatus}
            </span>
          )}
        </div>
      </div>

      {/* Action required */}
      {currentStatus === "OFFER_ISSUED" && (
        <div className="mb-6 p-5 rounded-xl border border-emerald-200 bg-emerald-50">
          <div className="flex items-start gap-3">
            <div className="w-8 h-8 rounded-full bg-emerald-100 flex items-center justify-center flex-shrink-0">
              <AlertTriangle className="w-4 h-4 text-emerald-600" />
            </div>
            <div className="flex-1">
              <p className="font-semibold text-emerald-800 text-[14px]">Action Required: Accept Your Offer</p>
              <p className="text-[12px] text-emerald-600 mt-1">
                Your offer letter has been issued.
                {application.offer_expiry && (
                  <> Please accept by <strong>{new Date(application.offer_expiry).toLocaleDateString("en-IN")}</strong> to confirm your seat.</>
                )}
              </p>
              <a href={`/apply/offer?id=${displayId}`} className="inline-flex items-center gap-1.5 mt-3 text-[13px] font-semibold text-emerald-700 hover:text-emerald-900 transition-colors">
                View & Accept Offer <ArrowRight className="w-3.5 h-3.5" />
              </a>
            </div>
          </div>
        </div>
      )}

      {/* Pipeline timeline */}
      <div className="portal-card p-6">
        <h3 className="font-bold text-slate-900 mb-6" style={{ fontFamily: "var(--font-family-sans)" }}>
          Application Journey
        </h3>
        <div className="space-y-0">
          {PIPELINE_STAGES.map((stage, idx) => {
            const isDone = idx <= currentStageIdx;
            const isActive = idx === currentStageIdx;
            const isLast = idx === PIPELINE_STAGES.length - 1;
            const Icon = isDone ? CheckCircle : isActive ? Clock : Circle;

            return (
              <div key={stage.key} className="flex gap-4">
                {/* Timeline */}
                <div className="flex flex-col items-center">
                  <div className={cn(
                    "w-7 h-7 rounded-full flex items-center justify-center flex-shrink-0 z-10",
                    isDone && !isActive ? "bg-emerald-100" : isActive ? "bg-blue-100" : "bg-slate-100"
                  )}>
                    <Icon className={cn(
                      "w-4 h-4",
                      isDone && !isActive ? "text-emerald-500" : isActive ? "text-blue-500" : "text-slate-300"
                    )} />
                  </div>
                  {!isLast && (
                    <div className={cn("w-0.5 h-8 mt-1", isDone ? "bg-emerald-200" : "bg-slate-100")} />
                  )}
                </div>

                {/* Content */}
                <div className={cn("pb-6 flex-1", isLast && "pb-0")}>
                  <p className={cn(
                    "text-[13px] font-semibold",
                    isDone && !isActive ? "text-emerald-700" : isActive ? "text-blue-700" : "text-slate-400"
                  )}>
                    {stage.label}
                  </p>
                  {isActive && (
                    <p className="text-[11px] text-blue-500 mt-0.5 font-medium">Current stage</p>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
