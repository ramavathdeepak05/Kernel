/**
 * sync.ts — Background sync: push pending offline attendance marks to the API
 *
 * Called automatically on `online` event and when the AttendanceMarking view mounts.
 * Uses /api/v1/attendance/bulk-sync which is idempotent (server deduplicates by
 * mark UUID, ignores duplicates with HTTP 200).
 */
import {
  getUnsyncedMarks,
  markSynced,
  incrementFailCount,
  pendingSyncCount,
  type PendingMark,
} from './offline-store'

const MAX_FAIL_COUNT = 5   // abandon marks after this many consecutive failures

interface SyncResult {
  synced: number
  failed: number
  pending: number
}

/**
 * Attempt to sync all pending offline marks.
 * Returns a summary — callers can update UI badges.
 */
export async function syncPendingMarks(
  tenantId: string,
  authToken: string,
): Promise<SyncResult> {
  const pending = await getUnsyncedMarks()
  if (!pending.length) return { synced: 0, failed: 0, pending: 0 }

  // Filter out marks that have exceeded the retry limit
  const retryable = pending.filter((m) => m.failCount < MAX_FAIL_COUNT)
  if (!retryable.length) return { synced: 0, failed: pending.length, pending: pending.length }

  let syncedIds: string[] = []
  let failedIds: string[] = []

  try {
    const res = await fetch('/api/v1/attendance/bulk-sync', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${authToken}`,
        'X-Tenant-ID': tenantId,
      },
      body: JSON.stringify({
        marks: retryable.map((m: PendingMark) => ({
          id: m.id,
          session_id: m.sessionId,
          student_id: m.studentId,
          status: m.status,
          marked_at: m.markedAt,
        })),
      }),
    })

    if (res.ok) {
      const data: { accepted: string[]; rejected: string[] } = await res.json()
      syncedIds = data.accepted ?? retryable.map((m) => m.id)
      failedIds = data.rejected ?? []
    } else {
      // Transient server error — increment fail count on all
      failedIds = retryable.map((m) => m.id)
    }
  } catch {
    // Network error — still offline
    failedIds = retryable.map((m) => m.id)
  }

  if (syncedIds.length) await markSynced(syncedIds)
  if (failedIds.length) await incrementFailCount(failedIds)

  const remaining = await pendingSyncCount()
  return { synced: syncedIds.length, failed: failedIds.length, pending: remaining }
}

/**
 * Register a one-shot online-event listener that triggers sync.
 * Safe to call multiple times — removes the listener after first fire.
 */
export function syncWhenOnline(tenantId: string, authToken: string): void {
  if (navigator.onLine) {
    syncPendingMarks(tenantId, authToken)
    return
  }
  const handler = () => {
    window.removeEventListener('online', handler)
    syncPendingMarks(tenantId, authToken)
  }
  window.addEventListener('online', handler)
}
