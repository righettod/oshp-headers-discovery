#!/bin/bash
rm -rf mdn 2>/dev/null
wget -q -O mdn.zip https://github.com/mdn/content/archive/refs/heads/main.zip
unzip -q mdn.zip "content-main/files/en-us/web/http/reference/headers/**" -d mdn
rm mdn.zip
