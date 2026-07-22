from __future__ import annotations

from itertools import count
from threading import Lock

from .jira_adapter import JiraAdapter
from .models import (
    JiraAdapterResult,
    JiraTicketBundleAdapterResult,
    JiraTicketBundlePayload,
    TicketPayload,
)


class MockJiraAdapter(JiraAdapter):
    """Creates local-only draft identifiers and performs no external writes."""

    def __init__(self, starting_number: int = 1001) -> None:
        self._numbers = count(starting_number)
        self._lock = Lock()

    def create_ticket(self, ticket_payload: TicketPayload) -> JiraAdapterResult:
        with self._lock:
            number = next(self._numbers)

        project = (ticket_payload.project_category or "BIM").upper()
        return JiraAdapterResult(
            ticket_key=f"DRAFT-{project}-{number}",
            status="Draft Only",
            created=False,
            message="No real Jira ticket was created. This is a prototype draft.",
            payload=ticket_payload,
        )

    def create_ticket_bundle(
        self,
        ticket_bundle: JiraTicketBundlePayload,
    ) -> JiraTicketBundleAdapterResult:
        with self._lock:
            ito_number = next(self._numbers)
            bim_number = next(self._numbers)
        return JiraTicketBundleAdapterResult(
            ito_ticket_key=f"DRAFT-ITO-{ito_number}",
            bim_ticket_key=f"DRAFT-BIM-{bim_number}",
            status="Draft Only",
            created=False,
            message="No real Jira ticket was created. This is a prototype draft bundle.",
            payload=ticket_bundle,
        )


# REAL JIRA HANDOFF POINT:
# Add a RealJiraAdapter(JiraAdapter) in a new real_jira.py module later. It should
# accept JiraTicketBundlePayload and return JiraTicketBundleAdapterResult from
# create_ticket_bundle. Do not change the intake engine, ticket generator, API
# response, or frontend when swapping it in.
