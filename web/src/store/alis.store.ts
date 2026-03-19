/**
 * ALIS Zustand Store — Canvas + Agent + Chat state
 *
 * The agent rail and primary canvas share this single store.
 * Never put canvas navigation state in local component state —
 * the agent must be able to drive the canvas from the rail.
 *
 * Reference: ALIS-skills/references/frontend.md §4, §5
 */

import { create } from 'zustand'
import type { CanvasAction, CanvasView, ALISModule } from '../lib/canvas-actions'

export interface ChatMessage {
  id: string
  role: 'agent' | 'user'
  text: string
  timestamp: Date
  /** Optional chips for action-card message type */
  chips?: string[]
  /** Canvas action to execute when this message is displayed */
  canvasAction?: CanvasAction | null
}

export interface ALISStore {
  // ── Canvas state ──────────────────────────────────────────────────
  canvas: {
    view: CanvasView
    module: ALISModule
    filters: Record<string, unknown>
    highlightedItemId: string | null
    selectedItemIds: string[]
    scrollToItemId: string | null
  }

  // ── Agent awareness ───────────────────────────────────────────────
  agent: {
    contextLabel: string
    pendingAction: CanvasAction | null
    isTyping: boolean
    quickActions: string[]
  }

  // ── Chat thread ───────────────────────────────────────────────────
  chat: {
    messages: ChatMessage[]
  }

  // ── Actions ───────────────────────────────────────────────────────
  setCanvasView: (view: CanvasView, module: ALISModule, filters?: Record<string, unknown>) => void
  highlightItem: (id: string) => void
  highlightMultiple: (ids: string[]) => void
  clearHighlight: () => void
  dispatchAgentAction: (action: CanvasAction) => void
  addMessage: (msg: Omit<ChatMessage, 'id' | 'timestamp'>) => void
  setAgentTyping: (typing: boolean) => void
  setQuickActions: (actions: string[]) => void
  setAgentContext: (label: string) => void
  clearPendingAction: () => void
}

let messageCounter = 0

export const useALISStore = create<ALISStore>((set) => ({
  canvas: {
    view: 'approval_queue',
    module: 'admissions',
    filters: {},
    highlightedItemId: null,
    selectedItemIds: [],
    scrollToItemId: null,
  },
  agent: {
    contextLabel: 'Ready',
    pendingAction: null,
    isTyping: false,
    quickActions: [],
  },
  chat: {
    messages: [
      {
        id: 'welcome',
        role: 'agent',
        text: "Good morning. I'm watching your dashboard. 3 approvals are urgent — hall ticket batch expires in 3h 32m.",
        timestamp: new Date(),
      },
    ],
  },

  setCanvasView: (view, module, filters = {}) =>
    set((state) => ({
      canvas: { ...state.canvas, view, module, filters, highlightedItemId: null, scrollToItemId: null },
    })),

  highlightItem: (id) =>
    set((state) => ({
      canvas: { ...state.canvas, highlightedItemId: id, scrollToItemId: id },
    })),

  highlightMultiple: (ids) =>
    set((state) => ({
      canvas: { ...state.canvas, selectedItemIds: ids, highlightedItemId: ids[0] ?? null },
    })),

  clearHighlight: () =>
    set((state) => ({
      canvas: { ...state.canvas, highlightedItemId: null, selectedItemIds: [], scrollToItemId: null },
    })),

  dispatchAgentAction: (action) =>
    set((state) => ({
      agent: { ...state.agent, pendingAction: action },
    })),

  addMessage: (msg) =>
    set((state) => ({
      chat: {
        messages: [
          ...state.chat.messages,
          { ...msg, id: `msg-${++messageCounter}-${Date.now()}`, timestamp: new Date() },
        ],
      },
    })),

  setAgentTyping: (typing) =>
    set((state) => ({
      agent: { ...state.agent, isTyping: typing },
    })),

  setQuickActions: (actions) =>
    set((state) => ({
      agent: { ...state.agent, quickActions: actions },
    })),

  setAgentContext: (label) =>
    set((state) => ({
      agent: { ...state.agent, contextLabel: label },
    })),

  clearPendingAction: () =>
    set((state) => ({
      agent: { ...state.agent, pendingAction: null },
    })),
}))
