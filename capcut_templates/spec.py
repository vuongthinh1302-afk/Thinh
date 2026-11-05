"""Đọc file mô tả template (JSON) và kiểm tra theo chuẩn template CapCut."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

# Khung hình thường dùng cho template CapCut.
ASPECT_PRESETS = {
    "9:16": (1080, 1920),  # TikTok / Reels / Shorts - phổ biến nhất
    "16:9": (1920, 1080),  # YouTube
    "1:1": (1080, 1080),
    "4:5": (1080, 1350),  # Instagram feed
}

# Quy tắc "chuẩn" khi đăng template lên CapCut.
RULES = {
    "min_duration": 3.0,  # giây
    "max_duration": 180.0,
    "min_slots": 1,
    "max_slots": 30,
    "min_slot_duration": 0.1,
    "allowed_fps": (24, 25, 30, 50, 60),
    "max_text_len": 80,
}

TRANSITIONS = ("none", "fade", "slide_left", "slide_up", "zoom", "flash")
ANIMATIONS = ("none", "fade_in", "zoom_in", "slide_up", "typewriter")


class SpecError(ValueError):
    """Lỗi khi file mô tả template sai."""


@dataclass
class Slot:
    """Một ô media người dùng sẽ thay ảnh/video của mình vào."""

    duration: float
    kind: str = "photo"  # photo | video
    label: str = ""
    transition: str = "none"  # chuyển cảnh vào slot tiếp theo
    zoom: float = 1.0  # hiệu ứng Ken Burns: 1.0 = không zoom


@dataclass
class TextLayer:
    text: str
    start: float
    duration: float
    size: int = 12  # cỡ chữ theo đơn vị CapCut (khoảng 5-30)
    color: str = "#FFFFFF"
    y: float = 0.0  # vị trí dọc: -1 (trên cùng) .. 1 (dưới cùng)
    animation: str = "none"
    editable: bool = True  # cho người dùng sửa chữ khi dùng template


@dataclass
class Music:
    path: str = ""
    start: float = 0.0
    volume: float = 1.0
    beats: list[float] = field(default_factory=list)  # mốc beat (giây)


@dataclass
class TemplateSpec:
    name: str
    aspect: str = "9:16"
    fps: int = 30
    background: str = "#000000"
    slots: list[Slot] = field(default_factory=list)
    texts: list[TextLayer] = field(default_factory=list)
    music: Music | None = None
    description: str = ""
    tags: list[str] = field(default_factory=list)

    @property
    def size(self) -> tuple[int, int]:
        return ASPECT_PRESETS[self.aspect]

    @property
    def duration(self) -> float:
        return round(sum(s.duration for s in self.slots), 6)

    def slot_starts(self) -> list[float]:
        starts, t = [], 0.0
        for s in self.slots:
            starts.append(round(t, 6))
            t += s.duration
        return starts


def _build(cls, data: dict, where: str):
    known = set(cls.__dataclass_fields__)
    extra = set(data) - known
    if extra:
        raise SpecError(f"{where}: trường không hợp lệ {sorted(extra)}")
    try:
        return cls(**data)
    except TypeError as e:
        raise SpecError(f"{where}: {e}") from None


def from_dict(data: dict) -> TemplateSpec:
    data = dict(data)
    slots_raw = data.pop("slots", [])
    # Cho phép viết tắt: "slots_from_beats": true -> tự chia slot theo beat nhạc.
    from_beats = data.pop("slots_from_beats", False)
    texts = [_build(TextLayer, t, f"texts[{i}]") for i, t in enumerate(data.pop("texts", []))]
    music_raw = data.pop("music", None)
    music = _build(Music, music_raw, "music") if music_raw else None
    slots = [_build(Slot, s, f"slots[{i}]") for i, s in enumerate(slots_raw)]
    if from_beats:
        if not music or len(music.beats) < 2:
            raise SpecError("slots_from_beats cần music.beats có ít nhất 2 mốc")
        slots = slots_from_beats(music.beats, slots)
    spec = _build(TemplateSpec, {**data, "slots": slots, "texts": texts, "music": music}, "template")
    return spec


def slots_from_beats(beats: list[float], base: list[Slot]) -> list[Slot]:
    """Tạo slot khớp beat: mỗi khoảng giữa 2 beat là 1 slot."""
    beats = sorted(beats)
    out = []
    for i in range(len(beats) - 1):
        tpl = base[i % len(base)] if base else Slot(duration=0)
        out.append(Slot(
            duration=round(beats[i + 1] - beats[i], 6),
            kind=tpl.kind,
            label=tpl.label or f"Ảnh {i + 1}",
            transition=tpl.transition,
            zoom=tpl.zoom,
        ))
    return out


def load(path: str | Path) -> TemplateSpec:
    path = Path(path)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise SpecError(f"{path}: JSON sai cú pháp ({e})") from None
    return from_dict(data)


def _is_color(c: str) -> bool:
    return isinstance(c, str) and len(c) == 7 and c[0] == "#" and all(
        ch in "0123456789abcdefABCDEF" for ch in c[1:])


def validate(spec: TemplateSpec) -> tuple[list[str], list[str]]:
    """Trả về (lỗi, cảnh báo). Có lỗi thì không build."""
    errors, warnings = [], []
    r = RULES

    if not spec.name.strip():
        errors.append("Thiếu tên template (name)")
    if spec.aspect not in ASPECT_PRESETS:
        errors.append(f"aspect '{spec.aspect}' không hỗ trợ, chọn: {list(ASPECT_PRESETS)}")
    elif spec.aspect != "9:16":
        warnings.append("Template CapCut phổ biến nhất là 9:16 (dọc)")
    if spec.fps not in r["allowed_fps"]:
        errors.append(f"fps {spec.fps} không chuẩn, chọn: {r['allowed_fps']}")
    if not _is_color(spec.background):
        errors.append(f"background '{spec.background}' phải dạng #RRGGBB")

    n = len(spec.slots)
    if not r["min_slots"] <= n <= r["max_slots"]:
        errors.append(f"Số slot phải từ {r['min_slots']} đến {r['max_slots']} (đang có {n})")
    for i, s in enumerate(spec.slots):
        if s.duration < r["min_slot_duration"]:
            errors.append(f"slots[{i}] quá ngắn ({s.duration}s)")
        if s.kind not in ("photo", "video"):
            errors.append(f"slots[{i}].kind phải là photo hoặc video")
        if s.transition not in TRANSITIONS:
            errors.append(f"slots[{i}].transition '{s.transition}' không hỗ trợ, chọn: {TRANSITIONS}")
        if not 1.0 <= s.zoom <= 2.0:
            errors.append(f"slots[{i}].zoom phải trong khoảng 1.0-2.0")

    d = spec.duration
    if n and not r["min_duration"] <= d <= r["max_duration"]:
        errors.append(f"Tổng thời lượng {d:.2f}s phải trong {r['min_duration']}-{r['max_duration']}s")
    elif d > 60:
        warnings.append("Template trên 60s thường ít người dùng; nên 7-30s")

    for i, t in enumerate(spec.texts):
        if not t.text.strip():
            errors.append(f"texts[{i}] trống")
        if len(t.text) > r["max_text_len"]:
            warnings.append(f"texts[{i}] dài hơn {r['max_text_len']} ký tự, dễ tràn khung")
        if t.start < 0 or t.duration <= 0:
            errors.append(f"texts[{i}] start/duration không hợp lệ")
        elif t.start + t.duration > d + 1e-6:
            errors.append(f"texts[{i}] kéo dài quá hết video ({t.start + t.duration:.2f}s > {d:.2f}s)")
        if not -1 <= t.y <= 1:
            errors.append(f"texts[{i}].y phải trong khoảng -1..1")
        if not _is_color(t.color):
            errors.append(f"texts[{i}].color phải dạng #RRGGBB")
        if t.animation not in ANIMATIONS:
            errors.append(f"texts[{i}].animation chọn: {ANIMATIONS}")
        if abs(t.y) > 0.8:
            warnings.append(f"texts[{i}] sát mép, có thể bị UI TikTok/Reels che (nên |y| <= 0.7)")

    if spec.music:
        m = spec.music
        if m.path and not Path(m.path).exists():
            warnings.append(f"Không tìm thấy file nhạc {m.path} (draft vẫn tạo, cần gắn lại nhạc)")
        if not 0 <= m.volume <= 2:
            errors.append("music.volume phải trong 0-2")
        if m.beats:
            starts = spec.slot_starts()
            off = [b for b in m.beats if b <= d and min(abs(b - s) for s in starts + [d]) > 0.05]
            if off:
                warnings.append(f"{len(off)} beat không trùng điểm cắt slot (lệch > 50ms)")
    else:
        warnings.append("Chưa có nhạc; template có nhạc khớp beat được dùng nhiều hơn")

    if not spec.description:
        warnings.append("Nên có description để người dùng dễ tìm template")
    return errors, warnings
