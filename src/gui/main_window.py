# main_window.py (修改后)

import sys
import os
import webbrowser
from PyQt6.QtWidgets import (
    QMainWindow, QApplication, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QTextEdit, QLabel, QMenuBar, QMenu, QToolBar,
    QStatusBar, QSplitter, QInputDialog, QMessageBox, QLineEdit,
    QDialog, QDialogButtonBox, QSizePolicy, QStyle
)
# 从 QtGui 导入 QFont
from PyQt6.QtGui import QFont

# 从 QtCore 导入 QThread, pyqtSignal, QTimer, Qt, QObject, QSize (QSize 可能会移到 ui_elements)
from PyQt6.QtCore import QThread, pyqtSignal, QTimer, Qt, QObject, QSize

# 导入 Worker 和 Dialogs
from .git_worker import GitWorker
from .dialogs import CommitMessageDialog, SimpleTextInputDialog

# 导入所有 Git 操作的包装器函数 (保留在 main_window.py 中，因为它们与 MainWindow 的槽函数紧密相关)
from .git_wrappers import (
    wrapper_show_status, wrapper_show_log, wrapper_show_diff,
    wrapper_add_changes, wrapper_commit_changes, wrapper_create_switch_branch,
    wrapper_pull_changes, wrapper_push_branch, wrapper_sync_fork_sequence,
    wrapper_merge_branch, wrapper_rebase_branch, wrapper_manage_stash,
    wrapper_cherry_pick_commit, wrapper_manage_tags, wrapper_manage_remotes,
    wrapper_delete_local_branch, wrapper_delete_remote_branch,
    wrapper_create_pull_request, wrapper_clean_commits,
)

# 导入 Config Manager 函数和全局 config, 以及 run_git_command (保留在 main_window.py)
from src.config_manager import config, check_git_repo_and_origin, complete_config_load, run_git_command

# 从新的文件导入 UI 元素创建类
from .ui_elements import UIElementsCreator


# --- 图标路径定义 (保留，因为可以在 _create_actions 中使用，或者移到 ui_elements) ---
# 如果只在 _create_actions 中使用，可以移到 ui_elements
ICON_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "icons")
def get_icon_path(name):
    path = os.path.join(ICON_DIR, f"{name}.png")
    return path

class MainWindow(QMainWindow):
    open_url_signal = pyqtSignal(str)
    config_loaded_signal = pyqtSignal(bool)

    def __init__(self, project_root, parent=None):
        super().__init__(parent)
        self.project_root = project_root
        # self.setWindowIcon(QIcon.fromTheme("git-gui")) # 尝试设置窗口图标

        self.setWindowTitle("Git Helper GUI")
        self.setGeometry(100, 100, 1000, 750)

        self._action_refs = {} # 字典用于存储 QAction 的引用

        # --- 中心控件和布局 ---
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(5, 5, 5, 5)
        main_layout.setSpacing(5)

        self.splitter = QSplitter(Qt.Orientation.Vertical)
        main_layout.addWidget(self.splitter)

        status_panel = QWidget()
        status_layout = QVBoxLayout(status_panel)
        status_layout.setContentsMargins(0, 0, 0, 0); status_layout.setSpacing(3)
        status_label = QLabel("<b>仓库状态概览</b>"); status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        status_layout.addWidget(status_label)
        self.status_text = QTextEdit(); self.status_text.setReadOnly(True)
        self.status_text.setMaximumHeight(150); self.status_text.setPlaceholderText("点击 '查看状态' 更新...")
        self.status_text.setFont(QFont("Consolas, Courier New, monospace", 9))
        status_layout.addWidget(self.status_text)
        self.splitter.addWidget(status_panel)

        output_panel = QWidget()
        output_layout = QVBoxLayout(output_panel)
        output_layout.setContentsMargins(0, 0, 0, 0); output_layout.setSpacing(3)
        output_label = QLabel("<b>详细输出 & 日志</b>"); output_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        output_layout.addWidget(output_label)
        self.output_text = QTextEdit(); self.output_text.setReadOnly(True)
        self.output_text.setPlaceholderText("Git 命令输出将显示在这里...")
        self.output_text.setFont(QFont("Consolas, Courier New, monospace", 10))
        output_layout.addWidget(self.output_text)
        self.splitter.addWidget(output_panel)

        self.splitter.setSizes([150, 550])

        # --- 状态栏 ---
        self.statusBar = QStatusBar()
        self.setStatusBar(self.statusBar)
        self.statusBar.showMessage("正在初始化...")

        # --- 创建 UI 元素 (菜单栏和工具栏) ---
        # 实例化 UIElementsCreator 并调用其方法
        self.ui_creator = UIElementsCreator(self, self._action_refs)
        self.ui_creator.create_actions()
        self.ui_creator.create_menu_bar()
        self.ui_creator.create_tool_bar()

        # --- Worker 线程 ---
        self.worker_thread = QThread()
        self.git_worker = None

        # --- 连接信号 ---
        self.open_url_signal.connect(self._open_browser)
        self.config_loaded_signal.connect(self._update_ui_after_config_load)
        # 将 Worker 的 open_url_signal 连接到 MainWindow 的槽
        # self._open_url_signal_instance = self.open_url_signal # 备用，直接传递 MainWindow 的信号实例

        # --- 触发初始配置加载 ---
        QTimer.singleShot(100, lambda: self._load_initial_config(self.project_root))

        # --- 初始禁用菜单 ---
        self._set_menus_enabled(False)

    # --- 配置加载逻辑 (保留) ---
    def _load_initial_config(self, path_to_check):
        self.statusBar.showMessage("正在加载配置...")
        self.output_text.setText("-- 正在加载 Git 配置 --")
        self.status_text.setText("")
        self._set_menus_enabled(False)
        is_repo, origin_url, origin_owner, origin_repo, error_msg = check_git_repo_and_origin(path_to_check)
        if not is_repo or error_msg:
            error_display = error_msg or "未知的配置错误。"
            self.output_text.append(f"<span style='color:red; font-weight:bold;'>错误: {error_display}</span>")
            QMessageBox.critical(self, "配置错误", error_display)
            self.config_loaded_signal.emit(False)
            return
        self._prompt_user_for_repo_type(origin_owner, origin_repo)

    def _prompt_user_for_repo_type(self, owner, repo):
        msg_box = QMessageBox(self)
        msg_box.setWindowTitle("确认仓库类型")
        msg_box.setIcon(QMessageBox.Icon.Question)
        msg_box.setText(f"检测到 'origin' 指向: <b>{owner}/{repo}</b><br><br>"
                        "这个仓库是？")
        original_button = msg_box.addButton("主要/原始仓库", QMessageBox.ButtonRole.YesRole)
        fork_button = msg_box.addButton("Fork (来自其他仓库)", QMessageBox.ButtonRole.NoRole)
        msg_box.exec()
        repo_type = None
        if msg_box.clickedButton() == original_button: repo_type = 'original'
        elif msg_box.clickedButton() == fork_button: repo_type = 'fork'
        else:
            self.output_text.append("配置被用户取消。")
            self.statusBar.showMessage("配置已取消。")
            self.config_loaded_signal.emit(False)
            return
        self.output_text.append(f"用户选择类型: {repo_type}")
        success = complete_config_load(repo_type)
        self.config_loaded_signal.emit(success)

    def _update_ui_after_config_load(self, success):
        """根据加载结果更新 UI"""
        self.show_config_info()
        if not success or not config.get("is_git_repo"):
            self.setWindowTitle("Git Helper GUI - 配置失败")
            self.statusBar.showMessage("配置失败，请检查输出或重新加载。")
            self._set_menus_enabled(False)
            # 特殊处理文件和设置菜单，仅启用退出、重新加载、显示配置
            if self.menuBar():
                 for menu in self.menuBar().findChildren(QMenu):
                     if menu.title() in ["设置(&T)", "&文件"]:
                         menu.setEnabled(True)
                         for action in menu.actions():
                             # 查找 action 在 _action_refs 中的 key
                             action_ref_key = next((k for k, v in self._action_refs.items() if v == action), None)
                             if action_ref_key in ["exit", "reload", "show_config"]:
                                 action.setEnabled(True)
                             # else: action.setEnabled(False) # 保持其他项禁用
                     else: menu.setEnabled(False)
            return

        # --- 加载成功 ---
        self._set_menus_enabled(True) # 先启用所有（除了特殊处理的）
        repo_type = config.get('repo_type')
        base_repo = config.get('base_repo', 'N/A')
        origin_user = config.get('fork_username', '?')
        origin_repo = config.get('fork_repo_name', 'N/A')
        title = "Git Helper GUI"
        if repo_type == 'original': title += f" - 原始: {base_repo}"
        elif repo_type == 'fork': title += f" - Fork: {origin_user}/{origin_repo} (Base: {base_repo})"
        self.setWindowTitle(title)
        self.statusBar.showMessage("配置加载成功。")

        # --- 根据配置更新特定菜单项状态 ---
        base_repo_ok = base_repo != 'N/A' and "检测失败" not in base_repo
        is_fork = (repo_type == 'fork')

        # 使用 self._action_refs 获取 Action
        sync_action = self._action_refs.get("sync")
        if sync_action:
            sync_enabled = is_fork and base_repo_ok
            sync_action.setEnabled(sync_enabled)
            tooltip = "与 Upstream 同步并推送到 Origin" if sync_enabled else \
                      ("仅适用于已正确配置 Upstream 的 Fork 仓库" if is_fork else "仅适用于 Fork 仓库")
            sync_action.setToolTip(tooltip)

        pr_action = self._action_refs.get("pr")
        if pr_action:
            pr_enabled = is_fork and base_repo_ok
            pr_action.setEnabled(pr_enabled)
            tooltip = "创建到 Base 仓库的 Pull Request" if pr_enabled else "通常需要仓库为已配置 Upstream 的 Fork"
            pr_action.setToolTip(tooltip)

        # 自动执行一次 status 更新状态区
        self.handle_status_action(update_status_area=True)


    def _set_menus_enabled(self, enabled):
        """启用或禁用大部分 Action"""
        exceptions = ["exit", "reload", "show_config"] # Key in _action_refs
        for key, action in self._action_refs.items():
            if key not in exceptions:
                action.setEnabled(enabled)
            else:
                action.setEnabled(True) # 例外项总是可用


    # --- Worker 管理 (保留) ---
    def _start_git_worker(self, task_callable=None, input_data=None, update_status_area=False, **kwargs):
        if not config.get("is_git_repo") or config.get("repo_type") == "未确定" or config.get("repo_type") == "加载中...":
             QMessageBox.warning(self, "配置未就绪", "Git 配置尚未加载或无效。请稍候或尝试重新加载配置。")
             return
        if self.worker_thread.isRunning():
             QMessageBox.warning(self, "操作进行中", "另一个 Git 操作正在运行，请稍候。")
             return

        self.statusBar.showMessage("正在运行 Git 操作...")
        repo_path_to_use = config.get("git_repo_path")
        if not repo_path_to_use:
            print("警告: 未在 config 中找到 git_repo_path, 回退到 project_root")
            repo_path_to_use = self.project_root

        worker_kwargs = kwargs.copy()
        worker_kwargs['update_status_area'] = update_status_area

        # 直接传递 MainWindow 的 open_url_signal 实例
        self.git_worker = GitWorker(
            task_func=task_callable,
            project_root=repo_path_to_use,
            open_url_signal=self.open_url_signal, # <-- 直接传递 MainWindow 的信号
            **worker_kwargs
        )
        self.git_worker.moveToThread(self.worker_thread)
        self.git_worker.finished.connect(self._git_operation_finished)
        self.git_worker.error.connect(self._display_error)
        self.git_worker.output.connect(self._handle_worker_output)
        self.git_worker.command_start.connect(self._handle_command_start)
        self.worker_thread.started.connect(self.git_worker.run)
        # 确保 Worker 线程退出时删除 Worker 对象
        self.git_worker.finished.connect(self.git_worker.deleteLater)
        # 【修改】移除下面这行连接：不再依赖 destroyed 信号来退出线程
        # self.git_worker.destroyed.connect(self.worker_thread.quit)

        self.worker_thread.start()


    def _handle_command_start(self, command_text):
        self.output_text.append(f"\n--- {command_text} ---")
        QTimer.singleShot(0, lambda: self.output_text.verticalScrollBar().setValue(self.output_text.verticalScrollBar().maximum()))

    def _handle_worker_output(self, text):
        worker = self.sender()
        update_status_area = getattr(worker, '_task_kwargs', {}).get('update_status_area', False) if worker else False
        target_widget = self.status_text if update_status_area else self.output_text
        if update_status_area and not hasattr(self, '_status_updated_this_run'):
             target_widget.clear()
             self._status_updated_this_run = True
        target_widget.moveCursor(target_widget.textCursor().MoveOperation.End)
        target_widget.insertPlainText(text)
        target_widget.verticalScrollBar().setValue(target_widget.verticalScrollBar().maximum())

    def _display_error(self, text):
        self.output_text.append(f"<span style='color:red; font-weight:bold;'>错误: {text}</span>")
        self.statusBar.showMessage("操作出错。", 5000)
        self.output_text.verticalScrollBar().setValue(self.output_text.verticalScrollBar().maximum())
        print(f"GUI 错误显示: {text}")
        if hasattr(self, '_status_updated_this_run'): del self._status_updated_this_run

    # 【修改】调整线程等待和清理逻辑
    def _git_operation_finished(self):
        sender_worker = self.sender()
        if sender_worker:
            # 断开信号连接，防止内存泄漏或重复调用
            try: sender_worker.finished.disconnect(self._git_operation_finished)
            except (TypeError, RuntimeError): pass
            try: sender_worker.error.disconnect(self._display_error)
            except (TypeError, RuntimeError): pass
            try: sender_worker.output.disconnect(self._handle_worker_output)
            except (TypeError, RuntimeError): pass
            try: sender_worker.command_start.disconnect(self._handle_command_start)
            except (TypeError, RuntimeError): pass
            # 注意: finished -> deleteLater 的连接仍然有效，由 Qt 自动处理

        # 等待线程自然结束 (run() 方法返回)
        if self.worker_thread.isRunning():
            # 等待最多 5 秒钟
            if not self.worker_thread.wait(5000):
                 # 如果 5 秒后线程仍在运行，说明可能卡住了
                 print("警告: Worker 线程在 5 秒内未能正常退出。强制终止。")
                 self.worker_thread.terminate() # 强制终止 (最后的手段)
                 self.worker_thread.wait() # 等待终止完成

        # 线程已停止（或被终止），Worker 对象将由 deleteLater 清理
        self.git_worker = None # 解除 MainWindow 对 Worker 对象的引用
        self.statusBar.showMessage("就绪")
        if hasattr(self, '_status_updated_this_run'):
            del self._status_updated_this_run


    # --- 菜单动作处理槽函数 (保留，未修改) ---
    # 这些槽函数直接调用 wrapper 函数并启动 worker
    def handle_status_action(self, update_status_area=True):
        self._start_git_worker(task_callable=wrapper_show_status, update_status_area=update_status_area)

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
                  if not ok2: return
                  kwargs['diff_type'] = "commits"; kwargs['commit1'] = commit1; kwargs['commit2'] = commit2 if commit2 else "HEAD"
             else: return
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
         if "检测失败" in default_branch: default_branch = "main"
         branch_name, ok_branch = QInputDialog.getText(self, "拉取更改", f"输入要拉取的分支 (默认: {default_branch}):", text=default_branch)
         if not ok_branch or not branch_name: return
         self._start_git_worker(task_callable=wrapper_pull_changes, remote_name=remote_name, branch_name=branch_name)
    def handle_push_action(self):
         remote_name, ok_remote = QInputDialog.getText(self, "推送分支", "输入远程仓库名称 (例如 origin):", text="origin")
         if not ok_remote or not remote_name: return
         repo_path = config.get("git_repo_path")
         current_local_branch = run_git_command(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=repo_path) if repo_path else None
         branch_name, ok_branch = QInputDialog.getText(self, "推送分支", "输入要推送的本地分支名称:", text=current_local_branch or "")
         if not ok_branch or not branch_name: return
         self._start_git_worker(task_callable=wrapper_push_branch, remote_name=remote_name, branch_name=branch_name)
    def handle_sync_fork_action(self):
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
                 if not ok_msg: return
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
                    tag_message, ok_msg = QInputDialog.getText(self, "创建标签", "输入附注消息:")
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
                 default_upstream = config.get("default_upstream_url", "")
                 if "检测失败" in default_upstream or "N/A" in default_upstream : default_upstream = ""
                 url, ok_url = QInputDialog.getText(self, "设置 Upstream", f"输入 'upstream' 的 URL:", text=default_upstream)
                 if not ok_url or not url: return; kwargs['url'] = url
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
         repo_type = config.get("repo_type")
         fork_username = config.get("fork_username", "你的用户名")
         base_repo = config.get("base_repo", "owner/repo")
         default_branch = config.get("default_branch_name", "main")
         if "检测失败" in default_branch or "未确定" in default_branch: default_branch = "main"
         repo_path = config.get("git_repo_path")

         if repo_type != 'fork' or "检测失败" in base_repo or "N/A" in base_repo or "未确定" in base_repo:
             QMessageBox.warning(self, "操作可能受限", "创建 PR 通常需要仓库为已正确配置 Upstream 的 Fork。请确认后续输入的信息正确。")

         current_local_branch = run_git_command(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=repo_path) if repo_path else None
         source_branch, ok_source = QInputDialog.getText(self, "创建 Pull Request", "输入源分支 (你的分支):", text=current_local_branch or "")
         if not ok_source or not source_branch: return

         target_branch, ok_target = QInputDialog.getText(self, "创建 Pull Request", f"输入目标分支 (在 '{base_repo}' 中，默认: {default_branch}):", text=default_branch)
         if not ok_target or not target_branch: return

         confirm_msg = f"从 '{fork_username}:{source_branch}' 创建 Pull Request 到 '{base_repo}:{target_branch}'？\n"
         if repo_type != 'fork' or "检测失败" in base_repo:
              confirm_msg += "\n警告：仓库配置不完整，请确保以上信息准确无误。\n"
         confirm_msg += "\n将生成 URL 并在浏览器中尝试打开。"

         confirm = QMessageBox.question(self, "确认创建 PR", confirm_msg, QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
         if confirm == QMessageBox.StandardButton.Yes:
             self._start_git_worker(task_callable=wrapper_create_pull_request,
                                    fork_username=fork_username if "检测失败" not in fork_username and "未确定" not in fork_username else "YOUR_USERNAME",
                                    base_repo=base_repo if "检测失败" not in base_repo and "未确定" not in base_repo else "OWNER/REPO",
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


    # --- 其他槽函数 (保留，未修改) ---
    def _open_browser(self, url):
         """在默认浏览器中打开 URL"""
         try:
             webbrowser.open(url)
             self.output_text.append(f"尝试在浏览器中打开 URL: <a href='{url}'>{url}</a>")
             self.output_text.append("如果浏览器未自动打开，请手动复制上面的链接。")
         except Exception as e:
             self.output_text.append(f"<span style='color:red;'>无法自动打开浏览器: {url}<br>错误: {e}</span>")
             self.output_text.append("请手动复制上面的链接并在浏览器中打开。")

    def show_config_info(self):
        """将当前配置状态追加到输出区域"""
        self.output_text.append("\n--- 当前配置信息 ---")
        if config:
             display_order = ["is_git_repo", "repo_type", "git_repo_path", "base_repo", "fork_username", "fork_repo_name", "default_branch_name", "default_upstream_url"]
             displayed_config = {k: config.get(k, "N/A") for k in display_order}
             for key, value in config.items():
                 if key not in displayed_config and not key.startswith("_tmp_"):
                     displayed_config[key] = value

             for key, value in displayed_config.items():
                 value_str = str(value)
                 style = ""
                 if isinstance(value, bool): style = "color: blue;"
                 elif value is None or value_str == "N/A" or "加载中" in value_str or "未确定" in value_str or "检测失败" in value_str or "非Git仓库" in value_str or "Git未找到" in value_str:
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
                # 【修改】使用与 _git_operation_finished 类似的方式尝试停止
                # quit() 对无事件循环的线程效果不佳，直接尝试等待或终止
                if not self.worker_thread.wait(1000): # 尝试等待1秒
                    print("Worker 线程未能正常停止，强制终止。")
                    self.worker_thread.terminate()
                    self.worker_thread.wait() # 等待终止完成
                event.accept()
            else:
                event.ignore()
        else:
            event.accept()