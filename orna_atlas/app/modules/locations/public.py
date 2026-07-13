from sqlalchemy import ColumnElement

from orna_atlas.app.modules.locations.models import Location

HIDDEN_PUBLIC = "hidden_public"


def publicly_discoverable_clause() -> ColumnElement[bool]:
    """Canonical database predicate for locations exposed by public APIs."""
    return Location.coordinate_visibility != HIDDEN_PUBLIC


def is_publicly_discoverable(location: Location) -> bool:
    """In-memory equivalent used when projecting already-loaded relationships."""
    return location.coordinate_visibility != HIDDEN_PUBLIC
