#!/usr/bin/env bash
set -euo pipefail

diagnostic_dir=$(cd -- "$(dirname -- "$0")" && pwd)
build_root=${1:-"$diagnostic_dir/build"}
mkdir -p "$build_root"
build_root=$(cd -- "$build_root" && pwd)

# Exact upstream source and launcher, including their pinned submodules.
ntr_sha=cbc8858c43ecda7903baeeb8efa7c433ae6e8ffa
boot_sha=6ba51e7d1d8664639bc55d3bdc35e78dfa18fffd

checkout() {
    local repo_url=$1 checkout_dir=$2 checkout_sha=$3
    if [[ -e "$checkout_dir" ]]; then
        echo "Build directory already exists: $checkout_dir. Use a fresh build directory." >&2
        return 1
    fi
    git init "$checkout_dir"
    git -C "$checkout_dir" remote add origin "$repo_url"
    git -C "$checkout_dir" fetch --depth=1 origin "$checkout_sha"
    git -C "$checkout_dir" checkout --detach FETCH_HEAD
    git -C "$checkout_dir" submodule update --init --recursive --depth=1
}

checkout https://github.com/xzn/ntr-hr.git "$build_root/ntr-hr" "$ntr_sha"
checkout https://github.com/xzn/BootNTR.git "$build_root/BootNTR-Bins" "$boot_sha"
python3 "$diagnostic_dir/apply_patch.py" "$build_root/ntr-hr" --encounter-reader

cd "$build_root/ntr-hr"
MAKEFLAGS="USE_CLANG=1 USE_LTO=1" bash make.sh install
cd "$build_root/BootNTR-Bins"
bash make.sh

mkdir -p "$build_root/artifacts/symbols" "$build_root/artifacts/source"
cp output/3ds-arm/BootNTRSelector-PabloMK7-Banner.cia "$build_root/artifacts/BootNTRSelector-NTR-Encounter-Reader-v3.cia"
cp "$build_root/ntr-hr/bin/"*.elf "$build_root/artifacts/symbols/"
cp "$build_root/ntr-hr/"*.map "$build_root/artifacts/symbols/"
cp "$build_root/ntr-hr/source/pm/main_pm.c" "$build_root/artifacts/source/"
cp "$diagnostic_dir/ntr_plugin_trace.h" "$build_root/artifacts/source/"
cp "$diagnostic_dir/ntr_safe_title.h" "$build_root/artifacts/source/"
cp "$build_root/ntr-hr/source/ns.c" "$build_root/artifacts/source/"
cp "$diagnostic_dir/ntr_read_encounter.h" "$build_root/artifacts/source/"
cp "$diagnostic_dir/../../usum_pi_bot/encounter_probe.py" "$build_root/artifacts/"
cp "$diagnostic_dir/../../usum_pi_bot/MEMORY_PROBE.md" "$build_root/artifacts/"
cp "$diagnostic_dir/LICENSE" "$build_root/artifacts/"
cp "$diagnostic_dir/README.md" "$build_root/artifacts/"
printf 'NTR-HR: %s\nBootNTR: %s\nDiagnostic: encounter-reader-v3\n' "$ntr_sha" "$boot_sha" > "$build_root/artifacts/BUILD.txt"
cd "$build_root/artifacts"
sha256sum ./*.cia symbols/* source/* > SHA256SUMS.txt

