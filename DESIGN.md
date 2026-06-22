# QUAICU Design Language & Brand Kit

## 1. Design Philosophy

**QUAICU Brutalist Sovereign Design System**
The QUAICU brand is built on authority, governance, and zero-trust principles. Its visual language reflects these core values:

- **No rounded corners.** Sharp, precise edges signify strict boundaries and definitive rules.
- **No drop shadows.** Flat, unadorned surfaces eliminate ambiguity and illusion.
- **No gradients.** Solid colors maintain clarity and directness.
- **Hairline rules.** Thin, precise dividers organize information with mathematical rigor.
- **Dense grids.** Structured layouts communicate complex information efficiently.
- **Heavy weight contrast.** Bold typography anchors the hierarchy.
- **Mono metadata.** Technical details are rendered in monospace, emphasizing the system's underlying code and logic.

## 2. Brand Positioning

- **Core Identity:** Kernel-first AI Operating Software for regulated enterprises.
- **Tagline:** The AI-native operating software for institutions to scale.
- **Principle:** AI Proposes. Rules Enforce. Humans Approve.
- **Tone:** Authoritative, definitive, uncompromising, technical, and clear. Avoid marketing fluff, "magic" AI framing, or ambiguous claims.

## 3. Color Palette

The color system is stark and utilitarian, relying heavily on high-contrast neutrals with a single, highly controlled brand accent.

### Neutrals (Light Mode Default)
- **Paper (Background):** `#fafaf7` (var(--paper))
- **Paper 2 (Secondary Background):** `#f0eee8` (var(--paper-2))
- **Ink (Primary Text/Elements):** `#0a0a0a` (var(--ink))
- **Graphite (Secondary Text):** `#1c1c1c` (var(--graphite))
- **Smoke (Tertiary Text):** `#525252` (var(--smoke))
- **Mist (Quaternary Text):** `#a3a3a3` (var(--mist))
- **Hairline (Borders/Rules):** `#d4d4d4` (var(--hairline))
- **Hairline Soft:** `#e5e5e2` (var(--hairline-soft))

### Neutrals (Dark Mode Variant)
- **Background:** `#0a0a0a`
- **Secondary Background:** `#141413`
- **Primary Text:** `#fafaf7`
- **Secondary Text:** `#e5e5e2`
- **Tertiary Text:** `#a3a3a3`
- **Quaternary Text:** `#525252`
- **Borders/Rules:** `#2a2a28`
- **Hairline Soft:** `#1c1c1c`

### Accents (Used sparingly, primarily for status)
- **Ember (Brand/Live/Active):** `#008746` (var(--ember))
- **Ember Soft (Highlight/Background):** `#e3f0e7` (var(--ember-soft)) / `#0d2519` (Dark Mode)
- **Alert (Block/Error):** `#c43a1a` (var(--alert))

## 4. Typography

The typographic hierarchy relies on structural contrast between display grotesques, functional sans-serifs, and utilitarian monospace fonts.

### Font Families
- **Display (`var(--f-display)`):** `"Space Grotesk", "Inter", system-ui, sans-serif`
  - *Usage:* H1, H2, H3, large display text, hero headlines.
- **Body (`var(--f-body)`):** `"Inter", system-ui, sans-serif`
  - *Usage:* Paragraphs, buttons, general UI text, links.
- **Mono (`var(--f-mono)`):** `"JetBrains Mono", "SFMono-Regular", Menlo, monospace`
  - *Usage:* Eyebrows, kickers, metadata, tags, code, kernel visualizations, table headers.

### Type Scale (Fluid)
- **Display:** `clamp(40px, 9vw, 144px)` — Line-height `0.95`, tracking `-0.035em`, weight `500`
- **H1:** `clamp(32px, 6vw, 96px)` — Line-height `1.02`, tracking `-0.025em`, weight `500`
- **H2:** `clamp(26px, 3.4vw, 48px)` — Line-height `1.06`, tracking `-0.02em`, weight `500`
- **H3:** `22px` — Line-height `1.2`, tracking `-0.01em`, weight `600`
- **Lead:** `19px` — Line-height `1.45`
- **Body:** `16px` — Line-height `1.45`
- **Meta:** `12px` — Tracking `0.04em`, weight `500`
- **Mono/Eyebrow:** `11px` — Tracking `0.12em` (Eyebrow), weight `500`, uppercase

## 5. Layout & Spacing

- **Shell (Max Width):** `1680px` centered container.
- **Grid:** 12-column CSS Grid (`gap: 24px`).
- **Padding X:** `clamp(20px, 4vw, 72px)`
- **Padding Y:** `clamp(48px, 7vw, 120px)`
- **Density:** Tight packing within structural blocks, separated by definitive hairline rules.

## 6. UI Components

### Buttons
- Sharp corners, geometric.
- **Primary:** Black background (`--fg`), White text (`--bg`). Hover: Ember background.
- **Ghost:** Transparent background, hairline border (`--rule`), muted text. Hover: Ember border/text.
- Often features a right-facing geometric arrow indicator (`->`).

### Tables
- **Style (`table.brutal`):** Unadorned, border-bottom only.
- **Headers:** Monospace, 10px, uppercase, heavy letter-spacing.
- **Highlight Column:** Used for QUAICU features against competitors. Ember-soft background, solid Ember left border.

### Status Pills
- Small, inline indicators. Monospace, uppercase.
- **Live:** Ember border/text, Ember-soft background. Features a pulsing Ember dot indicator.
- **Next:** Default border/text.
- **Future:** Muted border/text.

### Rules & Dividers
- Extensive use of 1px solid lines (`var(--rule)`) to demarcate sections, columns, and rows.
- 2px solid lines (`var(--fg)`) used for major structural breaks (e.g., above footer).

## 7. Imagery & Atmosphere

- **Atmosphere Strips:** Narrow, full-width image bands used as texture between sections. Images are multiplied with the brand Ember green to read as atmospheric texture rather than literal content.
- **Plates:** Isolated, structural image placements (Solo, Wide, Narrow, Left, Right). Imagery is heavily treated: `grayscale(1) contrast(1.05) brightness(0.62)`.
- **Image Overlays:** Images are never presented unmodified. They are either tinted brand green or desaturated and darkened to allow stark white typography to sit legibly on top.

## 8. Specific Visual Patterns

- **The Kernel Viz:** A signature UI pattern simulating a terminal or system output window. It uses monospace type, strict grid columns, and status indicators (Pass, Block, Wait, OK) to visually represent the QUAICU Ring 0 governance engine in action.
- **Green Marker Highlight:** When body text sits on top of a dark image background (`.section--bg`), it receives a tight, inline, translucent Ember background (`rgba(0, 135, 70, 0.78)`) to maintain legibility while letting the image breathe through. Headings remain un-highlighted.
- **Pulsing Dots:** Used in eyebrows and 'Live' status indicators to suggest an active, running system (`animation: pulse 1.4s ease-in-out infinite`).