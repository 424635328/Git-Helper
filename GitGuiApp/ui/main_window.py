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
    QStatusBar, QToolBar, QMenu, QTreeView, QTabWidget, QHeaderView, QTableWidget, QTableWidgetItem,
    QSpacerItem, QFrame, QStyle
)
from PyQt6.QtGui import QAction, QKeySequence, QColor, QTextCursor, QIcon, QFont, QStandardItemModel, QDesktopServices, QTextCharFormat
from PyQt6.QtCore import Qt, pyqtSlot, QSize, QTimer, QModelIndex, QUrl, QPoint, QItemSelection, QRect # Import QRect for setGeometry overload hint

# 确保这些导入指向您的模块的正确位置
from .dialogs import SettingsDialog # Only SettingsDialog is used directly in MainWindow
from .shortcut_manager import ShortcutManager
from .status_tree_model import StatusTreeModel, STATUS_STAGED, STATUS_UNSTAGED, STATUS_UNTRACKED
from core.git_handler import GitHandler
from core.db_handler import DatabaseHandler

# --- Constants ---
LOG_COL_COMMIT = 0
LOG_COL_AUTHOR = 1
LOG_COL_DATE = 2
LOG_COL_MESSAGE = 3

STATUS_COL_STATUS = 0
STATUS_COL_PATH = 1

class MainWindow(QMainWindow):
    """Git GUI 主窗口"""
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Git GUI v1.7")
        # Initial geometry is set in _init_ui based on screen size

        # Initialize handlers and manager early
        self.db_handler = DatabaseHandler()
        self.git_handler = GitHandler()
        # Pass self (MainWindow instance) and db_handler
        self.shortcut_manager = ShortcutManager(self, self.db_handler)

        self.current_command_sequence = []
        # 存储所有需要根据仓库状态启用/禁用的交互式UI元素
        self._repo_dependent_widgets = []

        # UI 元素占位符 (保持不变)
        self.output_display: QTextEdit | None = None
        self.command_input: QLineEdit | None = None
        self.sequence_display: QTextEdit | None = None
        self.shortcut_list_widget: QListWidget | None = None # Keep as placeholder initially
        self.repo_label: QLabel | None = None
        self.status_bar: QStatusBar | None = None
        self.branch_list_widget: QListWidget | None = None
        self.status_tree_view: QTreeView | None = None
        self.status_tree_model: StatusTreeModel | None = None
        self.log_table_widget: QTableWidget | None = None
        self.diff_text_edit: QTextEdit | None = None
        self.main_tab_widget: QTabWidget | None = None
        self.commit_details_textedit: QTextEdit | None = None
        self._output_tab_index = -1 # 新增：存储输出标签页的索引

        # --- Call _init_ui to build the UI and assign widgets ---
        self._init_ui()

        # --- Pass the created widget to the manager AFTER _init_ui ---
        # This must happen AFTER the widget is created in _init_ui
        if self.shortcut_list_widget:
            logging.debug("MainWindow: shortcut_list_widget created, setting in manager.")
            self.shortcut_manager.set_shortcut_list_widget(self.shortcut_list_widget)
        else:
            # This error indicates a failure in _init_ui to create the widget
            # The most likely cause was the TypeError in setGeometry preventing _init_ui completion
            logging.error("MainWindow: Failed to create shortcut_list_widget during _init_ui.")


        # --- Trigger initial refresh including shortcut loading ---
        # Loading shortcuts and updating repo status are now triggered by _update_repo_status
        # which is called at the end of __init__. This ensures the UI is ready first.
        self._update_repo_status()

        logging.info("主窗口初始化完成。")

    # --- Helper Methods ---

    def _check_repo_and_warn(self, message="请先选择一个有效的 Git 仓库。"):
        """检查是否有有效的 Git 仓库，否则显示警告并返回 False。"""
        if not self.git_handler or not self.git_handler.is_valid_repo():
            self._show_warning("操作无效", message)
            return False
        return True

    def _show_warning(self, title: str, message: str):
        QMessageBox.warning(self, title, message)

    def _show_information(self, title: str, message: str):
        QMessageBox.information(self, title, message)

    def _append_output(self, text: str, color: QColor = None):
        """向原始输出区域追加文本，可指定颜色"""
        if not self.output_display: return
        cursor = self.output_display.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        self.output_display.setTextCursor(cursor)

        original_format = cursor.charFormat()
        fmt = QTextCharFormat(original_format) # 从当前格式开始
        if color:
             fmt.setForeground(color)

        self.output_display.setCurrentCharFormat(fmt)
        # Ensure text ends with a newline if it doesn't already for consistent line breaks
        clean_text = text.strip() # Remove leading/trailing whitespace
        if clean_text:
             self.output_display.insertPlainText(clean_text + "\n")

        # 恢复原始格式以用于后续文本
        self.output_display.setCurrentCharFormat(original_format)
        self.output_display.ensureCursorVisible()


    def _run_command_list_sequentially(self, command_strings: list[str], refresh_on_success=True):
        """按顺序执行一列表 Git 命令字符串。"""
        # Validity check happens here at the start of the execution flow
        if not self._check_repo_and_warn("仓库无效，无法执行命令序列。"):
             # Ensure busy state is reset if it was set before calling this
             self._set_ui_busy(False)
             return

        # Filter out empty command strings from the list
        valid_commands = [cmd.strip() for cmd in command_strings if cmd.strip()]
        if not valid_commands:
             logging.debug("Command list is empty after filtering.")
             self._show_information("提示", "命令序列为空，无需执行。")
             # Ensure UI busy state is reset if it was set before calling this
             self._set_ui_busy(False) # Should already be False if list was empty initially
             return

        logging.debug(f"准备执行命令列表: {valid_commands}, 成功后刷新: {refresh_on_success}")

        # --- Switch to Raw Output tab and clear/mark ---
        if self.main_tab_widget and self._output_tab_index != -1:
             self.main_tab_widget.setCurrentIndex(self._output_tab_index)
             if self.output_display:
                  self._append_output("\n--- 开始执行新的命令序列 ---", QColor("darkCyan"))
             QApplication.processEvents() # Ensure UI updates immediately

        self._set_ui_busy(True)

        def execute_next(index):
            if index >= len(valid_commands):
                self._append_output("\n✅ --- 所有命令执行完毕 ---", QColor("green"))
                # In case of successful sequence execution, clear the builder
                self._clear_sequence() # This clears the sequence data and display
                self._set_ui_busy(False)
                if refresh_on_success:
                     self._refresh_all_views() # This will ultimately update status bar
                else:
                     self._update_status_bar_repo_info() # Update status bar specifically
                return

            cmd_str = valid_commands[index]
            logging.debug(f"执行命令 #{index + 1}/{len(valid_commands)}: {repr(cmd_str)}")

            try:
                # Use shlex.split to handle quoting correctly
                command_parts = shlex.split(cmd_str)
                logging.debug(f"解析结果: {command_parts}")
            except ValueError as e:
                err_msg = f"❌ 解析错误 '{cmd_str}': {e}"
                self._append_output(err_msg, QColor("red"))
                self._append_output("--- 执行中止 ---", QColor("red"))
                logging.error(err_msg)
                self._set_ui_busy(False)
                return

            if not command_parts:
                 logging.debug(f"命令 #{index + 1} 解析结果为空，跳过。")
                 # Use a small delay to avoid blocking if multiple empty commands
                 QTimer.singleShot(10, lambda idx=index + 1: execute_next(idx))
                 return

            # Re-quote for display to show how it was interpreted after parsing
            display_cmd = ' '.join(shlex.quote(part) for part in command_parts)
            self._append_output(f"\n$ {display_cmd}", QColor("blue"))
            if self.status_bar: self.status_bar.showMessage(f"正在执行: {display_cmd[:50]}...", 0)


            @pyqtSlot(int, str, str)
            def on_command_finished(return_code, stdout, stderr):
                # Use timer to process the results asynchronously, allowing UI to breathe
                # Pass command string to print it on finish/error message
                QTimer.singleShot(10, lambda rc=return_code, so=stdout, se=stderr: process_finish(rc, so, se, display_cmd))

            def process_finish(return_code, stdout, stderr, cmd_str_for_log):
                # Only append output if there's something to show or an error occurred
                if stdout.strip(): self._append_output(f"stdout:\n{stdout.strip()}")
                if stderr.strip(): self._append_output(f"stderr:\n{stderr.strip()}", QColor("red"))

                if return_code == 0:
                    self._append_output(f"✅ 成功: '{cmd_str_for_log}'", QColor("darkGreen"))
                    QTimer.singleShot(10, lambda idx=index + 1: execute_next(idx)) # Schedule next command
                else:
                    err_msg = f"❌ 失败 (RC: {return_code}) '{cmd_str_for_log}'，执行中止。"
                    logging.error(f"命令执行失败! 命令: '{cmd_str_for_log}', 返回码: {return_code}, 标准错误: {stderr.strip()}")
                    self._append_output(err_msg, QColor("red"))
                    self._set_ui_busy(False) # Stop execution on failure


            @pyqtSlot(str)
            def on_progress(message):
                # Filter common progress messages
                if message and not (message.startswith("Receiving objects:") or message.startswith("Resolving deltas:") or message.startswith("remote:")):
                     if self.status_bar:
                          # Show the progress message briefly
                          self.status_bar.showMessage(message.strip(), 2000)


            self.git_handler.execute_command_async(command_parts, on_command_finished, on_progress)

        # Start sequence execution
        execute_next(0)


    def _add_repo_dependent_widget(self, widget):
         """将一个需要根据仓库状态启用/禁用的widget添加到跟踪列表"""
         if widget:
              self._repo_dependent_widgets.append(widget)
              # Initial state is set by _update_ui_enable_state

    # --- UI Initialization Methods (Decomposed from _init_ui) ---

    def _init_ui(self):
        """初始化用户界面 (状态交互, 分支交互, 日志详情)"""
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)

        self._create_repo_area(main_layout)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        main_layout.addWidget(splitter, 1)

        self._create_left_panel(splitter) # This creates self.shortcut_list_widget
        self._create_right_panel_and_tabs(splitter)

        # 分隔器设置 (Moved here after adding panels)
        # Use QApplication.primaryScreen() for more reliable geometry on multi-monitor setups
        screen = QApplication.primaryScreen()
        screen_geometry = screen.availableGeometry() if screen else None

        # --- FIX: Cast calculated width and height to int ---
        initial_width = int(screen_geometry.width() * 0.8) if screen_geometry else 1200
        initial_height = int(screen_geometry.height() * 0.8) if screen_geometry else 900

        # Set initial window geometry
        # --- FIX: Ensure all arguments are integers ---
        self.setGeometry(100, 100, initial_width, initial_height) # Now passes integers


        # Set initial splitter sizes after geometry is known. Splitter also expects integers.
        # --- FIX: Cast splitter sizes to int ---
        splitter.setSizes([int(initial_width * 0.35), int(initial_width * 0.65)])


        self._create_status_bar()
        self._create_menu()
        self._create_toolbar()

    def _create_repo_area(self, main_layout: QVBoxLayout):
        """创建仓库选择区域"""
        repo_layout = QHBoxLayout()
        self.repo_label = QLabel("当前仓库: (未选择)")
        self.repo_label.setToolTip("当前操作的 Git 仓库路径")
        repo_layout.addWidget(self.repo_label, 1)

        select_repo_button = QPushButton("选择仓库")
        select_repo_button.setToolTip("选择仓库目录")
        select_repo_button.clicked.connect(self._select_repository)
        repo_layout.addWidget(select_repo_button)

        main_layout.addLayout(repo_layout)
        # Note: Select Repo button is *not* repo-dependent, it's always enabled

    def _create_left_panel(self, splitter: QSplitter):
        """创建左侧面板 (按钮, 序列构建器, 分支列表, 快捷键列表)"""
        logging.debug("Creating left panel...")
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(5, 0, 5, 5)
        left_layout.setSpacing(6)
        splitter.addWidget(left_panel)

        # Command buttons
        left_layout.addWidget(QLabel("常用 Git 命令:")) # Added label for clarity
        command_buttons_layout_1 = QHBoxLayout()
        # These buttons *add to sequence*
        self._add_command_button(command_buttons_layout_1, "Status", "添加 'git status' 到序列", lambda: self._add_command_to_sequence("git status"))
        self._add_command_button(command_buttons_layout_1, "Add .", "添加 'git add .' 到序列", lambda: self._add_command_to_sequence("git add ."))
        self._add_command_button(command_buttons_layout_1, "Add...", "添加 'git add <文件>' 到序列 (需要输入)", self._add_files_to_sequence)
        left_layout.addLayout(command_buttons_layout_1)

        command_buttons_layout_2 = QHBoxLayout()
        # These buttons *add to sequence*
        self._add_command_button(command_buttons_layout_2, "Commit...", "添加 'git commit -m <msg>' 到序列 (需要输入)", self._add_commit_to_sequence)
        self._add_command_button(command_buttons_layout_2, "Commit -a...", "添加 'git commit -am <msg>' 到序列 (需要输入)", self._add_commit_am_to_sequence)
        # Log button refreshes the view directly, doesn't add to sequence
        self._add_command_button(command_buttons_layout_2, "Log", "刷新提交历史视图 (Tab)", self._refresh_log_view)
        left_layout.addLayout(command_buttons_layout_2)

        more_commands_layout = QHBoxLayout()
        # These buttons *add to sequence*
        self._add_command_button(more_commands_layout, "Pull", "添加 'git pull' 到序列", lambda: self._add_command_to_sequence("git pull"))
        self._add_command_button(more_commands_layout, "Push", "添加 'git push' 到序列", lambda: self._add_command_to_sequence("git push"))
        self._add_command_button(more_commands_layout, "Fetch", "添加 'git fetch' 到序列", lambda: self._add_command_to_sequence("git fetch"))
        left_layout.addLayout(more_commands_layout)

        # Command sequence builder
        left_layout.addWidget(QLabel("命令序列构建器:"))
        self.sequence_display = QTextEdit()
        self.sequence_display.setReadOnly(True)
        self.sequence_display.setPlaceholderText("点击上方按钮构建命令序列，或从快捷键加载...")
        self.sequence_display.setFixedHeight(80)
        left_layout.addWidget(self.sequence_display)
        self._add_repo_dependent_widget(self.sequence_display)

        sequence_actions_layout = QHBoxLayout()
        execute_button = QPushButton("执行序列")
        execute_button.setToolTip("执行上方构建的命令序列")
        execute_button.setStyleSheet("background-color: lightgreen;")
        execute_button.clicked.connect(self._execute_sequence)
        self._add_repo_dependent_widget(execute_button)

        clear_button = QPushButton("清空序列")
        clear_button.setToolTip("清空上方构建的命令序列")
        clear_button.clicked.connect(self._clear_sequence)
        self._add_repo_dependent_widget(clear_button)

        save_shortcut_button = QPushButton("保存快捷键")
        save_shortcut_button.setToolTip("将上方命令序列保存为新的快捷键")
        # The slot should be in ShortcutManager, called by MainWindow
        save_shortcut_button.clicked.connect(self.shortcut_manager.save_shortcut_dialog)
        self._add_repo_dependent_widget(save_shortcut_button)

        sequence_actions_layout.addWidget(execute_button)
        sequence_actions_layout.addWidget(clear_button)
        sequence_actions_layout.addWidget(save_shortcut_button)
        left_layout.addLayout(sequence_actions_layout)


        # Branch list
        branch_label_layout = QHBoxLayout()
        branch_label_layout.addWidget(QLabel("分支列表:"))
        branch_label_layout.addStretch()
        create_branch_button = QPushButton("+ 新分支")
        create_branch_button.setToolTip("创建新的本地分支")
        # Create branch is a direct action, uses runner internally
        create_branch_button.clicked.connect(self._create_branch_dialog)
        self._add_repo_dependent_widget(create_branch_button)
        branch_label_layout.addWidget(create_branch_button)
        left_layout.addLayout(branch_label_layout)

        self.branch_list_widget = QListWidget()
        self.branch_list_widget.setToolTip("双击切换分支, 右键操作")
        # Double-click is a direct action, uses runner internally
        self.branch_list_widget.itemDoubleClicked.connect(self._branch_double_clicked)
        self.branch_list_widget.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.branch_list_widget.customContextMenuRequested.connect(self._show_branch_context_menu)
        left_layout.addWidget(self.branch_list_widget, 1)
        self._add_repo_dependent_widget(self.branch_list_widget)


        # Saved shortcuts list
        left_layout.addWidget(QLabel("快捷键组合:"))
        self.shortcut_list_widget = QListWidget() # --- This widget is assigned here ---
        self.shortcut_list_widget.setToolTip("双击加载到序列，右键删除")
        # Double-click loads into builder
        self.shortcut_list_widget.itemDoubleClicked.connect(self._load_shortcut_into_builder)
        self.shortcut_list_widget.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        # Context menu handled by ShortcutManager
        # Pass the context menu request to the manager
        self.shortcut_list_widget.customContextMenuRequested.connect(self.shortcut_manager.show_shortcut_context_menu)
        left_layout.addWidget(self.shortcut_list_widget, 1)
        self._add_repo_dependent_widget(self.shortcut_list_widget)
        # Note: ShortcutManager registers QActions for global shortcuts,
        # which are enabled/disabled by set_shortcuts_enabled.
        logging.debug("Left panel creation finished.")

    def _create_right_panel_and_tabs(self, splitter: QSplitter):
        """创建右侧面板 (标签页: 状态, 日志, Diff, 输出 + 命令输入)"""
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(0)
        splitter.addWidget(right_panel)

        # Tab widget
        self.main_tab_widget = QTabWidget()
        right_layout.addWidget(self.main_tab_widget, 1)

        self._create_status_tab()
        self._create_log_tab()
        self._create_diff_tab()
        self._create_output_tab()

        # Command input area (below tabs)
        self._create_command_input_area(right_layout)

    def _create_status_tab(self):
        """创建 '状态 / 文件' 标签页"""
        status_tab_widget = QWidget()
        status_tab_layout = QVBoxLayout(status_tab_widget)
        status_tab_layout.setContentsMargins(5, 5, 5, 5)
        status_tab_layout.setSpacing(4)
        self.main_tab_widget.addTab(status_tab_layout.parentWidget(), "状态 / 文件")

        status_action_layout = QHBoxLayout()
        # These buttons are direct actions, use runner internally
        stage_all_button = QPushButton("全部暂存 (+)")
        stage_all_button.setToolTip("暂存所有未暂存和未跟踪的文件 (git add .)")
        stage_all_button.clicked.connect(self._stage_all)
        self._add_repo_dependent_widget(stage_all_button)

        unstage_all_button = QPushButton("全部撤销暂存 (-)")
        unstage_all_button.setToolTip("撤销所有已暂存文件的暂存状态 (git reset HEAD --)")
        unstage_all_button.clicked.connect(self._unstage_all)
        self._add_repo_dependent_widget(unstage_all_button)

        refresh_status_button = QPushButton("刷新状态")
        refresh_status_button.setToolTip("重新加载当前文件状态")
        # Refresh status is a direct action
        refresh_status_button.clicked.connect(self._refresh_status_view)
        self._add_repo_dependent_widget(refresh_status_button)


        status_action_layout.addWidget(stage_all_button)
        status_action_layout.addWidget(unstage_all_button)
        status_action_layout.addStretch()
        status_action_layout.addWidget(refresh_status_button)
        status_tab_layout.addLayout(status_action_layout)

        self.status_tree_view = QTreeView()
        self.status_tree_model = StatusTreeModel(self) # Model needs parent
        self.status_tree_view.setModel(self.status_tree_model)
        self.status_tree_view.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.status_tree_view.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.status_tree_view.header().setSectionResizeMode(STATUS_COL_PATH, QHeaderView.ResizeMode.Stretch)
        self.status_tree_view.header().setStretchLastSection(False)
        self.status_tree_view.setColumnWidth(STATUS_COL_STATUS, 100)
        self.status_tree_view.setAlternatingRowColors(True)
        self.status_tree_view.selectionModel().selectionChanged.connect(self._status_selection_changed)
        self.status_tree_view.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.status_tree_view.customContextMenuRequested.connect(self._show_status_context_menu)
        status_tab_layout.addWidget(self.status_tree_view, 1)
        self._add_repo_dependent_widget(self.status_tree_view) # View needs repo to be interactive

    def _create_log_tab(self):
        """创建 '提交历史 (Log)' 标签页"""
        log_tab_widget = QWidget()
        log_tab_layout = QVBoxLayout(log_tab_widget)
        log_tab_layout.setContentsMargins(5, 5, 5, 5)
        log_tab_layout.setSpacing(4)
        self.main_tab_widget.addTab(log_tab_layout.parentWidget(), "提交历史 (Log)")

        self.log_table_widget = QTableWidget()
        self.log_table_widget.setColumnCount(4)
        self.log_table_widget.setHorizontalHeaderLabels(["Commit", "Author", "Date", "Message"])
        self.log_table_widget.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.log_table_widget.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.log_table_widget.verticalHeader().setVisible(False)
        self.log_table_widget.setColumnWidth(LOG_COL_COMMIT, 80)
        self.log_table_widget.setColumnWidth(LOG_COL_AUTHOR, 140)
        self.log_table_widget.setColumnWidth(LOG_COL_DATE, 100)
        self.log_table_widget.horizontalHeader().setSectionResizeMode(LOG_COL_MESSAGE, QHeaderView.ResizeMode.Stretch)
        self.log_table_widget.itemSelectionChanged.connect(self._log_selection_changed)
        log_tab_layout.addWidget(self.log_table_widget, 2)
        self._add_repo_dependent_widget(self.log_table_widget) # Table needs repo

        separator = QFrame(); separator.setFrameShape(QFrame.Shape.HLine); separator.setFrameShadow(QFrame.Shadow.Sunken);
        log_tab_layout.addWidget(separator)

        log_tab_layout.addWidget(QLabel("提交详情:"))
        self.commit_details_textedit = QTextEdit()
        self.commit_details_textedit.setReadOnly(True)
        self.commit_details_textedit.setFontFamily("Courier New")
        self.commit_details_textedit.setPlaceholderText("选中上方提交记录以查看详情...")
        log_tab_layout.addWidget(self.commit_details_textedit, 1)
        self._add_repo_dependent_widget(self.commit_details_textedit) # TextEdit content depends on repo log

    def _create_diff_tab(self):
        """创建 '差异 (Diff)' 标签页"""
        diff_tab_widget = QWidget()
        diff_tab_layout = QVBoxLayout(diff_tab_widget)
        diff_tab_layout.setContentsMargins(5, 5, 5, 5)
        self.main_tab_widget.addTab(diff_tab_layout.parentWidget(), "差异 (Diff)")

        self.diff_text_edit = QTextEdit()
        self.diff_text_edit.setReadOnly(True)
        self.diff_text_edit.setFontFamily("Courier New")
        self.diff_text_edit.setPlaceholderText("选中已更改的文件以查看差异...")
        diff_tab_layout.addWidget(self.diff_text_edit, 1)
        self._add_repo_dependent_widget(self.diff_text_edit) # TextEdit content depends on status diffs

    def _create_output_tab(self):
        """创建 '原始输出' 标签页"""
        output_tab_widget = QWidget()
        output_tab_layout = QVBoxLayout(output_tab_widget)
        output_tab_layout.setContentsMargins(5, 5, 5, 5)
        # Store output tab index before adding
        self._output_tab_index = self.main_tab_widget.addTab(output_tab_layout.parentWidget(), "原始输出")

        self.output_display = QTextEdit()
        self.output_display.setReadOnly(True)
        self.output_display.setFontFamily("Courier New")
        self.output_display.setPlaceholderText("Git 命令和命令行输出将显示在此处...")
        output_tab_layout.addWidget(self.output_display, 1)
        # Note: Output display is generally *not* repo-dependent, as it shows messages even when invalid

    def _create_command_input_area(self, parent_layout: QVBoxLayout):
        """创建命令输入区域"""
        command_input_container = QWidget()
        command_input_layout = QHBoxLayout(command_input_container)
        command_input_layout.setContentsMargins(5, 3, 5, 5)
        command_input_layout.setSpacing(4)

        command_input_label = QLabel("$")
        self.command_input = QLineEdit()
        self.command_input.setPlaceholderText("输入 Git 命令并按 Enter 直接执行")
        command_font = QFont("Courier New")
        self.command_input.setFont(command_font)
        # Simplified style (can be kept or put in a separate CSS file)
        command_input_style = """
            QLineEdit { background-color: #ffffff; border: 1px solid #abadb3; border-radius: 2px; padding: 4px 6px; color: #000000; }
            QLineEdit:focus { border: 1px solid #0078d4; }
            QLineEdit::placeholder { color: #a0a0a0; }
            QLineEdit:disabled { background-color: #f0f0f0; color: #a0a0a0; }
        """
        self.command_input.setStyleSheet(command_input_style)
        self.command_input.returnPressed.connect(self._execute_command_from_input)
        self._add_repo_dependent_widget(self.command_input)

        command_input_layout.addWidget(command_input_label)
        command_input_layout.addWidget(self.command_input)
        parent_layout.addWidget(command_input_container)


    def _create_status_bar(self):
        """创建状态栏"""
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("就绪")

    # --- Menu and Toolbar Creation ---

    def _create_menu(self):
        menu_bar = self.menuBar()

        # File Menu
        file_menu = menu_bar.addMenu("文件(&F)")
        select_repo_action = QAction("选择仓库(&O)...", self); select_repo_action.triggered.connect(self._select_repository); file_menu.addAction(select_repo_action)
        git_config_action = QAction("Git 全局配置(&G)...", self); git_config_action.triggered.connect(self._open_settings_dialog); file_menu.addAction(git_config_action)
        file_menu.addSeparator()
        exit_action = QAction("退出(&X)", self); exit_action.triggered.connect(self.close); file_menu.addAction(exit_action)

        # Repository Menu
        repo_menu = menu_bar.addMenu("仓库(&R)")
        refresh_action = QAction("刷新全部视图", self); refresh_action.setShortcut(QKeySequence(Qt.Key.Key_F5)); refresh_action.triggered.connect(self._refresh_all_views)
        repo_menu.addAction(refresh_action); self._add_repo_dependent_widget(refresh_action)

        repo_menu.addSeparator()
        create_branch_action = QAction("创建分支(&N)...", self); create_branch_action.triggered.connect(self._create_branch_dialog)
        repo_menu.addAction(create_branch_action); self._add_repo_dependent_widget(create_branch_action)

        switch_branch_action = QAction("切换分支(&S)...", self); switch_branch_action.triggered.connect(self._run_switch_branch)
        repo_menu.addAction(switch_branch_action); self._add_repo_dependent_widget(switch_branch_action)

        repo_menu.addSeparator()
        list_remotes_action = QAction("列出远程仓库", self); list_remotes_action.triggered.connect(self._run_list_remotes)
        repo_menu.addAction(list_remotes_action); self._add_repo_dependent_widget(list_remotes_action)

        # Help Menu
        help_menu = menu_bar.addMenu("帮助(&H)")
        about_action = QAction("关于(&A)", self); about_action.triggered.connect(self._show_about_dialog); help_menu.addAction(about_action)

    def _create_toolbar(self):
        toolbar = QToolBar("主要操作")
        # Use QApplication.primaryScreen() for consistent icon sizing if needed, otherwise default is fine
        toolbar.setIconSize(QSize(24, 24)) # Keep 24x24 for now
        self.addToolBar(toolbar)

        style = self.style()
        # Get icons using the style object
        refresh_icon = style.standardIcon(QStyle.StandardPixmap.SP_BrowserReload)
        pull_icon = style.standardIcon(QStyle.StandardPixmap.SP_ArrowDown)
        push_icon = style.standardIcon(QStyle.StandardPixmap.SP_ArrowUp)
        new_branch_icon = style.standardIcon(QStyle.StandardPixmap.SP_FileDialogNewFolder)
        switch_branch_icon = style.standardIcon(QStyle.StandardPixmap.SP_FileDialogDetailedView)
        remotes_icon = style.standardIcon(QStyle.StandardPixmap.SP_ComputerIcon)
        clear_icon = style.standardIcon(QStyle.StandardPixmap.SP_DialogResetButton)

        refresh_tb_action = QAction(refresh_icon, "刷新", self); refresh_tb_action.setToolTip("刷新状态、分支和日志视图 (F5)")
        refresh_tb_action.triggered.connect(self._refresh_all_views); toolbar.addAction(refresh_tb_action); self._add_repo_dependent_widget(refresh_tb_action)
        toolbar.addSeparator()

        # Toolbar buttons now add to sequence, consistent with main buttons
        pull_action = QAction(pull_icon, "Pull", self); pull_action.setToolTip("添加 'git pull' 到序列")
        pull_action.triggered.connect(lambda: self._add_command_to_sequence("git pull")); toolbar.addAction(pull_action); self._add_repo_dependent_widget(pull_action)

        push_action = QAction(push_icon,"Push", self); push_action.setToolTip("添加 'git push' 到序列")
        push_action.triggered.connect(lambda: self._add_command_to_sequence("git push")); toolbar.addAction(push_action); self._add_repo_dependent_widget(push_action)
        toolbar.addSeparator()

        create_branch_tb_action = QAction(new_branch_icon, "新分支", self); create_branch_tb_action.setToolTip("创建新的本地分支 (直接执行)")
        create_branch_tb_action.triggered.connect(self._create_branch_dialog); toolbar.addAction(create_branch_tb_action); self._add_repo_dependent_widget(create_branch_tb_action)

        switch_branch_action_tb = QAction(switch_branch_icon, "切换分支...", self); switch_branch_action_tb.setToolTip("切换本地分支 (直接执行)")
        switch_branch_action_tb.triggered.connect(self._run_switch_branch); toolbar.addAction(switch_branch_action_tb); self._add_repo_dependent_widget(switch_branch_action_tb)

        list_remotes_action_tb = QAction(remotes_icon, "远程列表", self); list_remotes_action_tb.setToolTip("列出远程仓库 (直接执行)")
        list_remotes_action_tb.triggered.connect(self._run_list_remotes); toolbar.addAction(list_remotes_action_tb); self._add_repo_dependent_widget(list_remotes_action_tb)
        toolbar.addSeparator()

        clear_output_action = QAction(clear_icon, "清空原始输出", self); clear_output_action.setToolTip("清空'原始输出'标签页的内容")
        # Connect if output_display exists, handled later during init
        # The output_display is created early in _create_output_tab, so this connect is fine here.
        if self.output_display:
             clear_output_action.triggered.connect(self.output_display.clear)
        # Clear output action is *not* repo-dependent, it's always enabled
        toolbar.addAction(clear_output_action)


    def _add_command_button(self, layout: QHBoxLayout, text: str, tooltip: str, slot):
        """Helper to create and add a command button."""
        button = QPushButton(text)
        button.setToolTip(tooltip)
        button.clicked.connect(slot)
        layout.addWidget(button)
        self._add_repo_dependent_widget(button) # All these buttons are repo-dependent
        return button

    # --- State Update and UI Enable/Disable ---

    def _update_repo_status(self):
        """Updates UI based on current repository validity."""
        repo_path = self.git_handler.get_repo_path() if self.git_handler else None
        is_valid = self.git_handler.is_valid_repo() if self.git_handler else False

        # Update repo label
        display_path = repo_path if repo_path and len(repo_path) < 60 else f"...{repo_path[-57:]}" if repo_path else "(未选择)"
        if self.repo_label:
            self.repo_label.setText(f"当前仓库: {display_path}")
            self.repo_label.setStyleSheet("" if is_valid else "color: red;")

        # Enable/Disable UI elements
        self._update_ui_enable_state(is_valid)

        # Clear views if invalid, refresh if valid
        if is_valid:
            if self.status_bar: self.status_bar.showMessage(f"正在加载仓库: {repo_path}", 0)
            QApplication.processEvents() # Allow status bar to update

            # --- FIX: Load shortcuts here if valid repo, after UI is built ---
            # Ensure shortcut_manager and list widget are ready
            if self.shortcut_manager: # Check manager exists
                 # load_and_register_shortcuts itself checks if the list widget is set internally
                self.shortcut_manager.load_and_register_shortcuts()
            else:
                 # This should ideally not happen if init is successful
                 logging.error("ShortcutManager not initialized. Cannot load shortcuts.")

            self._refresh_all_views() # This triggers async refreshes which update the status bar later
        else:
            if self.status_bar: self.status_bar.showMessage("请选择一个有效的 Git 仓库目录", 0)
            # Clear views when repo becomes invalid
            if self.status_tree_model: self.status_tree_model.clear_status()
            if self.branch_list_widget: self.branch_list_widget.clear()
            if self.log_table_widget: self.log_table_widget.setRowCount(0)
            if self.diff_text_edit: self.diff_text_edit.clear()
            if self.commit_details_textedit: self.commit_details_textedit.clear()
            self._clear_sequence() # Also clears sequence data and display

            # --- FIX: Also clear shortcuts display and unregister shortcuts ---
            if self.shortcut_manager:
                 # clear_shortcuts handles clearing the list widget if set
                 self.shortcut_manager.clear_shortcuts()
            else:
                 # Fallback clear just the widget if manager isn't there
                 if self.shortcut_list_widget:
                      self.shortcut_list_widget.clear()


            logging.info("Git 仓库无效，UI 已禁用。")

    def _update_ui_enable_state(self, enabled: bool):
        """Enable or disable UI elements based on repository validity."""
        # Handle repo-dependent widgets collected during UI creation
        for widget in self._repo_dependent_widgets:
            if widget: # Ensure widget is not None
                 # Widgets that aren't repo-dependent are not in this list
                 widget.setEnabled(enabled)


        # Shortcut actions are handled by the shortcut manager based on enable state
        if self.shortcut_manager:
            # The manager itself controls the QShortcut objects' enabled state
            self.shortcut_manager.set_shortcuts_enabled(enabled)

        # Ensure certain global menu/toolbar actions are always enabled
        for action in self.findChildren(QAction):
            action_text = action.text()
            # List of actions that should always be enabled regardless of repo validity
            always_enabled_actions = [
                 "选择仓库(&O)...",
                 "Git 全局配置(&G)...",
                 "退出(&X)",
                 "关于(&A)",
                 "清空原始输出"
            ]
            if action_text in always_enabled_actions:
                action.setEnabled(True)


    def _update_status_bar_repo_info(self):
        """Updates the status bar with current branch and repo path."""
        if not self.status_bar: return

        repo_path_short = self.git_handler.get_repo_path() if self.git_handler and self.git_handler.is_valid_repo() else "(未选择)"
        if len(repo_path_short) > 40:
             repo_path_short = f"...{repo_path_short[-37:]}"

        current_branch_name = "(未知分支)" # Default
        if self.branch_list_widget:
             # Find the bolded item (current branch)
             for i in range(self.branch_list_widget.count()):
                 item = self.branch_list_widget.item(i)
                 if item and item.font().bold():
                      current_branch_name = item.text().strip()
                      break

        is_valid = self.git_handler.is_valid_repo() if self.git_handler else False
        branch_display = current_branch_name if current_branch_name != "(未知分支)" else ("(未知分支)" if is_valid else "(无效仓库)")

        status_message = f"分支: {branch_display} | 仓库: {repo_path_short}"
        # Only update if status bar is not showing a busy or progress message
        if not self.status_bar.currentMessage().startswith("⏳"):
             self.status_bar.showMessage(status_message, 0)


    # --- Refresh View Slots ---
    @pyqtSlot()
    def _refresh_all_views(self):
        """刷新所有主要视图: 状态、分支、日志"""
        if not self._check_repo_and_warn("无法刷新视图，仓库无效。"): return

        logging.info("正在刷新状态、分支和日志视图...")
        # Only show "Refreshing..." if not already busy
        if self.status_bar and not self.status_bar.currentMessage().startswith("⏳"):
             self.status_bar.showMessage("正在刷新...", 0)
        QApplication.processEvents() # Show message immediately

        # Refresh order: Status -> Branches -> Log (dependencies / common workflow)
        self._refresh_status_view()
        self._refresh_branch_list()
        self._refresh_log_view()
        # Diff and commit details refresh automatically on selection changes

    @pyqtSlot()
    def _refresh_status_view(self):
        """异步获取并更新状态树视图"""
        if not self.git_handler or not self.git_handler.is_valid_repo(): return
        logging.debug("正在请求 status porcelain...")
        # Disable stage/unstage buttons while refreshing
        stage_all_btn = next((w for w in self._repo_dependent_widgets if isinstance(w, QPushButton) and w.text() == "全部暂存 (+)"), None)
        unstage_all_btn = next((w for w in self._repo_dependent_widgets if isinstance(w, QPushButton) and w.text() == "全部撤销暂存 (-)"), None)
        if stage_all_btn: stage_all_btn.setEnabled(False)
        if unstage_all_btn: unstage_all_btn.setEnabled(False)

        self.git_handler.get_status_porcelain_async(self._on_status_refreshed)

    @pyqtSlot(int, str, str)
    def _on_status_refreshed(self, return_code, stdout, stderr):
        """处理异步 git status 的结果"""
        if not self.status_tree_model or not self.status_tree_view:
             logging.error("状态树模型或视图在状态刷新时未初始化。")
             # Still try to update status bar
             self._update_status_bar_repo_info()
             return

        # !!! FIX: Clear the status model before populating to avoid duplicate insertion warnings !!!
        self.status_tree_model.clear_status()

        stage_all_btn = next((w for w in self._repo_dependent_widgets if isinstance(w, QPushButton) and w.text() == "全部暂存 (+)"), None)
        unstage_all_btn = next((w for w in self._repo_dependent_widgets if isinstance(w, QPushButton) and w.text() == "全部撤销暂存 (-)"), None)

        if return_code == 0:
            logging.debug("接收到 status porcelain，正在填充模型...")
            self.status_tree_model.parse_and_populate(stdout)
            self.status_tree_view.expandAll()
            self.status_tree_view.resizeColumnToContents(STATUS_COL_STATUS)
            self.status_tree_view.setColumnWidth(STATUS_COL_STATUS, max(100, self.status_tree_view.columnWidth(STATUS_COL_STATUS))) # Ensure min width

            # Re-enable/disable stage/unstage buttons based on model content
            has_unstaged_or_untracked = self.status_tree_model.unstage_root.rowCount() > 0 or self.status_tree_model.untracked_root.rowCount() > 0
            if stage_all_btn: stage_all_btn.setEnabled(has_unstaged_or_untracked)
            if unstage_all_btn: unstage_all_btn.setEnabled(self.status_tree_model.staged_root.rowCount() > 0)

        else:
            logging.error(f"获取状态失败: RC={return_code}, 错误: {stderr}")
            self._append_output(f"❌ 获取 Git 状态失败:\n{stderr}", QColor("red"))
            # Model is already cleared above in case of error as well
            # stage_all_btn and unstage_all_btn already disabled or set to False state

        # Update status bar after status refresh is done
        self._update_status_bar_repo_info()


    @pyqtSlot()
    def _refresh_branch_list(self):
        """异步获取并更新分支列表"""
        if not self.git_handler or not self.git_handler.is_valid_repo(): return
        logging.debug("正在请求格式化分支列表...")
        # Clear before requesting new data
        if self.branch_list_widget: self.branch_list_widget.clear()
        self.git_handler.get_branches_formatted_async(self._on_branches_refreshed)

    @pyqtSlot(int, str, str)
    def _on_branches_refreshed(self, return_code, stdout, stderr):
        """处理异步 git branch 的结果并更新分支列表和状态栏"""
        # Removed redundant checks - slot should only be called if handler was valid.
        if not self.branch_list_widget:
            logging.error("Branch list widget not initialized when branches refreshed.")
            self._update_status_bar_repo_info() # Still update status bar
            return

        current_branch_name = None # Will be updated if success

        if return_code == 0:
            lines = stdout.strip().splitlines()
            logging.debug(f"接收到分支: {len(lines)} 行")
            # Branch list was cleared by the caller (_refresh_branch_list)
            for line in lines:
                if not line: continue
                match = re.match(r'^\*\s+(.+)$', line)
                if match:
                    is_current = True
                    branch_name = match.group(1).strip()
                else:
                    is_current = False
                    branch_name = line.strip()

                if not branch_name: continue

                item = QListWidgetItem(branch_name)
                if is_current:
                    current_branch_name = branch_name
                    font = item.font(); font.setBold(True); item.setFont(font)
                    item.setForeground(QColor("blue"))
                elif branch_name.startswith("remotes/"):
                    item.setForeground(QColor("gray"))

                self.branch_list_widget.addItem(item)

            # Select the current branch item
            if current_branch_name:
                 items = self.branch_list_widget.findItems(current_branch_name, Qt.MatchFlag.MatchExactly)
                 if items: self.branch_list_widget.setCurrentItem(items[0])

        else:
            logging.error(f"获取分支失败: RC={return_code}, 错误: {stderr}")
            self._append_output(f"❌ 获取分支列表失败:\n{stderr}", QColor("red"))
            # Branch list was cleared before the async call

        # Update status bar after branch refresh is done
        self._update_status_bar_repo_info()


    @pyqtSlot()
    def _refresh_log_view(self):
        """异步获取并更新提交历史表格"""
        if not self.git_handler or not self.git_handler.is_valid_repo(): return
        logging.debug("正在请求格式化日志...")
        if self.log_table_widget: self.log_table_widget.setRowCount(0) # Clear before requesting
        if self.commit_details_textedit: self.commit_details_textedit.clear() # Clear details view
        self.git_handler.get_log_formatted_async(count=200, finished_slot=self._on_log_refreshed)

    @pyqtSlot(int, str, str)
    def _on_log_refreshed(self, return_code, stdout, stderr):
        """处理异步 git log 的结果"""
        if not self.log_table_widget:
             logging.error("日志表格组件在日志刷新时未初始化。")
             self._update_status_bar_repo_info() # Still update status bar
             return

        if return_code == 0:
            lines = stdout.strip().splitlines()
            logging.debug(f"接收到日志 ({len(lines)} 条记录)。正在填充表格...")
            self.log_table_widget.setUpdatesEnabled(False)
            self.log_table_widget.setRowCount(0) # Ensure clear before filling, though it's done by caller too
            monospace_font = QFont("Courier New")
            valid_rows = 0
            for line in lines:
                line = line.strip()
                if not line: continue
                # Use regex to parse commit lines with graph prefixes
                # Capture optional graph prefix, hash, author, date, message
                match = re.match(r'^([\s\\/|*.-]*?)?([a-fA-F0-9]+)\s+(.*?)\s+(.*?)\s+(.*)$', line)
                if match:
                    # graph_part = match.group(1) # Not currently displayed
                    commit_hash = match.group(2)
                    author = match.group(3)
                    date = match.group(4)
                    message = match.group(5)

                    if not commit_hash:
                         # This might happen for pure graph lines without commit info
                         logging.debug(f"Parsed empty commit hash, likely pure graph line: {repr(line)}")
                         continue # Skip rows without a valid hash

                    self.log_table_widget.setRowCount(valid_rows + 1)
                    # Use constants for column indices
                    hash_item = QTableWidgetItem(commit_hash[:7]) # Display truncated hash
                    author_item = QTableWidgetItem(author.strip())
                    date_item = QTableWidgetItem(date.strip())
                    message_item = QTableWidgetItem(message.strip())

                    flags = Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled
                    hash_item.setFlags(flags); author_item.setFlags(flags); date_item.setFlags(flags); message_item.setFlags(flags)
                    hash_item.setData(Qt.ItemDataRole.UserRole, commit_hash) # Store full hash in UserRole
                    hash_item.setFont(monospace_font); message_item.setFont(monospace_font)

                    self.log_table_widget.setItem(valid_rows, LOG_COL_COMMIT, hash_item)
                    self.log_table_widget.setItem(valid_rows, LOG_COL_AUTHOR, author_item)
                    self.log_table_widget.setItem(valid_rows, LOG_COL_DATE, date_item)
                    self.log_table_widget.setItem(valid_rows, LOG_COL_MESSAGE, message_item)

                    valid_rows += 1
                else:
                    # Log lines that couldn't be parsed, excluding lines that look like pure graph
                    if not re.match(r'^[\s\\/|*.-]+$', line):
                         logging.warning(f"无法解析日志行: {repr(line)}")


            self.log_table_widget.setUpdatesEnabled(True)
            logging.info(f"日志表格已填充 {valid_rows} 个有效条目。")
        else:
            logging.error(f"获取日志失败: RC={return_code}, 错误: {stderr}")
            self._append_output(f"❌ 获取提交历史失败:\n{stderr}", QColor("red"))
            # Log table is already cleared

        # Update status bar after log refresh is done
        self._update_status_bar_repo_info()


    # --- Repository Selection ---
    @pyqtSlot()
    def _select_repository(self):
        """打开目录选择对话框以选择 Git 仓库"""
        # Determine a reasonable starting path
        start_path = self.git_handler.get_repo_path() if self.git_handler and self.git_handler.get_repo_path() else None
        if not start_path or not os.path.isdir(start_path):
            # Fallback logic if current path is invalid or not set
            start_path = os.getcwd() # Start from current working directory
            # If current directory is not a repo, try user's home or a common 'git' folder
            if not os.path.isdir(os.path.join(start_path, '.git')):
                 home_dir = os.path.expanduser("~")
                 git_dir_in_home = os.path.join(home_dir, 'git')
                 if os.path.isdir(git_dir_in_home):
                      start_path = git_dir_in_home
                 else:
                      start_path = home_dir # Fallback to home directory


        dir_path = QFileDialog.getExistingDirectory(self, "选择 Git 仓库目录", start_path)
        if dir_path:
            if not self.git_handler:
                 logging.error("仓库选择期间 GitHandler 未初始化。")
                 self._show_warning("内部错误", "Git 处理程序未初始化。")
                 return
            try:
                # Clear relevant UI elements immediately to indicate change
                if self.output_display: self.output_display.clear()
                if self.diff_text_edit: self.diff_text_edit.clear()
                if self.commit_details_textedit: self.commit_details_textedit.clear()
                self._clear_sequence() # Also clears sequence data
                if self.status_tree_model: self.status_tree_model.clear_status()
                if self.branch_list_widget: self.branch_list_widget.clear()
                if self.log_table_widget: self.log_table_widget.setRowCount(0)
                 # Clearing shortcuts display is handled by _update_repo_status -> clear_shortcuts


                # Set the new repository path in the handler
                self.git_handler.set_repo_path(dir_path)
                # Update UI state and trigger refresh based on validity
                self._update_repo_status() # This will trigger load_and_register_shortcuts if valid
                logging.info(f"用户选择了新的仓库目录: {dir_path}")
            except ValueError as e:
                self._show_warning("选择仓库失败", str(e))
                logging.error(f"设置仓库路径失败: {e}")
                self.git_handler.set_repo_path(None) # Ensure handler state is reset
                self._update_repo_status() # Update UI to invalid state
            except Exception as e:
                 logging.exception("选择仓库时发生意外错误。")
                 QMessageBox.critical(self, "意外错误", f"选择仓库时出错: {e}")
                 self.git_handler.set_repo_path(None)
                 self._update_repo_status()


    # --- Command Button Slots (Now Add to Sequence) ---
    def _add_command_to_sequence(self, command_to_add: str | list[str]):
        """将命令字符串添加到序列列表并更新显示"""
        if isinstance(command_to_add, list):
            # Join list parts, quoting each one for safety
            command_str = ' '.join(shlex.quote(str(part)) for part in command_to_add)
        elif isinstance(command_to_add, str):
            command_str = command_to_add.strip() # Ensure no leading/trailing whitespace
        else:
            logging.warning(f"无效的命令类型传递给 _add_command_to_sequence: {type(command_to_add)}")
            return

        if not command_str:
             logging.debug("尝试添加空命令到序列，忽略。")
             return

        self.current_command_sequence.append(command_str)
        self._update_sequence_display()
        logging.debug(f"命令添加到序列: {command_str}")


    def _add_files_to_sequence(self):
        """弹出对话框让用户输入要暂存的文件/目录，并将其添加到序列"""
        if not self._check_repo_and_warn(): return
        files_str, ok = QInputDialog.getText(self, "暂存文件", "输入要暂存的文件或目录 (用空格分隔，可用引号):", QLineEdit.EchoMode.Normal)
        if ok and files_str:
            try:
                file_list = shlex.split(files_str.strip())
                if file_list:
                    # Add each file to the sequence as a separate command
                    for file_path in file_list:
                         self._add_command_to_sequence(f"git add -- {shlex.quote(file_path)}")
                else:
                    self._show_information("无操作", "未输入文件。")
            except ValueError as e:
                self._show_warning("输入错误", f"无法解析文件列表: {e}")
                logging.warning(f"无法解析暂存文件输入 '{files_str}': {e}")
        elif ok:
            self._show_information("无操作", "未输入文件。")

    def _add_commit_to_sequence(self):
        """弹出对话框获取提交信息，并将 git commit -m 命令添加到序列"""
        if not self._check_repo_and_warn(): return
        commit_msg, ok = QInputDialog.getText(self, "提交暂存的更改", "输入提交信息:", QLineEdit.EchoMode.Normal)
        if ok: # ok is True even if msg is empty
             cleaned_msg = commit_msg.strip()
             if not cleaned_msg:
                  self._show_warning("提交中止", "提交信息不能为空。")
                  return
             # Add the commit command to the sequence, quoting the message
             self._add_command_to_sequence(f"git commit -m {shlex.quote(cleaned_msg)}")

    def _add_commit_am_to_sequence(self):
        """弹出对话框获取提交信息，并将 git commit -am 命令添加到序列"""
        if not self._check_repo_and_warn(): return
        commit_msg, ok = QInputDialog.getText(self, "暂存所有已跟踪文件并提交", "输入提交信息:", QLineEdit.EchoMode.Normal)
        if ok: # ok is True even if msg is empty
             cleaned_msg = commit_msg.strip()
             if not cleaned_msg:
                  self._show_warning("提交中止", "提交信息不能为空。")
                  return
             # Add the commit -am command to the sequence, quoting the message
             self._add_command_to_sequence(f"git commit -am {shlex.quote(cleaned_msg)}")


    # --- Sequence Operations ---
    def _update_sequence_display(self):
        """更新命令序列构建器显示区域"""
        if self.sequence_display: self.sequence_display.setText("\n".join(self.current_command_sequence))

    def _clear_sequence(self):
        """清空命令序列构建器"""
        self.current_command_sequence = []
        self._update_sequence_display()
        # Status message handled by the runner on successful execution
        # Or you can uncomment this if clearing manually outside of runner
        # if self.status_bar: self.status_bar.showMessage("命令序列已清空", 2000)
        logging.info("命令序列已清空。")

    def _execute_sequence(self):
        """执行命令序列构建器中的命令"""
        # Validity check inside _run_command_list_sequentially
        # Copy the sequence before running, as _clear_sequence is called on success
        self._run_command_list_sequentially(list(self.current_command_sequence))
        # Sequence is cleared on success by _run_command_list_sequentially

    # --- Busy State Management ---
    def _set_ui_busy(self, busy: bool):
        """Enable/disable interactive UI elements and show/hide wait cursor."""
        # Handle repo-dependent widgets
        for widget in self._repo_dependent_widgets:
            if widget: # Ensure widget is not None
                 # Re-evaluate enabled state: busy AND valid repo
                 # Items that aren't repo-dependent (like the clear output action) are not in this list
                 # The isWidgetType() check is not quite right here as QAction is not a widget.
                 # A simpler check: if enabled=False due to busy, check if repo is valid; if enabled=True, it should also require valid repo.
                 is_repo_valid = self.git_handler.is_valid_repo() if self.git_handler else False
                 widget.setEnabled(not busy and is_repo_valid)

        # Ensure certain global menu/toolbar actions are always enabled (handled by _update_ui_enable_state)
        # The _update_ui_enable_state is called after _set_ui_busy(False),
        # or we can call it here with the current repo validity state.
        # Let's call it here to ensure consistency regardless of where _set_ui_busy is called.
        self._update_ui_enable_state(self.git_handler.is_valid_repo() if self.git_handler else False)

        # Update status bar
        if busy:
            if self.status_bar: self.status_bar.showMessage("⏳ 正在执行...", 0)
            QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        else:
            QApplication.restoreOverrideCursor()
            # Restore normal status message after busy state ends
            self._update_status_bar_repo_info() # Update status bar


    # --- Command Input Slot ---
    @pyqtSlot()
    def _execute_command_from_input(self):
        """执行命令行输入框中的命令 (直接执行)"""
        if not self.command_input: return
        command_text = self.command_input.text().strip();
        if not command_text: return
        logging.info(f"用户从命令行输入: {command_text}"); prompt_color = QColor(Qt.GlobalColor.darkCyan)

        # Parse and re-quote for robust display and execution
        try: command_parts = shlex.split(command_text)
        except ValueError as e:
             self._show_warning("输入错误", f"无法解析命令: {e}");
             self._append_output(f"❌ 解析命令失败: {command_text}\n{e}", QColor("red"))
             return

        if not command_parts: return # Empty after split

        # Append to output and clear input *before* execution starts
        display_cmd = ' '.join(shlex.quote(part) for part in command_parts)
        self._append_output(f"\n$ {display_cmd}", prompt_color)
        self.command_input.clear()

        # Execute the single command using the sequential runner
        self._run_command_list_sequentially([command_text], refresh_on_success=True) # Refresh after direct execution


    # --- Shortcut Execution/Loading ---
    # Called by ShortcutManager or list double-click
    @pyqtSlot(QListWidgetItem)
    def _load_shortcut_into_builder(self, item: QListWidgetItem):
        """加载选中的快捷键命令到序列构建器"""
        # This slot is connected to QListWidget.itemDoubleClicked, so 'item' is always passed.

        # Validity check inside _check_repo_and_warn
        if not self._check_repo_and_warn("无法加载快捷键，仓库无效。"): return # Check repo validity before loading

        # Retrieve the full shortcut data from the list item's UserRole
        shortcut_data = item.data(Qt.ItemDataRole.UserRole)
        if not shortcut_data or not isinstance(shortcut_data, dict):
             logging.error("Attempted to load shortcut with invalid item data.")
             self._show_warning("加载失败", "快捷键数据格式错误。")
             return

        name = shortcut_data.get('name', '未知名称')
        sequence_str = shortcut_data.get('sequence', '') # Sequence string

        if sequence_str:
            # Split lines, filter empty lines
            commands = [line.strip() for line in sequence_str.strip().splitlines() if line.strip()]
            # Re-quote each command line for display in the builder
            self.current_command_sequence = []
            for cmd in commands:
                 try:
                      # Parse and re-quote to normalize formatting in the builder
                      self.current_command_sequence.append(' '.join(shlex.quote(part) for part in shlex.split(cmd)))
                 except ValueError as e:
                      logging.warning(f"无法解析快捷键 '{name}' 中的命令 '{cmd[:50]}...': {e}")
                      self.current_command_sequence.append(cmd) # Add raw command if parsing fails


            self._update_sequence_display()
            if self.status_bar: self.status_bar.showMessage(f"快捷键 '{name}' 已加载到序列构建器", 3000)
            logging.info(f"快捷键 '{name}' 已加载到构建器。")
        else:
             # Even if sequence_str is empty, we might want to clear the builder
             self._clear_sequence()
             logging.warning(f"快捷键 '{name}' 没有关联的命令序列。")
             self._show_information("加载完成", f"快捷键 '{name}' 已加载，但没有关联的命令序列。构建器已清空。")


    # This method is called by ShortcutManager actions
    def _execute_sequence_from_string(self, name: str, sequence_str: str):
        """执行从字符串（快捷键定义）加载的命令序列"""
        # Validity check inside _run_command_list_sequentially
        # if not self._check_repo_and_warn(f"无法执行快捷键 '{name}'，仓库无效。"): return # Redundant check

        # Parse the sequence string into a list of commands
        commands = [line.strip() for line in sequence_str.strip().splitlines() if line.strip()]

        if not commands:
             self._show_warning("快捷键无效", f"快捷键 '{name}' 解析后命令序列为空。")
             logging.warning(f"快捷键 '{name}' 导致命令列表为空。")
             return

        # Optionally, show the sequence in the builder before executing
        # Re-quote commands for display in the builder
        display_commands = []
        for cmd in commands:
             try:
                  display_commands.append(' '.join(shlex.quote(part) for part in shlex.split(cmd)))
             except ValueError:
                  display_commands.append(cmd) # Fallback

        self.current_command_sequence = display_commands
        self._update_sequence_display()

        # Status message handled by the runner
        # if self.status_bar: self.status_bar.showMessage(f"正在执行快捷键: {name}", 3000)
        logging.info(f"准备执行快捷键 '{name}' 的命令列表: {commands}")

        # Execute the parsed commands using the sequential runner
        # _run_command_list_sequentially includes repo validity check and busy state management
        self._run_command_list_sequentially(commands)


    # --- Status View Operations (Direct Execution using runner) ---
    @pyqtSlot()
    def _stage_all(self):
        if not self._check_repo_and_warn(): return
        # Check if there's anything to stage first (optional but user-friendly)
        if self.status_tree_model and self.status_tree_model.unstage_root.rowCount() == 0 and self.status_tree_model.untracked_root.rowCount() == 0:
            self._show_information("无操作", "没有未暂存或未跟踪的文件可供暂存。")
            return
        logging.info("请求暂存所有更改 (git add .)")
        self._run_command_list_sequentially(["git add ."]) # Use runner

    @pyqtSlot()
    def _unstage_all(self):
        if not self._check_repo_and_warn(): return
        # Check if there's anything to unstage first
        if self.status_tree_model and self.status_tree_model.staged_root.rowCount() == 0:
             self._show_information("无操作", "没有已暂存的文件可供撤销。")
             return
        logging.info("请求撤销全部暂存 (git reset HEAD --)");
        self._run_command_list_sequentially(["git reset HEAD --"])

    # _stage_files and _unstage_files are called by context menu actions
    # They already use the _run_command_list_sequentially helper

    # --- Status View Context Menu ---
    @pyqtSlot(QPoint)
    def _show_status_context_menu(self, pos: QPoint):
        """显示状态树视图的右键上下文菜单"""
        # Validity check inside _check_repo_and_warn
        if not self._check_repo_and_warn() or not self.status_tree_view or not self.status_tree_model: return

        index = self.status_tree_view.indexAt(pos)
        if not index.isValid(): return

        # Get selected files data from the model
        selected_indexes = self.status_tree_view.selectionModel().selectedIndexes()
        if not selected_indexes: return

        # Ensure we only process unique rows by checking the first column index
        # Use list conversion and then set for unique rows
        unique_selected_rows_indices = set()
        for idx in selected_indexes:
             if idx.isValid() and idx.parent().isValid():
                  unique_selected_rows_indices.add(self.status_tree_model.index(idx.row(), STATUS_COL_STATUS, idx.parent()))

        if not unique_selected_rows_indices:
            # This might happen if clicking outside any valid item but selection model has old items
            return

        selected_files_data = self.status_tree_model.get_selected_files(list(unique_selected_rows_indices))
        menu = QMenu()
        added_action = False

        files_to_stage = selected_files_data.get(STATUS_UNSTAGED, []) + selected_files_data.get(STATUS_UNTRACKED, [])
        if files_to_stage:
            # Connect to methods that use the runner
            stage_action = QAction(f"暂存 {len(files_to_stage)} 项 (+)", self); stage_action.triggered.connect(lambda: self._stage_files(files_to_stage)); menu.addAction(stage_action); added_action = True

        files_to_unstage = selected_files_data.get(STATUS_STAGED, [])
        if files_to_unstage:
            # Connect to methods that use the runner
            unstage_action = QAction(f"撤销暂存 {len(files_to_unstage)} 项 (-)", self); unstage_action.triggered.connect(lambda: self._unstage_files(files_to_unstage)); menu.addAction(unstage_action); added_action = True

        # Discard changes action (for unstaged files)
        files_to_discard_unstaged = selected_files_data.get(STATUS_UNSTAGED, [])
        if files_to_discard_unstaged:
             if added_action: menu.addSeparator()
             discard_action = QAction(f"丢弃 {len(files_to_discard_unstaged)} 项未暂存更改...", self)
             discard_action.triggered.connect(lambda: self._discard_changes_dialog(files_to_discard_unstaged))
             menu.addAction(discard_action); added_action = True


        if added_action:
             # Map position to global screen coordinates
             menu.exec(self.status_tree_view.viewport().mapToGlobal(pos))
        else:
             logging.debug("No applicable actions for selected status items.")

    def _discard_changes_dialog(self, files: list[str]):
        """Confirm and discard unstaged changes for list of files"""
        if not self._check_repo_and_warn() or not files: return

        message = f"确定要丢弃以下 {len(files)} 个文件的未暂存更改吗？\n\n" + "\n".join(files) + "\n\n此操作不可撤销！"
        reply = QMessageBox.warning(self, "确认丢弃更改", message,
                                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
                                    QMessageBox.StandardButton.Cancel)

        if reply == QMessageBox.StandardButton.Yes:
            logging.info(f"请求丢弃文件更改: {files}")
            # Use git checkout -- <file> to discard changes
            commands = [f"git checkout -- {shlex.quote(f)}" for f in files]
            self._run_command_list_sequentially(commands)


    # --- Status View Selection Change ---
    @pyqtSlot(QItemSelection, QItemSelection)
    def _status_selection_changed(self, selected: QItemSelection, deselected: QItemSelection):
        """当状态树中的选择发生变化时，尝试加载并显示差异"""
        # Validity check inside _check_repo_and_warn
        if not self._check_repo_and_warn("仓库无效，无法显示差异。") or not self.status_tree_view or not self.status_tree_model or not self.diff_text_edit:
             self.diff_text_edit.clear();
             self.diff_text_edit.setPlaceholderText("选中已更改的文件以查看差异...")
             return

        self.diff_text_edit.clear() # Always clear on selection change
        selected_indexes = self.status_tree_view.selectionModel().selectedIndexes()

        if not selected_indexes:
            self.diff_text_edit.setPlaceholderText("选中已更改的文件以查看差异...");
            return

        # Check if *only one* item (representing a file row) is selected across all columns
        unique_selected_rows = set(self.status_tree_model.index(idx.row(), STATUS_COL_STATUS, idx.parent()) for idx in selected_indexes if idx.isValid() and idx.parent().isValid())

        if len(unique_selected_rows) != 1:
            self.diff_text_edit.setPlaceholderText("请选择单个文件以查看差异...");
            return

        # Get the single selected row's file path and status type
        first_row_index = list(unique_selected_rows)[0]
        # File path is in the second column (index 1) of the item's parent
        path_item_index = self.status_tree_model.index(first_row_index.row(), STATUS_COL_PATH, first_row_index.parent())
        path_item = self.status_tree_model.itemFromIndex(path_item_index)

        if not path_item:
            logging.warning("Could not find path item for selected status row.");
            self.diff_text_edit.setPlaceholderText("无法获取文件路径...");
            return

        # Get the full path stored in UserRole + 1
        file_path = path_item.data(Qt.ItemDataRole.UserRole + 1);
        parent_item = path_item.parent()
        if not parent_item:
             logging.warning("File path item has no parent.");
             self.diff_text_edit.setPlaceholderText("无法确定文件状态...");
             return

        # Get the section type (Staged, Unstaged, Untracked) from the parent item's UserRole
        section_type = parent_item.data(Qt.ItemDataRole.UserRole);

        if not file_path:
            logging.warning("File path data missing.");
            self.diff_text_edit.setPlaceholderText("无法获取文件路径...");
            return

        # Handle untracked files separately
        if section_type == STATUS_UNTRACKED:
            self.diff_text_edit.setText(f"'{file_path}' 是未跟踪的文件。\n\n无法显示与仓库的差异。")
            self.diff_text_edit.setPlaceholderText("")
        elif self.git_handler:
            staged_diff = (section_type == STATUS_STAGED)
            self.diff_text_edit.setPlaceholderText(f"正在加载 '{os.path.basename(file_path)}' 的差异...");
            QApplication.processEvents() # Update UI immediately

            # Use execute_command_async directly for diff display as it's a specific view action
            diff_command = ["git", "diff"]
            if staged_diff: diff_command.append("--cached")
            diff_command.extend(["--", shlex.quote(file_path)]) # Use shlex.quote explicitly for path

            self.git_handler.execute_command_async(diff_command, self._on_diff_received)
        else:
            self.diff_text_edit.setText("❌ 内部错误：Git 处理程序不可用。")
            self.diff_text_edit.setPlaceholderText("")


    @pyqtSlot(int, str, str)
    def _on_diff_received(self, return_code, stdout, stderr):
        """处理异步 git diff 的结果，并进行格式化显示"""
        if not self.diff_text_edit: return

        self.diff_text_edit.setPlaceholderText("") # Clear loading placeholder

        if return_code == 0:
            if stdout.strip():
                self._display_formatted_diff(stdout) # Call the helper
            else:
                self.diff_text_edit.setText("文件无差异。")
        else:
            error_message = f"❌ 获取差异失败:\n{stderr}"
            self.diff_text_edit.setText(error_message)
            logging.error(f"Git diff failed: RC={return_code}, Err:{stderr}")

    def _display_formatted_diff(self, diff_text: str):
        """格式化显示差异内容，高亮增减行"""
        if not self.diff_text_edit: return

        self.diff_text_edit.clear()
        cursor = self.diff_text_edit.textCursor()

        default_format = self.diff_text_edit.currentCharFormat()
        add_format = QTextCharFormat(default_format); add_format.setForeground(QColor("darkGreen"))
        del_format = QTextCharFormat(default_format); del_format.setForeground(QColor("red"))
        header_format = QTextCharFormat(default_format); header_format.setForeground(QColor("gray"))

        self.diff_text_edit.setFontFamily("Courier New") # Ensure monospace font

        lines = diff_text.splitlines()
        for line in lines:
            fmt_to_apply = default_format

            # Check line prefixes for formatting
            if line.startswith('diff ') or line.startswith('index ') or line.startswith('---') or line.startswith('+++') or line.startswith('@@ '):
                fmt_to_apply = header_format
            elif line.startswith('+'):
                fmt_to_apply = add_format
            elif line.startswith('-'):
                fmt_to_apply = del_format
            # Lines not starting with these prefixes will use the default_format

            # Apply format and insert text
            cursor.insertText(line, fmt_to_apply)
            cursor.insertText("\n", default_format) # Apply default format to newline

        cursor.movePosition(QTextCursor.MoveOperation.Start) # Scroll to top
        self.diff_text_edit.setTextCursor(cursor)
        self.diff_text_edit.ensureCursorVisible()


    # --- Branch List Actions ---
    @pyqtSlot(QListWidgetItem)
    def _branch_double_clicked(self, item: QListWidgetItem):
        # Validity check inside _check_repo_and_warn
        if not item or not self._check_repo_and_warn(): return
        branch_name = item.text().strip();
        if branch_name.startswith("remotes/"): self._show_information("操作无效", f"不能直接切换到远程跟踪分支 '{branch_name}'。"); return
        if item.font().bold():
             logging.info(f"Already on branch '{branch_name}'.");
             if self.status_bar: self.status_bar.showMessage(f"已在分支 '{branch_name}'", 2000);
             return
        reply = QMessageBox.question(self, "切换分支", f"确定要切换到本地分支 '{branch_name}' 吗？\n\n未提交的更改将会被携带。", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel, QMessageBox.StandardButton.Yes)
        if reply == QMessageBox.StandardButton.Yes:
             logging.info(f"请求切换到分支: {branch_name}")
             self._run_command_list_sequentially([f"git checkout {shlex.quote(branch_name)}"])


    @pyqtSlot()
    def _create_branch_dialog(self):
        if not self._check_repo_and_warn(): return
        branch_name, ok = QInputDialog.getText(self, "创建新分支", "输入新分支的名称:", QLineEdit.EchoMode.Normal)
        if ok and branch_name:
            clean_name = branch_name.strip();
            # Basic validation for branch names (simplified regex, git allows more)
            if not clean_name or re.search(r'[\s\~\^\:\?\*\[\\@\{]', clean_name):
                 self._show_warning("创建失败", "分支名称无效。\n\n分支名称不能包含空格或特殊字符如 ~^:?*[\\@{。")
                 return
            logging.info(f"请求创建新分支: {clean_name}");
            self._run_command_list_sequentially([f"git branch {shlex.quote(clean_name)}"])
        elif ok:
            self._show_warning("创建失败", "分支名称不能为空。")


    @pyqtSlot(QPoint)
    def _show_branch_context_menu(self, pos: QPoint):
        """显示分支列表的右键上下文菜单"""
        # Validity check inside _check_repo_and_warn
        if not self._check_repo_and_warn() or not self.branch_list_widget: return
        item = self.branch_list_widget.itemAt(pos);
        if not item: return
        menu = QMenu(); branch_name = item.text().strip(); is_remote = branch_name.startswith("remotes/"); is_current = item.font().bold(); added_action = False

        # Actions for local branches
        if not is_current and not is_remote:
            checkout_action = QAction(f"切换到 '{branch_name}'", self)
            checkout_action.triggered.connect(lambda checked=False, b=branch_name: self._run_command_list_sequentially([f"git checkout {shlex.quote(b)}"]))
            menu.addAction(checkout_action); added_action = True

            delete_action = QAction(f"删除本地分支 '{branch_name}'...", self)
            delete_action.triggered.connect(lambda checked=False, b=branch_name: self._delete_branch_dialog(b))
            menu.addAction(delete_action); added_action = True

        # Actions for remote branches
        if is_remote:
             remote_parts = branch_name.split('/', 2);
             if len(remote_parts) == 3:
                 remote_name = remote_parts[1];
                 remote_branch_name = remote_parts[2];
                 # Option to checkout remote branch into a new local branch
                 checkout_remote_action = QAction(f"基于 '{branch_name}' 创建并切换到本地分支...", self)
                 checkout_remote_action.triggered.connect(lambda checked=False, rbn=remote_branch_name: self._create_and_checkout_branch_from_dialog(rbn, branch_name)) # Pass suggest name and remote ref
                 menu.addAction(checkout_remote_action); added_action = True

                 # Option to delete remote branch
                 delete_remote_action = QAction(f"删除远程分支 '{remote_name}/{remote_branch_name}'...", self)
                 delete_remote_action.triggered.connect(lambda checked=False, rn=remote_name, rbn=remote_branch_name: self._delete_remote_branch_dialog(rn, rbn))
                 menu.addAction(delete_remote_action); added_action = True

        if added_action: menu.exec(self.branch_list_widget.mapToGlobal(pos))
        else: logging.debug(f"No applicable context actions for branch item: {branch_name}")


    def _delete_branch_dialog(self, branch_name: str):
        """Confirm and delete local branch"""
        # Validity check inside _check_repo_and_warn
        if not self._check_repo_and_warn() or not branch_name or branch_name.startswith("remotes/"):
            logging.error(f"Invalid local branch name for deletion: {branch_name}"); return
        reply = QMessageBox.warning(self, "确认删除本地分支", f"确定要删除本地分支 '{branch_name}' 吗？\n\n此操作通常不可撤销！", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel, QMessageBox.StandardButton.Cancel)
        if reply == QMessageBox.StandardButton.Yes:
             logging.info(f"请求删除本地分支: {branch_name} (using -d)")
             self._run_command_list_sequentially([f"git branch -d {shlex.quote(branch_name)}"])

    def _delete_remote_branch_dialog(self, remote_name: str, branch_name: str):
        """Confirm and delete remote branch"""
        # Validity check inside _check_repo_and_warn
        if not self._check_repo_and_warn() or not remote_name or not branch_name:
            logging.error(f"Invalid remote/branch name for deletion: {remote_name}/{branch_name}"); return
        reply = QMessageBox.warning(self, "确认删除远程分支", f"确定要从远程仓库 '{remote_name}' 删除分支 '{branch_name}' 吗？\n\n将执行: git push {remote_name} --delete {branch_name}\n\n此操作通常不可撤销！", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel, QMessageBox.StandardButton.Cancel)
        if reply == QMessageBox.StandardButton.Yes:
            logging.info(f"请求删除远程分支: {remote_name}/{branch_name}")
            self._run_command_list_sequentially([f"git push {shlex.quote(remote_name)} --delete {shlex.quote(branch_name)}"])

    def _create_and_checkout_branch_from_dialog(self, suggest_name: str, start_point: str):
         """Prompt for new branch name and create/checkout from a start point"""
         if not self._check_repo_and_warn(): return
         branch_name, ok = QInputDialog.getText(self, "创建并切换本地分支", f"输入新本地分支的名称 (基于 '{start_point}'):", QLineEdit.EchoMode.Normal, suggest_name)
         if ok: # ok is True even if text is empty
            clean_name = branch_name.strip()
            if not clean_name:
                 self._show_warning("操作取消", "名称不能为空。")
                 return
            # Basic validation, slightly more permissive than git itself but prevents common issues
            # Allow letters, numbers, underscore, dot, slash, hyphen
            if not re.match(r'^[a-zA-Z0-9_./-]+$', clean_name):
                 self._show_warning("操作失败", "分支名称包含无效字符。\n\n请使用字母、数字、下划线、斜杠、连字符或点号。")
                 return

            logging.info(f"请求创建并切换到分支: {clean_name} (基于 {start_point})");
            self._run_command_list_sequentially([f"git checkout -b {shlex.quote(clean_name)} {shlex.quote(start_point)}"])


    # --- Log View Actions ---
    @pyqtSlot()
    def _log_selection_changed(self):
        """当日志表格中的选择发生变化时，加载并显示 Commit 详情"""
        # Validity check inside _check_repo_and_warn
        if not self._check_repo_and_warn("仓库无效，无法显示提交详情。") or not self.log_table_widget or not self.commit_details_textedit or not self.git_handler:
             self.commit_details_textedit.clear()
             self.commit_details_textedit.setPlaceholderText("选中上方提交记录以查看详情...");
             return

        selected_items = self.log_table_widget.selectedItems();
        self.commit_details_textedit.clear() # Always clear on selection change

        if not selected_items:
             self.commit_details_textedit.setPlaceholderText("选中上方提交记录以查看详情...");
             return

        # Get the selected row index. We only process the first selected row.
        selected_row = self.log_table_widget.currentRow();
        if selected_row < 0:
             self.commit_details_textedit.setPlaceholderText("请选择一个提交记录。"); return

        # Get the commit hash from the first column (using constant)
        hash_item = self.log_table_widget.item(selected_row, LOG_COL_COMMIT);
        if hash_item:
            # Prefer full hash from UserRole, fallback to displayed text if necessary
            commit_hash = hash_item.data(Qt.ItemDataRole.UserRole)
            if not commit_hash: commit_hash = hash_item.text().strip() # Fallback

            if commit_hash:
                logging.debug(f"Log selection changed, requesting details for commit: {commit_hash}")
                self.commit_details_textedit.setPlaceholderText(f"正在加载 Commit '{commit_hash[:7]}...' 的详情...");
                QApplication.processEvents() # Update UI immediately

                # Use execute_command_async directly for commit details display
                # git show shows commit details and diff for that commit
                self.git_handler.execute_command_async(["git", "show", shlex.quote(commit_hash)], self._on_commit_details_received)
            else:
                self.commit_details_textedit.setPlaceholderText("无法获取选中提交的 Hash.");
                logging.error(f"无法从表格项获取有效 Hash (Row: {selected_row}).")
        else:
            self.commit_details_textedit.setPlaceholderText("无法确定选中的提交项.");
            logging.error(f"无法在日志表格中找到行 {selected_row} 的第 {LOG_COL_COMMIT} 列项。")


    @pyqtSlot(int, str, str)
    def _on_commit_details_received(self, return_code, stdout, stderr):
        """处理异步 git show (commit details) 的结果"""
        if not self.commit_details_textedit: return
        self.commit_details_textedit.setPlaceholderText(""); # Clear loading placeholder

        if return_code == 0:
            if stdout.strip():
                self.commit_details_textedit.setText(stdout)
            else:
                 self.commit_details_textedit.setText("未获取到提交详情。")
        else:
            error_message = f"❌ 获取提交详情失败:\n{stderr}"
            self.commit_details_textedit.setText(error_message)
            logging.error(f"获取 Commit 详情失败: RC={return_code}, Error: {stderr}")


    # --- Direct Action Slots (Using Runner) ---
    # These methods now build commands and call the sequential runner
    # _stage_all, _unstage_all, _stage_files, _unstage_files, _create_branch_dialog,
    # _delete_branch_dialog, _delete_remote_branch_dialog,
    # _create_and_checkout_branch_from_dialog, _run_switch_branch, _run_list_remotes
    # all use the _run_command_list_sequentially helper and include repo validity checks.


    @pyqtSlot()
    def _run_switch_branch(self): # Direct Execution (Dialog)
        if not self._check_repo_and_warn(): return
        # Fetch current local branches to suggest
        current_branches = []
        if self.branch_list_widget:
             for i in range(self.branch_list_widget.count()):
                  item = self.branch_list_widget.item(i)
                  # Filter out remote branches
                  if item and not item.text().strip().startswith("remotes/"):
                       current_branches.append(item.text().strip())

        # Use QInputDialog.getItem which allows selection from a list or typing
        branch_name, ok = QInputDialog.getItem(
             self, "切换分支", "选择或输入要切换到的本地分支名称:",
             current_branches, # List of suggestions
             0,              # Default selected index (0 is first item)
             True            # Allow user to type a new value
        )

        if ok and branch_name:
            clean_name = branch_name.strip()
            if not clean_name:
                 self._show_warning("操作取消", "名称不能为空。")
                 return
            # No validation needed here, git checkout handles it
            self._run_command_list_sequentially([f"git checkout {shlex.quote(clean_name)}"])


    @pyqtSlot()
    def _run_list_remotes(self):
        if not self._check_repo_and_warn(): return
        # This action is simple and doesn't need complex sequence, but use the runner for consistency
        # Use git remote -v to list remotes with URLs
        self._run_command_list_sequentially(["git remote -v"], refresh_on_success=False) # Don't refresh all views for this


    # --- Settings Dialog Slot ---
    @pyqtSlot()
    def _open_settings_dialog(self):
        """打开全局 Git 配置对话框"""
        dialog = SettingsDialog(self)
        current_name = ""
        current_email = ""
        # Fetch current global config to pre-populate the dialog (using sync call for simplicity here)
        if self.git_handler:
            try:
                 # Use execute_command_sync for quick config fetches
                 name_result = self.git_handler.execute_command_sync(["git", "config", "--global", "user.name"])
                 email_result = self.git_handler.execute_command_sync(["git", "config", "--global", "user.email"])
                 current_name = name_result.stdout.strip() if name_result.returncode == 0 else ""
                 current_email = email_result.stdout.strip() if email_result.returncode == 0 else ""
                 dialog.set_data({"user.name": current_name, "user.email": current_email})
            except Exception as e:
                 logging.warning(f"Failed to fetch global config: {e}")
                 # Dialog will open with empty fields

        if dialog.exec():
            config_data = dialog.get_data()
            commands_to_run = []

            # Use shlex.quote for potentially tricky values and strip whitespace
            name_val = config_data.get("user.name")
            email_val = config_data.get("user.email")

            # Only add commands if values are provided (or potentially if different from initial - but simpler to just set if provided)
            # Check if values are None (meaning the user unchecked the checkbox in the dialog) or empty string after strip
            # An empty string for user.name or user.email is valid to unset it.
            # git config --global user.name "" will unset it
            if name_val is not None: commands_to_run.append(f"git config --global user.name {shlex.quote(name_val.strip())}")
            if email_val is not None: commands_to_run.append(f"git config --global user.email {shlex.quote(email_val.strip())}")

            if commands_to_run:
                 confirmation_msg = "将执行以下全局 Git 配置命令:\n\n" + "\n".join(commands_to_run) + "\n\n确定吗？"
                 reply = QMessageBox.question(self, "应用全局配置", confirmation_msg, QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel, QMessageBox.StandardButton.Yes)
                 if reply == QMessageBox.StandardButton.Yes:
                     logging.info(f"Executing global config commands: {commands_to_run}")
                     if self.git_handler:
                         # Use the sequential runner for execution
                         self._run_command_list_sequentially(commands_to_run, refresh_on_success=False) # No need to refresh views after config
                     else:
                         logging.error("GitHandler unavailable for settings.")
                         QMessageBox.critical(self, "错误", "无法执行配置命令。")
                 else:
                     self._show_information("操作取消", "未应用全局配置更改。")
            else:
                 self._show_information("无更改", "未检测到有效的用户名或邮箱信息变更。")


    @pyqtSlot()
    def _show_about_dialog(self):
        """显示关于对话框"""
        try: version = self.windowTitle().split('v')[-1].strip()
        except: version = "N/A"
        # Using triple quotes for multi-line string is cleaner
        about_text = f"""
        **简易 Git GUI**

        版本: {version}

        这是一个简单的 Git GUI 工具，用于学习和执行 Git 命令。

        **开发日志:**
        v1.0 - 初始版本 (仓库选择, 状态, Diff, Log, 命令输入)
        v1.1 - 增加暂存/撤销暂存单个文件
        v1.2 - 增加创建/切换/删除分支
        v1.3 - 提交功能
        v1.4 - 增加 Pull/Push/Fetch 按钮
        v1.5 - 增加 Git 全局配置对话框
        v1.6 - 异步执行命令，优化UI响应
        v1.7 - 增加命令序列构建器和快捷键功能

        本项目是学习 Qt6 和 Git 命令交互的实践项目
        """
        QMessageBox.about(self, "关于 简易 Git GUI", about_text)


    def closeEvent(self, event):
        """处理窗口关闭事件"""
        logging.info("应用程序关闭请求。")
        try:
            # Check for pending operations - this is important!
            if self.git_handler and hasattr(self.git_handler, 'active_operations') and self.git_handler.active_operations:
                 active_count = len(self.git_handler.active_operations)
                 if active_count > 0:
                      logging.warning(f"窗口关闭时仍有 {active_count} 个 Git 操作可能在后台运行。")
                      # Optional: Add a confirmation dialog here before accepting the event
                      # reply = QMessageBox.question(self, "未完成的操作", f"有 {active_count} 个Git操作正在进行中。强制关闭可能导致问题。确定要退出吗？", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
                      # if reply == QMessageBox.StandardButton.No:
                      #     event.ignore()
                      #     return
        except Exception as e: logging.exception("关闭窗口时检查 Git 操作出错。")
        logging.info("应用程序正在关闭。")
        event.accept()

# --- Main Execution Block ---
if __name__ == '__main__':
    # Using basicConfig is fine for simple logging
    logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - [%(levelname)s] - %(filename)s:%(lineno)d - %(message)s')
    logging.info("应用程序启动...")
    app = QApplication(sys.argv)

    # Improve appearance slightly
    app.setStyle("Fusion")

    mainWin = MainWindow()
    mainWin.show()
    sys.exit(app.exec())