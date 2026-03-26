import { useState, FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { Loader2, Sparkles } from "lucide-react";
import { useAuthStore } from "@/store/authStore";
import { authService } from "@/services/auth";

export default function LoginPage() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [tenantId, setTenantId] = useState(
    (import.meta.env.VITE_TENANT_ID as string | undefined) || ""
  );
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const { setAuth } = useAuthStore();
  const navigate = useNavigate();

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      const data = await authService.login(email, password, tenantId || undefined);
      setAuth(data.user, data.access_token);
      navigate("/admissions");
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Invalid credentials");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div
      className="min-h-screen flex"
      style={{
        background: "var(--color-bg)",
        backgroundImage:
          "radial-gradient(ellipse 80% 60% at 10% 0%, rgba(129,140,248,0.07) 0%, transparent 60%), radial-gradient(ellipse 60% 50% at 90% 100%, rgba(167,139,250,0.07) 0%, transparent 60%)",
      }}
    >
      {/* Left brand panel */}
      <div
        className="hidden lg:flex flex-col justify-between w-[480px] flex-shrink-0 p-12"
        style={{
          borderRight: "1px solid rgba(255,255,255,0.06)",
          background: "rgba(129,140,248,0.025)",
        }}
      >
        <div>
          <div className="flex items-center gap-3 mb-16">
            <div
              className="w-10 h-10 rounded-xl flex items-center justify-center font-bold text-lg"
              style={{
                background: "rgba(129,140,248,0.15)",
                border: "1px solid rgba(129,140,248,0.3)",
                color: "#818cf8",
                fontFamily: "var(--font-family-sans)",
                boxShadow: "0 0 24px rgba(129,140,248,0.15)",
              }}
            >
              A
            </div>
            <div>
              <div className="text-[15px] font-semibold" style={{ fontFamily: "var(--font-family-sans)", color: "#e2e8f0" }}>
                ALIS
              </div>
              <div className="text-[10px] uppercase tracking-widest" style={{ color: "#475569" }}>
                Institutional OS
              </div>
            </div>
          </div>

          <div className="space-y-6">
            <h1
              className="text-4xl font-bold leading-tight"
              style={{ fontFamily: "var(--font-family-sans)", color: "#e2e8f0", letterSpacing: "-0.03em" }}
            >
              Autonomous
              <br />
              Institutional
              <br />
              Intelligence.
            </h1>
            <p className="text-[14px] leading-relaxed" style={{ color: "#64748b" }}>
              AI proposes. Rules enforce.
              <br />
              Humans approve the important things.
            </p>
          </div>
        </div>

        <div className="space-y-4">
          {[
            { metric: "904", label: "Tests passing" },
            { metric: "13", label: "Backend epics complete" },
            { metric: "40+", label: "Admissions workflow tables" },
          ].map((item) => (
            <div key={item.label} className="flex items-baseline gap-3">
              <span
                className="text-2xl font-bold"
                style={{ fontFamily: "var(--font-family-sans)", color: "#818cf8" }}
              >
                {item.metric}
              </span>
              <span className="text-[12px]" style={{ color: "#475569" }}>
                {item.label}
              </span>
            </div>
          ))}
        </div>
      </div>

      {/* Right login form */}
      <div className="flex-1 flex items-center justify-center px-8">
        <div className="w-full max-w-sm">
          <div className="mb-8">
            <div className="flex items-center gap-2 mb-3">
              <Sparkles className="w-4 h-4" style={{ color: "#818cf8" }} />
              <span className="text-[10px] uppercase tracking-[0.15em] font-semibold" style={{ color: "#818cf8" }}>
                Staff Portal
              </span>
            </div>
            <h2
              className="text-2xl font-bold"
              style={{ fontFamily: "var(--font-family-sans)", color: "#e2e8f0", letterSpacing: "-0.02em" }}
            >
              Sign in
            </h2>
          </div>

          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label className="block text-[10px] font-semibold uppercase tracking-wider mb-1.5" style={{ color: "#64748b" }}>
                Institution ID
              </label>
              <input
                type="text"
                value={tenantId}
                onChange={(e) => setTenantId(e.target.value)}
                placeholder="e.g. woxsen"
                className="w-full h-11 px-4 rounded-xl outline-none text-[13px] transition-all"
                style={{
                  background: "rgba(255,255,255,0.04)",
                  border: "1px solid rgba(255,255,255,0.08)",
                  color: "#e2e8f0",
                  fontFamily: "var(--font-family-mono)",
                }}
                onFocus={(e) => { e.currentTarget.style.borderColor = "rgba(129,140,248,0.4)"; e.currentTarget.style.boxShadow = "0 0 0 3px rgba(129,140,248,0.06)"; }}
                onBlur={(e) => { e.currentTarget.style.borderColor = "rgba(255,255,255,0.08)"; e.currentTarget.style.boxShadow = "none"; }}
              />
            </div>
            <div>
              <label className="block text-[10px] font-semibold uppercase tracking-wider mb-1.5" style={{ color: "#64748b" }}>
                Email
              </label>
              <input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
                placeholder="you@institution.edu"
                className="w-full h-11 px-4 rounded-xl outline-none text-[13px] transition-all"
                style={{
                  background: "rgba(255,255,255,0.04)",
                  border: "1px solid rgba(255,255,255,0.08)",
                  color: "#e2e8f0",
                  fontFamily: "var(--font-family-mono)",
                }}
                onFocus={(e) => { e.currentTarget.style.borderColor = "rgba(129,140,248,0.4)"; e.currentTarget.style.boxShadow = "0 0 0 3px rgba(129,140,248,0.06)"; }}
                onBlur={(e) => { e.currentTarget.style.borderColor = "rgba(255,255,255,0.08)"; e.currentTarget.style.boxShadow = "none"; }}
              />
            </div>

            <div>
              <label className="block text-[10px] font-semibold uppercase tracking-wider mb-1.5" style={{ color: "#64748b" }}>
                Password
              </label>
              <input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
                placeholder="••••••••"
                className="w-full h-11 px-4 rounded-xl outline-none text-[13px] transition-all"
                style={{
                  background: "rgba(255,255,255,0.04)",
                  border: "1px solid rgba(255,255,255,0.08)",
                  color: "#e2e8f0",
                  fontFamily: "var(--font-family-mono)",
                }}
                onFocus={(e) => { e.currentTarget.style.borderColor = "rgba(129,140,248,0.4)"; e.currentTarget.style.boxShadow = "0 0 0 3px rgba(129,140,248,0.06)"; }}
                onBlur={(e) => { e.currentTarget.style.borderColor = "rgba(255,255,255,0.08)"; e.currentTarget.style.boxShadow = "none"; }}
              />
            </div>

            {error && (
              <div className="px-4 py-3 rounded-lg text-[12px]"
                style={{ background: "rgba(251,113,133,0.08)", border: "1px solid rgba(251,113,133,0.2)", color: "#fb7185" }}>
                {error}
              </div>
            )}

            <button
              type="submit"
              disabled={loading}
              className="w-full h-11 rounded-xl flex items-center justify-center gap-2 font-semibold text-[13px] transition-all"
              style={{
                background: "rgba(129,140,248,0.15)",
                border: "1px solid rgba(129,140,248,0.3)",
                color: "#818cf8",
                boxShadow: loading ? "none" : "0 0 24px rgba(129,140,248,0.12)",
              }}
              onMouseEnter={(e) => { if (!loading) e.currentTarget.style.background = "rgba(129,140,248,0.22)"; }}
              onMouseLeave={(e) => { e.currentTarget.style.background = "rgba(129,140,248,0.15)"; }}
            >
              {loading ? (
                <Loader2 className="w-4 h-4 animate-spin" />
              ) : (
                "Sign in to ALIS"
              )}
            </button>
          </form>

          <p className="text-[10px] text-center mt-6" style={{ color: "#334155" }}>
            Staff access only · Contact IT for credentials
          </p>
        </div>
      </div>
    </div>
  );
}
