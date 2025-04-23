# src/utils.py
import os
import sys # 为处理 sys.exit 的可能性而添加，尽管 git_utils 处理了它。

def clear_screen():
    """清空屏幕"""
    os.system("cls" if os.name == "nt" else "clear")

# extract_repo_name_from_upstream_url 已移至 config_manager.py