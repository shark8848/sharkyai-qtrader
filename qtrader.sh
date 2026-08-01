#!/usr/bin/env bash
# ============================================================
# QTrader 服务管理脚本
# 用法: ./qtrader.sh {start|stop|restart|status|logs}
# ============================================================

set -euo pipefail

# --------------- 配置 ---------------
PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
BACKEND_DIR="$PROJECT_DIR/backend"
FRONTEND_DIR="$PROJECT_DIR/frontend"
VENV_DIR="$PROJECT_DIR/../.venv"

BACKEND_HOST="${QTRADER_HOST:-0.0.0.0}"
BACKEND_PORT="${QTRADER_PORT:-8000}"
FRONTEND_PORT="${QTRADER_FE_PORT:-5173}"

LOG_DIR="$PROJECT_DIR/logs"
BACKEND_LOG="$LOG_DIR/backend.log"
FRONTEND_LOG="$LOG_DIR/frontend.log"
BACKEND_PID="$LOG_DIR/backend.pid"
FRONTEND_PID="$LOG_DIR/frontend.pid"

# --------------- 颜色 ---------------
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

info()  { echo -e "${CYAN}[INFO]${NC}  $*"; }
ok()    { echo -e "${GREEN}[OK]${NC}    $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC}  $*"; }
fail()  { echo -e "${RED}[FAIL]${NC}  $*"; }

# --------------- 辅助函数 ---------------
ensure_dirs() {
    mkdir -p "$LOG_DIR"
}

is_process_alive() {
    local pidfile="$1"
    [[ -f "$pidfile" ]] && kill -0 "$(cat "$pidfile")" 2>/dev/null
}

check_port() {
    local port="$1"
    if command -v ss &>/dev/null; then
        ss -tlnp 2>/dev/null | grep -q ":${port} " && return 0
    elif command -v lsof &>/dev/null; then
        lsof -iTCP:"$port" -sTCP:LISTEN &>/dev/null && return 0
    fi
    return 1
}

# 清理占用端口的残留进程
kill_port() {
    local port="$1" name="$2"
    if check_port "$port"; then
        local pid
        pid=$(ss -tlnp 2>/dev/null | grep ":${port} " | grep -oP 'pid=\K[0-9]+' | head -1)
        if [[ -n "$pid" ]]; then
            warn "端口 $port 被占用 (PID $pid)，正在清理 $name 残留进程 ..."
            kill "$pid" 2>/dev/null || true
            sleep 1
            if kill -0 "$pid" 2>/dev/null; then
                kill -9 "$pid" 2>/dev/null || true
                sleep 1
            fi
            ok "已清理端口 $port 占用进程"
        fi
    fi
}

# --------------- 启动 ---------------
start_backend() {
    if is_process_alive "$BACKEND_PID"; then
        ok "后端已在运行 (PID $(cat "$BACKEND_PID"))"
        return 0
    fi

    kill_port "$BACKEND_PORT" "后端"

    # 查找 python
    local python=""
    if [[ -x "$VENV_DIR/bin/python" ]]; then
        python="$VENV_DIR/bin/python"
    elif command -v python3 &>/dev/null; then
        python="$(command -v python3)"
    else
        fail "找不到 Python 解释器"
        return 1
    fi

    info "启动后端 ($BACKEND_HOST:$BACKEND_PORT) ..."

    export MLFLOW_ALLOW_FILE_STORE=true

    # 从项目根目录启动，确保 qtrader 包可被正确导入
    cd "$PROJECT_DIR/.."
    nohup "$python" -m uvicorn qtrader.backend.main:app \
        --host "$BACKEND_HOST" \
        --port "$BACKEND_PORT" \
        >> "$BACKEND_LOG" 2>&1 &
    cd "$PROJECT_DIR"

    echo $! > "$BACKEND_PID"

    # 等待就绪
    for i in $(seq 1 15); do
        if check_port "$BACKEND_PORT"; then
            ok "后端启动成功 (PID $(cat "$BACKEND_PID"))"
            return 0
        fi
        sleep 1
    done
    fail "后端启动超时，请查看日志: $BACKEND_LOG"
    return 1
}

start_frontend() {
    if is_process_alive "$FRONTEND_PID"; then
        ok "前端已在运行 (PID $(cat "$FRONTEND_PID"))"
        return 0
    fi

    kill_port "$FRONTEND_PORT" "前端"

    if [[ ! -d "$FRONTEND_DIR/node_modules" ]]; then
        info "安装前端依赖 ..."
        (cd "$FRONTEND_DIR" && npm install --no-fund --no-audit --silent)
    fi

    info "启动前端 (:$FRONTEND_PORT) ..."

    nohup npm --prefix "$FRONTEND_DIR" run dev \
        >> "$FRONTEND_LOG" 2>&1 &

    echo $! > "$FRONTEND_PID"

    # 等待就绪
    for i in $(seq 1 15); do
        if check_port "$FRONTEND_PORT"; then
            ok "前端启动成功 (PID $(cat "$FRONTEND_PID"))"
            return 0
        fi
        sleep 1
    done
    fail "前端启动超时，请查看日志: $FRONTEND_LOG"
    return 1
}

do_start() {
    ensure_dirs
    echo ""
    echo -e "${CYAN}==============================${NC}"
    echo -e "${CYAN}     QTrader 服务启动${NC}"
    echo -e "${CYAN}==============================${NC}"
    echo ""
    start_backend
    start_frontend
    echo ""
    ok "所有服务已启动"
    echo ""
    info "后端 API:   http://localhost:$BACKEND_PORT"
    info "前端页面:   http://localhost:$FRONTEND_PORT"
    info "API 文档:   http://localhost:$BACKEND_PORT/docs"
    info "后端日志:   $BACKEND_LOG"
    info "前端日志:   $FRONTEND_LOG"
    echo ""
}

# --------------- 停止 ---------------
stop_process() {
    local name="$1" pidfile="$2"
    if ! is_process_alive "$pidfile"; then
        info "$name 未在运行"
        [[ -f "$pidfile" ]] && rm -f "$pidfile"
        return 0
    fi

    local pid
    pid=$(cat "$pidfile")
    info "停止 $name (PID $pid) ..."

    kill "$pid" 2>/dev/null || true

    # 等待退出
    for i in $(seq 1 10); do
        if ! kill -0 "$pid" 2>/dev/null; then
            ok "$name 已停止"
            rm -f "$pidfile"
            return 0
        fi
        sleep 1
    done

    warn "$name 未响应，强制终止 ..."
    kill -9 "$pid" 2>/dev/null || true
    rm -f "$pidfile"
    ok "$name 已强制终止"
}

do_stop() {
    echo ""
    echo -e "${CYAN}==============================${NC}"
    echo -e "${CYAN}     QTrader 服务停止${NC}"
    echo -e "${CYAN}==============================${NC}"
    echo ""
    stop_process "前端" "$FRONTEND_PID"
    stop_process "后端" "$BACKEND_PID"

    # 清理残留进程
    if pgrep -f "uvicorn qtrader" &>/dev/null; then
        pkill -f "uvicorn qtrader" 2>/dev/null || true
        info "已清理残留后端进程"
    fi
    if pgrep -f "vite.*qtrader" &>/dev/null; then
        pkill -f "vite.*qtrader" 2>/dev/null || true
        info "已清理残留前端进程"
    fi
    echo ""
    ok "所有服务已停止"
    echo ""
}

# --------------- 重启 ---------------
do_restart() {
    do_stop
    sleep 1
    do_start
}

# --------------- 状态 ---------------
do_status() {
    echo ""
    echo -e "${CYAN}==============================${NC}"
    echo -e "${CYAN}     QTrader 服务状态${NC}"
    echo -e "${CYAN}==============================${NC}"
    echo ""

    # 后端
    printf "  %-10s " "后端:"
    if is_process_alive "$BACKEND_PID"; then
        echo -e "${GREEN}运行中${NC} (PID $(cat "$BACKEND_PID"))"
    elif check_port "$BACKEND_PORT"; then
        echo -e "${YELLOW}端口 ${BACKEND_PORT} 被占用（可能是外部进程）${NC}"
    else
        echo -e "${RED}未运行${NC}"
    fi

    # 前端
    printf "  %-10s " "前端:"
    if is_process_alive "$FRONTEND_PID"; then
        echo -e "${GREEN}运行中${NC} (PID $(cat "$FRONTEND_PID"))"
    elif check_port "$FRONTEND_PORT"; then
        echo -e "${YELLOW}端口 ${FRONTEND_PORT} 被占用（可能是外部进程）${NC}"
    else
        echo -e "${RED}未运行${NC}"
    fi

    echo ""

    # 健康检查
    if check_port "$BACKEND_PORT"; then
        printf "  %-10s " "Health:"
        local resp
        resp=$(curl -sf "http://localhost:$BACKEND_PORT/api/health" 2>/dev/null) || resp=""
        if [[ -n "$resp" ]]; then
            echo -e "${GREEN}$resp${NC}"
        else
            echo -e "${RED}无响应${NC}"
        fi
    fi
    echo ""
}

# --------------- 日志 ---------------
do_logs() {
    local target="${1:-all}" lines="${2:-30}"
    ensure_dirs

    case "$target" in
        backend|be)
            info "后端日志 (最近 $lines 行):"
            tail -n "$lines" "$BACKEND_LOG" 2>/dev/null || warn "无后端日志"
            ;;
        frontend|fe)
            info "前端日志 (最近 $lines 行):"
            tail -n "$lines" "$FRONTEND_LOG" 2>/dev/null || warn "无前端日志"
            ;;
        *)
            info "后端日志 (最近 $lines 行):"
            tail -n "$lines" "$BACKEND_LOG" 2>/dev/null || warn "无后端日志"
            echo "---"
            info "前端日志 (最近 $lines 行):"
            tail -n "$lines" "$FRONTEND_LOG" 2>/dev/null || warn "无前端日志"
            ;;
    esac
}

# --------------- 入口 ---------------
usage() {
    echo ""
    echo "用法: $0 <命令> [参数]"
    echo ""
    echo "命令:"
    echo "  start             启动后端 + 前端"
    echo "  stop              停止所有服务"
    echo "  restart           重启所有服务"
    echo "  status            查看服务状态 + 健康检查"
    echo "  logs [be|fe] [N]  查看日志 (默认全部, 最近30行)"
    echo ""
    echo "环境变量:"
    echo "  QTRADER_PORT      后端端口 (默认 8000)"
    echo "  QTRADER_FE_PORT   前端端口 (默认 5173)"
    echo "  QTRADER_HOST      后端地址 (默认 0.0.0.0)"
    echo ""
    echo "示例:"
    echo "  $0 start          # 启动所有服务"
    echo "  $0 status         # 查看状态"
    echo "  $0 logs be 50     # 查看后端最近50行日志"
    echo "  $0 stop           # 停止所有服务"
    echo ""
}

case "${1:-}" in
    start)   do_start ;;
    stop)    do_stop ;;
    restart) do_restart ;;
    status)  do_status ;;
    logs)    do_logs "${2:-all}" "${3:-30}" ;;
    *)       usage ;;
esac
