/**
 * GuardianPortalPage — E16 Parent/Guardian Portal
 * Route: /guardian (PUBLIC — no ALIS shell, standalone page)
 *
 * OTP-only auth flow → single-page snapshot view
 * Student snapshot (attendance %, pending dues, upcoming exams)
 * Communication history (notification feed)
 * Consent management (DPDP: view + revoke consents)
 */

import { useState, useEffect } from 'react';
import { alisApi } from '@/lib/alis-api';

// ─── Types ────────────────────────────────────────────────────────────────────

type Step = 'phone' | 'otp' | 'dashboard';

interface StudentInfo {
  student_id: string;
  name: string;
  enrollment_number: string;
}

interface GuardianSession {
  token: string;
  student: StudentInfo;
  tenant_id: string;
}

interface ConsentItem {
  purpose: string;
  label?: string;
  status: 'GRANTED' | 'WITHDRAWN' | 'active' | 'revoked';
}

interface NotificationItem {
  id: string;
  title?: string;
  body?: string;
  message?: string;
  created_at?: string;
}

interface AttendanceSummary {
  overall_pct?: number;
  attendance_percentage?: number;
}

interface InvoiceItem {
  total_amount?: number;
  due_date?: string;
  status?: string;
}

interface HallTicket {
  exam_date?: string;
  course_code?: string;
  course_name?: string;
}

// ─── Color tokens ─────────────────────────────────────────────────────────────

const C = {
  bg:        '#0E1020',
  surface:   '#11131F',
  elevated:  '#1A1D2E',
  border:    '#1E2235',
  text:      '#C9D1E9',
  muted:     '#7B82A8',
  teal:      '#1D9E75',
  purple:    '#5D5FEF',
  amber:     '#EF9F27',
  red:       '#E24B4A',
  green:     '#22C55E',
} as const;

// ─── Sub-components ───────────────────────────────────────────────────────────

function ALISLogo() {
  return (
    <div
      style={{
        width: 48, height: 48, borderRadius: '50%', background: C.teal,
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        fontSize: 22, fontWeight: 800, color: '#fff', letterSpacing: '-1px', flexShrink: 0,
      }}
    >
      A
    </div>
  );
}

function SectionTitle({ children }: { children: React.ReactNode }) {
  return (
    <h2 style={{ fontSize: 15, fontWeight: 700, color: C.text, margin: '0 0 14px 0', letterSpacing: 0.2 }}>
      {children}
    </h2>
  );
}

// ─── Step 1: Phone entry ──────────────────────────────────────────────────────

function PhoneStep({
  phone, setPhone, onSubmit, loading,
}: {
  phone: string; setPhone: (v: string) => void; onSubmit: () => void; loading: boolean;
}) {
  return (
    <div style={{
      maxWidth: 380, margin: '0 auto', background: C.surface, borderRadius: 16,
      border: `1px solid ${C.border}`, padding: '40px 36px',
      display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 24,
    }}>
      <ALISLogo />
      <div style={{ textAlign: 'center' }}>
        <h1 style={{ fontSize: 22, fontWeight: 700, color: C.text, margin: '0 0 8px 0' }}>Guardian Portal</h1>
        <p style={{ fontSize: 14, color: C.muted, margin: 0, lineHeight: 1.5 }}>
          Enter your registered mobile number to receive OTP
        </p>
      </div>
      <div style={{ width: '100%', display: 'flex', flexDirection: 'column', gap: 12 }}>
        <input
          type="tel" placeholder="+91 98765 43210" value={phone}
          onChange={(e) => setPhone(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && !loading && onSubmit()}
          style={{
            width: '100%', boxSizing: 'border-box', padding: '12px 16px', borderRadius: 8,
            border: `1px solid ${C.border}`, background: C.elevated, color: C.text,
            fontSize: 15, outline: 'none', fontFamily: 'inherit',
          }}
        />
        <button
          onClick={onSubmit}
          disabled={loading || phone.trim().length < 10}
          style={{
            width: '100%', padding: '12px', borderRadius: 8, border: 'none',
            background: loading || phone.trim().length < 10 ? C.elevated : C.teal,
            color: loading || phone.trim().length < 10 ? C.muted : '#fff',
            fontSize: 15, fontWeight: 600,
            cursor: loading || phone.trim().length < 10 ? 'not-allowed' : 'pointer',
            transition: 'background 0.2s', fontFamily: 'inherit',
          }}
        >
          {loading ? 'Sending…' : 'Send OTP'}
        </button>
      </div>
    </div>
  );
}

// ─── Step 2: OTP entry ────────────────────────────────────────────────────────

function OTPStep({
  phone, otp, setOtp, onVerify, onResend, loading, error,
}: {
  phone: string; otp: string; setOtp: (v: string) => void;
  onVerify: () => void; onResend: () => void; loading: boolean; error: string | null;
}) {
  return (
    <div style={{
      maxWidth: 380, margin: '0 auto', background: C.surface, borderRadius: 16,
      border: `1px solid ${C.border}`, padding: '40px 36px',
      display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 24,
    }}>
      <ALISLogo />
      <div style={{ textAlign: 'center' }}>
        <h1 style={{ fontSize: 22, fontWeight: 700, color: C.text, margin: '0 0 8px 0' }}>Verify OTP</h1>
        <p style={{ fontSize: 14, color: C.muted, margin: 0, lineHeight: 1.5 }}>
          OTP sent to <span style={{ color: C.text, fontWeight: 600 }}>{phone}</span>
        </p>
      </div>
      <div style={{ width: '100%', display: 'flex', flexDirection: 'column', gap: 12 }}>
        <input
          type="text" inputMode="numeric" maxLength={6} placeholder="Enter 6-digit OTP"
          value={otp} onChange={(e) => setOtp(e.target.value.replace(/\D/g, '').slice(0, 6))}
          onKeyDown={(e) => e.key === 'Enter' && !loading && onVerify()}
          style={{
            width: '100%', boxSizing: 'border-box', padding: '12px 16px', borderRadius: 8,
            border: `1px solid ${error ? C.red : C.border}`, background: C.elevated, color: C.text,
            fontSize: 22, letterSpacing: 8, textAlign: 'center', outline: 'none', fontFamily: 'monospace',
          }}
          autoFocus
        />
        {error && <p style={{ fontSize: 13, color: C.red, margin: 0, textAlign: 'center' }}>{error}</p>}
        <button
          onClick={onVerify} disabled={loading || otp.length !== 6}
          style={{
            width: '100%', padding: '12px', borderRadius: 8, border: 'none',
            background: loading || otp.length !== 6 ? C.elevated : C.teal,
            color: loading || otp.length !== 6 ? C.muted : '#fff',
            fontSize: 15, fontWeight: 600,
            cursor: loading || otp.length !== 6 ? 'not-allowed' : 'pointer',
            transition: 'background 0.2s', fontFamily: 'inherit',
          }}
        >
          {loading ? 'Verifying…' : 'Verify OTP'}
        </button>
        <button onClick={onResend} style={{
          background: 'none', border: 'none', color: C.teal, fontSize: 14,
          cursor: 'pointer', textAlign: 'center', padding: '4px', fontFamily: 'inherit',
        }}>
          Resend OTP
        </button>
      </div>
    </div>
  );
}

// ─── Step 3: Dashboard ────────────────────────────────────────────────────────

function Dashboard({ session, onLogout }: { session: GuardianSession; onLogout: () => void }) {
  const { student, token, tenant_id } = session;

  const [attendance, setAttendance] = useState<AttendanceSummary | null>(null);
  const [invoices, setInvoices] = useState<InvoiceItem[]>([]);
  const [hallTickets, setHallTickets] = useState<HallTicket[]>([]);
  const [notifications, setNotifications] = useState<NotificationItem[]>([]);
  const [consents, setConsents] = useState<ConsentItem[]>([]);
  const [consentOpen, setConsentOpen] = useState(false);

  useEffect(() => {
    const headers = { Authorization: `Bearer ${token}`, 'X-Tenant-ID': tenant_id };

    alisApi.get<AttendanceSummary>(`/academics/attendance/student/${student.student_id}`, { headers })
      .then(setAttendance).catch(() => null);

    alisApi.get<{ invoices: InvoiceItem[] }>(`/finance/invoices/student/${student.student_id}`, { headers })
      .then((r) => setInvoices(r.invoices ?? [])).catch(() => null);

    alisApi.get<{ hall_tickets: HallTicket[] }>(`/examinations/hall-tickets/student/${student.student_id}`, { headers })
      .then((r) => setHallTickets(r.hall_tickets ?? [])).catch(() => null);

    alisApi.get<{ notifications: NotificationItem[] }>(`/communication/parent/${student.student_id}/notifications`, { headers })
      .then((r) => setNotifications(r.notifications ?? [])).catch(() => null);

    alisApi.get<{ consents: ConsentItem[] }>('/consent/', { headers })
      .then((r) => setConsents(r.consents ?? [])).catch(() => null);
  }, [student.student_id, token, tenant_id]);

  const attendancePct = attendance?.overall_pct ?? attendance?.attendance_percentage ?? null;
  const attendanceColor = attendancePct === null ? C.muted : attendancePct < 75 ? C.amber : C.teal;

  const overdueInvoices = invoices.filter((i) => i.status === 'OVERDUE' || i.status === 'DUE');
  const totalDues = overdueInvoices.reduce((sum, i) => sum + (i.total_amount ?? 0), 0);
  const nextExam = hallTickets[0] ?? null;

  const handleRevokeConsent = async (purpose: string) => {
    try {
      await alisApi.post('/consent/withdraw', { purposes: [purpose] }, {
        headers: { Authorization: `Bearer ${token}`, 'X-Tenant-ID': tenant_id },
      });
      setConsents((prev) => prev.map((c) => c.purpose === purpose ? { ...c, status: 'WITHDRAWN' } : c));
    } catch {
      // silently ignore — consent revoke failures shown on reload
    }
  };

  return (
    <div style={{ minHeight: '100vh', background: C.bg, display: 'flex', flexDirection: 'column' }}>
      {/* Top bar */}
      <header style={{
        background: C.surface, borderBottom: `1px solid ${C.border}`,
        padding: '0 24px', height: 60, display: 'flex', alignItems: 'center',
        justifyContent: 'space-between', flexShrink: 0,
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <ALISLogo />
          <div>
            <div style={{ fontSize: 15, fontWeight: 700, color: C.text }}>Guardian Portal</div>
            <div style={{ fontSize: 12, color: C.muted }}>Ward: {student.name}</div>
          </div>
        </div>
        <button onClick={onLogout} style={{
          background: 'none', border: `1px solid ${C.border}`, borderRadius: 8,
          color: C.muted, padding: '6px 14px', cursor: 'pointer', fontSize: 13,
          display: 'flex', alignItems: 'center', gap: 6, fontFamily: 'inherit',
        }}>
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4" />
            <polyline points="16 17 21 12 16 7" />
            <line x1="21" y1="12" x2="9" y2="12" />
          </svg>
          Log out
        </button>
      </header>

      {/* Body */}
      <main style={{
        flex: 1, maxWidth: 860, margin: '0 auto', width: '100%',
        padding: '28px 24px', display: 'flex', flexDirection: 'column', gap: 28,
      }}>
        {/* ── Student Snapshot ── */}
        <section>
          <SectionTitle>Student Snapshot</SectionTitle>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: 16 }}>
            {/* Attendance */}
            <SnapshotCard
              label="Attendance"
              value={attendancePct !== null ? `${attendancePct}%` : '—'}
              valueColor={attendanceColor}
              sub={attendancePct !== null ? (attendancePct < 75 ? 'Below 75% threshold' : 'Within limit') : 'Loading…'}
              subColor={attendanceColor}
            />
            {/* Pending Dues */}
            <SnapshotCard
              label="Pending Dues"
              value={totalDues > 0 ? `₹${totalDues.toLocaleString('en-IN')}` : '₹0'}
              valueColor={totalDues > 0 ? C.red : C.teal}
              sub={overdueInvoices[0]?.due_date ? `Due: ${new Date(overdueInvoices[0].due_date).toLocaleDateString('en-IN')}` : 'No pending dues'}
              subColor={totalDues > 0 ? C.red : C.muted}
              badge={totalDues > 0 ? 'Overdue' : undefined}
              badgeColor={C.red}
            />
            {/* Next Exam */}
            <SnapshotCard
              label="Next Exam"
              value={nextExam?.exam_date ? new Date(nextExam.exam_date).toLocaleDateString('en-IN', { day: '2-digit', month: 'short' }) : '—'}
              valueColor={C.purple}
              sub={nextExam ? `${nextExam.course_name ?? nextExam.course_code ?? ''}` : 'No upcoming exams'}
              subColor={C.muted}
            />
          </div>
        </section>

        {/* ── Upcoming Exams ── */}
        {hallTickets.length > 0 && (
          <section>
            <SectionTitle>Upcoming Exams</SectionTitle>
            <div style={{ background: C.surface, border: `1px solid ${C.border}`, borderRadius: 12, overflow: 'hidden' }}>
              {hallTickets.slice(0, 5).map((exam, i) => (
                <div key={i} style={{
                  display: 'flex', alignItems: 'center', gap: 16, padding: '14px 20px',
                  borderBottom: i < Math.min(hallTickets.length, 5) - 1 ? `1px solid ${C.border}` : 'none',
                }}>
                  <div style={{
                    minWidth: 68, fontSize: 13, fontWeight: 700, color: C.purple,
                    background: `${C.purple}18`, borderRadius: 6, padding: '4px 8px', textAlign: 'center',
                  }}>
                    {exam.exam_date ? new Date(exam.exam_date).toLocaleDateString('en-IN', { day: '2-digit', month: 'short' }) : '—'}
                  </div>
                  <div style={{ fontSize: 13, fontWeight: 600, color: C.muted, minWidth: 52 }}>{exam.course_code}</div>
                  <div style={{ fontSize: 14, color: C.text }}>{exam.course_name}</div>
                </div>
              ))}
            </div>
          </section>
        )}

        {/* ── Communication History ── */}
        {notifications.length > 0 && (
          <section>
            <SectionTitle>Communication History</SectionTitle>
            <div style={{
              background: C.surface, border: `1px solid ${C.border}`, borderRadius: 12,
              padding: '16px 20px', display: 'flex', flexDirection: 'column', gap: 12,
            }}>
              <div style={{
                display: 'flex', alignItems: 'center', gap: 8,
                paddingBottom: 10, borderBottom: `1px solid ${C.border}`,
              }}>
                <span style={{ fontSize: 12, color: C.muted, fontWeight: 600 }}>ALIS Notifications</span>
              </div>
              {notifications.slice(0, 6).map((msg) => (
                <div key={msg.id} style={{
                  alignSelf: 'flex-start', maxWidth: '80%', background: C.elevated,
                  borderRadius: '4px 12px 12px 12px', padding: '10px 14px',
                }}>
                  <p style={{ margin: 0, fontSize: 13, color: C.text, lineHeight: 1.55 }}>
                    {msg.body ?? msg.message ?? msg.title ?? ''}
                  </p>
                  {msg.created_at && (
                    <div style={{ marginTop: 4, fontSize: 11, color: C.muted, textAlign: 'right' }}>
                      {new Date(msg.created_at).toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit' })}
                    </div>
                  )}
                </div>
              ))}
            </div>
          </section>
        )}

        {/* ── DPDP Consent Management ── */}
        <section>
          <button onClick={() => setConsentOpen((v) => !v)} style={{
            width: '100%', background: C.surface, border: `1px solid ${C.border}`,
            borderRadius: consentOpen ? '12px 12px 0 0' : 12, padding: '14px 20px',
            display: 'flex', alignItems: 'center', justifyContent: 'space-between',
            cursor: 'pointer', fontFamily: 'inherit', color: C.text,
          }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke={C.teal} strokeWidth="2">
                <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
              </svg>
              <span style={{ fontSize: 15, fontWeight: 700 }}>Consent Management</span>
              <span style={{
                fontSize: 11, background: `${C.teal}20`, color: C.teal,
                padding: '2px 8px', borderRadius: 20, fontWeight: 600,
              }}>DPDP</span>
            </div>
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke={C.muted} strokeWidth="2"
              style={{ transform: consentOpen ? 'rotate(180deg)' : 'rotate(0)', transition: 'transform 0.2s' }}>
              <polyline points="6 9 12 15 18 9" />
            </svg>
          </button>

          {consentOpen && (
            <div style={{
              background: C.surface, border: `1px solid ${C.border}`,
              borderTop: 'none', borderRadius: '0 0 12px 12px', overflow: 'hidden',
            }}>
              {consents.length === 0 && (
                <div style={{ padding: '20px', fontSize: 13, color: C.muted, textAlign: 'center' }}>
                  No consent records found.
                </div>
              )}
              {consents.map((c, i) => {
                const isActive = c.status === 'GRANTED' || c.status === 'active';
                return (
                  <div key={c.purpose} style={{
                    display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                    padding: '14px 20px',
                    borderBottom: i < consents.length - 1 ? `1px solid ${C.border}` : 'none',
                    gap: 12,
                  }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 10, flex: 1 }}>
                      <div style={{ width: 8, height: 8, borderRadius: '50%', background: isActive ? C.green : C.red, flexShrink: 0 }} />
                      <span style={{ fontSize: 14, color: C.text }}>{c.label ?? c.purpose}</span>
                    </div>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexShrink: 0 }}>
                      <span style={{
                        fontSize: 12, fontWeight: 600,
                        color: isActive ? C.green : C.red,
                        background: isActive ? `${C.green}18` : `${C.red}18`,
                        padding: '3px 10px', borderRadius: 20,
                      }}>
                        {isActive ? 'Active' : 'Withdrawn'}
                      </span>
                      {isActive && (
                        <button onClick={() => handleRevokeConsent(c.purpose)} style={{
                          background: 'none', border: `1px solid ${C.red}`, borderRadius: 6,
                          color: C.red, fontSize: 12, fontWeight: 600,
                          padding: '4px 12px', cursor: 'pointer', fontFamily: 'inherit',
                        }}>
                          Revoke
                        </button>
                      )}
                    </div>
                  </div>
                );
              })}
              <div style={{
                padding: '12px 20px', borderTop: `1px solid ${C.border}`,
                fontSize: 12, color: C.muted, lineHeight: 1.5,
              }}>
                Consent managed under the Digital Personal Data Protection Act (DPDP), 2023.
                Revoked consents take effect immediately and data processing will cease within 72 hours.
              </div>
            </div>
          )}
        </section>
      </main>
    </div>
  );
}

// ─── Snapshot card helper ─────────────────────────────────────────────────────

function SnapshotCard({
  label, value, valueColor, sub, subColor, badge, badgeColor,
}: {
  label: string; value: string; valueColor: string;
  sub: string; subColor: string; badge?: string; badgeColor?: string;
}) {
  return (
    <div style={{
      background: C.surface, border: `1px solid ${C.border}`, borderRadius: 12,
      padding: '20px 20px 18px', display: 'flex', flexDirection: 'column', gap: 10,
    }}>
      <span style={{ fontSize: 13, color: C.muted, fontWeight: 600 }}>{label}</span>
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 10 }}>
        <span style={{ fontSize: 28, fontWeight: 800, color: valueColor, lineHeight: 1 }}>{value}</span>
        {badge && badgeColor && (
          <span style={{
            fontSize: 11, fontWeight: 700, color: badgeColor,
            background: `${badgeColor}20`, padding: '2px 8px', borderRadius: 20,
          }}>
            {badge}
          </span>
        )}
      </div>
      <span style={{ fontSize: 12, color: subColor }}>{sub}</span>
    </div>
  );
}

// ─── Root component ───────────────────────────────────────────────────────────

export function GuardianPortalPage() {
  const [step, setStep] = useState<Step>('phone');
  const [phone, setPhone] = useState('');
  const [otp, setOtp] = useState('');
  const [loading, setLoading] = useState(false);
  const [otpError, setOtpError] = useState<string | null>(null);
  const [guardianSession, setGuardianSession] = useState<GuardianSession | null>(null);

  // Restore session from localStorage if still valid
  useEffect(() => {
    const stored = localStorage.getItem('alis_guardian_session');
    if (stored) {
      try {
        setGuardianSession(JSON.parse(stored));
        setStep('dashboard');
      } catch {
        localStorage.removeItem('alis_guardian_session');
      }
    }
  }, []);

  const handleSendOtp = async () => {
    setLoading(true);
    setOtpError(null);
    try {
      const tenantId = localStorage.getItem('tenant_id') ?? 'demo';
      await alisApi.post('/auth/guardian/request-otp', { phone, tenant_id: tenantId });
      setStep('otp');
    } catch (err: unknown) {
      setOtpError(err instanceof Error ? err.message : 'Failed to send OTP.');
    } finally {
      setLoading(false);
    }
  };

  const handleVerifyOtp = async () => {
    setLoading(true);
    setOtpError(null);
    try {
      const tenantId = localStorage.getItem('tenant_id') ?? 'demo';
      const result = await alisApi.post<GuardianSession & { token: string; student: StudentInfo }>(
        '/auth/guardian/verify-otp',
        { phone, otp, tenant_id: tenantId }
      );
      const session: GuardianSession = {
        token: result.token,
        student: result.student,
        tenant_id: result.tenant_id ?? tenantId,
      };
      setGuardianSession(session);
      localStorage.setItem('alis_guardian_session', JSON.stringify(session));
      setStep('dashboard');
    } catch (err: unknown) {
      setOtpError(err instanceof Error ? err.message : 'Invalid OTP. Please try again.');
    } finally {
      setLoading(false);
    }
  };

  const handleResend = () => {
    setOtp('');
    setOtpError(null);
    handleSendOtp();
  };

  const handleLogout = () => {
    localStorage.removeItem('alis_guardian_session');
    setGuardianSession(null);
    setStep('phone');
    setPhone('');
    setOtp('');
  };

  if (step === 'dashboard' && guardianSession) {
    return <Dashboard session={guardianSession} onLogout={handleLogout} />;
  }

  return (
    <div style={{
      minHeight: '100vh', background: C.bg,
      display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 24,
    }}>
      {step === 'phone' ? (
        <PhoneStep phone={phone} setPhone={setPhone} onSubmit={handleSendOtp} loading={loading} />
      ) : (
        <OTPStep
          phone={phone} otp={otp} setOtp={setOtp}
          onVerify={handleVerifyOtp} onResend={handleResend}
          loading={loading} error={otpError}
        />
      )}
    </div>
  );
}
