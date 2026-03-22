#!/bin/bash
# Install SoupaWhisper for Wayland/Hyprland
# Optimized for Arch Linux with PipeWire

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_DIR="$HOME/.config/soupawhisper"
SERVICE_DIR="$HOME/.config/systemd/user"
HYPR_BINDINGS="$HOME/.config/hypr/bindings.conf"

# Install system dependencies (Wayland)
install_deps() {
    echo "Installing system dependencies..."

    if command -v pacman &> /dev/null; then
        sudo pacman -S --noconfirm --needed wl-clipboard wtype libnotify openbsd-netcat
        # pipewire (pw-record) should already be installed on modern Arch
    else
        echo "Non-Arch system detected. Please install manually:"
        echo "  wl-clipboard wtype libnotify netcat"
        echo "  (and ensure PipeWire is installed for pw-record)"
    fi
}

# Install Python dependencies
install_python() {
    echo ""
    echo "Installing Python dependencies..."

    if ! command -v poetry &> /dev/null; then
        echo "Poetry not found. Installing..."
        curl -sSL https://install.python-poetry.org | python3 -
        export PATH="$HOME/.local/bin:$PATH"
    fi

    cd "$SCRIPT_DIR"
    poetry config virtualenvs.in-project true
    poetry install --no-interaction
}

# Setup config file
setup_config() {
    echo ""
    echo "Setting up config..."
    mkdir -p "$CONFIG_DIR"

    if [ ! -f "$CONFIG_DIR/config.ini" ]; then
        cp "$SCRIPT_DIR/config.example.ini" "$CONFIG_DIR/config.ini"
        echo "Created config at $CONFIG_DIR/config.ini"
    else
        echo "Config already exists at $CONFIG_DIR/config.ini"
    fi
}

# Install Hyprland keybindings
install_hyprland_bindings() {
    echo ""
    echo "Setting up Hyprland keybindings..."

    # Make wayland scripts executable
    chmod +x "$SCRIPT_DIR/wayland/soupawhisper-start"
    chmod +x "$SCRIPT_DIR/wayland/soupawhisper-stop"
    chmod +x "$SCRIPT_DIR/wayland/soupawhisper-start-todo"
    chmod +x "$SCRIPT_DIR/wayland/soupawhisper-stop-todo"
    chmod +x "$SCRIPT_DIR/wayland/soupawhisper-toggle-todo"
    chmod +x "$SCRIPT_DIR/wayland/transcribe.py"
    chmod +x "$SCRIPT_DIR/wayland/soupawhisper-daemon.py"

    if [ ! -f "$HYPR_BINDINGS" ]; then
        echo "Hyprland bindings file not found at $HYPR_BINDINGS"
        echo "Please add these bindings manually:"
        echo ""
        echo "# SoupaWhisper voice dictation (push-to-talk: hold F9)"
        echo "bindd = , F9, Start voice recording, exec, $SCRIPT_DIR/wayland/soupawhisper-start"
        echo "binddr = , F9, Stop and transcribe, exec, $SCRIPT_DIR/wayland/soupawhisper-stop"
        echo ""
        echo "# SoupaWhisper todo capture (push-to-talk: hold F8)"
        echo "bindd = , F8, Start todo recording, exec, $SCRIPT_DIR/wayland/soupawhisper-start-todo"
        echo "binddr = , F8, Stop and add todo, exec, $SCRIPT_DIR/wayland/soupawhisper-stop-todo"
        return
    fi

    if grep -q "soupawhisper" "$HYPR_BINDINGS" 2>/dev/null; then
        echo "Hyprland bindings already configured"
    else
        cat >> "$HYPR_BINDINGS" << EOF

# SoupaWhisper voice dictation (push-to-talk: hold F9)
bindd = , F9, Start voice recording, exec, $SCRIPT_DIR/wayland/soupawhisper-start
binddr = , F9, Stop and transcribe, exec, $SCRIPT_DIR/wayland/soupawhisper-stop

# SoupaWhisper todo capture (push-to-talk: hold F8)
bindd = , F8, Start todo recording, exec, $SCRIPT_DIR/wayland/soupawhisper-start-todo
binddr = , F8, Stop and add todo, exec, $SCRIPT_DIR/wayland/soupawhisper-stop-todo
EOF
        echo "Added keybindings to $HYPR_BINDINGS"
    fi
}

# Install systemd service for daemon
install_service() {
    echo ""
    echo "Installing systemd user service..."

    mkdir -p "$SERVICE_DIR"

    cat > "$SERVICE_DIR/soupawhisper.service" << EOF
[Unit]
Description=SoupaWhisper Voice Dictation Daemon
After=graphical-session.target pipewire.service
BindsTo=graphical-session.target

[Service]
Type=simple
WorkingDirectory=$SCRIPT_DIR
ExecStart=$SCRIPT_DIR/.venv/bin/python $SCRIPT_DIR/wayland/soupawhisper-daemon.py
Restart=on-failure
RestartSec=5

# Wayland environment
PassEnvironment=WAYLAND_DISPLAY XDG_RUNTIME_DIR

[Install]
WantedBy=default.target
EOF

    echo "Created service at $SERVICE_DIR/soupawhisper.service"

    systemctl --user daemon-reload
    systemctl --user enable soupawhisper

    echo ""
    echo "Service installed! Commands:"
    echo "  systemctl --user start soupawhisper   # Start daemon"
    echo "  systemctl --user stop soupawhisper    # Stop daemon"
    echo "  systemctl --user status soupawhisper  # Status"
    echo "  journalctl --user -u soupawhisper -f  # Logs"
}

# Main
main() {
    echo "==================================="
    echo "  SoupaWhisper Wayland Installer"
    echo "==================================="
    echo ""

    install_deps
    install_python
    setup_config
    install_hyprland_bindings

    echo ""
    read -p "Install systemd service (daemon)? [Y/n] " -n 1 -r
    echo ""

    if [[ ! $REPLY =~ ^[Nn]$ ]]; then
        install_service
    fi

    echo ""
    echo "==================================="
    echo "  Installation complete!"
    echo "==================================="
    echo ""
    echo "Next steps:"
    echo "  1. Reload Hyprland: hyprctl reload"
    echo "  2. Start daemon:    systemctl --user start soupawhisper"
    echo "  3. Use:             Hold F9 to record, release to transcribe"
    echo ""
    echo "Config: $CONFIG_DIR/config.ini"
    echo ""
    echo "Manual transcription:"
    echo "  poetry run python dictate.py -f audio.wav"
    echo "  poetry run python dictate.py -d 5  # Record for 5 seconds"
}

main "$@"
