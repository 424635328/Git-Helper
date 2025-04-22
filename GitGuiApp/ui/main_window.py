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
    QSpacerItem, QFrame, QStyle # Added QSpacerItem, QFrame, QStyle
)
from PyQt6.QtGui import QAction, QKeySequence, QColor, QTextCursor, QIcon, QFont, QStandardItemModel, QDesktopServices # Added QDesktopServices
from PyQt6.QtCore import Qt, pyqtSlot, QSize, QTimer, QModelIndex, QUrl, QPoint, QItemSelection # Added QItemSelection
# Ensure these imports point to the correct location of your modules
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
        # Pass self.db_handler and self.git_handler to ShortcutManager
        self.shortcut_manager = ShortcutManager(self, self.db_handler, self.git_handler)


        self.current_command_sequence = []
        self.command_buttons = {}

        # UI Element Placeholders
        self.output_display = None; self.command_input = None; self.sequence_display = None
        self.shortcut_list_widget = None; self.repo_label = None; self.status_bar = None
        self.branch_list_widget = None; self.status_tree_view = None; self.status_tree_model = None
        self.log_table_widget = None; self.diff_text_edit = None; self.main_tab_widget = None
        self.commit_details_textedit = None # New textedit for commit details

        self._init_ui()
        self.shortcut_manager.load_and_register_shortcuts()
        self._update_repo_status()

        logging.info("主窗口初始化完成。")

    def _init_ui(self):
        """初始化用户界面 (状态交互, 分支交互, 日志详情)"""
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)

        # --- Repository Selection Area ---
        repo_layout = QHBoxLayout(); self.repo_label = QLabel("当前仓库: (未选择)"); self.repo_label.setToolTip("当前操作的 Git 仓库路径"); repo_layout.addWidget(self.repo_label, 1); select_repo_button = QPushButton("选择仓库"); select_repo_button.setToolTip("选择仓库目录"); select_repo_button.clicked.connect(self._select_repository); repo_layout.addWidget(select_repo_button); main_layout.addLayout(repo_layout)

        # --- Main Splitter ---
        splitter = QSplitter(Qt.Orientation.Horizontal)
        main_layout.addWidget(splitter, 1)

        # --- Left Panel ---
        left_panel = QWidget(); left_layout = QVBoxLayout(left_panel); left_layout.setContentsMargins(5, 0, 5, 5); left_layout.setSpacing(6); splitter.addWidget(left_panel)

        # Command Buttons (Execute directly, do not add to sequence builder)
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
        self._add_command_button(more_commands_layout, "Pull", "拉取 (git pull)", lambda: self._execute_command_if_valid_repo(["git", "pull"]))
        self._add_command_button(more_commands_layout, "Push", "推送 (git push)", lambda: self._execute_command_if_valid_repo(["git", "push"]))
        self._add_command_button(more_commands_layout, "Fetch", "获取 (git fetch)", lambda: self._execute_command_if_valid_repo(["git", "fetch"]))
        left_layout.addLayout(more_commands_layout)

        # Command Sequence Builder (Now more of a shortcut preview/executor)
        left_layout.addWidget(QLabel("快捷键命令预览/执行:")) # Renamed Label for clarity
        self.sequence_display = QTextEdit()
        self.sequence_display.setReadOnly(True)
        self.sequence_display.setPlaceholderText("从下方快捷键列表加载的命令将显示在此处...") # Updated placeholder
        self.sequence_display.setFixedHeight(80)
        left_layout.addWidget(self.sequence_display)

        sequence_actions_layout = QHBoxLayout()
        execute_button = QPushButton("执行序列")
        execute_button.setToolTip("执行上方显示的命令序列")
        execute_button.setStyleSheet("background-color: lightgreen;")
        execute_button.clicked.connect(self._execute_sequence)
        self.command_buttons['execute'] = execute_button
        clear_button = QPushButton("清空预览")
        clear_button.setToolTip("清空上方显示的命令序列")
        clear_button.clicked.connect(self._clear_sequence)
        self.command_buttons['clear'] = clear_button
        save_shortcut_button = QPushButton("保存快捷键")
        save_shortcut_button.setToolTip("将上方命令序列保存为新的快捷键")
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
        self.branch_list_widget.setToolTip("双击切换分支, 右键操作")
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
        right_layout.setContentsMargins(0, 0, 0, 0) # No margins for the right panel layout itself
        right_layout.setSpacing(0) # No spacing between tabs and input
        splitter.addWidget(right_panel)

        # Tab Widget
        self.main_tab_widget = QTabWidget()
        right_layout.addWidget(self.main_tab_widget, 1) # Tabs take most space

        # -- Tab 1: Status / Files --
        status_tab_widget = QWidget()
        status_tab_layout = QVBoxLayout(status_tab_widget)
        status_tab_layout.setContentsMargins(5, 5, 5, 5) # Margins inside the tab
        status_tab_layout.setSpacing(4) # Spacing inside the tab
        self.main_tab_widget.addTab(status_tab_widget, "状态 / 文件")

        status_action_layout = QHBoxLayout()
        stage_all_button = QPushButton("全部暂存 (+)")
        stage_all_button.setToolTip("暂存所有未暂存和未跟踪的文件 (git add .)")
        stage_all_button.clicked.connect(self._stage_all)
        self.command_buttons['stage_all'] = stage_all_button
        unstage_all_button = QPushButton("全部撤销暂存 (-)")
        unstage_all_button.setToolTip("撤销所有已暂存文件的暂存状态 (git reset HEAD --)")
        unstage_all_button.clicked.connect(self._unstage_all)
        self.command_buttons['unstage_all'] = unstage_all_button
        status_action_layout.addWidget(stage_all_button)
        status_action_layout.addWidget(unstage_all_button)
        status_action_layout.addStretch()
        status_tab_layout.addLayout(status_action_layout)

        self.status_tree_view = QTreeView()
        self.status_tree_model = StatusTreeModel(self) # Pass parent if needed by model
        self.status_tree_view.setModel(self.status_tree_model)
        self.status_tree_view.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.status_tree_view.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.status_tree_view.header().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch) # File path stretches
        self.status_tree_view.header().setStretchLastSection(False) # Don't stretch last (path)
        self.status_tree_view.setColumnWidth(0, 100) # Fixed width for status
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
        self.log_table_widget.setColumnWidth(0, 80)  # Hash
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
        self.commit_details_textedit.setFontFamily("Courier New") # Monospace font for diffs
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
        self.output_display.setPlaceholderText("Git 命令和命令行输出将显示在此处...")
        output_tab_layout.addWidget(self.output_display, 1)


        # Command Input Area (Below Tabs)
        command_input_container = QWidget() # Use a container for margins
        command_input_layout = QHBoxLayout(command_input_container)
        command_input_layout.setContentsMargins(5, 3, 5, 5) # Margins around the input line
        command_input_layout.setSpacing(4)
        command_input_label = QLabel("$")
        self.command_input = QLineEdit()
        self.command_input.setPlaceholderText("输入 Git 命令并按 Enter 执行 (如: git checkout main)")
        command_font = QFont("Courier New") # Monospace font
        self.command_input.setFont(command_font)
        # Basic styling for the command input
        command_input_style = """
            QLineEdit {
                background-color: #ffffff; /* White background */
                border: 1px solid #abadb3; /* Standard border */
                border-radius: 2px;
                padding: 4px 6px; /* Padding inside */
                color: #000000; /* Black text */
            }
            QLineEdit:focus {
                border: 1px solid #0078d4; /* Blue border on focus */
            }
            QLineEdit::placeholder {
                color: #a0a0a0; /* Gray placeholder text */
            }
             QLineEdit:disabled {
                background-color: #f0f0f0; /* Lighter gray when disabled */
                color: #a0a0a0;
            }
        """
        self.command_input.setStyleSheet(command_input_style)
        self.command_input.returnPressed.connect(self._execute_command_from_input)
        self.command_buttons['command_input'] = self.command_input # Track for enable/disable

        command_input_layout.addWidget(command_input_label)
        command_input_layout.addWidget(self.command_input)
        right_layout.addWidget(command_input_container) # Add container to right layout

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

        # File Menu
        file_menu = menu_bar.addMenu("文件(&F)")
        select_repo_action = QAction("选择仓库(&O)...", self)
        select_repo_action.triggered.connect(self._select_repository)
        file_menu.addAction(select_repo_action)

        git_config_action = QAction("Git 全局配置(&G)...", self)
        git_config_action.triggered.connect(self._open_settings_dialog)
        file_menu.addAction(git_config_action)

        file_menu.addSeparator()
        exit_action = QAction("退出(&X)", self)
        exit_action.triggered.connect(self.close) # Connect to QMainWindow's close method
        file_menu.addAction(exit_action)

        # Repository Menu
        repo_menu = menu_bar.addMenu("仓库(&R)")
        refresh_action = QAction("刷新全部视图", self)
        refresh_action.setShortcut(QKeySequence(Qt.Key.Key_F5))
        refresh_action.triggered.connect(self._refresh_all_views)
        repo_menu.addAction(refresh_action)
        self.command_buttons['refresh_action'] = refresh_action # Track for enable/disable
        repo_menu.addSeparator()

        create_branch_action = QAction("创建分支(&N)...", self)
        create_branch_action.triggered.connect(self._create_branch_dialog)
        repo_menu.addAction(create_branch_action)
        self.command_buttons['create_branch_menu'] = create_branch_action # Use separate key

        switch_branch_action = QAction("切换分支(&S)...", self)
        switch_branch_action.triggered.connect(self._run_switch_branch)
        repo_menu.addAction(switch_branch_action)
        self.command_buttons['switch_branch_action'] = switch_branch_action # Track for enable/disable

        repo_menu.addSeparator()
        list_remotes_action = QAction("列出远程仓库", self)
        list_remotes_action.triggered.connect(self._run_list_remotes)
        repo_menu.addAction(list_remotes_action)
        self.command_buttons['list_remotes_action'] = list_remotes_action # Track for enable/disable

        # Help Menu
        help_menu = menu_bar.addMenu("帮助(&H)")
        about_action = QAction("关于(&A)", self)
        about_action.triggered.connect(self._show_about_dialog)
        help_menu.addAction(about_action)

    def _create_toolbar(self):
        toolbar = QToolBar("主要操作")
        toolbar.setIconSize(QSize(24, 24)) # Standard icon size
        self.addToolBar(toolbar)

        # Add icons using standard pixmaps (requires QApplication instance)
        style = self.style() # Get the current style
        refresh_icon = style.standardIcon(QStyle.StandardPixmap.SP_BrowserReload)
        pull_icon = style.standardIcon(QStyle.StandardPixmap.SP_ArrowDown)
        push_icon = style.standardIcon(QStyle.StandardPixmap.SP_ArrowUp)
        new_branch_icon = style.standardIcon(QStyle.StandardPixmap.SP_FileDialogNewFolder) # Placeholder icon
        switch_branch_icon = style.standardIcon(QStyle.StandardPixmap.SP_FileDialogDetailedView) # Placeholder icon
        remotes_icon = style.standardIcon(QStyle.StandardPixmap.SP_ComputerIcon) # Placeholder icon
        clear_icon = style.standardIcon(QStyle.StandardPixmap.SP_DialogResetButton)


        refresh_tb_action = QAction(refresh_icon, "刷新", self)
        refresh_tb_action.setToolTip("刷新状态、分支和日志视图 (F5)")
        refresh_tb_action.triggered.connect(self._refresh_all_views)
        toolbar.addAction(refresh_tb_action)
        self.command_buttons['refresh_tb_action'] = refresh_tb_action # Track
        toolbar.addSeparator()

        pull_action = QAction(pull_icon, "Pull", self)
        pull_action.triggered.connect(self._run_pull)
        toolbar.addAction(pull_action)
        self.command_buttons['pull_action'] = pull_action # Track

        push_action = QAction(push_icon,"Push", self)
        push_action.triggered.connect(self._run_push)
        toolbar.addAction(push_action)
        self.command_buttons['push_action'] = push_action # Track

        toolbar.addSeparator()

        create_branch_tb_action = QAction(new_branch_icon, "新分支", self)
        create_branch_tb_action.setToolTip("创建新的本地分支")
        create_branch_tb_action.triggered.connect(self._create_branch_dialog)
        toolbar.addAction(create_branch_tb_action)
        self.command_buttons['create_branch_tb'] = create_branch_tb_action # Track

        switch_branch_action_tb = QAction(switch_branch_icon, "切换分支...", self)
        switch_branch_action_tb.triggered.connect(self._run_switch_branch)
        toolbar.addAction(switch_branch_action_tb)
        self.command_buttons['switch_branch_action_tb'] = switch_branch_action_tb # Track

        list_remotes_action_tb = QAction(remotes_icon, "远程列表", self)
        list_remotes_action_tb.triggered.connect(self._run_list_remotes)
        toolbar.addAction(list_remotes_action_tb)
        self.command_buttons['list_remotes_action_tb'] = list_remotes_action_tb # Track

        toolbar.addSeparator()

        clear_output_action = QAction(clear_icon, "清空原始输出", self)
        clear_output_action.setToolTip("清空'原始输出'标签页的内容")
        # Ensure output_display exists before connecting
        if self.output_display:
             clear_output_action.triggered.connect(self.output_display.clear)
        else:
             logging.warning("Output display not initialized when creating clear action.")
        toolbar.addAction(clear_output_action)
        # No need to track clear_output_action for enable/disable based on repo state

    def _add_command_button(self, layout, text, tooltip, slot):
        button = QPushButton(text)
        button.setToolTip(tooltip)
        button.clicked.connect(slot)
        layout.addWidget(button)
        # Generate a more robust key
        button_key = f"button_{text.lower().replace('...', '').replace(' ', '_').replace('/', '_').replace('.', '_dot_').replace('-', '_dash_')}"
        self.command_buttons[button_key] = button
        return button

    # --- 状态更新和 UI 启用/禁用 ---
    def _update_repo_status(self):
        repo_path = self.git_handler.get_repo_path()
        is_valid = self.git_handler.is_valid_repo()
        display_path = repo_path if repo_path and len(repo_path) < 60 else f"...{repo_path[-57:]}" if repo_path else "(未选择)"
        self.repo_label.setText(f"当前仓库: {display_path}")

        self._update_ui_enable_state(is_valid)

        if is_valid:
            self.repo_label.setStyleSheet("") # Reset style
            self.status_bar.showMessage(f"正在加载仓库: {repo_path}", 0) # Use 0 for permanent message until next update
            QApplication.processEvents() # Ensure message is shown
            self._refresh_all_views() # Refresh all views for the valid repo
        else:
            self.repo_label.setStyleSheet("color: red;") # Indicate invalid repo
            self.status_bar.showMessage("请选择一个有效的 Git 仓库目录", 0)
            # Clear all views if repo is invalid
            if self.status_tree_model: self.status_tree_model.clear_status()
            if self.branch_list_widget: self.branch_list_widget.clear()
            if self.log_table_widget: self.log_table_widget.setRowCount(0)
            if self.diff_text_edit: self.diff_text_edit.clear()
            if self.commit_details_textedit: self.commit_details_textedit.clear()
            if self.output_display: self.output_display.clear() # Clear output too
            if self.sequence_display: self.sequence_display.clear() # Clear sequence preview

    def _update_ui_enable_state(self, enabled: bool):
        """启用或禁用依赖于有效仓库的 UI 元素"""
        # Define keys for widgets/actions that depend on a valid repository
        repo_dependent_keys = [
            'execute', 'clear', 'save', # Sequence buttons
            'button_status', 'button_add__dot_', 'button_add...', 'button_commit...', 'button_commit__dash_a...', 'button_log', # Command buttons row 1/2
            'button_pull', 'button_push', 'button_fetch', # Command buttons row 3
            'stage_all', 'unstage_all', # Status tab buttons
            'refresh_action', 'refresh_tb_action', # Refresh actions
            'create_branch', 'create_branch_menu', 'create_branch_tb', # Create branch buttons/actions
            'switch_branch_action', 'switch_branch_action_tb', # Switch branch actions
            'list_remotes_action', 'list_remotes_action_tb', # List remotes actions
            'pull_action', 'push_action', # Toolbar Pull/Push
            'command_input' # Command line input
        ]

        for key, item in self.command_buttons.items():
            if key in repo_dependent_keys:
                 # Check if item actually exists before enabling/disabling
                if item:
                    item.setEnabled(enabled)
                else:
                    logging.warning(f"UI element with key '{key}' not found during state update.")


        # Enable/disable core view widgets only if they exist
        if self.shortcut_list_widget: self.shortcut_list_widget.setEnabled(enabled)
        if self.branch_list_widget: self.branch_list_widget.setEnabled(enabled)
        if self.status_tree_view: self.status_tree_view.setEnabled(enabled)
        if self.log_table_widget: self.log_table_widget.setEnabled(enabled)
        if self.diff_text_edit: self.diff_text_edit.setEnabled(enabled)
        if self.commit_details_textedit: self.commit_details_textedit.setEnabled(enabled)

        # Enable/disable global shortcuts managed by ShortcutManager
        if self.shortcut_manager: self.shortcut_manager.set_shortcuts_enabled(enabled)

        # Ensure certain actions are always enabled or handled separately
        for action in self.findChildren(QAction):
            action_text = action.text()
            # Always enabled
            if action_text in ["选择仓库(&O)...", "Git 全局配置(&G)...", "退出(&X)", "关于(&A)", "清空原始输出"]:
                action.setEnabled(True)
            # Other actions might be covered by repo_dependent_keys check above via command_buttons mapping

    @pyqtSlot(int, str, str)
    def _update_branch_display(self, return_code, stdout, stderr):
        # This slot seems unused now, as logic is in _on_branches_refreshed
        pass # Keep the slot signature for potential future use? Or remove if definitely unused.

    # --- Refresh Views ---
    def _refresh_all_views(self):
        """刷新所有主要视图: 状态、分支、日志"""
        if not self.git_handler or not self.git_handler.is_valid_repo():
            logging.warning("Attempted to refresh views with invalid repo or no GitHandler.")
            self._update_ui_enable_state(False) # Ensure UI is disabled
            return
        logging.info("Refreshing Status, Branches, and Log views...")
        self.status_bar.showMessage("正在刷新...", 0)
        QApplication.processEvents() # Make sure message updates
        self._refresh_status_view()
        self._refresh_branch_list()
        self._refresh_log_view()
        # Status bar will be updated finally by _on_branches_refreshed

    @pyqtSlot()
    def _refresh_status_view(self):
        """异步获取并更新状态树视图"""
        if not self.git_handler or not self.git_handler.is_valid_repo(): return
        logging.debug("Requesting status porcelain...")
        # Disable buttons that depend on status result until it arrives
        stage_all_btn = self.command_buttons.get('stage_all')
        unstage_all_btn = self.command_buttons.get('unstage_all')
        if stage_all_btn: stage_all_btn.setEnabled(False)
        if unstage_all_btn: unstage_all_btn.setEnabled(False)

        self.git_handler.get_status_porcelain_async(self._on_status_refreshed)

    @pyqtSlot(int, str, str)
    def _on_status_refreshed(self, return_code, stdout, stderr):
        """处理异步 git status 的结果"""
        # Ensure model exists
        if not self.status_tree_model or not self.status_tree_view:
             logging.error("Status tree model or view not initialized when status refreshed.")
             return

        stage_all_btn = self.command_buttons.get('stage_all')
        unstage_all_btn = self.command_buttons.get('unstage_all')

        if return_code == 0:
            logging.debug("Status porcelain received, populating model...")
            self.status_tree_model.parse_and_populate(stdout)
            self.status_tree_view.expandAll() # Expand roots by default
            # Auto-resize columns after populating
            self.status_tree_view.resizeColumnToContents(0) # Status column
            # Ensure status column isn't too narrow
            self.status_tree_view.setColumnWidth(0, max(100, self.status_tree_view.columnWidth(0)))
            # File path column (index 1) will stretch due to header settings

            # Re-enable buttons based on new status
            has_unstaged_or_untracked = self.status_tree_model.unstage_root.rowCount() > 0 or self.status_tree_model.untracked_root.rowCount() > 0
            if stage_all_btn: stage_all_btn.setEnabled(has_unstaged_or_untracked)
            if unstage_all_btn: unstage_all_btn.setEnabled(self.status_tree_model.staged_root.rowCount() > 0)
        else:
            logging.error(f"Failed to get status: RC={return_code}, Error: {stderr}")
            self._append_output(f"❌ 获取 Git 状态失败:\n{stderr}", QColor("red"))
            self.status_tree_model.clear_status() # Clear tree on error
            # Ensure buttons are disabled
            if stage_all_btn: stage_all_btn.setEnabled(False)
            if unstage_all_btn: unstage_all_btn.setEnabled(False)
        # Don't update status bar here, let _on_branches_refreshed do it finally

    @pyqtSlot()
    def _refresh_branch_list(self):
        """异步获取并更新分支列表"""
        if not self.git_handler or not self.git_handler.is_valid_repo(): return
        logging.debug("Requesting formatted branch list...")
        self.git_handler.get_branches_formatted_async(self._on_branches_refreshed)

    @pyqtSlot(int, str, str)
    def _on_branches_refreshed(self, return_code, stdout, stderr):
        """处理异步 git branch 的结果并更新状态栏"""
        if not self.branch_list_widget or not self.git_handler:
            logging.error("Branch list or GitHandler not initialized when branches refreshed.")
            return # Cannot proceed

        self.branch_list_widget.clear()
        current_branch_name = None
        is_valid = self.git_handler.is_valid_repo() # Check validity again

        if return_code == 0 and is_valid:
            lines = stdout.strip().splitlines()
            logging.debug(f"Branches received: {len(lines)} lines")
            for line in lines:
                if not line: continue
                parts = line.strip().split(' ', 1) # Split only on the first space
                is_current = parts[0] == '*'
                branch_name = parts[1].strip() if len(parts) > 1 else parts[0].strip() # Get name

                if not branch_name: continue # Skip if name is somehow empty

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

            # Ensure the current branch item is selected in the list
            if current_branch_name:
                 items = self.branch_list_widget.findItems(current_branch_name, Qt.MatchFlag.MatchExactly)
                 if items:
                     self.branch_list_widget.setCurrentItem(items[0])
                     # Optionally scroll to the current item
                     # self.branch_list_widget.scrollToItem(items[0], QAbstractItemView.ScrollHint.PositionAtCenter)

        elif is_valid: # Check if still valid repo even if command failed
            logging.error(f"Failed to get branches: RC={return_code}, Error: {stderr}")
            self._append_output(f"❌ 获取分支列表失败:\n{stderr}", QColor("red"))
        elif not is_valid:
             logging.warning("Repository became invalid before branches could be refreshed.")

        # --- Update Status Bar ---
        repo_path_short = self.git_handler.get_repo_path() or "(未选择)"
        if len(repo_path_short) > 40: repo_path_short = f"...{repo_path_short[-37:]}"

        branch_display = current_branch_name if current_branch_name else ("(未知分支)" if is_valid else "(无效仓库)")
        status_message = f"分支: {branch_display} | 仓库: {repo_path_short}"
        if self.status_bar: self.status_bar.showMessage(status_message, 0) # Set final status message (0 = permanent)


    @pyqtSlot()
    def _refresh_log_view(self):
        """异步获取并更新提交历史表格"""
        if not self.git_handler or not self.git_handler.is_valid_repo(): return
        logging.debug("Requesting formatted log...")
        if self.log_table_widget: self.log_table_widget.setRowCount(0) # Clear table immediately
        if self.commit_details_textedit: self.commit_details_textedit.clear() # Clear details view too
        self.git_handler.get_log_formatted_async(count=200, finished_slot=self._on_log_refreshed) # Increase count

    @pyqtSlot(int, str, str)
    def _on_log_refreshed(self, return_code, stdout, stderr):
        """处理异步 git log 的结果"""
        if not self.log_table_widget:
             logging.error("Log table widget not initialized when log refreshed.")
             return

        if return_code == 0:
            lines = stdout.strip().splitlines()
            logging.debug(f"Log received ({len(lines)} entries). Populating table...")
            self.log_table_widget.setUpdatesEnabled(False) # Optimize population
            self.log_table_widget.setRowCount(0) # Clear before adding valid rows
            monospace_font = QFont("Courier New") # Font for graph/hash
            valid_rows = 0
            for line in lines:
                line = line.strip()
                if not line: continue

                # Basic check to skip lines that are likely just graph characters
                if line.startswith(('/', '|', '\\', '* ')) and '\t' not in line:
                    logging.debug(f"Skipping potential graph-only line: {repr(line)}")
                    continue # Skip this line

                try:
                    graph_part = ""
                    # More robust split: expect 4 parts separated by tab
                    # Format: <graph-maybe><hash>\t<author>\t<date>\t<message>
                    parts = line.split('\t', 3)

                    if len(parts) == 4:
                        hash_maybe_graph, author, date, message = parts

                        # Try to separate graph from hash
                        first_token_match = re.match(r'^([\s\\/|*]*)([a-fA-F0-9]+)', hash_maybe_graph)
                        if first_token_match:
                            graph_part = first_token_match.group(1).strip()
                            commit_hash = first_token_match.group(2)
                        else:
                            # If regex fails, assume the first part is mostly hash (might include graph)
                            commit_hash = hash_maybe_graph.strip().split(' ')[-1] # Best guess
                            graph_part = hash_maybe_graph[:-len(commit_hash)].strip()
                            if not re.fullmatch(r'[a-fA-F0-9]+', commit_hash): # If guess is bad, log warning
                                 logging.warning(f"Could not reliably extract hash from log segment: '{hash_maybe_graph}'")
                                 commit_hash = hash_maybe_graph.strip() # Fallback to whole segment


                        display_message = f"{graph_part} {message}".strip() if graph_part else message

                        # Ensure we have a valid hash before proceeding
                        if not commit_hash:
                             logging.warning(f"Parsed commit hash is empty for line: {repr(line)}")
                             continue

                        # Pre-increment row count before adding items
                        self.log_table_widget.setRowCount(valid_rows + 1)

                        hash_item = QTableWidgetItem(commit_hash[:7]) # Show shortened hash in table
                        author_item = QTableWidgetItem(author.strip())
                        date_item = QTableWidgetItem(date.strip())
                        message_item = QTableWidgetItem(display_message)

                        # Set items non-editable
                        flags = Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled
                        hash_item.setFlags(flags)
                        author_item.setFlags(flags)
                        date_item.setFlags(flags)
                        message_item.setFlags(flags)

                        # Store the *full* hash in UserRole for later use
                        hash_item.setData(Qt.ItemDataRole.UserRole, commit_hash)

                        # Apply monospace font where appropriate
                        hash_item.setFont(monospace_font)
                        message_item.setFont(monospace_font) # Apply to message/graph column

                        self.log_table_widget.setItem(valid_rows, 0, hash_item)
                        self.log_table_widget.setItem(valid_rows, 1, author_item)
                        self.log_table_widget.setItem(valid_rows, 2, date_item)
                        self.log_table_widget.setItem(valid_rows, 3, message_item)
                        valid_rows += 1
                    else:
                        # Log lines that couldn't be split into 4 parts
                        logging.warning(f"Could not parse log line into 4 parts: {repr(line)}")
                        continue # Skip this row

                except Exception as e:
                    logging.error(f"Error processing log line: '{line}' - {e}", exc_info=True)
                    continue # Skip to next line on error

            # No need to set row count again if pre-incremented
            self.log_table_widget.setUpdatesEnabled(True) # Re-enable updates
            logging.info(f"Log table populated with {valid_rows} valid entries.")

        else:
            logging.error(f"Failed to get log: RC={return_code}, Error: {stderr}")
            self._append_output(f"❌ 获取提交历史失败:\n{stderr}", QColor("red"))

        # Clear status bar message if it was "refreshing"
        if self.status_bar:
            current_message = self.status_bar.currentMessage()
            if "正在刷新" in current_message:
                 # Let the final status update from _on_branches_refreshed handle the message
                 pass
                 # self.status_bar.clearMessage()


    # --- Repository Selection ---
    def _select_repository(self):
        """打开目录选择对话框以选择 Git 仓库"""
        start_path = self.git_handler.get_repo_path() if self.git_handler else None
        # If no repo is set or the path is invalid, default to user's home directory
        if not start_path or not os.path.isdir(start_path):
            start_path = os.path.expanduser("~")

        dir_path = QFileDialog.getExistingDirectory(self, "选择 Git 仓库目录", start_path)

        if dir_path:
            if not self.git_handler:
                 logging.error("GitHandler not initialized during repository selection.")
                 QMessageBox.critical(self, "内部错误", "Git 处理程序未初始化。")
                 return

            try:
                # Clear previous state before loading new repo
                if self.output_display: self.output_display.clear()
                if self.diff_text_edit: self.diff_text_edit.clear()
                if self.commit_details_textedit: self.commit_details_textedit.clear()
                if self.sequence_display: self.sequence_display.clear()
                self.current_command_sequence = []
                self._update_sequence_display() # Update empty display
                if self.status_tree_model: self.status_tree_model.clear_status()
                if self.branch_list_widget: self.branch_list_widget.clear()
                if self.log_table_widget: self.log_table_widget.setRowCount(0)

                # Set the new path and update status (which triggers refreshes)
                self.git_handler.set_repo_path(dir_path)
                self._update_repo_status() # This will handle UI updates and view refreshes
                logging.info(f"用户选择了新的仓库目录: {dir_path}")

            except ValueError as e: # Catch potential errors from set_repo_path (e.g., not a git repo)
                QMessageBox.warning(self, "选择仓库失败", str(e))
                logging.error(f"设置仓库路径失败: {e}")
                # Ensure UI reflects the failed state
                self.git_handler.set_repo_path(None) # Reset internal path
                self._update_repo_status() # Update UI to show "(未选择)" or error state
            except Exception as e:
                 logging.exception("选择仓库时发生意外错误。")
                 QMessageBox.critical(self, "意外错误", f"选择仓库时出错: {e}")


    # --- Command Button Slots ---
    def _add_files(self):
        """弹出对话框让用户输入要暂存的文件/目录"""
        if not self.git_handler or not self.git_handler.is_valid_repo():
             QMessageBox.warning(self, "操作无效", "请先选择一个有效的 Git 仓库。")
             return
        files_str, ok = QInputDialog.getText(self, "暂存文件",
                                             "输入要暂存的文件或目录 (用空格分隔，可用引号):",
                                             QLineEdit.EchoMode.Normal)
        if ok and files_str:
            try:
                file_list = shlex.split(files_str.strip())
                if file_list:
                    self._stage_files(file_list) # Use helper method
                else:
                    QMessageBox.information(self, "无操作", "未输入文件。")
            except ValueError as e:
                 QMessageBox.warning(self, "输入错误", f"无法解析文件列表: {e}")
                 logging.warning(f"无法解析暂存文件输入 '{files_str}': {e}")
        elif ok: # User pressed OK but entered nothing
             QMessageBox.information(self, "无操作", "未输入文件。")

    def _add_commit(self):
        """弹出对话框获取提交信息并执行 git commit -m"""
        if not self.git_handler or not self.git_handler.is_valid_repo():
             QMessageBox.warning(self, "操作无效", "请先选择一个有效的 Git 仓库。")
             return
        commit_msg, ok = QInputDialog.getText(self, "提交暂存的更改",
                                              "输入提交信息:",
                                              QLineEdit.EchoMode.Normal)
        if ok and commit_msg:
            safe_msg = shlex.quote(commit_msg.strip())
            self._execute_command_if_valid_repo(["git", "commit", "-m", safe_msg])
        elif ok and not commit_msg: # User pressed OK but entered nothing
            QMessageBox.warning(self, "提交中止", "提交信息不能为空。")

    def _add_commit_am(self):
        """弹出对话框获取提交信息并执行 git commit -am"""
        if not self.git_handler or not self.git_handler.is_valid_repo():
             QMessageBox.warning(self, "操作无效", "请先选择一个有效的 Git 仓库。")
             return
        commit_msg, ok = QInputDialog.getText(self, "暂存所有已跟踪文件并提交",
                                              "输入提交信息:",
                                              QLineEdit.EchoMode.Normal)
        if ok and commit_msg:
            safe_msg = shlex.quote(commit_msg.strip())
            self._execute_command_if_valid_repo(["git", "commit", "-am", safe_msg])
        elif ok and not commit_msg:
            QMessageBox.warning(self, "提交中止", "提交信息不能为空。")

    # --- Sequence Operations ---
    def _update_sequence_display(self):
        """更新命令序列（快捷键预览）显示区域"""
        if self.sequence_display:
            self.sequence_display.setText("\n".join(self.current_command_sequence))

    def _clear_sequence(self):
        """清空命令序列（快捷键预览）构建器"""
        self.current_command_sequence = []
        self._update_sequence_display()
        if self.status_bar: self.status_bar.showMessage("命令序列预览已清空", 2000)
        logging.info("命令序列预览已清空。")

    def _execute_sequence(self):
        """执行命令序列（快捷键预览）构建器中的命令"""
        if not self.git_handler or not self.git_handler.is_valid_repo():
            QMessageBox.critical(self, "错误", "仓库无效，无法执行序列。")
            return
        if not self.current_command_sequence:
            QMessageBox.information(self, "提示", "命令序列预览为空，无需执行。")
            return

        sequence_to_run = list(self.current_command_sequence) # Copy the list
        logging.info(f"准备执行预览的序列: {sequence_to_run}")
        self._run_command_list_sequentially(sequence_to_run)


    # --- Core Command Execution Logic ---
    def _run_command_list_sequentially(self, command_strings: list[str], refresh_on_success=True):
        """
        按顺序执行一列表 Git 命令字符串。
        """
        if not self.git_handler or not self.git_handler.is_valid_repo():
             logging.error("尝试在无效仓库中执行命令列表。")
             QMessageBox.critical(self, "错误", "仓库无效，操作中止。")
             return

        logging.debug(f"准备执行命令列表: {command_strings}, 成功后刷新: {refresh_on_success}")
        self._set_ui_busy(True) # Disable UI elements during execution

        def execute_next(index):
            if index >= len(command_strings):
                self._append_output("\n✅ --- 所有命令执行完毕 ---", QColor("green"))
                self._set_ui_busy(False) # Re-enable UI
                if refresh_on_success:
                    self._refresh_all_views() # Refresh everything
                else:
                    self._refresh_branch_list() # Always refresh branches at least
                return

            cmd_str = command_strings[index].strip()
            logging.debug(f"执行命令 #{index + 1}/{len(command_strings)}: {repr(cmd_str)}")

            if not cmd_str:
                logging.debug("跳过空命令。")
                QTimer.singleShot(0, lambda idx=index + 1: execute_next(idx))
                return

            try:
                command_parts = shlex.split(cmd_str)
                logging.debug(f"解析结果: {command_parts}")
            except ValueError as e:
                err_msg = f"❌ 解析错误 '{cmd_str}': {e}"
                self._append_output(err_msg, QColor("red"))
                self._append_output("--- 执行中止 ---", QColor("red"))
                logging.error(err_msg)
                self._set_ui_busy(False) # Re-enable UI on parsing error
                return # Stop the sequence

            if not command_parts:
                logging.debug("解析结果为空，跳过。")
                QTimer.singleShot(0, lambda idx=index + 1: execute_next(idx))
                return

            display_cmd = ' '.join(shlex.quote(part) for part in command_parts)
            self._append_output(f"\n▶️ 执行: {display_cmd}", QColor("blue"))

            @pyqtSlot(int, str, str)
            def on_command_finished(return_code, stdout, stderr):
                if stdout: self._append_output(f"stdout:\n{stdout.strip()}")
                if stderr: self._append_output(f"stderr:\n{stderr.strip()}", QColor("red"))

                if return_code == 0:
                    self._append_output(f"✅ 成功: '{display_cmd}'", QColor("darkGreen"))
                    QTimer.singleShot(0, lambda idx=index + 1: execute_next(idx))
                else:
                    err_msg = f"❌ 失败 (RC: {return_code}) '{display_cmd}'，执行中止。"
                    logging.error(f"命令执行失败! Cmd: '{display_cmd}', RC: {return_code}, Stderr: {stderr.strip()}")
                    self._append_output(err_msg, QColor("red"))
                    self._set_ui_busy(False) # Re-enable UI

            @pyqtSlot(str)
            def on_progress(message):
                if self.status_bar: self.status_bar.showMessage(message, 3000) # Show for 3 seconds

            # Execute the command asynchronously
            if self.git_handler:
                self.git_handler.execute_command_async(command_parts, on_command_finished, on_progress)
            else:
                 logging.error("GitHandler not available for command execution.")
                 self._append_output(f"❌ 内部错误：无法执行命令 '{display_cmd}'。", QColor("red"))
                 self._set_ui_busy(False)

        execute_next(0)


    def _set_ui_busy(self, busy: bool):
        """启用/禁用所有交互式 UI 元素，显示等待光标"""
        for key, item in self.command_buttons.items():
            if not item: continue # Skip if item somehow None
            action_text = getattr(item, 'text', lambda: '')() # Check if it's QAction
            if isinstance(item, QAction) and action_text in ["选择仓库(&O)...", "Git 全局配置(&G)...", "退出(&X)", "关于(&A)", "清空原始输出"]:
                 continue
            item.setEnabled(not busy)

        # Disable/enable view widgets only if they exist
        if self.shortcut_list_widget: self.shortcut_list_widget.setEnabled(not busy)
        if self.branch_list_widget: self.branch_list_widget.setEnabled(not busy)
        if self.status_tree_view: self.status_tree_view.setEnabled(not busy)
        if self.log_table_widget: self.log_table_widget.setEnabled(not busy)
        if self.diff_text_edit: self.diff_text_edit.setEnabled(not busy)
        if self.commit_details_textedit: self.commit_details_textedit.setEnabled(not busy)

        # Disable/enable global shortcuts
        if self.shortcut_manager: self.shortcut_manager.set_shortcuts_enabled(not busy)

        # Set cursor and status bar message
        if busy:
            if self.status_bar: self.status_bar.showMessage("⏳ 正在执行...", 0) # Permanent message while busy
            QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        else:
            QApplication.restoreOverrideCursor()
            # Status bar message should be updated by refresh logic or command completion


    def _append_output(self, text: str, color: QColor = None):
        """向原始输出区域追加文本，可指定颜色"""
        if not self.output_display: return

        cursor = self.output_display.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End) # Move cursor to end
        self.output_display.setTextCursor(cursor) # Apply cursor position

        original_format = self.output_display.currentCharFormat()
        fmt = QTextEdit().currentCharFormat() # Get a default format
        if color:
            fmt.setForeground(color)
        else:
            fmt.setForeground(self.output_display.palette().color(self.output_display.foregroundRole()))

        self.output_display.setCurrentCharFormat(fmt) # Apply format
        clean_text = text.rstrip('\n')
        self.output_display.insertPlainText(clean_text + "\n")
        self.output_display.setCurrentCharFormat(original_format)
        self.output_display.ensureCursorVisible()


    # --- Slot for Command Input ---
    @pyqtSlot()
    def _execute_command_from_input(self):
        """执行命令行输入框中的命令"""
        if not self.command_input: return
        command_text = self.command_input.text().strip()
        if not command_text: return

        logging.info(f"用户从命令行输入: {command_text}")
        prompt_color = QColor(Qt.GlobalColor.darkCyan)
        try:
            display_cmd = ' '.join(shlex.quote(part) for part in shlex.split(command_text))
        except ValueError:
            display_cmd = command_text # Fallback if quoting fails

        self._append_output(f"\n$ {display_cmd}", prompt_color)
        self.command_input.clear() # Clear input field
        self._run_command_list_sequentially([command_text]) # Pass original text


    # --- Shortcut Execution Logic (Called by ShortcutManager) ---
    def _execute_sequence_from_string(self, name: str, sequence_str: str):
        """执行从字符串（快捷键定义）加载的命令序列"""
        if not self.git_handler or not self.git_handler.is_valid_repo():
            QMessageBox.critical(self, "快捷键执行失败", f"无法执行快捷键 '{name}'，因为当前未选择有效的 Git 仓库。")
            logging.warning(f"Attempted to execute shortcut '{name}' with invalid repo.")
            return

        if self.status_bar: self.status_bar.showMessage(f"正在执行快捷键: {name}", 3000) # Temporary message

        commands = []
        lines = sequence_str.strip().splitlines()
        commands = [line.strip() for line in lines if line.strip()] # Filter empty lines

        if not commands:
            QMessageBox.warning(self, "快捷键无效", f"快捷键 '{name}' 解析后命令序列为空。")
            logging.warning(f"Shortcut '{name}' resulted in an empty command list after parsing.")
            return

        # Display the sequence in the preview area before execution
        self.current_command_sequence = commands
        self._update_sequence_display()

        logging.info(f"准备执行快捷键 '{name}' 的命令列表: {commands}")
        self._run_command_list_sequentially(commands)


    # --- Status View Actions ---
    @pyqtSlot()
    def _stage_all(self):
        """执行 git add . (暂存所有未暂存和未跟踪的文件)"""
        logging.info("请求暂存所有更改 (git add .)")
        self._execute_command_if_valid_repo(["git", "add", "."])

    @pyqtSlot()
    def _unstage_all(self):
        """执行 git reset HEAD -- (撤销所有已暂存文件的暂存)"""
        if self.status_tree_model and self.status_tree_model.staged_root.rowCount() == 0:
            QMessageBox.information(self, "无操作", "没有已暂存的文件可供撤销。")
            logging.info("请求撤销全部暂存，但没有文件处于暂存状态。")
            return
        logging.info("请求撤销全部暂存 (git reset HEAD --)")
        self._execute_command_if_valid_repo(["git", "reset", "HEAD", "--"])

    def _stage_files(self, files: list[str]):
        """执行 git add -- <files>"""
        if not files: return
        logging.info(f"请求暂存特定文件: {files}")
        self._execute_command_if_valid_repo(["git", "add", "--"] + files)

    def _unstage_files(self, files: list[str]):
        """执行 git reset HEAD -- <files>"""
        if not files: return
        logging.info(f"请求撤销暂存特定文件: {files}")
        self._execute_command_if_valid_repo(["git", "reset", "HEAD", "--"] + files)


    # --- Status View Context Menu ---
    @pyqtSlot(QPoint)
    def _show_status_context_menu(self, pos):
        """显示状态树视图的右键上下文菜单"""
        if not self.git_handler or not self.git_handler.is_valid_repo(): return
        if not self.status_tree_view or not self.status_tree_model: return

        selected_indexes = self.status_tree_view.selectedIndexes()
        if not selected_indexes:
            logging.debug("Status context menu requested, but no items selected.")
            return

        selected_files_data = self.status_tree_model.get_selected_files(selected_indexes)

        menu = QMenu()
        added_action = False

        # Stage Action
        files_to_stage = selected_files_data.get(STATUS_UNSTAGED, []) + selected_files_data.get(STATUS_UNTRACKED, [])
        if files_to_stage:
            stage_action = QAction("暂存选中项 (+)", self)
            stage_action.triggered.connect(self._stage_selected_files)
            menu.addAction(stage_action)
            added_action = True

        # Unstage Action
        files_to_unstage = selected_files_data.get(STATUS_STAGED, [])
        if files_to_unstage:
            unstage_action = QAction("撤销暂存选中项 (-)", self)
            unstage_action.triggered.connect(self._unstage_selected_files)
            menu.addAction(unstage_action)
            added_action = True

        # Show Menu
        if added_action:
            global_pos = self.status_tree_view.viewport().mapToGlobal(pos)
            menu.exec(global_pos)
        else:
            logging.debug("No applicable actions for selected status items.")


    @pyqtSlot()
    def _stage_selected_files(self):
        """暂存状态树视图中选中的 Unstaged/Untracked 文件"""
        if not self.status_tree_view or not self.status_tree_model: return
        selected_indexes = self.status_tree_view.selectedIndexes()
        if not selected_indexes: return
        selected_files_data = self.status_tree_model.get_selected_files(selected_indexes)
        files_to_stage = list(set(selected_files_data.get(STATUS_UNSTAGED, []) + selected_files_data.get(STATUS_UNTRACKED, [])))
        if files_to_stage:
            self._stage_files(files_to_stage)
        else:
            logging.debug("Stage selected called, but no unstaged/untracked files found in selection.")


    @pyqtSlot()
    def _unstage_selected_files(self):
        """撤销状态树视图中选中的 Staged 文件的暂存"""
        if not self.status_tree_view or not self.status_tree_model: return
        selected_indexes = self.status_tree_view.selectedIndexes()
        if not selected_indexes: return
        selected_files_data = self.status_tree_model.get_selected_files(selected_indexes)
        files_to_unstage = list(set(selected_files_data.get(STATUS_STAGED, [])))
        if files_to_unstage:
            self._unstage_files(files_to_unstage)
        else:
             logging.debug("Unstage selected called, but no staged files found in selection.")


    # --- Status View Selection Change ---
    @pyqtSlot(QItemSelection, QItemSelection)
    def _status_selection_changed(self, selected: QItemSelection, deselected: QItemSelection):
        """当状态树中的选择发生变化时，尝试加载并显示差异"""
        if not self.status_tree_view or not self.status_tree_model or not self.diff_text_edit: return

        selected_indexes = self.status_tree_view.selectionModel().selectedIndexes()
        self.diff_text_edit.clear() # Clear diff on any selection change first

        if not selected_indexes:
            self.diff_text_edit.setPlaceholderText("选中已更改的文件以查看差异...")
            return

        # Only show diff for single file selection for simplicity
        # Calculate unique rows selected
        selected_rows = set()
        for index in selected_indexes:
             if index.isValid() and index.parent().isValid(): # Check it's a file item
                 selected_rows.add((index.parent(), index.row()))

        if len(selected_rows) != 1:
             self.diff_text_edit.setPlaceholderText("请选择单个文件以查看差异...")
             return

        # Get the first valid index from the selection to determine the file
        first_index = selected_indexes[0]
        item = self.status_tree_model.itemFromIndex(first_index)
        if not item: return

        parent = item.parent()
        if not parent or parent not in [self.status_tree_model.staged_root,
                                        self.status_tree_model.unstage_root,
                                        self.status_tree_model.untracked_root]:
            self.diff_text_edit.setPlaceholderText("请选择一个文件行以查看差异...")
            return

        path_item_index = self.status_tree_model.index(first_index.row(), 1, parent.index())
        path_item = self.status_tree_model.itemFromIndex(path_item_index)
        if not path_item:
             logging.warning("Could not find path item for selected status row.")
             self.diff_text_edit.setPlaceholderText("无法获取文件路径...")
             return

        file_path = path_item.data(Qt.ItemDataRole.UserRole + 1)
        section_type = parent.data(Qt.ItemDataRole.UserRole)
        status_code_item = parent.child(first_index.row(), 0) # Get status code item
        status_code_text = status_code_item.text() if status_code_item else "??"


        if not file_path:
            logging.warning("File path data is missing from path item.")
            self.diff_text_edit.setPlaceholderText("无法获取文件路径...")
            return

        self.diff_text_edit.setPlaceholderText(f"正在加载 '{os.path.basename(file_path)}' 的差异...")
        QApplication.processEvents() # Ensure placeholder updates

        staged_diff = (section_type == STATUS_STAGED)

        if section_type == STATUS_UNTRACKED:
            self.diff_text_edit.setText(f"'{file_path}' 是未跟踪的文件。\n\n无法显示与仓库的差异。")
            self.diff_text_edit.setPlaceholderText("")
        elif self.git_handler:
             self.git_handler.get_diff_async(file_path, staged=staged_diff, finished_slot=self._on_diff_received)
        else:
             self.diff_text_edit.setText("❌ 内部错误：Git 处理程序不可用。")


    @pyqtSlot(int, str, str)
    def _on_diff_received(self, return_code, stdout, stderr):
        """处理异步 git diff 的结果"""
        if not self.diff_text_edit: return
        self.diff_text_edit.setPlaceholderText("") # Clear loading placeholder
        if return_code == 0:
            if stdout:
                self.diff_text_edit.setText(stdout)
            else:
                self.diff_text_edit.setPlaceholderText("文件无差异。")
        else:
            error_message = f"❌ 获取差异失败:\n{stderr}"
            self.diff_text_edit.setText(error_message)
            logging.error(f"Git diff command failed: RC={return_code}, Error: {stderr}")


    # --- Branch List Actions ---
    @pyqtSlot(QListWidgetItem)
    def _branch_double_clicked(self, item: QListWidgetItem):
        """处理分支列表项双击事件 (切换分支)"""
        if not item: return
        if not self.git_handler or not self.git_handler.is_valid_repo(): return

        branch_name = item.text().strip()
        if branch_name.startswith("remotes/"):
            QMessageBox.information(self, "操作无效", f"不能直接切换到远程跟踪分支 '{branch_name}'。")
            return

        if item.font().bold():
             logging.info(f"用户尝试切换到当前分支 '{branch_name}'，无需操作。")
             if self.status_bar: self.status_bar.showMessage(f"已在分支 '{branch_name}'", 2000)
             return

        reply = QMessageBox.question(self, "切换分支",
                                     f"确定要切换到本地分支 '{branch_name}' 吗？",
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
                                     QMessageBox.StandardButton.Yes)

        if reply == QMessageBox.StandardButton.Yes:
             logging.info(f"请求切换到分支: {branch_name}")
             self._execute_command_if_valid_repo(["git", "checkout", branch_name])


    @pyqtSlot()
    def _create_branch_dialog(self):
        """显示创建新分支的对话框"""
        if not self.git_handler or not self.git_handler.is_valid_repo():
            QMessageBox.warning(self, "操作无效", "请先选择一个有效的 Git 仓库。")
            return

        branch_name, ok = QInputDialog.getText(self, "创建新分支",
                                               "输入新分支的名称:",
                                               QLineEdit.EchoMode.Normal)
        if ok and branch_name:
            clean_name = branch_name.strip().replace(" ", "_")
            if not clean_name:
                QMessageBox.warning(self, "创建失败", "分支名称不能为空。")
                return
            logging.info(f"请求创建新分支: {clean_name}")
            self._execute_command_if_valid_repo(["git", "branch", clean_name])
        elif ok:
            QMessageBox.warning(self, "创建失败", "分支名称不能为空。")


    @pyqtSlot(QPoint)
    def _show_branch_context_menu(self, pos):
        """显示分支列表的右键上下文菜单"""
        if not self.git_handler or not self.git_handler.is_valid_repo() or not self.branch_list_widget: return

        item = self.branch_list_widget.itemAt(pos)
        if not item: return

        menu = QMenu()
        branch_name = item.text().strip()
        is_remote = branch_name.startswith("remotes/")
        is_current = item.font().bold()
        added_action = False

        # Action: Checkout
        if not is_current and not is_remote:
            checkout_action = QAction(f"切换到 '{branch_name}'", self)
            checkout_action.triggered.connect(lambda checked=False, b=branch_name: self._execute_command_if_valid_repo(["git", "checkout", b]))
            menu.addAction(checkout_action)
            added_action = True

        # Action: Delete Local Branch
        if not is_current and not is_remote:
            delete_action = QAction(f"删除本地分支 '{branch_name}'...", self)
            delete_action.triggered.connect(lambda checked=False, b=branch_name: self._delete_branch_dialog(b))
            menu.addAction(delete_action)
            added_action = True

        # Action: Delete Remote Branch
        if is_remote:
             remote_parts = branch_name.split('/', 2) # remotes/origin/branchname
             if len(remote_parts) == 3:
                 remote_name = remote_parts[1]
                 remote_branch_name = remote_parts[2]
                 delete_remote_action = QAction(f"删除远程分支 '{remote_name}/{remote_branch_name}'...", self)
                 delete_remote_action.triggered.connect(lambda checked=False, rn=remote_name, rbn=remote_branch_name: self._delete_remote_branch_dialog(rn, rbn))
                 menu.addAction(delete_remote_action)
                 added_action = True

        # Show Menu
        if added_action:
            global_pos = self.branch_list_widget.mapToGlobal(pos)
            menu.exec(global_pos)
        else:
             logging.debug(f"No applicable context actions for branch item: {branch_name}")


    def _delete_branch_dialog(self, branch_name: str):
        """显示确认对话框并尝试删除指定的本地分支"""
        if not branch_name or branch_name.startswith("remotes/"):
            logging.error(f"Invalid branch name provided for local deletion: {branch_name}")
            return

        reply = QMessageBox.warning(self, "确认删除本地分支",
                                    f"确定要删除本地分支 '{branch_name}' 吗？\n\n此操作通常不可撤销！",
                                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
                                    QMessageBox.StandardButton.Cancel)

        if reply == QMessageBox.StandardButton.Yes:
            logging.info(f"请求删除本地分支: {branch_name} (using -d)")
            self._execute_command_if_valid_repo(["git", "branch", "-d", branch_name])

    def _delete_remote_branch_dialog(self, remote_name: str, branch_name: str):
        """显示确认对话框并尝试删除指定的远程分支"""
        if not remote_name or not branch_name:
            logging.error(f"Invalid remote/branch name for remote deletion: {remote_name}/{branch_name}")
            return

        reply = QMessageBox.warning(self, "确认删除远程分支",
                                    f"确定要从远程仓库 '{remote_name}' 删除分支 '{branch_name}' 吗？\n\n"
                                    f"将执行: git push {remote_name} --delete {branch_name}\n\n"
                                    f"此操作通常不可撤销，并会影响其他协作者！",
                                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
                                    QMessageBox.StandardButton.Cancel)

        if reply == QMessageBox.StandardButton.Yes:
             logging.info(f"请求删除远程分支: {remote_name}/{branch_name}")
             self._execute_command_if_valid_repo(["git", "push", remote_name, "--delete", branch_name])


    # --- Log View Actions ---
    @pyqtSlot()
    def _log_selection_changed(self):
        """当日志表格中的选择发生变化时，加载并显示 Commit 详情"""
        if not self.log_table_widget or not self.commit_details_textedit or not self.git_handler: return

        selected_items = self.log_table_widget.selectedItems()
        self.commit_details_textedit.clear() # Clear previous details

        if not selected_items:
             self.commit_details_textedit.setPlaceholderText("选中上方提交记录以查看详情...")
             return

        selected_row = self.log_table_widget.currentRow()
        if selected_row < 0:
             self.commit_details_textedit.setPlaceholderText("请选择一个提交记录。")
             return

        hash_item = self.log_table_widget.item(selected_row, 0) # Column 0 is Commit Hash

        if hash_item:
            commit_hash = hash_item.data(Qt.ItemDataRole.UserRole) # Get full hash stored
            if not commit_hash:
                commit_hash = hash_item.text().strip() # Fallback
                logging.warning(f"Commit hash item for row {selected_row} missing UserRole data, using text: {commit_hash}")

            if commit_hash:
                logging.debug(f"Log selection changed, requesting details for commit: {commit_hash}")
                self.commit_details_textedit.setPlaceholderText(f"正在加载 Commit '{commit_hash[:7]}...' 的详情...")
                QApplication.processEvents() # Ensure placeholder is displayed
                self.git_handler.get_commit_details_async(commit_hash, self._on_commit_details_received)
            else:
                self.commit_details_textedit.setPlaceholderText("无法获取选中提交的 Hash。")
                logging.error(f"无法从表格项获取有效的 Commit Hash (Row: {selected_row}).")
        else:
             self.commit_details_textedit.setPlaceholderText("无法确定选中的提交项。")
             logging.error(f"无法在日志表格中找到行 {selected_row} 的第 0 列项。")


    @pyqtSlot(int, str, str)
    def _on_commit_details_received(self, return_code, stdout, stderr):
        """处理异步 git show (commit details) 的结果"""
        if not self.commit_details_textedit: return
        self.commit_details_textedit.setPlaceholderText("") # Clear loading message
        if return_code == 0:
            self.commit_details_textedit.setText(stdout)
        else:
            error_message = f"❌ 获取提交详情失败:\n{stderr}"
            self.commit_details_textedit.setText(error_message)
            logging.error(f"获取 Commit 详情失败: RC={return_code}, Error: {stderr}")


    # --- Direct Action Slots (Simplified Wrappers) ---
    def _execute_command_if_valid_repo(self, command_list: list[str], refresh=True):
        """
        检查仓库是否有效，如果有效则执行命令列表。
        """
        if not self.git_handler or not self.git_handler.is_valid_repo():
            QMessageBox.warning(self, "操作无效", "请先选择一个有效的 Git 仓库。")
            logging.warning(f"Attempted to run command {command_list} with invalid repo.")
            return
        self._run_command_list_sequentially(command_list, refresh_on_success=refresh)

    def _run_pull(self):
        self._execute_command_if_valid_repo(["git", "pull"])

    def _run_push(self):
        self._execute_command_if_valid_repo(["git", "push"])

    def _run_fetch(self):
        self._execute_command_if_valid_repo(["git", "fetch"])

    def _run_switch_branch(self):
        """使用输入对话框切换分支"""
        if not self.git_handler or not self.git_handler.is_valid_repo():
            QMessageBox.warning(self, "操作无效", "仓库无效，无法切换分支。")
            return
        branch_name, ok = QInputDialog.getText(self, "切换分支",
                                               "输入要切换到的本地分支名称:",
                                               QLineEdit.EchoMode.Normal)
        if ok and branch_name:
            self._execute_command_if_valid_repo(["git", "checkout", branch_name.strip()])
        elif ok and not branch_name:
            QMessageBox.warning(self, "操作取消", "分支名称不能为空。")

    def _run_list_remotes(self):
        self._execute_command_if_valid_repo(["git", "remote", "-v"], refresh=False)


    # --- Settings Dialog Slot ---
    def _open_settings_dialog(self):
        """打开全局 Git 配置对话框"""
        dialog = SettingsDialog(self)
        if dialog.exec():
            config_data = dialog.get_data()
            commands_to_run = []
            name_val = config_data.get("user.name")
            email_val = config_data.get("user.email")

            if name_val and name_val.strip():
                commands_to_run.append(f"git config --global user.name {shlex.quote(name_val.strip())}")
            if email_val and email_val.strip():
                commands_to_run.append(f"git config --global user.email {shlex.quote(email_val.strip())}")

            if commands_to_run:
                 confirmation_msg = "将执行以下全局 Git 配置命令:\n\n" + "\n".join(commands_to_run) + "\n\n确定吗？"
                 reply = QMessageBox.question(self, "应用全局配置", confirmation_msg,
                                                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
                                                QMessageBox.StandardButton.Yes)
                 if reply == QMessageBox.StandardButton.Yes:
                     logging.info(f"Executing global config commands: {commands_to_run}")
                     # Run commands sequentially, don't need repo refresh after global config
                     # Need to ensure GitHandler can execute global commands
                     if self.git_handler:
                         self._run_command_list_sequentially(commands_to_run, refresh_on_success=False)
                     else:
                          logging.error("GitHandler not available for settings command.")
                          QMessageBox.critical(self, "错误", "无法执行配置命令。")

                 else:
                     QMessageBox.information(self, "操作取消", "未应用全局配置更改。")
            else:
                QMessageBox.information(self, "无更改", "未输入有效的用户名或邮箱信息。")


    # --- Other Helper Methods ---
    def _show_about_dialog(self):
        """显示关于对话框"""
        try:
            version = self.windowTitle().split('v')[-1].strip()
        except:
            version = "N/A"

        QMessageBox.about( self, "关于 简易 Git GUI",
            f"**简易 Git GUI**\n\n"
            f"版本: {version}\n\n"
            "一个使用 PyQt6 构建的基础 Git 图形界面。\n\n"
            "**主要功能:**\n"
            "- 仓库选择与状态显示\n"
            "- 文件状态树视图 (暂存/未暂存/未跟踪)\n"
            "  - 右键菜单进行暂存/撤销暂存\n"
            "- 分支列表\n"
            "  - 双击切换本地分支\n"
            "  - 右键删除本地/远程分支 (带确认)\n"
            "  - 创建新分支按钮\n"
            "- 提交历史 (Log) 表格\n"
            "  - 选择提交记录查看详情 (git show)\n"
            "- 文件差异 (Diff) 视图\n"
            "- 快捷键命令预览/执行/保存\n"
            "- 命令行输入框直接执行 Git 命令\n"
            "- 常用操作按钮 (Pull, Push, Fetch, Commit...)\n"
            "- Git 全局配置 (用户名/邮箱)\n"
            "- 异步执行 Git 命令避免 UI 阻塞\n\n"
            "作者: AI & Contributor"
        )

    def closeEvent(self, event):
        """处理窗口关闭事件"""
        logging.info("应用程序关闭请求。")

        # --- Removed DB Closing Logic ---
        # Based on db_handler.py, connections are managed per-operation,
        # so no global close is needed here.

        # Optional: Check for running Git operations
        try:
            active_count = len(self.git_handler.active_operations) if hasattr(self.git_handler, 'active_operations') and self.git_handler.active_operations is not None else 0
            if active_count > 0:
                 logging.warning(f"窗口关闭时仍有 {active_count} 个 Git 操作可能在后台运行。")
                 # Consider if you want to warn the user or attempt graceful shutdown
                 # reply = QMessageBox.question(self, "确认退出",
                 #                             f"仍有 {active_count} 个 Git 操作正在进行中。\n"
                 #                             "立即退出可能会中断这些操作。\n\n"
                 #                             "确定要退出吗？",
                 #                             QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                 #                             QMessageBox.StandardButton.No)
                 # if reply == QMessageBox.StandardButton.No:
                 #     event.ignore() # Prevent closing
                 #     return
                 # else:
                 #     logging.info("用户选择退出，即使有活动操作。")
                 #     # Attempt to signal workers to stop (requires changes in GitWorker)
        except Exception as e:
            logging.exception("关闭窗口时检查 Git 操作出错。")

        logging.info("应用程序正在关闭。")
        event.accept() # Allow the window to close

# Example main execution block (if this is the main script)
if __name__ == '__main__':
    # Setup logging
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - [%(levelname)s] - %(filename)s:%(lineno)d - %(message)s')
    logging.info("应用程序启动...")

    app = QApplication(sys.argv)
    mainWin = MainWindow()
    mainWin.show()
    sys.exit(app.exec())