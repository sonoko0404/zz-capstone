from __future__ import annotations

from abc import ABC, abstractmethod

from .models import (
    JiraAdapterResult,
    JiraTicketBundleAdapterResult,
    JiraTicketBundlePayload,
    TicketPayload,
)


class JiraAdapter(ABC):
    """Boundary between intake/ticket generation and any Jira implementation.

    A future teammate can add RealJiraAdapter in a separate module and inject it
    in app/main.py. The intake engine and frontend must remain unchanged.
    """

    @abstractmethod
    def create_ticket(self, ticket_payload: TicketPayload) -> JiraAdapterResult:
        """Return an adapter result for the supplied normalized ticket payload."""
        raise NotImplementedError

    @abstractmethod
    def create_ticket_bundle(
        self,
        ticket_bundle: JiraTicketBundlePayload,
    ) -> JiraTicketBundleAdapterResult:
        """Create or preview the stable ITO + BIM bundle without UI coupling.

        REAL JIRA HANDOFF: a future RealJiraAdapter implements this method with
        approved project keys, issue types, link types, auth, and attachment APIs.
        No caller outside the adapter should contain Jira-specific API logic.
        """
        raise NotImplementedError
