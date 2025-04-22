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
from PyQt6.QtCore import Qt, pyqtSlot, QSize, QTimer, QModelIndex, QUrl, QPoint, QItemSelection
# 确保这些导入指向您的模块的正确位置
from .dialogs import ShortcutDialog, SettingsDialog
from .shortcut_manager import ShortcutManager
from .status_tree_model import StatusTreeModel, STATUS_STAGED, STATUS_UNSTAGED, STATUS_UNTRACKED
from core.git_handler import GitHandler
from core.db_handler import DatabaseHandler

class MainWindow(QMainWindow):
    """Git GUI 主窗口"""
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Git GUI v1.7")
        self.setGeometry(100, 100, 1200, 900)

        self.db_handler = DatabaseHandler()
        self.git_handler = GitHandler()
        self.shortcut_manager = ShortcutManager(self, self.db_handler, self.git_handler)

        self.current_command_sequence = []
        self.command_buttons = {}

        # UI 元素占位符
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
        self.commit_details_textedit = None
        self._output_tab_index = -1 # 新增：存储输出标签页的索引

        self._init_ui()
        self.shortcut_manager.load_and_register_shortcuts()
        self._update_repo_status()

        logging.info("主窗口初始化完成。")

    def _add_command_to_sequence(self, command_to_add: str | list[str]):
        """将命令字符串添加到序列列表并更新显示"""
        if isinstance(command_to_add, list):
            # 如果需要，将列表元素连接成一个字符串
            command_str = ' '.join(shlex.quote(part) for part in command_to_add)
        elif isinstance(command_to_add, str):
            command_str = command_to_add
        else:
            logging.warning(f"无效的命令类型传递给 _add_command_to_sequence: {type(command_to_add)}")
            return

        self.current_command_sequence.append(command_str)
        self._update_sequence_display()
        logging.debug(f"命令添加到序列: {command_str}")

    def _init_ui(self):
        """初始化用户界面 (状态交互, 分支交互, 日志详情)"""
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)

        # --- 仓库选择区域 ---
        repo_layout = QHBoxLayout()
        self.repo_label = QLabel("当前仓库: (未选择)")
        self.repo_label.setToolTip("当前操作的 Git 仓库路径")
        repo_layout.addWidget(self.repo_label, 1)
        select_repo_button = QPushButton("选择仓库")
        select_repo_button.setToolTip("选择仓库目录")
        select_repo_button.clicked.connect(self._select_repository)
        repo_layout.addWidget(select_repo_button)
        main_layout.addLayout(repo_layout)

        # --- 主分隔器 ---
        splitter = QSplitter(Qt.Orientation.Horizontal)
        main_layout.addWidget(splitter, 1)

        # --- 左侧面板 ---
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(5, 0, 5, 5)
        left_layout.setSpacing(6)
        splitter.addWidget(left_panel)

        # --- 修改后的按钮连接 ---
        command_buttons_layout_1 = QHBoxLayout()
        # Status: 将 "git status" 添加到序列 (注意: 这不会刷新视图本身)
        self._add_command_button(command_buttons_layout_1, "Status", "添加 'git status' 到序列", lambda: self._add_command_to_sequence("git status"))
        # Add .: 将 "git add ." 添加到序列
        self._add_command_button(command_buttons_layout_1, "Add .", "添加 'git add .' 到序列", lambda: self._add_command_to_sequence("git add ."))
        # Add...: 保留直接执行 (需要对话框)
        self._add_command_button(command_buttons_layout_1, "Add...", "暂存选中文件 (直接执行)", self._add_files)
        left_layout.addLayout(command_buttons_layout_1)

        command_buttons_layout_2 = QHBoxLayout()
        # Commit...: 保留直接执行 (需要对话框)
        self._add_command_button(command_buttons_layout_2, "Commit...", "提交暂存更改 (直接执行)", self._add_commit)
        # Commit -a...: 保留直接执行 (需要对话框)
        self._add_command_button(command_buttons_layout_2, "Commit -a...", "暂存所有已跟踪文件并提交 (直接执行)", self._add_commit_am)
        # Log: 保留直接刷新日志视图
        self._add_command_button(command_buttons_layout_2, "Log", "刷新提交历史视图 (Tab)", self._refresh_log_view)
        left_layout.addLayout(command_buttons_layout_2)

        more_commands_layout = QHBoxLayout()
        # Pull: 将 "git pull" 添加到序列
        self._add_command_button(more_commands_layout, "Pull", "添加 'git pull' 到序列", lambda: self._add_command_to_sequence("git pull"))
        # Push: 将 "git push" 添加到序列
        self._add_command_button(more_commands_layout, "Push", "添加 'git push' 到序列", lambda: self._add_command_to_sequence("git push"))
        # Fetch: 将 "git fetch" 添加到序列
        self._add_command_button(more_commands_layout, "Fetch", "添加 'git fetch' 到序列", lambda: self._add_command_to_sequence("git fetch"))
        left_layout.addLayout(more_commands_layout)
        # --- 修改后的按钮连接结束 ---

        # 命令序列构建器
        left_layout.addWidget(QLabel("命令序列构建器:")) # 恢复原始标签
        self.sequence_display = QTextEdit()
        self.sequence_display.setReadOnly(True) # 保持只读，由按钮/快捷键填充
        self.sequence_display.setPlaceholderText("点击上方按钮构建命令序列，或从快捷键加载...") # 更新占位符
        self.sequence_display.setFixedHeight(80)
        left_layout.addWidget(self.sequence_display)

        sequence_actions_layout = QHBoxLayout()
        execute_button = QPushButton("执行序列")
        execute_button.setToolTip("执行上方构建的命令序列")
        execute_button.setStyleSheet("background-color: lightgreen;")
        execute_button.clicked.connect(self._execute_sequence)
        self.command_buttons['execute'] = execute_button
        clear_button = QPushButton("清空序列")
        clear_button.setToolTip("清空上方构建的命令序列")
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

        # --- 分支列表 ---
        branch_label_layout = QHBoxLayout()
        branch_label_layout.addWidget(QLabel("分支列表:"))
        branch_label_layout.addStretch()
        create_branch_button = QPushButton("+ 新分支")
        create_branch_button.setToolTip("创建新的本地分支")
        create_branch_button.clicked.connect(self._create_branch_dialog)
        self.command_buttons['create_branch'] = create_branch_button
        branch_label_layout.addWidget(create_branch_button)
        left_layout.addLayout(branch_label_layout)

        self.branch_list_widget = QListWidget()
        self.branch_list_widget.setToolTip("双击切换分支, 右键操作")
        self.branch_list_widget.itemDoubleClicked.connect(self._branch_double_clicked)
        self.branch_list_widget.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.branch_list_widget.customContextMenuRequested.connect(self._show_branch_context_menu)
        left_layout.addWidget(self.branch_list_widget, 1)

        # 已保存的快捷键列表
        left_layout.addWidget(QLabel("快捷键组合:"))
        self.shortcut_list_widget = QListWidget()
        self.shortcut_list_widget.setToolTip("双击加载到序列，右键删除") # 更新提示信息
        # 连接双击事件以将序列加载到构建器/预览区域
        self.shortcut_list_widget.itemDoubleClicked.connect(self._load_shortcut_into_builder)
        self.shortcut_list_widget.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.shortcut_list_widget.customContextMenuRequested.connect(self.shortcut_manager.show_shortcut_context_menu)
        left_layout.addWidget(self.shortcut_list_widget, 1)


        # --- 右侧面板 (标签页 + 命令输入) ---
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(0)
        splitter.addWidget(right_panel)

        # 标签页组件
        self.main_tab_widget = QTabWidget()
        right_layout.addWidget(self.main_tab_widget, 1)

        # -- 标签页 1: 状态 / 文件 --
        status_tab_widget = QWidget()
        status_tab_layout = QVBoxLayout(status_tab_widget)
        status_tab_layout.setContentsMargins(5, 5, 5, 5)
        status_tab_layout.setSpacing(4)
        self.main_tab_widget.addTab(status_tab_widget, "状态 / 文件")

        status_action_layout = QHBoxLayout()
        stage_all_button = QPushButton("全部暂存 (+)")
        stage_all_button.setToolTip("暂存所有未暂存和未跟踪的文件 (git add .)")
        stage_all_button.clicked.connect(self._stage_all) # 全部暂存/撤销暂存仍然直接执行
        self.command_buttons['stage_all'] = stage_all_button
        unstage_all_button = QPushButton("全部撤销暂存 (-)")
        unstage_all_button.setToolTip("撤销所有已暂存文件的暂存状态 (git reset HEAD --)")
        unstage_all_button.clicked.connect(self._unstage_all) # 全部暂存/撤销暂存仍然直接执行
        self.command_buttons['unstage_all'] = unstage_all_button
        # 添加一个仅刷新状态视图的按钮
        refresh_status_button = QPushButton("刷新状态")
        refresh_status_button.setToolTip("重新加载当前文件状态")
        refresh_status_button.clicked.connect(self._refresh_status_view)
        self.command_buttons['refresh_status'] = refresh_status_button # 可选的跟踪
        status_action_layout.addWidget(stage_all_button)
        status_action_layout.addWidget(unstage_all_button)
        status_action_layout.addStretch()
        status_action_layout.addWidget(refresh_status_button) # 在这里添加刷新按钮
        status_tab_layout.addLayout(status_action_layout)

        self.status_tree_view = QTreeView()
        self.status_tree_model = StatusTreeModel(self)
        self.status_tree_view.setModel(self.status_tree_model)
        self.status_tree_view.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.status_tree_view.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.status_tree_view.header().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.status_tree_view.header().setStretchLastSection(False)
        self.status_tree_view.setColumnWidth(0, 100)
        self.status_tree_view.setAlternatingRowColors(True)
        self.status_tree_view.selectionModel().selectionChanged.connect(self._status_selection_changed)
        self.status_tree_view.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.status_tree_view.customContextMenuRequested.connect(self._show_status_context_menu)
        status_tab_layout.addWidget(self.status_tree_view, 1)

        # -- 标签页 2: 提交历史 --
        log_tab_widget = QWidget()
        log_tab_layout = QVBoxLayout(log_tab_widget)
        log_tab_layout.setContentsMargins(5, 5, 5, 5)
        log_tab_layout.setSpacing(4)
        self.main_tab_widget.addTab(log_tab_widget, "提交历史 (Log)")

        self.log_table_widget = QTableWidget()
        self.log_table_widget.setColumnCount(4)
        self.log_table_widget.setHorizontalHeaderLabels(["Commit", "Author", "Date", "Message"])
        self.log_table_widget.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.log_table_widget.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.log_table_widget.verticalHeader().setVisible(False)
        self.log_table_widget.setColumnWidth(0, 80)
        self.log_table_widget.setColumnWidth(1, 140)
        self.log_table_widget.setColumnWidth(2, 100)
        self.log_table_widget.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self.log_table_widget.itemSelectionChanged.connect(self._log_selection_changed)
        log_tab_layout.addWidget(self.log_table_widget, 2)

        separator = QFrame()
        separator.setFrameShape(QFrame.Shape.HLine)
        separator.setFrameShadow(QFrame.Shadow.Sunken)
        log_tab_layout.addWidget(separator)

        log_tab_layout.addWidget(QLabel("提交详情:"))
        self.commit_details_textedit = QTextEdit()
        self.commit_details_textedit.setReadOnly(True)
        self.commit_details_textedit.setFontFamily("Courier New")
        self.commit_details_textedit.setPlaceholderText("选中上方提交记录以查看详情...")
        log_tab_layout.addWidget(self.commit_details_textedit, 1)


        # -- 标签页 3: 差异视图 --
        diff_tab_widget = QWidget()
        diff_tab_layout = QVBoxLayout(diff_tab_widget)
        diff_tab_layout.setContentsMargins(5, 5, 5, 5)
        self.main_tab_widget.addTab(diff_tab_widget, "差异 (Diff)")
        self.diff_text_edit = QTextEdit()
        self.diff_text_edit.setReadOnly(True)
        self.diff_text_edit.setFontFamily("Courier New")
        self.diff_text_edit.setPlaceholderText("选中已更改的文件以查看差异...")
        diff_tab_layout.addWidget(self.diff_text_edit, 1)


        # -- 标签页 4: 原始输出 --
        output_tab_widget = QWidget()
        output_tab_layout = QVBoxLayout(output_tab_widget)
        output_tab_layout.setContentsMargins(5, 5, 5, 5)
        self.main_tab_widget.addTab(output_tab_widget, "原始输出")
        # 存储输出标签页的索引
        self._output_tab_index = self.main_tab_widget.indexOf(output_tab_widget)

        self.output_display = QTextEdit()
        self.output_display.setReadOnly(True)
        self.output_display.setFontFamily("Courier New")
        self.output_display.setPlaceholderText("Git 命令和命令行输出将显示在此处...")
        output_tab_layout.addWidget(self.output_display, 1)


        # 命令输入区域 (标签页下方)
        command_input_container = QWidget()
        command_input_layout = QHBoxLayout(command_input_container)
        command_input_layout.setContentsMargins(5, 3, 5, 5)
        command_input_layout.setSpacing(4)
        command_input_label = QLabel("$")
        self.command_input = QLineEdit()
        self.command_input.setPlaceholderText("输入 Git 命令并按 Enter 直接执行") # 明确直接执行
        command_font = QFont("Courier New")
        self.command_input.setFont(command_font)
        command_input_style = """
            QLineEdit { background-color: #ffffff; border: 1px solid #abadb3; border-radius: 2px; padding: 4px 6px; color: #000000; }
            QLineEdit:focus { border: 1px solid #0078d4; }
            QLineEdit::placeholder { color: #a0a0a0; }
            QLineEdit:disabled { background-color: #f0f0f0; color: #a0a0a0; }
        """
        self.command_input.setStyleSheet(command_input_style)
        self.command_input.returnPressed.connect(self._execute_command_from_input)
        self.command_buttons['command_input'] = self.command_input

        command_input_layout.addWidget(command_input_label)
        command_input_layout.addWidget(self.command_input)
        right_layout.addWidget(command_input_container)

        # 分隔器设置
        splitter.setSizes([int(self.width() * 0.35), int(self.width() * 0.65)]) # 调整比例

        # 状态栏
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("就绪")

        # 菜单和工具栏
        self._create_menu()
        self._create_toolbar()

    # --- 菜单、工具栏、按钮创建 ---
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
        refresh_action.setShortcut(QKeySequence(Qt.Key.Key_F5))
        refresh_action.triggered.connect(self._refresh_all_views)
        repo_menu.addAction(refresh_action)
        self.command_buttons['refresh_action'] = refresh_action
        repo_menu.addSeparator()
        create_branch_action = QAction("创建分支(&N)...", self)
        create_branch_action.triggered.connect(self._create_branch_dialog)
        repo_menu.addAction(create_branch_action)
        self.command_buttons['create_branch_menu'] = create_branch_action
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

        style = self.style()
        refresh_icon = style.standardIcon(QStyle.StandardPixmap.SP_BrowserReload)
        pull_icon = style.standardIcon(QStyle.StandardPixmap.SP_ArrowDown)
        push_icon = style.standardIcon(QStyle.StandardPixmap.SP_ArrowUp)
        new_branch_icon = style.standardIcon(QStyle.StandardPixmap.SP_FileDialogNewFolder)
        switch_branch_icon = style.standardIcon(QStyle.StandardPixmap.SP_FileDialogDetailedView)
        remotes_icon = style.standardIcon(QStyle.StandardPixmap.SP_ComputerIcon)
        clear_icon = style.standardIcon(QStyle.StandardPixmap.SP_DialogResetButton)

        refresh_tb_action = QAction(refresh_icon, "刷新", self)
        refresh_tb_action.setToolTip("刷新状态、分支和日志视图 (F5)")
        refresh_tb_action.triggered.connect(self._refresh_all_views)
        toolbar.addAction(refresh_tb_action)
        self.command_buttons['refresh_tb_action'] = refresh_tb_action
        toolbar.addSeparator()

        pull_action = QAction(pull_icon, "Pull", self)
        pull_action.setToolTip("添加 'git pull' 到序列") # 工具栏按钮也添加到序列
        pull_action.triggered.connect(lambda: self._add_command_to_sequence("git pull"))
        toolbar.addAction(pull_action)
        self.command_buttons['pull_action'] = pull_action

        push_action = QAction(push_icon,"Push", self)
        push_action.setToolTip("添加 'git push' 到序列") # 工具栏按钮也添加到序列
        push_action.triggered.connect(lambda: self._add_command_to_sequence("git push"))
        toolbar.addAction(push_action)
        self.command_buttons['push_action'] = push_action
        toolbar.addSeparator()

        create_branch_tb_action = QAction(new_branch_icon, "新分支", self)
        create_branch_tb_action.setToolTip("创建新的本地分支 (直接执行)") # 保持直接执行
        create_branch_tb_action.triggered.connect(self._create_branch_dialog)
        toolbar.addAction(create_branch_tb_action)
        self.command_buttons['create_branch_tb'] = create_branch_tb_action

        switch_branch_action_tb = QAction(switch_branch_icon, "切换分支...", self)
        switch_branch_action_tb.setToolTip("切换本地分支 (直接执行)") # 保持直接执行
        switch_branch_action_tb.triggered.connect(self._run_switch_branch)
        toolbar.addAction(switch_branch_action_tb)
        self.command_buttons['switch_branch_action_tb'] = switch_branch_action_tb

        list_remotes_action_tb = QAction(remotes_icon, "远程列表", self)
        list_remotes_action_tb.setToolTip("列出远程仓库 (直接执行)") # 保持直接执行
        list_remotes_action_tb.triggered.connect(self._run_list_remotes)
        toolbar.addAction(list_remotes_action_tb)
        self.command_buttons['list_remotes_action_tb'] = list_remotes_action_tb
        toolbar.addSeparator()

        clear_output_action = QAction(clear_icon, "清空原始输出", self)
        clear_output_action.setToolTip("清空'原始输出'标签页的内容")
        if self.output_display:
             clear_output_action.triggered.connect(self.output_display.clear)
        else:
             logging.warning("创建清除操作时，输出显示未初始化。")
        toolbar.addAction(clear_output_action)


    def _add_command_button(self, layout, text, tooltip, slot):
        button = QPushButton(text)
        button.setToolTip(tooltip)
        button.clicked.connect(slot)
        layout.addWidget(button)
        button_key = f"button_{text.lower().replace('...', '').replace(' ', '_').replace('/', '_').replace('.', '_dot_').replace('-', '_dash_')}"
        self.command_buttons[button_key] = button
        return button

    # --- 状态更新和 UI 启用/禁用 ---
    def _update_repo_status(self):
        repo_path = self.git_handler.get_repo_path() if self.git_handler else None
        is_valid = self.git_handler.is_valid_repo() if self.git_handler else False
        display_path = repo_path if repo_path and len(repo_path) < 60 else f"...{repo_path[-57:]}" if repo_path else "(未选择)"
        if self.repo_label: self.repo_label.setText(f"当前仓库: {display_path}")

        self._update_ui_enable_state(is_valid)

        if is_valid:
            if self.repo_label: self.repo_label.setStyleSheet("") # 重置样式
            if self.status_bar: self.status_bar.showMessage(f"正在加载仓库: {repo_path}", 0)
            QApplication.processEvents()
            self._refresh_all_views()
        else:
            if self.repo_label: self.repo_label.setStyleSheet("color: red;")
            if self.status_bar: self.status_bar.showMessage("请选择一个有效的 Git 仓库目录", 0)
            if self.status_tree_model: self.status_tree_model.clear_status()
            if self.branch_list_widget: self.branch_list_widget.clear()
            if self.log_table_widget: self.log_table_widget.setRowCount(0)
            if self.diff_text_edit: self.diff_text_edit.clear()
            if self.commit_details_textedit: self.commit_details_textedit.clear()
            if self.output_display: self.output_display.clear()
            if self.sequence_display: self.sequence_display.clear()
            self.current_command_sequence = [] # 也清空序列数据

    def _update_ui_enable_state(self, enabled: bool):
        """启用或禁用依赖于有效仓库的 UI 元素"""
        repo_dependent_keys = [
            'execute', 'clear', 'save',
            'button_status', 'button_add__dot_', 'button_add...', 'button_commit...', 'button_commit__dash_a...', 'button_log',
            'button_pull', 'button_push', 'button_fetch',
            'stage_all', 'unstage_all', 'refresh_status', # 添加了 refresh_status 按钮
            'refresh_action', 'refresh_tb_action',
            'create_branch', 'create_branch_menu', 'create_branch_tb',
            'switch_branch_action', 'switch_branch_action_tb',
            'list_remotes_action', 'list_remotes_action_tb',
            'pull_action', 'push_action', # 工具栏 Pull/Push 已经通过序列变化处理
            'command_input'
        ]

        for key, item in self.command_buttons.items():
            if not item: continue
            # 跳过“选择仓库”按钮和“Git 全局配置”操作，它们不应被禁用
            if isinstance(item, QPushButton) and item.text() == "选择仓库": continue
            if isinstance(item, QAction) and item.text() in ["选择仓库(&O)...", "Git 全局配置(&G)...", "退出(&X)", "关于(&A)", "清空原始输出"]: continue

            if key in repo_dependent_keys:
                item.setEnabled(enabled)
            else:
                 # 处理未明确列出但依赖于仓库的项目，如果存在
                 pass # 当前的键涵盖了大多数交互式项

        if self.shortcut_list_widget: self.shortcut_list_widget.setEnabled(enabled) # 如果仓库有效则启用快捷键列表
        if self.branch_list_widget: self.branch_list_widget.setEnabled(enabled)
        if self.status_tree_view: self.status_tree_view.setEnabled(enabled)
        if self.log_table_widget: self.log_table_widget.setEnabled(enabled)
        if self.diff_text_edit: self.diff_text_edit.setEnabled(enabled)
        if self.commit_details_textedit: self.commit_details_textedit.setEnabled(enabled)

        if self.shortcut_manager: self.shortcut_manager.set_shortcuts_enabled(enabled)

        # 确保某些菜单项始终启用
        for action in self.findChildren(QAction):
            action_text = action.text()
            if action_text in ["选择仓库(&O)...", "Git 全局配置(&G)...", "退出(&X)", "关于(&A)", "清空原始输出"]:
                action.setEnabled(True)

    @pyqtSlot(int, str, str)
    def _update_branch_display(self, return_code, stdout, stderr):
        pass # 未使用，被 _on_branches_refreshed 替换

    # --- 刷新视图 ---
    def _refresh_all_views(self):
        """刷新所有主要视图: 状态、分支、日志"""
        if not self.git_handler or not self.git_handler.is_valid_repo():
            logging.warning("尝试在无效仓库或没有 GitHandler 的情况下刷新视图。")
            self._update_ui_enable_state(False)
            return
        logging.info("正在刷新状态、分支和日志视图...")
        if self.status_bar: self.status_bar.showMessage("正在刷新...", 0)
        QApplication.processEvents()
        self._refresh_status_view()
        self._refresh_branch_list()
        self._refresh_log_view()
        # 注意: Diff 和提交详情是根据选择变化刷新的，而不是整个视图刷新。

    @pyqtSlot()
    def _refresh_status_view(self):
        """异步获取并更新状态树视图"""
        if not self.git_handler or not self.git_handler.is_valid_repo(): return
        logging.debug("正在请求 status porcelain...")
        stage_all_btn = self.command_buttons.get('stage_all')
        unstage_all_btn = self.command_buttons.get('unstage_all')
        if stage_all_btn: stage_all_btn.setEnabled(False)
        if unstage_all_btn: unstage_all_btn.setEnabled(False)
        self.git_handler.get_status_porcelain_async(self._on_status_refreshed)

    @pyqtSlot(int, str, str)
    def _on_status_refreshed(self, return_code, stdout, stderr):
        """处理异步 git status 的结果"""
        if not self.status_tree_model or not self.status_tree_view:
             logging.error("状态树模型或视图在状态刷新时未初始化。")
             return

        stage_all_btn = self.command_buttons.get('stage_all')
        unstage_all_btn = self.command_buttons.get('unstage_all')

        if return_code == 0:
            logging.debug("接收到 status porcelain，正在填充模型...")
            self.status_tree_model.parse_and_populate(stdout)
            self.status_tree_view.expandAll()
            self.status_tree_view.resizeColumnToContents(0)
            self.status_tree_view.setColumnWidth(0, max(100, self.status_tree_view.columnWidth(0)))

            has_unstaged_or_untracked = self.status_tree_model.unstage_root.rowCount() > 0 or self.status_tree_model.untracked_root.rowCount() > 0
            if stage_all_btn: stage_all_btn.setEnabled(has_unstaged_or_untracked)
            if unstage_all_btn: unstage_all_btn.setEnabled(self.status_tree_model.staged_root.rowCount() > 0)
        else:
            logging.error(f"获取状态失败: RC={return_code}, 错误: {stderr}")
            self._append_output(f"❌ 获取 Git 状态失败:\n{stderr}", QColor("red"))
            self.status_tree_model.clear_status()
            if stage_all_btn: stage_all_btn.setEnabled(False)
            if unstage_all_btn: unstage_all_btn.setEnabled(False)

    @pyqtSlot()
    def _refresh_branch_list(self):
        """异步获取并更新分支列表"""
        if not self.git_handler or not self.git_handler.is_valid_repo(): return
        logging.debug("正在请求格式化分支列表...")
        self.git_handler.get_branches_formatted_async(self._on_branches_refreshed)

    @pyqtSlot(int, str, str)
    def _on_branches_refreshed(self, return_code, stdout, stderr):
        """处理异步 git branch 的结果并更新状态栏"""
        if not self.branch_list_widget:
             logging.error("分支列表组件在分支刷新时未初始化。")
             if self.git_handler and self.status_bar: # 如果可能，尝试更新状态栏
                 is_valid = self.git_handler.is_valid_repo()
                 repo_path_short = self.git_handler.get_repo_path() or "(未选择)"
                 if len(repo_path_short) > 40: repo_path_short = f"...{repo_path_short[-37:]}"
                 branch_display = "(未知分支)" if is_valid else "(无效仓库)"
                 status_message = f"分支: {branch_display} | 仓库: {repo_path_short}"
                 self.status_bar.showMessage(status_message, 0)
             return

        if not self.git_handler:
            logging.error("GitHandler 在分支刷新时未初始化。")
            return

        self.branch_list_widget.clear()
        current_branch_name = None
        is_valid = self.git_handler.is_valid_repo()

        if return_code == 0 and is_valid:
            lines = stdout.strip().splitlines()
            logging.debug(f"接收到分支: {len(lines)} 行")
            for line in lines:
                if not line: continue
                # 使用正则表达式正确分割分支名称和可能的当前标记
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

            if current_branch_name:
                 items = self.branch_list_widget.findItems(current_branch_name, Qt.MatchFlag.MatchExactly)
                 if items: self.branch_list_widget.setCurrentItem(items[0])

        elif is_valid:
            logging.error(f"获取分支失败: RC={return_code}, 错误: {stderr}")
            self._append_output(f"❌ 获取分支列表失败:\n{stderr}", QColor("red"))
        elif not is_valid:
             logging.warning("仓库在分支刷新前变得无效。")

        # 更新状态栏
        repo_path_short = self.git_handler.get_repo_path() or "(未选择)"
        if len(repo_path_short) > 40: repo_path_short = f"...{repo_path_short[-37:]}"
        branch_display = current_branch_name if current_branch_name else ("(未知分支)" if is_valid else "(无效仓库)")
        status_message = f"分支: {branch_display} | 仓库: {repo_path_short}"
        if self.status_bar: self.status_bar.showMessage(status_message, 0)


    @pyqtSlot()
    def _refresh_log_view(self):
        """异步获取并更新提交历史表格"""
        if not self.git_handler or not self.git_handler.is_valid_repo(): return
        logging.debug("正在请求格式化日志...")
        if self.log_table_widget: self.log_table_widget.setRowCount(0)
        if self.commit_details_textedit: self.commit_details_textedit.clear()
        self.git_handler.get_log_formatted_async(count=200, finished_slot=self._on_log_refreshed)

    @pyqtSlot(int, str, str)
    def _on_log_refreshed(self, return_code, stdout, stderr):
        """处理异步 git log 的结果"""
        if not self.log_table_widget:
             logging.error("日志表格组件在日志刷新时未初始化。")
             return

        if return_code == 0:
            lines = stdout.strip().splitlines()
            logging.debug(f"接收到日志 ({len(lines)} 条记录)。正在填充表格...")
            self.log_table_widget.setUpdatesEnabled(False)
            self.log_table_widget.setRowCount(0)
            monospace_font = QFont("Courier New")
            valid_rows = 0
            for line in lines:
                line = line.strip()
                if not line: continue
                # 使用正则表达式解析带图的日志行
                match = re.match(r'^([\s\\/|*.-]*?)?([a-fA-F0-9]+)\s+(.*?)\s+(.*?)\s+(.*)$', line)
                if match:
                    graph_part = match.group(1) if match.group(1) else ""
                    commit_hash = match.group(2)
                    author = match.group(3)
                    date = match.group(4)
                    message = match.group(5)

                    if not commit_hash:
                         logging.warning(f"解析的提交哈希为空，对应的行为: {repr(line)}")
                         continue

                    self.log_table_widget.setRowCount(valid_rows + 1)
                    hash_item = QTableWidgetItem(commit_hash[:7])
                    author_item = QTableWidgetItem(author.strip())
                    date_item = QTableWidgetItem(date.strip())
                    message_item = QTableWidgetItem(message.strip())
                    flags = Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled
                    hash_item.setFlags(flags); author_item.setFlags(flags); date_item.setFlags(flags); message_item.setFlags(flags)
                    hash_item.setData(Qt.ItemDataRole.UserRole, commit_hash)
                    hash_item.setFont(monospace_font); message_item.setFont(monospace_font)
                    self.log_table_widget.setItem(valid_rows, 0, hash_item); self.log_table_widget.setItem(valid_rows, 1, author_item); self.log_table_widget.setItem(valid_rows, 2, date_item); self.log_table_widget.setItem(valid_rows, 3, message_item)
                    valid_rows += 1
                else:
                    # 处理可能只是图或不符合主要格式的行
                    if re.match(r'^[\s\\/|*.-]+$', line): # 跳过看起来纯粹是图的行
                         logging.debug(f"跳过潜在的纯图行: {repr(line)}")
                         continue
                    logging.warning(f"无法解析日志行: {repr(line)}")
                    # 可选地将未解析的行添加到表格并给出警告
                    # self.log_table_widget.setRowCount(valid_rows + 1)
                    # self.log_table_widget.setItem(valid_rows, 3, QTableWidgetItem(f"解析错误: {line}"))
                    # valid_rows += 1


            self.log_table_widget.setUpdatesEnabled(True)
            logging.info(f"日志表格已填充 {valid_rows} 个有效条目。")
        else:
            logging.error(f"获取日志失败: RC={return_code}, 错误: {stderr}")
            self._append_output(f"❌ 获取提交历史失败:\n{stderr}", QColor("red"))
        if self.status_bar:
            current_message = self.status_bar.currentMessage()
            if "正在刷新" in current_message: pass # 如果仍然存在刷新消息则保持


    # --- 仓库选择 ---
    def _select_repository(self):
        """打开目录选择对话框以选择 Git 仓库"""
        start_path = self.git_handler.get_repo_path() if self.git_handler and self.git_handler.get_repo_path() else None
        if not start_path or not os.path.isdir(start_path):
            start_path = os.path.expanduser("~")
            # 尝试寻找附近可能的 Git 仓库根目录
            if os.path.isdir(os.path.join(os.getcwd(), '.git')):
                 start_path = os.getcwd()
            elif os.path.isdir(os.path.join(os.path.expanduser("~"), 'git')):
                 start_path = os.path.join(os.path.expanduser("~"), 'git')

        dir_path = QFileDialog.getExistingDirectory(self, "选择 Git 仓库目录", start_path)
        if dir_path:
            if not self.git_handler:
                 logging.error("仓库选择期间 GitHandler 未初始化。")
                 QMessageBox.critical(self, "内部错误", "Git 处理程序未初始化。")
                 return
            try:
                # 立即清空相关的 UI 元素
                if self.output_display: self.output_display.clear()
                if self.diff_text_edit: self.diff_text_edit.clear()
                if self.commit_details_textedit: self.commit_details_textedit.clear()
                if self.sequence_display: self.sequence_display.clear()
                self.current_command_sequence = []
                self._update_sequence_display()
                if self.status_tree_model: self.status_tree_model.clear_status()
                if self.branch_list_widget: self.branch_list_widget.clear()
                if self.log_table_widget: self.log_table_widget.setRowCount(0)

                self.git_handler.set_repo_path(dir_path) # 此调用包括 is_valid_repo 检查
                self._update_repo_status() # 如果有效将触发刷新
                logging.info(f"用户选择了新的仓库目录: {dir_path}")
            except ValueError as e:
                QMessageBox.warning(self, "选择仓库失败", str(e))
                logging.error(f"设置仓库路径失败: {e}")
                self.git_handler.set_repo_path(None) # 确保处理程序状态重置
                self._update_repo_status() # 更新 UI 为无效状态
            except Exception as e:
                 logging.exception("选择仓库时发生意外错误。")
                 QMessageBox.critical(self, "意外错误", f"选择仓库时出错: {e}")
                 self.git_handler.set_repo_path(None)
                 self._update_repo_status()


    # --- 命令按钮槽 ---
    def _add_files(self):
        """弹出对话框让用户输入要暂存的文件/目录 (直接执行)"""
        if not self.git_handler or not self.git_handler.is_valid_repo(): QMessageBox.warning(self, "操作无效", "请先选择一个有效的 Git 仓库。"); return
        files_str, ok = QInputDialog.getText(self, "暂存文件", "输入要暂存的文件或目录 (用空格分隔，可用引号):", QLineEdit.EchoMode.Normal)
        if ok and files_str:
            try:
                # 安全地将输入字符串分割成文件路径列表
                file_list = shlex.split(files_str.strip())
                if file_list:
                    # 将 'add' 命令和指定的文件添加到序列并执行
                    commands = [f"git add -- {shlex.quote(part)}" for part in file_list]
                    # 通过列表执行器直接执行这些命令
                    self._run_command_list_sequentially(commands)
                else:
                    QMessageBox.information(self, "无操作", "未输入文件。")
            except ValueError as e:
                QMessageBox.warning(self, "输入错误", f"无法解析文件列表: {e}")
                logging.warning(f"无法解析暂存文件输入 '{files_str}': {e}")
        elif ok:
            QMessageBox.information(self, "无操作", "未输入文件。")

    def _add_commit(self):
        """弹出对话框获取提交信息并执行 git commit -m (直接执行)"""
        if not self.git_handler or not self.git_handler.is_valid_repo(): QMessageBox.warning(self, "操作无效", "请先选择一个有效的 Git 仓库。"); return
        commit_msg, ok = QInputDialog.getText(self, "提交暂存的更改", "输入提交信息:", QLineEdit.EchoMode.Normal)
        if ok and commit_msg:
            # 直接执行 commit 命令
            self._run_command_list_sequentially([f"git commit -m {shlex.quote(commit_msg.strip())}"])
        elif ok and not commit_msg: QMessageBox.warning(self, "提交中止", "提交信息不能为空。")

    def _add_commit_am(self):
        """弹出对话框获取提交信息并执行 git commit -am (直接执行)"""
        if not self.git_handler or not self.git_handler.is_valid_repo(): QMessageBox.warning(self, "操作无效", "请先选择一个有效的 Git 仓库。"); return
        commit_msg, ok = QInputDialog.getText(self, "暂存所有已跟踪文件并提交", "输入提交信息:", QLineEdit.EchoMode.Normal)
        if ok and commit_msg:
            # 直接执行 commit 命令
            self._run_command_list_sequentially([f"git commit -am {shlex.quote(commit_msg.strip())}"])
        elif ok and not commit_msg: QMessageBox.warning(self, "提交中止", "提交信息不能为空。")

    # --- 序列操作 ---
    def _update_sequence_display(self):
        """更新命令序列构建器显示区域"""
        if self.sequence_display: self.sequence_display.setText("\n".join(self.current_command_sequence))

    def _clear_sequence(self):
        """清空命令序列构建器"""
        self.current_command_sequence = []
        self._update_sequence_display()
        if self.status_bar: self.status_bar.showMessage("命令序列已清空", 2000)
        logging.info("命令序列已清空。")

    def _execute_sequence(self):
        """执行命令序列构建器中的命令"""
        if not self.git_handler or not self.git_handler.is_valid_repo(): QMessageBox.critical(self, "错误", "仓库无效，无法执行序列。"); return
        if not self.current_command_sequence: QMessageBox.information(self, "提示", "命令序列为空，无需执行。"); return
        sequence_to_run = list(self.current_command_sequence) # 复制
        logging.info(f"准备执行构建的序列: {sequence_to_run}")
        self._run_command_list_sequentially(sequence_to_run)
        # 序列构建器将在序列执行成功后在 _run_command_list_sequentially 中清空
        # 或者您可能希望在这里 *在* 执行之前清空它:
        # self.current_command_sequence = []
        # self._update_sequence_display()


    # --- 核心命令执行逻辑 ---
    def _run_command_list_sequentially(self, command_strings: list[str], refresh_on_success=True):
        """按顺序执行一列表 Git 命令字符串。"""
        if not self.git_handler: logging.error("GitHandler 不可用。"); QMessageBox.critical(self, "内部错误", "Git 处理程序丢失。"); return
        if not self.git_handler.is_valid_repo(): logging.error("尝试在无效仓库中执行命令列表。"); QMessageBox.critical(self, "错误", "仓库无效，操作中止。"); return

        logging.debug(f"准备执行命令列表: {command_strings}, 成功后刷新: {refresh_on_success}")

        # --- 新增：在执行前切换到原始输出标签页 ---
        if self.main_tab_widget and self._output_tab_index != -1:
             self.main_tab_widget.setCurrentIndex(self._output_tab_index)
             # 可选: 清空之前的输出或添加分隔符
             if self.output_display:
                  self._append_output("\n--- 开始执行新的命令序列 ---", QColor("darkCyan"))
                  self.output_display.ensureCursorVisible()
             QApplication.processEvents() # 确保标签页更改和潜在的清空可见

        self._set_ui_busy(True)

        def execute_next(index):
            if index >= len(command_strings):
                self._append_output("\n✅ --- 所有命令执行完毕 ---", QColor("green"))
                # 在成功执行后清空序列构建器
                self._clear_sequence()
                self._set_ui_busy(False)
                if refresh_on_success: self._refresh_all_views()
                else: self._refresh_branch_list() # 始终刷新分支，它们经常变化
                return

            cmd_str = command_strings[index].strip()
            logging.debug(f"执行命令 #{index + 1}/{len(command_strings)}: {repr(cmd_str)}")

            if not cmd_str:
                logging.debug("跳过空命令。")
                QTimer.singleShot(10, lambda idx=index + 1: execute_next(idx)); # 使用小延迟以避免冻结
                return

            try:
                # 使用 shlex.split 处理带引号的参数
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
                logging.debug("解析结果为空，跳过。")
                QTimer.singleShot(10, lambda idx=index + 1: execute_next(idx)); # 使用小延迟
                return

            display_cmd = ' '.join(shlex.quote(part) for part in command_parts)
            self._append_output(f"\n$ {display_cmd}", QColor("blue"))

            @pyqtSlot(int, str, str)
            def on_command_finished(return_code, stdout, stderr):
                if stdout: self._append_output(f"stdout:\n{stdout.strip()}")
                if stderr: self._append_output(f"stderr:\n{stderr.strip()}", QColor("red"))

                if return_code == 0:
                    self._append_output(f"✅ 成功: '{display_cmd}'", QColor("darkGreen"))
                    QTimer.singleShot(10, lambda idx=index + 1: execute_next(idx)) # 使用小延迟
                else:
                    err_msg = f"❌ 失败 (RC: {return_code}) '{display_cmd}'，执行中止。"
                    logging.error(f"命令执行失败! 命令: '{display_cmd}', 返回码: {return_code}, 标准错误: {stderr.strip()}")
                    self._append_output(err_msg, QColor("red"))
                    self._set_ui_busy(False)

            @pyqtSlot(str)
            def on_progress(message):
                if self.status_bar: self.status_bar.showMessage(message, 3000)

            self.git_handler.execute_command_async(command_parts, on_command_finished, on_progress)

        # 开始序列执行
        execute_next(0)


    def _set_ui_busy(self, busy: bool):
        """启用/禁用所有交互式 UI 元素，显示等待光标"""
        for key, item in self.command_buttons.items():
            if not item: continue
            # 检查项目是否是“选择仓库”按钮或某个始终启用的菜单/工具栏操作
            is_select_repo_button = isinstance(item, QPushButton) and item.text() == "选择仓库"
            is_always_enabled_action = isinstance(item, QAction) and item.text() in ["选择仓库(&O)...", "Git 全局配置(&G)...", "退出(&X)", "关于(&A)", "清空原始输出"]

            if not (is_select_repo_button or is_always_enabled_action):
                 item.setEnabled(not busy and self.git_handler.is_valid_repo() if not isinstance(item, QAction) else not busy) # 对大多数按钮保持仓库检查

        # 显式处理组件
        if self.shortcut_list_widget: self.shortcut_list_widget.setEnabled(not busy and self.git_handler.is_valid_repo())
        if self.branch_list_widget: self.branch_list_widget.setEnabled(not busy and self.git_handler.is_valid_repo())
        if self.status_tree_view: self.status_tree_view.setEnabled(not busy and self.git_handler.is_valid_repo())
        if self.log_table_widget: self.log_table_widget.setEnabled(not busy and self.git_handler.is_valid_repo())
        if self.diff_text_edit: self.diff_text_edit.setEnabled(not busy and self.git_handler.is_valid_repo())
        if self.commit_details_textedit: self.commit_details_textedit.setEnabled(not busy and self.git_handler.is_valid_repo())

        if self.shortcut_manager: self.shortcut_manager.set_shortcuts_enabled(not busy and self.git_handler.is_valid_repo())

        # 重新启用始终启用的操作
        for action in self.findChildren(QAction):
            action_text = action.text()
            if action_text in ["选择仓库(&O)...", "Git 全局配置(&G)...", "退出(&X)", "关于(&A)", "清空原始输出"]:
                action.setEnabled(True)

        if busy:
            if self.status_bar: self.status_bar.showMessage("⏳ 正在执行...", 0)
            QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        else:
            QApplication.restoreOverrideCursor()
            # 忙碌状态结束后恢复标准状态消息
            self._on_branches_refreshed(0, "", "") # 此方法更新状态栏中的分支/仓库信息


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
        # 否则: 使用原始格式的颜色

        self.output_display.setCurrentCharFormat(fmt)
        clean_text = text.rstrip('\n') # 如果存在尾随换行符则删除，我们自己添加一个
        self.output_display.insertPlainText(clean_text + "\n")

        # 恢复原始格式以用于后续文本
        self.output_display.setCurrentCharFormat(original_format)
        self.output_display.ensureCursorVisible()


    # --- 命令输入槽 ---
    @pyqtSlot()
    def _execute_command_from_input(self):
        """执行命令行输入框中的命令 (直接执行)"""
        if not self.command_input: return
        command_text = self.command_input.text().strip();
        if not command_text: return
        logging.info(f"用户从命令行输入: {command_text}"); prompt_color = QColor(Qt.GlobalColor.darkCyan)
        try:
            # 解析并重新引用以提高显示健壮性
            command_parts = shlex.split(command_text)
            display_cmd = ' '.join(shlex.quote(part) for part in command_parts)
        except ValueError:
            # 如果 shlex 失败则回退 (对于简单输入不应该发生，但要做好防御)
            display_cmd = command_text

        # 在清空输入之前将命令追加到输出
        self._append_output(f"\n$ {display_cmd}", prompt_color)
        self.command_input.clear()

        # 通过序列执行器执行命令
        self._run_command_list_sequentially([command_text])

    # --- 快捷键执行/加载 ---
    # 由 ShortcutManager 或列表中的双击调用
    def _load_shortcut_into_builder(self, item: QListWidgetItem = None):
        """加载选中的快捷键命令到序列构建器"""
        if not item: # 如果在其他地方需要，可能会在没有 item 的情况下调用
            item = self.shortcut_list_widget.currentItem()
            if not item: return

        shortcut_name = item.text()
        shortcut_data = self.shortcut_manager.get_shortcut_data_by_name(shortcut_name)
        if shortcut_data and shortcut_data.get('sequence'):
            sequence_str = shortcut_data['sequence']
            # 分割行，过滤空行，并更新序列数据和显示
            self.current_command_sequence = [line.strip() for line in sequence_str.strip().splitlines() if line.strip()]
            self._update_sequence_display()
            if self.status_bar: self.status_bar.showMessage(f"快捷键 '{shortcut_name}' 已加载到序列构建器", 3000)
            logging.info(f"快捷键 '{shortcut_name}' 已加载到构建器。")
        else:
            logging.warning(f"找不到快捷键 '{shortcut_name}' 的序列数据。")
            QMessageBox.warning(self, "加载失败", f"无法加载快捷键 '{shortcut_name}' 的命令序列。")


    def _execute_sequence_from_string(self, name: str, sequence_str: str):
        """执行从字符串（快捷键定义）加载的命令序列"""
        if not self.git_handler or not self.git_handler.is_valid_repo(): QMessageBox.critical(self, "快捷键执行失败", f"无法执行快捷键 '{name}'，仓库无效。"); return
        if self.status_bar: self.status_bar.showMessage(f"正在执行快捷键: {name}", 3000)

        commands = [line.strip() for line in sequence_str.strip().splitlines() if line.strip()]

        if not commands:
             QMessageBox.warning(self, "快捷键无效", f"快捷键 '{name}' 解析后命令序列为空。")
             logging.warning(f"快捷键 '{name}' 导致命令列表为空。")
             return

        # 在执行之前可视化地加载到构建器 (可选但有帮助)
        self.current_command_sequence = commands
        self._update_sequence_display()

        logging.info(f"准备执行快捷键 '{name}' 的命令列表: {commands}")
        self._run_command_list_sequentially(commands)

    # --- 状态视图操作 ---
    @pyqtSlot()
    def _stage_all(self): # 直接执行
        logging.info("请求暂存所有更改 (git add .)"); self._execute_command_if_valid_repo(["git", "add", "."])
    @pyqtSlot()
    def _unstage_all(self): # 直接执行
        if self.status_tree_model and self.status_tree_model.staged_root.rowCount() == 0: QMessageBox.information(self, "无操作", "没有已暂存的文件可供撤销。"); return
        logging.info("请求撤销全部暂存 (git reset HEAD --)"); self._execute_command_if_valid_repo(["git", "reset", "HEAD", "--"])
    def _stage_files(self, files: list[str]): # 直接执行 - 由上下文菜单使用
        if not files: return; logging.info(f"请求暂存特定文件: {files}"); self._execute_command_if_valid_repo(["git", "add", "--"] + files)
    def _unstage_files(self, files: list[str]): # 直接执行 - 由上下文菜单使用
        if not files: return; logging.info(f"请求撤销暂存特定文件: {files}"); self._execute_command_if_valid_repo(["git", "reset", "HEAD", "--"] + files)

    # --- 状态视图上下文菜单 ---
    @pyqtSlot(QPoint)
    def _show_status_context_menu(self, pos):
        """显示状态树视图的右键上下文菜单"""
        if not self.git_handler or not self.git_handler.is_valid_repo() or not self.status_tree_view or not self.status_tree_model: return
        index = self.status_tree_view.indexAt(pos)
        if not index.isValid(): return

        # 基于模型获取选中的文件，而不仅仅是点击的索引
        selected_indexes = self.status_tree_view.selectionModel().selectedIndexes()
        if not selected_indexes: return # 如果 indexAt(pos) 有效并且是选择的一部分，则不应该发生，但为了安全起见进行检查
        # 过滤每个选中行的第一列项，以避免重复
        unique_selected_rows = set()
        for sel_index in selected_indexes:
             unique_selected_rows.add(self.status_tree_model.index(sel_index.row(), 0, sel_index.parent()))

        selected_files_data = self.status_tree_model.get_selected_files(list(unique_selected_rows)); menu = QMenu(); added_action = False
        files_to_stage = selected_files_data.get(STATUS_UNSTAGED, []) + selected_files_data.get(STATUS_UNTRACKED, [])
        if files_to_stage: stage_action = QAction("暂存选中项 (+)", self); stage_action.triggered.connect(self._stage_selected_files); menu.addAction(stage_action); added_action = True
        files_to_unstage = selected_files_data.get(STATUS_STAGED, [])
        if files_to_unstage: unstage_action = QAction("撤销暂存选中项 (-)", self); unstage_action.triggered.connect(self._unstage_selected_files); menu.addAction(unstage_action); added_action = True

        # 添加将命令添加到序列的上下文菜单操作
        if added_action: menu.addSeparator()

        # 示例: 添加到序列操作
        # 注意: 这些会将 *通用* 命令添加到序列，而不是容易添加特定文件的命令
        # 以后如果需要，可以添加特定于上下文的序列添加操作。

        if added_action: menu.exec(self.status_tree_view.viewport().mapToGlobal(pos))
        else: logging.debug("所选状态项没有适用的操作。")


    @pyqtSlot()
    def _stage_selected_files(self):
        """暂存状态树视图中选中的 Unstaged/Untracked 文件"""
        if not self.status_tree_view or not self.status_tree_model: return
        selected_indexes = self.status_tree_view.selectionModel().selectedIndexes()
        if not selected_indexes: return
        # 过滤每个选中行的第一列项
        unique_selected_rows = set()
        for sel_index in selected_indexes:
             unique_selected_rows.add(self.status_tree_model.index(sel_index.row(), 0, sel_index.parent()))

        selected_files_data = self.status_tree_model.get_selected_files(list(unique_selected_rows))
        files_to_stage = list(set(selected_files_data.get(STATUS_UNSTAGED, []) + selected_files_data.get(STATUS_UNTRACKED, []))) # 使用集合处理树结构复杂时可能出现的重复项

        if files_to_stage:
            # 为每个文件构建命令并运行序列
            commands = [f"git add -- {shlex.quote(f)}" for f in files_to_stage]
            self._run_command_list_sequentially(commands)
        else:
            logging.debug("调用了暂存选中，但没有找到未暂存/未跟踪的文件。")
            QMessageBox.information(self, "无操作", "没有选中的未暂存或未跟踪文件可供暂存。")


    @pyqtSlot()
    def _unstage_selected_files(self):
        """撤销状态树视图中选中的 Staged 文件的暂存"""
        if not self.status_tree_view or not self.status_tree_model: return
        selected_indexes = self.status_tree_view.selectionModel().selectedIndexes()
        if not selected_indexes: return
        # 过滤每个选中行的第一列项
        unique_selected_rows = set()
        for sel_index in selected_indexes:
             unique_selected_rows.add(self.status_tree_model.index(sel_index.row(), 0, sel_index.parent()))

        selected_files_data = self.status_tree_model.get_selected_files(list(unique_selected_rows))
        files_to_unstage = list(set(selected_files_data.get(STATUS_STAGED, []))) # 使用集合

        if files_to_unstage:
             # 为每个文件构建命令并运行序列
            commands = [f"git reset HEAD -- {shlex.quote(f)}" for f in files_to_unstage]
            self._run_command_list_sequentially(commands)
        else:
            logging.debug("调用了撤销暂存选中，但没有找到已暂存的文件。")
            QMessageBox.information(self, "无操作", "没有选中的已暂存文件可供撤销暂存。")

    # --- 状态视图选择变化 ---
    @pyqtSlot(QItemSelection, QItemSelection)
    def _status_selection_changed(self, selected: QItemSelection, deselected: QItemSelection):
        """当状态树中的选择发生变化时，尝试加载并显示差异"""
        if not self.status_tree_view or not self.status_tree_model or not self.diff_text_edit: return

        self.diff_text_edit.clear() # 始终在选择变化时清空
        selected_indexes = self.status_tree_view.selectionModel().selectedIndexes()

        if not selected_indexes:
            self.diff_text_edit.setPlaceholderText("选中已更改的文件以查看差异...");
            return

        # 检查是否 *只有* 一个项目 (表示一个文件行) 被选中 (跨所有列)
        # 每行选中的第一列索引是唯一行选择的最佳指示符
        unique_selected_rows = set()
        for index in selected_indexes:
             if index.isValid() and index.parent().isValid():
                 # 获取第一列 (文件名项) 的索引
                 first_col_index = self.status_tree_model.index(index.row(), 0, index.parent())
                 unique_selected_rows.add(first_col_index)

        if len(unique_selected_rows) != 1:
            self.diff_text_edit.setPlaceholderText("请选择单个文件以查看差异...");
            return

        # 获取单个选中行的文件路径和状态类型
        first_row_index = list(unique_selected_rows)[0]
        path_item_index = self.status_tree_model.index(first_row_index.row(), 1, first_row_index.parent()) # 路径在列 1
        path_item = self.status_tree_model.itemFromIndex(path_item_index)

        if not path_item:
            logging.warning("找不到所选状态行的路径项。");
            self.diff_text_edit.setPlaceholderText("无法获取文件路径...");
            return

        file_path = path_item.data(Qt.ItemDataRole.UserRole + 1); # UserRole + 1 存储完整路径
        parent_item = path_item.parent()
        if not parent_item:
             logging.warning("文件路径项没有父项。");
             self.diff_text_edit.setPlaceholderText("无法确定文件状态...");
             return

        section_type = parent_item.data(Qt.ItemDataRole.UserRole); # UserRole 存储章节类型 (STAGED, UNSTAGED, UNTRACKED)

        if not file_path:
            logging.warning("文件路径数据丢失。");
            self.diff_text_edit.setPlaceholderText("无法获取文件路径...");
            return

        # 单独处理未跟踪文件，因为与仓库历史的差异没有意义
        if section_type == STATUS_UNTRACKED:
            self.diff_text_edit.setText(f"'{file_path}' 是未跟踪的文件。\n\n无法显示与仓库的差异。")
            self.diff_text_edit.setPlaceholderText("") # 设置文本后清空占位符
        elif self.git_handler:
            staged_diff = (section_type == STATUS_STAGED)
            self.diff_text_edit.setPlaceholderText(f"正在加载 '{os.path.basename(file_path)}' 的差异...");
            QApplication.processEvents() # 立即更新 UI
            self.git_handler.get_diff_async(file_path, staged=staged_diff, finished_slot=self._on_diff_received)
        else:
            self.diff_text_edit.setText("❌ 内部错误：Git 处理程序不可用。")
            self.diff_text_edit.setPlaceholderText("")


    @pyqtSlot(int, str, str)
    def _on_diff_received(self, return_code, stdout, stderr):
        """处理异步 git diff 的结果，并进行格式化显示"""
        if not self.diff_text_edit: return

        self.diff_text_edit.setPlaceholderText("") # 清空加载占位符

        if return_code == 0:
            if stdout.strip():
                self._display_formatted_diff(stdout) # 调用新的辅助方法进行格式化
            else:
                self.diff_text_edit.setText("文件无差异。") # 如果差异为空则设置简单文本
        else:
            error_message = f"❌ 获取差异失败:\n{stderr}"
            self.diff_text_edit.setText(error_message) # 直接设置错误文本
            logging.error(f"Git diff 失败: 返回码={return_code}, 错误:{stderr}")

    def _display_formatted_diff(self, diff_text: str):
        """格式化显示差异内容，高亮增减行"""
        if not self.diff_text_edit: return

        self.diff_text_edit.clear()
        cursor = self.diff_text_edit.textCursor()
        # 获取默认格式作为其他格式的基础
        default_format = self.diff_text_edit.currentCharFormat()

        # 定义用于高亮的格式
        add_format = QTextCharFormat(default_format)
        add_format.setForeground(QColor("darkGreen"))

        del_format = QTextCharFormat(default_format)
        del_format.setForeground(QColor("red"))

        header_format = QTextCharFormat(default_format)
        header_format.setForeground(QColor("gray")) # 对头部行使用灰色

        # 确保差异视图使用等宽字体
        monospace_font = QFont("Courier New")
        self.diff_text_edit.setFont(monospace_font)

        # 逐行处理
        lines = diff_text.splitlines()
        for line in lines:
            fmt_to_apply = default_format

            # 检查行前缀以进行格式化
            if line.startswith('diff ') or line.startswith('index ') or line.startswith('---') or line.startswith('+++') or line.startswith('@@ '):
                fmt_to_apply = header_format
            elif line.startswith('+'):
                fmt_to_apply = add_format
            elif line.startswith('-'):
                fmt_to_apply = del_format
            # 不以这些前缀开头的行将使用 default_format

            # 应用格式并插入文本
            cursor.insertText(line, fmt_to_apply)
            cursor.insertText("\n", default_format) # 确保换行符获得默认格式

        # 插入所有文本后将光标移动到开始位置
        cursor.movePosition(QTextCursor.MoveOperation.Start)
        self.diff_text_edit.setTextCursor(cursor)
        self.diff_text_edit.ensureCursorVisible() # 滚动到顶部

    # --- 分支列表操作 ---
    @pyqtSlot(QListWidgetItem)
    def _branch_double_clicked(self, item: QListWidgetItem): # 直接执行
        if not item or not self.git_handler or not self.git_handler.is_valid_repo(): return
        branch_name = item.text().strip();
        if branch_name.startswith("remotes/"): QMessageBox.information(self, "操作无效", f"不能直接切换到远程跟踪分支 '{branch_name}'。"); return
        if item.font().bold():
             logging.info(f"已在分支 '{branch_name}'。");
             if self.status_bar: self.status_bar.showMessage(f"已在分支 '{branch_name}'", 2000);
             return
        reply = QMessageBox.question(self, "切换分支", f"确定要切换到本地分支 '{branch_name}' 吗？\n\n未提交的更改将会被携带。", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel, QMessageBox.StandardButton.Yes)
        if reply == QMessageBox.StandardButton.Yes:
             logging.info(f"请求切换到分支: {branch_name}")
             # 使用 run_command_list_sequentially
             self._run_command_list_sequentially([f"git checkout {shlex.quote(branch_name)}"])


    @pyqtSlot()
    def _create_branch_dialog(self): # 直接执行
        if not self.git_handler or not self.git_handler.is_valid_repo(): QMessageBox.warning(self, "操作无效", "请先选择一个有效的 Git 仓库。"); return
        branch_name, ok = QInputDialog.getText(self, "创建新分支", "输入新分支的名称:", QLineEdit.EchoMode.Normal)
        if ok and branch_name:
            clean_name = branch_name.strip();
            # 对分支名称进行基本验证
            if not clean_name or re.search(r'[\s\~\^\:\?\*\[\\@\{]', clean_name):
                 QMessageBox.warning(self, "创建失败", "分支名称无效。\n\n分支名称不能包含空格或特殊字符如 ~^:?*[\\@{。")
                 return
            logging.info(f"请求创建新分支: {clean_name}");
            # 使用 run_command_list_sequentially
            self._run_command_list_sequentially([f"git branch {shlex.quote(clean_name)}"])
        elif ok:
            QMessageBox.warning(self, "创建失败", "分支名称不能为空。")


    @pyqtSlot(QPoint)
    def _show_branch_context_menu(self, pos):
        """显示分支列表的右键上下文菜单"""
        if not self.git_handler or not self.git_handler.is_valid_repo() or not self.branch_list_widget: return
        item = self.branch_list_widget.itemAt(pos);
        if not item: return
        menu = QMenu(); branch_name = item.text().strip(); is_remote = branch_name.startswith("remotes/"); is_current = item.font().bold(); added_action = False

        # 本地分支操作
        if not is_current and not is_remote:
            checkout_action = QAction(f"切换到 '{branch_name}'", self)
            checkout_action.triggered.connect(lambda checked=False, b=branch_name: self._run_command_list_sequentially([f"git checkout {shlex.quote(b)}"]))
            menu.addAction(checkout_action); added_action = True

            delete_action = QAction(f"删除本地分支 '{branch_name}'...", self)
            delete_action.triggered.connect(lambda checked=False, b=branch_name: self._delete_branch_dialog(b))
            menu.addAction(delete_action); added_action = True

        # 远程分支操作
        if is_remote:
             remote_parts = branch_name.split('/', 2);
             if len(remote_parts) == 3:
                 remote_name = remote_parts[1];
                 remote_branch_name = remote_parts[2];
                 # 基于远程分支检出为新的本地分支选项
                 checkout_remote_action = QAction(f"基于 '{branch_name}' 创建并切换到本地分支...", self)
                 checkout_remote_action.triggered.connect(lambda checked=False, rbn=remote_branch_name: self._create_and_checkout_branch_from_dialog(rbn, branch_name)) # 传递建议的名称和远程引用
                 menu.addAction(checkout_remote_action); added_action = True

                 # 删除远程分支选项
                 delete_remote_action = QAction(f"删除远程分支 '{remote_name}/{remote_branch_name}'...", self)
                 delete_remote_action.triggered.connect(lambda checked=False, rn=remote_name, rbn=remote_branch_name: self._delete_remote_branch_dialog(rn, rbn))
                 menu.addAction(delete_remote_action); added_action = True

        if added_action: menu.exec(self.branch_list_widget.mapToGlobal(pos))
        else: logging.debug(f"分支项目没有适用的上下文操作: {branch_name}")

    def _delete_branch_dialog(self, branch_name: str): # 直接执行
        if not branch_name or branch_name.startswith("remotes/"): logging.error(f"删除的本地分支名称无效: {branch_name}"); return
        reply = QMessageBox.warning(self, "确认删除本地分支", f"确定要删除本地分支 '{branch_name}' 吗？\n\n此操作通常不可撤销！", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel, QMessageBox.StandardButton.Cancel)
        if reply == QMessageBox.StandardButton.Yes:
             logging.info(f"请求删除本地分支: {branch_name} (使用 -d)")
             # 使用 run_command_list_sequentially
             self._run_command_list_sequentially([f"git branch -d {shlex.quote(branch_name)}"])

    def _delete_remote_branch_dialog(self, remote_name: str, branch_name: str): # 直接执行
        if not remote_name or not branch_name: logging.error(f"删除的远程/分支名称无效: {remote_name}/{branch_name}"); return
        reply = QMessageBox.warning(self, "确认删除远程分支", f"确定要从远程仓库 '{remote_name}' 删除分支 '{branch_name}' 吗？\n\n将执行: git push {remote_name} --delete {branch_name}\n\n此操作通常不可撤销！", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel, QMessageBox.StandardButton.Cancel)
        if reply == QMessageBox.StandardButton.Yes:
            logging.info(f"请求删除远程分支: {remote_name}/{branch_name}")
            # 使用 run_command_list_sequentially
            self._run_command_list_sequentially([f"git push {shlex.quote(remote_name)} --delete {shlex.quote(branch_name)}"])

    def _create_and_checkout_branch_from_dialog(self, suggest_name: str, start_point: str): # 直接执行
         if not self.git_handler or not self.git_handler.is_valid_repo(): QMessageBox.warning(self, "操作无效", "请先选择一个有效的 Git 仓库。"); return
         branch_name, ok = QInputDialog.getText(self, "创建并切换本地分支", f"输入新本地分支的名称 (基于 '{start_point}'):", QLineEdit.EchoMode.Normal, suggest_name)
         if ok and branch_name:
            clean_name = branch_name.strip();
            if not clean_name or re.search(r'[\s\~\^\:\?\*\[\\@\{]', clean_name):
                 QMessageBox.warning(self, "操作失败", "分支名称无效。\n\n分支名称不能包含空格或特殊字符如 ~^:?*[\\@{。")
                 return
            logging.info(f"请求创建并切换到分支: {clean_name} (基于 {start_point})");
            # 使用 run_command_list_sequentially 执行组合命令
            self._run_command_list_sequentially([f"git checkout -b {shlex.quote(clean_name)} {shlex.quote(start_point)}"])
         elif ok:
            QMessageBox.warning(self, "操作取消", "分支名称不能为空。")


    # --- 日志视图操作 ---
    @pyqtSlot()
    def _log_selection_changed(self):
        """当日志表格中的选择发生变化时，加载并显示 Commit 详情"""
        if not self.log_table_widget or not self.commit_details_textedit or not self.git_handler: return
        selected_items = self.log_table_widget.selectedItems();
        self.commit_details_textedit.clear() # 始终在选择变化时清空

        if not selected_items:
             self.commit_details_textedit.setPlaceholderText("选中上方提交记录以查看详情...");
             return

        # 获取选中行的索引。可能选中多行，但只显示第一行的详情。
        selected_row = self.log_table_widget.currentRow();
        if selected_row < 0: # 此检查可能因 selectedItems 而冗余，但更安全
             self.commit_details_textedit.setPlaceholderText("请选择一个提交记录。"); return

        hash_item = self.log_table_widget.item(selected_row, 0); # Commit 哈希在第一列
        if hash_item:
            # 优先使用 UserRole 中存储的数据，必要时回退到文本
            commit_hash = hash_item.data(Qt.ItemDataRole.UserRole)
            if not commit_hash:
                commit_hash = hash_item.text().strip()
                logging.warning(f"提交哈希项行 {selected_row} 缺少 UserRole，使用文本: {commit_hash}")

            if commit_hash:
                logging.debug(f"日志选择变化，正在请求提交详情: {commit_hash}")
                self.commit_details_textedit.setPlaceholderText(f"正在加载 Commit '{commit_hash[:7]}...' 的详情...");
                QApplication.processEvents() # 立即更新 UI
                # 使用 git show 获取提交详情和差异
                self.git_handler.execute_command_async(["git", "show", shlex.quote(commit_hash)], self._on_commit_details_received)
            else:
                self.commit_details_textedit.setPlaceholderText("无法获取选中提交的 Hash.");
                logging.error(f"无法从表格项获取有效 Hash (行: {selected_row})。")
        else:
            self.commit_details_textedit.setPlaceholderText("无法确定选中的提交项.");
            logging.error(f"无法在日志表格中找到行 {selected_row} 的第 0 列项。")


    @pyqtSlot(int, str, str)
    def _on_commit_details_received(self, return_code, stdout, stderr):
        """处理异步 git show (commit details) 的结果"""
        if not self.commit_details_textedit: return
        self.commit_details_textedit.setPlaceholderText(""); # 清空加载占位符

        if return_code == 0:
            if stdout.strip():
                # 在提交详情视图中显示详情
                self.commit_details_textedit.setText(stdout)
            else:
                 self.commit_details_textedit.setText("未获取到提交详情。")
        else:
            error_message = f"❌ 获取提交详情失败:\n{stderr}"
            self.commit_details_textedit.setText(error_message)
            logging.error(f"获取 Commit 详情失败: 返回码={return_code}, 错误: {stderr}")

        # 注意: Git show 的输出包含差异。我们可以在这里解析它，并可能更新差异标签页，
        # 但当前的设计仅将差异标签页链接到状态更改。
        # 为了简单起见，我们将提交详情和差异分开显示，基于用户的交互 (选择日志 vs 选择状态)。


    # --- 直接操作槽 ---
    # 这些方法现在构建命令并调用序列执行器
    def _execute_command_if_valid_repo(self, command_list: list[str], refresh=True):
        """检查仓库是否有效，如果有效则执行命令列表 (直接执行)"""
        # 此辅助方法现在只包装 _run_command_list_sequentially
        if not self.git_handler or not self.git_handler.is_valid_repo():
             QMessageBox.warning(self, "操作无效", "请先选择一个有效的 Git 仓库。");
             return
        # 将 command_list 转换为适合执行器的字符串列表
        command_strings = [' '.join(shlex.quote(part) for part in cmd) if isinstance(cmd, list) else cmd for cmd in command_list]
        self._run_command_list_sequentially(command_strings, refresh_on_success=refresh)


    def _run_switch_branch(self): # 直接执行 (对话框)
        if not self.git_handler or not self.git_handler.is_valid_repo(): QMessageBox.warning(self, "操作无效", "仓库无效。"); return
        branch_name, ok = QInputDialog.getText(self,"切换分支","输入要切换到的本地分支名称:",QLineEdit.EchoMode.Normal)
        if ok and branch_name:
            clean_name = branch_name.strip()
            if not clean_name:
                 QMessageBox.warning(self, "操作取消", "名称不能为空。")
                 return
            self._run_command_list_sequentially([f"git checkout {shlex.quote(clean_name)}"])
        elif ok and not branch_name: QMessageBox.warning(self, "操作取消", "名称不能为空。")


    def _run_list_remotes(self):
        # 这个操作很简单，不需要复杂的序列，但为了保持一致性，使用执行器
        self._execute_command_if_valid_repo(["git", "remote", "-v"], refresh=False) # 直接执行


    # --- 设置对话框槽 ---
    def _open_settings_dialog(self):
        """打开全局 Git 配置对话框"""
        dialog = SettingsDialog(self)
        # 获取当前的全局配置以预填充对话框
        if self.git_handler:
            try:
                 # 可以使用临时同步调用或专门的异步调用
                 # 为了简单起见，这里假设快速同步调用对于配置是可以接受的
                 # 更好的方法可能是像处理日志/状态刷新那样处理异步调用
                 name_result = self.git_handler.execute_command_sync(["git", "config", "--global", "user.name"])
                 email_result = self.git_handler.execute_command_sync(["git", "config", "--global", "user.email"])
                 current_name = name_result.stdout.strip() if name_result.returncode == 0 else ""
                 current_email = email_result.stdout.strip() if email_result.returncode == 0 else ""
                 dialog.set_data({"user.name": current_name, "user.email": current_email})
            except Exception as e:
                 logging.warning(f"获取全局配置失败: {e}")
                 # 对话框将以空字段打开

        if dialog.exec():
            config_data = dialog.get_data()
            commands_to_run = []
            name_val = config_data.get("user.name");
            email_val = config_data.get("user.email")

            # 仅当值与当前值不同或不为空时才添加配置命令
            # 需要重新获取当前值或依赖对话框的初始值 (不太健壮)
            # 让我们简化：如果对话框返回了值，则设置它 (允许清除配置)
            if name_val is not None: commands_to_run.append(f"git config --global user.name {shlex.quote(name_val.strip())}")
            if email_val is not None: commands_to_run.append(f"git config --global user.email {shlex.quote(email_val.strip())}")

            if commands_to_run:
                 confirmation_msg = "将执行以下全局 Git 配置命令:\n\n" + "\n".join(commands_to_run) + "\n\n确定吗？"
                 reply = QMessageBox.question(self, "应用全局配置", confirmation_msg, QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel, QMessageBox.StandardButton.Yes)
                 if reply == QMessageBox.StandardButton.Yes:
                     logging.info(f"正在执行全局配置命令: {commands_to_run}")
                     if self.git_handler:
                         # 使用序列执行器执行
                         self._run_command_list_sequentially(commands_to_run, refresh_on_success=False)
                     else:
                         logging.error("GitHandler 不可用，无法进行设置。")
                         QMessageBox.critical(self, "错误", "无法执行配置命令。")
                 else:
                     QMessageBox.information(self, "操作取消", "未应用全局配置更改。")
            else:
                 QMessageBox.information(self, "无更改", "未检测到有效的用户名或邮箱信息变更。") # 调整消息


    # --- 其他辅助方法 ---
    def _show_about_dialog(self):
        """显示关于对话框"""
        try: version = self.windowTitle().split('v')[-1].strip()
        except: version = "N/A"
        QMessageBox.about( self, "关于 简易 Git GUI", f"**简易 Git GUI**\n\n版本: {version}\n\n这是一个简单的 Git GUI 工具，用于学习和执行 Git 命令。\n\n开发日志:\nv1.0 - 初始版本 (仓库选择, 状态, Diff, Log, 命令输入)\nv1.1 - 增加暂存/撤销暂存单个文件\nv1.2 - 增加创建/切换/删除分支\nv1.3 - 提交功能\nv1.4 - 增加 Pull/Push/Fetch 按钮\nv1.5 - 增加 Git 全局配置对话框\nv1.6 - 异步执行命令，优化UI响应\nv1.7 - 增加命令序列构建器和快捷键功能\n\n本项目是学习 Qt6 和 Git 命令交互的实践项目。\n\n作者: 你的名字 (可选)\nGitHub: (你的项目链接，可选)")


    def closeEvent(self, event):
        """处理窗口关闭事件"""
        logging.info("应用程序关闭请求。")
        try:
            active_count = len(self.git_handler.active_operations) if hasattr(self.git_handler, 'active_operations') and self.git_handler.active_operations is not None else 0
            if active_count > 0:
                 # 如果有待处理的操作，您可能希望在此提示用户
                 logging.warning(f"窗口关闭时仍有 {active_count} 个 Git 操作可能在后台运行。")
        except Exception as e: logging.exception("关闭窗口时检查 Git 操作出错。")
        logging.info("应用程序正在关闭。")
        # 后台进程可能仍然会完成，但应用程序会关闭。
        event.accept()

# 示例主执行块
if __name__ == '__main__':
    # 根据需要设置日志级别，例如开发时设置为 DEBUG
    logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - [%(levelname)s] - %(filename)s:%(lineno)d - %(message)s')
    logging.info("应用程序启动...")
    app = QApplication(sys.argv)

    # 为整个应用程序设置一致的字体 (可选)
    # app.setFont(QFont("Segoe UI", 9)) # Windows 示例
    # app.setFont(QFont("Sans Serif", 9)) # 通用字体示例

    mainWin = MainWindow()
    mainWin.show()
    sys.exit(app.exec())