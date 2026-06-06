#!/bin/bash
# 🍅 启动番茄钟
cd "$(dirname "$0")"
source .venv/bin/activate
exec python3 pomodoro.py
