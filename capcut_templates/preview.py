"""Dựng video xem trước (MP4) của template bằng ffmpeg.

Mỗi slot là một khung màu có nhãn, chữ hiện đúng thời điểm, có nhạc nếu có.
Dùng để kiểm tra nhịp/bố cục trước khi mở trong CapCut.
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path

from .draft import SLOT_COLORS
from .spec import TemplateSpec

FADE = 0.15


def _font() -> str | None:
    if shutil.which("fc-match"):
        r = subprocess.run(["fc-match", "-f", "%{file}", "sans:bold"], capture_output=True, text=True)
        if r.returncode == 0 and Path(r.stdout).exists():
            return r.stdout
    return None


def _esc(path: str) -> str:
    return path.replace("\\", "/").replace(":", "\\:").replace("'", "\\'")


def build_command(spec: TemplateSpec, out: Path, workdir: Path) -> list[str]:
    w, h = spec.size
    font = _font()
    font_opt = f"fontfile='{_esc(font)}':" if font else ""
    d = spec.duration
    inputs, filters, labels = [], [], []

    for i, (slot, start) in enumerate(zip(spec.slots, spec.slot_starts())):
        color = SLOT_COLORS[i % len(SLOT_COLORS)]
        inputs += ["-f", "lavfi", "-i", f"color=c={color}:s={w}x{h}:r={spec.fps}:d={slot.duration}"]
        lbl = workdir / f"slot{i}.txt"
        lbl.write_text(f"{i + 1}. {slot.label or slot.kind}", encoding="utf-8")
        chain = [f"drawtext={font_opt}textfile='{_esc(str(lbl))}':fontcolor=white@0.85"
                 f":fontsize={w // 14}:x=(w-tw)/2:y=(h-th)/2"]
        if slot.zoom > 1.0:
            z = slot.zoom - 1.0
            chain.append(f"scale=w='iw*(1+{z}*t/{slot.duration})':h=-2:eval=frame,"
                         f"crop={w}:{h}")
        prev = spec.slots[i - 1].transition if i > 0 else "none"
        if prev == "fade":
            chain.append(f"fade=t=in:st=0:d={FADE}")
        if slot.transition == "fade" and i < len(spec.slots) - 1:
            chain.append(f"fade=t=out:st={max(0, slot.duration - FADE)}:d={FADE}")
        chain.append("setsar=1")
        filters.append(f"[{i}:v]{','.join(chain)}[v{i}]")
        labels.append(f"[v{i}]")

    filters.append(f"{''.join(labels)}concat=n={len(labels)}:v=1:a=0[base]")
    cur = "base"

    # Hiệu ứng flash trắng ở điểm cắt.
    for i, (slot, start) in enumerate(zip(spec.slots, spec.slot_starts())):
        if slot.transition == "flash" and i < len(spec.slots) - 1:
            t = start + slot.duration
            filters.append(f"[{cur}]drawbox=x=0:y=0:w=iw:h=ih:color=white@0.8:t=fill"
                           f":enable='between(t,{t - 0.05:.3f},{t + 0.08:.3f})'[f{i}]")
            cur = f"f{i}"

    for i, t in enumerate(spec.texts):
        tf = workdir / f"text{i}.txt"
        tf.write_text(t.text, encoding="utf-8")
        size = int(t.size * w / 180)  # quy đổi gần đúng cỡ chữ CapCut -> pixel
        y_px = f"(h-th)/2+{t.y}*h/2"
        alpha = "1"
        if t.animation == "fade_in":
            alpha = f"min(1,(t-{t.start})/0.4)"
        filters.append(
            f"[{cur}]drawtext={font_opt}textfile='{_esc(str(tf))}':fontsize={size}"
            f":fontcolor={t.color}:alpha='{alpha}':borderw=3:bordercolor=black@0.6"
            f":x=(w-tw)/2:y={y_px}:enable='between(t,{t.start},{t.start + t.duration})'[t{i}]")
        cur = f"t{i}"

    # Vạch beat ở đáy khung.
    if spec.music and spec.music.beats:
        for i, b in enumerate(spec.music.beats):
            filters.append(f"[{cur}]drawbox=x=0:y=ih-24:w=iw:h=24:color=yellow@0.9:t=fill"
                           f":enable='between(t,{b:.3f},{b + 0.08:.3f})'[b{i}]")
            cur = f"b{i}"

    cmd = ["ffmpeg", "-y", "-loglevel", "error", *inputs]
    audio_map = []
    m = spec.music
    if m and m.path and Path(m.path).exists():
        idx = len(spec.slots)
        cmd += ["-ss", str(m.start), "-i", m.path]
        filters.append(f"[{idx}:a]volume={m.volume},atrim=0:{d},asetpts=PTS-STARTPTS[aout]")
        audio_map = ["-map", "[aout]", "-c:a", "aac", "-b:a", "192k"]
    cmd += ["-filter_complex", ";".join(filters), "-map", f"[{cur}]", *audio_map,
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-r", str(spec.fps), "-t", str(d),
            "-movflags", "+faststart", str(out)]
    return cmd


def render_preview(spec: TemplateSpec, out: Path) -> Path:
    if not shutil.which("ffmpeg"):
        raise RuntimeError("Cần cài ffmpeg để dựng preview (https://ffmpeg.org)")
    out.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        cmd = build_command(spec, out, Path(tmp))
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode != 0:
            raise RuntimeError(f"ffmpeg lỗi:\n{r.stderr[-2000:]}")
    return out
