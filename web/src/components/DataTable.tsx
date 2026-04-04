/**
 * DataTable — high-density ALIS data table
 * Reference: ALIS-skills/references/frontend.md §10
 *
 * On mobile (<768px), wrap in a MobileCardList instead.
 * Never force horizontal scroll.
 */

import type { CSSProperties, ReactNode } from 'react'

export interface Column<T> {
  key: keyof T | string
  label: string
  render?: (row: T) => ReactNode
  width?: string
}

export interface DataTableProps<T extends { id: string }> {
  columns: Column<T>[]
  rows: T[]
  onRowClick?: (row: T) => void
  highlightedId?: string | null
  gridTemplateColumns?: string
  title?: string
}

export function DataTable<T extends { id: string }>({
  columns,
  rows,
  onRowClick,
  highlightedId,
  gridTemplateColumns,
}: DataTableProps<T>) {
  const cols = gridTemplateColumns ?? columns.map((c) => c.width ?? '1fr').join(' ')

  const headerStyle: CSSProperties = {
    display: 'grid',
    gridTemplateColumns: cols,
    background: 'var(--color-background-secondary)',
    padding: '6px 12px',
    borderBottom: 'var(--border)',
  }

  const rowStyle = (isHighlighted: boolean, isLast: boolean): CSSProperties => ({
    display: 'grid',
    gridTemplateColumns: cols,
    padding: '8px 12px',
    borderBottom: isLast ? 'none' : 'var(--border)',
    background: isHighlighted
      ? 'var(--color-background-secondary)'
      : 'var(--color-background-primary)',
    borderLeft: isHighlighted ? '2.5px solid var(--alis-teal)' : '2.5px solid transparent',
    alignItems: 'center',
    cursor: onRowClick ? 'pointer' : 'default',
    transition: 'background 0.12s',
  })

  return (
    <div
      style={{
        border: 'var(--border)',
        borderRadius: 'var(--radius-md)',
        overflow: 'hidden',
      }}
    >
      {/* Header */}
      <div style={headerStyle}>
        {columns.map((col) => (
          <span
            key={String(col.key)}
            style={{
              fontSize: 10,
              fontWeight: 500,
              color: 'var(--color-text-secondary)',
              textTransform: 'uppercase',
              letterSpacing: '0.04em',
            }}
          >
            {col.label}
          </span>
        ))}
      </div>

      {/* Rows */}
      {rows.length === 0 ? (
        <div style={{ padding: '20px 12px', textAlign: 'center', fontSize: 12, color: 'var(--color-text-secondary)' }}>
          No records
        </div>
      ) : (
        rows.map((row, i) => (
          <div
            key={row.id}
            id={`qi-${row.id}`}
            style={rowStyle(highlightedId === row.id, i === rows.length - 1)}
            onClick={() => onRowClick?.(row)}
          >
            {columns.map((col) => (
              <div key={String(col.key)} style={{ fontSize: 12, color: 'var(--color-text-primary)' }}>
                {col.render
                  ? col.render(row)
                  : String((row as Record<string, unknown>)[String(col.key)] ?? '')}
              </div>
            ))}
          </div>
        ))
      )}
    </div>
  )
}
