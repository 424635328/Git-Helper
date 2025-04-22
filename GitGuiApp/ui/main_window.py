# ui/main_window.py
import sys
import os
import logging
import shlex
import re
from PyQt6.QtWidgets import (
    QMainWindow, QApplication, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QTextEdit, QLineEdit, QLabel, QListWidget, QListWidgetItem,
    QInputDialog, QMessageBox, QFileDialog, QSplitter, QSizePolicy, QAbstractItemView,
    QStatusBar, QToolBar, QMenu
)
from PyQt6.QtGui import QAction, QKeySequence, QColor, QTextCursor, QIcon # QShortcut 不再直接需要
from PyQt6.QtCore import Qt, pyqtSlot, QSize, QTimer

from .dialogs import ShortcutDialog, SettingsDialog
# --- MODIFICATION: Import ShortcutManager ---
from .shortcut_manager import ShortcutManager
# --- END MODIFICATION ---

from core.git_handler import GitHandler
from core.db_handler import DatabaseHandler

class MainWindow(QMainWindow):
    """Git GUI 主窗口"""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("简易 Git GUI 工具")
        self.setGeometry(100, 100, 950, 750)

        self.db_handler = DatabaseHandler()
        self.git_handler = GitHandler()

        # --- MODIFICATION: Create ShortcutManager instance ---
        self.shortcut_manager = ShortcutManager(self, self.db_handler, self.git_handler)
        # --- END MODIFICATION ---

        self.current_command_sequence = []
        # self.shortcuts_map = {} # REMOVED - Now managed by ShortcutManager
        self.command_buttons = {}

        self._init_ui()
        # --- MODIFICATION: Call manager's method ---
        self.shortcut_manager.load_and_register_shortcuts()
        # --- END MODIFICATION ---
        self._update_repo_status()

        logging.info("主窗口初始化完成。")

    def _init_ui(self):
        """初始化用户界面"""
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)

        # --- UI Elements Creation (No changes needed here related to shortcut refactor) ---
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

        command_buttons_layout_1 = QHBoxLayout()
        self._add_command_button(command_buttons_layout_1, "Status", "git status", self._add_status)
        self._add_command_button(command_buttons_layout_1, "Add .", "git add .", lambda: self._add_simple_command("git add ."))
        self._add_command_button(command_buttons_layout_1, "Add...", "git add <文件>", self._add_files)

        command_buttons_layout_2 = QHBoxLayout()
        self._add_command_button(command_buttons_layout_2, "Commit...", "git commit -m '消息'", self._add_commit)
        self._add_command_button(command_buttons_layout_2, "Commit -a...", "git commit -am '消息' (暂存所有已跟踪文件并提交)", self._add_commit_am)
        self._add_command_button(command_buttons_layout_2, "Log", "git log --oneline --graph", lambda: self._add_simple_command("git log --oneline --graph"))

        more_commands_layout = QHBoxLayout()
        self._add_command_button(more_commands_layout, "Pull", "git pull", lambda: self._add_simple_command("git pull"))
        self._add_command_button(more_commands_layout, "Push", "git push", lambda: self._add_simple_command("git push"))
        self._add_command_button(more_commands_layout, "Fetch", "git fetch", lambda: self._add_simple_command("git fetch"))

        left_layout.addLayout(command_buttons_layout_1)
        left_layout.addLayout(command_buttons_layout_2)
        left_layout.addLayout(more_commands_layout)

        left_layout.addWidget(QLabel("当前命令序列:"))
        self.sequence_display = QTextEdit()
        self.sequence_display.setReadOnly(True)
        self.sequence_display.setPlaceholderText("点击上方按钮构建命令序列...")
        self.sequence_display.setFixedHeight(100)
        left_layout.addWidget(self.sequence_display)

        sequence_actions_layout = QHBoxLayout()
        execute_button = QPushButton("执行序列")
        execute_button.setStyleSheet("background-color: lightgreen;")
        execute_button.clicked.connect(self._execute_sequence)
        self.command_buttons['execute'] = execute_button

        clear_button = QPushButton("清空序列")
        clear_button.clicked.connect(self._clear_sequence)
        self.command_buttons['clear'] = clear_button

        save_shortcut_button = QPushButton("保存为快捷键")
        # --- MODIFICATION: Connect to manager's method ---
        save_shortcut_button.clicked.connect(self.shortcut_manager.save_shortcut_dialog)
        # --- END MODIFICATION ---
        self.command_buttons['save'] = save_shortcut_button

        sequence_actions_layout.addWidget(execute_button)
        sequence_actions_layout.addWidget(clear_button)
        sequence_actions_layout.addWidget(save_shortcut_button)
        left_layout.addLayout(sequence_actions_layout)

        left_layout.addWidget(QLabel("已保存的快捷键组合:"))
        self.shortcut_list_widget = QListWidget() # This widget is still owned by MainWindow
        self.shortcut_list_widget.setToolTip("双击执行，右键删除")
        # --- MODIFICATION: Connect to manager's methods ---
        self.shortcut_list_widget.itemDoubleClicked.connect(self.shortcut_manager.execute_shortcut_from_list)
        self.shortcut_list_widget.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.shortcut_list_widget.customContextMenuRequested.connect(self.shortcut_manager.show_shortcut_context_menu)
        # --- END MODIFICATION ---
        left_layout.addWidget(self.shortcut_list_widget)

        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        splitter.addWidget(right_panel)

        right_layout.addWidget(QLabel("Git 命令输出:"))
        self.output_display = QTextEdit()
        self.output_display.setReadOnly(True)
        self.output_display.setFontFamily("Courier New")
        self.output_display.setPlaceholderText("Git 命令的输出将显示在这里...")
        right_layout.addWidget(self.output_display)

        splitter.setSizes([int(self.width() * 0.4), int(self.width() * 0.6)])

        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("就绪")

        self._create_menu()
        self._create_toolbar()

        # Initial state update handled by __init__ calling _update_repo_status

    # --- Menu, Toolbar, Button Creation Methods (_create_menu, _create_toolbar, _add_command_button) ---
    # (No changes needed here)
    def _create_menu(self):
        """创建菜单栏"""
        menu_bar = self.menuBar()
        file_menu = menu_bar.addMenu("文件(&F)")
        select_repo_action = QAction("选择仓库(&O)...", self)
        select_repo_action.triggered.connect(self._select_repository)
        file_menu.addAction(select_repo_action)
        git_config_action = QAction("Git 全局配置(&G)...", self)
        git_config_action.triggered.connect(self._open_settings_dialog)
        file_menu.addAction(git_config_action)
        file_menu.addSeparator()
        exit_action = QAction("退出(&X)", self)
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)
        repo_menu = menu_bar.addMenu("仓库(&R)")
        list_branches_action = QAction("列出分支", self)
        list_branches_action.triggered.connect(self._run_list_branches)
        repo_menu.addAction(list_branches_action)
        self.command_buttons['list_branches_action'] = list_branches_action
        switch_branch_action = QAction("切换分支(&S)...", self)
        switch_branch_action.triggered.connect(self._run_switch_branch)
        repo_menu.addAction(switch_branch_action)
        self.command_buttons['switch_branch_action'] = switch_branch_action
        repo_menu.addSeparator()
        list_remotes_action = QAction("列出远程仓库", self)
        list_remotes_action.triggered.connect(self._run_list_remotes)
        repo_menu.addAction(list_remotes_action)
        self.command_buttons['list_remotes_action'] = list_remotes_action
        help_menu = menu_bar.addMenu("帮助(&H)")
        about_action = QAction("关于(&A)", self)
        about_action.triggered.connect(self._show_about_dialog)
        help_menu.addAction(about_action)

    def _create_toolbar(self):
        """创建工具栏"""
        toolbar = QToolBar("主要操作")
        toolbar.setIconSize(QSize(24, 24))
        self.addToolBar(toolbar)
        status_action = QAction("Status", self)
        status_action.triggered.connect(self._run_status); toolbar.addAction(status_action)
        self.command_buttons['status_action'] = status_action
        pull_action = QAction("Pull", self)
        pull_action.triggered.connect(self._run_pull); toolbar.addAction(pull_action)
        self.command_buttons['pull_action'] = pull_action
        push_action = QAction("Push", self)
        push_action.triggered.connect(self._run_push); toolbar.addAction(push_action)
        self.command_buttons['push_action'] = push_action
        toolbar.addSeparator()
        list_branches_action_tb = QAction("分支列表", self)
        list_branches_action_tb.triggered.connect(self._run_list_branches); toolbar.addAction(list_branches_action_tb)
        self.command_buttons['list_branches_action_tb'] = list_branches_action_tb
        switch_branch_action_tb = QAction("切换分支", self)
        switch_branch_action_tb.triggered.connect(self._run_switch_branch); toolbar.addAction(switch_branch_action_tb)
        self.command_buttons['switch_branch_action_tb'] = switch_branch_action_tb
        list_remotes_action_tb = QAction("远程列表", self)
        list_remotes_action_tb.triggered.connect(self._run_list_remotes); toolbar.addAction(list_remotes_action_tb)
        self.command_buttons['list_remotes_action_tb'] = list_remotes_action_tb
        toolbar.addSeparator()
        clear_output_action = QAction("清空输出", self)
        clear_output_action.triggered.connect(self.output_display.clear); toolbar.addAction(clear_output_action)

    def _add_command_button(self, layout, text, tooltip, slot):
        """辅助函数：添加命令按钮"""
        button = QPushButton(text)
        button.setToolTip(tooltip)
        button.clicked.connect(slot)
        layout.addWidget(button)
        button_key = f"button_{text.lower().replace('...', '').replace(' ', '_')}"
        self.command_buttons[button_key] = button
        return button

    # --- 状态更新和 UI 启用/禁用 方法 ---
    def _update_repo_status(self):
        """更新仓库相关UI元素状态"""
        repo_path = self.git_handler.get_repo_path()
        is_valid = self.git_handler.is_valid_repo()
        display_path = repo_path if len(repo_path) < 60 else f"...{repo_path[-57:]}"
        self.repo_label.setText(f"当前仓库: {display_path}")

        if is_valid:
            self.repo_label.setStyleSheet("")
            self._update_ui_enable_state(True)
            self.status_bar.showMessage(f"当前仓库: {repo_path}", 5000)
            self.git_handler.get_current_branch_async(self._update_branch_display)
        else:
            self.repo_label.setStyleSheet("color: red;")
            self._update_ui_enable_state(False)
            self.status_bar.showMessage("请选择一个有效的 Git 仓库目录", 0)

    def _update_ui_enable_state(self, enabled: bool):
        """根据是否是有效仓库，启用或禁用UI元素"""
        for key, item in self.command_buttons.items():
            is_build_button = key in ['button_add...', 'button_commit...', 'button_commit_-a...']
            is_sequence_op = key in ['execute', 'clear', 'save']

            if is_build_button: item.setEnabled(True)
            elif is_sequence_op: item.setEnabled(enabled)
            else: item.setEnabled(enabled)

        self.shortcut_list_widget.setEnabled(enabled)
        # --- MODIFICATION: Call manager's method ---
        self.shortcut_manager.set_shortcuts_enabled(enabled)
        # --- END MODIFICATION ---

        for action in self.findChildren(QAction):
             if action.text() == "Git 全局配置(&G)...": action.setEnabled(True)
             elif action.text() in ["选择仓库(&O)...", "退出(&X)", "关于(&A)", "清空输出"]: action.setEnabled(True)

    @pyqtSlot(int, str, str)
    def _update_branch_display(self, return_code, stdout, stderr):
        """更新状态栏中的当前分支显示"""
        if return_code == 0 and stdout:
            branch_name = stdout.strip()
            repo_path_short = self.git_handler.get_repo_path();
            if len(repo_path_short) > 40: repo_path_short = f"...{repo_path_short[-37:]}"
            self.status_bar.showMessage(f"分支: {branch_name} | 仓库: {repo_path_short}", 0)
        else:
             repo_path = self.git_handler.get_repo_path();
             if not repo_path: repo_path = "(未选择)"
             if len(repo_path) > 40: repo_path = f"...{repo_path[-37:]}"
             self.status_bar.showMessage(f"仓库: {repo_path} (无法获取分支)", 0)

    # --- Repository Selection ---
    def _select_repository(self):
        """弹出对话框让用户选择 Git 仓库目录"""
        start_path = self.git_handler.get_repo_path()
        if not start_path or not os.path.isdir(start_path): start_path = os.path.expanduser("~")
        dir_path = QFileDialog.getExistingDirectory(self, "选择 Git 仓库目录", start_path)
        if dir_path:
            try:
                self.output_display.clear(); self.current_command_sequence = []; self._update_sequence_display()
                self.git_handler.set_repo_path(dir_path); self._update_repo_status()
                logging.info(f"用户选择了新的仓库目录: {dir_path}")
            except ValueError as e:
                QMessageBox.warning(self, "选择仓库失败", str(e)); logging.error(f"设置仓库路径失败: {e}")
                self._update_repo_status()

    # --- Command Button Slots (No changes needed) ---
    def _add_simple_command(self, command_str: str):
        logging.debug(f"添加简单命令到序列列表: {repr(command_str)}")
        self.current_command_sequence.append(command_str)
        self._update_sequence_display()
    def _add_status(self): self._add_simple_command("git status")
    def _add_files(self):
        files, ok = QInputDialog.getText(self,"添加文件/目录","输入要添加的文件或目录 (用空格分隔, '.' 代表所有):",QLineEdit.EchoMode.Normal,".")
        if ok and files:
            command_str = f"git add {files.strip()}"
            logging.debug(f"添加 'add' 命令到序列列表: {repr(command_str)}")
            self.current_command_sequence.append(command_str); self._update_sequence_display()
    def _add_commit(self):
        commit_msg, ok = QInputDialog.getText(self,"提交更改","输入提交信息 (git commit -m):",QLineEdit.EchoMode.Normal)
        if ok and commit_msg:
            safe_msg = shlex.quote(commit_msg); command_str = f"git commit -m {safe_msg}"
            logging.debug(f"添加 'commit' 命令到序列列表: {repr(command_str)}")
            self.current_command_sequence.append(command_str); self._update_sequence_display()
        elif ok and not commit_msg: QMessageBox.warning(self, "提交失败", "提交信息不能为空。")
    def _add_commit_am(self):
        commit_msg, ok = QInputDialog.getText(self,"暂存并提交","输入提交信息 (git commit -am):\n(暂存所有已跟踪文件的更改)",QLineEdit.EchoMode.Normal)
        if ok and commit_msg:
            safe_msg = shlex.quote(commit_msg); command_str = f"git commit -am {safe_msg}"
            logging.debug(f"添加 'commit -am' 命令到序列列表: {repr(command_str)}")
            self.current_command_sequence.append(command_str); self._update_sequence_display()
        elif ok and not commit_msg: QMessageBox.warning(self, "提交失败", "提交信息不能为空。")

    # --- Sequence Operations (No changes needed for _update_sequence_display, _clear_sequence, _execute_sequence) ---
    def _update_sequence_display(self):
        self.sequence_display.setText("\n".join(self.current_command_sequence))
    def _clear_sequence(self):
        self.current_command_sequence = []; self._update_sequence_display()
        self.status_bar.showMessage("命令序列已清空", 2000); logging.info("命令序列已清空。")
    def _execute_sequence(self):
        if not self.git_handler.is_valid_repo():
            QMessageBox.critical(self, "错误", f"当前目录 '{self.git_handler.get_repo_path()}' 不是有效的 Git 仓库。"); return
        if not self.current_command_sequence:
            QMessageBox.information(self, "提示", "命令序列为空，无需执行。"); return
        sequence_to_run = list(self.current_command_sequence)
        logging.info(f"执行当前构建的命令序列: {sequence_to_run}")
        self._run_command_list_sequentially(sequence_to_run)

    # --- Core Command Execution Logic (_run_command_list_sequentially, _refresh_repo_state_ui, _set_ui_busy, _append_output) ---
    # (No changes needed here)
    def _run_command_list_sequentially(self, command_strings: list[str]):
        """按顺序执行命令字符串列表 (核心执行逻辑)"""
        logging.debug(f"进入 _run_command_list_sequentially，命令列表: {command_strings}")
        self.output_display.clear(); self._set_ui_busy(True)
        def execute_next(index):
            if index >= len(command_strings):
                self._append_output("\n✅ --- 所有命令执行完毕 ---", QColor("green"))
                self._set_ui_busy(False); self._refresh_repo_state_ui(); return
            cmd_str = command_strings[index].strip()
            logging.debug(f"Executing command string #{index}: {repr(cmd_str)}")
            if not cmd_str: QTimer.singleShot(0, lambda idx=index + 1: execute_next(idx)); return
            try: command_parts = shlex.split(cmd_str); logging.debug(f"shlex 解析结果: {command_parts}")
            except ValueError as e:
                 self._append_output(f"\n❌ 错误: 解析命令 '{cmd_str}' 失败: {e}", QColor("red"))
                 self._append_output("\n--- 执行中止 ---", QColor("red")); self._set_ui_busy(False); return
            if not command_parts or command_parts[0].lower() != 'git':
                 self._append_output(f"\n⚠️ 警告: 跳过非 Git 命令: '{cmd_str}'", QColor("orange"))
                 QTimer.singleShot(0, lambda idx=index + 1: execute_next(idx)); return
            self._append_output(f"\n▶️ 执行: {' '.join(command_parts)}", QColor("blue"))
            @pyqtSlot(int, str, str)
            def on_command_finished(return_code, stdout, stderr):
                if stdout: self._append_output(f"stdout:\n{stdout.strip()}")
                if stderr: self._append_output(f"stderr:\n{stderr.strip()}", QColor("red"))
                if return_code == 0:
                    self._append_output(f"✅ 命令成功: '{' '.join(command_parts)}'", QColor("darkGreen"))
                    QTimer.singleShot(0, lambda idx=index + 1: execute_next(idx))
                else:
                    failed_cmd_str = ' '.join(command_parts)
                    logging.error(f"命令执行失败! Command: '{failed_cmd_str}', Return Code: {return_code}, Stderr: {stderr.strip()}")
                    self._append_output(f"\n❌ --- 命令 '{failed_cmd_str}' 失败 (返回码: {return_code})，执行中止 ---", QColor("red"))
                    self._set_ui_busy(False)
            @pyqtSlot(str)
            def on_progress(message): self.status_bar.showMessage(message, 3000)
            self.git_handler.execute_command_async(command_parts, on_command_finished, on_progress)
        execute_next(0)

    def _refresh_repo_state_ui(self):
        if self.git_handler.is_valid_repo():
            self.git_handler.get_current_branch_async(self._update_branch_display)

    def _set_ui_busy(self, busy: bool):
        """设置 UI 为忙碌状态或解除忙碌"""
        for key, item in self.command_buttons.items(): item.setEnabled(not busy)
        self.shortcut_list_widget.setEnabled(not busy)
        # --- MODIFICATION: Call manager's method ---
        self.shortcut_manager.set_shortcuts_enabled(not busy) # Shortcuts disabled when busy
        # --- END MODIFICATION ---
        for action in self.findChildren(QAction):
            if action.text() in ["选择仓库(&O)...", "Git 全局配置(&G)...", "退出(&X)", "关于(&A)", "清空输出"]: action.setEnabled(True)
        if busy: self.status_bar.showMessage("⏳ 正在执行 Git 命令...", 0); QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        else: QApplication.restoreOverrideCursor()

    def _append_output(self, text: str, color: QColor = None):
        """向输出区域追加文本，可选颜色"""
        cursor = self.output_display.textCursor(); cursor.movePosition(QTextCursor.MoveOperation.End)
        self.output_display.setTextCursor(cursor); original_format = self.output_display.currentCharFormat()
        fmt = QTextEdit().currentCharFormat()
        if color: fmt.setForeground(color)
        else: fmt.setForeground(self.palette().color(self.foregroundRole()))
        self.output_display.setCurrentCharFormat(fmt); clean_text = text.strip()
        if clean_text: self.output_display.insertPlainText(clean_text + "\n")
        self.output_display.setCurrentCharFormat(original_format); self.output_display.ensureCursorVisible()

    # --- Shortcut Handling Methods (REMOVED - Moved to ShortcutManager) ---
    # def _save_shortcut_dialog(self): ... (REMOVED)
    # def _load_and_register_shortcuts(self): ... (REMOVED)
    # def _trigger_saved_shortcut_data(self, shortcut_data: dict): ... (REMOVED)
    # def _trigger_saved_shortcut(self, name: str, sequence_str: str): ... (REMOVED)
    # def _execute_shortcut_from_list(self, item: QListWidgetItem): ... (REMOVED)
    # def _show_shortcut_context_menu(self, pos): ... (REMOVED)
    # def _delete_shortcut(self, item: QListWidgetItem): ... (REMOVED)

    # --- Core execution logic for shortcuts (Still needed by ShortcutManager) ---
    def _execute_sequence_from_string(self, name: str, sequence_str: str):
        """根据名称和序列字符串执行命令 (包含健壮性分割)"""
        if not self.git_handler.is_valid_repo():
            QMessageBox.critical(self, "错误", f"当前目录 '{self.git_handler.get_repo_path()}' 不是有效的 Git 仓库。无法执行快捷键 '{name}'。"); return
        self.status_bar.showMessage(f"执行快捷键: {name}", 3000)
        commands = []; lines = sequence_str.splitlines(); lines = [line.strip() for line in lines if line.strip()]
        needs_git_split = False
        if len(lines) == 1 and lines[0].count(" git ") > 0: needs_git_split = True
        elif len(lines) > 1 and lines[0].count(" git ") > 0: logging.warning(f"快捷键 '{name}' 的第一行可能包含多个命令，尝试智能分割。"); needs_git_split = True
        if needs_git_split and lines:
            logging.warning(f"快捷键 '{name}' 的序列可能格式错误，尝试按 'git ' 分割: {repr(lines[0])}")
            potential_cmds = ["git " + part for part in lines[0].split(" git ") if part]
            if lines[0].startswith("git ") and potential_cmds and not potential_cmds[0].startswith("git "): potential_cmds[0] = "git " + potential_cmds[0]
            commands.extend([cmd.strip() for cmd in potential_cmds if cmd.strip().startswith("git")])
            if len(lines) > 1: commands.extend(lines[1:])
            logging.info(f"按 'git ' 分割后的命令: {commands}")
        elif lines: commands = lines
        commands = [cmd.strip() for cmd in commands if cmd.strip()]
        if not commands:
            QMessageBox.warning(self, "快捷键无效", f"快捷键 '{name}' 对应的命令序列为空或无法解析。原始序列: {repr(sequence_str)}"); logging.warning(f"快捷键 '{name}' 解析后命令列表为空。原始序列: {repr(sequence_str)}"); return
        if not commands[0].lower().startswith("git"):
             QMessageBox.critical(self, "执行错误", f"快捷键 '{name}' 解析后的第一个命令 '{commands[0]}' 不是有效的 git 命令。请删除并重建此快捷键。原始序列: {repr(sequence_str)}"); logging.error(f"快捷键 '{name}' 解析后第一个命令无效: {commands[0]}. 原始序列: {repr(sequence_str)}"); return
        logging.info(f"最终执行命令列表 for '{name}': {commands}")
        self._run_command_list_sequentially(commands)


    # --- Direct Action Slots (No changes needed) ---
    def _run_status(self):
        if not self.git_handler.is_valid_repo(): QMessageBox.warning(self, "操作无效", "请先选择一个有效的 Git 仓库。"); return
        self._run_command_list_sequentially(["git status"])
    def _run_pull(self):
        if not self.git_handler.is_valid_repo(): QMessageBox.warning(self, "操作无效", "请先选择一个有效的 Git 仓库。"); return
        self._run_command_list_sequentially(["git pull"])
    def _run_push(self):
        if not self.git_handler.is_valid_repo(): QMessageBox.warning(self, "操作无效", "请先选择一个有效的 Git 仓库。"); return
        self._run_command_list_sequentially(["git push"])
    def _run_list_branches(self):
        if not self.git_handler.is_valid_repo(): QMessageBox.warning(self, "操作无效", "请先选择一个有效的 Git 仓库。"); return
        self._run_command_list_sequentially(["git branch"])
    def _run_switch_branch(self):
        if not self.git_handler.is_valid_repo(): QMessageBox.warning(self, "操作无效", "请先选择一个有效的 Git 仓库。"); return
        branch_name, ok = QInputDialog.getText(self,"切换分支","输入要切换到的分支名称:",QLineEdit.EchoMode.Normal)
        if ok and branch_name: self._run_command_list_sequentially([f"git checkout {shlex.quote(branch_name)}"])
        elif ok and not branch_name: QMessageBox.warning(self, "操作取消", "分支名称不能为空。")
    def _run_list_remotes(self):
        if not self.git_handler.is_valid_repo(): QMessageBox.warning(self, "操作无效", "请先选择一个有效的 Git 仓库。"); return
        self._run_command_list_sequentially(["git remote -v"])

    # --- Settings Dialog Slot (No changes needed) ---
    def _open_settings_dialog(self):
        dialog = SettingsDialog(self)
        if dialog.exec():
            config_data = dialog.get_data(); commands_to_run = []
            name_val = config_data.get("user.name"); email_val = config_data.get("user.email")
            if name_val is not None: commands_to_run.append(f"git config --global user.name {shlex.quote(name_val)}")
            if email_val is not None: commands_to_run.append(f"git config --global user.email {shlex.quote(email_val)}")
            if commands_to_run: QMessageBox.information(self, "应用配置", f"将执行以下全局配置命令:\n" + "\n".join(commands_to_run)); self._run_command_list_sequentially(commands_to_run)
            else: QMessageBox.information(self, "无更改", "未输入任何配置信息。")

    # --- Other Helper Methods (No changes needed) ---
    def _show_about_dialog(self):
        QMessageBox.about(self,"关于简易 Git GUI","这是一个使用 PyQt6 构建的简单 Git 图形界面工具。\n\n版本: 1.3 (Refactored Shortcuts)\n\n...") # Update version/notes
    def closeEvent(self, event):
        logging.info("应用程序关闭。"); event.accept()