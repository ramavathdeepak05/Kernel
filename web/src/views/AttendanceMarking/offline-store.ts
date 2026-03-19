/**
 * offline-store.ts — IndexedDB schema for offline attendance marking (Dexie)
 *
 * Stores pending attendance marks locally when network is unavailable.
 * Marks are synced to /api/v1/attendance/bulk-sync when connectivity resumes.
 * Feature flag: academics.offline_attendance_pwa
 */
import Dexie, { type Table } from 'dexie'

export interface PendingMark {
  id: string               // local UUID (crypto.randomUUID)
  sessionId: string
  studentId: string
  status: 'PRESENT' | 'ABSENT' | 'LATE'
  markedAt: string         // ISO 8601 UTC timestamp
  synced: 0 | 1           // Dexie where() equality needs number, not boolean
  failCount: number        // number of failed sync attempts
}

export interface CachedSession {
  sessionId: string
  courseCode: string
  courseName: string
  date: string             // YYYY-MM-DD
  cachedAt: string         // ISO timestamp — used for TTL check
  students: CachedStudent[]
}

export interface CachedStudent {
  studentId: string
  rollNumber: string
  fullName: string
}

class OfflineAttendanceStore extends Dexie {
  pendingMarks!: Table<PendingMark, string>
  cachedSessions!: Table<CachedSession, string>

  constructor() {
    super('alis-attendance-offline')
    this.version(1).stores({
      pendingMarks:   'id, sessionId, markedAt, synced, failCount',
      cachedSessions: 'sessionId, courseCode, cachedAt',
    })
  }
}

export const db = new OfflineAttendanceStore()

/** Add or update a mark in the local store. */
export async function markAttendanceOffline(mark: Omit<PendingMark, 'synced' | 'failCount'>): Promise<void> {
  await db.pendingMarks.put({ ...mark, synced: 0, failCount: 0 })
}

/** Return all unsynced marks (ordered oldest-first for idempotent bulk sync). */
export async function getUnsyncedMarks(): Promise<PendingMark[]> {
  return db.pendingMarks.where('synced').equals(0).sortBy('markedAt')
}

/** Mark a list of IDs as synced. */
export async function markSynced(ids: string[]): Promise<void> {
  await db.pendingMarks.where('id').anyOf(ids).modify({ synced: 1 })
}

/** Increment fail count on marks that failed to sync. */
export async function incrementFailCount(ids: string[]): Promise<void> {
  await db.pendingMarks.where('id').anyOf(ids).modify((m: PendingMark) => {
    m.failCount += 1
  })
}

/** Cache the student roster for a session (pre-fetch while online). */
export async function cacheSession(session: CachedSession): Promise<void> {
  await db.cachedSessions.put(session)
}

/** Retrieve a cached session, or null if not cached / stale (>1h). */
export async function getCachedSession(sessionId: string): Promise<CachedSession | null> {
  const row = await db.cachedSessions.get(sessionId)
  if (!row) return null
  const age = Date.now() - new Date(row.cachedAt).getTime()
  if (age > 3_600_000) return null   // 1-hour TTL
  return row
}

/** Pending sync count — used to badge the UI. */
export async function pendingSyncCount(): Promise<number> {
  return db.pendingMarks.where('synced').equals(0).count()
}
