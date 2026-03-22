#!/usr/bin/env python3
"""Transcribe audio file using Wayland tools (fallback when daemon not running)."""

import subprocess
import sys
import os
import configparser
from pathlib import Path

from faster_whisper import WhisperModel

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
        "initial_prompt": config.get("context", "initial_prompt", fallback=None),
        "hotwords": config.get("context", "hotwords", fallback=None),
    }


def notify(title, message, icon="dialog-information", timeout=2000):
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


def main():
    if len(sys.argv) < 2:
        print("Usage: transcribe.py <audio_file>")
        sys.exit(1)

    audio_file = sys.argv[1]
    config = load_config()

    try:
        model = WhisperModel(
            config["model"],
            device=config["device"],
            compute_type=config["compute_type"],
        )

        # Build transcribe options with context if configured
        transcribe_opts = {
            "beam_size": 5,
            "vad_filter": True,
        }
        if config["initial_prompt"]:
            transcribe_opts["initial_prompt"] = config["initial_prompt"]
        if config["hotwords"]:
            transcribe_opts["hotwords"] = config["hotwords"]

        segments, _ = model.transcribe(audio_file, **transcribe_opts)
        text = " ".join(segment.text.strip() for segment in segments)

        if text:
            # Clipboard (always)
            process = subprocess.Popen(["wl-copy"], stdin=subprocess.PIPE)
            process.communicate(input=text.encode())

            # Auto-type (if enabled)
            if config["auto_type"]:
                result = subprocess.run(["wtype", text], capture_output=True)
                if result.returncode != 0:
                    notify(
                        "Copied!",
                        f"{text[:80]}... (couldn't type)",
                        "emblem-ok-symbolic",
                        3000,
                    )
                    print(text)
                    return

            notify(
                "Copied!",
                text[:100] + ("..." if len(text) > 100 else ""),
                "emblem-ok-symbolic",
                3000,
            )
            print(text)
        else:
            notify("No speech detected", "Try speaking louder", "dialog-warning", 2000)

    except Exception as e:
        notify("Error", str(e)[:50], "dialog-error", 3000)
        print(f"Error: {e}", file=sys.stderr)
    finally:
        if os.path.exists(audio_file):
            os.unlink(audio_file)


if __name__ == "__main__":
    main()
