#!/usr/bin/env python3
"""
SoupaWhisper - Voice dictation tool using faster-whisper.

Wayland version: Uses Hyprland keybindings (F9) for push-to-talk.
This script can also be used for manual single-file transcription.
"""

import argparse
import configparser
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from faster_whisper import WhisperModel

__version__ = "0.2.0"

CONFIG_PATH = Path.home() / ".config" / "soupawhisper" / "config.ini"


def load_config():
    config = configparser.ConfigParser()
    defaults = {
        "model": "base.en",
        "device": "cpu",
        "compute_type": "int8",
        "auto_type": "true",
        "notifications": "true",
    }

    if CONFIG_PATH.exists():
        config.read(CONFIG_PATH)

    return {
        "model": config.get("whisper", "model", fallback=defaults["model"]),
        "device": config.get("whisper", "device", fallback=defaults["device"]),
        "compute_type": config.get("whisper", "compute_type", fallback=defaults["compute_type"]),
        "auto_type": config.getboolean("behavior", "auto_type", fallback=True),
        "notifications": config.getboolean("behavior", "notifications", fallback=True),
    }


def notify(title, message, icon="dialog-information", timeout=2000):
    """Send a desktop notification."""
    subprocess.run(
        [
            "notify-send",
            "-a", "SoupaWhisper",
            "-i", icon,
            "-t", str(timeout),
            "-h", "string:x-canonical-private-synchronous:soupawhisper",
            title,
            message,
        ],
        capture_output=True,
    )


def check_dependencies():
    """Check that required Wayland commands are available."""
    missing = []

    for cmd, pkg in [("pw-record", "pipewire"), ("wl-copy", "wl-clipboard")]:
        if subprocess.run(["which", cmd], capture_output=True).returncode != 0:
            missing.append((cmd, pkg))

    config = load_config()
    if config["auto_type"]:
        if subprocess.run(["which", "wtype"], capture_output=True).returncode != 0:
            missing.append(("wtype", "wtype"))

    if missing:
        print("Missing dependencies:")
        for cmd, pkg in missing:
            print(f"  {cmd} - install with: sudo pacman -S {pkg}")
        sys.exit(1)


def transcribe_file(audio_file: str, config: dict) -> str:
    """Transcribe an audio file and return the text."""
    print(f"Loading model ({config['model']})...")
    model = WhisperModel(
        config["model"],
        device=config["device"],
        compute_type=config["compute_type"],
    )

    print("Transcribing...")
    segments, _ = model.transcribe(audio_file, beam_size=5, vad_filter=True)
    text = " ".join(segment.text.strip() for segment in segments)
    return text


def record_audio(duration: float = None) -> str:
    """Record audio using PipeWire and return the temp file path."""
    temp_file = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
    temp_file.close()

    cmd = ["pw-record", "--rate", "16000", "--channels", "1", "--format", "s16"]
    if duration:
        # Note: pw-record doesn't have a native duration flag, so we use timeout
        cmd = ["timeout", str(duration)] + cmd
    cmd.append(temp_file.name)

    print(f"Recording... (Press Ctrl+C to stop)" if not duration else f"Recording for {duration}s...")
    try:
        subprocess.run(cmd)
    except KeyboardInterrupt:
        pass

    return temp_file.name


def copy_to_clipboard(text: str):
    """Copy text to Wayland clipboard using wl-copy."""
    process = subprocess.Popen(["wl-copy"], stdin=subprocess.PIPE)
    process.communicate(input=text.encode())


def type_text(text: str):
    """Type text into the active window using wtype."""
    subprocess.run(["wtype", text])


def main():
    parser = argparse.ArgumentParser(
        description="SoupaWhisper - Voice dictation for Wayland/Hyprland"
    )
    parser.add_argument(
        "-v", "--version",
        action="version",
        version=f"SoupaWhisper {__version__}",
    )
    parser.add_argument(
        "-f", "--file",
        help="Transcribe an existing audio file instead of recording",
    )
    parser.add_argument(
        "-d", "--duration",
        type=float,
        help="Record for a specific duration in seconds",
    )
    parser.add_argument(
        "--no-type",
        action="store_true",
        help="Don't auto-type the transcription",
    )
    parser.add_argument(
        "--no-clipboard",
        action="store_true",
        help="Don't copy to clipboard",
    )

    args = parser.parse_args()
    config = load_config()

    print(f"SoupaWhisper v{__version__} (Wayland)")
    print(f"Config: {CONFIG_PATH}")
    print()

    check_dependencies()

    # Determine audio source
    if args.file:
        audio_file = args.file
        cleanup = False
    else:
        audio_file = record_audio(args.duration)
        cleanup = True

    try:
        # Transcribe
        text = transcribe_file(audio_file, config)

        if text:
            print(f"\nTranscription: {text}\n")

            if not args.no_clipboard:
                copy_to_clipboard(text)
                print("Copied to clipboard!")

            if config["auto_type"] and not args.no_type:
                type_text(text)
                print("Typed into active window!")

            if config["notifications"]:
                notify(
                    "Copied!",
                    text[:100] + ("..." if len(text) > 100 else ""),
                    "emblem-ok-symbolic",
                    3000,
                )
        else:
            print("No speech detected")
            if config["notifications"]:
                notify("No speech detected", "Try speaking louder", "dialog-warning", 2000)

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        if config.get("notifications", True):
            notify("Error", str(e)[:50], "dialog-error", 3000)
        sys.exit(1)
    finally:
        if cleanup and os.path.exists(audio_file):
            os.unlink(audio_file)


if __name__ == "__main__":
    main()
