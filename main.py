import sys
import os

# Import necessary modules from src
from src.config_manager import config, load_config_from_git
from src.utils import clear_screen

from src.basic_operations import (
    show_status, show_log, show_diff, add_changes, commit_changes,
)
from src.branch_sync import (
    create_switch_branch, pull_changes, push_branch, sync_fork,
)
from src.advanced import driver as advanced_driver


def main_menu():
    """显示主菜单并获取用户选择"""
    clear_screen()
    print("=====================================================")

    # --- 根据配置显示标题 ---
    repo_type = config.get('repo_type', '未确定')
    base_repo_display = config.get('base_repo', '未加载')
    origin_user_display = config.get('fork_username', '未加载') # 现在代表 origin 的 owner
    origin_repo_display = config.get('fork_repo_name', '未加载') # 现在代表 origin 的 repo name
    branch_display = config.get('default_branch_name', '未加载')

    if repo_type == 'original':
        print(f" [ 项目贡献助手 - 原始仓库: {base_repo_display} ]")
        print(f" [ Owner: {origin_user_display} | 默认分支: {branch_display} ]")
    elif repo_type == 'fork':
        # 对于 Fork，显示 Base 和 Fork 的信息可能更有用
        print(f" [ 项目贡献助手 - Base: {base_repo_display} ]")
        print(f" [ Fork: {origin_user_display}/{origin_repo_display} | 默认分支: {branch_display} ]")
    else: # 加载失败或未确定
        print(f" [ 项目贡献助手 - 仓库: {base_repo_display} ]") # 显示检测失败信息
        print(f" [ 用户: {origin_user_display} | 分支: {branch_display} ]")

    print("=====================================================")

    # --- 根据配置显示菜单项 ---
    if not config.get('is_git_repo', False) or repo_type == '未确定':
        print("\n错误：无法加载仓库信息或当前不在 Git 仓库中。")
        print("\n --- 其他 ---")
        print(" [0]  退出")
        while True:
            choice = input(" 请选择 (0): ")
            if choice == "0": return choice
            else: print("\n **错误**: 无效的选择。")
    else:
        # 只有在 Git 仓库中且类型确定时显示完整菜单
        print("\n 请选择操作:")
        print("\n --- 高级操作与管理 ---")
        print(" [10] 进入高级操作菜单")

        print("\n --- 分支与同步 ---")
        print(" [6]  创建/切换分支")
        print(" [7]  拉取远程更改 (建议从 origin)") # 拉取通常从 origin 或 upstream
        print(" [8]  推送本地分支 (推送到 origin)")

        # Sync Fork 功能仅对 Fork 类型且成功检测到 Base 仓库时有意义
        sync_fork_label = "[9]  同步 Fork (从 Upstream)"
        sync_fork_enabled = False
        if repo_type == 'fork':
            # 检查 base_repo 是否检测成功 (不是失败状态)
            if "检测失败" not in base_repo_display and base_repo_display != '未确定' and base_repo_display != '加载中...':
                sync_fork_enabled = True
            else:
                sync_fork_label += " (需设置 upstream)"
        else: # original 类型不需要同步
             sync_fork_label = "[9]  (同步 Fork 不适用于原始仓库)"

        print(f" {sync_fork_label}")


        print("\n --- 基础操作 ---")
        print(" [1]  查看仓库状态")
        print(" [2]  查看提交历史")
        print(" [3]  查看文件差异")
        print(" [4]  添加修改")
        print(" [5]  提交修改")
        print("\n --- 其他 ---")
        print(" [0]  退出")

        while True:
            choice = input(" 请选择 (0-10): ").strip()
            # 检查选择是否有效，并阻止选择禁用的 sync_fork
            if choice == '9' and not sync_fork_enabled:
                if repo_type == 'original':
                    print("\n **提示**: 此功能仅适用于 Fork 仓库。")
                else: # 是 fork 但未成功配置 upstream
                    print("\n **错误**: 需要先正确设置 'upstream' 远程仓库才能使用此功能。")
                    print("         请使用 'git remote add upstream <原始仓库URL>' 添加。")
                input("按任意键继续...")
                return None # 返回 None 让主循环重新显示菜单
            elif choice == "0" or (choice.isdigit() and 1 <= int(choice) <= 10):
                return choice
            else:
                print("\n **错误**: 无效的选择，请重新选择.")


if __name__ == "__main__":
    # 使用新的函数从 Git 配置加载
    load_config_from_git()

    # 主循环
    while True:
        # 检查是否是 Git 仓库或加载失败
        if not config.get('is_git_repo', False) or config.get('repo_type') == '未确定':
             choice = main_menu() # 显示受限菜单
             if choice == '0':
                 break
             else: # 理论上不会有其他选择
                 continue

        choice = main_menu() # 显示完整或部分禁用的菜单

        if choice is None: # 例如选择了禁用的 sync_fork
            continue

        if choice == "0":
            clear_screen()
            print("\n 感谢使用！")
            break

        # --- 执行操作 --- (确保操作前检查所需配置是否有效)
        if choice == "1": show_status()
        elif choice == "2": show_log()
        elif choice == "3": show_diff()
        elif choice == "4": add_changes()
        elif choice == "5": commit_changes()
        elif choice == "6": create_switch_branch() # 内部可能需要检查 config
        elif choice == "7": pull_changes()       # 内部可能需要检查 config
        elif choice == "8": push_branch()        # 内部可能需要检查 config
        elif choice == "9":
            # 双重检查，尽管菜单已尝试阻止
            if config.get('repo_type') == 'fork' and \
               ("检测失败" not in config.get('base_repo', '检测失败') and \
                config.get('base_repo') != '未确定'):
                 sync_fork() # 内部应使用 config['base_repo'] 和 upstream remote
            else:
                 # 这个分支理论上不应该被达到，因为菜单逻辑会阻止
                 print("\n **内部错误**: sync_fork 条件检查失败。")
                 input("按任意键继续...")
        elif choice == "10": advanced_driver.run_advanced_menu()
        # else 分支由 main_menu 处理无效输入