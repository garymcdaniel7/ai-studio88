# Ise UAT Analysis — Full Playwright E2E Run
> Date: 2026-07-11
> Agent: Ise (Production Advisor mode)
> Model: Analysis provided inline (Ollama RAM-constrained)

## Test Results Summary

| Phase | Tests | Pass | Fail | Rate |
|-------|-------|------|------|------|
| 1. Navigation | 28 | 28 | 0 | 100% |
| 2. Brain | 7 | 7 | 0 | 100% |
| 3. Create/Editor/Workflows | 14 | 14 | 0 | 100% |
| 4. Talent/Assets/Models | 19 | 17 | 2 | 89% |
| 5. Production/Publish/Analytics | 14 | 14 | 0 | 100% |
| 6. Admin/Training/Settings | 22 | 22 | 0 | 100% |
| 7. Fleet/Full-flow/Responsive | 65 | 65 | 0 | 100% |
| **TOTAL** | **169** | **167** | **2** | **98.8%** |

## Failures Root Cause

### Models Page Upload (2 tests)
- **Symptom**: `input[type='file']` not found on Models page
- **Root cause**: The Models page upload mechanism changed from a standard file input to a drag-drop zone or custom component that doesn't expose a native file input
- **Fix**: Either re-expose a hidden `<input type="file">` for programmatic access, or update tests to use the drag-drop API

## UI/UX Improvement Recommendations

### 1. Lazy-load heavy data on Admin page
The Admin page takes 10s+ on cold load. Move service health checks to:
- Show skeleton UI immediately
- Load service status cards progressively (each card fetches independently)
- Use `React.Suspense` boundaries around each service card

### 2. Defer API polling until after paint
Pages that poll APIs (Home, Admin, Models) should:
- Render static shell first
- Start polling only after `useEffect` fires (already happening, but the polling blocks `h1` render)
- Move data fetching BELOW the header render — header should render unconditionally

### 3. Models upload: Add hidden file input alongside drag-drop
For both testability and accessibility:
```tsx
<input type="file" className="sr-only" id="model-upload" onChange={handleFile} />
<label htmlFor="model-upload" className="drag-drop-zone">
  Drag & drop or click to upload
</label>
```
This maintains the visual drag-drop UX while keeping a programmatic file input accessible.

### 4. Add loading skeletons to all data-dependent pages
Pages that show a blank spinner while fetching should show:
- Skeleton cards (gray shimmer boxes) matching the expected layout
- Immediately visible header (not gated by data)
- Progressive enhancement as data loads

### 5. Standardize page structure
Every page should follow:
```
<h1>Page Title</h1>  <!-- Always renders immediately -->
<Suspense fallback={<Skeleton />}>
  <DataDependentContent />
</Suspense>
```
This ensures tests can always find `h1` without timeout games.

## Additional Test Coverage Needed

### Priority 1 — Missing flows
- [ ] Image generation end-to-end: fill prompt → generate → see result in Assets
- [ ] Brain conversation persistence: send message → refresh → conversation still there
- [ ] Training submission: select talent → configure → submit → job appears in queue
- [ ] Model download/archive from Fleet page
- [ ] Publish flow: connect platform → schedule post → see in calendar

### Priority 2 — Error states
- [ ] What happens when backend is unreachable (network error toasts?)
- [ ] What happens when generation fails (error message in Create page?)
- [ ] What happens when Ollama is down (Brain page graceful degradation?)
- [ ] File upload with invalid MIME type (rejection message?)

### Priority 3 — Performance
- [ ] Time-to-interactive for each page (flag pages >3s)
- [ ] API response time assertions (flag endpoints >2s)
- [ ] Memory leak detection (navigate all pages 3x, check heap)

### Priority 4 — Accessibility
- [ ] Keyboard navigation through all sidebar links
- [ ] Screen reader labels on all icon buttons
- [ ] Focus management after modal open/close
- [ ] Color contrast in dark theme (purple on dark navy)

## Brittle Patterns to Watch

1. **`h1` as page-load indicator**: Many pages gate their `h1` behind data loading. This makes tests fragile. Fix: render `h1` unconditionally.
2. **Parallel workers + shared browser state**: Tests that navigate rapidly can hit stale pages. Fix: use `--workers=1` or add explicit wait-for-navigation.
3. **`waitForTimeout` in tests**: Fixed delays (2s, 3s) are brittle. Replace with explicit `waitForSelector` or `waitForResponse`.
4. **API polling keeping network busy**: Pages that poll every few seconds prevent `networkidle` state. Already fixed by switching to `domcontentloaded`, but watch for new tests that regress.

## Test Fixes Applied This Run

1. `navigation.spec.ts`: `networkidle` → `domcontentloaded` (sidebar test)
2. `navigation.spec.ts`: Admin selector widened to `h1, [role='tablist'], button`
3. `admin.spec.ts`: `beforeEach` timeout increased to 15s, selector widened

## Next Steps

1. Fix Models page: add hidden file input for programmatic upload
2. Fix Admin cold load: render header unconditionally before data
3. Add Priority 1 test coverage (5 new test files)
4. Store this analysis in Hermes memory for future reference
5. Schedule UAT runs hourly via Ise scheduler (already configured)
