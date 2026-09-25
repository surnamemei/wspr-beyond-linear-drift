#!/usr/bin/env bash
set -euo pipefail

root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
bash "$root/scripts/run_awgn_baseline.sh" --full

plot_python='/mnt/d/ANACONDA/python.exe'
if [[ ! -x "$plot_python" ]]; then
    echo 'D:\ANACONDA\python.exe with Matplotlib is required to render the PNG.' >&2
    exit 1
fi
root_windows=$(wslpath -w "$root")
plot_script_windows=$(wslpath -w "$root/scripts/render_awgn_figure.py")
"$plot_python" "$plot_script_windows" "$root_windows"
