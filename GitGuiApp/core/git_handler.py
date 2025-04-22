# core/git_handler.py
import subprocess
import os
import sys
import logging
# --- MODIFICATION: Import pyqtSlot ---
from PyQt6.QtCore import QObject, pyqtSignal, QThread, pyqtSlot
# --- END MODIFICATION ---

# GitWorker class remains the same as the previous full version
class GitWorker(QObject):
    finished = pyqtSignal(int, str, str)
    progress = pyqtSignal(str)
    def __init__(self, command_list: list, repo_path: str):
        super().__init__(); self.command_list = command_list; self.repo_path = repo_path; self.process = None
        self.is_global_git_config = command_list and command_list[0].lower() == 'git' and '--global' in command_list and 'config' in command_list
    def run(self):
        stdout_full = ""; stderr_full = ""; return_code = -1; display_cmd = ' '.join(self.command_list)
        try:
            self.progress.emit(f"执行: {display_cmd}"); cwd = self.repo_path
            if self.is_global_git_config: cwd = None; logging.info(f"执行全局 Git 命令: {display_cmd}")
            elif self.repo_path and os.path.isdir(self.repo_path): logging.info(f"在目录 '{self.repo_path}' 中执行: {display_cmd}")
            else: cwd = None; logging.info(f"在默认环境执行: {display_cmd}")
            startupinfo = None
            if sys.platform == "win32": startupinfo = subprocess.STARTUPINFO(); startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW; startupinfo.wShowWindow = subprocess.SW_HIDE
            self.process = subprocess.Popen( self.command_list, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding='utf-8', errors='replace', startupinfo=startupinfo, shell=False )
            stdout_full, stderr_full = self.process.communicate(); return_code = self.process.returncode
            if return_code == 0: self.progress.emit(f"命令成功: {display_cmd}"); logging.info(f"命令成功 (RC {return_code}): {display_cmd}")
            else: self.progress.emit(f"命令失败 (RC {return_code}): {display_cmd}"); logging.warning(f"命令失败 (RC {return_code}): {display_cmd}\nStderr: {stderr_full}")
        except FileNotFoundError: stderr_full = f"错误: 命令 '{self.command_list[0]}' 未找到。"; logging.error(stderr_full); return_code = -1
        except PermissionError as e: stderr_full = f"错误: 权限不足 '{self.command_list[0]}': {e}"; logging.error(stderr_full); return_code = -3
        except Exception as e: stderr_full = f"意外错误: {e}\n命令: {display_cmd}"; logging.exception(f"意外错误: {display_cmd}"); return_code = -2
        finally: self.finished.emit(return_code, stdout_full, stderr_full)


class GitHandler(QObject): # --- MODIFICATION: Inherit from QObject for slots ---
    """Handles execution of Git and related Shell commands asynchronously."""
    def __init__(self, repo_path: str = None):
        super().__init__() # --- MODIFICATION: Call super().__init__ ---
        self._repo_path = repo_path or os.getcwd()
        # --- MODIFICATION: Keep track of active operations ---
        self.active_operations = [] # List to store (thread, worker) tuples
        # --- END MODIFICATION ---

    # set_repo_path, get_repo_path, _validate_repo, is_valid_repo remain the same
    def set_repo_path(self, path: str):
        if path and os.path.isdir(path): self._repo_path = path; self._validate_repo(); logging.info(f"仓库路径设为: {self._repo_path}")
        elif not path: self._repo_path = None; logging.warning("仓库路径设为空。")
        else: logging.error(f"设置路径失败 '{path}'"); self._repo_path = path
    def get_repo_path(self) -> str | None: return self._repo_path
    def _validate_repo(self):
        if not self._repo_path or not os.path.isdir(self._repo_path): logging.warning(f"仓库路径无效 '{self._repo_path}'"); return
        git_dir = os.path.join(self._repo_path, '.git');
        if not os.path.isdir(git_dir): logging.warning(f"路径 '{self._repo_path}' 可能不是Git仓库")
        else: logging.info(f"路径 '{self._repo_path}' 包含 .git")
    def is_valid_repo(self) -> bool:
        if not self._repo_path or not os.path.isdir(self._repo_path): return False
        git_dir = os.path.join(self._repo_path, '.git'); return os.path.isdir(git_dir)

    # --- MODIFICATION: Add slot to handle worker finished ---
    @pyqtSlot(object, object) # Decorator indicating it's a slot
    def _on_worker_finished(self, thread, worker):
        """Slot called internally when a worker's thread finishes to clean up references."""
        logging.debug(f"Worker for command '{' '.join(worker.command_list)}' finished. Removing from active list.")
        try:
            self.active_operations.remove((thread, worker))
            logging.debug(f"Removed operation. Active operations count: {len(self.active_operations)}")
        except ValueError:
            logging.warning("Attempted to remove an operation that was not in the active list.")
        # Note: deleteLater for thread and worker are still connected separately
    # --- END MODIFICATION ---


    def execute_command_async(self, command: list, finished_slot, progress_slot=None):
        """Executes a command asynchronously."""
        if not command: logging.error("尝试执行空命令。"); return
        is_global_git_config = command[0].lower() == 'git' and '--global' in command and 'config' in command
        if not is_global_git_config and not self.is_valid_repo():
            error_msg = f"错误：路径 '{self._repo_path}' 无效或未设置。"
            logging.warning(f"阻止执行 '{' '.join(command)}' 因仓库无效: {self._repo_path}")
            finished_slot(-3, "", error_msg); return

        thread = QThread() # Create new thread/worker instances
        worker = GitWorker(command, self._repo_path)
        worker.moveToThread(thread)

        # --- MODIFICATION: Add to active list and connect internal cleanup ---
        operation_tuple = (thread, worker)
        self.active_operations.append(operation_tuple)
        logging.debug(f"Starting operation: {' '.join(command)}. Active count: {len(self.active_operations)}")
        # Connect the worker's finished signal to OUR cleanup slot FIRST
        # Use a lambda to pass the thread and worker objects to the slot
        worker.finished.connect(lambda rc, so, se, t=thread, w=worker: self._on_worker_finished(t, w))
        # --- END MODIFICATION ---

        # Connect signals for external caller and standard cleanup
        worker.finished.connect(finished_slot) # External callback
        if progress_slot: worker.progress.connect(progress_slot)
        worker.finished.connect(thread.quit) # Quit the thread event loop
        worker.finished.connect(worker.deleteLater) # Schedule worker deletion
        thread.finished.connect(thread.deleteLater) # Schedule thread deletion

        thread.started.connect(worker.run)
        thread.start()

    # --- Git Command Specific Methods (remain the same as previous full version) ---
    def get_status_async(self, finished_slot, progress_slot=None): self.execute_command_async(['git', 'status'], finished_slot, progress_slot)
    def add_async(self, files: list[str] | str, finished_slot, progress_slot=None):
        cmd = ['git', 'add'];
        if isinstance(files, str):
             if files == '.': cmd.append('.')
             else: cmd.append(files)
        elif isinstance(files, list): cmd.extend(files)
        else: finished_slot(-4,"", "错误：'add' 需要文件路径字符串或列表。"); return
        self.execute_command_async(cmd, finished_slot, progress_slot)
    def commit_async(self, message: str, add_all: bool = False, finished_slot=None, progress_slot=None):
        if not message: finished_slot(-5, "", "错误：提交信息不能为空。"); return
        cmd = ['git', 'commit'];
        if add_all: cmd.append('-a')
        cmd.extend(['-m', message]); self.execute_command_async(cmd, finished_slot, progress_slot)
    def pull_async(self, remote='origin', branch=None, finished_slot=None, progress_slot=None):
        cmd = ['git', 'pull', remote];
        if branch: cmd.append(branch)
        self.execute_command_async(cmd, finished_slot, progress_slot)
    def push_async(self, remote='origin', branch=None, finished_slot=None, progress_slot=None):
        cmd = ['git', 'push', remote];
        if branch: cmd.append(branch)
        self.execute_command_async(cmd, finished_slot, progress_slot)
    def get_current_branch_async(self, finished_slot, progress_slot=None): self.execute_command_async(['git', 'rev-parse', '--abbrev-ref', 'HEAD'], finished_slot, progress_slot)
    def list_branches_async(self, finished_slot, progress_slot=None): self.execute_command_async(['git', 'branch'], finished_slot, progress_slot)
    def switch_branch_async(self, branch_name: str, finished_slot, progress_slot=None):
        if not branch_name: finished_slot(-6, "", "错误：分支名称不能为空。"); return
        self.execute_command_async(['git', 'checkout', branch_name], finished_slot, progress_slot)
    def create_branch_async(self, branch_name: str, finished_slot, progress_slot=None):
        if not branch_name: finished_slot(-11, "", "错误：新分支名称不能为空。"); return
        self.execute_command_async(['git', 'branch', branch_name], finished_slot, progress_slot)
    def delete_branch_async(self, branch_name: str, force: bool = False, finished_slot=None, progress_slot=None):
        if not branch_name: finished_slot(-12, "", "错误：要删除的分支名称不能为空。"); return
        cmd = ['git', 'branch']; cmd.append('-D' if force else '-d'); cmd.append(branch_name)
        self.execute_command_async(cmd, finished_slot, progress_slot)
    def list_remotes_async(self, finished_slot, progress_slot=None): self.execute_command_async(['git', 'remote', '-v'], finished_slot, progress_slot)
    def set_git_config_async(self, key: str, value: str, is_global: bool, finished_slot, progress_slot=None):
        if not key: finished_slot(-7, "", "错误：配置项名称不能为空。"); return
        cmd = ['git', 'config'];
        if is_global: cmd.append('--global')
        cmd.extend([key, value]); self.execute_command_async(cmd, finished_slot, progress_slot)
    def get_status_porcelain_async(self, finished_slot, progress_slot=None): self.execute_command_async(['git', 'status', '--porcelain=v1'], finished_slot, progress_slot)
    def get_branches_formatted_async(self, finished_slot, progress_slot=None):
        cmd = ['git', 'branch', '-a', '--format=%(HEAD) %(refname:short)', '--sort=-committerdate']
        self.execute_command_async(cmd, finished_slot, progress_slot)
    def stage_files_async(self, files: list[str], finished_slot, progress_slot=None):
        if not files: logging.warning("Attempted to stage empty list."); finished_slot(0,"",""); return
        cmd = ['git', 'add', '--'] + files; self.execute_command_async(cmd, finished_slot, progress_slot)
    def unstage_files_async(self, files: list[str], finished_slot, progress_slot=None):
        if not files: logging.warning("Attempted to unstage empty list."); finished_slot(0,"",""); return
        cmd = ['git', 'reset', 'HEAD', '--'] + files; self.execute_command_async(cmd, finished_slot, progress_slot)
    def get_diff_async(self, file_path: str, staged: bool, finished_slot, progress_slot=None):
         if not file_path: finished_slot(-8, "", "错误：需要提供文件路径。"); return
         cmd = ['git', 'diff'];
         if staged: cmd.append('--staged')
         cmd.extend(['--', file_path]); self.execute_command_async(cmd, finished_slot, progress_slot)
    def get_log_formatted_async(self, count=50, finished_slot=None, progress_slot=None):
         format_str = "%h%x09%an%x09%ar%x09%s"; cmd = ['git', 'log', f'--pretty=format:{format_str}', '--graph', f'-n{count}']
         self.execute_command_async(cmd, finished_slot, progress_slot)
    def get_commit_details_async(self, commit_hash: str, finished_slot, progress_slot=None):
        if not commit_hash: finished_slot(-9, "", "错误：需要提供 Commit Hash。"); return
        cmd = ['git', 'show', '--stat', commit_hash]; self.execute_command_async(cmd, finished_slot, progress_slot)