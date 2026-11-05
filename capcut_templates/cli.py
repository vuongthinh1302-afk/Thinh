"""Dòng lệnh: python -m capcut_templates <lệnh> ..."""

from __future__ import annotations

import argparse
import json
import os
import platform
import sys
from pathlib import Path

from . import spec as specmod
from .draft import write_draft
from .preview import render_preview

STARTER = {
    "name": "Template mới",
    "description": "Mô tả ngắn để người dùng dễ tìm",
    "tags": ["trend", "beat"],
    "aspect": "9:16",
    "fps": 30,
    "background": "#000000",
    "slots": [
        {"duration": 1.5, "label": "Ảnh mở đầu", "transition": "fade", "zoom": 1.1},
        {"duration": 1.0, "label": "Ảnh 2", "transition": "flash"},
        {"duration": 1.0, "label": "Ảnh 3", "transition": "slide_left"},
        {"duration": 2.0, "label": "Ảnh kết", "zoom": 1.15},
    ],
    "texts": [
        {"text": "Tiêu đề của bạn", "start": 0, "duration": 1.5, "size": 14, "y": -0.5,
         "animation": "fade_in"},
        {"text": "@tenkenh", "start": 3.5, "duration": 2.0, "size": 9, "y": 0.6},
    ],
    "music": {"path": "", "start": 0, "volume": 1.0, "beats": [0, 1.5, 2.5, 3.5, 5.5]},
}


def default_capcut_drafts_dir() -> Path | None:
    """Thư mục draft mặc định của CapCut PC (nếu tìm thấy)."""
    home = Path.home()
    candidates = []
    if platform.system() == "Windows":
        local = Path(os.environ.get("LOCALAPPDATA", home / "AppData/Local"))
        candidates.append(local / "CapCut/User Data/Projects/com.lveditor.draft")
    elif platform.system() == "Darwin":
        candidates.append(home / "Movies/CapCut/User Data/Projects/com.lveditor.draft")
    return next((c for c in candidates if c.is_dir()), None)


def _load_checked(path: str) -> specmod.TemplateSpec | None:
    try:
        s = specmod.load(path)
    except (specmod.SpecError, OSError) as e:
        print(f"LỖI: {e}")
        return None
    errors, warnings = specmod.validate(s)
    print(f"Template: {s.name} | {s.aspect} {s.size[0]}x{s.size[1]} @{s.fps}fps | "
          f"{len(s.slots)} slot | {s.duration:.2f}s")
    for w in warnings:
        print(f"  ⚠ {w}")
    for e in errors:
        print(f"  ✗ {e}")
    if errors:
        print("=> KHÔNG ĐẠT chuẩn, sửa lỗi rồi chạy lại.")
        return None
    print("=> Đạt chuẩn.")
    return s


def cmd_new(a) -> int:
    out = Path(a.file)
    if out.exists() and not a.force:
        print(f"{out} đã tồn tại (thêm --force để ghi đè)")
        return 1
    data = dict(STARTER, name=a.name or STARTER["name"])
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Đã tạo {out}. Sửa file rồi chạy: python -m capcut_templates build {out}")
    return 0


def cmd_validate(a) -> int:
    return 0 if all(_load_checked(f) for f in a.files) else 1


def cmd_build(a) -> int:
    code = 0
    out_root = Path(a.out) if a.out else None
    if a.install:
        out_root = default_capcut_drafts_dir()
        if not out_root:
            print("Không tìm thấy thư mục draft CapCut; dùng --out để chỉ định.")
            return 1
    out_root = out_root or Path("output")
    for f in a.files:
        s = _load_checked(f)
        if not s:
            code = 1
            continue
        folder = write_draft(s, out_root)
        print(f"  Draft: {folder}")
        if not a.no_preview:
            try:
                mp4 = render_preview(s, folder / "preview.mp4")
                print(f"  Preview: {mp4}")
            except RuntimeError as e:
                print(f"  (bỏ qua preview) {e}")
    return code


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="capcut_templates",
                                description="Tạo template CapCut chuẩn từ file JSON")
    sub = p.add_subparsers(dest="cmd", required=True)

    n = sub.add_parser("new", help="tạo file mô tả template mẫu")
    n.add_argument("file")
    n.add_argument("--name")
    n.add_argument("--force", action="store_true")
    n.set_defaults(fn=cmd_new)

    v = sub.add_parser("validate", help="kiểm tra template theo chuẩn")
    v.add_argument("files", nargs="+")
    v.set_defaults(fn=cmd_validate)

    b = sub.add_parser("build", help="xuất draft CapCut + video preview")
    b.add_argument("files", nargs="+")
    b.add_argument("--out", help="thư mục xuất (mặc định ./output)")
    b.add_argument("--install", action="store_true",
                   help="xuất thẳng vào thư mục draft của CapCut PC")
    b.add_argument("--no-preview", action="store_true")
    b.set_defaults(fn=cmd_build)

    a = p.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    return a.fn(a)
