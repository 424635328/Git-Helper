# src/utils.py
import os
import sys # Added for sys.exit handling possibility, though git_utils handles it.

def clear_screen():
    """清空屏幕"""
    os.system("cls" if os.name == "nt" else "clear")

# extract_repo_name_from_upstream_url moved to config_manager.py