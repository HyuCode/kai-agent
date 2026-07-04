#!/usr/bin/env bash
# obs-browser（CEF ブラウザソース）を aarch64 の Ubuntu 24.04 向けにビルドし、
# OBS のユーザープラグインとして配置する。kai-vm（UTM / Ubuntu 24.04 arm64）で検証済み。
#
# 背景: Ubuntu apt 版 OBS（arm64）は dfsg 再パッケージで CEF が除かれておりブラウザ
# ソースが使えない。Flathub にも aarch64 OBS がない。そこで OBS 本体（apt 版）は
# そのままに、obs-browser プラグインだけを apt 版と同じ 30.0.2 系ソースから自前
# ビルドして足す。字幕オーバーレイ（speechd の GET /overlay/）をブラウザソースで
# 配信映像に合成するのが目的。設計: docs/kai/design/00-system.md §4。
#
# 冪等（各ステップは成果物があればスキップ）。CEF 取得 + wrapper/プラグインの
# コンパイルで 20〜40 分・ディスク約 1GB。使い方（VM 内）:
#   bash kai-services/streaming/vm/build-obs-browser.sh
# 白紙から検証したい場合は BUILD_DIR を変える: BUILD_DIR=~/build-verify bash ...
#
# 完了条件（末尾で自己検証。満たさなければ非ゼロ終了）:
#   - obs-browser.so と obs-browser-page が配置され、ldd に "not found" が無い。
set -euo pipefail

OBS_VERSION="${OBS_VERSION:-30.0.2}"
# obs-studio 30.0.2 の buildspec.json が要求する CEF（label "cef", version "5060"）。
# Chromium 103.0.5060.134 = CEF 103.0.12。spotify CDN の linuxarm64 minimal を使う。
# URL の '+' は %2B にエンコードする（生の + でも通るが安全側に倒す）。
CEF_DIRNAME="cef_binary_103.0.12+g8eb56c7+chromium-103.0.5060.134_linuxarm64_minimal"
CEF_URL="https://cef-builds.spotifycdn.com/cef_binary_103.0.12%2Bg8eb56c7%2Bchromium-103.0.5060.134_linuxarm64_minimal.tar.bz2"

BUILD_DIR="${BUILD_DIR:-${HOME}/build}"
PLUGIN_DIR="${HOME}/.config/obs-studio/plugins/obs-browser/bin/64bit"

echo "==> 1/8 apt: build-dep と CEF/patchelf に必要なツール"
if ! grep -q "deb-src" /etc/apt/sources.list.d/ubuntu.sources 2>/dev/null; then
  sudo sed -i "s/^Types: deb$/Types: deb deb-src/" /etc/apt/sources.list.d/ubuntu.sources
fi
sudo apt-get update
sudo DEBIAN_FRONTEND=noninteractive apt-get build-dep -y obs-studio
sudo DEBIAN_FRONTEND=noninteractive apt-get install -y cmake ninja-build libobs-dev patchelf

echo "==> 2/8 CEF minimal をダウンロード・展開"
mkdir -p "${BUILD_DIR}"
cd "${BUILD_DIR}"
if [[ ! -f cef/Release/libcef.so ]]; then
  rm -rf cef "${CEF_DIRNAME}"
  # -f: HTTP エラー時に失敗させる（CDN が HTML エラーページを返したとき、それを
  #     tar に食わせて壊れたビルドに進むのを防ぐ）。--retry で一時エラーを吸収。
  curl -fSL --retry 3 --retry-delay 5 -o cef.tar.bz2 "${CEF_URL}"
  tar xjf cef.tar.bz2
  mv "${CEF_DIRNAME}" cef
  rm -f cef.tar.bz2
fi
test -f cef/Release/libcef.so # 展開の健全性を確認

echo "==> 3/8 libcef_dll_wrapper をビルド"
# PROJECT_ARCH=arm64 が必須。省略すると CEF の cmake が既定で -m64/-march=x86-64 を
# 付けてしまい aarch64 の gcc が 'unrecognized command-line option -m64' で落ちる。
cd "${BUILD_DIR}/cef"
if [[ ! -f build/libcef_dll_wrapper/libcef_dll_wrapper.a ]]; then
  cmake -B build -G Ninja -DCMAKE_BUILD_TYPE=Release -DPROJECT_ARCH=arm64
  cmake --build build --target libcef_dll_wrapper
fi

echo "==> 4/8 obs-studio ${OBS_VERSION} のソースを取得"
cd "${BUILD_DIR}"
if [[ ! -d obs-studio/.git ]]; then
  rm -rf obs-studio
  git clone --depth 1 --branch "${OBS_VERSION}" --recurse-submodules --shallow-submodules \
    https://github.com/obsproject/obs-studio.git obs-studio
fi

echo "==> 5/8 パッチ: gnome-keyring のパスワード作成ダイアログを配信画面に出さない"
# GNOME を検出すると CEF は暗号化パスワードストア（gnome-libsecret）を使おうとし、
# キーリング作成ダイアログをデスクトップ（＝配信映像）に出してしまう。ファイル
# ベースの basic ストアを強制してダイアログ自体を発生させない。パッチは
# OnBeforeCommandLineProcessing の末尾（__APPLE__ ブロックの外）に追加する。
APP_CPP="${BUILD_DIR}/obs-studio/plugins/obs-browser/browser-app.cpp"
if ! grep -q "password-store" "${APP_CPP}"; then
  python3 - "${APP_CPP}" <<'PYEOF'
import sys, pathlib
p = pathlib.Path(sys.argv[1])
s = p.read_text()
anchor = '#ifdef __APPLE__\n\tcommand_line->AppendSwitch("use-mock-keychain");\n#endif\n}'
patch = (
    '#ifdef __APPLE__\n'
    '\tcommand_line->AppendSwitch("use-mock-keychain");\n'
    '#endif\n'
    '\n'
    '#if !defined(_WIN32) && !defined(__APPLE__)\n'
    '\t// gnome-keyring のパスワード作成ダイアログを配信画面に出さない（kai パッチ）。\n'
    '\tcommand_line->AppendSwitchWithValue("password-store", "basic");\n'
    '#endif\n'
    '}'
)
assert anchor in s, "anchor for keyring patch not found (obs-browser のソースが想定と違う)"
p.write_text(s.replace(anchor, patch, 1))
print("  patched browser-app.cpp")
PYEOF
else
  echo "  (既にパッチ済み)"
fi

echo "==> 6/8 obs-studio を configure してブラウザプラグインをビルド"
cd "${BUILD_DIR}/obs-studio"
# QSV11(VPL) は arm64 に無いので OFF。ffmpeg の deprecated API 警告は OBS 側が
# -Werror で拾って libobs のビルドが止まるため、その警告だけ非エラー化する。
# ブラウザに不要な重い機能（AJA/WebRTC/NVENC）は落として時間短縮。
cmake -B build -G Ninja \
  -DCMAKE_BUILD_TYPE=RelWithDebInfo \
  -DCMAKE_C_FLAGS="-Wno-error=deprecated-declarations" \
  -DCMAKE_CXX_FLAGS="-Wno-error=deprecated-declarations" \
  -DENABLE_BROWSER=ON -DCEF_ROOT_DIR="${BUILD_DIR}/cef" \
  -DENABLE_AJA=OFF -DENABLE_WEBRTC=OFF -DENABLE_NATIVE_NVENC=OFF -DENABLE_QSV11=OFF
cmake --build build --target obs-browser obs-browser-page

echo "==> 7/8 ユーザープラグインとして配置（apt 版 OBS 本体はそのまま）"
mkdir -p "${PLUGIN_DIR}"
cp "${BUILD_DIR}/obs-studio/build/plugins/obs-browser/obs-browser.so" "${PLUGIN_DIR}/"
cp "${BUILD_DIR}/obs-studio/build/plugins/obs-browser/obs-browser-page" "${PLUGIN_DIR}/"
cp -r "${BUILD_DIR}/cef/Release/." "${PLUGIN_DIR}/"
cp -r "${BUILD_DIR}/cef/Resources/." "${PLUGIN_DIR}/"
# libcef.so をプラグインと同じディレクトリに置き、rpath=$ORIGIN で解決させる
# （システムには CEF が無いため）。obs-browser-page も同様。
patchelf --set-rpath '$ORIGIN' "${PLUGIN_DIR}/obs-browser.so" "${PLUGIN_DIR}/obs-browser-page"
chmod +x "${PLUGIN_DIR}/obs-browser-page"
# UI ロケール（cosmetic。無くても動くが「Failed to load 'en-US' text」警告が出る）
mkdir -p "${HOME}/.config/obs-studio/plugins/obs-browser/data"
cp -r "${BUILD_DIR}/obs-studio/plugins/obs-browser/data/locale" \
  "${HOME}/.config/obs-studio/plugins/obs-browser/data/" 2>/dev/null || true

echo "==> 8/8 自己検証（配置と依存解決）"
fail=0
for f in obs-browser.so obs-browser-page libcef.so; do
  if [[ ! -e "${PLUGIN_DIR}/${f}" ]]; then
    echo "  ❌ 配置されていない: ${PLUGIN_DIR}/${f}"
    fail=1
  fi
done
# 共有ライブラリが未解決（not found）でないこと。libobs/Qt はシステム側にある前提。
if ldd "${PLUGIN_DIR}/obs-browser.so" 2>/dev/null | grep -q "not found"; then
  echo "  ❌ obs-browser.so に未解決の共有ライブラリがあります:"
  ldd "${PLUGIN_DIR}/obs-browser.so" | grep "not found"
  fail=1
fi
if [[ "${fail}" -ne 0 ]]; then
  echo "ビルドは失敗です（配置または依存解決が不完全）。"
  exit 1
fi

echo ""
echo "✅ 完了。obs-browser.so / obs-browser-page / libcef.so を配置し、依存解決も OK。"
echo "OBS を再起動するとログに次が出れば成功:"
echo "  [obs-browser]: Version 2.22.2 / CEF Version 103.0.5060.134"
echo "ブラウザソースを追加し URL に http://127.0.0.1:8900/overlay/ を指定すると字幕が乗る。"
echo "注意: OBS はウィンドウを閉じるクリーン終了でないとシーン（ソース構成）を保存しない。"
