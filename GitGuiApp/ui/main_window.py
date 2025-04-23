# ui/main_window.py
# -*- coding: utf-8 -*-
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
from typing import Union, Optional, List
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
        self.setWindowTitle("Git GUI v1.11")
        self.setGeometry(100, 100, 1200, 900)

        self.git_handler = GitHandler()
        self.db_handler = DatabaseHandler()
        self.shortcut_manager = ShortcutManager(self,self.db_handler, self.git_handler)

        self.current_command_sequence = []
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


        self._init_ui()
        self.shortcut_manager.load_and_register_shortcuts()
        self._update_repo_status()

        logging.info("主窗口初始化完成。")

    def _check_repo_and_warn(self, message="请先选择一个有效的 Git 仓库。"):
        if not self.git_handler or not self.git_handler.is_valid_repo():
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
        is_init_command = command_strings and command_strings[0].strip().lower().startswith("git init")

        if not is_init_command and not self._check_repo_and_warn("仓库无效，无法执行命令序列 (除 git init 外)。"):
             return

        logging.debug(f"准备执行命令列表: {command_strings}, 成功后刷新: {refresh_on_success}")

        if self.main_tab_widget and self._output_tab_index != -1:
             self.main_tab_widget.setCurrentIndex(self._output_tab_index)
             if self.output_display:
                  self._append_output("\n--- 开始执行新的命令序列 ---", QColor("darkCyan"))
                  self.output_display.ensureCursorVisible()
             QApplication.processEvents()

        self._set_ui_busy(True)

        return_code = -1  # Initialize return_code in the enclosing scope

        def execute_next(index):
            if index >= len(command_strings):
                self._append_output("\n✅ --- 所有命令执行完毕 ---", QColor("green"))
                self._set_ui_busy(False)
                if refresh_on_success:
                     current_repo_valid = self.git_handler and self.git_handler.is_valid_repo()
                     # Only refresh if the repo is currently valid (might have become invalid during sequence)
                     if current_repo_valid:
                          self._refresh_all_views()
                     # If it was an init command that just finished successfully, update status which might trigger refresh
                     elif is_init_command and return_code == 0:
                          self._update_repo_status()

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

            # Store return code of the last executed command
            return_code = -1 # Reset for the next command

            @pyqtSlot(int, str, str)
            def on_command_finished(rc, stdout, stderr):
                # Assign to the nonlocal variable inside the callback
                nonlocal return_code
                return_code = rc
                QTimer.singleShot(10, lambda r=rc, s=stdout, e=stderr: process_finish(r, s, e))


            def process_finish(rc_local, stdout, stderr):
                # Process output first
                if stdout: self._append_output(f"stdout:\n{stdout.strip()}")
                if stderr: self._append_output(f"stderr:\n{stderr.strip()}")

                # Check result code
                if rc_local == 0:
                    self._append_output(f"✅ 成功: '{display_cmd}'", QColor("Green"))
                    # If it was a git init, re-validate repo immediately AFTER success
                    if display_cmd.lower().startswith("git init"):
                         if self.git_handler:
                              current_path = self.git_handler.get_repo_path()
                              if current_path:
                                   self.git_handler.set_repo_path(current_path) # Re-validate the path
                              self._update_repo_status() # This will enable UI if valid
                         QTimer.singleShot(50, lambda idx=index + 1: execute_next(idx)) # Allow UI to update slightly
                    else:
                         QTimer.singleShot(10, lambda idx=index + 1: execute_next(idx)) # Proceed immediately
                else:
                    # Command failed, stop the sequence
                    err_msg = f"❌ 失败 (RC: {rc_local}) '{display_cmd}'，执行中止。"
                    logging.error(f"命令执行失败! 命令: '{display_cmd}', 返回码: {rc_local}, 标准错误: {stderr.strip()}")
                    self._append_output(err_msg, QColor("red"))
                    self._set_ui_busy(False) # Release UI lock on failure


            @pyqtSlot(str)
            def on_progress(message):
                # Filter verbose progress messages if desired
                if message and not (message.startswith("Receiving objects:") or message.startswith("Resolving deltas:") or message.startswith("remote:")):
                    if self.status_bar: self.status_bar.showMessage(message, 3000)

            # Initial value before the first command runs
            return_code = -1
            self.git_handler.execute_command_async(command_parts, on_command_finished, on_progress)

        execute_next(0)

    def _add_repo_dependent_widget(self, widget):
         if widget:
              self._repo_dependent_widgets.append(widget)

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
        command_builder_layout_1.setObjectName('command_builder_layout_1') # Name for lookup
        init_button = self._add_command_button(command_builder_layout_1, "Init", "添加 'git init' 到序列 (用于初始化新仓库)", lambda: self._add_command_to_sequence("git init"), is_repo_dependent=False)
        init_button.setObjectName("Init") # Set object name for specific lookup
        self._add_command_button(command_builder_layout_1, "Branch...", "添加 'git branch ' 到序列 (需要补充)", lambda: self._add_command_to_sequence("git branch "))
        self._add_command_button(command_builder_layout_1, "Merge...", "添加 'git merge <branch>' 到序列 (需要输入)", self._add_merge_to_sequence)
        self._add_command_button(command_builder_layout_1, "Checkout...", "添加 'git checkout <ref/path>' 到序列 (需要输入)", self._add_checkout_to_sequence)
        left_layout.addLayout(command_builder_layout_1)

        command_builder_layout_2 = QHBoxLayout()
        command_builder_layout_2.setObjectName('command_builder_layout_2') # Name for lookup
        self._add_command_button(command_builder_layout_2, "Reset...", "添加 'git reset ' 到序列 (需要输入)", self._add_reset_to_sequence)
        self._add_command_button(command_builder_layout_2, "Revert...", "添加 'git revert <commit>' 到序列 (需要输入)", self._add_revert_to_sequence)
        self._add_command_button(command_builder_layout_2, "Rebase...", "添加 'git rebase ' 到序列 (需要输入)", self._add_rebase_to_sequence)
        self._add_command_button(command_builder_layout_2, "Stash Save...", "添加 'git stash save' 到序列 (可输入消息)", self._add_stash_save_to_sequence)
        left_layout.addLayout(command_builder_layout_2)

        command_builder_layout_3 = QHBoxLayout()
        command_builder_layout_3.setObjectName('command_builder_layout_3') # Name for lookup
        self._add_command_button(command_builder_layout_3, "Stash Pop", "添加 'git stash pop' 到序列", lambda: self._add_command_to_sequence("git stash pop"))
        self._add_command_button(command_builder_layout_3, "Tag...", "添加 'git tag <name>' 到序列 (需要输入)", self._add_tag_to_sequence)
        self._add_command_button(command_builder_layout_3, "Remote...", "添加 'git remote ' 到序列 (需要补充)", lambda: self._add_command_to_sequence("git remote "))
        self._add_command_button(command_builder_layout_3, "Restore...", "添加 'git restore ' 到序列 (需要输入)", self._add_restore_to_sequence)
        self._add_command_button(command_builder_layout_3, "Main", "添加 'git checkout main' 到序列", lambda: self._add_command_to_sequence("git checkout main"))
        self._add_command_button(command_builder_layout_3, "Master", "添加 'git checkout master' 到序列", lambda: self._add_command_to_sequence("git checkout master"))
        left_layout.addLayout(command_builder_layout_3)


        left_layout.addWidget(QLabel("常用参数/选项 (添加到序列末尾行):"))
        parameter_buttons_layout = QHBoxLayout()
        self._add_command_button(parameter_buttons_layout, "-a", "添加 '-a' 参数到序列末尾行", lambda: self._add_parameter_to_sequence("-a"))
        self._add_command_button(parameter_buttons_layout, "-v", "添加 '-v' 参数到序列末尾行", lambda: self._add_parameter_to_sequence("-v"))
        self._add_command_button(parameter_buttons_layout, "-s", "添加 '-s' 参数到序列末尾行 (常用于 commit)", lambda: self._add_parameter_to_sequence("-s"))
        self._add_command_button(parameter_buttons_layout, "-f", "添加 '-f' 参数到序列末尾行 (强制)", lambda: self._add_parameter_to_sequence("-f"))
        self._add_command_button(parameter_buttons_layout, "-u", "添加 '-u' 参数到序列末尾行 (上游跟踪)", lambda: self._add_parameter_to_sequence("-u"))
        self._add_command_button(parameter_buttons_layout, "-d", "添加 '-d' 参数到序列末尾行 (删除)", lambda: self._add_parameter_to_sequence("-d"))
        self._add_command_button(parameter_buttons_layout, "-p", "添加 '-p' 参数到序列末尾行 (补丁模式)", lambda: self._add_parameter_to_sequence("-p"))
        self._add_command_button(parameter_buttons_layout, "-x", "添加 '-x' 参数到序列末尾行", lambda: self._add_parameter_to_sequence("-x"))
        left_layout.addLayout(parameter_buttons_layout)

        parameter_buttons_layout_2 = QHBoxLayout()
        self._add_command_button(parameter_buttons_layout_2, "--hard", "添加 '--hard' 参数到序列末尾行 (危险! 通常用于 reset)", lambda: self._add_parameter_to_sequence("--hard"))
        self._add_command_button(parameter_buttons_layout_2, "--soft", "添加 '--soft' 参数到序列末尾行 (常用于 reset)", lambda: self._add_parameter_to_sequence("--soft"))
        self._add_command_button(parameter_buttons_layout_2, "--quiet", "添加 '--quiet' 参数到序列末尾行 (减少输出)", lambda: self._add_parameter_to_sequence("--quiet"))
        self._add_command_button(parameter_buttons_layout_2, "--force", "添加 '--force' 参数到序列末尾行 (强制)", lambda: self._add_parameter_to_sequence("--force"))
        left_layout.addLayout(parameter_buttons_layout_2)

        left_layout.addWidget(QLabel("命令序列构建器 (可编辑):"))
        self.sequence_display = QTextEdit()
        self.sequence_display.setPlaceholderText("点击上方按钮构建命令序列，手动编辑，或从快捷键加载...")
        self.sequence_display.setFixedHeight(100)
        left_layout.addWidget(self.sequence_display)
        self._add_repo_dependent_widget(self.sequence_display)

        sequence_actions_layout = QHBoxLayout()
        execute_button = QPushButton("执行序列")
        execute_button.setToolTip("执行上方编辑或构建的命令序列")
        execute_button.setStyleSheet("background-color: darkred; color: black;")
        execute_button.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        execute_button.clicked.connect(self._execute_sequence)
        self._add_repo_dependent_widget(execute_button)

        clear_button = QPushButton("清空序列")
        clear_button.setToolTip("清空上方命令序列")
        clear_button.clicked.connect(self._clear_sequence)
        self._add_repo_dependent_widget(clear_button)

        save_shortcut_button = QPushButton("保存快捷键")
        save_shortcut_button.setToolTip("将上方命令序列保存为新的快捷键")
        save_shortcut_button.clicked.connect(self._save_sequence_as_shortcut)
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
        self.shortcut_list_widget.setToolTip("双击加载到构建器，右键删除")
        self.shortcut_list_widget.itemDoubleClicked.connect(self._load_shortcut_into_builder)
        self.shortcut_list_widget.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.shortcut_list_widget.customContextMenuRequested.connect(self.shortcut_manager.show_shortcut_context_menu)
        left_layout.addWidget(self.shortcut_list_widget, 1)

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
        else:
            if self.status_bar: self.status_bar.showMessage("请选择一个有效的 Git 仓库目录", 0)
            if self.status_tree_model: self.status_tree_model.clear_status()
            if self.branch_list_widget: self.branch_list_widget.clear()
            if self.log_table_widget: self.log_table_widget.setRowCount(0)
            if self.diff_text_edit: self.diff_text_edit.clear(); self.diff_text_edit.setPlaceholderText("请选择有效仓库")
            if self.commit_details_textedit: self.commit_details_textedit.clear(); self.commit_details_textedit.setPlaceholderText("请选择有效仓库")
            self._clear_sequence()
            self.current_branch_name_display = "(无效仓库)"
            self._update_status_bar_info()
            logging.info("Git 仓库无效，相关 UI 已禁用/清空。")


    def _update_ui_enable_state(self, enabled: bool):
        logging.debug(f"Updating UI enable state to: {enabled}")
        for widget in self._repo_dependent_widgets:
            if widget:
                # Handle QAction separately as they might be in menus/toolbars
                if isinstance(widget, QAction):
                     is_always_enabled = widget.text() in ["选择仓库(&O)...", "Git 全局配置(&G)...", "退出(&X)", "关于(&A)", "清空原始输出"]
                     if not is_always_enabled:
                          widget.setEnabled(enabled)
                # Handle other widgets (Buttons, Edits, Lists, Views etc.)
                else:
                    widget.setEnabled(enabled)

        init_button = self.findChild(QPushButton, "Init", Qt.FindChildOption.FindChildrenRecursively)
        if init_button:
             init_button.setEnabled(True)
        else:
             logging.warning("Could not find the Init button to ensure it's enabled.")

        # Ensure always-enabled actions are definitely enabled
        for action in self.findChildren(QAction):
            action_text = action.text()
            if action_text in ["选择仓库(&O)...", "Git 全局配置(&G)...", "退出(&X)", "关于(&A)", "清空原始输出"]:
                action.setEnabled(True)


    def _update_status_bar_info(self):
        if not self.status_bar: return

        is_valid = self.git_handler.is_valid_repo() if self.git_handler else False
        repo_path = self.git_handler.get_repo_path() if self.git_handler else None

        repo_path_short = repo_path or "(未选择)"
        if len(repo_path_short) > 40:
            repo_path_short = f"...{repo_path_short[-37:]}"

        branch_display = self.current_branch_name_display if self.current_branch_name_display else ("(未知分支)" if is_valid else "(无效仓库)")

        remote_info = ""
        if is_valid:
            remotes_result = self.git_handler.execute_command_sync(["git", "remote"])
            if remotes_result and remotes_result.returncode == 0 and remotes_result.stdout.strip():
                remote_names = remotes_result.stdout.strip().splitlines()
                if remote_names:
                    remote_info = f" | 远程: {', '.join(remote_names[:2])}{'...' if len(remote_names) > 2 else ''}"

        status_message = f"分支: {branch_display}{remote_info} | 仓库: {repo_path_short}"

        if self.status_bar.currentMessage().startswith("⏳ "):
             pass
        else:
            self.status_bar.showMessage(status_message, 0)


    @pyqtSlot()
    def _refresh_all_views(self):
        if not self._check_repo_and_warn("无法刷新视图，仓库无效。"): return

        logging.info("正在刷新状态、分支和日志视图...")
        if self.status_bar: self.status_bar.showMessage("⏳ 正在刷新...", 0)
        QApplication.processEvents()

        self._pending_refreshes = {'status': True, 'branch': True, 'log': True}

        self._refresh_status_view()
        self._refresh_branch_list()
        self._refresh_log_view()


    def _check_and_clear_busy_status(self, view_name: str):
        if hasattr(self, '_pending_refreshes') and view_name in self._pending_refreshes:
            self._pending_refreshes[view_name] = False
            if not any(self._pending_refreshes.values()):
                self._update_status_bar_info()


    @pyqtSlot()
    def _refresh_status_view(self):
        if not self.git_handler or not self.git_handler.is_valid_repo():
             logging.warning("试图刷新状态，但 GitHandler 不可用或仓库无效。")
             self._check_and_clear_busy_status('status')
             return

        logging.debug("正在请求 status porcelain...")
        stage_all_btn = next((w for w in self._repo_dependent_widgets if isinstance(w, QPushButton) and w.text() == "全部暂存 (+)"), None)
        unstage_all_btn = next((w for w in self._repo_dependent_widgets if isinstance(w, QPushButton) and w.text() == "全部撤销暂存 (-)"), None)
        if stage_all_btn: stage_all_btn.setEnabled(False)
        if unstage_all_btn: unstage_all_btn.setEnabled(False)

        if self.diff_text_edit: self.diff_text_edit.clear(); self.diff_text_edit.setPlaceholderText("选中已更改的文件以查看差异...")

        self.git_handler.get_status_porcelain_async(self._on_status_refreshed)


    @pyqtSlot(int, str, str)
    def _on_status_refreshed(self, return_code: int, stdout: str, stderr: str):
        if not self.status_tree_model or not self.status_tree_view:
             logging.error("状态树模型或视图在状态刷新回调时未初始化。")
             self._check_and_clear_busy_status('status')
             return

        stage_all_btn = next((w for w in self._repo_dependent_widgets if isinstance(w, QPushButton) and w.text() == "全部暂存 (+)"), None)
        unstage_all_btn = next((w for w in self._repo_dependent_widgets if isinstance(w, QPushButton) and w.text() == "全部撤销暂存 (-)"), None)

        if self.status_tree_view:
             self.status_tree_view.setUpdatesEnabled(False)

        try:
            if return_code == 0:
                self.status_tree_model.parse_and_populate(stdout)
                self.status_tree_view.expandAll()
                self.status_tree_view.resizeColumnToContents(STATUS_COL_STATUS)
                self.status_tree_view.setColumnWidth(STATUS_COL_STATUS, max(100, self.status_tree_view.columnWidth(STATUS_COL_STATUS)))

                has_stageable = self.status_tree_model.unstage_root.rowCount() > 0 or \
                                self.status_tree_model.untracked_root.rowCount() > 0 or \
                                (hasattr(self.status_tree_model, 'unmerged_root') and self.status_tree_model.unmerged_root.rowCount() > 0)
                has_unstageable = self.status_tree_model.staged_root.rowCount() > 0

                if stage_all_btn: stage_all_btn.setEnabled(has_stageable)
                if unstage_all_btn: unstage_all_btn.setEnabled(has_unstageable)

            else:
                logging.error(f"获取状态失败: RC={return_code}, 错误: {stderr}")
                self._append_output(f"❌ 获取 Git 状态失败:\n{stderr}", QColor("red"))
                self.status_tree_model.clear_status()
                if stage_all_btn: stage_all_btn.setEnabled(False)
                if unstage_all_btn: unstage_all_btn.setEnabled(False)

        finally:
            if self.status_tree_view:
                 self.status_tree_view.setUpdatesEnabled(True)
            self._check_and_clear_busy_status('status')


    @pyqtSlot()
    def _refresh_branch_list(self):
        if not self.git_handler or not self.git_handler.is_valid_repo():
             logging.warning("试图刷新分支列表，但 GitHandler 不可用或仓库无效。")
             self._check_and_clear_busy_status('branch')
             return
        if self.branch_list_widget: self.branch_list_widget.clear()
        self.git_handler.get_branches_formatted_async(self._on_branches_refreshed)


    @pyqtSlot(int, str, str)
    def _on_branches_refreshed(self, return_code: int, stdout: str, stderr: str):
        if not self.branch_list_widget or not self.git_handler:
             logging.error("分支列表组件或 GitHandler 在分支刷新回调时未初始化。")
             self.current_branch_name_display = "(内部错误)"
             self._check_and_clear_busy_status('branch')
             self._update_status_bar_info()
             return

        self.branch_list_widget.clear()
        current_branch_found = None
        is_valid = self.git_handler.is_valid_repo()

        if return_code == 0 and is_valid:
            lines = stdout.strip().splitlines()
            for line in lines:
                if not line: continue
                is_current = line.startswith('*')
                branch_name = line.lstrip('* ').strip()

                if not branch_name: continue

                item = QListWidgetItem(branch_name)
                if is_current:
                    current_branch_found = branch_name
                    font = item.font(); font.setBold(True); item.setFont(font)
                    item.setForeground(QColor("blue"))
                elif branch_name.startswith("remotes/"):
                    item.setForeground(QColor("gray"))

                self.branch_list_widget.addItem(item)

            if current_branch_found:
                 self.current_branch_name_display = current_branch_found
                 items = self.branch_list_widget.findItems(current_branch_found, Qt.MatchFlag.MatchExactly)
                 if items: self.branch_list_widget.setCurrentItem(items[0])
            else:
                 self.current_branch_name_display = "(未知分支)"
                 logging.warning("未能从格式化输出中识别当前分支。")


        elif is_valid:
            logging.error(f"获取分支失败: RC={return_code}, 错误: {stderr}")
            self._append_output(f"❌ 获取分支列表失败:\n{stderr}", QColor("red"))
            self.current_branch_name_display = "(获取失败)"
        elif not is_valid:
             logging.warning("仓库在分支刷新前变得无效，跳过处理分支结果。")
             self.current_branch_name_display = "(无效仓库)"

        self._check_and_clear_busy_status('branch')
        self._update_status_bar_info()


    @pyqtSlot()
    def _refresh_log_view(self):
        if not self.git_handler or not self.git_handler.is_valid_repo():
             logging.warning("试图刷新日志，但 GitHandler 不可用或仓库无效。")
             self._check_and_clear_busy_status('log')
             return
        if self.log_table_widget: self.log_table_widget.setRowCount(0)
        if self.commit_details_textedit: self.commit_details_textedit.clear(); self.commit_details_textedit.setPlaceholderText("选中上方提交记录以查看详情...")

        self.git_handler.get_log_formatted_async(count=200, finished_slot=self._on_log_refreshed)


    @pyqtSlot(int, str, str)
    def _on_log_refreshed(self, return_code: int, stdout: str, stderr: str):
        if not self.log_table_widget:
             logging.error("日志表格组件在日志刷新回调时未初始化。")
             self._check_and_clear_busy_status('log')
             return

        if return_code == 0:
            lines = stdout.strip().splitlines()
            self.log_table_widget.setUpdatesEnabled(False)
            self.log_table_widget.setRowCount(0)
            monospace_font = QFont("Courier New")
            valid_rows = 0

            log_line_regex = re.compile(r'^[\\/|*._ -]*([a-fA-F0-9]+)\t(.*?)\t(.*?)\t(.*)$')

            for line in lines:
                line = line.strip()
                if not line: continue

                match = log_line_regex.match(line)
                if match:
                    commit_hash, author, date, message = match.groups()

                    if not commit_hash:
                         logging.warning(f"日志行匹配但哈希为空: {repr(line)}")
                         continue

                    self.log_table_widget.insertRow(valid_rows)

                    hash_item = QTableWidgetItem(commit_hash[:7])
                    author_item = QTableWidgetItem(author.strip())
                    date_item = QTableWidgetItem(date.strip())
                    message_item = QTableWidgetItem(message.strip())

                    flags = Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled
                    hash_item.setFlags(flags); author_item.setFlags(flags); date_item.setFlags(flags); message_item.setFlags(flags)
                    hash_item.setData(Qt.ItemDataRole.UserRole, commit_hash)
                    hash_item.setFont(monospace_font)

                    self.log_table_widget.setItem(valid_rows, LOG_COL_COMMIT, hash_item)
                    self.log_table_widget.setItem(valid_rows, LOG_COL_AUTHOR, author_item)
                    self.log_table_widget.setItem(valid_rows, LOG_COL_DATE, date_item)
                    self.log_table_widget.setItem(valid_rows, LOG_COL_MESSAGE, message_item)

                    valid_rows += 1
                else:
                     if not re.match(r'^[\s\\/|*._-]+$', line):
                        logging.warning(f"无法解析日志行（与预期格式不匹配）: {repr(line)}")


            self.log_table_widget.setUpdatesEnabled(True)
            logging.info(f"日志表格已填充 {valid_rows} 个有效条目。")
        else:
            logging.error(f"获取日志失败: RC={return_code}, 错误: {stderr}")
            self._append_output(f"❌ 获取提交历史失败:\n{stderr}", QColor("red"))

        self._check_and_clear_busy_status('log')


    def _select_repository(self):
        start_path = self.git_handler.get_repo_path() if self.git_handler else None
        if not start_path or not os.path.isdir(start_path):
            start_path = os.getcwd()
            if not os.path.isdir(os.path.join(start_path, '.git')):
                 home_git = os.path.join(os.path.expanduser("~"), 'git')
                 if os.path.isdir(home_git):
                      start_path = home_git
                 else:
                      start_path = os.path.expanduser("~")


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

        if not self.sequence_display: return

        current_text = self.sequence_display.toPlainText()
        if current_text and not current_text.endswith('\n'):
            self.sequence_display.append("")

        self.sequence_display.append(command_str)
        logging.debug(f"命令添加到序列显示: {command_str}")

    def _add_parameter_to_sequence(self, parameter_to_add: str):
        param_str = parameter_to_add.strip()
        if not param_str:
            logging.debug("Attempted to add empty parameter, ignoring.")
            return

        if not self.sequence_display: return

        current_text = self.sequence_display.toPlainText()
        lines = current_text.splitlines(keepends=True)

        last_non_empty_line_index = -1
        for i in range(len(lines) - 1, -1, -1):
            if lines[i].strip():
                last_non_empty_line_index = i
                break

        if last_non_empty_line_index != -1:
            lines[last_non_empty_line_index] = lines[last_non_empty_line_index].rstrip('\r\n') + " " + param_str + '\n'
            new_text = "".join(lines)
            self.sequence_display.setText(new_text)

            cursor = self.sequence_display.textCursor()
            cursor.movePosition(QTextCursor.MoveOperation.Start)
            for _ in range(last_non_empty_line_index + 1):
                cursor.movePosition(QTextCursor.MoveOperation.Down)
            cursor.movePosition(QTextCursor.MoveOperation.EndOfLine)
            self.sequence_display.setTextCursor(cursor)
            self.sequence_display.ensureCursorVisible()


            logging.debug(f"Parameter '{param_str}' appended to sequence line {last_non_empty_line_index}.")
            if self.status_bar:
                 self.status_bar.showMessage(f"参数 '{param_str}' 已添加到序列末尾行。", 3000)
        else:
            self.sequence_display.setText(param_str + '\n')
            logging.debug(f"Sequence was empty or whitespace, added parameter '{param_str}' as new line.")
            if self.status_bar:
                self.status_bar.showMessage(f"序列为空，参数 '{param_str}' 已添加。", 3000)

        if param_str == "--hard":
             self._show_warning("警告: --hard 参数",
                                 "'--hard' 参数已添加到序列末尾行。\n\n"
                                 "此参数通常用于 'git reset'，它会丢弃工作区和暂存区的所有未提交更改，且不可撤销！\n\n"
                                 "请确保您理解其风险，并已将其附加到正确的命令后。")
        elif param_str == "-f" or param_str == "--force":
             self._show_warning("警告: -f / --force 参数",
                                 "强制参数 ('-f' 或 '--force') 已添加到序列末尾行。\n\n"
                                 "此参数会强制执行某些操作，可能覆盖远程分支或本地未合并的分支。\n\n"
                                 "请确保您理解其风险，并已将其附加到正确的命令后。")

    def _add_files_to_sequence(self):
        if not self._check_repo_and_warn(): return
        files_str, ok = QInputDialog.getText(self, "暂存文件", "输入要暂存的文件或目录 (用空格分隔，可用引号):\n(通常是相对于仓库根目录的路径)", QLineEdit.EchoMode.Normal)
        if ok and files_str:
            try:
                file_list = shlex.split(files_str.strip())
                if file_list:
                    commands = [f"git add -- {shlex.quote(file_path)}" for file_path in file_list]
                    for cmd in commands: self._add_command_to_sequence(cmd)
                else:
                    self._show_information("无操作", "未输入有效的文件名。")
            except ValueError as e:
                self._show_warning("输入错误", f"无法解析文件列表: {e}")
                logging.warning(f"无法解析暂存文件输入 '{files_str}': {e}")
        elif ok:
            self._show_information("无操作", "未输入文件名。")


    def _add_commit_to_sequence(self):
        if not self._check_repo_and_warn(): return
        commit_msg, ok = QInputDialog.getText(self, "提交暂存的更改", "输入提交信息:", QLineEdit.EchoMode.Normal)
        if ok and commit_msg.strip():
            self._add_command_to_sequence(f"git commit -m {shlex.quote(commit_msg.strip())}")
        elif ok:
             self._show_warning("提交中止", "提交信息不能为空。")


    def _add_commit_am_to_sequence(self):
        if not self._check_repo_and_warn(): return
        commit_msg, ok = QInputDialog.getText(self, "暂存所有已跟踪文件并提交", "输入提交信息 (-am):", QLineEdit.EchoMode.Normal)
        if ok and commit_msg.strip():
            self._add_command_to_sequence(f"git commit -am {shlex.quote(commit_msg.strip())}")
        elif ok:
             self._show_warning("提交中止", "提交信息不能为空。")

    def _add_merge_to_sequence(self):
        if not self._check_repo_and_warn(): return
        merge_target, ok = QInputDialog.getText(self, "合并分支/提交", "输入要合并的分支名、标签或提交哈希:", QLineEdit.EchoMode.Normal)
        if ok and merge_target.strip():
            clean_target = merge_target.strip()
            self._add_command_to_sequence(f"git merge {shlex.quote(clean_target)}")
        elif ok:
            self._show_warning("操作取消", "合并目标不能为空。")

    def _add_checkout_to_sequence(self):
        if not self._check_repo_and_warn(): return
        checkout_target, ok = QInputDialog.getText(self, "切换分支/提交/文件",
                                                   "输入目标:\n"
                                                   "- 分支名: main\n"
                                                   "- 标签: v1.0\n"
                                                   "- 提交哈希: a1b2c3d, HEAD~2\n"
                                                   "- 文件 (恢复工作区): -- path/to/file.txt\n"
                                                   "- 新分支: -b new-feature-branch",
                                                   QLineEdit.EchoMode.Normal)
        if ok and checkout_target.strip():
            clean_target = checkout_target.strip()
            if clean_target.startswith("-- "):
                 parts = clean_target.split(" ", 1)
                 if len(parts) > 1 and parts[1].strip():
                      quoted_path = shlex.quote(parts[1].strip())
                      self._add_command_to_sequence(f"git checkout -- {quoted_path}")
                 else:
                      self._show_warning("输入错误", "无效的文件路径格式。应为 '-- <path>'")
            elif clean_target.startswith("-b "):
                 parts = clean_target.split(" ", 1)
                 if len(parts) > 1 and parts[1].strip():
                     new_branch_name = parts[1].strip()
                     if re.search(r'[\s\~\^\:\?\*\[\\@\{]|\.\.|\.$|/$|@\{|\\\\', new_branch_name):
                         self._show_warning("创建失败", "新分支名称包含无效字符。")
                     else:
                         self._add_command_to_sequence(f"git checkout -b {shlex.quote(new_branch_name)}")
                 else:
                      self._show_warning("输入错误", "无效的新分支格式。应为 '-b <branch-name>'")
            else:
                self._add_command_to_sequence(f"git checkout {shlex.quote(clean_target)}")
        elif ok:
            self._show_information("操作取消", "检出目标不能为空。")

    def _add_reset_to_sequence(self):
        if not self._check_repo_and_warn(): return
        reset_target, ok = QInputDialog.getText(self, "重置 (Reset)",
                                                "输入重置模式和目标/文件:\n"
                                                "- 恢复暂存区: -- path/to/file.txt\n"
                                                "- 回退提交 (保留工作区和暂存区): --soft HEAD~\n"
                                                "- 回退提交 (保留工作区): --mixed HEAD~ (默认)\n"
                                                "- 回退提交 (丢弃所有更改): --hard HEAD~ (危险!)",
                                                QLineEdit.EchoMode.Normal)
        if ok and reset_target.strip():
            clean_target = reset_target.strip()

            if "--hard" in clean_target:
                 reply = QMessageBox.warning(self, "⚠️ 危险操作: git reset --hard",
                                              f"命令 '{clean_target}' 包含 '--hard'。\n\n"
                                              "'git reset --hard' 将丢弃工作区和暂存区的所有未提交更改！\n\n"
                                              "此操作不可撤销！\n\n"
                                              "确定要添加此命令到序列吗？",
                                              QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
                                              QMessageBox.StandardButton.Cancel)
                 if reply != QMessageBox.StandardButton.Yes:
                      self._show_information("操作取消", "已取消添加 reset --hard 命令。")
                      return

            self._add_command_to_sequence(f"git reset {clean_target}")
        elif ok:
            self._show_information("操作取消", "重置目标不能为空。")

    def _add_revert_to_sequence(self):
        if not self._check_repo_and_warn(): return
        commit_hash, ok = QInputDialog.getText(self, "撤销提交 (Revert)", "输入要撤销的提交哈希 (将创建一个新的反向提交):", QLineEdit.EchoMode.Normal)
        if ok and commit_hash.strip():
            clean_hash = commit_hash.strip()
            if not re.match(r'^[a-fA-F0-9]+$', clean_hash):
                 reply = QMessageBox.question(self, "格式警告", f"'{clean_hash}' 看起来不像一个标准的提交哈希。确定要继续吗？", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel, QMessageBox.StandardButton.Cancel)
                 if reply != QMessageBox.StandardButton.Yes:
                      self._show_information("操作取消", "已取消 revert 操作。")
                      return

            self._add_command_to_sequence(f"git revert {shlex.quote(clean_hash)}")
        elif ok:
            self._show_information("操作取消", "提交哈希不能为空。")

    def _add_rebase_to_sequence(self):
        if not self._check_repo_and_warn(): return
        rebase_target, ok = QInputDialog.getText(self, "变基 (Rebase)", "输入变基目标 (例如: main, HEAD~3, origin/feature):", QLineEdit.EchoMode.Normal)
        if ok and rebase_target.strip():
            clean_target = rebase_target.strip()

            confirmation_msg = (f"将要把当前分支变基到 '{clean_target}'。\n\n"
                                f"将添加命令: git rebase {shlex.quote(clean_target)}\n\n"
                                "变基会重写提交历史，通常不应用于已共享的分支。\n"
                                "如果遇到冲突，您需要手动解决。\n\n"
                                "确定要添加此命令到序列吗？")
            reply = QMessageBox.warning(self, "⚠️ 确认变基", confirmation_msg,
                                        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
                                        QMessageBox.StandardButton.Cancel)

            if reply == QMessageBox.StandardButton.Yes:
                logging.info(f"添加到序列的变基命令: git rebase {clean_target}")
                self._add_command_to_sequence(f"git rebase {shlex.quote(clean_target)}")
            else:
                 self._show_information("操作取消", "变基命令未添加到序列。")

        elif ok:
            self._show_information("操作取消", "变基目标不能为空。")


    def _add_stash_save_to_sequence(self):
        if not self._check_repo_and_warn(): return
        stash_message, ok = QInputDialog.getText(self, "保存工作区 (Stash Save)", "输入 Stash 消息 (可选，留空则使用默认消息):", QLineEdit.EchoMode.Normal)
        if ok:
            if stash_message.strip():
                self._add_command_to_sequence(f"git stash save {shlex.quote(stash_message.strip())}")
            else:
                self._add_command_to_sequence("git stash save")

    def _add_tag_to_sequence(self):
        if not self._check_repo_and_warn(): return
        tag_name, ok = QInputDialog.getText(self, "创建标签 (Tag)", "输入标签名称 (例如 v1.0, release-candidate):", QLineEdit.EchoMode.Normal)
        if ok and tag_name.strip():
            clean_name = tag_name.strip()
            if re.search(r'[\s]', clean_name):
                self._show_warning("操作取消", "标签名称不能包含空格。")
                return

            message_reply = QMessageBox.question(self, "标签类型", "是否创建带注释的标签 (-a)?\n(推荐用于发布标签)",
                                                 QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No | QMessageBox.StandardButton.Cancel,
                                                 QMessageBox.StandardButton.Yes)

            if message_reply == QMessageBox.StandardButton.Cancel:
                self._show_information("操作取消", "已取消创建标签。")
                return

            command_parts = ["git", "tag"]
            if message_reply == QMessageBox.StandardButton.Yes:
                 tag_message, msg_ok = QInputDialog.getText(self, "标签注释", "输入标签的注释消息 (-m):", QLineEdit.EchoMode.Normal)
                 if msg_ok and tag_message.strip():
                      command_parts.append("-a")
                      command_parts.append(clean_name)
                      command_parts.append("-m")
                      command_parts.append(tag_message.strip())
                 elif msg_ok:
                      self._show_warning("注释为空", "将创建带注释标签，但注释消息为空。")
                      command_parts.append("-a")
                      command_parts.append(clean_name)
                      command_parts.append("-m")
                      command_parts.append("")
                 else:
                      self._show_information("操作取消", "已取消创建带注释标签。")
                      return
            else:
                command_parts.append(clean_name)

            self._add_command_to_sequence(command_parts)

        elif ok:
            self._show_information("操作取消", "标签名称不能为空。")

    def _add_restore_to_sequence(self):
        if not self._check_repo_and_warn(): return

        dialog_title = "恢复文件 (Restore)"
        dialog_prompt = "输入要恢复的文件路径或目录 (用空格分隔):\n(恢复工作区或暂存区的文件到特定状态)"
        files_str, ok = QInputDialog.getText(self, dialog_title, dialog_prompt, QLineEdit.EchoMode.Normal)

        if ok and files_str.strip():
            try:
                file_list = shlex.split(files_str.strip())
                if file_list:
                     source_options = ["工作区 (来自暂存区/HEAD)", "暂存区 (来自HEAD)", "特定提交..."]
                     restore_source_text, source_ok = QInputDialog.getItem(self, "选择恢复来源/目标",
                                                                            "选择操作类型:",
                                                                            source_options, 0, False)

                     if not source_ok:
                          self._show_information("操作取消", "文件恢复已取消。")
                          return

                     commands = []
                     commit_source = None

                     if restore_source_text == "特定提交...":
                         commit_ref, commit_ok = QInputDialog.getText(self, "指定提交", "输入要从中恢复的提交、分支或标签 (例如 HEAD~, main, v1.0):")
                         if commit_ok and commit_ref.strip():
                             commit_source = commit_ref.strip()
                         elif commit_ok:
                             self._show_warning("操作取消", "提交引用不能为空。")
                             return
                         else:
                             self._show_information("操作取消", "文件恢复已取消。")
                             return

                     for file_path in file_list:
                          command_parts = ["git", "restore"]
                          if commit_source:
                              command_parts.extend(["--source", commit_source])

                          if restore_source_text == "暂存区 (来自HEAD)":
                               command_parts.append("--staged")

                          command_parts.append("--")
                          command_parts.append(file_path)
                          commands.append(command_parts)

                     for cmd_parts in commands: self._add_command_to_sequence(cmd_parts)

                else:
                    self._show_information("无操作", "未输入有效的文件名。")
            except ValueError as e:
                self._show_warning("输入错误", f"无法解析文件列表: {e}")
                logging.warning(f"无法解析 restore file input '{files_str}': {e}")
        elif ok:
            self._show_information("无操作", "未输入文件名。")


    def _clear_sequence(self):
        if self.sequence_display: self.sequence_display.clear()
        if self.status_bar: self.status_bar.showMessage("命令序列已清空", 2000)
        logging.info("命令序列已清空。")

    def _execute_sequence(self):
        if not self.sequence_display: return
        commands_to_execute = [line.strip() for line in self.sequence_display.toPlainText().splitlines() if line.strip()]
        if not commands_to_execute:
            self._show_information("提示", "命令序列为空或只包含空行，无需执行。")
            return
        is_init_shortcut = commands_to_execute and commands_to_execute[0].lower().startswith("git init")
        if not is_init_shortcut and not self._check_repo_and_warn("无法执行序列，仓库无效。"): return
        self._run_command_list_sequentially(commands_to_execute)

    def _save_sequence_as_shortcut(self):
         if not self.sequence_display: return
         sequence_text = self.sequence_display.toPlainText()
         if not sequence_text.strip():
             self._show_information("无法保存", "命令序列为空，无法保存为快捷键。")
             return
         self.shortcut_manager.save_shortcut_dialog(current_sequence=sequence_text)


    def _set_ui_busy(self, busy: bool):
        is_valid_repo = self.git_handler.is_valid_repo() if self.git_handler else False
        enable_state = not busy and is_valid_repo

        for widget in self._repo_dependent_widgets:
            if widget:
                if isinstance(widget, QAction):
                     is_always_enabled = widget.text() in ["选择仓库(&O)...", "Git 全局配置(&G)...", "退出(&X)", "关于(&A)", "清空原始输出"]
                     if not is_always_enabled:
                          widget.setEnabled(enable_state)
                else:
                    widget.setEnabled(enable_state)

        init_button = self.findChild(QPushButton, "Init", Qt.FindChildOption.FindChildrenRecursively)
        if init_button:
            init_button.setEnabled(not busy)
        else:
             logging.warning("Could not find the Init button during busy state update.")

        for action in self.findChildren(QAction):
            action_text = action.text()
            if action_text in ["选择仓库(&O)...", "Git 全局配置(&G)...", "退出(&X)", "关于(&A)", "清空原始输出"]:
                action.setEnabled(True)

        if busy:
            if self.status_bar: self.status_bar.showMessage("⏳ 正在执行...", 0)
            QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        else:
            QApplication.restoreOverrideCursor()


    @pyqtSlot()
    def _execute_command_from_input(self):
        if not self.command_input: return
        command_text = self.command_input.text().strip();
        if not command_text: return
        logging.info(f"用户从命令行输入: {command_text}"); prompt_color = QColor(Qt.GlobalColor.darkCyan)

        is_git_command = command_text.lower().startswith("git ")
        is_init_command = command_text.lower().startswith("git init")

        if not is_git_command:
             self._show_warning("操作无效", "此输入框仅用于执行 Git 命令。")
             self._append_output(f"❌ 非 Git 命令: {command_text}", QColor("red"))
             return
        if not is_init_command and not self.git_handler.is_valid_repo():
             self._show_warning("操作无效", "仓库无效，只能执行 'git init' 命令。");
             self._append_output(f"❌ 仓库无效: {command_text}", QColor("red"))
             return

        try:
            command_parts = shlex.split(command_text)
        except ValueError as e:
             self._show_warning("输入错误", f"无法解析命令: {e}");
             self._append_output(f"❌ 解析命令失败: {command_text}\n{e}", QColor("red"))
             return

        if not command_parts: return

        display_cmd = ' '.join(shlex.quote(part) for part in command_parts)
        self._append_output(f"\n$ {display_cmd}", prompt_color)
        self.command_input.clear()

        self._run_command_list_sequentially([command_text], refresh_on_success=True)

    def _load_shortcut_into_builder(self, item: QListWidgetItem = None):
        if not self.shortcut_list_widget: return
        if not item:
            item = self.shortcut_list_widget.currentItem()
            if not item: return

        shortcut_data = item.data(Qt.ItemDataRole.UserRole)
        if shortcut_data and isinstance(shortcut_data, dict) and shortcut_data.get('sequence'):
            name = shortcut_data.get('name', '未知')
            sequence_str = shortcut_data['sequence']
            if self.sequence_display:
                self.sequence_display.setText(sequence_str.strip())
            if self.status_bar: self.status_bar.showMessage(f"快捷键 '{name}' 已加载到序列构建器", 3000)
            logging.info(f"快捷键 '{name}' 已加载到构建器。")
        else:
             logging.warning("双击了列表项，但未获取到快捷键数据或序列。")


    def _execute_sequence_from_string(self, name: str, sequence_str: str):
        if self.status_bar: self.status_bar.showMessage(f"正在执行快捷键: {name}", 3000)
        commands = [line.strip() for line in sequence_str.strip().splitlines() if line.strip()]
        if not commands:
             self._show_warning("快捷键无效", f"快捷键 '{name}' 解析后命令序列为空。")
             logging.warning(f"快捷键 '{name}' 导致命令列表为空。")
             return
        is_init_shortcut = commands and commands[0].lower().startswith("git init")
        if not is_init_shortcut and not self._check_repo_and_warn(f"无法执行快捷键 '{name}'，仓库无效。"):
             return
        if self.sequence_display: self.sequence_display.setText(sequence_str.strip())
        logging.info(f"准备执行快捷键 '{name}' 的命令列表: {commands}")
        self._run_command_list_sequentially(commands)


    @pyqtSlot()
    def _stage_all(self):
        if not self._check_repo_and_warn(): return
        if self.status_tree_model and \
           self.status_tree_model.unstage_root.rowCount() == 0 and \
           self.status_tree_model.untracked_root.rowCount() == 0 and \
           (not hasattr(self.status_tree_model, 'unmerged_root') or self.status_tree_model.unmerged_root.rowCount() == 0):
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
        command_parts = ['git', 'add', '--'] + files
        self._run_command_list_sequentially([ ' '.join(shlex.quote(p) for p in command_parts) ])


    def _unstage_files(self, files: list[str]):
        if not self._check_repo_and_warn() or not files: return
        logging.info(f"请求撤销暂存特定文件: {files}")
        command_parts = ['git', 'reset', 'HEAD', '--'] + files
        self._run_command_list_sequentially([ ' '.join(shlex.quote(p) for p in command_parts) ])


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

        files_to_stage = selected_files_data.get(STATUS_UNSTAGED, []) + selected_files_data.get(STATUS_UNTRACKED, []) + selected_files_data.get(STATUS_UNMERGED, [])
        if files_to_stage:
            stage_action = QAction(f"暂存 {len(files_to_stage)} 项 (+)", self)
            stage_action.triggered.connect(lambda checked=False, files=files_to_stage: self._stage_files(files))
            menu.addAction(stage_action)
            added_action = True

        files_to_unstage = selected_files_data.get(STATUS_STAGED, [])
        if files_to_unstage:
            unstage_action = QAction(f"撤销暂存 {len(files_to_unstage)} 项 (-)", self)
            unstage_action.triggered.connect(lambda checked=False, files=files_to_unstage: self._unstage_files(files))
            menu.addAction(unstage_action)
            added_action = True

        files_to_discard_unstaged = selected_files_data.get(STATUS_UNSTAGED, []) + selected_files_data.get(STATUS_UNTRACKED, [])
        if files_to_discard_unstaged:
             if added_action: menu.addSeparator()
             discard_action = QAction(f"丢弃 {len(files_to_discard_unstaged)} 项更改/文件...", self)
             discard_action.triggered.connect(lambda checked=False, files=files_to_discard_unstaged: self._discard_changes_dialog(files))
             menu.addAction(discard_action)
             added_action = True

        if len(unique_selected_rows) == 1:
            first_row_index = list(unique_selected_rows)[0]
            path_index = self.status_tree_model.index(first_row_index.row(), STATUS_COL_PATH, first_row_index.parent())
            file_path = self.status_tree_model.data(path_index, Qt.ItemDataRole.UserRole + 1)
            if file_path and self.git_handler.get_repo_path():
                full_path = os.path.join(self.git_handler.get_repo_path(), file_path)
                if os.path.exists(full_path):
                    if added_action: menu.addSeparator()
                    open_action = QAction("用默认程序打开", self)
                    open_action.triggered.connect(lambda checked=False, fp=full_path: QDesktopServices.openUrl(QUrl.fromLocalFile(fp)))
                    menu.addAction(open_action)
                    added_action = True

                    open_folder_action = QAction("打开所在文件夹", self)
                    open_folder_action.triggered.connect(lambda checked=False, fp=full_path: QDesktopServices.openUrl(QUrl.fromLocalFile(os.path.dirname(fp))))
                    menu.addAction(open_folder_action)
                    added_action = True


        if added_action: menu.exec(self.status_tree_view.viewport().mapToGlobal(pos))
        else: logging.debug("No applicable actions for selected status items.")

    def _discard_changes_dialog(self, files: list[str]):
        if not self._check_repo_and_warn() or not files: return

        untracked_files = []
        modified_files = []
        repo_root = self.git_handler.get_repo_path()
        if not repo_root: return

        for f in files:
            full_path = os.path.join(repo_root, f)
            ls_files_cmd = ["git", "ls-files", "--error-unmatch", "--", f]
            result = self.git_handler.execute_command_sync(ls_files_cmd)
            if result.returncode != 0:
                untracked_files.append(f)
            else:
                modified_files.append(f)

        message = "确定要执行以下操作吗？\n\n"
        commands_to_run = []
        if modified_files:
             message += f"丢弃 {len(modified_files)} 个已跟踪文件的未暂存更改:\n" + "\n".join([f" - {f}" for f in modified_files]) + "\n"
             commands_to_run.extend([f"git checkout -- {shlex.quote(f)}" for f in modified_files])
        if untracked_files:
             message += f"删除 {len(untracked_files)} 个未跟踪的文件/目录:\n" + "\n".join([f" - {f}" for f in untracked_files]) + "\n"
             commands_to_run.extend([f"git clean -fd -- {shlex.quote(f)}" for f in untracked_files])

        message += "\n此操作不可撤销！"

        if not commands_to_run:
             self._show_information("无操作", "没有可丢弃的已跟踪文件更改或可删除的未跟踪文件。")
             return

        reply = QMessageBox.warning(self, "⚠️ 确认丢弃更改/删除文件", message,
                                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
                                    QMessageBox.StandardButton.Cancel)

        if reply == QMessageBox.StandardButton.Yes:
            logging.info(f"请求丢弃/清理文件: {files}")
            self._run_command_list_sequentially(commands_to_run)

    def _resolve_files(self, files: list[str]):
        if not self._check_repo_and_warn() or not files: return
        logging.info(f"请求标记为已解决 (git add): {files}")
        command_parts = ['git', 'add', '--'] + files
        self._run_command_list_sequentially([ ' '.join(shlex.quote(p) for p in command_parts) ])


    @pyqtSlot(QItemSelection, QItemSelection)
    def _status_selection_changed(self, selected: QItemSelection, deselected: QItemSelection):
        if not self.status_tree_view or not self.status_tree_model or not self.diff_text_edit:
             return
        # FIX: Remove duplicate keyword argument 'message'
        if not self._check_repo_and_warn("仓库无效，无法显示差异。"):
             if self.diff_text_edit:
                 self.diff_text_edit.clear();
                 self.diff_text_edit.setPlaceholderText("仓库无效。")
             return

        self.diff_text_edit.clear()
        selected_indexes = self.status_tree_view.selectionModel().selectedIndexes()

        if not selected_indexes:
            self.diff_text_edit.setPlaceholderText("选中文件以查看差异...");
            return

        unique_selected_rows = set(self.status_tree_model.index(idx.row(), STATUS_COL_STATUS, idx.parent()) for idx in selected_indexes if idx.isValid() and idx.parent().isValid())

        if len(unique_selected_rows) != 1:
            self.diff_text_edit.setPlaceholderText("请选择单个文件以查看差异...");
            return

        first_row_index = list(unique_selected_rows)[0]
        path_item_index = self.status_tree_model.index(first_row_index.row(), STATUS_COL_PATH, first_row_index.parent())
        status_item_index = self.status_tree_model.index(first_row_index.row(), STATUS_COL_STATUS, first_row_index.parent())

        file_path = self.status_tree_model.data(path_item_index, Qt.ItemDataRole.UserRole + 1)
        status_code = self.status_tree_model.data(status_item_index, Qt.ItemDataRole.UserRole)

        parent_item = self.status_tree_model.itemFromIndex(first_row_index.parent())
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
            self.diff_text_edit.setText(f"'{file_path}' 是未跟踪的文件。\n\n无法与仓库比较差异。")
            self.diff_text_edit.setPlaceholderText("")
        elif section_type == STATUS_UNMERGED:
             self.diff_text_edit.setPlaceholderText(f"正在加载合并冲突 '{os.path.basename(file_path)}'...");
             QApplication.processEvents()
             self.git_handler.execute_command_async(['git', 'diff', '--', file_path], self._on_diff_received)
        elif self.git_handler:
            staged_diff = (section_type == STATUS_STAGED)
            self.diff_text_edit.setPlaceholderText(f"正在加载 '{os.path.basename(file_path)}' 的{'暂存区' if staged_diff else '工作区'}差异...");
            QApplication.processEvents()
            self.git_handler.get_diff_async(file_path, staged=staged_diff, finished_slot=self._on_diff_received)
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
                self.diff_text_edit.setText("(无差异)")
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
        header_format = QTextCharFormat(default_format); header_format.setForeground(QColor("gray")); header_format.setFontItalic(True)
        commit_info_format = QTextCharFormat(default_format); commit_info_format.setForeground(QColor(Qt.GlobalColor.darkBlue))
        conflict_marker_format = QTextCharFormat(default_format); conflict_marker_format.setForeground(QColor("orange")); conflict_marker_format.setFontWeight(QFont.Weight.Bold)

        self.diff_text_edit.setFontFamily("Courier New")

        lines = diff_text.splitlines()
        for line in lines:
            fmt_to_apply = default_format

            if line.startswith('commit ') or line.startswith('Author:') or line.startswith('Date:'):
                fmt_to_apply = commit_info_format
            elif line.startswith('diff ') or line.startswith('index ') or line.startswith('---') or line.startswith('+++'):
                fmt_to_apply = header_format
            elif line.startswith('@@ '):
                 hunk_header_format = QTextCharFormat(header_format)
                 fmt_to_apply = hunk_header_format
            elif line.startswith('+'):
                fmt_to_apply = add_format
            elif line.startswith('-'):
                fmt_to_apply = del_format
            elif line.startswith('<<<<<<< ') or line.startswith('=======') or line.startswith('>>>>>>> '):
                 fmt_to_apply = conflict_marker_format

            cursor.insertText(line, fmt_to_apply)
            cursor.insertText("\n", default_format)

        cursor.movePosition(QTextCursor.MoveOperation.Start)
        self.diff_text_edit.setTextCursor(cursor)
        self.diff_text_edit.ensureCursorVisible()


    @pyqtSlot(QListWidgetItem)
    def _branch_double_clicked(self, item: QListWidgetItem):
        if not item or not self._check_repo_and_warn(): return
        branch_name = item.text().strip();
        if not branch_name: return

        if branch_name.startswith("remotes/"):
             self._show_information("操作无效", f"不能直接切换到远程跟踪分支 '{branch_name}'。\n请右键选择 '基于此创建并切换本地分支...'。");
             return
        if item.font().bold():
             if self.status_bar: self.status_bar.showMessage(f"已在分支 '{branch_name}'", 2000);
             return

        reply = QMessageBox.question(self, "切换分支", f"确定要切换到本地分支 '{branch_name}' 吗？\n\n未提交或未暂存的更改将会被携带。", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel, QMessageBox.StandardButton.Yes)
        if reply == QMessageBox.StandardButton.Yes:
             logging.info(f"请求切换到分支: {branch_name}")
             self._run_command_list_sequentially([f"git checkout {shlex.quote(branch_name)}"])


    @pyqtSlot()
    def _create_branch_dialog(self):
        if not self._check_repo_and_warn(): return
        branch_name, ok = QInputDialog.getText(self, "创建新分支", "输入新分支的名称:", QLineEdit.EchoMode.Normal)
        if ok and branch_name.strip():
            clean_name = branch_name.strip();
            if re.search(r'[\s\~\^\:\?\*\[\\@\{]|\.\.|\.$|/$|@\{|\\\\', clean_name) or clean_name.startswith('-') or clean_name.lower() == 'head':
                 self._show_warning("创建失败", "分支名称无效。\n\n名称不能包含空格、特殊字符 (~^:?*[\\@{)，不能以 '.' 或 '/' 结尾，不能是 'HEAD'，不能包含 '..' 或 '@{' 或 '\\\\'。")
                 return
            logging.info(f"请求创建新分支: {clean_name}");
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
        if not branch_name: return

        is_remote = branch_name.startswith("remotes/");
        is_current = item.font().bold();
        added_action = False

        if not is_current and not is_remote:
            checkout_action = QAction(f"切换到 '{branch_name}'", self)
            checkout_action.triggered.connect(lambda checked=False, b=branch_name: self._run_command_list_sequentially([f"git checkout {shlex.quote(b)}"]))
            menu.addAction(checkout_action)
            added_action = True

        if is_remote:
             remote_parts = branch_name.split('/', 2);
             if len(remote_parts) == 3:
                 local_suggest_name = remote_parts[2];
                 checkout_remote_action = QAction(f"基于此创建并切换本地分支...", self)
                 checkout_remote_action.setToolTip(f"创建基于 '{branch_name}' 的本地分支")
                 checkout_remote_action.triggered.connect(lambda checked=False, suggest=local_suggest_name, start_point=branch_name: self._create_and_checkout_branch_from_dialog(suggest, start_point))
                 menu.addAction(checkout_remote_action)
                 added_action = True

        if not is_current and not is_remote:
            if added_action: menu.addSeparator()
            delete_action = QAction(f"删除本地分支 '{branch_name}'...", self)
            delete_action.triggered.connect(lambda checked=False, b=branch_name: self._delete_branch_dialog(b))
            menu.addAction(delete_action)
            added_action = True

        if is_remote:
             remote_parts = branch_name.split('/', 2);
             if len(remote_parts) == 3:
                 remote_name = remote_parts[1];
                 remote_branch_name = remote_parts[2];
                 if added_action: menu.addSeparator()
                 delete_remote_action = QAction(f"删除远程分支 '{remote_name}/{remote_branch_name}'...", self)
                 delete_remote_action.triggered.connect(lambda checked=False, rn=remote_name, rbn=remote_branch_name: self._delete_remote_branch_dialog(rn, rbn))
                 menu.addAction(delete_remote_action)
                 added_action = True

        if added_action: menu.exec(self.branch_list_widget.mapToGlobal(pos))


    def _delete_branch_dialog(self, branch_name: str, force: bool = False):
        if not self._check_repo_and_warn() or not branch_name or branch_name.startswith("remotes/"):
             logging.error(f"无效的本地分支名称用于删除: {branch_name}");
             return

        delete_flag = "-D" if force else "-d"
        action_text = "强制删除" if force else "删除"
        warning_message = f"确定要{action_text}本地分支 '{branch_name}' 吗？"
        if not force: warning_message += "\n\n如果分支包含未合并到 HEAD 或其上游的提交，普通删除将失败。"
        else: warning_message += "\n\n强制删除会丢失该分支上未合并的提交！"
        warning_message += "\n\n此操作通常不可撤销！"

        reply = QMessageBox.warning(self, f"确认{action_text}本地分支", warning_message,
                                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
                                    QMessageBox.StandardButton.Cancel)

        if reply == QMessageBox.StandardButton.Yes:
             logging.info(f"请求{action_text}本地分支: {branch_name} (using {delete_flag})")
             self._run_command_list_sequentially([f"git branch {delete_flag} {shlex.quote(branch_name)}"])


    def _delete_remote_branch_dialog(self, remote_name: str, branch_name: str):
        if not self._check_repo_and_warn() or not remote_name or not branch_name:
             logging.error(f"无效的远程/分支名称用于删除: {remote_name}/{branch_name}");
             return
        confirmation_message = (f"确定要从远程仓库 '{remote_name}' 删除分支 '{branch_name}' 吗？\n\n"
                                f"将执行: git push {shlex.quote(remote_name)} --delete {shlex.quote(branch_name)}\n\n"
                                "此操作会影响共享仓库，请谨慎操作！")
        reply = QMessageBox.warning(self, "⚠️ 确认删除远程分支", confirmation_message,
                                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
                                    QMessageBox.StandardButton.Cancel)
        if reply == QMessageBox.StandardButton.Yes:
            logging.info(f"请求删除远程分支: {remote_name}/{branch_name}")
            self._run_command_list_sequentially([f"git push {shlex.quote(remote_name)} --delete {shlex.quote(branch_name)}"])


    def _create_and_checkout_branch_from_dialog(self, suggest_name: str, start_point: str):
         if not self._check_repo_and_warn(): return
         branch_name, ok = QInputDialog.getText(self, "创建并切换本地分支", f"输入新本地分支的名称 (将基于 '{start_point}'):", QLineEdit.EchoMode.Normal, suggest_name)
         if ok and branch_name.strip():
            clean_name = branch_name.strip();
            if re.search(r'[\s\~\^\:\?\*\[\\@\{]|\.\.|\.$|/$|@\{|\\\\', clean_name) or clean_name.startswith('-') or clean_name.lower() == 'head':
                 self._show_warning("创建失败", "新分支名称无效。")
                 return
            logging.info(f"请求创建并切换到分支: {clean_name} (基于 {start_point})");
            self._run_command_list_sequentially([f"git checkout -b {shlex.quote(clean_name)} {shlex.quote(start_point)}"])
         elif ok:
            self._show_information("操作取消", "新分支名称不能为空。")


    @pyqtSlot()
    def _log_selection_changed(self):
        if not self.log_table_widget or not self.commit_details_textedit or not self.git_handler:
             return
        # FIX: Remove duplicate keyword argument 'message'
        if not self._check_repo_and_warn("仓库无效，无法显示提交详情。"):
             if self.commit_details_textedit:
                 self.commit_details_textedit.clear()
                 self.commit_details_textedit.setPlaceholderText("仓库无效。");
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
            if not commit_hash:
                commit_hash = hash_item.text().strip()
                logging.warning(f"Commit hash item (Row: {selected_row}) missing UserRole data, using text: {commit_hash}")


            if commit_hash:
                logging.debug(f"Log selection changed, requesting details for commit: {commit_hash}")
                self.commit_details_textedit.setPlaceholderText(f"正在加载 Commit '{commit_hash[:7]}...' 的详情...");
                QApplication.processEvents()
                self.git_handler.get_commit_details_async(commit_hash, self._on_commit_details_received)
            else:
                self.commit_details_textedit.setPlaceholderText("无法获取选中提交的 Hash.");
                logging.error(f"无法从表格项获取有效 Hash (Row: {selected_row}).")
        else:
            self.commit_details_textedit.setPlaceholderText("无法确定选中的提交项.");
            logging.error(f"无法在日志表格中找到行 {selected_row} 的第 {LOG_COL_COMMIT} 列项。")


    @pyqtSlot(int, str, str)
    def _on_commit_details_received(self, return_code: int, stdout: str, stderr: str):
        if not self.commit_details_textedit:
            logging.error("Commit details text edit is None in callback!")
            return
        self.commit_details_textedit.setPlaceholderText("");

        if return_code == 0:
            if stdout.strip():
                # Use the diff display function which handles commit headers and diff parts
                self._display_formatted_diff(stdout)
            else:
                 self.commit_details_textedit.setText("(无提交详情内容)")
                 logging.warning("git show succeeded but returned empty stdout.")
        else:
            error_message = f"❌ 获取提交详情失败:\n{stderr}"
            self.commit_details_textedit.setText(error_message)
            logging.error(f"获取 Commit 详情失败: RC={return_code}, Error: {stderr}")


    def _run_switch_branch(self):
        if not self._check_repo_and_warn(): return
        branch_name, ok = QInputDialog.getText(self,"切换分支","输入要切换到的本地分支名称:",QLineEdit.EchoMode.Normal)
        if ok and branch_name.strip():
            clean_name = branch_name.strip()
            if clean_name.startswith("remotes/"):
                 self._show_warning("操作无效", "不能直接切换到远程分支，请使用右键菜单创建本地分支。")
                 return
            self._run_command_list_sequentially([f"git checkout {shlex.quote(clean_name)}"])
        elif ok: self._show_information("操作取消", "分支名称不能为空。")


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

                 if name_result and name_result.returncode == 0:
                     current_name = name_result.stdout.strip()
                 else:
                      logging.warning(f"获取全局 user.name 失败 (RC={name_result.returncode if name_result else 'N/A'}): {name_result.stderr.strip() if name_result else 'N/A'}")

                 if email_result and email_result.returncode == 0:
                      current_email = email_result.stdout.strip()
                 else:
                      logging.warning(f"获取全局 user.email 失败 (RC={email_result.returncode if email_result else 'N/A'}): {email_result.stderr.strip() if email_result else 'N/A'}")

                 dialog.name_edit.setText(current_name)
                 dialog.email_edit.setText(current_email)
            except Exception as e:
                 logging.warning(f"获取全局 Git 配置时出错: {e}")
                 self._show_warning("配置错误", f"无法获取当前的全局 Git 配置: {e}")

        if dialog.exec():
            config_data = dialog.get_data()
            commands_to_run = []

            new_name = config_data.get("user.name", "").strip()
            new_email = config_data.get("user.email", "").strip()

            if new_name and new_name != current_name:
                commands_to_run.append(f"git config --global user.name {shlex.quote(new_name)}")
            if new_email and new_email != current_email:
                 if "@" not in new_email or "." not in new_email.split("@")[-1]:
                     self._show_warning("格式无效", f"邮箱地址 '{new_email}' 看起来无效，未应用更改。")
                 else:
                     commands_to_run.append(f"git config --global user.email {shlex.quote(new_email)}")

            if commands_to_run:
                 confirmation_msg = "将执行以下全局 Git 配置命令:\n\n" + "\n".join(commands_to_run) + "\n\n确定吗？"
                 reply = QMessageBox.question(self, "应用全局配置", confirmation_msg, QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel, QMessageBox.StandardButton.Yes)
                 if reply == QMessageBox.StandardButton.Yes:
                     logging.info(f"Executing global config commands: {commands_to_run}")
                     if self.git_handler:
                         self._run_command_list_sequentially(commands_to_run, refresh_on_success=False)
                     else:
                         logging.error("GitHandler unavailable for settings.")
                         QMessageBox.critical(self, "错误", "无法执行配置命令，Git 处理程序不可用。")
                 else:
                     self._show_information("操作取消", "未应用全局配置更改。")
            else:
                 self._show_information("无更改", "未检测到有效的用户名或邮箱信息变更。")


    def _show_about_dialog(self):
        try:
             match = re.search(r'v(\d+\.\d+(\.\d+)?)', self.windowTitle())
             version = match.group(1) if match else "N/A"
        except Exception:
             version = "N/A"
        about_text = f"""
<!DOCTYPE html>
<html>
<head><title>关于 简易 Git GUI</title></head>
<body>
  <h1>简易 Git GUI</h1>
  <p><b>版本: {version}</b></p>
  <p>一个基础的图形化 Git 工具，旨在简化常用命令的操作和学习。</p>

  <h2>主要功能:</h2>
  <ul>
    <li>仓库选择与状态显示</li>
    <li>文件状态树状视图 (暂存/未暂存/未跟踪/冲突)</li>
    <li>文件差异对比 (Diff)</li>
    <li>提交历史查看 (Log) 与提交详情</li>
    <li>分支列表、创建、切换、删除 (本地与远程)</li>
    <li>常用命令按钮 (Add, Commit, Pull, Push, Fetch, ...)</li>
    <li>命令序列构建器 (可编辑) 与执行</li>
    <li>快捷键定义与执行</li>
    <li>全局 Git 用户配置</li>
  </ul>

  <h2>近期更新 ({version}):</h2>
  <ul>
      <li>修正了 `_check_repo_and_warn` 调用中的 `TypeError`。</li>
      <li>命令序列构建器现在可以手动编辑。</li>
      <li>参数按钮 (如 -f, --hard) 现在追加到序列构建器的最后一行。</li>
      <li>增加了更多常用参数按钮 (-s, -x, --quiet, --force)。</li>
      <li>修正了提交详情无法显示的问题。</li>
      <li>优化了部分 UI 交互和状态更新逻辑。</li>
  </ul>

  <hr>
  <p>作者: <a href="https://github.com/424635328">GitHub @424635328</a></p>
  <p>项目地址: <a href="https://github.com/424635328/Git-Helper">https://github.com/424635328/Git-Helper</a></p>
  <p><small>构建日期: 2025-04-23</small></p>
</body>
</html>
"""
        QMessageBox.about(self, f"关于 简易 Git GUI v{version}", about_text)

    def closeEvent(self, event):
        logging.info("应用程序关闭请求。")
        can_close = True
        try:
            if self.git_handler and hasattr(self.git_handler, 'active_operations') and self.git_handler.active_operations:
                 active_count = len(self.git_handler.active_operations)
                 if active_count > 0:
                      logging.warning(f"窗口关闭时仍有 {active_count} 个 Git 操作可能在后台运行。")
                      reply = QMessageBox.question(self, "后台操作进行中",
                                                   f"当前仍有 {active_count} 个 Git 操作在后台运行。\n"
                                                   "立即退出可能会中断这些操作。\n\n"
                                                   "确定要退出吗？",
                                                   QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                                   QMessageBox.StandardButton.No)
                      if reply == QMessageBox.StandardButton.No:
                          can_close = False
                          event.ignore()
                          return
        except Exception as e:
            logging.exception("关闭窗口时检查 Git 操作出错。")

        if can_close:
            logging.info("应用程序正在关闭。")
            event.accept()