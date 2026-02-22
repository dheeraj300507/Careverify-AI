"""
CareVerify - OCR Pipeline
Extracts structured data from medical documents using Tesseract / EasyOCR
"""

from __future__ import annotations
import io
import logging
import re
from typing import Optional
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class OCRResult:
    raw_text: str
    confidence: float
    structured_data: dict = field(default_factory=dict)
    extracted_fields: dict = field(default_factory=dict)
    page_count: int = 1
    engine_used: str = "tesseract"


class OCRPipeline:
    """
    Multi-engine OCR pipeline.
    Tries EasyOCR first (better accuracy on medical docs), falls back to Tesseract.
    """

    # Medical document field patterns
    FIELD_PATTERNS = {
        "patient_name": r"(?:patient|name)[:\s]+([A-Z][a-z]+ [A-Z][a-z]+)",
        "dob": r"(?:date of birth|dob|d\.o\.b)[:\s]+(\d{1,2}[/\-]\d{1,2}[/\-]\d{2,4})",
        "admission_date": r"(?:admission date|admitted)[:\s]+(\d{1,2}[/\-]\d{1,2}[/\-]\d{2,4})",
        "discharge_date": r"(?:discharge date|discharged)[:\s]+(\d{1,2}[/\-]\d{1,2}[/\-]\d{2,4})",
        "diagnosis": r"(?:diagnosis|dx)[:\s]+([A-Z][^.\n]{10,80})",
        "total_amount": r"(?:total|amount due|grand total)[:\s]*\$?([\d,]+\.?\d*)",
        "provider_npi": r"(?:npi|national provider)[:\s]+(\d{10})",
        "claim_id": r"(?:claim\s*(?:id|number|#))[:\s]+([A-Z0-9\-]+)",
        "icd_codes": r"(?:ICD|diagnosis code)[:\s]+([A-Z]\d+\.?\d*)",
        "cpt_codes": r"(?:CPT|procedure code)[:\s]+(\d{5}(?:\-\w+)?)",
    }

    def __init__(self):
        self._easy_ocr = None
        self._tesseract_available = False
        self._check_engines()

    def _check_engines(self):
        try:
            import pytesseract
            pytesseract.get_tesseract_version()
            self._tesseract_available = True
            logger.info("Tesseract OCR available")
        except Exception:
            logger.warning("Tesseract not available")

        try:
            import easyocr
            self._easy_ocr_module = easyocr
            logger.info("EasyOCR available")
        except ImportError:
            self._easy_ocr_module = None

    def _load_easyocr(self):
        if self._easy_ocr is None and self._easy_ocr_module:
            self._easy_ocr = self._easy_ocr_module.Reader(["en"], gpu=False, verbose=False)

    def _extract_with_easyocr(self, image_bytes: bytes) -> OCRResult:
        """Use EasyOCR for text extraction."""
        self._load_easyocr()
        import numpy as np
        from PIL import Image

        image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        image_array = np.array(image)

        results = self._easy_ocr.readtext(image_array, detail=1, paragraph=True)
        texts = []
        confidences = []

        for (_, text, conf) in results:
            texts.append(text)
            confidences.append(conf)

        raw_text = "\n".join(texts)
        avg_confidence = sum(confidences) / len(confidences) if confidences else 0.0

        return OCRResult(
            raw_text=raw_text,
            confidence=round(avg_confidence, 4),
            engine_used="easyocr",
        )

    def _extract_with_tesseract(self, image_bytes: bytes) -> OCRResult:
        """Use Tesseract for text extraction."""
        import pytesseract
        from PIL import Image

        image = Image.open(io.BytesIO(image_bytes)).convert("RGB")

        # Use HOCR for confidence data
        try:
            data = pytesseract.image_to_data(image, output_type=pytesseract.Output.DICT)
            words = [w for w in data["text"] if w.strip()]
            confidences = [
                c / 100.0 for c, w in zip(data["conf"], data["text"])
                if w.strip() and c > 0
            ]
            raw_text = pytesseract.image_to_string(image, config="--psm 6")
            avg_confidence = sum(confidences) / len(confidences) if confidences else 0.5

        except Exception as e:
            logger.error(f"Tesseract error: {e}")
            raw_text = ""
            avg_confidence = 0.0

        return OCRResult(
            raw_text=raw_text,
            confidence=round(avg_confidence, 4),
            engine_used="tesseract",
        )

    def _process_pdf(self, pdf_bytes: bytes) -> OCRResult:
        """Convert PDF to images then run OCR on each page."""
        try:
            import fitz  # PyMuPDF
            doc = fitz.open(stream=pdf_bytes, filetype="pdf")
            all_text = []
            all_confidences = []
            page_count = len(doc)

            for page in doc:
                mat = fitz.Matrix(2.0, 2.0)  # 2x zoom for better OCR
                pix = page.get_pixmap(matrix=mat)
                image_bytes = pix.tobytes("png")
                result = self._run_ocr_on_image(image_bytes)
                all_text.append(result.raw_text)
                all_confidences.append(result.confidence)

            combined_text = "\n\n--- PAGE BREAK ---\n\n".join(all_text)
            avg_conf = sum(all_confidences) / len(all_confidences) if all_confidences else 0.0

            return OCRResult(
                raw_text=combined_text,
                confidence=round(avg_conf, 4),
                page_count=page_count,
                engine_used="pdf+ocr",
            )

        except ImportError:
            # Fallback: extract embedded text from PDF
            try:
                import pdfplumber
                with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
                    texts = [page.extract_text() or "" for page in pdf.pages]
                return OCRResult(
                    raw_text="\n\n".join(texts),
                    confidence=0.9,  # Embedded text is high confidence
                    page_count=len(texts),
                    engine_used="pdfplumber",
                )
            except Exception as e:
                logger.error(f"PDF processing failed: {e}")
                return OCRResult(raw_text="", confidence=0.0)

    def _run_ocr_on_image(self, image_bytes: bytes) -> OCRResult:
        """Run best available OCR engine on image bytes."""
        if self._easy_ocr_module:
            try:
                return self._extract_with_easyocr(image_bytes)
            except Exception as e:
                logger.warning(f"EasyOCR failed, falling back to Tesseract: {e}")

        if self._tesseract_available:
            try:
                return self._extract_with_tesseract(image_bytes)
            except Exception as e:
                logger.error(f"Tesseract failed: {e}")

        logger.error("No OCR engine available")
        return OCRResult(raw_text="", confidence=0.0, engine_used="none")

    def extract_structured_fields(self, text: str) -> dict:
        """Apply regex patterns to extract structured medical fields."""
        extracted = {}
        text_upper = text.upper()

        for field_name, pattern in self.FIELD_PATTERNS.items():
            matches = re.findall(pattern, text, re.IGNORECASE)
            if matches:
                extracted[field_name] = matches[0] if len(matches) == 1 else matches

        # Extract all ICD codes
        icd_matches = re.findall(r"\b[A-Z]\d{2}\.?\d{0,3}\b", text_upper)
        if icd_matches:
            extracted["all_icd_codes"] = list(set(icd_matches))

        # Extract all CPT codes
        cpt_matches = re.findall(r"\b\d{5}\b", text)
        if cpt_matches:
            extracted["all_cpt_codes"] = list(set(cpt_matches))

        # Extract dollar amounts
        amounts = re.findall(r"\$\s*([\d,]+\.?\d*)", text)
        if amounts:
            extracted["dollar_amounts"] = [float(a.replace(",", "")) for a in amounts]

        return extracted

    def process(self, file_bytes: bytes, mime_type: str) -> OCRResult:
        """
        Main entry point. Process a document and return OCR result.
        """
        if mime_type == "application/pdf":
            result = self._process_pdf(file_bytes)
        else:
            result = self._run_ocr_on_image(file_bytes)

        # Extract structured fields
        if result.raw_text:
            result.structured_data = self.extract_structured_fields(result.raw_text)
            result.extracted_fields = result.structured_data  # alias

        return result


# Singleton
_ocr_instance: Optional[OCRPipeline] = None


def get_ocr_pipeline() -> OCRPipeline:
    global _ocr_instance
    if _ocr_instance is None:
        _ocr_instance = OCRPipeline()
    return _ocr_instance