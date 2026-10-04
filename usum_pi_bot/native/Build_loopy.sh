#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "$0")"
source_dir="$PWD/build-source"
if [[ ! -d "$source_dir/.git" ]]; then
  git clone --depth 1 --branch 1.3.0.1 https://github.com/Lorenzooone/cc3dsfs.git "$source_dir"
fi
[[ $(git -C "$source_dir" rev-parse HEAD) == 60c9f81259310a8738d20110f3c6104a047fd082 ]]
if ! grep -q SHINY_FRAME_FD "$source_dir/source/cc3dsfs.cpp"; then
  python3 prepare_cc3dsfs.py "$source_dir"
else
  cp shiny_headless.hpp "$source_dir/source/shiny_headless.hpp"
fi
cmake -S "$source_dir" -B build -DCMAKE_BUILD_TYPE=Release
# Two jobs keep the first build's memory and thermal load reasonable on a Pi 4.
cmake --build build --parallel 2
mkdir -p bin
install -m 0755 build/bin/cc3dsfs bin/cc3dsfs
cp "$source_dir/LICENSE" bin/cc3dsfs-LICENSE
