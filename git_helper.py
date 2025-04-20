import os
import subprocess
import webbrowser
import urllib.parse
import yaml  # 导入 yaml 库
import re
import sys # 导入 sys 模块

# 定义一个全局变量来存储配置
config = {}


def load_config(config_file="config.yaml"):
    """加载配置文件"""
    global config
    try:
        with open(config_file, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f)
        if not config:
            print(
                "警告：配置文件为空或无法加载。请检查 config.yaml 文件是否存在且格式正确。"
            )
            config = {}  # 初始化为空字典
    except FileNotFoundError:
        print(
            "警告：config.yaml 文件未找到。将使用默认设置，某些功能可能无法正常工作。"
        )
        config = {}
    except yaml.YAMLError as e:
        print(f"警告：加载 config.yaml 文件时发生错误：{e}。将使用默认设置。")
        config = {}

    # 确保关键配置项存在，如果不存在，设置默认值
    if "default_fork_username" not in config:
        config["default_fork_username"] = "your_github_username"  # 你的 GitHub 用户名
        print("警告：'default_fork_username' 未在 config.yaml 中找到，使用默认值。")
    if "default_upstream_url" not in config:
        config["default_upstream_url"] = "git@github.com:upstream_owner/upstream_repo.git" # 上游仓库地址
        print("警告：'default_upstream_url' 未在 config.yaml 中找到，使用默认值。")
    if "default_base_repo" not in config:
         # 尝试从Upstream URL中提取，如果失败，就使用一个提示性的默认值
        extracted_base = extract_repo_name_from_upstream_url(config.get("default_upstream_url"))
        config["default_base_repo"] = extracted_base if extracted_base else "upstream_owner/upstream_repo"
        print("警告：'default_base_repo' 未在 config.yaml 中找到，尝试从 'default_upstream_url' 中提取或使用默认值。")

    if "default_branch_name" not in config:
        config["default_branch_name"] = "main"  # 默认分支名称
        print("警告: 'default_branch_name' 未在 config.yaml 中找到，使用默认值 'main'.")

    # 将从命令行或用户输入获取的 fork_username 和 base_repo 也存入 config，
    # 以便后续函数访问，但不在 load_config 中直接获取，而是在 main 函数中获取后更新 config。
    # 这里只是确保它们有一个默认值或占位符
    if "fork_username" not in config:
        config["fork_username"] = config["default_fork_username"]
    if "base_repo" not in config:
        config["base_repo"] = config["default_base_repo"]


def extract_repo_name_from_upstream_url(upstream_url):
  """
  从 Upstream 仓库地址中提取原始仓库的名称。

  Args:
    upstream_url: Upstream 仓库的 URL (例如: "https://github.com/owner/repo.git" 或者 "git@github.com:owner/repo.git")

  Returns:
    如果提取成功, 返回原始仓库的名称 (例如: "owner/repo")。
    如果提取失败, 返回 None。
  """
  if not upstream_url:
    return None

  # 修改正则表达式来同时匹配 https 和 git+ssh 协议
  # 注意：这个正则表达式只适用于 GitHub URL
  match = re.search(r"github\.com[:/]([^/]+)/([^.]+)", upstream_url)

  if match:
    owner = match.group(1)
    repo_name = match.group(2)
    return f"{owner}/{repo_name}"
  else:
    return None


def clear_screen():
    """清空屏幕"""
    os.system("cls" if os.name == "nt" else "clear")


def run_git_command(command_list, cwd=None):
    """
    运行 Git 命令并返回状态码、stdout 和 stderr。
    参数:
        command_list: 包含命令及其参数的列表。
        cwd: 可选，指定运行命令的工作目录。
    """
    process = None  # 初始化 process 变量
    try:
        print(f"\n> 执行命令: {' '.join(command_list)}") # 打印实际执行的命令
        process = subprocess.run(
            command_list,
            capture_output=True,
            text=True,
            check=True, # 如果命令返回非零状态码则抛出 CalledProcessError
            encoding="utf-8",
            cwd=cwd # 指定工作目录
        )
        # 对于成功执行的命令，返回状态码0，stdout，stderr
        return process.returncode, process.stdout, process.stderr
    except FileNotFoundError:
        print("\n **错误**: 未找到 git 命令。请确保 Git 已安装并配置到系统的 PATH 中。")
        # 使用 sys.exit 退出程序
        sys.exit(1)
        # return 1, "", "Git command not found." # 这行不会被执行到，因为 sys.exit 退出
    except subprocess.CalledProcessError as e:
        # 当 check=True 时，非零状态码会触发此异常
        # e.returncode 包含状态码
        # e.stdout 和 e.stderr 包含捕获的输出
        print(f"\n **错误**: 命令 '{' '.join(command_list)}' 执行失败，错误代码: {e.returncode}")
        # 某些命令的错误信息可能在 stdout 中 (例如 git pull 有冲突时)
        # 打印 stdout 和 stderr
        if e.stdout:
            print("\n--- stdout ---")
            print(e.stdout)
        if e.stderr:
            print("\n--- stderr ---")
            print(e.stderr)

        # 返回异常的状态码和输出
        return e.returncode, e.stdout, e.stderr
    except Exception as e:
        # 捕获其他可能的异常
        print(f"\n **错误**: 执行命令时发生未知错误: {e}")
        return 1, "", str(e) # 返回一个非零状态码表示失败


def main_menu():
    """显示主菜单并获取用户选择"""
    clear_screen()
    print("=====================================================")
    print(" [ 项目贡献助手 ]")
    print("=====================================================")
    print("\n 请选择操作:")
    print("\n --- 高级操作与管理 ---")
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
    print("\n --- 分支与同步 ---")
    print(" [6]  创建/切换分支       (git checkout -b / git checkout)")
    print(" [7]  拉取远程更改        (git pull)")
    print(" [8]  推送本地分支        (git push)")
    print(" [9]  同步 Fork (Upstream) (从上游拉取到本地并推送到origin)")
    print("\n --- 基础操作 ---")
    print(" [1]  查看仓库状态        (git status)")
    print(" [2]  查看提交历史        (git log)")
    print(" [3]  查看文件差异        (git diff)")
    print(" [4]  添加修改            (git add)")
    print(" [5]  提交修改            (git commit)")
    print("\n --- 其他 ---")
    print(" [0]  退出")
    while True:
        choice = input(" 请选择 (0-19): ")
        if choice in [str(i) for i in range(20)]: # 动态生成有效选项列表
            return choice
        else:
            print("\n **错误**: 无效的选择，请重新选择.")
            input("按任意键继续...")

# --- 新增功能实现 ---

def show_status():
    """显示仓库状态"""
    clear_screen()
    print("=====================================================")
    print(" [1] 查看仓库状态")
    print("=====================================================")
    print("\n")

    print(" 正在获取仓库状态...")
    return_code, stdout, stderr = run_git_command(["git", "status"])

    # run_git_command 已经处理了错误打印，这里只在成功时打印 stdout
    if return_code == 0:
        print(stdout)

    input("\n按任意键继续...")

def show_log():
    """显示提交历史"""
    clear_screen()
    print("=====================================================")
    print(" [2] 查看提交历史")
    print("=====================================================")
    print("\n")
    print("请选择日志格式：")
    print(" [1]  简洁日志 (一行一条)")
    print(" [2]  图形化日志 (显示分支合并图)")
    print("\n")

    log_choice = input(" 请选择 (1 或 2): ")
    command = ["git", "log"]

    if log_choice == "1":
        command.extend(["--pretty=oneline", "--abbrev-commit"]) # abbrev-commit 缩短 hash
    elif log_choice == "2":
        command.extend(["--graph", "--pretty=format:%C(auto)%h%d %s %C(dim)%an%C(reset)", "--all"]) # 美化图形日志，显示所有分支
    else:
        print("\n **错误**: 无效的选择，将使用默认日志格式。")

    print("\n 正在获取提交历史...")
    # 使用 Popen 运行命令，并直接将输出流式打印到控制台，以便处理长日志
    try:
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8")
        while True:
            output = process.stdout.readline()
            if output == '' and process.poll() is not None:
                break
            if output:
                print(output.strip()) # 打印日志行

        # 检查是否有错误输出
        stderr = process.stderr.read()
        if stderr:
             print("\n--- 错误输出 ---")
             print(stderr.strip())

        return_code = process.wait() # 等待进程结束并获取返回码

        if return_code != 0:
             print(f"\n **错误**: 查看日志失败，错误代码: {return_code}")
             # run_git_command 在这里不适用，因为我们直接使用 Popen
             # print(stderr) # stderr 已经在上面打印过了

    except FileNotFoundError:
         print("\n **错误**: 未找到 git 命令。请确保 Git 已安装并配置到系统的 PATH 中。")
    except Exception as e:
         print(f"\n **错误**: 执行命令时发生未知错误: {e}")


    input("\n按任意键继续...")


def show_diff():
    """显示文件差异"""
    clear_screen()
    print("=====================================================")
    print(" [3] 查看文件差异")
    print("=====================================================")
    print("\n")
    print("请选择要查看的差异：")
    print(" [1]  工作目录 vs 暂存区 (已修改但未 add 的文件)")
    print(" [2]  暂存区 vs 最新提交 (git add . 后准备 commit 的修改)")
    print(" [3]  工作目录 vs 最新提交 (所有未 commit 的修改)")
    print(" [4]  两个提交/分支 之间的差异 (例如: main...feature)")
    print("\n")

    diff_choice = input(" 请选择 (1-4): ")
    command = ["git", "diff"]

    if diff_choice == "1":
        # git diff (工作区 vs 暂存区) - 这是默认行为，不需要额外参数
        pass
    elif diff_choice == "2":
        command.append("--staged") # 或者 --cached (暂存区 vs HEAD)
    elif diff_choice == "3":
         command.append("HEAD") # 工作区 vs HEAD
    elif diff_choice == "4":
        commit1 = input(" 请输入第一个提交哈希或分支名: ")
        if not commit1:
            print("\n **错误**: 必须输入第一个提交/分支名称！ 操作已取消。")
            input("\n按任意键继续...")
            return
        commit2 = input(" 请输入第二个提交哈希或分支名 (默认为当前 HEAD): ")
        if not commit2:
            command.extend([commit1, "HEAD"])
        else:
            command.extend([commit1, commit2])
    else:
        print("\n **错误**: 无效的选择！ 操作已取消。")
        input("\n按任意键继续...")
        return

    print("\n 正在获取文件差异...")
    # Diff 输出也可能很长，使用 Popen
    try:
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8")
        while True:
            output = process.stdout.readline()
            if output == '' and process.poll() is not None:
                break
            if output:
                # git diff 输出中可能包含颜色控制符
                # 简单打印，终端会处理颜色
                print(output.rstrip()) # rstrip() 移除行尾的换行符，Popen 的 readline 保留了换行符
                # 或者如果需要过滤颜色可以使用库，这里为了简单直接打印

        stderr = process.stderr.read()
        if stderr:
             print("\n--- 错误输出 ---")
             print(stderr.strip())

        return_code = process.wait()

        if return_code != 0:
             print(f"\n **错误**: 查看差异失败，错误代码: {return_code}")

    except FileNotFoundError:
         print("\n **错误**: 未找到 git 命令。请确保 Git 已安装并配置到系统的 PATH 中。")
    except Exception as e:
         print(f"\n **错误**: 执行命令时发生未知错误: {e}")

    input("\n按任意键继续...")


# 原有的 add_changes, commit_changes 函数基本保留，稍微调整提示信息

def add_changes():
    """添加修改
    命令: git add .  (添加所有文件)
         git add <file_name> (添加指定文件)
    """
    clear_screen()
    print("=====================================================")
    print(" [4] 添加修改到暂存区")
    print("=====================================================")
    print("\n")
    print(" 已修改的文件 (使用 git status 查看)")
    print("\n [a]  添加所有已修改或新增的文件")
    print(" [文件名] 添加指定的单个文件 (例如： README.md)")
    print("\n")

    add_target = input(" 请输入选项 (a(所有文件) 或 文件名): ")
    command = ["git", "add"]

    if add_target.lower() == "a":
        command.append(".")
        print("\n 正在添加所有文件到暂存区...")
    elif add_target:
        command.append(add_target)
        print(f"\n 正在添加文件 '{add_target}' 到暂存区...")
    else:
        print("\n **错误**: 输入为空，操作已取消。")
        input("按任意键继续...")
        return

    return_code, stdout, stderr = run_git_command(command)

    # run_git_command 已经处理了错误打印
    if return_code == 0:
         print("\n 文件已成功添加到暂存区。")
    # else: 错误信息已在 run_git_command 中打印

    input("按任意键继续...")


def commit_changes():
    """提交修改
    命令: git commit --file temp_commit_message.txt
    """
    clear_screen()
    print("=====================================================")
    print(" [5] 提交暂存区的修改")
    print("=====================================================")
    print("\n")

    commit_message = input(" 请输入提交信息: ")
    if not commit_message:
        print("\n **错误**: 提交信息不能为空！ 操作已取消。")
        input("按任意键继续...")
        return

    # 写入临时文件，并确保文件编码是 UTF-8
    temp_file_name = "temp_git_commit_message.txt"
    try:
        with open(temp_file_name, "w", encoding="utf-8") as f:
            f.write(commit_message)
    except Exception as e:
        print(f"\n**错误**: 创建临时提交信息文件失败: {e}")
        input("按任意键继续...")
        return

    print("\n 正在提交修改...")
    return_code, stdout, stderr = run_git_command(
        ["git", "commit", "--file", temp_file_name]
    )

    # 提交完成后删除临时文件
    if os.path.exists(temp_file_name):
        os.remove(temp_file_name)

    # run_git_command 已经处理了错误打印
    if return_code == 0:
        print(f"\n 提交成功，提交信息: '{commit_message}'")
    # else: 错误信息已在 run_git_command 中打印

    input("按任意键继续...")

# 原有的 create_branch, push_branch, pull_upstream, setup_upstream, add_remote, delete_local_branch, delete_remote_branch, create_pull_request, clean_commits 函数保留，但需要整合到新的菜单和流程中，并可能微调提示。
# 为了避免代码过长，我们将旧函数直接搬过来，只修改提示和菜单编号。

# --- 分支与同步 函数 (原有的，调整编号和提示) ---

def create_switch_branch():
    """创建并切换到新分支 或 切换到已有分支
    命令: git checkout -b <branch_name> (创建并切换)
          git checkout <branch_name> (切换到已有)
    """
    clear_screen()
    print("=====================================================")
    print(" [6] 创建/切换分支")
    print("=====================================================")
    print("\n")
    print(" [1]  创建并切换到新分支")
    print(" [2]  切换到已有本地分支")
    print("\n [b]  返回上一级菜单")
    print("\n")

    while True:
        branch_action = input(" 请选择操作 (1, 2, b): ")
        if branch_action == 'b':
            return
        elif branch_action in ('1', '2'):
            break
        else:
            print("\n **错误**: 无效的选择.")

    if branch_action == '1':
        # 创建并切换
        branch_name = input(" 请输入新分支名称: ")
        if not branch_name:
            print("\n **错误**: 分支名称不能为空！")
            input("按任意键继续...")
            return

        print("\n 正在创建并切换到分支", branch_name, "...")
        return_code, stdout, stderr = run_git_command(
            ["git", "checkout", "-b", branch_name]
        )

        if return_code != 0:
            print("\n **错误**: 创建分支失败。")
            print(" 请检查分支名称是否合法或已存在。 可以尝试使用git branch查看已存在的分支")
            # run_git_command 已经打印了 stderr
        else:
             print("\n 已成功创建并切换到分支", branch_name)

        input("按任意键继续...")

    elif branch_action == '2':
        # 切换到已有
        print("\n 正在获取本地分支列表...")
        return_code, stdout, stderr = run_git_command(["git", "branch"])
        if return_code != 0:
             print("\n **错误**: 获取本地分支列表失败。")
             # run_git_command 已经打印了 stderr
             input("按任意键继续...")
             return

        print("\n 本地分支列表:")
        print(stdout) # 打印分支列表

        branch_name = input(" 请输入要切换到的分支名称: ")
        if not branch_name:
            print("\n **错误**: 分支名称不能为空！")
            input("按任意键继续...")
            return

        print("\n 正在切换到分支", branch_name, "...")
        return_code, stdout, stderr = run_git_command(
            ["git", "checkout", branch_name]
        )

        if return_code != 0:
            print("\n **错误**: 切换分支失败。")
            print(" 请检查分支名称是否正确或是否存在未提交的修改。 可以尝试使用git status查看工作区状态")
            # run_git_command 已经打印了 stderr
        else:
             print("\n 已成功切换到分支", branch_name)

        input("按任意键继续...")


def pull_changes():
    """拉取远程更改
    命令: git pull <remote_name> <branch_name>
    """
    clear_screen()
    print("=====================================================")
    print(" [7] 拉取远程更改")
    print("=====================================================")
    print("\n")

    remote_name = input(" 请输入要拉取的远程仓库名称 (默认为 origin): ")
    if not remote_name:
        remote_name = "origin"

    branch_name = input(f" 请输入要拉取的远程分支名称 (默认为 {config.get('default_branch_name', 'main')}, 直接回车使用默认值): ")
    if not branch_name:
        branch_name = config.get("default_branch_name", "main")

    print(f"\n 正在从远程仓库 '{remote_name}' 拉取分支 '{branch_name}' 的最新更改...")
    return_code, stdout, stderr = run_git_command(
        ["git", "pull", remote_name, branch_name]
    )

    if return_code != 0:
        print("\n **错误**: 拉取远程更改失败。")
        print("  请检查您的网络连接, 远程仓库地址是否正确，以及是否存在冲突。")
        # run_git_command 已经打印了 stderr/stdout
        # 检查是否是合并冲突
        if "conflict" in (stdout + stderr).lower():
             print("\n **提示**: 似乎存在合并冲突。请手动编辑冲突文件，解决冲突后使用 'git add .' 和 'git commit' 完成合并。")
    else:
        print(stdout) # pull 成功时通常会打印合并信息
        print(f"\n 已成功从 '{remote_name}/{branch_name}' 拉取最新更改。")

    input("按任意键继续...")


def push_branch():
    """推送分支到远程仓库
    命令: git push <remote_name> <branch_name>
    """
    clear_screen()
    print("=====================================================")
    print(" [8] 推送本地分支")
    print("=====================================================")
    print("\n")

    # 尝试获取当前分支名称作为默认推送分支
    current_branch = None
    rc, out, err = run_git_command(["git", "rev-parse", "--abbrev-ref", "HEAD"])
    if rc == 0:
        current_branch = out.strip()
        print(f"  当前分支为: {current_branch}")

    remote_name = input(" 请输入要推送到的远程仓库名称 (默认为 origin): ")
    if not remote_name:
        remote_name = "origin"

    push_branch_name = input(
        f" 请输入要推送的本地分支名称 (默认为当前分支 '{current_branch}' 或 '{config.get('default_branch_name', 'main')}'): "
    )
    if not push_branch_name:
        push_branch_name = current_branch if current_branch else config.get("default_branch_name", "main")

    print(f"\n 正在推送本地分支 '{push_branch_name}' 到远程仓库 '{remote_name}'...")
    return_code, stdout, stderr = run_git_command(
        ["git", "push", remote_name, push_branch_name]
    )

    if return_code != 0:
        print("\n **错误**: 推送分支失败。")
        print("  请检查分支名称是否正确, 远程仓库配置是否正确, 或者权限是否足够。")
        print("\n  常见错误：")
        print("  - 没有推送权限：确认你对该远程仓库有 push 权限。")
        print("  - 远程分支不存在/需要跟踪：首次推送新分支时，可能需要使用 'git push -u origin <branch_name>'。")
        print("  - 您的本地分支落后于远程分支：请先使用 'git pull' 拉取远程更改并解决冲突。")
        # run_git_command 已经打印了 stderr/stdout
    else:
        print(stdout) # push 成功时通常有输出
        print(f"\n 分支 '{push_branch_name}' 已成功推送到 '{remote_name}'。")

    input("按任意键继续...")


def sync_fork():
    """同步 Fork (从 Upstream 更新到本地，再推送到 origin)
    命令: git checkout <default_branch>
         git pull upstream <default_branch>
         git push origin <default_branch>
    """
    clear_screen()
    print("=====================================================")
    print(" [9] 同步 Fork (从 Upstream 更新)")
    print("=====================================================")
    print("\n")

    default_branch = config.get("default_branch_name", "main")
    upstream_url = config.get("default_upstream_url", "未配置Upstream URL") # 用于提示

    print(f" 假设你的 upstream 已设置为指向原始仓库 ({upstream_url})")
    print(f" 假设你的 origin 已设置为指向你的 Fork 仓库")
    print(f" 假设你的主分支是 '{default_branch}'")
    print("\n 此操作将执行以下步骤：")
    print(f" 1. 切换到 '{default_branch}' 分支")
    print(f" 2. 从 upstream 拉取 '{default_branch}' 分支的最新代码")
    print(f" 3. 将更新后的本地 '{default_branch}' 分支推送到 origin")
    print("\n 按回车键继续，或按 Ctrl+C 取消。")
    input()

    # 步骤 1: 切换到默认分支
    print(f"\n 正在切换到 '{default_branch}' 分支...")
    return_code, stdout, stderr = run_git_command(["git", "checkout", default_branch])
    if return_code != 0:
        print(f"\n **错误**: 切换到 '{default_branch}' 分支失败。")
        print("  请检查本地是否存在名为", default_branch, "的分支，或者是否有未提交的修改。")
        # run_git_command 已经打印了 stderr/stdout
        input("按任意键继续...")
        return

    # 步骤 2: 从 upstream 拉取
    print(f"\n 正在从 upstream 拉取 '{default_branch}' 分支...")
    return_code, stdout, stderr = run_git_command(
        ["git", "pull", "upstream", default_branch]
    )
    if return_code != 0:
        print(f"\n **错误**: 从 upstream 拉取 '{default_branch}' 分支失败。")
        print("  请检查 upstream 是否配置正确 (使用 'git remote -v' 查看)。")
        print("  如果存在合并冲突，请手动解决后再次提交。")
        # run_git_command 已经打印了 stderr/stdout
        input("按任意键继续...")
        # 注意: 发生拉取冲突后，本地仓库处于冲突状态，需要用户手动解决。
        # 这里的函数会退出，用户需要根据提示手动操作或使用其他菜单项。
        return

    # 步骤 3: 推送到 origin
    print(f"\n 正在推送到 origin/'{default_branch}'...")
    return_code, stdout, stderr = run_git_command(["git", "push", "origin", default_branch])
    if return_code != 0:
        print(f"\n **错误**: 推送 '{default_branch}' 分支到 origin 失败。")
        print("  请检查远程仓库配置是否正确, 远程分支是否存在。")
        # run_git_command 已经打印了 stderr/stdout
    else:
        print(stdout) # push 成功时通常有输出
        print(f"\n 已成功从 upstream 同步并推送到 origin/'{default_branch}'。")

    input("按任意键继续...")


# --- 高级操作与管理 函数 (部分新增，部分原有调整编号) ---

def merge_branch():
    """合并分支"""
    clear_screen()
    print("=====================================================")
    print(" [10] 合并分支")
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
        input("按任意键继续...")
        return

    print(f"\n 正在将分支 '{branch_to_merge}' 合并到当前分支 '{current_branch}'...")
    return_code, stdout, stderr = run_git_command(["git", "merge", branch_to_merge])

    if return_code != 0:
        print(f"\n **错误**: 合并分支 '{branch_to_merge}' 失败。")
        # run_git_command 已经打印了 stderr/stdout
        # 检查是否是合并冲突
        if "conflict" in (stdout + stderr).lower():
            print("\n **提示**: 似乎存在合并冲突。")
            print("   请手动编辑冲突文件 (使用 'git status' 查看冲突文件)，解决冲突标记 (<<<<<<<, =======, >>>>>>>)，")
            print("   然后使用 'git add <冲突文件>' 将解决后的文件标记为已解决，")
            print("   最后使用 'git commit' 完成合并。")
            print("   如果想放弃合并，请使用 'git merge --abort'。")
        else:
            print("  请检查来源分支名称是否正确，或者当前分支是否有未提交的修改。")
    else:
        print(stdout) # 成功合并通常有输出
        print(f"\n 已成功将分支 '{branch_to_merge}' 合并到当前分支 '{current_branch}'。")

    input("按任意键继续...")


def rebase_branch():
    """变基分支 (危险!)"""
    clear_screen()
    print("=====================================================")
    print(" [11] 变基分支 (危险!)")
    print("=====================================================")
    print("\n")

    print(" **警告：变基会重写提交历史！切勿对已经推送到公共（多人协作）仓库的分支进行变基！**")
    print(" **变基通常用于清理您自己的本地特性分支的历史，使其基于最新的主分支。**")
    print("\n")

    # 尝试获取当前分支
    current_branch = None
    rc, out, err = run_git_command(["git", "rev-parse", "--abbrev-ref", "HEAD"])
    if rc == 0:
        current_branch = out.strip()
        print(f"  当前分支: {current_branch}")

    onto_branch = input(" 请输入要将当前分支变基到哪个分支之上 (例如: main): ")
    if not onto_branch:
        print("\n **错误**: 目标分支名称不能为空！ 操作已取消。")
        input("按任意键继续...")
        return

    print(f"\n **再次警告：** 您确定要将当前分支 '{current_branch}' 变基到 '{onto_branch}' 之上吗？")
    confirmation = input("  输入 'yes' 继续，输入其他任何内容取消操作： ")
    if confirmation.lower() != "yes":
        print("\n操作已取消。")
        input("\n按任意键继续...")
        return

    print(f"\n 正在将分支 '{current_branch}' 变基到 '{onto_branch}' 之上...")
    return_code, stdout, stderr = run_git_command(["git", "rebase", onto_branch])

    if return_code != 0:
        print(f"\n **错误**: 变基分支失败。")
        # run_git_command 已经打印了 stderr/stdout
        # 检查是否是冲突
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
        print(stdout) # 成功变基通常有输出
        print(f"\n 已成功将分支 '{current_branch}' 变基到 '{onto_branch}' 之上。")
        print("\n **注意：** 变基后提交哈希会改变，如果之前已推送过，可能需要强制推送 ('git push --force')。")
        print("            **切勿对公共分支强制推送！**")


    input("按任意键继续...")


def manage_stash():
    """管理储藏区"""
    clear_screen()
    print("=====================================================")
    print(" [12] 储藏/暂存修改 (git stash)")
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

    if stash_choice == 'b':
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
            print(stdout) # 通常会显示创建的 stash 信息
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
            # run_git_command 已经打印了 stderr/stdout
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
            # run_git_command 已经打印了 stderr/stdout
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
            input("按任意键继续...")
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
             # run_git_command 已经打印了 stderr/stdout
        else:
             print(f"\n 储藏 '{stash_ref}' 已成功删除。")
    else:
        print("\n **错误**: 无效的选择！")

    input("\n按任意键继续...")


def cherry_pick_commit():
    """拣选/摘取提交"""
    clear_screen()
    print("=====================================================")
    print(" [13] 拣选/摘取提交 (git cherry-pick)")
    print("=====================================================")
    print("\n")

    print(" 此操作将指定提交的更改应用到当前分支。")
    print(" 请确保你当前所在的分支是接收这些更改的目标分支。")
    print(" 你可以使用 'git log' 查看提交历史，获取提交哈希。")
    print("\n")

    commit_hash = input(" 请输入要拣选的提交哈希: ")
    if not commit_hash:
        print("\n **错误**: 提交哈希不能为空！ 操作已取消。")
        input("按任意键继续...")
        return

    print(f"\n 正在将提交 '{commit_hash}' 拣选到当前分支...")
    return_code, stdout, stderr = run_git_command(["git", "cherry-pick", commit_hash])

    if return_code != 0:
        print("\n **错误**: 拣选提交失败。")
        # run_git_command 已经打印了 stderr/stdout
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


def manage_tags():
    """管理标签"""
    clear_screen()
    print("=====================================================")
    print(" [14] 管理标签 (git tag)")
    print("=====================================================")
    print("\n")
    print(" 请选择标签操作:")
    print(" [1]  列出所有标签      (git tag)")
    print(" [2]  创建新标签        (git tag <tagname> 或 git tag -a <tagname>)")
    print(" [3]  删除本地标签      (git tag -d <tagname>)")
    print(" [4]  推送所有本地标签  (git push origin --tags)") # 添加推送所有标签的功能
    print(" [5]  删除远程标签      (git push origin --delete tag <tagname>)") # 添加删除远程标签的功能
    print("\n [b]  返回上一级菜单")
    print("\n")

    tag_choice = input(" 请选择操作 (1-5, b): ")

    if tag_choice == 'b':
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
            input("按任意键继续...")
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
            input("按任意键继续...")
            return

        print(f"\n **警告：** 你确定要删除本地标签 '{tag_name}' 吗？")
        confirmation = input("  输入 'yes' 继续，输入其他任何内容取消操作： ")
        if confirmation.lower() != "yes":
            print("\n操作已取消。")
            input("\n按任意键继续...")
            return

        print(f"\n 正在删除本地标签 '{tag_name}'...")
        return_code, stdout, stderr = run_git_command(["git", "tag", "-d", tag_name])
        if return_code != 0:
             print("\n **错误**: 删除本地标签失败。请检查标签是否存在。")
             # run_git_command 已经打印了 stderr/stdout
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
             # run_git_command 已经打印了 stderr/stdout
        else:
             print(f"\n 所有本地标签已成功推送到 '{remote_name}'。")
    elif tag_choice == '5':
        tag_name = input(" 请输入要删除的远程标签名称: ")
        if not tag_name:
            print("\n **错误**: 标签名称不能为空！ 操作已取消。")
            input("按任意键继续...")
            return

        remote_name = input(" 请输入远程仓库名称 (默认为 origin): ")
        if not remote_name:
            remote_name = "origin"

        print(f"\n **警告：** 你确定要删除远程仓库 '{remote_name}' 上的标签 '{tag_name}' 吗？")
        confirmation = input("  输入 'yes' 继续，输入其他任何内容取消操作： ")
        if confirmation.lower() != "yes":
            print("\n操作已取消。")
            input("\n按任意键继续...")
            return

        print(f"\n 正在删除远程仓库 '{remote_name}' 上的标签 '{tag_name}'...")
        # 命令格式是 git push <remote_name> --delete tag <tag_name>
        return_code, stdout, stderr = run_git_command(["git", "push", remote_name, "--delete", "tag", tag_name])
        if return_code != 0:
             print("\n **错误**: 删除远程标签失败。请检查远程仓库配置或标签是否存在。")
             # run_git_command 已经打印了 stderr/stdout
        else:
             print(f"\n 远程仓库 '{remote_name}' 上的标签 '{tag_name}' 已成功删除。")
    else:
        print("\n **错误**: 无效的选择！")

    input("\n按任意键继续...")


def manage_remotes():
    """管理远程仓库"""
    clear_screen()
    print("=====================================================")
    print(" [15] 管理远程仓库 (git remote)")
    print("=====================================================")
    print("\n")
    print(" 请选择远程仓库操作:")
    print(" [1]  列出所有远程仓库  (git remote -v)")
    print(" [2]  添加新的远程仓库  (git remote add)")
    print(" [3]  删除指定的远程仓库 (git remote remove)")
    print(" [4]  重命名指定的远程仓库 (git remote rename)")
    print(" [5]  设置 upstream 仓库 (方便同步)") # 直接调用 setup_upstream 函数
    print("\n [b]  返回上一级菜单")
    print("\n")

    remote_choice = input(" 请选择操作 (1-5, b): ")

    if remote_choice == 'b':
        return
    elif remote_choice == '1':
        print("\n 正在列出所有远程仓库...")
        return_code, stdout, stderr = run_git_command(["git", "remote", "-v"])
        if return_code == 0:
            print("\n 远程仓库列表:")
            print(stdout if stdout.strip() else " (当前没有远程仓库)")
        # else: run_git_command 已经打印了错误
    elif remote_choice == '2':
        def add_remote():
            """添加新的远程仓库"""
            remote_name = input("请输入远程仓库名称 (例如 origin): ")
            if not remote_name:
                print("\n **错误**: 远程仓库名称不能为空！ 操作已取消。")
                return

            remote_url = input("请输入远程仓库地址 (例如 https://github.com/user/repo.git): ")
            if not remote_url:
                print("\n **错误**: 远程仓库地址不能为空！ 操作已取消。")
                return

            print(f"\n 正在添加远程仓库 '{remote_name}' -> '{remote_url}'...")
            return_code, stdout, stderr = run_git_command(["git", "remote", "add", remote_name, remote_url])
            if return_code != 0:
                print("\n **错误**: 添加远程仓库失败。请检查名称和地址是否正确。")
            else:
                print(f"\n 远程仓库 '{remote_name}' 已成功添加。")

        add_remote()
    elif remote_choice == '3':
        remote_name = input(" 请输入要删除的远程仓库名称: ")
        if not remote_name:
            print("\n **错误**: 远程仓库名称不能为空！ 操作已取消。")
            input("按任意键继续...")
            return

        print(f"\n **警告：** 你确定要删除远程仓库 '{remote_name}' 的配置吗？")
        confirmation = input("  输入 'yes' 继续，输入其他任何内容取消操作： ")
        if confirmation.lower() != "yes":
            print("\n操作已取消。")
            input("\n按任意键继续...")
            return

        print(f"\n 正在删除远程仓库 '{remote_name}'...")
        return_code, stdout, stderr = run_git_command(["git", "remote", "remove", remote_name])
        if return_code != 0:
             print("\n **错误**: 删除远程仓库失败。请检查远程仓库名称是否存在。")
             # run_git_command 已经打印了 stderr/stdout
        else:
             print(f"\n 远程仓库 '{remote_name}' 的配置已成功删除。")
    elif remote_choice == '4':
        old_name = input(" 请输入要重命名的远程仓库旧名称: ")
        if not old_name:
            print("\n **错误**: 旧名称不能为空！ 操作已取消。")
            input("按任意键继续...")
            return
        new_name = input(" 请输入要重命名的远程仓库新名称: ")
        if not new_name:
            print("\n **错误**: 新名称不能为空！ 操作已取消。")
            input("按任意键继续...")
            return

        print(f"\n 正在重命名远程仓库 '{old_name}' 为 '{new_name}'...")
        return_code, stdout, stderr = run_git_command(["git", "remote", "rename", old_name, new_name])
        if return_code != 0:
             print("\n **错误**: 重命名远程仓库失败。请检查旧名称是否存在或新名称是否合法。")
             # run_git_command 已经打印了 stderr/stdout
        else:
             print(f"\n 远程仓库 '{old_name}' 已成功重命名为 '{new_name}'。")
    elif remote_choice == '5':
        # 直接调用 setup_upstream 函数
        setup_upstream()
    else:
        print("\n **错误**: 无效的选择！")

    input("\n按任意键继续...")


# 原有的 setup_upstream 函数，用于菜单15中的选项5
def setup_upstream():
    """设置 Upstream 仓库地址
    命令: git remote add upstream https://github.com/owner/repo.git
    """
    clear_screen()
    print("=====================================================")
    print(" [15] -> [5] 设置 Upstream 仓库地址")
    print("=====================================================")
    print("\n")

    # 获取配置中的默认 upstream URL
    default_upstream = config.get(
        "default_upstream_url", "git@github.com:upstream_owner/upstream_repo.git"
    )
    print(f" 建议将 upstream 设置为原始仓库的地址，例如: {default_upstream}")
    print(" 如果 config.yaml 中已设置 default_upstream_url，将默认使用该地址。")
    print(" 如果 upstream 已存在，此操作会失败。")

    upstream_url = input(f" 请输入上游仓库 (upstream) 的地址 (默认为 {default_upstream}): ")
    if not upstream_url:
        upstream_url = default_upstream

    # 检查 upstream 是否已存在
    rc_check, out_check, err_check = run_git_command(["git", "remote", "-v"], cwd=os.getcwd()) # 检查远程仓库列表
    if rc_check == 0 and f"upstream\t" in out_check:
        print("\n **错误**: 远程仓库 'upstream' 已存在。")
        print("  如果需要更改地址，请先使用 'git remote remove upstream' 删除后再添加。")
        input("按任意键继续...")
        return


    print(f"\n 正在设置 upstream 为 '{upstream_url}'...")
    return_code, stdout, stderr = run_git_command(
        ["git", "remote", "add", "upstream", upstream_url]
    )
    if return_code != 0:
        print("\n **错误**: 设置 upstream 失败。")
        # run_git_command 已经打印了 stderr/stdout
        print("\n  常见原因：upstream 已经存在或地址格式错误。")
    else:
        print(f"\n 已成功设置 upstream 为 '{upstream_url}'。")
        print("  现在你可以使用 'git pull upstream <branch_name>' 来从上游仓库拉取更新。")

    input("按任意键继续...")


# 原有的 delete_local_branch 函数，调整编号
def delete_local_branch():
    """删除本地分支
    命令: git branch -d <local_branch_name>
    """
    clear_screen()
    print("=====================================================")
    print(" [16] 删除本地分支")
    print("=====================================================")
    print("\n")

    # 先列出本地分支供用户参考
    print("\n 正在获取本地分支列表...")
    return_code_list, stdout_list, stderr_list = run_git_command(["git", "branch"])
    if return_code_list != 0:
        print("\n **错误**: 获取本地分支列表失败。")
        # run_git_command 已经打印了 stderr_list
        input("按任意键继续...")
        return

    print("\n 本地分支列表:")
    print(stdout_list) # 打印分支列表

    local_branch = input(" 请输入要删除的本地分支名称: ")
    if not local_branch:
        print("\n **错误**: 分支名称不能为空！")
        input("按任意键继续...")
        return

    # 简单检查分支是否在列表中（不精确，只看字符串包含）
    if local_branch not in stdout_list:
         print(f"\n **警告**: 分支 '{local_branch}' 似乎不在本地分支列表中。请仔细检查名称。")
         confirm_exist = input(" 继续删除操作吗？ (yes/no): ")
         if confirm_exist.lower() != 'yes':
              print("\n操作已取消。")
              input("按任意键继续...")
              return

    print(f"\n 正在删除本地分支 '{local_branch}'...")
    print(" 如果分支未合并，需要强制删除 (-D 选项)。")
    force_delete = input(" 未合并分支是否强制删除 (-D)? (yes/no, 默认为 no): ")

    command = ["git", "branch"]
    if force_delete.lower() == 'yes':
        command.append("-D") # 强制删除
    else:
        command.append("-d") # 安全删除 (已合并才删除)
    command.append(local_branch)

    return_code, stdout, stderr = run_git_command(command)

    if return_code != 0:
        print(f"\n **错误**: 删除本地分支 '{local_branch}' 失败。")
        # run_git_command 已经打印了 stderr/stdout
        if "-d" in command and "not fully merged" in (stdout + stderr).lower():
             print("\n **提示**: 分支未完全合并。如果确定要删除，请尝试使用强制删除选项 (-D)。")
        elif "checked out branch" in (stdout + stderr).lower():
             print("\n **提示**: 你不能删除当前所在的分支。请先切换到其他分支。")
        else:
             print("  请检查分支名称是否正确。")
    else:
        print(f"\n 本地分支 '{local_branch}' 已成功删除。")

    input("按任意键继续...")


# 原有的 delete_remote_branch 函数，调整编号
def delete_remote_branch():
    """删除远程分支
    命令: git push origin --delete <remote_branch_name>
    """
    clear_screen()
    print("=====================================================")
    print(" [17] 删除远程分支")
    print("=====================================================")
    print("\n")

    # 先列出远程分支供用户参考 (可选，可能太长，先不加)
    # print("\n 正在获取远程分支列表...")
    # ... 调用 git branch -r

    remote_branch = input(" 请输入要删除的远程分支名称: ")
    if not remote_branch:
        print("\n **错误**: 分支名称不能为空！")
        input("按任意键继续...")
        return

    remote_name = input(" 请输入远程仓库名称 (默认为 origin): ")
    if not remote_name:
        remote_name = "origin"

    print(f"\n **警告：** 你确定要删除远程仓库 '{remote_name}' 上的分支 '{remote_branch}' 吗？")
    confirmation = input("  输入 'yes' 继续，输入其他任何内容取消操作： ")
    if confirmation.lower() != "yes":
        print("\n操作已取消。")
        input("\n按任意键继续...")
        return

    print(f"\n 正在删除远程分支 '{remote_branch}' 在 '{remote_name}' 上...")
    return_code, stdout, stderr = run_git_command(
        ["git", "push", remote_name, "--delete", remote_branch]
    )
    if return_code != 0:
        print(f"\n **错误**: 删除远程分支 '{remote_branch}' 失败。")
        # run_git_command 已经打印了 stderr/stdout
        print("\n  常见错误：")
        print("  - 没有删除权限：确认你对该远程仓库有删除分支的权限。")
        print("  - 远程分支不存在：确认远程分支名称是否正确。")
        print("  - 网络问题：确认网络连接正常。")
    else:
        print(f"\n 远程分支 '{remote_branch}' 在 '{remote_name}' 上已成功删除。")

    input("\n按任意键继续...")


# 原有的 create_pull_request 函数，调整编号，需要用户输入分支名称
def create_pull_request():
    """创建 Pull Request (实际上是生成 URL 并提示用户手动创建)
    命令：无 (需要用户手动操作)
    """
    clear_screen()
    print("=====================================================")
    print(" [18] 创建 Pull Request")
    print("=====================================================")
    print("\n")

    # 从 config 中获取 fork_username 和 base_repo
    fork_username = config.get("fork_username", config.get("default_fork_username", "your_github_username"))
    base_repo = config.get("base_repo", config.get("default_base_repo", "upstream_owner/upstream_repo"))

    if fork_username == "your_github_username" or base_repo == "upstream_owner/upstream_repo":
         print("\n **警告**: 你的 GitHub 用户名或原始仓库名称未正确配置或输入。")
         print(f" 当前使用的用户名为: {fork_username}")
         print(f" 当前使用的原始仓库为: {base_repo}")
         print(" 请在运行脚本时或 config.yaml 中设置这些信息。")
         input("按任意键继续...")
         # 重新获取一次用户输入，但不更新 config，只是本次使用
         temp_fork_username = input(f" 请输入你的 GitHub 用户名 ({fork_username}): ") or fork_username
         temp_base_repo = input(f" 请输入原始仓库名称 ({base_repo}): ") or base_repo
         fork_username = temp_fork_username
         base_repo = temp_base_repo


    # 获取当前分支名称作为 PR 源分支的默认值
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
            input("按任意键继续...")
            return

    target_branch = input(f" 请输入目标分支名称 (默认为原始仓库的默认分支 '{config.get('default_branch_name', 'main')}'): ")
    if not target_branch:
        target_branch = config.get("default_branch_name", "main")

    # 构建 head repo 名称，通常是 "fork_username:source_branch"
    head_repo_ref = f"{fork_username}:{source_branch}"

    # 构建 URL
    # urlencode 分支名称和 PR 标题、body，以处理特殊字符
    # 注意：GitHub PR URL 格式是 /<base_repo>/compare/<target_branch>...<head_repo_ref>
    encoded_target = urllib.parse.quote(target_branch)
    encoded_head = urllib.parse.quote(head_repo_ref)

    # 预设的 PR 标题和 Body
    default_pr_title = "feat: Add a new feature" # 示例标题
    pr_title = input(f" 请输入 PR 标题 (默认为 '{default_pr_title}'): ") or default_pr_title
    encoded_title = urllib.parse.quote(pr_title)

    # 默认的 PR Body 内容 (使用原有的，或提供一个简单模板)
    # pr_body 可以在这里定义或加载一个模板文件
    pr_body_template = """<!-- 请在这里填写您的 Pull Request 详细描述 -->

## 描述

<!-- 请清晰地描述您的修改内容、解决了什么问题、为什么需要这个修改等 -->


## 相关 Issue

<!-- 请关联相关的 Issue，例如：Closes #123 -->


## 变更类型

<!-- 请使用 X 标记出本次 PR 的类型 -->
- [ ] Bug fix (修复了一个非破坏性的 bug)
- [ ] New feature (新增了一个非破坏性的功能)
- [ ] Breaking change (引入了破坏性的变更)
- [ ] Documentation change (修改了文档)
- [ ] Chore (其他不修改 src 或 test 文件的变更，如构建过程、辅助工具等)


## 检查清单

<!-- 请确保您完成了以下各项 -->
- [ ] 我已阅读并遵循了项目的贡献指南。
- [ ] 我已对我的代码进行了自我审查。
- [ ] 我已添加了适当的测试来覆盖我的修改。
- [ ] 我的修改通过了所有测试。
- [ ] 我的代码符合项目的编码规范。
- [ ] 我已更新了相关文档（如果需要）。

## 特别提醒 (如果需要)

<!-- 例如：这个改动需要特别注意哪个部分，或者有什么依赖条件 -->

"""
    # 注意：GitHub 的 new pull request 页面会自动加载提交信息作为 body 的一部分。
    # 直接在 URL 中提供 body 可能会覆盖或与自动加载的内容叠加。
    # 简化的做法是只提供 source 和 target，让用户在 GitHub 页面填写详情。
    # 如果一定要预填，上面的模板是一个例子，需要用户手动编辑。
    # 我们使用一个更简单的默认 body
    default_pr_body = "<!-- 请在 GitHub 页面填写 Pull Request 详细描述 -->"
    encoded_body = urllib.parse.quote(default_pr_body) # 简单预填

    # GitHub 比较页面 URL 格式：https://github.com/owner/repo/compare/target_branch...source_branch?title=...&body=...
    pr_url = f"https://github.com/{base_repo}/compare/{encoded_target}...{encoded_head}?title={encoded_title}&body={encoded_body}"

    print("\n 请复制以下 URL 到你的浏览器中，手动创建 Pull Request：")
    print(pr_url)

    # 尝试使用 web browser 打开 URL
    try:
        print("\n 尝试在默认浏览器中打开此 URL...")
        webbrowser.open(pr_url)
        print(" 如果浏览器没有自动打开，请手动复制 URL。")
    except Exception as e:
        print(f" 无法自动打开浏览器: {e}")
        print(" 请手动复制 URL。")

    input("\n按任意键继续...")


# 原有的 clean_commits 函数，调整编号，并再次强调危险性
def clean_commits():
    """清理 Commits (使用 git reset --hard)
    **极其危险操作**:  将会永久丢弃未推送的 commits!  使用前请务必备份!
    **用途：** 整理本地的提交历史，例如合并/修改 commit、删除实验性 commit。 **非日常操作！**
    **命令：** git reset --hard HEAD~<number_of_commits>

    **详细解释：**
    假设你的 commit 历史如下：
    A -- B -- C -- D -- E  (HEAD -> current_branch)
    其中 HEAD 指针指向最新的提交 E。

    `git reset --hard HEAD~2`  会将你的仓库回退到提交 C 的状态：
    1. **移动 HEAD 指针：**  HEAD 指针从 E 移动到 C。
    2. **重置暂存区和工作目录：**  暂存区 (staging area) 和工作目录 (working directory) 会被强制重置，与提交 C 的状态完全一致。
    3. **永久丢失：** 提交 D 和 E 的更改（以及任何未提交的本地更改）都将 **永久丢失**。

    **操作步骤：**
    1.  **强烈建议** 在操作前创建备份分支（`git branch backup-before-reset`）。
    2.  **确认要保留的 commit 数量。**  （输入0 则清空所有 commit，回到最初状态）
    3.  **输入数量并再次确认。**
    4.  **执行 `git reset --hard HEAD~{num_commits}`。**
    5.  **（如果需要同步远程） 慎重使用 `git push --force origin <branch_name>`。**
    """
    clear_screen()
    print("=====================================================")
    print(" [19] 清理 Commits (极其危险!)")
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

    # 提示当前分支和最近的 commits (可选，可以通过 git log 辅助判断)
    print("\n 正在获取最近的提交...")
    rc_log, out_log, err_log = run_git_command(["git", "log", "--oneline", "-n", "10"])
    if rc_log == 0:
        print("\n 最近的 10 个提交 (越上面越新):")
        print(out_log)
    else:
        print("\n 无法获取最近的提交历史。")
        # run_git_command 已经打印了错误

    num_commits_input = input(
        "\n  要丢弃最近的多少个 commits？ (输入数字并回车，输入 0 则清空所有 commit 回到初始状态): "
    )
    if not num_commits_input:
        print("\n **错误**: 必须输入要丢弃的 commits 数量！ 操作已取消。")
        input("\n按任意键继续...")
        return

    try:
        num_commits = int(num_commits_input)
        if num_commits < 0:
            print("\n **错误**: commit 数量必须是非负整数！ 操作已取消。")
            input("\n按任意键继续...")
            return
    except ValueError:
        print("\n **错误**: 输入的不是有效的整数！ 操作已取消。")
        input("\n按任意键继续...")
        return

    # 再次发出警告并确认
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
        input("\n按任意键继续...")
        return

    reset_command_list = ["git", "reset", "--hard", f"HEAD~{num_commits}"]

    print(f"\n  执行命令： {' '.join(reset_command_list)}")

    return_code, stdout, stderr = run_git_command(reset_command_list)

    if return_code != 0:
        print("\n **错误**: reset 失败，请检查您的操作。")
        # run_git_command 已经打印了 stderr/stdout
    else:
        print(f"\n  成功重置到 HEAD~{num_commits}!")
        print("  **注意：** 你的本地更改可能已经被丢弃，请检查你的工作目录。")
        print("\n  **重要：** 如果你的这个分支之前已经推送到远程仓库，并且你想让远程仓库也回退到当前状态，")
        print("             你需要使用 **强制推送 (git push --force)**。")
        print("             **`--force` 会覆盖远程仓库的历史！ 请只在自己完全掌控的私有分支上使用！**")
        print("             **如果多人协作开发，强制推送可能会导致严重问题！ 请三思！**")
        print("             强制推送命令示例： git push --force origin <你的分支名称>")

    input("\n按任意键继续...")


# --- 主程序入口 ---

if __name__ == "__main__":
    # 加载配置文件
    load_config()

    # 获取并设置 fork_username
    default_fork_username = config.get("default_fork_username", "your_github_username")
    fork_username = input(
        f"请输入你的 GitHub 用户名 (你的 Fork 仓库的所有者, 默认为 {default_fork_username}): "
    )
    if not fork_username:
        fork_username = default_fork_username
        print(f"使用默认 GitHub 用户名: {fork_username}")
    config["fork_username"] = fork_username  # 更新配置中的用户名供后续函数使用

    # 尝试从 default_upstream_url 中提取 base_repo 作为默认值
    extracted_base = extract_repo_name_from_upstream_url(config.get("default_upstream_url"))
    default_base_repo = extracted_base if extracted_base else config.get("default_base_repo", "upstream_owner/upstream_repo")

    base_repo = input(
        f"请输入原始仓库的名称 (格式 owner/repo, 默认为 {default_base_repo}): "
    )
    if not base_repo:
        base_repo = default_base_repo
        print(f"使用默认原始仓库名称: {base_repo}")
    config["base_repo"] = base_repo  # 更新配置中的仓库名称供后续函数使用

    print(f"\n已设置 GitHub 用户名为: {fork_username}")
    print(f"已设置原始仓库为: {base_repo}")
    input("\n按任意键继续...")

    # branch_name 变量不再需要全局维护，每个需要分支名称的函数内部获取即可

    while True:
        choice = main_menu()

        if choice == "0":
            clear_screen()
            print("\n 感谢使用！")
            break
        # 基础操作
        elif choice == "1":
            show_status()
        elif choice == "2":
            show_log()
        elif choice == "3":
            show_diff()
        elif choice == "4":
            add_changes()
        elif choice == "5":
            commit_changes()
        # 分支与同步
        elif choice == "6":
            create_switch_branch() # 合并了创建和切换
        elif choice == "7":
            pull_changes()
        elif choice == "8":
            push_branch()
        elif choice == "9":
            sync_fork()
        # 高级操作与管理
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
            manage_remotes() # 将远程仓库管理功能合并
        elif choice == "16":
            delete_local_branch()
        elif choice == "17":
            delete_remote_branch()
        elif choice == "18":
            create_pull_request()
        elif choice == "19":
            clean_commits()
        else:
            print("\n **错误**: 无效的选择！")
            input("\n按任意键继续...")