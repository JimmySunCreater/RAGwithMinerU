#!/bin/bash

echo "开始安装 MinerU API 服务..."

# 检测操作系统类型和用户
detect_os_and_user() {
    if [ -f /etc/os-release ]; then
        . /etc/os-release
        OS_TYPE=$ID
        echo "检测到操作系统类型: $OS_TYPE"
        
        # 确定默认用户
        if [[ "$OS_TYPE" == "ubuntu" ]]; then
            DEFAULT_USER="ubuntu"
        else
            DEFAULT_USER="ec2-user"
        fi
        
        # 检查当前用户
        CURRENT_USER=$(whoami)
        if [[ "$CURRENT_USER" == "root" ]]; then
            # 如果是root用户，尝试确定实际用户
            SUDO_USER_NAME=${SUDO_USER:-$DEFAULT_USER}
            echo "当前以root身份运行，将使用 $SUDO_USER_NAME 作为目标用户"
        else
            SUDO_USER_NAME=$CURRENT_USER
            echo "当前以 $SUDO_USER_NAME 身份运行"
        fi
        
        # 设置用户主目录
        USER_HOME=$(eval echo ~$SUDO_USER_NAME)
        echo "用户主目录: $USER_HOME"
    else
        echo "无法检测操作系统类型，将使用默认设置"
        OS_TYPE="unknown"
        DEFAULT_USER="ec2-user"
        SUDO_USER_NAME=$DEFAULT_USER
        USER_HOME="/home/$DEFAULT_USER"
    fi
}

# 安装系统依赖
install_system_dependencies() {
    echo "安装系统依赖..."
    if [[ "$OS_TYPE" == "ubuntu" ]]; then
        sudo apt-get update
        sudo apt-get install -y wget python3-pip mesa-libgl
    else
        # Amazon Linux 或其他 RHEL 系列
        sudo yum update -y
        sudo yum install -y wget python3-pip mesa-libGL
    fi
    echo "系统依赖安装完成"
}

# 更新 hosts 文件
echo "0. 更新 hosts 文件以访问 GitHub..."
wget --timeout=30 --tries=3 --waitretry=5 -O - https://raw.hellogithub.com/hosts | sudo tee -a /etc/hosts
echo "   hosts 文件更新完成"

# 检测操作系统和用户
detect_os_and_user

# 安装系统依赖
install_system_dependencies

# 安装 Miniconda
echo "1. 安装 Miniconda..."
wget --timeout=30 --tries=3 --waitretry=5 https://repo.anaconda.com/miniconda/Miniconda3-latest-Linux-x86_64.sh -O ~/miniconda.sh
# 使用 -u 参数确保更新已存在的安装
bash ~/miniconda.sh -b -u -p $USER_HOME/miniconda

# 添加 conda 到当前会话的 PATH
export PATH="$USER_HOME/miniconda/bin:$PATH"

# 确保 conda 目录权限正确
echo "1.1. 修正 Miniconda 目录权限..."
sudo chown -R $SUDO_USER_NAME:$SUDO_USER_NAME $USER_HOME/miniconda
echo "   Miniconda 目录权限修正完成"

# 初始化 conda 并添加到 .bashrc
echo "2. 初始化 Conda 并添加到启动项..."
$USER_HOME/miniconda/bin/conda init bash

# 确保当前会话可以使用 conda 命令
source ~/.bashrc

# 检查 conda 安装
echo "3. 验证 conda 安装..."
conda --version
echo "   Conda 安装完成"

# 创建并激活 conda 环境
echo "4. 创建并激活 mineru 环境..."
conda create -n mineru python=3.10 -y
source $USER_HOME/miniconda/bin/activate mineru
echo "   mineru 环境创建并激活完成"

# 再次确保权限正确（环境创建后）
echo "4.1. 再次确保权限正确..."
sudo chown -R $SUDO_USER_NAME:$SUDO_USER_NAME $USER_HOME/miniconda
echo "   权限确认完成"

# 安装 pip 和必要的 Python 包
echo "4.2. 安装 pip 和必要的 Python 包..."
source $USER_HOME/miniconda/bin/activate mineru
pip install boto3 flask
echo "   pip 和必要的 Python 包安装完成"

# 安装依赖包
echo "5. 安装依赖包..."
pip install -U "magic-pdf[full]" --extra-index-url https://wheels.myhloli.com -i https://mirrors.aliyun.com/pypi/simple
echo "   依赖包安装完成"

# 安装 modelscope 并下载预训练模型
echo "5.1. 安装 modelscope..."
pip install modelscope
echo "    modelscope 安装完成"

echo "5.2. 下载模型下载脚本..."
wget https://gcore.jsdelivr.net/gh/opendatalab/MinerU@master/scripts/download_models.py -O download_models.py
echo "    下载脚本获取完成"

echo "5.3. 执行模型下载..."
source $USER_HOME/miniconda/bin/activate mineru
python download_models.py
echo "    模型下载完成"

# 创建目标目录（如果不存在）
echo "6. 创建目标目录 /opt/mineru_service/..."
sudo mkdir -p /opt/mineru_service/
echo "   目录创建完成"

# 下载 lambda_api.py 到目标目录
echo "7. 下载 lambda_api.py..."
if ! sudo wget --timeout=30 --tries=3 --waitretry=5 -O /opt/mineru_service/lambda_api.py https://raw.githubusercontent.com/JimmySunCreater/RAGwithMinerU/main/lambda_api.py; then
    echo "   从 GitHub 下载失败，尝试从备用源下载..."
    sudo wget --timeout=30 --tries=3 --waitretry=5 -O /opt/mineru_service/lambda_api.py https://d3d2iaoi1ibop8.cloudfront.net/lambda_api.py
fi
echo "   lambda_api.py 下载完成"

# 下载 start_mineru_api.sh 到目标目录
echo "8. 下载 start_mineru_api.sh..."
if ! sudo wget --timeout=30 --tries=3 --waitretry=5 -O /opt/mineru_service/start_mineru_api.sh https://raw.githubusercontent.com/JimmySunCreater/RAGwithMinerU/main/start_mineru_api.sh; then
    echo "   从 GitHub 下载失败，尝试从备用源下载..."
    sudo wget --timeout=30 --tries=3 --waitretry=5 -O /opt/mineru_service/start_mineru_api.sh https://d3d2iaoi1ibop8.cloudfront.net/start_mineru_api.sh
fi
echo "   start_mineru_api.sh 下载完成"

# 修改 start_mineru_api.sh 以适配当前操作系统
echo "8.1. 修改 start_mineru_api.sh 以适配当前操作系统..."
if [[ "$OS_TYPE" == "ubuntu" ]]; then
    # 替换 Ubuntu 用户路径
    sudo sed -i "s|/home/ec2-user|/home/ubuntu|g" /opt/mineru_service/start_mineru_api.sh
    echo "   已将 start_mineru_api.sh 中的路径从 /home/ec2-user 修改为 /home/ubuntu"
else
    echo "   当前为 Amazon Linux，无需修改 start_mineru_api.sh 中的路径"
fi

# 添加执行权限
echo "9. 添加执行权限..."
sudo chmod +x /opt/mineru_service/start_mineru_api.sh
echo "   执行权限添加完成"

# 修改 start_mineru_api.sh 以包含正确的 conda 路径
echo "10. 更新启动脚本中的 conda 路径..."
sudo sed -i "s|conda activate|source $USER_HOME/miniconda/bin/activate|g" /opt/mineru_service/start_mineru_api.sh
echo "    启动脚本更新完成"

# 下载服务配置文件
echo "11. 下载服务配置文件..."
if ! sudo wget --timeout=30 --tries=3 --waitretry=5 -O /etc/systemd/system/mineru-api.service https://raw.githubusercontent.com/JimmySunCreater/RAGwithMinerU/main/mineru-api.service; then
    echo "    从 GitHub 下载失败，尝试从备用源下载..."
    sudo wget --timeout=30 --tries=3 --waitretry=5 -O /etc/systemd/system/mineru-api.service https://d3d2iaoi1ibop8.cloudfront.net/mineru-api.service
fi
echo "    服务配置文件下载完成"

# 修改服务文件以适配当前操作系统
echo "11.1. 修改服务文件以适配当前操作系统..."
if [[ "$OS_TYPE" == "ubuntu" ]]; then
    # 替换 Ubuntu 用户和组
    sudo sed -i "s/User=ec2-user/User=ubuntu/g" /etc/systemd/system/mineru-api.service
    sudo sed -i "s/Group=ec2-user/Group=ubuntu/g" /etc/systemd/system/mineru-api.service
    # 替换 ExecStart 中的路径
    sudo sed -i "s|/home/ec2-user|/home/ubuntu|g" /etc/systemd/system/mineru-api.service
    echo "    已将服务文件中的用户从 ec2-user 修改为 ubuntu，并更新了路径"
else
    echo "    当前为 Amazon Linux，无需修改服务文件中的用户和路径"
fi

# 更新服务文件以使用完整路径
echo "12. 更新服务文件中的路径..."
sudo sed -i "/^ExecStart=/c\ExecStart=/bin/bash -c \"source $USER_HOME/miniconda/bin/activate mineru && python3 /opt/mineru_service/lambda_api.py\"" /etc/systemd/system/mineru-api.service
# 更新服务文件中的用户
sudo sed -i "s/User=ec2-user/User=$SUDO_USER_NAME/g" /etc/systemd/system/mineru-api.service
echo "    服务文件更新完成"

# 确认 magic-pdf 安装路径
echo "12.1. 确认 magic-pdf 安装路径..."
MAGIC_PDF_PATH=$(find $USER_HOME/miniconda -name "magic-pdf" | head -1)

if [ -z "$MAGIC_PDF_PATH" ]; then
    echo "    找不到 magic-pdf 可执行文件，请检查安装是否完成"
    echo "    将使用 lambda_api.py 中的自动检测功能查找 magic-pdf"
else
    echo "    找到 magic-pdf 路径: $MAGIC_PDF_PATH"
    echo "    lambda_api.py 将自动检测并使用正确的 magic-pdf 路径"
fi

# 重新加载 systemd 配置
echo "13. 重新加载 systemd 配置..."
sudo systemctl daemon-reload
echo "    systemd 配置加载完成"

# 启用服务（设置开机自启动）
echo "14. 启用 mineru-api 服务开机自启动..."
sudo systemctl enable mineru-api.service
echo "    服务自启动设置完成"

# 启动服务
echo "15. 启动 mineru-api 服务..."
sudo systemctl start mineru-api.service
echo "    服务已启动"

# 检查服务状态
echo "16. 检查服务状态..."
sudo systemctl status mineru-api.service --no-pager
echo "    状态检查完成"

echo "17. 安装完成！MinerU API 服务已成功配置并启动"
echo "重要提示：请注意，如果您在新会话中需要使用 conda 命令，请先执行 'source ~/.bashrc'"
