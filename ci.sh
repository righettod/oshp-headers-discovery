#!/bin/bash
bash update-mdn-ref-headers-folder.sh
uv sync
uv run main.py
rm -rf mdn 2>/dev/null