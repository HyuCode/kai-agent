#!/usr/bin/env bash
# コンテナ起動時の初期化（root で実行 → supervisord が各プロセスを kai ユーザーで起動）
set -euo pipefail

# X ソケットディレクトリ
mkdir -p /tmp/.X11-unix && chmod 1777 /tmp/.X11-unix

# kai ユーザーのランタイムディレクトリ（PulseAudio 用）
mkdir -p /run/user/1000 && chown kai:kai /run/user/1000 && chmod 700 /run/user/1000

# システム DBus（XFCE の警告抑制）
mkdir -p /run/dbus
dbus-daemon --system --fork 2>/dev/null || true

# VNC パスワード（VNC_PASSWORD env から生成。既存ファイルがあれば維持）
if [[ ! -f /home/kai/.vnc/passwd ]]; then
  if [[ -z "${VNC_PASSWORD:-}" ]]; then
    echo "ERROR: VNC_PASSWORD が未設定です（compose の .env で設定）" >&2
    exit 1
  fi
  su kai -c "mkdir -p ~/.vnc && x11vnc -storepasswd '$VNC_PASSWORD' ~/.vnc/passwd"
fi

mkdir -p /var/log/supervisor
exec /usr/bin/supervisord -n -c /etc/supervisor/supervisord.conf
