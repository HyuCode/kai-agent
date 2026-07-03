# kai 配信スタック（Linux デスクトップ + OBS + VNC）— Mac 上の Docker で稼働
# 設計: docs/kai/design/streaming.md
# ベースは Debian trixie: Ubuntu 24.04 と違い obs-studio / chromium が snap でなく deb で入る（コンテナ向き）
FROM debian:trixie

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y --no-install-recommends \
    # X サーバー（dummy ドライバ = GPU 不要のソフトウェアレンダリング）
    xserver-xorg-core xserver-xorg-video-dummy x11-utils x11-xserver-utils xauth \
    # デスクトップ（XFCE、非コンポジットで CPU 軽量）
    xfce4 xfce4-terminal dbus-x11 dbus \
    # リモート GUI
    x11vnc \
    # 音声（null-sink kai_speaker を提供。コンテナ内は PipeWire より PulseAudio が扱いやすい）
    pulseaudio pulseaudio-utils \
    # 配信
    obs-studio ffmpeg \
    # ブラウザ（kai のブラウジング実演・PuruPuruPNGTuber 用）
    chromium \
    # 日本語表示
    fonts-noto-cjk fonts-noto-color-emoji \
    # プロセス管理・ユーティリティ
    supervisor curl jq procps \
    && rm -rf /var/lib/apt/lists/*

# kai ユーザー（uid 1000）。全 GUI プロセスはこのユーザーで動く
RUN useradd -m -u 1000 -s /bin/bash kai

# Xorg dummy 設定（1920x1080）は VM 版と共通のものを使う
COPY conf/10-dummy.conf /etc/X11/xorg.conf.d/10-dummy.conf

# PulseAudio: null-sink kai_speaker（OBS がこの monitor を音声ソースにする）
COPY docker/pulse-kai-speaker.pa /etc/pulse/default.pa.d/kai-speaker.pa

COPY docker/supervisord.conf /etc/supervisor/conf.d/kai.conf
COPY docker/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

EXPOSE 5900 4455

HEALTHCHECK --interval=30s --timeout=5s --start-period=60s \
    CMD su kai -c "DISPLAY=:0 xdpyinfo > /dev/null" || exit 1

ENTRYPOINT ["/entrypoint.sh"]
