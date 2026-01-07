import pandas as pd
import os

# 读取配置文件
excel_file = '/home/alex/aidev/SvnMonitor/config/svn_monitor_config.xlsx'

# 读取全局配置工作表
global_df = pd.read_excel(excel_file, sheet_name='Global Configs')

# 检查是否已经存在SVN全局配置
if not ((global_df['Section'] == 'SVN') & (global_df['Key'] == 'username')).any():
    # 添加SVN全局用户名配置
    new_username_row = pd.DataFrame({
        'Section': ['SVN'],
        'Key': ['username'],
        'Value': ['svn_bot']
    })
    global_df = pd.concat([global_df, new_username_row], ignore_index=True)

if not ((global_df['Section'] == 'SVN') & (global_df['Key'] == 'password')).any():
    # 添加SVN全局密码配置
    new_password_row = pd.DataFrame({
        'Section': ['SVN'],
        'Key': ['password'],
        'Value': ['svn_bot']
    })
    global_df = pd.concat([global_df, new_password_row], ignore_index=True)

# 保存更新后的配置
with pd.ExcelWriter(excel_file, engine='openpyxl', mode='a', if_sheet_exists='replace') as writer:
    global_df.to_excel(writer, sheet_name='Global Configs', index=False)

print("已成功添加全局SVN用户名和密码配置！")
print("更新后的全局配置：")
print(global_df[global_df['Section'] == 'SVN'])
