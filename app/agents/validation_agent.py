"""Validate document quality, period, and arithmetic consistency."""

import json
import os
import re
from datetime import datetime
from decimal import Decimal
from functools import lru_cache
from pathlib import Path
from string import Template
from app.services.ai_service import get_bedrock_client, parse_agent_response, log_agent_fallback

try:
    from dotenv import load_dotenv
except ImportError:
    def load_dotenv():
        return False

load_dotenv()

MODEL_ID = os.getenv("LLM_MODEL") or os.getenv("AWS_BEDROCK_MODEL_ID")
PROMPT_PATH = Path(__file__).resolve().parents[2] / "prompts" / "validation_agent_prompt.txt"
IMAGE_FORMATS = {
    "image/jpeg": "jpeg",
    "image/png": "png",
    "image/gif": "gif",
    "image/webp": "webp",
}


@lru_cache(maxsize=1)
def _validation_prompt():
    """Read the immutable validation prompt once per process."""
    return PROMPT_PATH.read_text(encoding="utf-8")


def read_image(document_bytes, content_type=""):
    """Extract readable text from an image with the configured vision model."""
    image_format = IMAGE_FORMATS.get(content_type)
    if not MODEL_ID or not image_format or not document_bytes:
        return ""

    try:
        bedrock = get_bedrock_client(os.getenv("AWS_REGION", "us-east-1"))
        response = bedrock.converse(
            modelId=MODEL_ID,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "text": (
                                "Read this document image. Transcribe all visible text, dates, "
                                "amounts, labels, and totals exactly as shown. Return only the "
                                "transcribed text, with no commentary."
                            )
                        },
                        {"image": {"format": image_format, "source": {"bytes": document_bytes}}},
                    ],
                }
            ],
            inferenceConfig={"maxTokens": 1200, "temperature": 0},
        )
        return "".join(
            block.get("text", "") for block in response["output"]["message"]["content"]
        ).strip()
    except Exception as error:
        log_agent_fallback(__name__, error)
        return ""


def _normalize_result(result):
    validation_status = str(result.get("validation_status", "Incomplete")).strip()
    if validation_status not in {"Complete", "Incomplete"}:
        validation_status = "Incomplete"

    try:
        confidence = float(result.get("confidence", 0))
    except (TypeError, ValueError):
        confidence = 0

    confidence = max(0.0, min(1.0, confidence))
    reasons = result.get("reasons")
    if not isinstance(reasons, list):
        reasons = []
    reasons = [str(reason).strip() for reason in reasons if str(reason).strip()]

    if validation_status == "Complete":
        reasons = []

    logical_error = (
        str(result.get("logical_error") or "").strip()
        or str(result.get("validation_reason") or "").strip()
        or (reasons[0] if reasons else "")
    )

    if validation_status == "Complete":
        logical_error = ""

    normalized = {
        "validation_status": validation_status,
        "reasons": reasons,
        "ai_confidence": confidence,
        "logical_error": logical_error,
        "validation_reason": logical_error,
    }
    return normalized


def _bank_summary_reasons(document_text):
    """Reconcile explicit statement summaries with exact decimal arithmetic.

    Skip absent or ambiguous summaries instead of guessing column positions or
    mixing accounts. This check does not depend on filenames or AI availability.
    """
    text = " ".join(document_text.lower().split())
    labels = {
        "opening": r"(?:opening|beginning)\s+balance",
        "closing": r"(?:closing|ending)\s+balance",
        "credits": r"total\s+(?:credits|deposits)",
        "debits": r"total\s+(?:debits|withdrawals)",
    }
    amount = r"(-?\d[\d,]*\.\d{2})(?![\d.,])"
    currency = r"(?:(?:sgd|usd|gbp|eur|aud|s\$|us\$|\$|£|€)\s*)?"
    values = {}
    for name, label in labels.items():
        matches = re.findall(r"\b" + label + r"\s*:?\s*" + currency + amount, text)
        amounts = {Decimal(match.replace(",", "")) for match in matches}
        if len(amounts) != 1:
            return []
        values[name] = amounts.pop()
    expected = values["opening"] + values["credits"] - values["debits"]
    return ["totals_mismatch"] if expected != values["closing"] else []


def _is_bank_statement(document_text, title="", description="", filename=""):
    evidence = " ".join((document_text, title, description, filename)).lower()
    return any(
        marker in evidence
        for marker in ("bank statement", "account statement", "opening balance", "closing balance")
    )


def _date_matches_expected(detected, expected, bank_statement=False):
    if detected.year == expected.year and detected.month == expected.month:
        return True

    # Bank statements may be submitted during the first ten days of the
    # following month, but never across a calendar year boundary.
    return (
        bank_statement
        and expected.day <= 10
        and detected.year == expected.year
        and detected.month == expected.month - 1
    )


def _fallback_validation(document_text, title="", description="", expected_period="", filename=""):
    evidence = " ".join((document_text, title, description, filename)).lower()
    reasons = []

    if not document_text or not document_text.strip():
        reasons.append("missing_document_text")

    # Submission metadata cannot substitute for a date visible in the document.
    detected_dates = _extract_dates(document_text)
    if not detected_dates:
        reasons.append("missing_date")
    elif expected_period:
        try:
            expected = datetime.strptime(expected_period[:10], "%Y-%m-%d")
        except ValueError:
            try:
                expected = datetime.strptime(expected_period[:7], "%Y-%m")
            except ValueError:
                expected = None
        if expected and not any(
            _date_matches_expected(
                detected,
                expected,
                bank_statement=_is_bank_statement(document_text, title, description, filename),
            )
            for detected in detected_dates
        ):
            reasons.append("date_out_of_period")

    if "blurry" in evidence or "cut off" in evidence or "unreadable" in evidence:
        reasons.append("image_quality_issue")

    reasons.extend(_bank_summary_reasons(document_text))
    logical_error = reasons[0] if reasons else ""

    return {
        "validation_status": "Incomplete" if reasons else "Complete",
        "reasons": reasons,
        "confidence": 0.85 if reasons else 0.95,
        "logical_error": logical_error,
        "validation_reason": logical_error,
    }


def _extract_dates(value):
    """Read ISO, numeric and named-month dates; ambiguous numeric dates use D/M/Y."""
    dates = []
    month = r"(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:tember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)"
    patterns = (
        (("%Y-%m-%d",), r"\b\d{4}-\d{1,2}-\d{1,2}\b"),
        (("%d %b %Y", "%d %B %Y"), rf"\b\d{{1,2}}[\s-]+{month}[\s-]+\d{{4}}\b"),
        (("%b %d %Y", "%B %d %Y"), rf"\b{month}\s+\d{{1,2}},?\s+\d{{4}}\b"),
    )
    for date_formats, pattern in patterns:
        for match in re.findall(pattern, value, re.IGNORECASE):
            normalized = match if date_formats == ("%Y-%m-%d",) else " ".join(
                match.replace(",", "").replace("-", " ").split()
            )
            for date_format in date_formats:
                try:
                    dates.append(datetime.strptime(normalized, date_format))
                    break
                except ValueError:
                    continue

    numeric_dates = re.findall(r"\b(\d{1,2})([/.-])(\d{1,2})\2(\d{4}|\d{2})\b", value)
    # Use unambiguous dates elsewhere in the same document to identify US ordering.
    day_first = any(int(first) > 12 for first, _, second, year in numeric_dates)
    month_first = not day_first and any(int(second) > 12 for first, _, second, year in numeric_dates)
    for first, separator, second, year in numeric_dates:
        date_format = "%m/%d/" if month_first else "%d/%m/"
        date_format += "%Y" if len(year) == 4 else "%y"
        try:
            dates.append(datetime.strptime(f"{first}/{second}/{year}", date_format))
        except ValueError:
            continue
    return dates


def validate_document(
    document_text,
    title="",
    description="",
    filename="",
    content_type="",
    expected_period="",
    document_bytes=None,
):
    prompt = Template(_validation_prompt()).safe_substitute(
        title=title,
        description=description,
        document_text=document_text,
        expected_period=expected_period,
    )

    result = None
    if MODEL_ID:
        try:
            bedrock = get_bedrock_client(os.getenv("AWS_REGION", "us-east-1"))
            message_content = [{"text": prompt}]
            image_format = IMAGE_FORMATS.get(content_type)
            if image_format and document_bytes:
                message_content.append(
                    {"image": {"format": image_format, "source": {"bytes": document_bytes}}}
                )

            response = bedrock.converse(
                modelId=MODEL_ID,
                messages=[{"role": "user", "content": message_content}],
                inferenceConfig={"maxTokens": 800, "temperature": 0},
            )
            result = parse_agent_response(response)
            if result.get("validation_status") not in {"Complete", "Incomplete"} or not isinstance(result.get("reasons"), list) or "confidence" not in result:
                raise ValueError("Invalid validation fields")
        except Exception as error:
            log_agent_fallback(__name__, error)
            result = None

    if not isinstance(result, dict):
        result = _fallback_validation(document_text, title, description, expected_period, filename)

    normalized = _normalize_result(result)
    arithmetic_reasons = _bank_summary_reasons(document_text)
    if arithmetic_reasons:
        normalized["validation_status"] = "Incomplete"
        normalized["reasons"] = list(dict.fromkeys(normalized["reasons"] + arithmetic_reasons))

    if normalized["validation_status"] == "Incomplete":
        logical_error = (
            normalized.get("logical_error")
            or normalized.get("validation_reason")
            or (normalized.get("reasons", ["logical_error"])[0] if normalized.get("reasons") else "logical_error")
        )
        normalized["logical_error"] = logical_error
        normalized["validation_reason"] = logical_error
    else:
        normalized["logical_error"] = ""
        normalized["validation_reason"] = ""

    return normalized
