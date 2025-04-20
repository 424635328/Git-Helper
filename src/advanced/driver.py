# src/advanced/driver.py
from src.utils import clear_screen
# Import functions from the specific advanced operation modules
from .branch_ops import merge_branch, rebase_branch
from .stash_ops import manage_stash
from .cherry_pick_ops import cherry_pick_commit
from .tag_ops import manage_tags
from .remote_ops import manage_remotes
from .branch_cleanup import delete_local_branch, delete_remote_branch
from .pr_ops import create_pull_request
from .dangerous_ops import clean_commits


def advanced_menu():
    """显示高级操作菜单并获取用户选择"""
    clear_screen()
    print("=====================================================")
    print(" [ 项目贡献助手 ] 高级操作与管理")
    print("=====================================================")
    print("\n 请选择操作:")
    print(" [10] 合并分支            (git merge)")
    print(" [11] 变基分支 (危险!)    (git rebase)")
    print(" [12] 储藏/暂存修改      (git stash)")
    print(" [13] 拣选/摘取提交      (git cherry-pick)")
    print(" [14] 管理标签            (git tag)")
    print(" [15] 管理远程仓库        (git remote add/remove/rename)") # 将添加远程仓库等合并到此
    print(" [16] 删除本地分支        (git branch -d)")
    print(" [17] 删除远程分支        (git push --delete)")
    print(" [18] 创建 Pull Request    (生成 URL 手动创建)")
    print(" [19] 清理 Commits (极其危险!)  (git reset --hard)")
    print("\n [0]  返回主菜单") # Option to return to main menu
    while True:
        # Only allow choices from 10-19 and 0
        choice = input(" 请选择 (0, 10-19): ")
        if choice == "0" or (choice.isdigit() and 10 <= int(choice) <= 19):
            return choice
        else:
            print("\n **错误**: 无效的选择，请重新选择.")
            input("按任意键继续...")

def run_advanced_menu():
    """运行高级操作菜单循环"""
    while True:
        choice = advanced_menu()

        if choice == "0":
            # User wants to return to main menu
            return
        elif choice == "10":
            merge_branch()
        elif choice == "11":
            rebase_branch()
        elif choice == "12":
            manage_stash()
        elif choice == "13":
            cherry_pick_commit()
        elif choice == "14":
            manage_tags()
        elif choice == "15":
            manage_remotes()
        elif choice == "16":
            delete_local_branch()
        elif choice == "17":
            delete_remote_branch()
        elif choice == "18":
            create_pull_request()
        elif choice == "19":
            clean_commits()
        # The 'else' case for invalid choice is handled by the advanced_menu() loop itself