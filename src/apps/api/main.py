"""Local authenticated API. Static bearer fixtures are not production identity."""
import hmac
from pathlib import Path
from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.exceptions import RequestValidationError
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from apps.config import configured_application, configured_identities
from contracts.api import Message, IntakeConfirmation, ReviewDecision
from insurance_domain.intake import DomainError


def create_app(application=None, identities=None):
    application = application if application is not None else configured_application()
    identities = identities if identities is not None else configured_identities()
    app = FastAPI(title="Synthetic insurance journey", version="0.1.0")
    app.state.application = application
    bearer = HTTPBearer(auto_error=False)

    def identity(credentials: HTTPAuthorizationCredentials | None = Depends(bearer)):
        if credentials is not None and credentials.scheme.lower() == "bearer":
            for token, principal in identities.items():
                if hmac.compare_digest(credentials.credentials, token):
                    return principal
        raise HTTPException(401, "unauthenticated", headers={"WWW-Authenticate": "Bearer"})

    def customer(principal=Depends(identity)):
        if principal["role"] != "customer":
            raise HTTPException(403, "customer_required")
        return principal["subject"]

    def employee(principal=Depends(identity)):
        if principal["role"] != "employee":
            raise HTTPException(403, "employee_required")
        return principal["subject"]

    @app.exception_handler(DomainError)
    async def domain_error(request, exc):
        code = str(exc)
        status = 404 if code == "not_found" else 409 if code in {
            "stale_version", "stale_confirmation", "stale_review", "conversation_busy",
            "idempotency_conflict", "submission_pending", "submission_already_started"} else 422
        return JSONResponse({"error": code}, status_code=status)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request, exc):
        # Do not echo pasted request values or tokens in validation responses.
        return JSONResponse({"error": "invalid_request"}, status_code=422)

    @app.get("/", response_class=HTMLResponse, include_in_schema=False)
    def index():
        return Path(__file__).parents[1].joinpath("web/index.html").read_text()

    @app.post("/v1/conversations", status_code=201)
    def create(owner=Depends(customer)):
        return application.create(owner)

    @app.get("/v1/conversations/{conversation}")
    def get_conversation(conversation: str, owner=Depends(customer)):
        with application.store.transaction() as db:
            return application.customer_state(application.owned(db, conversation, owner))

    @app.post("/v1/conversations/{conversation}/messages", status_code=202)
    def message(conversation: str, body: Message, owner=Depends(customer)):
        return application.enqueue(owner, conversation, "message_" + body.message_id,
                                   {"kind": "message", "message": body.model_dump()})

    @app.post("/v1/conversations/{conversation}/intake-confirmations", status_code=202)
    def confirm(conversation: str, body: IntakeConfirmation, owner=Depends(customer)):
        return application.enqueue(owner, conversation, f"confirmation_{body.draft_version}",
                                   {"kind": "confirmation", "confirmation": body.model_dump()})

    @app.get("/v1/tasks/{task}")
    def get_task(task: str, owner=Depends(customer)):
        return application.get_task(owner, task)

    @app.get("/v1/reviews")
    def reviews(reviewer=Depends(employee)):
        return {"items": application.reviews()}

    @app.post("/v1/reviews/{review}/decision")
    def decision(review: str, body: ReviewDecision, reviewer=Depends(employee)):
        return application.decide(reviewer, review, body.model_dump())

    return app
