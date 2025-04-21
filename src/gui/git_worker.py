# src/gui/git_worker.py

from PyQt6.QtCore import QObject, QThread, pyqtSignal, QByteArray, QProcess
import subprocess
import sys
import os
import io
import traceback # 用于详细错误日志

class GitWorker(QObject):
    """
    在单独线程中运行 Git 命令或包装器函数的 Worker。
    """
    finished = pyqtSignal() # 操作完成信号（无论成功失败）
    error = pyqtSignal(str)    # 操作失败信号，携带错误信息
    output = pyqtSignal(str)   # 操作成功时的输出信号 (包括 stdout 和 stderr 信息)
    command_start = pyqtSignal(str) # 操作开始信号，携带任务/命令描述

    def __init__(self, command_list=None, cwd=None, input_data=None, task_func=None, project_root=None, open_url_signal=None, *args, **kwargs):
        super().__init__()
        # self._command_list = command_list # 不再支持直接命令列表，强制使用包装器
        # self._cwd = cwd
        # self._input_data = input_data
        self._task_func = task_func # 包装器函数
        self._task_args = args      # 包装器位置参数 (通常不用)
        self._task_kwargs = kwargs  # 包装器关键字参数 (主要方式)
        self._project_root = project_root # 检测到的仓库路径 (作为 cwd 传递)
        self._open_url_signal_instance = open_url_signal # 主窗口传递的信号实例

        # --- 输入验证 ---
        if not self._task_func:
            # 在构造函数中就引发错误或设置错误状态可能更好
            # 但为了保持 run 的结构，我们让 run 处理它
             print("错误: GitWorker 初始化时未提供 task_func。", file=sys.stderr)


    def run(self):
        """
        在线程中执行任务 (调用包装器函数)。
        确保 finished 信号总是被发射。
        根据包装器返回的 exit_code 决定发射 output 还是 error 信号。
        """
        try:
            if not self._task_func:
                self.error.emit("Worker 未指定要执行的任务函数。")
                self.finished.emit()
                return

            # --- 执行包装器函数 ---
            task_name = getattr(self._task_func, '__name__', '匿名任务')
            self.command_start.emit(f"正在运行任务: {task_name}")
            print(f"\n> 正在运行任务: {task_name}") # 控制台日志

            # 准备传递给包装器的参数
            task_kwargs_with_context = self._task_kwargs.copy()
            task_kwargs_with_context['project_root'] = self._project_root # 传递仓库路径
            if self._open_url_signal_instance:
                 task_kwargs_with_context['open_url_signal'] = self._open_url_signal_instance # 传递信号实例

            # 调用包装器
            out, err, code = self._task_func(*self._task_args, **task_kwargs_with_context)

            # --- 根据退出码处理结果 ---
            if code != 0:
                # --- 操作失败 ---
                error_message = f"操作失败 (代码: {code})。\n"
                # 优先显示 stderr，然后是 stdout (如果它们有助于诊断)
                if err:
                    error_message += f"--- 错误详情 (STDERR) ---\n{err}\n"
                if out: # 有时 stdout 也包含错误信息
                    error_message += f"--- 相关输出 (STDOUT) ---\n{out}\n"
                self.error.emit(error_message.strip()) # 发射 error 信号

            else:
                # --- 操作成功 ---
                # 1. 特殊处理: 创建 Pull Request
                try:
                    from .git_wrappers import wrapper_create_pull_request
                    if self._task_func == wrapper_create_pull_request and out:
                        # 假设 wrapper 成功时返回 URL 在 out 中
                        pr_url = out.strip()
                        if self._open_url_signal_instance:
                            self._open_url_signal_instance.emit(pr_url)
                        # 在 UI 中显示 URL 和提示
                        self.output.emit("Pull Request URL 已生成 (尝试在浏览器中打开):\n")
                        self.output.emit(f"<a href='{pr_url}'>{pr_url}</a>\n")
                        # 对于 PR，不再需要显示原始的 out/err 或成功消息
                        # 直接在此处结束成功处理
                        self.finished.emit() # 别忘了发射 finished
                        return # 结束 run 方法
                except ImportError:
                     pass # 如果导入失败，则按通用逻辑处理

                # 2. 通用成功处理: 发射 stdout (如果存在)
                if out:
                    self.output.emit(out + "\n") # 附加换行

                # 3. 通用成功处理: 发射 stderr (如果存在，标记为信息)
                if err:
                    # 将 stderr 作为普通信息发送到 output
                    self.output.emit(f"--- 信息/进度 (STDERR) ---\n{err}\n")

                # 4. 通用成功处理: 发射最终的成功消息
                success_msg = f"<span style='color:green;'>操作成功完成 (代码: {code})。</span>\n"
                self.output.emit(success_msg)

        except Exception as e:
            # --- 捕获执行过程中的 Python 异常 ---
            error_msg = f"执行任务 '{getattr(self._task_func, '__name__', '未知任务')}' 时发生内部错误: {e}\n"
            error_msg += "------ Traceback ------\n"
            error_msg += traceback.format_exc()
            error_msg += "-----------------------\n"
            self.error.emit(error_msg)
            print(error_msg, file=sys.stderr) # 同时打印到控制台

        finally:
            # --- 确保 finished 信号总是发射 ---
            # print("> Worker finished.") # Debug
            self.finished.emit()

# --- End of src/gui/git_worker.py ---