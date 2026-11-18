# Design System

The visual direction is a **premium energy intelligence instrument**, not a
generic AI dashboard. The interface should feel calm, precise, and accountable:
deep green-black surfaces, restrained signal green, fine rules, and dense but
legible technical metadata.

---

## 1. Design principles

1. **Instrument, not spectacle.** Show what is measured. Avoid decorative
   metrics, fake charts, and trend arrows.
2. **One signal.** Green is reserved for live state, primary actions, and
   analytical emphasis. It is not a background decoration.
3. **Quiet structure.** Hairline borders and surface shifts create hierarchy
   before shadows or large colour blocks.
4. **Technical honesty.** Labels state what is real, planned, or unavailable.
   The Phase 1 status panel reports infrastructure checks only.
5. **Readable density.** Small metadata is acceptable, but body copy remains at
   a comfortable 13-16px with generous line height.
6. **Accessible by default.** Visible focus rings, semantic headings, text
   labels alongside status colours, and reduced-motion handling.

---

## 2. Colour tokens

Defined in `frontend/app/globals.css` as Tailwind theme variables.

| Token | Hex | Usage |
| --- | --- | --- |
| `canvas` | `#101713` | Page background |
| `surface` | `#171F19` | Panels, cards, header |
| `surface-raised` | `#202A22` | Hover states, secondary surfaces |
| `primary` | `#8BCF9B` | Signal, primary buttons, live state |
| `accent` | `#B6E3B7` | Primary hover |
| `ink` | `#F1F5F1` | Primary text |
| `muted` | `#9BA99D` | Supporting text, metadata |
| `line` | `#2A352D` | Borders and dividers |
| `warning` | `#E7C88B` | Degraded state |
| `danger` | `#E39A8B` | Offline/failure state |

Rules:

- Buttons with a green fill use near-black text (`#0B120D`), not white.
- Status must be conveyed by a word as well as a colour.
- Large areas stay in canvas/surface tones. Green fills are limited to actions
  and small indicators.
- Avoid pure black, pure white, and saturated neon green.

---

## 3. Typography

| Role | Font | Treatment |
| --- | --- | --- |
| Display | Geist Sans | 44-80px, medium weight, tight tracking (-0.04 to -0.055em) |
| Section heading | Geist Sans | 30-36px, medium, tight tracking |
| Body | Geist Sans | 13-16px, 1.6-1.75 line height |
| Metadata | Geist Mono | 9-10px, uppercase, 0.12-0.2em tracking |
| Code | Geist Mono | 10-12px, subtle canvas background |

Guidelines:

- Use `font-medium`, not `font-bold`, for headings.
- Keep labels short and uppercase. Do not uppercase full sentences.
- Avoid more than three visible type sizes in one panel.
- Long-form copy uses `muted`; key statements use `ink`.

---

## 4. Surfaces and spacing

- Base radius: 8px controls, 12px cards, 16px major panels, 999px status pills.
- Border: 1px `line`; hover borders may shift to `primary/20-30`.
- Panel background: `surface`; nested panels use `canvas/40-70`.
- Primary content width: 1280px with 24px mobile and 40px desktop gutters.
- Section rhythm: 96-112px vertical padding on desktop.
- Use larger gaps between sections than inside cards. Hairlines separate
  related information, not every element.
- Ambient lighting: one broad radial green glow in the upper-right and a second
  faint glow at the left. Keep opacity below 10%.

---

## 5. Components

### Buttons

- Primary: green fill, dark text, 8px radius, 20px horizontal padding.
- Secondary: transparent fill, `line` border, text `ink`, hover raised surface.
- Focus: 2px primary ring with 2px canvas offset, always keyboard-visible.
- No icon-only buttons without an accessible label.

### Chips

Small mono labels for technology or state metadata. Use `line` borders and
canvas background. They are informational, not interactive.

### Status panel

- Badge states: Checking (neutral), Operational (green), Degraded (warning),
  Offline (danger).
- Headline and badge update live from `/api/v1/health`.
- The panel never displays consumption data because none exists in Phase 1.
- The animated ring appears only in the healthy state and is removed for
  `prefers-reduced-motion`.

### Cards

- Hairline border, surface fill, 20-28px padding.
- Icons in a 36px bordered tile.
- Hover is subtle: border and surface shift only.

### Tables and charts (future)

- Use Recharts only for values computed from stored datasets.
- Label units explicitly (kWh, kW, timestamps in UTC or clearly stated local
  time).
- No smoothing that hides missing intervals; show gaps honestly.
- Anomaly markers need a text explanation and the detection threshold.
- Forecast charts must distinguish observed history from predicted values and
  show the evaluation window.

---

## 6. Motion

- Motion explains state change, never decorates idle content.
- Allowed: status ring pulse, short colour transitions (150-250ms), hover
  feedback.
- Avoid entrance animations, parallax, floating cards, and animated counters.
- Respect `prefers-reduced-motion`; the implementation disables non-essential
  animation globally.

---

## 7. Voice

- Direct, technical, and non-promotional.
- Say "not implemented yet" instead of implying a feature exists.
- Prefer concrete nouns: dataset, schema, interval, forecast horizon, error
  metric.
- Avoid "revolutionary", "AI-powered magic", and unverifiable superlatives.
- The product is local; do not imply cloud processing or live deployment.

---

## 8. Accessibility checks for new UI

- Text contrast meets WCAG AA against canvas/surface.
- Focus states are visible without a mouse.
- Status uses words, not colour alone.
- Charts have accessible summaries and tabular alternatives where practical.
- Form inputs have labels and error messages tied by `aria-describedby`.
- Heading order remains logical as sections are added.
