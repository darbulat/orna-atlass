from orna_atlas.app.integrations.bird_analysis import (
    ANALYSIS_MODEL_VERSION,
    BIRDNET_ANALYZER_VERSION,
    normalize_birdnet_detections,
    species_code_from_scientific_name,
)


def test_species_code_from_scientific_name() -> None:
    assert species_code_from_scientific_name("Turdus merula") == "turdus_merula"
    assert species_code_from_scientific_name(None) == "unknown_species"


def test_analysis_model_version_matches_pinned_analyzer() -> None:
    assert ANALYSIS_MODEL_VERSION == f"birdnet-analyzer-v{BIRDNET_ANALYZER_VERSION}"


def test_normalize_birdnet_detections_filters_low_confidence() -> None:
    detections = normalize_birdnet_detections(
        [
            {
                "common_name": "Common blackbird",
                "scientific_name": "Turdus merula",
                "start_time": 10.0,
                "end_time": 13.0,
                "confidence": 0.91,
                "label": "Turdus merula_Common blackbird",
            },
            {
                "common_name": "Great tit",
                "scientific_name": "Parus major",
                "start_time": 20.0,
                "end_time": 23.0,
                "confidence": 0.1,
                "label": "Parus major_Great tit",
            },
        ],
        min_confidence=0.25,
    )

    assert len(detections) == 1
    assert detections[0].species_code == "turdus_merula"
    assert detections[0].species_common_name == "Common blackbird"
    assert detections[0].starts_at_seconds == 10.0
    assert detections[0].ends_at_seconds == 13.0
