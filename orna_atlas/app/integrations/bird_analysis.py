"""BirdNET-Analyzer integration for detecting bird vocalizations in field recordings."""

from __future__ import annotations

import math
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
    try:
        threshold = float(min_confidence)
    except (TypeError, ValueError) as exc:
        raise ValueError("min_confidence must be a finite value between 0 and 1") from exc
    if not math.isfinite(threshold) or not 0 <= threshold <= 1:
        raise ValueError("min_confidence must be a finite value between 0 and 1")

    normalized: list[BirdDetection] = []
    for detection in detections:
        if not isinstance(detection, dict):
            continue
        try:
            raw_confidence = detection.get("confidence")
            raw_start_time = detection.get("start_time")
            raw_end_time = detection.get("end_time")
            confidence = float(0.0 if raw_confidence is None else raw_confidence)
            start_time = float(0.0 if raw_start_time is None else raw_start_time)
            end_time = float(start_time if raw_end_time is None else raw_end_time)
        except (TypeError, ValueError, OverflowError):
            continue
        if (
            not all(math.isfinite(value) for value in (confidence, start_time, end_time))
            or not 0 <= confidence <= 1
            or confidence < threshold
            or start_time < 0
            or end_time < start_time
        ):
            continue
        raw_scientific_name = detection.get("scientific_name")
        scientific_name = (
            str(raw_scientific_name).strip() if raw_scientific_name else None
        )
        common_name = str(
            detection.get("common_name") or scientific_name or "Unknown species"
        ).strip()
        species_code = species_code_from_scientific_name(scientific_name)
        if (
            not common_name
            or len(common_name) > 180
            or (scientific_name is not None and len(scientific_name) > 180)
            or len(species_code) > 120
        ):
            continue
        label = detection.get("label")
        normalized.append(
            BirdDetection(
                species_code=species_code,
                species_common_name=common_name,
                species_scientific_name=scientific_name,
                starts_at_seconds=start_time,
                ends_at_seconds=end_time,
                confidence=round(confidence, 4),
                metadata={
                    "label": str(label)[:500] if label is not None else None,
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
