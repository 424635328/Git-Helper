#!/usr/bin/env python3
import os

# 定义项目根目录名称
PROJECT_ROOT = "GitGuiApp"

# 定义要创建的目录结构 (相对路径，以 '/' 结尾表示目录)
directories = [
    f"{PROJECT_ROOT}/ui/",
    f"{PROJECT_ROOT}/core/",
    f"{PROJECT_ROOT}/database/",
]

# 定义要创建的空文件 (相对路径)
files = [
    f"{PROJECT_ROOT}/main.py",
    f"{PROJECT_ROOT}/ui/__init__.py",
    f"{PROJECT_ROOT}/ui/main_window.py",
    f"{PROJECT_ROOT}/core/__init__.py",
    f"{PROJECT_ROOT}/core/git_handler.py",
    f"{PROJECT_ROOT}/core/db_handler.py",
    f"{PROJECT_ROOT}/database/shortcuts.db", # 这个文件会是空的，作为数据库文件的占位符
    f"{PROJECT_ROOT}/requirements.txt",
]

def create_project_structure(root_dir):
    """
    创建项目目录和文件结构
    """
    print(f"Attempting to create project structure rooted at: {os.path.abspath(root_dir)}")

    # 1. 创建所有必要的目录
    for dir_path in directories:
        # 使用 os.path.join 处理路径分隔符，并去掉末尾的 '/'
        cleaned_dir_path = os.path.join(*dir_path.strip('/').split('/'))
        full_path = os.path.join(os.getcwd(), cleaned_dir_path) # 基于当前脚本运行目录

        try:
            os.makedirs(full_path, exist_ok=True) # exist_ok=True 防止目录已存在时报错
            print(f"Created directory: {full_path}")
        except OSError as e:
            print(f"Error creating directory {full_path}: {e}")

    # 2. 创建所有空文件
    for file_path in files:
        # 使用 os.path.join 处理路径分隔符
        cleaned_file_path = os.path.join(*file_path.split('/'))
        full_path = os.path.join(os.getcwd(), cleaned_file_path) # 基于当前脚本运行目录

        # 确保文件的父目录存在 ( যদিও创建目录的步骤已经保证了这一点，但为了鲁棒性可以再检查一次)
        # os.makedirs(os.path.dirname(full_path), exist_ok=True)

        try:
            # 使用 'w' 模式打开文件并立即关闭，即可创建空文件
            with open(full_path, 'w') as f:
                pass
            print(f"Created file: {full_path}")
        except OSError as e:
            print(f"Error creating file {full_path}: {e}")

    print("\nProject structure creation complete.")
    print(f"Structure created under: {os.path.join(os.getcwd(), PROJECT_ROOT)}")

if __name__ == "__main__":
    # 获取脚本运行的当前目录
    current_working_directory = os.getcwd()

    # 调用函数创建结构
    # 结构将创建在脚本当前目录下的 PROJECT_ROOT 文件夹内
    create_project_structure(os.path.join(current_working_directory, PROJECT_ROOT))