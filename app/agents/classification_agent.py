import io
import json
import logging
import os
import zipfile
from pathlib import Path
from string import Template
from xml.etree import ElementTree

from pypdf import PdfReader
from pypdf.errors import PyPdfError
from app.services.ai_service import parse_agent_response, log_agent_fallback

try:
    from dotenv import load_dotenv
except ImportError:
    def load_dotenv():
        return False

load_dotenv()

MODEL_ID = os.getenv("AWS_BEDROCK_MODEL_ID")
ALLOWED_DOCUMENT_TYPES = {"Invoice", "Receipt", "Bank Statement", "Other"}
SUCCESS_DOCUMENT_TYPES = ALLOWED_DOCUMENT_TYPES - {"Other"}
PROMPT_PATH = Path(__file__).resolve().parents[2] / "prompts" / "classification_agent_prompt.txt"


def extract_document_text(file_data, filename="", content_type=""):
    extension = os.path.splitext(filename)[1].lower()

    if extension == ".docx":
        return _extract_zip_xml_text(file_data, "word/document.xml")
    if extension in {".xlsx", ".xlsm"}:
        return _extract_zip_xml_text(file_data, "xl/sharedStrings.xml")
    if extension == ".pdf" or content_type == "application/pdf":
        return _extract_pdf_text(file_data)
    if content_type.startswith("text/") or extension in {".txt", ".csv"}:
        return file_data.decode("utf-8", errors="ignore")
    return ""


def _extract_zip_xml_text(file_data, member_name):
    try:
        with zipfile.ZipFile(io.BytesIO(file_data)) as archive:
            xml_data = archive.read(member_name)
        root = ElementTree.fromstring(xml_data)
        return " ".join(value.strip() for value in root.itertext() if value.strip())
    except (ElementTree.ParseError, KeyError, OSError, zipfile.BadZipFile):
        return ""


def _extract_pdf_text(file_data):
    try:
        reader = PdfReader(io.BytesIO(file_data))
        return "\n".join(page.extract_text() or "" for page in reader.pages)
    except (PyPdfError, OSError, ValueError):
        logging.getLogger(__name__).warning("Could not extract PDF document text", exc_info=True)
        return ""


def _normalize_result(result):
    document_type = str(result.get("document_type", "Other")).strip()
    aliases = {
        "bank statement": "Bank Statement",
        "bank statements": "Bank Statement",
        "invoice": "Invoice",
        "receipt": "Receipt",
        "other": "Other",
    }
    document_type = aliases.get(document_type.lower(), "Other")
    try:
        confidence = float(result.get("confidence", 0))
    except (TypeError, ValueError):
        confidence = 0
    if 0 <= confidence <= 1:
        confidence *= 100
    confidence = max(0, min(100, round(confidence, 2)))
    status = "Success" if document_type in SUCCESS_DOCUMENT_TYPES else "Under review"
    return {
        "document_type": document_type,
        "ai_document_type": document_type,
        "ai_confidence": confidence,
        "classification_status": status,
    }


def _fallback_classification(document_text, title, description, filename):
    # PDF text often separates words with tabs or line breaks.
    evidence = " ".join(document_text.lower().split())
    keyword_groups = {
        "Bank Statement": ("bank statement", "account statement", "opening balance", "closing balance", "transaction date"),
        "Invoice": ("invoice", "bill to", "amount due", "due date", "subtotal"),
        "Receipt": ("receipt", "payment received", "paid", "change due", "thank you for your purchase"),
    }
    scores = {
        document_type: sum(1 for keyword in keywords if keyword in evidence)
        for document_type, keywords in keyword_groups.items()
    }
    document_type, score = max(scores.items(), key=lambda item: item[1])
    if score == 0:
        metadata = " ".join(" ".join((title, description, filename)).lower().replace("_", " ").split())
        scores = {
            category: sum(1 for keyword in keywords if keyword in metadata)
            for category, keywords in keyword_groups.items()
        }
        document_type, score = max(scores.items(), key=lambda item: item[1])
    if score == 0:
        return {"document_type": "Other", "confidence": 0}
    return {"document_type": document_type, "confidence": min(95, 70 + score * 5)}


def classify_document(
    document_text,
    title="",
    description="",
    filename="",
    content_type="",
    document_bytes=None,
):

    prompt = Template(PROMPT_PATH.read_text(encoding="utf-8")).safe_substitute(
        title=title,
        description=description,
        document_text=document_text,
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
                inferenceConfig={"maxTokens": 400, "temperature": 0},
            )
            result = parse_agent_response(response)
            if "document_type" not in result or "confidence" not in result:
                raise ValueError("Missing classification fields")
        except Exception as error:
            log_agent_fallback(__name__, error)
            result = None

    if not isinstance(result, dict):
        result = _fallback_classification(document_text, title, description, filename)
    return _normalize_result(result)
