# src/config_manager.py
import re
import os
import subprocess
import sys # 虽然没直接用 sys.exit，但导入它有时用于示意关键错误处理

# 定义一个全局变量来存储配置 (这是所有模块共享的实例)
config = {
    "fork_username": "未确定",     # Fork 仓库的所有者 (仓库类型为 'fork' 时) / 原始仓库所有者 (类型为 'original' 时)
    "fork_repo_name": "未确定",    # Fork 仓库的名称 (仓库类型为 'fork' 时) / 原始仓库名称 (类型为 'original' 时)
    "base_repo": "未确定",         # 基础仓库 (owner/repo 格式)
    "default_upstream_url": "N/A", # Upstream remote 的 URL (仓库类型为 'fork' 且配置存在时)
    "default_branch_name": "未确定",
    "is_git_repo": False,
    "repo_type": "未确定"         # 'original' 或 'fork'
}

def is_git_repository(path='.'):
    """检查指定路径或其父目录是否包含 .git 目录"""
    current_path = os.path.abspath(path)
    while True:
        if os.path.isdir(os.path.join(current_path, '.git')):
            print(f"  [信息] 在 {current_path} 检测到 .git 目录。")
            return True
        parent_path = os.path.dirname(current_path)
        if parent_path == current_path: # 到达文件系统根目录
            break
        current_path = parent_path
    print("  [错误] 当前目录及其父目录均未检测到 .git 目录。")
    return False

def run_git_command(command_list):
    """
    执行 Git 命令并返回其标准输出，错误时返回 None。
    会静默处理 'git config --get' 找不到键的预期错误。
    """
    try:
        # 使用列表形式的命令更安全
        result = subprocess.run(
            command_list,
            capture_output=True,
            text=True,
            check=True, # 让命令失败时抛出 CalledProcessError
            encoding='utf-8',
            errors='ignore' # 忽略编码错误，虽然最好是明确编码
        )
        return result.stdout.strip()
    except FileNotFoundError:
        print(f"错误：未找到 'git' 命令。请确保 Git 已安装并添加到系统 PATH。")
        return None
    except subprocess.CalledProcessError as e:
        error_message = e.stderr.strip() if e.stderr else ""
        # 特别处理 'git config --get' 失败的情况，这通常不是严重错误
        is_config_get_miss = (
            len(command_list) >= 3 and
            command_list[0] == 'git' and
            command_list[1] == 'config' and
            command_list[2] == '--get' and
            e.returncode == 1 # 通常 'get' 找不到键返回 1
        )
        if not is_config_get_miss:
             # 对于其他 Git 命令错误，打印警告
             print(f"警告：执行 Git 命令 '{' '.join(command_list)}' 时出错 (返回码: {e.returncode})。")
             if error_message:
                 simplified_error = error_message.splitlines()[0] # 只取第一行错误信息
                 print(f"Git 提示: {simplified_error}")
        # 对于 config get miss 或其他错误，都返回 None 表示未获取到期望值
        return None
    except Exception as e:
        print(f"执行 Git 命令 '{' '.join(command_list)}' 时发生未知错误：{e}")
        return None

def extract_owner_repo_from_url(url):
    """
    从仓库 URL 中提取 owner 和 repo 名称。
    目前主要支持 GitHub 格式。
    """
    if not url:
        return None, None
    # 正则表达式匹配 https 和 git@ 两种 GitHub URL 格式
    match = re.search(r"github\.com[/:]([^/]+)/([^/.]+?)(?:\.git)?$", url)
    if match:
        owner = match.group(1)
        repo_name = match.group(2)
        return owner, repo_name
    else:
        print(f"  [警告] 无法从 URL '{url}' 中按预期的 GitHub 格式提取 owner/repo。")
        return None, None

def prompt_for_repo_type(origin_owner, origin_repo):
    """询问用户仓库类型 (Original or Fork)"""
    while True:
        print("-" * 30)
        print("请确认当前仓库的性质：")
        # 使用 f-string 格式化输出
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
            # 使用换行符改善提示的可读性
            print("\n** 输入无效，请输入 1 或 2 **\n")

def load_config_from_git():
    """
    尝试从 Git 仓库的 remote 配置中加载信息，并询问用户仓库类型。
    直接修改全局 config 字典。
    """
    # 使用 global 关键字明确表示我们要修改的是模块级的 config 变量
    # 这对于赋值操作是必需的，但对于修改字典内部内容（config["key"]=...）不是必需的，
    # 不过写上 global config 可以更清晰地表明意图。
    global config
    print("--- 正在尝试从 Git 配置中加载信息 ---")

    # 0. 检查是否是 Git 仓库
    if not is_git_repository():
        # 使用 update 方法修改原始字典
        config.update({key: "非Git仓库" for key in config})
        config["is_git_repo"] = False # 直接修改键值
        print("错误：无法在当前目录或父目录找到有效的 Git 仓库。请在仓库内运行此脚本。")
        print("--- Git 配置信息加载失败 ---")
        return # 结束加载过程
    else:
        config["is_git_repo"] = True # 直接修改键值

    # --- 如果是 Git 仓库，继续加载 ---

    # 1. 获取 Origin 信息
    print("正在获取 'origin' remote 信息...")
    origin_url = run_git_command(["git", "config", "--get", "remote.origin.url"])
    origin_owner, origin_repo = None, None

    if origin_url:
        origin_owner, origin_repo = extract_owner_repo_from_url(origin_url)
        if origin_owner and origin_repo:
            print(f"  [成功] 检测到 'origin' 指向: {origin_owner}/{origin_repo}")
            # 直接修改原始字典的键值
            config["fork_username"] = origin_owner
            config["fork_repo_name"] = origin_repo
        else:
            print(f"  [失败] 无法从 origin URL ({origin_url}) 解析 owner/repo。")
            # 更新原始字典状态
            config.update({k: "检测失败(origin格式错误)" for k in ["fork_username", "fork_repo_name", "base_repo", "repo_type"]})
            # 依赖 origin 解析，如果失败则提前返回
            return
    else:
        print(f"  [失败] 未能获取 remote 'origin' 的 URL。Git remote 配置不完整。")
        # 更新原始字典状态
        config.update({k: "检测失败(无origin)" for k in ["fork_username", "fork_repo_name", "base_repo", "repo_type"]})
        return

    # 2. 询问用户仓库类型
    repo_type = prompt_for_repo_type(origin_owner, origin_repo)
    config["repo_type"] = repo_type # 直接修改键值
    print(f"  [信息] 用户确认为: {'原始仓库' if repo_type == 'original' else 'Fork仓库'}")

    # 3. 根据仓库类型处理 Base Repo 和 Upstream
    if repo_type == 'original':
        # 对于原始仓库, origin 就是 base
        config["base_repo"] = f"{origin_owner}/{origin_repo}"
        config["default_upstream_url"] = "N/A (原始仓库)"
        print(f"  [配置] Base 仓库设置为: {config['base_repo']}")
    elif repo_type == 'fork':
        # 对于 Fork 仓库, 需要查找 upstream 来确定 base
        print("正在获取 'upstream' (原始仓库) 信息...")
        upstream_url = run_git_command(["git", "config", "--get", "remote.upstream.url"])
        if upstream_url:
            base_owner, base_repo_name = extract_owner_repo_from_url(upstream_url)
            if base_owner and base_repo_name:
                # 检查解析出的 upstream repo name 是否与 origin repo name 一致（可选，用于 sanity check）
                if base_repo_name != origin_repo:
                     print(f"  [警告] Upstream 仓库名 '{base_repo_name}' 与 Origin 仓库名 '{origin_repo}' 不一致。")
                config["base_repo"] = f"{base_owner}/{base_repo_name}"
                config["default_upstream_url"] = upstream_url
                print(f"  [成功] 检测到 'upstream' 指向: {config['base_repo']}")
                print(f"  [配置] Base 仓库设置为: {config['base_repo']}")
            else:
                print(f"  [失败] 无法从 upstream URL ({upstream_url}) 解析 owner/repo。")
                config["base_repo"] = "检测失败 (Upstream URL格式错误?)"
                config["default_upstream_url"] = upstream_url # 仍然存储原始 URL
        else:
            print(f"  [失败] 用户确认为 Fork，但未配置名为 'upstream' 的 remote。")
            print("         请添加 upstream: git remote add upstream <原始仓库URL>")
            config["base_repo"] = "检测失败 (Fork 但未设置 upstream)"
            config["default_upstream_url"] = "未设置"

    # 4. 获取默认分支名称
    print("正在获取默认分支名称...")
    default_branch_name = None
    # 尝试从 origin 的 HEAD ref 获取
    origin_head_ref = run_git_command(["git", "symbolic-ref", "refs/remotes/origin/HEAD"])
    if origin_head_ref:
        match = re.search(r"refs/remotes/origin/(\S+)", origin_head_ref)
        if match:
            default_branch_name = match.group(1)
            print(f"  [成功] 推测默认分支 (来自 origin HEAD): {default_branch_name}")
        else:
             print(f"  [警告] 无法从 'origin' 的 HEAD ref ({origin_head_ref}) 解析分支名。")

    # 如果上述失败，尝试获取当前本地分支名
    if not default_branch_name:
        print("  [信息] 获取远程默认分支失败，尝试获取当前本地分支...")
        # 使用 rev-parse 获取当前分支名更可靠
        current_branch = run_git_command(["git", "rev-parse", "--abbrev-ref", "HEAD"])
        # 检查是否成功获取且不是 'HEAD' (分离头指针状态)
        if current_branch and current_branch.upper() != "HEAD":
            default_branch_name = current_branch
            print(f"  [备选] 使用当前本地分支: {current_branch}")
        else:
            print(f"  [失败] 无法确定默认分支或当前分支。")

    # 更新 config 中的默认分支值
    if default_branch_name:
        config["default_branch_name"] = default_branch_name
    else:
        config["default_branch_name"] = "检测失败" # 更新为失败状态


    # --- 加载完成 ---
    print("--- Git 配置信息加载完成 ---")
    # 使用 config.get 提供默认值，避免因加载过程意外中断导致 KeyError
    repo_type_display = config.get('repo_type', '错误')
    repo_type_text = '原始仓库' if repo_type_display == 'original' else \
                     'Fork仓库' if repo_type_display == 'fork' else \
                     repo_type_display # 显示 "未确定" 或 "非Git仓库" 等状态

    print(f"仓库类型: {repo_type_text}")
    print(f"Base 仓库: {config.get('base_repo', '错误')}")
    # 区分显示 Fork Owner/Repo 和 Base Owner/Repo
    if config.get('repo_type') == 'fork':
         print(f"Fork 指向 (用户/仓库): {config.get('fork_username', '错误')}/{config.get('fork_repo_name', '错误')}")
    else: # Original repo
         print(f"Origin 指向 (用户/仓库): {config.get('fork_username', '错误')}/{config.get('fork_repo_name', '错误')}")
    print(f"默认分支: {config.get('default_branch_name', '错误')}")

if __name__ == '__main__':
    print("正在直接运行 config_manager.py 进行测试...")
    load_config_from_git()
    print("\n测试加载后的全局 config 内容:")
    import json
    print(json.dumps(config, indent=2, ensure_ascii=False))
    print("\n测试完成。")