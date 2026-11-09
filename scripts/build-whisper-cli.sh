#!/usr/bin/env bash
# Builds one self-contained whisper-cli for Apple Silicon from a whisper.cpp tag (see README.md).
# Usage: build-whisper-cli.sh [--dry-run] <tag> <out dir>
set -euo pipefail

dry_run=0
if [[ "${1:-}" == "--dry-run" ]]; then
  dry_run=1
  shift
fi
if [[ $# -ne 2 || -z "$1" || -z "$2" ]]; then
  echo "usage: build-whisper-cli.sh [--dry-run] <tag> <out dir>" >&2
  exit 2
fi

tag="$1"
out="${2%/}"
bin="$out/whisper-cli"

run() {
  if [[ $dry_run -eq 1 ]]; then
    printf '%s\n' "$*"
  else
    "$@"
  fi
}

fail() {
  echo "build-whisper-cli.sh: $*" >&2
  exit 1
}

run git clone --depth 1 --branch "$tag" https://github.com/ggml-org/whisper.cpp src
run cmake -S src -B build -DCMAKE_BUILD_TYPE=Release -DBUILD_SHARED_LIBS=OFF -DGGML_METAL=ON \
  -DGGML_METAL_EMBED_LIBRARY=ON -DCMAKE_OSX_ARCHITECTURES=arm64 -DCMAKE_OSX_DEPLOYMENT_TARGET=11.0 \
  -DWHISPER_BUILD_TESTS=OFF -DWHISPER_BUILD_EXAMPLES=ON
run cmake --build build --target whisper-cli -j
run mkdir -p "$out"
run cp build/bin/whisper-cli "$bin"
run codesign --force -s - "$bin"

if [[ $dry_run -eq 1 ]]; then
  printf '%s\n' "lipo -archs $bin" "otool -L $bin" "$bin --help" "shasum -a 256 $bin" "stat -f %z $bin"
  exit 0
fi

archs="$(lipo -archs "$bin")"
[[ "$archs" == "arm64" ]] || fail "lipo -archs printed '$archs', expected 'arm64'"

libraries="$(otool -L "$bin" | tail -n +2 | awk '{print $1}')"
foreign="$(grep -v -e '^/usr/lib/' -e '^/System/' <<<"$libraries" || true)"
[[ -z "$foreign" ]] || fail "whisper-cli links libraries outside /usr/lib and /System: $foreign"

"$bin" --help >/dev/null 2>&1 || fail "$bin --help did not exit 0"

sha256="$(shasum -a 256 "$bin" | awk '{print $1}')"
size="$(stat -f %z "$bin")"
printf 'sha256=%s\nsize=%s\n' "$sha256" "$size"
