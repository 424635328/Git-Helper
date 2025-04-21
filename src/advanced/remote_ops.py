# src/advanced/remote_ops.py
from src.utils import clear_screen
from src.git_utils import run_git_command
from src.config_manager import config# 导入配置和URL提取工具
import os # Needed for os.path.join etc. if needed, not strictly for git commands cwd here.


def setup_upstream():
    """设置 Upstream 仓库地址
    命令: git remote add upstream https://github.com/owner/repo.git
    """
    # clear_screen() # Called from manage_remotes, no need to clear again
    print("\n----------------------------------------------------")
    print(" [高级] -> 设置 Upstream 仓库地址")
    print("----------------------------------------------------")
    print("\n")

    default_upstream = config.get(
        "default_upstream_url", "git@github.com:upstream_owner/upstream_repo.git"
    )
    print(f" 建议将 upstream 设置为原始仓库的地址，例如: {default_upstream}")
    print(" 如果 config.yaml 中已设置 default_upstream_url，将默认使用该地址。")
    print(" 如果 upstream 已存在，此操作会失败。")

    upstream_url = input(f" 请输入上游仓库 (upstream) 的地址 (默认为 {default_upstream}): ")
    if not upstream_url:
        upstream_url = default_upstream

    # Check if upstream already exists
    rc_check, out_check, err_check = run_git_command(["git", "remote", "-v"])
    if rc_check == 0 and f"upstream\t" in out_check:
        print("\n **错误**: 远程仓库 'upstream' 已存在。")
        print("  如果需要更改地址，请先使用 'git remote remove upstream' 删除后再添加 (使用远程仓库管理菜单的删除选项)。")
        # input("按任意键继续...") # Let manage_remotes handle the input
        return


    print(f"\n 正在设置 upstream 为 '{upstream_url}'...")
    return_code, stdout, stderr = run_git_command(
        ["git", "remote", "add", "upstream", upstream_url]
    )
    if return_code != 0:
        print("\n **错误**: 设置 upstream 失败。")
        print("\n  常见原因：upstream 已经存在（可使用删除选项删除后再试）或地址格式错误。")
    else:
        print(f"\n 已成功设置 upstream 为 '{upstream_url}'。")
        print("  现在你可以使用 'git pull upstream <branch_name>' 来从上游仓库拉取更新。")

    # input("按任意键继续...") # Let manage_remotes handle the input


def manage_remotes():
    """管理远程仓库"""
    clear_screen()
    print("=====================================================")
    print(" [高级] 管理远程仓库 (git remote)")
    print("=====================================================")
    print("\n")
    print(" 请选择远程仓库操作:")
    print(" [1]  列出所有远程仓库  (git remote -v)")
    print(" [2]  添加新的远程仓库  (git remote add)")
    print(" [3]  删除指定的远程仓库 (git remote remove)")
    print(" [4]  重命名指定的远程仓库 (git remote rename)")
    print(" [5]  设置 upstream 仓库 (方便同步)") # Direct call to setup_upstream
    print("\n [b]  返回上一级菜单")
    print("\n")

    while True:
        remote_choice = input(" 请选择操作 (1-5, b): ")

        if remote_choice.lower() == 'b':
            return
        elif remote_choice == '1':
            print("\n 正在列出所有远程仓库...")
            return_code, stdout, stderr = run_git_command(["git", "remote", "-v"])
            if return_code == 0:
                print("\n 远程仓库列表:")
                print(stdout if stdout.strip() else " (当前没有远程仓库)")
        elif remote_choice == '2':
            remote_name = input("请输入远程仓库名称 (例如 origin): ")
            if not remote_name:
                print("\n **错误**: 远程仓库名称不能为空！ 操作已取消。")
            else:
                remote_url = input("请输入远程仓库地址 (例如 https://github.com/user/repo.git): ")
                if not remote_url:
                    print("\n **错误**: 远程仓库地址不能为空！ 操作已取消。")
                else:
                    print(f"\n 正在添加远程仓库 '{remote_name}' -> '{remote_url}'...")
                    return_code, stdout, stderr = run_git_command(["git", "remote", "add", remote_name, remote_url])
                    if return_code != 0:
                        print("\n **错误**: 添加远程仓库失败。请检查名称和地址是否正确。")
                    else:
                        print(f"\n 远程仓库 '{remote_name}' 已成功添加。")
        elif remote_choice == '3':
            remote_name = input(" 请输入要删除的远程仓库名称: ")
            if not remote_name:
                print("\n **错误**: 远程仓库名称不能为空！ 操作已取消。")
            else:
                print(f"\n **警告：** 你确定要删除远程仓库 '{remote_name}' 的配置吗？")
                confirmation = input("  输入 'yes' 继续，输入其他任何内容取消操作： ")
                if confirmation.lower() != "yes":
                    print("\n操作已取消。")
                else:
                    print(f"\n 正在删除远程仓库 '{remote_name}'...")
                    return_code, stdout, stderr = run_git_command(["git", "remote", "remove", remote_name])
                    if return_code != 0:
                         print("\n **错误**: 删除远程仓库失败。请检查远程仓库名称是否存在。")
                    else:
                         print(f"\n 远程仓库 '{remote_name}' 的配置已成功删除。")
        elif remote_choice == '4':
            old_name = input(" 请输入要重命名的远程仓库旧名称: ")
            if not old_name:
                print("\n **错误**: 旧名称不能为空！ 操作已取消。")
            else:
                new_name = input(" 请输入要重命名的远程仓库新名称: ")
                if not new_name:
                    print("\n **错误**: 新名称不能为空！ 操作已取消。")
                else:
                    print(f"\n 正在重命名远程仓库 '{old_name}' 为 '{new_name}'...")
                    return_code, stdout, stderr = run_git_command(["git", "remote", "rename", old_name, new_name])
                    if return_code != 0:
                         print("\n **错误**: 重命名远程仓库失败。请检查旧名称是否存在或新名称是否合法。")
                    else:
                         print(f"\n 远程仓库 '{old_name}' 已成功重命名为 '{new_name}'。")
        elif remote_choice == '5':
            setup_upstream() # Call the internal function
        else:
            print("\n **错误**: 无效的选择！")

        input("\n按任意键继续...") # Pause after each operation within the remote management menu