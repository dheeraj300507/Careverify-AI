"""
CareVerify - Organizations API Blueprint
"""

from flask import Blueprint, request, jsonify
from app.middleware.auth import require_auth, require_roles, get_current_user
from app.services.supabase_client import get_supabase_admin

organizations_bp = Blueprint("organizations", __name__)


@organizations_bp.route("/<org_id>", methods=["GET"])
@require_auth
def get_organization(org_id: str):
    user = get_current_user()
    supabase = get_supabase_admin()

    if user["role"] not in ("admin",) and str(user["organization_id"]) != org_id:
        return jsonify({"error": "Access denied"}), 403

    result = supabase.table("organizations").select("*").eq("id", org_id).single().execute()
    if not result.data:
        return jsonify({"error": "Organization not found"}), 404

    return jsonify(result.data)


@organizations_bp.route("/<org_id>/members", methods=["GET"])
@require_auth
def get_org_members(org_id: str):
    user = get_current_user()
    supabase = get_supabase_admin()

    if user["role"] not in ("admin",) and str(user["organization_id"]) != org_id:
        return jsonify({"error": "Access denied"}), 403

    result = supabase.table("users").select(
        "id, email, full_name, role, is_active, last_login_at, created_at"
    ).eq("organization_id", org_id).order("created_at").execute()

    return jsonify({"members": result.data, "total": len(result.data)})


@organizations_bp.route("/<org_id>/stats", methods=["GET"])
@require_auth
def get_org_stats(org_id: str):
    user = get_current_user()
    if user["role"] not in ("admin",) and str(user["organization_id"]) != org_id:
        return jsonify({"error": "Access denied"}), 403

    supabase = get_supabase_admin()
    org = supabase.table("organizations").select("*").eq("id", org_id).single().execute().data
    if not org:
        return jsonify({"error": "Not found"}), 404

    if org["type"] == "hospital":
        claims = supabase.table("claims").select("status, claimed_amount, approved_amount, trust_score").eq(
            "hospital_org_id", org_id
        ).execute()
    else:
        claims = supabase.table("claims").select("status, claimed_amount, approved_amount, trust_score").eq(
            "insurance_org_id", org_id
        ).execute()

    data = claims.data
    total_claimed = sum(float(c.get("claimed_amount") or 0) for c in data)
    total_approved = sum(float(c.get("approved_amount") or 0) for c in data)
    status_counts = {}
    for c in data:
        s = c.get("status", "unknown")
        status_counts[s] = status_counts.get(s, 0) + 1

    return jsonify({
        "organization": org,
        "claims_total": len(data),
        "total_claimed_amount": total_claimed,
        "total_approved_amount": total_approved,
        "approval_rate": (total_approved / total_claimed * 100) if total_claimed > 0 else 0,
        "status_breakdown": status_counts,
        "trust_score": org["trust_score"],
    })