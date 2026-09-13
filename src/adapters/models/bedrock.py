"""Development Bedrock probes. Not the application LanguageAdapter contract."""
import json
import os

import boto3
from botocore.config import Config


def client(service):
    return boto3.client(
        service, region_name=os.environ["AWS_REGION"],
        config=Config(connect_timeout=10, read_timeout=120,
                      retries={"mode": "standard", "total_max_attempts": 3}),
    )


def converse(text, runtime=None):
    max_tokens = int(os.environ["MODEL_MAX_TOKENS"])
    temperature = float(os.environ["MODEL_TEMPERATURE"])
    if not 1 <= max_tokens <= 4096 or not 0 <= temperature <= 1:
        raise ValueError("MODEL_MAX_TOKENS must be 1..4096 and MODEL_TEMPERATURE 0..1")
    response = (runtime or client("bedrock-runtime")).converse(
        modelId=os.environ["BEDROCK_MODEL_ID"],
        system=[{"text": "You are a development smoke-test assistant. Use synthetic examples only. "
                         "Do not make coverage decisions, assign claims, or claim to take actions."}],
        messages=[{"role": "user", "content": [{"text": text}]}],
        inferenceConfig={"maxTokens": max_tokens, "temperature": temperature},
    )
    return {"text": "\n".join(part["text"] for part in response["output"]["message"]["content"] if "text" in part),
            "usage": response["usage"], "stop_reason": response["stopReason"]}


def embed(text, runtime=None):
    dimensions = int(os.environ["BEDROCK_EMBEDDING_DIMENSIONS"])
    if dimensions not in (256, 512, 1024):
        raise ValueError("Titan v2 dimensions must be 256, 512, or 1024")
    response = (runtime or client("bedrock-runtime")).invoke_model(
        modelId=os.environ["BEDROCK_EMBEDDING_MODEL_ID"],
        contentType="application/json", accept="application/json",
        body=json.dumps({"inputText": text, "dimensions": dimensions, "normalize": True}),
    )
    body = json.loads(response["body"].read())
    if len(body["embedding"]) != dimensions:
        raise ValueError("Embedding dimension differs from configured vector index")
    return {"dimensions": len(body["embedding"]), "input_tokens": body["inputTextTokenCount"]}


def retrieve(text, runtime=None):
    count = int(os.environ["KNOWLEDGE_RESULT_COUNT"])
    if not 1 <= count <= 10:
        raise ValueError("KNOWLEDGE_RESULT_COUNT must be 1..10")
    response = (runtime or client("bedrock-agent-runtime")).retrieve(
        knowledgeBaseId=os.environ["BEDROCK_KNOWLEDGE_BASE_ID"],
        retrievalQuery={"text": text},
        retrievalConfiguration={"vectorSearchConfiguration": {
            "numberOfResults": count,
            "filter": {"andAll": [
                {"equals": {"key": "audience", "value": "customer"}},
                {"equals": {"key": "approved", "value": True}},
            ]},
        }},
    )
    # Preserve citations and metadata for inspection; never interpret retrieval as authorization.
    return {"results": response["retrievalResults"]}
