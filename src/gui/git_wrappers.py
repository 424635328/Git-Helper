# src/gui/git_wrappers.py

# Import necessary backend functions
from src.git_utils import run_git_command

import os
import sys
import webbrowser
import urllib.parse
from src.config_manager import config # Access config for defaults/stored values


# --- Basic Operations Wrappers ---
def wrapper_show_status(**kwargs):
    """Wraps git status to return output."""
    code, out, err = run_git_command(["git", "status"], cwd=kwargs.get('project_root'))
    return out, err, code

def wrapper_show_log(log_format, **kwargs):
    """Wraps git log to return output based on format."""
    command = ["git", "log"]
    if log_format == "oneline":
        command.extend(["--pretty=oneline", "--abbrev-commit"])
    elif log_format == "graph":
        command.extend(["--graph", "--pretty=format:%C(auto)%h%d %s %C(dim)%an%C(reset)", "--all"])
    else:
        return "", "Invalid log format specified.", 1

    code, out, err = run_git_command(command, cwd=kwargs.get('project_root'))
    return out, err, code

def wrapper_show_diff(diff_type, commit1=None, commit2=None, **kwargs):
    """Wraps git diff to return output."""
    command = ["git", "diff"]
    if diff_type == "unstaged":
        pass # default
    elif diff_type == "staged":
        command.append("--staged")
    elif diff_type == "working_tree_vs_head":
         command.append("HEAD")
    elif diff_type == "commits":
        if not commit1: return "", "Error: Commit1 is required for diff type 'commits'.", 1
        if not commit2:
             command.extend([commit1, "HEAD"])
        else:
             command.extend([commit1, commit2])
    else:
        return "", "Invalid diff type specified.", 1

    code, out, err = run_git_command(command, cwd=kwargs.get('project_root'))
    return out, err, code

def wrapper_add_changes(add_target, **kwargs):
    """Wraps git add."""
    command = ["git", "add"]
    if not add_target: return "", "Error: Add target cannot be empty.", 1
    command.append(add_target)

    code, out, err = run_git_command(command, cwd=kwargs.get('project_root'))
    return out, err, code

def wrapper_commit_changes(message, **kwargs):
    """Wraps git commit, handling temporary file."""
    if not message: return "", "Error: Commit message cannot be empty.", 1

    project_root = kwargs.get('project_root')
    if not project_root: return "", "Error: Project root not provided to commit wrapper.", 1

    temp_file_name = "temp_git_commit_message.txt"
    temp_file_path = os.path.join(project_root, temp_file_name)

    code, out, err = 1, "", "Unknown error" # Initialize for finally block

    try:
        os.makedirs(os.path.dirname(temp_file_path), exist_ok=True)
        with open(temp_file_path, "w", encoding="utf-8") as f:
            f.write(message)

        command = ["git", "commit", "--file", temp_file_name]
        code, out, err = run_git_command(command, cwd=project_root)
        return out, err, code
    except Exception as e:
         return "", f"Error during commit: {e}", 1
    finally:
        if os.path.exists(temp_file_path):
            try:
                os.remove(temp_file_path)
            except Exception as e:
                print(f"Warning: Could not remove temp file {temp_file_path}: {e}", file=sys.stderr)


# --- Branch & Sync Wrappers ---
def wrapper_create_switch_branch(action_type, branch_name, **kwargs):
    """Wraps git checkout -b or git checkout."""
    if not branch_name: return "", "Error: Branch name cannot be empty.", 1

    command = []
    if action_type == "create_and_switch":
        command = ["git", "checkout", "-b", branch_name]
    elif action_type == "switch":
        command = ["git", "checkout", branch_name]
    else: return "", "Error: Invalid branch action type.", 1

    code, out, err = run_git_command(command, cwd=kwargs.get('project_root'))
    return out, err, code

def wrapper_pull_changes(remote_name, branch_name, **kwargs):
    """Wraps git pull."""
    if not remote_name or not branch_name: return "", "Error: Remote name and branch name are required for pull.", 1
    command = ["git", "pull", remote_name, branch_name]
    code, out, err = run_git_command(command, cwd=kwargs.get('project_root'))
    return out, err, code

def wrapper_push_branch(remote_name, branch_name, **kwargs):
    """Wraps git push."""
    if not remote_name or not branch_name: return "", "Error: Remote name and branch name are required for push.", 1
    command = ["git", "push", remote_name, branch_name]
    code, out, err = run_git_command(command, cwd=kwargs.get('project_root'))
    return out, err, code

def wrapper_sync_fork_sequence(project_root, default_branch, **kwargs):
     """Wraps the sync fork sequence."""
     if not default_branch: return "", "Error: Default branch name is required for sync fork.", 1

     steps = [
         (["git", "checkout", default_branch], f"Checking out branch '{default_branch}'..."),
         (["git", "pull", "upstream", default_branch], f"Pulling from upstream/{default_branch}..."),
         (["git", "push", "origin", default_branch], f"Pushing to origin/{default_branch}...")
     ]

     output_text = ""
     error_text = ""
     final_code = 0

     for cmd, msg in steps:
         code, out, err = run_git_command(cmd, cwd=project_root)
         output_text += out
         if err:
             error_text += f"Error in step '{msg}':\n{err}\n"
         if code != 0:
              final_code = code
              error_text += f"Step failed with code {code}. Aborting sync.\n"
              break

     return output_text, error_text, final_code

# --- Advanced Operations Wrappers ---

def wrapper_merge_branch(branch_to_merge, **kwargs):
    """Wraps git merge."""
    if not branch_to_merge: return "", "Error: Branch name to merge cannot be empty.", 1
    command = ["git", "merge", branch_to_merge]
    code, out, err = run_git_command(command, cwd=kwargs.get('project_root'))
    return out, err, code

def wrapper_rebase_branch(onto_branch, **kwargs):
    """Wraps git rebase."""
    if not onto_branch: return "", "Error: Base branch name for rebase cannot be empty.", 1
    command = ["git", "rebase", onto_branch]
    code, out, err = run_git_command(command, cwd=kwargs.get('project_root'))
    return out, err, code

def wrapper_manage_stash(stash_action, stash_ref=None, message=None, **kwargs):
    """Wraps git stash operations."""
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
        if stash_ref: command.append(stash_ref)
        else: return "", "Error: Stash reference is required for drop.", 1
    else: return "", "Error: Invalid stash action specified.", 1

    code, out, err = run_git_command(command, cwd=kwargs.get('project_root'))
    return out, err, code

def wrapper_cherry_pick_commit(commit_hash, **kwargs):
    """Wraps git cherry-pick."""
    if not commit_hash: return "", "Error: Commit hash cannot be empty for cherry-pick.", 1
    command = ["git", "cherry-pick", commit_hash]
    code, out, err = run_git_command(command, cwd=kwargs.get('project_root'))
    return out, err, code

def wrapper_manage_tags(tag_action, tag_name=None, tag_type=None, tag_message=None, remote_name=None, **kwargs):
    """Wraps git tag operations."""
    command = ["git", "tag"]
    if tag_action == "list":
        pass
    elif tag_action == "create":
        if not tag_name: return "", "Error: Tag name is required for creation.", 1
        if tag_type == "annotated":
             command.append("-a")
             command.append(tag_name)
             if tag_message: command.extend(["-m", tag_message])
        else:
            command.append(tag_name)
    elif tag_action == "delete_local":
        if not tag_name: return "", "Error: Tag name is required for local deletion.", 1
        command.extend(["-d", tag_name])
    elif tag_action == "push_all":
        command = ["git", "push"]
        remote_name = remote_name or "origin"
        command.extend([remote_name, "--tags"])
    elif tag_action == "delete_remote":
         if not tag_name: return "", "Error: Tag name is required for remote deletion.", 1
         command = ["git", "push"]
         remote_name = remote_name or "origin"
         command.extend([remote_name, "--delete", "tag", tag_name])
    else: return "", "Error: Invalid tag action specified.", 1

    code, out, err = run_git_command(command, cwd=kwargs.get('project_root'))
    return out, err, code


def wrapper_manage_remotes(remote_action, name=None, url=None, old_name=None, new_name=None, **kwargs):
     """Wraps git remote operations."""
     command = ["git", "remote"]
     if remote_action == "list":
         command.append("-v")
     elif remote_action == "add":
         if not name or not url: return "", "Error: Name and URL are required for adding remote.", 1
         command.extend(["add", name, url])
     elif remote_action == "remove":
         if not name: return "", "Error: Remote name is required for removal.", 1
         command.extend(["remove", name])
     elif remote_action == "rename":
         if not old_name or not new_name: return "", "Error: Old and new names are required for renaming.", 1
         command.extend(["rename", old_name, new_name])
     elif remote_action == "setup_upstream":
          upstream_url = url or config.get("default_upstream_url", "git@github.com:upstream_owner/upstream_repo.git")
          if not upstream_url: return "", "Error: Upstream URL not provided or configured.", 1
          code_check, out_check, err_check = run_git_command(["git", "remote", "-v"], cwd=kwargs.get('project_root'))
          if code_check == 0 and f"upstream\t" in out_check:
              return "", "Error: Remote 'upstream' already exists. Please remove it first (Option 15-3).", 1

          command.extend(["add", "upstream", upstream_url])
     else: return "", "Error: Invalid remote action specified.", 1

     code, out, err = run_git_command(command, cwd=kwargs.get('project_root'))
     return out, err, code


def wrapper_delete_local_branch(branch_name, force=False, **kwargs):
    """Wraps git branch -d/-D."""
    if not branch_name: return "", "Error: Branch name is required for local deletion.", 1
    command = ["git", "branch"]
    if force: command.append("-D")
    else: command.append("-d")
    command.append(branch_name)
    code, out, err = run_git_command(command, cwd=kwargs.get('project_root'))
    return out, err, code

def wrapper_delete_remote_branch(branch_name, remote_name="origin", **kwargs):
    """Wraps git push --delete."""
    if not branch_name: return "", "Error: Branch name is required for remote deletion.", 1
    if not remote_name: remote_name = "origin"
    command = ["git", "push", remote_name, "--delete", branch_name]
    code, out, err = run_git_command(command, cwd=kwargs.get('project_root'))
    return out, err, code

# --- Specific High-Level Wrappers (originally in advanced_management) ---

def wrapper_create_pull_request(fork_username, base_repo, source_branch, target_branch, open_url_signal=None, **kwargs):
    """Generates PR URL and potentially opens browser."""
    # Note: open_url_signal is passed from the worker, which receives it from MainWindow
    if not fork_username or not base_repo or not source_branch or not target_branch:
         return "", "Error: Fork username, base repo, source and target branches are required for PR.", 1

    head_repo_ref = f"{fork_username}:{source_branch}"
    encoded_target = urllib.parse.quote(target_branch)
    encoded_head = urllib.parse.quote(head_repo_ref)

    # Simple default title/body, or get from dialogs if needed
    pr_title = "feat: Update from Fork"
    pr_body = "<!-- Created by git-helper GUI -->" # Added GUI indicator
    encoded_title = urllib.parse.quote(pr_title)
    default_pr_body = "This is the default pull request body."  # Define a default PR body
    encoded_body = urllib.parse.quote(default_pr_body) # Use default body from previous example

    # GitHub URL format for creating a PR: https://github.com/owner/repo/compare?base=...&head=...&title=...&body=...
    pr_url = f"https://github.com/{base_repo}/compare?base={encoded_target}&head={encoded_head}&title={encoded_title}&body={encoded_body}"

    output_msg = f"Please copy the following URL to your browser to create the Pull Request:\n{pr_url}"

    # Emit the signal to open the URL in the main thread
    if open_url_signal:
         open_url_signal.emit(pr_url) # Emit the signal with the generated URL

    return output_msg, "", 0 # Return URL string as output, no error, success code 0


def wrapper_clean_commits(num_commits_to_discard, **kwargs):
    """Wraps git reset --hard HEAD~N."""
    # WARNING: Reset --hard is extremely dangerous. Confirmation MUST be handled in the GUI.
    if num_commits_to_discard < 0:
        return "", "Error: Invalid commit count.", 1

    command = ["git", "reset", "--hard", f"HEAD~{num_commits_to_discard}"]
    code, out, err = run_git_command(command, cwd=kwargs.get('project_root'))
    return out, err, code