#!/usr/bin/env bash
# Install SPIN + the Python package on a fresh Ubuntu/Colab VM.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq spin gcc g++ make git
python3 -m pip install -q -e "${ROOT}[dev]"
python3 -m semanticdrift check-tools
python3 -m semanticdrift list
