#!/bin/bash
# 项目根目录入口：转发到 scripts/start.sh，便于在仓库根直接 ./run.sh 启动。
exec "$(dirname "$0")/scripts/start.sh" "$@"
