# src/advanced/branch_ops.py(包含合并和变基)
from src.utils import clear_screen
from src.git_utils import run_git_command
from src.config_manager import config # 导入配置

def merge_branch():
    """合并分支"""
    clear_screen()
    print("=====================================================")
    print(" [高级] 合并分支")
    print("=====================================================")
    print("\n")

    # 尝试获取当前分支
    current_branch = None
    rc, out, err = run_git_command(["git", "rev-parse", "--abbrev-ref", "HEAD"])
    if rc == 0:
        current_branch = out.strip()
        print(f"  当前分支: {current_branch}")

    branch_to_merge = input(" 请输入要合并到当前分支的来源分支名称: ")
    if not branch_to_merge:
        print("\n **错误**: 来源分支名称不能为空！ 操作已取消。")
        input("按任意键继续...") # 保持输入在这里以暂停
        return

    print(f"\n 正在将分支 '{branch_to_merge}' 合并到当前分支 '{current_branch}'...")
    return_code, stdout, stderr = run_git_command(["git", "merge", branch_to_merge])

    if return_code != 0:
        print(f"\n **错误**: 合并分支 '{branch_to_merge}' 失败。")
        if "conflict" in (stdout + stderr).lower():
            print("\n **提示**: 似乎存在合并冲突。")
            print("   请手动编辑冲突文件 (使用 'git status' 查看冲突文件)，解决冲突标记 (<<<<<<<, =======, >>>>>>>)，")
            print("   然后使用 'git add <冲突文件>' 将解决后的文件标记为已解决，")
            print("   最后使用 'git commit' 完成合并。")
            print("   如果想放弃合并，请使用 'git merge --abort'。")
    else:
        print(stdout)
        print(f"\n 已成功将分支 '{branch_to_merge}' 合并到当前分支 '{current_branch}'。")

    input("\n按任意键继续...")


def rebase_branch():
    """变基分支 (危险!)"""
    clear_screen()
    print("=====================================================")
    print(" [高级] 变基分支 (危险!)")
    print("=====================================================")
    print("\n")

    print(" **警告：变基会重写提交历史！切勿对已经推送到公共（多人协作）仓库的分支进行变基！**")
    print(" **变基通常用于清理您自己的本地特性分支的历史，使其基于最新的主分支。**")
    print("\n")

    current_branch = None
    rc, out, err = run_git_command(["git", "rev-parse", "--abbrev-ref", "HEAD"])
    if rc == 0:
        current_branch = out.strip()
        print(f"  当前分支: {current_branch}")

    onto_branch = input(" 请输入要将当前分支变基到哪个分支之上 (例如: main): ")
    if not onto_branch:
        print("\n **错误**: 目标分支名称不能为空！ 操作已取消。")
        input("按任意键继续...") # 保持输入在这里以暂停
        return

    print(f"\n **再次警告：** 您确定要将当前分支 '{current_branch}' 变基到 '{onto_branch}' 之上吗？")
    confirmation = input("  输入 'yes' 继续，输入其他任何内容取消操作： ")
    if confirmation.lower() != "yes":
        print("\n操作已取消。")
        input("\n按任意键继续...") # 保持输入在这里以暂停
        return

    print(f"\n 正在将分支 '{current_branch}' 变基到 '{onto_branch}' 之上...")
    return_code, stdout, stderr = run_git_command(["git", "rebase", onto_branch])

    if return_code != 0:
        print(f"\n **错误**: 变基分支失败。")
        if "conflict" in (stdout + stderr).lower():
             print("\n **提示**: 变基过程中发生冲突。")
             print("   请手动编辑冲突文件，解决冲突后使用 'git add <冲突文件>'，")
             print("   然后使用 'git rebase --continue' 继续变基过程。")
             print("   如果想跳过当前有冲突的 commit，请使用 'git rebase --skip'。")
             print("   如果想完全放弃变基，请使用 'git rebase --abort'。")
             print("   在解决冲突时，使用 'git status' 可以查看哪些文件有冲突以及变基的进度。")
        else:
             print("  请检查目标分支名称是否正确，或者当前分支是否有未提交的修改。")
    else:
        print(stdout)
        print(f"\n 已成功将分支 '{current_branch}' 变基到 '{onto_branch}' 之上。")
        print("\n **注意：** 变基后提交哈希会改变，如果之前已推送过，可能需要强制推送 ('git push --force')。")
        print("            **切勿对公共分支强制推送！**")

    input("\n按任意键继续...")