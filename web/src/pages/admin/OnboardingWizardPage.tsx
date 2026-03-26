/**
 * OnboardingWizardPage — Institution Setup Wizard
 * Route: /admin/onboarding (SUPER_ADMIN only)
 *
 * Step 1 — Hierarchy Builder   (Schools → Departments)
 * Step 2 — Module Managers     (M1–M9 functional heads)
 * Step 3 — Module Scope        (which schools each module oversees + cross-grants)
 * Step 4 — HOD Mapping         (one HOD per department)
 * Step 5 — Policy Defaults
 * Step 6 — Provision & Launch
 */

import { useState, useRef } from 'react'
import {
  Plus, Trash2, ChevronRight, CheckCircle, XCircle, Loader,
  Building2, Users, GitBranch, UserCheck, ScrollText, Rocket,
  ChevronDown, Eye, EyeOff, Link2,
} from 'lucide-react'

// ─── Types ────────────────────────────────────────────────────────────────────

interface Dept   { id: string; name: string; code: string }
interface School { id: string; name: string; code: string; depts: Dept[] }

interface ManagerEntry { name: string; email: string; password: string; skip: boolean }
interface HODEntry     { name: string; email: string; password: string; skip: boolean }

// moduleScope[moduleKey] = Set of school IDs it oversees
// crossGrants[moduleKey] = Set of other module keys whose READ perms are granted
type LogEntry = { text: string; status: 'ok' | 'error' | 'running' }

// ─── Constants ────────────────────────────────────────────────────────────────

const MODULE_DEFS = [
  { key: 'm1_manager', label: 'Admissions',       module: 'M1', color: '#818cf8', desc: 'Admissions pipeline & CRM',              crossCutting: true  },
  { key: 'm2_manager', label: 'Academics',         module: 'M2', color: '#60a5fa', desc: 'Courses, timetable, attendance',         crossCutting: false },
  { key: 'm3_manager', label: 'Examinations',      module: 'M3', color: '#34d399', desc: 'Hall tickets, results, re-evaluation',   crossCutting: false },
  { key: 'm4_manager', label: 'Finance',           module: 'M4', color: '#fbbf24', desc: 'Fee structures, invoices, scholarships', crossCutting: true  },
  { key: 'm5_manager', label: 'HR',                module: 'M5', color: '#f472b6', desc: 'Staff profiles, payroll, leave',         crossCutting: true  },
  { key: 'm6_manager', label: 'Student Services',  module: 'M6', color: '#a78bfa', desc: 'Hostel, transport, library',             crossCutting: false },
  { key: 'm7_manager', label: 'Communications',    module: 'M7', color: '#22d3ee', desc: 'Announcements, bulk messaging',          crossCutting: true  },
  { key: 'm8_manager', label: 'Reporting',         module: 'M8', color: '#fb923c', desc: 'Dashboards, exports, AI insights',       crossCutting: true  },
  { key: 'm9_manager', label: 'Alumni & Placement',module: 'M9', color: '#4ade80', desc: 'Placement drives, alumni, TPO',          crossCutting: true  },
]

const POLICY_DEFAULTS = [
  { key: 'academics.attendance.min_percentage',     label: 'Min Attendance %',     value: '75',  unit: '%'    },
  { key: 'admissions.eligibility.min_academic_pct', label: 'Min Eligibility Marks',value: '55',  unit: '%'    },
  { key: 'admissions.offer_letter.validity_days',   label: 'Offer Letter Validity', value: '30',  unit: 'days' },
  { key: 'finance.fee.overdue_grace_days',          label: 'Fee Grace Period',      value: '7',   unit: 'days' },
  { key: 'finance.fee.late_penalty_pct',            label: 'Late Fee Penalty',      value: '2',   unit: '%/mo' },
  { key: 'exams.marks.min_passing_pct',             label: 'Min Passing Marks',     value: '40',  unit: '%'    },
]

const STEP_META = [
  { n: 1, icon: Building2,  label: 'Hierarchy'  },
  { n: 2, icon: Users,      label: 'Managers'   },
  { n: 3, icon: GitBranch,  label: 'Scope'      },
  { n: 4, icon: UserCheck,  label: 'HODs'       },
  { n: 5, icon: ScrollText, label: 'Policies'   },
  { n: 6, icon: Rocket,     label: 'Launch'     },
]

// ─── Helpers ─────────────────────────────────────────────────────────────────

const uid     = () => Math.random().toString(36).slice(2, 9)
const autoCode = (n: string) => n.toUpperCase().replace(/[^A-Z0-9]/g, '').slice(0, 8) || 'DEPT'
const tempPwd  = () => `ALIS@${Math.floor(1000 + Math.random() * 9000)}!`

function apiFetch(path: string, body?: object) {
  const token = localStorage.getItem('token') ?? ''
  return fetch(path, {
    method: body ? 'POST' : 'GET',
    headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
    body: body ? JSON.stringify(body) : undefined,
  })
}

// ─── Styles ───────────────────────────────────────────────────────────────────

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

// ─── Sub-components ───────────────────────────────────────────────────────────

function StepBar({ step }: { step: number }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 0, marginBottom: 32 }}>
      {STEP_META.map((s, i) => {
        const Icon  = s.icon
        const done    = step > s.n
        const current = step === s.n
        const color   = done ? '#1D9E75' : current ? '#818cf8' : '#334155'
        return (
          <div key={s.n} style={{ display: 'flex', alignItems: 'center', flex: i < STEP_META.length - 1 ? 1 : undefined }}>
            <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 4 }}>
              <div style={{
                width: 34, height: 34, borderRadius: '50%',
                background: done ? 'rgba(29,158,117,0.12)' : current ? 'rgba(129,140,248,0.12)' : 'rgba(255,255,255,0.03)',
                border: `2px solid ${color}`,
                display: 'flex', alignItems: 'center', justifyContent: 'center',
              }}>
                {done ? <CheckCircle size={15} color="#1D9E75" /> : <Icon size={14} color={color} />}
              </div>
              <span style={{ fontSize: 9, fontWeight: 600, color, whiteSpace: 'nowrap', letterSpacing: '0.04em' }}>{s.label}</span>
            </div>
            {i < STEP_META.length - 1 && (
              <div style={{ flex: 1, height: 2, background: done ? '#1D9E75' : 'rgba(255,255,255,0.05)', margin: '0 4px', marginBottom: 18 }} />
            )}
          </div>
        )
      })}
    </div>
  )
}

function PasswordField({ value, onChange }: { value: string; onChange: (v: string) => void }) {
  const [show, setShow] = useState(false)
  return (
    <div style={{ position: 'relative' }}>
      <input type={show ? 'text' : 'password'} value={value} onChange={e => onChange(e.target.value)}
        placeholder="Temp password" style={INPUT} />
      <button onClick={() => setShow(p => !p)}
        style={{ position: 'absolute', right: 10, top: '50%', transform: 'translateY(-50%)', background: 'none', border: 'none', cursor: 'pointer', color: '#475569' }}>
        {show ? <EyeOff size={12} /> : <Eye size={12} />}
      </button>
    </div>
  )
}

// ─── Checkbox cell for the scope matrix ──────────────────────────────────────

function MatrixCell({ checked, onChange, color }: { checked: boolean; onChange: () => void; color: string }) {
  return (
    <div onClick={onChange} style={{
      width: 28, height: 28, borderRadius: 6, cursor: 'pointer',
      background: checked ? `${color}22` : 'rgba(255,255,255,0.03)',
      border: `1px solid ${checked ? color + '55' : 'rgba(255,255,255,0.07)'}`,
      display: 'flex', alignItems: 'center', justifyContent: 'center',
      transition: 'all 0.1s',
    }}>
      {checked && <CheckCircle size={13} color={color} />}
    </div>
  )
}

// ─── Main Component ───────────────────────────────────────────────────────────

export function OnboardingWizardPage() {
  const [step, setStep]       = useState(1)

  // Step 1: Hierarchy
  const [schools, setSchools] = useState<School[]>([
    { id: uid(), name: 'School of Engineering', code: 'SOE', depts: [
      { id: uid(), name: 'Computer Science', code: 'CSE' },
      { id: uid(), name: 'Electronics',      code: 'ECE' },
    ]},
  ])
  const [expandedSchools, setExpandedSchools] = useState<Set<string>>(new Set())

  // Step 2: Module Managers
  const [managers, setManagers] = useState<Record<string, ManagerEntry>>(() =>
    Object.fromEntries(MODULE_DEFS.map(m => [m.key, { name: '', email: '', password: tempPwd(), skip: false }]))
  )

  // Step 3: Module Scope
  // moduleScope[moduleKey] = set of school IDs this module oversees
  // crossGrants[moduleKey] = set of other module keys this manager gets cross-access to
  const [moduleScope, setModuleScope]   = useState<Record<string, Set<string>>>(() =>
    Object.fromEntries(MODULE_DEFS.map(m => [m.key, new Set<string>()]))
  )
  const [crossGrants, setCrossGrants]   = useState<Record<string, Set<string>>>(() =>
    Object.fromEntries(MODULE_DEFS.map(m => [m.key, new Set<string>()]))
  )

  // Step 4: HODs
  const [hods, setHods] = useState<Record<string, HODEntry>>({})

  // Step 5: Policies
  const [policies, setPolicies] = useState<Record<string, string>>(() =>
    Object.fromEntries(POLICY_DEFAULTS.map(p => [p.key, p.value]))
  )

  // Step 6: Provision
  const [log, setLog]   = useState<LogEntry[]>([])
  const [done, setDone] = useState(false)
  const logRef          = useRef<HTMLDivElement>(null)

  const allDepts   = schools.flatMap(s => s.depts.map(d => ({ ...d, schoolName: s.name, schoolId: s.id })))
  const activeMods = MODULE_DEFS.filter(m => !managers[m.key].skip)

  // Auto-init HOD entries for new depts
  allDepts.forEach(d => {
    if (!hods[d.id]) setHods(p => ({ ...p, [d.id]: { name: '', email: '', password: tempPwd(), skip: false } }))
  })

  // ── Step 1 helpers ─────────────────────────────────────────────────────────

  const addSchool = () => {
    const id = uid()
    setSchools(p => [...p, { id, name: '', code: '', depts: [] }])
    setExpandedSchools(p => new Set([...p, id]))
  }
  const updateSchool = (id: string, f: 'name' | 'code', v: string) =>
    setSchools(p => p.map(s => s.id === id ? { ...s, [f]: v, ...(f === 'name' && !s.code ? { code: autoCode(v) } : {}) } : s))
  const removeSchool = (id: string) => setSchools(p => p.filter(s => s.id !== id))
  const addDept      = (sId: string) => setSchools(p => p.map(s => s.id === sId ? { ...s, depts: [...s.depts, { id: uid(), name: '', code: '' }] } : s))
  const updateDept   = (sId: string, dId: string, f: 'name' | 'code', v: string) =>
    setSchools(p => p.map(s => s.id === sId ? { ...s, depts: s.depts.map(d => d.id === dId ? { ...d, [f]: v, ...(f === 'name' && !d.code ? { code: autoCode(v) } : {}) } : d) } : s))
  const removeDept   = (sId: string, dId: string) =>
    setSchools(p => p.map(s => s.id === sId ? { ...s, depts: s.depts.filter(d => d.id !== dId) } : s))

  // ── Step 3 helpers ─────────────────────────────────────────────────────────

  const toggleScope = (modKey: string, schoolId: string) =>
    setModuleScope(p => {
      const next = new Set(p[modKey])
      next.has(schoolId) ? next.delete(schoolId) : next.add(schoolId)
      return { ...p, [modKey]: next }
    })

  const toggleCross = (modKey: string, targetKey: string) =>
    setCrossGrants(p => {
      const next = new Set(p[modKey])
      next.has(targetKey) ? next.delete(targetKey) : next.add(targetKey)
      return { ...p, [modKey]: next }
    })

  const selectAllScope = (modKey: string) =>
    setModuleScope(p => ({ ...p, [modKey]: new Set(schools.map(s => s.id)) }))

  const clearScope = (modKey: string) =>
    setModuleScope(p => ({ ...p, [modKey]: new Set() }))

  // ── Step 6: Provision ─────────────────────────────────────────────────────

  const pushLog = (text: string, status: LogEntry['status']) => {
    setLog(p => [...p, { text, status }])
    setTimeout(() => logRef.current?.scrollTo({ top: 99999, behavior: 'smooth' }), 40)
  }

  const updateLog = (i: number, status: LogEntry['status'], text?: string) =>
    setLog(p => p.map((l, j) => j === i ? { status, text: text ?? l.text } : l))

  async function provision() {
    let idx = 0
    const token = localStorage.getItem('token') ?? ''

    async function run(label: string, fn: () => Promise<Response | null>) {
      const i = idx++
      pushLog(label, 'running')
      try {
        const res = await fn()
        if (!res) { updateLog(i, 'ok', `${label} — skipped`); return null }
        if (!res.ok) {
          const e = await res.json().catch(() => ({}))
          updateLog(i, 'error', `${label} — ${e.detail || e.error || res.status}`)
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

    // 1. Schools + Departments
    const schoolOrgIds: Record<string, string> = {}
    for (const s of schools.filter(s => s.name.trim())) {
      const data = await run(`School: ${s.name}`, () =>
        apiFetch('/api/organizations', { name: s.name, code: s.code || autoCode(s.name) })
      )
      if (data?.id) schoolOrgIds[s.id] = data.id
      for (const d of s.depts.filter(d => d.name.trim())) {
        await run(`  └─ ${d.name}`, () =>
          apiFetch('/api/organizations', { name: d.name, code: d.code || autoCode(d.name), parent_id: schoolOrgIds[s.id] })
        )
      }
    }

    // 2. Module managers
    const managerUserIds: Record<string, string> = {}
    for (const mod of activeMods) {
      const m = managers[mod.key]
      if (!m.email.trim() || !m.name.trim()) continue
      const data = await run(`${mod.module} Manager: ${m.email}`, () =>
        apiFetch('/api/auth/register', { username: m.email, email: m.email, display_name: m.name, password: m.password, role: mod.key })
      )
      if (data?.id) managerUserIds[mod.key] = data.id
    }

    // 3. Cross-module grants via custom roles (SUPER_ADMIN → auto-approved)
    for (const mod of activeMods) {
      const grants = [...crossGrants[mod.key]]
      if (!grants.length || !managerUserIds[mod.key]) continue

      // Create a cross-grant custom role for this manager
      const roleName = `${mod.module}_with_${grants.map(g => MODULE_DEFS.find(x => x.key === g)?.module).join('_')}_access`
      const roleData = await run(
        `Cross-grant role for ${mod.module}: +${grants.map(g => MODULE_DEFS.find(x => x.key === g)?.module).join(', ')}`,
        () => apiFetch('/api/roles', { role_name: roleName, description: `Auto-created: ${mod.label} cross-module access` })
      )

      if (roleData?.id) {
        // Request the cross-module permissions — SUPER_ADMIN = auto-approved
        await run(`  └─ Assign permissions`, () =>
          apiFetch(`/api/roles/${roleData.id}/permissions`, {
            permissions: grants.flatMap(gKey => {
              const gMod = MODULE_DEFS.find(x => x.key === gKey)
              // Map module to its read permissions
              const permMap: Record<string, string[]> = {
                M1: ['student:read', 'student:read_pii'],
                M2: ['academics:read', 'course:read', 'marks:read'],
                M3: ['exam_paper:read', 'marks:read'],
                M4: ['fee:read', 'ledger:read'],
                M5: ['staff:read', 'payroll:read'],
                M6: ['service:read'],
                M7: ['notification:read'],
                M8: ['report:read'],
                M9: ['alumni:read'],
              }
              return permMap[gMod?.module ?? ''] ?? []
            }),
          })
        )
        // Assign the custom role to the manager user
        await run(`  └─ Assign role to user`, () =>
          apiFetch(`/api/users/${managerUserIds[mod.key]}/roles`, { role_id: roleData.id })
        )
      }
    }

    // 4. HODs
    for (const d of allDepts) {
      const hod = hods[d.id]
      if (!hod || hod.skip || !hod.email.trim() || !hod.name.trim()) continue
      await run(`HOD ${d.name}: ${hod.email}`, () =>
        apiFetch('/api/auth/register', { username: hod.email, email: hod.email, display_name: hod.name, password: hod.password, role: 'hod' })
      )
    }

    // 5. Policies
    for (const pol of POLICY_DEFAULTS) {
      const val = policies[pol.key]
      if (!val) continue
      await run(`Policy: ${pol.label} = ${val}${pol.unit}`, () =>
        fetch(`/api/v1/admin/policies/${pol.key}`, {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
          body: JSON.stringify({ value: val }),
        })
      )
    }

    pushLog('Setup complete — ALIS is ready!', 'ok')
    setDone(true)
  }

  // ── Render ────────────────────────────────────────────────────────────────

  return (
    <div style={{ maxWidth: 820, margin: '0 auto', padding: '8px 0 48px' }}>
      <div style={{ marginBottom: 28 }}>
        <p style={{ fontSize: 10, fontWeight: 700, color: '#818cf8', letterSpacing: '0.15em', textTransform: 'uppercase', marginBottom: 4 }}>
          Institution Setup
        </p>
        <h1 style={{ fontSize: 22, fontWeight: 700, color: '#e2e8f0', letterSpacing: '-0.02em', margin: 0 }}>
          Onboarding Wizard
        </h1>
        <p style={{ fontSize: 12, color: '#475569', marginTop: 4 }}>
          Configure hierarchy, assign functional heads, define module scope, and set policies.
        </p>
      </div>

      <StepBar step={step} />

      {/* ──────────── STEP 1: Hierarchy ──────────── */}
      {step === 1 && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
          <p style={{ fontSize: 11, color: '#64748b', margin: '0 0 4px' }}>
            Build your school and department tree. Each department can be assigned an HOD in Step 4.
          </p>
          {schools.map(school => {
            const open = expandedSchools.has(school.id)
            return (
              <div key={school.id} style={{ ...CARD, padding: 0, overflow: 'hidden' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '12px 14px', background: 'rgba(129,140,248,0.04)', borderBottom: open ? '1px solid rgba(255,255,255,0.06)' : 'none' }}>
                  <button onClick={() => setExpandedSchools(p => { const n = new Set(p); open ? n.delete(school.id) : n.add(school.id); return n })}
                    style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#818cf8', padding: 2 }}>
                    <ChevronDown size={15} style={{ transform: open ? 'none' : 'rotate(-90deg)', transition: 'transform 0.15s' }} />
                  </button>
                  <input value={school.name} onChange={e => updateSchool(school.id, 'name', e.target.value)}
                    placeholder="School / Faculty name"
                    style={{ ...INPUT, flex: 1, fontWeight: 600, fontSize: 13, background: 'transparent', border: 'none', padding: '4px 0' }} />
                  <input value={school.code} onChange={e => updateSchool(school.id, 'code', e.target.value)}
                    placeholder="CODE" style={{ ...INPUT, width: 80, textTransform: 'uppercase', textAlign: 'center', fontSize: 11 }} />
                  <button onClick={() => removeSchool(school.id)} style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#475569', padding: 4 }}>
                    <Trash2 size={13} />
                  </button>
                </div>
                {open && (
                  <div style={{ padding: '10px 14px 12px 40px', display: 'flex', flexDirection: 'column', gap: 8 }}>
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

      {/* ──────────── STEP 2: Module Managers ──────────── */}
      {step === 2 && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
          <p style={{ fontSize: 11, color: '#64748b', margin: '0 0 4px' }}>
            Assign a functional head for each module. Scope and cross-module access are configured in Step 3.
          </p>
          {MODULE_DEFS.map(mod => {
            const m = managers[mod.key]
            return (
              <div key={mod.key} style={{ ...CARD, opacity: m.skip ? 0.45 : 1, transition: 'opacity 0.15s' }}>
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: m.skip ? 0 : 12 }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                    <span style={{ fontSize: 9, fontWeight: 700, padding: '2px 7px', borderRadius: 5, background: `${mod.color}18`, color: mod.color, border: `1px solid ${mod.color}33`, letterSpacing: '0.5px' }}>{mod.module}</span>
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
                    <input value={m.name} onChange={e => setManagers(p => ({ ...p, [mod.key]: { ...p[mod.key], name: e.target.value } }))} placeholder="Full name" style={INPUT} />
                    <input value={m.email} onChange={e => setManagers(p => ({ ...p, [mod.key]: { ...p[mod.key], email: e.target.value } }))} placeholder="Email" type="email" style={INPUT} />
                    <PasswordField value={m.password} onChange={v => setManagers(p => ({ ...p, [mod.key]: { ...p[mod.key], password: v } }))} />
                  </div>
                )}
              </div>
            )
          })}
        </div>
      )}

      {/* ──────────── STEP 3: Module Scope Mapping ──────────── */}
      {step === 3 && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
          <p style={{ fontSize: 11, color: '#64748b', margin: 0 }}>
            Define which schools each module manager oversees, and grant read-only cross-module access where needed.
          </p>

          {/* Scope matrix */}
          <div style={CARD}>
            <div style={{ fontSize: 12, fontWeight: 600, color: '#94a3b8', marginBottom: 14, display: 'flex', alignItems: 'center', gap: 6 }}>
              <Building2 size={13} color="#818cf8" /> Department Scope per Module
            </div>

            {schools.length === 0 ? (
              <p style={{ fontSize: 11, color: '#475569' }}>Add schools in Step 1 first.</p>
            ) : (
              <div style={{ overflowX: 'auto' }}>
                <table style={{ borderCollapse: 'collapse', minWidth: '100%' }}>
                  <thead>
                    <tr>
                      <th style={{ width: 160, textAlign: 'left', padding: '0 12px 10px 0', fontSize: 10, color: '#475569', fontWeight: 500 }}>Module</th>
                      {schools.map(s => (
                        <th key={s.id} style={{ padding: '0 4px 10px', textAlign: 'center', fontSize: 10, color: '#64748b', fontWeight: 600, whiteSpace: 'nowrap' }}>
                          {s.name || s.code || '—'}
                        </th>
                      ))}
                      <th style={{ padding: '0 0 10px 12px', textAlign: 'center', fontSize: 10, color: '#334155' }}>Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {activeMods.map(mod => (
                      <tr key={mod.key} style={{ borderTop: '1px solid rgba(255,255,255,0.04)' }}>
                        <td style={{ padding: '8px 12px 8px 0' }}>
                          <div style={{ display: 'flex', alignItems: 'center', gap: 7 }}>
                            <span style={{ fontSize: 9, fontWeight: 700, padding: '1px 6px', borderRadius: 4, background: `${mod.color}18`, color: mod.color }}>{mod.module}</span>
                            <span style={{ fontSize: 11, color: '#94a3b8' }}>{mod.label}</span>
                          </div>
                        </td>
                        {schools.map(s => (
                          <td key={s.id} style={{ padding: '8px 4px', textAlign: 'center' }}>
                            <MatrixCell
                              checked={moduleScope[mod.key]?.has(s.id) ?? false}
                              onChange={() => toggleScope(mod.key, s.id)}
                              color={mod.color}
                            />
                          </td>
                        ))}
                        <td style={{ padding: '8px 0 8px 12px', textAlign: 'center' }}>
                          <div style={{ display: 'flex', gap: 4, justifyContent: 'center' }}>
                            <button onClick={() => selectAllScope(mod.key)} style={{ fontSize: 9, padding: '2px 7px', borderRadius: 4, cursor: 'pointer', background: `${mod.color}18`, color: mod.color, border: `1px solid ${mod.color}33` }}>
                              All
                            </button>
                            <button onClick={() => clearScope(mod.key)} style={{ fontSize: 9, padding: '2px 7px', borderRadius: 4, cursor: 'pointer', background: 'rgba(255,255,255,0.03)', color: '#475569', border: '1px solid rgba(255,255,255,0.08)' }}>
                              None
                            </button>
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>

          {/* Cross-module access grants */}
          <div style={CARD}>
            <div style={{ fontSize: 12, fontWeight: 600, color: '#94a3b8', marginBottom: 4, display: 'flex', alignItems: 'center', gap: 6 }}>
              <Link2 size={13} color="#fbbf24" /> Cross-Module Read Access
            </div>
            <p style={{ fontSize: 10, color: '#475569', margin: '0 0 14px' }}>
              Grant a module manager read-only access to other modules. Auto-approved as SUPER_ADMIN.
              Cross-module access is provisioned as a custom role on the user.
            </p>

            {activeMods.map(mod => (
              <div key={mod.key} style={{ display: 'flex', alignItems: 'flex-start', gap: 12, padding: '10px 0', borderTop: '1px solid rgba(255,255,255,0.04)' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 7, width: 160, flexShrink: 0 }}>
                  <span style={{ fontSize: 9, fontWeight: 700, padding: '1px 6px', borderRadius: 4, background: `${mod.color}18`, color: mod.color }}>{mod.module}</span>
                  <span style={{ fontSize: 11, color: '#94a3b8' }}>{mod.label}</span>
                </div>
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
                  {activeMods.filter(x => x.key !== mod.key).map(target => {
                    const granted = crossGrants[mod.key]?.has(target.key) ?? false
                    return (
                      <button key={target.key} onClick={() => toggleCross(mod.key, target.key)} style={{
                        padding: '3px 10px', borderRadius: 20, fontSize: 10, cursor: 'pointer',
                        background: granted ? `${target.color}22` : 'rgba(255,255,255,0.03)',
                        color: granted ? target.color : '#475569',
                        border: `1px solid ${granted ? target.color + '44' : 'rgba(255,255,255,0.08)'}`,
                        fontWeight: granted ? 600 : 400,
                        transition: 'all 0.1s',
                      }}>
                        {target.module}
                      </button>
                    )
                  })}
                  {activeMods.filter(x => x.key !== mod.key).length === 0 && (
                    <span style={{ fontSize: 11, color: '#334155' }}>No other active modules</span>
                  )}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* ──────────── STEP 4: HOD Mapping ──────────── */}
      {step === 4 && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
          <p style={{ fontSize: 11, color: '#64748b', margin: '0 0 4px' }}>
            Assign a Head of Department for each unit. Skip if not yet hired.
          </p>
          {allDepts.length === 0 && (
            <p style={{ fontSize: 12, color: '#475569', textAlign: 'center', padding: 32 }}>
              No departments defined — go back to Step 1.
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
                    <input value={hod.name} onChange={e => setHods(p => ({ ...p, [dept.id]: { ...hod, name: e.target.value } }))} placeholder="HOD full name" style={INPUT} />
                    <input value={hod.email} onChange={e => setHods(p => ({ ...p, [dept.id]: { ...hod, email: e.target.value } }))} placeholder="Email" type="email" style={INPUT} />
                    <PasswordField value={hod.password} onChange={v => setHods(p => ({ ...p, [dept.id]: { ...hod, password: v } }))} />
                  </div>
                )}
              </div>
            )
          })}
        </div>
      )}

      {/* ──────────── STEP 5: Policies ──────────── */}
      {step === 5 && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
          <p style={{ fontSize: 11, color: '#64748b', margin: '0 0 4px' }}>
            Review and adjust standard policies. Full editing available in Policy Studio post-launch.
          </p>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
            {POLICY_DEFAULTS.map(pol => (
              <div key={pol.key} style={CARD}>
                <div style={{ fontSize: 11, fontWeight: 600, color: '#94a3b8', marginBottom: 8 }}>{pol.label}</div>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  <input type="number" value={policies[pol.key] ?? pol.value}
                    onChange={e => setPolicies(p => ({ ...p, [pol.key]: e.target.value }))}
                    style={{ ...INPUT, width: 90 }} />
                  <span style={{ fontSize: 11, color: '#475569' }}>{pol.unit}</span>
                </div>
                <div style={{ fontSize: 9, color: '#334155', marginTop: 6, fontFamily: 'monospace' }}>{pol.key}</div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* ──────────── STEP 6: Provision ──────────── */}
      {step === 6 && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          {log.length === 0 && (
            <>
              <p style={{ fontSize: 11, color: '#64748b', margin: 0 }}>
                Review the summary, then click <strong style={{ color: '#1D9E75' }}>Provision Everything</strong>.
              </p>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 10 }}>
                {[
                  { label: 'Schools',        count: schools.filter(s => s.name).length,  color: '#818cf8' },
                  { label: 'Departments',    count: allDepts.filter(d => d.name).length,  color: '#60a5fa' },
                  { label: 'Mod. Managers',  count: activeMods.filter(m => managers[m.key].email).length, color: '#1D9E75' },
                  { label: 'Cross-Grants',   count: activeMods.reduce((n, m) => n + (crossGrants[m.key]?.size ?? 0), 0), color: '#fbbf24' },
                  { label: 'HODs',           count: allDepts.filter(d => !hods[d.id]?.skip && hods[d.id]?.email).length, color: '#f472b6' },
                  { label: 'Total Users',    count: activeMods.filter(m => managers[m.key].email).length + allDepts.filter(d => !hods[d.id]?.skip && hods[d.id]?.email).length, color: '#34d399' },
                ].map(item => (
                  <div key={item.label} style={{ ...CARD, textAlign: 'center' }}>
                    <div style={{ fontSize: 26, fontWeight: 700, color: item.color }}>{item.count}</div>
                    <div style={{ fontSize: 11, color: '#475569', marginTop: 2 }}>{item.label}</div>
                  </div>
                ))}
              </div>
              <button onClick={provision} style={{ ...BTN_PRIMARY, alignSelf: 'flex-start', display: 'flex', alignItems: 'center', gap: 8 }}>
                <Rocket size={14} /> Provision Everything
              </button>
            </>
          )}

          {log.length > 0 && (
            <div ref={logRef} style={{ ...CARD, maxHeight: 380, overflowY: 'auto', fontFamily: 'monospace', fontSize: 12, display: 'flex', flexDirection: 'column', gap: 6 }}>
              {log.map((entry, i) => (
                <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                  {entry.status === 'running' && <Loader   size={13} color="#818cf8" style={{ animation: 'spin 1s linear infinite', flexShrink: 0 }} />}
                  {entry.status === 'ok'      && <CheckCircle size={13} color="#1D9E75" style={{ flexShrink: 0 }} />}
                  {entry.status === 'error'   && <XCircle    size={13} color="#f87171" style={{ flexShrink: 0 }} />}
                  <span style={{ color: entry.status === 'error' ? '#f87171' : entry.status === 'ok' ? '#94a3b8' : '#e2e8f0' }}>{entry.text}</span>
                </div>
              ))}
            </div>
          )}

          {done && (
            <div style={{ ...CARD, borderColor: 'rgba(29,158,117,0.25)', background: 'rgba(29,158,117,0.06)', textAlign: 'center', padding: 24 }}>
              <CheckCircle size={28} color="#1D9E75" style={{ margin: '0 auto 10px' }} />
              <div style={{ fontSize: 16, fontWeight: 700, color: '#e2e8f0', marginBottom: 6 }}>ALIS is live!</div>
              <div style={{ fontSize: 12, color: '#64748b', marginBottom: 16 }}>All users, departments, and role mappings have been provisioned.</div>
              <a href="/dashboard" style={{ ...BTN_PRIMARY, textDecoration: 'none', display: 'inline-flex', alignItems: 'center', gap: 6 }}>
                Go to Dashboard
              </a>
            </div>
          )}
        </div>
      )}

      {/* ──────────── Navigation ──────────── */}
      {!done && (
        <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: 28 }}>
          <button onClick={() => setStep(p => p - 1)} disabled={step === 1}
            style={{ ...BTN_GHOST, opacity: step === 1 ? 0.4 : 1, cursor: step === 1 ? 'not-allowed' : 'pointer' }}>
            ← Back
          </button>
          {step < 6 && (
            <button onClick={() => setStep(p => p + 1)} style={BTN_PRIMARY}>
              Next →
            </button>
          )}
        </div>
      )}
    </div>
  )
}
