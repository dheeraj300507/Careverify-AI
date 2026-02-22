-- ============================================================
-- CareVerify Database Schema
-- Supabase PostgreSQL with Row-Level Security
-- ============================================================

-- Enable required extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";
CREATE EXTENSION IF NOT EXISTS "pg_trgm"; -- for full-text search

-- ============================================================
-- ENUMS
-- ============================================================

CREATE TYPE org_type AS ENUM ('hospital', 'insurance', 'admin');
CREATE TYPE user_role AS ENUM ('hospital', 'insurance', 'admin');
CREATE TYPE claim_status AS ENUM (
    'draft', 'submitted', 'ocr_processing', 'ai_analyzing',
    'pending_review', 'compliance_review', 'insurer_review',
    'approved', 'partially_approved', 'denied', 'appealed', 'closed'
);
CREATE TYPE document_type AS ENUM (
    'claim_form', 'discharge_summary', 'lab_report',
    'prescription', 'invoice', 'supporting_document'
);
CREATE TYPE decision_type AS ENUM ('approved', 'partially_approved', 'denied');
CREATE TYPE review_outcome AS ENUM ('pass', 'flag', 'escalate', 'reject');
CREATE TYPE audit_event_type AS ENUM (
    'claim_created', 'claim_updated', 'claim_submitted',
    'document_uploaded', 'ai_analysis_completed',
    'review_assigned', 'review_completed',
    'decision_made', 'appeal_filed',
    'user_login', 'user_logout', 'permission_denied',
    'org_trust_score_updated', 'sla_breach_detected'
);

-- ============================================================
-- ORGANIZATIONS
-- ============================================================

CREATE TABLE organizations (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name                TEXT NOT NULL,
    type                org_type NOT NULL,
    registration_number TEXT UNIQUE,
    contact_email       TEXT NOT NULL,
    contact_phone       TEXT,
    address             JSONB,
    trust_score         NUMERIC(5,2) DEFAULT 50.0 CHECK (trust_score BETWEEN 0 AND 100),
    is_active           BOOLEAN DEFAULT true,
    metadata            JSONB DEFAULT '{}',
    created_at          TIMESTAMPTZ DEFAULT NOW(),
    updated_at          TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_organizations_type ON organizations(type);
CREATE INDEX idx_organizations_trust_score ON organizations(trust_score DESC);

-- ============================================================
-- USERS
-- ============================================================

CREATE TABLE users (
    id              UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
    organization_id UUID REFERENCES organizations(id),
    email           TEXT NOT NULL UNIQUE,
    full_name       TEXT,
    role            user_role NOT NULL,
    is_active       BOOLEAN DEFAULT true,
    avatar_url      TEXT,
    last_login_at   TIMESTAMPTZ,
    preferences     JSONB DEFAULT '{}',
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_users_organization ON users(organization_id);
CREATE INDEX idx_users_role ON users(role);
CREATE INDEX idx_users_email ON users(email);

-- ============================================================
-- CLAIMS
-- ============================================================

CREATE TABLE claims (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    claim_number        TEXT UNIQUE NOT NULL DEFAULT 'CV-' || UPPER(SUBSTRING(gen_random_uuid()::TEXT, 1, 8)),
    hospital_org_id     UUID NOT NULL REFERENCES organizations(id),
    insurance_org_id    UUID REFERENCES organizations(id),
    submitted_by        UUID REFERENCES users(id),
    assigned_insurer_id UUID REFERENCES users(id),
    assigned_reviewer_id UUID REFERENCES users(id),

    -- Patient (de-identified for PHI compliance in metadata)
    patient_id          TEXT, -- internal reference only, no PII stored here
    patient_metadata    JSONB DEFAULT '{}', -- encrypted PHI fields

    -- Financial
    claimed_amount      NUMERIC(12,2) NOT NULL,
    approved_amount     NUMERIC(12,2),
    currency            CHAR(3) DEFAULT 'USD',

    -- Status & Workflow
    status              claim_status DEFAULT 'draft',
    priority            SMALLINT DEFAULT 2 CHECK (priority BETWEEN 1 AND 5),

    -- AI Results
    trust_score         NUMERIC(5,2),
    fraud_probability   NUMERIC(5,4),
    anomaly_score       NUMERIC(5,4),
    approval_likelihood NUMERIC(5,4),
    ai_recommendation   TEXT,
    ai_explanation      JSONB DEFAULT '{}',
    ai_analyzed_at      TIMESTAMPTZ,

    -- SLA Tracking
    sla_deadline        TIMESTAMPTZ,
    sla_breached        BOOLEAN DEFAULT false,

    -- Metadata
    diagnosis_codes     TEXT[],
    procedure_codes     TEXT[],
    admission_date      DATE,
    discharge_date      DATE,
    notes               TEXT,
    tags                TEXT[],

    created_at          TIMESTAMPTZ DEFAULT NOW(),
    updated_at          TIMESTAMPTZ DEFAULT NOW(),
    submitted_at        TIMESTAMPTZ,
    closed_at           TIMESTAMPTZ
);

CREATE INDEX idx_claims_hospital ON claims(hospital_org_id);
CREATE INDEX idx_claims_insurance ON claims(insurance_org_id);
CREATE INDEX idx_claims_status ON claims(status);
CREATE INDEX idx_claims_trust_score ON claims(trust_score DESC NULLS LAST);
CREATE INDEX idx_claims_fraud_probability ON claims(fraud_probability DESC NULLS LAST);
CREATE INDEX idx_claims_created_at ON claims(created_at DESC);
CREATE INDEX idx_claims_claim_number ON claims(claim_number);
CREATE INDEX idx_claims_tags ON claims USING GIN(tags);
CREATE INDEX idx_claims_diagnosis ON claims USING GIN(diagnosis_codes);

-- Full-text search
ALTER TABLE claims ADD COLUMN search_vector TSVECTOR;
CREATE INDEX idx_claims_fts ON claims USING GIN(search_vector);

-- ============================================================
-- CLAIM DOCUMENTS
-- ============================================================

CREATE TABLE claim_documents (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    claim_id        UUID NOT NULL REFERENCES claims(id) ON DELETE CASCADE,
    uploaded_by     UUID REFERENCES users(id),
    document_type   document_type NOT NULL,
    file_name       TEXT NOT NULL,
    storage_path    TEXT NOT NULL,
    file_size_bytes BIGINT,
    mime_type       TEXT,
    checksum        TEXT, -- SHA-256 for integrity
    ocr_extracted   BOOLEAN DEFAULT false,
    ocr_text        TEXT,
    ocr_confidence  NUMERIC(5,4),
    ocr_data        JSONB DEFAULT '{}', -- structured OCR output
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_documents_claim ON claim_documents(claim_id);
CREATE INDEX idx_documents_type ON claim_documents(document_type);

-- ============================================================
-- AI RESULTS (Detailed per-model outputs)
-- ============================================================

CREATE TABLE ai_results (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    claim_id            UUID NOT NULL REFERENCES claims(id) ON DELETE CASCADE,
    model_version       TEXT NOT NULL,
    
    -- Per-model scores
    xgboost_fraud_score     NUMERIC(5,4),
    rf_approval_score       NUMERIC(5,4),
    isolation_anomaly_score NUMERIC(5,4),
    autoencoder_anomaly_score NUMERIC(5,4),
    nlp_sentiment_score     NUMERIC(5,4),
    nlp_entities            JSONB DEFAULT '{}',
    
    -- Ensemble
    trust_score         NUMERIC(5,2),
    final_recommendation TEXT,
    confidence          NUMERIC(5,4),
    
    -- Explainability
    feature_importances JSONB DEFAULT '{}',
    shap_values         JSONB DEFAULT '{}',
    explanation_text    TEXT,
    risk_factors        JSONB DEFAULT '[]',
    
    -- Processing metadata
    processing_time_ms  INTEGER,
    model_config        JSONB DEFAULT '{}',
    created_at          TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_ai_results_claim ON ai_results(claim_id);
CREATE INDEX idx_ai_results_trust ON ai_results(trust_score DESC);

-- ============================================================
-- REVIEWS (Human-in-the-loop)
-- ============================================================

CREATE TABLE reviews (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    claim_id        UUID NOT NULL REFERENCES claims(id) ON DELETE CASCADE,
    reviewer_id     UUID REFERENCES users(id),
    review_type     TEXT NOT NULL CHECK (review_type IN ('compliance', 'medical', 'fraud', 'appeal')),
    outcome         review_outcome,
    notes           TEXT,
    checklist       JSONB DEFAULT '{}',
    flags           TEXT[],
    time_spent_mins INTEGER,
    assigned_at     TIMESTAMPTZ DEFAULT NOW(),
    completed_at    TIMESTAMPTZ,
    due_at          TIMESTAMPTZ,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_reviews_claim ON reviews(claim_id);
CREATE INDEX idx_reviews_reviewer ON reviews(reviewer_id);
CREATE INDEX idx_reviews_outcome ON reviews(outcome);
CREATE INDEX idx_reviews_due ON reviews(due_at ASC NULLS LAST);

-- ============================================================
-- DECISIONS (Insurance final decisions)
-- ============================================================

CREATE TABLE decisions (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    claim_id        UUID NOT NULL REFERENCES claims(id) ON DELETE CASCADE,
    decided_by      UUID REFERENCES users(id),
    insurance_org_id UUID NOT NULL REFERENCES organizations(id),
    decision        decision_type NOT NULL,
    approved_amount NUMERIC(12,2),
    denial_reason   TEXT,
    denial_codes    TEXT[],
    conditions      TEXT[],
    notes           TEXT,
    is_final        BOOLEAN DEFAULT false,
    decided_at      TIMESTAMPTZ DEFAULT NOW(),
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_decisions_claim ON decisions(claim_id);
CREATE INDEX idx_decisions_insurance ON decisions(insurance_org_id);
CREATE INDEX idx_decisions_type ON decisions(decision);

-- ============================================================
-- ORGANIZATION TRUST SCORES (Historical)
-- ============================================================

CREATE TABLE organization_trust_scores (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    organization_id UUID NOT NULL REFERENCES organizations(id),
    score           NUMERIC(5,2) NOT NULL,
    previous_score  NUMERIC(5,2),
    delta           NUMERIC(5,2) GENERATED ALWAYS AS (score - COALESCE(previous_score, 50)) STORED,
    factors         JSONB DEFAULT '{}',
    computed_at     TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_trust_scores_org ON organization_trust_scores(organization_id, computed_at DESC);

-- ============================================================
-- AUDIT LOGS (Immutable event log)
-- ============================================================

CREATE TABLE audit_logs (
    id              BIGSERIAL PRIMARY KEY,
    event_type      audit_event_type NOT NULL,
    actor_id        UUID,
    actor_role      user_role,
    organization_id UUID REFERENCES organizations(id),
    resource_type   TEXT,
    resource_id     UUID,
    event_data      JSONB DEFAULT '{}',
    ip_address      INET,
    user_agent      TEXT,
    session_id      TEXT,
    created_at      TIMESTAMPTZ DEFAULT NOW() NOT NULL
);

-- Audit logs are append-only (no UPDATE or DELETE)
CREATE INDEX idx_audit_actor ON audit_logs(actor_id);
CREATE INDEX idx_audit_resource ON audit_logs(resource_type, resource_id);
CREATE INDEX idx_audit_event ON audit_logs(event_type);
CREATE INDEX idx_audit_org ON audit_logs(organization_id);
CREATE INDEX idx_audit_created ON audit_logs(created_at DESC);

-- Prevent modifications (immutability enforced via RLS + trigger)
CREATE OR REPLACE FUNCTION prevent_audit_modification()
RETURNS TRIGGER AS $$
BEGIN
    RAISE EXCEPTION 'Audit logs are immutable';
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER no_audit_update BEFORE UPDATE ON audit_logs FOR EACH ROW EXECUTE FUNCTION prevent_audit_modification();
CREATE TRIGGER no_audit_delete BEFORE DELETE ON audit_logs FOR EACH ROW EXECUTE FUNCTION prevent_audit_modification();

-- ============================================================
-- NOTIFICATIONS
-- ============================================================

CREATE TABLE notifications (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id         UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    organization_id UUID REFERENCES organizations(id),
    type            TEXT NOT NULL,
    title           TEXT NOT NULL,
    message         TEXT NOT NULL,
    resource_type   TEXT,
    resource_id     UUID,
    is_read         BOOLEAN DEFAULT false,
    priority        SMALLINT DEFAULT 2,
    metadata        JSONB DEFAULT '{}',
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    read_at         TIMESTAMPTZ
);

CREATE INDEX idx_notifications_user ON notifications(user_id, is_read, created_at DESC);
CREATE INDEX idx_notifications_org ON notifications(organization_id);

-- ============================================================
-- UPDATED_AT TRIGGER
-- ============================================================

CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER update_organizations_updated_at BEFORE UPDATE ON organizations FOR EACH ROW EXECUTE FUNCTION set_updated_at();
CREATE TRIGGER update_users_updated_at BEFORE UPDATE ON users FOR EACH ROW EXECUTE FUNCTION set_updated_at();
CREATE TRIGGER update_claims_updated_at BEFORE UPDATE ON claims FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- ============================================================
-- ROW LEVEL SECURITY
-- ============================================================

ALTER TABLE organizations ENABLE ROW LEVEL SECURITY;
ALTER TABLE users ENABLE ROW LEVEL SECURITY;
ALTER TABLE claims ENABLE ROW LEVEL SECURITY;
ALTER TABLE claim_documents ENABLE ROW LEVEL SECURITY;
ALTER TABLE ai_results ENABLE ROW LEVEL SECURITY;
ALTER TABLE reviews ENABLE ROW LEVEL SECURITY;
ALTER TABLE decisions ENABLE ROW LEVEL SECURITY;
ALTER TABLE notifications ENABLE ROW LEVEL SECURITY;
ALTER TABLE audit_logs ENABLE ROW LEVEL SECURITY;
ALTER TABLE organization_trust_scores ENABLE ROW LEVEL SECURITY;

-- Helper: get current user's role
CREATE OR REPLACE FUNCTION get_current_user_role()
RETURNS user_role AS $$
  SELECT role FROM users WHERE id = auth.uid()
$$ LANGUAGE SQL SECURITY DEFINER STABLE;

-- Helper: get current user's org
CREATE OR REPLACE FUNCTION get_current_user_org()
RETURNS UUID AS $$
  SELECT organization_id FROM users WHERE id = auth.uid()
$$ LANGUAGE SQL SECURITY DEFINER STABLE;

-- ORGANIZATIONS: All authenticated users can read active orgs; admins can write
CREATE POLICY "orgs_read" ON organizations FOR SELECT TO authenticated USING (is_active = true);
CREATE POLICY "orgs_admin_all" ON organizations FOR ALL TO authenticated USING (get_current_user_role() = 'admin');

-- USERS: Users can read their own record; same-org read; admins see all
CREATE POLICY "users_own" ON users FOR SELECT TO authenticated USING (id = auth.uid());
CREATE POLICY "users_same_org" ON users FOR SELECT TO authenticated USING (organization_id = get_current_user_org());
CREATE POLICY "users_admin_all" ON users FOR ALL TO authenticated USING (get_current_user_role() = 'admin');

-- CLAIMS: Hospitals see their own claims; insurers see assigned claims; admins see all
CREATE POLICY "claims_hospital_own" ON claims FOR SELECT TO authenticated
    USING (hospital_org_id = get_current_user_org() AND get_current_user_role() = 'hospital');

CREATE POLICY "claims_hospital_insert" ON claims FOR INSERT TO authenticated
    WITH CHECK (hospital_org_id = get_current_user_org() AND get_current_user_role() = 'hospital');

CREATE POLICY "claims_insurer_assigned" ON claims FOR SELECT TO authenticated
    USING (insurance_org_id = get_current_user_org() AND get_current_user_role() = 'insurance');

CREATE POLICY "claims_admin_all" ON claims FOR ALL TO authenticated
    USING (get_current_user_role() = 'admin');

-- DOCUMENTS: Follow claim access
CREATE POLICY "docs_via_claim_hospital" ON claim_documents FOR SELECT TO authenticated
    USING (
        EXISTS (
            SELECT 1 FROM claims c
            WHERE c.id = claim_id
              AND c.hospital_org_id = get_current_user_org()
        )
    );

CREATE POLICY "docs_via_claim_insurer" ON claim_documents FOR SELECT TO authenticated
    USING (
        EXISTS (
            SELECT 1 FROM claims c
            WHERE c.id = claim_id
              AND c.insurance_org_id = get_current_user_org()
        )
    );

CREATE POLICY "docs_admin_all" ON claim_documents FOR ALL TO authenticated
    USING (get_current_user_role() = 'admin');

-- AI_RESULTS: Only admin and assigned insurer
CREATE POLICY "ai_results_admin" ON ai_results FOR ALL TO authenticated
    USING (get_current_user_role() = 'admin');

CREATE POLICY "ai_results_hospital" ON ai_results FOR SELECT TO authenticated
    USING (
        EXISTS (SELECT 1 FROM claims c WHERE c.id = claim_id AND c.hospital_org_id = get_current_user_org())
    );

-- REVIEWS: Reviewer + admin
CREATE POLICY "reviews_own" ON reviews FOR ALL TO authenticated
    USING (reviewer_id = auth.uid() OR get_current_user_role() = 'admin');

-- DECISIONS: Insurance org + hospital of claim + admin
CREATE POLICY "decisions_insurance" ON decisions FOR ALL TO authenticated
    USING (insurance_org_id = get_current_user_org() OR get_current_user_role() = 'admin');

CREATE POLICY "decisions_hospital_read" ON decisions FOR SELECT TO authenticated
    USING (
        EXISTS (SELECT 1 FROM claims c WHERE c.id = claim_id AND c.hospital_org_id = get_current_user_org())
    );

-- NOTIFICATIONS: Own user only
CREATE POLICY "notifications_own" ON notifications FOR ALL TO authenticated
    USING (user_id = auth.uid());

-- AUDIT_LOGS: Admins read; all authenticated can insert
CREATE POLICY "audit_insert" ON audit_logs FOR INSERT TO authenticated WITH CHECK (true);
CREATE POLICY "audit_admin_read" ON audit_logs FOR SELECT TO authenticated USING (get_current_user_role() = 'admin');

-- TRUST SCORES: Admin + own org
CREATE POLICY "trust_scores_admin" ON organization_trust_scores FOR ALL TO authenticated
    USING (get_current_user_role() = 'admin');
CREATE POLICY "trust_scores_own_org" ON organization_trust_scores FOR SELECT TO authenticated
    USING (organization_id = get_current_user_org());

-- ============================================================
-- REALTIME SUBSCRIPTIONS
-- ============================================================

ALTER PUBLICATION supabase_realtime ADD TABLE notifications;
ALTER PUBLICATION supabase_realtime ADD TABLE claims;
ALTER PUBLICATION supabase_realtime ADD TABLE reviews;