/**
 * OnboardingWizardPage — Institution Setup Wizard
 * Route: /admin/onboarding (SUPER_ADMIN only)
 *
 * Step 1 — Hierarchy Builder (Schools → Departments)
 * Step 2 — Module Manager Assignment (M1–M9)
 * Step 3 — HOD Mapping (one per department)
 * Step 4 — Policy Defaults (review standard pack)
 * Step 5 — Provision & Launch (live API log)
 */

import { useState, useRef } from 'react'
import { Plus, Trash2, ChevronRight, CheckCircle, XCircle, Loader, Building2, Users, UserCheck, ScrollText, Rocket, ChevronDown, Eye, EyeOff } from 'lucide-react'

// ─── Types ───────────────────────────────────────────────────────────────────

interface Dept  { id: string; name: string; code: string }
interface School { id: string; name: string; code: string; depts: Dept[] }

const MODULE_DEFS = [
  { key: 'm1_manager', label: 'Admissions Manager',         module: 'M1', desc: 'Leads the admissions pipeline and CRM' },
  { key: 'm2_manager', label: 'Academics Manager',          module: 'M2', desc: 'Owns course offerings, timetable, attendance' },
  { key: 'm3_manager', label: 'Examinations Manager',       module: 'M3', desc: 'Controls hall tickets, results, re-evaluation' },
  { key: 'm4_manager', label: 'Finance Manager',            module: 'M4', desc: 'Fee structures, invoices, scholarships' },
  { key: 'm5_manager', label: 'HR Manager',                 module: 'M5', desc: 'Staff profiles, payroll, leave approvals' },
  { key: 'm6_manager', label: 'Student Services Manager',   module: 'M6', desc: 'Hostel, transport, library, grievances' },
  { key: 'm7_manager', label: 'Communications Manager',     module: 'M7', desc: 'Announcements, bulk messaging, templates' },
  { key: 'm8_manager', label: 'Reporting Manager',          module: 'M8', desc: 'Dashboards, exports, AI insights' },
  { key: 'm9_manager', label: 'Alumni & Placement Manager', module: 'M9', desc: 'Placement drives, alumni network, TPO' },
]

const POLICY_DEFAULTS = [
  { key: 'academics.attendance.min_percentage',     label: 'Min Attendance %',           value: '75',   unit: '%' },
  { key: 'admissions.eligibility.min_academic_pct', label: 'Min Eligibility Marks',      value: '55',   unit: '%' },
  { key: 'admissions.offer_letter.validity_days',   label: 'Offer Letter Validity',      value: '30',   unit: 'days' },
  { key: 'finance.fee.overdue_grace_days',          label: 'Fee Grace Period',           value: '7',    unit: 'days' },
  { key: 'finance.fee.late_penalty_pct',            label: 'Late Fee Penalty',           value: '2',    unit: '%/mo' },
  { key: 'exams.marks.min_passing_pct',             label: 'Min Passing Marks',          value: '40',   unit: '%' },
]

interface ManagerEntry { name: string; email: string; password: string; skip: boolean }
interface HODEntry     { name: string; email: string; password: string; skip: boolean }

type LogEntry = { text: string; status: 'ok' | 'error' | 'running' | 'pending' }

// ─── Helpers ─────────────────────────────────────────────────────────────────

const uid = () => Math.random().toString(36).slice(2, 9)
const autoCode = (name: string) => name.toUpperCase().replace(/[^A-Z0-9]/g, '').slice(0, 8) || 'DEPT'
const tempPwd = () => `ALIS@${Math.floor(1000 + Math.random() * 9000)}!`

function api(path: string, body?: object) {
  const token = localStorage.getItem('token') ?? ''
  return fetch(path, {
    method: body ? 'POST' : 'GET',
    headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
    body: body ? JSON.stringify(body) : undefined,
  })
}

// ─── Sub-components ──────────────────────────────────────────────────────────

function StepBar({ step }: { step: number }) {
  const steps = [
    { n: 1, icon: Building2, label: 'Hierarchy'   },
    { n: 2, icon: Users,     label: 'Managers'    },
    { n: 3, icon: UserCheck, label: 'HODs'        },
    { n: 4, icon: ScrollText,label: 'Policies'    },
    { n: 5, icon: Rocket,    label: 'Launch'      },
  ]
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 0, marginBottom: 32 }}>
      {steps.map((s, i) => {
        const Icon = s.icon
        const done    = step > s.n
        const current = step === s.n
        const color   = done ? '#1D9E75' : current ? '#818cf8' : '#334155'
        return (
          <div key={s.n} style={{ display: 'flex', alignItems: 'center', flex: i < steps.length - 1 ? 1 : undefined }}>
            <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 4 }}>
              <div style={{
                width: 36, height: 36, borderRadius: '50%',
                background: done ? 'rgba(29,158,117,0.15)' : current ? 'rgba(129,140,248,0.15)' : 'rgba(255,255,255,0.04)',
                border: `2px solid ${color}`,
                display: 'flex', alignItems: 'center', justifyContent: 'center',
              }}>
                {done
                  ? <CheckCircle size={16} color="#1D9E75" />
                  : <Icon size={15} color={color} />}
              </div>
              <span style={{ fontSize: 10, fontWeight: 600, color, whiteSpace: 'nowrap' }}>{s.label}</span>
            </div>
            {i < steps.length - 1 && (
              <div style={{ flex: 1, height: 2, background: done ? '#1D9E75' : 'rgba(255,255,255,0.06)', margin: '0 6px', marginBottom: 18 }} />
            )}
          </div>
        )
      })}
    </div>
  )
}

function PasswordField({ value, onChange, placeholder }: { value: string; onChange: (v: string) => void; placeholder?: string }) {
  const [show, setShow] = useState(false)
  return (
    <div style={{ position: 'relative' }}>
      <input
        type={show ? 'text' : 'password'}
        value={value}
        onChange={e => onChange(e.target.value)}
        placeholder={placeholder ?? 'Temp password'}
        style={INPUT}
      />
      <button onClick={() => setShow(p => !p)} style={{ position: 'absolute', right: 10, top: '50%', transform: 'translateY(-50%)', background: 'none', border: 'none', cursor: 'pointer', color: '#475569' }}>
        {show ? <EyeOff size={13} /> : <Eye size={13} />}
      </button>
    </div>
  )
}

// ─── Styles ──────────────────────────────────────────────────────────────────

const INPUT: React.CSSProperties = {
  width: '100%', padding: '8px 12px', borderRadius: 8, fontSize: 12,
  background: 'rgba(255,255,255,0.04)', border: '1px solid rgba(255,255,255,0.08)',
  color: '#e2e8f0', outline: 'none', boxSizing: 'border-box',
}
const CARD: React.CSSProperties = {
  borderRadius: 12, border: '1px solid rgba(255,255,255,0.07)',
  background: 'rgba(255,255,255,0.025)', padding: 16,
}
const BTN_PRIMARY: React.CSSProperties = {
  padding: '9px 20px', borderRadius: 8, fontSize: 13, fontWeight: 600, cursor: 'pointer',
  background: 'rgba(29,158,117,0.15)', color: '#1D9E75', border: '1px solid rgba(29,158,117,0.3)',
}
const BTN_GHOST: React.CSSProperties = {
  padding: '9px 20px', borderRadius: 8, fontSize: 13, cursor: 'pointer',
  background: 'rgba(255,255,255,0.04)', color: '#64748b', border: '1px solid rgba(255,255,255,0.08)',
}

// ─── Main Component ───────────────────────────────────────────────────────────

export function OnboardingWizardPage() {
  const [step, setStep]       = useState(1)
  const [schools, setSchools] = useState<School[]>([
    { id: uid(), name: 'School of Engineering', code: 'SOE', depts: [
      { id: uid(), name: 'Computer Science', code: 'CSE' },
      { id: uid(), name: 'Electronics',      code: 'ECE' },
    ]},
  ])
  const [managers, setManagers] = useState<Record<string, ManagerEntry>>(() =>
    Object.fromEntries(MODULE_DEFS.map(m => [m.key, { name: '', email: '', password: tempPwd(), skip: false }]))
  )
  const [hods, setHods] = useState<Record<string, HODEntry>>({})
  const [policies, setPolicies] = useState<Record<string, string>>(() =>
    Object.fromEntries(POLICY_DEFAULTS.map(p => [p.key, p.value]))
  )
  const [expandedSchools, setExpandedSchools] = useState<Set<string>>(new Set())
  const [log, setLog]     = useState<LogEntry[]>([])
  const [done, setDone]   = useState(false)
  const logRef = useRef<HTMLDivElement>(null)

  // HOD state derived from schools — auto-init missing entries
  const allDepts = schools.flatMap(s => s.depts.map(d => ({ ...d, schoolName: s.name })))

  function ensureHod(deptId: string) {
    if (!hods[deptId]) {
      setHods(p => ({ ...p, [deptId]: { name: '', email: '', password: tempPwd(), skip: false } }))
    }
  }
  allDepts.forEach(d => { if (!hods[d.id]) ensureHod(d.id) })

  // ── Step 1: Hierarchy ──────────────────────────────────────────────────────

  function addSchool() {
    const id = uid()
    setSchools(p => [...p, { id, name: '', code: '', depts: [] }])
    setExpandedSchools(p => new Set([...p, id]))
  }

  function updateSchool(id: string, field: 'name' | 'code', val: string) {
    setSchools(p => p.map(s => s.id === id
      ? { ...s, [field]: val, ...(field === 'name' && !s.code ? { code: autoCode(val) } : {}) }
      : s
    ))
  }

  function removeSchool(id: string) {
    setSchools(p => p.filter(s => s.id !== id))
  }

  function addDept(schoolId: string) {
    setSchools(p => p.map(s => s.id === schoolId
      ? { ...s, depts: [...s.depts, { id: uid(), name: '', code: '' }] }
      : s
    ))
  }

  function updateDept(schoolId: string, deptId: string, field: 'name' | 'code', val: string) {
    setSchools(p => p.map(s => s.id === schoolId
      ? { ...s, depts: s.depts.map(d => d.id === deptId
          ? { ...d, [field]: val, ...(field === 'name' && !d.code ? { code: autoCode(val) } : {}) }
          : d
        )}
      : s
    ))
  }

  function removeDept(schoolId: string, deptId: string) {
    setSchools(p => p.map(s => s.id === schoolId
      ? { ...s, depts: s.depts.filter(d => d.id !== deptId) }
      : s
    ))
  }

  // ── Step 5: Provision ──────────────────────────────────────────────────────

  function pushLog(text: string, status: LogEntry['status']) {
    setLog(p => [...p, { text, status }])
    setTimeout(() => logRef.current?.scrollTo({ top: 99999, behavior: 'smooth' }), 50)
  }

  function updateLog(idx: number, status: LogEntry['status'], text?: string) {
    setLog(p => p.map((l, i) => i === idx ? { ...l, status, ...(text ? { text } : {}) } : l))
  }

  async function provision() {
    const token = localStorage.getItem('token') ?? ''
    let idx = 0

    async function step5(label: string, fn: () => Promise<Response | null>) {
      const i = idx++
      pushLog(label, 'running')
      try {
        const res = await fn()
        if (!res) { updateLog(i, 'ok', `${label} — skipped`); return null }
        if (!res.ok) {
          const err = await res.json().catch(() => ({}))
          updateLog(i, 'error', `${label} — ${err.detail || err.error || res.status}`)
          return null
        }
        const data = await res.json()
        updateLog(i, 'ok', `${label} ✓`)
        return data
      } catch (e: unknown) {
        updateLog(i, 'error', `${label} — ${e instanceof Error ? e.message : 'network error'}`)
        return null
      }
    }

    // 1. Create schools + departments
    const schoolOrgIds: Record<string, string> = {}
    for (const school of schools.filter(s => s.name.trim())) {
      const data = await step5(`Create school: ${school.name}`, () =>
        api('/api/organizations', { name: school.name, code: school.code || autoCode(school.name) })
      )
      if (data?.id) schoolOrgIds[school.id] = data.id

      for (const dept of school.depts.filter(d => d.name.trim())) {
        await step5(`  └─ Department: ${dept.name}`, () =>
          api('/api/organizations', {
            name: dept.name,
            code: dept.code || autoCode(dept.name),
            parent_id: schoolOrgIds[school.id] ?? undefined,
          })
        )
      }
    }

    // 2. Create module managers
    for (const mod of MODULE_DEFS) {
      const m = managers[mod.key]
      if (m.skip || !m.email.trim() || !m.name.trim()) continue
      await step5(`Create ${mod.label}: ${m.email}`, () =>
        api('/api/auth/register', {
          username: m.email,
          email: m.email,
          display_name: m.name,
          password: m.password,
          role: mod.key,
        })
      )
    }

    // 3. Create HODs
    for (const dept of allDepts) {
      const hod = hods[dept.id]
      if (!hod || hod.skip || !hod.email.trim() || !hod.name.trim()) continue
      await step5(`Create HOD for ${dept.name}: ${hod.email}`, () =>
        api('/api/auth/register', {
          username: hod.email,
          email: hod.email,
          display_name: hod.name,
          password: hod.password,
          role: 'hod',
        })
      )
    }

    // 4. Seed policies
    for (const pol of POLICY_DEFAULTS) {
      const val = policies[pol.key]
      if (!val) continue
      await step5(`Policy: ${pol.label} = ${val}${pol.unit}`, () =>
        fetch(`/api/v1/admin/policies/${pol.key}`, {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
          body: JSON.stringify({ value: val }),
        })
      )
    }

    pushLog('Setup complete — ALIS is ready to use!', 'ok')
    setDone(true)
  }

  // ── Render ─────────────────────────────────────────────────────────────────

  return (
    <div style={{ maxWidth: 780, margin: '0 auto', padding: '8px 0 48px' }}>
      {/* Header */}
      <div style={{ marginBottom: 28 }}>
        <p style={{ fontSize: 10, fontWeight: 700, color: '#818cf8', letterSpacing: '0.15em', textTransform: 'uppercase', marginBottom: 4 }}>
          Institution Setup
        </p>
        <h1 style={{ fontSize: 22, fontWeight: 700, color: '#e2e8f0', letterSpacing: '-0.02em', margin: 0 }}>
          Onboarding Wizard
        </h1>
        <p style={{ fontSize: 12, color: '#475569', marginTop: 4 }}>
          Configure your institution's hierarchy, staff roles, and default policies.
        </p>
      </div>

      <StepBar step={step} />

      {/* ── Step 1: Hierarchy ── */}
      {step === 1 && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
          <p style={{ fontSize: 11, color: '#64748b', margin: '0 0 4px' }}>
            Build your school and department tree. Each department can be assigned an HOD in Step 3.
          </p>

          {schools.map(school => {
            const open = expandedSchools.has(school.id)
            return (
              <div key={school.id} style={{ ...CARD, padding: 0, overflow: 'hidden' }}>
                {/* School row */}
                <div style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '12px 14px', background: 'rgba(129,140,248,0.04)', borderBottom: open ? '1px solid rgba(255,255,255,0.06)' : 'none' }}>
                  <button onClick={() => setExpandedSchools(p => { const n = new Set(p); open ? n.delete(school.id) : n.add(school.id); return n })}
                    style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#818cf8', display: 'flex', padding: 2 }}>
                    <ChevronDown size={15} style={{ transform: open ? 'none' : 'rotate(-90deg)', transition: 'transform 0.15s' }} />
                  </button>
                  <input value={school.name} onChange={e => updateSchool(school.id, 'name', e.target.value)}
                    placeholder="School / Faculty name" style={{ ...INPUT, flex: 1, fontWeight: 600, fontSize: 13, background: 'transparent', border: 'none', padding: '4px 0' }} />
                  <input value={school.code} onChange={e => updateSchool(school.id, 'code', e.target.value)}
                    placeholder="CODE" style={{ ...INPUT, width: 80, textTransform: 'uppercase', textAlign: 'center', fontSize: 11 }} />
                  <button onClick={() => removeSchool(school.id)} style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#475569', padding: 4 }}>
                    <Trash2 size={13} />
                  </button>
                </div>

                {/* Departments */}
                {open && (
                  <div style={{ padding: '10px 14px 12px 36px', display: 'flex', flexDirection: 'column', gap: 8 }}>
                    {school.depts.map(dept => (
                      <div key={dept.id} style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                        <ChevronRight size={12} color="#334155" style={{ flexShrink: 0 }} />
                        <input value={dept.name} onChange={e => updateDept(school.id, dept.id, 'name', e.target.value)}
                          placeholder="Department name" style={{ ...INPUT, flex: 1, fontSize: 12 }} />
                        <input value={dept.code} onChange={e => updateDept(school.id, dept.id, 'code', e.target.value)}
                          placeholder="CODE" style={{ ...INPUT, width: 72, textTransform: 'uppercase', textAlign: 'center', fontSize: 11 }} />
                        <button onClick={() => removeDept(school.id, dept.id)} style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#475569', padding: 4 }}>
                          <Trash2 size={12} />
                        </button>
                      </div>
                    ))}
                    <button onClick={() => addDept(school.id)} style={{ display: 'flex', alignItems: 'center', gap: 5, background: 'none', border: '1px dashed rgba(255,255,255,0.1)', borderRadius: 7, padding: '6px 10px', cursor: 'pointer', color: '#475569', fontSize: 11 }}>
                      <Plus size={11} /> Add Department
                    </button>
                  </div>
                )}
              </div>
            )
          })}

          <button onClick={addSchool} style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 6, padding: '10px 0', borderRadius: 10, fontSize: 12, fontWeight: 500, background: 'transparent', color: '#818cf8', border: '1px dashed rgba(129,140,248,0.3)', cursor: 'pointer' }}>
            <Plus size={13} /> Add School / Faculty
          </button>
        </div>
      )}

      {/* ── Step 2: Module Managers ── */}
      {step === 2 && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
          <p style={{ fontSize: 11, color: '#64748b', margin: '0 0 4px' }}>
            Assign a manager for each functional module. Leave blank or toggle Skip to set up later.
          </p>
          {MODULE_DEFS.map(mod => {
            const m = managers[mod.key]
            return (
              <div key={mod.key} style={{ ...CARD, opacity: m.skip ? 0.45 : 1 }}>
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: m.skip ? 0 : 12 }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                    <span style={{ fontSize: 9, fontWeight: 700, padding: '2px 7px', borderRadius: 5, background: 'rgba(129,140,248,0.1)', color: '#818cf8', border: '1px solid rgba(129,140,248,0.2)', letterSpacing: '0.5px' }}>{mod.module}</span>
                    <div>
                      <div style={{ fontSize: 13, fontWeight: 600, color: '#e2e8f0' }}>{mod.label}</div>
                      <div style={{ fontSize: 10, color: '#475569' }}>{mod.desc}</div>
                    </div>
                  </div>
                  <label style={{ display: 'flex', alignItems: 'center', gap: 6, cursor: 'pointer', fontSize: 11, color: '#475569' }}>
                    <input type="checkbox" checked={m.skip} onChange={e => setManagers(p => ({ ...p, [mod.key]: { ...p[mod.key], skip: e.target.checked } }))} />
                    Skip
                  </label>
                </div>
                {!m.skip && (
                  <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 8 }}>
                    <input value={m.name} onChange={e => setManagers(p => ({ ...p, [mod.key]: { ...p[mod.key], name: e.target.value } }))}
                      placeholder="Full name" style={INPUT} />
                    <input value={m.email} onChange={e => setManagers(p => ({ ...p, [mod.key]: { ...p[mod.key], email: e.target.value } }))}
                      placeholder="Email address" type="email" style={INPUT} />
                    <PasswordField value={m.password} onChange={v => setManagers(p => ({ ...p, [mod.key]: { ...p[mod.key], password: v } }))} />
                  </div>
                )}
              </div>
            )
          })}
        </div>
      )}

      {/* ── Step 3: HOD Mapping ── */}
      {step === 3 && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
          <p style={{ fontSize: 11, color: '#64748b', margin: '0 0 4px' }}>
            Assign a Head of Department for each academic unit. Skip if the person isn't hired yet.
          </p>
          {allDepts.length === 0 && (
            <p style={{ fontSize: 12, color: '#475569', textAlign: 'center', padding: 32 }}>
              No departments defined. Go back to Step 1 and add departments first.
            </p>
          )}
          {allDepts.map(dept => {
            const hod = hods[dept.id] ?? { name: '', email: '', password: tempPwd(), skip: false }
            return (
              <div key={dept.id} style={{ ...CARD, opacity: hod.skip ? 0.45 : 1 }}>
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: hod.skip ? 0 : 12 }}>
                  <div>
                    <div style={{ fontSize: 13, fontWeight: 600, color: '#e2e8f0' }}>{dept.name}</div>
                    <div style={{ fontSize: 10, color: '#475569' }}>{dept.schoolName}</div>
                  </div>
                  <label style={{ display: 'flex', alignItems: 'center', gap: 6, cursor: 'pointer', fontSize: 11, color: '#475569' }}>
                    <input type="checkbox" checked={hod.skip} onChange={e => setHods(p => ({ ...p, [dept.id]: { ...hod, skip: e.target.checked } }))} />
                    Skip
                  </label>
                </div>
                {!hod.skip && (
                  <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 8 }}>
                    <input value={hod.name} onChange={e => setHods(p => ({ ...p, [dept.id]: { ...hod, name: e.target.value } }))}
                      placeholder="HOD full name" style={INPUT} />
                    <input value={hod.email} onChange={e => setHods(p => ({ ...p, [dept.id]: { ...hod, email: e.target.value } }))}
                      placeholder="Email address" type="email" style={INPUT} />
                    <PasswordField value={hod.password} onChange={v => setHods(p => ({ ...p, [dept.id]: { ...hod, password: v } }))} />
                  </div>
                )}
              </div>
            )
          })}
        </div>
      )}

      {/* ── Step 4: Policy Defaults ── */}
      {step === 4 && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
          <p style={{ fontSize: 11, color: '#64748b', margin: '0 0 4px' }}>
            Review and adjust the standard policy pack. These can be changed later in Policy Studio.
          </p>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
            {POLICY_DEFAULTS.map(pol => (
              <div key={pol.key} style={CARD}>
                <div style={{ fontSize: 11, fontWeight: 600, color: '#94a3b8', marginBottom: 8 }}>{pol.label}</div>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  <input
                    type="number"
                    value={policies[pol.key] ?? pol.value}
                    onChange={e => setPolicies(p => ({ ...p, [pol.key]: e.target.value }))}
                    style={{ ...INPUT, width: 100 }}
                  />
                  <span style={{ fontSize: 11, color: '#475569' }}>{pol.unit}</span>
                </div>
                <div style={{ fontSize: 9, color: '#334155', marginTop: 6, fontFamily: 'monospace' }}>{pol.key}</div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* ── Step 5: Provision ── */}
      {step === 5 && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          {/* Summary */}
          {log.length === 0 && (
            <>
              <p style={{ fontSize: 11, color: '#64748b', margin: 0 }}>
                Review the summary below, then click <strong style={{ color: '#1D9E75' }}>Provision Everything</strong> to create all accounts and departments.
              </p>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 10 }}>
                {[
                  { label: 'Schools', count: schools.filter(s => s.name).length, color: '#818cf8' },
                  { label: 'Departments', count: allDepts.filter(d => d.name).length, color: '#60a5fa' },
                  { label: 'Module Managers', count: MODULE_DEFS.filter(m => !managers[m.key].skip && managers[m.key].email).length, color: '#1D9E75' },
                  { label: 'HODs', count: allDepts.filter(d => !hods[d.id]?.skip && hods[d.id]?.email).length, color: '#f472b6' },
                  { label: 'Policies', count: POLICY_DEFAULTS.length, color: '#fbbf24' },
                  { label: 'Total Users', count: MODULE_DEFS.filter(m => !managers[m.key].skip && managers[m.key].email).length + allDepts.filter(d => !hods[d.id]?.skip && hods[d.id]?.email).length, color: '#34d399' },
                ].map(item => (
                  <div key={item.label} style={{ ...CARD, textAlign: 'center' }}>
                    <div style={{ fontSize: 28, fontWeight: 700, color: item.color }}>{item.count}</div>
                    <div style={{ fontSize: 11, color: '#475569', marginTop: 2 }}>{item.label}</div>
                  </div>
                ))}
              </div>
              <button onClick={provision} style={{ ...BTN_PRIMARY, alignSelf: 'flex-start', display: 'flex', alignItems: 'center', gap: 8, fontSize: 13 }}>
                <Rocket size={14} /> Provision Everything
              </button>
            </>
          )}

          {/* Live log */}
          {log.length > 0 && (
            <div ref={logRef} style={{ ...CARD, maxHeight: 360, overflowY: 'auto', fontFamily: 'monospace', fontSize: 12, display: 'flex', flexDirection: 'column', gap: 6 }}>
              {log.map((entry, i) => (
                <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                  {entry.status === 'running' && <Loader size={13} color="#818cf8" style={{ animation: 'spin 1s linear infinite', flexShrink: 0 }} />}
                  {entry.status === 'ok'      && <CheckCircle size={13} color="#1D9E75" style={{ flexShrink: 0 }} />}
                  {entry.status === 'error'   && <XCircle size={13} color="#f87171" style={{ flexShrink: 0 }} />}
                  {entry.status === 'pending' && <div style={{ width: 13, height: 13, borderRadius: '50%', background: '#334155', flexShrink: 0 }} />}
                  <span style={{ color: entry.status === 'error' ? '#f87171' : entry.status === 'ok' ? '#94a3b8' : '#e2e8f0' }}>{entry.text}</span>
                </div>
              ))}
            </div>
          )}

          {done && (
            <div style={{ ...CARD, borderColor: 'rgba(29,158,117,0.25)', background: 'rgba(29,158,117,0.06)', textAlign: 'center', padding: 24 }}>
              <CheckCircle size={28} color="#1D9E75" style={{ margin: '0 auto 10px' }} />
              <div style={{ fontSize: 16, fontWeight: 700, color: '#e2e8f0', marginBottom: 6 }}>ALIS is ready!</div>
              <div style={{ fontSize: 12, color: '#64748b', marginBottom: 16 }}>All accounts and departments have been provisioned.</div>
              <a href="/dashboard" style={{ ...BTN_PRIMARY, textDecoration: 'none', display: 'inline-flex', alignItems: 'center', gap: 6 }}>
                Go to Dashboard
              </a>
            </div>
          )}
        </div>
      )}

      {/* ── Navigation ── */}
      {!done && (
        <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: 28 }}>
          <button onClick={() => setStep(p => p - 1)} disabled={step === 1} style={{ ...BTN_GHOST, opacity: step === 1 ? 0.4 : 1, cursor: step === 1 ? 'not-allowed' : 'pointer' }}>
            ← Back
          </button>
          {step < 5 && (
            <button onClick={() => setStep(p => p + 1)} style={{ ...BTN_PRIMARY, display: 'flex', alignItems: 'center', gap: 6 }}>
              Next →
            </button>
          )}
        </div>
      )}
    </div>
  )
}
