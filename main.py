# main.py
import sys
import os

# Import necessary modules from src
from src.config_manager import config, load_config, extract_repo_name_from_upstream_url
from src.utils import clear_screen

# Import specific operation functions from src modules
# Basic operations (1-5) are still called directly from main.py
from src.basic_operations import (
    show_status,
    show_log,
    show_diff,
    add_changes,
    commit_changes,
)
# Branch and sync operations (6-9) are still called directly from main.py
from src.branch_sync import (
    create_switch_branch,
    pull_changes,
    push_branch,
    sync_fork,
)
# Import the advanced operations driver
from src.advanced import driver as advanced_driver


def main_menu():
    """显示主菜单并获取用户选择"""
    clear_screen()
    print("=====================================================")
    print(" [ 项目贡献助手 ]")
    print("=====================================================")
    print("\n 请选择操作:")
    print("\n --- 高级操作与管理 ---")
    print(" [10] 进入高级操作菜单 (合并, 变基, 储藏, 标签, 远程等)") # New option to enter the advanced sub-menu
    # Note: Specific advanced operations (10-19) are *not* listed here anymore

    print("\n --- 分支与同步 ---")
    print(" [6]  创建/切换分支       (git checkout -b / git checkout)")
    print(" [7]  拉取远程更改        (git pull)")
    print(" [8]  推送本地分支        (git push)")
    print(" [9]  同步 Fork (Upstream) (从上游拉取到本地并推送到origin)")
    print("\n --- 基础操作 ---")
    print(" [1]  查看仓库状态        (git status)")
    print(" [2]  查看提交历史        (git log)")
    print(" [3]  查看文件差异        (git diff)")
    print(" [4]  添加修改            (git add)")
    print(" [5]  提交修改            (git commit)")
    print(" [0]  退出                (exit) ")
    while True:
        # Allowed choices: 0, 1-9, 10 (for advanced menu)
        choice = input(" 请选择 (0-10): ")
        if choice == "0" or (choice.isdigit() and 1 <= int(choice) <= 10):
            return choice
        else:
            print("\n **错误**: 无效的选择，请重新选择.")
            input("按任意键继续...")


if __name__ == "__main__":
    # Load configuration
    load_config()

    # Get and set fork_username and base_repo
    default_fork_username = config.get("default_fork_username", "your_github_username")
    fork_username = input(
        f"请输入你的 GitHub 用户名 (你的 Fork 仓库的所有者, 默认为 '{default_fork_username}'): "
    )
    if not fork_username:
        fork_username = default_fork_username
        print(f"使用默认 GitHub 用户名: {fork_username}")
    config["fork_username"] = fork_username  # Update config

    extracted_base = extract_repo_name_from_upstream_url(config.get("default_upstream_url"))
    default_base_repo = extracted_base if extracted_base else config.get("default_base_repo", "upstream_owner/upstream_repo")

    base_repo = input(
        f"请输入原始仓库的名称 (格式 owner/repo, 默认为 '{default_base_repo}'): "
    )
    if not base_repo:
        base_repo = default_base_repo
        print(f"使用默认原始仓库名称: {base_repo}")
    config["base_repo"] = base_repo  # Update config

    print(f"\n已设置 GitHub 用户名为: {fork_username}")
    print(f"已设置原始仓库为: {base_repo}")
    input("\n按任意键继续...")


    while True:
        choice = main_menu()

        if choice == "0":
            clear_screen()
            print("\n 感谢使用！")
            break
        # Basic operations
        elif choice == "1":
            show_status()
        elif choice == "2":
            show_log()
        elif choice == "3":
            show_diff()
        elif choice == "4":
            add_changes()
        elif choice == "5":
            commit_changes()
        # Branch and sync operations
        elif choice == "6":
            create_switch_branch()
        elif choice == "7":
            pull_changes()
        elif choice == "8":
            push_branch()
        elif choice == "9":
            sync_fork()
        # Advanced Operations Menu Entry
        elif choice == "10":
            advanced_driver.run_advanced_menu() # Delegate to the advanced driver
        else:
            # This else should ideally not be reached due to main_menu validation
            print("\n **错误**: 未知的菜单选项！")
            input("\n按任意键继续...")