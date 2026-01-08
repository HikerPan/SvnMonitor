#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
发送服务启动通知邮件的脚本
当svnmonitor服务启动时，该脚本会被调用，发送启动通知邮件
"""

import datetime
import os
import sys
import logging

# 设置日志
logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                    handlers=[
                        logging.FileHandler('/home/alex/aidev/SvnMonitor/logs/send_startup_email.log'),
                        logging.StreamHandler()
                    ])
logger = logging.getLogger(__name__)

# 添加脚本所在目录到Python路径
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# 导入邮件发送所需的模块
from send_failure_email import send_email

def send_startup_notification():
    """
    发送服务启动通知邮件
    
    :return: bool: 是否发送成功
    """
    # 获取当前时间
    current_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    # 邮件主题
    subject = f"SVN监控服务启动通知 - {current_time}"
    
    # 邮件内容
    content = f"""SVN监控服务已成功启动！

启动时间: {current_time}

服务信息：
- 服务名称：SVN Monitor
- 监控模式：自动检测
- 工作目录：/home/alex/aidev/SvnMonitor

服务将持续监控所有配置的SVN仓库变更。
如有任何问题，请查看系统日志或联系管理员。
"""
    
    # 发送邮件
    return send_email(subject, content)


if __name__ == "__main__":
    logger.info("=== SVN监控服务启动通知 ===")
    success = send_startup_notification()
    
    if success:
        logger.info("服务启动通知邮件发送成功！")
        sys.exit(0)
    else:
        logger.error("服务启动通知邮件发送失败！")
        sys.exit(1)