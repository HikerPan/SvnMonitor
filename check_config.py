import pandas as pd
import os

# 读取配置文件
config_file = '/home/alex/aidev/SvnMonitor/config/svn_monitor_config.xlsx'

# 读取仓库配置工作表
repo_df = pd.read_excel(config_file, sheet_name='Repository Configs')
print("仓库配置:")
print(repo_df)
print("\n")

# 读取全局配置工作表
global_df = pd.read_excel(config_file, sheet_name='Global Configs')
print("全局配置:")
print(global_df)
