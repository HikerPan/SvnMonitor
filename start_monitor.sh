#!/bin/bash

# 激活虚拟环境
source venv/bin/activate

# 设置SSL配置
# 获取脚本的绝对路径
SCRIPT_PATH="$(readlink -f "$0")"
SCRIPT_DIR="$(dirname "$SCRIPT_PATH")"
export OPENSSL_CONF="$SCRIPT_DIR/ssl_config.cnf"


# 检查环境变量是否正确设置
echo "当前OPENSSL_CONF: $OPENSSL_CONF"
python -c "import os; print('Python进程OPENSSL_CONF:', os.environ.get('OPENSSL_CONF'))"

# 发送服务启动通知邮件
echo "发送服务启动通知邮件..."
python scripts/send_startup_email.py

# 进入src目录并启动程序
cd src
python -c "import os; print('Python进程(在src目录)OPENSSL_CONF:', os.environ.get('OPENSSL_CONF'))"
python svn_monitor.py