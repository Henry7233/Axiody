"""Shared Bedrock client lifecycle and agent-response parsing."""

import json
import logging
import re
import base64
import os
import urllib.error
import urllib.request
from functools import lru_cache


@lru_cache(maxsize=1)
def get_bedrock_client(region_name):
    if os.getenv("LLM_GATEWAY_URL") and os.getenv("LLM_GATEWAY_API_KEY"):
        return GatewayClient(
            os.getenv("LLM_GATEWAY_URL"),
            os.getenv("LLM_GATEWAY_API_KEY"),
        )

    import boto3

    return boto3.client("bedrock-runtime", region_name=region_name)


class GatewayClient:
    """Expose an OpenAI-compatible gateway through the Bedrock converse shape."""

    def __init__(self, base_url, api_key):
        self.url = base_url.rstrip("/") + "/v1/chat/completions"
        self.api_key = api_key

    def converse(self, modelId, messages, inferenceConfig=None):
        gateway_messages = []
        for message in messages:
            content = []
            for block in message.get("content", []):
                if "text" in block:
                    content.append({"type": "text", "text": block["text"]})
                elif "image" in block:
                    image = block["image"]
                    encoded = base64.b64encode(image["source"]["bytes"]).decode("ascii")
                    content.append(
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/{image['format']};base64,{encoded}"
                            },
                        }
                    )
            gateway_messages.append({"role": message["role"], "content": content})

        inferenceConfig = inferenceConfig or {}
        payload = json.dumps(
            {
                "model": modelId,
                "messages": gateway_messages,
                "max_tokens": inferenceConfig.get("maxTokens", 400),
                "temperature": inferenceConfig.get("temperature", 0),
            }
        ).encode("utf-8")
        request = urllib.request.Request(
            self.url,
            data=payload,
            method="POST",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                result = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as error:
            raise RuntimeError(f"Gateway HTTP {error.code}") from error
        except urllib.error.URLError as error:
            raise RuntimeError("Gateway connection failed") from error

        usage = result.get("usage") or {}
        if os.getenv("DEBUG_LLM", "").strip().lower() in {"1", "true", "yes", "on"}:
            print(
                "LLM usage:",
                {
                    "prompt_tokens": usage.get("prompt_tokens"),
                    "completion_tokens": usage.get("completion_tokens"),
                    "total_tokens": usage.get("total_tokens"),
                },
            )

        text = result["choices"][0]["message"]["content"]
        return {"output": {"message": {"content": [{"text": text}]}}}


def _extract_json_from_text(text):
    cleaned = text.strip()
    if not cleaned:
        raise json.JSONDecodeError("Empty response", text, 0)

    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*```$", "", cleaned, flags=re.IGNORECASE)

    decoder = json.JSONDecoder()
    for index, char in enumerate(cleaned):
        if char not in "[{":
            continue
        try:
            value, _ = decoder.raw_decode(cleaned[index:])
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            return value

    raise json.JSONDecodeError("No JSON object found in agent response", text, 0)


def parse_agent_response(response):
    text = "".join(
        block.get("text", "") for block in response["output"]["message"]["content"]
    ).strip()
    result = _extract_json_from_text(text)
    if not isinstance(result, dict):
        raise ValueError("Agent response must be an object")
    return result


def log_agent_fallback(logger_name, error):
    # Do not log request contents, credentials, or provider response bodies.
    code = getattr(error, "response", {}).get("Error", {}).get("Code", type(error).__name__)
    logging.getLogger(logger_name).warning(
        "AI agent failed (%s); using local fallback checks.", code
    )
