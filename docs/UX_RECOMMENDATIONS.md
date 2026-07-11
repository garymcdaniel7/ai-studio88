# UX Recommendations — AI Studio

**Date**: July 2026  
**Based on**: Full UAT Audit of 15 pages, 6 user journeys, 26 issues found  

---

## 1. Navigation & Information Architecture

### Current State
The sidebar has 4 sections (Top, Create, Manage, Operate) with 12 items. Two pages (`/workflows`, `/settings`) are not in the sidebar. The `/story` route redirects to `/editor`.

### Recommendations

| # | Change | Rationale | Effort |
|---|--------|-----------|--------|
| N1 | Add "Workflows" to Create section (between Editor and Training) | Users can't discover workflow viewer | Small |
| N2 | Remove `/story` route (it's just a redirect) | Dead route, no value | Small |
| N3 | Add Settings to sidebar bottom (above user section) | Currently only via avatar click — low discoverability | Small |
| N4 | Consider grouping Admin + Settings under a single "System" section | Reduces cognitive load for non-technical users | Medium |

### Proposed Sidebar Structure
```
(Top)
  Home
  Brain

Create
  Create
  Editor
  Workflows ← ADD
  Training

Manage
  Talent
  Assets
  Models

Operate
  Production
  Publish
  Analytics
  Admin
```

---

## 2. Empty States & First-Time Experience

### Principle
Every page that loads data should have a clear, helpful empty state that tells the user: (1) what goes here, (2) how to add it, (3) a primary action button.

### Pages Needing Better Empty States

| Page | Current | Recommended |
|------|---------|-------------|
| Talent (no talent) | Shows grid with 0 items, no message | "No talent yet. Create your first AI persona to start generating content." + CTA button |
| Workflows (no workflows) | Nothing renders | "No workflow templates found. Workflows are loaded from the backend." + link to docs |
| Brain (no sessions) | Shows empty conversation list | Already good |
| Analytics (no data) | Shows "—" values | "Generate content to see analytics. Data populates after your first image generation." |

### Onboarding Checklist (Future)
For new users, consider a dismissible checklist on the Home page:
- [ ] Create your first talent
- [ ] Upload training photos
- [ ] Generate your first image
- [ ] Train a custom LoRA
- [ ] Schedule a post

---

## 3. Feedback & Loading States

### Principle
Every async action needs: (1) immediate visual feedback, (2) progress indication for long operations, (3) success/error confirmation.

### Issues Found

| Action | Current Feedback | Recommended |
|--------|-----------------|-------------|
| Create Talent | No toast on success | Add success toast |
| Generate Image | Spinner + text | Good (keep as-is) |
| Generate Video | Spinner only | Add estimated time remaining or progress bar |
| Delete Talent | Instant removal from UI | Good (confirm dialog exists) |
| Save Storyboard | Button changes to "Saved!" | Good |
| Clear Completed Jobs | No confirmation, instant delete | Add confirm dialog |
| Upload Model | Progress bar | Good |
| Toggle Service | Toggle animates | Good |

### Skeleton Screens
Replace generic spinners with content-shaped skeleton loaders for:
- Talent grid cards
- Asset gallery thumbnails
- Job queue list items
- Model cards

---

## 4. Consistency & Design Language

### Color Semantic System (Current)
- Purple (#7c3aed) — Primary action, AI/Brain features
- Green — Success, connected, completed
- Amber/Yellow — Warning, pending, queued
- Red — Error, failed, destructive
- Blue — Info, running jobs
- Gray — Disabled, secondary text

**Finding**: This system is consistently applied. No changes needed.

### Button Hierarchy
- Primary: `bg-purple-600` (solid purple)
- Secondary: `border border-white/[0.08] bg-white/[0.03]` (ghost)
- Destructive: `border-red-500/20 text-red-400` (outlined red)
- Disabled: Any of the above + `opacity-50 cursor-not-allowed`

**Finding**: Consistent across all pages. Good.

### Card Style
- Standard: `rounded-xl border border-white/[0.06] bg-[#12122a] p-5`
- Active/Selected: `border-purple-500/50 ring-1 ring-purple-500/30`
- Warning: `border-amber-500/20 bg-amber-500/5`

**Finding**: Consistent. The dark navy theme (#0a0a1a bg, #12122a cards) is premium and cohesive.

---

## 5. Form & Input Patterns

### What Works Well
- All inputs use consistent dark styling
- Focus states are visible (purple border)
- Select dropdowns match the dark theme
- File upload areas use dashed borders with hover state

### Recommendations

| # | Issue | Fix |
|---|-------|-----|
| F1 | Some forms lack validation messages (Talent create, Training) | Add inline error text below inputs |
| F2 | Training page has no "required field" indicators | Add asterisk or "(required)" label |
| F3 | Brain chat textarea doesn't auto-resize | Use auto-height based on content |
| F4 | Several inputs lack `aria-label` or associated `<label>` | Add for accessibility |

---

## 6. Mobile Responsiveness

### Current State
- Sidebar is fixed 200px width — no mobile collapse
- Grid layouts use fixed column counts (grid-cols-6, grid-cols-4)
- No hamburger menu or mobile navigation

### Recommendations (Future)

| Priority | Change |
|----------|--------|
| High | Make sidebar collapsible (icon-only mode on small screens) |
| High | Responsive grid breakpoints on Talent, Assets, Models pages |
| Medium | Mobile-friendly Brain chat (full-screen on mobile) |
| Low | Touch-friendly drag handles on Storyboard shots |

---

## 7. Performance UX

### Recommendations

| # | Change | Impact |
|---|--------|--------|
| P1 | Add SWR or React Query for API caching | Instant navigation between pages |
| P2 | Use Next.js `<Image>` component for optimized loading | Faster asset/talent image rendering |
| P3 | Add `loading.tsx` files for route-level suspense | Better perceived performance |
| P4 | Debounce search inputs (Talent, Brain conversations) | Reduce re-renders |
| P5 | Virtualize long lists (Job queue, Asset gallery) | Handle 100+ items smoothly |

---

## 8. Accessibility (WCAG 2.1 AA) Gaps

### Must Fix

| # | Issue | WCAG Criterion |
|---|-------|---------------|
| A1 | Icon-only buttons (Settings gear, MoreHorizontal, delete) lack `aria-label` | 1.1.1 Non-text Content |
| A2 | Color-only status indicators (green/amber/red dots) need text labels | 1.4.1 Use of Color |
| A3 | Modals don't trap focus | 2.4.3 Focus Order |
| A4 | No skip-to-content link | 2.4.1 Bypass Blocks |
| A5 | Drag-and-drop storyboard reorder has no keyboard alternative | 2.1.1 Keyboard |

### Should Fix

| # | Issue | WCAG Criterion |
|---|-------|---------------|
| A6 | Custom toggles (Admin services) not announced as switches | 4.1.2 Name, Role, Value |
| A7 | Toast notifications not announced to screen readers | 4.1.3 Status Messages |
| A8 | No `prefers-reduced-motion` media query for animations | 2.3.3 Animation |

---

## 9. Information Density vs. Clarity

### Pages That Feel Dense
- **Admin** — Many sections, toggles, status cards. Consider tabs or accordion.
- **Create (Advanced panel)** — Good that it's hidden by default. Keep this pattern.
- **Talent (Edit modal)** — Long form. Consider step-by-step wizard for complex talents.

### Pages That Could Show More
- **Settings** — Very sparse. Could include notification preferences, theme, keyboard shortcuts.
- **Home** — Good balance currently. Don't add more.

---

## 10. Micro-Interactions (Delight)

### Current Good Examples
- Brain dock in sidebar with green "Ready" indicator
- Mode cards in Brain with hover states
- "Use as Prompt" popover on Brain messages
- Tooltip on GPU cost card showing hourly breakdown
- Storyboard drag-and-drop with visual feedback

### Opportunities
- Add subtle entrance animations on cards (stagger)
- Add confetti/celebration on first successful generation
- Add progress percentage on long video generation
- Add sound feedback option for generation complete (optional)

---

## Priority Matrix

| Effort \ Impact | High Impact | Medium Impact | Low Impact |
|-----------------|-------------|---------------|------------|
| **Small** | Fix greeting (H1), Add workflows to sidebar (H3), Confirm on clear jobs, Fix dead code (C1) | Add success toasts, Fix model label (H2) | Remove /story route |
| **Medium** | Wire talent_id in training (C3), SWR caching (P1), Aria labels (A1-A2) | Empty states (Talent, Workflows), Skeleton screens | Mobile sidebar collapse |
| **Large** | Component extraction (Brain, Create), Focus trap on modals | Onboarding wizard | Full mobile responsive |
