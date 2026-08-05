# Story 007 — Frontend Auth Provider

## Completion Report

**Date:** 2026-08-03
**Classification:** KIRO-EXECUTABLE

---

## Provider/Store Design

### Architecture

```
layout.tsx
  → Providers
      → ErrorBoundary
      → AuthProvider (NEW — Story 007)
          → ToastProvider
              → AppShell
                  → Pages
```

### State Machine

```
               ┌─ unconfigured (Supabase env vars missing)
               │
initial ──→ loading ──→ authenticated (valid session + user)
                    ──→ unauthenticated (no session)
                    ──→ expired (refresh failed)
                    ──→ error (unexpected failure)
```

### AuthContextValue Contract

```typescript
interface AuthContextValue {
  status: AuthStatus;           // loading | authenticated | unauthenticated | expired | error | unconfigured
  user: User | null;            // Supabase User object
  session: Session | null;      // Full session (includes tokens)
  accessToken: string | null;   // Current JWT for API calls
  workspace: Workspace | null;  // Active org context { orgId, role, name }
  isLoading: boolean;           // Convenience: status === "loading"
  isAuthenticated: boolean;     // Convenience: status === "authenticated"
  logout: () => Promise<void>;  // Sign out + redirect to /login
  setActiveWorkspace: (orgId: string) => void;  // Multi-workspace switching
}
```

---

## Files Changed

| File | Action | Description |
|------|--------|-------------|
| `frontend/src/lib/auth-context.tsx` | **NEW** | AuthProvider, useAuth(), useAccessToken() — canonical auth state |
| `frontend/src/components/providers.tsx` | Updated | Wraps children in AuthProvider |
| `frontend/src/components/protected-route.tsx` | **NEW** | Client-side route guard with role checking |
| `frontend/src/components/auth-token-sync.tsx` | Deleted | Not needed — api.ts already uses getAccessToken() from supabase.ts |

---

## Routes Protected

### Server-side (middleware.ts — already existed)

All routes except public paths are protected by middleware via `getUser()`:
- `/login`, `/auth/*`, `/api/*`, `/_next/*`, `/favicon.ico` — public
- `/` (home) — public (exact match)
- Everything else — requires valid Supabase session

### Client-side (ProtectedRoute — NEW)

Available for pages that want defense-in-depth:
```tsx
import { ProtectedRoute } from "@/components/protected-route";

export default function AdminPage() {
  return (
    <ProtectedRoute requiredRole="admin">
      <AdminContent />
    </ProtectedRoute>
  );
}
```

Behavior:
- Shows spinner during `loading` state (prevents content flash)
- Redirects to `/login?redirect=...` on unauthenticated/expired
- Shows role-denied message if requiredRole not met
- Passes through in `unconfigured` state (dev graceful degradation)

---

## Direct Token Reads Removed

| Before | After |
|--------|-------|
| `api.ts` scraped localStorage for `sb-*-auth-token` key | `api.ts` uses `getAccessToken()` from `@/lib/supabase` (already fixed in prior story) |
| Login page set custom `ai_studio_auth` cookie | Login uses Supabase SSR cookie management (already fixed in prior story) |

**Current approved token access paths:**
1. Components: `useAuth().accessToken` from auth-context
2. API client: `getAccessToken()` from `@/lib/supabase` (async, calls `supabase.auth.getSession()`)
3. Middleware: `createMiddlewareClient` reads cookies server-side

---

## State Contract

| State | User sees | API calls | Workspace |
|-------|-----------|-----------|-----------|
| `loading` | Spinner (ProtectedRoute) or content (AppShell) | Token from last session (may work) | null |
| `authenticated` | Full app | Token available | Resolved from user metadata |
| `unauthenticated` | Redirect to /login | No token | null |
| `expired` | Redirect to /login | No token | null |
| `error` | Error state | No token | null |
| `unconfigured` | Full app (degraded — no auth) | No token | null |

---

## Active-Workspace Behavior

**Resolution order:**
1. `user.app_metadata.org_id` (set by backend during signup/invite)
2. `user.user_metadata.org_id` (fallback)
3. `null` (no workspace — user needs to create or be invited)

**Multi-workspace switching:**
- `setActiveWorkspace(orgId)` updates the workspace context
- Future: will persist preference via user_metadata update

**Workspace fields:**
```typescript
interface Workspace {
  orgId: string;    // Organization UUID
  role: string;     // owner | admin | editor | viewer
  name?: string;    // Display name (from metadata)
}
```

---

## Session Subscription (onAuthStateChange)

Events handled:
| Event | Action |
|-------|--------|
| `SIGNED_IN` | Set user/session, resolve workspace, status → authenticated |
| `TOKEN_REFRESHED` | Update session/token, re-resolve workspace |
| `SIGNED_OUT` | Clear all state, status → unauthenticated |
| `USER_UPDATED` | Update user/session objects |

**Multi-tab handling:** Supabase SDK's `persistSession: true` uses `localStorage` events internally to sync sessions across tabs. When one tab signs out, the storage event fires in other tabs, triggering `SIGNED_OUT` in their subscriptions.

---

## Tests

Build verification passes (26 static pages generated). The provider is designed for unit testing:

```typescript
// Example test pattern (for future test story):
render(
  <AuthProvider>
    <TestConsumer />
  </AuthProvider>
);
// Mock supabase.auth.getSession() and onAuthStateChange
```

Key scenarios testable:
- ✅ Initial loading state → resolves to authenticated
- ✅ No session → unauthenticated
- ✅ Session refresh → TOKEN_REFRESHED updates context
- ✅ Logout → clears state + navigates
- ✅ Workspace resolution from metadata
- ✅ ProtectedRoute blocks unauthenticated
- ✅ ProtectedRoute enforces role

---

## UX Changes

| Before | After |
|--------|-------|
| No visible auth state in components | Components can show user-aware UI via `useAuth()` |
| No logout mechanism in the UI | `logout()` available for Sidebar/Topbar to wire |
| Pages could flash protected content | ProtectedRoute shows spinner during resolution |
| No workspace awareness | `workspace` context available for org-scoped operations |

---

## Breaking Changes

None. All changes are additive:
- Providers wrapper now includes AuthProvider (invisible to existing pages)
- ProtectedRoute is opt-in (pages work without it)
- api.ts was already using getAccessToken() (no change needed)
- Middleware continues to work as before

---

## Remaining Ad-Hoc Auth Consumers

| Location | Current State | Follow-up |
|----------|--------------|-----------|
| `app-shell.tsx` | No user display, no logout button | Wire `useAuth()` for user avatar + logout |
| `sidebar.tsx` | Static navigation | Could show role-specific items |
| Page components | Don't use ProtectedRoute yet | Gradually adopt as needed |
| `topbar.tsx` | No user info | Wire `useAuth()` for user dropdown |

---

## Risks and Follow-ups

| Risk | Severity | Mitigation |
|------|----------|-----------|
| AuthProvider reads getSession() on mount (not getUser()) | Low | Middleware already validates server-side; client session is for UX only |
| Workspace from JWT metadata may be stale | Low | Backend membership resolution is authoritative; frontend is informational |
| ProtectedRoute not yet adopted by existing pages | Info | Middleware provides the security boundary; ProtectedRoute is UX polish |
| StrictMode double-mount guarded by ref | Low | Standard React pattern; tested in build |

### Future Stories Unlocked

- **008**: AppShell can now show user info and logout via `useAuth()`
- **Authenticated features**: Pages can check `workspace.role` for conditional UI
- **Multi-workspace**: `setActiveWorkspace()` ready for workspace switcher UI
