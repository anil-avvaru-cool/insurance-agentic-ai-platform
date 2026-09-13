"""IAM-protected AgentCore smoke runtime; does not expose application workflows."""
import os
from contextlib import asynccontextmanager

from botocore.exceptions import BotoCoreError, ClientError
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from typing import Literal

from adapters.models.bedrock import converse, retrieve


@asynccontextmanager
async def lifespan(app):
    for name in ("AWS_REGION", "BEDROCK_MODEL_ID", "BEDROCK_KNOWLEDGE_BASE_ID",
                 "MODEL_MAX_TOKENS", "MODEL_TEMPERATURE", "KNOWLEDGE_RESULT_COUNT"):
        if not os.environ[name].strip():
            raise ValueError(f"{name} must be configured")
    yield


app = FastAPI(lifespan=lifespan)


class Invocation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    operation: Literal["converse", "retrieve"]
    text: str = Field(min_length=1, max_length=8000)


@app.get("/ping")
def ping():
    return {"status": "Healthy"}


@app.post("/invocations")
def invoke(request: Invocation):
    try:
        return (converse if request.operation == "converse" else retrieve)(request.text)
    except (BotoCoreError, ClientError):
        # Do not return provider internals or input text through the HTTP error path.
        raise HTTPException(status_code=502, detail="AWS model or retrieval request failed") from None
