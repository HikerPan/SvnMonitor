#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
SVN Monitor Script
This script monitors SVN repository changes, sends email notifications,
performs backup and restore operations, and maintains operation logs.
"""

import os
import sys
import time
import subprocess
import xml.etree.ElementTree as ET
import logging
import configparser
import datetime
import smtplib
import re
import signal
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from logging.handlers import RotatingFileHandler

# 导入时区处理模块
try:
    # Python 3.9+ 推荐使用zoneinfo
    from zoneinfo import ZoneInfo
except ImportError:
    # 兼容旧版本Python
    try:
        import pytz
    except ImportError:
        pytz = None

# 定义北京时间时区
def get_beijing_time():
    """获取北京时间（UTC+8）"""
    now = datetime.datetime.now()
    # 尝试使用zoneinfo（Python 3.9+）
    if 'ZoneInfo' in globals():
        return now.astimezone(ZoneInfo('Asia/Shanghai'))
    # 尝试使用pytz
    elif pytz:
        if now.tzinfo is None:
            # 如果没有时区信息，先设为UTC
            now = pytz.UTC.localize(now)
        return now.astimezone(pytz.timezone('Asia/Shanghai'))
    # 如果都不可用，至少记录当前使用的是系统时区
    logging.warning("无法设置北京时间时区，使用系统默认时区")
    return now

# 获取北京时间的格式化字符串
def get_beijing_time_str(format_str='%Y-%m-%d %H:%M:%S'):
    """获取格式化的北京时间字符串"""
    return get_beijing_time().strftime(format_str)

# 尝试导入pandas用于读取Excel文件
try:
    import pandas as pd
except ImportError:
    pd = None
    logging.warning("pandas库未安装，将使用默认收件人配置。如需使用Excel收件人功能，请安装pandas: pip install pandas openpyxl")

def setup_logging(config=None):
    """Setup logging based on configuration"""
    # Default log settings
    log_file = 'svn_monitor.log'
    log_level = logging.INFO
    
    # 确保日志使用北京时间
    if 'ZoneInfo' in globals():
        # 为logging设置时区
        logging.Formatter.converter = lambda *args: datetime.datetime.now(ZoneInfo('Asia/Shanghai')).timetuple()
    elif pytz:
        # 使用pytz设置时区
        logging.Formatter.converter = lambda *args: datetime.datetime.now(pytz.timezone('Asia/Shanghai')).timetuple()
    
    # Override with config values if available
    if config and 'LOGGING' in config:
        log_file = config['LOGGING'].get('log_file', log_file)
        log_level_str = config['LOGGING'].get('log_level', 'INFO').upper()
        log_level = getattr(logging, log_level_str, logging.INFO)
    
    # Ensure log file path is absolute
    if not os.path.isabs(log_file):
        # Get the directory of the script or current working directory
        base_dir = os.path.dirname(os.path.abspath(sys.argv[0])) if sys.argv else os.getcwd()
        log_file = os.path.normpath(os.path.join(base_dir, log_file))
    
    # Ensure log directory exists
    log_dir = os.path.dirname(log_file)
    if log_dir and not os.path.exists(log_dir):
        os.makedirs(log_dir, exist_ok=True)
    
    # Configure logging
    numeric_level = getattr(logging, logging.getLevelName(log_level), logging.INFO)
    
    # Create logger
    logger = logging.getLogger(__name__)
    logger.setLevel(numeric_level)
    
    # Clear existing handlers if any
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)
    
    # Create handlers
    handlers = []
    
    # File handler for detailed logging
    file_handler = RotatingFileHandler(
        log_file,
        maxBytes=10*1024*1024,  # 10MB
        backupCount=5
    )
    file_handler.setLevel(numeric_level)
    file_handler.setFormatter(logging.Formatter(
        '%(asctime)s - %(levelname)s - %(module)s - %(funcName)s - %(message)s'
    ))
    handlers.append(file_handler)
    
    # Stream handler for console output
    stream_handler = logging.StreamHandler()
    stream_handler.setLevel(numeric_level)
    stream_handler.setFormatter(logging.Formatter(
        '%(asctime)s - %(levelname)s - %(message)s'
    ))
    handlers.append(stream_handler)
    
    # Add handlers to logger
    for handler in handlers:
        logger.addHandler(handler)
    
    return logger

# Initialize logger with default settings
logger = setup_logging()

# 默认配置常量
DEFAULT_CHECK_INTERVAL = 300  # 默认检查间隔（秒）

class SVNMonitor:
    """SVN Monitor class to handle SVN operations, monitoring, backup and restore"""
    
    def __init__(self):
        """Initialize SVN Monitor with configuration from Excel file"""
        # 使用Excel作为唯一配置源
        # 使用项目根目录的config目录中的配置文件
        base_dir = os.path.dirname(os.path.abspath(sys.argv[0])) if sys.argv else os.getcwd()
        # 如果当前在src目录，需要向上退一级到项目根目录
        if os.path.basename(base_dir) == 'src':
            base_dir = os.path.dirname(base_dir)
        self.config_file = os.path.join(base_dir, 'config', 'svn_monitor_config.xlsx')
        self.config = self._load_config()
        self._validate_config()
        self.repositories = self._get_repositories()
        # Convert relative paths to absolute paths in repository configurations
        self._convert_relative_paths()
        self.last_revisions = self._get_last_recorded_revisions()
        # 加载仓库名称映射关系（动态从Excel读取）
        self.repo_name_mapping = self._load_repo_name_mapping()
        # 加载收件人信息
        self.recipients_mapping = self._load_recipients_from_excel()
        # 初始化远程检测模式配置
        self.use_remote_check = self._get_remote_check_setting()
        
        # 设置程序运行标志和信号处理
        self.running = True
        signal.signal(signal.SIGTERM, self._handle_sigterm)
        signal.signal(signal.SIGINT, self._handle_sigterm)
        
        logger.info(f"SVN Monitor initialized with {len(self.repositories)} repositories, remote check mode: {self.use_remote_check}")
    
    def _load_config(self):
        """Load configuration from Excel file only"""
        config = configparser.ConfigParser()
        
        # Load from Excel config file
        if os.path.exists(self.config_file):
            logger.info(f"Loading configuration from Excel file: {self.config_file}")
            success = self._load_config_from_excel(config, self.config_file)
            if success:
                return config
            else:
                logger.error("Failed to load configuration from Excel, creating default configuration")
        else:
            logger.warning(f"Configuration Excel file {self.config_file} not found. Creating default configuration.")
        
        # Create default Excel configuration if it doesn't exist
        self._create_default_config()
        
        # Try to load the newly created configuration
        success = self._load_config_from_excel(config, self.config_file)
        if success:
            return config
        else:
            # If all else fails, return a minimal default config
            logger.error("Failed to create or load default configuration. Using minimal fallback config.")
            return self._create_minimal_config()
    
    def _load_config_from_excel(self, config, excel_file):
        """Load configuration from Excel file and populate the config object"""
        try:
            import pandas as pd
            
            # 首先检查Excel文件是否存在
            if not os.path.exists(excel_file):
                logger.warning(f"Excel configuration file does not exist: {excel_file}")
                return False
            
            # Try to load repository configs sheet
            try:
                repo_df = pd.read_excel(excel_file, sheet_name='Repository Configs')
                
                # Process each repository configuration
                for _, row in repo_df.iterrows():
                    repo_id = row.get('Repository ID')
                    if repo_id:
                        if repo_id not in config:
                            config.add_section(repo_id)
                        
                        # Map Excel columns to INI keys
                        if pd.notna(row.get('Repository Name')):
                            config.set(repo_id, 'name', str(row.get('Repository Name')))
                        if pd.notna(row.get('Repository Path')):
                            config.set(repo_id, 'repository_path', str(row.get('Repository Path')))
                        if pd.notna(row.get('URL')):
                            config.set(repo_id, 'url', str(row.get('URL')))
                        if pd.notna(row.get('Username')):
                            config.set(repo_id, 'username', str(row.get('Username')))
                        if pd.notna(row.get('Password')):
                            config.set(repo_id, 'password', str(row.get('Password')))
                        if pd.notna(row.get('Check Interval')):
                            config.set(repo_id, 'check_interval', str(row.get('Check Interval')))
                        if pd.notna(row.get('Local Working Copy')):
                            config.set(repo_id, 'local_working_copy', str(row.get('Local Working Copy')))
                        if pd.notna(row.get('Notify On Changes')):
                            config.set(repo_id, 'notify_on_changes', str(row.get('Notify On Changes')))
            except Exception as e:
                logger.warning(f"Error loading repository configs from Excel: {str(e)}")
            
            # Try to load global configs sheet
            try:
                global_df = pd.read_excel(excel_file, sheet_name='Global Configs')
                
                for _, row in global_df.iterrows():
                    section = row.get('Section')
                    key = row.get('Key')
                    value = row.get('Value')
                    
                    if section and key is not None and pd.notna(key):
                        if section not in config:
                            config.add_section(section)
                        config.set(section, key, str(value))
            except Exception as e:
                logger.warning(f"Error loading global configs from Excel: {str(e)}")
            
            # 检查是否成功加载了任何配置
            if len(config.sections()) > 0:
                logger.info("Configuration successfully loaded from Excel file")
                return True
            else:
                logger.warning("No configuration sections were loaded from Excel file")
                return False
            
        except ImportError:
            logger.error("pandas library not installed. Cannot read Excel configuration.")
            return False
        except Exception as e:
            logger.error(f"Error loading configuration from Excel: {str(e)}")
            return False
    
    def _create_default_config(self):
        """Create default configuration Excel file instead of INI"""
        try:
            import pandas as pd
            
            # 确保配置目录存在
            config_dir = os.path.dirname(self.config_file)
            if not os.path.exists(config_dir):
                os.makedirs(config_dir, exist_ok=True)
                logger.info(f"Created configuration directory: {config_dir}")
            
            # 创建仓库配置数据 - 使用更合理的默认值
            repo_data = {
                'Repository ID': ['REPO_1'],
                'Repository Name': ['Demo Repository'],
                'Repository Path': ['https://svn.apache.org/repos/asf/subversion/trunk'],
                'URL': ['https://svn.apache.org/repos/asf/subversion/trunk'],
                'Username': [''],
                'Password': [''],
                'Check Interval': [DEFAULT_CHECK_INTERVAL],
                'Local Working Copy': [os.path.join(os.path.dirname(self.config_file), '..', 'svn_wc', 'repo_1')],
                'Notify On Changes': [False],
                'Recipients': ['admin@example.com']
            }
            
            # 创建全局配置数据
            global_data = {
                'Section': ['EMAIL', 'EMAIL', 'EMAIL', 'EMAIL', 'EMAIL', 'EMAIL', 'EMAIL', 'LOGGING', 'LOGGING', 'SYSTEM', 'SYSTEM', 'SYSTEM'],
                'Key': ['smtp_server', 'smtp_port', 'use_ssl', 'username', 'password', 'from_email', 'to_emails', 'log_file', 'log_level', 'auto_startup', 'mode', 'use_remote_check'],
                'Value': ['smtp.example.com', '465', 'True', 'svn@example.com', 'your_password', 'svn@example.com', 'admin@example.com', 'svn_monitor.log', 'INFO', 'True', 'monitor', 'False']
            }
            
            # 创建DataFrame
            repo_df = pd.DataFrame(repo_data)
            global_df = pd.DataFrame(global_data)
            
            # 保存为Excel文件
            with pd.ExcelWriter(self.config_file, engine='openpyxl') as writer:
                repo_df.to_excel(writer, sheet_name='Repository Configs', index=False)
                global_df.to_excel(writer, sheet_name='Global Configs', index=False)
            
            logger.info(f"Default configuration Excel created at {self.config_file}")
            return True
        except ImportError:
            logger.error("pandas library not installed. Cannot create Excel configuration.")
            return False
        except Exception as e:
            logger.error(f"Failed to create default configuration Excel: {str(e)}")
            return False
    
    def _create_minimal_config(self):
        """Create minimal fallback configuration when Excel creation fails"""
        config = configparser.ConfigParser()
        
        config.add_section('SVN')
        config.set('SVN', 'url', 'https://svn.apache.org/repos/asf/subversion/trunk')
        config.set('SVN', 'repository_path', 'https://svn.apache.org/repos/asf/subversion/trunk')
        config.set('SVN', 'username', '')
        config.set('SVN', 'password', '')
        config.set('SVN', 'check_interval', str(DEFAULT_CHECK_INTERVAL))
        config.set('SVN', 'local_working_copy', os.path.join(os.getcwd(), 'svn_wc'))
        
        config.add_section('EMAIL')
        config.set('EMAIL', 'smtp_server', 'smtp.example.com')
        config.set('EMAIL', 'smtp_port', '465')
        config.set('EMAIL', 'use_ssl', 'True')
        config.set('EMAIL', 'username', '')
        config.set('EMAIL', 'password', '')
        config.set('EMAIL', 'from_email', 'svn@example.com')
        config.set('EMAIL', 'to_emails', 'admin@example.com')
        
        config.add_section('LOGGING')
        config.set('LOGGING', 'log_file', 'svn_monitor.log')
        config.set('LOGGING', 'log_level', 'INFO')
        
        config.add_section('SYSTEM')
        config.set('SYSTEM', 'auto_startup', 'False')
        config.set('SYSTEM', 'mode', 'monitor')
        config.set('SYSTEM', 'use_remote_check', 'False')
        
        config.add_section('REPO_1')
        config.set('REPO_1', 'name', 'Default Repository')
        config.set('REPO_1', 'url', 'https://svn.apache.org/repos/asf/subversion/trunk')
        config.set('REPO_1', 'repository_path', 'https://svn.apache.org/repos/asf/subversion/trunk')
        config.set('REPO_1', 'username', '')
        config.set('REPO_1', 'password', '')
        config.set('REPO_1', 'check_interval', str(DEFAULT_CHECK_INTERVAL))
        config.set('REPO_1', 'local_working_copy', os.path.join(os.getcwd(), 'svn_wc', 'repo_1'))
        config.set('REPO_1', 'notify_on_changes', 'False')
        
        return config
    
    def _get_repositories(self):
        """Get all repository configurations from the config file"""
        repositories = {}
        for section in self.config.sections():
            if section.startswith('REPO_'):
                repo_name = section[5:]  # Remove 'REPO_' prefix
                repositories[repo_name] = self.config[section]
        return repositories
        
    def _convert_relative_paths(self):
        """Convert relative paths in configuration to absolute paths based on project directory"""
        # 使用项目目录作为基础目录（脚本所在目录）
        base_dir = os.path.dirname(os.path.abspath(sys.argv[0])) if sys.argv else os.getcwd()
        
        # 确保所有相对路径都转换为绝对路径，基于项目目录
        
        # Convert paths in main SVN section if it exists
        if 'SVN' in self.config:
            for key in ['local_working_copy', 'local_path', 'repository_path', 'url']:
                if key in self.config['SVN']:
                    path = self.config['SVN'][key]
                    # 仅对文件路径进行转换，URL类型的路径保持不变
                    if path and not os.path.isabs(path) and not (path.startswith('http://') or path.startswith('https://')):
                        self.config['SVN'][key] = os.path.normpath(os.path.join(base_dir, path))
        
        # Convert paths in each repository configuration
        for repo_name, repo_config in self.repositories.items():
            for key in ['local_working_copy', 'repository_path']:
                if key in repo_config:
                    path = repo_config[key]
                    # 仅对文件路径进行转换，URL类型的路径保持不变
                    if path and not os.path.isabs(path) and not (path.startswith('http://') or path.startswith('https://')):
                        abs_path = os.path.normpath(os.path.join(base_dir, path))
                        # Update in both the repositories dictionary and the config object
                        repo_config[key] = abs_path
                        self.config[f'REPO_{repo_name}'][key] = abs_path
        
        # Convert log file path
        if 'LOGGING' in self.config and 'log_file' in self.config['LOGGING']:
            log_file = self.config['LOGGING']['log_file']
            if log_file and not os.path.isabs(log_file):
                self.config['LOGGING']['log_file'] = os.path.normpath(os.path.join(base_dir, log_file))
        
        logger.info(f"Relative paths converted to absolute paths using base directory: {base_dir}")
    
    def _create_default_repository_config(self):
        """Create a default repository configuration"""
        self.config['REPO_1'] = {
            'name': 'Demo Repository',
            'repository_path': 'https://svn.apache.org/repos/asf/subversion/trunk',
            'username': '',
            'password': '',
            'check_interval': str(DEFAULT_CHECK_INTERVAL),  # in seconds
            'local_working_copy': os.path.join(os.getcwd(), 'svn_wc', 'repo_1'),
            'enable_notifications': 'False',
            'enable_backup': 'False'
        }
        
        # Save the updated configuration
        try:
            with open(self.config_file, 'w', encoding='utf-8') as f:
                self.config.write(f)
            logger.info("Default repository configuration created")
        except Exception as e:
            logger.error(f"Failed to save default repository configuration: {str(e)}")
    
    def _get_last_recorded_revisions(self):
        """Get the last recorded revisions for all repositories"""
        revisions = {}
        revision_file = 'last_revisions.json'
        
        if os.path.exists(revision_file):
            try:
                import json
                with open(revision_file, 'r') as f:
                    loaded_revisions = json.load(f)
                    
                # Only keep revisions for repositories that actually exist in configuration
                for repo_name in self.repositories:
                    if repo_name in loaded_revisions:
                        revisions[repo_name] = loaded_revisions[repo_name]
            except Exception as e:
                logger.error(f"Failed to read last revisions: {str(e)}")
        
        # Initialize revisions for repositories without recorded data
        for repo_name in self.repositories:
            if repo_name not in revisions:
                revisions[repo_name] = 0
        
        return revisions
    
    def _get_remote_check_setting(self):
        """获取远程检测模式配置"""
        if 'SYSTEM' in self.config and 'use_remote_check' in self.config['SYSTEM']:
            value = self.config['SYSTEM']['use_remote_check']
            return str(value).lower() in ('true', '1', 'yes', 'on')
        return False
    
    def _handle_sigterm(self, signum, frame):
        """处理终止信号(SIGTERM和SIGINT)
        
        Args:
            signum: 信号编号
            frame: 当前堆栈帧
        """
        logger.info(f"收到终止信号 {signum}，准备优雅退出")
        self.log_operation('INFO', f"SVN Monitor收到终止信号 {signum}，准备优雅退出")
        self.running = False
    
    def _save_last_revisions(self, revisions):
        """Save the last revisions for all repositories"""
        revision_file = 'last_revisions.json'
        try:
            import json
            with open(revision_file, 'w') as f:
                json.dump(revisions, f)
            logger.info(f"Last revisions updated")
        except Exception as e:
            logger.error(f"Failed to save last revisions: {str(e)}")
    
    def _load_repo_name_mapping(self):
        """动态从Excel加载仓库名称映射关系
        
        Returns:
            dict: 双向映射字典，包含英文到中文、中文到英文的映射
        """
        mapping = {}
        
        # 从完整配置Excel加载仓库信息
        if os.path.exists(self.config_file):
            try:
                import pandas as pd
                
                # 尝试从完整配置Excel加载
                repo_df = pd.read_excel(self.config_file, sheet_name='Repository Configs')
                
                # 检查是否有必要的列
                if 'Repository ID' in repo_df.columns and 'Repository Name' in repo_df.columns:
                    for _, row in repo_df.iterrows():
                        repo_id = row.get('Repository ID')
                        repo_name = row.get('Repository Name')
                        
                        if pd.notna(repo_id) and pd.notna(repo_name):
                            repo_id_str = str(repo_id).strip()
                            repo_name_str = str(repo_name).strip()
                            
                            # 添加双向映射
                            mapping[repo_id_str] = f"{repo_name_str}仓库"  # 例如：REPO_1 -> 采购仓库
                            mapping[f"{repo_name_str}仓库"] = repo_id_str  # 例如：采购仓库 -> REPO_1
                            mapping[repo_name_str] = repo_id_str  # 简写形式：采购 -> REPO_1
                
                # 添加一些常见的别名映射（向后兼容）
                mapping['Procurement'] = '采购仓库'
                mapping['Production'] = '生产仓库'
                
                logger.info(f"成功加载仓库名称映射关系: {mapping}")
            except Exception as e:
                logger.warning(f"从Excel加载仓库名称映射失败: {str(e)}")
                # 使用默认映射作为备份
                mapping = self._get_default_repo_mapping()
        else:
            # 使用默认映射作为备份
            mapping = self._get_default_repo_mapping()
            
        return mapping
    
    def _get_default_repo_mapping(self):
        """获取默认的仓库名称映射（作为备份）"""
        return {
            'REPO_1': '采购仓库',
            'REPO_2': '生产仓库',
            'REPO_3': '研发仓库',
            'REPO_4': '质量仓库',
            'REPO_5': '售后仓库',
            '采购仓库': 'REPO_1',
            '生产仓库': 'REPO_2',
            '研发仓库': 'REPO_3',
            '质量仓库': 'REPO_4',
            '售后仓库': 'REPO_5',
            '采购': 'REPO_1',
            '生产': 'REPO_2',
            '研发': 'REPO_3',
            '质量': 'REPO_4',
            '售后': 'REPO_5',
            'Procurement': '采购仓库',
            'Production': '生产仓库'
        }
    
    def _load_recipients_from_excel(self):
        """从Excel文件中加载收件人信息
        
        支持两种格式：
        1. 完整配置Excel（svn_monitor_config.xlsx）：从'Repository Configs'工作表加载
        2. 旧版收件人Excel：从第一列和第二列加载
        
        Returns:
            dict: 仓库名称到收件人列表的映射
        """
        recipients_mapping = {}
        
        # 首先检查是否存在完整配置Excel文件
        # 使用与主配置文件相同的路径
        excel_config_file = self.config_file
        if os.path.exists(excel_config_file):
            try:
                import pandas as pd
                
                # 尝试从完整配置Excel加载
                repo_df = pd.read_excel(excel_config_file, sheet_name='Repository Configs')
                
                # 检查是否有Recipients列
                if 'Recipients' in repo_df.columns:
                    for _, row in repo_df.iterrows():
                        # 获取仓库ID或名称
                        repo_id = row.get('Repository ID') or row.get('Repository Name')
                        if pd.notna(repo_id):
                            repo_name = str(repo_id).strip()
                            recipients_str = row.get('Recipients')
                            
                            if pd.notna(recipients_str):
                                # 分割多个邮箱地址
                                recipients = [email.strip() for email in str(recipients_str).split(';') if email.strip()]
                                if recipients:
                                    recipients_mapping[repo_name] = recipients
                                    logger.info(f"从完整配置Excel加载仓库 '{repo_name}' 的收件人: {', '.join(recipients)}")
                
                logger.info(f"成功从完整配置Excel加载 {len(recipients_mapping)} 个仓库的收件人信息")
                return recipients_mapping
                
            except Exception as e:
                logger.warning(f"从完整配置Excel加载收件人失败: {str(e)}，尝试使用旧版收件人配置")
        
        # 如果完整配置Excel不存在或加载失败，尝试使用旧版收件人Excel
        if 'EMAIL' in self.config and 'recipients_excel' in self.config['EMAIL']:
            excel_path = self.config['EMAIL']['recipients_excel']
            
            # 确保路径是绝对路径
            if not os.path.isabs(excel_path):
                base_dir = os.path.dirname(os.path.abspath(self.config_file))
                excel_path = os.path.normpath(os.path.join(base_dir, excel_path))
            
            # 检查pandas是否已安装
            if pd is None:
                logger.warning(f"pandas库未安装，无法读取收件人Excel文件: {excel_path}")
                return recipients_mapping
            
            # 检查文件是否存在
            if not os.path.exists(excel_path):
                logger.warning(f"收件人Excel文件不存在: {excel_path}")
                return recipients_mapping
            
            try:
                # 读取Excel文件
                df = pd.read_excel(excel_path)
                
                # 检查必要的列是否存在
                if df.empty:
                    logger.warning(f"收件人Excel文件为空: {excel_path}")
                    return recipients_mapping
                
                # 获取列名（使用前两列）
                columns = df.columns.tolist()
                if len(columns) < 2:
                    logger.warning(f"收件人Excel文件格式不正确，至少需要两列: {excel_path}")
                    return recipients_mapping
                
                repo_col = columns[0]
                email_col = columns[1]
                
                # 处理每一行数据
                for _, row in df.iterrows():
                    repo_name = str(row[repo_col]).strip()
                    email_str = str(row[email_col]).strip()
                    
                    # 跳过空值
                    if repo_name and email_str and repo_name.lower() != 'nan' and email_str.lower() != 'nan':
                        # 分割多个邮箱地址
                        recipients = [email.strip() for email in email_str.split(';') if email.strip()]
                        if recipients:
                            recipients_mapping[repo_name] = recipients
                            logger.info(f"从Excel加载仓库 '{repo_name}' 的收件人: {', '.join(recipients)}")
                
                logger.info(f"成功从旧版收件人Excel加载 {len(recipients_mapping)} 个仓库的收件人信息")
            except Exception as e:
                logger.error(f"读取旧版收件人Excel文件时出错: {str(e)}")
        
        return recipients_mapping
    
    def _get_recipients_for_repository(self, repo_name):
        """获取指定仓库的收件人列表
        
        Args:
            repo_name: 仓库名称
            
        Returns:
            str: 收件人邮箱字符串（逗号分隔）
        """
        logger.info(f"尝试获取仓库 '{repo_name}' 的收件人")
        logger.info(f"当前recipients_mapping: {self.recipients_mapping}")
        
        # 首先尝试直接匹配
        if repo_name in self.recipients_mapping:
            recipients = self.recipients_mapping[repo_name]
            logger.info(f"使用Excel中配置的仓库 '{repo_name}' 的收件人: {', '.join(recipients)}")
            return ', '.join(recipients)
        
        # 检查是否需要映射到英文名称（使用动态映射）
        mapped_repo_name = self.repo_name_mapping.get(repo_name)
        if mapped_repo_name and mapped_repo_name in self.recipients_mapping:
            recipients = self.recipients_mapping[mapped_repo_name]
            logger.info(f"使用Excel中配置的仓库 '{mapped_repo_name}' (映射自 '{repo_name}') 的收件人: {', '.join(recipients)}")
            return ', '.join(recipients)
        
        # 如果直接匹配失败，尝试添加'REPO_'前缀
        repo_with_prefix = f'REPO_{repo_name}'
        if repo_with_prefix in self.recipients_mapping:
            recipients = self.recipients_mapping[repo_with_prefix]
            logger.info(f"使用Excel中配置的仓库 '{repo_with_prefix}' 的收件人: {', '.join(recipients)}")
            return ', '.join(recipients)
        
        # 尝试移除可能的前缀
        if repo_name.startswith('REPO_'):
            repo_without_prefix = repo_name[5:]
            if repo_without_prefix in self.recipients_mapping:
                recipients = self.recipients_mapping[repo_without_prefix]
                logger.info(f"使用Excel中配置的仓库 '{repo_without_prefix}' 的收件人: {', '.join(recipients)}")
                return ', '.join(recipients)
        
        # 如果recipients_mapping不为空，尝试从Excel中获取所有收件人
        if self.recipients_mapping:
            all_excel_recipients = set()
            for repo, recipients in self.recipients_mapping.items():
                all_excel_recipients.update(recipients)
            if all_excel_recipients:
                logger.info(f"未找到特定仓库的收件人，使用Excel中所有的收件人: {', '.join(all_excel_recipients)}")
                return ', '.join(all_excel_recipients)
        
        # 如果Excel中没有配置，使用默认收件人
        default_recipients = self.config['EMAIL'].get('to_emails', '')
        logger.info(f"使用默认收件人: {default_recipients}")
        return default_recipients
    
    def process_commit(self, repository_path, revision):
        """Process a single commit triggered by SVN hook
        
        Args:
            repository_path: Path to the SVN repository
            revision: The revision number of the commit
        """
        try:
            revision = int(revision)
            logger.info(f"Processing commit for repository: {repository_path}, revision: {revision}")
            
            # Find the matching repository configuration
            matching_repo = None
            matching_repo_name = None
            
            for repo_name, repo_config in self.repositories.items():
                if 'repository_path' in repo_config:
                    # Check if the repository path matches
                    if repository_path in repo_config['repository_path'] or \
                       repo_config['repository_path'] in repository_path:
                        matching_repo = repo_config
                        matching_repo_name = repo_name
                        break
            
            if not matching_repo:
                logger.warning(f"No matching repository configuration found for: {repository_path}")
                # Try to use the first repository config as fallback
                if self.repositories:
                    matching_repo_name, matching_repo = next(iter(self.repositories.items()))
                    logger.warning(f"Using fallback repository configuration: {matching_repo_name}")
                else:
                    logger.error("No repository configurations available")
                    return
            
            # Get the last recorded revision
            last_revision = self.last_revisions.get(matching_repo_name, 0)
            
            # Only process if this is a new revision
            if revision > last_revision:
                logger.info(f"New commit detected: {last_revision} -> {revision}")
                
                # Log the operation
                self.log_operation('COMMIT_PROCESSED', 
                                  f"Processing commit: {last_revision} -> {revision}",
                                  repository=matching_repo_name)
                
                # Get the changes
                changes = self.get_changes(last_revision, revision, matching_repo)
                
                # Send notification if enabled
                if matching_repo.get('notify_on_changes', 'True').lower() == 'true' and changes:
                    email_success = self.send_email_notification(changes)
                    
                    # Update revision if email was sent successfully
                    if email_success:
                        logger.info(f"Email notification successful for revision {revision}")
                        self.last_revisions[matching_repo_name] = revision
                        self._save_last_revisions(self.last_revisions)
                    else:
                        logger.warning(f"Email notification failed for revision {revision}")
                else:
                    # Update revision even if notifications are disabled
                    self.last_revisions[matching_repo_name] = revision
                    self._save_last_revisions(self.last_revisions)
            else:
                logger.info(f"Revision {revision} has already been processed")
                
        except Exception as e:
            error_msg = f"Error processing commit: {str(e)}"
            logger.error(error_msg)
            self.log_operation('ERROR', error_msg)
    
    def _try_svn_cleanup(self, working_dir, repo_config=None):
        """尝试执行SVN清理操作来解除锁定"""
        try:
            if not working_dir:
                logger.warning("无法执行SVN清理：工作目录为空")
                return False
            
            # 检查工作目录是否存在
            if not os.path.exists(working_dir):
                logger.warning(f"工作目录不存在，无法清理: {working_dir}")
                return False
            
            # 检查是否为SVN工作副本
            svn_dir = os.path.join(working_dir, '.svn')
            if not os.path.exists(svn_dir):
                logger.warning(f"目录不是SVN工作副本，无法清理: {working_dir}")
                return False
            
            logger.info(f"执行SVN清理操作: {working_dir}")
            
            # 构建清理命令 - 使用绝对路径确保正确性
            cleanup_command = ['svn', 'cleanup', working_dir]
            
            # 添加凭据（如果可用）
            # 首先尝试从仓库配置获取凭据
            username = None
            password = None
            
            if repo_config and 'username' in repo_config and 'password' in repo_config:
                if repo_config['username'] and repo_config['password']:
                    username = repo_config['username']
                    password = repo_config['password']
            # 如果仓库配置没有凭据，尝试从全局配置获取
            elif 'SVN' in self.config:
                if self.config['SVN'].get('username') and self.config['SVN'].get('password'):
                    username = self.config['SVN']['username']
                    password = self.config['SVN']['password']
            
            # 如果有凭据，添加到命令中
            if username and password:
                cleanup_command.extend(['--username', username])
                cleanup_command.extend(['--password', password])
                cleanup_command.append('--non-interactive')
                cleanup_command.append('--trust-server-cert')
                cleanup_command.append('--trust-server-cert-failures')
                cleanup_command.append('unknown-ca,cn-mismatch,expired,not-yet-valid,other')
            
            # 执行清理命令
            result = subprocess.run(
                cleanup_command,
                capture_output=True,
                cwd=working_dir,  # 在工作目录中执行清理
                check=True
            )
            
            logger.info(f"SVN清理成功: {result.stdout.strip() if result.stdout else '无输出'}")
            return True
            
        except subprocess.CalledProcessError as e:
            # 处理错误消息编码
            if isinstance(e.stderr, bytes):
                try:
                    error_message = e.stderr.decode('utf-8', errors='replace')
                except UnicodeDecodeError:
                    error_message = e.stderr.decode('gbk', errors='replace')
            else:
                error_message = e.stderr
            
            logger.error(f"SVN清理失败: {error_message}")
            
            # 如果清理失败，尝试手动删除锁定文件
            if 'locked' in error_message.lower():
                logger.info("尝试手动删除锁定文件")
                manual_cleanup_success = self._remove_svn_locks_manually(working_dir)
                
                # 手动删除锁定文件后，重试SVN清理操作
                if manual_cleanup_success:
                    logger.info("手动锁定文件删除成功，重试SVN清理")
                    try:
                        # 重新执行清理命令
                        result = subprocess.run(
                            cleanup_command,
                            capture_output=True,
                            cwd=working_dir,
                            check=True
                        )
                        logger.info(f"重试SVN清理成功: {result.stdout.strip() if result.stdout else '无输出'}")
                        return True
                    except subprocess.CalledProcessError as retry_e:
                        logger.error(f"重试SVN清理仍然失败: {retry_e.stderr}")
                        return False
                else:
                    logger.error("手动锁定文件删除失败")
                    return False
            
            return False
        except Exception as e:
            logger.error(f"执行SVN清理时出错: {str(e)}")
            return False
    
    def _remove_svn_locks_manually(self, working_dir):
        """手动删除SVN锁定文件"""
        try:
            svn_dir = os.path.join(working_dir, '.svn')
            if not os.path.exists(svn_dir):
                logger.warning(f"SVN目录不存在: {svn_dir}")
                return False
            
            # 查找并删除锁定文件
            lock_files = []
            for root, dirs, files in os.walk(svn_dir):
                for file in files:
                    if 'lock' in file.lower():
                        lock_files.append(os.path.join(root, file))
            
            if not lock_files:
                logger.info("未找到锁定文件")
                return False
            
            # 删除所有锁定文件
            for lock_file in lock_files:
                try:
                    os.remove(lock_file)
                    logger.info(f"删除锁定文件: {lock_file}")
                except Exception as e:
                    logger.warning(f"无法删除锁定文件 {lock_file}: {str(e)}")
            
            logger.info("手动锁定文件删除完成")
            return True
            
        except Exception as e:
            logger.error(f"手动删除锁定文件失败: {str(e)}")
            return False
    
    def _get_safe_command_string(self, command):
        """获取安全的命令字符串，隐藏用户名和密码信息
        
        Args:
            command: 命令列表
            
        Returns:
            str: 安全的命令字符串
        """
        safe_command = []
        i = 0
        while i < len(command):
            if command[i] in ['--username', '--password']:
                # 跳过用户名和密码参数，用***代替
                safe_command.append(command[i])
                safe_command.append('***')
                i += 2  # 跳过参数值
            else:
                safe_command.append(command[i])
                i += 1
        return ' '.join(safe_command)
    
    def _run_svn_command(self, command, repo_config=None, working_dir=None, is_retry=False, output_raw_log=False):
        """运行SVN命令并返回输出
        
        Args:
            command: SVN命令列表
            repo_config: 仓库配置字典
            working_dir: 工作目录
            is_retry: 是否为重试调用（避免参数重复）
            output_raw_log: 是否输出原始SVN日志
        """
        try:
            # 添加SVN凭据（如果可用），仅在非重试调用时添加
            if not is_retry:
                # 首先尝试从仓库配置获取凭据
                username = None
                password = None
                
                if repo_config and 'username' in repo_config and 'password' in repo_config:
                    if repo_config['username'] and repo_config['password']:
                        username = repo_config['username']
                        password = repo_config['password']
                # 如果仓库配置没有凭据，尝试从全局配置获取
                elif 'SVN' in self.config:
                    if self.config['SVN'].get('username') and self.config['SVN'].get('password'):
                        username = self.config['SVN']['username']
                        password = self.config['SVN']['password']
                
                # 如果有凭据，添加到命令中
                if username and password:
                    # 检查是否已经包含凭据参数，避免重复添加
                    if '--username' not in command:
                        command.extend(['--username', username])
                    if '--password' not in command:
                        command.extend(['--password', password])
                    if '--non-interactive' not in command:
                        command.append('--non-interactive')
                    if '--trust-server-cert' not in command:
                        command.append('--trust-server-cert')
                    if '--trust-server-cert-failures' not in command:
                        command.append('--trust-server-cert-failures')
                        command.append('unknown-ca,cn-mismatch,expired,not-yet-valid,other')
            
            # 在Windows中文环境下，SVN输出可能是GBK编码，使用通用方法处理
            # 确保传递环境变量，特别是OPENSSL_CONF
            env = os.environ.copy()
            result = subprocess.run(
                command,
                capture_output=True,
                cwd=working_dir,
                env=env,
                check=True
            )
            
            # 处理输出编码问题
            if result.stdout:
                if isinstance(result.stdout, bytes):
                    # 尝试UTF-8解码，如果失败则使用GBK解码
                    try:
                        decoded_output = result.stdout.decode('utf-8').strip()
                    except UnicodeDecodeError:
                        decoded_output = result.stdout.decode('gbk').strip()
                else:
                    decoded_output = result.stdout.strip()
                
                # 输出原始SVN日志（使用安全的命令字符串）
                if output_raw_log:
                    safe_command = self._get_safe_command_string(command)
                    logger.info(f"[SVN原始日志] 命令: {safe_command}")
                    logger.info(f"[SVN原始日志] 输出: {decoded_output}")
                    
                return decoded_output
            return ''
        except subprocess.CalledProcessError as e:
            # 确保错误消息正确解码，处理中文编码问题
            if isinstance(e.stderr, bytes):
                # 尝试UTF-8解码，如果失败则使用GBK解码（Windows中文环境）
                try:
                    error_message = e.stderr.decode('utf-8', errors='replace')
                except UnicodeDecodeError:
                    error_message = e.stderr.decode('gbk', errors='replace')
            else:
                error_message = e.stderr
            
            # 输出原始SVN错误日志（使用安全的命令字符串）
            safe_command = self._get_safe_command_string(command)
            logger.info(f"[SVN原始错误日志] 命令: {safe_command}")
            logger.info(f"[SVN原始错误日志] 错误: {error_message}")
            
            # 检测SVN锁定错误并尝试自动清理
            if 'locked' in error_message.lower() or 'cleanup' in error_message.lower():
                logger.warning(f"检测到SVN锁定错误，尝试自动清理: {error_message}")
                
                # 尝试执行svn cleanup命令
                cleanup_success = self._try_svn_cleanup(working_dir, repo_config)
                if cleanup_success:
                    logger.info("SVN清理成功，重试原始命令")
                    # 重试原始命令，传递is_retry=True避免参数重复
                    try:
                        return self._run_svn_command(command, repo_config, working_dir, is_retry=True)
                    except Exception:
                        # 如果重试仍然失败，返回空字符串
                        logger.error("重试SVN命令仍然失败")
                        return ''
                else:
                    logger.error("SVN清理失败，无法解除锁定")
                    # 即使清理失败，也尝试重试一次原始命令（可能锁定已被手动删除）
                    try:
                        logger.info("尝试重试原始命令（可能锁定已被手动删除）")
                        return self._run_svn_command(command, repo_config, working_dir, is_retry=True)
                    except Exception:
                        logger.error("重试SVN命令仍然失败")
                        return ''
            
            logger.error(f"SVN命令失败: {command}\n错误: {error_message}")
            return ''
        except Exception as e:
            logger.error(f"运行SVN命令时出错: {str(e)}")
            return ''
    
    def _ensure_working_copy(self, repo_config):
        """确保本地工作副本存在且是最新的"""
        working_copy = repo_config['local_working_copy']
        repo_path = repo_config['repository_path']
        
        try:
            # 确保父目录存在
            parent_dir = os.path.dirname(working_copy)
            if parent_dir and not os.path.exists(parent_dir):
                os.makedirs(parent_dir, exist_ok=True)
            
            # 如果工作副本存在，先检查.svn目录是否存在，避免不必要的状态检查
            if os.path.exists(working_copy):
                logger.info(f"检查工作副本: {working_copy}")
                
                # 检查是否是有效的SVN工作副本
                if not os.path.exists(os.path.join(working_copy, '.svn')):
                    logger.warning(f"目录存在但不是工作副本，删除: {working_copy}")
                    import shutil
                    shutil.rmtree(working_copy)
                else:
                    # 只有在.svn目录存在的情况下才进行状态检查
                    logger.info(f"工作副本有效，跳过状态检查以提升性能")
                    # 注释：为了提升性能，我们假设工作副本正常，只在更新失败时才处理锁定问题
            
            # 清理目录如果存在但不是工作副本
            if os.path.exists(working_copy) and not os.path.exists(os.path.join(working_copy, '.svn')):
                logger.info(f"目录存在但不是工作副本，删除: {working_copy}")
                import shutil
                shutil.rmtree(working_copy)
            
            if not os.path.exists(working_copy):
                logger.info(f"创建工作副本: {working_copy}")
                # 对于checkout，需要在父目录中运行命令
                self._run_svn_command(['svn', 'checkout', repo_path, os.path.basename(working_copy)], 
                                     repo_config, working_dir=parent_dir or os.getcwd())
            else:
                logger.info(f"更新工作副本: {working_copy}")
                # 优化更新策略：先执行cleanup，然后尝试快速更新，如果失败再尝试修复
                try:
                    # 在更新前先执行cleanup操作
                    logger.info(f"在更新前先执行SVN清理: {working_copy}")
                    self._try_svn_cleanup(working_copy, repo_config)
                    # 尝试快速更新
                    logger.info(f"执行SVN更新: {working_copy}")
                    self._run_svn_command(['svn', 'update', '--accept', 'theirs-full', working_copy], repo_config, output_raw_log=True)
                except Exception as update_error:
                    logger.warning(f"快速更新失败，尝试修复工作副本: {str(update_error)}")
                    
                    # 检查是否有缺失文件问题
                    try:
                        status_result = self._run_svn_command(['svn', 'status'], repo_config, working_dir=working_copy)
                        if '!' in status_result:
                            logger.info("检测到缺失文件，执行修复操作")
                            # 先执行清理
                            self._try_svn_cleanup(working_copy, repo_config)
                            # 然后执行revert恢复缺失文件
                            self._run_svn_command(['svn', 'revert', '-R', working_copy], repo_config)
                            # 最后重新更新
                            self._run_svn_command(['svn', 'update', '--accept', 'theirs-full', working_copy], repo_config)
                        else:
                            # 其他错误，尝试清理后重试
                            self._try_svn_cleanup(working_copy, repo_config)
                            self._run_svn_command(['svn', 'update', '--accept', 'theirs-full', working_copy], repo_config)
                    except Exception as repair_error:
                        logger.error(f"修复工作副本失败: {str(repair_error)}")
                        raise update_error
        except Exception as e:
            logger.error(f"确保工作副本失败: {str(e)}")
            raise
    
    def get_latest_revision(self, repo_config):
        """Get the latest revision number of the repository"""
        try:
            # 根据检测模式选择不同的获取方式
            if self.use_remote_check:
                # 远程检测模式：直接通过SVN URL获取信息
                repo_url = repo_config.get('repository_path', repo_config.get('url', ''))
                if not repo_url:
                    logger.error(f"No repository URL found in configuration")
                    raise ValueError(f"No repository URL found in configuration")
                
                # 使用_run_svn_command方法获取远程仓库的最新版本号（支持认证和证书信任）
                cmd = ['svn', 'info', repo_url, '--show-item', 'revision']
                logger.info(f"Getting latest revision remotely for {repo_config.get('name', 'Unnamed Repository')}")
                output = self._run_svn_command(cmd, repo_config)
                
                if not output:
                    logger.warning(f"Empty output when getting latest revision")
                    return 0
                
                return int(output)
            else:
                # 本地检测模式：更新本地工作副本后获取
                self._ensure_working_copy(repo_config)
                output = self._run_svn_command(
                    ['svn', 'info', '--show-item', 'revision'],
                    repo_config,
                    working_dir=repo_config['local_working_copy']
                )
                return int(output)
        except Exception as e:
            logger.error(f"Failed to get latest revision: {str(e)}")
            raise
    
    # get_file_diff method removed as AI analysis feature is no longer required
    
    # analyze_file_change method removed as AI analysis feature is no longer required
    
    def _get_paginated_svn_log(self, repo_config, from_revision, to_revision, repo_name):
        """Get SVN log using pagination for large revision ranges
        
        Args:
            repo_config: Repository configuration
            from_revision: Starting revision
            to_revision: Ending revision
            repo_name: Repository name
            
        Returns:
            str: Combined log output in XML format
        """
        try:
            repo_url = repo_config.get('repository_path', repo_config.get('url', ''))
            if not repo_url:
                logger.error(f"No repository URL found in configuration for {repo_name}")
                return ""
            combined_logs = []
            
            # Use page size of 500 to avoid overwhelming the SVN server
            page_size = 500
            current_start = from_revision
            
            while current_start <= to_revision:
                current_end = min(current_start + page_size - 1, to_revision)
                
                # Build SVN log command with revision range
                cmd = [
                    'svn', 'log', repo_url,
                    '--xml', '--verbose',
                    '-r', f'{current_start}:{current_end}'
                ]
                
                logger.debug(f"Fetching SVN log for revisions {current_start} to {current_end}")
                
                try:
                    # 使用_run_svn_command方法执行SVN命令，确保环境变量正确传递
                    log_output = self._run_svn_command(cmd, repo_config)
                    if log_output:
                        combined_logs.append(log_output)
                    else:
                        logger.warning(f"Empty log output for revisions {current_start} to {current_end}")
                        # If we get empty output, try to get individual revisions
                        for rev in range(current_start, current_end + 1):
                            try:
                                single_cmd = [
                                    'svn', 'log', repo_url,
                                    '--xml', '--verbose',
                                    '-r', str(rev)
                                ]
                                single_log = self._run_svn_command(single_cmd, repo_config)
                                if single_log:
                                    combined_logs.append(single_log)
                            except Exception as e:
                                logger.warning(f"Failed to get revision {rev}: {str(e)}")
                except Exception as e:
                    logger.error(f"Error executing SVN log command: {str(e)}")
                
                # Move to next page
                current_start = current_end + 1
                
                # Small delay to avoid overwhelming the SVN server
                time.sleep(0.5)
            
            # Combine all log outputs
            if combined_logs:
                # Create a root XML element to wrap all log entries
                root = ET.Element('log')
                for log_xml in combined_logs:
                    try:
                        log_root = ET.fromstring(log_xml)
                        for logentry in log_root.findall('.//logentry'):
                            root.append(logentry)
                    except ET.ParseError:
                        logger.warning("Failed to parse individual log XML, skipping")
                
                # Convert back to XML string
                return ET.tostring(root, encoding='unicode')
            else:
                return ""
                
        except Exception as e:
            logger.error(f"Error in paginated SVN log retrieval: {str(e)}")
            return ""

    def get_changes(self, from_revision, to_revision, repo_config):
        """Get changes between two revisions"""
        logger.debug(f"Getting changes from revision {from_revision} to {to_revision}")
        
        try:
            # Check if repo_config is valid
            if not repo_config:
                logger.error("Invalid repository configuration")
                return [{
                    'revision': to_revision,
                    'author': 'unknown',
                    'date': get_beijing_time_str(),
                    'message': 'Invalid repository configuration',
                    'changed_paths': [],
                    'repository': 'Unknown Repository'
                }]
            
            # Get repository name for logging
            repo_name = repo_config.get('name', 'Unnamed Repository')
            
            # 根据检测模式选择不同的获取方式
            if self.use_remote_check:
                # 远程检测模式：直接通过SVN URL获取日志
                repo_url = repo_config.get('repository_path', repo_config.get('url', ''))
                if not repo_url:
                    logger.error(f"No repository URL found in configuration for {repo_name}")
                    return [{
                        'revision': to_revision,
                        'author': 'unknown',
                        'date': get_beijing_time_str(),
                        'message': 'Missing repository URL configuration',
                        'changed_paths': [],
                        'repository': repo_name
                    }]
                
                logger.info(f"Getting changes remotely for {repo_name}")
                # 使用分页方式获取SVN日志
                output = self._get_paginated_svn_log(repo_config, from_revision, to_revision, repo_name)
            else:
                # 本地检测模式：更新本地工作副本后获取
                # Check if local_working_copy is set
                if 'local_working_copy' not in repo_config:
                    logger.error("local_working_copy not set in repository configuration")
                    return [{
                        'revision': to_revision,
                        'author': 'unknown',
                        'date': get_beijing_time_str(),
                        'message': 'Missing local_working_copy configuration',
                        'changed_paths': [],
                        'repository': repo_name
                    }]
                
                self._ensure_working_copy(repo_config)
                
                # Calculate the number of revisions to fetch
                revision_gap = to_revision - from_revision
                
                # Use the new approach: svn log --verbose -l N where N is the revision gap
                # This limits the number of log entries fetched to exactly the number needed
                limit_option = f'-l {revision_gap}' if revision_gap > 0 else '-l 1'
                
                # Build the SVN log command with limit option and revision range
                # Use -r option to specify the revision range
                revision_range = f'-r{from_revision+1}:{to_revision}' if from_revision > 1 else f'-r1:{to_revision}'
                
                cmd = ['svn', 'log', revision_range, limit_option, '--xml', '--verbose']
                
                logger.info(f"Getting SVN log for {repo_name} using range: {revision_range} and limit: {limit_option}")
                
                # Execute the SVN log command
                output = self._run_svn_command(
                    cmd,
                    repo_config,
                    working_dir=repo_config['local_working_copy']
                )
            
            logger.debug(f"Raw SVN log result for {repo_name}: {output[:500]}..." if len(output) > 500 else f"Raw SVN log result for {repo_name}: {output}")
            
            # Ensure output is string type
            if not isinstance(output, str):
                output = str(output) if output is not None else ''
            
            # Fix: Properly get all changes, add additional logging
            logger.info(f"Parsing SVN log output for {repo_name}, checking for multiple revisions")
            changes = self._parse_svn_log(output, repo_name)
            logger.info(f"Successfully parsed {len(changes)} changes from SVN log")
            
            # Removed AI analysis functionality, keeping only basic change records
            for change in changes:
                logger.debug(f"Parsed change for {repo_name} (rev {change.get('revision')}): {len(change.get('changed_paths', []))} files changed")
                for path in change.get('changed_paths', []):
                    logger.debug(f"  - {path.get('action')}: {path.get('path')}")
            
            return changes
        except Exception as e:
            logger.error(f"Failed to get changes: {str(e)}")
            # Return a default change object to avoid crashing
            return [{
                'revision': to_revision,
                'author': 'unknown',
                'date': get_beijing_time().isoformat(),
                'message': 'Unable to parse commit details',
                'changed_paths': [],
                'repository': repo_config.get('name', 'Unnamed Repository'),
                'ai_analysis': 'Unable to parse commit details'
            }]
    
    def _parse_svn_log(self, xml_log, repo_name):
        """Parse SVN log XML output"""
        changes = []
        
        try:
            # Check if xml_log is empty, None, or not a string
            if not xml_log or not isinstance(xml_log, str) or xml_log.strip() == '':
                logger.warning("Empty or invalid SVN log output received")
                return changes
            
            # Preprocess XML output by removing leading spaces and newlines
            xml_log = xml_log.strip()
            logger.info(f"Parsing SVN log XML of length: {len(xml_log)} characters")
            
            # Try to parse XML with error handling
            try:
                root = ET.fromstring(xml_log)
                logger.info("Successfully parsed XML log")
            except ET.ParseError as e:
                logger.error(f"XML parsing error: {str(e)}")
                logger.debug(f"XML content: {xml_log[:100]}...")
                
                # Try multiple fix methods
                # 1. Check and fix XML declaration position issues
                if "XML or text declaration not at start of entity" in str(e):
                    # Try to find the first < opening tag
                    first_tag_pos = xml_log.find('<')
                    if first_tag_pos > 0:
                        xml_log = xml_log[first_tag_pos:]
                        try:
                            root = ET.fromstring(xml_log)
                            logger.info("Successfully parsed XML after removing leading characters")
                        except:
                            # If fixing fails, try wrapping
                            if not xml_log.startswith('<log'):
                                xml_log = f'<log>{xml_log}</log>'
                            root = ET.fromstring(xml_log)
                    else:
                        # 2. Try wrapping as a complete XML document
                        if not xml_log.startswith('<log>'):
                            xml_log = f'<log>{xml_log}</log>'
                        root = ET.fromstring(xml_log)
            
            # Debug: Print the XML structure
            logger.debug(f"XML root tag: {root.tag}, children: {len(root)}")
            
            # Fix: Use multiple ways to find logentry elements to ensure all changes are captured
            logentries = []
            if root is not None:
                try:
                    # First try XPath query
                    logentries = root.findall('.//logentry')
                    logger.info(f"Found {len(logentries)} logentries using XPath")
                    
                    if not logentries:
                        # If XPath fails, try direct child iteration
                        logentries = [child for child in root if child.tag == 'logentry']
                        logger.info(f"Found {len(logentries)} logentries using direct child access")
                except Exception as e:
                    logger.error(f"Error finding logentries: {str(e)}")
            
            # Fix: Ensure all log entries are processed in correct order
            logger.info(f"Processing {len(logentries)} logentries for {repo_name}")
            
            for i, logentry in enumerate(logentries):
                try:
                    revision = int(logentry.get('revision', 0))
                    author_elem = logentry.find('author')
                    author = author_elem.text if author_elem is not None else 'unknown'
                    date_elem = logentry.find('date')
                    if date_elem is not None and date_elem.text:
                        try:
                            # Parse ISO format date string
                            date_obj = datetime.datetime.fromisoformat(date_elem.text.replace('Z', '+00:00'))
                            # Format to yyyy-MM-dd HH:mm:ss format
                            date = date_obj.strftime('%Y-%m-%d %H:%M:%S')
                        except Exception as e:
                            logger.warning(f"Failed to parse date: {date_elem.text}, error: {str(e)}")
                            # If parsing fails, use current time
                            date = get_beijing_time_str()
                    else:
                        # If no date element, use current time
                        date = get_beijing_time_str()
                    msg_elem = logentry.find('msg')
                    message = msg_elem.text.strip() if msg_elem is not None and msg_elem.text else ''
                    
                    # Get changed paths - add None check for paths_elem
                    changed_paths = []
                    paths_elem = logentry.find('paths')
                    logger.debug(f"Parsing paths element for revision {revision}: {paths_elem is not None}")
                    
                    if paths_elem is not None:
                        try:
                            path_elements = paths_elem.findall('path')
                            logger.info(f"Found {len(path_elements)} path elements in revision {revision}")
                            
                            for path in path_elements:
                                action = path.get('action', 'M')
                                path_name = path.text if path.text else ''
                                
                                # Skip empty paths
                                if path_name.strip():
                                    changed_paths.append({
                                        'path': path_name,
                                        'action': action
                                    })
                                    logger.debug(f"Added path: {action}: {path_name}")
                                else:
                                    logger.debug(f"Skipping empty path")
                        except AttributeError as e:
                            logger.error(f"AttributeError when finding paths: {str(e)}")
                    
                    logger.info(f"Revision {revision}: {len(changed_paths)} changed paths")
                    
                    # Create change record
                    change_record = {
                        'revision': revision,
                        'author': author,
                        'date': date,
                        'message': message,
                        'changed_paths': changed_paths,
                        'repository': repo_name
                    }
                    
                    # Add to result list
                    changes.append(change_record)
                    logger.info(f"Successfully added change record for revision {revision}")
                    
                except Exception as e:
                    logger.error(f"Error parsing log entry {i}: {str(e)}")
                    # Continue with other entries
            
            # Fix: Ensure all parsed changes are returned
            logger.info(f"Total changes parsed: {len(changes)}")
            return changes
        except ET.ParseError as e:
            logger.error(f"XML parsing error: {str(e)}")
            logger.debug(f"Offending XML: {xml_log}")
            # Return a minimal change object
            return [{
                'revision': 0,
                'author': 'unknown',
                'date': get_beijing_time().isoformat(),
                'message': 'XML parsing error',
                'changed_paths': [],
                'repository': repo_name
            }]
        except Exception as e:
            logger.error(f"Failed to parse SVN log: {str(e)}")
            # Return a minimal change object
            return [{
                'revision': 0,
                'author': 'unknown',
                'date': get_beijing_time().isoformat(),
                'message': 'Unknown error parsing log',
                'changed_paths': [],
                'repository': repo_name
            }]
    
    def log_operation(self, operation_type, message, repository=None, change_details=None):
        """Log script operation for tracking and auditing"""
        operation_log = {
            'timestamp': get_beijing_time().isoformat(),
            'operation_type': operation_type,
            'message': message,
            'repository': repository
        }
        
        if change_details:
            operation_log['change_details'] = change_details
        
        # 安全处理repository参数，避免AttributeError
        repo_display = repository
        if isinstance(repository, dict):
            # 如果是字典，尝试获取name字段，否则显示字典类型
            repo_display = repository.get('name', f"dict({type(repository).__name__})")
        elif repository is None:
            repo_display = 'None'
        elif not isinstance(repository, str):
            # 如果是其他非字符串类型，显示类型信息
            repo_display = f"{type(repository).__name__}({repository})"
        
        # Log to file and console
        if operation_type == 'ERROR':
            logger.error(f"[OPERATION] {operation_log['timestamp']} - {operation_log['message']} - Repo: {repo_display}")
        elif operation_type == 'WARNING':
            logger.warning(f"[OPERATION] {operation_log['timestamp']} - {operation_log['message']} - Repo: {repo_display}")
        else:
            logger.info(f"[OPERATION] {operation_log['timestamp']} - {operation_log['message']} - Repo: {repo_display}")
        
        # Additional logging of change details if provided
        if change_details and isinstance(change_details, list):
            for detail in change_details:
                logger.info(f"[CHANGE_DETAIL] {detail}")
    
    def send_email_notification(self, changes):
        """Send email notification about changes"""
        if not changes:
            return False
        
        try:
            # Log the notification attempt
            self.log_operation('NOTIFICATION', f"Attempting to send email notification with {len(changes)} changes")
            
            # Check if email configuration is complete
            if 'EMAIL' not in self.config or not all([
                'smtp_server' in self.config['EMAIL'],
                'from_email' in self.config['EMAIL'],
                'to_emails' in self.config['EMAIL']
            ]):
                logger.warning("Email notification skipped: incomplete email configuration")
                self.log_operation('WARNING', "Email notification skipped: incomplete email configuration")
                return False
            
            # Check if SMTP credentials are configured, skip email sending if not
            has_credentials = False
            if 'username' in self.config['EMAIL'] and 'password' in self.config['EMAIL']:
                username = self.config['EMAIL'].get('username', '').strip()
                password = self.config['EMAIL'].get('password', '').strip()
                has_credentials = bool(username) and bool(password)
                
            if not has_credentials:
                logger.info("Email notification skipped: No valid SMTP credentials configured")
                self.log_operation('INFO', "Email notification skipped: No valid SMTP credentials configured")
                return False
            
            # Group changes by repository
            changes_by_repo = {}
            try:
                for change in changes:
                    repo_name = change.get('repository', 'Unnamed Repository')
                    logger.info(f"Processing change with repository name: '{repo_name}'")
                    if repo_name not in changes_by_repo:
                        changes_by_repo[repo_name] = []
                    changes_by_repo[repo_name].append(change)
            except Exception as e:
                logger.error(f"Error grouping changes by repository: {str(e)}")
                return
            
            # 修改：无论有多少个仓库，都将所有变更合并到一封邮件中发送
            # 获取所有相关仓库的唯一收件人列表
            all_recipients = set()
            logger.info(f"Changes grouped by repository: {list(changes_by_repo.keys())}")
            logger.info(f"Available recipients mapping: {list(self.recipients_mapping.keys())}")
            for repo_name in changes_by_repo.keys():
                logger.info(f"Trying to get recipients for repository: '{repo_name}'")
                repo_recipients = self._get_recipients_for_repository(repo_name)
                if repo_recipients:
                    # 灵活支持逗号或分号分隔的收件人字符串
                    # 首先将所有分号替换为逗号，然后统一用逗号分割
                    recipients_str = repo_recipients.replace(';', ',')
                    for recipient in recipients_str.split(','):
                        recipient = recipient.strip()
                        if recipient and recipient.lower() != 'nan':
                            all_recipients.add(recipient)
            
            # 如果没有配置收件人，使用默认收件人
            if not all_recipients:
                default_recipients = self.config['EMAIL'].get('to_emails', '')
                if default_recipients:
                    # 灵活支持逗号或分号分隔的收件人字符串
                    recipients_str = default_recipients.replace(';', ',')
                    for recipient in recipients_str.split(','):
                        recipient = recipient.strip()
                        if recipient and recipient.lower() != 'nan':
                            all_recipients.add(recipient)
            
            # 准备邮件内容
            # 使用动态加载的仓库名称映射（从Excel配置文件读取）
            repo_name_mapping = self.repo_name_mapping
            
            # 获取仓库名称列表（包含ID和中文名称）
            formatted_repo_names = []
            for repo_name in changes_by_repo.keys():
                chinese_name = repo_name_mapping.get(repo_name, repo_name)
                # 查找英文ID（REPO_*）
                repo_id = None
                for key, value in self.repo_name_mapping.items():
                    if key.startswith('REPO_') and (value == chinese_name or key == repo_name):
                        repo_id = key
                        break
                if repo_id is None:
                    repo_id = repo_name
                formatted_repo_names.append(f"{repo_id} ({chinese_name})")
            
            # 创建邮件主题
            if len(formatted_repo_names) == 1:
                subject = f"SVN仓库变更通知 - {formatted_repo_names[0]} ({len(changes)}个变更)"
            else:
                subject = f"SVN仓库变更通知 - {len(changes)}个变更涉及{len(changes_by_repo)}个仓库 ({', '.join(formatted_repo_names)})"
            
            body = f"""
            <html>
            <body>
                <h2>SVN仓库变更检测通知</h2>
                <p>检测到以下SVN仓库变更：</p>
            """
            
            # 为每个仓库添加变更详情
            for repo_name, repo_changes in changes_by_repo.items():
                # Get repository URL if available
                repo_url = ""
                # Find the corresponding repository configuration
                for r_name, r_config in self.repositories.items():
                    if r_name == repo_name:
                        repo_url = r_config.get('repository_path', '')
                        break
                
                # 使用动态加载的仓库名称映射（从Excel配置文件读取）
                repo_name_mapping = self.repo_name_mapping
                chinese_repo_name = repo_name_mapping.get(repo_name, repo_name)
                
                # Format the repository name with ID and Chinese name
                # 查找英文ID（REPO_*）
                repo_id = None
                for key, value in self.repo_name_mapping.items():
                    if key.startswith('REPO_') and (value == chinese_repo_name or key == repo_name):
                        repo_id = key
                        break
                if repo_id is None:
                    repo_id = repo_name
                
                repo_display = f"{repo_id} ({chinese_repo_name})"
                if repo_url:
                    repo_display += f" (URL: {repo_url})"
                
                body += f"""
                <h3>{repo_display}</h3>
                <table border="1" cellpadding="5" cellspacing="0">
                    <tr bgcolor="#f2f2f2">
                        <th>Revision</th>
                        <th>Author</th>
                        <th>Date</th>
                        <th>Message</th>
                        <th>Change Type</th>
                        <th>Changed Files</th>
                    </tr>
                """
                
                for change in repo_changes:
                    try:
                        # Get changed paths
                        changed_paths = change.get('changed_paths', [])
                        
                        # Create HTML for changed files and determine change type
                        if changed_paths:
                            files_html = "<ul style='margin: 0; padding-left: 15px;'>"
                            # Collect all actions in this revision
                            actions = set()
                            for path in changed_paths:
                                action = path.get('action', 'M')
                                actions.add(action)
                                path_name = path.get('path', 'unknown')
                                action_desc = {
                                    'A': 'Added',
                                    'M': 'Modified',
                                    'D': 'Deleted',
                                    'R': 'Replaced'
                                }.get(action, action)
                                files_html += f"<li>{action_desc}: {path_name}</li>"
                            files_html += "</ul>"
                            
                            # Determine the primary change type for coloring
                            if 'D' in actions:
                                change_type = 'Deleted'
                                change_color = 'red'
                            elif len(actions) > 1:
                                change_type = 'Mixed'
                                change_color = 'orange'
                            elif 'M' in actions:
                                change_type = 'Modified'
                                change_color = 'blue'
                            elif 'A' in actions:
                                change_type = 'Added'
                                change_color = 'green'
                            else:
                                change_type = 'Other'
                                change_color = 'black'
                        else:
                            files_html = "<span style='color: #666;'>No files listed in log</span>"
                            change_type = 'None'
                            change_color = 'grey'
                        
                        # Add to email body
                        body += f"""
                            <tr>
                            <td>{change.get('revision', 'N/A')}</td>
                            <td>{change.get('author', 'unknown')}</td>
                            <td>{change.get('date', 'N/A')}</td>
                            <td>{change.get('message', '')}</td>
                            <td style='color: {change_color}; font-weight: bold;'>{change_type}</td>
                            <td style='white-space: normal; word-break: break-all; max-width: 500px;'>{files_html}</td>
                        </tr>
                        """
                    except Exception as e:
                        logger.error(f"Error processing change for email: {str(e)}")
                        # Skip this change but continue with others
                
                body += """
                </table>
                <br>
                """
            
            body += """
            </body>
            </html>
            """
            
            # Create message
            msg = MIMEMultipart('alternative')
            msg['From'] = self.config['EMAIL']['from_email']
            # 修改：正确设置多个收件人
            recipients_str = ', '.join(all_recipients)
            msg['To'] = recipients_str
            msg['Subject'] = subject
            
            # Attach HTML body
            msg.attach(MIMEText(body, 'html'))
            
            # 发送邮件
            return self._send_email(msg)
        except Exception as e:
            logger.error(f"Error in send_email_notification: {str(e)}")
            self.log_operation('ERROR', f"Failed to send email notification: {str(e)}")
            return False
    
    def _send_email_for_repository(self, repo_name, changes):
        """为指定仓库发送邮件通知
        
        Args:
            repo_name: 仓库名称
            changes: 该仓库的变更列表
            
        Returns:
            bool: 是否发送成功
        """
        try:
            # 获取该仓库的收件人
            recipients = self._get_recipients_for_repository(repo_name)
            if not recipients:
                logger.warning(f"仓库 '{repo_name}' 没有配置收件人，跳过邮件发送")
                return False
                
            # 准备邮件内容
            # 使用动态加载的仓库名称映射（从Excel配置文件读取）
            repo_name_mapping = self.repo_name_mapping
            chinese_repo_name = repo_name_mapping.get(repo_name, repo_name)
            
            # 查找英文ID（REPO_*）
            repo_id = None
            for key, value in self.repo_name_mapping.items():
                if key.startswith('REPO_') and (value == chinese_repo_name or key == repo_name):
                    repo_id = key
                    break
            if repo_id is None:
                repo_id = repo_name
                
            subject = f"SVN仓库变更通知 - {repo_id} ({chinese_repo_name}) ({len(changes)}个变更)"
            
            body = f"""
            <html>
            <body>
                <h2>SVN仓库变更检测通知</h2>
                <p>检测到以下SVN仓库变更：</p>
            """
            
            # 添加仓库信息和变更详情
            # Get repository URL if available
            repo_url = ""
            # Find the corresponding repository configuration
            for r_name, r_config in self.repositories.items():
                if r_name == repo_name:
                    repo_url = r_config.get('repository_path', '')
                    break
            
            # Format the repository name with ID and Chinese name
            repo_display = f"{repo_id} ({chinese_repo_name})"
            if repo_url:
                repo_display += f" (URL: {repo_url})"
            
            body += f"""
            <h3>{repo_display}</h3>
            <table border="1" cellpadding="5" cellspacing="0">
                <tr bgcolor="#f2f2f2">
                    <th>Revision</th>
                    <th>Author</th>
                    <th>Date</th>
                    <th>Message</th>
                    <th>Change Type</th>
                    <th>Changed Files</th>
                </tr>
            """
            
            for change in changes:
                try:
                    # Log the change details for debugging
                    logger.debug(f"Processing change for email - repo: {repo_name}, rev: {change.get('revision')}")
                    
                    # Get changed paths
                    changed_paths = change.get('changed_paths', [])
                    logger.debug(f"  Has {len(changed_paths)} changed paths")
                    
                    # Create HTML for changed files and determine change type
                    if changed_paths:
                        files_html = "<ul style='margin: 0; padding-left: 15px;'>"
                        # Collect all actions in this revision
                        actions = set()
                        for path in changed_paths:
                            action = path.get('action', 'M')
                            actions.add(action)
                            path_name = path.get('path', 'unknown')
                            action_desc = {
                                'A': 'Added',
                                'M': 'Modified',
                                'D': 'Deleted',
                                'R': 'Replaced'
                            }.get(action, action)
                            files_html += f"<li>{action_desc}: {path_name}</li>"
                            logger.debug(f"  Added to email: {action_desc}: {path_name}")
                        files_html += "</ul>"
                        
                        # Determine the primary change type for coloring
                        # Priority: Deleted > Mixed > Modified > Added
                        if 'D' in actions:
                            change_type = 'Deleted'
                            change_color = 'red'
                        elif len(actions) > 1:
                            change_type = 'Mixed'
                            change_color = 'orange'
                        elif 'M' in actions:
                            change_type = 'Modified'
                            change_color = 'blue'
                        elif 'A' in actions:
                            change_type = 'Added'
                            change_color = 'green'
                        else:
                            change_type = 'Other'
                            change_color = 'black'
                    else:
                        # Show a message when no files were changed
                        files_html = "<span style='color: #666;'>No files listed in log</span>"
                        change_type = 'None'
                        change_color = 'grey'
                        logger.debug(f"  No changed files found in this revision")
                    
                    # Add to email body
                    body += f"""
                        <tr>
                        <td>{change.get('revision', 'N/A')}</td>
                        <td>{change.get('author', 'unknown')}</td>
                        <td>{change.get('date', 'N/A')}</td>
                        <td>{change.get('message', '')}</td>
                        <td style='color: {change_color}; font-weight: bold;'>{change_type}</td>
                        <td style='white-space: normal; word-break: break-all; max-width: 500px;'>{files_html}</td>
                    </tr>
                    """
                except Exception as e:
                    logger.error(f"Error processing change for email: {str(e)}")
                    # Skip this change but continue with others
            
            body += """
            </table>
            <br>
            </body>
            </html>
            """
            
            # Create message
            msg = MIMEMultipart('alternative')
            msg['From'] = self.config['EMAIL']['from_email']
            msg['To'] = recipients
            msg['Subject'] = subject
            
            # Attach HTML body
            msg.attach(MIMEText(body, 'html'))
            
            # 调用原有的邮件发送逻辑
            return self._send_email(msg)
        except Exception as e:
            logger.error(f"Error in _send_email_for_repository: {str(e)}")
            return False
    
    def _send_email(self, msg):
        """内部邮件发送方法，包含重试逻辑
        
        Args:
            msg: 邮件消息对象
            
        Returns:
            bool: 是否发送成功
        """
        try:
            # 检查是否有SMTP凭证
            has_credentials = False
            if 'username' in self.config['EMAIL'] and 'password' in self.config['EMAIL']:
                username = self.config['EMAIL'].get('username', '').strip()
                password = self.config['EMAIL'].get('password', '').strip()
                has_credentials = bool(username) and bool(password)
            
            # Send email with retry logic
            smtp_server = self.config['EMAIL']['smtp_server']
            smtp_port = int(self.config['EMAIL'].get('smtp_port', '465'))
            use_ssl = self.config['EMAIL'].get('use_ssl', 'True').lower() == 'true'
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
                    
                    # Only attempt login if we have complete credentials and has_credentials is True
                    if has_credentials:
                        try:
                            username = self.config['EMAIL'].get('username', '').strip()
                            password = self.config['EMAIL'].get('password', '').strip()
                            if username and password:  # Double check for security
                                server.login(username, password)
                        except smtplib.SMTPAuthenticationError:
                            logger.error(f"SMTP authentication failed (attempt {retry_count + 1}/{max_retries + 1})")
                            retry_count += 1
                            time.sleep(2)  # Wait before retry
                            continue
                    else:
                        logger.info("Skipping SMTP authentication as no valid credentials provided")
                    
                    # 明确提取收件人列表，确保所有收件人都能收到邮件
                    recipients_str = msg['To']
                    # 将收件人字符串拆分为列表
                    recipients_list = [r.strip() for r in recipients_str.split(',') if r.strip()]
                    
                    # 使用明确的收件人列表发送邮件
                    server.send_message(msg, to_addrs=recipients_list)
                    server.quit()
                    success = True
                    logger.info(f"Email notification sent to {recipients_str}")
                    self.log_operation('SUCCESS', f"Email notification successfully sent to {recipients_str}")
                    return True
                except smtplib.SMTPException as e:
                    logger.error(f"SMTP error sending email: {str(e)} (attempt {retry_count + 1}/{max_retries + 1})")
                    retry_count += 1
                    time.sleep(2)  # Wait before retry
                except Exception as e:
                    logger.error(f"Unexpected error sending email: {str(e)}")
                    break
            
            if not success:
                logger.error("Failed to send email after multiple attempts")
                # Do not throw exception, allow program to continue running
                return False
        except Exception as e:
            logger.error(f"Error in _send_email: {str(e)}")
            return False
                
        except Exception as e:
            logger.error(f"Failed to send email notification: {str(e)}")
            # Ensure no exception is thrown, allow program to continue running
            return False
    
    # Backup functionality has been removed

    def send_status_email(self, check_result):
        """发送程序运行状态邮件
        
        Args:
            check_result: 检查结果字典，包含以下字段：
                - check_time: 检查时间
                - total_repos: 总仓库数
                - repos_with_changes: 有变更的仓库数
                - total_changes: 总变更数
                - repos_checked: 已检查的仓库列表
                - errors: 错误信息列表
                
        Returns:
            bool: 是否发送成功
        """
        try:
            # 检查邮件配置是否完整
            if 'EMAIL' not in self.config or not all([
                'smtp_server' in self.config['EMAIL'],
                'from_email' in self.config['EMAIL']
            ]):
                logger.warning("状态邮件发送跳过：邮件配置不完整")
                self.log_operation('WARNING', "状态邮件发送跳过：邮件配置不完整")
                return False
            
            # 检查是否有SMTP凭证
            has_credentials = False
            if 'username' in self.config['EMAIL'] and 'password' in self.config['EMAIL']:
                username = self.config['EMAIL'].get('username', '').strip()
                password = self.config['EMAIL'].get('password', '').strip()
                has_credentials = bool(username) and bool(password)
            
            if not has_credentials:
                logger.info("状态邮件发送跳过：未配置有效的SMTP凭证")
                self.log_operation('INFO', "状态邮件发送跳过：未配置有效的SMTP凭证")
                return False
            
            # 准备邮件内容
            check_time = check_result.get('check_time', get_beijing_time_str())
            total_repos = check_result.get('total_repos', 0)
            repos_with_changes = check_result.get('repos_with_changes', 0)
            total_changes = check_result.get('total_changes', 0)
            repos_checked = check_result.get('repos_checked', [])
            errors = check_result.get('errors', [])
            
            # 创建邮件主题
            subject = f"SVN监控程序运行状态报告 - {check_time}"
            
            # 创建邮件正文
            body = f"""
            <html>
            <body>
                <h2>SVN监控程序运行状态报告</h2>
                <p><strong>检测时间：</strong>{check_time}</p>
                
                <h3>检测概况</h3>
                <table border="1" cellpadding="5" cellspacing="0">
                    <tr>
                        <td><strong>监控仓库总数</strong></td>
                        <td>{total_repos}</td>
                    </tr>
                    <tr>
                        <td><strong>本次检测仓库数</strong></td>
                        <td>{len(repos_checked)}</td>
                    </tr>
                    <tr>
                        <td><strong>有变更的仓库数</strong></td>
                        <td>{repos_with_changes}</td>
                    </tr>
                    <tr>
                        <td><strong>检测到的变更总数</strong></td>
                        <td>{total_changes}</td>
                    </tr>
                </table>
                
                <h3>检测的仓库列表</h3>
                <table border="1" cellpadding="5" cellspacing="0">
                    <tr bgcolor="#f2f2f2">
                        <th>仓库ID</th>
                        <th>仓库名称</th>
                        <th>状态</th>
                    </tr>
            """
            
            # 添加仓库详情
            for repo_name in repos_checked:
                # 使用动态加载的仓库名称映射（从Excel配置文件读取）
                repo_name_mapping = self.repo_name_mapping
                chinese_repo_name = repo_name_mapping.get(repo_name, repo_name)
                
                # 查找英文ID（REPO_*）
                repo_id = None
                for key, value in self.repo_name_mapping.items():
                    if key.startswith('REPO_') and (value == chinese_repo_name or key == repo_name):
                        repo_id = key
                        break
                if repo_id is None:
                    repo_id = repo_name
                
                # 检查该仓库是否有变更
                has_change = False
                if repos_with_changes > 0 and total_changes > 0:
                    # 这里简化处理，实际可以根据check_result中的详细信息判断
                    has_change = False
                
                status = "正常" if not has_change else "有变更"
                status_color = "green" if not has_change else "orange"
                
                body += f"""
                    <tr>
                        <td>{repo_id}</td>
                        <td>{chinese_repo_name}</td>
                        <td style='color: {status_color}; font-weight: bold;'>{status}</td>
                    </tr>
                """
            
            body += """
                </table>
            """
            
            # 添加错误信息（如果有）
            if errors:
                body += """
                <h3 style='color: red;'>检测过程中发生的错误</h3>
                <table border="1" cellpadding="5" cellspacing="0">
                    <tr bgcolor="#f2f2f2">
                        <th>仓库</th>
                        <th>错误信息</th>
                    </tr>
                """
                for error in errors:
                    repo_name = error.get('repo', '未知')
                    error_msg = error.get('message', '未知错误')
                    body += f"""
                        <tr>
                            <td>{repo_name}</td>
                            <td style='color: red;'>{error_msg}</td>
                        </tr>
                    """
                body += """
                </table>
                """
            
            body += """
                <p><em>此邮件由SVN监控程序自动发送，请勿回复。</em></p>
            </body>
            </html>
            """
            
            # 创建邮件消息
            msg = MIMEMultipart('alternative')
            msg['From'] = self.config['EMAIL']['from_email']
            # 状态邮件发送给pyc@lektec.com
            msg['To'] = 'pyc@lektec.com'
            msg['Subject'] = subject

            # 附加HTML正文
            msg.attach(MIMEText(body, 'html'))

            # 发送邮件
            success = self._send_email(msg)
            if success:
                logger.info("程序运行状态邮件发送成功")
                self.log_operation('SUCCESS', "程序运行状态邮件发送成功")
            else:
                logger.warning("程序运行状态邮件发送失败")
                self.log_operation('WARNING', "程序运行状态邮件发送失败")

            return success
        except Exception as e:
            logger.error(f"发送程序运行状态邮件时出错：{str(e)}")
            self.log_operation('ERROR', f"发送程序运行状态邮件时出错：{str(e)}")
            return False

    def setup_auto_startup(self):
        """Set up the script to run automatically on startup (Windows)"""
        try:
            if sys.platform == 'win32':
                import winreg

                # Get the path to the current script
                script_path = os.path.abspath(__file__)
                python_exe = sys.executable

                # Create a batch file to run the script
                batch_path = os.path.join(os.path.dirname(script_path),
                                          'run_svn_monitor.bat')
                with open(batch_path, 'w') as f:
                    f.write('@echo off\n')
                    f.write(f'"{python_exe}" "{script_path}"\n')
                    f.write('exit\n')

                # Add to startup registry
                key = winreg.OpenKey(
                    winreg.HKEY_CURRENT_USER,
                    r'SOFTWARE\Microsoft\Windows\CurrentVersion\Run',
                    0,
                    winreg.KEY_SET_VALUE
                )
                winreg.SetValueEx(key, 'SVN_Monitor', 0, winreg.REG_SZ,
                                 batch_path)
                winreg.CloseKey(key)
                
                logger.info(f"Auto startup configured. Script will run on system boot.")
            else:
                logger.warning("Auto startup setup is only supported on Windows.")
        except Exception as e:
            logger.error(f"Failed to set up auto startup: {str(e)}")
            raise

    # 备份功能已移除

    def _validate_config(self):
        """Validate the configuration settings"""
        # Global required sections
        required_sections = ['EMAIL', 'LOGGING', 'SYSTEM']

        # Ensure all required global sections exist
        for section in required_sections:
            if section not in self.config:
                logger.warning(
                    f"Configuration section '{section}' missing. Creating default settings."
                )
                self.config[section] = {}

        # Ensure SYSTEM section has required keys
        if 'auto_startup' not in self.config['SYSTEM']:
            self.config['SYSTEM']['auto_startup'] = 'True'
        if 'use_remote_check' not in self.config['SYSTEM']:
            self.config['SYSTEM']['use_remote_check'] = 'True'

        # Check for at least one repository configuration
        repositories = self._get_repositories()
        if not repositories:
            logger.warning(
                "No repository configurations found. Creating a default repository configuration."
            )
            self._create_default_repository_config()
        else:
            # Validate each repository configuration has required fields
            for repo_name, repo_config in repositories.items():
                # Ensure local_working_copy exists for all repositories
                if 'local_working_copy' not in repo_config:
                    logger.warning(
                        f"Repository '{repo_name}' missing 'local_working_copy'. Adding default path."
                    )
                    # Create a default working copy path
                    default_path = os.path.join(
                        os.path.dirname(os.path.abspath(__file__)), 'svn_wc',
                        repo_name
                    )
                    repo_config['local_working_copy'] = default_path

        # No need to save configuration to file as we're using Excel for configuration management

    def run(self):
        """Main run method for the SVN monitor"""
        try:
            # Default to monitor mode
            mode = "远程检测模式" if self.use_remote_check else "本地检测模式"
            logger.info(f"Starting SVN Monitor ({mode})")
            
            # 在远程检测模式下跳过本地工作副本初始化
            if not self.use_remote_check:
                # Ensure working copies are properly initialized
                for repo_name, repo_config in self.repositories.items():
                    self._ensure_working_copy(repo_config)
            else:
                logger.info("Running in remote check mode, skipping local working copy initialization")
            
            # Setup auto startup if enabled
            if self.config['SYSTEM'].get('auto_startup', 'True').lower() == 'true':
                try:
                    self.setup_auto_startup()
                except Exception as e:
                    logger.warning(f"Failed to setup auto startup: {str(e)}")
            
            # Main monitoring loop
            # 使用基于时间的调度，确保检查间隔准确
            min_check_interval = min(
                int(repo_config.get('check_interval', str(DEFAULT_CHECK_INTERVAL))) 
                for repo_config in self.repositories.values()
            )
            
            # 记录上一次检查的时间
            last_check_time = time.time()
            
            # 启动时立即检测一次版本变化（不等待第一个检查间隔）
            logger.info("服务启动，立即检查所有仓库变更...")
            try:
                all_changes = []
                changes_to_update = {}
                errors = []  # 收集所有仓库检查错误
                
                # Fix: Dynamically reread last_revisions.json file to ensure using the latest version records
                self.last_revisions = self._get_last_recorded_revisions()
                
                # Check each repository for changes
                for repo_name, repo_config in self.repositories.items():
                    try:
                        # Check for changes
                        latest_revision = self.get_latest_revision(repo_config)
                        last_revision = self.last_revisions.get(repo_name, 0)
                        
                        if latest_revision > last_revision:
                            logger.info(f"New changes detected in repository '{repo_name}': {last_revision} -> {latest_revision}")
                            # Log the detected changes
                            self.log_operation('CHANGE_DETECTED', 
                                              f"New changes detected: {last_revision} -> {latest_revision}",
                                              repository=repo_name)
                            changes = self.get_changes(last_revision, latest_revision, repo_config)
                            
                            # Only add changes if notifications are enabled for this repository
                            if repo_config.get('notify_on_changes', 'True').lower() == 'true':
                                all_changes.extend(changes)
                                # Store changes and revision info for this repository
                                changes_to_update[repo_name] = {
                                    'last_revision': last_revision,
                                    'latest_revision': latest_revision
                                }
                            else:
                                # If notifications are disabled, update revision immediately
                                self.last_revisions[repo_name] = latest_revision
                                # Save immediately for repos with notifications disabled
                                self._save_last_revisions(self.last_revisions)
                    except Exception as e:
                        error_msg = f"Error checking repository '{repo_name}': {str(e)}"
                        logger.error(error_msg)
                        self.log_operation('ERROR', error_msg, repository=repo_name)
                        # 收集错误信息
                        errors.append({
                            'repo': repo_name,
                            'message': error_msg
                        })
                        # Continue with other repositories even if one fails
                
                # No unconditional save here to ensure revisions are only saved after successful email or for disabled notifications
                
                # 记录检查完成的日志
                logger.info("所有仓库检查完成，准备处理变更通知")
                
                # Send notifications for all changes
                if all_changes:
                    email_success = self.send_email_notification(all_changes)
                    # Only update and save revision numbers if email was sent successfully
                    if email_success:
                        logger.info("Email notification successful, updating repository revision numbers")
                        # Create a temporary copy to avoid modifying self.last_revisions directly
                        temp_revisions = self.last_revisions.copy()
                        for repo_name, info in changes_to_update.items():
                            temp_revisions[repo_name] = info['latest_revision']
                        # Only update and save if all updates were successful
                        self.last_revisions = temp_revisions
                        self._save_last_revisions(self.last_revisions)
                    else:
                        logger.warning("Email notification failed, keeping original revision numbers")
                        # Explicitly reload last revisions to ensure no changes were made
                        self.last_revisions = self._get_last_recorded_revisions()
                
                # 服务启动后发送状态通知邮件，无论是否有变更
                try:
                    # 准备状态邮件的检测结果数据
                    check_result = {
                        'check_time': get_beijing_time_str(),
                        'total_repos': len(self.repositories),
                        'repos_with_changes': len(changes_to_update),
                        'total_changes': len(all_changes),
                        'repos_checked': list(self.repositories.keys()),
                        'errors': errors  # 包含所有收集到的错误信息
                    }
                    
                    # 发送状态邮件
                    self.send_status_email(check_result)
                except Exception as e:
                    logger.error(f"发送程序运行状态邮件时出错：{str(e)}")
                    # 状态邮件发送失败不影响主程序运行
            except Exception as e:
                error_msg = f"Error in initial repository check: {str(e)}"
                logger.error(error_msg)
                self.log_operation('ERROR', error_msg)
            
            while self.running:
                try:
                    # 计算应该等待的时间
                    current_time = time.time()
                    elapsed = current_time - last_check_time
                    
                    # 如果距离上次检查的时间小于最小间隔，等待剩余时间
                    if elapsed < min_check_interval:
                        wait_time = min_check_interval - elapsed
                        logger.info(f"等待 {wait_time:.2f} 秒后进行下一次仓库检查，当前时间: {get_beijing_time_str()}")
                        # 使用小步循环等待，以便能够响应终止信号
                        remaining_time = wait_time
                        start_wait_time = time.time()
                        while remaining_time > 0 and self.running:
                            time.sleep(min(1, remaining_time))  # 最多等待1秒
                            remaining_time = wait_time - (time.time() - start_wait_time)
                        
                        # 如果在等待期间收到终止信号，直接退出循环
                        if not self.running:
                            break
                    
                    # 更新最后检查时间
                    last_check_time = time.time()
                    logger.info(f"开始检查所有仓库变更，当前时间: {get_beijing_time_str()}")
                    
                    all_changes = []
                    changes_to_update = {}
                    errors = []  # 收集所有仓库检查错误
                    
                    # Fix: Dynamically reread last_revisions.json file to ensure using the latest version records
                    self.last_revisions = self._get_last_recorded_revisions()
                    
                    # Check each repository for changes
                    for repo_name, repo_config in self.repositories.items():
                        try:
                            # Check for changes
                            latest_revision = self.get_latest_revision(repo_config)
                            last_revision = self.last_revisions.get(repo_name, 0)
                            
                            if latest_revision > last_revision:
                                logger.info(f"New changes detected in repository '{repo_name}': {last_revision} -> {latest_revision}")
                                # Log the detected changes
                                self.log_operation('CHANGE_DETECTED', 
                                                  f"New changes detected: {last_revision} -> {latest_revision}",
                                                  repository=repo_name)
                                changes = self.get_changes(last_revision, latest_revision, repo_config)
                                
                                # Only add changes if notifications are enabled for this repository
                                if repo_config.get('notify_on_changes', 'True').lower() == 'true':
                                    all_changes.extend(changes)
                                    # Store changes and revision info for this repository
                                    changes_to_update[repo_name] = {
                                        'last_revision': last_revision,
                                        'latest_revision': latest_revision
                                    }
                                else:
                                    # If notifications are disabled, update revision immediately
                                    self.last_revisions[repo_name] = latest_revision
                                    # Save immediately for repos with notifications disabled
                                    self._save_last_revisions(self.last_revisions)
                        except Exception as e:
                            error_msg = f"Error checking repository '{repo_name}': {str(e)}"
                            logger.error(error_msg)
                            self.log_operation('ERROR', error_msg, repository=repo_name)
                            # 收集错误信息
                            errors.append({
                                'repo': repo_name,
                                'message': error_msg
                            })
                            # Continue with other repositories even if one fails
                    
                    # No unconditional save here to ensure revisions are only saved after successful email or for disabled notifications
                    
                    # 记录检查完成的日志
                    logger.info("所有仓库检查完成，准备处理变更通知")
                    
                    # Send notifications for all changes
                    if all_changes:
                        email_success = self.send_email_notification(all_changes)
                        # Only update and save revision numbers if email was sent successfully
                        if email_success:
                            logger.info("Email notification successful, updating repository revision numbers")
                            # Create a temporary copy to avoid modifying self.last_revisions directly
                            temp_revisions = self.last_revisions.copy()
                            for repo_name, info in changes_to_update.items():
                                temp_revisions[repo_name] = info['latest_revision']
                            # Only update and save if all updates were successful
                            self.last_revisions = temp_revisions
                            self._save_last_revisions(self.last_revisions)
                        else:
                            logger.warning("Email notification failed, keeping original revision numbers")
                            # Explicitly reload last revisions to ensure no changes were made
                            self.last_revisions = self._get_last_recorded_revisions()
                    
                    # 每次定时检测完成后，发送程序运行状态邮件
                    try:
                        # 准备状态邮件的检测结果数据
                        check_result = {
                            'check_time': get_beijing_time_str(),
                            'total_repos': len(self.repositories),
                            'repos_with_changes': len(changes_to_update),
                            'total_changes': len(all_changes),
                            'repos_checked': list(self.repositories.keys()),
                            'errors': errors  # 包含所有收集到的错误信息
                        }
                        
                        # 发送状态邮件
                        self.send_status_email(check_result)
                    except Exception as e:
                        logger.error(f"发送程序运行状态邮件时出错：{str(e)}")
                        # 状态邮件发送失败不影响主程序运行
                        
                except KeyboardInterrupt:
                    logger.info("SVN Monitor stopped by user")
                    self.log_operation('INFO', "SVN Monitor stopped by user")
                    break
                except Exception as e:
                    error_msg = f"Error in monitoring loop: {str(e)}"
                    logger.error(error_msg)
                    self.log_operation('ERROR', error_msg)
                    # 发生异常时，仍然保持原有的检查间隔，但给系统一点恢复时间
                    # 使用配置的最小检查间隔，确保时间设置的一致性和动态性
                    logger.info(f"监控循环发生异常，将在 {min_check_interval} 秒后重试")
                    time.sleep(min_check_interval)  # 等待配置的最小检查间隔后重试
        except Exception as e:
            logger.error(f"Fatal error in run method: {str(e)}")
            raise


def main():
    """Main entry point - can be run in monitor mode or hook mode"""
    try:
        import argparse
        
        # Parse command line arguments
        parser = argparse.ArgumentParser(description='SVN Monitor Script')
        parser.add_argument('--repository', help='Repository path (used by SVN hooks)')
        parser.add_argument('--revision', help='Revision number (used by SVN hooks)')
        args = parser.parse_args()
        
        monitor = SVNMonitor()
        
        # If repository and revision are provided, run in hook mode
        if args.repository and args.revision:
            logger.info(f"Running in hook mode for repository: {args.repository}, revision: {args.revision}")
            monitor.process_commit(args.repository, args.revision)
        else:
            # Otherwise run in normal monitor mode (continuous monitoring)
            logger.info("Running in continuous monitor mode")
            monitor.run()
    except Exception as e:
        logger.critical(f"Unhandled exception: {str(e)}")
        sys.exit(1)


if __name__ == "__main__":
    main()