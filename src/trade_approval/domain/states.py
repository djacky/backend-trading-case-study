"""Trade lifecycle states and actions."""

from enum import Enum


class State(str, Enum):
    DRAFT = "Draft"
    PENDING_APPROVAL = "PendingApproval"
    NEEDS_REAPPROVAL = "NeedsReapproval"
    APPROVED = "Approved"
    SENT_TO_COUNTERPARTY = "SentToCounterparty"
    EXECUTED = "Executed"
    CANCELLED = "Cancelled"

    @property
    def is_terminal(self) -> bool:
        return self in {State.EXECUTED, State.CANCELLED}


class Action(str, Enum):
    CREATE = "Create"  # internal — sets initial Draft state
    SUBMIT = "Submit"
    APPROVE = "Approve"
    UPDATE = "Update"
    CANCEL = "Cancel"
    SEND_TO_EXECUTE = "SendToExecute"
    BOOK = "Book"
