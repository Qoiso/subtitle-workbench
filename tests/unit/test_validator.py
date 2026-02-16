from app.core.models import MergeInput
from app.core.validator import Validator


def test_reject_single_category() -> None:
    payload = MergeInput(
        visual_paths=["a.mp4"],
        audio_paths=[],
        subtitle_paths=[],
        output_path="out.mkv",
    )
    result = Validator.validate_merge_input(payload)
    assert result.ok is False
    assert result.code == "INSUFFICIENT_MEDIA"


def test_accept_two_categories() -> None:
    payload = MergeInput(
        visual_paths=["a.mp4"],
        audio_paths=["a.mp3"],
        subtitle_paths=[],
        output_path="out.mkv",
    )
    result = Validator.validate_merge_input(payload)
    assert result.ok is True


def test_accept_video_and_image_as_two_categories() -> None:
    payload = MergeInput(
        visual_paths=["a.mp4"],
        image_paths=["b.jpg"],
        audio_paths=[],
        subtitle_paths=[],
        output_path="out.mkv",
    )
    result = Validator.validate_merge_input(payload)
    assert result.ok is True


def test_reject_lossless_when_image_exists() -> None:
    payload = MergeInput(
        visual_paths=[],
        image_paths=["a.png"],
        audio_paths=["a.mp3"],
        subtitle_paths=[],
        output_path="out.mkv",
        output_quality="lossless_copy",
    )
    result = Validator.validate_merge_input(payload)
    assert result.ok is False
    assert result.code == "LOSSLESS_BLOCKED_BY_IMAGE"


def test_reject_lossless_when_hard_subtitle_selected() -> None:
    payload = MergeInput(
        visual_paths=["a.mp4"],
        audio_paths=["a.mp3"],
        subtitle_paths=["a.srt"],
        output_path="out.mkv",
        output_quality="lossless_copy",
        subtitle_mode="hard",
    )
    result = Validator.validate_merge_input(payload)
    assert result.ok is False
    assert result.code == "LOSSLESS_BLOCKED_BY_HARD_SUBTITLE"
