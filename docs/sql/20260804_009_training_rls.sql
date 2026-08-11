-- =============================================================================
-- AI Studio: LoRA Training RLS Policies (Story 021)
-- =============================================================================

-- Phase 1: Ensure org_id columns exist
ALTER TABLE training_datasets ADD COLUMN IF NOT EXISTS org_id UUID;
ALTER TABLE training_images ADD COLUMN IF NOT EXISTS org_id UUID;
ALTER TABLE training_jobs ADD COLUMN IF NOT EXISTS org_id UUID;
ALTER TABLE lora_versions ADD COLUMN IF NOT EXISTS org_id UUID;
ALTER TABLE talent_loras ADD COLUMN IF NOT EXISTS org_id UUID;
ALTER TABLE lora_evaluations ADD COLUMN IF NOT EXISTS org_id UUID;

-- Phase 2: Indexes
CREATE INDEX IF NOT EXISTS ix_training_datasets_org_id ON training_datasets(org_id);
CREATE INDEX IF NOT EXISTS ix_training_images_org_id ON training_images(org_id);
CREATE INDEX IF NOT EXISTS ix_training_jobs_org_id ON training_jobs(org_id);
CREATE INDEX IF NOT EXISTS ix_lora_versions_org_id ON lora_versions(org_id);
CREATE INDEX IF NOT EXISTS ix_talent_loras_org_id ON talent_loras(org_id);

-- Phase 3: Enable RLS
ALTER TABLE training_datasets ENABLE ROW LEVEL SECURITY;
ALTER TABLE training_images ENABLE ROW LEVEL SECURITY;
ALTER TABLE training_jobs ENABLE ROW LEVEL SECURITY;
ALTER TABLE lora_versions ENABLE ROW LEVEL SECURITY;
ALTER TABLE talent_loras ENABLE ROW LEVEL SECURITY;
ALTER TABLE lora_evaluations ENABLE ROW LEVEL SECURITY;

-- Phase 4: Org-isolation policies
DROP POLICY IF EXISTS "training_datasets_org_isolation" ON training_datasets;
CREATE POLICY "training_datasets_org_isolation" ON training_datasets
    FOR ALL USING (org_id IN (SELECT om.org_id FROM org_members om WHERE om.user_id = auth.uid() AND om.status = 'active'))
    WITH CHECK (org_id IN (SELECT om.org_id FROM org_members om WHERE om.user_id = auth.uid() AND om.status = 'active'));

DROP POLICY IF EXISTS "training_images_org_isolation" ON training_images;
CREATE POLICY "training_images_org_isolation" ON training_images
    FOR ALL USING (org_id IN (SELECT om.org_id FROM org_members om WHERE om.user_id = auth.uid() AND om.status = 'active'))
    WITH CHECK (org_id IN (SELECT om.org_id FROM org_members om WHERE om.user_id = auth.uid() AND om.status = 'active'));

DROP POLICY IF EXISTS "training_jobs_org_isolation" ON training_jobs;
CREATE POLICY "training_jobs_org_isolation" ON training_jobs
    FOR ALL USING (org_id IN (SELECT om.org_id FROM org_members om WHERE om.user_id = auth.uid() AND om.status = 'active'))
    WITH CHECK (org_id IN (SELECT om.org_id FROM org_members om WHERE om.user_id = auth.uid() AND om.status = 'active'));

DROP POLICY IF EXISTS "lora_versions_org_isolation" ON lora_versions;
CREATE POLICY "lora_versions_org_isolation" ON lora_versions
    FOR ALL USING (org_id IN (SELECT om.org_id FROM org_members om WHERE om.user_id = auth.uid() AND om.status = 'active'))
    WITH CHECK (org_id IN (SELECT om.org_id FROM org_members om WHERE om.user_id = auth.uid() AND om.status = 'active'));

DROP POLICY IF EXISTS "talent_loras_org_isolation" ON talent_loras;
CREATE POLICY "talent_loras_org_isolation" ON talent_loras
    FOR ALL USING (org_id IN (SELECT om.org_id FROM org_members om WHERE om.user_id = auth.uid() AND om.status = 'active'))
    WITH CHECK (org_id IN (SELECT om.org_id FROM org_members om WHERE om.user_id = auth.uid() AND om.status = 'active'));

DROP POLICY IF EXISTS "lora_evaluations_org_isolation" ON lora_evaluations;
CREATE POLICY "lora_evaluations_org_isolation" ON lora_evaluations
    FOR ALL USING (org_id IN (SELECT om.org_id FROM org_members om WHERE om.user_id = auth.uid() AND om.status = 'active'))
    WITH CHECK (org_id IN (SELECT om.org_id FROM org_members om WHERE om.user_id = auth.uid() AND om.status = 'active'));
