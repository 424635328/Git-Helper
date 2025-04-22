# src/gui/git_wrappers.py

# 导入必要的后端函数
from src.git_utils import run_git_command

import os
import sys
import webbrowser
import urllib.parse
# 导入配置管理器 - 用于默认的上游 URL
from src.config_manager import config

# 为包装器使用一致的函数签名模式：
# def wrapper_func(参数1, 参数2, ..., project_root=None, open_url_signal=None, **kwargs):
# 这使得 _start_git_worker 可以将用户输入作为命名参数传递，
# 并将上下文参数（project_root, signals）作为特定的 kwargs 传递。
# 任何其他意外的 kwargs 将进入 **kwargs（尽管理想情况下不应该有）。

# --- 基本操作包装器 ---
def wrapper_show_status(project_root=None, **kwargs):
    """包装 git status 返回输出。"""
    code, out, err = run_git_command(["git", "status"], cwd=project_root)
    return out, err, code

def wrapper_show_log(log_format, project_root=None, **kwargs):
    """包装 git log 根据格式返回输出。"""
    if log_format is None: return "", "错误：log_format 是必需的。", 1 # 添加验证

    command = ["git", "log"]
    if log_format == "oneline":
        command.extend(["--pretty=oneline", "--abbrev-commit"])
    elif log_format == "graph":
        command.extend(["--graph", "--pretty=format:%C(auto)%h%d %s %C(dim)%an%C(reset)", "--all"])
    else:
        # 这种情况应该在调用前被 GUI 捕获
        return "", "指定了无效的日志格式。", 1

    code, out, err = run_git_command(command, cwd=project_root)
    return out, err, code

def wrapper_show_diff(diff_type, commit1=None, commit2=None, project_root=None, **kwargs):
    """包装 git diff 返回输出。"""
    if diff_type is None: return "", "错误：diff_type 是必需的。", 1 # 添加验证

    command = ["git", "diff"]
    if diff_type == "unstaged":
        pass # 默认
    elif diff_type == "staged":
        command.append("--staged")
    elif diff_type == "working_tree_vs_head":
         command.append("HEAD")
    elif diff_type == "commits":
        if not commit1: return "", "错误：对于 diff 类型 'commits'，Commit1 是必需的。", 1
        if not commit2:
             command.extend([commit1, "HEAD"])
        else:
             command.extend([commit1, commit2])
    else:
        # 应该被 GUI 捕获
        return "", "指定了无效的 diff 类型。", 1

    code, out, err = run_git_command(command, cwd=project_root)
    return out, err, code

def wrapper_add_changes(add_target, project_root=None, **kwargs):
    """包装 git add。"""
    if not add_target: return "", "错误：添加目标不能为空。", 1 # 添加验证

    command = ["git", "add", add_target] # add_target 已经过验证
    code, out, err = run_git_command(command, cwd=project_root)
    return out, err, code

def wrapper_commit_changes(message, project_root=None, **kwargs):
    """包装 git commit，处理临时文件。"""
    if not message: return "", "错误：提交信息不能为空。", 1 # 添加验证
    if not project_root: return "", "错误：未向提交包装器提供项目根目录。", 1

    temp_file_name = "temp_git_commit_message.txt"
    temp_file_path = os.path.join(project_root, temp_file_name)

    code, out, err = 1, "", "未知错误" # 初始化用于 finally 块

    try:
        # 在写入前确保目录存在（在根目录不太可能需要，但这是一个好的做法）
        os.makedirs(os.path.dirname(temp_file_path), exist_ok=True)
        with open(temp_file_path, "w", encoding="utf-8") as f:
            f.write(message)

        command = ["git", "commit", "--file", temp_file_name]
        code, out, err = run_git_command(command, cwd=project_root)
        return out, err, code
    except Exception as e:
         return "", f"提交过程中出错：{e}", 1
    finally:
        # 清理临时文件
        if os.path.exists(temp_file_path):
            try:
                os.remove(temp_file_path)
            except Exception as e:
                print(f"警告：无法删除临时文件 {temp_file_path}：{e}", file=sys.stderr)


# --- 分支与同步包装器 ---
def wrapper_create_switch_branch(action_type, branch_name, project_root=None, **kwargs):
    """包装 git checkout -b 或 git checkout。"""
    if not action_type: return "", "错误：action_type 是必需的。", 1
    if not branch_name: return "", "错误：分支名称不能为空。", 1

    command = []
    if action_type == "create_and_switch":
        command = ["git", "checkout", "-b", branch_name]
    elif action_type == "switch":
        command = ["git", "checkout", branch_name]
    else: return "", "错误：无效的分支操作类型。", 1

    code, out, err = run_git_command(command, cwd=project_root)
    return out, err, code

def wrapper_pull_changes(remote_name, branch_name, project_root=None, **kwargs):
    """包装 git pull。"""
    if not remote_name or not branch_name: return "", "错误：拉取需要远程名称和分支名称。", 1
    command = ["git", "pull", remote_name, branch_name]
    code, out, err = run_git_command(command, cwd=project_root)
    return out, err, code

def wrapper_push_branch(remote_name, branch_name, project_root=None, **kwargs):
    """包装 git push。"""
    if not remote_name or not branch_name: return "", "错误：推送需要远程名称和分支名称。", 1
    command = ["git", "push", remote_name, branch_name]
    code, out, err = run_git_command(command, cwd=project_root)
    return out, err, code

def wrapper_sync_fork_sequence(default_branch, project_root=None, **kwargs):
     """包装同步 fork 的序列操作。"""
     if not default_branch: return "", "错误：同步 fork 需要默认分支名称。", 1
     if not project_root: return "", "错误：同步 fork 未提供项目根目录。", 1


     steps = [
         (["git", "checkout", default_branch], f"正在切换到分支 '{default_branch}'..."),
         (["git", "pull", "upstream", default_branch], f"正在从 upstream/{default_branch} 拉取..."),
         (["git", "push", "origin", default_branch], f"正在推送到 origin/{default_branch}...")
     ]

     output_text = ""
     error_text = ""
     final_code = 0

     for cmd, msg in steps:
         # 注意：此包装器运行序列阻塞调用。
         # 对于实时分步反馈，包装器需要发出信号。
         # 目前，聚合输出/错误。
         output_text += f"\n--- 步骤：{msg} ---\n" # 将步骤信息添加到输出
         code, out, err = run_git_command(cmd, cwd=project_root)
         output_text += out
         if err:
             error_text += f"步骤 '{msg}' 中出错：\n{err}\n"
         if code != 0:
              final_code = code
              error_text += f"步骤因代码 {code} 失败。正在中止同步。\n"
              break

     return output_text, error_text, final_code

# --- 高级操作包装器 ---

def wrapper_merge_branch(branch_to_merge, project_root=None, **kwargs):
    """包装 git merge。"""
    if not branch_to_merge: return "", "错误：要合并的分支名称不能为空。", 1
    command = ["git", "merge", branch_to_merge]
    code, out, err = run_git_command(command, cwd=project_root)
    return out, err, code

def wrapper_rebase_branch(onto_branch, project_root=None, **kwargs):
    """包装 git rebase。"""
    if not onto_branch: return "", "错误：rebase 的基分支名称不能为空。", 1
    command = ["git", "rebase", onto_branch]
    code, out, err = run_git_command(command, cwd=project_root)
    return out, err, code

def wrapper_manage_stash(stash_action, stash_ref=None, message=None, project_root=None, **kwargs):
    """包装 git stash 操作。"""
    if not stash_action: return "", "错误：stash_action 是必需的。", 1

    command = ["git", "stash"]
    if stash_action == "list":
        command.append("list")
    elif stash_action == "push":
        command.append("push")
        if message: command.extend(["-m", message])
    elif stash_action == "apply":
        command.append("apply")
        if stash_ref: command.append(stash_ref)
    elif stash_action == "pop":
        command.append("pop")
        if stash_ref: command.append(stash_ref)
    elif stash_action == "drop":
        command.append("drop")
        if stash_ref: command.append(stash_ref) # drop 需要 stash ref
        else: return "", "错误：drop 需要 stash 引用。", 1 # 如果 GUI 验证，此检查是多余的
    else: return "", "错误：指定了无效的 stash 操作。", 1 # 应该被 GUI 捕获

    code, out, err = run_git_command(command, cwd=project_root)
    return out, err, code

def wrapper_cherry_pick_commit(commit_hash, project_root=None, **kwargs):
    """包装 git cherry-pick。"""
    if not commit_hash: return "", "错误：cherry-pick 的提交哈希不能为空。", 1
    command = ["git", "cherry-pick", commit_hash]
    code, out, err = run_git_command(command, cwd=project_root)
    return out, err, code

def wrapper_manage_tags(tag_action, tag_name=None, tag_type=None, tag_message=None, remote_name=None, project_root=None, **kwargs):
    """包装 git tag 操作。"""
    if not tag_action: return "", "错误：tag_action 是必需的。", 1

    command = ["git", "tag"] # 基本命令，可能在 push 时被替换

    if tag_action == "list":
        pass # git tag
    elif tag_action == "create":
        if not tag_name: return "", "错误：创建标签需要标签名称。", 1
        if tag_type == "annotated":
             command.append("-a")
             command.append(tag_name)
             if tag_message: command.extend(["-m", tag_message])
        else: # 默认为轻量级，或者如果类型是 'lightweight'
            command.append(tag_name)
    elif tag_action == "delete_local":
        if not tag_name: return "", "错误：删除本地标签需要标签名称。", 1
        command.extend(["-d", tag_name])
    elif tag_action == "push_all":
        command = ["git", "push"] # 重定义 push 命令
        remote_name_used = remote_name or "origin" # push 的默认远程
        command.extend([remote_name_used, "--tags"])
    elif tag_action == "delete_remote":
         if not tag_name: return "", "错误：删除远程标签需要标签名称。", 1
         command = ["git", "push"] # 重定义 push 命令
         remote_name_used = remote_name or "origin"
         command.extend([remote_name_used, "--delete", "tag", tag_name])
    else: return "", "错误：指定了无效的标签操作。", 1 # 应该被 GUI 捕获

    code, out, err = run_git_command(command, cwd=project_root)
    return out, err, code


def wrapper_manage_remotes(remote_action, name=None, url=None, old_name=None, new_name=None, project_root=None, **kwargs):
     """包装 git remote 操作。"""
     if not remote_action: return "", "错误：remote_action 是必需的。", 1

     command = ["git", "remote"]

     if remote_action == "list":
         command.append("-v")
     elif remote_action == "add":
         if not name or not url: return "", "错误：添加远程需要名称和 URL。", 1
         command.extend(["add", name, url])
     elif remote_action == "remove":
         if not name: return "", "错误：删除远程需要远程名称。", 1
         command.extend(["remove", name])
     elif remote_action == "rename":
         if not old_name or not new_name: return "", "错误：重命名需要旧名称和新名称。", 1
         command.extend(["rename", old_name, new_name])
     elif remote_action == "setup_upstream":
          # 如果提供了 URL，则使用，否则回退到配置
          upstream_url = url or config.get("default_upstream_url", "git@github.com:upstream_owner/upstream_repo.git")
          if not upstream_url: return "", "错误：未提供或配置上游 URL。", 1
          # 在尝试添加之前检查 'upstream' 是否已经存在
          # 理想情况下，此检查应该在 GUI 处理程序或单独的包装器中进行
          # 但为了健壮性，在此添加一个基本检查
          code_check, out_check, err_check = run_git_command(["git", "remote", "-v"], cwd=project_root)
          if code_check == 0 and f"upstream\t" in out_check:
              return "", "错误：远程 'upstream' 已存在。请先删除它（使用远程删除选项）。", 1

          command.extend(["add", "upstream", upstream_url]) # 名称硬编码为 'upstream'
     else: return "", "错误：指定了无效的远程操作。", 1 # 应该被 GUI 捕获

     code, out, err = run_git_command(command, cwd=project_root)
     return out, err, code


def wrapper_delete_local_branch(branch_name, force=False, project_root=None, **kwargs):
    """包装 git branch -d/-D。"""
    if not branch_name: return "", "错误：删除本地分支需要分支名称。", 1

    command = ["git", "branch"]
    if force: command.append("-D")
    else: command.append("-d")
    command.append(branch_name)

    code, out, err = run_git_command(command, cwd=project_root)
    return out, err, code

def wrapper_delete_remote_branch(branch_name, remote_name="origin", project_root=None, **kwargs):
    """包装 git push --delete。"""
    if not branch_name: return "", "错误：删除远程分支需要分支名称。", 1
    if not remote_name: remote_name = "origin" # 如果未提供，则默认为 origin

    command = ["git", "push", remote_name, "--delete", branch_name]
    code, out, err = run_git_command(command, cwd=project_root)
    return out, err, code

# --- 特定的高级包装器（最初在 advanced_management 中） ---

# 此包装器需要访问 open_url_signal 实例才能发出它。
# 信号实例从 MainWindow -> GitWorker -> 包装器 kwargs 传递。
def wrapper_create_pull_request(fork_username, base_repo, source_branch, target_branch, project_root=None, open_url_signal=None, **kwargs):
    """生成 PR URL 并可能打开浏览器。"""
    # 注意：open_url_signal 从 worker 传递过来，worker 从 MainWindow 接收它
    if not fork_username or not base_repo or not source_branch or not target_branch:
         return "", "错误：创建 PR 需要 fork 用户名、基础仓库、源分支和目标分支。", 1

    head_repo_ref = f"{fork_username}:{source_branch}"
    encoded_target = urllib.parse.quote(target_branch)
    encoded_head = urllib.parse.quote(head_repo_ref)

    # 简单的默认标题/正文，如果需要，可以从对话框中获取
    pr_title = "feat: Update from Fork"
    pr_body = "<!-- 由 git-helper GUI 创建 -->"
    encoded_title = urllib.parse.quote(pr_title)
    encoded_body = urllib.parse.quote(pr_body)

    # GitHub 创建 PR 的 URL 格式：https://github.com/owner/repo/compare?base=...&head=...&title=...&body=...
    pr_url = f"https://github.com/{base_repo}/compare?base={encoded_target}&head={encoded_head}&title={encoded_title}&body={encoded_body}"

    output_msg = f"请将以下 URL 复制到您的浏览器中创建 Pull Request：\n{pr_url}"

    # 使用传递的信号实例在主线程中发出信号以打开 URL
    if open_url_signal:
         open_url_signal.emit(pr_url)

    # 同时将 URL 字符串作为标准输出的一部分返回，以便在 QTextEdit 中显示
    # 返回 (output_msg, "", 0) 是标准的包装器返回格式
    return output_msg, "", 0


def wrapper_clean_commits(num_commits_to_discard, project_root=None, **kwargs):
    """包装 git reset --hard HEAD~N。"""
    # 警告：Reset --hard 极其危险。必须在 GUI 中处理确认。
    # num_commits_to_discard 已经在 GUI 中验证为非负整数
    if not project_root: return "", "错误：清除提交未提供项目根目录。", 1


    command = ["git", "reset", "--hard", f"HEAD~{num_commits_to_discard}"]
    code, out, err = run_git_command(command, cwd=project_root)
    return out, err, code