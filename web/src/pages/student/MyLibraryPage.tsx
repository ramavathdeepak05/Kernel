/**
 * My Library — Student view
 *
 * Shows:
 * - Currently borrowed books
 * - Due dates + overdue warnings
 * - Fine status
 * - Book search / reservation
 */

import { useState, useEffect } from 'react'
import { Badge } from '../../components/Badge'

const API = import.meta.env.VITE_API_URL || "/api/v1";

interface BorrowedBook {
  id: string; title: string; author: string; due_date: string;
  is_overdue: boolean; fine_amount: number;
}

export function MyLibraryPage() {
  const [books, setBooks] = useState<BorrowedBook[]>([])

  useEffect(() => {
    const token = sessionStorage.getItem("token")
    if (!token) return
    fetch(`${API}/student-services/library/my-borrowings`, {
      headers: { Authorization: `Bearer ${token}` },
    })
      .then(r => r.ok ? r.json() : { items: [] })
      .then(data => {
        setBooks((data.items ?? data ?? []).map((b: Record<string, unknown>) => ({
          id: String(b.id ?? ''), title: String(b.title ?? b.book_title ?? ''),
          author: String(b.author ?? ''), due_date: String(b.due_date ?? ''),
          is_overdue: Boolean(b.is_overdue ?? false),
          fine_amount: Number(b.fine_amount ?? 0),
        })))
      })
  }, [])

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      <h1 style={{ fontSize: 15, fontWeight: 600 }}>My Library</h1>

      {books.length === 0 ? (
        <p style={{ textAlign: 'center', color: 'var(--color-text-secondary)', padding: 40 }}>
          No books currently borrowed.
        </p>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          {books.map(b => (
            <div key={b.id} style={{
              display: 'grid', gridTemplateColumns: '2fr 1.5fr 120px 80px',
              gap: 8, padding: '10px 14px', border: 'var(--border)', borderRadius: 8, alignItems: 'center',
            }}>
              <span style={{ fontSize: 13, fontWeight: 500 }}>{b.title}</span>
              <span style={{ fontSize: 12, color: 'var(--color-text-secondary)' }}>{b.author}</span>
              <span style={{ fontSize: 12, color: b.is_overdue ? '#E24B4A' : 'var(--color-text-secondary)' }}>
                Due: {b.due_date}
              </span>
              {b.is_overdue ? (
                <Badge variant="red">₹{b.fine_amount} fine</Badge>
              ) : (
                <Badge variant="green">On time</Badge>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
