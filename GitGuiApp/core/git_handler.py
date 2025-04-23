# core/git_handler.py
# -*- coding: utf-8 -*-
import subprocess
import os
import sys
import logging
from PyQt6.QtCore import QObject, pyqtSignal, QThread, pyqtSlot
from typing import Union # 导入 Union

class GitWorker(QObject):
    finished = pyqtSignal(int, str, str)
    progress = pyqtSignal(str)

    def __init__(self, command_list: list, repo_path: str):
        super().__init__()
        self.command_list = command_list
        self.repo_path = repo_path
        self.process = None
        # 检查命令是否是全局 git config
        self.is_global_git_config = command_list and command_list[0].lower() == 'git' and '--global' in command_list and 'config' in command_list

    def run(self):
        """执行 Git 命令并发出信号"""
        stdout_full = ""
        stderr_full = ""
        return_code = -1
        display_cmd = ' '.join(self.command_list)

        try:
            self.progress.emit(f"执行: {display_cmd}")
            cwd = self.repo_path

            if self.is_global_git_config:
                cwd = None
                logging.info(f"执行全局 Git 命令: {display_cmd}")
            elif self.repo_path and os.path.isdir(self.repo_path):
                logging.info(f"在目录 '{self.repo_path}' 中执行: {display_cmd}")
            else:
                cwd = None
                logging.info(f"在默认环境执行: {display_cmd}")

            startupinfo = None
            if sys.platform == "win32":
                # 在 Windows 上隐藏控制台窗口
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                startupinfo.wShowWindow = subprocess.SW_HIDE

            # 执行子进程
            self.process = subprocess.Popen(
                self.command_list,
                cwd=cwd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding='utf-8',
                errors='replace',
                startupinfo=startupinfo,
                shell=False  # 避免 shell=True 带来的安全风险
            )

            # 读取输出
            stdout_full, stderr_full = self.process.communicate()
            return_code = self.process.returncode

            if return_code == 0:
                self.progress.emit(f"命令成功: {display_cmd}")
                logging.info(f"命令成功 (返回码 {return_code}): {display_cmd}")
            else:
                self.progress.emit(f"命令失败 (返回码 {return_code}): {display_cmd}")
                logging.warning(f"命令失败 (返回码 {return_code}): {display_cmd}\n标准错误: {stderr_full}")

        except FileNotFoundError:
            stderr_full = f"错误: 命令 '{self.command_list[0]}' 未找到。"
            logging.error(stderr_full)
            return_code = -1
        except PermissionError as e:
            stderr_full = f"错误: 权限不足 '{self.command_list[0]}': {e}"
            logging.error(stderr_full)
            return_code = -3
        except Exception as e:
            stderr_full = f"意外错误: {e}\n命令: {display_cmd}"
            logging.exception(f"意外错误: {display_cmd}")
            return_code = -2
        finally:
            # 发出完成信号
            self.finished.emit(return_code, stdout_full, stderr_full)


class GitHandler(QObject):
    """异步处理 Git 和相关 Shell 命令的执行。"""
    def __init__(self, repo_path: str = None):
        super().__init__()
        self._repo_path = repo_path or os.getcwd()
        # 跟踪活动的 Git 操作 (线程和工作者实例)
        self.active_operations = []

    def set_repo_path(self, path: str):
        """设置 Git 仓库路径并验证。"""
        if path and os.path.isdir(path):
            self._repo_path = path
            self._validate_repo()
            logging.info(f"仓库路径设为: {self._repo_path}")
        elif not path:
            self._repo_path = None
            logging.warning("仓库路径设为空。")
        else:
            logging.error(f"设置路径失败 '{path}'")
            self._repo_path = path

    # 已在上次修改中处理
    def get_repo_path(self) -> Union[str, None]:
        """获取当前的 Git 仓库路径。"""
        return self._repo_path

    def _validate_repo(self):
        """验证设置的路径是否是有效的 Git 仓库。"""
        if not self._repo_path or not os.path.isdir(self._repo_path):
            logging.warning(f"仓库路径无效 '{self._repo_path}'")
            return
        git_dir = os.path.join(self._repo_path, '.git')
        if not os.path.isdir(git_dir):
            logging.warning(f"路径 '{self._repo_path}' 可能不是 Git 仓库")
        else:
            logging.info(f"路径 '{self._repo_path}' 包含 .git")

    def is_valid_repo(self) -> bool:
        """检查当前的仓库路径是否有效。"""
        if not self._repo_path or not os.path.isdir(self._repo_path):
            return False
        git_dir = os.path.join(self._repo_path, '.git')
        return os.path.isdir(git_dir)

    @pyqtSlot(object, object)
    def _on_worker_finished(self, thread, worker):
        """工作者线程完成时由内部调用的槽，用于清理引用。"""
        logging.debug(f"命令 '{' '.join(worker.command_list)}' 的工作者已完成。正在从活动列表中移除。")
        try:
            # 安全地从活动操作列表中移除元组
            if (thread, worker) in self.active_operations:
                 self.active_operations.remove((thread, worker))
                 logging.debug(f"已移除操作。活动操作计数: {len(self.active_operations)}")
            else:
                 logging.warning("尝试移除不在活动列表中的操作。")
        except ValueError:
            logging.warning("移除操作时发生 ValueError，可能列表已改变。")
        except Exception as e:
             logging.exception(f"在 _on_worker_finished 中发生意外错误: {e}")

        # 注意: thread.deleteLater() 和 worker.deleteLater() 仍然会单独连接

    def execute_command_async(self, command: list, finished_slot, progress_slot=None):
        """异步执行一个命令。"""
        if not command:
            logging.error("尝试执行空命令。")
            return

        # 检查是否是全局 git config 命令，如果是则允许在非仓库路径下执行
        is_global_git_config = command[0].lower() == 'git' and '--global' in command and 'config' in command

        if not is_global_git_config and not self.is_valid_repo():
            error_msg = f"错误：路径 '{self._repo_path}' 无效或未设置。"
            logging.warning(f"阻止执行 '{' '.join(command)}'，因为仓库无效: {self._repo_path}")
            finished_slot(-3, "", error_msg) # 发出错误信号
            return

        # 创建新的线程和工作者实例
        thread = QThread()
        worker = GitWorker(command, self._repo_path)
        worker.moveToThread(thread)

        # 添加到活动列表并连接内部清理槽
        operation_tuple = (thread, worker)
        self.active_operations.append(operation_tuple)
        logging.debug(f"开始操作: {' '.join(command)}。活动计数: {len(self.active_operations)}")

        # 首先将工作者的 finished 信号连接到我们的清理槽
        # 使用 lambda 传递线程和工作者对象到槽
        worker.finished.connect(lambda rc, so, se, t=thread, w=worker: self._on_worker_finished(t, w))

        # 连接外部调用者的信号和标准的清理信号
        worker.finished.connect(finished_slot)  # 外部回调
        if progress_slot:
            worker.progress.connect(progress_slot)

        worker.finished.connect(thread.quit)  # 退出线程事件循环
        worker.finished.connect(worker.deleteLater)  # 安排工作者删除
        thread.finished.connect(thread.deleteLater)  # 安排线程删除

        # 连接线程的 started 信号到工作者的 run 方法
        thread.started.connect(worker.run)

        # 启动线程
        thread.start()

    def execute_command_sync(self, command: list) -> subprocess.CompletedProcess:
        """同步执行一个命令并返回 CompletedProcess 对象。"""
        if not command:
            logging.error("尝试同步执行空命令。")
            return subprocess.CompletedProcess(command, -1, "", "错误：尝试执行空命令。")

        # 检查是否是全局 git config 命令，如果是则允许在非仓库路径下执行
        is_global_git_config = command[0].lower() == 'git' and '--global' in command and 'config' in command

        if not is_global_git_config and not self.is_valid_repo():
             error_msg = f"错误：路径 '{self._repo_path}' 无效或未设置。"
             logging.warning(f"阻止同步执行 '{' '.join(command)}'，因为仓库无效: {self._repo_path}")
             return subprocess.CompletedProcess(command, -3, "", error_msg) # 返回模拟的 CompletedProcess

        cwd = self.repo_path
        if is_global_git_config:
            cwd = None # 全局配置命令不需要在特定仓库目录执行
            logging.info(f"同步执行全局 Git 命令: {' '.join(command)}")
        elif self.repo_path and os.path.isdir(self.repo_path):
            logging.info(f"在目录 '{self._repo_path}' 中同步执行: {' '.join(command)}")
        else:
            cwd = None
            logging.info(f"在默认环境同步执行: {' '.join(command)}")

        startupinfo = None
        if sys.platform == "win32":
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = subprocess.SW_HIDE

        try:
            # 使用 run 方法进行同步执行
            result = subprocess.run(
                command,
                cwd=cwd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding='utf-8',
                errors='replace',
                startupinfo=startupinfo,
                shell=False,
                check=False # 不要抛出异常，只返回返回码
            )
            if result.returncode != 0:
                 logging.warning(f"同步命令失败 (返回码 {result.returncode}): {' '.join(command)}\n标准错误: {result.stderr.strip()}")
            else:
                 logging.info(f"同步命令成功 (返回码 {result.returncode}): {' '.join(command)}")
            return result
        except FileNotFoundError:
            error_msg = f"错误: 命令 '{command[0]}' 未找到。"
            logging.error(error_msg)
            return subprocess.CompletedProcess(command, -1, "", error_msg)
        except PermissionError as e:
            error_msg = f"错误: 权限不足 '{command[0]}': {e}"
            logging.error(error_msg)
            return subprocess.CompletedProcess(command, -3, "", error_msg)
        except Exception as e:
            error_msg = f"意外错误: {e}\n命令: {' '.join(command)}"
            logging.exception(f"同步执行时发生意外错误: {' '.join(command)}")
            return subprocess.CompletedProcess(command, -2, "", error_msg)


    # --- Git 命令特定方法 ---
    def get_status_async(self, finished_slot, progress_slot=None):
        """异步获取 Git 状态。"""
        self.execute_command_async(['git', 'status'], finished_slot, progress_slot)

    # 修改了这一行的类型提示
    def add_async(self, files: Union[list[str], str], finished_slot, progress_slot=None):
        """异步执行 git add 命令。"""
        cmd = ['git', 'add']
        if isinstance(files, str):
             if files == '.': cmd.append('.')
             else: cmd.append(files)
        elif isinstance(files, list):
             cmd.extend(files)
        else:
             finished_slot(-4, "", "错误：'add' 需要文件路径字符串或列表。")
             return
        self.execute_command_async(cmd, finished_slot, progress_slot)

    def commit_async(self, message: str, add_all: bool = False, finished_slot=None, progress_slot=None):
        """异步执行 git commit 命令。"""
        if not message:
            finished_slot(-5, "", "错误：提交信息不能为空。")
            return
        cmd = ['git', 'commit']
        if add_all:
            cmd.append('-a')
        cmd.extend(['-m', message])
        self.execute_command_async(cmd, finished_slot, progress_slot)

    def pull_async(self, remote='origin', branch=None, finished_slot=None, progress_slot=None):
        """异步执行 git pull 命令。"""
        cmd = ['git', 'pull', remote]
        if branch:
            cmd.append(branch)
        self.execute_command_async(cmd, finished_slot, progress_slot)

    def push_async(self, remote='origin', branch=None, finished_slot=None, progress_slot=None):
        """异步执行 git push 命令。"""
        cmd = ['git', 'push', remote]
        if branch:
            cmd.append(branch)
        self.execute_command_async(cmd, finished_slot, progress_slot)

    def get_current_branch_async(self, finished_slot, progress_slot=None):
        """异步获取当前分支名称。"""
        self.execute_command_async(['git', 'rev-parse', '--abbrev-ref', 'HEAD'], finished_slot, progress_slot)

    def list_branches_async(self, finished_slot, progress_slot=None):
        """异步列出所有分支。"""
        self.execute_command_async(['git', 'branch'], finished_slot, progress_slot)

    def switch_branch_async(self, branch_name: str, finished_slot, progress_slot=None):
        """异步切换分支。"""
        if not branch_name:
            finished_slot(-6, "", "错误：分支名称不能为空。")
            return
        self.execute_command_async(['git', 'checkout', branch_name], finished_slot, progress_slot)

    def create_branch_async(self, branch_name: str, finished_slot, progress_slot=None):
        """异步创建分支。"""
        if not branch_name:
            finished_slot(-11, "", "错误：新分支名称不能为空。")
            return
        self.execute_command_async(['git', 'branch', branch_name], finished_slot, progress_slot)

    def delete_branch_async(self, branch_name: str, force: bool = False, finished_slot=None, progress_slot=None):
        """异步删除分支。"""
        if not branch_name:
            finished_slot(-12, "", "错误：要删除的分支名称不能为空。")
            return
        cmd = ['git', 'branch']
        cmd.append('-D' if force else '-d')
        cmd.append(branch_name)
        self.execute_command_async(cmd, finished_slot, progress_slot)

    def list_remotes_async(self, finished_slot, progress_slot=None):
        """异步列出远程仓库。"""
        self.execute_command_async(['git', 'remote', '-v'], finished_slot, progress_slot)

    def set_git_config_async(self, key: str, value: str, is_global: bool, finished_slot, progress_slot=None):
        """异步设置 Git 配置项。"""
        if not key:
            finished_slot(-7, "", "错误：配置项名称不能为空。")
            return
        cmd = ['git', 'config']
        if is_global:
            cmd.append('--global')
        cmd.extend([key, value])
        self.execute_command_async(cmd, finished_slot, progress_slot)

    def get_status_porcelain_async(self, finished_slot, progress_slot=None):
        """异步获取 'git status --porcelain=v1' 的输出。"""
        self.execute_command_async(['git', 'status', '--porcelain=v1'], finished_slot, progress_slot)

    def get_branches_formatted_async(self, finished_slot, progress_slot=None):
        """异步获取格式化的分支列表。"""
        cmd = ['git', 'branch', '-a', '--format=%(HEAD) %(refname:short)', '--sort=-committerdate']
        self.execute_command_async(cmd, finished_slot, progress_slot)

    def stage_files_async(self, files: list[str], finished_slot, progress_slot=None):
        """异步暂存文件。"""
        if not files:
            logging.warning("尝试暂存空列表。")
            finished_slot(0, "", "")
            return
        # 注意: 这里的 list[str] 是 Python 3.9+ 的语法。如果你的 Python 版本非常老 (低于 3.9)，
        # 你可能需要 from typing import List 并修改为 files: List[str]
        cmd = ['git', 'add', '--'] + files
        self.execute_command_async(cmd, finished_slot, progress_slot)

    def unstage_files_async(self, files: list[str], finished_slot, progress_slot=None):
        """异步撤销文件的暂存。"""
        if not files:
            logging.warning("尝试撤销暂存空列表。")
            finished_slot(0, "", "")
            return
        # 同上，list[str] 是 Python 3.9+ 语法
        cmd = ['git', 'reset', 'HEAD', '--'] + files
        self.execute_command_async(cmd, finished_slot, progress_slot)

    def get_diff_async(self, file_path: str, staged: bool, finished_slot, progress_slot=None):
         """异步获取文件差异。"""
         if not file_path:
             finished_slot(-8, "", "错误：需要提供文件路径。")
             return
         cmd = ['git', 'diff']
         if staged:
             cmd.append('--staged')
         cmd.extend(['--', file_path])
         self.execute_command_async(cmd, finished_slot, progress_slot)

    def get_log_formatted_async(self, count=50, finished_slot=None, progress_slot=None):
         """异步获取格式化的提交日志。"""
         format_str = "%h%x09%an%x09%ar%x09%s"
         cmd = ['git', 'log', f'--pretty=format:{format_str}', '--graph', f'-n{count}']
         self.execute_command_async(cmd, finished_slot, progress_slot)

    def get_commit_details_async(self, commit_hash: str, finished_slot, progress_slot=None):
        """异步获取提交详情。"""
        if not commit_hash:
            finished_slot(-9, "", "错误：需要提供 Commit Hash。")
            return
        cmd = ['git', 'show', '--stat', commit_hash]
        self.execute_command_async(cmd, finished_slot, progress_slot)