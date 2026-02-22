from __future__ import annotations
import functools
from typing import Callable, Optional, List

from flask import request, g, jsonify, current_app

from app.services.supabase_client import get_user_from_token


def _extract_bearer_token() -> Optional[str]:
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        return auth_header[7:]
    return None


def require_auth(f: Callable) -> Callable:
    """
    Decorator: validates JWT and sets g.current_user.
    Aborts with 401 if token is missing or invalid.
    """
    @functools.wraps(f)
    def decorated(*args, **kwargs):
        token = _extract_bearer_token()
        if not token:
            return jsonify({"error": "Authorization token required"}), 401

        user = get_user_from_token(token)
        if not user:
            return jsonify({"error": "Invalid or expired token"}), 401

        if not user.get("is_active", True):
            return jsonify({"error": "Account deactivated"}), 401

        g.current_user = user
        g.current_token = token
        return f(*args, **kwargs)

    return decorated


def require_roles(*roles: str) -> Callable:
    """
    Decorator factory: restricts endpoint to specified roles.
    Must be used after @require_auth.
    """
    def decorator(f: Callable) -> Callable:
        @functools.wraps(f)
        def decorated(*args, **kwargs):
            user = getattr(g, "current_user", None)
            if not user:
                return jsonify({"error": "Authentication required"}), 401

            user_role = user.get("role")
            if user_role not in roles:
                return jsonify({
                    "error": "Insufficient permissions",
                    "required_roles": list(roles),
                    "current_role": user_role,
                }), 403

            return f(*args, **kwargs)
        return decorated
    return decorator


def require_organization_access(f: Callable) -> Callable:
    """
    Decorator: ensures the user can only access resources within their org.
    Admins bypass this check.
    """
    @functools.wraps(f)
    def decorated(*args, **kwargs):
        user = getattr(g, "current_user", None)
        if not user:
            return jsonify({"error": "Authentication required"}), 401

        # Admins have cross-org access
        if user.get("role") == "admin":
            return f(*args, **kwargs)

        org_id = kwargs.get("org_id") or request.args.get("org_id")
        if not org_id and request.is_json:
            org_id = request.json.get("org_id")
            
        if org_id and str(org_id) != str(user.get("organization_id")):
            return jsonify({"error": "Access denied to this organization"}), 403

        return f(*args, **kwargs)
    return decorated


def get_current_user() -> Optional[dict]:
    return getattr(g, "current_user", None)


def get_current_org_id() -> Optional[str]:
    user = get_current_user()
    return str(user["organization_id"]) if user else None


def get_current_role() -> Optional[str]:
    user = get_current_user()
    return user.get("role") if user else None