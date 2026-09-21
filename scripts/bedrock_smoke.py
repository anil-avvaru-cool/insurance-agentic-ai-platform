"""Run using uv run --env-file .env with PYTHONPATH=src. All AWS calls are opt-in."""
import argparse
import json
import os
import time
import uuid

from adapters.models.bedrock import client, converse, embed, retrieve
from ingestion.jobs import poll_job


def ingest(runtime=None):
    runtime = runtime or client("bedrock-agent")
    timeout = int(os.environ["KNOWLEDGE_INGESTION_TIMEOUT_SECONDS"])
    if timeout <= 0:
        raise ValueError("KNOWLEDGE_INGESTION_TIMEOUT_SECONDS must be positive")
    args = {"knowledgeBaseId": os.environ["BEDROCK_KNOWLEDGE_BASE_ID"],
            "dataSourceId": os.environ["BEDROCK_DATA_SOURCE_ID"]}
    job = runtime.start_ingestion_job(**args)["ingestionJob"]
    return poll_job(runtime, args, job, timeout, clock=time.monotonic, sleep=time.sleep)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=["models", "converse", "embed", "ingest", "retrieve", "invoke"])
    parser.add_argument("--text", help="Synthetic test input; do not use customer data")
    args = parser.parse_args()
    if args.operation in ("converse", "embed", "retrieve", "invoke") and not args.text:
        parser.error("--text is required for this operation")
    if args.operation == "models":
        result = client("bedrock").list_foundation_models()
    elif args.operation == "ingest":
        result = ingest()
    elif args.operation == "invoke":
        response = client("bedrock-agentcore").invoke_agent_runtime(
            agentRuntimeArn=os.environ["AGENTCORE_RUNTIME_ARN"],
            runtimeSessionId=str(uuid.uuid4()), qualifier="DEFAULT", contentType="application/json",
            payload=json.dumps({"operation": "converse", "text": args.text}).encode(),
        )
        result = json.loads(response["response"].read())
    else:
        result = {"converse": converse, "embed": embed, "retrieve": retrieve}[args.operation](args.text)
    print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    main()
