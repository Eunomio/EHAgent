from app.sleep.baseline import compare_to_personal_baseline


def night(
    duration: int = 450,
    heart_rate: float | None = 62,
    respiratory_rate: float | None = 16,
    quality: str = "usable",
) -> dict[str, object]:
    return {
        "duration_minutes": duration,
        "heart_rate": heart_rate,
        "respiratory_rate": respiratory_rate,
        "quality": quality,
        "data_status": "final",
    }


def test_baseline_requires_seven_prior_valid_nights() -> None:
    result = compare_to_personal_baseline([night(), *[night() for _ in range(6)]])
    assert result["state"] == "baseline_building"
    assert result["baseline_nights"] == 6


def test_baseline_marks_stable_values_as_close() -> None:
    result = compare_to_personal_baseline([night(440, 63, 16.5), *[night() for _ in range(7)]])
    assert result["state"] == "close_to_baseline"
    assert result["changed_metrics"] == []


def test_baseline_reports_large_personal_deviations_without_diagnosis() -> None:
    result = compare_to_personal_baseline([night(330, 72, 20), *[night() for _ in range(7)]])
    assert result["state"] == "changed"
    assert set(result["changed_metrics"]) == {
        "duration_minutes", "heart_rate", "respiratory_rate",
    }
    assert "诊断" not in result["message"]


def test_insufficient_latest_night_is_not_compared() -> None:
    result = compare_to_personal_baseline([
        night(quality="insufficient"),
        *[night() for _ in range(7)],
    ])
    assert result["state"] == "insufficient"
