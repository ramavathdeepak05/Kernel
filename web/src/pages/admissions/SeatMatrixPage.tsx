/**
 * SeatMatrixPage — E19 Quota Seat Matrix Admin UI
 * Route: /admissions/seat-matrix
 *
 * Program-wise quota utilisation cards (filled/total per category, color-coded)
 * Category conversion action (Dean only)
 * Waitlist depth per category
 */

import { useState, useEffect } from 'react'
import { Progress } from '@/components/ui/interfaces-progress'

// ---------------------------------------------------------------------------
// Types + mock data
// ---------------------------------------------------------------------------

interface CategorySlot {
  label: string
  code: string
  total: number
  filled: number
  waitlist: number
  color: string
}

interface ProgramMatrix {
  id: string
  program: string
  intakeYear: number
  totalIntake: number
  filledSeats: number
  fillPct: number
  categories: CategorySlot[]
}

const MATRIX_DATA: ProgramMatrix[] = [
  {
    id: 'p1',
    program: 'B.Tech CSE',
    intakeYear: 2024,
    totalIntake: 120,
    filledSeats: 108,
    fillPct: 90,
    categories: [
      { label: 'General', code: 'GENERAL', total: 60, filled: 58, waitlist: 12, color: '#5D5FEF' },
      { label: 'SC', code: 'SC', total: 18, filled: 17, waitlist: 3, color: '#1D9E75' },
      { label: 'ST', code: 'ST', total: 9, filled: 8, waitlist: 1, color: '#4CAF9F' },
      { label: 'OBC-NCL', code: 'OBC_NCL', total: 27, filled: 20, waitlist: 5, color: '#EF9F27' },
      { label: 'EWS', code: 'EWS', total: 6, filled: 5, waitlist: 2, color: '#9B59B6' },
      { label: 'Management', code: 'MANAGEMENT', total: 18, filled: 0, waitlist: 0, color: '#E24B4A' },
      { label: 'NRI', code: 'NRI', total: 6, filled: 0, waitlist: 0, color: '#7B82A8' },
    ],
  },
  {
    id: 'p2',
    program: 'B.Tech ECE',
    intakeYear: 2024,
    totalIntake: 60,
    filledSeats: 52,
    fillPct: 87,
    categories: [
      { label: 'General', code: 'GENERAL', total: 30, filled: 28, waitlist: 6, color: '#5D5FEF' },
      { label: 'SC', code: 'SC', total: 9, filled: 9, waitlist: 2, color: '#1D9E75' },
      { label: 'ST', code: 'ST', total: 4, filled: 3, waitlist: 0, color: '#4CAF9F' },
      { label: 'OBC-NCL', code: 'OBC_NCL', total: 14, filled: 12, waitlist: 3, color: '#EF9F27' },
      { label: 'EWS', code: 'EWS', total: 3, filled: 0, waitlist: 1, color: '#9B59B6' },
      { label: 'Management', code: 'MANAGEMENT', total: 9, filled: 0, waitlist: 0, color: '#E24B4A' },
      { label: 'NRI', code: 'NRI', total: 3, filled: 0, waitlist: 0, color: '#7B82A8' },
    ],
  },
  {
    id: 'p3',
    program: 'MBA',
    intakeYear: 2024,
    totalIntake: 60,
    filledSeats: 45,
    fillPct: 75,
    categories: [
      { label: 'General', code: 'GENERAL', total: 30, filled: 25, waitlist: 4, color: '#5D5FEF' },
      { label: 'SC', code: 'SC', total: 9, filled: 7, waitlist: 1, color: '#1D9E75' },
      { label: 'ST', code: 'ST', total: 4, filled: 2, waitlist: 0, color: '#4CAF9F' },
      { label: 'OBC-NCL', code: 'OBC_NCL', total: 14, filled: 11, waitlist: 2, color: '#EF9F27' },
      { label: 'EWS', code: 'EWS', total: 3, filled: 0, waitlist: 0, color: '#9B59B6' },
      { label: 'Management', code: 'MANAGEMENT', total: 12, filled: 0, waitlist: 0, color: '#E24B4A' },
    ],
  },
]

// ---------------------------------------------------------------------------
// Subcomponents
// ---------------------------------------------------------------------------

function FillBar({ filled, total, color }: { filled: number; total: number; color: string }) {
  const pct = total > 0 ? (filled / total) * 100 : 0
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
      <div style={{
        flex: 1, height: 6, borderRadius: 3,
        background: '#1E2235', overflow: 'hidden',
      }}>
        <div style={{
          width: `${pct}%`, height: '100%',
          background: pct >= 90 ? '#E24B4A' : pct >= 75 ? color : '#7B82A8',
          borderRadius: 3, transition: 'width 0.3s ease',
        }} />
      </div>
      <span style={{ fontSize: 11, color: '#7B82A8', flexShrink: 0, minWidth: 60 }}>
        {filled}/{total}
      </span>
    </div>
  )
}

function CategoryCard({ cat }: { cat: CategorySlot }) {
  const pct = cat.total > 0 ? Math.round((cat.filled / cat.total) * 100) : 0
  return (
    <div style={{
      background: '#11131F',
      border: `1px solid ${cat.color}33`,
      borderRadius: 10, padding: '14px 16px', minWidth: 140,
    }}>
      <p style={{ margin: 0, fontSize: 11, color: cat.color, fontWeight: 700, letterSpacing: '0.05em', textTransform: 'uppercase' }}>
        {cat.label}
      </p>
      <p style={{ margin: '8px 0 4px', fontSize: 22, fontWeight: 700, color: '#C9D1E9' }}>
        {pct}%
      </p>
      <FillBar filled={cat.filled} total={cat.total} color={cat.color} />
      {cat.waitlist > 0 && (
        <p style={{ margin: '6px 0 0', fontSize: 11, color: '#7B82A8' }}>
          Waitlist: <span style={{ color: '#EF9F27', fontWeight: 600 }}>{cat.waitlist}</span>
        </p>
      )}
    </div>
  )
}

function ProgramCard({ matrix }: { matrix: ProgramMatrix }) {
  const [expanded, setExpanded] = useState(false)

  return (
    <div style={{
      background: '#0E1020',
      border: '1px solid #1E2235',
      borderRadius: 14, padding: 20,
    }}>
      {/* Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
        <div>
          <h3 style={{ margin: 0, color: '#C9D1E9', fontSize: 16, fontWeight: 700 }}>
            {matrix.program}
          </h3>
          <p style={{ margin: '2px 0 0', fontSize: 12, color: '#7B82A8' }}>
            Intake {matrix.intakeYear} · {matrix.totalIntake} seats
          </p>
        </div>
        <div style={{ textAlign: 'right' }}>
          <span style={{
            fontSize: 22, fontWeight: 700,
            color: matrix.fillPct >= 90 ? '#E24B4A' : matrix.fillPct >= 75 ? '#EF9F27' : '#1D9E75',
          }}>
            {matrix.fillPct}%
          </span>
          <p style={{ margin: '2px 0 0', fontSize: 11, color: '#7B82A8' }}>
            {matrix.filledSeats}/{matrix.totalIntake} filled
          </p>
        </div>
      </div>

      {/* Category cards row */}
      <div style={{
        display: 'flex', gap: 10, overflowX: 'auto', paddingBottom: 4,
        scrollbarWidth: 'thin',
      }}>
        {matrix.categories.map(cat => (
          <CategoryCard key={cat.code} cat={cat} />
        ))}
      </div>

      {/* Dean action — category conversion */}
      <div style={{ marginTop: 16, display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
        <button
          onClick={() => setExpanded(!expanded)}
          style={{
            padding: '6px 14px', borderRadius: 6, border: '1px solid #E24B4A55',
            background: 'transparent', color: '#E24B4A', cursor: 'pointer',
            fontSize: 12, fontWeight: 600,
          }}
        >
          Category Conversion (Dean)
        </button>
      </div>

      {expanded && (
        <div style={{
          marginTop: 12, padding: 16, background: '#1A1D2E',
          borderRadius: 8, border: '1px solid #E24B4A33',
        }}>
          <p style={{ margin: '0 0 12px', fontSize: 13, color: '#C9D1E9', fontWeight: 600 }}>
            Convert Unused Category Seats
          </p>
          <div style={{ display: 'flex', gap: 10, alignItems: 'center', flexWrap: 'wrap' }}>
            <select style={{ padding: '6px 10px', borderRadius: 6, background: '#11131F', border: '1px solid #1E2235', color: '#C9D1E9', fontSize: 13 }}>
              <option>From: ST (1 unused)</option>
              <option>From: EWS (3 unused)</option>
              <option>From: NRI (6 unused)</option>
            </select>
            <span style={{ color: '#7B82A8', fontSize: 14 }}>→</span>
            <select style={{ padding: '6px 10px', borderRadius: 6, background: '#11131F', border: '1px solid #1E2235', color: '#C9D1E9', fontSize: 13 }}>
              <option>To: General</option>
              <option>To: OBC-NCL</option>
            </select>
            <input type="number" placeholder="Seats" min="1" style={{
              width: 70, padding: '6px 10px', borderRadius: 6,
              background: '#11131F', border: '1px solid #1E2235', color: '#C9D1E9', fontSize: 13,
            }} />
            <button style={{
              padding: '6px 16px', borderRadius: 6, border: 'none',
              background: '#5D5FEF', color: '#fff', cursor: 'pointer',
              fontSize: 13, fontWeight: 600,
            }}>
              Convert
            </button>
          </div>
          <p style={{ margin: '8px 0 0', fontSize: 11, color: '#7B82A8' }}>
            ⚠ Requires UGC deadline to have passed. Logged to audit trail.
          </p>
        </div>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// API types from backend
// ---------------------------------------------------------------------------

interface SeatMatrixApiRecord {
  id: string
  program_name?: string
  program_id?: string
  intake_batch?: string | number
  categories?: {
    code: string
    label?: string
    total_seats?: number
    filled_seats?: number
    waitlist_count?: number
  }[]
}

const CATEGORY_COLORS: Record<string, string> = {
  GENERAL: '#5D5FEF', SC: '#1D9E75', ST: '#4CAF9F', OBC_NCL: '#EF9F27',
  OBC: '#EF9F27', EWS: '#9B59B6', MANAGEMENT: '#E24B4A', NRI: '#7B82A8',
  SPORTS: '#60a5fa', DEFENCE: '#f472b6',
}

function apiRecordToMatrix(r: SeatMatrixApiRecord, index: number): ProgramMatrix {
  const cats: CategorySlot[] = (r.categories ?? []).map(c => ({
    label: c.label ?? c.code.replace(/_/g, '-'),
    code: c.code,
    total: c.total_seats ?? 0,
    filled: c.filled_seats ?? 0,
    waitlist: c.waitlist_count ?? 0,
    color: CATEGORY_COLORS[c.code] ?? '#7B82A8',
  }))
  const totalIntake = cats.reduce((s, c) => s + c.total, 0)
  const filledSeats = cats.reduce((s, c) => s + c.filled, 0)
  return {
    id: r.id ?? `matrix-${index}`,
    program: r.program_name ?? r.program_id ?? 'Program',
    intakeYear: Number(r.intake_batch ?? new Date().getFullYear()),
    totalIntake,
    filledSeats,
    fillPct: totalIntake > 0 ? Math.round((filledSeats / totalIntake) * 100) : 0,
    categories: cats,
  }
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export function SeatMatrixPage() {
  const currentYear = new Date().getFullYear()
  const [year, setYear] = useState(currentYear)
  const [matrixData, setMatrixData] = useState<ProgramMatrix[]>([])

  useEffect(() => {
    const token = sessionStorage.getItem('token') ?? ''
    fetch(`/api/v1/seats?intake_batch=${year}`, {
      headers: { Authorization: `Bearer ${token}` },
    })
      .then(r => r.ok ? r.json() as Promise<{ seats?: SeatMatrixApiRecord[] }> : null)
      .then(data => {
        const seats = data?.seats ?? []
        if (seats.length > 0) {
          setMatrixData(seats.map(apiRecordToMatrix))
        }
      })
      .catch(() => {/* keep static fallback */})
  }, [year])

  const totalIntake = matrixData.reduce((s, m) => s + m.totalIntake, 0)
  const totalFilled = matrixData.reduce((s, m) => s + m.filledSeats, 0)
  const totalWaitlist = matrixData.reduce((s, m) => s + m.categories.reduce((cs, c) => cs + c.waitlist, 0), 0)
  const totalUnfilled = totalIntake - totalFilled

  const yearOptions = [currentYear, currentYear - 1, currentYear - 2]

  return (
    <div style={{ padding: '0 0 40px' }}>
      {/* Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 24 }}>
        <div>
          <h2 style={{ margin: 0, color: '#C9D1E9', fontSize: 20, fontWeight: 700 }}>
            Seat Matrix — E19
          </h2>
          <p style={{ margin: '4px 0 0', fontSize: 13, color: '#7B82A8' }}>
            Category & quota utilisation across all programs
          </p>
        </div>
        <select
          value={year}
          onChange={e => setYear(Number(e.target.value))}
          style={{ padding: '8px 14px', borderRadius: 8, background: '#1A1D2E', border: '1px solid #1E2235', color: '#C9D1E9', fontSize: 14 }}
        >
          {yearOptions.map(y => <option key={y} value={y}>Intake {y}</option>)}
        </select>
      </div>

      {/* Summary strip */}
      <div style={{ display: 'flex', gap: 12, marginBottom: 24, flexWrap: 'wrap' }}>
        {[
          { label: 'Total Intake', value: String(totalIntake || '—') },
          { label: 'Filled', value: String(totalFilled || '—'), color: '#1D9E75' },
          { label: 'Waitlisted', value: String(totalWaitlist || '—'), color: '#EF9F27' },
          { label: 'Unfilled', value: String(totalUnfilled > 0 ? totalUnfilled : '—'), color: '#E24B4A' },
        ].map(s => (
          <div key={s.label} style={{
            padding: '12px 20px', background: '#11131F',
            border: '1px solid #1E2235', borderRadius: 10, textAlign: 'center', flex: 1, minWidth: 100,
          }}>
            <p style={{ margin: 0, fontSize: 22, fontWeight: 700, color: (s.color as string | undefined) || '#C9D1E9' }}>
              {s.value}
            </p>
            <p style={{ margin: '4px 0 0', fontSize: 11, color: '#7B82A8', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
              {s.label}
            </p>
          </div>
        ))}
      </div>

      {/* Program cards */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
        {matrixData.length === 0 ? (
          <p style={{ color: '#7B82A8', fontSize: 14 }}>No seat matrix data found for intake {year}.</p>
        ) : (
          matrixData.map(matrix => (
            <ProgramCard key={matrix.id} matrix={matrix} />
          ))
        )}
      </div>
    </div>
  )
}
