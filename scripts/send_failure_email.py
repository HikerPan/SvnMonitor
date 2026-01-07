#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
发送服务失败提醒邮件的脚本
当svnmonitor服务失败时，该脚本会被systemd调用，发送提醒邮件
"""

import datetime
import subprocess
import sys
import os
import smtplib
import logging
import configparser
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# 设置日志
logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                    handlers=[
                        logging.FileHandler('/home/alex/aidev/SvnMonitor/logs/send_failure_email.log'),
                        logging.StreamHandler()
                    ])
logger = logging.getLogger(__name__)


def _load_config_from_excel(config_file):
    """
    从Excel配置文件加载邮件配置
    
    :param config_file: Excel配置文件路径
    :return: configparser.ConfigParser对象，如果加载失败则返回None
    """
    config = configparser.ConfigParser()
    
    try:
        import pandas as pd
        
        if not os.path.exists(config_file):
            logger.error(f"Excel配置文件不存在: {config_file}")
            return None
        
        # 读取全局配置
        global_df = pd.read_excel(config_file, sheet_name='Global Configs')
        
        for _, row in global_df.iterrows():
            try:
                section = str(row['Section'])
                key = str(row['Key'])
                value = str(row['Value'])
                
                if section not in config:
                    config.add_section(section)
                config.set(section, key, value)
            except Exception as e:
                logger.error(f"解析配置行失败: {row}, 错误: {str(e)}")
        
        return config
    except ImportError:
        logger.error("pandas库未安装，无法读取Excel配置文件")
        return None
    except Exception as e:
        logger.error(f"从Excel加载配置失败: {str(e)}")
        return None


def _send_email(msg, config):
    """
    内部邮件发送方法，包含重试逻辑
    
    :param msg: 邮件消息对象
    :param config: 配置对象
    :return: bool: 是否发送成功
    """
    try:
        # 检查是否有SMTP凭证
        has_credentials = False
        if 'username' in config['EMAIL'] and 'password' in config['EMAIL']:
            username = config['EMAIL'].get('username', '').strip()
            password = config['EMAIL'].get('password', '').strip()
            has_credentials = bool(username) and bool(password)
        
        # 发送邮件，带重试逻辑
        smtp_server = config['EMAIL']['smtp_server']
        smtp_port = int(config['EMAIL'].get('smtp_port', '465'))
        use_ssl = config['EMAIL'].get('use_ssl', 'True').lower() == 'true'
        max_retries = 2
        retry_count = 0
        success = False
        
        while retry_count <= max_retries and not success:
            try:
                if use_ssl:
                    server = smtplib.SMTP_SSL(smtp_server, smtp_port, timeout=30)
                else:
                    server = smtplib.SMTP(smtp_server, smtp_port, timeout=30)
                    server.starttls()
                
                # 只有在有完整凭证时才尝试登录
                if has_credentials:
                    try:
                        username = config['EMAIL'].get('username', '').strip()
                        password = config['EMAIL'].get('password', '').strip()
                        if username and password:  # 再次检查安全性
                            server.login(username, password)
                    except smtplib.SMTPAuthenticationError:
                        logger.error(f"SMTP认证失败 (尝试 {retry_count + 1}/{max_retries + 1})")
                        retry_count += 1
                        import time
                        time.sleep(2)  # 重试前等待
                        continue
                else:
                    logger.info("跳过SMTP认证，因为未提供有效凭证")
                
                # 提取收件人列表
                recipients_str = msg['To']
                recipients_list = [r.strip() for r in recipients_str.split(',') if r.strip()]
                
                # 发送邮件
                server.send_message(msg, to_addrs=recipients_list)
                server.quit()
                success = True
                logger.info(f"邮件发送成功，收件人: {recipients_str}")
                return True
            except smtplib.SMTPException as e:
                logger.error(f"SMTP发送错误: {str(e)} (尝试 {retry_count + 1}/{max_retries + 1})")
                retry_count += 1
                import time
                time.sleep(2)  # 重试前等待
            except Exception as e:
                logger.error(f"发送邮件时发生意外错误: {str(e)}")
                break
        
        if not success:
            logger.error("多次尝试后仍无法发送邮件")
            return False
    except Exception as e:
        logger.error(f"_send_email方法出错: {str(e)}")
        return False


def send_email(subject, content):
    """
    发送邮件函数
    
    :param subject: 邮件主题
    :param content: 邮件内容
    :return: bool: 是否发送成功
    """
    # 获取配置文件路径
    config_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'config', 'svn_monitor_config.xlsx')
    
    # 加载配置
    config = _load_config_from_excel(config_path)
    if config is None:
        logger.error("无法加载配置文件，邮件发送失败")
        return False
    
    # 检查邮件配置是否完整
    if 'EMAIL' not in config or not all([
        'smtp_server' in config['EMAIL'],
        'from_email' in config['EMAIL'],
        'to_emails' in config['EMAIL']
    ]):
        logger.error("邮件配置不完整，缺少必要的SMTP参数")
        return False
    
    # 检查SMTP凭证
    has_credentials = False
    if 'username' in config['EMAIL'] and 'password' in config['EMAIL']:
        username = config['EMAIL'].get('username', '').strip()
        password = config['EMAIL'].get('password', '').strip()
        has_credentials = bool(username) and bool(password)
    
    if not has_credentials:
        logger.error("SMTP凭证不完整，无法发送邮件")
        return False
    
    # 获取收件人列表
    to_emails = config['EMAIL'].get('to_emails', '').strip()
    if not to_emails:
        logger.error("收件人列表为空")
        return False
    
    # 构建HTML邮件内容
    html_content = f"""
    <html>
    <body>
        <h2>SVN监控服务状态通知</h2>
        <p>{subject}</p>
        <pre style="background-color: #f5f5f5; padding: 10px; border-radius: 5px; font-family: monospace;">
{content}
        </pre>
    </body>
    </html>
    """
    
    # 创建邮件对象
    msg = MIMEMultipart('alternative')
    msg['From'] = config['EMAIL']['from_email']
    msg['To'] = to_emails
    msg['Subject'] = subject
    
    # 添加邮件正文（HTML和纯文本）
    plain_text = content  # 纯文本版本
    msg.attach(MIMEText(plain_text, 'plain'))
    msg.attach(MIMEText(html_content, 'html'))
    
    # 发送邮件
    return _send_email(msg, config)


def get_service_status():
    """
    获取服务状态信息
    :return: 服务状态信息字符串
    """
    try:
        # 获取服务状态
        result = subprocess.run(
            ['systemctl', 'status', 'svnmonitor.service'],
            capture_output=True,
            text=True,
            encoding='utf-8'
        )
        status_info = result.stdout

        # 获取服务日志
        logs = subprocess.run(
            ['journalctl', '-u', 'svnmonitor.service', '-n', '20'],
            capture_output=True,
            text=True,
            encoding='utf-8'
        )
        log_info = logs.stdout

        return f"服务状态:\n{status_info}\n\n最近20条日志:\n{log_info}"
    except Exception as e:
        return f"获取服务状态失败: {str(e)}"


if __name__ == "__main__":
    import sys
    
    # 检查是否是测试模式
    is_test = len(sys.argv) > 1 and sys.argv[1] == '--test'
    
    # 获取当前时间
    current_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    if is_test:
        # 测试模式
        subject = f"SVN监控服务测试邮件 - {current_time}"
        content = f"""这是一封测试邮件，用于验证SVN监控服务的邮件发送功能是否正常。

发送时间: {current_time}

如果您收到这封邮件，说明邮件发送功能已配置成功。"""
        print("=== SVN监控服务邮件测试 ===")
    else:
        # 正常模式 - 服务失败提醒
        subject = f"SVN监控服务运行失败提醒 - {current_time}"
        content = f"""SVN监控服务于 {current_time} 运行失败！

请尽快检查服务状态，以下是详细信息：

{get_service_status()}

请及时处理，确保SVN监控服务正常运行。"""

    # 发送邮件
    success = send_email(subject, content)
    
    if is_test:
        if success:
            print("测试邮件发送成功！")
        else:
            print("测试邮件发送失败，请检查系统邮件配置。")
        sys.exit(0 if success else 1)