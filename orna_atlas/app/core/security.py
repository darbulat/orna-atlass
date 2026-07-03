from dataclasses import dataclass


@dataclass(frozen=True)
class CurrentUser:
    id: str
    is_admin: bool = False
