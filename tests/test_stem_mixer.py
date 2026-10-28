from pathlib import Path

import numpy as np
import soundfile as sf

import stem_mixer as sm

SR = 44100


def tone(freq, n=SR, amp=0.25):
    t = np.arange(n) / SR
    return (amp * np.sin(2 * np.pi * freq * t)).astype(np.float32)


def make_stems(tmp: Path) -> Path:
    d = tmp / "song"
    d.mkdir()
    for name, f in {"Song (Vocals)": 440, "song_drums": 100, "song-bass": 55, "other": 880}.items():
        sf.write(str(d / f"{name}.wav"), np.stack([tone(f), tone(f)], 1), SR)
    return d


def peak_at(audio, freq):
    spec = np.abs(np.fft.rfft(audio[:, 0]))
    freqs = np.fft.rfftfreq(len(audio), 1 / SR)
    return spec[np.argmin(np.abs(freqs - freq))]


def test_canonical_names():
    assert sm.canonical_name(Path("Song (Vocals).wav")) == "vocals"
    assert sm.canonical_name(Path("track_no_vocals.wav")) == "instrumental"
    assert sm.canonical_name(Path("my-song-Drums.flac")) == "drums"
    assert sm.canonical_name(Path("keys.wav")) == "piano"


def test_karaoke_preset_mutes_vocals(tmp_path):
    stems = sm.discover(make_stems(tmp_path))
    sm.apply_preset(stems, "karaoke")
    audio, sr = sm.mix(sm.MixSettings(stems=stems))
    assert sr == SR
    assert peak_at(audio, 440) < 1e-3 * peak_at(audio, 880)
    assert peak_at(audio, 55) > 1


def test_acapella_preset_keeps_only_vocals(tmp_path):
    stems = sm.discover(make_stems(tmp_path))
    sm.apply_preset(stems, "acapella")
    audio, _ = sm.mix(sm.MixSettings(stems=stems))
    assert peak_at(audio, 100) < 1e-3 * peak_at(audio, 440)


def test_limiter_respects_ceiling(tmp_path):
    stems = sm.discover(make_stems(tmp_path))
    for s in stems:
        s.gain_db = 12.0
    audio, _ = sm.mix(sm.MixSettings(stems=stems, ceiling_db=-1.0))
    assert np.max(np.abs(audio)) <= sm.db_to_amp(-1.0) + 1e-6


def test_pan_law_center_is_unity():
    assert np.allclose(sm.pan_gains(0.0), (1.0, 1.0))
    left, right = sm.pan_gains(-1.0)
    assert right < 1e-6 and left > 1.4


def test_cli_writes_file(tmp_path):
    d = make_stems(tmp_path)
    out = tmp_path / "out.wav"
    assert sm.main([str(d), "-p", "drumless", "--gain", "vocals=-6", "-o", str(out)]) == 0
    data, sr = sf.read(str(out))
    assert sr == SR and data.shape == (SR, 2)
