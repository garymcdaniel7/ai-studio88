# Index Performance Plan — Story 012

**Date:** 2026-08-05  
**Status:** CANDIDATE — Blocked on Story 010/011 (canonical schema confirmation)  
**Scope:** Workload-justified indexes for tenant filters, FK joins, queues, and status polling  

---

## 1. Query Pattern Inventory (Top 20 by Frequency)

| Rank | Pattern | Frequency | Tables Affected |
|------|---------|-----------|-----------------|
| 1 | `WHERE id = ?` | 164 calls | All tables (PK — already indexed) |
| 2 | `WHERE org_id = ?` | 97 calls | All tenant tables (indexed by 030) |
| 3 | `ORDER BY created_at DESC` | 61 calls | assets, jobs, talent, brain_*, publishing_posts |
| 4 | `WHERE talent_id = ?` | 45 calls | assets, jobs, training_*, lora_*, creative_dna |
| 5 | `WHERE status = ?` | 31 calls | jobs, training_jobs, video_renders, publishing_posts |
| 6 | `ORDER BY name` | 21 calls | talent, models, brands, projects |
| 7 | `WHERE episode_id = ?` | 7 calls | scenes |
| 8 | `WHERE category = ?` | 7 calls | brain_memory, creative_recipes |
| 9 | `WHERE asset_id = ?` | 7 calls | asset_provenance, project_assets, shots |
| 10 | `WHERE universe_id = ?` | 5 calls | characters, episodes, story_memory |
| 11 | `WHERE project_id = ?` | 5 calls | universes, jobs, video_projects |
| 12 | `WHERE provider = ?` | 5 calls | cost_records, worker_connection_attempts |
| 13 | `WHERE voice_profile_id = ?` | 4 calls | voice_samples |
| 14 | `WHERE session_id = ?` | 4 calls | brain_messages, aios_messages |
| 15 | `WHERE platform = ?` | 4 calls | publishing_accounts, social_connections |
| 16 | `WHERE organization_id = ?` | 4 calls | studios, brands, brand_campaigns |
| 17 | `WHERE scene_id = ?` | 3 calls | shots |
| 18 | `WHERE collection_id = ?` | 3 calls | collection_items |
| 19 | `WHERE character_id = ?` | 3 calls | story_memory |
| 20 | `WHERE brand_id = ?` | 2 calls | brand_campaigns, approval_requests |

### Composite Patterns (Multi-Column)

| Pattern | Frequency | Tables |
|---------|-----------|--------|
| `org_id = ? AND status = ?` + `ORDER BY created_at DESC` | ~30 | jobs, training_jobs, publishing_posts |
| `org_id = ? AND talent_id = ?` | ~20 | assets, creative_dna, training_datasets |
| `org_id = ? AND project_id = ?` | ~10 | assets, jobs, storyboards |
| `org_id = ? ORDER BY created_at DESC` | ~60 | Nearly all tenant list queries |
| `status = 'queued' ORDER BY priority DESC, created_at` | ~5 | jobs (queue processing) |

---

## 2. Existing Index Coverage

### Well-Indexed (no action needed)

| Table | Indexed Columns | Source |
|-------|-----------------|--------|
| jobs | status, type, project_id, talent_id, created_at, priority+status | 001 |
| workflows | type, status, category | 002 |
| creative_dna | talent_id, type | 003 |
| training_jobs | project_id, status, talent_id | 008 |
| video_projects | project_id, type, status | 009 |
| publishing_posts | talent_id, platform, status, scheduled_for | 012 |
| org_members | user_id, org_id, user+org active | 029 |
| All tenant tables | org_id (single column) | 030 |
| generation_batches | org_id, user_id, state, created_at, idempotency | 037 |

### Gaps Identified

Tables with high-frequency FK queries but NO index on the queried FK column:

| Table | Missing FK Index | Query Frequency |
|-------|-----------------|-----------------|
| assets | `talent_id` | 45 calls |
| assets | `project_id` | 5 calls |
| training_images | `dataset_id` | implicit (CASCADE) |
| voice_samples | `voice_profile_id` | 4 calls |
| scenes | `episode_id` | 7 calls |
| brand_campaigns | `brand_id` | 2 calls |
| collection_items | `collection_id` | 3 calls |
| shots | `scene_id` | 3 calls |
| brain_messages | `session_id` | 4 calls |
| aios_messages | `session_id` | 4 calls |

---

## 3. Candidate Indexes

### Tier 1: High-Impact Composites (Covering the #1 Query Pattern)

These cover the most common combined filter+sort pattern: `WHERE org_id = ? ORDER BY created_at DESC`.


```sql
-- Tier 1: Composite tenant+sort indexes (highest impact)
-- These replace sequential scan + sort with index-only scan for list queries.

-- assets: org_id filter + created_at sort (most frequent list query)
CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_assets_org_created
    ON assets(org_id, created_at DESC);

-- jobs: org_id + status filter + created_at sort (job polling)
CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_jobs_org_status_created
    ON jobs(org_id, status, created_at DESC);

-- talent: org_id + created_at sort (talent listing)
CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_talent_org_created
    ON talent(org_id, created_at DESC);

-- brain_memory: org_id + category (memory retrieval by topic)
CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_brain_memory_org_category
    ON brain_memory(org_id, category);

-- publishing_posts: org_id + status + scheduled_for (scheduling queue)
CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_publishing_posts_org_status_scheduled
    ON publishing_posts(org_id, status, scheduled_for)
    WHERE status IN ('scheduled', 'pending');
```

### Tier 2: Missing FK Indexes (Join/CASCADE Performance)

```sql
-- assets: talent_id FK (45 query hits — highest unindexed FK)
CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_assets_talent_id
    ON assets(talent_id);

-- assets: project_id FK (cross-project grouping)
CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_assets_project_id
    ON assets(project_id);

-- voice_samples: voice_profile_id FK (profile → samples join)
CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_voice_samples_profile_id
    ON voice_samples(voice_profile_id);

-- scenes: episode_id FK (episode → scenes join)
CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_scenes_episode_id
    ON scenes(episode_id);

-- shots: scene_id FK (scene → shots join)
CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_shots_scene_id
    ON shots(scene_id);

-- brain_messages: session_id FK (session → messages join)
CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_brain_messages_session_id
    ON brain_messages(session_id);

-- aios_messages: session_id FK (session → messages join)
CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_aios_messages_session_id
    ON aios_messages(session_id);

-- collection_items: collection_id FK
CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_collection_items_collection_id
    ON collection_items(collection_id);

-- brand_campaigns: brand_id FK
CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_brand_campaigns_brand_id_v2
    ON brand_campaigns(brand_id);

-- training_images: dataset_id FK (CASCADE path)
CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_training_images_dataset_id
    ON training_images(dataset_id);
```

### Tier 3: Queue/Scheduling Indexes (Partial)

```sql
-- jobs: queue worker pickup (status=queued, ordered by priority)
-- NOTE: 001 already has ix_jobs_priority_status for this.
-- Verify it exists; if not:
CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_jobs_queue_pickup
    ON jobs(priority DESC, created_at ASC)
    WHERE status = 'queued';

-- batch_variation_jobs: queue pickup
-- NOTE: 037 already has ix_batch_variation_jobs_state for this.
-- No additional index needed.

-- training_jobs: org_id + status (training queue)
CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_training_jobs_org_status
    ON training_jobs(org_id, status);
```

### Tier 4: Lifecycle/Deletion Support

```sql
-- lifecycle_transitions: entity lookup (soft delete audit trail)
-- NOTE: 038 already has ix_lifecycle_transitions_entity. No action.

-- entity_holds: active holds lookup
-- NOTE: 038 already has ix_entity_holds_entity with WHERE released_at IS NULL. No action.

-- assets/talent: lifecycle_state filter (if 038 applied with these columns)
CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_assets_org_lifecycle
    ON assets(org_id, lifecycle_state)
    WHERE lifecycle_state != 'active';
```

---

## 4. Write Overhead & Storage Cost Estimates

### Per-Index Cost Model

| Factor | Estimate |
|--------|----------|
| B-tree index overhead per row | ~40-80 bytes (UUID key + tuple pointer) |
| Composite 2-column index per row | ~80-120 bytes |
| Write amplification per INSERT | +1 index page write per index |
| Write amplification per UPDATE (indexed col) | +2 index page writes (delete old + insert new) |

### Projected Impact for This Plan

| Metric | Current | After Tier 1-2 | Delta |
|--------|---------|----------------|-------|
| Total indexes on `assets` table | 1 (org_id) | 4 (org_id, org+created, talent_id, project_id) | +3 |
| Total indexes on `jobs` table | 6 | 7 (add org+status+created) | +1 |
| Total indexes on `talent` table | 1 (org_id) | 2 (add org+created) | +1 |
| INSERT overhead (assets) | ~1 index write | ~4 index writes | +3x index writes |
| Storage per 1000 assets rows | ~40 KB index | ~200 KB index | +160 KB |

### Risk Assessment

| Risk | Mitigation |
|------|-----------|
| Write amplification on high-insert tables (assets, jobs) | Use CONCURRENTLY; monitor pg_stat_user_indexes after 1 week |
| Index bloat on low-cardinality columns (status) | Use partial indexes (WHERE status = 'queued') |
| Unused indexes consuming storage | Review pg_stat_user_indexes.idx_scan after 30 days |
| Lock contention during creation | All indexes use CONCURRENTLY (no table locks) |

### Cost-Benefit Summary

At current scale (<10K rows per table), these indexes provide negligible improvement. At target scale (100K+ rows per table per org), they prevent:
- Sequential scans on tenant-filtered list queries (O(n) → O(log n))
- Full table scans during CASCADE deletes
- Sort operations on unindexed ORDER BY columns

**Recommendation:** Apply Tier 1 and Tier 2 now (low risk, future-proofing). Apply Tier 3-4 only after confirming the queue patterns are active in production.


---

## 5. Indexes NOT Recommended (Avoided Sprawl)

| Candidate | Reason Not Added |
|-----------|------------------|
| `ix_talent_name` (ORDER BY name) | Low frequency (21 calls); small table; seq scan is fine |
| `ix_models_type` | Already exists from 006 |
| `ix_brain_memory_key` | Composite with org+category already covers this pattern |
| `ix_creative_recipes_category` | Already exists from 027 |
| `ix_publishing_posts_talent_id` | Already exists from 012 |
| Indexes on `workers`, `worker_sessions` | Platform tables; tiny row counts; no tenant filter |
| GIN index on JSONB `metadata` | No structured queries against metadata; premature |

---

## 6. Migration File (When Approved)

The indexes above should be applied as:

```
docs/sql/042_workload_indexes.sql
```

All statements use `CREATE INDEX CONCURRENTLY` to avoid table locks. The migration cannot run inside a transaction (CONCURRENTLY requirement), so each statement is independent and idempotent (`IF NOT EXISTS`).

---

## 7. Verification Protocol

### Before Applying

1. Take current `pg_stat_user_indexes` snapshot (baseline scan counts)
2. Run `EXPLAIN ANALYZE` on top 5 queries without indexes
3. Note current query latencies from application logs

### After Applying

1. Wait 7 days for normal workload to exercise indexes
2. Compare `pg_stat_user_indexes.idx_scan` — any index with 0 scans is a removal candidate
3. Run same `EXPLAIN ANALYZE` queries — confirm index usage
4. Check `pg_stat_user_tables.seq_scan` decrease on targeted tables
5. Monitor `pg_total_relation_size` for storage impact

### Explain Plan Templates

```sql
-- Before: assets list query (expect seq scan + sort)
EXPLAIN ANALYZE
SELECT * FROM assets
WHERE org_id = 'FOUNDER_ORG_UUID'
ORDER BY created_at DESC
LIMIT 20;

-- After: should show Index Scan using ix_assets_org_created
```

---

## 8. Follow-ups

| Item | Dependency |
|------|-----------|
| Apply Tier 1+2 indexes | Stories 010/011 complete |
| Measure with representative dataset | Need 10K+ rows seeded per table |
| Review after 30 days | Production traffic required |
| Remove unused indexes from early migrations | Need pg_stat evidence |
| Add covering indexes (INCLUDE) for hot paths | Need EXPLAIN ANALYZE data |
| Evaluate partial indexes for job queue | Need queue worker telemetry |
| Consider hash indexes for exact-match-only FKs | Postgres 10+ feature; low priority |

---

## 9. Summary

| Tier | Indexes | Impact | Risk | Recommended |
|------|---------|--------|------|-------------|
| 1 — Composite tenant+sort | 5 | High (list queries) | Low | Yes, apply now |
| 2 — Missing FK indexes | 10 | Medium (joins, cascades) | Low | Yes, apply now |
| 3 — Queue/scheduling | 2 | Medium (worker pickup) | Low | Conditional |
| 4 — Lifecycle/deletion | 1 | Low (future feature) | Low | Deferred |

**Total candidate indexes:** 18  
**Estimated storage overhead:** <5 MB at current scale  
**Write amplification:** +1-3 index writes per INSERT on affected tables  
**Expected query improvement at 100K rows:** 10-100x for filtered list queries  
