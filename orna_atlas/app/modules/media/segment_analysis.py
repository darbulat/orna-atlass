from dataclasses import replace

from orna_atlas.app.integrations.bird_analysis import BirdDetection


def offset_segment_detections(
    detections: list[BirdDetection], *, offset_ms: int, sequence_number: int
) -> list[BirdDetection]:
    """Translate segment-local BirdNET intervals onto the session timeline."""
    offset_seconds = offset_ms / 1000
    return [
        replace(
            detection,
            starts_at_seconds=detection.starts_at_seconds + offset_seconds,
            ends_at_seconds=detection.ends_at_seconds + offset_seconds,
            metadata={
                **detection.metadata,
                "segment_sequence_number": sequence_number,
                "segment_local_starts_at_seconds": detection.starts_at_seconds,
                "segment_local_ends_at_seconds": detection.ends_at_seconds,
            },
        )
        for detection in detections
    ]
