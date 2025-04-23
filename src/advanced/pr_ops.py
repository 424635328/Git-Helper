# src/advanced/pr_ops.py
import webbrowser
import urllib.parse
import os
from src.utils import clear_screen
from src.git_utils import run_git_command
from src.config_manager import config # 导入配置


def create_pull_request():
    """创建 Pull Request (实际上是生成 URL 并提示用户手动创建)
    命令：无 (需要用户手动操作)
    """
    clear_screen()
    print("=====================================================")
    print(" [高级] 创建 Pull Request")
    print("=====================================================")
    print("\n")

    # Get fork_username and base_repo from config
    # 从配置中获取 fork_username 和 base_repo
    # These are set in main.py startup and updated in the global config dict
    # 这些在 main.py 启动时设置并更新到全局配置字典中
    fork_username = config.get("fork_username", config.get("default_fork_username", "your_github_username"))
    base_repo = config.get("base_repo", config.get("default_base_repo", "upstream_owner/upstream_repo"))

    if fork_username == "your_github_username" or base_repo == "upstream_owner/upstream_repo":
         print("\n **警告**: 你的 GitHub 用户名或原始仓库名称可能未正确设置。")
         print(f" 当前使用的用户名为: {fork_username}")
         print(f" 当前使用的原始仓库为: {base_repo}")
         print(" 请确保 config.yaml 或程序启动时的输入正确。")
         input("按任意键继续...") # 保持输入在这里以暂停
         # Do not re-prompt, just use current values
         # 不重新提示，直接使用当前值

    # Get current branch name as default source branch
    # 获取当前分支名称作为默认源分支
    current_branch = None
    rc, out, err = run_git_command(["git", "rev-parse", "--abbrev-ref", "HEAD"])
    if rc == 0:
        current_branch = out.strip()
        print(f"  当前分支为: {current_branch}")

    source_branch = input(f" 请输入要创建 Pull Request 的源分支名称 (默认为当前分支 '{current_branch}'): ")
    if not source_branch:
        source_branch = current_branch
        if not source_branch:
            print("\n **错误**: 无法确定当前分支且未输入源分支名称。 操作已取消。")
            input("按任意键继续...") # 保持输入在这里以暂停
            return

    target_branch = input(f" 请输入目标分支名称 (默认为原始仓库的默认分支 '{config.get('default_branch_name', 'main')}'): ")
    if not target_branch:
        target_branch = config.get("default_branch_name", "main")

    # Build head repo reference, typically "fork_username:source_branch"
    # 构建 head 仓库引用，通常是 "fork_username:source_branch"
    head_repo_ref = f"{fork_username}:{source_branch}"

    # Build the URL
    # 构建 URL
    encoded_target = urllib.parse.quote(target_branch)
    encoded_head = urllib.parse.quote(head_repo_ref)

    # Default PR Title and Body
    # 默认 PR 标题和内容
    default_pr_title = "feat: Add a new feature" # 示例标题
    pr_title = input(f" 请输入 PR 标题 (默认为 '{default_pr_title}'): ") or default_pr_title
    encoded_title = urllib.parse.quote(pr_title)

    default_pr_body = "<!-- 请在 GitHub 页面填写 Pull Request 详细描述 -->"
    encoded_body = urllib.parse.quote(default_pr_body)

    # GitHub URL format for creating a PR: https://github.com/owner/repo/compare?base=...&head=...&title=...&body=...
    # 用于创建 PR 的 GitHub URL 格式: https://github.com/owner/repo/compare?base=...&head=...&title=...&body=...
    pr_url = f"https://github.com/{base_repo}/compare?base={encoded_target}&head={encoded_head}&title={encoded_title}&body={encoded_body}"

    print("\n 请复制以下 URL 到你的浏览器中，手动创建 Pull Request：")
    print(pr_url)

    # Attempt to open URL in default browser
    # 尝试在默认浏览器中打开 URL
    try:
        print("\n 尝试在默认浏览器中打开此 URL...")
        webbrowser.open(pr_url)
        print(" 如果浏览器没有自动打开，请手动复制 URL。")
    except Exception as e:
        print(f" 无法自动打开浏览器: {e}")
        print(" 请手动复制 URL。")

    input("\n按任意键继续...")