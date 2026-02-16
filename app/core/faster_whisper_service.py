from __future__ import annotations

import asyncio
import base64
from concurrent.futures import ThreadPoolExecutor
import ctypes
import gc
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
from typing import Any, Literal
import warnings
import wave
from dataclasses import dataclass

if os.name == "nt":
    import winreg


class FasterWhisperService:
    def __init__(self) -> None:
        # Keep Windows cache warning from flooding stderr; app shows actionable hints itself.
        os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")
        os.environ.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")
        self._executor: ThreadPoolExecutor | None = ThreadPoolExecutor(max_workers=1, thread_name_prefix="fw_asr")
        self._dll_dir_handles: list[Any] = []
        self._dll_dir_keys: set[str] = set()
        self._active_model = None
        self._active_runtime = ""
        self._active_model_name = ""
        self._active_model_dir = ""

    @staticmethod
    def _is_cuda_runtime_error(exc: Exception) -> bool:
        text = str(exc).lower()
        markers = (
            "cublas64",
            "cudnn",
            "cuda",
            "libcublas",
            "libcudnn",
        )
        return any(m in text for m in markers)

    @staticmethod
    def model_source(model_name: str) -> str:
        repo = FasterWhisperService._model_repo_id(model_name)
        return f"https://huggingface.co/{repo}"

    @staticmethod
    def _model_repo_id(model_name: str) -> str:
        # Resolve official repository mapping from faster-whisper when possible.
        try:
            from faster_whisper.utils import _MODELS  # type: ignore

            repo = _MODELS.get(model_name)
            if repo:
                return str(repo)
        except Exception:
            pass

        # Fallback for common Systran naming.
        return f"Systran/faster-whisper-{model_name}"

    @staticmethod
    def _runtime_display(runtime: str) -> str:
        if runtime.startswith("cuda:int8"):
            return "cuda:int8"
        return runtime

    @staticmethod
    def _gpu_attempts(
        preference: Literal["auto", "float16", "int8"] = "auto",
    ) -> tuple[tuple[str, str, str], ...]:
        if preference == "float16":
            return (("cuda", "float16", "cuda:float16"),)
        if preference == "int8":
            return (("cuda", "int8", "cuda:int8"),)
        return (
            ("cuda", "float16", "cuda:float16"),
            ("cuda", "int8", "cuda:int8"),
        )

    @staticmethod
    def _load_model_with_fallback(
        model_name: str,
        base_kwargs: dict[str, Any],
        preference: Literal["auto", "float16", "int8"] = "auto",
    ) -> tuple[Any, str]:
        from faster_whisper import WhisperModel  # type: ignore

        # Try selected GPU precision strategy first, then CPU fallback.
        for device, compute_type, runtime in FasterWhisperService._gpu_attempts(preference):
            try:
                return WhisperModel(model_name, device=device, compute_type=compute_type, **base_kwargs), runtime
            except Exception:
                continue
        return WhisperModel(model_name, device="cpu", compute_type="int8", **base_kwargs), "cpu:int8"

    def _model_dir_key(self, model_dir: str | None) -> str:
        return str(Path(model_dir).resolve()) if model_dir else ""

    def _clear_model(self) -> None:
        self._active_model = None
        self._active_runtime = ""
        self._active_model_name = ""
        self._active_model_dir = ""
        gc.collect()
        try:
            import torch  # type: ignore

            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        except Exception:
            pass

    def unload_model(self) -> None:
        self._clear_model()

    def active_runtime(self) -> str:
        return self._active_runtime or "none"

    def _ensure_executor(self) -> ThreadPoolExecutor:
        if self._executor is None:
            self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="fw_asr")
        return self._executor

    async def _run_blocking(self, fn):
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(self._ensure_executor(), fn)

    async def unload_model_async(self) -> None:
        ex = self._executor
        if ex is None:
            return
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(ex, self._clear_model)
        self._executor = None
        await asyncio.to_thread(ex.shutdown, wait=True, cancel_futures=True)

    @staticmethod
    def _discover_nvidia_dll_dirs() -> list[Path]:
        if os.name != "nt":
            return []
        module_candidates = (
            "nvidia.cublas.bin",
            "nvidia.cublas.lib",
            "nvidia.cudnn.bin",
            "nvidia.cudnn.lib",
            "nvidia.cuda_runtime.bin",
            "nvidia.cuda_runtime.lib",
        )
        dirs: list[Path] = []
        seen: set[str] = set()
        for mod in module_candidates:
            try:
                spec = importlib.util.find_spec(mod)
            except Exception:
                spec = None
            if spec is None:
                continue
            locs = list(spec.submodule_search_locations or [])
            for loc in locs:
                p = Path(loc)
                key = str(p).lower()
                if p.exists() and key not in seen:
                    dirs.append(p)
                    seen.add(key)
        # ctranslate2 wheel can bundle cudnn DLLs in its package directory.
        try:
            spec = importlib.util.find_spec("ctranslate2")
            if spec and spec.origin:
                p = Path(spec.origin).resolve().parent
                key = str(p).lower()
                if p.exists() and key not in seen:
                    dirs.append(p)
                    seen.add(key)
        except Exception:
            pass
        return dirs

    def _setup_windows_nvidia_dll_dirs(self) -> None:
        if os.name != "nt":
            return
        for p in self._discover_nvidia_dll_dirs():
            if p.exists():
                try:
                    key = str(p).lower()
                    if key in self._dll_dir_keys:
                        continue
                    self._dll_dir_handles.append(os.add_dll_directory(str(p)))
                    self._dll_dir_keys.add(key)
                except Exception:
                    pass

    def _prime_windows_cuda_dlls(self) -> None:
        """Best-effort preload of CUDA/cuDNN runtime DLLs on Windows.

        This reduces sporadic runtime-load failures where the DLL exists but
        gets resolved too late during the first CUDA inference call.
        """
        if os.name != "nt":
            return
        self._setup_windows_nvidia_dll_dirs()
        names = ("cublas64_12.dll", "cudnn64_9.dll")
        for dll in names:
            # First try normal resolution with added DLL directories.
            try:
                ctypes.CDLL(dll)
                continue
            except Exception:
                pass
            # Then try absolute-path loading from discovered vendor dirs.
            for p in self._discover_nvidia_dll_dirs():
                candidate = p / dll
                if not candidate.exists():
                    continue
                try:
                    ctypes.CDLL(str(candidate))
                    break
                except Exception:
                    continue

    def diagnose_gpu_stack(self) -> dict[str, str]:
        self._setup_windows_nvidia_dll_dirs()
        out: dict[str, str] = {}
        try:
            from importlib.metadata import version

            out["ctranslate2"] = version("ctranslate2")
        except Exception:
            out["ctranslate2"] = "not installed"
        try:
            from importlib.metadata import version

            out["nvidia-cublas-cu12"] = version("nvidia-cublas-cu12")
        except Exception:
            out["nvidia-cublas-cu12"] = ""
        try:
            from importlib.metadata import version

            out["nvidia-cudnn-cu12"] = version("nvidia-cudnn-cu12")
        except Exception:
            out["nvidia-cudnn-cu12"] = ""
        out["gpu_count"] = self._gpu_count_from_nvidia_smi()
        for dll in ("cublas64_12.dll", "cudnn64_9.dll"):
            try:
                ctypes.CDLL(dll)
                out[dll] = "ok"
            except Exception as exc:
                found = self._find_dll_on_known_dirs(dll)
                if found:
                    out[dll] = "found_unloadable"
                    out[f"{dll}_detail"] = str(exc)
                else:
                    out[dll] = "missing"
        return out

    @staticmethod
    def _gpu_count_from_nvidia_smi() -> str:
        try:
            proc = subprocess.run(["nvidia-smi", "-L"], capture_output=True, text=True, timeout=5, check=False)
            lines = [ln for ln in (proc.stdout or "").splitlines() if ln.strip().startswith("GPU ")]
            return str(len(lines))
        except Exception:
            return "0"

    def _find_dll_on_known_dirs(self, dll_name: str) -> bool:
        for p in self._discover_nvidia_dll_dirs():
            if (p / dll_name).exists():
                return True
        return False

    @staticmethod
    def _hf_token() -> str | None:
        token = (os.environ.get("HF_TOKEN") or os.environ.get("HUGGINGFACE_HUB_TOKEN") or "").strip()
        if token:
            return token
        if os.name == "nt":
            # setx writes to user env in registry; current shell may not see it immediately.
            try:
                with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Environment") as key:
                    for name in ("HF_TOKEN", "HUGGINGFACE_HUB_TOKEN"):
                        try:
                            value, _ = winreg.QueryValueEx(key, name)
                        except FileNotFoundError:
                            continue
                        token = str(value).strip()
                        if token:
                            return token
            except Exception:
                pass
        return token or None

    @dataclass
    class _DownloadPlan:
        repo_id: str
        items: list[Any]
        total_bytes: int

    def _build_download_plan(self, model_name: str, model_dir: str | None, token: str | None) -> _DownloadPlan:
        try:
            from huggingface_hub import snapshot_download  # type: ignore
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError("huggingface_hub unavailable. Install: pip install huggingface_hub") from exc

        repo_id = self._model_repo_id(model_name)
        dry_infos = snapshot_download(
            repo_id=repo_id,
            cache_dir=model_dir or None,
            token=token,
            dry_run=True,
            local_files_only=False,
        )
        total = 0
        for info in dry_infos:
            if bool(getattr(info, "will_download", False)):
                total += int(getattr(info, "file_size", 0) or 0)
        return self._DownloadPlan(repo_id=repo_id, items=list(dry_infos), total_bytes=total)

    @staticmethod
    def _is_hf_cas_error(exc: Exception) -> bool:
        text = str(exc).lower()
        return "cas service error" in text or "xet" in text or "requestmiddleware error" in text

    @staticmethod
    def _snapshot_download(repo_id: str, cache_dir: str | None, token: str | None, *, disable_xet: bool) -> str:
        from huggingface_hub import snapshot_download  # type: ignore

        old_disable_xet = os.environ.get("HF_HUB_DISABLE_XET")
        old_hf_transfer = os.environ.get("HF_HUB_ENABLE_HF_TRANSFER")
        try:
            if disable_xet:
                os.environ["HF_HUB_DISABLE_XET"] = "1"
                os.environ["HF_HUB_ENABLE_HF_TRANSFER"] = "0"
            return snapshot_download(
                repo_id=repo_id,
                cache_dir=cache_dir or None,
                token=token,
                local_files_only=False,
                max_workers=3 if disable_xet else 6,
                etag_timeout=40,
            )
        finally:
            if old_disable_xet is None:
                os.environ.pop("HF_HUB_DISABLE_XET", None)
            else:
                os.environ["HF_HUB_DISABLE_XET"] = old_disable_xet
            if old_hf_transfer is None:
                os.environ.pop("HF_HUB_ENABLE_HF_TRANSFER", None)
            else:
                os.environ["HF_HUB_ENABLE_HF_TRANSFER"] = old_hf_transfer

    @staticmethod
    def _plan_downloaded_bytes(items: list[Any]) -> int:
        done = 0
        for info in items:
            if not bool(getattr(info, "will_download", False)):
                continue
            path = Path(str(getattr(info, "local_path", "")))
            size = int(getattr(info, "file_size", 0) or 0)
            if path.exists():
                try:
                    done += min(size, int(path.stat().st_size))
                except Exception:
                    pass
        return done

    def _ensure_loaded_model(
        self,
        model_name: str,
        model_dir: str | None,
        *,
        local_only: bool = False,
        compute_preference: Literal["auto", "float16", "int8"] = "auto",
    ) -> tuple[Any, str]:
        model_dir_key = self._model_dir_key(model_dir)
        if (
            self._active_model is not None
            and self._active_model_name == model_name
            and self._active_model_dir == model_dir_key
        ):
            return self._active_model, self._active_runtime

        common: dict[str, Any] = {}
        if model_dir:
            Path(model_dir).mkdir(parents=True, exist_ok=True)
            common["download_root"] = model_dir
        common["local_files_only"] = bool(local_only)
        token = self._hf_token()
        if token:
            common["use_auth_token"] = token
        model, runtime = self._load_model_with_fallback(model_name, common, preference=compute_preference)
        self._active_model = model
        self._active_runtime = runtime
        self._active_model_name = model_name
        self._active_model_dir = model_dir_key
        return model, runtime

    async def download_model(
        self,
        model_name: str,
        model_dir: str | None = None,
        *,
        compute_preference: Literal["auto", "float16", "int8"] = "auto",
        progress_cb=None,
    ) -> dict[str, str | bool]:
        source = self.model_source(model_name)
        token = self._hf_token()
        if progress_cb:
            progress_cb({"progress": 0.0, "message": f"Preparing download for {model_name}"})
            progress_cb({"progress": 0.0, "message": f"Download source: {source}"})
            progress_cb({"progress": 0.0, "message": "Checking local model cache..."})

        # If model already exists locally, skip redownload and return a clear status.
        try:
            await self.warmup_model(model_name, model_dir, compute_preference=compute_preference, local_only=True)
            if progress_cb:
                progress_cb({"progress": 0.0, "message": f"Model already exists locally: {model_name} (skip download)"})
            return {"source": source, "model": model_name, "ok": True, "skipped": True}
        except Exception:
            pass

        plan = await self._run_blocking(lambda: self._build_download_plan(model_name, model_dir, token))
        if plan.total_bytes <= 0:
            # Nothing to download (already cached), just verify local load.
            await self.warmup_model(
                model_name,
                model_dir,
                compute_preference=compute_preference,
                local_only=True,
                progress_cb=progress_cb,
            )
            return {"source": source, "model": model_name, "ok": True, "skipped": True}

        if progress_cb:
            total_mb = max(1, plan.total_bytes // (1024 * 1024))
            progress_cb({"progress": 0.0, "message": f"Downloading model files... (0/{total_mb} MB)"})
            if not token:
                progress_cb(
                    {
                        "progress": 0.0,
                        "message": "No HF_TOKEN detected in current process/user env. Download may be rate-limited.",
                    }
                )
            progress_cb(
                {
                    "progress": 0.0,
                    "message": "Tip: enable Windows Developer Mode to improve HF cache behavior on symlink-limited systems.",
                }
            )

        def _do_download() -> str:
            try:
                return self._snapshot_download(plan.repo_id, model_dir, token, disable_xet=False)
            except Exception as exc:
                if not self._is_hf_cas_error(exc):
                    raise
                if progress_cb:
                    progress_cb(
                        {
                            "progress": 0.0,
                            "message": "HF CAS/Xet path failed, retrying with legacy download mode...",
                        }
                    )
                return self._snapshot_download(plan.repo_id, model_dir, token, disable_xet=True)

        download_task = asyncio.create_task(self._run_blocking(_do_download))
        while not download_task.done():
            await asyncio.sleep(1.0)
            done = self._plan_downloaded_bytes(plan.items)
            ratio = 0.0 if plan.total_bytes <= 0 else float(done) / float(plan.total_bytes)
            pct = min(82.0, max(0.0, ratio * 82.0))
            if progress_cb:
                done_mb = done // (1024 * 1024)
                total_mb = max(1, plan.total_bytes // (1024 * 1024))
                progress_cb(
                    {
                        "progress": pct,
                        "message": f"Downloading model files... ({done_mb}/{total_mb} MB)",
                        "transient": True,
                    }
                )
        await download_task
        if progress_cb:
            progress_cb({"progress": 84.0, "message": "Model files downloaded. Loading model..."})
        await self.warmup_model(
            model_name,
            model_dir,
            compute_preference=compute_preference,
            local_only=False,
            progress_cb=None,
        )
        if progress_cb:
            progress_cb({"progress": 94.0, "message": f"ASR runtime: {self._runtime_display(self.active_runtime())}"})
            progress_cb({"progress": 98.0, "message": "Verifying model load..."})
            progress_cb({"progress": 100.0, "message": f"Model download completed: {model_name}"})
        return {"source": source, "model": model_name, "ok": True, "skipped": False}

    async def warmup_model(
        self,
        model_name: str,
        model_dir: str | None = None,
        *,
        compute_preference: Literal["auto", "float16", "int8"] = "auto",
        local_only: bool = False,
        progress_cb=None,
    ) -> None:
        def _load() -> str:
            self._setup_windows_nvidia_dll_dirs()
            try:
                from faster_whisper import WhisperModel  # type: ignore  # noqa: F401
            except Exception as exc:  # noqa: BLE001
                raise RuntimeError("faster-whisper unavailable. Install: pip install faster-whisper") from exc
            try:
                with warnings.catch_warnings():
                    warnings.filterwarnings(
                        "ignore",
                        message=".*cache-system uses symlinks by default.*",
                        category=UserWarning,
                    )
                    _, runtime = self._ensure_loaded_model(
                        model_name,
                        model_dir,
                        local_only=local_only,
                        compute_preference=compute_preference,
                    )
                return runtime
            except Exception as exc:  # noqa: BLE001
                if not self._is_cuda_runtime_error(exc):
                    raise
                # CUDA runtime is unavailable, force CPU fallback.
                common: dict[str, Any] = {}
                if model_dir:
                    Path(model_dir).mkdir(parents=True, exist_ok=True)
                    common["download_root"] = model_dir
                common["local_files_only"] = bool(local_only)
                token = self._hf_token()
                if token:
                    common["use_auth_token"] = token
                with warnings.catch_warnings():
                    warnings.filterwarnings(
                        "ignore",
                        message=".*cache-system uses symlinks by default.*",
                        category=UserWarning,
                    )
                    WhisperModel(model_name, device="cpu", compute_type="int8", **common)
                self._active_model = None
                self._active_runtime = "cpu:int8"
                self._active_model_name = model_name
                self._active_model_dir = self._model_dir_key(model_dir)
                return "cpu:int8"

        if progress_cb:
            progress_cb({"progress": 10.0, "message": f"Loading model: {model_name}"})
        task = asyncio.create_task(self._run_blocking(_load))
        tick = 0
        while True:
            try:
                runtime = await asyncio.wait_for(asyncio.shield(task), timeout=1.5)
                break
            except asyncio.TimeoutError:
                tick += 1
                if progress_cb:
                    pct = min(88.0, 86.0 + tick * 0.2)
                    progress_cb(
                        {
                            "progress": pct,
                            "message": f"Finalizing model load... ({tick * 1.5:.0f}s)",
                            "transient": True,
                        }
                    )
        if progress_cb:
            progress_cb({"progress": 90.0, "message": f"ASR runtime: {self._runtime_display(runtime)}"})
            if runtime.startswith("cpu:"):
                progress_cb({"progress": 90.0, "message": "ASR is running on CPU fallback (may be slower)."})
            progress_cb({"progress": 100.0, "message": f"Model loaded: {model_name}"})

    async def transcribe_to_srt(
        self,
        video_path: str,
        model_name: str,
        out_srt: str,
        source_lang: str = "auto",
        compute_preference: Literal["auto", "float16", "int8"] = "auto",
        model_dir: str | None = None,
        progress_cb=None,
    ) -> None:
        def _run() -> None:
            self._setup_windows_nvidia_dll_dirs()
            try:
                from faster_whisper import WhisperModel  # type: ignore
            except Exception as exc:  # noqa: BLE001
                raise RuntimeError("faster-whisper unavailable. Install: pip install faster-whisper") from exc

            base_kwargs: dict[str, Any] = {}
            if model_dir:
                Path(model_dir).mkdir(parents=True, exist_ok=True)
                base_kwargs["download_root"] = model_dir

            transcribe_kwargs: dict[str, Any] = {}
            if source_lang != "auto":
                transcribe_kwargs["language"] = source_lang

            attempts: list[tuple[str, str, str]] = list(self._gpu_attempts(compute_preference))
            attempts.append(("cpu", "int8", "cpu:int8"))

            model_dir_key = self._model_dir_key(model_dir)
            if (
                self._active_model is not None
                and self._active_model_name == model_name
                and self._active_model_dir == model_dir_key
                and self._active_runtime
            ):
                active = self._active_runtime
                attempts = [x for x in attempts if x[2] != active]
                dev, ctype = active.split(":", 1)
                attempts.insert(0, (dev, ctype, active))

            lines: list[str] = []
            last_exc: Exception | None = None
            completed = False
            for attempt_idx, (device, compute_type, runtime) in enumerate(attempts):
                max_retry = 2 if device == "cuda" else 1
                for retry_idx in range(max_retry):
                    try:
                        if device == "cuda":
                            self._prime_windows_cuda_dlls()

                        reuse_cached = (
                            retry_idx == 0
                            and self._active_model is not None
                            and self._active_model_name == model_name
                            and self._active_model_dir == model_dir_key
                            and self._active_runtime == runtime
                        )
                        if reuse_cached:
                            model = self._active_model
                        else:
                            model = WhisperModel(model_name, device=device, compute_type=compute_type, **base_kwargs)
                            self._active_model = model
                            self._active_runtime = runtime
                            self._active_model_name = model_name
                            self._active_model_dir = model_dir_key

                        if progress_cb:
                            progress_cb({"progress": 25.0, "message": f"ASR runtime: {self._runtime_display(runtime)}"})
                            if runtime.startswith("cpu:"):
                                progress_cb({"progress": 25.0, "message": "ASR is running on CPU fallback (may be slower)."})

                        segments, _ = model.transcribe(video_path, **transcribe_kwargs)
                        idx = 1
                        lines = []
                        for seg in segments:
                            txt = str(getattr(seg, "text", "")).strip()
                            if not txt:
                                continue
                            start = self._fmt_time(float(getattr(seg, "start", 0.0)))
                            end = self._fmt_time(float(getattr(seg, "end", 0.0)))
                            lines.extend([str(idx), f"{start} --> {end}", txt, ""])
                            idx += 1
                        completed = True
                        break
                    except Exception as exc:  # noqa: BLE001
                        last_exc = exc
                        retryable_cuda = device == "cuda" and self._is_cuda_runtime_error(exc) and retry_idx + 1 < max_retry
                        if retryable_cuda:
                            # Drop cached handle and retry same CUDA runtime once after re-priming DLLs.
                            if self._active_runtime == runtime:
                                self._active_model = None
                            continue

                        has_next_runtime = attempt_idx + 1 < len(attempts)
                        if has_next_runtime:
                            next_runtime = self._runtime_display(attempts[attempt_idx + 1][2])
                            if progress_cb:
                                progress_cb(
                                    {
                                        "progress": 25.0,
                                        "message": f"ASR runtime fallback: {self._runtime_display(runtime)} -> {next_runtime}",
                                    }
                                )
                            if self._active_runtime == runtime:
                                self._active_model = None
                            break

                        short = str(exc).strip().replace("\n", " ")
                        if progress_cb:
                            progress_cb({"progress": 25.0, "message": f"ASR failed on {runtime}: {short[:120]}"})
                        raise
                if completed:
                    break

            if not lines and last_exc is not None:
                raise last_exc
            Path(out_srt).write_text("\n".join(lines).strip() + "\n", encoding="utf-8")

        await self._run_blocking(_run)

    async def transcribe_cloud_to_srt(
        self,
        media_path: str,
        out_srt: str,
        *,
        api_base_url: str,
        api_key: str,
        model_name: str,
        backend: str = "asr_openai_compatible",
        source_lang: str = "auto",
    ) -> None:
        def _run() -> None:
            try:
                from openai import OpenAI  # type: ignore
            except Exception as exc:  # noqa: BLE001
                raise RuntimeError("openai SDK unavailable. Install: pip install openai") from exc

            base = (api_base_url or "").strip().rstrip("/")
            if not base:
                raise RuntimeError("Cloud ASR requires API base URL.")
            if not api_key:
                raise RuntimeError("Cloud ASR requires API key/token.")
            if not model_name:
                raise RuntimeError("Cloud ASR requires model name.")

            try:
                client = OpenAI(base_url=base, api_key=api_key)
                if backend == "asr_gemini" or self._is_gemini_openai_base(base):
                    srt_text = self._gemini_chat_audio_to_srt(
                        client=client,
                        media_path=media_path,
                        model_name=model_name,
                        source_lang=source_lang,
                    )
                    Path(out_srt).write_text(srt_text, encoding="utf-8")
                    return
                if backend == "asr_qwen" or self._is_qwen_openai_base(base):
                    srt_text = self._qwen_chat_audio_to_srt(
                        client=client,
                        media_path=media_path,
                        model_name=model_name,
                        source_lang=source_lang,
                    )
                    Path(out_srt).write_text(srt_text, encoding="utf-8")
                    return

                with open(media_path, "rb") as fp:
                    kwargs: dict[str, Any] = {
                        "model": model_name,
                        "file": fp,
                        "response_format": "verbose_json",
                    }
                    if source_lang != "auto":
                        kwargs["language"] = source_lang
                    resp = client.audio.transcriptions.create(**kwargs)
            except Exception as exc:  # noqa: BLE001
                raise RuntimeError(self._format_cloud_asr_error(exc, base, model_name)) from exc

            # openai-python may return pydantic model or dict-like object.
            segments = getattr(resp, "segments", None)
            if segments is None and isinstance(resp, dict):
                segments = resp.get("segments")

            lines: list[str] = []
            if segments:
                idx = 1
                for seg in segments:
                    if isinstance(seg, dict):
                        txt = str(seg.get("text", "")).strip()
                        start_val = float(seg.get("start", 0.0))
                        end_val = float(seg.get("end", start_val + 1.0))
                    else:
                        txt = str(getattr(seg, "text", "")).strip()
                        start_val = float(getattr(seg, "start", 0.0))
                        end_val = float(getattr(seg, "end", start_val + 1.0))
                    if not txt:
                        continue
                    lines.extend(
                        [
                            str(idx),
                            f"{self._fmt_time(start_val)} --> {self._fmt_time(end_val)}",
                            txt,
                            "",
                        ]
                    )
                    idx += 1
            else:
                text = getattr(resp, "text", None)
                if text is None and isinstance(resp, dict):
                    text = resp.get("text")
                txt = str(text or "").strip()
                if not txt:
                    raise RuntimeError("Cloud ASR returned empty transcript.")
                lines = ["1", "00:00:00,000 --> 00:00:30,000", txt, ""]

            Path(out_srt).write_text("\n".join(lines).strip() + "\n", encoding="utf-8")

        await self._run_blocking(_run)

    async def test_cloud_asr_connection(
        self,
        *,
        api_base_url: str,
        api_key: str,
        model_name: str,
        backend: str = "asr_openai_compatible",
    ) -> tuple[bool, str]:
        def _run() -> tuple[bool, str]:
            try:
                from openai import OpenAI  # type: ignore
            except Exception as exc:  # noqa: BLE001
                return False, f"openai SDK unavailable. Install: pip install openai ({exc})"

            base = (api_base_url or "").strip().rstrip("/")
            if not base:
                return False, "Cloud ASR requires API base URL."
            if not api_key:
                return False, "Cloud ASR requires API key/token."
            if not model_name:
                return False, "Cloud ASR requires model name."

            client = OpenAI(base_url=base, api_key=api_key)
            try:
                if backend == "asr_gemini" or self._is_gemini_openai_base(base):
                    text = self._gemini_chat_audio_test(client=client, model_name=model_name)
                elif backend == "asr_qwen" or self._is_qwen_openai_base(base):
                    text = self._qwen_chat_audio_test(client=client, model_name=model_name)
                else:
                    ping_wav = self._build_test_wav_bytes()
                    payload_file = ("asr_test.wav", ping_wav, "audio/wav")
                    resp = client.audio.transcriptions.create(
                        model=model_name,
                        file=payload_file,
                        response_format="text",
                    )
                    text = str(resp or "").strip()
                if text:
                    return True, "ASR endpoint reachable."
                return True, "ASR endpoint reachable (empty test transcript)."
            except Exception as exc:  # noqa: BLE001
                return False, self._format_cloud_asr_error(exc, base, model_name)

        return await self._run_blocking(_run)

    @staticmethod
    def _build_test_wav_bytes() -> bytes:
        # 0.3s of mono 16kHz silence for lightweight endpoint probing.
        sample_rate = 16_000
        frames = b"\x00\x00" * int(sample_rate * 0.3)
        buf = io.BytesIO()
        with wave.open(buf, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)  # 16-bit PCM
            wf.setframerate(sample_rate)
            wf.writeframes(frames)
        return buf.getvalue()

    @staticmethod
    def _is_gemini_openai_base(base_url: str) -> bool:
        base = (base_url or "").lower()
        return "generativelanguage.googleapis.com" in base

    @staticmethod
    def _is_qwen_openai_base(base_url: str) -> bool:
        base = (base_url or "").lower()
        return "dashscope.aliyuncs.com" in base

    @staticmethod
    def _looks_like_srt(text: str) -> bool:
        return "-->" in text

    @staticmethod
    def _strip_markdown_fence(text: str) -> str:
        raw = text.strip()
        if raw.startswith("```"):
            lines = raw.splitlines()
            if lines:
                lines = lines[1:]
            if lines and lines[-1].strip().startswith("```"):
                lines = lines[:-1]
            return "\n".join(lines).strip()
        return raw

    @staticmethod
    def _response_text(resp: Any) -> str:
        # OpenAI SDK may return message content as string or typed parts.
        try:
            choice = resp.choices[0]
            content = choice.message.content
        except Exception:
            return str(resp or "").strip()
        if isinstance(content, str):
            return content.strip()
        if isinstance(content, list):
            parts: list[str] = []
            for item in content:
                if isinstance(item, dict):
                    txt = str(item.get("text", "")).strip()
                    if txt:
                        parts.append(txt)
                else:
                    txt = str(getattr(item, "text", "") or "").strip()
                    if txt:
                        parts.append(txt)
            return "\n".join(parts).strip()
        return str(content or "").strip()

    def _audio_duration_seconds(self, media_path: str) -> float:
        try:
            with wave.open(media_path, "rb") as wf:
                frames = wf.getnframes()
                rate = wf.getframerate()
                if rate > 0:
                    return max(1.0, float(frames) / float(rate))
        except Exception:
            pass
        return 30.0

    def _gemini_chat_audio_to_srt(
        self,
        *,
        client: Any,
        media_path: str,
        model_name: str,
        source_lang: str,
    ) -> str:
        suffix = Path(media_path).suffix.lower()
        if suffix == ".wav":
            audio_fmt = "wav"
        elif suffix == ".mp3":
            audio_fmt = "mp3"
        else:
            raise RuntimeError(
                "Gemini cloud ASR currently expects wav/mp3 input in OpenAI-compatible mode. "
                f"Got: {suffix or 'unknown'}"
            )

        audio_b64 = base64.b64encode(Path(media_path).read_bytes()).decode("utf-8")
        lang_hint = "" if source_lang == "auto" else f" The source language is {source_lang}."
        prompt = (
            "Transcribe this audio and return strict SRT format only, with accurate timestamps."
            " Do not output markdown fences or explanations."
            + lang_hint
        )
        resp = client.chat.completions.create(
            model=model_name,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {"type": "input_audio", "input_audio": {"data": audio_b64, "format": audio_fmt}},
                    ],
                }
            ],
        )
        text = self._strip_markdown_fence(self._response_text(resp))
        if self._looks_like_srt(text):
            return text.strip() + "\n"

        transcript = text.strip()
        if not transcript:
            raise RuntimeError("Cloud ASR returned empty transcript.")
        duration = self._audio_duration_seconds(media_path)
        return (
            "1\n"
            f"00:00:00,000 --> {self._fmt_time(duration)}\n"
            f"{transcript}\n"
        )

    def _gemini_chat_audio_test(self, *, client: Any, model_name: str) -> str:
        ping_wav = self._build_test_wav_bytes()
        audio_b64 = base64.b64encode(ping_wav).decode("utf-8")
        resp = client.chat.completions.create(
            model=model_name,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "Transcribe this short silent audio. Return short plain text only."},
                        {"type": "input_audio", "input_audio": {"data": audio_b64, "format": "wav"}},
                    ],
                }
            ],
        )
        return self._response_text(resp)

    def _qwen_chat_audio_to_srt(
        self,
        *,
        client: Any,
        media_path: str,
        model_name: str,
        source_lang: str,
    ) -> str:
        audio_b64 = base64.b64encode(Path(media_path).read_bytes()).decode("utf-8")
        lang_hint = "" if source_lang == "auto" else f" The source language is {source_lang}."
        prompt = (
            "Transcribe this audio and return strict SRT format only with accurate timestamps."
            " Do not output markdown fences or explanations."
            + lang_hint
        )
        resp = client.chat.completions.create(
            model=model_name,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {"type": "input_audio", "input_audio": {"data": f"data:;base64,{audio_b64}", "format": "wav"}},
                    ],
                }
            ],
        )
        text = self._strip_markdown_fence(self._response_text(resp))
        if self._looks_like_srt(text):
            return text.strip() + "\n"
        transcript = text.strip()
        if not transcript:
            raise RuntimeError("Cloud ASR returned empty transcript.")
        duration = self._audio_duration_seconds(media_path)
        return (
            "1\n"
            f"00:00:00,000 --> {self._fmt_time(duration)}\n"
            f"{transcript}\n"
        )

    def _qwen_chat_audio_test(self, *, client: Any, model_name: str) -> str:
        ping_wav = self._build_test_wav_bytes()
        audio_b64 = base64.b64encode(ping_wav).decode("utf-8")
        resp = client.chat.completions.create(
            model=model_name,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "Transcribe this short silent audio. Return short plain text only."},
                        {"type": "input_audio", "input_audio": {"data": f"data:;base64,{audio_b64}", "format": "wav"}},
                    ],
                }
            ],
        )
        return self._response_text(resp)

    @staticmethod
    def _format_cloud_asr_error(exc: Exception, base_url: str, model_name: str) -> str:
        status = getattr(exc, "status_code", None)
        response = getattr(exc, "response", None)
        body = getattr(exc, "body", None)
        text = str(exc).strip().replace("\n", " ")

        if status is None and response is not None:
            status = getattr(response, "status_code", None)

        detail = ""
        if response is not None:
            try:
                detail = str(getattr(response, "text", "") or "").strip()
            except Exception:
                detail = ""
        if not detail and body is not None:
            try:
                if isinstance(body, (dict, list)):
                    detail = json.dumps(body, ensure_ascii=False)
                else:
                    detail = str(body).strip()
            except Exception:
                detail = str(body).strip()
        if not detail:
            detail = text
        if len(detail) > 320:
            detail = detail[:320] + "..."

        hint = ""
        status_num = int(status) if isinstance(status, int) else None
        if status_num == 401:
            hint = "Hint: API key/token invalid or missing."
        elif status_num == 403:
            hint = "Hint: token has no ASR permission for this endpoint/model."
        elif status_num == 404:
            hint = "Hint: base URL or ASR route not found. Check '/v1' path and model name."
        elif status_num == 429:
            hint = "Hint: rate-limited or quota exceeded."
        elif status_num is not None and status_num >= 500:
            hint = "Hint: provider server-side failure, retry later."
        elif "connection" in text.lower() or "timeout" in text.lower():
            hint = "Hint: network/SSL timeout or connectivity issue."

        prefix = f"Cloud ASR request failed (HTTP {status_num})" if status_num is not None else "Cloud ASR request failed"
        segments = [prefix, f"base={base_url}", f"model={model_name}", f"detail={detail}"]
        if hint:
            segments.append(hint)
        return " | ".join(segments)

    @staticmethod
    def _fmt_time(seconds: float) -> str:
        ms = int(max(0.0, seconds) * 1000)
        h, rem = divmod(ms, 3_600_000)
        m, rem = divmod(rem, 60_000)
        s, rem = divmod(rem, 1000)
        return f"{h:02d}:{m:02d}:{s:02d},{rem:03d}"
