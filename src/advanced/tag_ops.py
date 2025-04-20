# src/advanced/tag_ops.py
from src.utils import clear_screen
from src.git_utils import run_git_command

def manage_tags():
    """管理标签"""
    clear_screen()
    print("=====================================================")
    print(" [高级] 管理标签 (git tag)")
    print("=====================================================")
    print("\n")
    print(" 请选择标签操作:")
    print(" [1]  列出所有标签      (git tag)")
    print(" [2]  创建新标签        (git tag <tagname> 或 git tag -a <tagname>)")
    print(" [3]  删除本地标签      (git tag -d <tagname>)")
    print(" [4]  推送所有本地标签  (git push origin --tags)")
    print(" [5]  删除远程标签      (git push origin --delete tag <tagname>)")
    print("\n [b]  返回上一级菜单")
    print("\n")

    tag_choice = input(" 请选择操作 (1-5, b): ")

    if tag_choice.lower() == 'b':
        return
    elif tag_choice == '1':
        print("\n 正在列出所有标签...")
        return_code, stdout, stderr = run_git_command(["git", "tag"])
        if return_code == 0:
            print("\n 标签列表:")
            print(stdout if stdout.strip() else " (当前没有标签)")
        # else: run_git_command 已经打印了错误
    elif tag_choice == '2':
        tag_name = input(" 请输入要创建的标签名称 (例如 v1.0): ")
        if not tag_name:
            print("\n **错误**: 标签名称不能为空！ 操作已取消。")
            input("按任意键继续...") # Keep input here for pause
            return

        tag_type = input(" 创建轻量标签 (L) 还是附注标签 (A)? (输入 L 或 A, 默认为 A): ")
        if tag_type.lower() == 'l':
            command = ["git", "tag", tag_name]
            print(f"\n 正在创建轻量标签 '{tag_name}'...")
        else: # 默认为附注标签
            tag_message = input(" 请输入标签信息 (可选，对于附注标签推荐输入): ")
            command = ["git", "tag", "-a", tag_name]
            if tag_message:
                command.extend(["-m", tag_message])
            print(f"\n 正在创建附注标签 '{tag_name}'...")

        return_code, stdout, stderr = run_git_command(command)
        if return_code == 0:
            print(f"\n 标签 '{tag_name}' 已成功创建。")
            print(" **注意：** 创建的标签默认只在本地仓库中，需要使用 'git push --tags' 推送到远程。")
        # else: run_git_command 已经打印了错误
    elif tag_choice == '3':
        tag_name = input(" 请输入要删除的本地标签名称: ")
        if not tag_name:
            print("\n **错误**: 标签名称不能为空！ 操作已取消。")
            input("按任意键继续...") # Keep input here for pause
            return

        print(f"\n **警告：** 你确定要删除本地标签 '{tag_name}' 吗？")
        confirmation = input("  输入 'yes' 继续，输入其他任何内容取消操作： ")
        if confirmation.lower() != "yes":
            print("\n操作已取消。")
            input("\n按任意键继续...") # Keep input here for pause
            return

        print(f"\n 正在删除本地标签 '{tag_name}'...")
        return_code, stdout, stderr = run_git_command(["git", "tag", "-d", tag_name])
        if return_code != 0:
             print("\n **错误**: 删除本地标签失败。请检查标签是否存在。")
        else:
             print(f"\n 本地标签 '{tag_name}' 已成功删除。")
             print(" **注意：** 这只删除了本地标签，远程仓库的同名标签需要单独删除。")
    elif tag_choice == '4':
        remote_name = input(" 请输入要推送标签的远程仓库名称 (默认为 origin): ")
        if not remote_name:
            remote_name = "origin"
        print(f"\n 正在推送所有本地标签到远程仓库 '{remote_name}'...")
        return_code, stdout, stderr = run_git_command(["git", "push", remote_name, "--tags"])
        if return_code != 0:
             print("\n **错误**: 推送标签失败。请检查远程仓库配置或权限。")
        else:
             print(f"\n 所有本地标签已成功推送到 '{remote_name}'。")
    elif tag_choice == '5':
        tag_name = input(" 请输入要删除的远程标签名称: ")
        if not tag_name:
            print("\n **错误**: 标签名称不能为空！ 操作已取消。")
            input("按任意键继续...") # Keep input here for pause
            return

        remote_name = input(" 请输入远程仓库名称 (默认为 origin): ")
        if not remote_name:
            remote_name = "origin"

        print(f"\n **警告：** 你确定要删除远程仓库 '{remote_name}' 上的标签 '{tag_name}' 吗？")
        confirmation = input("  输入 'yes' 继续，输入其他任何内容取消操作： ")
        if confirmation.lower() != "yes":
            print("\n操作已取消。")
            input("\n按任意键继续...") # Keep input here for pause
            return

        print(f"\n 正在删除远程仓库 '{remote_name}' 上的标签 '{tag_name}'...")
        return_code, stdout, stderr = run_git_command(["git", "push", remote_name, "--delete", "tag", tag_name])
        if return_code != 0:
             print("\n **错误**: 删除远程标签失败。请检查远程仓库配置或标签是否存在。")
        else:
             print(f"\n 远程仓库 '{remote_name}' 上的标签 '{tag_name}' 已成功删除。")
    else:
        print("\n **错误**: 无效的选择！")

    input("\n按任意键继续...")