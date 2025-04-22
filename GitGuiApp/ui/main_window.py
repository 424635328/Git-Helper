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
from PyQt6.QtWebEn

from PyQt6.QtGui import QAction, QKeySequence, QColor, QTextCursor, QIcon, QFont, QStandardItemModel, QDesktopServices, QTextCharFormat
from PyQt6.QtCore import Qt, pyqtSlot, QSize, QTimer, QModelIndex, QUrl, QPoint, QItemSelection
from typing import Union, Optional
try:
    from .dialogs import ShortcutDialog, SettingsDialog
except ImportError:
    from dialogs import ShortcutDialog, SettingsDialog
from .shortcut_manager import ShortcutManager
from .status_tree_model import StatusTreeModel, STATUS_STAGED, STATUS_UNSTAGED, STATUS_UNTRACKED, STATUS_UNMERGED
from core.git_handler import GitHandler
from core.db_handler import DatabaseHandler

LOG_COL_COMMIT = 0
LOG_COL_AUTHOR = 1
LOG_COL_DATE = 2
LOG_COL_MESSAGE = 3

STATUS_COL_STATUS = 0
STATUS_COL_PATH = 1

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Git GUI v1.13")
        self.setGeometry(100, 100, 1200, 900)

        self.git_handler = GitHandler()
        self.db_handler = DatabaseHandler()
        self.shortcut_manager = ShortcutManager(self,self.db_handler, self.git_handler)

        self._repo_dependent_widgets = []

        self.output_display: Optional[QTextEdit] = None
        self.command_input: Optional[QLineEdit] = None
        self.sequence_display: Optional[QTextEdit] = None
        self.shortcut_list_widget: Optional[QListWidget] = None
        self.repo_label: Optional[QLabel] = None
        self.status_bar: Optional[QStatusBar] = None
        self.branch_list_widget: Optional[QListWidget] = None
        self.status_tree_view: Optional[QTreeView] = None
        self.status_tree_model: Optional[StatusTreeModel] = None
        self.log_table_widget: Optional[QTableWidget] = None
        self.diff_text_edit: Optional[QTextEdit] = None
        self.main_tab_widget: Optional[QTabWidget] = None
        self._output_tab_index = -1
        self.commit_details_textedit: Optional[QTextEdit] = None

        self.current_branch_name_display: Optional[str] = None
        self._remote_info: Optional[str] = None

        self._init_ui()
        self.shortcut_manager.load_and_register_shortcuts()
        self._update_repo_status()

        logging.info("主窗口初始化完成。")

    def _check_repo_and_warn(self, message="请先选择一个有效的 Git 仓库。", allow_init=False):
        is_valid = self.git_handler and self.git_handler.is_valid_repo()
        if not is_valid:
            if not allow_init or not (self.sequence_display and self.sequence_display.toPlainText().strip().startswith("git init")):
                self._show_warning("操作无效", message)
                return False
        return True

    def _show_warning(self, title: str, message: str):
        QMessageBox.warning(self, title, message)

    def _show_information(self, title: str, message: str):
        QMessageBox.information(self, title, message)

    def _append_output(self, text: str, color: QColor = None):
        if not self.output_display: return
        cursor = self.output_display.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        self.output_display.setTextCursor(cursor)

        original_format = cursor.charFormat()
        fmt = QTextCharFormat(original_format)
        if color:
             fmt.setForeground(color)

        self.output_display.setCurrentCharFormat(fmt)
        clean_text = text.rstrip('\n')
        self.output_display.insertPlainText(clean_text + "\n")

        self.output_display.setCurrentCharFormat(original_format)
        self.output_display.ensureCursorVisible()

    def _run_command_list_sequentially(self, command_strings: list[str], refresh_on_success=True):
        if not self.git_handler:
             logging.error("Git handler is not initialized.")
             self._append_output("❌ 内部错误: Git 处理程序不可用。", QColor("red"))
             self._set_ui_busy(False)
             return

        logging.debug(f"准备执行命令列表: {command_strings}, 成功后刷新: {refresh_on_success}")

        if self.main_tab_widget and self._output_tab_index != -1:
             self.main_tab_widget.setCurrentIndex(self._output_tab_index)
             if self.output_display:
                  self._append_output("\n--- 开始执行新的命令序列 ---", QColor("darkCyan"))
                  self.output_display.ensureCursorVisible()
             QApplication.processEvents()

        self._set_ui_busy(True)

        def execute_next(index):
            if index >= len(command_strings):
                self._append_output("\n✅ --- 所有命令执行完毕 ---", QColor("green"))
                self._set_ui_busy(False)
                if refresh_on_success:
                     self._refresh_all_views()
                return

            cmd_str = command_strings[index].strip()
            if not cmd_str:
                logging.debug(f"跳过空命令 #{index + 1}.");
                QTimer.singleShot(10, lambda idx=index + 1: execute_next(idx));
                return

            try:
                command_parts = shlex.split(cmd_str)
                logging.debug(f"解析命令 #{index + 1}: {command_parts}")
            except ValueError as e:
                err_msg = f"❌ 解析错误 '{cmd_str}': {e}"
                self._append_output(err_msg, QColor("red"))
                self._append_output("--- 执行中止 ---", QColor("red"))
                logging.error(err_msg)
                self._set_ui_busy(False)
                return

            if not command_parts:
                 logging.debug(f"命令 #{index + 1} 解析结果为空，跳过。")
                 QTimer.singleShot(10, lambda idx=index + 1: execute_next(idx));
                 return

            display_cmd = ' '.join(shlex.quote(part) for part in command_parts)
            self._append_output(f"\n$ {display_cmd}", QColor("darkGray"))
            if self.status_bar: self.status_bar.showMessage(f"正在执行: {display_cmd[:50]}...", 0)

            @pyqtSlot(int, str, str)
            def on_command_finished(return_code, stdout, stderr):
                QTimer.singleShot(10, lambda rc=return_code, so=stdout, se=stderr: process_finish(rc, so, se))

            def process_finish(return_code, stdout, stderr):
                if stdout: self._append_output(f"stdout:\n{stdout.strip()}")
                if stderr: self._append_output(f"stderr:\n{stderr.strip()}")

                if return_code == 0:
                    self._append_output(f"✅ 成功: '{display_cmd}'", QColor("Green"))
                    QTimer.singleShot(10, lambda idx=index + 1: execute_next(idx))
                else:
                    err_msg = f"❌ 失败 (RC: {return_code}) '{display_cmd}'，执行中止。"
                    logging.error(f"命令执行失败! 命令: '{display_cmd}', 返回码: {return_code}, 标准错误: {stderr.strip()}")
                    self._append_output(err_msg, QColor("red"))
                    self._set_ui_busy(False)

            @pyqtSlot(str)
            def on_progress(message):
                if message and not (message.startswith("Receiving objects:") or message.startswith("Resolving deltas:") or message.startswith("remote:")):
                    if self.status_bar: self.status_bar.showMessage(message, 3000)

            self.git_handler.execute_command_async(command_parts, on_command_finished, on_progress)

        execute_next(0)

    def _add_repo_dependent_widget(self, widget):
         if widget:
              self._repo_dependent_widgets.append(widget)
              self._update_ui_enable_state(self.git_handler.is_valid_repo())

    def _init_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)

        self._create_repo_area(main_layout)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        main_layout.addWidget(splitter, 1)

        self._create_left_panel(splitter)
        self._create_right_panel_and_tabs(splitter)

        splitter.setSizes([int(self.width() * 0.35), int(self.width() * 0.65)])

        self._create_status_bar()
        self._create_menu()
        self._create_toolbar()

    def _create_repo_area(self, main_layout: QVBoxLayout):
        repo_layout = QHBoxLayout()
        self.repo_label = QLabel("当前仓库: (未选择)")
        self.repo_label.setToolTip("当前操作的 Git 仓库路径")
        repo_layout.addWidget(self.repo_label, 1)

        select_repo_button = QPushButton("选择仓库")
        select_repo_button.setToolTip("选择仓库目录")
        select_repo_button.clicked.connect(self._select_repository)
        repo_layout.addWidget(select_repo_button)

        main_layout.addLayout(repo_layout)

    def _create_left_panel(self, splitter: QSplitter):
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(5, 0, 5, 5)
        left_layout.setSpacing(6)
        splitter.addWidget(left_panel)

        left_layout.addWidget(QLabel("常用 Git 命令:"))
        command_buttons_layout_1 = QHBoxLayout()
        self._add_command_button(command_buttons_layout_1, "Status", "添加 'git status' 到序列", lambda: self._add_command_to_sequence("git status"))
        self._add_command_button(command_buttons_layout_1, "Add .", "添加 'git add .' 到序列", lambda: self._add_command_to_sequence("git add ."))
        self._add_command_button(command_buttons_layout_1, "Add...", "添加 'git add <文件>' 到序列 (需要输入)", self._add_files_to_sequence)
        left_layout.addLayout(command_buttons_layout_1)

        command_buttons_layout_2 = QHBoxLayout()
        self._add_command_button(command_buttons_layout_2, "Commit...", "添加 'git commit -m <msg>' 到序列 (需要输入)", self._add_commit_to_sequence)
        self._add_command_button(command_buttons_layout_2, "Commit -a...", "添加 'git commit -am <msg>' 到序列 (需要输入)", self._add_commit_am_to_sequence)
        self._add_command_button(command_buttons_layout_2, "Log", "刷新提交历史视图 (Tab)", self._refresh_log_view)
        left_layout.addLayout(command_buttons_layout_2)

        remote_buttons_layout = QHBoxLayout()
        self._add_command_button(remote_buttons_layout, "Pull", "添加 'git pull' 到序列", lambda: self._add_command_to_sequence("git pull"))
        self._add_command_button(remote_buttons_layout, "Push", "添加 'git push' 到序列", lambda: self._add_command_to_sequence("git push"))
        self._add_command_button(remote_buttons_layout, "Fetch", "添加 'git fetch' 到序列", lambda: self._add_command_to_sequence("git fetch"))
        left_layout.addLayout(remote_buttons_layout)

        left_layout.addWidget(QLabel("命令序列构建块:"))
        command_builder_layout_1 = QHBoxLayout()
        self._add_command_button(command_builder_layout_1, "Init", "添加 'git init' 到序列 (用于初始化新仓库)", lambda: self._add_command_to_sequence("git init"), is_repo_dependent=False)
        self._add_command_button(command_builder_layout_1, "Branch...", "添加 'git branch <名称>' 到序列 (需要输入)", self._add_branch_to_sequence)
        self._add_command_button(command_builder_layout_1, "Merge...", "添加 'git merge <分支/提交>' 到序列 (需要输入)", self._add_merge_to_sequence)
        self._add_command_button(command_builder_layout_1, "Checkout...", "添加 'git checkout <目标>' 到序列 (需要输入)", self._add_checkout_to_sequence)
        left_layout.addLayout(command_builder_layout_1)

        command_builder_layout_2 = QHBoxLayout()
        self._add_command_button(command_builder_layout_2, "Reset...", "添加 'git reset <模式> <目标>' 到序列 (需要输入)", self._add_reset_to_sequence)
        self._add_command_button(command_builder_layout_2, "Revert...", "添加 'git revert <提交>' 到序列 (需要输入)", self._add_revert_to_sequence)
        self._add_command_button(command_builder_layout_2, "Rebase...", "添加 'git rebase <目标>' 到序列 (需要输入)", self._add_rebase_to_sequence)
        self._add_command_button(command_builder_layout_2, "Stash Save...", "添加 'git stash save <消息>' 到序列 (可选消息)", self._add_stash_save_to_sequence)
        left_layout.addLayout(command_builder_layout_2)

        command_builder_layout_3 = QHBoxLayout()
        self._add_command_button(command_builder_layout_3, "Stash Pop", "添加 'git stash pop' 到序列", lambda: self._add_command_to_sequence("git stash pop"))
        self._add_command_button(command_builder_layout_3, "Tag...", "添加 'git tag <名称> [-m <消息>]' 到序列 (需要输入)", self._add_tag_to_sequence)
        self._add_command_button(command_builder_layout_3, "Remote...", "添加 'git remote <子命令及参数>' 到序列 (需要输入)", self._add_remote_to_sequence)
        self._add_command_button(command_builder_layout_3, "Restore...", "添加 'git restore <文件> [--staged]' 到序列 (需要输入)", self._add_restore_to_sequence)
        self._add_command_button(command_builder_layout_3, "Main", "添加 'git checkout main' 到序列", lambda: self._add_command_to_sequence("git checkout main"))
        self._add_command_button(command_builder_layout_3, "Master", "添加 'git checkout master' 到序列", lambda: self._add_command_to_sequence("git checkout master"))
        left_layout.addLayout(command_builder_layout_3)

        left_layout.addWidget(QLabel("常用参数/选项 (点击添加到当前命令末尾):"))
        parameter_buttons_layout = QHBoxLayout()
        self._add_command_button(parameter_buttons_layout, "-a", "添加 '-a' 参数到序列最后一行", lambda: self._add_parameter_to_sequence("-a"))
        self._add_command_button(parameter_buttons_layout, "-v", "添加 '-v' 参数到序列最后一行", lambda: self._add_parameter_to_sequence("-v"))
        self._add_command_button(parameter_buttons_layout, "--hard", "添加 '--hard' 参数到序列最后一行 (危险!)", lambda: self._add_parameter_to_sequence("--hard"))
        self._add_command_button(parameter_buttons_layout, "-f", "添加 '-f' 参数到序列最后一行 (强制!)", lambda: self._add_parameter_to_sequence("-f"))
        self._add_command_button(parameter_buttons_layout, "-u", "添加 '-u' 参数到序列最后一行", lambda: self._add_parameter_to_sequence("-u"))
        self._add_command_button(parameter_buttons_layout, "-p", "添加 '-p' 参数到序列最后一行", lambda: self._add_parameter_to_sequence("-p"))
        self._add_command_button(parameter_buttons_layout, "--soft", "添加 '--soft' 参数到序列最后一行", lambda: self._add_parameter_to_sequence("--soft"))
        left_layout.addLayout(parameter_buttons_layout)


        left_layout.addWidget(QLabel("命令序列构建器 (可手动编辑):"))
        self.sequence_display = QTextEdit()
        self.sequence_display.setReadOnly(False)
        self.sequence_display.setPlaceholderText("点击上方按钮构建命令序列，或从快捷键加载，或手动输入...")
        self.sequence_display.setFixedHeight(80)
        left_layout.addWidget(self.sequence_display)
        self._add_repo_dependent_widget(self.sequence_display)


        sequence_actions_layout = QHBoxLayout()
        execute_button = QPushButton("执行序列")
        execute_button.setToolTip("执行上方构建的命令序列")
        execute_button.setStyleSheet("background-color: darkred; color: black;")
        execute_button.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        execute_button.clicked.connect(self._execute_sequence)
        self._add_repo_dependent_widget(execute_button)

        clear_button = QPushButton("清空序列")
        clear_button.setToolTip("清空上方构建的命令序列")
        clear_button.clicked.connect(self._clear_sequence)
        self._add_repo_dependent_widget(clear_button)

        save_shortcut_button = QPushButton("保存快捷键")
        save_shortcut_button.setToolTip("将上方命令序列保存为新的快捷键")
        save_shortcut_button.clicked.connect(self.shortcut_manager.save_shortcut_dialog)
        self._add_repo_dependent_widget(save_shortcut_button)

        sequence_actions_layout.addWidget(execute_button)
        sequence_actions_layout.addWidget(clear_button)
        sequence_actions_layout.addWidget(save_shortcut_button)
        left_layout.addLayout(sequence_actions_layout)

        branch_label_layout = QHBoxLayout()
        branch_label_layout.addWidget(QLabel("分支列表:"))
        branch_label_layout.addStretch()
        create_branch_button = QPushButton("+ 新分支")
        create_branch_button.setToolTip("创建新的本地分支")
        create_branch_button.clicked.connect(self._create_branch_dialog)
        self._add_repo_dependent_widget(create_branch_button)
        branch_label_layout.addWidget(create_branch_button)
        left_layout.addLayout(branch_label_layout)

        self.branch_list_widget = QListWidget()
        self.branch_list_widget.setToolTip("双击切换分支, 右键操作")
        self.branch_list_widget.itemDoubleClicked.connect(self._branch_double_clicked)
        self.branch_list_widget.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.branch_list_widget.customContextMenuRequested.connect(self._show_branch_context_menu)
        left_layout.addWidget(self.branch_list_widget, 1)
        self._add_repo_dependent_widget(self.branch_list_widget)

        left_layout.addWidget(QLabel("快捷键组合:"))
        self.shortcut_list_widget = QListWidget()
        self.shortcut_list_widget.setToolTip("双击执行，右键删除")
        self.shortcut_list_widget.itemDoubleClicked.connect(self._load_shortcut_into_builder)
        self.shortcut_list_widget.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.shortcut_list_widget.customContextMenuRequested.connect(self.shortcut_manager.show_shortcut_context_menu)
        left_layout.addWidget(self.shortcut_list_widget, 1)
        self._add_repo_dependent_widget(self.shortcut_list_widget)

        left_layout.addStretch()


    def _create_right_panel_and_tabs(self, splitter: QSplitter):
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(0)
        splitter.addWidget(right_panel)

        self.main_tab_widget = QTabWidget()
        right_layout.addWidget(self.main_tab_widget, 1)

        self._create_status_tab()
        self._create_log_tab()
        self._create_diff_tab()
        self._create_output_tab()

        self._create_command_input_area(right_layout)

    def _create_status_tab(self):
        status_tab_widget = QWidget()
        status_tab_layout = QVBoxLayout(status_tab_widget)
        status_tab_layout.setContentsMargins(5, 5, 5, 5)
        status_tab_layout.setSpacing(4)
        self.main_tab_widget.addTab(status_tab_layout.parentWidget(), "状态 / 文件")

        status_action_layout = QHBoxLayout()
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
        refresh_status_button.clicked.connect(self._refresh_status_view)
        self._add_repo_dependent_widget(refresh_status_button)

        status_action_layout.addWidget(stage_all_button)
        status_action_layout.addWidget(unstage_all_button)
        status_action_layout.addStretch()
        status_action_layout.addWidget(refresh_status_button)
        status_tab_layout.addLayout(status_action_layout)

        self.status_tree_view = QTreeView()
        self.status_tree_model = StatusTreeModel(self)
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
        self._add_repo_dependent_widget(self.status_tree_view)


    def _create_log_tab(self):
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
        self._add_repo_dependent_widget(self.log_table_widget)

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
        self._add_repo_dependent_widget(self.commit_details_textedit)

    def _create_diff_tab(self):
        diff_tab_widget = QWidget()
        diff_tab_layout = QVBoxLayout(diff_tab_widget)
        diff_tab_layout.setContentsMargins(5, 5, 5, 5)
        self.main_tab_widget.addTab(diff_tab_layout.parentWidget(), "差异 (Diff)")

        self.diff_text_edit = QTextEdit()
        self.diff_text_edit.setReadOnly(True)
        self.diff_text_edit.setFontFamily("Courier New")
        self.diff_text_edit.setPlaceholderText("选中已更改的文件以查看差异...")
        diff_tab_layout.addWidget(self.diff_text_edit, 1)
        self._add_repo_dependent_widget(self.diff_text_edit)

    def _create_output_tab(self):
        output_tab_widget = QWidget()
        output_tab_layout = QVBoxLayout(output_tab_widget)
        output_tab_layout.setContentsMargins(5, 5, 5, 5)
        self._output_tab_index = self.main_tab_widget.addTab(output_tab_layout.parentWidget(), "原始输出")

        self.output_display = QTextEdit()
        self.output_display.setReadOnly(True)
        self.output_display.setFontFamily("Courier New")
        self.output_display.setPlaceholderText("Git 命令和命令行输出将显示在此处...")
        output_tab_layout.addWidget(self.output_display, 1)

    def _create_command_input_area(self, parent_layout: QVBoxLayout):
        command_input_container = QWidget()
        command_input_layout = QHBoxLayout(command_input_container)
        command_input_layout.setContentsMargins(5, 3, 5, 5)
        command_input_layout.setSpacing(4)

        command_input_label = QLabel("$")
        self.command_input = QLineEdit()
        self.command_input.setPlaceholderText("输入 Git 命令并按 Enter 直接执行")
        command_font = QFont("Courier New")
        self.command_input.setFont(command_font)
        self.command_input.returnPressed.connect(self._execute_command_from_input)
        self._add_repo_dependent_widget(self.command_input)

        command_input_layout.addWidget(command_input_label)
        command_input_layout.addWidget(self.command_input)
        parent_layout.addWidget(command_input_container)


    def _create_status_bar(self):
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("就绪")


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
        self._add_repo_dependent_widget(refresh_action)

        repo_menu.addSeparator()

        create_branch_action = QAction("创建分支(&N)...", self)
        create_branch_action.triggered.connect(self._create_branch_dialog)
        repo_menu.addAction(create_branch_action)
        self._add_repo_dependent_widget(create_branch_action)

        switch_branch_action = QAction("切换分支(&S)...", self)
        switch_branch_action.triggered.connect(self._run_switch_branch)
        repo_menu.addAction(switch_branch_action)
        self._add_repo_dependent_widget(switch_branch_action)

        repo_menu.addSeparator()

        list_remotes_action = QAction("列出远程仓库", self)
        list_remotes_action.triggered.connect(self._run_list_remotes)
        repo_menu.addAction(list_remotes_action)
        self._add_repo_dependent_widget(list_remotes_action)

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
        self._add_repo_dependent_widget(refresh_tb_action)
        toolbar.addSeparator()

        pull_action = QAction(pull_icon, "Pull", self)
        pull_action.setToolTip("添加 'git pull' 到序列")
        pull_action.triggered.connect(lambda: self._add_command_to_sequence("git pull"))
        toolbar.addAction(pull_action)
        self._add_repo_dependent_widget(pull_action)

        push_action = QAction(push_icon,"Push", self)
        push_action.setToolTip("添加 'git push' 到序列")
        push_action.triggered.connect(lambda: self._add_command_to_sequence("git push"))
        toolbar.addAction(push_action)
        self._add_repo_dependent_widget(push_action)
        toolbar.addSeparator()

        create_branch_tb_action = QAction(new_branch_icon, "新分支", self)
        create_branch_tb_action.setToolTip("创建新的本地分支 (直接执行)")
        create_branch_tb_action.triggered.connect(self._create_branch_dialog)
        toolbar.addAction(create_branch_tb_action)
        self._add_repo_dependent_widget(create_branch_tb_action)

        switch_branch_action_tb = QAction(switch_branch_icon, "切换分支...", self)
        switch_branch_action_tb.setToolTip("切换本地分支 (直接执行)")
        switch_branch_action_tb.triggered.connect(self._run_switch_branch)
        toolbar.addAction(switch_branch_action_tb)
        self._add_repo_dependent_widget(switch_branch_action_tb)

        list_remotes_action_tb = QAction(remotes_icon, "远程列表", self)
        list_remotes_action_tb.setToolTip("列出远程仓库 (直接执行)")
        list_remotes_action_tb.triggered.connect(self._run_list_remotes)
        toolbar.addAction(list_remotes_action_tb)
        self._add_repo_dependent_widget(list_remotes_action_tb)
        toolbar.addSeparator()

        clear_output_action = QAction(clear_icon, "清空原始输出", self)
        clear_output_action.setToolTip("清空'原始输出'标签页的内容")
        if self.output_display:
             clear_output_action.triggered.connect(self.output_display.clear)
        toolbar.addAction(clear_output_action)


    def _add_command_button(self, layout: QHBoxLayout, text: str, tooltip: str, slot, is_repo_dependent: bool = True):
        button = QPushButton(text)
        button.setToolTip(tooltip)
        button.clicked.connect(slot)
        layout.addWidget(button)
        if is_repo_dependent:
            self._add_repo_dependent_widget(button)
        else:
             button.setEnabled(True)
        return button

    def _update_repo_status(self):
        repo_path = self.git_handler.get_repo_path() if self.git_handler else None
        is_valid = self.git_handler.is_valid_repo() if self.git_handler else False

        display_path = repo_path if repo_path and len(repo_path) < 60 else (f"...{repo_path[-57:]}" if repo_path else "(未选择)")
        if self.repo_label:
            self.repo_label.setText(f"当前仓库: {display_path}")
            self.repo_label.setStyleSheet("" if is_valid else "color: red;")

        self._update_ui_enable_state(is_valid)

        if is_valid:
            if self.status_bar: self.status_bar.showMessage(f"正在加载仓库: {repo_path}", 0)
            QApplication.processEvents()
            self._refresh_all_views()
            self._refresh_remote_info()
        else:
            if self.status_bar: self.status_bar.showMessage("请选择一个有效的 Git 仓库目录", 0)
            if self.status_tree_model: self.status_tree_model.clear_status()
            if self.branch_list_widget: self.branch_list_widget.clear()
            if self.log_table_widget: self.log_table_widget.setRowCount(0)
            if self.diff_text_edit: self.diff_text_edit.clear()
            if self.commit_details_textedit: self.commit_details_textedit.clear()
            self._clear_sequence()
            self.current_branch_name_display = "(无效仓库)"
            self._remote_info = None
            self._update_status_bar_info()
            logging.info("Git 仓库无效，UI 已禁用。")


    def _update_ui_enable_state(self, enabled: bool):
        for widget in self._repo_dependent_widgets:
            if widget:
                 widget.setEnabled(enabled)

        init_button = None
        # Iterate through all QHBoxLayouts found
        for layout in self.findChildren(QHBoxLayout):
             if layout:
                  # Iterate through items in the layout
                  for item_index in range(layout.count()):
                       item = layout.itemAt(item_index)
                       # Check if the item contains a widget and it's a QPushButton
                       if item and item.widget() and isinstance(item.widget(), QPushButton) and item.widget().text() == "Init":
                            init_button = item.widget()
                            break # Found the Init button, can stop searching this layout
                  if init_button:
                       break # Found the Init button in some layout, can stop searching all layouts


        if init_button:
             init_button.setEnabled(True)

        for action in self.findChildren(QAction):
            action_text = action.text()
            if action_text in ["选择仓库(&O)...", "Git 全局配置(&G)...", "退出(&X)", "关于(&A)", "清空原始输出"]:
                action.setEnabled(True)

    def _refresh_remote_info(self):
        if not self.git_handler or not self.git_handler.is_valid_repo():
             self._remote_info = None
             self._update_status_bar_info()
             return
        logging.debug("正在请求远程信息 (git remote -v)...")
        self.git_handler.execute_command_async(["git", "remote", "-v"], self._on_remote_info_refreshed)

    @pyqtSlot(int, str, str)
    def _on_remote_info_refreshed(self, return_code: int, stdout: str, stderr: str):
        if return_code == 0:
            lines = stdout.strip().splitlines()
            logging.debug(f"接收到远程信息: {len(lines)} 行")
            remotes = {}

            for line in lines:
                line = line.strip()
                if not line: continue
                parts = line.split()
                if len(parts) == 3:
                    name, url, type = parts
                    if name not in remotes:
                        remotes[name] = {'fetch_url': None, 'push_url': None}
                    if type.strip('()') == 'fetch':
                        remotes[name]['fetch_url'] = url
                    elif type.strip('()') == 'push':
                        remotes[name]['push_url'] = url

            summary_parts = []
            for name, urls in remotes.items():
                url_text = "N/A"
                # Prioritize push URL for display if different, otherwise fetch URL
                if urls['push_url']:
                    url_text = urls['push_url']
                elif urls['fetch_url']:
                    url_text = urls['fetch_url']

                if url_text != "N/A":
                     # Attempt to parse potential GitHub/GitLab URL for concise display
                     match = re.search(r'(github\.com|gitlab\.com|bitbucket\.org)[:/](.+?)/(.+?)(\.git)?$', url_text)
                     if match:
                         domain = match.group(1)
                         owner = match.group(2)
                         repo = match.group(3)
                         display_url = f"{domain}/{owner}/{repo}"
                     else:
                         display_url = url_text # Fallback to full URL if parsing fails

                     summary_parts.append(f"{name}: {display_url}")
                else:
                    summary_parts.append(f"{name}: (无URL)")


            self._remote_info = " | Remotes: " + ", ".join(summary_parts) if summary_parts else " | Remotes: (none)"
            logging.debug(f"远程信息总结: {self._remote_info}")

        else:
            logging.error(f"获取远程信息失败: RC={return_code}, 错误: {stderr}")
            self._append_output(f"❌ 获取远程信息失败:\n{stderr}", QColor("red"))
            self._remote_info = " | Remotes: (获取失败)"

        self._update_status_bar_info()


    def _update_status_bar_info(self):
        if not self.status_bar: return

        is_valid = self.git_handler.is_valid_repo() if self.git_handler else False
        repo_path = self.git_handler.get_repo_path() if self.git_handler else None

        repo_path_short = repo_path or "(未选择)"
        if len(repo_path_short) > 40:
            repo_path_short = f"...{repo_path_short[-37:]}"

        branch_display = self.current_branch_name_display if self.current_branch_name_display else ("(未知分支)" if is_valid else "(无效仓库)")

        status_message_parts = [f"分支: {branch_display}", f"仓库: {repo_path_short}"]

        if is_valid and self._remote_info is not None:
             status_message_parts.append(self._remote_info.strip())

        status_message = " | ".join(status_message_parts)


        if self.status_bar.currentMessage().startswith("⏳ "):
             logging.debug("状态栏正在显示繁忙消息，跳过更新。")
        else:
            self.status_bar.showMessage(status_message, 0)
            logging.debug(f"状态栏更新: {status_message}")


    @pyqtSlot()
    def _refresh_all_views(self):
        if not self._check_repo_and_warn("无法刷新视图，仓库无效。"): return

        logging.info("正在刷新状态、分支和日志视图...")
        if self.status_bar: self.status_bar.showMessage("⏳ 正在刷新...", 0)
        QApplication.processEvents()

        self._refresh_status_view()
        self._refresh_branch_list()
        self._refresh_log_view()


    @pyqtSlot()
    def _refresh_status_view(self):
        if not self.git_handler or not self.git_handler.is_valid_repo():
             logging.warning("试图刷新状态，但 GitHandler 不可用或仓库无效。")
             return

        logging.debug("正在请求 status porcelain...")
        stage_all_btn = next((w for w in self._repo_dependent_widgets if isinstance(w, QPushButton) and w.text() == "全部暂存 (+)"), None)
        unstage_all_btn = next((w for w in self._repo_dependent_widgets if isinstance(w, QPushButton) and w.text() == "全部撤销暂存 (-)"), None)
        if stage_all_btn: stage_all_btn.setEnabled(False)
        if unstage_all_btn: unstage_all_btn.setEnabled(False)

        if self.diff_text_edit: self.diff_text_edit.clear(); self.diff_text_edit.setPlaceholderText("选中已更改的文件以查看差异...")
        if self.commit_details_textedit: self.commit_details_textedit.clear(); self.commit_details_textedit.setPlaceholderText("选中上方提交记录以查看详情...")


        self.git_handler.get_status_porcelain_async(self._on_status_refreshed)


    @pyqtSlot(int, str, str)
    def _on_status_refreshed(self, return_code: int, stdout: str, stderr: str):
        if not self.status_tree_model or not self.status_tree_view:
             logging.error("状态树模型或视图在状态刷新回调时未初始化。")
             self._update_status_bar_info()
             return

        stage_all_btn = next((w for w in self._repo_dependent_widgets if isinstance(w, QPushButton) and w.text() == "全部暂存 (+)"), None)
        unstage_all_btn = next((w for w in self._repo_dependent_widgets if isinstance(w, QPushButton) and w.text() == "全部撤销暂存 (-)"), None)

        if self.status_tree_view:
             self.status_tree_view.setUpdatesEnabled(False)

        try:
            if return_code == 0:
                logging.debug("接收到 status porcelain，正在填充模型...")
                self.status_tree_model.parse_and_populate(stdout)
                self.status_tree_view.expandAll()
                self.status_tree_view.resizeColumnToContents(STATUS_COL_STATUS)
                self.status_tree_view.setColumnWidth(STATUS_COL_STATUS, max(100, self.status_tree_view.columnWidth(STATUS_COL_STATUS)))

                has_unstaged_or_untracked = self.status_tree_model.unstage_root.rowCount() > 0 or self.status_tree_model.untracked_root.rowCount() > 0 or (hasattr(self.status_tree_model, 'unmerged_root') and self.status_tree_model.unmerged_root.rowCount() > 0)
                if stage_all_btn: stage_all_btn.setEnabled(has_unstaged_or_untracked)
                if unstage_all_btn: unstage_all_btn.setEnabled(self.status_tree_model.staged_root.rowCount() > 0)

            else:
                logging.error(f"获取状态失败: RC={return_code}, 错误: {stderr}")
                self._append_output(f"❌ 获取 Git 状态失败:\n{stderr}", QColor("red"))
                self.status_tree_model.clear_status()
                if stage_all_btn: stage_all_btn.setEnabled(False)
                if unstage_all_btn: unstage_all_btn.setEnabled(False)

        finally:
            if self.status_tree_view:
                 self.status_tree_view.setUpdatesEnabled(True)

        self._update_status_bar_info()


    @pyqtSlot()
    def _refresh_branch_list(self):
        if not self.git_handler or not self.git_handler.is_valid_repo():
             logging.warning("试图刷新分支列表，但 GitHandler 不可用或仓库无效。")
             return
        logging.debug("正在请求格式化分支列表...")
        if self.branch_list_widget: self.branch_list_widget.clear()
        self.git_handler.get_branches_formatted_async(self._on_branches_refreshed)


    @pyqtSlot(int, str, str)
    def _on_branches_refreshed(self, return_code: int, stdout: str, stderr: str):
        if not self.branch_list_widget or not self.git_handler:
             logging.error("分支列表组件或 GitHandler 在分支刷新回调时未初始化。")
             self.current_branch_name_display = "(内部错误)"
             self._update_status_bar_info()
             return

        self.branch_list_widget.clear()
        current_branch_name = None
        is_valid = self.git_handler.is_valid_repo()

        if return_code == 0 and is_valid:
            lines = stdout.strip().splitlines()
            logging.debug(f"接收到分支: {len(lines)} 行")
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

            if current_branch_name:
                 self.current_branch_name_display = current_branch_name
                 items = self.branch_list_widget.findItems(current_branch_name, Qt.MatchFlag.MatchExactly)
                 if items: self.branch_list_widget.setCurrentItem(items[0])
            else:
                 self.current_branch_name_display = "(未知分支)"

        elif is_valid:
            logging.error(f"获取分支失败: RC={return_code}, 错误: {stderr}")
            self._append_output(f"❌ 获取分支列表失败:\n{stderr}", QColor("red"))
            self.current_branch_name_display = "(未知分支)"
        elif not is_valid:
             logging.warning("仓库在分支刷新前变得无效，跳过处理分支结果。")
             self.current_branch_name_display = "(无效仓库)"

        self._update_status_bar_info()


    @pyqtSlot()
    def _refresh_log_view(self):
        if not self.git_handler or not self.git_handler.is_valid_repo():
             logging.warning("试图刷新日志，但 GitHandler 不可用或仓库无效。")
             return
        logging.debug("正在请求格式化日志...")
        if self.log_table_widget: self.log_table_widget.setRowCount(0)
        if self.commit_details_textedit: self.commit_details_textedit.clear(); self.commit_details_textedit.setPlaceholderText("选中上方提交记录以查看详情...")

        self.git_handler.get_log_formatted_async(count=200, finished_slot=self._on_log_refreshed)


    @pyqtSlot(int, str, str)
    def _on_log_refreshed(self, return_code: int, stdout: str, stderr: str):
        if not self.log_table_widget:
             logging.error("日志表格组件在日志刷新回调时未初始化。")
             self._update_status_bar_info()
             return

        if return_code == 0:
            lines = stdout.strip().splitlines()
            logging.debug(f"接收到日志 ({len(lines)} 条记录)。正在填充表格...")
            self.log_table_widget.setUpdatesEnabled(False)
            self.log_table_widget.setRowCount(0)
            monospace_font = QFont("Courier New")
            valid_rows = 0

            log_line_regex = re.compile(r'^([\s\\/|*.-]*?)?([a-fA-F0-9]+)\s+(.*?)\s+(.*?)\s+(.*)$')

            for line in lines:
                line = line.strip()
                if not line: continue

                match = log_line_regex.match(line)
                if match:
                    commit_hash = match.group(2)
                    author = match.group(3)
                    date = match.group(4)
                    message = match.group(5)

                    if not commit_hash:
                         logging.warning(f"Parsed empty commit hash for line (regex match but empty hash?): {repr(line)}")
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

                    self.log_table_widget.setItem(valid_rows, LOG_COL_COMMIT, hash_item)
                    self.log_table_widget.setItem(valid_rows, LOG_COL_AUTHOR, author_item)
                    self.log_table_widget.setItem(valid_rows, LOG_COL_DATE, date_item)
                    self.log_table_widget.setItem(valid_rows, LOG_COL_MESSAGE, message_item)

                    valid_rows += 1
                else:
                     if not re.match(r'^[\s\\/|*.-]+$', line):
                        logging.warning(f"无法解析日志行（与预期格式不匹配?）: {repr(line)}")


            self.log_table_widget.setUpdatesEnabled(True)
            logging.info(f"日志表格已填充 {valid_rows} 个有效条目。")
        else:
            logging.error(f"获取日志失败: RC={return_code}, 错误: {stderr}")
            self._append_output(f"❌ 获取提交历史失败:\n{stderr}", QColor("red"))

        self._update_status_bar_info()


    def _select_repository(self):
        start_path = self.git_handler.get_repo_path() if self.git_handler else None
        if not start_path or not os.path.isdir(start_path):
            start_path = os.getcwd()
            if not os.path.isdir(os.path.join(start_path, '.git')):
                 start_path = os.path.expanduser("~")
                 if os.path.isdir(os.path.join(os.path.expanduser("~"), 'git')):
                      start_path = os.path.join(os.path.expanduser("~"), 'git')

        dir_path = QFileDialog.getExistingDirectory(self, "选择 Git 仓库目录", start_path)
        if dir_path:
            if not self.git_handler:
                 logging.error("仓库选择期间 GitHandler 未初始化。")
                 self._show_warning("内部错误", "Git 处理程序未初始化。")
                 return
            try:
                if self.output_display: self.output_display.clear()
                if self.diff_text_edit: self.diff_text_edit.clear()
                if self.commit_details_textedit: self.commit_details_textedit.clear()
                self._clear_sequence()
                if self.status_tree_model: self.status_tree_model.clear_status()
                if self.branch_list_widget: self.branch_list_widget.clear()
                if self.log_table_widget: self.log_table_widget.setRowCount(0)
                self.current_branch_name_display = None
                self._remote_info = None

                self.git_handler.set_repo_path(dir_path)
                self._update_repo_status()
                logging.info(f"用户选择了新的仓库目录: {dir_path}")
            except ValueError as e:
                self._show_warning("选择仓库失败", str(e))
                logging.error(f"设置仓库路径失败: {e}")
                self.git_handler.set_repo_path(None)
                self._update_repo_status()
            except Exception as e:
                 logging.exception("选择仓库时发生意外错误。")
                 QMessageBox.critical(self, "意外错误", f"选择仓库时出错: {e}")
                 self.git_handler.set_repo_path(None)
                 self._update_repo_status()

    def _add_command_to_sequence(self, command_to_add: Union[str, list[str]]):
        if isinstance(command_to_add, list):
            command_str = ' '.join(shlex.quote(part) for part in command_to_add)
        elif isinstance(command_to_add, str):
            command_str = command_to_add.strip()
        else:
            logging.warning(f"无效的命令类型传递给 _add_command_to_sequence: {type(command_to_add)}")
            return

        if not command_str:
             logging.debug("尝试添加空命令到序列，忽略。")
             return

        if self.sequence_display:
             current_text = self.sequence_display.toPlainText().strip()
             new_text = f"{current_text}\n{command_str}" if current_text else command_str
             self.sequence_display.setText(new_text)
             self.sequence_display.ensureCursorVisible()
        logging.debug(f"命令添加到序列构建器: {command_str}")

    def _add_parameter_to_sequence(self, parameter_to_add: str):
        param_str = parameter_to_add.strip()
        if not param_str:
            logging.debug("Attempted to add empty parameter, ignoring.")
            return

        if self.sequence_display:
            current_text = self.sequence_display.toPlainText().strip()
            lines = current_text.splitlines()
            if not lines:
                self._show_warning("提示", "请先添加一个命令，再添加参数。")
                logging.warning(f"Attempted to add parameter '{param_str}' to empty sequence.")
                return

            last_line_index = -1
            for i in range(len(lines) - 1, -1, -1):
                if lines[i].strip():
                    last_line_index = i
                    break

            if last_line_index != -1:
                lines[last_line_index] = f"{lines[last_line_index].strip()} {param_str}"
                new_text = "\n".join(lines)
                self.sequence_display.setText(new_text)
                self.sequence_display.ensureCursorVisible()
                logging.debug(f"参数 '{param_str}' 添加到序列构建器最后一行。")
                if self.status_bar:
                     self.status_bar.showMessage(f"参数 '{param_str}' 已添加到最后一条命令。", 3000)

                if param_str == "--hard":
                    self._show_warning("警告: --hard 参数", "'--hard' 参数通常用于 'git reset'。它可能导致工作区和暂存区的更改丢失，不可撤销！")
                elif param_str == "-f" or param_str == "--force":
                    self._show_warning("警告: -f 参数", "'-f' 参数用于强制执行操作。它可能覆盖远程分支或本地未合并的分支！")
            else:
                self._show_warning("提示", "无法找到可以添加参数的命令行。")
                logging.warning(f"Could not find a line to append parameter '{param_str}' in sequence: {repr(current_text)}")

    def _add_files_to_sequence(self):
        if not self._check_repo_and_warn(): return
        files_str, ok = QInputDialog.getText(self, "暂存文件", "输入要暂存的文件或目录 (用空格分隔，可用引号):", QLineEdit.EchoMode.Normal)
        if ok and files_str:
            try:
                file_list = shlex.split(files_str.strip())
                if file_list:
                    commands = [f"git add -- {shlex.quote(file_path)}" for file_path in file_list]
                    for cmd in commands: self._add_command_to_sequence(cmd)
                else:
                    self._show_information("无操作", "未输入文件。")
            except ValueError as e:
                self._show_warning("输入错误", f"无法解析文件列表: {e}")
                logging.warning(f"无法解析暂存文件输入 '{files_str}': {e}")
        elif ok:
            self._show_information("无操作", "未输入文件。")


    def _add_commit_to_sequence(self):
        if not self._check_repo_and_warn(): return
        commit_msg, ok = QInputDialog.getText(self, "提交暂存的更改", "输入提交信息:", QLineEdit.EchoMode.Normal)
        if ok and commit_msg:
            clean_msg = commit_msg.strip()
            if not clean_msg:
                self._show_warning("提交中止", "提交信息不能为空。")
                return
            self._add_command_to_sequence(f"git commit -m {shlex.quote(clean_msg)}")
        elif ok and not commit_msg: self._show_warning("提交中止", "提交信息不能为空。")


    def _add_commit_am_to_sequence(self):
        if not self._check_repo_and_warn(): return
        commit_msg, ok = QInputDialog.getText(self, "暂存所有已跟踪文件并提交", "输入提交信息:", QLineEdit.EchoMode.Normal)
        if ok and commit_msg:
            clean_msg = commit_msg.strip()
            if not clean_msg:
                self._show_warning("提交中止", "提交信息不能为空。")
                return
            self._add_command_to_sequence(f"git commit -am {shlex.quote(clean_msg)}")
        elif ok and not commit_msg: self._show_warning("提交中止", "提交信息不能为空。")

    def _add_branch_to_sequence(self):
         if not self._check_repo_and_warn(): return
         branch_name, ok = QInputDialog.getText(self, "创建新分支", "输入新分支的名称:", QLineEdit.EchoMode.Normal)
         if ok and branch_name:
             clean_name = branch_name.strip()
             if not clean_name or re.search(r'[\s\~\^\:\?\*\[\\@\{]', clean_name):
                 self._show_warning("创建失败", "分支名称无效。\n\n分支名称不能包含空格或特殊字符如 ~^:?*[\\@{。")
                 return
             self._add_command_to_sequence(f"git branch {shlex.quote(clean_name)}")
         elif ok and not branch_name:
            self._show_information("操作取消", "分支名称不能为空。")


    def _add_merge_to_sequence(self):
        if not self._check_repo_and_warn(): return
        merge_target, ok = QInputDialog.getText(self, "合并分支/提交", "输入要合并的分支名、标签或提交哈希:", QLineEdit.EchoMode.Normal)
        if ok and merge_target:
            clean_target = merge_target.strip()
            if not clean_target:
                 self._show_warning("操作取消", "目标名称不能为空。")
                 return
            self._add_command_to_sequence(f"git merge {shlex.quote(clean_target)}")
        elif ok and not merge_target:
            self._show_information("操作取消", "目标名称不能为空。")

    def _add_checkout_to_sequence(self):
        if not self._check_repo_and_warn(): return
        checkout_target, ok = QInputDialog.getText(self, "切换分支/提交/文件", "输入要切换到的分支名、标签、提交哈希或文件路径 (使用 -- <path>):\n例如: main, HEAD~1, -- README.md", QLineEdit.EchoMode.Normal)
        if ok and checkout_target:
            clean_target = checkout_target.strip()
            if not clean_target:
                 self._show_warning("操作取消", "目标不能为空。")
                 return
            if clean_target.startswith("-- "):
                 parts = clean_target.split(" ", 1)
                 if len(parts) > 1:
                      quoted_path = shlex.quote(parts[1].strip())
                      self._add_command_to_sequence(f"git checkout -- {quoted_path}")
                 else:
                      self._show_warning("输入错误", "无效的文件路径格式。应为 '-- <path>'")
            else:
                self._add_command_to_sequence(f"git checkout {shlex.quote(clean_target)}")
        elif ok and not checkout_target:
            self._show_information("操作取消", "目标不能为空。")

    def _add_reset_to_sequence(self):
        if not self._check_repo_and_warn(): return
        reset_target, ok = QInputDialog.getText(self, "重置 (Reset)", "输入重置目标和模式 (例如: --hard HEAD~1, --soft <commit>, -- <file>):", QLineEdit.EchoMode.Normal)
        if ok and reset_target:
            clean_target = reset_target.strip()
            if not clean_target:
                 self._show_warning("操作取消", "目标不能为空。")
                 return
            if "--hard" in clean_target.lower():
                 reply = QMessageBox.warning(self, "⚠️ 危险操作: git reset --hard",
                                              "'git reset --hard' 将丢弃工作区和暂存区的所有更改！\n\n此操作不可撤销！\n\n确定要继续吗？",
                                              QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
                                              QMessageBox.StandardButton.Cancel)
                 if reply != QMessageBox.StandardButton.Yes:
                      self._show_information("操作取消", "已取消重置操作。")
                      return

            self._add_command_to_sequence(f"git reset {clean_target}")
        elif ok and not reset_target:
            self._show_information("操作取消", "目标不能为空。")

    def _add_revert_to_sequence(self):
        if not self._check_repo_and_warn(): return
        commit_hash, ok = QInputDialog.getText(self, "撤销提交 (Revert)", "输入要撤销的提交哈希 (commit hash):", QLineEdit.EchoMode.Normal)
        if ok and commit_hash:
            clean_hash = commit_hash.strip()
            if not clean_hash:
                 self._show_warning("操作取消", "提交哈希不能为空。")
                 return
            if not re.match(r'^[a-fA-F0-9]+$', clean_hash):
                 reply = QMessageBox.question(self, "警告", f"'{clean_hash}' 看起来不像一个有效的提交哈希。确定要继续吗？", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel, QMessageBox.StandardButton.Cancel)
                 if reply != QMessageBox.StandardButton.Yes:
                      self._show_information("操作取消", "已取消撤销操作。")
                      return

            self._add_command_to_sequence(f"git revert {shlex.quote(clean_hash)}")
        elif ok and not commit_hash:
            self._show_information("操作取消", "提交哈希不能为空。")

    def _add_rebase_to_sequence(self):
        if not self._check_repo_and_warn(): return
        rebase_target, ok = QInputDialog.getText(self, "变基 (Rebase)", "输入变基目标 (例如: main, HEAD~1, origin/feature):", QLineEdit.EchoMode.Normal)
        if ok and rebase_target:
            clean_target = rebase_target.strip()
            if not clean_target:
                 self._show_warning("操作取消", "变基目标不能为空。")
                 return

            confirmation_msg = f"确定要将当前分支变基到 '{clean_target}' 吗？\n\n将执行: git rebase {clean_target}\n\n变基是一个复杂的操作，可能需要手动解决冲突。请确保您理解其影响！"
            reply = QMessageBox.question(self, "确认变基", confirmation_msg,
                                        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
                                        QMessageBox.StandardButton.Cancel)

            if reply == QMessageBox.StandardButton.Yes:
                logging.info(f"请求变基到: {clean_target}")
                self._add_command_to_sequence(f"git rebase {shlex.quote(clean_target)}")
            else:
                 self._show_information("操作取消", "变基操作已取消。")

        elif ok and not rebase_target:
            self._show_information("操作取消", "变基目标不能为空。")


    def _add_stash_save_to_sequence(self):
        if not self._check_repo_and_warn(): return
        stash_message, ok = QInputDialog.getText(self, "保存工作区 (Stash Save)", "输入 Stash 消息 (可选):", QLineEdit.EchoMode.Normal)
        if ok:
            if stash_message.strip():
                self._add_command_to_sequence(f"git stash save {shlex.quote(stash_message.strip())}")
            else:
                self._add_command_to_sequence("git stash save")

    def _add_tag_to_sequence(self):
        if not self._check_repo_and_warn(): return
        tag_name, ok = QInputDialog.getText(self, "创建标签 (Tag)", "输入标签名称:", QLineEdit.EchoMode.Normal)
        if ok and tag_name:
            clean_name = tag_name.strip()
            if not clean_name:
                self._show_warning("操作取消", "标签名称不能为空。")
                return

            message_reply = QMessageBox.question(self, "添加标签消息", "是否要为标签添加注释消息?",
                                                 QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No | QMessageBox.StandardButton.Cancel,
                                                 QMessageBox.StandardButton.No)

            command = f"git tag {shlex.quote(clean_name)}"
            if message_reply == QMessageBox.StandardButton.Yes:
                 tag_message, msg_ok = QInputDialog.getText(self, "标签消息", "输入标签的注释消息:", QLineEdit.EchoMode.Normal)
                 if msg_ok and tag_message.strip():
                      command = f"git tag -a {shlex.quote(clean_name)} -m {shlex.quote(tag_message.strip())}"
                 elif msg_ok:
                      pass
            elif message_reply == QMessageBox.StandardButton.Cancel:
                 self._show_information("操作取消", "标签创建已取消。")
                 return

            self._add_command_to_sequence(command)
        elif ok and not tag_name:
            self._show_information("操作取消", "标签名称不能为空。")

    def _add_remote_to_sequence(self):
        if not self._check_repo_and_warn(): return
        remote_args, ok = QInputDialog.getText(self, "执行 Remote 命令", "输入 'git remote' 后的子命令和参数 (例如: add origin <url>, remove origin):", QLineEdit.EchoMode.Normal)
        if ok and remote_args:
            clean_args = remote_args.strip()
            if not clean_args:
                 self._show_information("操作取消", "Remote 参数不能为空。")
                 return
            self._add_command_to_sequence(f"git remote {clean_args}")
        elif ok and not remote_args:
            self._show_information("操作取消", "Remote 参数不能为空。")


    def _add_restore_to_sequence(self):
        if not self._check_repo_and_warn(): return

        dialog_title = "恢复文件 (Restore)"
        dialog_prompt = "输入要恢复的文件路径或目录 (用空格分隔，可用引号):"
        files_str, ok = QInputDialog.getText(self, dialog_title, dialog_prompt, QLineEdit.EchoMode.Normal)

        if ok and files_str:
            try:
                file_list = shlex.split(files_str.strip())
                if file_list:
                     restore_source, source_ok = QInputDialog.getItem(self, "选择恢复来源", "从哪里恢复文件?\n(工作树=丢弃未暂存, 暂存区=丢弃已暂存)",
                                                                       ["工作树", "暂存区"], 0, False)

                     if not source_ok:
                          self._show_information("操作取消", "文件恢复已取消。")
                          return

                     is_staged_source = (restore_source == "暂存区")

                     commands = []
                     for file_path in file_list:
                          command = ["git", "restore"]
                          if is_staged_source: command.append("--staged")
                          command.append("--")
                          command.append(shlex.quote(file_path))
                          commands.append(' '.join(command))

                     for cmd in commands: self._add_command_to_sequence(cmd)
                else:
                    self._show_information("无操作", "未输入文件。")
            except ValueError as e:
                self._show_warning("输入错误", f"无法解析文件列表: {e}")
                logging.warning(f"无法解析 restore file input '{files_str}': {e}")
        elif ok:
            self._show_information("无操作", "未输入文件。")


    def get_sequence_text(self) -> str:
         if self.sequence_display:
              return self.sequence_display.toPlainText()
         return ""

    def _clear_sequence(self):
        if self.sequence_display:
             self.sequence_display.clear()
        if self.status_bar: self.status_bar.showMessage("命令序列已清空", 2000)
        logging.info("命令序列已清空。")

    def _execute_sequence(self):
        if not self.sequence_display: return
        full_sequence_text = self.sequence_display.toPlainText()
        command_strings = full_sequence_text.strip().splitlines()
        cleaned_commands = []
        is_repo_valid = self.git_handler.is_valid_repo() if self.git_handler else False

        if not command_strings:
            self._show_information("提示", "命令序列为空，无需执行.")
            return

        is_init_sequence = False
        if command_strings:
             try:
                 first_command_parts = shlex.split(command_strings[0].strip())
                 if first_command_parts and first_command_parts[0].lower() == 'git' and len(first_command_parts) > 1 and first_command_parts[1].lower() == 'init':
                      is_init_sequence = True
             except ValueError:
                 pass

        if not is_repo_valid and not is_init_sequence:
             self._check_repo_and_warn("仓库无效，无法执行命令序列。", allow_init=True)
             return

        for i, cmd_str in enumerate(command_strings):
            cmd_str = cmd_str.strip()
            if not cmd_str:
                continue

            try:
                command_parts = shlex.split(cmd_str)
            except ValueError as e:
                err_msg = f"❌ 命令序列校验失败: 无法解析第 {i+1} 行 '{cmd_str}': {e}"
                self._append_output(err_msg, QColor("red"))
                self._show_warning("命令序列错误", err_msg)
                logging.error(err_msg)
                return

            if not command_parts:
                 continue

            if not is_repo_valid:
                 if i == 0 and not (command_parts[0].lower() == 'git' and len(command_parts) > 1 and command_parts[1].lower() == 'init'):
                      err_msg = f"❌ 命令序列校验失败: 仓库无效，第 {i+1} 行 '{cmd_str}' 不允许执行 (仅允许 'git init' 作为序列的第一条命令)。"
                      self._append_output(err_msg, QColor("red"))
                      self._show_warning("命令序列错误", err_msg)
                      logging.error(err_msg)
                      return
                 elif i > 0:
                      err_msg = f"❌ 命令序列校验失败: 仓库无效，第 {i+1} 行 '{cmd_str}' 不允许执行 (仅允许 'git init' 命令序列)。"
                      self._append_output(err_msg, QColor("red"))
                      self._show_warning("命令序列错误", err_msg)
                      logging.error(err_msg)
                      return

            cleaned_commands.append(cmd_str)

        if not cleaned_commands:
             self._show_information("提示", "命令序列为空（仅包含空行），无需执行.")
             return

        logging.info(f"准备执行命令列表: {cleaned_commands}")
        self._run_command_list_sequentially(cleaned_commands)


    def _set_ui_busy(self, busy: bool):
        for widget in self._repo_dependent_widgets:
            if widget:
                widget.setEnabled(not busy and self.git_handler.is_valid_repo())

        init_button = None
        for layout in self.findChildren(QHBoxLayout):
             if layout:
                  for item_index in range(layout.count()):
                       item = layout.itemAt(item_index)
                       if item and item.widget() and isinstance(item.widget(), QPushButton) and item.widget().text() == "Init":
                            init_button = item.widget()
                            break
                  if init_button: break

        if init_button:
             init_button.setEnabled(not busy)


        for action in self.findChildren(QAction):
            action_text = action.text()
            if action_text in ["选择仓库(&O)...", "Git 全局配置(&G)...", "退出(&X)", "关于(&A)", "清空原始输出"]:
                action.setEnabled(True)


        if busy:
            if self.status_bar: self.status_bar.showMessage("⏳ 正在执行...", 0)
            QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        else:
            QApplication.restoreOverrideCursor()
            self._update_status_bar_info()

    @pyqtSlot()
    def _execute_command_from_input(self):
        if not self.command_input: return
        command_text = self.command_input.text().strip();
        if not command_text: return
        logging.info(f"用户从命令行输入: {command_text}"); prompt_color = QColor(Qt.GlobalColor.darkCyan)

        is_repo_valid = self.git_handler.is_valid_repo() if self.git_handler else False

        try:
             command_parts = shlex.split(command_text)
        except ValueError as e:
             self._show_warning("输入错误", f"无法解析命令: {e}");
             self._append_output(f"❌ 解析命令失败: {command_text}\n{e}", QColor("red"))
             return

        if not command_parts: return

        if not is_repo_valid:
             if len(command_parts) < 2 or command_parts[0].lower() != 'git' or command_parts[1].lower() != 'init':
                  self._show_warning("操作无效", "仓库无效，无法执行除 'git init' 以外的命令。");
                  self._append_output(f"❌ 仓库无效，无法执行命令: {command_text}", QColor("red"))
                  return

        display_cmd = ' '.join(shlex.quote(part) for part in command_parts)
        self._append_output(f"\n$ {display_cmd}", prompt_color)
        self.command_input.clear()

        self._run_command_list_sequentially([command_text], refresh_on_success=True)

    def _load_shortcut_into_builder(self, item: QListWidgetItem = None):
        if not item:
            item = self.shortcut_list_widget.currentItem()
            if not item: return

        shortcut_data = item.data(Qt.ItemDataRole.UserRole)
        if shortcut_data and isinstance(shortcut_data, dict) and shortcut_data.get('sequence'):
            name = shortcut_data.get('name', '未知')
            sequence_str = shortcut_data['sequence']
            if self.sequence_display:
                self.sequence_display.setText(sequence_str.strip())
                self.sequence_display.ensureCursorVisible()

            if self.status_bar: self.status_bar.showMessage(f"快捷键 '{name}' 已加载到序列构建器", 3000)
            logging.info(f"快捷键 '{name}' 已加载到构建器。")
        else:
             logging.warning("双击了列表项，但未获取到快捷键数据或序列。")


    def _execute_sequence_from_string(self, name: str, sequence_str: str):
        if self.status_bar: self.status_bar.showMessage(f"正在执行快捷键: {name}", 3000)

        command_strings = [line.strip() for line in sequence_str.strip().splitlines() if line.strip()]
        cleaned_commands = []
        is_repo_valid = self.git_handler.is_valid_repo() if self.git_handler else False


        if not command_strings:
             self._show_warning("快捷键无效", f"快捷键 '{name}' 解析后命令序列为空。")
             logging.warning(f"快捷键 '{name}' 导致命令列表为空。")
             return

        is_init_sequence = False
        if command_strings:
             try:
                 first_command_parts = shlex.split(command_strings[0].strip())
                 if first_command_parts and first_command_parts[0].lower() == 'git' and len(first_command_parts) > 1 and first_command_parts[1].lower() == 'init':
                      is_init_sequence = True
             except ValueError:
                 pass

        if not is_repo_valid and not is_init_sequence:
            self._check_repo_and_warn(f"仓库无效，无法执行快捷键 '{name}'。", allow_init=True)
            return

        for i, cmd_str in enumerate(command_strings):
             cmd_str = cmd_str.strip()
             if not cmd_str:
                  continue

             try:
                  command_parts = shlex.split(cmd_str)
             except ValueError as e:
                  err_msg = f"❌ 快捷键 '{name}' 校验失败: 无法解析第 {i+1} 行 '{cmd_str}': {e}"
                  self._append_output(err_msg, QColor("red"))
                  self._show_warning("快捷键命令错误", err_msg)
                  logging.error(err_msg)
                  return

             if not command_parts:
                  continue

             if not is_repo_valid:
                  if i == 0 and not (command_parts[0].lower() == 'git' and len(command_parts) > 1 and command_parts[1].lower() == 'init'):
                       err_msg = f"❌ 快捷键 '{name}' 校验失败: 仓库无效，第 {i+1} 行 '{cmd_str}' 不允许执行 (仅允许 'git init' 作为序列的第一条命令)。"
                       self._append_output(err_msg, QColor("red"))
                       self._show_warning("快捷键命令错误", err_msg)
                       logging.error(err_msg)
                       return
                  elif i > 0:
                       err_msg = f"❌ 快捷键 '{name}' 校验失败: 仓库无效，第 {i+1} 行 '{cmd_str}' 不允许执行 (仅允许 'git init' 命令序列)。"
                       self._append_output(err_msg, QColor("red"))
                       self._show_warning("快捷键命令错误", err_msg)
                       logging.error(err_msg)
                       return

             cleaned_commands.append(cmd_str)

        if not cleaned_commands:
            self._show_information("提示", f"快捷键 '{name}' 的命令序列为空，无需执行.")
            return

        logging.info(f"准备执行快捷键 '{name}' 的命令列表: {cleaned_commands}")
        self._run_command_list_sequentially(cleaned_commands)


    @pyqtSlot()
    def _stage_all(self):
        if not self._check_repo_and_warn(): return
        if self.status_tree_model and self.status_tree_model.unstage_root.rowCount() == 0 and self.status_tree_model.untracked_root.rowCount() == 0 and (not hasattr(self.status_tree_model, 'unmerged_root') or self.status_tree_model.unmerged_root.rowCount() == 0):
            self._show_information("无操作", "没有未暂存或未跟踪的文件可供暂存。")
            return
        logging.info("请求暂存所有更改 (git add .)")
        self._run_command_list_sequentially(["git add ."])


    @pyqtSlot()
    def _unstage_all(self):
        if not self._check_repo_and_warn(): return
        if self.status_tree_model and self.status_tree_model.staged_root.rowCount() == 0:
             self._show_information("无操作", "没有已暂存的文件可供撤销。")
             return
        logging.info("请求撤销全部暂存 (git reset HEAD --)");
        self._run_command_list_sequentially(["git reset HEAD --"])


    def _stage_files(self, files: list[str]):
        if not self._check_repo_and_warn() or not files: return
        logging.info(f"请求暂存特定文件: {files}")
        commands = [f"git add -- {shlex.quote(f)}" for f in files]
        self._run_command_list_sequentially(commands)


    def _unstage_files(self, files: list[str]):
        if not self._check_repo_and_warn() or not files: return
        logging.info(f"请求撤销暂存特定文件: {files}")
        commands = [f"git reset HEAD -- {shlex.quote(f)}" for f in files]
        self._run_command_list_sequentially(commands)


    @pyqtSlot(QPoint)
    def _show_status_context_menu(self, pos: QPoint):
        if not self._check_repo_and_warn() or not self.status_tree_view or not self.status_tree_model: return

        index = self.status_tree_view.indexAt(pos)
        if not index.isValid(): return

        selected_indexes = self.status_tree_view.selectionModel().selectedIndexes()
        if not selected_indexes: return

        unique_selected_rows = set(self.status_tree_model.index(idx.row(), STATUS_COL_STATUS, idx.parent()) for idx in selected_indexes if idx.isValid() and idx.parent().isValid())

        if not unique_selected_rows: return

        selected_files_data = self.status_tree_model.get_selected_files(list(unique_selected_rows))
        menu = QMenu()
        added_action = False

        files_to_stage = selected_files_data.get(STATUS_UNSTAGED, []) + selected_files_data.get(STATUS_UNTRACKED, [])
        if files_to_stage:
            stage_action = QAction("暂存选中项 (+)", self)
            stage_action.triggered.connect(lambda: self._stage_files(files_to_stage))
            menu.addAction(stage_action)
            added_action = True

        files_to_unstage = selected_files_data.get(STATUS_STAGED, [])
        if files_to_unstage:
            unstage_action = QAction("撤销暂存选中项 (-)", self)
            unstage_action.triggered.connect(lambda: self._unstage_files(files_to_unstage))
            menu.addAction(unstage_action)
            added_action = True

        files_to_discard_unstaged = selected_files_data.get(STATUS_UNSTAGED, [])
        if files_to_discard_unstaged:
             if added_action: menu.addSeparator()
             discard_action = QAction("丢弃未暂存的更改...", self)
             discard_action.triggered.connect(lambda: self._discard_changes_dialog(files_to_discard_unstaged))
             menu.addAction(discard_action)
             added_action = True

        files_to_resolve_unmerged = selected_files_data.get(STATUS_UNMERGED, [])
        if files_to_resolve_unmerged:
            if added_action: menu.addSeparator()
            resolve_action = QAction("标记为已解决 (仅限合并冲突)", self)
            resolve_action.triggered.connect(lambda: self._resolve_files(files_to_resolve_unmerged))
            menu.addAction(resolve_action)
            added_action = True


        if added_action: menu.exec(self.status_tree_view.viewport().mapToGlobal(pos))
        else: logging.debug("No applicable actions for selected status items.")

    def _discard_changes_dialog(self, files: list[str]):
        if not self._check_repo_and_warn() or not files: return

        message = f"确定要丢弃以下 {len(files)} 个文件的未暂存更改吗？\n\n" + "\n".join(files) + "\n\n此操作不可撤销！"
        reply = QMessageBox.warning(self, "确认丢弃更改", message,
                                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
                                    QMessageBox.StandardButton.Cancel)

        if reply == QMessageBox.StandardButton.Yes:
            logging.info(f"请求丢弃文件更改: {files}")
            commands = [f"git checkout -- {shlex.quote(f)}" for f in files]
            self._run_command_list_sequentially(commands)

    def _resolve_files(self, files: list[str]):
        if not self._check_repo_and_warn() or not files: return
        logging.info(f"请求标记为已解决: {files}")
        commands = [f"git add -- {shlex.quote(f)}" for f in files]
        self._run_command_list_sequentially(commands)


    @pyqtSlot(QItemSelection, QItemSelection)
    def _status_selection_changed(self, selected: QItemSelection, deselected: QItemSelection):
        if not self.status_tree_view or not self.status_tree_model or not self.diff_text_edit or not self._check_repo_and_warn("仓库无效，无法显示差异。"):
             self.diff_text_edit.clear();
             self.diff_text_edit.setPlaceholderText("选中已更改的文件以查看差异...")
             return

        self.diff_text_edit.clear()
        selected_indexes = self.status_tree_view.selectionModel().selectedIndexes()

        if not selected_indexes:
            self.diff_text_edit.setPlaceholderText("选中已更改的文件以查看差异...");
            return

        unique_selected_rows = set(self.status_tree_model.index(idx.row(), STATUS_COL_STATUS, idx.parent()) for idx in selected_indexes if idx.isValid() and idx.parent().isValid())

        if len(unique_selected_rows) != 1:
            self.diff_text_edit.setPlaceholderText("请选择单个文件以查看差异...");
            return

        first_row_index = list(unique_selected_rows)[0]
        path_item_index = self.status_tree_model.index(first_row_index.row(), STATUS_COL_PATH, first_row_index.parent())
        path_item = self.status_tree_model.itemFromIndex(path_item_index)

        if not path_item:
            logging.warning("Could not find path item for selected status row.");
            self.diff_text_edit.setPlaceholderText("无法获取文件路径...");
            return

        file_path = path_item.data(Qt.ItemDataRole.UserRole + 1);
        parent_item = path_item.parent()
        if not parent_item:
             logging.warning("File path item has no parent.");
             self.diff_text_edit.setPlaceholderText("无法确定文件状态...");
             return

        section_type = parent_item.data(Qt.ItemDataRole.UserRole);

        if not file_path:
            logging.warning("File path data missing.");
            self.diff_text_edit.setPlaceholderText("无法获取文件路径...");
            return

        if section_type == STATUS_UNTRACKED:
            self.diff_text_edit.setText(f"'{file_path}' 是未跟踪的文件。\n\n无法显示与仓库的差异。")
            self.diff_text_edit.setPlaceholderText("")
        elif self.git_handler:
            staged_diff = (section_type == STATUS_STAGED)
            self.diff_text_edit.setPlaceholderText(f"正在加载 '{os.path.basename(file_path)}' 的差异...");
            QApplication.processEvents()
            diff_command = ["git", "diff"]
            if staged_diff: diff_command.append("--cached")
            diff_command.extend(["--", file_path])
            self.git_handler.execute_command_async(diff_command, self._on_diff_received)
        else:
            self.diff_text_edit.setText("❌ 内部错误：Git 处理程序不可用。")
            self.diff_text_edit.setPlaceholderText("")


    @pyqtSlot(int, str, str)
    def _on_diff_received(self, return_code: int, stdout: str, stderr: str):
        if not self.diff_text_edit: return
        self.diff_text_edit.setPlaceholderText("");

        if return_code == 0:
            if stdout.strip():
                self._display_formatted_diff(stdout)
            else:
                self.diff_text_edit.setText("文件无差异。")
        else:
            error_message = f"❌ 获取差异失败:\n{stderr}"
            self.diff_text_edit.setText(error_message)
            logging.error(f"Git diff failed: RC={return_code}, Err:{stderr}")

    def _display_formatted_diff(self, diff_text: str):
        if not self.diff_text_edit: return

        self.diff_text_edit.clear()
        cursor = self.diff_text_edit.textCursor()

        default_format = self.diff_text_edit.currentCharFormat()
        add_format = QTextCharFormat(default_format); add_format.setForeground(QColor("darkGreen"))
        del_format = QTextCharFormat(default_format); del_format.setForeground(QColor("red"))
        header_format = QTextCharFormat(default_format); header_format.setForeground(QColor("gray"))

        self.diff_text_edit.setFontFamily("Courier New")

        lines = diff_text.splitlines()
        for line in lines:
            fmt_to_apply = default_format

            if line.startswith('diff ') or line.startswith('index ') or line.startswith('---') or line.startswith('+++') or line.startswith('@@ '):
                fmt_to_apply = header_format
            elif line.startswith('+'):
                fmt_to_apply = add_format
            elif line.startswith('-'):
                fmt_to_apply = del_format
            elif line.startswith('<<<<<<< ') or line.startswith('=======') or line.startswith('>>>>>>> '):
                 header_format_conflict = QTextCharFormat(header_format); header_format_conflict.setForeground(QColor("orange"))
                 fmt_to_apply = header_format_conflict


            cursor.insertText(line, fmt_to_apply)
            cursor.insertText("\n", default_format)

        cursor.movePosition(QTextCursor.MoveOperation.Start)
        self.diff_text_edit.setTextCursor(cursor)
        self.diff_text_edit.ensureCursorVisible()


    @pyqtSlot(QListWidgetItem)
    def _branch_double_clicked(self, item: QListWidgetItem):
        if not item or not self._check_repo_and_warn(): return
        branch_name = item.text().strip();
        if branch_name.startswith("remotes/"):
             self._show_information("操作无效", f"不能直接切换到远程跟踪分支 '{branch_name}'。请右键选择 '基于此创建并切换本地分支...'。");
             return
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
        if ok:
            clean_name = branch_name.strip();
            if not clean_name or re.search(r'[\s\~\^\:\?\*\[\\@\{]', clean_name):
                 self._show_warning("创建失败", "分支名称无效。\n\n分支名称不能包含空格或特殊字符如 ~^:?*[\\@{。")
                 return
            logging.info(f"正在创建新分支: {clean_name}");
            self._run_command_list_sequentially([f"git branch {shlex.quote(clean_name)}"])
        elif ok:
            self._show_information("创建失败", "分支名称不能为空。")


    @pyqtSlot(QPoint)
    def _show_branch_context_menu(self, pos: QPoint):
        if not self._check_repo_and_warn() or not self.branch_list_widget: return
        item = self.branch_list_widget.itemAt(pos);
        if not item: return
        menu = QMenu();
        branch_name = item.text().strip();
        is_remote = branch_name.startswith("remotes/");
        is_current = item.font().bold();
        added_action = False

        if not is_current and not is_remote:
            checkout_action = QAction(f"切换到 '{branch_name}'", self)
            checkout_action.triggered.connect(lambda checked=False, b=branch_name: self._run_command_list_sequentially([f"git checkout {shlex.quote(b)}"]))
            menu.addAction(checkout_action)
            added_action = True

            delete_action = QAction(f"删除本地分支 '{branch_name}'...", self)
            delete_action.triggered.connect(lambda checked=False, b=branch_name: self._delete_branch_dialog(b))
            menu.addAction(delete_action)
            added_action = True

        if is_remote:
             remote_parts = branch_name.split('/', 2);
             if len(remote_parts) == 3:
                 remote_branch_name = remote_parts[2];
                 checkout_remote_action = QAction(f"基于 '{branch_name}' 创建并切换到本地分支...", self)
                 checkout_remote_action.triggered.connect(lambda checked=False, rbn=remote_branch_name, sp=branch_name: self._create_and_checkout_branch_from_dialog(rbn, sp))
                 menu.addAction(checkout_remote_action)
                 added_action = True

                 delete_remote_action = QAction(f"删除远程分支 '{branch_name}'...", self)
                 delete_remote_action.triggered.connect(lambda checked=False, full_name=branch_name: self._delete_remote_branch_dialog_from_full_name(full_name))
                 menu.addAction(delete_remote_action)
                 added_action = True

        if added_action: menu.exec(self.branch_list_widget.mapToGlobal(pos))
        else: logging.debug(f"No applicable context actions for branch item: {branch_name}")


    def _delete_branch_dialog(self, branch_name: str, force: bool = False):
        if not self._check_repo_and_warn() or not branch_name or branch_name.startswith("remotes/"):
             logging.error(f"Invalid local branch name for deletion: {branch_name}");
             return
        delete_flag = "-D" if force else "-d"
        action_text = "强制删除" if force else "删除"
        warning_message = f"确定要{action_text}本地分支 '{branch_name}' 吗？"
        if not force: warning_message += "\n\n此操作仅在分支已合并时安全。如果分支未合并，请使用强制删除 (-D) 或先合并。"
        warning_message += "\n\n此操作通常不可撤销！"

        reply = QMessageBox.warning(self, f"确认{action_text}本地分支", warning_message,
                                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
                                    QMessageBox.StandardButton.Cancel)

        if reply == QMessageBox.StandardButton.Yes:
             logging.info(f"请求{action_text}本地分支: {branch_name} (using {delete_flag})")
             self._run_command_list_sequentially([f"git branch {delete_flag} {shlex.quote(branch_name)}"])
        elif reply == QMessageBox.StandardButton.Cancel and not force:
             force_delete_reply = QMessageBox.question(self, "强制删除?", f"由于分支可能未合并，普通删除失败。\n\n要尝试强制删除本地分支 '{branch_name}' 吗？\n\n此操作可能导致工作丢失。",
                                                         QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                                         QMessageBox.StandardButton.No)
             if force_delete_reply == QMessageBox.StandardButton.Yes:
                  self._delete_branch_dialog(branch_name, force=True)

    def _delete_remote_branch_dialog_from_full_name(self, full_remote_branch_name: str):
         if not self._check_repo_and_warn() or not full_remote_branch_name or not full_remote_branch_name.startswith("remotes/"):
              logging.error(f"Invalid remote branch name for deletion: {full_remote_branch_name}")
              return
         parts = full_remote_branch_name.split('/', 2)
         if len(parts) != 3:
              logging.error(f"Invalid remote branch format: {full_remote_branch_name}")
              self._show_warning("删除失败", f"无法解析远程分支名称: {full_remote_branch_name}")
              return
         remote_name = parts[1]
         branch_name = parts[2]
         self._delete_remote_branch_dialog(remote_name, branch_name)


    def _delete_remote_branch_dialog(self, remote_name: str, branch_name: str):
        if not self._check_repo_and_warn() or not remote_name or not branch_name:
             logging.error(f"Invalid remote/branch name for deletion: {remote_name}/{branch_name}");
             return
        confirmation_message = f"确定要从远程仓库 '{remote_name}' 删除分支 '{branch_name}' 吗？\n\n将执行: git push {remote_name} --delete {branch_name}\n\n此操作通常不可撤销！"
        reply = QMessageBox.warning(self, "确认删除远程分支", confirmation_message, QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel, QMessageBox.StandardButton.Cancel)
        if reply == QMessageBox.StandardButton.Yes:
            logging.info(f"请求删除远程分支: {remote_name}/{branch_name}")
            self._run_command_list_sequentially([f"git push {shlex.quote(remote_name)} --delete {shlex.quote(branch_name)}"])


    def _create_and_checkout_branch_from_dialog(self, suggest_name: str, start_point: str):
         if not self._check_repo_and_warn(): return
         branch_name, ok = QInputDialog.getText(self, "创建并切换本地分支", f"输入新本地分支的名称 (基于 '{start_point}'):", QLineEdit.EchoMode.Normal, suggest_name)
         if ok:
            clean_name = branch_name.strip();
            if not clean_name or re.search(r'[\s\~\^\:\?\*\[\\@\{]', clean_name):
                 self._show_warning("操作失败", "分支名称无效。\n\n分支名称不能包含空格或特殊字符如 ~^:?*[\\@{。")
                 return
            logging.info(f"请求创建并切换到分支: {clean_name} (基于 {start_point})");
            self._run_command_list_sequentially([f"git checkout -b {shlex.quote(clean_name)} {shlex.quote(start_point)}"])
         elif ok:
            self._show_information("操作取消", "名称不能为空。")


    @pyqtSlot()
    def _log_selection_changed(self):
        if not self.log_table_widget or not self.commit_details_textedit or not self.git_handler or not self._check_repo_and_warn("仓库无效，无法显示提交详情。"):
             self.commit_details_textedit.clear()
             self.commit_details_textedit.setPlaceholderText("选中上方提交记录以查看详情...");
             return

        selected_items = self.log_table_widget.selectedItems();
        self.commit_details_textedit.clear()

        if not selected_items:
             self.commit_details_textedit.setPlaceholderText("选中上方提交记录以查看详情...");
             return

        selected_row = self.log_table_widget.currentRow();
        if selected_row < 0:
             self.commit_details_textedit.setPlaceholderText("请选择一个提交记录。"); return

        hash_item = self.log_table_widget.item(selected_row, LOG_COL_COMMIT);
        if hash_item:
            commit_hash = hash_item.data(Qt.ItemDataRole.UserRole)
            if not commit_hash: commit_hash = hash_item.text().strip()

            if commit_hash:
                logging.debug(f"Log selection changed, requesting details for commit: {commit_hash}")
                self.commit_details_textedit.setPlaceholderText(f"正在加载 Commit '{commit_hash[:7]}...' 的详情...");
                QApplication.processEvents()
                self.git_handler.execute_command_async(["git", "show", shlex.quote(commit_hash)], self._on_commit_details_received)
            else:
                self.commit_details_textedit.setPlaceholderText("无法获取选中提交的 Hash.");
                logging.error(f"无法从表格项获取有效 Hash (Row: {selected_row}).")
        else:
            self.commit_details_textedit.setPlaceholderText("无法确定选中的提交项.");
            logging.error(f"无法在日志表格中找到行 {selected_row} 的第 {LOG_COL_COMMIT} 列项。")


    @pyqtSlot(int, str, str)
    def _on_commit_details_received(self, return_code: int, stdout: str, stderr: str):
        if not self.commit_details_textedit: return
        self.commit_details_textedit.setPlaceholderText("");

        if return_code == 0:
            if stdout.strip():
                self.commit_details_textedit.setText(stdout)
            else:
                 self.commit_details_textedit.setText("未获取到提交详情。")
        else:
            error_message = f"❌ 获取提交详情失败:\n{stderr}"
            self.commit_details_textedit.setText(error_message)
            logging.error(f"获取 Commit 详情失败: RC={return_code}, Error: {stderr}")


    def _run_switch_branch(self):
        if not self._check_repo_and_warn(): return
        branch_name, ok = QInputDialog.getText(self,"切换分支","输入要切换到的本地分支名称:",QLineEdit.EchoMode.Normal)
        if ok and branch_name:
            clean_name = branch_name.strip()
            if not clean_name:
                 self._show_information("操作取消", "名称不能为空。")
                 return
            self._run_command_list_sequentially([f"git checkout {shlex.quote(clean_name)}"])
        elif ok and not branch_name: self._show_information("操作取消", "名称不能为空。")


    def _run_list_remotes(self):
        if not self._check_repo_and_warn(): return
        self._run_command_list_sequentially(["git remote -v"], refresh_on_success=False)


    def _open_settings_dialog(self):
        dialog = SettingsDialog(self)
        current_name = ""
        current_email = ""
        if self.git_handler:
            try:
                 name_result = self.git_handler.execute_command_sync(["git", "config", "--global", "user.name"])
                 email_result = self.git_handler.execute_command_sync(["git", "config", "--global", "user.email"])
                 current_name = name_result.stdout.strip() if name_result and name_result.returncode == 0 else ""
                 current_email = email_result.stdout.strip() if email_result and email_result.returncode == 0 else ""
                 dialog.name_edit.setText(current_name)
                 dialog.email_edit.setText(current_email)
            except Exception as e:
                 logging.warning(f"Failed to fetch global config: {e}")

        if dialog.exec():
            config_data = dialog.get_data()
            commands_to_run = []

            name_val = config_data.get("user.name")
            email_val = config_data.get("user.email")

            if name_val is not None and name_val.strip() != current_name: commands_to_run.append(f"git config --global user.name {shlex.quote(name_val.strip())}")
            if email_val is not None and email_val.strip() != current_email: commands_to_run.append(f"git config --global user.email {shlex.quote(email_val.strip())}")

            if commands_to_run:
                 confirmation_msg = "将执行以下全局 Git 配置命令:\n\n" + "\n".join(commands_to_run) + "\n\n确定吗？"
                 reply = QMessageBox.question(self, "应用全局配置", confirmation_msg, QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel, QMessageBox.StandardButton.Yes)
                 if reply == QMessageBox.StandardButton.Yes:
                     logging.info(f"Executing global config commands: {commands_to_run}")
                     if self.git_handler:
                         self._run_command_list_sequentially(commands_to_run, refresh_on_success=False)
                     else:
                         logging.error("GitHandler unavailable for settings.")
                         QMessageBox.critical(self, "错误", "无法执行配置命令。")
                 else:
                     self._show_information("操作取消", "未应用全局配置更改。")
            else:
                 self._show_information("无更改", "未检测到有效的用户名或邮箱信息变更。")


    def _show_about_dialog(self):
        try:
             version = self.windowTitle().split('v')[-1].strip()
        except:
             version = "N/A"
        about_text = f"""
<!DOCTYPE html>
        <html lang="zh-CN">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>简易 Git GUI 信息</title>
            <style>
                body {
                    font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                    line-height: 1.6;
                    margin: 20px;
                    background-color: #f4f4f4;
                    color: #333;
                }
                .container {
                    max-width: 800px;
                    margin: auto;
                    background-color: #fff;
                    padding: 30px;
                    border-radius: 8px;
                    box-shadow: 0 2px 5px rgba(0, 0, 0, 0.1);
                    position: relative;
                }
                h1 { color: #007bff; border-bottom: 2px solid #007bff; padding-bottom: 10px; margin-bottom: 20px; }
                h2 { color: #555; margin-top: 25px; margin-bottom: 15px; }
                ul { list-style-type: disc; padding-left: 20px; }
                li { margin-bottom: 8px; }
                a { color: #007bff; text-decoration: none; }
                a:hover { text-decoration: underline; }
                .info-section { margin-top: 25px; padding-top: 15px; border-top: 1px dashed #ccc; font-size: 0.9em; color: #666; }

                .copy-button {
                    display: inline-block; /* Change from absolute if you don't want top-right positioning */
                    margin-top: 15px; /* Add some space below the text */
                    padding: 8px 15px;
                    background-color: #28a745;
                    color: white;
                    border: none;
                    border-radius: 5px;
                    cursor: pointer;
                    font-size: 0.9em;
                    transition: background-color 0.3s ease;
                }
                .copy-button:hover { background-color: #218838; }
                .copy-button:active { background-color: #1e7e34; }

                 /* Simple feedback for WebEngine - more complex feedback needs JS within HTML */
                 #copyFeedback {
                     color: green;
                     margin-left: 10px;
                     opacity: 0;
                     transition: opacity 0.3s ease;
                 }
                 #copyFeedback.visible {
                     opacity: 1;
                 }

            </style>
             <!-- Required for QWebChannel communication -->
            <script src="qrc:///qtwebchannel/qwebchannel.js"></script>
        </head>
        <body>

        <div class="container" id="contentToCopy"> {/* Added ID for easy access */}
            <h1>简易 Git GUI</h1>

            <p>版本: {version}</p>

            <p>这是一个简单的 Git GUI 工具，用于学习和执行 Git 命令。</p>

            <h2>开发日志:</h2>
            <ul>
                <li>v1.0 - 初始版本 (仓库选择, 状态, Diff, Log, 命令输入)</li>
                <li>v1.1 - 增加暂存/撤销暂存单个文件</li>
                <li>v1.2 - 增加创建/切换/删除分支</li>
                <li>v1.2 - 增加创建/切换/删除分支</li>
                <li>v1.3 - 提交功能</li>
                <li>v1.4 - 增加 Pull/Push/Fetch 按钮</li>
                <li>v1.5 - 增加 Git 全局配置对话框</li>
                <li>v1.6 - 异步执行命令，优化UI响应</li>
                <li>v1.7 - 增加命令序列构建器和快捷键功能</li>
                <li>v1.8 - 增加提交详情显示和提交历史记录</li>
                <li>v1.9 - 增加远程仓库列表功能</li>
                <li>v1.10 - 增加全局配置保存和加载功能</li>
                <li>v1.11 - 增加更多命令和参数按钮，优化参数添加提示/校验，增强输入校验/警告</li>
                <li>v1.12 - 增加 rebase 命令构建块</li>
                <li>v1.13 - 修复 _update_ui_enable_state 中的 TypeError；实现参数添加到当前行；状态栏显示远程仓库信息；优化需要参数的命令构建对话框。</li>
            </ul>

            <div class="info-section">
                <p>本项目是学习 Qt6 和 Git 命令交互的实践项目</p>
                <p>作者: GitHub @424635328</p>
                <p>项目地址: <a href="https://github.com/424635328/Git-Helper" target="_blank">https://github.com/424635328/Git-Helper</a></p>
                <p>date: 2025-04-22</p>
            </div>

            {/* Button and Feedback within HTML */}
            <button class="copy-button" onclick="copyAllContent()">复制全部文本</button>
            <span id="copyFeedback">已复制!</span> {/* Simple feedback element */}

        </div>

        <script>
            // Function called by the button click
            function copyAllContent() {
                const contentElement = document.getElementById('contentToCopy');
                if (contentElement) {
                    // Get the text content, ignoring the copy button and feedback
                    let textToCopy = '';
                     const elements = contentElement.querySelectorAll('h1, p, h2, li, .info-section p');
                        elements.forEach(element => {
                            if (element.tagName === 'H1') {
                                textToCopy += element.innerText + '\n\n';
                            } else if (element.tagName === 'H2') {
                                 textToCopy += '\n' + element.innerText + ':\n';
                            } else if (element.tagName === 'LI') {
                                 textToCopy += '- ' + element.innerText + '\n';
                            } else {
                                textToCopy += element.innerText + '\n';
                            }
                        });
                    textToCopy = textToCopy.trim();


                    // Call the Qt method exposed via QWebChannel
                    if (window.clipboardHelper) {
                        window.clipboardHelper.copyToClipboard(textToCopy);

                        // Show feedback
                        const feedback = document.getElementById('copyFeedback');
                        if (feedback) {
                            feedback.classList.add('visible');
                            setTimeout(() => {
                                feedback.classList.remove('visible');
                            }, 1500); // Hide feedback after 1.5 seconds
                        }

                    } else {
                         console.error("ClipboardHelper object not available in JavaScript.");
                         alert("复制功能未初始化，请稍后再试或手动复制。");
                    }
                } else {
                    console.error("Content element not found.");
                }
            }
        </script>

        </body>
        </html>
"""
        msg_box = QMessageBox(self)
        msg_box.setWindowTitle("关于 简易 Git GUI")
        msg_box.setText(about_text)
        msg_box.setTextFormat(Qt.TextFormat.RichText)
        msg_box.setStandardButtons(QMessageBox.StandardButton.Ok)
        msg_box.exec()

    def closeEvent(self, event):
        logging.info("应用程序关闭请求。")
        try:
            if self.git_handler and hasattr(self.git_handler, 'active_operations') and self.git_handler.active_operations:
                 active_count = len(self.git_handler.active_operations)
                 if active_count > 0:
                      logging.warning(f"窗口关闭时仍有 {active_count} 个 Git 操作可能在后台运行。")
        except Exception as e: logging.exception("关闭窗口时检查 Git 操作出错。")

        logging.info("应用程序正在关闭。")
        event.accept()