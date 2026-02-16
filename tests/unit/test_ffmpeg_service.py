from app.core.ffmpeg_service import FFmpegService
from app.core.models import MediaMeta, MergeInput


def test_build_command_video_audio_cpu_h264() -> None:
    svc = FFmpegService("ffmpeg.exe", "ffprobe.exe")
    payload = MergeInput(
        visual_paths=["video.mp4"],
        audio_paths=["audio.aac"],
        subtitle_paths=[],
        output_path="out.mkv",
        output_quality="cpu_h264",
    )
    metas = {
        "video.mp4": MediaMeta(path="video.mp4", has_video=True, has_audio=True, has_subtitle=False),
        "audio.aac": MediaMeta(path="audio.aac", has_video=False, has_audio=True, has_subtitle=False),
    }
    cmd = svc.build_merge_command(payload, metas)
    assert "-c:v" in cmd and "libx264" in cmd
    assert "out.mkv" in cmd


def test_build_command_video_audio_nvidia_h265() -> None:
    svc = FFmpegService("ffmpeg.exe", "ffprobe.exe")
    payload = MergeInput(
        visual_paths=["video.mp4"],
        audio_paths=["audio.aac"],
        subtitle_paths=[],
        output_path="out.mkv",
        output_quality="nvidia_h265",
    )
    metas = {
        "video.mp4": MediaMeta(path="video.mp4", has_video=True, has_audio=True, has_subtitle=False),
        "audio.aac": MediaMeta(path="audio.aac", has_video=False, has_audio=True, has_subtitle=False),
    }
    cmd = svc.build_merge_command(payload, metas)
    assert "-c:v" in cmd and "hevc_nvenc" in cmd
    assert "out.mkv" in cmd


def test_build_command_video_audio_lossless_copy() -> None:
    svc = FFmpegService("ffmpeg.exe", "ffprobe.exe")
    payload = MergeInput(
        visual_paths=["video.mp4"],
        audio_paths=["audio.aac"],
        subtitle_paths=[],
        output_path="out.mkv",
        output_quality="lossless_copy",
    )
    metas = {
        "video.mp4": MediaMeta(path="video.mp4", has_video=True, has_audio=True, has_subtitle=False),
        "audio.aac": MediaMeta(path="audio.aac", has_video=False, has_audio=True, has_subtitle=False),
    }
    cmd = svc.build_merge_command(payload, metas)
    assert "-c:v" in cmd and "copy" in cmd
    assert "-c:a" in cmd and "copy" in cmd


def test_build_command_hard_subtitle_forces_filter() -> None:
    svc = FFmpegService("ffmpeg.exe", "ffprobe.exe")
    payload = MergeInput(
        visual_paths=["video.mp4"],
        audio_paths=[],
        subtitle_paths=["sub.srt"],
        output_path="out.mkv",
        output_quality="cpu_h264",
        subtitle_mode="hard",
    )
    metas = {
        "video.mp4": MediaMeta(path="video.mp4", has_video=True, has_audio=True, has_subtitle=False),
        "sub.srt": MediaMeta(path="sub.srt", has_video=False, has_audio=False, has_subtitle=True),
    }
    cmd = svc.build_merge_command(payload, metas)
    assert "-vf" in cmd
    assert any("subtitles=" in part for part in cmd)


def test_build_command_uses_image_when_video_input_has_no_video_stream() -> None:
    svc = FFmpegService("ffmpeg.exe", "ffprobe.exe")
    payload = MergeInput(
        visual_paths=["track_only.mkv"],
        image_paths=["cover.jpg"],
        audio_paths=[],
        subtitle_paths=[],
        output_path="out.mkv",
        output_quality="nvidia_h265",
        subtitle_mode="soft",
    )
    metas = {
        "track_only.mkv": MediaMeta(path="track_only.mkv", has_video=False, has_audio=True, has_subtitle=True),
        "cover.jpg": MediaMeta(path="cover.jpg", has_video=True, has_audio=False, has_subtitle=False),
    }
    cmd = svc.build_merge_command(payload, metas)
    assert "-loop" in cmd
    assert "-i" in cmd and "cover.jpg" in cmd
    assert "-map" in cmd and "0:v:0" in cmd
    assert "-map" in cmd and "1:a:0" in cmd
    assert "-map" in cmd and "1:s:0" in cmd
