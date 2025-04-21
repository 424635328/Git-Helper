# src/config_manager.py
import re
import os
import subprocess
import sys

# --- 全局配置字典 (所有模块共享此实例) ---
config = {
    "fork_username": "未确定",     # Fork 仓库所有者 ('fork') / 原始仓库所有者 ('original')
    "fork_repo_name": "未确定",    # Fork 仓库名 ('fork') / 原始仓库名 ('original')
    "base_repo": "未确定",         # 基础仓库 (owner/repo 格式)
    "default_upstream_url": "N/A", # Upstream remote 的 URL (类型为 'fork' 且存在时)
    "default_branch_name": "未确定",
    "is_git_repo": False,
    "repo_type": "未确定",         # 'original' 或 'fork'
    # 内部使用的临时变量，加载后会被清理
    "_tmp_origin_url": None,
    "_tmp_origin_owner": None,
    "_tmp_origin_repo": None,
    "_tmp_repo_path": None      # 存储检测到的 .git 目录的父路径
}

def is_git_repository(path='.'):
    """检查指定路径或其父目录是否包含 .git 目录，返回 (bool, path)"""
    current_path = os.path.abspath(path)
    while True:
        git_dir = os.path.join(current_path, '.git')
        # 检查 .git 是目录还是指向目录的文件（用于 worktrees）
        is_dir = os.path.isdir(git_dir)
        is_file = os.path.isfile(git_dir) # .git 文件通常包含 'gitdir: <path>'

        if is_dir or is_file:
            # print(f"  [信息] 在 {current_path} 检测到 .git 结构。") # GUI模式下减少打印
            return True, current_path # 返回找到 .git 的目录路径
        parent_path = os.path.dirname(current_path)
        if parent_path == current_path: # 到达文件系统根目录
            break
        current_path = parent_path
    # print("  [错误] 当前目录及其父目录均未检测到 .git 目录。") # GUI模式下减少打印
    return False, None

def run_git_command(command_list, cwd=None):
    """
    执行 Git 命令并返回其标准输出，错误时返回 None。
    会静默处理 'git config --get' 找不到键的预期错误。
    在指定的 cwd (当前工作目录) 下执行。
    """
    try:
        result = subprocess.run(
            command_list,
            cwd=cwd, # 使用指定的工作目录
            capture_output=True,
            text=True,
            check=True, # 失败时抛出 CalledProcessError
            encoding='utf-8',
            errors='ignore' # 忽略可能的编码错误
        )
        return result.stdout.strip()
    except FileNotFoundError:
        print(f"错误：未找到 'git' 命令。请确保 Git 已安装并添加到系统 PATH。")
        # 在 config 中标记 Git 不可用
        config["is_git_repo"] = False
        config.update({k: "Git未找到" for k in config if k != "is_git_repo"})
        return None
    except subprocess.CalledProcessError as e:
        error_message = e.stderr.strip() if e.stderr else ""
        # 静默处理 'git config --get' key not found (return code 1)
        is_config_get_miss = (
            len(command_list) >= 3 and
            command_list[0] == 'git' and
            command_list[1] == 'config' and
            command_list[2] == '--get' and
            e.returncode == 1
        )
        if not is_config_get_miss:
             # 其他 Git 错误在控制台打印警告，GUI 层面会显示更友好的信息
             print(f"警告：执行 Git 命令 '{' '.join(command_list)}' 时出错 (返回码: {e.returncode})。")
             if error_message:
                 simplified_error = error_message.splitlines()[0]
                 print(f"Git 提示: {simplified_error}")
        return None # 命令失败或预期内无结果
    except Exception as e:
        print(f"执行 Git 命令 '{' '.join(command_list)}' 时发生未知错误：{e}")
        return None

def extract_owner_repo_from_url(url):
    """从仓库 URL 中提取 owner 和 repo 名称 (主要支持 GitHub)。"""
    if not url:
        return None, None
    # 匹配 https:// 和 git@ 两种 GitHub 格式
    match = re.search(r"github\.com[/:]([^/]+)/([^/.]+?)(?:\.git)?$", url)
    if match:
        owner = match.group(1)
        repo_name = match.group(2)
        return owner, repo_name
    else:
        # print(f"  [警告] 无法从 URL '{url}' 中按预期的 GitHub 格式提取 owner/repo。") # GUI模式下减少打印
        return None, None

# --- 交互式提示（保留给 CLI 使用） ---
def prompt_for_repo_type(origin_owner, origin_repo):
    """询问用户仓库类型 (Original or Fork) - CLI 版本"""
    while True:
        print("-" * 30)
        print("请确认当前仓库的性质：")
        print(f"检测到 'origin' 指向: {origin_owner}/{origin_repo}")
        print("  1: 这是主要的/原始的仓库 (您创建或直接克隆)")
        print("  2: 这是您 Fork 自其它仓库的版本")
        print("-" * 30)
        choice = input("请选择 (1 或 2): ").strip()
        if choice == '1':
            return 'original'
        elif choice == '2':
            return 'fork'
        else:
            print("\n** 输入无效，请输入 1 或 2 **\n")

# --- 新: 非交互式初始检查 (供 GUI 调用) ---
def check_git_repo_and_origin(project_root_or_cwd='.'):
    """
    检查是否为 Git 仓库并获取 Origin URL 信息 (非交互式)。

    Returns:
        tuple: (is_repo, origin_url, origin_owner, origin_repo, error_message)
               成功: (True, 'url', 'owner', 'repo', None)
               失败: (False 或 True, ..., '错误信息')
    """
    global config
    # 清理上次可能残留的临时数据
    for k in list(config.keys()):
        if k.startswith("_tmp_"):
            del config[k]

    is_repo, repo_path = is_git_repository(project_root_or_cwd)
    if not is_repo:
        config["is_git_repo"] = False
        config.update({k: "非Git仓库" for k in config if k != "is_git_repo"})
        return False, None, None, None, "当前目录或指定路径不是有效的 Git 仓库。"

    # 是 Git 仓库，记录状态和路径
    config["is_git_repo"] = True
    config["_tmp_repo_path"] = repo_path # 存储实际仓库路径供后续命令使用

    origin_url = run_git_command(["git", "config", "--get", "remote.origin.url"], cwd=repo_path)

    if not origin_url:
        config.update({k: "检测失败(无origin)" for k in config if k != "is_git_repo" and not k.startswith("_tmp_")})
        return True, None, None, None, "未能获取 remote 'origin' 的 URL。请检查 'git remote -v'。"

    origin_owner, origin_repo = extract_owner_repo_from_url(origin_url)
    if not origin_owner or not origin_repo:
        config.update({k: "检测失败(origin格式错误)" for k in config if k != "is_git_repo" and not k.startswith("_tmp_")})
        return True, origin_url, None, None, f"无法从 origin URL ({origin_url}) 解析 owner/repo。请检查 URL 格式。"

    # 存储临时信息，并初步更新 config
    config["_tmp_origin_url"] = origin_url
    config["_tmp_origin_owner"] = origin_owner
    config["_tmp_origin_repo"] = origin_repo
    config["fork_username"] = origin_owner # 暂时赋值
    config["fork_repo_name"] = origin_repo # 暂时赋值

    return True, origin_url, origin_owner, origin_repo, None

# --- 新: 根据 GUI 选择完成加载 (供 GUI 调用) ---
def complete_config_load(repo_type):
    """
    根据用户提供的 repo_type 完成配置加载 (非交互式)。
    假定 check_git_repo_and_origin 已成功调用。
    """
    global config
    print(f"[ConfigManager] 完成加载，类型: {repo_type}") # 控制台调试信息

    # 检查必需的临时数据是否存在
    if "_tmp_origin_owner" not in config or "_tmp_origin_repo" not in config:
        print("[ConfigManager] 错误: 缺少初始检查数据。")
        config.update({k: "加载错误" for k in config if k != "is_git_repo" and not k.startswith("_tmp_")})
        return False

    origin_owner = config["_tmp_origin_owner"]
    origin_repo = config["_tmp_origin_repo"]
    repo_path = config.get("_tmp_repo_path") # 获取之前存储的仓库路径

    config["repo_type"] = repo_type # 记录用户选择的类型

    # 根据类型处理 Base Repo 和 Upstream
    if repo_type == 'original':
        config["base_repo"] = f"{origin_owner}/{origin_repo}"
        config["default_upstream_url"] = "N/A (原始仓库)"
        # fork_username/repo_name 之前存的是 origin 的，正好也是 base 的，无需修改
    elif repo_type == 'fork':
        # fork_username/repo_name 之前存的是 origin 的，是正确的 fork 信息，无需修改
        upstream_url = run_git_command(["git", "config", "--get", "remote.upstream.url"], cwd=repo_path)
        if upstream_url:
            base_owner, base_repo_name = extract_owner_repo_from_url(upstream_url)
            if base_owner and base_repo_name:
                config["base_repo"] = f"{base_owner}/{base_repo_name}"
                config["default_upstream_url"] = upstream_url
            else:
                config["base_repo"] = "检测失败 (Upstream URL格式错误?)"
                config["default_upstream_url"] = upstream_url # 仍然记录检测到的 URL
        else:
            config["base_repo"] = "检测失败 (Fork 但未设置 upstream)"
            config["default_upstream_url"] = "未设置"

    # 获取默认分支名称 (使用 repo_path 执行命令)
    default_branch_name = None
    origin_head_ref = run_git_command(["git", "symbolic-ref", "refs/remotes/origin/HEAD"], cwd=repo_path)
    if origin_head_ref:
        match = re.search(r"refs/remotes/origin/(\S+)", origin_head_ref)
        if match:
            default_branch_name = match.group(1)

    if not default_branch_name:
        current_branch = run_git_command(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=repo_path)
        if current_branch and current_branch.upper() != "HEAD":
            default_branch_name = current_branch

    config["default_branch_name"] = default_branch_name if default_branch_name else "检测失败"

    # 清理内部使用的临时键
    for k in list(config.keys()):
        if k.startswith("_tmp_"):
            del config[k]

    print("[ConfigManager] 配置加载完成。")
    return True

# --- 原交互式加载函数 (保留给 CLI) ---
def load_config_from_git():
    """
    尝试从 Git 仓库的 remote 配置中加载信息，并询问用户仓库类型 (CLI 版本)。
    """
    global config
    print("--- 正在尝试从 Git 配置中加载信息 (CLI Mode) ---")

    # 调用第一阶段检查
    is_repo, origin_url, origin_owner, origin_repo, error = check_git_repo_and_origin()

    if not is_repo:
        print(f"错误: {error}")
        return
    if error: # 是仓库，但获取 origin 出错
        print(f"错误: {error}")
        return
    if not origin_owner or not origin_repo: # 理论上不会发生，因为 error 会被设置
        print("错误: 未能解析 Origin 信息。")
        return

    # --- CLI 交互 ---
    repo_type = prompt_for_repo_type(origin_owner, origin_repo)
    # --- ---

    # 调用第二阶段完成加载
    complete_config_load(repo_type)

    # --- 打印总结 (CLI 模式下) ---
    print("--- Git 配置信息加载完成 ---")
    repo_type_display = config.get('repo_type', '错误')
    repo_type_text = '原始仓库' if repo_type_display == 'original' else \
                     'Fork仓库' if repo_type_display == 'fork' else \
                     repo_type_display
    print(f"仓库类型: {repo_type_text}")
    print(f"Base 仓库: {config.get('base_repo', '错误')}")
    if config.get('repo_type') == 'fork':
         print(f"Fork 指向 (用户/仓库): {config.get('fork_username', '错误')}/{config.get('fork_repo_name', '错误')}")
    else: # Original repo
         print(f"Origin 指向 (用户/仓库): {config.get('fork_username', '错误')}/{config.get('fork_repo_name', '错误')}")
    print(f"默认分支: {config.get('default_branch_name', '错误')}")
