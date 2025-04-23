# src/advanced/dangerous_ops.py
import os
from src.utils import clear_screen
from src.git_utils import run_git_command

def clean_commits():
    """清理 Commits (使用 git reset --hard)
    **极其危险操作**:  将会永久丢弃未推送的 commits!  使用前请务必备份!
    """
    clear_screen()
    print("=====================================================")
    print(" [高级] 清理 Commits (极其危险!)")
    print("=====================================================")
    print("\n")

    print("  !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!")
    print("  !!  **警告：此操作会永久丢弃你本地分支上未推送的 commits!**  !!")
    print("  !!  **请务必备份你的代码! 操作不可撤销!**                    !!")
    print("  !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!")

    print(
        "\n  **强烈建议：** 在执行此操作之前，创建一个备份分支： `git branch backup-before-reset`"
    )
    print("\n  此操作会将你的仓库回退到指定的 commit 状态，并永久删除之后的 commits。")
    print("  例如，如果你选择回退最近的2个 commit，那么你仓库将会回到倒数第三个commit的状态，")
    print("  最近的两个commit以及它们引入的所有修改都将被永久删除。")
    print("  请谨慎选择要丢弃的 commits 个数。")

    print("\n 正在获取最近的提交...")
    rc_log, out_log, err_log = run_git_command(["git", "log", "--oneline", "-n", "10"])
    if rc_log == 0:
        print("\n 最近的 10 个提交 (越上面越新):")
        print(out_log)
    else:
        print("\n 无法获取最近的提交历史。")

    num_commits_input = input(
        "\n  要丢弃最近的多少个 commits？ (输入数字并回车，输入 0 则清空所有 commit 回到初始状态): "
    )
    if not num_commits_input:
        print("\n **错误**: 必须输入要丢弃的 commits 数量！ 操作已取消。")
        input("\n按任意键继续...") # 保持输入在这里以暂停
        return

    try:
        num_commits = int(num_commits_input)
        if num_commits < 0:
            print("\n **错误**: commit 数量必须是非负整数！ 操作已取消。")
            input("\n按任意键继续...") # 保持输入在这里以暂停
            return
    except ValueError:
        print("\n **错误**: 输入的不是有效的整数！ 操作已取消。")
        input("\n按任意键继续...") # 保持输入在这里以暂停
        return

    print(
        f"\n  !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!"
    )
    print(
        f"  !!  **再次警告： 你确定要永久丢弃最近的 {num_commits} 个 commit 之后的所有 commits 吗？**  !!"
    )
    print(f"  !!  **此操作不可撤销！请务必备份你的代码！**                            !!")
    print(
        f"  !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!"
    )
    confirmation = input("  输入 'yes' 并回车以确认执行此危险操作： ")
    if confirmation.lower() != "yes":
        print("\n操作已取消。")
        input("\n按任意键继续...") # 保持输入在这里以暂停
        return

    reset_command_list = ["git", "reset", "--hard", f"HEAD~{num_commits}"]

    print(f"\n  执行命令： {' '.join(reset_command_list)}")

    return_code, stdout, stderr = run_git_command(reset_command_list)

    if return_code != 0:
        print("\n **错误**: reset 失败，请检查您的操作。")
    else:
        print(f"\n  成功重置到 HEAD~{num_commits}!")
        print("  **注意：** 你的本地更改可能已经被丢弃，请检查你的工作目录。")
        print("\n  **重要：** 如果你的这个分支之前已经推送到远程仓库，并且你想让远程仓库也回退到当前状态，")
        print("             你需要使用 **强制推送 (git push --force)**。")
        print("             **`--force` 会覆盖远程仓库的历史！ 请只在自己完全掌控的私有分支上使用！**")
        print("             **如果多人协作开发，强制推送可能会导致严重问题！ 请三思！**")
        print("             强制推送命令示例： git push --force origin <你的分支名称>")

    input("\n按任意键继续...")