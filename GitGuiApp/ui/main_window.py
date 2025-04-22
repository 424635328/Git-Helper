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
# --- 修改: 添加 QFont ---
from PyQt6.QtGui import QAction, QKeySequence, QColor, QTextCursor, QIcon, QFont
# --- 修改结束 ---
from PyQt6.QtCore import Qt, pyqtSlot, QSize, QTimer

# --- 导入对话框和快捷键管理器 ---
from .dialogs import ShortcutDialog, SettingsDialog
from .shortcut_manager import ShortcutManager
# --- 导入结束 ---

from core.git_handler import GitHandler
from core.db_handler import DatabaseHandler

class MainWindow(QMainWindow):
    """Git GUI 主窗口"""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("简易 Git GUI 工具 (带命令行)")
        self.setGeometry(100, 100, 950, 800) # 增加高度以容纳命令输入框

        # --- 初始化核心处理程序 ---
        self.db_handler = DatabaseHandler()
        self.git_handler = GitHandler()

        # --- 初始化快捷键管理器 ---
        self.shortcut_manager = ShortcutManager(self, self.db_handler, self.git_handler)

        # --- 状态变量 ---
        self.current_command_sequence = []
        self.command_buttons = {} # 用于管理按钮/动作/输入框的启用状态

        # --- UI 元素占位符 ---
        self.output_display = None
        self.command_input = None
        self.sequence_display = None
        self.shortcut_list_widget = None
        self.repo_label = None
        self.status_bar = None

        # --- 初始化 UI ---
        self._init_ui()

        # --- 加载快捷键 ---
        self.shortcut_manager.load_and_register_shortcuts()

        # --- 设置初始仓库状态 ---
        self._update_repo_status()

        logging.info("主窗口初始化完成。")

    def _init_ui(self):
        """初始化用户界面 (优化命令行风格和布局)"""
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)

        # --- 仓库选择区域 ---
        repo_layout = QHBoxLayout()
        self.repo_label = QLabel(f"当前仓库: {self.git_handler.get_repo_path()}") # 在此处赋值
        self.repo_label.setToolTip("当前操作的 Git 仓库路径")
        repo_layout.addWidget(self.repo_label, 1)
        select_repo_button = QPushButton("选择仓库")
        select_repo_button.setToolTip("选择要操作的 Git 仓库目录")
        select_repo_button.clicked.connect(self._select_repository)
        repo_layout.addWidget(select_repo_button)
        main_layout.addLayout(repo_layout)

        # --- 主分割器 ---
        splitter = QSplitter(Qt.Orientation.Horizontal)
        main_layout.addWidget(splitter, 1)

        # --- 左侧面板 ---
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        splitter.addWidget(left_panel)

        # Git 命令按钮
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

        # 当前命令序列显示
        left_layout.addWidget(QLabel("当前命令序列:"))
        self.sequence_display = QTextEdit() # 在此处赋值
        self.sequence_display.setReadOnly(True)
        self.sequence_display.setPlaceholderText("点击上方按钮构建命令序列...")
        self.sequence_display.setFixedHeight(100)
        left_layout.addWidget(self.sequence_display)

        # 序列操作按钮
        sequence_actions_layout = QHBoxLayout()
        execute_button = QPushButton("执行序列")
        execute_button.setStyleSheet("background-color: lightgreen;")
        execute_button.clicked.connect(self._execute_sequence)
        self.command_buttons['execute'] = execute_button
        clear_button = QPushButton("清空序列")
        clear_button.clicked.connect(self._clear_sequence)
        self.command_buttons['clear'] = clear_button
        save_shortcut_button = QPushButton("保存为快捷键")
        save_shortcut_button.clicked.connect(self.shortcut_manager.save_shortcut_dialog) # 连接到管理器
        self.command_buttons['save'] = save_shortcut_button
        sequence_actions_layout.addWidget(execute_button)
        sequence_actions_layout.addWidget(clear_button)
        sequence_actions_layout.addWidget(save_shortcut_button)
        left_layout.addLayout(sequence_actions_layout)

        # 已保存快捷键列表
        left_layout.addWidget(QLabel("已保存的快捷键组合:"))
        self.shortcut_list_widget = QListWidget() # 在此处赋值
        self.shortcut_list_widget.setToolTip("双击执行，右键删除")
        self.shortcut_list_widget.itemDoubleClicked.connect(self.shortcut_manager.execute_shortcut_from_list) # 连接到管理器
        self.shortcut_list_widget.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.shortcut_list_widget.customContextMenuRequested.connect(self.shortcut_manager.show_shortcut_context_menu) # 连接到管理器
        left_layout.addWidget(self.shortcut_list_widget)


        # --- 右侧面板 (输出区域 + 命令输入) ---
        right_panel = QWidget()
        # --- 修改: 添加布局和边距到右侧面板 ---
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(5, 0, 5, 5) # 添加小边距 (左, 上, 右, 下) - 无上边距
        right_layout.setSpacing(4)                  # 减少此布局中控件间的间距
        # --- 修改结束 ---
        splitter.addWidget(right_panel)

        # Git/命令输出区域
        output_label = QLabel("命令输出:") # 更改变量名以提高清晰度
        self.output_display = QTextEdit() # 在此处赋值
        self.output_display.setReadOnly(True)
        self.output_display.setFontFamily("Courier New") # QTextEdit 有 setFontFamily 方法
        self.output_display.setPlaceholderText("Git 命令和命令行输出将显示在这里...")
        right_layout.addWidget(output_label)
        right_layout.addWidget(self.output_display, 1) # 输出显示区域垂直伸展

        # 命令输入区域
        input_label = QLabel("命令行输入:")
        self.command_input = QLineEdit() # 在此处赋值
        self.command_input.setPlaceholderText("在此输入命令 (例如: git status, ls -l) 然后按 Enter")
        command_font = QFont("Courier New") # 创建 QFont 对象
        # command_font.setPointSize(10) # 可选地调整大小
        self.command_input.setFont(command_font) # 应用字体对象

        # --- 修改: 应用样式表 ---
        command_input_style = """
            QLineEdit {
                background-color: #ffffff; /* 白色背景 (根据主题需要调整) */
                border: 1px solid #abadb3; /* 标准 Windows 风格边框 */
                border-radius: 2px;
                padding: 4px 6px;         /* 略多一点填充 */
                /* font-size: 10pt; */    /* 继承自上面设置的 QFont */
                color: #000000;           /* 确保文本是黑色 */
            }
            QLineEdit:focus {
                border: 1px solid #0078d4; /* 标准 Windows 焦点高亮 */
            }
            QLineEdit::placeholder {
                color: #a0a0a0;           /* 占位符使用浅灰色 */
            }
            QLineEdit:disabled {
                background-color: #f0f0f0; /* 禁用时背景颜色略有不同 */
                color: #a0a0a0;
            }
        """
        self.command_input.setStyleSheet(command_input_style)
        # --- 修改结束 ---

        self.command_input.returnPressed.connect(self._execute_command_from_input) # 连接信号
        self.command_buttons['command_input'] = self.command_input # 添加到字典以管理状态

        right_layout.addWidget(input_label)
        right_layout.addWidget(self.command_input) # 添加到布局，间距已减小

        # 分割器设置
        splitter.setSizes([int(self.width() * 0.4), int(self.width() * 0.6)]) # 必要时调整比例

        # --- 状态栏 ---
        self.status_bar = QStatusBar() # 在此处赋值
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("就绪")

        # --- 菜单和工具栏 ---
        self._create_menu()
        self._create_toolbar()

    def _create_menu(self):
        """创建菜单栏"""
        menu_bar = self.menuBar()
        file_menu = menu_bar.addMenu("文件(&F)")
        select_repo_action = QAction("选择仓库(&O)...", self); select_repo_action.triggered.connect(self._select_repository); file_menu.addAction(select_repo_action)
        git_config_action = QAction("Git 全局配置(&G)...", self); git_config_action.triggered.connect(self._open_settings_dialog); file_menu.addAction(git_config_action)
        file_menu.addSeparator(); exit_action = QAction("退出(&X)", self); exit_action.triggered.connect(self.close); file_menu.addAction(exit_action)
        repo_menu = menu_bar.addMenu("仓库(&R)")
        list_branches_action = QAction("列出分支", self); list_branches_action.triggered.connect(self._run_list_branches); repo_menu.addAction(list_branches_action); self.command_buttons['list_branches_action'] = list_branches_action
        switch_branch_action = QAction("切换分支(&S)...", self); switch_branch_action.triggered.connect(self._run_switch_branch); repo_menu.addAction(switch_branch_action); self.command_buttons['switch_branch_action'] = switch_branch_action
        repo_menu.addSeparator()
        list_remotes_action = QAction("列出远程仓库", self); list_remotes_action.triggered.connect(self._run_list_remotes); repo_menu.addAction(list_remotes_action); self.command_buttons['list_remotes_action'] = list_remotes_action
        help_menu = menu_bar.addMenu("帮助(&H)")
        about_action = QAction("关于(&A)", self); about_action.triggered.connect(self._show_about_dialog); help_menu.addAction(about_action)

    def _create_toolbar(self):
        """创建工具栏"""
        toolbar = QToolBar("主要操作"); toolbar.setIconSize(QSize(24, 24)); self.addToolBar(toolbar)
        status_action = QAction("Status", self); status_action.triggered.connect(self._run_status); toolbar.addAction(status_action); self.command_buttons['status_action'] = status_action
        pull_action = QAction("Pull", self); pull_action.triggered.connect(self._run_pull); toolbar.addAction(pull_action); self.command_buttons['pull_action'] = pull_action
        push_action = QAction("Push", self); push_action.triggered.connect(self._run_push); toolbar.addAction(push_action); self.command_buttons['push_action'] = push_action
        toolbar.addSeparator()
        list_branches_action_tb = QAction("分支列表", self); list_branches_action_tb.triggered.connect(self._run_list_branches); toolbar.addAction(list_branches_action_tb); self.command_buttons['list_branches_action_tb'] = list_branches_action_tb
        switch_branch_action_tb = QAction("切换分支", self); switch_branch_action_tb.triggered.connect(self._run_switch_branch); toolbar.addAction(switch_branch_action_tb); self.command_buttons['switch_branch_action_tb'] = switch_branch_action_tb
        list_remotes_action_tb = QAction("远程列表", self); list_remotes_action_tb.triggered.connect(self._run_list_remotes); toolbar.addAction(list_remotes_action_tb); self.command_buttons['list_remotes_action_tb'] = list_remotes_action_tb
        toolbar.addSeparator()
        clear_output_action = QAction("清空输出", self); clear_output_action.triggered.connect(self.output_display.clear); toolbar.addAction(clear_output_action)

    def _add_command_button(self, layout, text, tooltip, slot):
        """辅助函数：添加命令按钮"""
        button = QPushButton(text); button.setToolTip(tooltip); button.clicked.connect(slot)
        layout.addWidget(button); button_key = f"button_{text.lower().replace('...', '').replace(' ', '_')}"
        self.command_buttons[button_key] = button; return button

    # --- 状态更新和 UI 启用/禁用 方法 ---
    def _update_repo_status(self):
        """更新仓库相关UI元素状态"""
        repo_path = self.git_handler.get_repo_path()
        is_valid = self.git_handler.is_valid_repo()
        display_path = repo_path if len(repo_path) < 60 else f"...{repo_path[-57:]}"
        self.repo_label.setText(f"当前仓库: {display_path}")
        if is_valid:
            self.repo_label.setStyleSheet(""); self._update_ui_enable_state(True)
            self.status_bar.showMessage(f"当前仓库: {repo_path}", 5000)
            self.git_handler.get_current_branch_async(self._update_branch_display)
        else:
            self.repo_label.setStyleSheet("color: red;"); self._update_ui_enable_state(False)
            self.status_bar.showMessage("请选择一个有效的 Git 仓库目录", 0)

    def _update_ui_enable_state(self, enabled: bool):
        """根据是否是有效仓库，启用或禁用UI元素 (包括命令行输入框)"""
        for key, item in self.command_buttons.items():
            if key == 'command_input': item.setEnabled(enabled); continue # 处理命令输入框
            is_build_button = key in ['button_add...', 'button_commit...', 'button_commit_-a...']
            is_sequence_op = key in ['execute', 'clear', 'save']
            if is_build_button: item.setEnabled(True)
            elif is_sequence_op: item.setEnabled(enabled)
            else: item.setEnabled(enabled)
        self.shortcut_list_widget.setEnabled(enabled)
        self.shortcut_manager.set_shortcuts_enabled(enabled) # 委托给管理器
        for action in self.findChildren(QAction):
             if action.text() == "Git 全局配置(&G)...": action.setEnabled(True)
             elif action.text() in ["选择仓库(&O)...", "退出(&X)", "关于(&A)", "清空输出"]: action.setEnabled(True)

    @pyqtSlot(int, str, str)
    def _update_branch_display(self, return_code, stdout, stderr):
        """更新状态栏中的当前分支显示"""
        if return_code == 0 and stdout:
            branch_name = stdout.strip(); repo_path_short = self.git_handler.get_repo_path();
            if len(repo_path_short) > 40: repo_path_short = f"...{repo_path_short[-37:]}"
            self.status_bar.showMessage(f"分支: {branch_name} | 仓库: {repo_path_short}", 0)
        else:
             repo_path = self.git_handler.get_repo_path();
             if not repo_path: repo_path = "(未选择)"
             if len(repo_path) > 40: repo_path = f"...{repo_path[-37:]}"
             self.status_bar.showMessage(f"仓库: {repo_path} (无法获取分支)", 0)

    # --- 仓库选择 ---
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

    # --- 命令按钮槽 ---
    def _add_simple_command(self, command_str: str):
        logging.debug(f"添加简单命令到序列列表: {repr(command_str)}")
        self.current_command_sequence.append(command_str); self._update_sequence_display()
    def _add_status(self): self._add_simple_command("git status")
    def _add_files(self):
        files, ok = QInputDialog.getText(self,"添加文件/目录","输入要添加的文件或目录 (用空格分隔, '.' 代表所有):",QLineEdit.EchoMode.Normal,".")
        if ok and files: command_str = f"git add {files.strip()}"; logging.debug(f"添加 'add' ...: {repr(command_str)}"); self.current_command_sequence.append(command_str); self._update_sequence_display()
    def _add_commit(self):
        commit_msg, ok = QInputDialog.getText(self,"提交更改","输入提交信息 (git commit -m):",QLineEdit.EchoMode.Normal)
        if ok and commit_msg: safe_msg = shlex.quote(commit_msg); command_str = f"git commit -m {safe_msg}"; logging.debug(f"添加 'commit' ...: {repr(command_str)}"); self.current_command_sequence.append(command_str); self._update_sequence_display()
        elif ok and not commit_msg: QMessageBox.warning(self, "提交失败", "提交信息不能为空。")
    def _add_commit_am(self):
        commit_msg, ok = QInputDialog.getText(self,"暂存并提交","输入提交信息 (git commit -am):\n(暂存所有已跟踪文件的更改)",QLineEdit.EchoMode.Normal)
        if ok and commit_msg: safe_msg = shlex.quote(commit_msg); command_str = f"git commit -am {safe_msg}"; logging.debug(f"添加 'commit -am' ...: {repr(command_str)}"); self.current_command_sequence.append(command_str); self._update_sequence_display()
        elif ok and not commit_msg: QMessageBox.warning(self, "提交失败", "提交信息不能为空。")

    # --- 序列操作 ---
    def _update_sequence_display(self): self.sequence_display.setText("\n".join(self.current_command_sequence))
    def _clear_sequence(self): self.current_command_sequence = []; self._update_sequence_display(); self.status_bar.showMessage("命令序列已清空", 2000); logging.info("命令序列已清空。")
    def _execute_sequence(self):
        if not self.git_handler.is_valid_repo(): QMessageBox.critical(self, "错误", "当前目录不是有效的 Git 仓库。"); return
        if not self.current_command_sequence: QMessageBox.information(self, "提示", "命令序列为空，无需执行。"); return
        sequence_to_run = list(self.current_command_sequence); logging.info(f"执行当前构建的命令序列: {sequence_to_run}"); self._run_command_list_sequentially(sequence_to_run)

    # --- 核心命令执行逻辑 ---
    def _run_command_list_sequentially(self, command_strings: list[str]):
        """按顺序执行命令字符串列表 (核心执行逻辑，现在可处理非git命令)"""
        logging.debug(f"进入 _run_command_list_sequentially，命令列表: {command_strings}")
        self._set_ui_busy(True) # 禁用 UI 元素

        def execute_next(index):
            if index >= len(command_strings):
                self._append_output("\n✅ --- 所有命令执行完毕 ---", QColor("green"))
                self._set_ui_busy(False); self._refresh_repo_state_ui(); return

            cmd_str = command_strings[index].strip()
            logging.debug(f"正在执行命令字符串 #{index}: {repr(cmd_str)}")
            if not cmd_str: QTimer.singleShot(0, lambda idx=index + 1: execute_next(idx)); return

            try: command_parts = shlex.split(cmd_str); logging.debug(f"shlex 解析结果: {command_parts}")
            except ValueError as e:
                 self._append_output(f"\n❌ 错误: 解析命令 '{cmd_str}' 失败: {e}", QColor("red"))
                 self._append_output("\n--- 执行中止 ---", QColor("red")); self._set_ui_busy(False); return

            if not command_parts: QTimer.singleShot(0, lambda idx=index+1: execute_next(idx)); return # 如果解析为空则跳过

            # 为显示重构命令 (比原始 cmd_str 更安全)
            display_cmd = ' '.join(shlex.quote(part) for part in command_parts)
            self._append_output(f"\n▶️ 执行: {display_cmd}", QColor("blue")) # 执行前回显

            @pyqtSlot(int, str, str)
            def on_command_finished(return_code, stdout, stderr):
                if stdout: self._append_output(f"stdout:\n{stdout.strip()}")
                if stderr: self._append_output(f"stderr:\n{stderr.strip()}", QColor("red")) # 为简化起见，stderr 保持红色
                if return_code == 0:
                    self._append_output(f"✅ 命令成功: '{display_cmd}'", QColor("darkGreen"))
                    QTimer.singleShot(0, lambda idx=index + 1: execute_next(idx)) # 继续执行下一个
                else:
                    logging.error(f"命令执行失败! Command: '{display_cmd}', RC: {return_code}, Stderr: {stderr.strip()}")
                    self._append_output(f"\n❌ --- 命令 '{display_cmd}' 失败 (RC: {return_code})，执行中止 ---", QColor("red"))
                    self._set_ui_busy(False) # 失败时重新启用 UI

            @pyqtSlot(str)
            def on_progress(message): self.status_bar.showMessage(message, 3000)

            self.git_handler.execute_command_async(command_parts, on_command_finished, on_progress)

        execute_next(0) # 开始执行第一个命令

    def _refresh_repo_state_ui(self):
        """执行完命令后刷新仓库状态相关的 UI（状态和分支）"""
        if self.git_handler.is_valid_repo():
            self.git_handler.get_current_branch_async(self._update_branch_display)

    def _set_ui_busy(self, busy: bool):
        """设置 UI 为忙碌状态或解除忙碌 (包括命令行输入框)"""
        for key, item in self.command_buttons.items(): item.setEnabled(not busy)
        self.shortcut_list_widget.setEnabled(not busy)
        self.shortcut_manager.set_shortcuts_enabled(not busy) # 委托给管理器
        if self.command_input: self.command_input.setEnabled(not busy) # 处理命令输入框

        for action in self.findChildren(QAction):
            if action.text() in ["选择仓库(&O)...", "Git 全局配置(&G)...", "退出(&X)", "关于(&A)", "清空输出"]: action.setEnabled(True)
        if busy: self.status_bar.showMessage("⏳ 正在执行...", 0); QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        else: QApplication.restoreOverrideCursor(); # 状态栏更新在别处进行

    def _append_output(self, text: str, color: QColor = None):
        """向输出区域追加文本，可选颜色"""
        if not self.output_display: return # 防止在 UI 设置前调用
        cursor = self.output_display.textCursor(); cursor.movePosition(QTextCursor.MoveOperation.End)
        self.output_display.setTextCursor(cursor); original_format = self.output_display.currentCharFormat()
        fmt = QTextEdit().currentCharFormat() # 从干净的格式开始
        if color: fmt.setForeground(color)
        else: fmt.setForeground(self.palette().color(self.foregroundRole()))
        self.output_display.setCurrentCharFormat(fmt);
        # 确保末尾有一个换行符，但如果文本末尾已经有换行符，则不添加额外的
        clean_text = text.rstrip('\n')
        self.output_display.insertPlainText(clean_text + "\n")
        self.output_display.setCurrentCharFormat(original_format); self.output_display.ensureCursorVisible()


    # --- 命令行输入框槽 ---
    @pyqtSlot()
    def _execute_command_from_input(self):
        """执行在命令行输入框中输入的命令"""
        if not self.command_input: return
        command_text = self.command_input.text().strip()
        if not command_text: return

        logging.info(f"用户从命令行输入: {command_text}")
        prompt_color = QColor(Qt.GlobalColor.magenta)
        # 如果解析成功，使用带引号的重构命令进行回显
        try: display_cmd = ' '.join(shlex.quote(part) for part in shlex.split(command_text))
        except ValueError: display_cmd = command_text # 解析失败时的回退
        self._append_output(f"\n$ {display_cmd}", prompt_color) # 回显命令
        self.command_input.clear()
        # 执行单个命令
        self._run_command_list_sequentially([command_text])

    # --- 快捷键执行逻辑 (由 ShortcutManager 调用) ---
    def _execute_sequence_from_string(self, name: str, sequence_str: str):
        """根据名称和序列字符串执行命令 (包含健壮性分割)"""
        if not self.git_handler.is_valid_repo(): QMessageBox.critical(self, "错误", f"仓库无效，无法执行快捷键 '{name}'。"); return
        self.status_bar.showMessage(f"执行快捷键: {name}", 3000)

        commands = []; lines = sequence_str.splitlines(); lines = [line.strip() for line in lines if line.strip()]
        needs_git_split = False
        if len(lines) == 1 and lines[0].count(" git ") > 0: needs_git_split = True
        elif len(lines) > 1 and lines[0].count(" git ") > 0: logging.warning(f"快捷键 '{name}' 的第一行可能包含多个命令，尝试智能分割。"); needs_git_split = True
        if needs_git_split and lines:
            logging.warning(f"快捷键 '{name}' 序列可能格式错误，尝试按 'git ' 分割: {repr(lines[0])}")
            # 改进的分割逻辑: 处理混合的、不以 git 开头的命令
            parts = re.split(r'(\bgit\s)', lines[0]) # 分割并保留 'git ' 作为分隔符
            potential_cmds = []
            current_cmd = ""
            for i, part in enumerate(parts):
                if part == 'git ':
                    if current_cmd: potential_cmds.append(current_cmd.strip())
                    current_cmd = part
                else:
                    current_cmd += part
            if current_cmd: potential_cmds.append(current_cmd.strip())

            # 过滤掉分割可能产生的空字符串
            commands.extend([cmd for cmd in potential_cmds if cmd])

            if len(lines) > 1: commands.extend(lines[1:])
            logging.info(f"按 'git ' 分割后的命令: {commands}")
        elif lines: commands = lines
        commands = [cmd.strip() for cmd in commands if cmd.strip()]

        if not commands: QMessageBox.warning(self, "快捷键无效", f"快捷键 '{name}' 命令序列为空或无法解析。"); logging.warning(f"快捷键 '{name}' 解析后命令列表为空。"); return
        # 目前允许来自快捷键的任何命令
        logging.info(f"最终执行命令列表 for '{name}': {commands}")
        self._run_command_list_sequentially(commands)

    # --- 直接操作槽 (简化) ---
    def _execute_command_if_valid_repo(self, command_list: list):
         if not self.git_handler.is_valid_repo(): QMessageBox.warning(self, "操作无效", "请先选择一个有效的 Git 仓库。"); return
         self._run_command_list_sequentially(command_list)
    def _run_status(self): self._execute_command_if_valid_repo(["git", "status"])
    def _run_pull(self): self._execute_command_if_valid_repo(["git", "pull"])
    def _run_push(self): self._execute_command_if_valid_repo(["git", "push"])
    def _run_list_branches(self): self._execute_command_if_valid_repo(["git", "branch"])
    def _run_switch_branch(self):
        if not self.git_handler.is_valid_repo(): QMessageBox.warning(self, "操作无效", "请先选择一个有效的 Git 仓库。"); return
        branch_name, ok = QInputDialog.getText(self,"切换分支","输入要切换到的分支名称:",QLineEdit.EchoMode.Normal)
        if ok and branch_name: self._run_command_list_sequentially(["git", "checkout", branch_name]) # 传递分块
        elif ok and not branch_name: QMessageBox.warning(self, "操作取消", "分支名称不能为空。")
    def _run_list_remotes(self): self._execute_command_if_valid_repo(["git", "remote", "-v"])

    # --- 设置对话框槽 ---
    def _open_settings_dialog(self):
        dialog = SettingsDialog(self);
        if dialog.exec():
            config_data = dialog.get_data(); commands_to_run = []
            name_val = config_data.get("user.name"); email_val = config_data.get("user.email")
            # 为配置构建命令字符串 - 此处 shlex.quote 很好用
            if name_val is not None: commands_to_run.append(f"git config --global user.name {shlex.quote(name_val)}")
            if email_val is not None: commands_to_run.append(f"git config --global user.email {shlex.quote(email_val)}")
            if commands_to_run: QMessageBox.information(self, "应用配置", f"将执行以下全局配置命令:\n" + "\n".join(commands_to_run)); self._run_command_list_sequentially(commands_to_run)
            else: QMessageBox.information(self, "无更改", "未输入任何配置信息。")

    # --- 其他辅助方法 ---
    def _show_about_dialog(self):
        QMessageBox.about(
            self,
            "关于简易 Git GUI",
            "这是一个使用 PyQt6 构建的简单 Git 图形界面工具。\n\n"
            "版本: 1.5 (优化命令行样式)\n\n"
            "功能:\n"
            "- 基本 Git 命令按钮\n"
            "- 命令序列组合与执行\n"
            "- 保存/加载带快捷键的命令组合\n"
            "- 异步执行 Git 命令和 Shell 命令\n"
            "- 底部命令行输入 (带样式)\n"
            "- 分支/远程/配置基础操作\n\n"
            "作者: GitHub @424635328"
        )
    def closeEvent(self, event): logging.info("应用程序关闭。"); event.accept()