#!/bin/bash

# 检测操作系统类型
detect_os() {
    if [ -f /etc/os-release ]; then
        . /etc/os-release
        OS_NAME=$ID
    elif [ -f /etc/lsb-release ]; then
        . /etc/lsb-release
        OS_NAME=$DISTRIB_ID
    else
        OS_NAME=$(uname -s)
    fi
    echo $OS_NAME | tr '[:upper:]' '[:lower:]'
}

# 获取当前用户
get_user_home() {
    OS=$(detect_os)
    if [[ "$OS" == *"ubuntu"* ]]; then
        echo "/home/ubuntu"
    else
        # 默认为 Amazon Linux
        echo "/home/ec2-user"
    fi
}

# 设置用户主目录
USER_HOME=$(get_user_home)

# 设置日志文件
LOG_FILE="$USER_HOME/logs/mineru_api.log"
mkdir -p "$(dirname "$LOG_FILE")"

# 日志函数
log() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') - $1" | tee -a "$LOG_FILE"
}

# 检查必要的目录和文件
CONDA_PATH="$USER_HOME/miniconda"
SERVICE_DIR="/opt/mineru_service"
API_SCRIPT="$SERVICE_DIR/lambda_api.py"

# 检查 conda 安装
if [ ! -f "$CONDA_PATH/etc/profile.d/conda.sh" ]; then
    log "错误: 找不到 conda.sh 在 $CONDA_PATH/etc/profile.d/conda.sh"
    exit 1
fi

# 检查服务目录
if [ ! -d "$SERVICE_DIR" ]; then
    log "错误: 找不到服务目录 $SERVICE_DIR"
    exit 1
fi

# 检查 API 脚本
if [ ! -f "$API_SCRIPT" ]; then
    log "错误: 找不到 API 脚本 $API_SCRIPT"
    exit 1
fi

# 初始化 conda
log "初始化 conda..."
source "$CONDA_PATH/etc/profile.d/conda.sh"

# 激活环境
log "激活 mineru 环境..."
conda activate mineru

# 检查环境是否成功激活
if [ "$CONDA_DEFAULT_ENV" != "mineru" ]; then
    log "错误: 无法激活 mineru 环境"
    exit 1
fi

# 切换到服务目录
log "切换到服务目录 $SERVICE_DIR..."
cd "$SERVICE_DIR"

# 启动 API 服务
log "启动 API 服务..."
python3 "$API_SCRIPT"