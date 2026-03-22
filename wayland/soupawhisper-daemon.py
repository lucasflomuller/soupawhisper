#!/usr/bin/env python3
"""SoupaWhisper daemon - keeps model loaded for instant transcription."""

import configparser
import os
import signal
import socket
import subprocess
import sys
from pathlib import Path

from faster_whisper import WhisperModel

CONFIG_PATH = Path.home() / ".config" / "soupawhisper" / "config.ini"


def get_runtime_dir():
    return Path(os.environ.get("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}")) / "soupawhisper"


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


class Daemon:
    def __init__(self):
        self.config = load_config()
        self.runtime_dir = get_runtime_dir()
        self.socket_path = self.runtime_dir / "daemon.sock"
        self.model = None
        self.running = True

    def _notify(self, title, message, icon="dialog-information", timeout=2000):
        if self.config["notifications"]:
            notify(title, message, icon, timeout)

    def load_model(self):
        print(f"Loading Whisper model ({self.config['model']})...")
        self.model = WhisperModel(
            self.config["model"],
            device=self.config["device"],
            compute_type=self.config["compute_type"],
        )
        print("Model loaded. Daemon ready.")
        if self.config["initial_prompt"]:
            print(f"Context prompt: {self.config['initial_prompt'][:60]}...")
        if self.config["hotwords"]:
            print(f"Hotwords: {self.config['hotwords'][:60]}...")
        self._notify("SoupaWhisper", "Daemon ready - press F9 to dictate", "audio-input-microphone", 3000)

    def transcribe(self, audio_file):
        try:
            # Build transcribe options with context if configured
            transcribe_opts = {
                "beam_size": 5,
                "vad_filter": True,
            }
            if self.config["initial_prompt"]:
                transcribe_opts["initial_prompt"] = self.config["initial_prompt"]
            if self.config["hotwords"]:
                transcribe_opts["hotwords"] = self.config["hotwords"]

            segments, _ = self.model.transcribe(audio_file, **transcribe_opts)
            text = " ".join(segment.text.strip() for segment in segments)

            if text:
                # Clipboard
                process = subprocess.Popen(["wl-copy"], stdin=subprocess.PIPE)
                process.communicate(input=text.encode())

                # Auto-type
                if self.config["auto_type"]:
                    result = subprocess.run(["wtype", text], capture_output=True)
                    if result.returncode != 0:
                        self._notify("Copied!", f"{text[:80]}...", "emblem-ok-symbolic", 3000)
                        return text

                self._notify(
                    "Copied!",
                    text[:100] + ("..." if len(text) > 100 else ""),
                    "emblem-ok-symbolic",
                    3000,
                )
                return text
            else:
                self._notify("No speech detected", "Try speaking louder", "dialog-warning", 2000)
                return ""
        except Exception as e:
            self._notify("Error", str(e)[:50], "dialog-error", 3000)
            print(f"Transcription error: {e}", file=sys.stderr)
            return ""
        finally:
            if os.path.exists(audio_file):
                os.unlink(audio_file)

    def transcribe_todo(self, audio_file):
        """Transcribe audio and append to todo.md."""
        try:
            # Check audio file exists
            if not os.path.exists(audio_file):
                self._notify("No audio", "Recording file not found", "dialog-warning", 2000)
                return ""

            # Check audio file has content
            if os.path.getsize(audio_file) == 0:
                self._notify("No audio", "Recording was empty", "dialog-warning", 2000)
                return ""

            transcribe_opts = {
                "beam_size": 5,
                "vad_filter": True,
            }
            if self.config["initial_prompt"]:
                transcribe_opts["initial_prompt"] = self.config["initial_prompt"]
            if self.config["hotwords"]:
                transcribe_opts["hotwords"] = self.config["hotwords"]

            segments, _ = self.model.transcribe(audio_file, **transcribe_opts)
            text = " ".join(segment.text.strip() for segment in segments)

            # Handle empty transcription
            if not text or not text.strip():
                self._notify("No speech detected", "Try speaking louder or closer to mic", "dialog-warning", 2000)
                return ""

            # Clean up text (remove leading/trailing whitespace)
            text = text.strip()

            todo_line = f"- [ ] {text}\n"
            todo_path = Path.home() / "todo.md"

            # Append to todo file
            try:
                with open(todo_path, "a") as f:
                    f.write(todo_line)
            except PermissionError:
                self._notify("Permission denied", f"Cannot write to {todo_path}", "dialog-error", 3000)
                return ""
            except IOError as e:
                self._notify("Write failed", f"Could not save todo: {e}", "dialog-error", 3000)
                return ""

            self._notify(
                "Todo added!",
                text[:100] + ("..." if len(text) > 100 else ""),
                "checkbox-checked-symbolic",
                3000,
            )
            return text

        except Exception as e:
            self._notify("Error", str(e)[:50], "dialog-error", 3000)
            print(f"Todo transcription error: {e}", file=sys.stderr)
            return ""
        finally:
            if os.path.exists(audio_file):
                os.unlink(audio_file)

    def run(self):
        # Create runtime directory
        self.runtime_dir.mkdir(parents=True, exist_ok=True)

        # Clean up stale socket
        if self.socket_path.exists():
            self.socket_path.unlink()

        self.load_model()

        # Create socket with secure permissions
        old_umask = os.umask(0o077)
        server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        server.bind(str(self.socket_path))
        server.listen(1)
        os.umask(old_umask)

        def handle_signal(sig, frame):
            print("\nShutting down...")
            self.running = False
            server.close()
            if self.socket_path.exists():
                self.socket_path.unlink()
            sys.exit(0)

        signal.signal(signal.SIGINT, handle_signal)
        signal.signal(signal.SIGTERM, handle_signal)

        print(f"Listening on {self.socket_path}")
        while self.running:
            try:
                conn, _ = server.accept()
                conn.settimeout(30)  # 30 second timeout
                data = conn.recv(4096).decode().strip()
                if data.startswith("TRANSCRIBE:"):
                    audio_file = data.split(":", 1)[1]
                    result = self.transcribe(audio_file)
                    conn.sendall(result.encode() if result else b"")
                elif data.startswith("TRANSCRIBE_TODO:"):
                    audio_file = data.split(":", 1)[1]
                    result = self.transcribe_todo(audio_file)
                    conn.sendall(result.encode() if result else b"")
                conn.close()
            except socket.timeout:
                pass
            except Exception as e:
                if self.running:
                    print(f"Socket error: {e}", file=sys.stderr)


if __name__ == "__main__":
    Daemon().run()
