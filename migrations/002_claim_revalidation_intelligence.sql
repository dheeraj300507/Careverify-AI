-- ============================================================
-- CareVerify Revalidation Intelligence Upgrade
-- Adds claim-level fields for upload-driven AI revalidation
-- ============================================================

ALTER TABLE claims
    ADD COLUMN IF NOT EXISTS ai_confidence_score NUMERIC(5,4),
    ADD COLUMN IF NOT EXISTS violation_flags TEXT[] DEFAULT '{}',
    ADD COLUMN IF NOT EXISTS extracted_medical_facts JSONB DEFAULT '{}',
    ADD COLUMN IF NOT EXISTS matched_policies TEXT[] DEFAULT '{}',
    ADD COLUMN IF NOT EXISTS detected_risks TEXT[] DEFAULT '{}',
    ADD COLUMN IF NOT EXISTS reviewer_suggestion TEXT,
    ADD COLUMN IF NOT EXISTS workflow_stage TEXT,
    ADD COLUMN IF NOT EXISTS auto_approval_eligible BOOLEAN DEFAULT false;

CREATE INDEX IF NOT EXISTS idx_claims_ai_confidence ON claims(ai_confidence_score DESC NULLS LAST);
CREATE INDEX IF NOT EXISTS idx_claims_workflow_stage ON claims(workflow_stage);
CREATE INDEX IF NOT EXISTS idx_claims_auto_approval ON claims(auto_approval_eligible);
CREATE INDEX IF NOT EXISTS idx_claims_violation_flags ON claims USING GIN(violation_flags);
CREATE INDEX IF NOT EXISTS idx_claims_detected_risks ON claims USING GIN(detected_risks);
CREATE INDEX IF NOT EXISTS idx_claims_matched_policies ON claims USING GIN(matched_policies);
