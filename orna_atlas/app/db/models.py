"""Import every ORM model so SQLAlchemy can resolve string relationships.

Non-HTTP entry points such as maintenance workers do not import all routers, so
relying on incidental router imports leaves parts of the mapper registry empty.
"""

from orna_atlas.app.modules.admin.models import AuditEvent
from orna_atlas.app.modules.auth.models import RefreshToken
from orna_atlas.app.modules.collections.models import Collection, CollectionLocation, CollectionSession
from orna_atlas.app.modules.locations.models import Location
from orna_atlas.app.modules.media.models import (
    HlsProcessingJob,
    MediaAsset,
    ProcessingJob,
    RecordingSegment,
)
from orna_atlas.app.modules.memberships.models import Membership
from orna_atlas.app.modules.sessions.models import BirdVocalPart, RecordingSession
from orna_atlas.app.modules.users.models import User

__all__ = [
    "AuditEvent",
    "BirdVocalPart",
    "Collection",
    "CollectionLocation",
    "CollectionSession",
    "HlsProcessingJob",
    "Location",
    "MediaAsset",
    "Membership",
    "ProcessingJob",
    "RecordingSegment",
    "RecordingSession",
    "RefreshToken",
    "User",
]
