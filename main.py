import sys
import os

# Import necessary modules from src
# 修改导入，使用新的加载函数，不再需要 extract_repo_name_from_upstream_url (因为它在 config_manager 内部使用)
from src.config_manager import config, load_config_from_git
from src.utils import clear_screen

# Import specific operation functions from src modules
# Basic operations (1-5)
from src.basic_operations import (
    show_status,
    show_log,
    show_diff,
    add_changes,
    commit_changes,
)
# Branch and sync operations (6-9)
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
    print(f" [ 项目贡献助手 - 仓库: {config.get('base_repo', '未知')} ]") # 在标题显示仓库
    print(f" [ Fork 用户: {config.get('fork_username', '未知')} | 默认分支: {config.get('default_branch_name', '未知')} ]") # 显示更多信息
    print("=====================================================")
    print("\n 请选择操作:")
    print("\n --- 高级操作与管理 ---")
    print(" [10] 进入高级操作菜单 (合并, 变基, 储藏, 标签, 远程等)")

    print("\n --- 分支与同步 ---")
    print(" [6]  创建/切换分支       (git checkout -b / git checkout)")
    print(" [7]  拉取远程更改        (git pull origin <当前分支>)") # 菜单提示更具体
    print(" [8]  推送本地分支        (git push origin <当前分支>)") # 菜单提示更具体
    print(" [9]  同步 Fork (Upstream) (从 upstream 拉取并推送到 origin)") # 菜单提示更具体
    print("\n --- 基础操作 ---")
    print(" [1]  查看仓库状态        (git status)")
    print(" [2]  查看提交历史        (git log)")
    print(" [3]  查看文件差异        (git diff)")
    print(" [4]  添加修改            (git add)")
    print(" [5]  提交修改            (git commit)")
    print("\n --- 其他 ---")
    print(" [0]  退出")
    while True:
        choice = input(" 请选择 (0-10): ")
        if choice == "0" or (choice.isdigit() and 1 <= int(choice) <= 10):
            return choice
        else:
            print("\n **错误**: 无效的选择，请重新选择.")
            # 不再需要按键继续，让用户直接重新输入
            # input("按任意键继续...")


if __name__ == "__main__":
    # 使用新的函数从 Git 配置加载
    load_config_from_git()
    input("\n按任意键继续...") # 暂停让用户看到加载的信息
    # 检查是否成功获取了关键信息，如果使用占位符，可以给用户一个更强的提示
    if config.get("fork_username") == "your_github_username" or \
       config.get("base_repo") == "upstream_owner/upstream_repo":
        print("\n*****************************************************")
        print("警告：未能完全从 Git 配置中自动推断出所有信息。")
        print("可能原因：")
        print("  - 当前目录不是有效的 Git 仓库。")
        print("  - 未设置名为 'origin' 的 remote 指向你的 Fork。")
        print("  - 未设置名为 'upstream' 的 remote 指向原始仓库。")
        print("请检查你的 Git remote 配置 ('git remote -v').")
        print("脚本将尝试使用占位符值继续，但部分功能可能无法正常工作。")
        print("*****************************************************")
        input("\n按任意键确认并继续...") # 暂停让用户看到警告
    else:
        print("\nGit 配置信息已成功加载。")
        # 可以选择性地暂停一下让用户看到加载的信息
        # input("\n按任意键继续...")


    # 不再需要提示用户输入 fork_username 和 base_repo
    # fork_username_input = ... (删除)
    # base_repo_input = ... (删除)

    # 打印最终使用的配置（这些值现在由 load_config_from_git 设置）
    # print(f"\n将使用 GitHub 用户名: {config.get('fork_username')}")
    # print(f"将使用原始仓库: {config.get('base_repo')}")
    # print(f"将使用默认分支: {config.get('default_branch_name')}")
    # input("\n按任意键开始...") # 合并到上面的暂停逻辑或移除


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
            create_switch_branch() # 需要确保它能从 config 获取所需信息
        elif choice == "7":
            pull_changes() # 需要确保它能从 config 获取所需信息
        elif choice == "8":
            push_branch() # 需要确保它能从 config 获取所需信息
        elif choice == "9":
            sync_fork() # 这个函数特别依赖 config 中的 upstream 和 fork 信息
        # Advanced Operations Menu Entry
        elif choice == "10":
            advanced_driver.run_advanced_menu() # 确保高级操作也能访问 config
        else:
            print("\n **错误**: 未知的菜单选项！")
            input("\n按任意键继续...")