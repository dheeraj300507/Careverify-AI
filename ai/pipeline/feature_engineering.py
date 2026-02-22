"""
CareVerify - Feature Engineering Pipeline
Converts raw claim data + OCR results → ML feature vector
"""

from __future__ import annotations
import logging
from datetime import datetime, date
from typing import Optional

from ai.models.ensemble_engine import ClaimFeatures

logger = logging.getLogger(__name__)

# Common high-value / high-risk CPT code prefixes
HIGH_VALUE_CPT_PREFIXES = {"3", "4", "5", "6", "7"}  # surgical and complex procedures
HOLIDAY_MONTHS_DAYS = {(12, 25), (1, 1), (7, 4), (11, 28), (11, 27)}


class FeatureEngineer:
    """
    Converts raw claim + org data into a ClaimFeatures struct
    suitable for the ensemble AI engine.
    """

    def __init__(self, supabase_client):
        self._db = supabase_client

    def _get_org_stats(self, org_id: str) -> dict:
        """Fetch organization-level statistics for feature engineering."""
        try:
            org = self._db.table("organizations").select(
                "trust_score"
            ).eq("id", org_id).single().execute().data

            # Claims in last 30 days
            from datetime import timedelta
            cutoff = (datetime.utcnow() - timedelta(days=30)).isoformat()
            recent_claims = self._db.table("claims").select(
                "id, claimed_amount, status, fraud_probability"
            ).eq("hospital_org_id", org_id).gte("created_at", cutoff).execute().data

            fraud_claims = [c for c in recent_claims if c.get("fraud_probability", 0) and c["fraud_probability"] > 0.7]
            amounts = [float(c["claimed_amount"]) for c in recent_claims if c.get("claimed_amount")]

            return {
                "trust_score": float(org["trust_score"]) if org else 50.0,
                "claim_volume_30d": len(recent_claims),
                "avg_claim_amount": sum(amounts) / len(amounts) if amounts else 0.0,
                "historical_fraud_rate": len(fraud_claims) / len(recent_claims) if recent_claims else 0.05,
            }
        except Exception as e:
            logger.warning(f"Could not fetch org stats for {org_id}: {e}")
            return {
                "trust_score": 50.0,
                "claim_volume_30d": 0,
                "avg_claim_amount": 0.0,
                "historical_fraud_rate": 0.05,
            }

    def _get_procedure_avg_amount(self, procedure_codes: list[str]) -> float:
        """Look up average amount for given procedure codes across platform."""
        if not procedure_codes:
            return 0.0
        try:
            result = self._db.table("claims").select("claimed_amount").contains(
                "procedure_codes", procedure_codes[:3]
            ).limit(100).execute().data
            amounts = [float(r["claimed_amount"]) for r in result if r.get("claimed_amount")]
            return sum(amounts) / len(amounts) if amounts else 0.0
        except Exception:
            return 0.0

    def _check_duplicate(self, claim: dict) -> bool:
        """Check if a similar claim exists in the system (same patient + codes within 90 days)."""
        if not claim.get("patient_id") or not claim.get("procedure_codes"):
            return False
        try:
            from datetime import timedelta
            cutoff = (datetime.utcnow() - timedelta(days=90)).isoformat()
            dupes = self._db.table("claims").select("id").eq(
                "patient_id", claim["patient_id"]
            ).neq("id", claim["id"]).gte("created_at", cutoff).execute().data
            return len(dupes) > 0
        except Exception:
            return False

    def _check_rapid_readmission(self, claim: dict) -> bool:
        """Check for readmission within 30 days of a prior discharge."""
        if not claim.get("patient_id") or not claim.get("admission_date"):
            return False
        try:
            from datetime import timedelta
            adm_date = datetime.fromisoformat(str(claim["admission_date"]))
            cutoff = (adm_date - timedelta(days=30)).isoformat()

            prior = self._db.table("claims").select("discharge_date").eq(
                "patient_id", claim["patient_id"]
            ).neq("id", claim["id"]).gte("discharge_date", cutoff).lt(
                "discharge_date", adm_date.isoformat()
            ).execute().data
            return len(prior) > 0
        except Exception:
            return False

    def _is_weekend(self, claim: dict) -> bool:
        adm = claim.get("admission_date")
        if not adm:
            return False
        try:
            d = datetime.fromisoformat(str(adm))
            return d.weekday() >= 5
        except Exception:
            return False

    def _is_holiday(self, claim: dict) -> bool:
        adm = claim.get("admission_date")
        if not adm:
            return False
        try:
            d = datetime.fromisoformat(str(adm))
            return (d.month, d.day) in HOLIDAY_MONTHS_DAYS
        except Exception:
            return False

    def _compute_length_of_stay(self, claim: dict) -> int:
        try:
            adm = datetime.fromisoformat(str(claim["admission_date"]))
            dis = datetime.fromisoformat(str(claim["discharge_date"]))
            return max(0, (dis - adm).days)
        except Exception:
            return 0

    def _ocr_completeness(self, ocr_data: dict) -> tuple[float, int]:
        """Returns (completeness_score, missing_fields_count)."""
        required_fields = ["patient_name", "admission_date", "diagnosis", "total_amount"]
        present = sum(1 for f in required_fields if ocr_data.get(f))
        missing = len(required_fields) - present
        return round(present / len(required_fields), 3), missing

    def build_features(
        self,
        claim: dict,
        ocr_data: Optional[dict] = None,
        nlp_inconsistency_score: float = 0.0,
    ) -> ClaimFeatures:
        """
        Build a complete ClaimFeatures vector from raw claim data.
        """
        org_stats = self._get_org_stats(claim["hospital_org_id"])
        claimed_amount = float(claim.get("claimed_amount", 0))

        proc_codes = claim.get("procedure_codes", [])
        diag_codes = claim.get("diagnosis_codes", [])
        proc_avg = self._get_procedure_avg_amount(proc_codes)

        amount_vs_org_avg = (
            claimed_amount / org_stats["avg_claim_amount"]
            if org_stats["avg_claim_amount"] > 0 else 1.0
        )
        amount_vs_proc_avg = (
            claimed_amount / proc_avg if proc_avg > 0 else 1.0
        )

        ocr_completeness, missing_fields = self._ocr_completeness(ocr_data or {})

        # Patient age from OCR or metadata
        patient_age = 0
        if ocr_data and ocr_data.get("dob"):
            try:
                dob = datetime.strptime(str(ocr_data["dob"]), "%m/%d/%Y")
                patient_age = (datetime.utcnow() - dob).days // 365
            except Exception:
                pass
        if not patient_age and claim.get("patient_metadata", {}).get("age"):
            patient_age = int(claim["patient_metadata"]["age"])

        return ClaimFeatures(
            claimed_amount=claimed_amount,
            patient_age=patient_age,
            length_of_stay=self._compute_length_of_stay(claim),
            procedure_count=len(proc_codes),
            diagnosis_count=len(diag_codes),
            org_trust_score=org_stats["trust_score"],
            org_historical_fraud_rate=org_stats["historical_fraud_rate"],
            org_claim_volume_30d=org_stats["claim_volume_30d"],
            amount_vs_org_avg=amount_vs_org_avg,
            amount_vs_procedure_avg=amount_vs_proc_avg,
            is_weekend_admission=int(self._is_weekend(claim)),
            is_holiday=int(self._is_holiday(claim)),
            has_high_value_procedures=int(
                any(str(c)[0] in HIGH_VALUE_CPT_PREFIXES for c in proc_codes)
            ),
            duplicate_claim_flag=int(self._check_duplicate(claim)),
            rapid_readmission=int(self._check_rapid_readmission(claim)),
            unusual_provider_combo=0,  # TODO: graph-based detection
            nlp_inconsistency_score=nlp_inconsistency_score,
            nlp_urgency_score=0.0,
            ocr_completeness_score=ocr_completeness,
            missing_required_fields=missing_fields,
        )