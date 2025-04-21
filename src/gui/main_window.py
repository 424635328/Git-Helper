# src/gui/main_window.py

import sys
import os
import webbrowser
from PyQt6.QtWidgets import (
    QMainWindow, QApplication, QWidget, QVBoxLayout, QPushButton,
    QTextEdit, QLabel, QMenuBar, QMenu, QToolBar, QStatusBar, QSplitter,
    QInputDialog, QMessageBox, QLineEdit, QDialog, QDialogButtonBox,
)
from PyQt6.QtCore import QThread, pyqtSignal, QTimer, Qt, QObject
from PyQt6.QtGui import QAction, QIcon

# 导入 Worker 和 Dialogs (假设这些文件存在且路径正确)
from .git_worker import GitWorker
from .dialogs import CommitMessageDialog, SimpleTextInputDialog

# 导入所有 Git 操作的包装器函数 (确保它们都定义在 git_wrappers.py 中)
from .git_wrappers import (
    wrapper_show_status, wrapper_show_log, wrapper_show_diff,
    wrapper_add_changes, wrapper_commit_changes, wrapper_create_switch_branch,
    wrapper_pull_changes, wrapper_push_branch, wrapper_sync_fork_sequence,
    wrapper_merge_branch, wrapper_rebase_branch, wrapper_manage_stash,
    wrapper_cherry_pick_commit, wrapper_manage_tags, wrapper_manage_remotes,
    wrapper_delete_local_branch, wrapper_delete_remote_branch,
    wrapper_create_pull_request, wrapper_clean_commits,
)

# 导入新的 Config Manager 函数和全局 config 字典
from src.config_manager import config, check_git_repo_and_origin, complete_config_load

class MainWindow(QMainWindow):
    # 自定义信号
    open_url_signal = pyqtSignal(str)
    config_loaded_signal = pyqtSignal(bool) # True=成功, False=失败

    def __init__(self, project_root, parent=None):
        super().__init__(parent)
        self.project_root = project_root # 存储脚本启动路径，用于初始检查

        self.setWindowTitle("Git Helper GUI")
        self.setGeometry(100, 100, 900, 700) # 稍微调大窗口

        # --- 用于启用/禁用的菜单动作引用 ---
        self.sync_fork_action = None
        self.create_pr_action = None # 添加 Pull Request 动作引用
        # 可以为其他依赖配置的动作添加引用...

        # --- 中心控件和布局 ---
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)

        # 输出文本区域
        self.output_text = QTextEdit()
        self.output_text.setReadOnly(True)
        self.output_text.setPlaceholderText("Git 输出将显示在这里...")
        # 使用等宽字体更适合显示代码/日志
        self.output_text.setStyleSheet("font-family: Consolas, Courier New, monospace; font-size: 10pt;")
        main_layout.addWidget(self.output_text)

        # 状态栏
        self.statusBar = QStatusBar()
        self.setStatusBar(self.statusBar)
        self.statusBar.showMessage("正在初始化...")

        # 创建菜单栏 (此时部分动作可能被禁用)
        self._create_menu_bar()

        # --- Worker 线程 ---
        self.worker_thread = QThread()
        self.git_worker = None # 当前 Worker 实例

        # --- 连接信号 ---
        self.open_url_signal.connect(self._open_browser)
        self.config_loaded_signal.connect(self._update_ui_after_config_load)

        # --- 触发初始配置加载 ---
        # 使用 QTimer.singleShot 确保在事件循环开始后再执行加载
        # 传入 project_root 作为检查起点
        QTimer.singleShot(100, lambda: self._load_initial_config(self.project_root))

    def _create_menu_bar(self):
        """创建应用程序的菜单栏"""
        menu_bar = self.menuBar()

        # 文件菜单
        file_menu = menu_bar.addMenu("&文件")
        exit_action = file_menu.addAction("退出(&X)")
        exit_action.triggered.connect(self.close)

        # 基础操作菜单
        basic_menu = menu_bar.addMenu("基础操作(&B)")
        basic_menu.addAction("查看状态(&S)").triggered.connect(self.handle_status_action)
        basic_menu.addAction("查看日志(&L)...").triggered.connect(self.handle_log_action)
        basic_menu.addAction("查看差异(&D)...").triggered.connect(self.handle_diff_action)
        basic_menu.addAction("添加更改(&A)...").triggered.connect(self.handle_add_action)
        basic_menu.addAction("提交更改(&C)...").triggered.connect(self.handle_commit_action)

        # 分支与同步菜单
        branch_menu = menu_bar.addMenu("分支与同步(&N)")
        branch_menu.addAction("创建/切换分支...").triggered.connect(self.handle_create_switch_branch_action)
        branch_menu.addAction("拉取更改...").triggered.connect(self.handle_pull_action)
        branch_menu.addAction("推送分支...").triggered.connect(self.handle_push_action)
        # 保存 Sync Fork 动作引用，并初始禁用
        self.sync_fork_action = branch_menu.addAction("同步 Fork (Upstream)")
        self.sync_fork_action.triggered.connect(self.handle_sync_fork_action)
        self.sync_fork_action.setEnabled(False)
        self.sync_fork_action.setToolTip("加载配置后可用 (仅限 Fork 仓库)")

        # 高级操作菜单
        advanced_menu = menu_bar.addMenu("高级操作(&V)")
        advanced_menu.addAction("合并分支...").triggered.connect(self.handle_merge_action)
        advanced_menu.addAction("变基分支... (危险!)").triggered.connect(self.handle_rebase_action)
        advanced_menu.addAction("管理储藏...").triggered.connect(self.handle_stash_action)
        advanced_menu.addAction("挑选提交 (Cherry-Pick)...").triggered.connect(self.handle_cherry_pick_action)
        advanced_menu.addAction("管理标签...").triggered.connect(self.handle_manage_tags_action)
        advanced_menu.addAction("管理远程仓库...").triggered.connect(self.handle_manage_remotes_action)
        advanced_menu.addAction("删除本地分支...").triggered.connect(self.handle_delete_local_branch_action)
        advanced_menu.addAction("删除远程分支...").triggered.connect(self.handle_delete_remote_branch_action)
        # 保存 Create PR 动作引用，并初始禁用
        self.create_pr_action = advanced_menu.addAction("创建 Pull Request...")
        self.create_pr_action.triggered.connect(self.handle_create_pull_request_action)
        self.create_pr_action.setEnabled(False)
        self.create_pr_action.setToolTip("加载配置后可用 (通常用于 Fork 仓库)")
        advanced_menu.addAction("清理提交... (极度危险!)").triggered.connect(self.handle_clean_commits_action)

        # 设置菜单
        settings_menu = menu_bar.addMenu("设置(&T)")
        settings_menu.addAction("重新加载配置").triggered.connect(lambda: self._load_initial_config(self.project_root))
        settings_menu.addAction("显示当前配置").triggered.connect(self.show_config_info_action)

    # --- 配置加载逻辑 ---
    def _load_initial_config(self, path_to_check):
        """启动配置加载的第一阶段（非交互式检查）"""
        self.statusBar.showMessage("正在加载配置...")
        self.output_text.append("\n--- 正在加载 Git 配置 ---")
        # 禁用可能触发 Git 命令的菜单，防止在加载完成前操作
        self._set_menus_enabled(False)

        # 调用非交互式检查函数
        is_repo, origin_url, origin_owner, origin_repo, error_msg = check_git_repo_and_origin(path_to_check)

        if not is_repo or error_msg:
            error_display = error_msg or "未知的配置错误。"
            self.output_text.append(f"<span style='color:red; font-weight:bold;'>错误: {error_display}</span>")
            QMessageBox.critical(self, "配置错误", error_display)
            self.config_loaded_signal.emit(False) # 发送失败信号
            # 保留菜单禁用状态
            return

        # 初步检查成功，进行 GUI 交互询问
        self._prompt_user_for_repo_type(origin_owner, origin_repo)

    def _prompt_user_for_repo_type(self, owner, repo):
        """使用 QMessageBox 询问用户仓库类型"""
        msg_box = QMessageBox(self)
        msg_box.setWindowTitle("确认仓库类型")
        msg_box.setIcon(QMessageBox.Icon.Question)
        msg_box.setText(f"检测到 'origin' 指向: <b>{owner}/{repo}</b><br><br>"
                        "这个仓库是？")
        # 使用中文按钮文本
        original_button = msg_box.addButton("主要/原始仓库", QMessageBox.ButtonRole.YesRole)
        fork_button = msg_box.addButton("Fork (来自其他仓库)", QMessageBox.ButtonRole.NoRole)
        # msg_box.setDefaultButton(fork_button) # 可以设置默认按钮

        msg_box.exec() # 显示对话框并等待用户选择

        repo_type = None
        if msg_box.clickedButton() == original_button:
            repo_type = 'original'
        elif msg_box.clickedButton() == fork_button:
            repo_type = 'fork'
        else: # 用户关闭了对话框
            self.output_text.append("配置被用户取消。")
            self.statusBar.showMessage("配置已取消。")
            self.config_loaded_signal.emit(False) # 发送失败/取消信号
            # 保留菜单禁用状态
            return

        # 用户已选择，完成配置加载的第二阶段
        self.output_text.append(f"用户选择类型: {repo_type}")
        success = complete_config_load(repo_type) # 更新全局 config
        self.config_loaded_signal.emit(success) # 发送完成信号

    def _update_ui_after_config_load(self, success):
        """根据加载结果更新 UI (窗口标题、菜单状态等)"""
        self.show_config_info() # 在输出区域显示最终配置

        if not success or not config.get("is_git_repo"):
            self.setWindowTitle("Git Helper GUI - 配置失败")
            self.statusBar.showMessage("配置失败，请检查输出或重新加载。")
            self._set_menus_enabled(False) # 保持菜单禁用
            # 特别启用“重新加载配置”和“退出”
            if self.menuBar():
                for menu in self.menuBar().findChildren(QMenu):
                    if menu.title() == "设置(&T)":
                        for action in menu.actions():
                            if action.text() == "重新加载配置":
                                action.setEnabled(True)
                    elif menu.title() == "&文件":
                         for action in menu.actions():
                             if action.text() == "退出(&X)":
                                action.setEnabled(True)
            return

        # --- 加载成功，更新 UI ---
        self._set_menus_enabled(True) # 启用所有菜单
        repo_type = config.get('repo_type')
        base_repo = config.get('base_repo', 'N/A')
        origin_repo = config.get('fork_repo_name', 'N/A')
        title = "Git Helper GUI"
        if repo_type == 'original':
            title += f" - 原始仓库: {base_repo}"
        elif repo_type == 'fork':
            # 对于 fork，显示 fork 名和 base 名
            fork_user = config.get('fork_username', '?')
            title += f" - Fork: {fork_user}/{origin_repo} (Base: {base_repo})"
        else:
             title += " - 仓库已加载" # 理论上不会到这里
        self.setWindowTitle(title)
        self.statusBar.showMessage("配置加载成功。")

        # --- 根据配置启用/禁用特定菜单项 ---
        base_repo_ok = base_repo != 'N/A' and "检测失败" not in base_repo
        is_fork = (repo_type == 'fork')

        # Sync Fork 菜单项
        if self.sync_fork_action:
            sync_enabled = is_fork and base_repo_ok
            self.sync_fork_action.setEnabled(sync_enabled)
            if not sync_enabled:
                tooltip = "仅适用于已正确配置 Upstream 的 Fork 仓库" if is_fork else "仅适用于 Fork 仓库"
                self.sync_fork_action.setToolTip(tooltip)
            else:
                self.sync_fork_action.setToolTip("与 Upstream 同步并推送到 Origin")

        # Create Pull Request 菜单项
        if self.create_pr_action:
            # 通常 PR 也是基于 Fork 流程，且需要知道 base repo
            pr_enabled = is_fork and base_repo_ok
            self.create_pr_action.setEnabled(pr_enabled)
            if not pr_enabled:
                 tooltip = "通常需要仓库为 Fork 且已配置 Upstream"
                 self.create_pr_action.setToolTip(tooltip)
            else:
                 self.create_pr_action.setToolTip("从当前分支创建到 Base 仓库的 Pull Request")

        # 可以根据需要添加其他菜单项的启用/禁用逻辑

    def _set_menus_enabled(self, enabled):
        """启用或禁用所有菜单项（除了 File 和 Settings 下的特定项）"""
        if not self.menuBar(): return
        for menu in self.menuBar().findChildren(QMenu):
            # 保留 File -> Exit 和 Settings -> Reload/Show Config 始终可用
            if menu.title() in ["&文件", "设置(&T)"]:
                for action in menu.actions():
                    if action.text() not in ["退出(&X)", "重新加载配置", "显示当前配置"]:
                        action.setEnabled(enabled)
            else: # 其他菜单整体启用/禁用
                menu.setEnabled(enabled)


    # --- Worker 管理 ---
    def _start_git_worker(self, task_callable=None, command_list=None, input_data=None, **kwargs):
        """启动 GitWorker 线程执行任务"""
        # 检查配置是否就绪
        if not config.get("is_git_repo") or config.get("repo_type") == "未确定":
             QMessageBox.warning(self, "配置未就绪", "Git 配置尚未加载或无效。请稍候或尝试重新加载配置。")
             return

        # 检查是否有任务正在运行
        if self.worker_thread.isRunning():
             QMessageBox.warning(self, "操作进行中", "另一个 Git 操作正在运行，请稍候。")
             return

        self.output_text.append(f"\n--- 启动 Git 操作 ---")
        self.statusBar.showMessage("正在运行 Git 操作...")
        # 滚动到底部
        QTimer.singleShot(0, lambda: self.output_text.verticalScrollBar().setValue(self.output_text.verticalScrollBar().maximum()))

        # 从 config 获取实际的仓库路径作为 cwd
        repo_path_to_use = config.get("_tmp_repo_path") # 加载时存储的路径
        if not repo_path_to_use: # 如果因为某种原因丢失，回退到 project_root
            print("警告: 未在 config 中找到 _tmp_repo_path, 回退到 project_root")
            repo_path_to_use = self.project_root

        # 创建 Worker 实例
        self.git_worker = GitWorker(
            command_list=command_list,
            input_data=input_data,
            task_func=task_callable,
            project_root=repo_path_to_use, # 将实际仓库路径作为 cwd 传递
            open_url_signal=self.open_url_signal,
            # 传递其他从调用者传来的参数给 wrapper 函数
            **kwargs
        )
        self.git_worker.moveToThread(self.worker_thread)

        # 连接信号与槽
        self.git_worker.finished.connect(self._git_operation_finished)
        self.git_worker.error.connect(self._display_error)
        self.git_worker.output.connect(self._append_output)
        self.git_worker.command_start.connect(self._append_output) # 显示正在执行的命令
        self.worker_thread.started.connect(self.git_worker.run)

        # 设置完成后自动清理
        self.git_worker.finished.connect(self.git_worker.deleteLater)
        # 注意：worker_thread 通常不直接 deleteLater，除非应用退出
        # self.worker_thread.finished.connect(self.worker_thread.deleteLater) # 可能导致问题

        # 启动线程
        self.worker_thread.start()
        # 可以在这里禁用某些UI元素
        # self._set_menus_enabled(False) # 禁用菜单直到操作完成

    def _append_output(self, text):
        """线程安全地追加文本到输出区域"""
        # 使用 insertPlainText 避免 QTextEdit 自动添加多余换行
        self.output_text.moveCursor(self.output_text.textCursor().MoveOperation.End)
        self.output_text.insertPlainText(text)
        # 滚动到底部
        self.output_text.verticalScrollBar().setValue(self.output_text.verticalScrollBar().maximum())

    def _display_error(self, text):
        """显示错误信息"""
        self.output_text.append(f"<span style='color:red; font-weight:bold;'>错误: {text}</span>")
        self.statusBar.showMessage("操作出错。", 5000) # 显示 5 秒
        self.output_text.verticalScrollBar().setValue(self.output_text.verticalScrollBar().maximum())
        print(f"GUI 错误显示: {text}") # 同时打印到控制台

    def _git_operation_finished(self):
        """Git 操作完成后的清理"""
        sender_worker = self.sender()
        # 安全地断开连接
        if sender_worker:
            try: sender_worker.finished.disconnect(self._git_operation_finished)
            except (TypeError, RuntimeError): pass
            try: sender_worker.error.disconnect(self._display_error)
            except (TypeError, RuntimeError): pass
            try: sender_worker.output.disconnect(self._append_output)
            except (TypeError, RuntimeError): pass
            try: sender_worker.command_start.disconnect(self._append_output)
            except (TypeError, RuntimeError): pass

        # 退出线程
        if self.worker_thread.isRunning():
            self.worker_thread.quit()
            self.worker_thread.wait(1000) # 等待线程正常退出
            if self.worker_thread.isRunning(): # 如果还没退出，强制终止
                print("警告: Worker 线程未能正常退出，强制终止。")
                self.worker_thread.terminate()
                self.worker_thread.wait() # 等待终止完成

        self.git_worker = None # 清除 worker 引用 (deleteLater 会处理对象删除)

        self.output_text.append("\n--- Git 操作完成 ---\n")
        self.statusBar.showMessage("就绪")
        # 滚动到底部
        QTimer.singleShot(0, lambda: self.output_text.verticalScrollBar().setValue(self.output_text.verticalScrollBar().maximum()))
        # 重新启用 UI
        # self._set_menus_enabled(True) # 如果之前禁用了菜单

    # --- 菜单动作处理槽函数 ---
    # (大部分保持不变，确保它们从全局 config 获取所需数据)

    # 基础操作
    def handle_status_action(self): self._start_git_worker(task_callable=wrapper_show_status)
    def handle_log_action(self):
         log_formats = ["简洁 (oneline)", "图形化"]
         log_format_choice, ok = QInputDialog.getItem(self, "选择日志格式", "选择格式:", log_formats, 0, False)
         if ok and log_format_choice:
             format_map = {"简洁 (oneline)": "oneline", "图形化": "graph"}
             self._start_git_worker(task_callable=wrapper_show_log, log_format=format_map[log_format_choice])
    def handle_diff_action(self):
         diff_types = ["工作区 vs 暂存区", "暂存区 vs HEAD", "工作区 vs HEAD", "提交/分支之间..."]
         diff_type_choice, ok = QInputDialog.getItem(self, "选择差异类型", "选择类型:", diff_types, 0, False)
         if ok and diff_type_choice:
             task_callable = wrapper_show_diff; kwargs = {}
             if diff_type_choice == "工作区 vs 暂存区": kwargs['diff_type'] = "unstaged"
             elif diff_type_choice == "暂存区 vs HEAD": kwargs['diff_type'] = "staged"
             elif diff_type_choice == "工作区 vs HEAD": kwargs['diff_type'] = "working_tree_vs_head"
             elif diff_type_choice == "提交/分支之间...":
                  commit1, ok1 = QInputDialog.getText(self, "比较差异", "输入第一个提交/分支:")
                  if not ok1 or not commit1: return
                  commit2, ok2 = QInputDialog.getText(self, "比较差异", "输入第二个提交/分支 (留空则为 HEAD):")
                  if not ok2: return # ok2 为 False 表示取消
                  kwargs['diff_type'] = "commits"; kwargs['commit1'] = commit1; kwargs['commit2'] = commit2 if commit2 else "HEAD"
             else: return # 如果类型选择未匹配
             self._start_git_worker(task_callable=task_callable, **kwargs)
    def handle_add_action(self):
        add_target, ok = QInputDialog.getText(self, "添加更改", "输入要添加的文件路径/模式 ('.' 代表所有):", text=".")
        if ok and add_target: self._start_git_worker(task_callable=wrapper_add_changes, add_target=add_target)
        elif ok and not add_target: QMessageBox.warning(self, "需要输入", "添加目标不能为空。")
    def handle_commit_action(self):
        dialog = CommitMessageDialog(self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            commit_message = dialog.get_message()
            if commit_message: self._start_git_worker(task_callable=wrapper_commit_changes, message=commit_message)
            else: QMessageBox.warning(self, "需要输入", "提交信息不能为空。")

    # 分支与同步
    def handle_create_switch_branch_action(self):
        branch_action_types = ["创建并切换", "切换到现有分支"]
        action_choice, ok = QInputDialog.getItem(self, "分支操作", "选择操作:", branch_action_types, 0, False)
        if ok and action_choice:
             branch_name, ok_name = QInputDialog.getText(self, action_choice, "输入分支名称:")
             if ok_name and branch_name:
                 action_map = {"创建并切换": "create_and_switch", "切换到现有分支": "switch"}
                 self._start_git_worker(task_callable=wrapper_create_switch_branch, action_type=action_map[action_choice], branch_name=branch_name)
             elif ok_name and not branch_name: QMessageBox.warning(self, "需要输入", "分支名称不能为空。")
    def handle_pull_action(self):
         remote_name, ok_remote = QInputDialog.getText(self, "拉取更改", "输入远程仓库名称 (例如 origin):", text="origin")
         if not ok_remote or not remote_name: return
         default_branch = config.get("default_branch_name", "main")
         if "检测失败" in default_branch: default_branch = "main" # 回退
         branch_name, ok_branch = QInputDialog.getText(self, "拉取更改", f"输入要拉取的分支 (默认: {default_branch}):", text=default_branch)
         if not ok_branch or not branch_name: return
         self._start_git_worker(task_callable=wrapper_pull_changes, remote_name=remote_name, branch_name=branch_name)
    def handle_push_action(self):
         remote_name, ok_remote = QInputDialog.getText(self, "推送分支", "输入远程仓库名称 (例如 origin):", text="origin")
         if not ok_remote or not remote_name: return
         # 提示用户输入要推送的本地分支名
         current_local_branch = run_git_command(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=config.get("_tmp_repo_path", self.project_root)) # 尝试获取当前分支
         branch_name, ok_branch = QInputDialog.getText(self, "推送分支", "输入要推送的本地分支名称:", text=current_local_branch or "")
         if not ok_branch or not branch_name: return
         # 可以添加选项询问是否设置上游跟踪 (-u)
         self._start_git_worker(task_callable=wrapper_push_branch, remote_name=remote_name, branch_name=branch_name)
    def handle_sync_fork_action(self):
         # 再次检查 (虽然菜单已处理)
         repo_type = config.get('repo_type')
         base_repo = config.get('base_repo', '')
         if repo_type != 'fork' or "检测失败" in base_repo or not base_repo or base_repo == 'N/A':
              QMessageBox.warning(self, "操作不可用", "同步 Fork 需要仓库为已正确配置 Upstream 的 Fork。")
              return
         default_branch = config.get("default_branch_name", "main")
         if "检测失败" in default_branch: default_branch = "main"
         confirm = QMessageBox.question(self, "确认同步 Fork",
                                        f"这将同步本地 '{default_branch}' 分支与 Upstream ('{base_repo}') 并推送到 Origin。\n"
                                        f"步骤:\n1. 切换到 '{default_branch}'\n2. 从 Upstream 拉取 '{default_branch}'\n3. 推送到 Origin '{default_branch}'\n\n确定继续?",
                                        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
         if confirm == QMessageBox.StandardButton.Yes:
             self._start_git_worker(task_callable=wrapper_sync_fork_sequence, default_branch=default_branch)

    # 高级操作 (保持之前的逻辑，确保从 config 读取数据)
    def handle_merge_action(self):
        branch_to_merge, ok = QInputDialog.getText(self, "合并分支", "输入要合并到当前分支的名称:")
        if ok and branch_to_merge: self._start_git_worker(task_callable=wrapper_merge_branch, branch_to_merge=branch_to_merge)
        elif ok and not branch_to_merge: QMessageBox.warning(self, "需要输入", "要合并的分支名称不能为空。")
    def handle_rebase_action(self):
        QMessageBox.warning(self, "危险操作!", "变基会重写提交历史！不要对已公开推送的分支执行变基！", QMessageBox.StandardButton.Ok)
        onto_branch, ok = QInputDialog.getText(self, "变基分支", "输入目标基础分支 (例如 main):")
        if ok and onto_branch:
            confirm = QMessageBox.question(self, "最终确认！", f"确定要将当前分支变基到 '{onto_branch}' 上吗？\n历史将被重写！", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No)
            if confirm == QMessageBox.StandardButton.Yes: self._start_git_worker(task_callable=wrapper_rebase_branch, onto_branch=onto_branch)
        elif ok and not onto_branch: QMessageBox.warning(self, "需要输入", "基础分支名称不能为空。")
    def handle_stash_action(self):
        stash_actions = ["列表", "创建", "应用", "弹出", "删除"]
        stash_action_choice, ok = QInputDialog.getItem(self, "管理储藏", "选择操作:", stash_actions, 0, False)
        if ok and stash_action_choice:
            action_map = {"列表": "list", "创建": "push", "应用": "apply", "弹出": "pop", "删除": "drop"}
            selected_action = action_map.get(stash_action_choice); kwargs = {"stash_action": selected_action}
            if selected_action in ["apply", "pop", "drop"]:
                stash_ref, ok_ref = QInputDialog.getText(self, f"{stash_action_choice} 储藏", f"输入储藏引用 (例如 stash@{{0}})。应用/弹出时留空为最新:")
                if not ok_ref: return
                if selected_action == "drop" and not stash_ref: QMessageBox.warning(self, "需要输入", "删除操作需要储藏引用。"); return
                kwargs['stash_ref'] = stash_ref
                if selected_action == "drop":
                     confirm_drop = QMessageBox.question(self, "确认删除", f"确定要永久删除储藏 '{stash_ref or '最新'}' 吗?", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
                     if confirm_drop != QMessageBox.StandardButton.Yes: return
            elif selected_action == "push":
                 message, ok_msg = QInputDialog.getText(self, "创建储藏", "输入储藏消息 (可选):")
                 if not ok_msg: return # 允许取消
                 kwargs['message'] = message
            if selected_action: self._start_git_worker(task_callable=wrapper_manage_stash, **kwargs)
    def handle_cherry_pick_action(self):
        commit_hash, ok = QInputDialog.getText(self, "挑选提交", "输入要挑选的提交哈希值:")
        if ok and commit_hash: self._start_git_worker(task_callable=wrapper_cherry_pick_commit, commit_hash=commit_hash)
        elif ok and not commit_hash: QMessageBox.warning(self, "需要输入", "提交哈希值不能为空。")
    def handle_manage_tags_action(self):
        tag_actions = ["列表", "创建", "删除本地", "推送所有", "删除远程"]
        tag_action_choice, ok = QInputDialog.getItem(self, "管理标签", "选择操作:", tag_actions, 0, False)
        if ok and tag_action_choice:
            action_map = {"列表": "list", "创建": "create", "删除本地": "delete_local", "推送所有": "push_all", "删除远程": "delete_remote"}
            selected_action = action_map.get(tag_action_choice); kwargs = {"tag_action": selected_action}
            if selected_action == "create":
                tag_name, ok_name = QInputDialog.getText(self, "创建标签", "输入标签名称 (例如 v1.0):");
                if not ok_name or not tag_name: return; kwargs['tag_name'] = tag_name
                tag_type, ok_type = QInputDialog.getItem(self, "创建标签", "选择类型:", ["附注标签", "轻量标签"], 0, False)
                if not ok_type: return; kwargs['tag_type'] = "annotated" if tag_type == "附注标签" else "lightweight"
                if kwargs['tag_type'] == "annotated":
                    tag_message, ok_msg = QInputDialog.getText(self, "创建标签", "输入附注消息:") # 附注标签消息通常是必需的
                    if not ok_msg or not tag_message: QMessageBox.warning(self, "需要输入", "附注标签需要消息。"); return
                    kwargs['tag_message'] = tag_message
            elif selected_action in ["delete_local", "delete_remote"]:
                tag_name, ok_name = QInputDialog.getText(self, f"{tag_action_choice} 标签", "输入要删除的标签名称:");
                if not ok_name or not tag_name: return; kwargs['tag_name'] = tag_name
                if selected_action == "delete_remote":
                    remote_name, ok_remote = QInputDialog.getText(self, "删除远程标签", "输入远程仓库名称 (例如 origin):", text="origin")
                    if not ok_remote or not remote_name: return; kwargs['remote_name'] = remote_name
                confirm_delete = QMessageBox.question(self, "确认删除", f"确定要删除标签 '{tag_name}' ({'远程' if selected_action == 'delete_remote' else '本地'}) 吗?", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
                if confirm_delete != QMessageBox.StandardButton.Yes: return
            elif selected_action == "push_all":
                 remote_name, ok_remote = QInputDialog.getText(self, "推送所有标签", "输入远程仓库名称 (例如 origin):", text="origin")
                 if not ok_remote or not remote_name: return; kwargs['remote_name'] = remote_name
                 confirm_push = QMessageBox.question(self, "确认推送", f"确定要将所有本地标签推送到 '{remote_name}' 吗?", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
                 if confirm_push != QMessageBox.StandardButton.Yes: return
            if selected_action: self._start_git_worker(task_callable=wrapper_manage_tags, **kwargs)
    def handle_manage_remotes_action(self):
        remote_actions = ["列表", "添加", "移除", "重命名", "设置 Upstream"]
        remote_action_choice, ok = QInputDialog.getItem(self, "管理远程仓库", "选择操作:", remote_actions, 0, False)
        if ok and remote_action_choice:
            action_map = {"列表": "list", "添加": "add", "移除": "remove", "重命名": "rename", "设置 Upstream": "setup_upstream"}
            selected_action = action_map.get(remote_action_choice); kwargs = {"remote_action": selected_action}
            if selected_action == "add":
                name, ok_name = QInputDialog.getText(self, "添加远程仓库", "输入名称:");
                if not ok_name or not name: return;
                url, ok_url = QInputDialog.getText(self, "添加远程仓库", "输入 URL:");
                if not ok_url or not url: return; kwargs['name'] = name; kwargs['url'] = url
            elif selected_action == "remove":
                name, ok_name = QInputDialog.getText(self, "移除远程仓库", "输入要移除的名称:");
                if not ok_name or not name: return; kwargs['name'] = name
                confirm_remove = QMessageBox.question(self, "确认移除", f"确定要移除远程仓库 '{name}' 吗?", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
                if confirm_remove != QMessageBox.StandardButton.Yes: return
            elif selected_action == "rename":
                old_name, ok_old = QInputDialog.getText(self, "重命名远程仓库", "输入当前名称:");
                if not ok_old or not old_name: return;
                new_name, ok_new = QInputDialog.getText(self, "重命名远程仓库", "输入新名称:");
                if not ok_new or not new_name: return; kwargs['old_name'] = old_name; kwargs['new_name'] = new_name
            elif selected_action == "setup_upstream":
                 # 从 config 获取当前 upstream URL 作为默认值，如果无效则为空
                 default_upstream = config.get("default_upstream_url", "")
                 if "检测失败" in default_upstream or "N/A" in default_upstream : default_upstream = ""
                 url, ok_url = QInputDialog.getText(self, "设置 Upstream", f"输入 'upstream' 的 URL:", text=default_upstream)
                 if not ok_url or not url: return; kwargs['url'] = url # Wrapper 会处理 add 或 set-url
            if selected_action: self._start_git_worker(task_callable=wrapper_manage_remotes, **kwargs)
    def handle_delete_local_branch_action(self):
        branch_name, ok = QInputDialog.getText(self, "删除本地分支", "输入要删除的本地分支名称:")
        if ok and branch_name:
             force_delete = QMessageBox.question(self, "删除本地分支", f"删除本地分支 '{branch_name}'。\n是否强制删除 (-D)？（即使未完全合并）", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No | QMessageBox.StandardButton.Cancel, QMessageBox.StandardButton.No)
             if force_delete == QMessageBox.StandardButton.Cancel: return; is_force = (force_delete == QMessageBox.StandardButton.Yes)
             confirm = QMessageBox.question(self, "确认删除", f"确定要{'强制' if is_force else ''}删除本地分支 '{branch_name}' 吗?", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
             if confirm == QMessageBox.StandardButton.Yes: self._start_git_worker(task_callable=wrapper_delete_local_branch, branch_name=branch_name, force=is_force)
        elif ok and not branch_name: QMessageBox.warning(self, "需要输入", "分支名称不能为空。")
    def handle_delete_remote_branch_action(self):
        branch_name, ok = QInputDialog.getText(self, "删除远程分支", "输入要删除的远程分支名称:")
        if not ok or not branch_name: return
        remote_name, ok_remote = QInputDialog.getText(self, "删除远程分支", "输入远程仓库名称 (例如 origin):", text="origin")
        if not ok_remote or not remote_name: return
        confirm = QMessageBox.question(self, "确认删除远程分支", f"确定要从远程仓库 '{remote_name}' 删除分支 '{branch_name}' 吗？\n此操作通常不可逆！", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if confirm == QMessageBox.StandardButton.Yes: self._start_git_worker(task_callable=wrapper_delete_remote_branch, branch_name=branch_name, remote_name=remote_name)
    def handle_create_pull_request_action(self):
         # 再次检查配置
         repo_type = config.get("repo_type")
         fork_username = config.get("fork_username", "你的用户名")
         base_repo = config.get("base_repo", "owner/repo")
         default_branch = config.get("default_branch_name", "main")
         if "检测失败" in default_branch or "未确定" in default_branch: default_branch = "main"

         if repo_type != 'fork' or "检测失败" in base_repo or "N/A" in base_repo or "未确定" in base_repo:
             QMessageBox.warning(self, "操作可能受限", "创建 PR 通常需要仓库为已正确配置 Upstream 的 Fork。请确认后续输入的信息正确。")
             # 允许继续，但信息可能不完整

         # 获取源分支 (通常是当前分支)
         current_local_branch = run_git_command(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=config.get("_tmp_repo_path", self.project_root))
         source_branch, ok_source = QInputDialog.getText(self, "创建 Pull Request", "输入源分支 (你的分支):", text=current_local_branch or "")
         if not ok_source or not source_branch: return

         # 获取目标分支 (base repo 的分支)
         target_branch, ok_target = QInputDialog.getText(self, "创建 Pull Request", f"输入目标分支 (在 '{base_repo}' 中，默认: {default_branch}):", text=default_branch)
         if not ok_target or not target_branch: return

         # 构建确认信息
         confirm_msg = f"从 '{fork_username}:{source_branch}' 创建 Pull Request 到 '{base_repo}:{target_branch}'？\n"
         if repo_type != 'fork' or "检测失败" in base_repo:
              confirm_msg += "\n警告：仓库配置不完整，请确保以上信息准确无误。\n"
         confirm_msg += "\n将生成 URL 并在浏览器中尝试打开。"

         confirm = QMessageBox.question(self, "确认创建 PR", confirm_msg, QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
         if confirm == QMessageBox.StandardButton.Yes:
             # 即使配置不完整，也尝试调用 wrapper，让 wrapper 处理或失败
             self._start_git_worker(task_callable=wrapper_create_pull_request,
                                    fork_username=fork_username if "检测失败" not in fork_username else "YOUR_USERNAME",
                                    base_repo=base_repo if "检测失败" not in base_repo else "OWNER/REPO",
                                    source_branch=source_branch,
                                    target_branch=target_branch)
    def handle_clean_commits_action(self):
        QMessageBox.warning(self, "极度危险！", "此操作 (git reset --hard) 将永久丢弃提交和本地更改！\n请确保已备份重要工作。", QMessageBox.StandardButton.Ok)
        num_commits_input, ok = QInputDialog.getText(self, "清理提交 (危险)", "输入要丢弃的最近提交数量:", text="1")
        if ok:
            try:
                num_commits = int(num_commits_input);
                if num_commits < 0: QMessageBox.critical(self, "无效输入", "提交数量不能为负。"); return
                confirm = QMessageBox.question(self, "最终警告！", f"确定要永久丢弃最后 {num_commits} 个提交以及所有本地未提交的更改吗？\n此操作无法撤销！", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No)
                if confirm == QMessageBox.StandardButton.Yes: self._start_git_worker(task_callable=wrapper_clean_commits, num_commits_to_discard=num_commits)
            except ValueError: QMessageBox.critical(self, "无效输入", "请输入有效的数字。")

    # --- 其他槽函数 ---
    def _open_browser(self, url):
         """在默认浏览器中打开 URL"""
         try:
             webbrowser.open(url)
             self.output_text.append(f"尝试在浏览器中打开 URL: <a href='{url}'>{url}</a>") # 让 URL 可点击
             self.output_text.append("如果浏览器未自动打开，请手动复制上面的链接。")
         except Exception as e:
             self.output_text.append(f"<span style='color:red;'>无法自动打开浏览器: {url}<br>错误: {e}</span>")
             self.output_text.append("请手动复制上面的链接并在浏览器中打开。")

    def show_config_info(self):
        """将当前配置状态追加到输出区域"""
        self.output_text.append("\n--- 当前配置信息 ---")
        if config:
             display_order = ["is_git_repo", "repo_type", "base_repo", "fork_username", "fork_repo_name", "default_branch_name", "default_upstream_url"]
             displayed_config = {k: config.get(k, "N/A") for k in display_order}
             for key, value in config.items():
                 if key not in displayed_config and not key.startswith("_tmp_"):
                     displayed_config[key] = value

             for key, value in displayed_config.items():
                 value_str = str(value)
                 style = ""
                 if isinstance(value, bool): style = "color: blue;"
                 elif value is None or value_str == "N/A" or "检测失败" in value_str or "未确定" in value_str or "非Git仓库" in value_str or "Git未找到" in value_str:
                     style = "color: gray; font-style: italic;"
                 self.output_text.append(f"- <b>{key}:</b> <span style='{style}'>{value_str}</span>")
        else:
            self.output_text.append("配置字典为空。")
        self.output_text.append("--------------------------")
        QTimer.singleShot(0, lambda: self.output_text.verticalScrollBar().setValue(self.output_text.verticalScrollBar().maximum()))

    def show_config_info_action(self):
         """用于菜单“显示当前配置”的槽函数"""
         self.show_config_info()

    def closeEvent(self, event):
        """处理程序退出事件，确保 Worker 停止"""
        if self.worker_thread.isRunning():
            reply = QMessageBox.question(self, '退出确认', "Git 操作正在进行中，确定要退出吗？", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No)
            if reply == QMessageBox.StandardButton.Yes:
                print("尝试停止 Worker 线程...")
                self.worker_thread.quit()
                if not self.worker_thread.wait(1000): # 等待 1 秒
                    print("Worker 线程未能正常停止，强制终止。")
                    self.worker_thread.terminate()
                    self.worker_thread.wait() # 等待终止完成
                event.accept() # 接受退出事件
            else:
                event.ignore() # 忽略退出事件
        else:
            event.accept() # 没有任务运行，正常退出

# --- End of src/gui/main_window.py ---