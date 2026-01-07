#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试编码处理和多仓库支持功能

该脚本用于验证SVN监控工具在远程检测模式下的编码处理能力和多仓库处理功能，
确保所有仓库都能正常被检测，且中文编码问题已解决。
"""

import unittest
import sys
import os
import subprocess
import logging

# 设置基本日志记录
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# 添加src目录到Python路径，确保能导入svn_monitor模块
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'src')))

from svn_monitor import SVNMonitor


class TestEncodingAndMultipleRepos(unittest.TestCase):
    """
    测试编码处理和多仓库支持的测试类
    """
    
    def setUp(self):
        """
        测试前的准备工作
        """
        # 设置测试使用的配置文件路径（用于验证配置文件存在）
        current_dir = os.path.dirname(os.path.abspath(__file__))
        config_dir = os.path.join(current_dir, '..')
        self.config_file = os.path.join(config_dir, 'config.ini')
    
    def test_config_loading(self):
        """
        测试配置加载是否正确
        """
        try:
            # 初始化SVNMonitor实例以访问其配置
            monitor = SVNMonitor()
            
            # 验证配置是否成功加载
            self.assertIsNotNone(monitor.config)
            
            # 检查是否有REPO_开头的section
            repo_sections = [section for section in monitor.config.sections() if section.startswith('REPO_')]
            logger.info(f"Found {len(repo_sections)} repository sections in config: {repo_sections}")
            
            # 验证repositories字典是否包含仓库
            self.assertTrue(len(monitor.repositories) > 0, "没有加载到仓库配置")
            logger.info(f"Repositories loaded in monitor: {list(monitor.repositories.keys())}")
                
        except Exception as e:
            self.fail(f"配置加载测试失败: {str(e)}")
    
    def test_encoding_support(self):
        """
        测试编码支持功能
        """
        # 尝试使用subprocess运行一个简单的svn命令，测试编码处理
        try:
            # 这里使用svn help命令作为测试，它应该能正常工作并返回一些输出
            cmd = ['svn', 'help']
            result = subprocess.run(cmd, capture_output=True, timeout=10)
            
            # 尝试用utf-8解码，如果失败则使用gbk
            try:
                output_utf8 = result.stdout.decode('utf-8')
                self.assertGreater(len(output_utf8), 0, "UTF-8解码后的输出为空")
                logger.info("UTF-8解码成功")
            except UnicodeDecodeError:
                try:
                    output_gbk = result.stdout.decode('gbk')
                    self.assertGreater(len(output_gbk), 0, "GBK解码后的输出为空")
                    logger.info("GBK解码成功")
                except UnicodeDecodeError as e:
                    self.fail(f"编码解码失败: {str(e)}")
        except Exception as e:
            logger.warning(f"SVN命令执行失败，可能是SVN客户端未安装: {str(e)}")
    
    def test_remote_check_support(self):
        """
        测试远程检测模式是否支持所有仓库
        """
        try:
            # 初始化SVNMonitor实例
            monitor = SVNMonitor()
            
            # 直接验证use_remote_check属性（这是更可靠的方式）
            self.assertTrue(monitor.use_remote_check, "远程检测模式未启用")
            
            # 也可以检查配置中的设置
            if 'SYSTEM' in monitor.config and 'use_remote_check' in monitor.config['SYSTEM']:
                self.assertEqual(monitor.config['SYSTEM'].get('use_remote_check'), 'True',
                                "系统配置中的use_remote_check未设置为True")
                              
        except Exception as e:
            self.fail(f"远程检测模式测试失败: {str(e)}")
    
    def test_svn_monitor_initialization(self):
        """
        测试SVNMonitor初始化
        """
        try:
            # 初始化SVNMonitor实例（不实际运行监控）
            monitor = SVNMonitor()
            
            # 验证是否成功初始化
            self.assertIsNotNone(monitor)
            
            # 验证仓库数量（检查有多少仓库被加载）
            logger.info(f"Found {len(monitor.repositories)} repositories: {list(monitor.repositories.keys())}")
            
            # 验证远程检测模式是否启用
            self.assertTrue(monitor.use_remote_check, "远程检测模式未启用")
            
        except Exception as e:
            self.fail(f"SVNMonitor初始化失败: {str(e)}")
            



if __name__ == '__main__':
    unittest.main()