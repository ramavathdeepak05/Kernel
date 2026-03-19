/**
 * GuardianPortalPage — E16 Parent/Guardian Portal
 * Route: /guardian (PUBLIC — no ALIS shell, standalone page)
 *
 * OTP-only auth flow → single-page snapshot view
 * Student snapshot (attendance %, pending dues, upcoming exams)
 * Communication history (WhatsApp thread summary)
 * Consent management (DPDP: view + revoke consents)
 */

import { useState } from 'react';

// ─── Types ────────────────────────────────────────────────────────────────────

type Step = 'phone' | 'otp' | 'dashboard';

interface ConsentItem {
  id: string;
  label: string;
  status: 'active' | 'revoked';
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

// ─── Static mock data ─────────────────────────────────────────────────────────

const STUDENT_NAME = 'Arjun Mehta';
const ATTENDANCE_PCT = 74;

const UPCOMING_EXAMS = [
  { date: 'Nov 18', code: 'CS301', name: 'Data Structures' },
  { date: 'Nov 20', code: 'CS302', name: 'DBMS' },
  { date: 'Nov 22', code: 'EC201', name: 'Signals & Systems' },
];

const MESSAGES = [
  {
    id: '1',
    text: 'Your ward Arjun Mehta has an attendance of 74% in CS303. Minimum required is 75%.',
    time: '9:41 AM',
  },
  {
    id: '2',
    text: 'Fee invoice INV-2026-0847 of ₹18,500 is due on March 31.',
    time: '10:15 AM',
  },
  {
    id: '3',
    text: 'Exam hall ticket for Semester 5 has been issued. Download link: alis.edu/hall-ticket/S5',
    time: '11:02 AM',
  },
  {
    id: '4',
    text: 'Offer letter for B.Tech CSE has been accepted.',
    time: '2:30 PM',
  },
];

const INITIAL_CONSENTS: ConsentItem[] = [
  { id: 'c1', label: 'Attendance notifications via WhatsApp', status: 'active' },
  { id: 'c2', label: 'Fee reminders via SMS', status: 'active' },
  { id: 'c3', label: 'Academic result sharing with employer', status: 'revoked' },
  { id: 'c4', label: 'Biometric data processing', status: 'active' },
];

// ─── Sub-components ───────────────────────────────────────────────────────────

function ALISLogo() {
  return (
    <div
      style={{
        width: 48,
        height: 48,
        borderRadius: '50%',
        background: C.teal,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        fontSize: 22,
        fontWeight: 800,
        color: '#fff',
        letterSpacing: '-1px',
        flexShrink: 0,
      }}
    >
      A
    </div>
  );
}

function Divider() {
  return <div style={{ height: 1, background: C.border, margin: '20px 0' }} />;
}

function SectionTitle({ children }: { children: React.ReactNode }) {
  return (
    <h2
      style={{
        fontSize: 15,
        fontWeight: 700,
        color: C.text,
        margin: '0 0 14px 0',
        letterSpacing: 0.2,
      }}
    >
      {children}
    </h2>
  );
}

// ─── Step 1: Phone entry ──────────────────────────────────────────────────────

function PhoneStep({
  phone,
  setPhone,
  onSubmit,
  loading,
}: {
  phone: string;
  setPhone: (v: string) => void;
  onSubmit: () => void;
  loading: boolean;
}) {
  return (
    <div
      style={{
        maxWidth: 380,
        margin: '0 auto',
        background: C.surface,
        borderRadius: 16,
        border: `1px solid ${C.border}`,
        padding: '40px 36px',
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        gap: 24,
      }}
    >
      <ALISLogo />

      <div style={{ textAlign: 'center' }}>
        <h1 style={{ fontSize: 22, fontWeight: 700, color: C.text, margin: '0 0 8px 0' }}>
          Guardian Portal
        </h1>
        <p style={{ fontSize: 14, color: C.muted, margin: 0, lineHeight: 1.5 }}>
          Enter your registered mobile number to receive OTP
        </p>
      </div>

      <div style={{ width: '100%', display: 'flex', flexDirection: 'column', gap: 12 }}>
        <input
          type="tel"
          placeholder="+91 98765 43210"
          value={phone}
          onChange={(e) => setPhone(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && !loading && onSubmit()}
          style={{
            width: '100%',
            boxSizing: 'border-box',
            padding: '12px 16px',
            borderRadius: 8,
            border: `1px solid ${C.border}`,
            background: C.elevated,
            color: C.text,
            fontSize: 15,
            outline: 'none',
            fontFamily: 'inherit',
          }}
        />
        <button
          onClick={onSubmit}
          disabled={loading || phone.trim().length < 10}
          style={{
            width: '100%',
            padding: '12px',
            borderRadius: 8,
            border: 'none',
            background: loading || phone.trim().length < 10 ? C.elevated : C.teal,
            color: loading || phone.trim().length < 10 ? C.muted : '#fff',
            fontSize: 15,
            fontWeight: 600,
            cursor: loading || phone.trim().length < 10 ? 'not-allowed' : 'pointer',
            transition: 'background 0.2s',
            fontFamily: 'inherit',
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
  phone,
  otp,
  setOtp,
  onVerify,
  onResend,
  loading,
}: {
  phone: string;
  otp: string;
  setOtp: (v: string) => void;
  onVerify: () => void;
  onResend: () => void;
  loading: boolean;
}) {
  return (
    <div
      style={{
        maxWidth: 380,
        margin: '0 auto',
        background: C.surface,
        borderRadius: 16,
        border: `1px solid ${C.border}`,
        padding: '40px 36px',
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        gap: 24,
      }}
    >
      <ALISLogo />

      <div style={{ textAlign: 'center' }}>
        <h1 style={{ fontSize: 22, fontWeight: 700, color: C.text, margin: '0 0 8px 0' }}>
          Verify OTP
        </h1>
        <p style={{ fontSize: 14, color: C.muted, margin: 0, lineHeight: 1.5 }}>
          OTP sent to{' '}
          <span style={{ color: C.text, fontWeight: 600 }}>{phone}</span>
        </p>
      </div>

      <div style={{ width: '100%', display: 'flex', flexDirection: 'column', gap: 12 }}>
        <input
          type="text"
          inputMode="numeric"
          maxLength={6}
          placeholder="Enter 6-digit OTP"
          value={otp}
          onChange={(e) => setOtp(e.target.value.replace(/\D/g, '').slice(0, 6))}
          onKeyDown={(e) => e.key === 'Enter' && !loading && onVerify()}
          style={{
            width: '100%',
            boxSizing: 'border-box',
            padding: '12px 16px',
            borderRadius: 8,
            border: `1px solid ${C.border}`,
            background: C.elevated,
            color: C.text,
            fontSize: 22,
            letterSpacing: 8,
            textAlign: 'center',
            outline: 'none',
            fontFamily: 'monospace',
          }}
          autoFocus
        />
        <button
          onClick={onVerify}
          disabled={loading || otp.length !== 6}
          style={{
            width: '100%',
            padding: '12px',
            borderRadius: 8,
            border: 'none',
            background: loading || otp.length !== 6 ? C.elevated : C.teal,
            color: loading || otp.length !== 6 ? C.muted : '#fff',
            fontSize: 15,
            fontWeight: 600,
            cursor: loading || otp.length !== 6 ? 'not-allowed' : 'pointer',
            transition: 'background 0.2s',
            fontFamily: 'inherit',
          }}
        >
          {loading ? 'Verifying…' : 'Verify OTP'}
        </button>
        <button
          onClick={onResend}
          style={{
            background: 'none',
            border: 'none',
            color: C.teal,
            fontSize: 14,
            cursor: 'pointer',
            textAlign: 'center',
            padding: '4px',
            fontFamily: 'inherit',
          }}
        >
          Resend OTP
        </button>
      </div>
    </div>
  );
}

// ─── Step 3: Dashboard ────────────────────────────────────────────────────────

function Dashboard({ onLogout }: { onLogout: () => void }) {
  const [consents, setConsents] = useState<ConsentItem[]>(INITIAL_CONSENTS);
  const [consentOpen, setConsentOpen] = useState(false);

  const revokeConsent = (id: string) => {
    setConsents((prev) =>
      prev.map((c) => (c.id === id ? { ...c, status: 'revoked' } : c))
    );
  };

  const attendanceColor =
    ATTENDANCE_PCT < 75 ? C.amber : C.teal;

  return (
    <div style={{ minHeight: '100vh', background: C.bg, display: 'flex', flexDirection: 'column' }}>
      {/* Top bar */}
      <header
        style={{
          background: C.surface,
          borderBottom: `1px solid ${C.border}`,
          padding: '0 24px',
          height: 60,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          flexShrink: 0,
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <ALISLogo />
          <div>
            <div style={{ fontSize: 15, fontWeight: 700, color: C.text }}>Guardian Portal</div>
            <div style={{ fontSize: 12, color: C.muted }}>Ward: {STUDENT_NAME}</div>
          </div>
        </div>

        <button
          onClick={onLogout}
          title="Log out"
          style={{
            background: 'none',
            border: `1px solid ${C.border}`,
            borderRadius: 8,
            color: C.muted,
            padding: '6px 14px',
            cursor: 'pointer',
            fontSize: 13,
            display: 'flex',
            alignItems: 'center',
            gap: 6,
            fontFamily: 'inherit',
          }}
        >
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4" />
            <polyline points="16 17 21 12 16 7" />
            <line x1="21" y1="12" x2="9" y2="12" />
          </svg>
          Log out
        </button>
      </header>

      {/* Body */}
      <main
        style={{
          flex: 1,
          maxWidth: 860,
          margin: '0 auto',
          width: '100%',
          padding: '28px 24px',
          display: 'flex',
          flexDirection: 'column',
          gap: 28,
        }}
      >
        {/* ── Student Snapshot ── */}
        <section>
          <SectionTitle>Student Snapshot</SectionTitle>
          <div
            style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))',
              gap: 16,
            }}
          >
            {/* Attendance card */}
            <SnapshotCard
              label="Attendance"
              value={`${ATTENDANCE_PCT}%`}
              valueColor={attendanceColor}
              sub={ATTENDANCE_PCT < 75 ? 'Below 75% threshold' : 'Within limit'}
              subColor={attendanceColor}
              icon={
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke={attendanceColor} strokeWidth="2">
                  <path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2" />
                  <circle cx="9" cy="7" r="4" />
                  <path d="M23 21v-2a4 4 0 0 0-3-3.87" />
                  <path d="M16 3.13a4 4 0 0 1 0 7.75" />
                </svg>
              }
            />

            {/* Pending Dues card */}
            <SnapshotCard
              label="Pending Dues"
              value="₹18,500"
              valueColor={C.red}
              sub="Due: March 31, 2026"
              subColor={C.red}
              badge="Overdue"
              badgeColor={C.red}
              icon={
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke={C.red} strokeWidth="2">
                  <rect x="2" y="5" width="20" height="14" rx="2" />
                  <path d="M2 10h20" />
                </svg>
              }
            />

            {/* Next Exam card */}
            <SnapshotCard
              label="Next Exam"
              value="Nov 18"
              valueColor={C.purple}
              sub="Data Structures — 7 days"
              subColor={C.muted}
              icon={
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke={C.purple} strokeWidth="2">
                  <rect x="3" y="4" width="18" height="18" rx="2" />
                  <line x1="16" y1="2" x2="16" y2="6" />
                  <line x1="8" y1="2" x2="8" y2="6" />
                  <line x1="3" y1="10" x2="21" y2="10" />
                </svg>
              }
            />
          </div>
        </section>

        {/* ── Upcoming Exams ── */}
        <section>
          <SectionTitle>Upcoming Exams</SectionTitle>
          <div
            style={{
              background: C.surface,
              border: `1px solid ${C.border}`,
              borderRadius: 12,
              overflow: 'hidden',
            }}
          >
            {UPCOMING_EXAMS.map((exam, i) => (
              <div
                key={exam.code}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: 16,
                  padding: '14px 20px',
                  borderBottom: i < UPCOMING_EXAMS.length - 1 ? `1px solid ${C.border}` : 'none',
                }}
              >
                <div
                  style={{
                    minWidth: 68,
                    fontSize: 13,
                    fontWeight: 700,
                    color: C.purple,
                    background: `${C.purple}18`,
                    borderRadius: 6,
                    padding: '4px 8px',
                    textAlign: 'center',
                  }}
                >
                  {exam.date}
                </div>
                <div style={{ fontSize: 13, fontWeight: 600, color: C.muted, minWidth: 52 }}>
                  {exam.code}
                </div>
                <div style={{ fontSize: 14, color: C.text }}>{exam.name}</div>
              </div>
            ))}
          </div>
        </section>

        {/* ── Communication History ── */}
        <section>
          <SectionTitle>Communication History</SectionTitle>
          <div
            style={{
              background: C.surface,
              border: `1px solid ${C.border}`,
              borderRadius: 12,
              padding: '16px 20px',
              display: 'flex',
              flexDirection: 'column',
              gap: 12,
            }}
          >
            {/* WhatsApp header indicator */}
            <div
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: 8,
                paddingBottom: 10,
                borderBottom: `1px solid ${C.border}`,
              }}
            >
              <svg width="16" height="16" viewBox="0 0 24 24" fill={C.teal}>
                <path d="M17.472 14.382c-.297-.149-1.758-.867-2.03-.967-.273-.099-.471-.148-.67.15-.197.297-.767.966-.94 1.164-.173.199-.347.223-.644.075-.297-.15-1.255-.463-2.39-1.475-.883-.788-1.48-1.761-1.653-2.059-.173-.297-.018-.458.13-.606.134-.133.298-.347.446-.52.149-.174.198-.298.298-.497.099-.198.05-.371-.025-.52-.075-.149-.669-1.612-.916-2.207-.242-.579-.487-.5-.669-.51-.173-.008-.371-.01-.57-.01-.198 0-.52.074-.792.372-.272.297-1.04 1.016-1.04 2.479 0 1.462 1.065 2.875 1.213 3.074.149.198 2.096 3.2 5.077 4.487.709.306 1.262.489 1.694.625.712.227 1.36.195 1.871.118.571-.085 1.758-.719 2.006-1.413.248-.694.248-1.289.173-1.413-.074-.124-.272-.198-.57-.347m-5.421 7.403h-.004a9.87 9.87 0 01-5.031-1.378l-.361-.214-3.741.982.998-3.648-.235-.374a9.86 9.86 0 01-1.51-5.26c.001-5.45 4.436-9.884 9.888-9.884 2.64 0 5.122 1.03 6.988 2.898a9.825 9.825 0 012.893 6.994c-.003 5.45-4.437 9.884-9.885 9.884m8.413-18.297A11.815 11.815 0 0012.05 0C5.495 0 .16 5.335.157 11.892c0 2.096.547 4.142 1.588 5.945L.057 24l6.305-1.654a11.882 11.882 0 005.683 1.448h.005c6.554 0 11.89-5.335 11.893-11.893A11.821 11.821 0 0020.885 3.49" />
              </svg>
              <span style={{ fontSize: 12, color: C.muted, fontWeight: 600 }}>
                WhatsApp — ALIS Notifications
              </span>
            </div>

            {MESSAGES.map((msg) => (
              <div
                key={msg.id}
                style={{
                  alignSelf: 'flex-start',
                  maxWidth: '80%',
                  background: C.elevated,
                  borderRadius: '4px 12px 12px 12px',
                  padding: '10px 14px',
                  position: 'relative',
                }}
              >
                <p style={{ margin: 0, fontSize: 13, color: C.text, lineHeight: 1.55 }}>
                  {msg.text}
                </p>
                <div
                  style={{
                    marginTop: 4,
                    fontSize: 11,
                    color: C.muted,
                    textAlign: 'right',
                  }}
                >
                  {msg.time}
                </div>
              </div>
            ))}
          </div>
        </section>

        {/* ── DPDP Consent Management ── */}
        <section>
          <button
            onClick={() => setConsentOpen((v) => !v)}
            style={{
              width: '100%',
              background: C.surface,
              border: `1px solid ${C.border}`,
              borderRadius: consentOpen ? '12px 12px 0 0' : 12,
              padding: '14px 20px',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              cursor: 'pointer',
              fontFamily: 'inherit',
              color: C.text,
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke={C.teal} strokeWidth="2">
                <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
              </svg>
              <span style={{ fontSize: 15, fontWeight: 700 }}>Consent Management</span>
              <span
                style={{
                  fontSize: 11,
                  background: `${C.teal}20`,
                  color: C.teal,
                  padding: '2px 8px',
                  borderRadius: 20,
                  fontWeight: 600,
                }}
              >
                DPDP
              </span>
            </div>
            <svg
              width="16"
              height="16"
              viewBox="0 0 24 24"
              fill="none"
              stroke={C.muted}
              strokeWidth="2"
              style={{
                transform: consentOpen ? 'rotate(180deg)' : 'rotate(0)',
                transition: 'transform 0.2s',
              }}
            >
              <polyline points="6 9 12 15 18 9" />
            </svg>
          </button>

          {consentOpen && (
            <div
              style={{
                background: C.surface,
                border: `1px solid ${C.border}`,
                borderTop: 'none',
                borderRadius: '0 0 12px 12px',
                overflow: 'hidden',
              }}
            >
              {consents.map((c, i) => (
                <div
                  key={c.id}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                    padding: '14px 20px',
                    borderBottom: i < consents.length - 1 ? `1px solid ${C.border}` : 'none',
                    gap: 12,
                  }}
                >
                  <div style={{ display: 'flex', alignItems: 'center', gap: 10, flex: 1 }}>
                    <div
                      style={{
                        width: 8,
                        height: 8,
                        borderRadius: '50%',
                        background: c.status === 'active' ? C.green : C.red,
                        flexShrink: 0,
                      }}
                    />
                    <span style={{ fontSize: 14, color: C.text }}>{c.label}</span>
                  </div>

                  <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexShrink: 0 }}>
                    <span
                      style={{
                        fontSize: 12,
                        fontWeight: 600,
                        color: c.status === 'active' ? C.green : C.red,
                        background: c.status === 'active' ? `${C.green}18` : `${C.red}18`,
                        padding: '3px 10px',
                        borderRadius: 20,
                      }}
                    >
                      {c.status === 'active' ? 'Active' : 'Revoked'}
                    </span>
                    {c.status === 'active' && (
                      <button
                        onClick={() => revokeConsent(c.id)}
                        style={{
                          background: 'none',
                          border: `1px solid ${C.red}`,
                          borderRadius: 6,
                          color: C.red,
                          fontSize: 12,
                          fontWeight: 600,
                          padding: '4px 12px',
                          cursor: 'pointer',
                          fontFamily: 'inherit',
                        }}
                      >
                        Revoke
                      </button>
                    )}
                  </div>
                </div>
              ))}
              <div
                style={{
                  padding: '12px 20px',
                  borderTop: `1px solid ${C.border}`,
                  fontSize: 12,
                  color: C.muted,
                  lineHeight: 1.5,
                }}
              >
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
  label,
  value,
  valueColor,
  sub,
  subColor,
  badge,
  badgeColor,
  icon,
}: {
  label: string;
  value: string;
  valueColor: string;
  sub: string;
  subColor: string;
  badge?: string;
  badgeColor?: string;
  icon: React.ReactNode;
}) {
  return (
    <div
      style={{
        background: C.surface,
        border: `1px solid ${C.border}`,
        borderRadius: 12,
        padding: '20px 20px 18px',
        display: 'flex',
        flexDirection: 'column',
        gap: 10,
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <span style={{ fontSize: 13, color: C.muted, fontWeight: 600 }}>{label}</span>
        {icon}
      </div>
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 10 }}>
        <span style={{ fontSize: 28, fontWeight: 800, color: valueColor, lineHeight: 1 }}>
          {value}
        </span>
        {badge && badgeColor && (
          <span
            style={{
              fontSize: 11,
              fontWeight: 700,
              color: badgeColor,
              background: `${badgeColor}20`,
              padding: '2px 8px',
              borderRadius: 20,
            }}
          >
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

  const handleSendOtp = () => {
    setLoading(true);
    setTimeout(() => {
      setLoading(false);
      setStep('otp');
    }, 1000);
  };

  const handleVerifyOtp = () => {
    setLoading(true);
    setTimeout(() => {
      setLoading(false);
      setStep('dashboard');
    }, 800);
  };

  const handleResend = () => {
    // Re-trigger OTP (no-op in mock)
    setOtp('');
  };

  const handleLogout = () => {
    setStep('phone');
    setPhone('');
    setOtp('');
  };

  if (step === 'dashboard') {
    return <Dashboard onLogout={handleLogout} />;
  }

  return (
    <div
      style={{
        minHeight: '100vh',
        background: C.bg,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        padding: 24,
      }}
    >
      {step === 'phone' ? (
        <PhoneStep
          phone={phone}
          setPhone={setPhone}
          onSubmit={handleSendOtp}
          loading={loading}
        />
      ) : (
        <OTPStep
          phone={phone}
          otp={otp}
          setOtp={setOtp}
          onVerify={handleVerifyOtp}
          onResend={handleResend}
          loading={loading}
        />
      )}
    </div>
  );
}
