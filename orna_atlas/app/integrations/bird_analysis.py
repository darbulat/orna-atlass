"""BirdNET-Analyzer integration for detecting bird vocalizations in field recordings."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

ANALYSIS_PROVIDER = "birdnet"
BIRDNET_ANALYZER_VERSION = "2.4"
ANALYSIS_MODEL_VERSION = f"birdnet-analyzer-v{BIRDNET_ANALYZER_VERSION}"
DEFAULT_MIN_CONFIDENCE = 0.25


@dataclass(frozen=True)
class BirdDetection:
    """Normalized bird vocalization interval produced by BirdNET analysis."""

    species_code: str
    species_common_name: str
    species_scientific_name: str | None
    starts_at_seconds: float
    ends_at_seconds: float
    confidence: float
    call_type: str = "unknown"
    metadata: dict = field(default_factory=dict)


def species_code_from_scientific_name(scientific_name: str | None) -> str:
    """Convert a scientific name into a stable snake_case species code."""
    if not scientific_name:
        return "unknown_species"
    normalized = re.sub(r"[^a-zA-Z0-9]+", "_", scientific_name.strip().lower())
    return normalized.strip("_") or "unknown_species"


def normalize_birdnet_detections(
    detections: list[dict],
    *,
    min_confidence: float = DEFAULT_MIN_CONFIDENCE,
) -> list[BirdDetection]:
    """Map raw BirdNET detections into normalized atlas bird part payloads."""
    normalized: list[BirdDetection] = []
    for detection in detections:
        confidence = float(detection.get("confidence") or 0.0)
        if confidence < min_confidence:
            continue
        scientific_name = detection.get("scientific_name")
        common_name = detection.get("common_name") or scientific_name or "Unknown species"
        start_time = float(detection.get("start_time") or 0.0)
        end_time = float(detection.get("end_time") or start_time)
        if end_time < start_time:
            end_time = start_time
        normalized.append(
            BirdDetection(
                species_code=species_code_from_scientific_name(scientific_name),
                species_common_name=str(common_name),
                species_scientific_name=str(scientific_name) if scientific_name else None,
                starts_at_seconds=start_time,
                ends_at_seconds=end_time,
                confidence=round(confidence, 4),
                metadata={
                    "label": detection.get("label"),
                    "source": ANALYSIS_PROVIDER,
                },
            )
        )
    normalized.sort(key=lambda item: (item.starts_at_seconds, item.species_code))
    return normalized


def analyze_audio_file(
    audio_path: Path,
    *,
    lat: float | None = None,
    lon: float | None = None,
    recorded_at: datetime | None = None,
    min_confidence: float = DEFAULT_MIN_CONFIDENCE,
) -> list[BirdDetection]:
    """Run BirdNET analysis on an audio file and return normalized detections."""
    from birdnetlib import LargeRecording
    from birdnetlib.analyzer import LargeRecordingAnalyzer

    analyzer = LargeRecordingAnalyzer(version=BIRDNET_ANALYZER_VERSION)
    recording_kwargs: dict = {
        "min_conf": min_confidence,
    }
    if lat is not None and lon is not None:
        recording_kwargs["lat"] = lat
        recording_kwargs["lon"] = lon
    if recorded_at is not None:
        recording_kwargs["date"] = recorded_at

    recording = LargeRecording(analyzer, str(audio_path), **recording_kwargs)
    recording.analyze()
    return normalize_birdnet_detections(recording.detections, min_confidence=min_confidence)
