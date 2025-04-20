# src/branch_sync.py
from src.utils import clear_screen
from src.git_utils import run_git_command
from src.config_manager import config # 导入配置

def create_switch_branch():
    """创建并切换到新分支 或 切换到已有分支
    命令: git checkout -b <branch_name> (创建并切换)
          git checkout <branch_name> (切换到已有)
    """
    clear_screen()
    print("=====================================================")
    print(" [6] 创建/切换分支")
    print("=====================================================")
    print("\n")
    print(" [1]  创建并切换到新分支")
    print(" [2]  切换到已有本地分支")
    print("\n [b]  返回上一级菜单")
    print("\n")

    while True:
        branch_action = input(" 请选择操作 (1, 2, b): ")
        if branch_action.lower() == 'b':
            return
        elif branch_action in ('1', '2'):
            break
        else:
            print("\n **错误**: 无效的选择.")

    if branch_action == '1':
        # 创建并切换
        branch_name = input(" 请输入新分支名称: ")
        if not branch_name:
            print("\n **错误**: 分支名称不能为空！")
            input("按任意键继续...")
            return

        print("\n 正在创建并切换到分支", branch_name, "...")
        return_code, stdout, stderr = run_git_command(
            ["git", "checkout", "-b", branch_name]
        )

        if return_code != 0:
            print("\n **错误**: 创建分支失败。")
            print(" 请检查分支名称是否合法或已存在。 可以尝试使用git branch查看已存在的分支")
            # run_git_command 已经打印了 stderr
        else:
             print("\n 已成功创建并切换到分支", branch_name)

        input("按任意键继续...")

    elif branch_action == '2':
        # 切换到已有
        print("\n 正在获取本地分支列表...")
        return_code, stdout, stderr = run_git_command(["git", "branch"])
        if return_code != 0:
             print("\n **错误**: 获取本地分支列表失败。")
             # run_git_command 已经打印了 stderr
             input("按任意键继续...")
             return

        print("\n 本地分支列表:")
        print(stdout) # 打印分支列表

        branch_name = input(" 请输入要切换到的分支名称: ")
        if not branch_name:
            print("\n **错误**: 分支名称不能为空！")
            input("按任意键继续...")
            return

        print("\n 正在切换到分支", branch_name, "...")
        return_code, stdout, stderr = run_git_command(
            ["git", "checkout", branch_name]
        )

        if return_code != 0:
            print("\n **错误**: 切换分支失败。")
            print(" 请检查分支名称是否正确或是否存在未提交的修改。 可以尝试使用git status查看工作区状态")
            # run_git_command 已经打印了 stderr
        else:
             print("\n 已成功切换到分支", branch_name)

        input("按任意键继续...")


def pull_changes():
    """拉取远程更改
    命令: git pull <remote_name> <branch_name>
    """
    clear_screen()
    print("=====================================================")
    print(" [7] 拉取远程更改")
    print("=====================================================")
    print("\n")

    remote_name = input(" 请输入要拉取的远程仓库名称 (默认为 origin): ")
    if not remote_name:
        remote_name = "origin"

    branch_name = input(f" 请输入要拉取的远程分支名称 (默认为 {config.get('default_branch_name', 'main')}, 直接回车使用默认值): ")
    if not branch_name:
        branch_name = config.get("default_branch_name", "main")

    print(f"\n 正在从远程仓库 '{remote_name}' 拉取分支 '{branch_name}' 的最新更改...")
    return_code, stdout, stderr = run_git_command(
        ["git", "pull", remote_name, branch_name]
    )

    if return_code != 0:
        print("\n **错误**: 拉取远程更改失败。")
        print("  请检查您的网络连接, 远程仓库地址是否正确，以及是否存在冲突。")
        # run_git_command 已经打印了 stderr/stdout
        # 检查是否是合并冲突
        if "conflict" in (stdout + stderr).lower():
             print("\n **提示**: 似乎存在合并冲突。请手动编辑冲突文件，解决冲突后使用 'git add .' 和 'git commit' 完成合并。")
    else:
        print(stdout) # pull 成功时通常会打印合并信息
        print(f"\n 已成功从 '{remote_name}/{branch_name}' 拉取最新更改。")

    input("按任意键继续...")


def push_branch():
    """推送分支到远程仓库
    命令: git push <remote_name> <branch_name>
    """
    clear_screen()
    print("=====================================================")
    print(" [8] 推送本地分支")
    print("=====================================================")
    print("\n")

    # 尝试获取当前分支名称作为默认推送分支
    current_branch = None
    rc, out, err = run_git_command(["git", "rev-parse", "--abbrev-ref", "HEAD"])
    if rc == 0:
        current_branch = out.strip()
        print(f"  当前分支为: {current_branch}")

    remote_name = input(" 请输入要推送到的远程仓库名称 (默认为 origin): ")
    if not remote_name:
        remote_name = "origin"

    push_branch_name = input(
        f" 请输入要推送的本地分支名称 (默认为当前分支 '{current_branch}' 或 '{config.get('default_branch_name', 'main')}'): "
    )
    if not push_branch_name:
        push_branch_name = current_branch if current_branch else config.get("default_branch_name", "main")

    print(f"\n 正在推送本地分支 '{push_branch_name}' 到远程仓库 '{remote_name}'...")
    return_code, stdout, stderr = run_git_command(
        ["git", "push", remote_name, push_branch_name]
    )

    if return_code != 0:
        print("\n **错误**: 推送分支失败。")
        print("  请检查分支名称是否正确, 远程仓库配置是否正确, 或者权限是否足够。")
        print("\n  常见错误：")
        print("  - 没有推送权限：确认你对该远程仓库有 push 权限。")
        print("  - 远程分支不存在/需要跟踪：首次推送新分支时，可能需要使用 'git push -u origin <branch_name>'。")
        print("  - 您的本地分支落后于远程分支：请先使用 'git pull' 拉取远程更改并解决冲突。")
        # run_git_command 已经打印了 stderr/stdout
    else:
        print(stdout) # push 成功时通常有输出
        print(f"\n 分支 '{push_branch_name}' 已成功推送到 '{remote_name}'。")

    input("按任意键继续...")


def sync_fork():
    """同步 Fork (从 Upstream 更新到本地，再推送到 origin)
    命令: git checkout <default_branch>
         git pull upstream <default_branch>
         git push origin <default_branch>
    """
    clear_screen()
    print("=====================================================")
    print(" [9] 同步 Fork (从 Upstream 更新)")
    print("=====================================================")
    print("\n")

    default_branch = config.get("default_branch_name", "main")
    upstream_url = config.get("default_upstream_url", "未配置Upstream URL") # 用于提示

    print(f" 假设你的 upstream 已设置为指向原始仓库 ({upstream_url})")
    print(f" 假设你的 origin 已设置为指向你的 Fork 仓库")
    print(f" 假设你的主分支是 '{default_branch}'")
    print("\n 此操作将执行以下步骤：")
    print(f" 1. 切换到 '{default_branch}' 分支")
    print(f" 2. 从 upstream 拉取 '{default_branch}' 分支的最新代码")
    print(f" 3. 将更新后的本地 '{default_branch}' 分支推送到 origin")
    print("\n 按回车键继续，或按 Ctrl+C 取消。")
    input()

    # 步骤 1: 切换到默认分支
    print(f"\n 正在切换到 '{default_branch}' 分支...")
    return_code, stdout, stderr = run_git_command(["git", "checkout", default_branch])
    if return_code != 0:
        print(f"\n **错误**: 切换到 '{default_branch}' 分支失败。")
        print("  请检查本地是否存在名为", default_branch, "的分支，或者是否有未提交的修改。")
        # run_git_command 已经打印了 stderr/stdout
        input("按任意键继续...")
        return

    # 步骤 2: 从 upstream 拉取
    print(f"\n 正在从 upstream 拉取 '{default_branch}' 分支...")
    return_code, stdout, stderr = run_git_command(
        ["git", "pull", "upstream", default_branch]
    )
    if return_code != 0:
        print(f"\n **错误**: 从 upstream 拉取 '{default_branch}' 分支失败。")
        print("  请检查 upstream 是否配置正确 (使用 'git remote -v' 查看)。")
        print("  如果存在合并冲突，请手动解决后再次提交。")
        # run_git_command 已经打印了 stderr/stdout
        input("按任意键继续...")
        # 注意: 发生拉取冲突后，本地仓库处于冲突状态，需要用户手动解决。
        # 这里的函数会退出，用户需要根据提示手动操作或使用其他菜单项。
        return

    # 步骤 3: 推送到 origin
    print(f"\n 正在推送到 origin/'{default_branch}'...")
    return_code, stdout, stderr = run_git_command(["git", "push", "origin", default_branch])
    if return_code != 0:
        print(f"\n **错误**: 推送 '{default_branch}' 分支到 origin 失败。")
        print("  请检查远程仓库配置是否正确, 远程分支是否存在。")
        # run_git_command 已经打印了 stderr/stdout
    else:
        print(stdout) # push 成功时通常有输出
        print(f"\n 已成功从 upstream 同步并推送到 origin/'{default_branch}'。")

    input("按任意键继续...")