"""Xuất thư mục draft (dự án) mà CapCut PC mở được.

Cấu trúc tạo ra:
    <tên>/
        draft_content.json     timeline: track video, chữ, nhạc
        draft_meta_info.json   thông tin dự án hiển thị trong CapCut
        placeholders/          ảnh giữ chỗ cho từng slot
        template_info.json     mô tả slot/chữ thay được (để đăng template)

Lưu ý: định dạng draft không được CapCut công bố. File này dựa trên cấu trúc
draft của CapCut PC bản cũ (draft_content.json chưa mã hoá). Bản CapCut mới
có thể mã hoá draft và không mở draft tạo bên ngoài.
"""

from __future__ import annotations

import json
import shutil
import struct
import subprocess
import time
import uuid
import zlib
from pathlib import Path

from .spec import TemplateSpec

US = 1_000_000  # CapCut dùng micro giây

# Hiệu ứng CapCut tương ứng (tên hiển thị trong CapCut; người dùng kiểm tra lại).
TRANSITION_NAMES = {
    "fade": "Mix", "slide_left": "Pull in", "slide_up": "Slide up",
    "zoom": "Zoom in", "flash": "Flash",
}
ANIMATION_NAMES = {
    "fade_in": "Fade in", "zoom_in": "Zoom in", "slide_up": "Slide up",
    "typewriter": "Typewriter",
}

SLOT_COLORS = ["#E4572E", "#17BEBB", "#FFC914", "#2E282A", "#76B041", "#5B5F97"]


def _id() -> str:
    return str(uuid.uuid4()).upper()


def _us(sec: float) -> int:
    return int(round(sec * US))


def _rgb(hex_color: str) -> list[float]:
    h = hex_color.lstrip("#")
    return [round(int(h[i:i + 2], 16) / 255, 4) for i in (0, 2, 4)]


# ---------- ảnh giữ chỗ ----------

def _png(path: Path, w: int, h: int, color: str) -> None:
    """Ghi PNG một màu, không cần thư viện ngoài."""
    r, g, b = (int(color[i:i + 2], 16) for i in (1, 3, 5))
    row = b"\x00" + bytes([r, g, b]) * w
    raw = zlib.compress(row * h, 9)

    def chunk(tag: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data))

    path.write_bytes(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
                     + chunk(b"IDAT", raw) + chunk(b"IEND", b""))


def make_placeholder(path: Path, w: int, h: int, color: str, label: str) -> None:
    """Ảnh màu có ghi nhãn slot (dùng ffmpeg nếu có, không thì ảnh trơn)."""
    if shutil.which("ffmpeg"):
        safe = label.replace("\\", "").replace(":", "\\:").replace("'", "")
        cmd = ["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi",
               "-i", f"color=c={color}:s={w}x{h}",
               "-vf", f"drawtext=text='{safe}':fontcolor=white:fontsize={w // 12}"
                      ":x=(w-tw)/2:y=(h-th)/2:box=1:boxcolor=black@0.4:boxborderw=20",
               "-frames:v", "1", str(path)]
        if subprocess.run(cmd, capture_output=True).returncode == 0:
            return
    _png(path, w, h, color)


# ---------- các khối JSON của draft ----------

def _segment(material_id: str, start: float, dur: float, refs: list[str], render_index: int,
             clip: dict | None = None, src_start: float = 0.0, volume: float = 1.0) -> dict:
    seg = {
        "id": _id(),
        "material_id": material_id,
        "source_timerange": {"start": _us(src_start), "duration": _us(dur)},
        "target_timerange": {"start": _us(start), "duration": _us(dur)},
        "speed": 1.0,
        "volume": volume,
        "visible": True,
        "reverse": False,
        "extra_material_refs": refs,
        "render_index": render_index,
        "track_render_index": 0,
        "common_keyframes": [],
        "keyframe_refs": [],
        "enable_adjust": True,
        "enable_color_curves": True,
        "enable_lut": True,
        "uniform_scale": {"on": True, "value": 1.0},
    }
    if clip is not None:
        seg["clip"] = clip
    return seg


def _clip(scale: float = 1.0, y: float = 0.0) -> dict:
    return {
        "alpha": 1.0,
        "flip": {"horizontal": False, "vertical": False},
        "rotation": 0.0,
        "scale": {"x": scale, "y": scale},
        "transform": {"x": 0.0, "y": -y},  # CapCut: y dương là đi lên
    }


def _track(kind: str, segments: list[dict]) -> dict:
    return {"id": _id(), "type": kind, "attribute": 0, "flag": 0, "is_default_name": True,
            "name": "", "segments": segments}


def _speed() -> dict:
    return {"id": _id(), "type": "speed", "mode": 0, "speed": 1.0, "curve_speed": None}


def _text_content(t) -> str:
    return json.dumps({
        "text": t.text,
        "styles": [{
            "fill": {"alpha": 1.0, "content": {"render_type": "solid",
                                                "solid": {"alpha": 1.0, "color": _rgb(t.color)}}},
            "range": [0, len(t.text)],
            "size": float(t.size),
            "bold": True,
            "useLetterColor": True,
        }],
    }, ensure_ascii=False)


def build_content(spec: TemplateSpec, placeholder_paths: list[Path]) -> tuple[dict, dict]:
    """Trả về (draft_content, template_info)."""
    w, h = spec.size
    mats = {k: [] for k in (
        "videos", "audios", "texts", "speeds", "canvases", "transitions",
        "material_animations", "sound_channel_mappings", "placeholders", "beats",
        "effects", "stickers", "audio_effects", "audio_fades", "filters")}
    tracks = []
    info = {"name": spec.name, "aspect": spec.aspect, "duration": spec.duration,
            "replaceable_slots": [], "editable_texts": []}

    # Track video: mỗi slot là 1 ảnh giữ chỗ.
    canvas_id = _id()
    mats["canvases"].append({"id": canvas_id, "type": "canvas_color", "color": spec.background,
                             "blur": 0.0, "image": ""})
    video_segs = []
    for i, (slot, start, ph) in enumerate(zip(spec.slots, spec.slot_starts(), placeholder_paths)):
        mid, sp = _id(), _speed()
        mats["speeds"].append(sp)
        mats["videos"].append({
            "id": mid, "type": "photo", "path": str(ph.resolve()), "material_name": ph.name,
            "duration": _us(10800), "width": w, "height": h, "category_name": "local",
            "has_audio": False, "crop": {"upper_left_x": 0.0, "upper_left_y": 0.0,
                                         "upper_right_x": 1.0, "upper_right_y": 0.0,
                                         "lower_left_x": 0.0, "lower_left_y": 1.0,
                                         "lower_right_x": 1.0, "lower_right_y": 1.0},
            "crop_ratio": "free", "crop_scale": 1.0,
        })
        refs = [sp["id"], canvas_id]
        if slot.transition != "none" and i < len(spec.slots) - 1:
            tid = _id()
            mats["transitions"].append({
                "id": tid, "type": "transition", "name": TRANSITION_NAMES[slot.transition],
                "duration": _us(min(0.5, slot.duration / 2)), "is_overlap": True,
                "effect_id": "", "resource_id": "", "path": "", "category_name": "",
            })
            refs.append(tid)
        seg = _segment(mid, start, slot.duration, refs, 0, _clip())
        if slot.zoom > 1.0:  # Ken Burns bằng keyframe scale
            seg["common_keyframes"] = [{
                "id": _id(), "property_type": "KFTypeScaleX", "keyframe_list": [
                    {"id": _id(), "time_offset": 0, "values": [1.0], "curveType": "Line"},
                    {"id": _id(), "time_offset": _us(slot.duration), "values": [slot.zoom],
                     "curveType": "Line"}]}]
        video_segs.append(seg)
        info["replaceable_slots"].append({
            "index": i + 1, "label": slot.label or f"Slot {i + 1}", "kind": slot.kind,
            "start": start, "duration": slot.duration, "transition": slot.transition,
        })
    tracks.append(_track("video", video_segs))

    # Track chữ.
    if spec.texts:
        text_segs = []
        for i, t in enumerate(spec.texts):
            mid = _id()
            mats["texts"].append({
                "id": mid, "type": "text", "content": _text_content(t),
                "alignment": 1, "typesetting": 0, "font_size": float(t.size),
                "text_color": t.color, "check_flag": 7, "global_alpha": 1.0,
                "line_max_width": 0.82, "words": {"start_time": [], "end_time": [], "text": []},
            })
            refs = []
            if t.animation != "none":
                aid = _id()
                mats["material_animations"].append({
                    "id": aid, "type": "sticker_animation", "multi_language_current": "none",
                    "animations": [{"name": ANIMATION_NAMES[t.animation], "type": "in",
                                    "duration": _us(min(0.5, t.duration / 2)),
                                    "start": 0, "id": "", "resource_id": "", "path": "",
                                    "platform": "all", "category_name": ""}],
                })
                refs.append(aid)
            text_segs.append(_segment(mid, t.start, t.duration, refs, 14000 + i, _clip(y=t.y)))
            if t.editable:
                info["editable_texts"].append({"index": i + 1, "default": t.text,
                                               "start": t.start, "duration": t.duration})
        tracks.append(_track("text", text_segs))

    # Track nhạc + beat.
    if spec.music:
        m = spec.music
        if m.path:
            mid = _id()
            mats["audios"].append({
                "id": mid, "type": "extract_music", "name": Path(m.path).name,
                "path": str(Path(m.path).resolve()), "duration": _us(m.start + spec.duration),
                "category_name": "local", "check_flag": 1,
            })
            tracks.append(_track("audio", [_segment(mid, 0, spec.duration, [], 0,
                                                    src_start=m.start, volume=m.volume)]))
        if m.beats:
            mats["beats"].append({
                "id": _id(), "type": "beats", "mode": 404, "enable_ai_beats": False,
                "user_beats": [_us(b) for b in m.beats],
                "ai_beats": {"beat_speed_infos": [], "beats_path": "", "melody_path": "",
                             "melody_percents": [0.0], "beats_url": "", "melody_url": ""},
                "gear": 404, "user_delete_ai_beats": None,
            })
        info["beats"] = m.beats

    content = {
        "id": _id(),
        "name": spec.name,
        "canvas_config": {"width": w, "height": h, "ratio": "original"},
        "config": {"adjust_max_index": 1, "attachment_info": [], "combination_max_index": 1,
                   "export_range": None, "extract_audio_last_index": 1,
                   "lyrics_recognition_id": "", "lyrics_sync": True, "lyrics_taskinfo": [],
                   "maintrack_adsorb": True, "material_save_mode": 0,
                   "original_sound_last_index": 1, "record_audio_last_index": 1,
                   "sticker_max_index": 1, "subtitle_recognition_id": "", "subtitle_sync": True,
                   "subtitle_taskinfo": [], "system_font_list": [], "video_mute": False,
                   "zoom_info_params": None},
        "color_space": 0,
        "cover": None,
        "create_time": 0,
        "duration": _us(spec.duration),
        "extra_info": None,
        "fps": float(spec.fps),
        "free_render_index_mode_on": False,
        "group_container": None,
        "keyframe_graph_list": [],
        "keyframes": {"adjusts": [], "audios": [], "effects": [], "filters": [],
                      "handwrites": [], "stickers": [], "texts": [], "videos": []},
        "last_modified_platform": {"app_id": 359289, "app_source": "cc", "app_version": "4.0.0",
                                   "os": "windows"},
        "platform": {"app_id": 359289, "app_source": "cc", "app_version": "4.0.0",
                     "os": "windows"},
        "materials": mats,
        "mutable_config": None,
        "new_version": "110.0.0",
        "relationships": [],
        "render_index_track_mode_on": False,
        "retouch_cover": None,
        "source": "default",
        "static_cover_image_path": "",
        "tracks": tracks,
        "update_time": 0,
        "version": 360000,
    }
    return content, info


def build_meta(spec: TemplateSpec, folder: Path, root: Path) -> dict:
    now_us = int(time.time() * US)
    return {
        "draft_id": _id(),
        "draft_name": folder.name,
        "draft_fold_path": str(folder.resolve()),
        "draft_root_path": str(root.resolve()),
        "draft_cover": "",
        "draft_removable_storage_device": "",
        "draft_is_article_video_draft": False,
        "draft_materials": [{"type": t, "value": []} for t in (0, 1, 2, 3, 6, 7, 8)],
        "draft_segment_extra_info": [],
        "draft_timeline_materials_size_": 0,
        "tm_draft_create": now_us,
        "tm_draft_modified": now_us,
        "tm_duration": _us(spec.duration),
    }


def safe_name(name: str) -> str:
    keep = "".join(c if c.isalnum() or c in " -_" else "_" for c in name).strip()
    return keep or "template"


def write_draft(spec: TemplateSpec, out_root: Path) -> Path:
    """Tạo thư mục draft trong out_root, trả về đường dẫn thư mục."""
    folder = out_root / safe_name(spec.name)
    ph_dir = folder / "placeholders"
    ph_dir.mkdir(parents=True, exist_ok=True)
    w, h = spec.size
    paths = []
    for i, slot in enumerate(spec.slots):
        p = ph_dir / f"slot_{i + 1:02d}.png"
        make_placeholder(p, w, h, SLOT_COLORS[i % len(SLOT_COLORS)],
                         f"{i + 1}. {slot.label or slot.kind} ({slot.duration:g}s)")
        paths.append(p)
    content, info = build_content(spec, paths)
    dump = lambda obj: json.dumps(obj, ensure_ascii=False, indent=2)  # noqa: E731
    (folder / "draft_content.json").write_text(dump(content), encoding="utf-8")
    (folder / "draft_meta_info.json").write_text(dump(build_meta(spec, folder, out_root)),
                                                 encoding="utf-8")
    info.update(description=spec.description, tags=spec.tags)
    (folder / "template_info.json").write_text(dump(info), encoding="utf-8")
    return folder
