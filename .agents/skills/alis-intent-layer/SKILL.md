---
name: alis-intent-layer
description: |
  ALIS Intent Layer architecture and implementation patterns. Use when shifting UI from traditional buttons/forms to proactive AI-driven intent execution, Command Bars (Omnibox), and Unified Review Queues. Covers IntentStateRegistry, NextBestAction frontend components, and AIGateway intent translation. Trigger keywords: intent, proactive UI, omnibox, command bar, next best action, unified review queue, intent state, conversational UI, conversational execution, chat intent.
---

# ALIS Intent-Driven Architecture (The Intent Layer)

You are the ALIS UX/UI AI Agent and Architect. The ALIS frontend is transitioning from a "System of Record" (nested menus, static forms, and buttons) to an **"Autonomous System of Engagement"** (proactive guidance, task queues, and natural language command execution). 

## Core Philosophy: The Intent Layer

1. **Never make the user search:** If the system knows what the user needs to do (e.g., upload a missing document), surface it immediately via a `NextBestAction` component.
2. **Never make the user fill out a 50-field form:** Let the user express their intent via natural language in an **Omnibox (Command Bar)**. Use the ALIS `AIGateway` to translate that intent into structured payloads for backend Celery execution.
3. **The UI is a Queue and a Chat:** Routine tasks happen autonomously via Celery agents. The human UI is reduced to handling AI-flagged exceptions (a Unified Review Queue) and initiating complex workflows (Chat/Command Bar).

---

## The 3 Pillars of the Intent Layer

### 1. The Intent State Tracker (Backend)
Instead of forcing users to explicitly create "Tasks", the AI Agents (running via Celery and Domain Events) implicitly register "Pending Intents".

* **Concept:** `IntentStateRegistry`
* **Workflow:**
    1. A `DomainEvent` fires (e.g., `FinancialAid.RequestSubmitted`).
    2. Background `Intake Quality Agent` notices a missing PII document (e.g., tax return).
    3. The Celery pipeline registers an `IntentState` against the student: `{"type": "UPLOAD_DOCUMENT", "doc_type": "tax_return", "status": "PENDING"}`.

### 2. The Next Best Action (Frontend Proactive UI)
A React dashboard component that polls the `IntentStateRegistry`.

* **Behavior:** When the UI detects a pending intent, it hides standard navigation and aggressively surfaces a contextual action card.
* **Example UX:** *"Action Required: Upload your 2025 Tax Return to complete your Financial Aid Application."* + `[Upload Document]` button. 
* **Result:** The user completes their goal immediately without navigating through `Finance -> Aid -> Documents`.

### 3. The Omnibox / Universal Command Parser (Conversational Execution)
Replaces complex creation forms and the traditional "swivel-chair" navigation. 

* **Endpoint:** `POST /api/intent/execute`
* **Workflow:**
    1. User types in the UI Command Bar: *"Defer Student 12345 to Fall 2026."*
    2. The endpoint passes the raw string to `AIGateway.invoke` with an intent-parsing prompt.
    3. The AI analyzes the intent and outputs a structured JSON payload: 
       ```json
       {
         "action": "enrollment.defer",
         "entity_id": "12345",
         "params": {"term": "Fall 2026"},
         "confidence_tier": "HIGH",
         "state_impact": "DRAFT"
       }
       ```
    4. ALIS routes this to the relevant Academic module handler.
    5. The UI renders a dynamic confirmation card based on the payload: *"Ready to defer Student 12345 to Fall 2026. This will trigger a recalculation of their Fall scholarship."* + `[Confirm Execute]`

---

## Implementation Rules (Guardrails)

- **Advisory Only (E00-S06):** The Omnibox and Intent Parser **never** directly mutate state. They always return `state_impact: "DRAFT"` payloads. The human user must explicitly click a `[Confirm Execute]` button on the generated UI, which then triggers the final `execute_transaction` via standard REST patterns.
- **Context Injection:** When evaluating user intent in the `AIGateway`, the pipeline MUST inject the recent `AuditLedger` and `DomainEvent` history for the active session/entity to give the AI "telepathic" contextual awareness (like ve.ai).
- **Graceful Fallbacks (Chat):** If the user provides incomplete data in the Omnibox (*"Enroll student 12345 in BIO 101"* -> missing lab section), the system returns a `DRAFT` response requesting clarification. The UI renders this as a chat bubble: *"BIO 101 requires a lab. Do you prefer Tuesday 2 PM or Thursday 9 AM?"*
- **Micro-Interactions over Page Loads:** Build UI around dynamic cards and chat bubbles, preventing full page redirects whenever possible.
