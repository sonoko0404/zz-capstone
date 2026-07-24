"""Real Jira Cloud adapter — creates linked ITO + BIM tickets via REST API v3.

Repurposed from the standalone jira_service create/link flow. All Jira auth,
ADF conversion, project/issue-type mapping, and HTTP calls stay inside this
module so IntakeEngine and the frontend remain unchanged.

Enable with ENABLE_REAL_JIRA=true and Jira credentials in backend/.env.
"""

from __future__ import annotations

import base64
import logging
import os
from typing import Any

import httpx

from .jira_adapter import JiraAdapter
from .models import (
    AttachmentDraft,
    JiraAdapterResult,
    JiraTicketBundleAdapterResult,
    JiraTicketBundlePayload,
    JiraTicketDraftPayload,
    TicketPayload,
    TicketRelationshipDraft,
)

logger = logging.getLogger(__name__)

_PLACEHOLDER_ISSUE_TYPE = "to be confirmed by jira integration"


def _truthy(value: str | None) -> bool:
    return (value or "").strip().lower() in {"1", "true", "yes", "on"}


# ─── Atlassian Document Format (ADF) helpers ─────────────────────────────────


def adf_doc(*blocks: dict[str, Any]) -> dict[str, Any]:
    return {"type": "doc", "version": 1, "content": list(blocks) or [adf_paragraph("—")]}


def adf_heading(level: int, text: str) -> dict[str, Any]:
    return {
        "type": "heading",
        "attrs": {"level": max(1, min(level, 6))},
        "content": [{"type": "text", "text": text or "—"}],
    }


def adf_paragraph(text: str) -> dict[str, Any]:
    return {
        "type": "paragraph",
        "content": [{"type": "text", "text": text or "—"}],
    }


def adf_rule() -> dict[str, Any]:
    return {"type": "rule"}


def plain_text_to_adf(text: str) -> dict[str, Any]:
    """Convert intake blueprint plain text into ADF paragraphs/headings."""
    blocks: list[dict[str, Any]] = []
    for raw_line in (text or "").splitlines():
        stripped = raw_line.strip()
        if not stripped:
            if blocks and blocks[-1].get("type") != "rule":
                blocks.append(adf_rule())
            continue
        # Section titles in the generator are ALL CAPS or end with (DRAFT).
        if stripped.isupper() or stripped.endswith("(DRAFT)") or (
            stripped.endswith(":") and len(stripped) < 80
        ):
            blocks.append(adf_heading(3, stripped.rstrip(":")))
        else:
            blocks.append(adf_paragraph(stripped))
    return adf_doc(*blocks)


# ─── Adapter ─────────────────────────────────────────────────────────────────


class RealJiraAdapter(JiraAdapter):
    """Creates a real ITO + BIM ticket pair and links them in Jira Cloud."""

    def __init__(
        self,
        *,
        base_url: str,
        email: str,
        api_token: str,
        ito_project_key: str = "ITO",
        bim_project_key: str = "BIM",
        ito_issue_type: str = "Task",
        bim_issue_type: str = "Story",
        link_type: str = "Relates",
        timeout: float = 30.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.email = email
        self.api_token = api_token
        self.ito_project_key = ito_project_key
        self.bim_project_key = bim_project_key
        self.ito_issue_type = ito_issue_type
        self.bim_issue_type = bim_issue_type
        self.link_type = link_type
        self.timeout = timeout

    @classmethod
    def from_env(cls) -> RealJiraAdapter:
        base_url = os.getenv("JIRA_BASE_URL", "").strip()
        email = os.getenv("JIRA_EMAIL", "").strip()
        api_token = os.getenv("JIRA_API_TOKEN", "").strip()
        missing = [
            name
            for name, value in (
                ("JIRA_BASE_URL", base_url),
                ("JIRA_EMAIL", email),
                ("JIRA_API_TOKEN", api_token),
            )
            if not value
        ]
        if missing:
            raise ValueError(
                "ENABLE_REAL_JIRA is true but missing required env vars: "
                + ", ".join(missing)
            )
        return cls(
            base_url=base_url,
            email=email,
            api_token=api_token,
            ito_project_key=os.getenv("ITO_PROJECT_KEY", "ITO").strip() or "ITO",
            bim_project_key=os.getenv("BIM_PROJECT_KEY", "BIM").strip() or "BIM",
            ito_issue_type=os.getenv("ITO_ISSUE_TYPE", "Task").strip() or "Task",
            bim_issue_type=os.getenv("BIM_ISSUE_TYPE", "Story").strip() or "Story",
            link_type=os.getenv("JIRA_LINK_TYPE", "Relates").strip() or "Relates",
        )

    def _auth_headers(self) -> dict[str, str]:
        token = base64.b64encode(f"{self.email}:{self.api_token}".encode()).decode()
        # Do not set Content-Type here — json= sets application/json, and
        # multipart attachment uploads must set their own boundary.
        return {
            "Authorization": f"Basic {token}",
            "Accept": "application/json",
        }

    def _client(self) -> httpx.Client:
        return httpx.Client(headers=self._auth_headers(), timeout=self.timeout)

    def _resolve_issue_type(self, draft: JiraTicketDraftPayload) -> str:
        configured = (
            self.ito_issue_type if draft.project_category == "ITO" else self.bim_issue_type
        )
        candidate = (draft.issue_type or "").strip()
        if not candidate or candidate.casefold() == _PLACEHOLDER_ISSUE_TYPE:
            return configured
        return candidate

    def _resolve_project_key(self, draft: JiraTicketDraftPayload) -> str:
        return self.ito_project_key if draft.project_category == "ITO" else self.bim_project_key

    def _create_issue(
        self,
        client: httpx.Client,
        draft: JiraTicketDraftPayload,
        *,
        summary_override: str | None = None,
    ) -> dict[str, Any]:
        project_key = self._resolve_project_key(draft)
        issue_type = self._resolve_issue_type(draft)
        summary = (summary_override or draft.summary or "BI intake request").strip()[:255]
        payload: dict[str, Any] = {
            "fields": {
                "project": {"key": project_key},
                "summary": summary,
                "description": plain_text_to_adf(draft.description),
                "issuetype": {"name": issue_type},
                "priority": {"name": (draft.priority or "Medium").strip() or "Medium"},
            }
        }
        if draft.labels:
            payload["fields"]["labels"] = draft.labels

        response = client.post(f"{self.base_url}/rest/api/3/issue", json=payload)
        if response.status_code not in {200, 201}:
            raise RuntimeError(
                f"Jira {draft.project_category} ticket creation failed "
                f"({response.status_code}): {response.text}"
            )
        ticket = response.json()
        logger.info("Created Jira %s ticket %s", draft.project_category, ticket.get("key"))
        return ticket

    def _link_tickets(self, client: httpx.Client, ito_key: str, bim_key: str) -> None:
        payload = {
            "type": {"name": self.link_type},
            "inwardIssue": {"key": ito_key},
            "outwardIssue": {"key": bim_key},
            "comment": {
                "body": adf_doc(
                    adf_paragraph(
                        f"{bim_key} is the engineering ticket for this request. "
                        "Created by the AI BI Intake Assistant."
                    )
                )
            },
        }
        response = client.post(f"{self.base_url}/rest/api/3/issueLink", json=payload)
        if response.status_code != 201:
            raise RuntimeError(
                f"Jira ticket linking failed ({response.status_code}): {response.text}"
            )
        logger.info("Linked Jira tickets %s ↔ %s (%s)", ito_key, bim_key, self.link_type)

    def _upload_attachments(
        self,
        client: httpx.Client,
        issue_key: str,
        attachments: list[AttachmentDraft],
    ) -> list[str]:
        """Upload included attachments. Returns human-readable error strings."""
        errors: list[str] = []
        for attachment in attachments:
            if not attachment.included or not attachment.content:
                continue
            filename = attachment.filename or "chat.txt"
            if attachment.content_encoding == "base64":
                try:
                    raw = base64.b64decode(attachment.content, validate=True)
                except Exception as exc:
                    errors.append(f"{filename} → {issue_key} failed: invalid base64 ({exc})")
                    continue
            else:
                raw = attachment.content.encode("utf-8")
            files = {
                "file": (
                    filename,
                    raw,
                    attachment.content_type or "application/octet-stream",
                )
            }
            # Override any inherited Content-Type; Jira requires multipart + no-check.
            headers = {
                "X-Atlassian-Token": "no-check",
                "Authorization": self._auth_headers()["Authorization"],
                "Accept": "application/json",
            }
            response = client.post(
                f"{self.base_url}/rest/api/3/issue/{issue_key}/attachments",
                headers=headers,
                files=files,
            )
            if response.status_code not in {200, 201}:
                detail = response.text.strip() or response.reason_phrase
                message = f"{filename} → {issue_key} failed ({response.status_code}): {detail}"
                logger.warning("Attachment upload %s", message)
                errors.append(message)
                continue
            attachment.uploaded = True
            logger.info("Uploaded attachment %s to %s", filename, issue_key)
        return errors

    def create_ticket(self, ticket_payload: TicketPayload) -> JiraAdapterResult:
        """Legacy single-ticket path — creates one BIM (or category) issue."""
        category = (ticket_payload.project_category or "BIM").upper()
        if category not in {"ITO", "BIM"}:
            category = "BIM"
        draft = JiraTicketDraftPayload(
            project_category=category,  # type: ignore[arg-type]
            issue_type=self.bim_issue_type if category == "BIM" else self.ito_issue_type,
            summary=ticket_payload.title or ticket_payload.summary,
            description="\n".join(
                [
                    ticket_payload.summary,
                    "",
                    f"Business purpose: {ticket_payload.business_purpose}",
                    f"Requester: {ticket_payload.requester}",
                    f"Owner: {ticket_payload.owner}",
                    f"Audience: {ticket_payload.audience}",
                    f"Data sources: {', '.join(ticket_payload.data_sources)}",
                    f"Metrics: {', '.join(ticket_payload.metrics_or_kpis)}",
                    f"Display format: {ticket_payload.display_format}",
                    f"Refresh: {ticket_payload.refresh_frequency}",
                    f"Scope: {ticket_payload.scope}",
                ]
            ),
            priority=ticket_payload.suggested_priority or "Medium",
        )
        with self._client() as client:
            created = self._create_issue(client, draft)
        key = created["key"]
        return JiraAdapterResult(
            ticket_key=key,
            status="Created in Jira",
            created=True,
            message=f"Created Jira issue {key}. Browse: {self.base_url}/browse/{key}",
            payload=ticket_payload,
        )

    def create_ticket_bundle(
        self,
        ticket_bundle: JiraTicketBundlePayload,
    ) -> JiraTicketBundleAdapterResult:
        """Create ITO, then BIM (summary prefixed with ITO key), then link them."""
        with self._client() as client:
            ito = self._create_issue(client, ticket_bundle.ito_ticket)
            ito_key = ito["key"]
            bim = self._create_issue(
                client,
                ticket_bundle.bim_ticket,
                summary_override=f"[{ito_key}] {ticket_bundle.bim_ticket.summary}",
            )
            bim_key = bim["key"]
            self._link_tickets(client, ito_key, bim_key)
            upload_errors = self._upload_attachments(
                client, ito_key, ticket_bundle.ito_ticket.attachments
            )
            upload_errors.extend(
                self._upload_attachments(client, bim_key, ticket_bundle.bim_ticket.attachments)
            )

        updated = ticket_bundle.model_copy(deep=True)
        updated.ito_ticket.issue_type = self._resolve_issue_type(ticket_bundle.ito_ticket)
        updated.bim_ticket.issue_type = self._resolve_issue_type(ticket_bundle.bim_ticket)
        updated.proposed_relationship = TicketRelationshipDraft(
            source_ticket_category="ITO",
            delivery_ticket_category="BIM",
            direction=f"BIM → ITO ({self.link_type})",
            relationship_type=self.link_type,
            created=True,
        )

        uploaded = sum(
            1
            for draft in (updated.ito_ticket, updated.bim_ticket)
            for item in draft.attachments
            if item.uploaded
        )
        intended = sum(
            1
            for draft in (updated.ito_ticket, updated.bim_ticket)
            for item in draft.attachments
            if item.included and item.content
        )
        message = (
            f"Created linked Jira tickets {ito_key} and {bim_key}. "
            f"ITO: {self.base_url}/browse/{ito_key} · "
            f"BIM: {self.base_url}/browse/{bim_key}"
        )
        if intended:
            message += f" Attachments uploaded: {uploaded}/{intended}."
        if upload_errors:
            message += " Attachment errors: " + "; ".join(upload_errors)

        return JiraTicketBundleAdapterResult(
            ito_ticket_key=ito_key,
            bim_ticket_key=bim_key,
            status="Created in Jira",
            created=True,
            message=message,
            payload=updated,
        )


def build_jira_adapter() -> JiraAdapter:
    """Return RealJiraAdapter when enabled and configured; otherwise MockJiraAdapter."""
    from .mock_jira import MockJiraAdapter

    if not _truthy(os.getenv("ENABLE_REAL_JIRA")):
        return MockJiraAdapter()
    try:
        return RealJiraAdapter.from_env()
    except ValueError as exc:
        logger.error("Falling back to MockJiraAdapter: %s", exc)
        return MockJiraAdapter()
