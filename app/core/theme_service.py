from __future__ import annotations

import shutil
from pathlib import Path

from app.infra.paths import backgrounds_dir, project_root


class ThemeService:
    def __init__(self) -> None:
        self._styles_dir = project_root() / "resources" / "styles"

    def load_stylesheet(self, name: str = "ios_light.qss") -> str:
        path = self._styles_dir / name
        if not path.exists():
            return ""
        return path.read_text(encoding="utf-8")

    def import_background(self, src_path: str) -> str:
        src = Path(src_path)
        if not src.exists():
            raise FileNotFoundError(src_path)
        dst = backgrounds_dir() / f"user_bg{src.suffix.lower()}"
        shutil.copy2(src, dst)
        return str(dst)

    def import_preview_image(self, src_path: str, slot: int) -> str:
        src = Path(src_path)
        if not src.exists():
            raise FileNotFoundError(src_path)
        dst = backgrounds_dir() / f"preview_{slot}{src.suffix.lower()}"
        shutil.copy2(src, dst)
        return str(dst)
