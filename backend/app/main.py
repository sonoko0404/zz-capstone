from __future__ import annotations

import json
import os
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware

from .intake_engine import IntakeEngine
from .knowledge_base import KnowledgeBase
from .llm_client import create_llm_client
from .models import (
    AttachmentListResponse,
    FieldPatchRequest,
    GenerateTicketRequest,
    IntakeMessageResponse,
    LLMStatusResponse,
    MessageRequest,
    RemoveAttachmentRequest,
    ResetRequest,
    StressTestRequest,
    StressTestResponse,
    TicketGenerationResponse,
    ValidationActionRequest,
)
from .real_jira import build_jira_adapter
from .stress_tests import run_stress_test, scenario_catalog
from .ticket_generator import TicketGenerator


BACKEND_ROOT = Path(__file__).resolve().parent.parent
# This standalone local prototype treats backend/.env as the explicit source of
# truth. The opt-out exists for tests and managed deployments that intentionally
# inject process-level secrets.
dotenv_override = os.getenv("DOTENV_OVERRIDE", "true").strip().lower() not in {"0", "false", "no"}
load_dotenv(BACKEND_ROOT / ".env", override=dotenv_override)

app = FastAPI(
    title="AI BI Intake Assistant API",
    version="1.0.0",
    description="Standalone PRD-guided BI intake with static context and optional real Jira ticket creation.",
)

origins = [
    value.strip()
    for value in os.getenv(
        "FRONTEND_ORIGINS",
        "http://localhost:5173,http://127.0.0.1:5173,http://localhost:5174,http://127.0.0.1:5174",
    ).split(",")
    if value.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

knowledge = KnowledgeBase()

# Jira adapter injection point: Mock by default; RealJiraAdapter when
# ENABLE_REAL_JIRA=true and JIRA_* credentials are present in backend/.env.
jira_adapter = build_jira_adapter()
ticket_generator = TicketGenerator(jira_adapter)
engine = IntakeEngine(create_llm_client(), knowledge, ticket_generator)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/context/summary")
def context_summary() -> dict:
    return knowledge.summary()


@app.get("/api/sample-requests")
def sample_requests() -> dict[str, list[str]]:
    path = BACKEND_ROOT / "data" / "sample_requests.json"
    with path.open(encoding="utf-8") as handle:
        return {"requests": json.load(handle)}


@app.get("/api/llm/status", response_model=LLMStatusResponse)
def llm_status() -> LLMStatusResponse:
    return engine.llm_status()


@app.get("/api/stress-test/scenarios")
def stress_test_scenarios() -> dict[str, list[dict[str, str]]]:
    return {"scenarios": scenario_catalog()}


@app.post("/api/intake/message", response_model=IntakeMessageResponse)
def intake_message(request: MessageRequest) -> IntakeMessageResponse:
    try:
        return engine.process_message(request.session_id, request.message)
    except Exception as exc:
        import logging

        logging.getLogger("uvicorn.error").exception("Unhandled intake error")
        state = engine.get_state(request.session_id)
        return IntakeMessageResponse(
            session_id=request.session_id,
            assistant_message="I couldn’t safely process that response. Your current intake was preserved; please clarify the data source, audience, or success criteria.",
            intake=state.intake,
            missing_fields=state.intake.missing_fields,
            completion_score=round(state.intake.confidence_score * 100),
            ready_for_ticket=False,
            ticket_preview=None,
            risk_flags=list(dict.fromkeys(state.intake.risk_flags + ["The last message could not be validated."])),
            context_used=[],
            mode="error",
            llm_provider="system",
            llm_model=engine.llm_status().model,
            fallback_reason=f"Unhandled intake error: {type(exc).__name__}: {exc}",
        )


@app.post("/api/intake/reset")
def intake_reset(request: ResetRequest) -> dict[str, str]:
    engine.reset(request.session_id)
    return {"session_id": request.session_id, "status": "reset"}


@app.patch("/api/intake/field", response_model=IntakeMessageResponse)
def update_intake_field(request: FieldPatchRequest) -> IntakeMessageResponse:
    try:
        return engine.update_field(request.session_id, request.field, request.value, request.confirmed)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/api/intake/validation/submit", response_model=IntakeMessageResponse)
def submit_for_validation(request: ValidationActionRequest) -> IntakeMessageResponse:
    try:
        return engine.submit_for_validation(request.session_id, request.validator_name, request.note)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.post("/api/intake/validation/approve", response_model=IntakeMessageResponse)
def approve_validation(request: ValidationActionRequest) -> IntakeMessageResponse:
    try:
        return engine.validate(request.session_id, request.validator_name, request.note)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.post("/api/intake/validation/reject", response_model=IntakeMessageResponse)
def reject_validation(request: ValidationActionRequest) -> IntakeMessageResponse:
    try:
        return engine.reject(request.session_id, request.validator_name, request.note)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.post("/api/intake/generate-ticket", response_model=TicketGenerationResponse)
def generate_ticket(request: GenerateTicketRequest) -> TicketGenerationResponse:
    try:
        return engine.generate_ticket(request.session_id)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.post("/api/intake/attachments", response_model=AttachmentListResponse)
async def upload_intake_attachment(
    session_id: str = Form(...),
    file: UploadFile = File(...),
) -> AttachmentListResponse:
    payload = await file.read()
    try:
        return engine.add_user_attachment(
            session_id,
            filename=file.filename or "upload.bin",
            content_type=file.content_type or "application/octet-stream",
            content=payload,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.delete("/api/intake/attachments", response_model=AttachmentListResponse)
def remove_intake_attachment(request: RemoveAttachmentRequest) -> AttachmentListResponse:
    try:
        return engine.remove_user_attachment(request.session_id, request.filename)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/api/stress-test/run", response_model=StressTestResponse)
def stress_test(request: StressTestRequest) -> StressTestResponse:
    try:
        return run_stress_test(engine, request.scenario_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"Unknown scenario: {request.scenario_id}") from exc
