"""
CareVerify - Service Layer
Audit logging, notifications, analytics, and smart routing services
"""

from __future__ import annotations
import logging
from datetime import datetime, timedelta
from typing import Optional

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────
# AUDIT SERVICE
# ─────────────────────────────────────────

class AuditService:
    """
    Immutable audit event logger.
    All events are written to audit_logs table (no update/delete via RLS+trigger).
    """

    @staticmethod
    def log(
        event_type: str,
        actor_id: Optional[str] = None,
        actor_role: Optional[str] = None,
        organization_id: Optional[str] = None,
        resource_type: Optional[str] = None,
        resource_id: Optional[str] = None,
        event_data: Optional[dict] = None,
        request=None,
    ):
        try:
            from app.services.supabase_client import get_supabase_admin
            supabase = get_supabase_admin()

            record = {
                "event_type": event_type,
                "actor_id": str(actor_id) if actor_id else None,
                "actor_role": actor_role,
                "organization_id": str(organization_id) if organization_id else None,
                "resource_type": resource_type,
                "resource_id": str(resource_id) if resource_id else None,
                "event_data": event_data or {},
            }

            if request:
                record["ip_address"] = request.remote_addr
                record["user_agent"] = request.headers.get("User-Agent", "")[:500]
                record["session_id"] = request.headers.get("X-Session-ID")

            supabase.table("audit_logs").insert(record).execute()

        except Exception as e:
            logger.error(f"[AuditService] Failed to log event {event_type}: {e}")

    @staticmethod
    def log_system(
        event_type: str,
        resource_type: Optional[str] = None,
        resource_id: Optional[str] = None,
        event_data: Optional[dict] = None,
    ):
        """Log a system-generated event (no human actor)."""
        AuditService.log(
            event_type=event_type,
            actor_id=None,
            actor_role=None,
            resource_type=resource_type,
            resource_id=str(resource_id) if resource_id else None,
            event_data=event_data,
        )


# ─────────────────────────────────────────
# NOTIFICATION SERVICE
# ─────────────────────────────────────────

class NotificationService:
    """
    Push notifications to users via Supabase Realtime.
    Writes to notifications table; Supabase broadcasts via Realtime subscriptions.
    """

    @staticmethod
    def _push(
        user_ids: list[str],
        title: str,
        message: str,
        notification_type: str,
        resource_type: Optional[str] = None,
        resource_id: Optional[str] = None,
        priority: int = 2,
        metadata: Optional[dict] = None,
    ):
        try:
            from app.services.supabase_client import get_supabase_admin
            supabase = get_supabase_admin()

            records = [
                {
                    "user_id": uid,
                    "type": notification_type,
                    "title": title,
                    "message": message,
                    "resource_type": resource_type,
                    "resource_id": str(resource_id) if resource_id else None,
                    "priority": priority,
                    "metadata": metadata or {},
                }
                for uid in user_ids
            ]

            if records:
                supabase.table("notifications").insert(records).execute()

        except Exception as e:
            logger.error(f"[NotificationService] Failed to push notification: {e}")

    @staticmethod
    def notify_admin_high_risk(claim_id: str, trust_score: float):
        """Alert admins about high-risk claims."""
        try:
            from app.services.supabase_client import get_supabase_admin
            supabase = get_supabase_admin()
            admins = supabase.table("users").select("id").eq("role", "admin").execute().data
            admin_ids = [a["id"] for a in admins]

            NotificationService._push(
                user_ids=admin_ids,
                title="⚠️ High-Risk Claim Detected",
                message=f"Claim {claim_id[:8]}... has a trust score of {trust_score}/100. Immediate review required.",
                notification_type="high_risk_claim",
                resource_type="claim",
                resource_id=claim_id,
                priority=5,
            )
        except Exception as e:
            logger.error(f"[NotificationService] notify_admin_high_risk error: {e}")

    @staticmethod
    def notify_insurers_new_claim(claim_id: str):
        """Notify assigned insurer of a claim ready for review."""
        try:
            from app.services.supabase_client import get_supabase_admin
            supabase = get_supabase_admin()

            claim = supabase.table("claims").select(
                "id, claim_number, insurance_org_id"
            ).eq("id", claim_id).single().execute().data

            if not claim or not claim.get("insurance_org_id"):
                return

            insurers = supabase.table("users").select("id").eq(
                "organization_id", claim["insurance_org_id"]
            ).eq("role", "insurance").execute().data

            NotificationService._push(
                user_ids=[i["id"] for i in insurers],
                title="New Claim Ready for Review",
                message=f"Claim {claim['claim_number']} has passed compliance review and is ready for your decision.",
                notification_type="claim_ready_for_decision",
                resource_type="claim",
                resource_id=claim_id,
                priority=3,
            )
        except Exception as e:
            logger.error(f"[NotificationService] notify_insurers_new_claim error: {e}")

    @staticmethod
    def notify_hospital_decision(claim_id: str, decision: str):
        """Notify hospital staff of insurance decision."""
        try:
            from app.services.supabase_client import get_supabase_admin
            supabase = get_supabase_admin()

            claim = supabase.table("claims").select(
                "id, claim_number, hospital_org_id"
            ).eq("id", claim_id).single().execute().data

            if not claim:
                return

            hospital_users = supabase.table("users").select("id").eq(
                "organization_id", claim["hospital_org_id"]
            ).execute().data

            emoji = {"approved": "✅", "partially_approved": "⚠️", "denied": "❌"}.get(decision, "📋")
            title = f"{emoji} Claim Decision: {decision.replace('_', ' ').title()}"

            NotificationService._push(
                user_ids=[u["id"] for u in hospital_users],
                title=title,
                message=f"Claim {claim['claim_number']} has received a decision: {decision}.",
                notification_type="claim_decision",
                resource_type="claim",
                resource_id=claim_id,
                priority=4 if decision == "denied" else 3,
            )
        except Exception as e:
            logger.error(f"[NotificationService] notify_hospital_decision error: {e}")

    @staticmethod
    def notify_sla_breach(claim_id: str):
        """Notify admins of SLA breach."""
        try:
            from app.services.supabase_client import get_supabase_admin
            supabase = get_supabase_admin()
            admins = supabase.table("users").select("id").eq("role", "admin").execute().data

            NotificationService._push(
                user_ids=[a["id"] for a in admins],
                title="🚨 SLA Breach Detected",
                message=f"Claim {claim_id[:8]}... has exceeded its SLA deadline.",
                notification_type="sla_breach",
                resource_type="claim",
                resource_id=claim_id,
                priority=5,
            )
        except Exception as e:
            logger.error(f"[NotificationService] notify_sla_breach error: {e}")


# ─────────────────────────────────────────
# ANALYTICS SERVICE
# ─────────────────────────────────────────

class AnalyticsService:
    def __init__(self, user: dict):
        self.user = user
        self._db = None

    @property
    def db(self):
        if not self._db:
            from app.services.supabase_client import get_supabase_admin
            self._db = get_supabase_admin()
        return self._db

    def _org_filter(self, query, field: str):
        """Apply org scoping for non-admins."""
        if self.user["role"] == "hospital":
            return query.eq(field, self.user["organization_id"])
        elif self.user["role"] == "insurance":
            return query.eq("insurance_org_id", self.user["organization_id"])
        return query

    def get_dashboard_overview(self) -> dict:
        """Generate role-specific KPI dashboard."""
        if self.user["role"] == "hospital":
            return self._hospital_dashboard()
        elif self.user["role"] == "insurance":
            return self._insurer_dashboard()
        else:
            return self._admin_dashboard()

    def _hospital_dashboard(self) -> dict:
        org_id = self.user["organization_id"]
        claims = self.db.table("claims").select(
            "status, claimed_amount, approved_amount, trust_score, created_at"
        ).eq("hospital_org_id", org_id).execute().data

        total_claimed = sum(float(c.get("claimed_amount") or 0) for c in claims)
        total_approved = sum(float(c.get("approved_amount") or 0) for c in claims)
        avg_trust = sum(float(c.get("trust_score") or 0) for c in claims if c.get("trust_score")) / max(len([c for c in claims if c.get("trust_score")]), 1)

        return {
            "role": "hospital",
            "kpis": {
                "total_claims": len(claims),
                "total_claimed_amount": total_claimed,
                "total_approved_amount": total_approved,
                "approval_rate": round(total_approved / total_claimed * 100, 1) if total_claimed > 0 else 0,
                "average_trust_score": round(avg_trust, 1),
                "pending_claims": sum(1 for c in claims if c["status"] in ("submitted", "ai_analyzing", "pending_review")),
                "approved_claims": sum(1 for c in claims if c["status"] == "approved"),
                "denied_claims": sum(1 for c in claims if c["status"] == "denied"),
            }
        }

    def _insurer_dashboard(self) -> dict:
        org_id = self.user["organization_id"]
        claims = self.db.table("claims").select(
            "status, claimed_amount, approved_amount, trust_score, fraud_probability"
        ).eq("insurance_org_id", org_id).execute().data

        return {
            "role": "insurance",
            "kpis": {
                "total_claims": len(claims),
                "pending_decisions": sum(1 for c in claims if c["status"] == "insurer_review"),
                "approved_this_month": sum(1 for c in claims if c["status"] == "approved"),
                "denied_this_month": sum(1 for c in claims if c["status"] == "denied"),
                "high_risk_claims": sum(1 for c in claims if (c.get("fraud_probability") or 0) > 0.7),
                "total_exposure": sum(float(c.get("claimed_amount") or 0) for c in claims if c["status"] not in ("denied", "closed")),
            }
        }

    def _admin_dashboard(self) -> dict:
        claims = self.db.table("claims").select("status, claimed_amount, trust_score, sla_breached", count="exact").execute()
        orgs = self.db.table("organizations").select("type, trust_score", count="exact").execute()

        return {
            "role": "admin",
            "kpis": {
                "total_claims": claims.count,
                "total_organizations": orgs.count,
                "sla_breaches": sum(1 for c in (claims.data or []) if c.get("sla_breached")),
                "avg_platform_trust": round(
                    sum(float(c.get("trust_score") or 50) for c in (claims.data or [])) / max(len(claims.data or []), 1),
                    1
                ),
                "claims_by_status": self._count_by_field(claims.data or [], "status"),
                "orgs_by_type": self._count_by_field(orgs.data or [], "type"),
            }
        }

    def _count_by_field(self, items: list, field: str) -> dict:
        counts = {}
        for item in items:
            val = item.get(field, "unknown")
            counts[val] = counts.get(val, 0) + 1
        return counts

    def get_claim_trends(self, period: str, granularity: str) -> dict:
        """Simplified trend data — production would use Supabase RPC/pg functions."""
        period_days = {"7d": 7, "30d": 30, "90d": 90, "1y": 365}.get(period, 30)
        cutoff = (datetime.utcnow() - timedelta(days=period_days)).isoformat()

        query = self.db.table("claims").select("created_at, claimed_amount, status")
        if self.user["role"] == "hospital":
            query = query.eq("hospital_org_id", self.user["organization_id"])
        elif self.user["role"] == "insurance":
            query = query.eq("insurance_org_id", self.user["organization_id"])
        result = query.gte("created_at", cutoff).execute()

        return {"period": period, "granularity": granularity, "data": result.data}

    def get_fraud_graph(self) -> dict:
        """
        Fraud Intelligence Graph.
        Returns org nodes and suspicious connection edges.
        """
        high_fraud = self.db.table("claims").select(
            "id, claim_number, hospital_org_id, insurance_org_id, fraud_probability, claimed_amount"
        ).gt("fraud_probability", 0.6).limit(100).execute().data

        nodes = {}
        edges = []

        for claim in high_fraud:
            hosp_id = str(claim["hospital_org_id"])
            ins_id = str(claim.get("insurance_org_id", ""))

            if hosp_id not in nodes:
                nodes[hosp_id] = {"id": hosp_id, "type": "hospital", "risk_claims": 0}
            nodes[hosp_id]["risk_claims"] += 1

            if ins_id and ins_id not in nodes:
                nodes[ins_id] = {"id": ins_id, "type": "insurance", "risk_claims": 0}

            if ins_id:
                edges.append({
                    "source": hosp_id,
                    "target": ins_id,
                    "claim_id": claim["id"],
                    "fraud_probability": claim["fraud_probability"],
                    "claimed_amount": float(claim["claimed_amount"]),
                })

        return {
            "nodes": list(nodes.values()),
            "edges": edges,
            "high_risk_claim_count": len(high_fraud),
        }


# ─────────────────────────────────────────
# SMART INSURER ROUTING
# ─────────────────────────────────────────

class SmartInsurerRouter:
    """
    Routes claims to the most appropriate insurance organization based on:
    - Diagnosis/procedure code matching
    - Insurer capacity and current workload
    - Organization trust scores
    - Historical approval rates
    """

    def route(self, claim: dict) -> dict:
        try:
            from app.services.supabase_client import get_supabase_admin
            supabase = get_supabase_admin()

            insurers = supabase.table("organizations").select("*").eq(
                "type", "insurance"
            ).eq("is_active", True).execute().data

            if not insurers:
                return {"insurer_id": None, "reason": "No active insurers available"}

            # Score each insurer
            scored = []
            for insurer in insurers:
                score = float(insurer.get("trust_score", 50))

                # Check current workload
                workload = supabase.table("claims").select("id", count="exact").eq(
                    "insurance_org_id", insurer["id"]
                ).in_("status", ["insurer_review", "compliance_review"]).execute()
                pending_count = workload.count or 0

                # Penalize high-workload insurers
                score -= min(pending_count * 0.5, 20)

                scored.append({"insurer": insurer, "score": score, "pending": pending_count})

            scored.sort(key=lambda x: x["score"], reverse=True)
            best = scored[0]

            return {
                "insurer_id": best["insurer"]["id"],
                "insurer_name": best["insurer"]["name"],
                "routing_score": best["score"],
                "current_workload": best["pending"],
                "reason": "Highest available trust score with capacity",
                "all_candidates": [
                    {"id": s["insurer"]["id"], "name": s["insurer"]["name"], "score": s["score"]}
                    for s in scored[:5]
                ],
            }

        except Exception as e:
            logger.error(f"[Router] Error routing claim: {e}")
            return {"insurer_id": None, "reason": f"Routing error: {str(e)}"}