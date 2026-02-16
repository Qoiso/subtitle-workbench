from __future__ import annotations

from app.core.models import MergeInput, ValidationResult


class Validator:
    @staticmethod
    def validate_merge_input(data: MergeInput) -> ValidationResult:
        has_video = bool(data.visual_paths)
        has_image = bool(data.image_paths)
        has_audio = bool(data.audio_paths)
        has_sub = bool(data.subtitle_paths)

        categories = sum((has_video, has_image, has_audio, has_sub))
        if categories < 2:
            return ValidationResult(
                ok=False,
                code="INSUFFICIENT_MEDIA",
                message="至少需要两类不同素材（视频、图片、音频、字幕）才能执行合并。",
            )

        if not data.output_path.strip():
            return ValidationResult(
                ok=False,
                code="OUTPUT_REQUIRED",
                message="请设置输出文件路径。",
            )

        container = data.output_container.lower().strip(".")
        if container not in {"mkv", "mp4"}:
            return ValidationResult(
                ok=False,
                code="UNSUPPORTED_CONTAINER",
                message="仅支持 mkv/mp4 输出格式。",
            )

        if data.output_quality == "lossless_copy":
            if has_image:
                return ValidationResult(
                    ok=False,
                    code="LOSSLESS_BLOCKED_BY_IMAGE",
                    message="选择了图片素材时不能使用无损合并，请改用可编码输出质量。",
                )
            if data.subtitle_mode == "hard":
                return ValidationResult(
                    ok=False,
                    code="LOSSLESS_BLOCKED_BY_HARD_SUBTITLE",
                    message="硬字幕需要重新编码，不能使用无损合并。",
                )
            if not has_video:
                return ValidationResult(
                    ok=False,
                    code="LOSSLESS_REQUIRES_VIDEO",
                    message="无损合并需要至少一个视频素材作为可拷贝视频流。",
                )

        return ValidationResult(ok=True, code="OK", message="参数合法。")
