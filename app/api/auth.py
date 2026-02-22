"""
CareVerify - Auth API Blueprint
Handles JWT validation, user profile, and session management
"""

from flask import Blueprint, request, jsonify, g
from app.middleware.auth import require_auth, get_current_user
from app.services.supabase_client import get_supabase_client, get_user_from_token
from app.services.audit_service import AuditService

auth_bp = Blueprint("auth", __name__)


@auth_bp.route("/verify", methods=["POST"])
def verify_token():
    """
    Verify a Supabase JWT and return the decoded user profile.
    Frontend calls this on app load to validate session.
    """
    data = request.get_json()
    token = data.get("token") if data else None

    if not token:
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]

    if not token:
        return jsonify({"error": "Token required"}), 400

    user = get_user_from_token(token)
    if not user:
        return jsonify({"valid": False, "error": "Invalid or expired token"}), 401

    return jsonify({
        "valid": True,
        "user": {
            "id": user["id"],
            "email": user["email"],
            "full_name": user.get("full_name"),
            "role": user["role"],
            "organization_id": user.get("organization_id"),
            "organization": user.get("organizations"),
            "avatar_url": user.get("avatar_url"),
        }
    })


@auth_bp.route("/profile", methods=["GET"])
@require_auth
def get_profile():
    """Return full profile for the authenticated user."""
    user = get_current_user()
    return jsonify({
        "id": user["id"],
        "email": user["email"],
        "full_name": user.get("full_name"),
        "role": user["role"],
        "organization_id": user.get("organization_id"),
        "organization": user.get("organizations"),
        "avatar_url": user.get("avatar_url"),
        "preferences": user.get("preferences", {}),
        "last_login_at": user.get("last_login_at"),
    })


@auth_bp.route("/profile", methods=["PATCH"])
@require_auth
def update_profile():
    """Update current user's profile fields."""
    user = get_current_user()
    data = request.get_json()

    allowed_fields = {"full_name", "avatar_url", "preferences"}
    updates = {k: v for k, v in data.items() if k in allowed_fields}

    if not updates:
        return jsonify({"error": "No valid fields to update"}), 400

    from app.services.supabase_client import get_supabase_admin
    supabase = get_supabase_admin()

    result = supabase.table("users").update(updates).eq("id", user["id"]).execute()
    if not result.data:
        return jsonify({"error": "Update failed"}), 500

    return jsonify({"message": "Profile updated", "user": result.data[0]})


@auth_bp.route("/logout", methods=["POST"])
@require_auth
def logout():
    """Log audit event for session end."""
    user = get_current_user()
    AuditService.log(
        event_type="user_logout",
        actor_id=user["id"],
        actor_role=user["role"],
        organization_id=user.get("organization_id"),
        request=request,
    )
    return jsonify({"message": "Logged out successfully"})


@auth_bp.route("/login-event", methods=["POST"])
@require_auth
def record_login():
    """Record login event (called by frontend after successful OAuth)."""
    user = get_current_user()

    from app.services.supabase_client import get_supabase_admin
    supabase = get_supabase_admin()
    supabase.table("users").update({"last_login_at": "NOW()"}).eq("id", user["id"]).execute()

    AuditService.log(
        event_type="user_login",
        actor_id=user["id"],
        actor_role=user["role"],
        organization_id=user.get("organization_id"),
        request=request,
    )
    return jsonify({"message": "Login recorded"})