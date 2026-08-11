-- =============================================================================
-- Migration 040: RLS Policies for Critical Unprotected Tables
-- Story 005 — Database-Level Tenant Isolation
-- =============================================================================
--
-- STATUS: TEMPLATE — DO NOT APPLY until Story 004 approval.
--
-- This migration enables RLS and creates org_id-based isolation policies for
-- critical tables that currently lack row-level security.
--
-- Pattern: Every tenant-scoped table gets:
--   1. RLS enabled
--   2. SELECT policy: org_id = auth.jwt() ->> 'org_id'
--   3. INSERT policy: org_id = auth.jwt() ->> 'org_id'
--   4. UPDATE policy: org_id = auth.jwt() ->> 'org_id'
--   5. DELETE policy: org_id = auth.jwt() ->> 'org_id'
--
-- Service-role access bypasses RLS by default in Supabase.
-- Anonymous access is denied (no policies for anon role).
--
-- Rollback: See bottom of file for DROP POLICY + DISABLE RLS statements.
-- =============================================================================

BEGIN;

-- ─────────────────────────────────────────────────────────────────────────────
-- TIER 1: Highest Risk — Customer Data Tables
-- These contain customer content, cost data, or operational state.
-- ─────────────────────────────────────────────────────────────────────────────

-- ── brand_campaigns ──────────────────────────────────────────────────────────

ALTER TABLE brand_campaigns ENABLE ROW LEVEL SECURITY;

CREATE POLICY brand_campaigns_select_own_org ON brand_campaigns
    FOR SELECT USING (org_id = (auth.jwt() ->> 'org_id')::uuid);

CREATE POLICY brand_campaigns_insert_own_org ON brand_campaigns
    FOR INSERT WITH CHECK (org_id = (auth.jwt() ->> 'org_id')::uuid);

CREATE POLICY brand_campaigns_update_own_org ON brand_campaigns
    FOR UPDATE USING (org_id = (auth.jwt() ->> 'org_id')::uuid);

CREATE POLICY brand_campaigns_delete_own_org ON brand_campaigns
    FOR DELETE USING (org_id = (auth.jwt() ->> 'org_id')::uuid);


-- ── digital_twins ────────────────────────────────────────────────────────────

ALTER TABLE digital_twins ENABLE ROW LEVEL SECURITY;

CREATE POLICY digital_twins_select_own_org ON digital_twins
    FOR SELECT USING (org_id = (auth.jwt() ->> 'org_id')::uuid);

CREATE POLICY digital_twins_insert_own_org ON digital_twins
    FOR INSERT WITH CHECK (org_id = (auth.jwt() ->> 'org_id')::uuid);

CREATE POLICY digital_twins_update_own_org ON digital_twins
    FOR UPDATE USING (org_id = (auth.jwt() ->> 'org_id')::uuid);

CREATE POLICY digital_twins_delete_own_org ON digital_twins
    FOR DELETE USING (org_id = (auth.jwt() ->> 'org_id')::uuid);


-- ── digital_twin_versions ────────────────────────────────────────────────────

ALTER TABLE digital_twin_versions ENABLE ROW LEVEL SECURITY;

CREATE POLICY digital_twin_versions_select_own_org ON digital_twin_versions
    FOR SELECT USING (org_id = (auth.jwt() ->> 'org_id')::uuid);

CREATE POLICY digital_twin_versions_insert_own_org ON digital_twin_versions
    FOR INSERT WITH CHECK (org_id = (auth.jwt() ->> 'org_id')::uuid);

CREATE POLICY digital_twin_versions_update_own_org ON digital_twin_versions
    FOR UPDATE USING (org_id = (auth.jwt() ->> 'org_id')::uuid);

CREATE POLICY digital_twin_versions_delete_own_org ON digital_twin_versions
    FOR DELETE USING (org_id = (auth.jwt() ->> 'org_id')::uuid);


-- ── object_dna ───────────────────────────────────────────────────────────────

ALTER TABLE object_dna ENABLE ROW LEVEL SECURITY;

CREATE POLICY object_dna_select_own_org ON object_dna
    FOR SELECT USING (org_id = (auth.jwt() ->> 'org_id')::uuid);

CREATE POLICY object_dna_insert_own_org ON object_dna
    FOR INSERT WITH CHECK (org_id = (auth.jwt() ->> 'org_id')::uuid);

CREATE POLICY object_dna_update_own_org ON object_dna
    FOR UPDATE USING (org_id = (auth.jwt() ->> 'org_id')::uuid);

CREATE POLICY object_dna_delete_own_org ON object_dna
    FOR DELETE USING (org_id = (auth.jwt() ->> 'org_id')::uuid);


-- ── product_dna ──────────────────────────────────────────────────────────────

ALTER TABLE product_dna ENABLE ROW LEVEL SECURITY;

CREATE POLICY product_dna_select_own_org ON product_dna
    FOR SELECT USING (org_id = (auth.jwt() ->> 'org_id')::uuid);

CREATE POLICY product_dna_insert_own_org ON product_dna
    FOR INSERT WITH CHECK (org_id = (auth.jwt() ->> 'org_id')::uuid);

CREATE POLICY product_dna_update_own_org ON product_dna
    FOR UPDATE USING (org_id = (auth.jwt() ->> 'org_id')::uuid);

CREATE POLICY product_dna_delete_own_org ON product_dna
    FOR DELETE USING (org_id = (auth.jwt() ->> 'org_id')::uuid);


-- ── talent_assets ────────────────────────────────────────────────────────────

ALTER TABLE talent_assets ENABLE ROW LEVEL SECURITY;

CREATE POLICY talent_assets_select_own_org ON talent_assets
    FOR SELECT USING (org_id = (auth.jwt() ->> 'org_id')::uuid);

CREATE POLICY talent_assets_insert_own_org ON talent_assets
    FOR INSERT WITH CHECK (org_id = (auth.jwt() ->> 'org_id')::uuid);

CREATE POLICY talent_assets_update_own_org ON talent_assets
    FOR UPDATE USING (org_id = (auth.jwt() ->> 'org_id')::uuid);

CREATE POLICY talent_assets_delete_own_org ON talent_assets
    FOR DELETE USING (org_id = (auth.jwt() ->> 'org_id')::uuid);


-- ── talent_relationships ─────────────────────────────────────────────────────

ALTER TABLE talent_relationships ENABLE ROW LEVEL SECURITY;

CREATE POLICY talent_relationships_select_own_org ON talent_relationships
    FOR SELECT USING (org_id = (auth.jwt() ->> 'org_id')::uuid);

CREATE POLICY talent_relationships_insert_own_org ON talent_relationships
    FOR INSERT WITH CHECK (org_id = (auth.jwt() ->> 'org_id')::uuid);

CREATE POLICY talent_relationships_update_own_org ON talent_relationships
    FOR UPDATE USING (org_id = (auth.jwt() ->> 'org_id')::uuid);

CREATE POLICY talent_relationships_delete_own_org ON talent_relationships
    FOR DELETE USING (org_id = (auth.jwt() ->> 'org_id')::uuid);


-- ── project_assets ───────────────────────────────────────────────────────────

ALTER TABLE project_assets ENABLE ROW LEVEL SECURITY;

CREATE POLICY project_assets_select_own_org ON project_assets
    FOR SELECT USING (org_id = (auth.jwt() ->> 'org_id')::uuid);

CREATE POLICY project_assets_insert_own_org ON project_assets
    FOR INSERT WITH CHECK (org_id = (auth.jwt() ->> 'org_id')::uuid);

CREATE POLICY project_assets_update_own_org ON project_assets
    FOR UPDATE USING (org_id = (auth.jwt() ->> 'org_id')::uuid);

CREATE POLICY project_assets_delete_own_org ON project_assets
    FOR DELETE USING (org_id = (auth.jwt() ->> 'org_id')::uuid);


-- ── workflow_runs ────────────────────────────────────────────────────────────

ALTER TABLE workflow_runs ENABLE ROW LEVEL SECURITY;

CREATE POLICY workflow_runs_select_own_org ON workflow_runs
    FOR SELECT USING (org_id = (auth.jwt() ->> 'org_id')::uuid);

CREATE POLICY workflow_runs_insert_own_org ON workflow_runs
    FOR INSERT WITH CHECK (org_id = (auth.jwt() ->> 'org_id')::uuid);

CREATE POLICY workflow_runs_update_own_org ON workflow_runs
    FOR UPDATE USING (org_id = (auth.jwt() ->> 'org_id')::uuid);

CREATE POLICY workflow_runs_delete_own_org ON workflow_runs
    FOR DELETE USING (org_id = (auth.jwt() ->> 'org_id')::uuid);


-- ── workflow_templates ───────────────────────────────────────────────────────

ALTER TABLE workflow_templates ENABLE ROW LEVEL SECURITY;

CREATE POLICY workflow_templates_select_own_org ON workflow_templates
    FOR SELECT USING (org_id = (auth.jwt() ->> 'org_id')::uuid);

CREATE POLICY workflow_templates_insert_own_org ON workflow_templates
    FOR INSERT WITH CHECK (org_id = (auth.jwt() ->> 'org_id')::uuid);

CREATE POLICY workflow_templates_update_own_org ON workflow_templates
    FOR UPDATE USING (org_id = (auth.jwt() ->> 'org_id')::uuid);

CREATE POLICY workflow_templates_delete_own_org ON workflow_templates
    FOR DELETE USING (org_id = (auth.jwt() ->> 'org_id')::uuid);


-- ─────────────────────────────────────────────────────────────────────────────
-- TIER 2: Operational Tables — Customer-Adjacent
-- ─────────────────────────────────────────────────────────────────────────────

-- ── approval_requests ────────────────────────────────────────────────────────

ALTER TABLE approval_requests ENABLE ROW LEVEL SECURITY;

CREATE POLICY approval_requests_select_own_org ON approval_requests
    FOR SELECT USING (org_id = (auth.jwt() ->> 'org_id')::uuid);

CREATE POLICY approval_requests_insert_own_org ON approval_requests
    FOR INSERT WITH CHECK (org_id = (auth.jwt() ->> 'org_id')::uuid);

CREATE POLICY approval_requests_update_own_org ON approval_requests
    FOR UPDATE USING (org_id = (auth.jwt() ->> 'org_id')::uuid);


-- ── analytics_snapshots ──────────────────────────────────────────────────────

ALTER TABLE analytics_snapshots ENABLE ROW LEVEL SECURITY;

CREATE POLICY analytics_snapshots_select_own_org ON analytics_snapshots
    FOR SELECT USING (org_id = (auth.jwt() ->> 'org_id')::uuid);

CREATE POLICY analytics_snapshots_insert_own_org ON analytics_snapshots
    FOR INSERT WITH CHECK (org_id = (auth.jwt() ->> 'org_id')::uuid);


-- ── visual_dna ───────────────────────────────────────────────────────────────

ALTER TABLE visual_dna ENABLE ROW LEVEL SECURITY;

CREATE POLICY visual_dna_select_own_org ON visual_dna
    FOR SELECT USING (org_id = (auth.jwt() ->> 'org_id')::uuid);

CREATE POLICY visual_dna_insert_own_org ON visual_dna
    FOR INSERT WITH CHECK (org_id = (auth.jwt() ->> 'org_id')::uuid);

CREATE POLICY visual_dna_update_own_org ON visual_dna
    FOR UPDATE USING (org_id = (auth.jwt() ->> 'org_id')::uuid);


-- ── wardrobes ────────────────────────────────────────────────────────────────

ALTER TABLE wardrobes ENABLE ROW LEVEL SECURITY;

CREATE POLICY wardrobes_select_own_org ON wardrobes
    FOR SELECT USING (org_id = (auth.jwt() ->> 'org_id')::uuid);

CREATE POLICY wardrobes_insert_own_org ON wardrobes
    FOR INSERT WITH CHECK (org_id = (auth.jwt() ->> 'org_id')::uuid);

CREATE POLICY wardrobes_update_own_org ON wardrobes
    FOR UPDATE USING (org_id = (auth.jwt() ->> 'org_id')::uuid);

CREATE POLICY wardrobes_delete_own_org ON wardrobes
    FOR DELETE USING (org_id = (auth.jwt() ->> 'org_id')::uuid);


-- ─────────────────────────────────────────────────────────────────────────────
-- TIER 3: RLS Enabled but MISSING POLICIES (blocked access until fixed)
-- These tables have RLS on but no policies — only service_role can access.
-- Add org_id policies so authenticated users can access their own data.
-- ─────────────────────────────────────────────────────────────────────────────

-- ── brain_messages ───────────────────────────────────────────────────────────

CREATE POLICY brain_messages_select_own_org ON brain_messages
    FOR SELECT USING (org_id = (auth.jwt() ->> 'org_id')::uuid);

CREATE POLICY brain_messages_insert_own_org ON brain_messages
    FOR INSERT WITH CHECK (org_id = (auth.jwt() ->> 'org_id')::uuid);

CREATE POLICY brain_messages_delete_own_org ON brain_messages
    FOR DELETE USING (org_id = (auth.jwt() ->> 'org_id')::uuid);


-- ── brain_sessions ───────────────────────────────────────────────────────────

CREATE POLICY brain_sessions_select_own_org ON brain_sessions
    FOR SELECT USING (org_id = (auth.jwt() ->> 'org_id')::uuid);

CREATE POLICY brain_sessions_insert_own_org ON brain_sessions
    FOR INSERT WITH CHECK (org_id = (auth.jwt() ->> 'org_id')::uuid);

CREATE POLICY brain_sessions_update_own_org ON brain_sessions
    FOR UPDATE USING (org_id = (auth.jwt() ->> 'org_id')::uuid);

CREATE POLICY brain_sessions_delete_own_org ON brain_sessions
    FOR DELETE USING (org_id = (auth.jwt() ->> 'org_id')::uuid);


-- ── publishing_accounts ──────────────────────────────────────────────────────

CREATE POLICY publishing_accounts_select_own_org ON publishing_accounts
    FOR SELECT USING (org_id = (auth.jwt() ->> 'org_id')::uuid);

CREATE POLICY publishing_accounts_insert_own_org ON publishing_accounts
    FOR INSERT WITH CHECK (org_id = (auth.jwt() ->> 'org_id')::uuid);

CREATE POLICY publishing_accounts_update_own_org ON publishing_accounts
    FOR UPDATE USING (org_id = (auth.jwt() ->> 'org_id')::uuid);

CREATE POLICY publishing_accounts_delete_own_org ON publishing_accounts
    FOR DELETE USING (org_id = (auth.jwt() ->> 'org_id')::uuid);


-- ─────────────────────────────────────────────────────────────────────────────
-- TIER 4: Special Cases — Require Different Policy Patterns
-- ─────────────────────────────────────────────────────────────────────────────

-- ── organizations ────────────────────────────────────────────────────────────
-- Users can only see their own org. Ownership via org_members join.
-- NOTE: This uses id (the org's own PK) not org_id.

ALTER TABLE organizations ENABLE ROW LEVEL SECURITY;

CREATE POLICY organizations_select_own ON organizations
    FOR SELECT USING (id = (auth.jwt() ->> 'org_id')::uuid);

-- Only service_role can create/update/delete organizations.
-- No INSERT/UPDATE/DELETE policies for authenticated role.


-- ── worker_connection_attempts ───────────────────────────────────────────────
-- Infrastructure table — service-role only, no authenticated access.

ALTER TABLE worker_connection_attempts ENABLE ROW LEVEL SECURITY;
-- No policies = only service_role can access (RLS blocks all else).


COMMIT;


-- =============================================================================
-- ROLLBACK SCRIPT
-- Run this to revert all changes if issues are detected.
-- =============================================================================
-- BEGIN;
--
-- -- Tier 1
-- DROP POLICY IF EXISTS brand_campaigns_select_own_org ON brand_campaigns;
-- DROP POLICY IF EXISTS brand_campaigns_insert_own_org ON brand_campaigns;
-- DROP POLICY IF EXISTS brand_campaigns_update_own_org ON brand_campaigns;
-- DROP POLICY IF EXISTS brand_campaigns_delete_own_org ON brand_campaigns;
-- ALTER TABLE brand_campaigns DISABLE ROW LEVEL SECURITY;
--
-- DROP POLICY IF EXISTS digital_twins_select_own_org ON digital_twins;
-- DROP POLICY IF EXISTS digital_twins_insert_own_org ON digital_twins;
-- DROP POLICY IF EXISTS digital_twins_update_own_org ON digital_twins;
-- DROP POLICY IF EXISTS digital_twins_delete_own_org ON digital_twins;
-- ALTER TABLE digital_twins DISABLE ROW LEVEL SECURITY;
--
-- DROP POLICY IF EXISTS digital_twin_versions_select_own_org ON digital_twin_versions;
-- DROP POLICY IF EXISTS digital_twin_versions_insert_own_org ON digital_twin_versions;
-- DROP POLICY IF EXISTS digital_twin_versions_update_own_org ON digital_twin_versions;
-- DROP POLICY IF EXISTS digital_twin_versions_delete_own_org ON digital_twin_versions;
-- ALTER TABLE digital_twin_versions DISABLE ROW LEVEL SECURITY;
--
-- DROP POLICY IF EXISTS object_dna_select_own_org ON object_dna;
-- DROP POLICY IF EXISTS object_dna_insert_own_org ON object_dna;
-- DROP POLICY IF EXISTS object_dna_update_own_org ON object_dna;
-- DROP POLICY IF EXISTS object_dna_delete_own_org ON object_dna;
-- ALTER TABLE object_dna DISABLE ROW LEVEL SECURITY;
--
-- DROP POLICY IF EXISTS product_dna_select_own_org ON product_dna;
-- DROP POLICY IF EXISTS product_dna_insert_own_org ON product_dna;
-- DROP POLICY IF EXISTS product_dna_update_own_org ON product_dna;
-- DROP POLICY IF EXISTS product_dna_delete_own_org ON product_dna;
-- ALTER TABLE product_dna DISABLE ROW LEVEL SECURITY;
--
-- DROP POLICY IF EXISTS talent_assets_select_own_org ON talent_assets;
-- DROP POLICY IF EXISTS talent_assets_insert_own_org ON talent_assets;
-- DROP POLICY IF EXISTS talent_assets_update_own_org ON talent_assets;
-- DROP POLICY IF EXISTS talent_assets_delete_own_org ON talent_assets;
-- ALTER TABLE talent_assets DISABLE ROW LEVEL SECURITY;
--
-- DROP POLICY IF EXISTS talent_relationships_select_own_org ON talent_relationships;
-- DROP POLICY IF EXISTS talent_relationships_insert_own_org ON talent_relationships;
-- DROP POLICY IF EXISTS talent_relationships_update_own_org ON talent_relationships;
-- DROP POLICY IF EXISTS talent_relationships_delete_own_org ON talent_relationships;
-- ALTER TABLE talent_relationships DISABLE ROW LEVEL SECURITY;
--
-- DROP POLICY IF EXISTS project_assets_select_own_org ON project_assets;
-- DROP POLICY IF EXISTS project_assets_insert_own_org ON project_assets;
-- DROP POLICY IF EXISTS project_assets_update_own_org ON project_assets;
-- DROP POLICY IF EXISTS project_assets_delete_own_org ON project_assets;
-- ALTER TABLE project_assets DISABLE ROW LEVEL SECURITY;
--
-- DROP POLICY IF EXISTS workflow_runs_select_own_org ON workflow_runs;
-- DROP POLICY IF EXISTS workflow_runs_insert_own_org ON workflow_runs;
-- DROP POLICY IF EXISTS workflow_runs_update_own_org ON workflow_runs;
-- DROP POLICY IF EXISTS workflow_runs_delete_own_org ON workflow_runs;
-- ALTER TABLE workflow_runs DISABLE ROW LEVEL SECURITY;
--
-- DROP POLICY IF EXISTS workflow_templates_select_own_org ON workflow_templates;
-- DROP POLICY IF EXISTS workflow_templates_insert_own_org ON workflow_templates;
-- DROP POLICY IF EXISTS workflow_templates_update_own_org ON workflow_templates;
-- DROP POLICY IF EXISTS workflow_templates_delete_own_org ON workflow_templates;
-- ALTER TABLE workflow_templates DISABLE ROW LEVEL SECURITY;
--
-- -- Tier 2
-- DROP POLICY IF EXISTS approval_requests_select_own_org ON approval_requests;
-- DROP POLICY IF EXISTS approval_requests_insert_own_org ON approval_requests;
-- DROP POLICY IF EXISTS approval_requests_update_own_org ON approval_requests;
-- ALTER TABLE approval_requests DISABLE ROW LEVEL SECURITY;
--
-- DROP POLICY IF EXISTS analytics_snapshots_select_own_org ON analytics_snapshots;
-- DROP POLICY IF EXISTS analytics_snapshots_insert_own_org ON analytics_snapshots;
-- ALTER TABLE analytics_snapshots DISABLE ROW LEVEL SECURITY;
--
-- DROP POLICY IF EXISTS visual_dna_select_own_org ON visual_dna;
-- DROP POLICY IF EXISTS visual_dna_insert_own_org ON visual_dna;
-- DROP POLICY IF EXISTS visual_dna_update_own_org ON visual_dna;
-- ALTER TABLE visual_dna DISABLE ROW LEVEL SECURITY;
--
-- DROP POLICY IF EXISTS wardrobes_select_own_org ON wardrobes;
-- DROP POLICY IF EXISTS wardrobes_insert_own_org ON wardrobes;
-- DROP POLICY IF EXISTS wardrobes_update_own_org ON wardrobes;
-- DROP POLICY IF EXISTS wardrobes_delete_own_org ON wardrobes;
-- ALTER TABLE wardrobes DISABLE ROW LEVEL SECURITY;
--
-- -- Tier 3 (policies only, RLS was already enabled)
-- DROP POLICY IF EXISTS brain_messages_select_own_org ON brain_messages;
-- DROP POLICY IF EXISTS brain_messages_insert_own_org ON brain_messages;
-- DROP POLICY IF EXISTS brain_messages_delete_own_org ON brain_messages;
--
-- DROP POLICY IF EXISTS brain_sessions_select_own_org ON brain_sessions;
-- DROP POLICY IF EXISTS brain_sessions_insert_own_org ON brain_sessions;
-- DROP POLICY IF EXISTS brain_sessions_update_own_org ON brain_sessions;
-- DROP POLICY IF EXISTS brain_sessions_delete_own_org ON brain_sessions;
--
-- DROP POLICY IF EXISTS publishing_accounts_select_own_org ON publishing_accounts;
-- DROP POLICY IF EXISTS publishing_accounts_insert_own_org ON publishing_accounts;
-- DROP POLICY IF EXISTS publishing_accounts_update_own_org ON publishing_accounts;
-- DROP POLICY IF EXISTS publishing_accounts_delete_own_org ON publishing_accounts;
--
-- -- Tier 4
-- DROP POLICY IF EXISTS organizations_select_own ON organizations;
-- ALTER TABLE organizations DISABLE ROW LEVEL SECURITY;
--
-- ALTER TABLE worker_connection_attempts DISABLE ROW LEVEL SECURITY;
--
-- COMMIT;
