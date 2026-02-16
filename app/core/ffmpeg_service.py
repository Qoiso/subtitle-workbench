from __future__ import annotations

import json
import os
from dataclasses import replace
from pathlib import Path

from app.core.models import MediaMeta, MergeInput, ValidationResult
from app.infra.process_runner import ProcessRunner


IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".bmp", ".webp"}
SUB_EXTS = {".srt", ".ass", ".ssa", ".vtt", ".sub"}


class FFmpegService:
    def __init__(self, ffmpeg_path: str, ffprobe_path: str, runner: ProcessRunner | None = None) -> None:
        self.ffmpeg_path = ffmpeg_path
        self.ffprobe_path = ffprobe_path
        self.runner = runner or ProcessRunner()
        self._active_proc: object | None = None
        self._paused = False

    async def probe(self, path: str) -> MediaMeta:
        cmd = [
            self.ffprobe_path,
            "-v",
            "quiet",
            "-print_format",
            "json",
            "-show_streams",
            "-show_format",
            path,
        ]
        code, out, _ = await self.runner.run(cmd)
        if code != 0 or not out.strip():
            ext = Path(path).suffix.lower()
            return MediaMeta(
                path=path,
                has_video=ext in IMAGE_EXTS,
                has_audio=False,
                has_subtitle=ext in SUB_EXTS,
            )

        parsed = json.loads(out)
        streams = parsed.get("streams", [])
        fmt = parsed.get("format", {})
        has_video = any(s.get("codec_type") == "video" for s in streams)
        has_audio = any(s.get("codec_type") == "audio" for s in streams)
        has_subtitle = any(s.get("codec_type") == "subtitle" for s in streams)
        video_stream = next((s for s in streams if s.get("codec_type") == "video"), {})
        audio_stream = next((s for s in streams if s.get("codec_type") == "audio"), {})
        duration = None
        try:
            duration = float(fmt.get("duration")) if fmt.get("duration") else None
        except ValueError:
            duration = None
        return MediaMeta(
            path=path,
            has_video=has_video,
            has_audio=has_audio,
            has_subtitle=has_subtitle,
            duration=duration,
            format_name=fmt.get("format_name"),
            video_codec=video_stream.get("codec_name"),
            audio_codec=audio_stream.get("codec_name"),
        )

    def _is_image(self, p: str) -> bool:
        return Path(p).suffix.lower() in IMAGE_EXTS

    def _needs_mov_text(self, out_path: str, subtitle_paths: list[str]) -> bool:
        ext = Path(out_path).suffix.lower()
        has_srt = any(Path(p).suffix.lower() == ".srt" for p in subtitle_paths)
        return ext == ".mp4" and has_srt

    @staticmethod
    def _unique_output_path(raw_path: str) -> str:
        path = Path(raw_path)
        if not path.exists():
            return str(path)
        stem = path.stem
        suffix = path.suffix
        parent = path.parent
        idx = 1
        while True:
            candidate = parent / f"{stem} ({idx}){suffix}"
            if not candidate.exists():
                return str(candidate)
            idx += 1

    @staticmethod
    def _pick_audio_codec(out_path: str) -> list[str]:
        _ = out_path
        return ["-c:a", "aac", "-b:a", "256k"]

    @staticmethod
    def _pick_video_codec_args(output_quality: str) -> list[str]:
        if output_quality == "lossless_copy":
            return ["-c:v", "copy"]
        if output_quality == "nvidia_h265":
            return [
                "-c:v",
                "hevc_nvenc",
                "-preset",
                "p5",
                "-rc",
                "vbr",
                "-cq",
                "23",
                "-b:v",
                "0",
                "-pix_fmt",
                "yuv420p",
            ]
        return ["-c:v", "libx264", "-crf", "18", "-preset", "medium", "-pix_fmt", "yuv420p"]

    @staticmethod
    def _escape_subtitle_filter_path(path: str) -> str:
        escaped = path.replace("\\", "/")
        escaped = escaped.replace(":", "\\:")
        escaped = escaped.replace("'", r"\'")
        return escaped

    @staticmethod
    def _max_duration(paths: list[str], metas: dict[str, MediaMeta]) -> float | None:
        values = [metas[p].duration for p in paths if p in metas and metas[p].duration]
        if not values:
            return None
        return max(values)

    def build_merge_command(self, data: MergeInput, metas: dict[str, MediaMeta]) -> list[str]:
        cmd = [self.ffmpeg_path, "-hide_banner", "-n"]
        video = data.visual_paths[0] if data.visual_paths else None
        image = data.image_paths[0] if data.image_paths else None
        audio = data.audio_paths[0] if data.audio_paths else None
        subtitle = data.subtitle_paths[0] if data.subtitle_paths else None
        video_meta = metas.get(video) if video else None

        has_video_visual = bool(video and video_meta and video_meta.has_video and not self._is_image(video))
        use_image_visual = bool(image and not has_video_visual)
        has_any_visual = has_video_visual or use_image_visual

        aux_media = video if (video and not has_video_visual and video_meta) else None
        use_aux_audio = bool(aux_media and not audio and video_meta and video_meta.has_audio)
        use_aux_subtitle = bool(
            aux_media and not subtitle and data.subtitle_mode == "soft" and video_meta and video_meta.has_subtitle
        )

        hard_subtitle = bool(subtitle and data.subtitle_mode == "hard")
        soft_subtitle = bool((subtitle and data.subtitle_mode == "soft") or use_aux_subtitle)

        allow_lossless = (
            data.output_quality == "lossless_copy"
            and has_video_visual
            and not use_image_visual
            and not hard_subtitle
        )
        effective_quality = data.output_quality if (data.output_quality != "lossless_copy" or allow_lossless) else "cpu_h264"

        idx_visual: int | None = None
        idx_audio: int | None = None
        idx_sub: int | None = None
        idx_aux: int | None = None
        using_color_visual = False

        audio_source_exists = bool(audio or use_aux_audio)
        subtitle_source_exists = bool((subtitle and data.subtitle_mode == "soft") or use_aux_subtitle)

        if not has_any_visual and audio_source_exists and subtitle_source_exists:
            color = "color=size=1280x720:rate=30:color=0x111111"
            cmd.extend(["-f", "lavfi", "-i", color])
            idx_visual = 0
            using_color_visual = True
            input_idx = 1

            if audio:
                cmd.extend(["-i", audio])
                idx_audio = input_idx
                input_idx += 1
            elif use_aux_audio and aux_media:
                cmd.extend(["-i", aux_media])
                idx_aux = input_idx
                idx_audio = idx_aux
                input_idx += 1

            if subtitle and data.subtitle_mode == "soft":
                cmd.extend(["-i", subtitle])
                idx_sub = input_idx
            elif use_aux_subtitle and aux_media:
                if idx_aux is None:
                    cmd.extend(["-i", aux_media])
                    idx_aux = input_idx
                    input_idx += 1
                idx_sub = idx_aux
        else:
            input_idx = 0
            if has_video_visual and video:
                cmd.extend(["-i", video])
                idx_visual = input_idx
                input_idx += 1
            elif use_image_visual and image:
                if audio or use_aux_audio:
                    cmd.extend(["-loop", "1"])
                cmd.extend(["-i", image])
                idx_visual = input_idx
                input_idx += 1

            if audio:
                cmd.extend(["-i", audio])
                idx_audio = input_idx
                input_idx += 1

            if soft_subtitle and subtitle:
                cmd.extend(["-i", subtitle])
                idx_sub = input_idx
                input_idx += 1

            if aux_media and (use_aux_audio or use_aux_subtitle):
                cmd.extend(["-i", aux_media])
                idx_aux = input_idx
                input_idx += 1
                if use_aux_audio and idx_audio is None:
                    idx_audio = idx_aux
                if use_aux_subtitle and idx_sub is None:
                    idx_sub = idx_aux

        if hard_subtitle and subtitle:
            escaped_sub = self._escape_subtitle_filter_path(subtitle)
            cmd.extend(["-vf", f"subtitles='{escaped_sub}'"])

        if allow_lossless:
            cmd.extend(["-c:v", "copy"])
        elif idx_visual is not None:
            cmd.extend(self._pick_video_codec_args(effective_quality))

        if use_image_visual and not audio and not use_aux_audio:
            cmd.extend(["-t", "5"])

        has_audio_output = False
        if idx_visual is not None:
            cmd.extend(["-map", f"{idx_visual}:v:0"])

        if idx_audio is not None:
            cmd.extend(["-map", f"{idx_audio}:a:0"])
            has_audio_output = True
        elif has_video_visual and idx_visual is not None and bool(video_meta and video_meta.has_audio):
            cmd.extend(["-map", f"{idx_visual}:a:0"])
            has_audio_output = True

        if has_audio_output:
            if allow_lossless:
                cmd.extend(["-c:a", "copy"])
            else:
                cmd.extend(self._pick_audio_codec(data.output_path))

        if idx_sub is not None and soft_subtitle:
            cmd.extend(["-map", f"{idx_sub}:s:0"])
            if self._needs_mov_text(data.output_path, data.subtitle_paths):
                cmd.extend(["-c:s", "mov_text"])
            else:
                cmd.extend(["-c:s", "copy"])
            cmd.extend(["-disposition:s:0", "default"])

        if data.sync_mode == "shortest":
            cmd.append("-shortest")
        elif data.sync_mode == "longest":
            relevant = data.visual_paths + data.image_paths + data.audio_paths + data.subtitle_paths
            max_dur = self._max_duration(relevant, metas)
            if max_dur and (use_image_visual or using_color_visual):
                cmd.extend(["-t", f"{max_dur:.3f}"])

        cmd.append(data.output_path)
        return cmd

    async def merge(
        self,
        data: MergeInput,
        metas: dict[str, MediaMeta],
        progress_cb=None,
    ) -> tuple[ValidationResult, str]:
        target_path = self._unique_output_path(data.output_path)
        effective_data = replace(data, output_path=target_path)
        out_parent = Path(target_path).parent
        os.makedirs(out_parent, exist_ok=True)
        cmd = self.build_merge_command(effective_data, metas)
        def _on_start(proc) -> None:
            self._active_proc = proc
            self._paused = False

        try:
            code, _, err = await self.runner.run(
                cmd,
                progress_parser=self._parse_progress,
                progress_cb=progress_cb,
                on_start=_on_start,
            )
        finally:
            self._active_proc = None
            self._paused = False
        if code == 0:
            out_meta = await self.probe(target_path)
            expect_video = bool(data.visual_paths or data.image_paths or (data.audio_paths and data.subtitle_paths))
            expect_soft_sub = bool(data.subtitle_paths and data.subtitle_mode == "soft")
            missing: list[str] = []
            if expect_video and not out_meta.has_video:
                missing.append("video")
            if expect_soft_sub and not out_meta.has_subtitle:
                missing.append("subtitle")
            if missing:
                return (
                    ValidationResult(
                        ok=False,
                        code="OUTPUT_STREAM_MISSING",
                        message=f"Output missing expected stream(s): {', '.join(missing)}",
                    ),
                    target_path,
                )
            return ValidationResult(ok=True, code="OK", message="Merge completed"), target_path
        return ValidationResult(ok=False, code="FFMPEG_FAILED", message=err.strip()[-800:]), target_path

    async def toggle_pause(self) -> bool | None:
        proc = self._active_proc
        if not proc or getattr(proc, "returncode", 1) is not None:
            return None
        stdin = getattr(proc, "stdin", None)
        if stdin is None:
            return None
        stdin.write(b"p")
        await stdin.drain()
        self._paused = not self._paused
        return self._paused

    @staticmethod
    def _parse_progress(line: str) -> dict:
        line = line.strip()
        if "time=" not in line:
            return {}
        payload: dict[str, str | float] = {}
        for part in line.split():
            if "=" in part:
                k, v = part.split("=", 1)
                payload[k] = v
        if "speed" in payload:
            payload["status"] = f"speed {payload['speed']}"
        return payload

