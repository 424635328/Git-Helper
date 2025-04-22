# core/git_handler.py
import subprocess
import os
import sys
import logging
from PyQt6.QtCore import QObject, pyqtSignal, QThread

# GitWorker 类保持不变...
class GitWorker(QObject):
    """在单独线程中执行 Git 命令的工作类"""
    finished = pyqtSignal(int, str, str) # 信号：返回码, stdout, stderr
    progress = pyqtSignal(str)          # 信号：进度信息

    def __init__(self, command_list: list, repo_path: str):
        super().__init__()
        self.command_list = command_list
        self.repo_path = repo_path
        self.process = None

    def run(self):
        """执行 Git 命令"""
        stdout_full = ""
        stderr_full = ""
        return_code = -1

        try:
            self.progress.emit(f"执行: {' '.join(self.command_list)}")
            logging.info(f"在目录 '{self.repo_path}' 中执行: {' '.join(self.command_list)}")

            # 确定启动参数，根据平台隐藏控制台窗口
            startupinfo = None
            if sys.platform == "win32":
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                startupinfo.wShowWindow = subprocess.SW_HIDE # 隐藏命令行窗口

            # 检查命令是否需要特定工作目录 (config --global 不需要)
            cwd = self.repo_path
            if '--global' in self.command_list and 'config' in self.command_list:
                 cwd = None # 全局配置不需要在仓库目录执行

            self.process = subprocess.Popen(
                self.command_list,
                cwd=cwd, # 使用条件 cwd
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding='utf-8', # 尝试使用 utf-8 解码
                errors='replace', # 如果解码失败，用替换字符处理
                startupinfo=startupinfo,
                shell=False # 推荐不使用 shell=True
            )

            stdout_full, stderr_full = self.process.communicate()
            return_code = self.process.returncode

            if return_code == 0:
                self.progress.emit(f"命令成功: {' '.join(self.command_list)}")
                logging.info(f"命令成功 (返回码 {return_code}): {' '.join(self.command_list)}")
            else:
                self.progress.emit(f"命令失败 (返回码 {return_code}): {' '.join(self.command_list)}")
                logging.warning(f"命令失败 (返回码 {return_code}): {' '.join(self.command_list)}\nStderr: {stderr_full}")

        except FileNotFoundError:
            stderr_full = f"错误: 'git' 命令未找到。请确保 Git 已安装并添加到系统 PATH 中。"
            logging.error(stderr_full)
            return_code = -1 # 特殊错误码表示 git 未找到
        except Exception as e:
            stderr_full = f"执行 Git 命令时发生意外错误: {e}\n命令: {' '.join(self.command_list)}"
            logging.error(stderr_full)
            return_code = -2 # 特殊错误码表示其他异常
        finally:
            self.finished.emit(return_code, stdout_full, stderr_full)


class GitHandler:
    """封装 Git 操作"""
    def __init__(self, repo_path: str = None):
        self._repo_path = repo_path or os.getcwd() # 默认为当前工作目录
        self.current_thread = None
        self.current_worker = None
        # 验证仓库路径只在需要时进行，避免启动时报错
        # self._validate_repo() # 移除这里的初始验证

    def set_repo_path(self, path: str):
        """设置并验证新的仓库路径"""
        if os.path.isdir(path):
            self._repo_path = path
            # self._validate_repo() # 验证推迟到 is_valid_repo 调用时
            logging.info(f"仓库路径已设置为: {self._repo_path}")
        else:
            logging.error(f"设置仓库路径失败：路径 '{path}' 不是有效目录。")
            raise ValueError(f"无效的仓库路径: {path}")

    def get_repo_path(self) -> str:
        """获取当前仓库路径"""
        return self._repo_path

    # _validate_repo 方法保持不变...
    def _validate_repo(self):
        """检查当前路径是否为有效的 Git 仓库"""
        git_dir = os.path.join(self._repo_path, '.git')
        if not os.path.isdir(git_dir):
            logging.warning(f"路径 '{self._repo_path}' 可能不是一个有效的 Git 仓库 (未找到 .git 目录)。")

    # is_valid_repo 方法保持不变...
    def is_valid_repo(self) -> bool:
        """检查当前设置的路径是否是有效的 Git 仓库"""
        if not self._repo_path or not os.path.isdir(self._repo_path):
             return False
        git_dir = os.path.join(self._repo_path, '.git')
        is_valid = os.path.isdir(git_dir)
        if not is_valid:
             self._validate_repo() # 如果无效，记录警告日志
        return is_valid

    # execute_command_async 方法稍作修改，处理全局命令
    def execute_command_async(self, command: list, finished_slot, progress_slot=None):
        """
        异步执行 Git 命令。
        """
        # 对非全局命令检查仓库有效性
        is_global_cmd = '--global' in command and 'config' in command
        if not is_global_cmd and not self.is_valid_repo():
             # 直接调用 finished_slot 传递错误信息
            finished_slot(-3, "", f"错误：当前路径 '{self._repo_path}' 不是有效的 Git 仓库。请先选择正确的仓库目录。")
            return

        # 创建工作线程和工作对象 (这部分逻辑不变)
        self.current_thread = QThread()
        # 注意：这里传递 self._repo_path，但 GitWorker 内部会判断是否使用它作为 cwd
        self.current_worker = GitWorker(command, self._repo_path)
        self.current_worker.moveToThread(self.current_thread)

        # 连接信号
        self.current_worker.finished.connect(finished_slot)
        if progress_slot:
            self.current_worker.progress.connect(progress_slot)

        # 清理工作
        self.current_worker.finished.connect(self.current_thread.quit)
        self.current_worker.finished.connect(self.current_worker.deleteLater)
        self.current_thread.finished.connect(self.current_thread.deleteLater)

        # 启动线程
        self.current_thread.started.connect(self.current_worker.run)
        self.current_thread.start()


    # --- 常用命令便捷方法 (添加新的) ---

    # get_status_async, add_async, commit_async, pull_async, push_async, get_current_branch_async 保持不变...
    def get_status_async(self, finished_slot, progress_slot=None):
        self.execute_command_async(['git', 'status'], finished_slot, progress_slot)

    def add_async(self, files: list[str] | str, finished_slot, progress_slot=None):
        if isinstance(files, str):
            cmd = ['git', 'add', files]
        elif isinstance(files, list):
             cmd = ['git', 'add'] + files
        else:
             finished_slot(-4,"", "错误：'add' 命令需要文件路径字符串或列表。")
             return
        if files == '.':
            cmd = ['git', 'add', '.']
        self.execute_command_async(cmd, finished_slot, progress_slot)

    def commit_async(self, message: str, add_all: bool = False, finished_slot=None, progress_slot=None):
        """
        执行 git commit。
        Args:
            message (str): 提交信息.
            add_all (bool): 如果为 True, 使用 -a 参数 (等同于 git commit -am).
            finished_slot: 完成回调.
            progress_slot: 进度回调.
        """
        if not message:
            finished_slot(-5, "", "错误：提交信息不能为空。")
            return
        cmd = ['git', 'commit']
        if add_all:
            cmd.append('-a') # 添加 -a 选项
        cmd.extend(['-m', message])
        self.execute_command_async(cmd, finished_slot, progress_slot)

    def pull_async(self, remote='origin', branch=None, finished_slot=None, progress_slot=None):
        cmd = ['git', 'pull', remote]
        if branch:
            cmd.append(branch)
        self.execute_command_async(cmd, finished_slot, progress_slot)

    def push_async(self, remote='origin', branch=None, finished_slot=None, progress_slot=None):
        cmd = ['git', 'push', remote]
        if branch:
             cmd.append(branch)
        self.execute_command_async(cmd, finished_slot, progress_slot)

    def get_current_branch_async(self, finished_slot, progress_slot=None):
        self.execute_command_async(['git', 'rev-parse', '--abbrev-ref', 'HEAD'], finished_slot, progress_slot)

    # --- 新增的便捷方法 ---
    def list_branches_async(self, finished_slot, progress_slot=None):
        """异步获取本地分支列表 (git branch)"""
        self.execute_command_async(['git', 'branch'], finished_slot, progress_slot)

    def switch_branch_async(self, branch_name: str, finished_slot, progress_slot=None):
        """异步切换分支 (git checkout <branch_name>)"""
        if not branch_name:
            finished_slot(-6, "", "错误：分支名称不能为空。")
            return
        # 可以添加更复杂的检查，如检查分支是否存在，但 checkout 命令本身会报错
        self.execute_command_async(['git', 'checkout', branch_name], finished_slot, progress_slot)

    def list_remotes_async(self, finished_slot, progress_slot=None):
        """异步获取远程仓库列表 (git remote -v)"""
        self.execute_command_async(['git', 'remote', '-v'], finished_slot, progress_slot)

    def set_git_config_async(self, key: str, value: str, is_global: bool, finished_slot, progress_slot=None):
        """异步设置 Git 配置 (git config [--global] <key> <value>)"""
        if not key:
            finished_slot(-7, "", "错误：配置项名称 (key) 不能为空。")
            return
        # value 可以为空字符串，例如 git config user.email ""
        cmd = ['git', 'config']
        if is_global:
            cmd.append('--global')
        cmd.extend([key, value])
        # 注意：全局配置命令不需要仓库路径，execute_command_async 需要处理这种情况
        self.execute_command_async(cmd, finished_slot, progress_slot)

# --- (可选) 添加自定义异常 ---
# class GitCommandError(Exception):
#     def __init__(self, message, return_code, stderr):
#         super().__init__(message)
#         self.return_code = return_code
#         self.stderr = stderr