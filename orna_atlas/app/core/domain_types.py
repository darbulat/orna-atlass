from enum import StrEnum


class CoordinateVisibility(StrEnum):
    EXACT_PUBLIC = "exact_public"
    APPROXIMATE_PUBLIC = "approximate_public"
    HIDDEN_PUBLIC = "hidden_public"


class SensitivityLevel(StrEnum):
    NONE = "none"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    PROTECTED = "protected"


class SessionAccess(StrEnum):
    PUBLIC = "public"
    MEMBERS_ONLY = "members_only"
    PRIVATE = "private"


class PublicationStatus(StrEnum):
    DRAFT = "draft"
    PUBLISHED = "published"
    ARCHIVED = "archived"


class ProcessingStatus(StrEnum):
    PENDING = "pending"
    UPLOADED = "uploaded"
    QUEUED = "queued"
    PROCESSING = "processing"
    READY = "ready"
    FAILED = "failed"


class MediaKind(StrEnum):
    AUDIO = "audio"
    SOURCE_AUDIO = "source_audio"
    MASTER_AUDIO = "master_audio"
    STREAMING_RENDITION = "streaming_rendition"
    AUDIO_STREAM = "audio_stream"


class JobType(StrEnum):
    AUDIO_PIPELINE = "audio_pipeline"


class JobStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class UserRole(StrEnum):
    MEMBER = "member"
    EDITOR = "editor"
    ADMIN = "admin"


class MembershipStatus(StrEnum):
    INACTIVE = "inactive"
    ACTIVE = "active"
    CANCELLED = "cancelled"
    EXPIRED = "expired"
