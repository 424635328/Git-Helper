# core/git_handler.py
import subprocess
import os
import sys
import logging
from PyQt6.QtCore import QObject, pyqtSignal, QThread

# 配置日志记录 (如果需要在此模块中单独配置)
# logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

class GitWorker(QObject):
    """在单独线程中执行 Git 命令或 Shell 命令的工作类"""
    finished = pyqtSignal(int, str, str) # 信号：返回码, stdout, stderr
    progress = pyqtSignal(str)          # 信号：进度信息

    def __init__(self, command_list: list, repo_path: str):
        super().__init__()
        self.command_list = command_list
        self.repo_path = repo_path
        self.process = None
        # 标记是否是 Git 全局配置命令，这类命令不应使用 repo_path 作为 cwd
        self.is_global_git_config = command_list \
                                    and command_list[0].lower() == 'git' \
                                    and '--global' in command_list \
                                    and 'config' in command_list

    def run(self):
        """执行命令"""
        stdout_full = ""
        stderr_full = ""
        return_code = -1 # 默认错误码

        try:
            display_cmd = ' '.join(self.command_list) # 用于日志记录
            self.progress.emit(f"执行: {display_cmd}")

            # 确定工作目录
            cwd = self.repo_path
            if self.is_global_git_config:
                # Git 全局配置不应在特定仓库下执行
                cwd = None
                logging.info(f"执行全局 Git 命令: {display_cmd}")
            elif self.repo_path and os.path.isdir(self.repo_path):
                logging.info(f"在目录 '{self.repo_path}' 中执行: {display_cmd}")
            else:
                # 如果仓库路径无效或未设置，但不是全局 git config，可能仍需执行 (例如 'git --version')
                # 或者是非 git 命令，此时在默认环境执行
                cwd = None # 在当前环境执行
                logging.info(f"在默认环境 (非仓库目录) 执行: {display_cmd}")


            # 确定启动参数，根据平台隐藏控制台窗口 (仅 Windows)
            startupinfo = None
            if sys.platform == "win32":
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                startupinfo.wShowWindow = subprocess.SW_HIDE # 隐藏命令行窗口

            # 使用 Popen 执行命令
            self.process = subprocess.Popen(
                self.command_list,
                cwd=cwd, # 使用确定的工作目录
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding='utf-8', # 尝试使用 utf-8 解码
                errors='replace', # 如果解码失败，用替换字符处理
                startupinfo=startupinfo,
                shell=False # 强烈建议保持 False 以避免安全风险
            )

            # 读取 stdout 和 stderr (communicate 会等待进程结束)
            stdout_full, stderr_full = self.process.communicate()
            return_code = self.process.returncode

            # 日志记录结果
            if return_code == 0:
                self.progress.emit(f"命令成功: {display_cmd}")
                logging.info(f"命令成功 (返回码 {return_code}): {display_cmd}")
                # 可选：记录部分 stdout
                # logging.debug(f"Stdout: {stdout_full[:200]}...") # Log first 200 chars
            else:
                self.progress.emit(f"命令失败 (返回码 {return_code}): {display_cmd}")
                logging.warning(f"命令失败 (返回码 {return_code}): {display_cmd}\nStderr: {stderr_full}")

        except FileNotFoundError:
            # 通常是命令本身 (如 'git' 或 'ls') 未找到
            stderr_full = f"错误: 命令 '{self.command_list[0]}' 未找到。请确保它已安装并添加到系统 PATH 中。"
            logging.error(stderr_full)
            return_code = -1 # 特殊错误码表示命令未找到
        except PermissionError as e:
             stderr_full = f"错误: 没有权限执行命令 '{self.command_list[0]}': {e}"
             logging.error(stderr_full)
             return_code = -3 # 特殊错误码表示权限错误
        except Exception as e:
            # 其他意外错误
            stderr_full = f"执行命令时发生意外错误: {e}\n命令: {display_cmd}"
            logging.exception(f"执行命令时发生意外错误: {display_cmd}") # 使用 exception 记录堆栈信息
            return_code = -2 # 特殊错误码表示其他异常
        finally:
            # 确保 finished 信号总是被发射
            self.finished.emit(return_code, stdout_full, stderr_full)


class GitHandler:
    """封装 Git 和相关 Shell 命令操作"""
    def __init__(self, repo_path: str = None):
        self._repo_path = repo_path or os.getcwd() # 默认为当前工作目录
        self.current_thread = None
        self.current_worker = None
        # 初始时不强制验证路径，推迟到需要时

    def set_repo_path(self, path: str):
        """设置并验证新的仓库路径"""
        if path and os.path.isdir(path):
            self._repo_path = path
            # 验证只记录日志，不在此处抛出异常，允许用户稍后修复
            self._validate_repo()
            logging.info(f"仓库路径已设置为: {self._repo_path}")
        elif not path:
             self._repo_path = None # 允许设置为空路径
             logging.warning("仓库路径被设置为空。")
        else:
            logging.error(f"设置仓库路径失败：路径 '{path}' 不是有效目录。")
            # 不抛出异常，允许UI继续运行并提示用户
            self._repo_path = path # 保留无效路径，让 is_valid_repo() 处理

    def get_repo_path(self) -> str | None:
        """获取当前仓库路径"""
        return self._repo_path

    def _validate_repo(self):
        """检查当前路径是否为有效的 Git 仓库，仅记录日志"""
        if not self._repo_path or not os.path.isdir(self._repo_path):
             logging.warning(f"仓库路径 '{self._repo_path}' 无效或未设置。")
             return
        git_dir = os.path.join(self._repo_path, '.git')
        if not os.path.isdir(git_dir):
            logging.warning(f"路径 '{self._repo_path}' 可能不是一个有效的 Git 仓库 (未找到 .git 目录)。")
        else:
            logging.info(f"路径 '{self._repo_path}' 检查通过，找到 .git 目录。")


    def is_valid_repo(self) -> bool:
        """检查当前设置的路径是否是有效的 Git 仓库目录"""
        if not self._repo_path or not os.path.isdir(self._repo_path):
            return False
        git_dir = os.path.join(self._repo_path, '.git')
        return os.path.isdir(git_dir)

    def execute_command_async(self, command: list, finished_slot, progress_slot=None):
        """
        异步执行命令 (可以是 git 命令或其他 shell 命令)。
        Args:
            command (list): 要执行的命令列表 (例如 ['git', 'status'] 或 ['ls', '-l']).
            finished_slot (callable): 命令完成后调用的槽函数，接收 (return_code, stdout, stderr)。
            progress_slot (callable, optional): 报告进度的槽函数，接收 (message)。
        """
        if not command:
             logging.error("尝试执行空命令列表。")
             # 可以选择调用 finished_slot 报告错误
             # finished_slot(-10, "", "错误：命令列表为空。")
             return

        # 检查仓库有效性，除非是特定的全局git命令
        is_global_git_config = command[0].lower() == 'git' and '--global' in command and 'config' in command

        # 对于非全局git命令，或者需要在仓库上下文执行的命令，检查仓库是否有效
        # 假设非 git 命令也期望在当前选定的仓库目录下执行其效果
        # 注意：有些命令如 'git --version' 可能不需要有效仓库，这里简化处理
        if not is_global_git_config and not self.is_valid_repo():
            # 保持此错误检查，因为用户通常期望非 git 命令也在选定仓库下运行
            error_msg = f"错误：当前路径 '{self._repo_path}' 不是有效的 Git 仓库或未设置。请先选择正确的仓库目录。"
            logging.warning(f"阻止执行命令 '{' '.join(command)}' 因为仓库无效: {self._repo_path}")
            finished_slot(-3, "", error_msg) # 使用特殊返回码 -3 表示仓库无效
            return

        # 创建工作线程和工作对象
        self.current_thread = QThread()
        # GitWorker 现在也处理非 git 命令
        self.current_worker = GitWorker(command, self._repo_path)
        self.current_worker.moveToThread(self.current_thread)

        # 连接信号
        self.current_worker.finished.connect(finished_slot)
        if progress_slot:
            self.current_worker.progress.connect(progress_slot)

        # 连接清理信号 (确保线程和 worker 在完成后能被垃圾回收)
        # 当 worker 完成后，它会发射 finished 信号，触发 quit
        self.current_worker.finished.connect(self.current_thread.quit)
        # 当 worker 完成后，安排删除 worker 对象
        self.current_worker.finished.connect(self.current_worker.deleteLater)
        # 当线程退出后 (quit 被调用)，安排删除线程对象
        self.current_thread.finished.connect(self.current_thread.deleteLater)

        # 启动线程，线程启动后会执行 worker 的 run 方法
        self.current_thread.started.connect(self.current_worker.run)
        self.current_thread.start()

    # --- 提供一些常用 Git 命令的便捷方法 ---

    def get_status_async(self, finished_slot, progress_slot=None):
        self.execute_command_async(['git', 'status'], finished_slot, progress_slot)

    def add_async(self, files: list[str] | str, finished_slot, progress_slot=None):
        cmd = ['git', 'add']
        if isinstance(files, str):
            # 如果是单个字符串，可能包含空格，shlex.split 可以帮助处理
            # 但 git add 本身能处理多数情况，简单起见直接添加
            # 对于 '.' 的特殊情况需要处理
            if files == '.':
                 cmd.append('.')
            else:
                 # 假设用户输入的文件/目录名是正确的，或者由调用者处理引号
                 # 如果需要更安全，应该在调用此方法前处理好文件名列表
                 cmd.append(files) # 简单添加，可能对带空格的文件名有问题
        elif isinstance(files, list):
             cmd.extend(files)
        else:
             finished_slot(-4,"", "错误：'add' 命令需要文件路径字符串或列表。")
             return
        self.execute_command_async(cmd, finished_slot, progress_slot)

    def commit_async(self, message: str, add_all: bool = False, finished_slot=None, progress_slot=None):
        """执行 git commit。"""
        if not message:
            finished_slot(-5, "", "错误：提交信息不能为空。")
            return
        cmd = ['git', 'commit']
        if add_all:
            cmd.append('-a') # 添加 -a 选项
        cmd.extend(['-m', message]) # message 应该已经是安全处理过的 (e.g., shlex.quoted)
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
        # git rev-parse --abbrev-ref HEAD 是获取当前分支较好的方式
        self.execute_command_async(['git', 'rev-parse', '--abbrev-ref', 'HEAD'], finished_slot, progress_slot)

    def list_branches_async(self, finished_slot, progress_slot=None):
        """异步获取本地分支列表 (git branch)"""
        self.execute_command_async(['git', 'branch'], finished_slot, progress_slot)

    def switch_branch_async(self, branch_name: str, finished_slot, progress_slot=None):
        """异步切换分支 (git checkout <branch_name>)"""
        if not branch_name:
            finished_slot(-6, "", "错误：分支名称不能为空。")
            return
        # branch_name 应该已经是安全处理过的 (e.g., shlex.quoted)
        self.execute_command_async(['git', 'checkout', branch_name], finished_slot, progress_slot)

    def list_remotes_async(self, finished_slot, progress_slot=None):
        """异步获取远程仓库列表 (git remote -v)"""
        self.execute_command_async(['git', 'remote', '-v'], finished_slot, progress_slot)

    def set_git_config_async(self, key: str, value: str, is_global: bool, finished_slot, progress_slot=None):
        """异步设置 Git 配置 (git config [--global] <key> <value>)"""
        if not key:
            finished_slot(-7, "", "错误：配置项名称 (key) 不能为空。")
            return
        cmd = ['git', 'config']
        if is_global:
            cmd.append('--global')
        # key 和 value 应该已经是安全处理过的 (e.g., shlex.quoted)
        cmd.extend([key, value])
        self.execute_command_async(cmd, finished_slot, progress_slot)