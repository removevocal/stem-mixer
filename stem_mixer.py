#!/usr/bin/env python3
"""
stem-mixer
==========

Recombine separated stems (vocals, drums, bass, other, ...) into a new mix.

You already have stems from a source-separation tool. Now you want a karaoke
version, a "drumless" practice track, a bass-only reference, or the full song
with the vocals turned down 6 dB. This script does that from the command line:

* per-stem gain in dB, mute, solo and pan;
* built-in presets (karaoke, acapella, drumless, bassless, ...);
* length/sample-rate checks so stems line up sample-accurately;
* optional integrated-loudness (LUFS) normalisation with a true-peak-safe limiter;
* WAV/FLAC output, plus MP3 if ffmpeg is installed.
"""

from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import soundfile as sf

__version__ = "1.0.0"

AUDIO_EXT = {".wav", ".flac", ".ogg", ".aiff", ".aif"}

# Stem names are matched case-insensitively against these aliases.
ALIASES = {
    "vocals": {"vocals", "vocal", "voice", "acapella", "lead"},
    "drums": {"drums", "drum", "percussion"},
    "bass": {"bass"},
    "piano": {"piano", "keys"},
    "guitar": {"guitar", "guitars"},
    "other": {"other", "others", "rest", "accompaniment"},
    "instrumental": {"instrumental", "instrum", "no_vocals", "music"},
}

PRESETS: dict[str, dict[str, float | None]] = {
    # value = gain in dB, None = muted. Stems not listed keep 0 dB.
    "full": {},
    "karaoke": {"vocals": None},
    "guide-vocal": {"vocals": -12.0},     # karaoke with a quiet guide vocal
    "acapella": {"*": None, "vocals": 0.0},
    "drumless": {"drums": None},
    "bassless": {"bass": None},
    "drums-only": {"*": None, "drums": 0.0},
    "bass-only": {"*": None, "bass": 0.0},
}


@dataclass
class Stem:
    name: str
    path: Path
    gain_db: float | None = 0.0   # None = muted
    pan: float = 0.0              # -1 (left) .. +1 (right)


@dataclass
class MixSettings:
    target_lufs: float | None = None
    ceiling_db: float = -1.0
    stems: list[Stem] = field(default_factory=list)


def canonical_name(stem_file: Path) -> str:
    """Map a file name like 'Song (Vocals).wav' or 'song_no_vocals.wav' to a stem name."""
    base = stem_file.stem.lower()
    tokens = [t for t in re.split(r"[^a-z0-9]+", base) if t]
    joined = "_".join(tokens)
    if "no_vocals" in joined or "novocals" in joined or "without_vocals" in joined:
        return "instrumental"
    for token in reversed(tokens):
        for canon, names in ALIASES.items():
            if token in names:
                return canon
    return tokens[-1] if tokens else base


def discover(folder: Path) -> list[Stem]:
    files = sorted(p for p in folder.iterdir() if p.suffix.lower() in AUDIO_EXT)
    if not files:
        raise SystemExit(f"No audio stems found in {folder}")
    return [Stem(canonical_name(p), p) for p in files]


def apply_preset(stems: list[Stem], preset: str) -> None:
    if preset not in PRESETS:
        raise SystemExit(f"Unknown preset {preset!r}. Choose from: {', '.join(PRESETS)}")
    rules = PRESETS[preset]
    default = rules.get("*", 0.0)
    for s in stems:
        s.gain_db = rules.get(s.name, default)


def db_to_amp(db: float) -> float:
    return float(10.0 ** (db / 20.0))


def pan_gains(pan: float) -> tuple[float, float]:
    """Constant-power pan law. pan=0 -> (1, 1) so centered stems are untouched."""
    pan = float(np.clip(pan, -1.0, 1.0))
    angle = (pan + 1.0) * np.pi / 4.0
    return float(np.cos(angle) * np.sqrt(2)), float(np.sin(angle) * np.sqrt(2))


def load_stem(path: Path) -> tuple[np.ndarray, int]:
    audio, sr = sf.read(str(path), always_2d=True, dtype="float32")
    if audio.shape[1] == 1:
        audio = np.repeat(audio, 2, axis=1)
    return audio[:, :2], sr


def mix(settings: MixSettings) -> tuple[np.ndarray, int]:
    active = [s for s in settings.stems if s.gain_db is not None]
    if not active:
        raise SystemExit("Every stem is muted -- nothing to mix.")
    loaded = [(s, *load_stem(s.path)) for s in active]
    rates = {sr for _, _, sr in loaded}
    if len(rates) != 1:
        raise SystemExit(f"Stems have different sample rates: {sorted(rates)}. Resample them first.")
    sr = rates.pop()
    length = max(a.shape[0] for _, a, _ in loaded)
    out = np.zeros((length, 2), dtype=np.float64)
    for stem, audio, _ in loaded:
        gl, gr = pan_gains(stem.pan)
        g = db_to_amp(stem.gain_db)
        out[: audio.shape[0], 0] += audio[:, 0] * g * gl
        out[: audio.shape[0], 1] += audio[:, 1] * g * gr

    if settings.target_lufs is not None:
        out = loudness_normalize(out, sr, settings.target_lufs)
    out = limit(out, settings.ceiling_db)
    return out.astype(np.float32), sr


def loudness_normalize(audio: np.ndarray, sr: int, target_lufs: float) -> np.ndarray:
    try:
        import pyloudnorm as pyln
    except ImportError as exc:  # pragma: no cover - optional dependency
        raise SystemExit("LUFS normalisation needs pyloudnorm: pip install pyloudnorm") from exc
    meter = pyln.Meter(sr)
    loudness = meter.integrated_loudness(audio)
    if not np.isfinite(loudness):
        return audio
    return audio * db_to_amp(target_lufs - loudness)


def limit(audio: np.ndarray, ceiling_db: float) -> np.ndarray:
    """Simple safety stage: scale down if the peak exceeds the ceiling (no pumping, no distortion)."""
    ceiling = db_to_amp(ceiling_db)
    peak = float(np.max(np.abs(audio))) if audio.size else 0.0
    if peak > ceiling:
        audio = audio * (ceiling / peak)
    return audio


def write(audio: np.ndarray, sr: int, dst: Path, mp3_bitrate: str = "320k") -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    ext = dst.suffix.lower()
    if ext in {".wav", ".flac"}:
        sf.write(str(dst), audio, sr, subtype="PCM_24")
        return
    if ext == ".mp3":
        ffmpeg = shutil.which("ffmpeg")
        if not ffmpeg:
            raise SystemExit("MP3 export needs ffmpeg on your PATH (or choose .wav/.flac).")
        with tempfile.TemporaryDirectory() as tmp:
            wav = Path(tmp) / "mix.wav"
            sf.write(str(wav), audio, sr, subtype="PCM_24")
            subprocess.run([ffmpeg, "-y", "-loglevel", "error", "-i", str(wav),
                            "-codec:a", "libmp3lame", "-b:a", mp3_bitrate, str(dst)], check=True)
        return
    raise SystemExit(f"Unsupported output format: {ext}")


def _parse_kv(values: list[str], kind: str) -> dict[str, float]:
    result = {}
    for item in values or []:
        if "=" not in item:
            raise SystemExit(f"--{kind} expects name=value, got {item!r}")
        k, v = item.split("=", 1)
        result[k.strip().lower()] = float(v)
    return result


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="stem_mixer", description="Remix separated stems: karaoke, practice tracks, custom balances.")
    p.add_argument("stems_dir", type=Path, help="folder containing the stem files")
    p.add_argument("-o", "--output", type=Path, help="output file (.wav, .flac or .mp3)")
    p.add_argument("-p", "--preset", default="full", help=f"one of: {', '.join(PRESETS)} (default: full)")
    p.add_argument("--gain", action="append", metavar="STEM=DB", help="set gain, e.g. --gain vocals=-6")
    p.add_argument("--pan", action="append", metavar="STEM=POS", help="pan -1..1, e.g. --pan guitar=-0.5")
    p.add_argument("--mute", action="append", default=[], metavar="STEM", help="mute a stem (repeatable)")
    p.add_argument("--solo", action="append", default=[], metavar="STEM", help="only play these stems (repeatable)")
    p.add_argument("--lufs", type=float, default=None, help="normalise to this integrated loudness, e.g. -14")
    p.add_argument("--ceiling", type=float, default=-1.0, help="peak ceiling in dBFS (default: -1)")
    p.add_argument("--list", action="store_true", help="list detected stems and exit")
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    stems = discover(args.stems_dir)
    if args.list:
        for s in stems:
            print(f"{s.name:<13} {s.path.name}")
        return 0

    apply_preset(stems, args.preset)
    gains, pans = _parse_kv(args.gain, "gain"), _parse_kv(args.pan, "pan")
    mute = {m.lower() for m in args.mute}
    solo = {s.lower() for s in args.solo}
    names = {s.name for s in stems}
    for wanted in set(gains) | set(pans) | mute | solo:
        if wanted not in names:
            print(f"warning: no stem called {wanted!r} (found: {', '.join(sorted(names))})", file=sys.stderr)
    for s in stems:
        if s.name in gains:
            s.gain_db = gains[s.name]
        if s.name in pans:
            s.pan = pans[s.name]
        if s.name in mute or (solo and s.name not in solo):
            s.gain_db = None

    audio, sr = mix(MixSettings(target_lufs=args.lufs, ceiling_db=args.ceiling, stems=stems))
    dst = args.output or Path(f"{args.stems_dir.name}_{args.preset}.wav")
    write(audio, sr, dst)
    summary = ", ".join(f"{s.name}={'mute' if s.gain_db is None else f'{s.gain_db:+.1f}dB'}" for s in stems)
    print(f"{dst}  [{summary}]")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
