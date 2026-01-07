#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
用于查看Excel配置文件结构的脚本
"""

import os
import sys
import pandas as pd
import configparser

def inspect_excel_config():
    """
    查看Excel配置文件的结构
    """
    # 使用项目根目录的config目录中的配置文件
    base_dir = os.path.dirname(os.path.abspath(__file__))
    config_file = os.path.join(base_dir, 'config', 'svn_monitor_config.xlsx')
    
    print(f"检查配置文件: {config_file}")
    print("=" * 60)
    
    # 检查文件是否存在
    if not os.path.exists(config_file):
        print("配置文件不存在!")
        return
    
    # 读取所有工作表
    try:
        excel_file = pd.ExcelFile(config_file)
        sheets = excel_file.sheet_names
        print(f"Excel文件包含的工作表: {sheets}")
        print()
        
        # 读取每个工作表的内容
        for sheet_name in sheets:
            print(f"[工作表: {sheet_name}]")
            df = pd.read_excel(config_file, sheet_name=sheet_name)
            print(f"  行数: {len(df)}")
            print(f"  列数: {len(df.columns)}")
            print(f"  列名: {list(df.columns)}")
            print()
            
            # 打印前5行数据
            print("  前5行数据:")
            print(df.head().to_string(index=False))
            print()
            print("-" * 60)
            print()
            
    except Exception as e:
        print(f"读取Excel文件失败: {str(e)}")

def load_config_from_excel(config, excel_file):
    """
    从Excel文件加载配置到configparser对象
    这是从svn_monitor.py中提取的逻辑
    """
    try:
        import pandas as pd
        
        # 读取所有工作表
        sheets = pd.ExcelFile(excel_file).sheet_names
        
        for section in sheets:
            df = pd.read_excel(excel_file, sheet_name=section)
            
            if df.empty:
                continue
                
            # 检查必要的列是否存在
            if 'key' not in df.columns or 'value' not in df.columns:
                continue
                
            if not config.has_section(section):
                config.add_section(section)
            
            # 将每行的key-value添加到配置中
            for _, row in df.iterrows():
                key = str(row['key']).strip()
                value = str(row['value']).strip()
                
                # 跳过空值
                if key and key.lower() != 'nan' and value and value.lower() != 'nan':
                    config.set(section, key, value)
        
        return True
    except Exception as e:
        print(f"从Excel加载配置失败: {str(e)}")
        return False

def inspect_config_values():
    """
    检查实际加载的配置值
    """
    base_dir = os.path.dirname(os.path.abspath(__file__))
    config_file = os.path.join(base_dir, 'config', 'svn_monitor_config.xlsx')
    
    config = configparser.ConfigParser()
    success = load_config_from_excel(config, config_file)
    
    if success:
        print("\n[成功加载的配置值]")
        print("=" * 60)
        
        for section in config.sections():
            print(f"[{section}]")
            for key, value in config.items(section):
                print(f"  {key}: {value}")
            print()
    else:
        print("无法加载配置值!")

if __name__ == "__main__":
    print("Excel配置文件检查工具")
    print("=" * 60)
    
    inspect_excel_config()
    inspect_config_values()
