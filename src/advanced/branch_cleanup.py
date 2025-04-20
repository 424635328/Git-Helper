# src/advanced/branch_cleanup.py
from src.utils import clear_screen
from src.git_utils import run_git_command

def delete_local_branch():
    """删除本地分支
    命令: git branch -d <local_branch_name>
    """
    clear_screen()
    print("=====================================================")
    print(" [高级] 删除本地分支")
    print("=====================================================")
    print("\n")

    print("\n 正在获取本地分支列表...")
    return_code_list, stdout_list, stderr_list = run_git_command(["git", "branch"])
    if return_code_list != 0:
        print("\n **错误**: 获取本地分支列表失败。")
        input("按任意键继续...") # Keep input here for pause
        return

    print("\n 本地分支列表:")
    print(stdout_list)

    local_branch = input(" 请输入要删除的本地分支名称: ")
    if not local_branch:
        print("\n **错误**: 分支名称不能为空！")
        input("按任意键继续...") # Keep input here for pause
        return

    # Simple check if branch is in the list (not precise, just checks string inclusion)
    if local_branch.strip() not in [b.strip() for b in stdout_list.splitlines()]:
         print(f"\n **警告**: 分支 '{local_branch}' 似乎不在本地分支列表中。请仔细检查名称。")
         confirm_exist = input(" 继续删除操作吗？ (yes/no): ")
         if confirm_exist.lower() != 'yes':
              print("\n操作已取消。")
              input("按任意键继续...") # Keep input here for pause
              return

    print(f"\n 正在删除本地分支 '{local_branch}'...")
    print(" 如果分支未合并，需要强制删除 (-D 选项)。")
    force_delete = input(" 未合并分支是否强制删除 (-D)? (yes/no, 默认为 no): ")

    command = ["git", "branch"]
    if force_delete.lower() == 'yes':
        command.append("-D") # Force delete
    else:
        command.append("-d") # Safe delete (only if merged)
    command.append(local_branch)

    return_code, stdout, stderr = run_git_command(command)

    if return_code != 0:
        print(f"\n **错误**: 删除本地分支 '{local_branch}' 失败。")
        if "-d" in command and "not fully merged" in (stdout + stderr).lower():
             print("\n **提示**: 分支未完全合并。如果确定要删除，请尝试使用强制删除选项 (-D)。")
        elif "checked out branch" in (stdout + stderr).lower():
             print("\n **提示**: 你不能删除当前所在的分支。请先切换到其他分支。")
        else:
             print("  请检查分支名称是否正确。")
    else:
        print(f"\n 本地分支 '{local_branch}' 已成功删除。")

    input("按任意键继续...")


def delete_remote_branch():
    """删除远程分支
    命令: git push origin --delete <remote_branch_name>
    """
    clear_screen()
    print("=====================================================")
    print(" [高级] 删除远程分支")
    print("=====================================================")
    print("\n")

    remote_branch = input(" 请输入要删除的远程分支名称: ")
    if not remote_branch:
        print("\n **错误**: 分支名称不能为空！")
        input("按任意键继续...") # Keep input here for pause
        return

    remote_name = input(" 请输入远程仓库名称 (默认为 origin): ")
    if not remote_name:
        remote_name = "origin"

    print(f"\n **警告：** 你确定要删除远程仓库 '{remote_name}' 上的分支 '{remote_branch}' 吗？")
    confirmation = input("  输入 'yes' 继续，输入其他任何内容取消操作： ")
    if confirmation.lower() != "yes":
        print("\n操作已取消。")
        input("按任意键继续...") # Keep input here for pause
        return

    print(f"\n 正在删除远程分支 '{remote_branch}' 在 '{remote_name}' 上...")
    return_code, stdout, stderr = run_git_command(
        ["git", "push", remote_name, "--delete", remote_branch]
    )
    if return_code != 0:
        print(f"\n **错误**: 删除远程分支 '{remote_branch}' 失败。")
        print("\n  常见错误：")
        print("  - 没有删除权限：确认你对该远程仓库有删除分支的权限。")
        print("  - 远程分支不存在：确认远程分支名称是否正确。")
        print("  - 网络问题：确认网络连接正常。")
    else:
        print(f"\n 远程分支 '{remote_branch}' 在 '{remote_name}' 上已成功删除。")

    input("\n按任意键继续...")