import os
import json
import boto3
from dotenv import load_dotenv

load_dotenv()

bedrock = boto3.client(
    "bedrock-runtime",
    region_name=os.getenv("AWS_REGION")
)

MODEL_ID = os.getenv("AWS_BEDROCK_MODEL_ID")


def classify_document(document_text, title="", description=""):

    prompt = f"""
You are the Classification Agent for AXIODY,
a bookkeeping document collection system.

Your job is ONLY to classify the bookkeeping document.

Allowed document types:
- Invoice
- Receipt
- Bank Statement
- Other

Do not classify the technical file format such as:
PDF, DOCX, XLSX, JPG or PNG.

Use the actual contents of the document as the main evidence.
The title and description are only supporting information.

Document title:
{title}

Document description:
{description}

Document content:
{document_text}

Return ONLY valid JSON using this format:

{{
    "document_type": "Invoice"
}}

Rules:
- Use "Invoice" for invoices or bills requesting payment.
- Use "Receipt" for proof that payment has already been made.
- Use "Bank Statement" for bank account transaction statements.
- Use "Other" when the document does not clearly belong to the three categories.
"""

    response = bedrock.converse(
        modelId=MODEL_ID,
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "text": prompt
                    }
                ]
            }
        ],
        inferenceConfig={
            "maxTokens": 100,
            "temperature": 0
        }
    )

    result_text = response["output"]["message"]["content"][0]["text"]

    result = json.loads(result_text)

    return result