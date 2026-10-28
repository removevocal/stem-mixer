# Stem Mixer

**Turn separated stems into karaoke tracks, practice tracks and custom remixes with one command.**

You've split a song into `vocals`, `drums`, `bass` and `other`. Now you want the song **without vocals**, **without drums** for practice, the **vocals 6 dB quieter**, or the bass panned left. `stem_mixer.py` recombines the stems sample-accurately, with gain, mute, solo, pan, presets and loudness normalisation, and exports WAV, FLAC or MP3.

![python](https://img.shields.io/badge/python-3.9%2B-blue) ![license](https://img.shields.io/badge/license-MIT-green) ![tests](https://img.shields.io/badge/tests-pytest-orange)

---

## Features

- **Presets**: `karaoke`, `guide-vocal`, `acapella`, `drumless`, `bassless`, `drums-only`, `bass-only`, `full`
- **Per-stem control**: `--gain vocals=-6`, `--mute drums`, `--solo bass`, `--pan guitar=-0.4`
- **Smart stem detection**: recognises `Song (Vocals).wav`, `track_no_vocals.wav`, `drums.flac`, `keys.wav` and similar names
- **Loudness**: optional integrated-LUFS normalisation (`--lufs -14`) plus a peak ceiling, so mixes never clip
- **Formats**: reads WAV, FLAC, OGG and AIFF, and writes WAV or FLAC (24-bit) or MP3 (via ffmpeg)
- **Safe**: refuses to mix stems with different sample rates instead of silently drifting out of sync

## Install

```bash
git clone https://github.com/removevocal/stem-mixer.git
cd stem-mixer
pip install -r requirements.txt   # numpy, soundfile, pyloudnorm (optional)
```

MP3 export needs [ffmpeg](https://ffmpeg.org/) on your `PATH`.

## Quick start

```
my-song/
├── vocals.wav
├── drums.wav
├── bass.wav
└── other.wav
```

```bash
# See what was detected
python stem_mixer.py my-song --list

# Karaoke version (vocals muted) -> my-song_karaoke.wav
python stem_mixer.py my-song -p karaoke

# Karaoke with a quiet guide vocal, normalised for streaming, as MP3
python stem_mixer.py my-song -p guide-vocal --lufs -14 -o my-song_guide.mp3

# Drummer practice track: everything except drums
python stem_mixer.py my-song -p drumless

# Custom balance: vocals -6 dB, bass +3 dB, guitar panned left
python stem_mixer.py my-song --gain vocals=-6 --gain bass=+3 --pan other=-0.4 -o custom.wav

# Only bass and drums (rhythm-section reference)
python stem_mixer.py my-song --solo bass --solo drums
```

## Presets

| Preset | What you get | Good for |
|---|---|---|
| `full` | All stems at 0 dB | Checking the separation |
| `karaoke` | Vocals muted | Karaoke, covers |
| `guide-vocal` | Vocals at -12 dB | Learning a song while singing along |
| `acapella` | Vocals only | Remixes, vocal analysis |
| `drumless` | Drums muted | Drum practice |
| `bassless` | Bass muted | Bass practice |
| `drums-only` / `bass-only` | One stem | Transcription |

Flags such as `--gain`, `--mute` and `--solo` are applied **after** the preset, so you can start from `karaoke` and tweak it from there.

## Where do the stems come from?

Any source-separation tool works, as long as it outputs one file per stem at the same sample rate. If you don't have stems yet, the [Remove Vocal online stem splitter](https://remove-vocal.com/) separates a song or a music video into **2, 4 or 6 tracks** in your browser. Upload MP3, WAV, FLAC, MP4, MOV and more, preview each stem, and download WAV files that drop straight into this tool.

```
Song or video ──► AI separation (2/4/6 stems) ──► stem_mixer.py ──► karaoke / practice / remix
```

## Library use

```python
from pathlib import Path
import stem_mixer as sm

stems = sm.discover(Path("my-song"))
sm.apply_preset(stems, "karaoke")
audio, sr = sm.mix(sm.MixSettings(stems=stems, target_lufs=-14))
sm.write(audio, sr, Path("karaoke.wav"))
```

## Tests

```bash
pip install pytest
pytest -q
```

## FAQ

**My stems have different lengths.** Shorter stems are padded with silence at the end, so they stay aligned from the start.

**Can I use mono stems?** Yes. Mono files are duplicated to both channels.

**Will this remove vocals from a normal song?** No. This tool mixes stems that have *already* been separated. To get stems from a finished song, use an AI vocal remover first.

## Related tools

- [`classic-vocal-remover`](https://github.com/removevocal/classic-vocal-remover): offline phase-cancellation karaoke maker
- [`video-audio-swap`](https://github.com/removevocal/video-audio-swap): extract a video's soundtrack and put the instrumental back in
- [Remove Vocal](https://remove-vocal.com/): AI vocal remover and stem splitter in the browser

## Support

Bug reports and feature requests are welcome as GitHub issues. For questions about separation quality or the hosted tool, email **[support@remove-vocal.com](mailto:support@remove-vocal.com)**.

## License

MIT. See [LICENSE](LICENSE). Please only remix audio you have the rights to use.

---

Maintained by the team behind [Remove Vocal](https://remove-vocal.com/), an AI vocal remover and stem splitter.
