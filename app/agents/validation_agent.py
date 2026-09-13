import json
import os
import re
from datetime import datetime
from pathlib import Path
from string import Template

try:
    from dotenv import load_dotenv
except ImportError:
    def load_dotenv():
        return False

load_dotenv()

MODEL_ID = os.getenv("AWS_BEDROCK_MODEL_ID")
PROMPT_PATH = Path(__file__).resolve().parents[2] / "prompts" / "validation_agent_prompt.txt"


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

    return {
        "validation_status": validation_status,
        "reasons": reasons,
        "ai_confidence": confidence,
    }


def _fallback_validation(document_text, title="", description="", expected_period="", filename=""):
    evidence = " ".join((document_text, title, description, filename)).lower()
    reasons = []

    if not document_text or not document_text.strip():
        reasons.append("missing_document_text")

    detected_dates = _extract_dates(evidence)
    if not detected_dates:
        reasons.append("missing_date")
    elif expected_period:
        try:
            expected = datetime.strptime(expected_period[:7], "%Y-%m")
        except ValueError:
            expected = None
        if expected and not any(
            detected.year == expected.year and detected.month == expected.month
            for detected in detected_dates
        ):
            reasons.append("date_out_of_period")

    if "blurry" in evidence or "cut off" in evidence or "unreadable" in evidence:
        reasons.append("image_quality_issue")

    logical_issue_terms = (
        "total mismatch",
        "totals mismatch",
        "does not match",
        "do not match",
        "inconsistent",
        "contradictory",
        "invalid total",
    )
    if any(term in evidence for term in logical_issue_terms):
        reasons.append("totals_mismatch")

    return {
        "validation_status": "Incomplete" if reasons else "Complete",
        "reasons": reasons,
        "confidence": 0.85 if reasons else 0.95,
    }


def _extract_dates(value):
    dates = []
    patterns = (
        ("%Y-%m-%d", r"\b\d{4}-\d{2}-\d{2}\b"),
        ("%m/%d/%Y", r"\b\d{1,2}/\d{1,2}/\d{4}\b"),
        ("%m/%d/%y", r"\b\d{1,2}/\d{1,2}/\d{2}\b"),
        ("%b %d %Y", r"\b(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\s+\d{1,2},?\s+\d{4}\b"),
    )
    for date_format, pattern in patterns:
        for match in re.findall(pattern, value, re.IGNORECASE):
            normalized = match.replace(",", "")
            if date_format == "%b %d %Y":
                normalized = " ".join(normalized.split()[:3])
            try:
                dates.append(datetime.strptime(normalized, date_format))
            except ValueError:
                if date_format != "%b %d %Y":
                    continue
                try:
                    dates.append(datetime.strptime(normalized, "%B %d %Y"))
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
    prompt = Template(PROMPT_PATH.read_text(encoding="utf-8")).safe_substitute(
        title=title,
        description=description,
        document_text=document_text,
        expected_period=expected_period,
    )

    result = None
    if MODEL_ID:
        try:
            import boto3

            bedrock = boto3.client("bedrock-runtime", region_name=os.getenv("AWS_REGION", "us-east-1"))
            message_content = [{"text": prompt}]
            image_formats = {
                "image/jpeg": "jpeg",
                "image/png": "png",
                "image/gif": "gif",
                "image/webp": "webp",
            }
            image_format = image_formats.get(content_type)
            if image_format and document_bytes:
                message_content.append(
                    {"image": {"format": image_format, "source": {"bytes": document_bytes}}}
                )

            response = bedrock.converse(
                modelId=MODEL_ID,
                messages=[{"role": "user", "content": message_content}],
                inferenceConfig={"maxTokens": 200, "temperature": 0},
            )
            response_text = response["output"]["message"]["content"][0]["text"]
            result = json.loads(response_text)
        except Exception:
            result = None

    if not isinstance(result, dict):
        result = _fallback_validation(document_text, title, description, expected_period, filename)

    return _normalize_result(result)
