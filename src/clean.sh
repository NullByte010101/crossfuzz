#!/bin/bash

TARGET_DIR="../data/crash_file_gcc_2"
# rm -rf "$TARGET_DIR"
# mkdir -p "$TARGET_DIR"
find . -type f ! -name '*.py' ! -name '*.sh' ! -name '*.json' ! -name '*.txt' -exec mv {} "$TARGET_DIR" \; 2>/dev/null
mv javacore.* "$TARGET_DIR"