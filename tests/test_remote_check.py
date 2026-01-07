#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
远程检测模式测试脚本
用于测试 SVN Monitor 的远程检测功能，无需本地工作副本即可检测变更
"""

import os
import sys
import time
import logging
import subprocess
from datetime import datetime

# 添加 src 目录到 Python 路径
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.svn_monitor import SVNMonitor

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('remote_check_test.log'),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger('remote_check_test')

def test_remote_check_mode():
    """
    测试远程检测模式
    """
    logger.info("开始测试远程检测模式...")
    
    try:
        # 创建 SVNMonitor 实例，将自动读取配置
        monitor = SVNMonitor()
        
        # 检查是否启用了远程检测模式
        if monitor.use_remote_check:
            logger.info("远程检测模式已启用")
            
            # 测试获取最新版本号
            for repo_name, repo_config in monitor.repositories.items():
                try:
                    logger.info(f"测试仓库: {repo_name}")
                    
                    # 获取最新版本号
                    latest_revision = monitor.get_latest_revision(repo_config)
                    logger.info(f"仓库 {repo_name} 的最新版本号: {latest_revision}")
                    
                    # 获取最近的变更 (如果有)
                    last_revision = max(0, latest_revision - 5)  # 获取最近5个版本的变更
                    logger.info(f"获取仓库 {repo_name} 版本 {last_revision} 到 {latest_revision} 的变更")
                    
                    changes = monitor.get_changes(last_revision, latest_revision, repo_config)
                    logger.info(f"成功获取到 {len(changes)} 个变更记录")
                    
                    # 打印部分变更信息
                    for i, change in enumerate(changes[:3]):  # 只打印前3个
                        logger.info(f"变更 {i+1}:")
                        logger.info(f"  版本: {change['revision']}")
                        logger.info(f"  作者: {change['author']}")
                        logger.info(f"  日期: {change['date']}")
                        logger.info(f"  消息: {change['message'][:100]}..." if len(change['message']) > 100 else f"  消息: {change['message']}")
                        logger.info(f"  变更文件数: {len(change['changed_paths'])}")
                    
                except Exception as e:
                    logger.error(f"测试仓库 {repo_name} 时出错: {str(e)}")
        else:
            logger.warning("远程检测模式未启用，请在配置中设置 use_remote_check = True")
            logger.info("您可以通过以下方式启用:")
            logger.info("1. 在 Excel 配置文件的 SYSTEM 部分添加 use_remote_check = True")
            logger.info("2. 或者修改默认配置文件中的相应设置")
        
    except Exception as e:
        logger.error(f"测试过程中发生错误: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())

if __name__ == "__main__":
    logger.info("==========================================")
    logger.info(f"SVN Monitor 远程检测模式测试 - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info("==========================================")
    
    test_remote_check_mode()
    
    logger.info("测试完成")
    logger.info("==========================================")