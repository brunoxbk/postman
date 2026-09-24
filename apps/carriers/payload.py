from dataclasses import dataclass, field
from datetime import date, datetime


@dataclass(slots=True)
class EventData:
    occurred_at: datetime | None = None
    status_key: str = ""
    status_label: str = ""
    location: str = ""
    raw: dict = field(default_factory=dict)


@dataclass(slots=True)
class NormalizedPayload:
    tracking_code: str
    status_code: str
    status_label: str
    location: str
    last_event_at: datetime | None
    estimated_delivery: date | None
    is_terminal: bool
    events: list[EventData]
    raw: dict
    terminal_state: str | None = None