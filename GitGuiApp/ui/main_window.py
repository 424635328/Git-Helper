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
    QSpacerItem, QFrame # Added QSpacerItem, QFrame
)
from PyQt6.QtGui import QAction, QKeySequence, QColor, QTextCursor, QIcon, QFont, QStandardItemModel, QDesktopServices # Added QDesktopServices
from PyQt6.QtCore import Qt, pyqtSlot, QSize, QTimer, QModelIndex, QUrl, QPoint, QItemSelection # Added QItemSelection

# Assuming these modules are in the same parent directory structure
from .dialogs import ShortcutDialog, SettingsDialog
from .shortcut_manager import ShortcutManager
from .status_tree_model import StatusTreeModel, STATUS_STAGED, STATUS_UNSTAGED, STATUS_UNTRACKED # Import constants
from core.git_handler import GitHandler
from core.db_handler import DatabaseHandler


class MainWindow(QMainWindow):
    """Git GUI 主窗口"""
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Git GUI v1.7") # Update version
        self.setGeometry(100, 100, 1200, 900) # Even wider default size

        self.db_handler = DatabaseHandler()
        self.git_handler = GitHandler()
        self.shortcut_manager = ShortcutManager(self, self.db_handler, self.git_handler)

        self.current_command_sequence = []
        self.command_buttons = {}

        # UI Element Placeholders
        self.output_display = None
        self.command_input = None
        self.sequence_display = None
        self.shortcut_list_widget = None
        self.repo_label = None
        self.status_bar = None
        self.branch_list_widget = None
        self.status_tree_view = None
        self.status_tree_model = None
        self.log_table_widget = None
        self.diff_text_edit = None
        self.main_tab_widget = None
        self.commit_details_textedit = None # New textedit for commit details

        self._init_ui()
        self.shortcut_manager.load_and_register_shortcuts()
        self._update_repo_status() # Initial status update and view refresh

        logging.info("主窗口初始化完成。")

    def _init_ui(self):
        """初始化用户界面 (状态交互, 分支交互, 日志详情)"""
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)

        # --- Repository Selection Area ---
        repo_layout = QHBoxLayout()
        self.repo_label = QLabel("当前仓库: (未选择)")
        self.repo_label.setToolTip("当前操作的 Git 仓库路径")
        repo_layout.addWidget(self.repo_label, 1)
        select_repo_button = QPushButton("选择仓库")
        select_repo_button.setToolTip("选择仓库目录")
        select_repo_button.clicked.connect(self._select_repository)
        repo_layout.addWidget(select_repo_button)
        main_layout.addLayout(repo_layout)

        # --- Main Splitter ---
        splitter = QSplitter(Qt.Orientation.Horizontal)
        main_layout.addWidget(splitter, 1)

        # --- Left Panel ---
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(5, 0, 5, 5)
        left_layout.setSpacing(6)
        splitter.addWidget(left_panel)

        # Command Buttons (Keep as is, tooltips updated maybe)
        # FIX: Corrected typo in lambda calls from _run_command_if_valid_repo to _execute_command_if_valid_repo
        command_buttons_layout_1 = QHBoxLayout()
        self._add_command_button(command_buttons_layout_1, "Status", "刷新状态/文件视图 (Tab)", self._refresh_status_view)
        self._add_command_button(command_buttons_layout_1, "Add .", "暂存所有更改 (git add .)", lambda: self._execute_command_if_valid_repo(["git", "add", "."]))
        self._add_command_button(command_buttons_layout_1, "Add...", "暂存选中文件 (需手动输入)", self._add_files)
        left_layout.addLayout(command_buttons_layout_1)

        command_buttons_layout_2 = QHBoxLayout()
        self._add_command_button(command_buttons_layout_2, "Commit...", "提交暂存更改", self._add_commit)
        self._add_command_button(command_buttons_layout_2, "Commit -a...", "暂存所有已跟踪文件并提交", self._add_commit_am)
        self._add_command_button(command_buttons_layout_2, "Log", "刷新提交历史 (Tab)", self._refresh_log_view)
        left_layout.addLayout(command_buttons_layout_2)

        more_commands_layout = QHBoxLayout()
        # FIX: Corrected typo in lambda calls from _run_command_if_valid_repo to _execute_command_if_valid_repo
        self._add_command_button(more_commands_layout, "Pull", "拉取 (git pull)", lambda: self._execute_command_if_valid_repo(["git", "pull"]))
        self._add_command_button(more_commands_layout, "Push", "推送 (git push)", lambda: self._execute_command_if_valid_repo(["git", "push"]))
        self._add_command_button(more_commands_layout, "Fetch", "获取 (git fetch)", lambda: self._execute_command_if_valid_repo(["git", "fetch"]))
        left_layout.addLayout(more_commands_layout)

        # Command Sequence Builder (Keep as is)
        left_layout.addWidget(QLabel("命令序列构建器:"))
        self.sequence_display = QTextEdit()
        self.sequence_display.setReadOnly(True)
        self.sequence_display.setPlaceholderText("...")
        self.sequence_display.setFixedHeight(80)
        left_layout.addWidget(self.sequence_display)

        sequence_actions_layout = QHBoxLayout()
        execute_button = QPushButton("执行")
        execute_button.setToolTip("执行上方序列")
        execute_button.setStyleSheet("background-color: lightgreen;")
        execute_button.clicked.connect(self._execute_sequence)
        self.command_buttons['execute'] = execute_button
        clear_button = QPushButton("清空")
        clear_button.setToolTip("清空上方序列")
        clear_button.clicked.connect(self._clear_sequence)
        self.command_buttons['clear'] = clear_button
        save_shortcut_button = QPushButton("保存")
        save_shortcut_button.setToolTip("存为快捷键")
        save_shortcut_button.clicked.connect(self.shortcut_manager.save_shortcut_dialog)
        self.command_buttons['save'] = save_shortcut_button
        sequence_actions_layout.addWidget(execute_button)
        sequence_actions_layout.addWidget(clear_button)
        sequence_actions_layout.addWidget(save_shortcut_button)
        left_layout.addLayout(sequence_actions_layout)

        # --- Branch List ---
        branch_label_layout = QHBoxLayout()
        branch_label_layout.addWidget(QLabel("分支列表:"))
        branch_label_layout.addStretch()
        create_branch_button = QPushButton("+ 新分支") # New button
        create_branch_button.setToolTip("创建新的本地分支")
        create_branch_button.clicked.connect(self._create_branch_dialog)
        self.command_buttons['create_branch'] = create_branch_button # Manage state
        branch_label_layout.addWidget(create_branch_button)
        left_layout.addLayout(branch_label_layout) # Add layout with button

        self.branch_list_widget = QListWidget()
        self.branch_list_widget.setToolTip("双击切换分支, 右键删除")
        self.branch_list_widget.itemDoubleClicked.connect(self._branch_double_clicked)
        self.branch_list_widget.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu) # Enable context menu
        self.branch_list_widget.customContextMenuRequested.connect(self._show_branch_context_menu) # Connect signal
        left_layout.addWidget(self.branch_list_widget, 1)

        # Saved Shortcuts List
        left_layout.addWidget(QLabel("快捷键组合:"))
        self.shortcut_list_widget = QListWidget()
        self.shortcut_list_widget.setToolTip("双击执行，右键删除")
        self.shortcut_list_widget.itemDoubleClicked.connect(self.shortcut_manager.execute_shortcut_from_list)
        self.shortcut_list_widget.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.shortcut_list_widget.customContextMenuRequested.connect(self.shortcut_manager.show_shortcut_context_menu)
        left_layout.addWidget(self.shortcut_list_widget, 1)


        # --- Right Panel (Tabs + Command Input) ---
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(0)
        splitter.addWidget(right_panel)

        # Tab Widget
        self.main_tab_widget = QTabWidget()
        right_layout.addWidget(self.main_tab_widget, 1)

        # -- Tab 1: Status / Files --
        status_tab_widget = QWidget()
        status_tab_layout = QVBoxLayout(status_tab_widget)
        status_tab_layout.setContentsMargins(5, 5, 5, 5)
        status_tab_layout.setSpacing(4)
        self.main_tab_widget.addTab(status_tab_widget, "状态 / 文件")

        status_action_layout = QHBoxLayout()
        stage_all_button = QPushButton("全部暂存 (+)")
        stage_all_button.setToolTip("git add .")
        stage_all_button.clicked.connect(self._stage_all)
        self.command_buttons['stage_all'] = stage_all_button
        unstage_all_button = QPushButton("全部撤销暂存 (-)")
        unstage_all_button.setToolTip("git reset HEAD --")
        unstage_all_button.clicked.connect(self._unstage_all)
        self.command_buttons['unstage_all'] = unstage_all_button
        status_action_layout.addWidget(stage_all_button)
        status_action_layout.addWidget(unstage_all_button)
        status_action_layout.addStretch()
        status_tab_layout.addLayout(status_action_layout)

        self.status_tree_view = QTreeView()
        self.status_tree_model = StatusTreeModel()
        self.status_tree_view.setModel(self.status_tree_model)
        self.status_tree_view.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.status_tree_view.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.status_tree_view.header().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.status_tree_view.header().setStretchLastSection(False)
        self.status_tree_view.setColumnWidth(0, 100) # Initial width
        self.status_tree_view.setAlternatingRowColors(True)
        self.status_tree_view.selectionModel().selectionChanged.connect(self._status_selection_changed)
        self.status_tree_view.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu) # Enable context menu
        self.status_tree_view.customContextMenuRequested.connect(self._show_status_context_menu) # Connect signal
        status_tab_layout.addWidget(self.status_tree_view, 1)

        # -- Tab 2: Commit History --
        log_tab_widget = QWidget()
        log_tab_layout = QVBoxLayout(log_tab_widget)
        log_tab_layout.setContentsMargins(5, 5, 5, 5)
        log_tab_layout.setSpacing(4)
        self.main_tab_widget.addTab(log_tab_widget, "提交历史 (Log)")

        # Log Table
        self.log_table_widget = QTableWidget()
        self.log_table_widget.setColumnCount(4)
        self.log_table_widget.setHorizontalHeaderLabels(["Commit", "Author", "Date", "Message"])
        self.log_table_widget.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.log_table_widget.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.log_table_widget.verticalHeader().setVisible(False)
        self.log_table_widget.setColumnWidth(0, 80) # Commit hash
        self.log_table_widget.setColumnWidth(1, 140) # Author
        self.log_table_widget.setColumnWidth(2, 100) # Date
        self.log_table_widget.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch) # Message stretches
        self.log_table_widget.itemSelectionChanged.connect(self._log_selection_changed) # Connect selection signal
        log_tab_layout.addWidget(self.log_table_widget, 2) # Give table more stretch factor

        # Separator Line
        separator = QFrame()
        separator.setFrameShape(QFrame.Shape.HLine)
        separator.setFrameShadow(QFrame.Shadow.Sunken)
        log_tab_layout.addWidget(separator)

        # Commit Details Area
        log_tab_layout.addWidget(QLabel("提交详情:"))
        self.commit_details_textedit = QTextEdit() # New textedit for details
        self.commit_details_textedit.setReadOnly(True)
        self.commit_details_textedit.setFontFamily("Courier New")
        self.commit_details_textedit.setPlaceholderText("选中上方提交记录以查看详情...")
        log_tab_layout.addWidget(self.commit_details_textedit, 1) # Give details some stretch factor

        # -- Tab 3: Diff View --
        diff_tab_widget = QWidget()
        diff_tab_layout = QVBoxLayout(diff_tab_widget)
        diff_tab_layout.setContentsMargins(5, 5, 5, 5)
        self.main_tab_widget.addTab(diff_tab_widget, "差异 (Diff)")
        self.diff_text_edit = QTextEdit()
        self.diff_text_edit.setReadOnly(True)
        self.diff_text_edit.setFontFamily("Courier New")
        self.diff_text_edit.setPlaceholderText("选中已更改的文件以查看差异...")
        diff_tab_layout.addWidget(self.diff_text_edit, 1)

        # -- Tab 4: Raw Output --
        output_tab_widget = QWidget()
        output_tab_layout = QVBoxLayout(output_tab_widget)
        output_tab_layout.setContentsMargins(5, 5, 5, 5)
        self.main_tab_widget.addTab(output_tab_widget, "原始输出")
        self.output_display = QTextEdit()
        self.output_display.setReadOnly(True)
        self.output_display.setFontFamily("Courier New")
        self.output_display.setPlaceholderText("Git 命令和命令行输出...")
        output_tab_layout.addWidget(self.output_display, 1)


        # Command Input Area (Below Tabs)
        command_input_container = QWidget()
        command_input_layout = QHBoxLayout(command_input_container)
        command_input_layout.setContentsMargins(5, 3, 5, 5)
        command_input_layout.setSpacing(4)
        command_input_label = QLabel("$")
        self.command_input = QLineEdit()
        self.command_input.setPlaceholderText("输入命令并按 Enter")
        command_font = QFont("Courier New")
        self.command_input.setFont(command_font)
        # Add some styling for better appearance
        command_input_style = """
            QLineEdit {
                background-color: #ffffff;
                border: 1px solid #abadb3;
                border-radius: 2px;
                padding: 4px 6px;
                color: #000000;
            }
            QLineEdit:focus {
                border: 1px solid #0078d4;
            }
            QLineEdit::placeholder {
                color: #a0a0a0;
            }
            QLineEdit:disabled {
                background-color: #f0f0f0;
                color: #a0a0a0;
            }
        """
        self.command_input.setStyleSheet(command_input_style)
        self.command_input.returnPressed.connect(self._execute_command_from_input)
        self.command_buttons['command_input'] = self.command_input # Add input box to buttons dict for busy state
        command_input_layout.addWidget(command_input_label)
        command_input_layout.addWidget(self.command_input)
        right_layout.addWidget(command_input_container)


        # Splitter setup
        splitter.setSizes([int(self.width() * 0.3), int(self.width() * 0.7)]) # Adjust ratio, give more space to right


        # Status Bar
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("就绪")

        # Menu and Toolbar
        self._create_menu()
        self._create_toolbar()

    # --- Menu, Toolbar, Button Creation ---

    def _create_menu(self):
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
        refresh_action = QAction("刷新全部视图", self)
        refresh_action.triggered.connect(self._refresh_all_views)
        repo_menu.addAction(refresh_action)
        self.command_buttons['refresh_action'] = refresh_action # Manage state
        repo_menu.addSeparator()

        create_branch_action = QAction("创建分支(&N)...", self)
        create_branch_action.triggered.connect(self._create_branch_dialog)
        repo_menu.addAction(create_branch_action)
        self.command_buttons['create_branch_menu'] = create_branch_action # Use separate key

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
        toolbar = QToolBar("主要操作")
        toolbar.setIconSize(QSize(24, 24))
        self.addToolBar(toolbar)

        refresh_tb_action = QAction("刷新", self)
        refresh_tb_action.setToolTip("刷新状态、分支和日志视图")
        refresh_tb_action.triggered.connect(self._refresh_all_views)
        toolbar.addAction(refresh_tb_action)
        self.command_buttons['refresh_tb_action'] = refresh_tb_action
        toolbar.addSeparator()

        pull_action = QAction("Pull", self)
        pull_action.triggered.connect(self._run_pull)
        toolbar.addAction(pull_action)
        self.command_buttons['pull_action'] = pull_action

        push_action = QAction("Push", self)
        push_action.triggered.connect(self._run_push)
        toolbar.addAction(push_action)
        self.command_buttons['push_action'] = push_action

        # Fetch is less common on toolbar, but could add
        # fetch_action = QAction("Fetch", self); fetch_action.triggered.connect(self._run_fetch); toolbar.addAction(fetch_action); self.command_buttons['fetch_action_tb'] = fetch_action

        toolbar.addSeparator()

        create_branch_tb_action = QAction("新分支", self)
        create_branch_tb_action.setToolTip("创建新的本地分支")
        create_branch_tb_action.triggered.connect(self._create_branch_dialog)
        toolbar.addAction(create_branch_tb_action)
        self.command_buttons['create_branch_tb'] = create_branch_tb_action

        switch_branch_action_tb = QAction("切换分支...", self)
        switch_branch_action_tb.triggered.connect(self._run_switch_branch) # Use the dialog version
        toolbar.addAction(switch_branch_action_tb)
        self.command_buttons['switch_branch_action_tb'] = switch_branch_action_tb

        list_remotes_action_tb = QAction("远程列表", self)
        list_remotes_action_tb.triggered.connect(self._run_list_remotes)
        toolbar.addAction(list_remotes_action_tb)
        self.command_buttons['list_remotes_action_tb'] = list_remotes_action_tb

        toolbar.addSeparator()

        clear_output_action = QAction("清空原始输出", self)
        clear_output_action.setToolTip("清空'原始输出'标签页")
        clear_output_action.triggered.connect(self.output_display.clear)
        toolbar.addAction(clear_output_action)


    def _add_command_button(self, layout, text, tooltip, slot):
        """Helper to create and add command buttons"""
        button = QPushButton(text)
        button.setToolTip(tooltip)
        button.clicked.connect(slot)
        layout.addWidget(button)
        # Generate a simple key from button text
        button_key = f"button_{text.lower().replace('...', '').replace(' ', '_').replace('/','_')}"
        self.command_buttons[button_key] = button # Store reference
        return button # Return button in case specific styling/config is needed


    # --- 状态更新和 UI 启用/禁用 ---

    def _update_repo_status(self):
        """Update repository display and UI state based on GitHandler validity."""
        repo_path = self.git_handler.get_repo_path()
        is_valid = self.git_handler.is_valid_repo()

        # Display full path or truncated path if too long
        display_path = repo_path if repo_path and len(repo_path) < 60 else f"...{repo_path[-57:]}" if repo_path else "(未选择)"
        self.repo_label.setText(f"当前仓库: {display_path}")

        self._update_ui_enable_state(is_valid)

        if is_valid:
            self.repo_label.setStyleSheet("") # Reset style
            self.status_bar.showMessage(f"正在加载: {repo_path}", 0) # Show loading status without timeout
            QApplication.processEvents() # Process events to update status bar immediately
            self._refresh_all_views() # Refresh all views if repo is valid
        else:
            self.repo_label.setStyleSheet("color: red;")
            self.status_bar.showMessage("请选择一个有效的 Git 仓库目录", 0) # Persistent message
            # Clear views if repo is invalid
            self.status_tree_model.clear_status()
            self.branch_list_widget.clear()
            self.log_table_widget.setRowCount(0)
            self.diff_text_edit.clear()
            self.commit_details_textedit.clear()
            self.output_display.clear()


    def _update_ui_enable_state(self, enabled: bool):
        """Enable/disable UI elements depending on whether a valid repository is selected."""
        # List keys of elements that depend on a valid repo
        repo_dependent_keys = [
            'execute', 'clear', 'save', # Sequence buttons
            'button_status', 'button_add_.', 'button_add...', 'button_commit...', 'button_commit_-a...', 'button_log', 'button_pull', 'button_push', 'button_fetch', # Command buttons
            'stage_all', 'unstage_all', # Status tab buttons
            'refresh_action', 'refresh_tb_action', # Refresh actions
            'create_branch', 'create_branch_menu', 'create_branch_tb', # Create branch buttons/actions
            'switch_branch_action', 'switch_branch_action_tb', # Switch branch actions
            'list_remotes_action', 'list_remotes_action_tb', # List remotes actions
            'command_input' # Command input line edit
        ]

        for key, item in self.command_buttons.items():
             if key in repo_dependent_keys:
                # Check if item is a widget or an action
                if isinstance(item, QWidget):
                     item.setEnabled(enabled)
                elif isinstance(item, QAction):
                     item.setEnabled(enabled)


        # Enable/disable specific widgets
        self.shortcut_list_widget.setEnabled(enabled)
        self.branch_list_widget.setEnabled(enabled)
        self.status_tree_view.setEnabled(enabled)
        self.log_table_widget.setEnabled(enabled)
        self.diff_text_edit.setEnabled(enabled)
        self.commit_details_textedit.setEnabled(enabled)

        # Enable/disable registered global shortcuts
        self.shortcut_manager.set_shortcuts_enabled(enabled)

        # Ensure certain actions are ALWAYS enabled
        for action in self.findChildren(QAction):
             if action.text() in ["选择仓库(&O)...", "Git 全局配置(&G)...", "退出(&X)", "关于(&A)", "清空原始输出"]:
                action.setEnabled(True)


    # --- Refresh Views ---

    def _refresh_all_views(self):
        """Refresh status, branch list, and log views."""
        if not self.git_handler.is_valid_repo():
            logging.warning("Attempted to refresh views with invalid repo.")
            return

        logging.info("Refreshing Status, Branches, and Log views...")
        self.status_bar.showMessage("正在刷新...", 0) # Show loading status
        QApplication.processEvents() # Update UI immediately

        # Refresh views asynchronously
        self._refresh_status_view()
        self._refresh_branch_list()
        self._refresh_log_view()

    @pyqtSlot()
    def _refresh_status_view(self):
        """Request current repository status asynchronously."""
        if not self.git_handler.is_valid_repo(): return
        logging.debug("Requesting status porcelain...")
        # Disable stage/unstage all buttons while refreshing
        self.command_buttons.get('stage_all', QWidget()).setEnabled(False)
        self.command_buttons.get('unstage_all', QWidget()).setEnabled(False)
        self.git_handler.get_status_porcelain_async(self._on_status_refreshed)


    @pyqtSlot(int, str, str)
    def _on_status_refreshed(self, return_code, stdout, stderr):
        """Slot to handle status porcelain output."""
        if return_code == 0:
            logging.debug("Status porcelain received, populating model...")
            self.status_tree_model.parse_and_populate(stdout)
            self.status_tree_view.expandAll()
            # Adjust column width after populating
            self.status_tree_view.resizeColumnToContents(0)
            self.status_tree_view.setColumnWidth(0, max(100, self.status_tree_view.columnWidth(0))) # Ensure minimum width
            # Enable/disable stage/unstage all buttons based on model content
            self.command_buttons.get('stage_all', QWidget()).setEnabled(self.status_tree_model.unstage_root.rowCount()>0 or self.status_tree_model.untracked_root.rowCount()>0)
            self.command_buttons.get('unstage_all', QWidget()).setEnabled(self.status_tree_model.staged_root.rowCount()>0)

        else:
            logging.error(f"Failed to get status: RC={return_code}, Error: {stderr}")
            self._append_output(f"❌ 获取状态失败:\n{stderr}", QColor("red"))
            self.status_tree_model.clear_status() # Clear status on error
            self.command_buttons.get('stage_all', QWidget()).setEnabled(False) # Disable buttons on error
            self.command_buttons.get('unstage_all', QWidget()).setEnabled(False)

        # Don't clear status message here, let branch update handle it


    @pyqtSlot()
    def _refresh_branch_list(self):
        """Request branch list asynchronously."""
        if not self.git_handler.is_valid_repo(): return
        logging.debug("Requesting formatted branch list...")
        self.git_handler.get_branches_formatted_async(self._on_branches_refreshed)


    @pyqtSlot(int, str, str)
    def _on_branches_refreshed(self, return_code, stdout, stderr):
        """Slot to handle branch list output."""
        self.branch_list_widget.clear()
        current_branch_name = None
        is_valid = self.git_handler.is_valid_repo() # Re-check validity

        if return_code == 0 and is_valid:
            lines = stdout.strip().splitlines()
            logging.debug(f"Branches received: {lines}")
            for line in lines:
                parts = line.strip().split(' ', 1)
                is_current = parts[0] == '*'
                # Handle cases where branch name might contain spaces
                branch_name = parts[1] if len(parts) > 1 else parts[0].lstrip('* ')
                item = QListWidgetItem(branch_name)
                if is_current:
                    current_branch_name = branch_name
                    font = item.font()
                    font.setBold(True)
                    item.setFont(font)
                    item.setForeground(QColor("blue")) # Highlight current branch
                elif branch_name.startswith("remotes/"):
                    item.setForeground(QColor("gray")) # Dim remote branches
                self.branch_list_widget.addItem(item)

            # Select the current branch in the list
            if current_branch_name:
                 items = self.branch_list_widget.findItems(current_branch_name, Qt.MatchFlag.MatchExactly)
                 if items:
                     self.branch_list_widget.setCurrentItem(items[0])

        elif is_valid: # Check if still valid repo even if command failed
            logging.error(f"Failed to get branches: RC={return_code}, Error: {stderr}")
            self._append_output(f"❌ 获取分支列表失败:\n{stderr}", QColor("red"))

        # Update status bar with current branch and repo path
        repo_path_short = self.git_handler.get_repo_path() or "(未选择)"
        if len(repo_path_short) > 40:
             repo_path_short = f"...{repo_path_short[-37:]}" # Truncate long paths for status bar
        branch_display = current_branch_name if current_branch_name else ("(未知分支)" if is_valid else "(无效仓库)")
        self.status_bar.showMessage(f"分支: {branch_display} | 仓库: {repo_path_short}", 0) # Final status message with no timeout

    @pyqtSlot()
    def _refresh_log_view(self):
        """Request commit log asynchronously."""
        if not self.git_handler.is_valid_repo(): return
        logging.debug("Requesting formatted log...")
        self.log_table_widget.setRowCount(0) # Clear current log display
        self.commit_details_textedit.clear() # Clear details too
        # Using --graph format
        self.git_handler.get_log_formatted_async(count=200, finished_slot=self._on_log_refreshed) # Increase count for more history


    @pyqtSlot(int, str, str)
    def _on_log_refreshed(self, return_code, stdout, stderr):
        """Slot to handle log output."""
        if return_code == 0:
            lines = stdout.strip().splitlines()
            logging.debug(f"Log received ({len(lines)} entries). Populating table...")
            self.log_table_widget.setRowCount(len(lines))
            monospace_font = QFont("Courier New") # Font for graph/hash/message

            for row, line in enumerate(lines):
                line = line.strip()
                if not line: continue # Skip empty lines

                first_tab_index = line.find('\t')

                if first_tab_index == -1:
                    # Likely a purely graphical line or malformed without tabs (skip these for table)
                    # logging.debug(f"Skipping log line without tab: {repr(line)}") # Too noisy
                    # Optional: Add these lines to the raw output only
                    continue

                # Split into two main parts: before the first tab (graph+hash) and after (author, date, subject)
                graph_hash_part = line[:first_tab_index].strip()
                rest_of_line = line[first_tab_index + 1:].strip() # Strip leading tab and whitespace

                # Split the rest of the line into author, date, subject using 2 more tabs
                parts = rest_of_line.split('\t', 2) # Split into 3 parts: author, date, subject

                if len(parts) == 3:
                    author, date, message = parts

                    # Extract hash from graph_hash_part. It's usually the last sequence of hex chars.
                    # Use regex for robustness against varying graph symbols
                    hash_match = re.search(r'([a-fA-F0-9]+)$', graph_hash_part)
                    commit_hash = hash_match.group(1) if hash_match else graph_hash_part.split()[-1] if graph_hash_part else "N/A" # Fallback logic

                    # The graph part is what's left of graph_hash_part before the hash
                    graph_part = graph_hash_part[:-len(commit_hash)].rstrip() if graph_hash_part.endswith(commit_hash) else graph_hash_part
                    display_message = f"{graph_part} {message}".strip() # Combine graph text and subject

                    # Create QTableWidgetItems
                    hash_item = QTableWidgetItem(commit_hash) # Display only hash in hash column
                    hash_item.setData(Qt.ItemDataRole.UserRole, commit_hash) # Store full hash or part for details retrieval later

                    author_item = QTableWidgetItem(author)
                    date_item = QTableWidgetItem(date)
                    message_item = QTableWidgetItem(display_message) # Use combined graph/message for message column

                    # Set flags (selectable and enabled)
                    flags = Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled
                    hash_item.setFlags(flags)
                    author_item.setFlags(flags)
                    date_item.setFlags(flags)
                    message_item.setFlags(flags)

                    # Apply monospace font to hash and message items for better alignment of graph text
                    hash_item.setFont(monospace_font)
                    message_item.setFont(monospace_font)


                    # Set items in the table
                    self.log_table_widget.setItem(row, 0, hash_item)
                    self.log_table_widget.setItem(row, 1, author_item)
                    self.log_table_widget.setItem(row, 2, date_item)
                    self.log_table_widget.setItem(row, 3, message_item)

                else:
                     # Handle lines that have tabs but couldn't be split into 3 parts after the first tab
                     logging.warning(f"Could not parse log line after first tab: {repr(line)} -> {repr(rest_of_line)}")
                     # Put the raw line in the message column as a fallback
                     raw_item = QTableWidgetItem(line.strip())
                     raw_item.setFlags(Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled)
                     self.log_table_widget.setItem(row, 3, raw_item)
                     # Maybe also set other columns as empty or "N/A" if needed
                     self.log_table_widget.setItem(row, 0, QTableWidgetItem("N/A"))
                     self.log_table_widget.setItem(row, 1, QTableWidgetItem("N/A"))
                     self.log_table_widget.setItem(row, 2, QTableWidgetItem("N/A"))


        else:
            logging.error(f"Failed to get log: RC={return_code}, Error: {stderr}")
            self._append_output(f"❌ 获取提交历史失败:\n{stderr}", QColor("red"))

        # The branch refresh handles the final status bar message


    # --- Repository Selection ---

    def _select_repository(self):
        """Open a dialog to select a Git repository directory."""
        start_path = self.git_handler.get_repo_path()
        # If no repo set, start from user's home directory
        if not start_path or not os.path.isdir(start_path):
            start_path = os.path.expanduser("~")

        dir_path = QFileDialog.getExistingDirectory(self, "选择 Git 仓库目录", start_path)

        if dir_path:
            # Clear previous state before setting new repo
            self.output_display.clear()
            self.diff_text_edit.clear()
            self.commit_details_textedit.clear()
            self.current_command_sequence = []
            self._update_sequence_display()
            self.status_tree_model.clear_status()
            self.branch_list_widget.clear()
            self.log_table_widget.setRowCount(0)


            try:
                self.git_handler.set_repo_path(dir_path)
                self._update_repo_status() # This will trigger refresh_all_views if valid
                logging.info(f"用户选择了新的仓库目录: {dir_path}")
            except ValueError as e:
                QMessageBox.warning(self, "选择仓库失败", str(e))
                logging.error(f"设置仓库路径失败: {e}")
                self.git_handler.set_repo_path(None) # Ensure internal state is invalid
                self._update_repo_status() # Update UI state to invalid


    # --- Command Button Slots ---
    # These slots are connected to the command buttons in _init_ui

    def _add_simple_command(self, command_str: str):
        """Add a simple command string to the sequence."""
        logging.debug(f"添加简单命令: {repr(command_str)}")
        self.current_command_sequence.append(command_str)
        self._update_sequence_display()

    # Renamed _add_status to reflect it's a refresh action now
    # This is already handled by the "Status" button connect to _refresh_status_view

    def _add_files(self):
        """Open input dialog to specify files for staging."""
        # Future: Use file dialog or selection from tree view
        files, ok = QInputDialog.getText(
            self,
            "暂存文件",
            "输入要暂存的文件/目录 (用空格分隔):",
            QLineEdit.EchoMode.Normal # Or QLineEdit.Normal
        )
        if ok and files:
            # Use shlex.split to handle paths with spaces or quotes
            file_list = shlex.split(files.strip())
            self._stage_files(file_list) # Use the dedicated stage_files method
        elif ok: # User pressed OK but entered nothing
             QMessageBox.information(self, "提示", "未输入任何文件路径。")


    def _add_commit(self):
        """Open input dialog for commit message and perform commit."""
        commit_msg, ok = QInputDialog.getText(
            self,
            "提交更改",
            "输入提交信息:",
            QLineEdit.EchoMode.Normal # Or QLineEdit.Normal
        )
        if ok: # Check if OK was pressed, even if message is empty
            if commit_msg.strip():
                # Use shlex.quote to handle messages with special characters
                safe_msg = shlex.quote(commit_msg.strip())
                # FIX: Corrected typo
                self._execute_command_if_valid_repo(["git", "commit", "-m", safe_msg])
            else:
                QMessageBox.warning(self, "提交失败", "提交信息不能为空。")


    def _add_commit_am(self):
        """Open input dialog for commit message and perform commit -am."""
        commit_msg, ok = QInputDialog.getText(
            self,
            "暂存所有已跟踪文件并提交", # More accurate tooltip
            "输入提交信息:",
            QLineEdit.EchoMode.Normal # Or QLineEdit.Normal
        )
        if ok: # Check if OK was pressed, even if message is empty
             if commit_msg.strip():
                # Use shlex.quote to handle messages with special characters
                safe_msg = shlex.quote(commit_msg.strip())
                # FIX: Corrected typo
                self._execute_command_if_valid_repo(["git", "commit", "-am", safe_msg])
             else:
                QMessageBox.warning(self, "提交失败", "提交信息不能为空。")


    # This button slot is already handled by the "Log" button connected to _refresh_log_view
    # def _refresh_log_view_button(self):
    #     self._refresh_log_view()


    # --- Sequence Operations ---

    def _update_sequence_display(self):
        """Update the QTextEdit displaying the command sequence."""
        self.sequence_display.setText("\n".join(self.current_command_sequence))

    def _clear_sequence(self):
        """Clear the current command sequence."""
        self.current_command_sequence = []
        self._update_sequence_display()
        self.status_bar.showMessage("命令序列已清空", 2000) # Show for 2 seconds
        logging.info("命令序列已清空。")

    def _execute_sequence(self):
        """Execute the commands in the current sequence one by one."""
        if not self.git_handler.is_valid_repo():
            QMessageBox.critical(self, "错误", "请先选择一个有效的 Git 仓库。")
            return
        if not self.current_command_sequence:
            QMessageBox.information(self, "提示", "命令序列为空，请先添加命令。")
            return

        # Execute a copy of the sequence list in case it's modified during execution
        sequence_to_run = list(self.current_command_sequence)
        logging.info(f"执行构建的序列: {sequence_to_run}")
        self._run_command_list_sequentially(sequence_to_run)


    # --- Core Command Execution Logic ---

    def _run_command_list_sequentially(self, command_strings: list[str], refresh_on_success=True):
        """Execute a list of command strings sequentially."""
        logging.debug(f"执行命令列表: {command_strings}, 刷新: {refresh_on_success}")

        if not command_strings:
             logging.debug("Command list is empty, nothing to execute.")
             self._set_ui_busy(False) # Ensure UI is not busy if list was empty
             return

        self._set_ui_busy(True) # Set UI to busy state

        def execute_next(index):
            """Execute the command at the given index and schedule the next."""
            if index >= len(command_strings):
                # All commands finished
                self._append_output("\n✅ --- 所有命令执行完毕 ---", QColor("green"))
                self._set_ui_busy(False) # Restore UI state
                if refresh_on_success:
                    self._refresh_all_views() # Refresh all if requested
                else:
                     self._refresh_branch_list() # Always refresh branch list to show current branch state
                return

            cmd_str = command_strings[index].strip()
            logging.debug(f"准备执行命令 #{index}: {repr(cmd_str)}")

            if not cmd_str:
                # Skip empty command strings
                logging.debug(f"Skipping empty command string at index {index}")
                QTimer.singleShot(0, lambda idx=index + 1: execute_next(idx)) # Schedule next command immediately
                return

            try:
                # Use shlex.split to handle quoted arguments correctly
                command_parts = shlex.split(cmd_str)
                logging.debug(f"解析结果: {command_parts}")
            except ValueError as e:
                self._append_output(f"❌ 解析错误 '{cmd_str}': {e}", QColor("red"))
                self._append_output("--- 执行中止 ---", QColor("red"))
                logging.error(f"Command parse error for '{cmd_str}': {e}")
                self._set_ui_busy(False) # Restore UI state on error
                return # Stop the sequence

            if not command_parts:
                 # shlex.split might return empty list for strings like just whitespace
                 logging.debug(f"Parsed command parts is empty for '{cmd_str}'")
                 QTimer.singleShot(0, lambda idx=index + 1: execute_next(idx)) # Schedule next command immediately
                 return

            # Display the command being executed (quoted for clarity)
            display_cmd = ' '.join(shlex.quote(part) for part in command_parts)
            self._append_output(f"\n▶️ 执行: {display_cmd}", QColor("blue"))


            # Define slots for command finish and progress updates
            @pyqtSlot(int, str, str)
            def on_command_finished(return_code, stdout, stderr):
                """Handle the completion of a single command."""
                if stdout:
                    self._append_output(f"stdout:\n{stdout.strip()}")
                if stderr:
                    self._append_output(f"stderr:\n{stderr.strip()}", QColor("red"))

                if return_code == 0:
                    self._append_output(f"✅ 成功: '{display_cmd}'", QColor("darkGreen"))
                    # Schedule the next command execution
                    QTimer.singleShot(0, lambda idx=index + 1: execute_next(idx))
                else:
                    # Command failed
                    logging.error(f"命令失败! Cmd: '{display_cmd}', RC: {return_code}, Stderr: {stderr.strip()}")
                    self._append_output(f"❌ 失败 (RC: {return_code}) '{display_cmd}'，中止执行。", QColor("red"))
                    self._set_ui_busy(False) # Restore UI state on error
                    # Do NOT schedule the next command - sequence is stopped

            @pyqtSlot(str)
            def on_progress(message):
                """Handle progress updates from GitHandler."""
                # Display progress message in the status bar
                self.status_bar.showMessage(message, 3000) # Show for 3 seconds

            # Execute the command asynchronously
            self.git_handler.execute_command_async(command_parts, on_command_finished, on_progress)

        # Start the sequence execution
        execute_next(0)


    def _set_ui_busy(self, busy: bool):
        """Set UI elements to busy/non-busy state."""
        # Enable/disable buttons and input field
        for key, item in self.command_buttons.items():
             # Avoid disabling the Select Repo button and other essential actions
             if key in ['select_repo_action', 'git_config_action', 'exit_action', 'about_action', 'clear_output_action']:
                  continue
             # Check if item is a widget or an action
             if isinstance(item, QWidget):
                  item.setEnabled(not busy)
             elif isinstance(item, QAction):
                  item.setEnabled(not busy)

        # Enable/disable specific widgets
        self.shortcut_list_widget.setEnabled(not busy)
        # Note: branch_list_widget, status_tree_view, log_table_widget, diff_text_edit, commit_details_textedit are usually handled by _update_ui_enable_state
        # but we might temporarily disable them here during sequence execution for stronger feedback.
        # However, selection changes might trigger actions (like diff/details), so let's keep them enabled unless interaction causes issues.
        # For now, rely on _update_ui_enable_state and keep them enabled during busy state for viewing results.

        # Disable global shortcuts managed by ShortcutManager
        self.shortcut_manager.set_shortcuts_enabled(not busy) # Disable while busy

        # Ensure ALWAYS enabled actions remain enabled (redundant with loop check, but good fallback)
        for action in self.findChildren(QAction):
             if action.text() in ["选择仓库(&O)...", "Git 全局配置(&G)...", "退出(&X)", "关于(&A)", "清空原始输出"]:
                action.setEnabled(True)


        if busy:
            self.status_bar.showMessage("⏳ 正在执行...", 0) # Persistent busy message
            QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor) # Show wait cursor
        else:
            QApplication.restoreOverrideCursor() # Restore default cursor
            # Status bar message will be updated by the finished slot (e.g., _on_branches_refreshed)


    def _append_output(self, text: str, color: QColor = None):
        """Append text to the raw output display."""
        if not self.output_display: return # Safety check

        cursor = self.output_display.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        self.output_display.setTextCursor(cursor)

        # Save current format to restore later
        original_format = self.output_display.currentCharFormat()

        # Set format for new text
        fmt = QTextEdit().currentCharFormat() # Get a default format
        if color:
            fmt.setForeground(color)
        else:
            # Use default text color from the palette
            fmt.setForeground(self.palette().color(self.foregroundRole()))
        self.output_display.setCurrentCharFormat(fmt)

        # Append the text and a newline
        # Ensure text doesn't have leading/trailing newlines from source if not intended
        clean_text = text.rstrip('\n')
        self.output_display.insertPlainText(clean_text + "\n")

        # Restore original format
        self.output_display.setCurrentCharFormat(original_format)

        # Ensure the new text is visible
        self.output_display.ensureCursorVisible()


    # --- Slot for Command Input ---

    @pyqtSlot()
    def _execute_command_from_input(self):
        """Execute command entered in the command input line edit."""
        if not self.command_input: return

        command_text = self.command_input.text().strip()
        if not command_text: return

        logging.info(f"命令行输入: {command_text}")

        # Display the command in the output window
        prompt_color = QColor(Qt.GlobalColor.darkCyan)
        try:
            # Use shlex to correctly display the command with quoting
            display_cmd = ' '.join(shlex.quote(part) for part in shlex.split(command_text))
        except ValueError:
            # Fallback if shlex fails (e.g., unmatched quotes)
            display_cmd = command_text
        self._append_output(f"\n$ {display_cmd}", prompt_color)

        # Clear the input field
        self.command_input.clear()

        # Execute the single command as a list of one
        self._run_command_list_sequentially([command_text])


    # --- Shortcut Execution Logic (Called by ShortcutManager) ---

    def _execute_sequence_from_string(self, name: str, sequence_str: str):
        """Execute a sequence of commands provided as a single string."""
        if not self.git_handler.is_valid_repo():
            QMessageBox.critical(self, "错误", f"仓库无效 '{name}'。请先选择一个有效的 Git 仓库。")
            return

        self.status_bar.showMessage(f"执行快捷键: {name}", 3000)
        logging.info(f"执行快捷键 '{name}' 序列: {repr(sequence_str)}")

        # Split the sequence string into individual command lines, ignoring empty lines
        # FIX: Simplified sequence string parsing
        commands = [line.strip() for line in sequence_str.splitlines() if line.strip()]

        if not commands:
            QMessageBox.warning(self, "快捷键无效", f"'{name}' 序列为空或解析失败。")
            logging.warning(f"快捷键 '{name}' 解析后为空。")
            return

        logging.info(f"最终执行列表 for '{name}': {commands}")

        # Use the existing sequential command runner
        # Pass refresh=True by default, but could make it configurable per shortcut
        self._run_command_list_sequentially(commands, refresh_on_success=True)


    # --- Status View Actions ---

    @pyqtSlot()
    def _stage_all(self):
        """Stage all changes (git add .)."""
        if not self.git_handler.is_valid_repo(): return
        logging.info("Staging all (git add .)")
        # FIX: Corrected typo
        self._execute_command_if_valid_repo(["git", "add", "."])

    @pyqtSlot()
    def _unstage_all(self):
        """Unstage all staged changes (git reset HEAD --)."""
        if not self.git_handler.is_valid_repo(): return
        # Optional: Check if there are staged changes before running the command
        if self.status_tree_model and self.status_tree_model.staged_root.rowCount() == 0:
            QMessageBox.information(self, "无操作", "没有已暂存文件可撤销暂存。")
            return

        logging.info("Unstaging all (git reset HEAD --)")
        # FIX: Corrected typo
        self._execute_command_if_valid_repo(["git", "reset", "HEAD", "--"])

    def _stage_files(self, files: list):
         """Stage specific files (git add -- <files>)."""
         if not files: return # Nothing to stage
         if not self.git_handler.is_valid_repo(): return
         logging.info(f"Staging files: {files}")
         # FIX: Corrected typo
         self._execute_command_if_valid_repo(["git", "add", "--"] + files) # Use "--" to separate command from file list

    def _unstage_files(self, files: list):
         """Unstage specific files (git reset HEAD -- <files>)."""
         if not files: return # Nothing to unstage
         if not self.git_handler.is_valid_repo(): return
         logging.info(f"Unstaging files: {files}")
         # FIX: Corrected typo
         self._execute_command_if_valid_repo(["git", "reset", "HEAD", "--"] + files) # Use "--" to separate command from file list


    # --- Status View Context Menu ---

    @pyqtSlot(QPoint)
    def _show_status_context_menu(self, pos):
        """显示状态树的右键菜单"""
        if not self.git_handler.is_valid_repo(): return

        # Get the item clicked
        index = self.status_tree_view.indexAt(pos)
        if not index.isValid():
             # Clicked on empty space, maybe show a generic menu? Or just return.
             return

        menu = QMenu()
        selected_indexes = self.status_tree_view.selectedIndexes()

        # Get file paths grouped by status section for all selected items
        selected_files_data = self.status_tree_model.get_selected_files(selected_indexes)

        # Determine if staging/unstaging actions are possible based on selection
        can_stage = selected_files_data[STATUS_UNSTAGED] or selected_files_data[STATUS_UNTRACKED]
        can_unstage = selected_files_data[STATUS_STAGED]

        # Add actions based on what can be done
        if can_stage:
            stage_action = QAction("暂存选中文件 (+)", self)
            stage_action.triggered.connect(self._stage_selected_files)
            menu.addAction(stage_action)

        if can_unstage:
            unstage_action = QAction("撤销暂存选中文件 (-)", self)
            unstage_action.triggered.connect(self._unstage_selected_files)
            menu.addAction(unstage_action)

        # Add other actions later maybe? Like discard changes for unstaged/untracked

        # Show the menu if any actions were added
        if menu.actions():
            menu.exec(self.status_tree_view.viewport().mapToGlobal(pos))


    @pyqtSlot()
    def _stage_selected_files(self):
        """暂存状态树中选中的 Unstaged/Untracked 文件"""
        selected_indexes = self.status_tree_view.selectedIndexes()
        selected_files_data = self.status_tree_model.get_selected_files(selected_indexes)
        files_to_stage = selected_files_data.get(STATUS_UNSTAGED, []) + selected_files_data.get(STATUS_UNTRACKED, [])

        # Ensure unique files before staging
        unique_files_to_stage = list(set(files_to_stage))

        if unique_files_to_stage:
             self._stage_files(unique_files_to_stage)
        else:
             QMessageBox.information(self, "无操作", "没有选中的未暂存或未跟踪文件可暂存。")


    @pyqtSlot()
    def _unstage_selected_files(self):
        """撤销状态树中选中的 Staged 文件的暂存"""
        selected_indexes = self.status_tree_view.selectedIndexes()
        selected_files_data = self.status_tree_model.get_selected_files(selected_indexes)
        files_to_unstage = selected_files_data.get(STATUS_STAGED, [])

        # Ensure unique files before unstaging
        unique_files_to_unstage = list(set(files_to_unstage))

        if unique_files_to_unstage:
            self._unstage_files(unique_files_to_unstage)
        else:
            QMessageBox.information(self, "无操作", "没有选中的已暂存文件可撤销暂存。")


    # --- Status View Selection Change ---

    @pyqtSlot(QItemSelection, QItemSelection)
    def _status_selection_changed(self, selected, deselected):
        """当状态树中的选择发生变化时，更新差异视图"""
        # We only care about the current selection, not the delta
        selected_indexes = self.status_tree_view.selectedIndexes()
        self.diff_text_edit.clear() # Clear diff on any selection change first

        if not selected_indexes:
             self.diff_text_edit.setPlaceholderText("选中文件以查看差异...")
             return

        # Get the first selected index (Qt allows multi-selection, but diff is usually per-file)
        # We need to find the *file item* among the selected indices
        file_index = None
        file_path = None
        section_type = None

        for index in selected_indexes:
             # Check if the index is valid and corresponds to a file item
             item = self.status_tree_model.itemFromIndex(index)
             if item:
                 parent = item.parent()
                 if parent in [self.status_tree_model.staged_root, self.status_tree_model.unstage_root, self.status_tree_model.untracked_root]:
                     # Found a selected item that is a direct child of a root node (i.e., a file item)
                     # Ensure we get the data from the path column (column 1) regardless of which column is selected
                     path_item_index = self.status_tree_model.index(index.row(), 1, parent.index())
                     path_item = self.status_tree_model.itemFromIndex(path_item_index)
                     if path_item:
                        file_path = path_item.data(Qt.ItemDataRole.UserRole + 1) # Get the real file path
                        section_type = parent.data(Qt.ItemDataRole.UserRole)    # Get the section type (Staged, Unstaged, Untracked)
                        file_index = index # Store this index
                        break # Found a file item, process its diff


        if not file_path:
             self.diff_text_edit.setPlaceholderText("请选择一个文件行以查看差异...")
             return

        # Determine if we need staged or unstaged diff
        staged_diff = (section_type == STATUS_STAGED)

        if section_type == STATUS_UNTRACKED:
             # Untracked files have no diff against the index/HEAD
             self.diff_text_edit.setText(f"'{file_path}' 是未跟踪文件。\n无法显示差异，但你可以暂存它。")
        else:
             # Request diff for tracked files (staged or unstaged)
             self.diff_text_edit.setPlaceholderText(f"正在加载 {file_path} 的差异...")
             QApplication.processEvents() # Update placeholder text immediately
             self.git_handler.get_diff_async(file_path, staged=staged_diff, finished_slot=self._on_diff_received)


    @pyqtSlot(int, str, str)
    def _on_diff_received(self, return_code, stdout, stderr):
         """Handle the output of the git diff command."""
         if return_code == 0:
             if stdout:
                 self.diff_text_edit.setText(stdout)
             else:
                 self.diff_text_edit.setPlaceholderText("文件无差异。") # File exists but no changes shown
         else:
              # Display error message
              self.diff_text_edit.setText(f"❌ 获取差异失败:\n{stderr}")
              logging.error(f"Diff失败: RC={return_code}, Err:{stderr}")


    # --- Branch List Actions ---

    @pyqtSlot(QListWidgetItem)
    def _branch_double_clicked(self, item: QListWidgetItem):
        """Handle double click on a branch item to checkout."""
        branch_name = item.text().strip() # Strip potential '*' or spaces

        if branch_name.startswith("remotes/"):
             QMessageBox.information(self, "提示", f"不能直接切换到远程跟踪分支 '{branch_name}'。\n您可以创建并切换到与其关联的本地分支。")
             return

        # Check if it's the current branch
        # Iterate through all items to find the one with bold font
        is_current = False
        for i in range(self.branch_list_widget.count()):
             list_item = self.branch_list_widget.item(i)
             if list_item.font().bold() and list_item.text().strip() == branch_name:
                 is_current = True
                 break

        if is_current:
            logging.info(f"已在分支 '{branch_name}'。")
            self.status_bar.showMessage(f"已在分支 '{branch_name}'。", 2000)
            return

        # Confirm checkout
        reply = QMessageBox.question(
            self,
            "切换分支",
            f"确定要切换到本地分支 '{branch_name}' 吗？\n\n请确保您已保存或暂存当前更改。",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel # Default button
        )

        if reply == QMessageBox.StandardButton.Yes:
             logging.info(f"切换到分支: {branch_name}")
             # FIX: Corrected typo
             self._execute_command_if_valid_repo(["git", "checkout", branch_name])


    @pyqtSlot()
    def _create_branch_dialog(self):
        """显示创建新分支的对话框"""
        if not self.git_handler.is_valid_repo():
            QMessageBox.warning(self, "操作无效", "请先选择一个有效的 Git 仓库。")
            return

        branch_name, ok = QInputDialog.getText(
            self,
            "创建新分支",
            "输入新分支名称:",
            QLineEdit.EchoMode.Normal # Or QLineEdit.Normal
        )

        if ok and branch_name:
            clean_name = branch_name.strip() # Keep spaces if git allows, but strip leading/trailing
            # Basic check for invalid characters (optional, git handles most)
            if re.search(r'[^\w\-\./]', clean_name): # Allow letters, numbers, hyphen, underscore, dot, slash
                 QMessageBox.warning(self, "错误", "分支名称包含无效字符。")
                 return
            if not clean_name:
                 QMessageBox.warning(self, "错误", "分支名称不能为空。")
                 return

            logging.info(f"创建分支: {clean_name}")
            # FIX: Corrected typo
            self._execute_command_if_valid_repo(["git", "branch", clean_name]) # Create the branch
        elif ok: # User pressed OK but entered nothing
            QMessageBox.warning(self, "错误", "分支名称不能为空。")


    @pyqtSlot(QPoint)
    def _show_branch_context_menu(self, pos):
        """显示分支列表的右键菜单"""
        if not self.git_handler.is_valid_repo(): return

        # Get the item at the clicked position
        item = self.branch_list_widget.itemAt(pos)
        if not item: return # Clicked on empty space

        menu = QMenu()
        branch_name = item.text().strip()
        is_remote = branch_name.startswith("remotes/")
        is_current = item.font().bold() # Check if it's the current branch (bold font)

        # Action: Checkout (if not current and not remote)
        if not is_current and not is_remote:
            checkout_action = QAction(f"切换到 '{branch_name}'", self)
            # Use a lambda to pass the branch name to the slot
            checkout_action.triggered.connect(lambda checked=False, b=branch_name: self._execute_command_if_valid_repo(["git", "checkout", b]))
            menu.addAction(checkout_action)

        # Action: Delete (if not current and not remote)
        # Note: deleting remote branches needs git push origin :branch-name
        # This menu focuses on local branches for now
        if not is_current and not is_remote:
            delete_action = QAction(f"删除本地分支 '{branch_name}'...", self)
            delete_action.triggered.connect(lambda checked=False, b=branch_name: self._delete_branch(b))
            menu.addAction(delete_action)

        # Add other actions later (e.g., rename, merge into current, rebase)

        # Show menu if it has actions
        if menu.actions():
            menu.exec(self.branch_list_widget.mapToGlobal(pos))


    def _delete_branch(self, branch_name: str):
        """删除指定的本地分支 (带确认)"""
        # Safety check
        if not branch_name or branch_name.startswith("remotes/"):
            logging.warning(f"Attempted to delete invalid branch name: {branch_name}")
            return
        if not self.git_handler.is_valid_repo(): return

        reply = QMessageBox.warning(
            self,
            "确认删除",
            f"确定要删除本地分支 '{branch_name}' 吗？\n此操作不可撤销！\n(将使用 git branch -d)",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel # Default button
        )

        if reply == QMessageBox.StandardButton.Yes:
             logging.info(f"删除本地分支: {branch_name}")
             # Use -d (delete) which prevents deletion if it's not fully merged
             # Could use -D (force delete) with stronger warning if needed
             # FIX: Corrected typo
             self._execute_command_if_valid_repo(["git", "branch", "-d", branch_name])


    # --- Log View Actions ---

    @pyqtSlot()
    def _log_selection_changed(self):
        """当日志表格中的选择发生变化时，尝试显示提交详情。"""
        selected_items = self.log_table_widget.selectedItems()
        self.commit_details_textedit.clear() # Clear previous details

        if not selected_items:
             self.commit_details_textedit.setPlaceholderText("选中上方提交记录以查看详情...")
             return

        # Get the commit hash from the selected row (first column)
        selected_row = self.log_table_widget.currentRow()
        if selected_row < 0:
             self.commit_details_textedit.setPlaceholderText("无法确定选中的提交。")
             return

        hash_item = self.log_table_widget.item(selected_row, 0) # Column 0 is Hash

        if hash_item:
            # Get the full hash stored in UserRole, fallback to displayed text if not found
            commit_hash = hash_item.data(Qt.ItemDataRole.UserRole)
            if not commit_hash:
                 commit_hash = hash_item.text().split()[-1] # Fallback: try getting last word from displayed text (might contain graph)


            if commit_hash and commit_hash != "N/A": # Ensure we have a valid-looking hash
                logging.debug(f"Log selection changed, requesting details for commit: {commit_hash}")
                self.commit_details_textedit.setPlaceholderText(f"正在加载 {commit_hash} 的详情...")
                QApplication.processEvents() # Update placeholder text immediately
                # Request commit details asynchronously (git show command)
                self.git_handler.get_commit_details_async(commit_hash, self._on_commit_details_received)
            else:
                self.commit_details_textedit.setPlaceholderText("无法获取选中提交的 Hash。")
                logging.warning(f"Could not get commit hash from selected item data or text: {hash_item.text()}")
        else:
             self.commit_details_textedit.setPlaceholderText("无法确定选中的提交。")
             logging.warning("Hash item (column 0) is None for selected log row.")


    @pyqtSlot(int, str, str)
    def _on_commit_details_received(self, return_code, stdout, stderr):
        """处理 get_commit_details_async 的结果"""
        if return_code == 0:
            if stdout.strip():
                 # Display the raw 'git show' output in the details area
                 self.commit_details_textedit.setText(stdout)
            else:
                 self.commit_details_textedit.setText("未获取到提交详情。") # Should not happen often for valid commits
        else:
            # Display error message
            self.commit_details_textedit.setText(f"❌ 获取提交详情失败:\n{stderr}")
            logging.error(f"获取 Commit 详情失败: RC={return_code}, Error: {stderr}")


    # --- Direct Action Slots (Simplified) ---
    # These are convenience methods for single commands, e.g., from menu/toolbar

    def _execute_command_if_valid_repo(self, command_list: list, refresh=True):
         """Check if repo is valid, then execute a single command."""
         if not self.git_handler.is_valid_repo():
             QMessageBox.warning(self, "操作无效", "请先选择一个有效的 Git 仓库。")
             return
         # Execute the single command using the sequential runner
         # Use shlex.join to reconstruct the command string from list for the runner
         command_str = ' '.join(shlex.quote(arg) for arg in command_list) if command_list else ""
         if command_str:
              self._run_command_list_sequentially([command_str], refresh_on_success=refresh)
         else:
              logging.warning("Attempted to execute empty command list.")


    def _run_pull(self):
        """Execute git pull."""
        # FIX: Corrected typo
        self._execute_command_if_valid_repo(["git", "pull"]) # Pull usually implies a refresh

    def _run_push(self):
        """Execute git push."""
        # FIX: Corrected typo
        self._execute_command_if_valid_repo(["git", "push"]) # Push usually implies a refresh

    def _run_fetch(self):
        """Execute git fetch."""
        # FIX: Corrected typo
        self._execute_command_if_valid_repo(["git", "fetch"]) # Fetch updates remotes, refresh branches/log might be good
        # Note: Fetch doesn't change working copy/index, so status refresh isn't strictly needed
        # But branches might change (new remote branches), and log might change (new commits on remotes)
        # Let's refresh everything for simplicity unless performance is an issue.
        # Or pass refresh=False if only fetching and will pull/merge later.
        # For now, let's make Fetch trigger refresh, aligning with Pull/Push
        # self._execute_command_if_valid_repo(["git", "fetch"], refresh=True) # Explicitly refresh

    # This method is essentially _refresh_branch_list, connected via the "Branches" button if it existed
    # def _run_list_branches(self):
    #     self._refresh_branch_list()

    def _run_switch_branch(self):
        """Open input dialog to switch branch."""
        if not self.git_handler.is_valid_repo():
            QMessageBox.warning(self, "操作无效", "请先选择一个有效的 Git 仓库。")
            return

        branch_name, ok = QInputDialog.getText(
            self,
            "切换分支",
            "输入要切换到的本地分支名称:",
            QLineEdit.EchoMode.Normal # Or QLineEdit.Normal
        )

        if ok and branch_name:
             clean_name = branch_name.strip()
             if not clean_name:
                  QMessageBox.warning(self, "操作取消", "名称不能为空。")
                  return
             logging.info(f"通过对话框切换到分支: {clean_name}")
             # FIX: Corrected typo
             self._execute_command_if_valid_repo(["git", "checkout", clean_name]) # Use checkout for switching
        elif ok: # User pressed OK but entered nothing
             QMessageBox.warning(self, "操作取消", "名称不能为空。")


    def _run_list_remotes(self):
        """Execute git remote -v and show output."""
        # FIX: Corrected typo
        self._execute_command_if_valid_repo(["git", "remote", "-v"], refresh=False) # No need to refresh views after just listing remotes


    # --- Settings Dialog Slot ---

    def _open_settings_dialog(self):
        """Open the settings dialog for global git config."""
        # The dialog fetches current config and allows editing user.name/user.email
        dialog = SettingsDialog(self)

        # Execute the dialog
        if dialog.exec():
            # Dialog returned accepted, get data
            config_data = dialog.get_data()
            commands_to_run = []

            name_val = config_data.get("user.name")
            email_val = config_data.get("user.email")

            # Build git config commands if values were provided/changed
            if name_val is not None:
                 commands_to_run.append(f"git config --global user.name {shlex.quote(name_val)}")
            if email_val is not None:
                 commands_to_run.append(f"git config --global user.email {shlex.quote(email_val)}")

            if commands_to_run:
                 # Optional: Confirm with user before running config commands
                 reply = QMessageBox.information(
                     self,
                     "应用配置",
                     f"将执行以下命令来更新全局 Git 配置:\n\n" + "\n".join(commands_to_run) + "\n\n确定继续吗？",
                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
                 )
                 if reply == QMessageBox.StandardButton.Yes:
                     # Run the config commands
                     # FIX: Corrected typo
                     self._run_command_list_sequentially(commands_to_run, refresh_on_success=False) # Don't need to refresh git state views for global config
            else:
                QMessageBox.information(self, "无更改", "未输入任何 Git 全局配置信息。")


    # --- Other Helper Methods ---

    def _show_about_dialog(self):
        """Show the About dialog."""
        QMessageBox.about(
            self,
            "关于简易 Git GUI",
            "版本: 1.7 (Status/Branch交互, Log详情)\n\n"
            "- 状态文件树 (带图标, 右键暂存/撤销)\n"
            "- 分支列表 (双击切换, 右键删除, 创建按钮)\n"
            "- 提交历史表格 & 详情视图\n"
            "- 差异视图 (基础)\n"
            "- Tabs布局, 命令行输入\n"
            "- 异步操作, 快捷键...\n\n"
            "作者: AI\n"
            "使用 PyQt6 构建"
        )

    def closeEvent(self, event):
        """Handle application closing event."""
        logging.info("应用程序关闭。")
        # Clean up resources if necessary
        if self.db_handler:
            self.db_handler.close_connection()
        # The GitHandler process pool might need graceful shutdown
        # self.git_handler.shutdown() # Assuming a shutdown method exists

        event.accept() # Accept the close event and exit