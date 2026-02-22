"""
CareVerify - Maintenance Celery Tasks
Scheduled cleanup and batch operations
"""

import logging
from app.extensions import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(name="app.tasks.maintenance_tasks.refresh_all_trust_scores", queue="default")
def refresh_all_trust_scores():
    """Nightly batch recomputation of all organization trust scores."""
    logger.info("[Maintenance] Starting nightly trust score refresh")
    try:
        from app.services.supabase_client import get_supabase_admin
        from app.tasks.ai_tasks import recompute_trust_scores

        supabase = get_supabase_admin()
        orgs = supabase.table("organizations").select("id").eq("is_active", True).execute().data

        for org in orgs:
            recompute_trust_scores.apply_async(args=[org["id"]], countdown=1)

        logger.info(f"[Maintenance] Queued trust score refresh for {len(orgs)} organizations")
    except Exception as e:
        logger.error(f"[Maintenance] Trust score refresh failed: {e}")


@celery_app.task(name="app.tasks.maintenance_tasks.cleanup_expired_records", queue="default")
def cleanup_expired_records():
    """Clean up stale draft claims and expired temp records."""
    logger.info("[Maintenance] Running cleanup")
    try:
        from app.services.supabase_client import get_supabase_admin
        from datetime import datetime, timedelta

        supabase = get_supabase_admin()
        cutoff = (datetime.utcnow() - timedelta(days=30)).isoformat()

        # Mark very old draft claims as abandoned
        result = supabase.table("claims").update({"status": "closed"}).eq(
            "status", "draft"
        ).lt("created_at", cutoff).execute()

        logger.info(f"[Maintenance] Cleanup complete")
    except Exception as e:
        logger.error(f"[Maintenance] Cleanup failed: {e}")