# core/git_handler.py
# -*- coding: utf-8 -*-
import subprocess
import os
import sys
import logging
from PyQt6.QtCore import QObject, pyqtSignal, QThread, pyqtSlot, QTimer
from typing import Union, Optional, List # Added List for older Python versions if needed

class GitWorker(QObject):
    finished = pyqtSignal(int, str, str)
    progress = pyqtSignal(str)

    def __init__(self, command_list: list, effective_cwd: Optional[str]):
        super().__init__()
        self.command_list = command_list
        # effective_cwd is the directory where the command should run,
        # determined by the handler (could be repo_path, explicit cwd, or None for global)
        self.effective_cwd = effective_cwd
        self.process: Optional[subprocess.Popen] = None

    def run(self):
        """Executes the Git command in the specified directory."""
        stdout_full = ""
        stderr_full = ""
        return_code = -1
        display_cmd = ' '.join(self.command_list) # For logging

        try:
            # Use the effective_cwd passed during initialization
            popen_cwd = self.effective_cwd
            if popen_cwd and not os.path.isdir(popen_cwd):
                 logging.warning(f"工作目录无效 '{popen_cwd}'，在默认环境执行。")
                 popen_cwd = None # Fallback to default environment if explicit cwd is bad

            if popen_cwd:
                 log_msg = f"在目录 '{popen_cwd}' 中执行: {display_cmd}"
            else:
                 log_msg = f"在默认环境/全局执行: {display_cmd}"

            logging.info(log_msg)
            self.progress.emit(f"执行: {display_cmd[:100]}...") # Emit progress start

            startupinfo = None
            if sys.platform == "win32":
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                startupinfo.wShowWindow = subprocess.SW_HIDE

            self.process = subprocess.Popen(
                self.command_list,
                cwd=popen_cwd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding='utf-8', # Use utf-8 consistently
                errors='replace', # Handle potential encoding errors
                startupinfo=startupinfo,
                shell=False # Security: Never use shell=True with variable command parts
            )

            # Process communication blocks until command finishes
            stdout_full, stderr_full = self.process.communicate()
            return_code = self.process.returncode
            self.process = None # Clear process reference

            if return_code == 0:
                self.progress.emit(f"命令成功: {display_cmd[:100]}")
                logging.info(f"命令成功 (返回码 {return_code}): {display_cmd}")
            else:
                # Don't emit progress for failure here, let finished signal handle it
                logging.warning(f"命令失败 (返回码 {return_code}): {display_cmd}\n标准错误: {stderr_full.strip()}")

        except FileNotFoundError:
            stderr_full = f"错误: 命令 '{self.command_list[0]}' 未找到。请确保 Git 已安装并在系统 PATH 中。"
            logging.error(stderr_full)
            return_code = -1 # Use specific code for file not found
        except PermissionError as e:
            stderr_full = f"错误: 权限不足，无法执行 '{self.command_list[0]}': {e}"
            logging.error(stderr_full)
            return_code = -3 # Use specific code for permission error
        except Exception as e:
            stderr_full = f"执行命令时发生意外错误: {e}\n命令: {display_cmd}"
            logging.exception(f"执行命令时发生意外错误: {display_cmd}")
            return_code = -2 # Use specific code for other exceptions
        finally:
            # Always emit finished signal
            self.finished.emit(return_code, stdout_full, stderr_full)

    def terminate(self):
        """Attempt to terminate the running process."""
        if self.process and self.process.poll() is None: # Check if process exists and is running
            logging.warning(f"尝试终止进程: {' '.join(self.command_list)}")
            try:
                self.process.terminate()
                # Optionally wait a short time and force kill if needed
                # self.process.wait(timeout=1)
                # if self.process.poll() is None:
                #     self.process.kill()
            except Exception as e:
                logging.error(f"终止进程时出错: {e}")
            self.process = None


class GitHandler(QObject):
    """Asynchronously handles Git command execution."""
    # Note: repo_path can be None if no repo is selected/valid yet
    def __init__(self, repo_path: Optional[str] = None):
        super().__init__()
        self._repo_path: Optional[str] = None
        # Store active operations as tuples (thread, worker)
        self.active_operations: list[tuple[QThread, GitWorker]] = []
        # Set initial path (might be None)
        self.set_repo_path(repo_path)

    def set_repo_path(self, path: Optional[str], check_valid=True):
        """Sets the Git repository path. Optionally checks validity."""
        old_path = self._repo_path
        if path and os.path.isdir(path):
            self._repo_path = os.path.abspath(path) # Store absolute path
            if check_valid and not self.is_valid_repo():
                 # Log warning but keep the path set, is_valid_repo() is the source of truth
                 logging.warning(f"设置的路径 '{self._repo_path}' 不是有效的 Git 仓库。")
            if old_path != self._repo_path:
                logging.info(f"仓库路径设为: {self._repo_path}")
        elif not path:
            if self._repo_path is not None:
                logging.info("仓库路径已清除。")
            self._repo_path = None
        else: # Path provided but not a directory
            logging.error(f"设置路径失败，无效目录: '{path}'")
            raise ValueError(f"路径 '{path}' 不是一个有效的目录。") # Raise error for invalid dir

    def get_repo_path(self) -> Optional[str]:
        """Gets the current Git repository path (can be None)."""
        return self._repo_path

    def is_valid_repo(self) -> bool:
        """Checks if the current repository path points to a valid Git repository."""
        if not self._repo_path: # Explicitly check if path is None
            return False
        # Check if the path exists and is a directory BEFORE checking for .git
        if not os.path.isdir(self._repo_path):
            return False
        git_dir = os.path.join(self._repo_path, '.git')
        return os.path.isdir(git_dir)

    @pyqtSlot(QThread, GitWorker) # Type hint the arguments
    def _on_worker_finished(self, thread: QThread, worker: GitWorker):
        """Internal slot called when a worker thread finishes, for cleanup."""
        op_tuple = (thread, worker)
        if op_tuple in self.active_operations:
            try:
                self.active_operations.remove(op_tuple)
                logging.debug(f"已移除完成的操作: {' '.join(worker.command_list)}. 剩余活动: {len(self.active_operations)}")
            except ValueError:
                # This might happen in rare race conditions, log it but don't crash
                logging.warning(f"尝试移除操作时发生 ValueError (可能已被移除): {' '.join(worker.command_list)}")
        else:
            logging.warning(f"完成的操作未在活动列表中找到: {' '.join(worker.command_list)}")

        # Standard cleanup signals (deleteLater) are connected in execute_command_async

    def get_active_process_count(self) -> int:
        """Returns the number of currently active Git operations."""
        return len(self.active_operations)

    def terminate_all_processes(self):
        """Attempts to terminate all currently running Git processes."""
        logging.warning(f"请求终止 {len(self.active_operations)} 个活动操作...")
        # Iterate over a copy because _on_worker_finished might modify the list concurrently
        ops_to_terminate = list(self.active_operations)
        terminated_count = 0
        for thread, worker in ops_to_terminate:
            try:
                worker.terminate() # Ask worker to terminate its process
                # We don't forcefully quit the thread here, allow finished signal
                # thread.quit() # This might be too abrupt
                # thread.wait(100) # Wait briefly?
                terminated_count += 1
            except Exception as e:
                logging.error(f"终止操作 '{' '.join(worker.command_list)}' 时出错: {e}")
        logging.warning(f"已尝试终止 {terminated_count} 个进程。")
        # Clear list optimistically? Or let finished signals clean up?
        # Let finished signals clean up normally for robustness.


    def execute_command_async(self, command: list, finished_slot, progress_slot=None, cwd: Optional[str] = None):
        """
        Asynchronously executes a command list in a separate thread.

        Args:
            command: The command and arguments as a list of strings.
            finished_slot: The slot to call upon completion. Signature: (return_code: int, stdout: str, stderr: str)
            progress_slot: Optional slot for progress updates. Signature: (message: str)
            cwd: Optional explicit working directory. If None, uses repo_path or global context.
        """
        if not command:
            logging.error("尝试执行空命令列表。")
            # Call finished slot immediately with an error code
            if finished_slot:
                QTimer.singleShot(0, lambda: finished_slot(-10, "", "错误：尝试执行空命令。"))
            return

        # Determine the effective working directory
        effective_cwd = cwd # Use explicitly passed cwd first
        is_global_cmd = command[0].lower() == 'git' and '--global' in command

        if effective_cwd is None and not is_global_cmd:
             # If no explicit cwd and not global, use the repo path
             effective_cwd = self._repo_path # This might be None if no repo selected

        if is_global_cmd:
             effective_cwd = None # Ensure global commands run without specific cwd


        # Basic check: Don't run most commands if repo invalid and path required
        # Allow specific commands like init, clone, config --global even if repo invalid
        needs_valid_repo = not is_global_cmd and command[0].lower() == 'git' and \
                           (len(command) < 2 or command[1].lower() not in ('init', 'clone'))

        if needs_valid_repo and not self.is_valid_repo():
            error_msg = f"错误：需要有效的 Git 仓库才能执行此命令，当前路径 '{self._repo_path}' 无效或未设置。"
            logging.warning(f"阻止执行 '{' '.join(command)}'，因为仓库无效: {self._repo_path}")
            if finished_slot:
                # Call finished slot immediately with an error code
                QTimer.singleShot(0, lambda: finished_slot(-3, "", error_msg))
            return

        # --- Thread and Worker Setup ---
        thread = QThread()
        # Pass the determined effective_cwd to the worker
        worker = GitWorker(command, effective_cwd)
        worker.moveToThread(thread)

        # --- Signal Connections ---
        # IMPORTANT: Connect internal cleanup *first* to ensure list is updated reliably
        op_tuple = (thread, worker)
        worker.finished.connect(lambda rc, so, se, t=thread, w=worker: self._on_worker_finished(t, w))

        # Connect external slots
        if finished_slot:
            worker.finished.connect(finished_slot)
        if progress_slot:
            worker.progress.connect(progress_slot)

        # Connect standard thread management signals
        worker.finished.connect(thread.quit)
        worker.finished.connect(worker.deleteLater) # Schedule worker for deletion after finished
        thread.finished.connect(thread.deleteLater) # Schedule thread for deletion after finished

        # Connect thread started signal to worker's run method
        thread.started.connect(worker.run)

        # --- Start Operation ---
        self.active_operations.append(op_tuple) # Add before starting
        logging.debug(f"开始异步操作: {' '.join(command)}. 活动计数: {len(self.active_operations)}")
        thread.start()


    def execute_command_sync(self, command: list) -> subprocess.CompletedProcess:
        """Synchronously executes a command list and returns CompletedProcess."""
        if not command:
            logging.error("尝试同步执行空命令列表。")
            return subprocess.CompletedProcess(command, -10, "", "错误：尝试执行空命令。")

        # Determine effective working directory
        effective_cwd = self._repo_path # Default to repo path
        is_global_cmd = command[0].lower() == 'git' and '--global' in command

        if is_global_cmd:
            effective_cwd = None # Global commands don't need repo path
        elif effective_cwd and not os.path.isdir(effective_cwd):
             logging.warning(f"同步执行的工作目录无效 '{effective_cwd}'，在默认环境执行。")
             effective_cwd = None

        # Check repo validity if needed
        needs_valid_repo = not is_global_cmd and command[0].lower() == 'git' and \
                           (len(command) < 2 or command[1].lower() not in ('init', 'clone'))

        if needs_valid_repo and not self.is_valid_repo():
             error_msg = f"错误：需要有效的 Git 仓库才能执行此命令，当前路径 '{self._repo_path}' 无效或未设置。"
             logging.warning(f"阻止同步执行 '{' '.join(command)}'，因为仓库无效: {self._repo_path}")
             return subprocess.CompletedProcess(command, -3, "", error_msg)

        if effective_cwd:
             log_msg = f"在目录 '{effective_cwd}' 中同步执行: {' '.join(command)}"
        else:
             log_msg = f"在默认环境/全局同步执行: {' '.join(command)}"
        logging.info(log_msg)

        startupinfo = None
        if sys.platform == "win32":
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = subprocess.SW_HIDE

        try:
            result = subprocess.run(
                command,
                cwd=effective_cwd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding='utf-8',
                errors='replace',
                startupinfo=startupinfo,
                shell=False,
                check=False # Let us handle the return code
            )
            if result.returncode != 0:
                 logging.warning(f"同步命令失败 (RC {result.returncode}): {' '.join(command)}\n标准错误: {result.stderr.strip()}")
            else:
                 logging.info(f"同步命令成功 (RC {result.returncode}): {' '.join(command)}")
            return result
        except FileNotFoundError:
            error_msg = f"错误: 命令 '{command[0]}' 未找到。请确保 Git 已安装并在系统 PATH 中。"
            logging.error(error_msg)
            return subprocess.CompletedProcess(command, -1, "", error_msg)
        except PermissionError as e:
            error_msg = f"错误: 权限不足，无法执行 '{command[0]}': {e}"
            logging.error(error_msg)
            return subprocess.CompletedProcess(command, -3, "", error_msg)
        except Exception as e:
            error_msg = f"同步执行时发生意外错误: {e}\n命令: {' '.join(command)}"
            logging.exception(f"同步执行时发生意外错误: {' '.join(command)}")
            return subprocess.CompletedProcess(command, -2, "", error_msg)


    # --- Git Command Specific Helper Methods ---
    # These wrap execute_command_async for convenience

    def get_status_porcelain_async(self, finished_slot, progress_slot=None):
        """Asynchronously gets `git status --porcelain=v1` output."""
        self.execute_command_async(['git', 'status', '--porcelain=v1', '--untracked-files=all'], finished_slot, progress_slot)

    def get_branches_formatted_async(self, finished_slot, progress_slot=None):
        """Asynchronously gets formatted branch list (* current, sorted)."""
        # Format includes HEAD indicator '*' and short refname
        cmd = ['git', 'branch', '-a', '--format=%(HEAD) %(refname:short)', '--sort=-committerdate']
        self.execute_command_async(cmd, finished_slot, progress_slot)

    def get_log_formatted_async(self, count=50, format: Optional[str] = None, extra_args: Optional[list] = None, finished_slot=None, progress_slot=None):
        """
        Asynchronously gets formatted commit log.

        Args:
            count: Number of commits to retrieve.
            format: Optional format string (e.g., "%h %s"). If None, uses default.
            extra_args: Optional list of additional arguments (e.g., ["--graph"]).
            finished_slot: Callback slot.
            progress_slot: Progress callback slot.
        """
        # Default format matches the one expected by main_window's parser
        format_str = format if format is not None else "%h\t%H\t%an\t%ar\t%s"
        cmd = ['git', 'log', f'--pretty=format:{format_str}', f'-n{count}']
        if extra_args:
            cmd.extend(extra_args)
        self.execute_command_async(cmd, finished_slot, progress_slot)

    def get_commit_details_async(self, commit_hash: str, finished_slot, progress_slot=None):
        """Asynchronously gets commit details using 'git show'."""
        if not commit_hash:
            if finished_slot: QTimer.singleShot(0, lambda: finished_slot(-9, "", "错误：需要提供 Commit Hash。"))
            return
        # Use --no-ext-diff for consistency and safety
        cmd = ['git', 'show', '--no-ext-diff', commit_hash]
        self.execute_command_async(cmd, finished_slot, progress_slot)

    # Other helpers can be added as needed, or use execute_command_async directly
    # Example:
    # def fetch_async(self, remote='origin', prune=False, finished_slot=None, progress_slot=None):
    #     cmd = ['git', 'fetch', remote]
    #     if prune:
    #         cmd.append('--prune')
    #     self.execute_command_async(cmd, finished_slot, progress_slot)