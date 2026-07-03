# AI Studio — Production Company OS

> Priority 12. Multi-brand digital production company.

---

## Overview

Transforms AI Studio from a production tool into a complete digital production company
operating system. Manage multiple AI influencers, brands, campaigns, clients, teams,
and series from one unified platform.

---

## Company Structure

```
Organization
  ├── Studios (production units)
  ├── Brands (visual identities)
  │     ├── Campaigns
  │     ├── Content Calendar
  │     └── Publishing Schedule
  ├── Team (roles + permissions)
  ├── Clients (future agency work)
  └── Licenses (asset ownership)
```

---

## Multi-Brand Management

Each brand stores:
- Logo, colors, brand voice, visual identity
- Preferred models, workflows, publishing schedule
- Target audience, creative guidelines, approval rules
- Isolation: brands don't see each other's assets unless shared

---

## Team Roles (8)

owner, admin, creative_director, editor, producer, prompt_engineer, reviewer, viewer

---

## Approval Workflow

```
Draft → Internal Review → Creative Approval → Client Approval → Scheduled → Published
                                    ↓
                             Rejected / Revision Requested
```

---

## Database Tables (9 new)

`organizations`, `studios`, `brands`, `brand_campaigns`, `team_members`,
`approval_requests`, `clients`, `asset_licenses`

See `docs/sql/017_company_os.sql`.

---

## API Endpoints (30+)

| Category | Endpoints |
|---|---|
| Organizations | CRUD |
| Studios | CRUD |
| Brands | CRUD |
| Campaigns | CRUD |
| Team | CRUD + roles |
| Approvals | Create + decide (approve/reject/revision) |
| Clients | CRUD |
| Licenses | Create + list |

---

## Future: Marketplace

Architecture prepared for:
- Sell templates, workflows, LoRAs, voices, scene packs
- License tracking + usage rights
- Revenue tracking per brand

---

## Future: Mobile Studio

Every API designed for future iPhone/Android apps:
- Approve from phone
- Launch productions
- Monitor campaigns
- View analytics

---

## Brain Integration

The Brain understands brands, budgets, deadlines, and campaigns.

Example: "Launch Melissa's summer campaign"
→ Brain creates content plan, story arcs, production schedule, workflows, calendar.

---

## Files

| File | Purpose |
|---|---|
| `backend/company/__init__.py` | Package |
| `backend/company/router.py` | 30+ API endpoints |
| `docs/sql/017_company_os.sql` | 9 database tables |
| `docs/COMPANY_OS.md` | This documentation |
