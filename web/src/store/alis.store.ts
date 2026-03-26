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
import type { TaskGroup } from '../lib/agent-gateway'

const MESSAGE_CAP = 50

export interface ChatMessage {
  id: string
  role: 'agent' | 'user'
  text: string
  timestamp: Date
  /** Which canvas view was active when this message was sent — used for thread dividers */
  sourceView: CanvasView | null
  /** Optional chips for action-card message type */
  chips?: string[]
  /** Canvas action to execute when this message is displayed */
  canvasAction?: CanvasAction | null
  /** Structured task cockpit — rendered as action cockpit when present (Phase C) */
  tasks?: TaskGroup[]
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
    /**
     * Opaque session hint produced by the backend on each response.
     * Echoed back in input_data.agent_context on the next invocation
     * so the agent can resolve references like "open the first one".
     * Not displayed to the user.
     */
    agentContext: string | null
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
  addMessage: (msg: Omit<ChatMessage, 'id' | 'timestamp' | 'sourceView'>) => void
  setAgentTyping: (typing: boolean) => void
  setQuickActions: (actions: string[]) => void
  setAgentContext: (label: string) => void
  setAgentContextHint: (hint: string | null) => void
  clearPendingAction: () => void
}

let messageCounter = 0

export const useALISStore = create<ALISStore>((set, get) => ({
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
    quickActions: ['What should I do today?', 'Show urgent items', 'Show overdue items'],
    agentContext: null,
  },
  chat: {
    messages: [
      {
        id: 'welcome',
        role: 'agent',
        text: "Good morning. I'm watching your dashboard. 3 approvals are urgent — hall ticket batch expires in 3h 32m.",
        timestamp: new Date(),
        sourceView: 'approval_queue',
      },
    ],
  },

  setCanvasView: (view, module, filters = {}) =>
    set((state) => ({
      canvas: {
        ...state.canvas,
        view,
        module,
        filters,
        highlightedItemId: null,
        scrollToItemId: null,
      },
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
      canvas: {
        ...state.canvas,
        highlightedItemId: null,
        selectedItemIds: [],
        scrollToItemId: null,
      },
    })),

  dispatchAgentAction: (action) =>
    set((state) => ({
      agent: { ...state.agent, pendingAction: action },
    })),

  addMessage: (msg) =>
    set((state) => {
      const newMsg: ChatMessage = {
        ...msg,
        id: `msg-${++messageCounter}-${Date.now()}`,
        timestamp: new Date(),
        sourceView: state.canvas.view,
      }
      const updated = [...state.chat.messages, newMsg]
      // Cap at MESSAGE_CAP — oldest messages dropped first
      const capped =
        updated.length > MESSAGE_CAP
          ? updated.slice(updated.length - MESSAGE_CAP)
          : updated
      return { chat: { messages: capped } }
    }),

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

  setAgentContextHint: (hint) =>
    set((state) => ({
      agent: { ...state.agent, agentContext: hint },
    })),

  clearPendingAction: () =>
    set((state) => ({
      agent: { ...state.agent, pendingAction: null },
    })),
}))
