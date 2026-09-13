"""Required local configuration; never load cloud credentials or model secrets."""
import json
import os
from pathlib import Path
from apps.storage import Store
from apps.service import Application
from adapters.insurance.synthetic import SyntheticCore
from insurance_domain.urgency import screen
from insurance_domain.intake import AutoDraft


def configured_application():
    if os.environ["APP_MODE"] != "synthetic_local":
        raise ValueError("Only synthetic_local mode is implemented")
    screen(AutoDraft("config_validation"))
    db_path, core_path = os.environ["APP_DB_PATH"], os.environ["CORE_DB_PATH"]
    if Path(db_path).resolve() == Path(core_path).resolve():
        raise ValueError("Core and application databases must be separate")
    return Application(Store(db_path), SyntheticCore(os.environ["FIXTURES_PATH"], core_path))


def configured_identities():
    identities = json.loads(os.environ["LOCAL_IDENTITIES_JSON"])
    if not identities:
        raise ValueError("Local identities are required")
    for token, identity in identities.items():
        if len(token) < 16 or not identity["subject"] or identity["role"] not in ("customer", "employee"):
            raise ValueError("Invalid local identity")
    return identities
