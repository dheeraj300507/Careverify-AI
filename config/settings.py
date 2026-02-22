"""
CareVerify - Configuration
Environment-aware settings management
"""

import os
from datetime import timedelta


class BaseConfig:
    # Core
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-change-in-production")
    DEBUG = False
    TESTING = False

    # Supabase
    SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
    SUPABASE_ANON_KEY = os.environ.get("SUPABASE_ANON_KEY", "")
    SUPABASE_SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_KEY", "")
    SUPABASE_JWT_SECRET = os.environ.get("SUPABASE_JWT_SECRET", "")

    # Redis / Celery
    REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")

    # CORS
    ALLOWED_ORIGINS = os.environ.get("ALLOWED_ORIGINS", "*").split(",")

    # JWT
    JWT_ALGORITHM = "HS256"
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(hours=1)

    # File Upload
    MAX_CONTENT_LENGTH = 50 * 1024 * 1024  # 50MB
    ALLOWED_EXTENSIONS = {"pdf", "png", "jpg", "jpeg", "tiff", "bmp"}
    SUPABASE_STORAGE_BUCKET = "medical-documents"

    # AI Thresholds
    FRAUD_SCORE_ALERT_THRESHOLD = 0.75
    ANOMALY_SCORE_THRESHOLD = 0.65
    AUTO_APPROVE_TRUST_SCORE = 85
    AUTO_REVIEW_TRUST_SCORE = 40

    # SLA (hours)
    SLA_INITIAL_REVIEW_HOURS = 24
    SLA_COMPLIANCE_REVIEW_HOURS = 72
    SLA_INSURER_DECISION_HOURS = 168  # 7 days

    # Pagination
    DEFAULT_PAGE_SIZE = 20
    MAX_PAGE_SIZE = 100

    # Audit
    AUDIT_LOG_RETENTION_DAYS = 2555  # 7 years (HIPAA requirement)


class DevelopmentConfig(BaseConfig):
    DEBUG = True
    ALLOWED_ORIGINS = ["*"]


class TestingConfig(BaseConfig):
    TESTING = True
    DEBUG = True
    REDIS_URL = "redis://localhost:6379/1"


class ProductionConfig(BaseConfig):
    DEBUG = False

    @property
    def SUPABASE_URL(self):
        val = os.environ.get("SUPABASE_URL")
        if not val:
            raise RuntimeError("SUPABASE_URL environment variable is required in production")
        return val

    @property
    def SUPABASE_SERVICE_KEY(self):
        val = os.environ.get("SUPABASE_SERVICE_KEY")
        if not val:
            raise RuntimeError("SUPABASE_SERVICE_KEY environment variable is required in production")
        return val


config_map = {
    "development": DevelopmentConfig,
    "testing": TestingConfig,
    "production": ProductionConfig,
}