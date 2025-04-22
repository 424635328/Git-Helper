# ui/main_window.py
import sys
import os
import logging
import shlex
from PyQt6.QtWidgets import (
    QMainWindow, QApplication, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QTextEdit, QLineEdit, QLabel, QListWidget, QListWidgetItem,
    QInputDialog, QMessageBox, QFileDialog, QSplitter, QSizePolicy, QAbstractItemView,
    QStatusBar, QToolBar, QMenu, QDialog, QFormLayout, QDialogButtonBox # QDialog, QFormLayout, QDialogButtonBox 不再直接需要，除非MainWindow内部创建简单对话框
)
from PyQt6.QtGui import QAction, QKeySequence, QShortcut, QColor, QTextCursor, QIcon
from PyQt6.QtCore import Qt, pyqtSlot, QSize, QTimer

# --- MODIFICATION: Import dialogs from the new file ---
from .dialogs import ShortcutDialog, SettingsDialog
# --- END MODIFICATION ---

from core.git_handler import GitHandler
from core.db_handler import DatabaseHandler

# --- REMOVE ShortcutDialog and SettingsDialog class definitions from here ---
# class ShortcutDialog(QDialog): ... (已删除)
# class SettingsDialog(QDialog): ... (已删除)
# --- END REMOVAL ---


class MainWindow(QMainWindow):
    """Git GUI 主窗口"""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("简易 Git GUI 工具")
        self.setGeometry(100, 100, 950, 750)

        self.db_handler = DatabaseHandler()
        self.git_handler = GitHandler()

        self.current_command_sequence = []
        self.shortcuts_map = {}
        self.command_buttons = {}

        self._init_ui()
        self._load_and_register_shortcuts()
        self._update_repo_status()

        logging.info("主窗口初始化完成。")

    # --- _init_ui 方法 ---
    # (这个方法不需要改动，因为它只是使用了 self._add_command_button 等内部方法)
    def _init_ui(self):
        """初始化用户界面 (包含新按钮和调整)"""
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)

        # --- 创建核心 UI 元素 (调整顺序后) ---
        repo_layout = QHBoxLayout()
        self.repo_label = QLabel(f"当前仓库: {self.git_handler.get_repo_path()}")
        self.repo_label.setToolTip("当前操作的 Git 仓库路径")
        repo_layout.addWidget(self.repo_label, 1)
        select_repo_button = QPushButton("选择仓库")
        select_repo_button.setToolTip("选择要操作的 Git 仓库目录")
        select_repo_button.clicked.connect(self._select_repository)
        repo_layout.addWidget(select_repo_button)
        main_layout.addLayout(repo_layout)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        main_layout.addWidget(splitter, 1)

        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        splitter.addWidget(left_panel)

        # --- Git 命令按钮区域 (添加 Commit -am) ---
        command_buttons_layout_1 = QHBoxLayout() # 第一行
        self._add_command_button(command_buttons_layout_1, "Status", "git status", self._add_status)
        self._add_command_button(command_buttons_layout_1, "Add .", "git add .", lambda: self._add_simple_command("git add ."))
        self._add_command_button(command_buttons_layout_1, "Add...", "git add <文件>", self._add_files)

        command_buttons_layout_2 = QHBoxLayout() # 第二行
        self._add_command_button(command_buttons_layout_2, "Commit...", "git commit -m '消息'", self._add_commit)
        self._add_command_button(command_buttons_layout_2, "Commit -a...", "git commit -am '消息' (暂存所有已跟踪文件并提交)", self._add_commit_am) # 新增按钮
        self._add_command_button(command_buttons_layout_2, "Log", "git log --oneline --graph", lambda: self._add_simple_command("git log --oneline --graph"))

        # 更多命令...
        more_commands_layout = QHBoxLayout()
        self._add_command_button(more_commands_layout, "Pull", "git pull", lambda: self._add_simple_command("git pull"))
        self._add_command_button(more_commands_layout, "Push", "git push", lambda: self._add_simple_command("git push"))
        self._add_command_button(more_commands_layout, "Fetch", "git fetch", lambda: self._add_simple_command("git fetch"))

        left_layout.addLayout(command_buttons_layout_1)
        left_layout.addLayout(command_buttons_layout_2)
        left_layout.addLayout(more_commands_layout)

        # 当前命令序列显示
        left_layout.addWidget(QLabel("当前命令序列:"))
        self.sequence_display = QTextEdit()
        self.sequence_display.setReadOnly(True)
        self.sequence_display.setPlaceholderText("点击上方按钮构建命令序列...")
        self.sequence_display.setFixedHeight(100)
        left_layout.addWidget(self.sequence_display)

        # 命令序列操作按钮
        sequence_actions_layout = QHBoxLayout()
        execute_button = QPushButton("执行序列")
        execute_button.setStyleSheet("background-color: lightgreen;")
        execute_button.clicked.connect(self._execute_sequence)
        self.command_buttons['execute'] = execute_button

        clear_button = QPushButton("清空序列")
        clear_button.clicked.connect(self._clear_sequence)
        self.command_buttons['clear'] = clear_button

        save_shortcut_button = QPushButton("保存为快捷键")
        save_shortcut_button.clicked.connect(self._save_shortcut_dialog)
        self.command_buttons['save'] = save_shortcut_button

        sequence_actions_layout.addWidget(execute_button)
        sequence_actions_layout.addWidget(clear_button)
        sequence_actions_layout.addWidget(save_shortcut_button)
        left_layout.addLayout(sequence_actions_layout)

        # 快捷键列表
        left_layout.addWidget(QLabel("已保存的快捷键组合:"))
        self.shortcut_list_widget = QListWidget()
        self.shortcut_list_widget.setToolTip("双击执行，右键删除")
        self.shortcut_list_widget.itemDoubleClicked.connect(self._execute_shortcut_from_list)
        self.shortcut_list_widget.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.shortcut_list_widget.customContextMenuRequested.connect(self._show_shortcut_context_menu)
        left_layout.addWidget(self.shortcut_list_widget)


        # --- 右侧面板：输出和状态 ---
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        splitter.addWidget(right_panel)

        # Git 命令输出区域
        right_layout.addWidget(QLabel("Git 命令输出:"))
        self.output_display = QTextEdit()
        self.output_display.setReadOnly(True)
        self.output_display.setFontFamily("Courier New")
        self.output_display.setPlaceholderText("Git 命令的输出将显示在这里...")
        right_layout.addWidget(self.output_display)

        splitter.setSizes([int(self.width() * 0.4), int(self.width() * 0.6)]) # 调整分割比例

        # --- 状态栏 ---
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("就绪")

        # --- 创建菜单栏和工具栏 ---
        self._create_menu()
        self._create_toolbar() # 工具栏现在也添加新动作

        # --- 使能/禁用 按钮 (放在最后) ---
        # 状态由 _update_repo_status 初始化


    # --- _create_menu 方法 ---
    # (这个方法不需要改动，因为它只是创建 Action 并连接到 self 的方法)
    def _create_menu(self):
        """创建菜单栏 (添加 Git 配置)"""
        menu_bar = self.menuBar()

        # 文件菜单
        file_menu = menu_bar.addMenu("文件(&F)")
        select_repo_action = QAction("选择仓库(&O)...", self)
        select_repo_action.triggered.connect(self._select_repository)
        file_menu.addAction(select_repo_action)

        # --- 新增：Git 配置菜单项 ---
        git_config_action = QAction("Git 全局配置(&G)...", self)
        git_config_action.triggered.connect(self._open_settings_dialog)
        file_menu.addAction(git_config_action)
        # --- 结束新增 ---

        file_menu.addSeparator()

        exit_action = QAction("退出(&X)", self)
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

        # --- 新增：仓库操作菜单 ---
        repo_menu = menu_bar.addMenu("仓库(&R)")
        list_branches_action = QAction("列出分支", self)
        list_branches_action.triggered.connect(self._run_list_branches)
        repo_menu.addAction(list_branches_action)
        self.command_buttons['list_branches_action'] = list_branches_action # 用于启用/禁用

        switch_branch_action = QAction("切换分支(&S)...", self)
        switch_branch_action.triggered.connect(self._run_switch_branch)
        repo_menu.addAction(switch_branch_action)
        self.command_buttons['switch_branch_action'] = switch_branch_action

        repo_menu.addSeparator()

        list_remotes_action = QAction("列出远程仓库", self)
        list_remotes_action.triggered.connect(self._run_list_remotes)
        repo_menu.addAction(list_remotes_action)
        self.command_buttons['list_remotes_action'] = list_remotes_action
        # --- 结束新增 ---


        # 帮助菜单
        help_menu = menu_bar.addMenu("帮助(&H)")
        about_action = QAction("关于(&A)", self)
        about_action.triggered.connect(self._show_about_dialog)
        help_menu.addAction(about_action)


    # --- _create_toolbar 方法 ---
    # (这个方法不需要改动)
    def _create_toolbar(self):
        """创建工具栏 (添加分支和远程操作)"""
        toolbar = QToolBar("主要操作")
        toolbar.setIconSize(QSize(24, 24))
        self.addToolBar(toolbar)

        # 添加已有操作到工具栏
        status_action = QAction("Status", self)
        status_action.triggered.connect(self._run_status)
        toolbar.addAction(status_action)
        self.command_buttons['status_action'] = status_action

        pull_action = QAction("Pull", self)
        pull_action.triggered.connect(self._run_pull)
        toolbar.addAction(pull_action)
        self.command_buttons['pull_action'] = pull_action

        push_action = QAction("Push", self)
        push_action.triggered.connect(self._run_push)
        toolbar.addAction(push_action)
        self.command_buttons['push_action'] = push_action

        toolbar.addSeparator()

        # --- 新增：分支和远程操作到工具栏 ---
        list_branches_action_tb = QAction("分支列表", self)
        list_branches_action_tb.triggered.connect(self._run_list_branches)
        toolbar.addAction(list_branches_action_tb)
        self.command_buttons['list_branches_action_tb'] = list_branches_action_tb

        switch_branch_action_tb = QAction("切换分支", self)
        switch_branch_action_tb.triggered.connect(self._run_switch_branch)
        toolbar.addAction(switch_branch_action_tb)
        self.command_buttons['switch_branch_action_tb'] = switch_branch_action_tb

        list_remotes_action_tb = QAction("远程列表", self)
        list_remotes_action_tb.triggered.connect(self._run_list_remotes)
        toolbar.addAction(list_remotes_action_tb)
        self.command_buttons['list_remotes_action_tb'] = list_remotes_action_tb
        # --- 结束新增 ---

        toolbar.addSeparator()

        clear_output_action = QAction("清空输出", self)
        clear_output_action.triggered.connect(self.output_display.clear)
        toolbar.addAction(clear_output_action)


    # --- _add_command_button 方法 ---
    # (这个方法不需要改动)
    def _add_command_button(self, layout, text, tooltip, slot):
        """辅助函数：添加命令按钮"""
        button = QPushButton(text)
        button.setToolTip(tooltip)
        button.clicked.connect(slot)
        layout.addWidget(button)
        # 使用唯一键，避免与 Action 冲突
        button_key = f"button_{text.lower().replace('...', '').replace(' ', '_')}"
        self.command_buttons[button_key] = button
        return button


    # --- 状态更新和 UI 启用/禁用 方法 ---
    # (_update_repo_status, _update_ui_enable_state, _update_branch_display)
    # (这些方法不需要改动，因为它们操作的是 MainWindow 自身的属性和方法)
    def _update_repo_status(self):
        """更新仓库相关UI元素状态"""
        repo_path = self.git_handler.get_repo_path()
        is_valid = self.git_handler.is_valid_repo() # is_valid_repo 现在更可靠
        display_path = repo_path if len(repo_path) < 60 else f"...{repo_path[-57:]}"
        self.repo_label.setText(f"当前仓库: {display_path}")

        if is_valid:
            self.repo_label.setStyleSheet("")
            self._update_ui_enable_state(True) # 启用相关按钮/动作
            self.status_bar.showMessage(f"当前仓库: {repo_path}", 5000)
            self.git_handler.get_current_branch_async(self._update_branch_display)
        else:
            self.repo_label.setStyleSheet("color: red;")
            self._update_ui_enable_state(False) # 禁用相关按钮/动作
            self.status_bar.showMessage("请选择一个有效的 Git 仓库目录", 0)

    def _update_ui_enable_state(self, enabled: bool):
        """根据是否是有效仓库，启用或禁用UI元素"""
        # 遍历 self.command_buttons 中的所有对象 (按钮和动作)
        for key, item in self.command_buttons.items():
            is_build_button = key in ['button_add...', 'button_commit...', 'button_commit_-a...']
            is_sequence_op = key in ['execute', 'clear', 'save']

            if is_build_button:
                item.setEnabled(True) # 构建按钮总是启用
            elif is_sequence_op:
                item.setEnabled(enabled) # 序列操作依赖仓库状态
            else:
                item.setEnabled(enabled)

        # 快捷键列表也需要有效仓库才能双击执行
        self.shortcut_list_widget.setEnabled(enabled)
        # 更新 QShortcut 对象的状态
        for shortcut_obj in self.shortcuts_map.values():
            shortcut_obj.setEnabled(enabled)

        # 检查不在 command_buttons 中的菜单项
        for action in self.findChildren(QAction):
             if action.text() == "Git 全局配置(&G)...":
                 action.setEnabled(True)
             elif action.text() in ["选择仓库(&O)...", "退出(&X)", "关于(&A)", "清空输出"]:
                 action.setEnabled(True) # 这些也总是启用

    @pyqtSlot(int, str, str)
    def _update_branch_display(self, return_code, stdout, stderr):
        """更新状态栏中的当前分支显示"""
        if return_code == 0 and stdout:
            branch_name = stdout.strip()
            repo_path_short = self.git_handler.get_repo_path()
            if len(repo_path_short) > 40: repo_path_short = f"...{repo_path_short[-37:]}"
            self.status_bar.showMessage(f"分支: {branch_name} | 仓库: {repo_path_short}", 0) # 永久显示
        else:
            # 获取分支失败
             repo_path = self.git_handler.get_repo_path()
             if not repo_path: repo_path = "(未选择)"
             if len(repo_path) > 40: repo_path = f"...{repo_path[-37:]}"
             self.status_bar.showMessage(f"仓库: {repo_path} (无法获取分支)", 0)


    # --- _select_repository 方法 ---
    # (这个方法不需要改动)
    def _select_repository(self):
        """弹出对话框让用户选择 Git 仓库目录"""
        start_path = self.git_handler.get_repo_path()
        if not start_path or not os.path.isdir(start_path):
             start_path = os.path.expanduser("~")

        dir_path = QFileDialog.getExistingDirectory(
            self,
            "选择 Git 仓库目录",
            start_path
        )
        if dir_path:
            try:
                self.output_display.clear()
                self.current_command_sequence = []
                self._update_sequence_display()
                self.git_handler.set_repo_path(dir_path)
                self._update_repo_status()
                logging.info(f"用户选择了新的仓库目录: {dir_path}")
            except ValueError as e:
                QMessageBox.warning(self, "选择仓库失败", str(e))
                logging.error(f"设置仓库路径失败: {e}")
                self._update_repo_status()


    # --- 命令按钮槽函数 ---
    # (_add_simple_command, _add_status, _add_files, _add_commit, _add_commit_am)
    # (这些方法不需要改动)
    def _add_simple_command(self, command_str: str):
        """添加不需要额外输入的简单命令到序列"""
        self.current_command_sequence.append(command_str)
        self._update_sequence_display()
        logging.debug(f"添加命令: {command_str}")

    def _add_status(self):
        self._add_simple_command("git status")

    def _add_files(self):
        """弹出文件对话框让用户选择要 add 的文件/目录"""
        files, ok = QInputDialog.getText(
             self, "添加文件/目录",
            "输入要添加的文件或目录 (用空格分隔, '.' 代表所有):",
            QLineEdit.EchoMode.Normal,
            "." # 默认是 '.'
        )
        if ok and files:
            command_str = f"git add {files.strip()}"
            self.current_command_sequence.append(command_str)
            self._update_sequence_display()
            logging.debug(f"添加命令: {command_str}")


    def _add_commit(self):
        """弹出对话框让用户输入 commit 消息 (用于 git commit -m)"""
        commit_msg, ok = QInputDialog.getText(
            self, "提交更改",
            "输入提交信息 (git commit -m):",
            QLineEdit.EchoMode.Normal
        )
        if ok and commit_msg:
            safe_msg = shlex.quote(commit_msg)
            command_str = f"git commit -m {safe_msg}"
            self.current_command_sequence.append(command_str)
            self._update_sequence_display()
            logging.debug(f"添加命令: {command_str}")
        elif ok and not commit_msg:
             QMessageBox.warning(self, "提交失败", "提交信息不能为空。")

    def _add_commit_am(self):
        """弹出对话框让用户输入 commit 消息 (用于 git commit -am)"""
        commit_msg, ok = QInputDialog.getText(
            self, "暂存并提交",
            "输入提交信息 (git commit -am):\n(暂存所有已跟踪文件的更改)",
            QLineEdit.EchoMode.Normal
        )
        if ok and commit_msg:
            safe_msg = shlex.quote(commit_msg)
            command_str = f"git commit -am {safe_msg}"
            self.current_command_sequence.append(command_str)
            self._update_sequence_display()
            logging.debug(f"添加命令: {command_str}")
        elif ok and not commit_msg:
             QMessageBox.warning(self, "提交失败", "提交信息不能为空。")


    # --- 序列操作槽函数 ---
    # (_update_sequence_display, _clear_sequence, _execute_sequence, _run_command_list_sequentially, _refresh_repo_state_ui, _set_ui_busy, _append_output)
    # (这些方法不需要改动)
    def _update_sequence_display(self):
        """更新命令序列显示区域"""
        self.sequence_display.setText("\n".join(self.current_command_sequence))

    def _clear_sequence(self):
        """清空当前命令序列"""
        self.current_command_sequence = []
        self._update_sequence_display()
        self.status_bar.showMessage("命令序列已清空", 2000)
        logging.info("命令序列已清空。")

    def _execute_sequence(self):
        """执行当前命令序列中的所有命令"""
        if not self.git_handler.is_valid_repo():
            QMessageBox.critical(self, "错误", f"当前目录 '{self.git_handler.get_repo_path()}' 不是有效的 Git 仓库。")
            return

        if not self.current_command_sequence:
            QMessageBox.information(self, "提示", "命令序列为空，无需执行。")
            return

        sequence_to_run = list(self.current_command_sequence)
        self._run_command_list_sequentially(sequence_to_run)

    def _run_command_list_sequentially(self, command_strings: list[str]):
        """按顺序执行命令字符串列表 (核心执行逻辑)"""
        self.output_display.clear()
        self._set_ui_busy(True)

        def execute_next(index):
            if index >= len(command_strings):
                self._append_output("\n✅ --- 所有命令执行完毕 ---", QColor("green"))
                self._set_ui_busy(False)
                self._refresh_repo_state_ui()
                return

            cmd_str = command_strings[index].strip()
            if not cmd_str:
                QTimer.singleShot(0, lambda idx=index + 1: execute_next(idx)) # 跳过空行也用 timer
                # execute_next(index + 1)
                return

            try:
                command_parts = shlex.split(cmd_str)
            except ValueError as e:
                 self._append_output(f"\n❌ 错误: 解析命令 '{cmd_str}' 失败: {e}", QColor("red"))
                 self._append_output("\n--- 执行中止 ---", QColor("red"))
                 self._set_ui_busy(False)
                 return

            if not command_parts or command_parts[0].lower() != 'git':
                 self._append_output(f"\n⚠️ 警告: 跳过非 Git 命令: '{cmd_str}'", QColor("orange"))
                 QTimer.singleShot(0, lambda idx=index + 1: execute_next(idx)) # 跳过也用 timer
                 # execute_next(index + 1)
                 return

            self._append_output(f"\n▶️ 执行: {cmd_str}", QColor("blue"))

            @pyqtSlot(int, str, str)
            def on_command_finished(return_code, stdout, stderr):
                if stdout:
                    self._append_output(f"stdout:\n{stdout.strip()}")
                if stderr:
                    error_color = QColor("red")
                    is_actual_error = "error:" in stderr.lower() or "fatal:" in stderr.lower() or return_code != 0
                    if not is_actual_error and not stdout:
                         error_color = self.palette().color(self.foregroundRole())
                    self._append_output(f"stderr:\n{stderr.strip()}", error_color if is_actual_error else None)

                if return_code == 0:
                    self._append_output(f"✅ 命令成功: '{cmd_str}'", QColor("darkGreen"))
                    QTimer.singleShot(0, lambda idx=index + 1: execute_next(idx))
                else:
                    self._append_output(f"\n❌ --- 命令 '{cmd_str}' 失败 (返回码: {return_code})，执行中止 ---", QColor("red"))
                    self._set_ui_busy(False)

            @pyqtSlot(str)
            def on_progress(message):
                self.status_bar.showMessage(message, 3000)

            self.git_handler.execute_command_async(command_parts, on_command_finished, on_progress)

        execute_next(0)

    def _refresh_repo_state_ui(self):
        """执行完命令后刷新仓库状态相关的 UI（状态和分支）"""
        if self.git_handler.is_valid_repo():
            # 直接调用 run_status 可能导致命令堆积，更好的方式是只更新分支
            # self._run_status() # 移除，避免不必要的 status 调用
            self.git_handler.get_current_branch_async(self._update_branch_display) # 只更新分支显示

    def _set_ui_busy(self, busy: bool):
        """设置 UI 为忙碌状态或解除忙碌"""
        # 禁用/启用所有按钮和动作 (除了总是启用的)
        for key, item in self.command_buttons.items():
            item.setEnabled(not busy)

        self.shortcut_list_widget.setEnabled(not busy)
        # 更新 QShortcut 对象的状态
        for shortcut_obj in self.shortcuts_map.values():
            shortcut_obj.setEnabled(not busy) # 快捷键在忙碌时禁用

        # 处理固定启用的 Action
        for action in self.findChildren(QAction):
            if action.text() in ["选择仓库(&O)...", "Git 全局配置(&G)...", "退出(&X)", "关于(&A)", "清空输出"]:
                 action.setEnabled(True) # 这些在忙碌时也可用

        if busy:
            self.status_bar.showMessage("⏳ 正在执行 Git 命令...", 0)
            QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        else:
            QApplication.restoreOverrideCursor()
            # 状态栏消息会在命令完成后或 _refresh_repo_state_ui 中更新


    def _append_output(self, text: str, color: QColor = None):
        """向输出区域追加文本，可选颜色"""
        cursor = self.output_display.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        self.output_display.setTextCursor(cursor)

        original_format = self.output_display.currentCharFormat()
        fmt = QTextEdit().currentCharFormat() # 从干净的格式开始
        if color:
            fmt.setForeground(color)
        else:
             default_color = self.palette().color(self.foregroundRole())
             fmt.setForeground(default_color)

        self.output_display.setCurrentCharFormat(fmt)
        clean_text = text.strip()
        if clean_text:
            self.output_display.insertPlainText(clean_text + "\n")

        self.output_display.setCurrentCharFormat(original_format) # 恢复追加前的格式
        self.output_display.ensureCursorVisible()


    # --- 快捷键处理 ---
    # (_save_shortcut_dialog, _load_and_register_shortcuts, _trigger_saved_shortcut, _execute_shortcut_from_list, _show_shortcut_context_menu, _delete_shortcut)
    # (这些方法不需要改动，因为它们使用了导入的 ShortcutDialog)
    def _save_shortcut_dialog(self):
        """弹出对话框让用户保存当前序列为快捷键"""
        current_sequence_str = "\n".join(self.current_command_sequence)
        if not current_sequence_str:
            QMessageBox.warning(self, "无法保存", "当前命令序列为空。")
            return

        # 使用导入的 ShortcutDialog
        dialog = ShortcutDialog(self, sequence=current_sequence_str)
        if dialog.exec():
            data = dialog.get_data()
            name = data["name"]
            sequence = data["sequence"]
            shortcut_key = data["shortcut_key"]

            if not name or not shortcut_key:
                QMessageBox.warning(self, "保存失败", "快捷键名称和组合不能为空。")
                return

            try:
                qks = QKeySequence.fromString(shortcut_key, QKeySequence.SequenceFormat.NativeText)
                if qks.isEmpty() and shortcut_key.lower() != 'none':
                     raise ValueError("Invalid key sequence string")
            except Exception:
                QMessageBox.warning(self, "保存失败", f"无效的快捷键格式: '{shortcut_key}'. 请使用例如 'Ctrl+S', 'Alt+Shift+X' 等格式。")
                return

            if self.db_handler.save_shortcut(name, sequence, shortcut_key):
                QMessageBox.information(self, "成功", f"快捷键 '{name}' ({shortcut_key}) 已保存。")
                self._load_and_register_shortcuts()
                self._clear_sequence()
            else:
                 QMessageBox.critical(self, "保存失败", f"无法保存快捷键 '{name}'。请检查名称或快捷键是否已存在，或查看日志了解详情。")

    def _load_and_register_shortcuts(self):
        """从数据库加载快捷键并注册 QShortcut"""
        self.shortcut_list_widget.clear()
        for name, shortcut_obj in list(self.shortcuts_map.items()):
            try:
                shortcut_obj.setEnabled(False)
                shortcut_obj.setParent(None)
                shortcut_obj.deleteLater()
            except Exception as e:
                logging.warning(f"移除旧快捷键 '{name}' 时出错: {e}")
            del self.shortcuts_map[name]

        shortcuts = self.db_handler.load_shortcuts()
        is_repo_valid = self.git_handler.is_valid_repo() # 检查一次即可
        for shortcut_data in shortcuts:
            name = shortcut_data['name']
            sequence_str = shortcut_data['sequence']
            key_str = shortcut_data['shortcut_key']

            item = QListWidgetItem(f"{name} ({key_str})")
            item.setData(Qt.ItemDataRole.UserRole, shortcut_data)
            self.shortcut_list_widget.addItem(item)

            try:
                q_key_sequence = QKeySequence.fromString(key_str, QKeySequence.SequenceFormat.NativeText)
                if not q_key_sequence.isEmpty():
                    shortcut = QShortcut(q_key_sequence, self)
                    shortcut.activated.connect(lambda name=name, seq=sequence_str: self._trigger_saved_shortcut(name, seq))
                    shortcut.setContext(Qt.ShortcutContext.WindowShortcut)
                    shortcut.setEnabled(is_repo_valid) # 设置初始状态
                    self.shortcuts_map[name] = shortcut
                    logging.info(f"成功注册快捷键: {name} ({key_str})")
                else:
                     logging.warning(f"无法解析快捷键字符串 '{key_str}' 为有效的 QKeySequence。")
            except Exception as e:
                logging.error(f"注册快捷键 '{name}' ({key_str}) 失败: {e}")

    def _trigger_saved_shortcut(self, name: str, sequence_str: str):
        """由 QShortcut 触发，执行保存的命令序列"""
        if not self.git_handler.is_valid_repo():
            QMessageBox.critical(self, "错误", f"当前目录 '{self.git_handler.get_repo_path()}' 不是有效的 Git 仓库。无法执行快捷键 '{name}'。")
            return

        logging.info(f"快捷键 '{name}' 被触发。")
        self.status_bar.showMessage(f"执行快捷键: {name}", 3000)
        commands = sequence_str.splitlines()
        commands = [cmd for cmd in commands if cmd.strip()]
        if commands:
            self._run_command_list_sequentially(commands)
        else:
            QMessageBox.warning(self, "快捷键无效", f"快捷键 '{name}' 对应的命令序列为空。")

    def _execute_shortcut_from_list(self, item: QListWidgetItem):
        """双击列表项时执行对应的快捷键组合"""
        shortcut_data = item.data(Qt.ItemDataRole.UserRole)
        if shortcut_data:
            name = shortcut_data['name']
            sequence_str = shortcut_data['sequence']
            self._trigger_saved_shortcut(name, sequence_str)

    def _show_shortcut_context_menu(self, pos):
        """显示快捷键列表的右键菜单"""
        item = self.shortcut_list_widget.itemAt(pos)
        if not item:
            return

        menu = QMenu()
        delete_action = QAction("删除", self)
        delete_action.triggered.connect(lambda checked=False, item=item: self._delete_shortcut(item))
        menu.addAction(delete_action)

        menu.exec(self.shortcut_list_widget.mapToGlobal(pos))

    def _delete_shortcut(self, item: QListWidgetItem):
        """删除选中的快捷键"""
        shortcut_data = item.data(Qt.ItemDataRole.UserRole)
        if not shortcut_data: return

        name = shortcut_data['name']
        reply = QMessageBox.question(
            self, "确认删除", f"确定要删除快捷键 '{name}' 吗？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )

        if reply == QMessageBox.StandardButton.Yes:
            if self.db_handler.delete_shortcut(name):
                logging.info(f"用户删除了快捷键 '{name}'。")
                if name in self.shortcuts_map:
                    try:
                        shortcut_obj = self.shortcuts_map[name]
                        shortcut_obj.setEnabled(False)
                        shortcut_obj.setParent(None)
                        shortcut_obj.deleteLater()
                    except Exception as e:
                         logging.warning(f"禁用或删除已删除快捷键 '{name}' 时出错: {e}")
                    del self.shortcuts_map[name]

                self.shortcut_list_widget.takeItem(self.shortcut_list_widget.row(item))
                QMessageBox.information(self, "成功", f"快捷键 '{name}' 已删除。")
            else:
                QMessageBox.critical(self, "删除失败", f"无法从数据库删除快捷键 '{name}'。请查看日志。")


    # --- 单独执行的动作 ---
    # (_run_status, _run_pull, _run_push)
    # (这些方法不需要改动)
    def _run_status(self):
        """执行 git status"""
        if not self.git_handler.is_valid_repo():
             QMessageBox.warning(self, "操作无效", "请先选择一个有效的 Git 仓库。")
             return
        self._run_command_list_sequentially(["git status"])

    def _run_pull(self):
        """执行 git pull"""
        if not self.git_handler.is_valid_repo():
             QMessageBox.warning(self, "操作无效", "请先选择一个有效的 Git 仓库。")
             return
        self._run_command_list_sequentially(["git pull"])

    def _run_push(self):
        """执行 git push"""
        if not self.git_handler.is_valid_repo():
             QMessageBox.warning(self, "操作无效", "请先选择一个有效的 Git 仓库。")
             return
        self._run_command_list_sequentially(["git push"])


    # --- 分支和远程操作的槽函数 ---
    # (_run_list_branches, _run_switch_branch, _run_list_remotes)
    # (这些方法不需要改动)
    def _run_list_branches(self):
        """执行 git branch"""
        if not self.git_handler.is_valid_repo():
             QMessageBox.warning(self, "操作无效", "请先选择一个有效的 Git 仓库。")
             return
        self._run_command_list_sequentially(["git branch"])

    def _run_switch_branch(self):
        """弹出对话框让用户输入要切换的分支名，然后执行 git checkout"""
        if not self.git_handler.is_valid_repo():
             QMessageBox.warning(self, "操作无效", "请先选择一个有效的 Git 仓库。")
             return

        branch_name, ok = QInputDialog.getText(
            self, "切换分支",
            "输入要切换到的分支名称:",
            QLineEdit.EchoMode.Normal
        )
        if ok and branch_name:
            self._run_command_list_sequentially([f"git checkout {shlex.quote(branch_name)}"])
        elif ok and not branch_name:
             QMessageBox.warning(self, "操作取消", "分支名称不能为空。")

    def _run_list_remotes(self):
        """执行 git remote -v"""
        if not self.git_handler.is_valid_repo():
             QMessageBox.warning(self, "操作无效", "请先选择一个有效的 Git 仓库。")
             return
        self._run_command_list_sequentially(["git remote -v"])


    # --- 打开设置对话框的槽函数 ---
    # (这个方法不需要改动，因为它使用了导入的 SettingsDialog)
    def _open_settings_dialog(self):
        """打开 Git 全局配置对话框"""
        # 使用导入的 SettingsDialog
        dialog = SettingsDialog(self)
        if dialog.exec():
            config_data = dialog.get_data()
            commands_to_run = []
            name_val = config_data.get("user.name")
            email_val = config_data.get("user.email")

            if name_val is not None:
                 commands_to_run.append(f"git config --global user.name {shlex.quote(name_val)}")
            if email_val is not None:
                 commands_to_run.append(f"git config --global user.email {shlex.quote(email_val)}")

            if commands_to_run:
                 QMessageBox.information(self, "应用配置", f"将执行以下全局配置命令:\n" + "\n".join(commands_to_run))
                 self._run_command_list_sequentially(commands_to_run)
            else:
                 QMessageBox.information(self, "无更改", "未输入任何配置信息。")


    # --- 其他辅助方法 ---
    # (_show_about_dialog, closeEvent)
    # (这些方法不需要改动)
    def _show_about_dialog(self):
        """显示关于对话框"""
        QMessageBox.about(
            self,
            "关于简易 Git GUI",
            "这是一个使用 PyQt6 构建的简单 Git 图形界面工具。\n\n"
            "版本: 1.1 (添加基础分支/远程/配置功能)\n\n"
            "功能:\n"
            "- 基本 Git 命令按钮 (Status, Add, Commit, Commit -am, Pull, Push, Fetch, Log)\n"
            "- 命令序列组合与执行\n"
            "- 保存/加载带快捷键的命令组合\n"
            "- 异步执行 Git 命令，避免界面冻结\n"
            "- 列出分支/远程仓库\n"
            "- 切换分支 (通过名称输入)\n"
            "- 配置全局 user.name/user.email\n\n"
            "作者: AI"
        )

    def closeEvent(self, event):
        """关闭窗口前的处理"""
        logging.info("应用程序关闭。")
        event.accept()