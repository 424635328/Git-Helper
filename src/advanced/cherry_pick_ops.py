# src/advanced/cherry_pick_ops.py
from src.utils import clear_screen
from src.git_utils import run_git_command

def cherry_pick_commit():
    """拣选/摘取提交"""
    clear_screen()
    print("=====================================================")
    print(" [高级] 拣选/摘取提交 (git cherry-pick)")
    print("=====================================================")
    print("\n")

    print(" 此操作将指定提交的更改应用到当前分支。")
    print(" 请确保你当前所在的分支是接收这些更改的目标分支。")
    print(" 你可以使用 'git log' 查看提交历史，获取提交哈希。")
    print("\n")

    commit_hash = input(" 请输入要拣选的提交哈希: ")
    if not commit_hash:
        print("\n **错误**: 提交哈希不能为空！ 操作已取消。")
        input("按任意键继续...") # 保持输入在这里以暂停
        return

    print(f"\n 正在将提交 '{commit_hash}' 拣选到当前分支...")
    return_code, stdout, stderr = run_git_command(["git", "cherry-pick", commit_hash])

    if return_code != 0:
        print("\n **错误**: 拣选提交失败。")
        if "conflict" in (stdout + stderr).lower():
            print("\n **提示**: 拣选提交时发生冲突。")
            print("   请手动编辑冲突文件，解决冲突后使用 'git add <冲突文件>'，")
            print("   然后使用 'git cherry-pick --continue' 继续拣选过程。")
            print("   如果想跳过当前有冲突的 commit，请使用 'git cherry-pick --skip'。")
            print("   如果想完全放弃拣选，请使用 'git cherry-pick --abort'。")
            print("   在解决冲突时，使用 'git status' 可以查看哪些文件有冲突。")
        else:
            print("  请检查提交哈希是否正确。")
    else:
        print("\n 提交已成功拣选。")

    input("按任意键继续...")