"""
CareVerify - Analytics API Blueprint
Dashboard intelligence: KPIs, trends, fraud graph, SLA monitoring
"""

from flask import Blueprint, request, jsonify
from app.middleware.auth import require_auth, require_roles, get_current_user
from app.services.supabase_client import get_supabase_admin
from app.services.analytics_service import AnalyticsService

analytics_bp = Blueprint("analytics", __name__)


@analytics_bp.route("/dashboard", methods=["GET"])
@require_auth
def dashboard_overview():
    """
    Role-aware dashboard KPIs.
    Returns different metrics based on caller's role.
    """
    user = get_current_user()
    service = AnalyticsService(user)
    return jsonify(service.get_dashboard_overview())


@analytics_bp.route("/claims/trends", methods=["GET"])
@require_auth
def claim_trends():
    """Claim volume and value trends over time."""
    user = get_current_user()
    period = request.args.get("period", "30d")
    granularity = request.args.get("granularity", "day")
    service = AnalyticsService(user)
    return jsonify(service.get_claim_trends(period, granularity))


@analytics_bp.route("/fraud/graph", methods=["GET"])
@require_auth
@require_roles("admin", "insurance")
def fraud_intelligence_graph():
    """
    Fraud Intelligence Graph.
    Returns nodes (orgs, providers) and edges (suspicious connections).
    """
    user = get_current_user()
    service = AnalyticsService(user)
    return jsonify(service.get_fraud_graph())


@analytics_bp.route("/anomalies", methods=["GET"])
@require_auth
@require_roles("admin", "insurance")
def cross_hospital_anomalies():
    """
    Cross-hospital anomaly detection.
    Identifies billing patterns that deviate from network norms.
    """
    user = get_current_user()
    supabase = get_supabase_admin()

    # Claims with high anomaly scores
    result = supabase.table("ai_results").select(
        "*, claims(claim_number, claimed_amount, status, hospital_org_id, organizations(name))"
    ).gt("isolation_anomaly_score", 0.65).order(
        "isolation_anomaly_score", desc=True
    ).limit(50).execute()

    return jsonify({"anomalies": result.data, "count": len(result.data)})


@analytics_bp.route("/sla/status", methods=["GET"])
@require_auth
@require_roles("admin")
def sla_status():
    """SLA monitoring: breached, at-risk, and on-track claims."""
    supabase = get_supabase_admin()

    from datetime import datetime, timedelta
    now = datetime.utcnow().isoformat()
    at_risk_threshold = (datetime.utcnow() + timedelta(hours=4)).isoformat()

    breached = supabase.table("claims").select(
        "id, claim_number, status, sla_deadline, hospital_org_id"
    ).lt("sla_deadline", now).in_(
        "status", ["submitted", "ocr_processing", "ai_analyzing", "pending_review", "compliance_review"]
    ).execute()

    at_risk = supabase.table("claims").select(
        "id, claim_number, status, sla_deadline, hospital_org_id"
    ).gte("sla_deadline", now).lt("sla_deadline", at_risk_threshold).execute()

    return jsonify({
        "breached": {"count": len(breached.data), "claims": breached.data},
        "at_risk": {"count": len(at_risk.data), "claims": at_risk.data},
    })


@analytics_bp.route("/organizations/<org_id>/trust-history", methods=["GET"])
@require_auth
def org_trust_history(org_id: str):
    """Historical trust score trend for an organization."""
    user = get_current_user()
    if user["role"] not in ("admin",) and str(user["organization_id"]) != org_id:
        return jsonify({"error": "Access denied"}), 403

    supabase = get_supabase_admin()
    result = supabase.table("organization_trust_scores").select("*").eq(
        "organization_id", org_id
    ).order("computed_at", desc=False).limit(90).execute()

    return jsonify({"organization_id": org_id, "history": result.data})


@analytics_bp.route("/processing/queue", methods=["GET"])
@require_auth
@require_roles("admin")
def processing_queue_stats():
    """Background processing queue statistics."""
    from app.tasks.ai_tasks import get_queue_stats
    return jsonify(get_queue_stats())