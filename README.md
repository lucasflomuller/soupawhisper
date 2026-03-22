# SoupaWhisper

A push-to-talk voice dictation tool for Wayland/Hyprland using [faster-whisper](https://github.com/SYSTRAN/faster-whisper). Press a key to record, press again to transcribe — text is copied to clipboard and typed into the active input.

Forked from [ksred/soupawhisper](https://github.com/ksred/soupawhisper) and reworked for Wayland with a daemon architecture.

## Requirements

- Arch Linux (or compatible) with Hyprland
- PipeWire (for `pw-record`)
- Python 3.10+
- Poetry

## Installation

```bash
git clone https://github.com/lucasflomuller/soupawhisper.git
cd soupawhisper
chmod +x install.sh
./install.sh
```

The installer will:
1. Install system dependencies (`wl-clipboard`, `wtype`, `libnotify`, `openbsd-netcat`)
2. Install Python dependencies via Poetry
3. Set up the config file at `~/.config/soupawhisper/config.ini`
4. Add Hyprland keybindings for F9 (dictation) and F8 (todo capture)
5. Optionally install as a systemd user service

## Usage

After installing, reload Hyprland and start the daemon:

```bash
hyprctl reload
systemctl --user start soupawhisper
```

- **F9** — Toggle voice dictation (press to start recording, press again to transcribe)
- **F8** — Toggle todo capture (transcribes and appends to `~/todo.md`)

The daemon keeps the Whisper model loaded in memory for near-instant transcription.

### Manual transcription

```bash
poetry run python dictate.py -f audio.wav       # Transcribe a file
poetry run python dictate.py -d 5               # Record for 5 seconds
poetry run python dictate.py --no-type           # Don't auto-type, just clipboard
```

### Service commands

```bash
systemctl --user start soupawhisper     # Start daemon
systemctl --user stop soupawhisper      # Stop daemon
systemctl --user restart soupawhisper   # Restart
systemctl --user status soupawhisper    # Status
journalctl --user -u soupawhisper -f    # View logs
```

## Configuration

Edit `~/.config/soupawhisper/config.ini`:

```ini
[whisper]
# Model size: tiny.en, base.en, small.en, medium.en, large-v3
model = base.en

# Device: cpu or cuda (cuda requires cuDNN)
device = cpu

# Compute type: int8 for CPU, float16 for GPU
compute_type = int8

[behavior]
# Type text into active input field
auto_type = true

# Show desktop notifications
notifications = true

[context]
# Optional: guide transcription with a prompt
# initial_prompt = Technical discussion about software development

# Optional: boost recognition of specific words
# hotwords = Hyprland, Wayland, SoupaWhisper
```

### GPU Support

For NVIDIA GPU acceleration, install cuDNN and update your config:

```ini
[whisper]
device = cuda
compute_type = float16
```

## Model Sizes

| Model | Size | Speed | Accuracy |
|-------|------|-------|----------|
| tiny.en | ~75MB | Fastest | Basic |
| base.en | ~150MB | Fast | Good |
| small.en | ~500MB | Medium | Better |
| medium.en | ~1.5GB | Slower | Great |
| large-v3 | ~3GB | Slowest | Best |

For dictation, `base.en` or `small.en` is usually the sweet spot.

## Troubleshooting

**No audio recording:**
```bash
# Check PipeWire is running
pw-cli info

# Test recording
pw-record --rate 16000 --channels 1 test.wav
# Ctrl+C to stop, then play back:
pw-play test.wav
```

**Daemon not responding:**
```bash
# Check if socket exists
ls $XDG_RUNTIME_DIR/soupawhisper/daemon.sock

# Restart the daemon
systemctl --user restart soupawhisper
```

**wtype not typing into window:**
Some applications (e.g., Electron apps) may not accept `wtype` input. The text is still copied to clipboard — use Ctrl+V as a fallback.

## Architecture

```
Hyprland keybinding (F9/F8)
  → wayland/soupawhisper-toggle (bash, manages recording via pw-record)
  → daemon socket (Unix domain socket)
  → soupawhisper-daemon.py (keeps Whisper model loaded, transcribes instantly)
  → wl-copy + wtype (clipboard + auto-type)
```

## License

MIT — see [LICENSE](LICENSE).
