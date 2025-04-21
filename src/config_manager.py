import re
import os
import subprocess # 用于执行 git 命令

# 定义一个全局变量来存储配置
config = {}

def run_git_command(command_list):
    """执行 Git 命令并返回其标准输出，错误时返回 None。"""
    try:
        # 使用列表形式的命令更安全，避免 shell=True
        # cwd=os.path.dirname(os.path.dirname(__file__)) # 尝试在项目根目录运行
        # 更健壮的方式是找到 .git 目录的位置，但对于简单场景，当前工作目录通常可以
        result = subprocess.run(command_list, capture_output=True, text=True, check=True, encoding='utf-8')
        return result.stdout.strip()
    except FileNotFoundError:
        print(f"错误：未找到 'git' 命令。请确保 Git 已安装并添加到系统 PATH。")
        return None
    except subprocess.CalledProcessError as e:
        # 打印更详细的错误，特别是 stderr
        error_message = e.stderr.strip()
        print(f"错误：执行 Git 命令 '{' '.join(command_list)}' 失败。")
        if error_message:
            print(f"Git 输出: {error_message}")
        # 特别检查是否是因为不在 Git 仓库中
        if "not a git repository" in error_message.lower() or "不是 git 仓库" in error_message:
             print("错误：当前目录或其父目录似乎不是一个有效的 Git 仓库。")
        return None
    except Exception as e:
        print(f"执行 Git 命令 '{' '.join(command_list)}' 时发生未知错误：{e}")
        return None

def extract_owner_repo_from_url(url):
    """
    从仓库 URL 中提取 owner 和 repo 名称。

    Args:
      url: 仓库的 URL (例如: "https://github.com/owner/repo.git" 或 "git@github.com:owner/repo.git")

    Returns:
      元组 (owner, repo_name)，如果提取失败则返回 (None, None)。
    """
    if not url:
        return None, None

    # 改进正则表达式以处理 .git 后缀（可选）和其他可能的变体
    match = re.search(r"github\.com[:/]([^/]+)/([^/.]+?)(?:\.git)?$", url)

    if match:
        owner = match.group(1)
        repo_name = match.group(2)
        return owner, repo_name
    else:
        return None, None

def load_config_from_git():
    """
    尝试从 Git 仓库的 remote 配置中加载信息，填充全局 config 字典。
    不再读取 config.yaml 文件。
    """
    global config
    print("--- 正在尝试从 Git 配置中加载信息 ---")
    config = {} # 重置配置

    # 1. 获取 Origin (Fork) 信息
    print("正在获取 'origin' (Fork) 信息...")
    origin_url = run_git_command(["git", "config", "--get", "remote.origin.url"])
    fork_owner, fork_repo = extract_owner_repo_from_url(origin_url)

    if fork_owner:
        config["fork_username"] = fork_owner
        print(f"  [成功] Fork 用户名 (来自 origin): {fork_owner}")
        config["fork_repo_name"] = fork_repo # 存储 fork 仓库名，可能有用
    else:
        config["fork_username"] = "your_github_username" # 占位符
        print(f"  [警告] 无法从 remote 'origin' URL ({origin_url}) 推断出 Fork 用户名。请检查 'origin' 配置。")

    # 2. 获取 Origin 的默认分支 (HEAD branch)
    print("正在获取 'origin' 的默认分支...")
    # 'git remote show origin' 可能较慢，尝试 'git symbolic-ref refs/remotes/origin/HEAD'
    origin_head_ref = run_git_command(["git", "symbolic-ref", "refs/remotes/origin/HEAD"])
    default_branch_name = None
    if origin_head_ref:
        # 输出通常是 "refs/remotes/origin/main" 或 "refs/remotes/origin/master"
        match = re.search(r"refs/remotes/origin/(\S+)", origin_head_ref)
        if match:
            default_branch_name = match.group(1)
            config["default_branch_name"] = default_branch_name
            print(f"  [成功] 默认分支 (来自 origin HEAD): {default_branch_name}")
        else:
            print(f"  [警告] 无法从 'origin' 的 HEAD ref ({origin_head_ref}) 解析默认分支名。")
    else:
        # 备选方案：尝试解析 'git remote show origin'
        print("  [信息] 尝试备选方案 'git remote show origin' 获取默认分支...")
        origin_show_output = run_git_command(["git", "remote", "show", "origin"])
        if origin_show_output:
             match = re.search(r"HEAD branch:\s*(\S+)", origin_show_output)
             if match:
                 default_branch_name = match.group(1)
                 config["default_branch_name"] = default_branch_name
                 print(f"  [成功] 默认分支 (来自 remote show): {default_branch_name}")
             else:
                 print("  [警告] 无法从 'git remote show origin' 输出中找到 HEAD branch。")
        else:
            print("  [警告] 执行 'git remote show origin' 失败。")

    if "default_branch_name" not in config:
        config["default_branch_name"] = "main" # 最终回退
        print(f"  [信息] 使用最终回退默认分支名: {config['default_branch_name']}")

    # 3. 获取 Upstream (Base) 信息
    print("正在获取 'upstream' (原始仓库) 信息...")
    upstream_url = run_git_command(["git", "config", "--get", "remote.upstream.url"])
    base_owner, base_repo_name = extract_owner_repo_from_url(upstream_url)

    if base_owner and base_repo_name and upstream_url:
        config["base_repo"] = f"{base_owner}/{base_repo_name}"
        config["default_upstream_url"] = upstream_url
        print(f"  [成功] 原始仓库 (来自 upstream): {config['base_repo']}")
        print(f"  [成功] Upstream URL: {upstream_url}")
    else:
        config["base_repo"] = "upstream_owner/upstream_repo" # 占位符
        config["default_upstream_url"] = "git@github.com:upstream_owner/upstream_repo.git" # 占位符
        print(f"  [警告] 未找到名为 'upstream' 的 remote 或无法解析其 URL ({upstream_url})。")
        print("         请确保你已添加 upstream remote: git remote add upstream <原始仓库URL>")
        print(f"         将使用占位符原始仓库: {config['base_repo']}")

    # 确保运行时需要的 key 存在 (可能部分来自占位符)
    config.setdefault("fork_username", "your_github_username")
    config.setdefault("base_repo", "upstream_owner/upstream_repo")
    config.setdefault("default_branch_name", "main")
    config.setdefault("default_upstream_url", "git@github.com:upstream_owner/upstream_repo.git")


    # 移除旧的 config.yaml 相关设置（如有需要，但现在 load_config_from_git 完全覆盖）
    # config.pop("default_fork_username", None)
    # config.pop("default_base_repo", None)

    print("--- Git 配置信息加载完成 ---")
    print(f"当前推断的配置: Fork 用户='{config['fork_username']}', Base 仓库='{config['base_repo']}', 默认分支='{config['default_branch_name']}'")
    # print("完整配置:", config) # 调试用