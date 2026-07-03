# kai 配信スタック（Linux デスクトップ + OBS + VNC）— Mac 上の Docker で稼働
# 設計: docs/kai/design/streaming.md
FROM ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates curl \
    # X サーバー（dummy ドライバ = GPU 不要のソフトウェアレンダリング）
    xserver-xorg-core xserver-xorg-video-dummy x11-utils x11-xserver-utils xauth \
    # デスクトップ（XFCE、非コンポジットで CPU 軽量）
    xfce4 xfce4-terminal dbus-x11 dbus \
    # リモート GUI
    x11vnc \
    # 音声（null-sink kai_speaker を提供。コンテナ内は PipeWire より PulseAudio が扱いやすい）
    pulseaudio pulseaudio-utils \
    # 配信（obs-studio は Ubuntu 24.04 universe の deb）
    obs-studio ffmpeg \
    # 日本語表示
    fonts-noto-cjk fonts-noto-color-emoji \
    # プロセス管理・ユーティリティ
    supervisor jq procps \
    # デスクトップ操作（テキスト注入・将来のアバター=カーソル追従で使用）
    xdotool \
    && rm -rf /var/lib/apt/lists/*

# ブラウザ: Ubuntu の chromium/firefox は snap 配布でコンテナに入らないため、
# Chromium エンジンの Brave（公式 apt リポジトリ、arm64 deb あり）を使う
RUN curl -fsSL https://brave-browser-apt-release.s3.brave.com/brave-browser-archive-keyring.gpg \
      -o /usr/share/keyrings/brave-browser-archive-keyring.gpg \
    && echo "deb [signed-by=/usr/share/keyrings/brave-browser-archive-keyring.gpg] https://brave-browser-apt-release.s3.brave.com/ stable main" \
      > /etc/apt/sources.list.d/brave-browser-release.list \
    && apt-get update && apt-get install -y --no-install-recommends brave-browser \
    && rm -rf /var/lib/apt/lists/*

# ブラウザ起動ラッパー: Docker の seccomp が Chromium サンドボックスの userns を塞ぐため
# --no-sandbox で起動（コンテナ自体が隔離境界）。XFCE の「Web Browser」もこれを使う
COPY docker/kai-browser /usr/local/bin/kai-browser
COPY docker/brave-helper.desktop /usr/share/xfce4/helpers/brave.desktop
RUN chmod +x /usr/local/bin/kai-browser \
    && mkdir -p /etc/xdg/xfce4 \
    && { grep -q "^WebBrowser=" /etc/xdg/xfce4/helpers.rc 2>/dev/null \
         && sed -i "s/^WebBrowser=.*/WebBrowser=brave/" /etc/xdg/xfce4/helpers.rc \
         || echo "WebBrowser=brave" >> /etc/xdg/xfce4/helpers.rc; }

# kai ユーザー（uid 1000。ubuntu:24.04 既定の ubuntu ユーザーを置き換える）
RUN userdel -r ubuntu 2>/dev/null || true \
    && useradd -m -u 1000 -s /bin/bash kai

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
