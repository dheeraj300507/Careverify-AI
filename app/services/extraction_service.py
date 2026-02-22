"""
CareVerify - Medical Fact Extraction Service
Identifies diagnosis, procedures, policy alignment, and document risks.
"""

import re
from dataclasses import dataclass
from typing import Dict, List


@dataclass
class ExtractedFacts:
    diagnosis_codes: List[str]
    procedure_codes: List[str]
    physician_identifiers: List[str]
    authorization_indicators: List[str]
    matched_policies: List[str]
    detected_risks: List[str]
    is_consistent: bool
    confidence: float
    summary: str

    def to_dict(self) -> Dict[str, object]:
        return {
            "diagnosis_codes": self.diagnosis_codes,
            "procedure_codes": self.procedure_codes,
            "physician_identifiers": self.physician_identifiers,
            "authorization_indicators": self.authorization_indicators,
            "matched_policies": self.matched_policies,
            "detected_risks": self.detected_risks,
            "is_consistent": self.is_consistent,
            "confidence": self.confidence,
            "summary": self.summary,
        }


class MedicalExtractionService:
    """
    Modular extraction service. Current implementation uses deterministic regex
    and keyword heuristics and can be replaced by model-backed extraction later.
    """

    ICD_PATTERN = re.compile(r"\b[A-TV-Z][0-9][0-9A-Z](?:\.[0-9A-Z]{1,4})?\b", re.IGNORECASE)
    CPT_PATTERN = re.compile(r"\b\d{5}\b")
    NPI_PATTERN = re.compile(r"\b(?:NPI|Provider(?:\s+ID)?|Physician\s+ID)[:\s#-]*([0-9]{10})\b", re.IGNORECASE)
    DOCTOR_PATTERN = re.compile(r"\b(?:Dr\.?|Physician)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)\b")

    def _extract_authorization_indicators(self, text: str) -> List[str]:
        matches: List[str] = []
        if re.search(r"\b(pre[-\s]?authori[sz]ed|prior auth(?:orization)?)\b", text, re.IGNORECASE):
            matches.append("PRIOR_AUTH_DECLARED")
        if re.search(r"\b(auth(?:orization)?\s*(?:#|no\.?)?\s*[A-Z0-9\-]{4,})\b", text, re.IGNORECASE):
            matches.append("AUTH_REFERENCE_PRESENT")
        return sorted(set(matches))

    def _extract_physician_identifiers(self, text: str) -> List[str]:
        physician_ids = [f"NPI:{npi}" for npi in self.NPI_PATTERN.findall(text)]
        physician_names = [f"PROVIDER:{name}" for name in self.DOCTOR_PATTERN.findall(text)]
        return sorted(set(physician_ids + physician_names))

    def _build_policy_and_risk_signals(
        self,
        diagnosis_codes: List[str],
        procedure_codes: List[str],
        physician_identifiers: List[str],
        authorization_indicators: List[str],
    ) -> tuple[List[str], List[str], bool]:
        policies: List[str] = []
        risks: List[str] = []

        if diagnosis_codes and procedure_codes:
            policies.append("DIAGNOSIS_PROCEDURE_LINKED")
        else:
            risks.append("DIAGNOSIS_PROCEDURE_MISMATCH")

        if authorization_indicators:
            policies.append("PRIOR_AUTH_MATCHED")
        else:
            risks.append("MISSING_AUTHORIZATION")

        if physician_identifiers:
            policies.append("PROVIDER_IDENTIFIER_PRESENT")
        else:
            risks.append("MISSING_PROVIDER_IDENTIFIER")

        if not diagnosis_codes and not procedure_codes:
            risks.append("NO_BILLABLE_CODE_EXTRACTED")

        is_consistent = (
            "DIAGNOSIS_PROCEDURE_LINKED" in policies
            and "PRIOR_AUTH_MATCHED" in policies
            and "PROVIDER_IDENTIFIER_PRESENT" in policies
        )
        return sorted(set(policies)), sorted(set(risks)), is_consistent

    def extract(self, text: str) -> ExtractedFacts:
        """
        Parse text into medical facts and policy-risk context.
        """
        if not text:
            return ExtractedFacts([], [], [], [], [], ["NO_TEXT_AVAILABLE"], False, 0.0, "No text provided")

        diagnosis_codes = sorted(set(code.upper() for code in self.ICD_PATTERN.findall(text)))
        procedure_codes = sorted(set(self.CPT_PATTERN.findall(text)))
        physician_identifiers = self._extract_physician_identifiers(text)
        authorization_indicators = self._extract_authorization_indicators(text)

        matched_policies, detected_risks, is_consistent = self._build_policy_and_risk_signals(
            diagnosis_codes=diagnosis_codes,
            procedure_codes=procedure_codes,
            physician_identifiers=physician_identifiers,
            authorization_indicators=authorization_indicators,
        )

        confidence = 0.95 if is_consistent else 0.72 if diagnosis_codes or procedure_codes else 0.4
        summary = (
            f"Extracted {len(diagnosis_codes)} diagnosis code(s), {len(procedure_codes)} procedure code(s), "
            f"{len(physician_identifiers)} provider identifier(s)."
        )

        return ExtractedFacts(
            diagnosis_codes=diagnosis_codes,
            procedure_codes=procedure_codes,
            physician_identifiers=physician_identifiers,
            authorization_indicators=authorization_indicators,
            matched_policies=matched_policies,
            detected_risks=detected_risks,
            is_consistent=is_consistent,
            confidence=confidence,
            summary=summary,
        )

# Singleton
_extraction_service = None

def get_extraction_service() -> MedicalExtractionService:
    global _extraction_service
    if _extraction_service is None:
        _extraction_service = MedicalExtractionService()
    return _extraction_service
