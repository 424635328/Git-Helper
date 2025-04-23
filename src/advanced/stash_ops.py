# src/advanced/stash_ops.py
from src.utils import clear_screen
from src.git_utils import run_git_command

def manage_stash():
    """管理储藏区"""
    clear_screen()
    print("=====================================================")
    print(" [高级] 储藏/暂存修改 (git stash)")
    print("=====================================================")
    print("\n")
    print(" 请选择储藏区操作:")
    print(" [1]  查看储藏列表      (git stash list)")
    print(" [2]  储藏当前修改      (git stash push)")
    print(" [3]  应用最近的储藏    (git stash apply)") # 默认应用 stash@{0}
    print(" [4]  应用并移除最近的储藏 (git stash pop)") # 默认 pop stash@{0}
    print(" [5]  删除指定的储藏    (git stash drop)")
    print("\n [b]  返回上一级菜单")
    print("\n")

    stash_choice = input(" 请选择操作 (1-5, b): ")

    if stash_choice.lower() == 'b':
        return
    elif stash_choice == '1':
        print("\n 正在查看储藏列表...")
        return_code, stdout, stderr = run_git_command(["git", "stash", "list"])
        if return_code == 0:
            print("\n 储藏列表:")
            print(stdout if stdout.strip() else " (储藏列表为空)")
        # else: run_git_command 已经打印了错误
    elif stash_choice == '2':
        message = input(" 请输入储藏信息 (可选): ")
        command = ["git", "stash", "push"]
        if message:
            command.extend(["-m", message])
        print("\n 正在储藏当前修改...")
        return_code, stdout, stderr = run_git_command(command)
        if return_code == 0:
            print("\n 修改已储藏。")
            print(stdout)
        # else: run_git_command 已经打印了错误
    elif stash_choice == '3':
        print("\n 应用储藏：")
        print(" (通常格式为 stash@{n}，例如 stash@{0} 表示最新的储藏)")
        stash_ref = input(" 请输入要应用的储藏引用 (默认为最新的 stash@{0}): ")
        command = ["git", "stash", "apply"]
        if stash_ref:
            command.append(stash_ref)
        print(f"\n 正在应用储藏 '{stash_ref or 'stash@{0}'}'...")
        return_code, stdout, stderr = run_git_command(command)
        if return_code != 0:
            print("\n **错误**: 应用储藏失败。")
            if "conflict" in (stdout + stderr).lower():
                print("\n **提示**: 应用储藏时发生冲突。请手动解决冲突后使用 'git add .'。")
        else:
            print("\n 储藏已成功应用。")
            print(" **注意：** 应用后储藏仍然保留在列表中，可以使用 'git stash drop' 删除。")
    elif stash_choice == '4':
        print("\n 应用并移除储藏 (pop)：")
        print(" (通常格式为 stash@{n}，例如 stash@{0} 表示最新的储藏)")
        stash_ref = input(" 请输入要 pop 的储藏引用 (默认为最新的 stash@{0}): ")
        command = ["git", "stash", "pop"]
        if stash_ref:
            command.append(stash_ref)
        print(f"\n 正在应用并移除储藏 '{stash_ref or 'stash@{0}'}'...")
        return_code, stdout, stderr = run_git_command(command)
        if return_code != 0:
            print("\n **错误**: Pop 储藏失败。")
            if "conflict" in (stdout + stderr).lower():
                print("\n **提示**: Pop 储藏时发生冲突。请手动解决冲突后使用 'git add .'。")
                print("   由于发生冲突，此储藏并未被自动删除。")
        else:
            print("\n 储藏已成功应用并移除。")
    elif stash_choice == '5':
        print("\n 删除指定的储藏：")
        print(" (通常格式为 stash@{n}，例如 stash@{0} 表示最新的储藏)")
        stash_ref = input(" 请输入要删除的储藏引用 (例如 stash@{1}): ")
        if not stash_ref:
            print("\n **错误**: 必须输入要删除的储藏引用！ 操作已取消。")
            input("按任意键继续...") # Keep input here for pause
            return

        print(f"\n **警告：** 你确定要删除储藏 '{stash_ref}' 吗？此操作不可撤销！")
        confirmation = input("  输入 'yes' 继续，输入其他任何内容取消操作： ")
        if confirmation.lower() != "yes":
            print("\n操作已取消。")
            input("\n按任意键继续...") 
            return

        print(f"\n 正在删除储藏 '{stash_ref}'...")
        return_code, stdout, stderr = run_git_command(["git", "stash", "drop", stash_ref])
        if return_code != 0:
             print("\n **错误**: 删除储藏失败。请检查储藏引用是否存在。")
        else:
             print(f"\n 储藏 '{stash_ref}' 已成功删除。")
    else:
        print("\n **错误**: 无效的选择！")

    input("\n按任意键继续...")