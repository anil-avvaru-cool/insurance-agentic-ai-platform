"""Explicit synthetic-local configuration with an optional model provider."""
import json
import os
from pathlib import Path
from apps.storage import Store
from apps.service import Application
from adapters.insurance.synthetic import SyntheticCore
from insurance_domain.urgency import screen
from insurance_domain.intake import AutoDraft
from workflows.checkpoints import configured_checkpoints


def configured_application():
    if os.environ["APP_MODE"] != "synthetic_local":
        raise ValueError("Only synthetic_local mode is implemented")
    screen(AutoDraft("config_validation"))
    db_path, core_path = os.environ["APP_DB_PATH"], os.environ["CORE_DB_PATH"]
    if Path(db_path).resolve() == Path(core_path).resolve():
        raise ValueError("Core and application databases must be separate")
    checkpoints = configured_checkpoints()
    if checkpoints.backend == "sqlite" and Path(checkpoints.target).resolve() in (Path(db_path).resolve(), Path(core_path).resolve()):
        raise ValueError("Checkpoint database must be separate")
    from adapters.models.language import DisabledLanguage
    from adapters.models.openai import OpenAIAdapter
    provider = os.environ["LLM_PROVIDER"]
    if provider == "disabled":
        language = DisabledLanguage()
    elif provider == "openai":
        language = OpenAIAdapter(os.environ["LLM_MODEL"], os.environ["OPENAI_API_KEY"],
                                 float(os.environ["LLM_TIMEOUT_SECONDS"]), int(os.environ["LLM_MAX_OUTPUT_TOKENS"]))
    else:
        raise ValueError("Unsupported model provider")
    return Application(Store(db_path), SyntheticCore(os.environ["FIXTURES_PATH"], core_path),
                       language=language, checkpoints=checkpoints)


def configured_identities():
    identities = json.loads(os.environ["LOCAL_IDENTITIES_JSON"])
    if not identities:
        raise ValueError("Local identities are required")
    for token, identity in identities.items():
        if len(token) < 16 or not identity["subject"] or identity["role"] not in ("customer", "employee"):
            raise ValueError("Invalid local identity")
    return identities
