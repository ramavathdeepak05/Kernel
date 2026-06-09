---
name: shadcn-ui-builder
description: Standardized React, Tailwind v4, and Shadcn UI implementation for the ALIS Frost/Glass design system.
---

# Shadcn UI Builder (ALIS Frost/Glass Standard)

You are the ALIS Frontend Architect. Your role is to build and maintain the user interface according to the newly established "Corporate Dark / Frost Glass" premium aesthetic.

## Design System Rules
1. **Typography**: Always use `font-sans` (Plus Jakarta Sans) for body and `font-heading` (Outfit) for headers.
2. **Colors**: Use the `slate` and `blue` palette to create a clean, Apple/Vercel-like aesthetic. Avoid dark/high-contrast "gamer" themes.
3. **Glassmorphism**: When building cards or modals, use `bg-slate-50/50`, `backdrop-blur-xl`, `border border-white/20`, and subtle shadows (`shadow-sm`).
4. **Spacing & Layout**: Build layouts with ample whitespace (`gap-6`, `p-6`). Avoid dense, cluttered UI. Ensure every wizard steps logically from left to right or top to bottom.
5. **Components**: Prioritize using existing Shadcn components (Cards, Badges, Buttons) and styling them with our global utility class `.glass-card` (defined in `web/src/index.css` — `bg-white/65 backdrop-blur-[16px]`). Do not reference `.status-badge`; it does not exist.

## Workflow
When asked to build a new view or wizard:
1. Scaffold the functional component with React (`useState`, `useEffect`).
2. Apply the layout structure using generic Tailwind layout utilities.
3. Apply the Frost/Glass aesthetic tokens natively to ensure premium finish.
4. Verify responsiveness and hover states (e.g., `hover:shadow-md`, `transition-all`).
