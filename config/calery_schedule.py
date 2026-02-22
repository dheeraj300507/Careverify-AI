"""
CareVerify - Celery Beat Schedule
Periodic task configuration
"""

from celery.schedules import crontab

CELERYBEAT_SCHEDULE = {
    # SLA monitoring every 30 minutes
    "check-sla-breaches": {
        "task": "app.tasks.ai_tasks.check_sla_breaches",
        "schedule": 1800,  # every 30 minutes
        "options": {"queue": "default"},
    },
    # Nightly trust score batch recomputation for all orgs
    "nightly-trust-score-refresh": {
        "task": "app.tasks.maintenance_tasks.refresh_all_trust_scores",
        "schedule": crontab(hour=2, minute=0),  # 2 AM UTC
        "options": {"queue": "default"},
    },
    # Hourly cleanup of expired signed URLs / temp records
    "hourly-cleanup": {
        "task": "app.tasks.maintenance_tasks.cleanup_expired_records",
        "schedule": crontab(minute=0),
        "options": {"queue": "default"},
    },
}