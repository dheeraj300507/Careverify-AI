"""
CareVerify - Notifications API Blueprint
"""

from flask import Blueprint, request, jsonify
from app.middleware.auth import require_auth, get_current_user
from app.services.supabase_client import get_supabase_admin

notifications_bp = Blueprint("notifications", __name__)


@notifications_bp.route("", methods=["GET"])
@require_auth
def list_notifications():
    user = get_current_user()
    supabase = get_supabase_admin()
    page = int(request.args.get("page", 1))
    page_size = min(int(request.args.get("page_size", 20)), 50)
    unread_only = request.args.get("unread_only", "false").lower() == "true"

    query = supabase.table("notifications").select("*", count="exact").eq("user_id", user["id"])
    if unread_only:
        query = query.eq("is_read", False)

    query = query.order("created_at", desc=True).range(
        (page - 1) * page_size, page * page_size - 1
    )
    result = query.execute()

    return jsonify({
        "notifications": result.data,
        "total": result.count,
        "unread_count": sum(1 for n in result.data if not n["is_read"]),
    })


@notifications_bp.route("/<notification_id>/read", methods=["POST"])
@require_auth
def mark_read(notification_id: str):
    user = get_current_user()
    supabase = get_supabase_admin()
    from datetime import datetime
    supabase.table("notifications").update({
        "is_read": True,
        "read_at": datetime.utcnow().isoformat(),
    }).eq("id", notification_id).eq("user_id", user["id"]).execute()
    return jsonify({"message": "Marked as read"})


@notifications_bp.route("/read-all", methods=["POST"])
@require_auth
def mark_all_read():
    user = get_current_user()
    supabase = get_supabase_admin()
    from datetime import datetime
    supabase.table("notifications").update({
        "is_read": True,
        "read_at": datetime.utcnow().isoformat(),
    }).eq("user_id", user["id"]).eq("is_read", False).execute()
    return jsonify({"message": "All notifications marked as read"})