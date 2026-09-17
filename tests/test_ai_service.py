import pytest

from app.services.ai_service import parse_agent_response


def test_parse_agent_response_accepts_markdown_json_with_extra_text():
    response = {
        "output": {
            "message": {
                "content": [
                    {
                        "text": "```json\n{\n  \"document_type\": \"Invoice\",\n  \"confidence\": 0.97\n}\n```\n\nSome trailing note"
                    }
                ]
            }
        }
    }

    assert parse_agent_response(response) == {"document_type": "Invoice", "confidence": 0.97}


def test_parse_agent_response_accepts_json_embedded_in_text():
    response = {
        "output": {
            "message": {
                "content": [
                    {"text": "Here is the result: {\"document_type\":\"Receipt\",\"confidence\":0.91} Thanks."}
                ]
            }
        }
    }

    assert parse_agent_response(response) == {"document_type": "Receipt", "confidence": 0.91}
