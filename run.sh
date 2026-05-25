#!/bin/bash
# Media Tools Web 一键启动脚本
# 
# 用法:
#   ./run.sh              # 同时启动后端 API 和前端 React 开发服务器
#   ./run.sh backend      # 仅启动后端 API
#   ./run.sh frontend     # 仅启动前端 React 开发服务器
#   ./run.sh build        # 构建前端静态资源

set -e

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m'

BACKEND_HOST="127.0.0.1"
BACKEND_PORT="8000"
BACKEND_HEALTH_URL="http://${BACKEND_HOST}:${BACKEND_PORT}/api/health"

info() { echo -e "${BLUE}[INFO]${NC} $1"; }
success() { echo -e "${GREEN}[SUCCESS]${NC} $1"; }
error() { echo -e "${RED}[ERROR]${NC} $1"; }

# 确保在项目根目录运行
cd "$(dirname "$0")"

# 强制使用项目 .venv 的 Python，避免与系统/miniconda 解释器混用
# （历史教训：miniconda Python 会拾起 ~/.local/lib/.../f2，绕开 .venv 的依赖）
PY="${PY:-$(pwd)/.venv/bin/python}"
if [ ! -x "${PY}" ]; then
    error "未找到项目 venv: ${PY}"
    error "请先创建: python3.11 -m venv .venv && .venv/bin/pip install -e ."
    exit 1
fi

port_in_use() {
    lsof -iTCP:"$1" -sTCP:LISTEN -n -P >/dev/null 2>&1
}

backend_is_healthy() {
    curl -fsS "${BACKEND_HEALTH_URL}" >/dev/null 2>&1
}

start_backend_background() {
    info "启动后端 (端口 ${BACKEND_PORT})..."
    # --reload-dir src 收紧监控范围：默认 watch 整个仓库（含 frontend、node_modules、
    # 几千个 fsstat 调用）→ reloader 进程持续 ~28% CPU。仅监控 src/ 后回落到 <2%。
    PYTHONPATH=src "${PY}" -m uvicorn media_tools.api.app:app --reload --reload-dir src --host "${BACKEND_HOST}" --port "${BACKEND_PORT}" &
    BACKEND_PID=$!

    for _ in $(seq 1 20); do
        if backend_is_healthy; then
            success "后端已就绪: ${BACKEND_HEALTH_URL}"
            return 0
        fi
        sleep 0.5
    done

    error "后端启动超时，请检查日志"
    return 1
}

run_backend() {
    info "启动 FastAPI 后端服务 (端口 ${BACKEND_PORT})..."
    PYTHONPATH=src "${PY}" -m uvicorn media_tools.api.app:app --reload --reload-dir src --host "${BACKEND_HOST}" --port "${BACKEND_PORT}"
}

run_frontend() {
    info "启动 React 前端开发服务器..."
    cd frontend
    if [ ! -d "node_modules" ]; then
        info "安装前端依赖..."
        npm install
    fi
    npm run dev -- --host 127.0.0.1
}

run_both() {
    info "准备同时启动前后端..."
    
    # 后端检查依赖
    if ! "${PY}" -c "import uvicorn" 2>/dev/null; then
        info "安装后端依赖..."
        "${PY}" -m pip install -r requirements.txt
    fi

    # 前端检查依赖
    if [ ! -d "frontend/node_modules" ]; then
        info "安装前端依赖..."
        cd frontend && npm install && cd ..
    fi

    BACKEND_STARTED_BY_SCRIPT=0

    if backend_is_healthy; then
        info "检测到后端已在运行，复用现有服务: ${BACKEND_HEALTH_URL}"
    elif port_in_use "${BACKEND_PORT}"; then
        error "端口 ${BACKEND_PORT} 已被占用，但健康检查未通过，请先释放端口后再启动。"
        exit 1
    else
        start_backend_background
        BACKEND_STARTED_BY_SCRIPT=1
    fi

    # 启动前端在前台
    info "启动前端 (Vite)..."
    trap 'if [ "${BACKEND_STARTED_BY_SCRIPT}" = "1" ] && [ -n "${BACKEND_PID:-}" ]; then kill "${BACKEND_PID}" 2>/dev/null || true; fi' EXIT
    cd frontend && npm run dev -- --host 127.0.0.1

}

build_frontend() {
    info "构建前端生产环境资源..."
    cd frontend
    npm install
    npm run build
    success "构建完成！产物位于 frontend/dist/"
}

case "${1:-}" in
    backend) run_backend ;;
    frontend) run_frontend ;;
    build) build_frontend ;;
    help|--help|-h)
        echo "Media Tools Web 一键启动脚本"
        echo "  ./run.sh           同时启动前后端（开发模式）"
        echo "  ./run.sh backend   仅启动 FastAPI 后端"
        echo "  ./run.sh frontend  仅启动 React 前端"
        echo "  ./run.sh build     构建前端静态资源"
        ;;
    "") run_both ;;
    *)
        error "未知命令: $1"
        exit 1
        ;;
esac
