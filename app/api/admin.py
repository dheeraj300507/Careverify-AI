"""
CareVerify - Admin API Blueprint
Platform-level administration: org management, user management, audit access
"""

from flask import Blueprint, request, jsonify
from app.middleware.auth import require_auth, require_roles, get_current_user
from app.services.supabase_client import get_supabase_admin
from app.services.audit_service import AuditService
from app.tasks.ai_tasks import recompute_trust_scores

admin_bp = Blueprint("admin", __name__)


@admin_bp.route("/organizations", methods=["GET"])
@require_auth
@require_roles("admin")
def list_organizations():
    supabase = get_supabase_admin()
    org_type = request.args.get("type")
    query = supabase.table("organizations").select("*", count="exact")
    if org_type:
        query = query.eq("type", org_type)
    result = query.order("name").execute()
    return jsonify({"organizations": result.data, "total": result.count})


@admin_bp.route("/organizations", methods=["POST"])
@require_auth
@require_roles("admin")
def create_organization():
    user = get_current_user()
    data = request.get_json()
    required = {"name", "type", "contact_email"}
    if not required.issubset(data.keys()):
        return jsonify({"error": f"Required fields: {required}"}), 422

    supabase = get_supabase_admin()
    result = supabase.table("organizations").insert({
        "name": data["name"],
        "type": data["type"],
        "contact_email": data["contact_email"],
        "contact_phone": data.get("contact_phone"),
        "registration_number": data.get("registration_number"),
        "address": data.get("address"),
        "trust_score": 50.0,
    }).execute()

    AuditService.log(
        event_type="org_trust_score_updated",
        actor_id=user["id"],
        actor_role=user["role"],
        resource_type="organization",
        resource_id=result.data[0]["id"],
        event_data={"action": "created"},
        request=request,
    )
    return jsonify(result.data[0]), 201


@admin_bp.route("/organizations/<org_id>", methods=["PATCH"])
@require_auth
@require_roles("admin")
def update_organization(org_id: str):
    data = request.get_json()
    allowed = {"name", "contact_email", "contact_phone", "address", "is_active", "metadata"}
    updates = {k: v for k, v in data.items() if k in allowed}
    supabase = get_supabase_admin()
    result = supabase.table("organizations").update(updates).eq("id", org_id).execute()
    return jsonify(result.data[0])


@admin_bp.route("/organizations/<org_id>/trust-score", methods=["POST"])
@require_auth
@require_roles("admin")
def update_trust_score(org_id: str):
    """Manually trigger trust score recomputation for an org."""
    recompute_trust_scores.apply_async(args=[org_id])
    return jsonify({"message": "Trust score recomputation queued", "organization_id": org_id})


@admin_bp.route("/users", methods=["GET"])
@require_auth
@require_roles("admin")
def list_users():
    supabase = get_supabase_admin()
    org_id = request.args.get("organization_id")
    role = request.args.get("role")

    query = supabase.table("users").select("*, organizations(name, type)", count="exact")
    if org_id:
        query = query.eq("organization_id", org_id)
    if role:
        query = query.eq("role", role)

    result = query.order("created_at", desc=True).execute()
    return jsonify({"users": result.data, "total": result.count})


@admin_bp.route("/users/<user_id>/deactivate", methods=["POST"])
@require_auth
@require_roles("admin")
def deactivate_user(user_id: str):
    user = get_current_user()
    supabase = get_supabase_admin()
    supabase.table("users").update({"is_active": False}).eq("id", user_id).execute()
    AuditService.log(
        event_type="user_logout",
        actor_id=user["id"],
        actor_role=user["role"],
        resource_type="user",
        resource_id=user_id,
        event_data={"action": "deactivated"},
        request=request,
    )
    return jsonify({"message": "User deactivated"})


@admin_bp.route("/audit-logs", methods=["GET"])
@require_auth
@require_roles("admin")
def get_audit_logs():
    supabase = get_supabase_admin()
    page = int(request.args.get("page", 1))
    page_size = min(int(request.args.get("page_size", 50)), 100)
    event_type = request.args.get("event_type")
    actor_id = request.args.get("actor_id")
    resource_id = request.args.get("resource_id")

    query = supabase.table("audit_logs").select("*", count="exact")
    if event_type:
        query = query.eq("event_type", event_type)
    if actor_id:
        query = query.eq("actor_id", actor_id)
    if resource_id:
        query = query.eq("resource_id", resource_id)

    query = query.order("created_at", desc=True).range(
        (page - 1) * page_size, page * page_size - 1
    )
    result = query.execute()

    return jsonify({
        "logs": result.data,
        "total": result.count,
        "page": page,
        "page_size": page_size,
    })


@admin_bp.route("/insurer-routing/<claim_id>", methods=["POST"])
@require_auth
@require_roles("admin")
def smart_insurer_routing(claim_id: str):
    """Smart insurer routing: assign claim to best-fit insurer."""
    from app.services.routing_service import SmartInsurerRouter
    user = get_current_user()
    supabase = get_supabase_admin()

    claim = supabase.table("claims").select("*").eq("id", claim_id).single().execute().data
    if not claim:
        return jsonify({"error": "Claim not found"}), 404

    router = SmartInsurerRouter()
    routing_result = router.route(claim)

    if routing_result["insurer_id"]:
        supabase.table("claims").update({
            "insurance_org_id": routing_result["insurer_id"]
        }).eq("id", claim_id).execute()

    return jsonify(routing_result)