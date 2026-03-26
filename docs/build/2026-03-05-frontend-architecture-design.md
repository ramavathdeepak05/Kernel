# ALIS Frontend Architecture Design

**Date:** 2026-03-05
**Topic:** Frontend Aesthetic, Layout, and State Management

## 1. Context
ALIS is an AI-assisted Institutional Operating System. It is an active system relying on Celery tasks and event-driven automation for core university processes. Staff interact with ALIS primarily to handle exceptions, configure policies, and approve high-stakes actions via AI Wizards. 

The frontend needs to convey extreme reliability, trust, and premium enterprise grade execution. 

## 2. Aesthetic Direction: Corporate & Refined (Frost/Glass)
We are adopting a clean, premium "white-glove" aesthetic utilizing Frost/Glass morphisms.
- **Colors:** Deep slate text on `hsl(0 0% 98%)` ultra-light backgrounds. Primary functional colors are cohesive (e.g., deep enterprise blue).
- **Surfaces:** Generous whitespace, rounded borders (`0.75rem`), and subtle `backdrop-blur` for modal and floating elements representing depth. High-end shadows (`0 4px 20px -2px rgba(0,0,0,0.04)`).
- **Typography:** "Outfit" (display) headers for extreme legibility and style, and "Plus Jakarta Sans" for dense data UI. Avoid generic AI tool tropes.
- **Micro-interactions:** Restrained CSS transitions. Items slide and fade into view smoothly but deterministically without feeling bouncy or chaotic.

## 3. Layout & Navigation: Sidebar Module (Traditional Navigation)
ALIS consists of heavy Epic modules (Admissions, Academics, Finance, Governance).
- **Navigation:** Persistent left-hand sidebar grouping Epic modules. Keeps context clear.
- **Header:** Contains Omni-search, notification center for routing exceptions, and User Avatar/Role.
- **Module Dashboards:** Each module uses a central dashboard to visually outline its active pipelines (e.g., Lead -> Accepted), with tiles for running Wizards and handling exception queues.

## 4. State Management
A clear separation of concerns between Server State and UI State:
- **Server State (`@tanstack/react-query`):** Manages fetching, caching, synchronizing, and updating the state from the FastAPI backend. Used entirely for data like Applicant Lists, Workflow Exceptions, Eligibility Scores. Handles automatic loading/error handling.
- **Client State (`zustand`):** Ultra-lightweight global store for ephemeral UI state (e.g., Omni-Search open/closed, Sidebar expanded/collapsed, multi-step local wizard draft states before submission).

## 5. Role-Based Access Control (RBAC)
The UI is strictly determined by the user's assigned role (extracted from the JWT payload during login).
- **Navigation Guarding:** The Sidebar will dynamically render only the modules (E01, E04, etc.) the user is authorized to access.
- **Wizard Guarding:** Inside module dashboards, `RoleGuard` wrapper components will selectively render Wizard action buttons. 
  - *Example:* An "Admissions Clerk" can run the Eligibility Wizard, but only the "Admissions Director" will see and run the Generate Offer Letter Wizard.
- Unauthorized users navigating to direct wizard URLs will be blocked by a frontend router guard and redirected to the dashboard.

## 6. Technology Stack Summary (Implementation)
- **Framework:** React 18 + Vite + TypeScript
- **Styling:** Tailwind CSS (v4) + Shadcn UI (Frost Aesthetic Layer)
- **Routing:** React Router v6
- **Server State:** `@tanstack/react-query`
- **Client State:** `zustand`
- **API Client:** Shared Axios/Fetch wrapper with Zod for contract enforcement against backend.
- **Animation:** CSS `transition-all` + `framer-motion` (for complex modal/wizard orchestration).
