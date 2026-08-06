# Semantic Design Tokens — AI Studio

> **Version:** 1.0.0
> **Owner:** Design System / Frontend
> **Source of truth:** `frontend/src/app/globals.css` (`:root` block)
> **Story:** 142

---

## Overview

Semantic tokens are CSS custom properties that give meaning to raw design values. Components consume tokens by name (`surface-raised`) rather than raw hex (`#12122a`), so brand and accessibility changes happen in one place.

Tailwind v4 generates utility classes from the `@theme inline` block in `globals.css`. Use them like: `bg-surface-raised`, `text-content-secondary`, `border-border-subtle`.

---

## Token Taxonomy

### Surfaces

| Token | Value | Tailwind Utility | Usage |
|-------|-------|-----------------|-------|
| `--surface-base` | `#0a0a1a` | `bg-surface-base` | Page/app background |
| `--surface-raised` | `#12122a` | `bg-surface-raised` | Cards, panels, elevated containers |
| `--surface-overlay` | `#0f0f24` | `bg-surface-overlay` | Dialogs, popovers, overlays |
| `--surface-sunken` | `#0d0d20` | `bg-surface-sunken` | Sidebar, nav, inset areas |
| `--surface-hover` | `rgba(255,255,255,0.04)` | `bg-surface-hover` | Hover state backgrounds |
| `--surface-active` | `rgba(255,255,255,0.06)` | `bg-surface-active` | Active/pressed state backgrounds |

### Content (text and icons)

| Token | Value | Tailwind Utility | Usage |
|-------|-------|-----------------|-------|
| `--content-primary` | `#e8e8f0` | `text-content-primary` | Headings, primary text |
| `--content-secondary` | `#c8c8e0` | `text-content-secondary` | Body text, descriptions |
| `--content-tertiary` | `#9ca3af` | `text-content-tertiary` | Labels, secondary info |
| `--content-muted` | `#6b7280` | `text-content-muted` | Placeholders, disabled, hints |
| `--content-inverse` | `#0a0a1a` | `text-content-inverse` | Text on light/accent backgrounds |

### Borders

| Token | Value | Tailwind Utility | Usage |
|-------|-------|-----------------|-------|
| `--border-default` | `rgba(255,255,255,0.08)` | `border-border-default` | Default container borders |
| `--border-subtle` | `rgba(255,255,255,0.04)` | `border-border-subtle` | Dividers, section separators |
| `--border-strong` | `rgba(255,255,255,0.12)` | `border-border-strong` | Emphasis, dropdown borders |

### Interactive (accent / brand purple)

| Token | Value | Tailwind Utility | Usage |
|-------|-------|-----------------|-------|
| `--interactive-default` | `#7c3aed` | `bg-interactive-default` | Primary buttons, active nav |
| `--interactive-hover` | `#6d28d9` | `bg-interactive-hover` | Hover on primary elements |
| `--interactive-active` | `#5b21b6` | `bg-interactive-active` | Pressed/active state |
| `--interactive-muted` | `rgba(124,58,237,0.15)` | `bg-interactive-muted` | Active nav background, tags |
| `--interactive-foreground` | `#ffffff` | `text-interactive-foreground` | Text on interactive bg |

### Focus

| Token | Value | Tailwind Utility | Usage |
|-------|-------|-----------------|-------|
| `--focus-ring` | `#7c3aed` | `ring-focus-ring` | Focus indicator rings |

### Status

| Token | Value | Tailwind Utility | Usage |
|-------|-------|-----------------|-------|
| `--status-success` | `#34d399` | `text-status-success` | Success text/icons |
| `--status-success-muted` | `rgba(16,185,129,0.1)` | `bg-status-success-muted` | Success backgrounds |
| `--status-warning` | `#fbbf24` | `text-status-warning` | Warning text/icons |
| `--status-warning-muted` | `rgba(245,158,11,0.1)` | `bg-status-warning-muted` | Warning backgrounds |
| `--status-error` | `#f87171` | `text-status-error` | Error text/icons |
| `--status-error-muted` | `rgba(239,68,68,0.1)` | `bg-status-error-muted` | Error backgrounds |
| `--status-info` | `#a78bfa` | `text-status-info` | Info/accent text/icons |
| `--status-info-muted` | `rgba(124,58,237,0.1)` | `bg-status-info-muted` | Info backgrounds |

---

## Accessibility Contrast

All combinations verified against WCAG 2.1 AA requirements:
- Normal text: 4.5:1 minimum
- Large text / UI components: 3:1 minimum

| Pair | Ratio | Requirement |
|------|-------|-------------|
| content-primary on surface-base | 16.09:1 | 4.5:1 text |
| content-secondary on surface-base | 11.94:1 | 4.5:1 text |
| content-tertiary on surface-base | 7.72:1 | 4.5:1 text |
| content-muted on surface-base | 4.05:1 | 3:1 UI |
| interactive-default on surface-base | 3.44:1 | 3:1 UI |
| status-success on surface-base | 10.20:1 | 3:1 UI |
| status-warning on surface-base | 11.74:1 | 3:1 UI |
| status-error on surface-base | 7.09:1 | 3:1 UI |
| status-info on surface-base | 7.20:1 | 3:1 UI |

Run `uv run python frontend/scripts/contrast-check.py` to re-verify after token changes.

---

## Figma Variable Mapping

Map these tokens 1:1 in Figma Variables using the same names:

| Figma Collection | Figma Variable | CSS Token |
|-----------------|----------------|-----------|
| Surfaces | `surface/base` | `--surface-base` |
| Surfaces | `surface/raised` | `--surface-raised` |
| Surfaces | `surface/overlay` | `--surface-overlay` |
| Surfaces | `surface/sunken` | `--surface-sunken` |
| Surfaces | `surface/hover` | `--surface-hover` |
| Surfaces | `surface/active` | `--surface-active` |
| Content | `content/primary` | `--content-primary` |
| Content | `content/secondary` | `--content-secondary` |
| Content | `content/tertiary` | `--content-tertiary` |
| Content | `content/muted` | `--content-muted` |
| Content | `content/inverse` | `--content-inverse` |
| Borders | `border/default` | `--border-default` |
| Borders | `border/subtle` | `--border-subtle` |
| Borders | `border/strong` | `--border-strong` |
| Interactive | `interactive/default` | `--interactive-default` |
| Interactive | `interactive/hover` | `--interactive-hover` |
| Interactive | `interactive/active` | `--interactive-active` |
| Interactive | `interactive/muted` | `--interactive-muted` |
| Interactive | `interactive/foreground` | `--interactive-foreground` |
| Focus | `focus/ring` | `--focus-ring` |
| Status | `status/success` | `--status-success` |
| Status | `status/success-muted` | `--status-success-muted` |
| Status | `status/warning` | `--status-warning` |
| Status | `status/warning-muted` | `--status-warning-muted` |
| Status | `status/error` | `--status-error` |
| Status | `status/error-muted` | `--status-error-muted` |
| Status | `status/info` | `--status-info` |
| Status | `status/info-muted` | `--status-info-muted` |

---

## Migration Rules

1. **New components:** must use semantic tokens. No hardcoded hex values for colors that have a token equivalent.
2. **Existing components:** migrate during feature work touching that component. No big-bang refactor.
3. **Exceptions:** Gradients, one-off marketing colors, provider brand colors (Vast.ai blue, GitHub black) may use raw values. Document exceptions with a `/* token-exception: reason */` comment.
4. **Charts:** Use `--chart-1` through `--chart-5` (existing shadcn tokens). Provider brand colors in charts are exceptions.

---

## Versioning

- Token values live in `globals.css` `:root` block.
- Breaking changes (removing/renaming tokens) require a version bump in this doc and a migration notice.
- Additive changes (new tokens) are non-breaking.
- Run contrast checker after any value change: `uv run python frontend/scripts/contrast-check.py`

---

## Components Migrated (v1.0.0)

| Component | Tokens Used |
|-----------|-------------|
| `sidebar.tsx` | surface-sunken, surface-raised, content-*, interactive-*, border-subtle, status-info |
| `topbar.tsx` | surface-base, surface-raised, surface-hover, content-*, status-*, border-* |
| `confirmation-dialog.tsx` | surface-overlay, surface-hover, content-*, status-*, border-default |
| `notification-toast.tsx` | status-success/warning/error/info + muted variants |
| `talent/page.tsx` | Full token coverage (surfaces, content, borders, interactive, status) |
| `admin/page.tsx` | Full token coverage |
| `models/page.tsx` | Full token coverage |
| `production/page.tsx` | Full token coverage |
| `assets/page.tsx` | Full token coverage |
| `publish/page.tsx` | Full token coverage |
| `training/page.tsx` | Full token coverage |
| `brain/page.tsx` | Full token coverage |
| `create/page.tsx` | Full token coverage |

---

## Motion / Duration Tokens

| Token | Value | Usage |
|-------|-------|-------|
| `--duration-instant` | `75ms` | Micro-interactions (checkbox, toggle) |
| `--duration-fast` | `150ms` | Hover states, small transitions |
| `--duration-normal` | `200ms` | Standard transitions, fades |
| `--duration-slow` | `300ms` | Panel slides, accordions |
| `--duration-slower` | `500ms` | Page transitions, complex animations |
| `--easing-default` | `cubic-bezier(0.4, 0, 0.2, 1)` | General purpose |
| `--easing-in` | `cubic-bezier(0.4, 0, 1, 1)` | Elements entering viewport |
| `--easing-out` | `cubic-bezier(0, 0, 0.2, 1)` | Elements leaving viewport |
| `--easing-bounce` | `cubic-bezier(0.34, 1.56, 0.64, 1)` | Playful emphasis |

Use in CSS: `transition: all var(--duration-fast) var(--easing-default);`

Tailwind utilities: `duration-[--duration-fast]` or use the registered `--transition-duration-*` tokens.

---

## Remaining Migration (future work)

All page components and shared components have been migrated to semantic tokens. Minor hardcoded values may remain in edge cases (gradients, chart-specific colors, provider brand colors). These are documented exceptions per the migration rules above.
