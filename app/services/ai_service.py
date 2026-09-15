"""Shared handling for Bedrock agent responses."""

import json
import logging
import re


def parse_agent_response(response):
    text = "".join(
        block.get("text", "") for block in response["output"]["message"]["content"]
    ).strip()
    text = re.sub(r"^```(?:json)?\s*\n?(.*?)\n?```$", r"\1", text, flags=re.DOTALL | re.IGNORECASE)
    result = json.loads(text)
    if not isinstance(result, dict):
        raise ValueError("Agent response must be an object")
    return result


def log_agent_fallback(logger_name, error):
    # Do not log request contents, credentials, or provider response bodies.
    code = getattr(error, "response", {}).get("Error", {}).get("Code", type(error).__name__)
    logging.getLogger(logger_name).warning(
        "Bedrock agent failed (%s); using local fallback checks.", code
    )
