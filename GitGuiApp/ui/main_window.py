import subprocess
import os
import sys
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
from PyQt6.QtGui import (
    QAction, QKeySequence, QColor, QTextCursor, QIcon, QFont, QStandardItemModel,
    QDesktopServices, QTextCharFormat, QMovie
)
from PyQt6.QtCore import Qt, pyqtSlot, QSize, QTimer, QModelIndex, QUrl, QPoint, QItemSelection, QSettings
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

LOADING_ANIMATION_PATH = os.path.join(os.path.dirname(__file__), "loading_spinner.gif")
SETTINGS_ORG_NAME = "MyGitApp"
SETTINGS_APP_NAME = "GitHelperGUI"
SETTINGS_LAST_REPO_KEY = "lastRepoPath"


class MainWindow(QMainWindow):
    # 主应用窗口，集成了 Git GUI 功能
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Git GUI v1.17")
        self.setGeometry(100, 100, 1200, 900)

        self.git_handler = GitHandler()
        self.db_handler = DatabaseHandler()
        self.shortcut_manager = ShortcutManager(self, self.db_handler, self.git_handler)

        self.current_command_sequence = []
        self._repo_dependent_widgets = []
        self._is_busy = False
        self._pending_refreshes = 0

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
        self.loading_label: Optional[QLabel] = None
        self.loading_movie: Optional[QMovie] = None

        self.stage_all_button: Optional[QPushButton] = None
        self.unstage_all_button: Optional[QPushButton] = None
        self.init_button: Optional[QPushButton] = None
        self.select_repo_button: Optional[QPushButton] = None

        self._init_ui()
        self.shortcut_manager.load_and_register_shortcuts()
        self._load_last_repo()

        logging.info("主窗口初始化完成。")

    # 加载上次打开的仓库路径
    def _load_last_repo(self):
        settings = QSettings(SETTINGS_ORG_NAME, SETTINGS_APP_NAME)
        last_repo_path = settings.value(SETTINGS_LAST_REPO_KEY, None)
        if last_repo_path and isinstance(last_repo_path, str) and os.path.isdir(last_repo_path):
            logging.info(f"尝试加载上次使用的仓库: {last_repo_path}")
            QTimer.singleShot(100, lambda path=last_repo_path: self._set_repository_path(path))
        else:
            logging.info("没有找到上次使用的有效仓库路径。")
            self._update_repo_status()

    # 保存当前仓库路径
    def _save_current_repo(self):
        settings = QSettings(SETTINGS_ORG_NAME, SETTINGS_APP_NAME)
        current_path = self.git_handler.get_repo_path()
        if current_path and self.git_handler.is_valid_repo():
            settings.setValue(SETTINGS_LAST_REPO_KEY, current_path)
            logging.info(f"保存当前仓库路径: {current_path}")
        else:
             if settings.contains(SETTINGS_LAST_REPO_KEY):
                  settings.remove(SETTINGS_LAST_REPO_KEY)
                  logging.info("当前仓库无效，清除上次仓库路径记录。")


    # 检查是否在有效仓库中，否则显示警告
    def _check_repo_and_warn(self, message="请先选择一个有效的 Git 仓库。"):
        if not self.git_handler or not self.git_handler.is_valid_repo():
            self._show_warning("操作无效", message)
            return False
        return True

    # 显示警告消息框
    def _show_warning(self, title: str, message: str):
        QMessageBox.warning(self, title, message)

    # 显示信息消息框
    def _show_information(self, title: str, message: str):
        QMessageBox.information(self, title, message)

    # 向输出文本框追加内容，支持颜色
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

    # 按顺序异步执行命令列表
    def _run_command_list_sequentially(self, command_strings: list[str], refresh_on_success=True):
        command_strings = [cmd.strip() for cmd in command_strings if cmd.strip()]
        if not command_strings:
             logging.debug("命令列表为空，无需执行。")
             return

        is_init_or_clone = command_strings and command_strings[0].lower().startswith(("git init", "git clone"))
        if not is_init_or_clone and not self._check_repo_and_warn("仓库无效，无法执行命令序列。"):
             return

        if self._is_busy:
             logging.warning("UI 正在忙碌，跳过新的命令序列请求。")
             self._show_information("操作繁忙", "当前正在执行其他操作，请稍后再试。")
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
                logging.debug("命令序列执行完毕。")
                self._append_output("\n✅ --- 所有命令执行完毕 ---", QColor("green"))
                self._clear_sequence()
                self._set_ui_busy(False)

                was_init = command_strings and command_strings[0].lower() == "git init"
                was_clone = command_strings and command_strings[0].lower().startswith("git clone")

                if was_init or was_clone:
                     logging.debug("Init/Clone 命令成功，更新仓库状态。")
                     self._update_repo_status()
                elif refresh_on_success:
                     logging.debug("命令序列成功，请求刷新。")
                     self._refresh_all_views()
                else:
                    logging.debug("命令序列成功，无需刷新。")
                    self._set_ui_busy(False)

                return

            cmd_str = command_strings[index].strip()

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
                QTimer.singleShot(0, lambda rc=return_code, so=stdout, se=stderr: process_finish(rc, so, se))

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
                     if self.status_bar and self._is_busy:
                          self.status_bar.showMessage(f"进度: {message}", 0)


            self.git_handler.execute_command_async(command_parts, on_command_finished, on_progress)

        execute_next(0)

    # 添加需要仓库有效时才启用的控件到列表
    def _add_repo_dependent_widget(self, widget):
        if widget:
              self._repo_dependent_widgets.append(widget)

    # 初始化 UI 布局和控件
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
        self._update_ui_enable_state(False)


    # 创建仓库路径显示和选择区域
    def _create_repo_area(self, main_layout: QVBoxLayout):
        repo_layout = QHBoxLayout()
        self.repo_label = QLabel("当前仓库: (未选择)")
        self.repo_label.setToolTip("当前操作的 Git 仓库路径")
        repo_layout.addWidget(self.repo_label, 1)

        self.select_repo_button = QPushButton("选择仓库")
        self.select_repo_button.setToolTip("选择或克隆仓库目录")
        self.select_repo_button.clicked.connect(self._select_or_clone_repo_dialog)
        repo_layout.addWidget(self.select_repo_button)

        main_layout.addLayout(repo_layout)

    # 创建左侧面板，包含命令按钮、序列构建器、分支列表、快捷键列表
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
        self.init_button = self._add_command_button(command_builder_layout_1, "Init", "添加 'git init' 到序列 (用于初始化新仓库)", lambda: self._add_command_to_sequence("git init"), is_repo_dependent=False)
        self._add_command_button(command_builder_layout_1, "Branch...", "添加 'git branch ' 到序列 (需要补充)", lambda: self._add_command_to_sequence("git branch "))
        self._add_command_button(command_builder_layout_1, "Merge...", "添加 'git merge <branch>' 到序列 (需要输入)", self._add_merge_to_sequence)
        self._add_command_button(command_builder_layout_1, "Checkout...", "添加 'git checkout <ref/path>' 到序列 (需要输入)", self._add_checkout_to_sequence)
        left_layout.addLayout(command_builder_layout_1)

        command_builder_layout_2 = QHBoxLayout()
        self._add_command_button(command_builder_layout_2, "Reset...", "添加 'git reset ' 到序列 (需要输入)", self._add_reset_to_sequence)
        self._add_command_button(command_builder_layout_2, "Revert...", "添加 'git revert <commit>' 到序列 (需要输入)", self._add_revert_to_sequence)
        self._add_command_button(command_builder_layout_2, "Rebase...", "添加 'git rebase ' 到序列 (需要输入)", self._add_rebase_to_sequence)
        self._add_command_button(command_builder_layout_2, "Stash Save...", "添加 'git stash save' 到序列 (可输入消息)", self._add_stash_save_to_sequence)
        left_layout.addLayout(command_builder_layout_2)

        command_builder_layout_3 = QHBoxLayout()
        self._add_command_button(command_builder_layout_3, "Stash Pop", "添加 'git stash pop' 到序列", lambda: self._add_command_to_sequence("git stash pop"))
        self._add_command_button(command_builder_layout_3, "Tag...", "添加 'git tag <name>' 到序列 (需要输入)", self._add_tag_to_sequence)
        self._add_command_button(command_builder_layout_3, "Remote...", "添加 'git remote ' 到序列 (需要补充)", lambda: self._add_command_to_sequence("git remote "))
        self._add_command_button(command_builder_layout_3, "Restore...", "添加 'git restore ' 到序列 (需要输入)", self._add_restore_to_sequence)
        left_layout.addLayout(command_builder_layout_3)

        left_layout.addWidget(QLabel("常用参数/选项 (追加到序列命令后，使用空格隔开):"))
        parameter_buttons_layout_1 = QHBoxLayout()
        self._add_command_button(parameter_buttons_layout_1, "-a", "添加 '-a' 参数到序列 (例如 commit -am)", lambda: self._add_parameter_to_sequence("-a"))
        self._add_command_button(parameter_buttons_layout_1, "-v", "添加 '-v' 参数到序列 (详细输出)", lambda: self._add_parameter_to_sequence("-v"))
        self._add_command_button(parameter_buttons_layout_1, "--hard", "添加 '--hard' 参数到序列 (危险! 通常用于 reset)", lambda: self._add_parameter_to_sequence("--hard"))
        self._add_command_button(parameter_buttons_layout_1, "-f", "添加 '-f' 参数到序列 (强制, 危险!)", lambda: self._add_parameter_to_sequence("-f"))
        left_layout.addLayout(parameter_buttons_layout_1)

        parameter_buttons_layout_2 = QHBoxLayout()
        self._add_command_button(parameter_buttons_layout_2, "-u", "添加 '-u' 参数到序列 (上游跟踪, 例如 push -u)", lambda: self._add_parameter_to_sequence("-u"))
        self._add_command_button(parameter_buttons_layout_2, "-d", "添加 '-d' 参数到序列 (删除, 例如 branch -d)", lambda: self._add_parameter_to_sequence("-d"))
        self._add_command_button(parameter_buttons_layout_2, "-p", "添加 '-p' 参数到序列 (补丁模式, 例如 add -p)", lambda: self._add_parameter_to_sequence("-p"))
        self._add_command_button(parameter_buttons_layout_2, "--soft", "添加 '--soft' 参数到序列 (常用于 reset)", lambda: self._add_parameter_to_sequence("--soft"))
        left_layout.addLayout(parameter_buttons_layout_2)

        parameter_buttons_layout_3 = QHBoxLayout()
        self._add_command_button(parameter_buttons_layout_3, "-s", "添加 '-s' 参数到序列 (例如 commit -s, Signed-off-by)", lambda: self._add_parameter_to_sequence("-s"))
        self._add_command_button(parameter_buttons_layout_3, "-x", "添加 '-x' 参数到序列 (例如 clean -fdx, 危险!)", lambda: self._add_parameter_to_sequence("-x"))
        self._add_command_button(parameter_buttons_layout_3, "--quiet", "添加 '--quiet' 或 '-q' 参数到序列 (静默模式)", lambda: self._add_parameter_to_sequence("--quiet"))
        left_layout.addLayout(parameter_buttons_layout_3)

        left_layout.addWidget(QLabel("命令序列构建器:"))
        self.sequence_display = QTextEdit()
        self.sequence_display.setReadOnly(False)
        self.sequence_display.setPlaceholderText("点击上方按钮构建命令序列，或从快捷键加载，可直接编辑...")
        self.sequence_display.setFixedHeight(80)
        self.sequence_display.textChanged.connect(self._sequence_text_changed)
        left_layout.addWidget(self.sequence_display)
        self._add_repo_dependent_widget(self.sequence_display)

        sequence_actions_layout = QHBoxLayout()
        execute_button = QPushButton("执行序列")
        execute_button.setToolTip("执行上方构建的命令序列")
        execute_button.setStyleSheet("background-color: darkgreen; color: white;")
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
        self.shortcut_list_widget.setToolTip("双击加载到构建器，右键删除")
        self.shortcut_list_widget.itemDoubleClicked.connect(self._load_shortcut_into_builder)
        self.shortcut_list_widget.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.shortcut_list_widget.customContextMenuRequested.connect(self.shortcut_manager.show_shortcut_context_menu)
        left_layout.addWidget(self.shortcut_list_widget, 1)
        self._add_repo_dependent_widget(self.shortcut_list_widget)

        left_layout.addStretch()


    # 创建右侧面板，包含状态、日志、差异和输出标签页
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

    # 创建状态/文件标签页
    def _create_status_tab(self):
        status_tab_widget = QWidget()
        status_tab_layout = QVBoxLayout(status_tab_widget)
        status_tab_layout.setContentsMargins(5, 5, 5, 5)
        status_tab_layout.setSpacing(4)
        self.main_tab_widget.addTab(status_tab_layout.parentWidget(), "状态 / 文件")

        status_action_layout = QHBoxLayout()
        self.stage_all_button = QPushButton("全部暂存 (+)")
        self.stage_all_button.setToolTip("暂存所有未暂存和未跟踪的文件 (git add .)")
        self.stage_all_button.clicked.connect(self._stage_all)
        self._add_repo_dependent_widget(self.stage_all_button)

        self.unstage_all_button = QPushButton("全部撤销暂存 (-)")
        self.unstage_all_button.setToolTip("撤销所有已暂存文件的暂存状态 (git reset HEAD --)")
        self.unstage_all_button.clicked.connect(self._unstage_all)
        self._add_repo_dependent_widget(self.unstage_all_button)

        refresh_status_button = QPushButton("刷新状态")
        refresh_status_button.setToolTip("重新加载当前文件状态")
        refresh_status_button.clicked.connect(self._refresh_status_view)
        self._add_repo_dependent_widget(refresh_status_button)

        status_action_layout.addWidget(self.stage_all_button)
        status_action_layout.addWidget(self.unstage_all_button)
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
        self.status_tree_view.setAlternatingRowColors(True)
        self.status_tree_view.selectionModel().selectionChanged.connect(self._status_selection_changed)
        self.status_tree_view.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.status_tree_view.customContextMenuRequested.connect(self._show_status_context_menu)
        status_tab_layout.addWidget(self.status_tree_view, 1)
        self._add_repo_dependent_widget(self.status_tree_view)


    # 创建提交历史标签页
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
        self.log_table_widget.horizontalHeader().setSectionResizeMode(LOG_COL_MESSAGE, QHeaderView.ResizeMode.Stretch)
        self.log_table_widget.horizontalHeader().setSectionResizeMode(LOG_COL_COMMIT, QHeaderView.ResizeMode.ResizeToContents)
        self.log_table_widget.horizontalHeader().setSectionResizeMode(LOG_COL_AUTHOR, QHeaderView.ResizeMode.ResizeToContents)
        self.log_table_widget.horizontalHeader().setSectionResizeMode(LOG_COL_DATE, QHeaderView.ResizeMode.ResizeToContents)
        self.log_table_widget.itemSelectionChanged.connect(self._log_selection_changed)
        self.log_table_widget.setWordWrap(False)
        self.log_table_widget.setTextElideMode(Qt.TextElideMode.ElideRight)

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

    # 创建文件差异标签页
    def _create_diff_tab(self):
        diff_tab_widget = QWidget()
        diff_tab_layout = QVBoxLayout(diff_tab_widget)
        diff_tab_layout.setContentsMargins(5, 5, 5, 5)
        self.main_tab_widget.addTab(diff_tab_layout.parentWidget(), "差异 (Diff)")

        self.diff_text_edit = QTextEdit()
        self.diff_text_edit.setReadOnly(True)
        self.diff_text_edit.setPlaceholderText("选中已更改的文件以查看差异...")
        diff_tab_layout.addWidget(self.diff_text_edit, 1)
        self._add_repo_dependent_widget(self.diff_text_edit)

    # 创建原始输出标签页
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

    # 创建命令行输入区域
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


    # 创建状态栏
    def _create_status_bar(self):
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)

        self.loading_label = QLabel(self)
        self.loading_label.setFixedSize(24, 24)
        self.loading_movie = QMovie(LOADING_ANIMATION_PATH)
        self.loading_movie.setScaledSize(QSize(24, 24))

        if not os.path.exists(LOADING_ANIMATION_PATH) or not self.loading_movie.isValid():
             logging.warning(f"动画文件未找到或无效: {LOADING_ANIMATION_PATH}. 将显示文本指示器。")
             self.loading_movie = None
             self.loading_label.setText("⏳")
             self.loading_label.setStyleSheet("QLabel { padding-left: 5px; padding-right: 5px; }")
        else:
            self.loading_label.setMovie(self.loading_movie)

        self.status_bar.addPermanentWidget(self.loading_label)
        self.loading_label.hide()

        self.status_bar.showMessage("就绪")


    # 创建菜单栏
    def _create_menu(self):
        menu_bar = self.menuBar()

        file_menu = menu_bar.addMenu("文件(&F)")
        select_repo_action = QAction("选择或克隆仓库(&O)...", self)
        select_repo_action.triggered.connect(self._select_or_clone_repo_dialog)
        file_menu.addAction(select_repo_action)

        init_repo_action = QAction("在此初始化新仓库(&I)...", self)
        init_repo_action.triggered.connect(self._init_repository_here_dialog)
        file_menu.addAction(init_repo_action)

        clone_repo_action = QAction("克隆远程仓库(&C)...", self)
        clone_repo_action.triggered.connect(self._clone_repository_dialog)
        file_menu.addAction(clone_repo_action)

        file_menu.addSeparator()

        git_config_action = QAction("Git 全局配置(&G)...", self)
        git_config_action.triggered.connect(self._open_settings_dialog)
        file_menu.addAction(git_config_action)

        file_menu.addSeparator()

        exit_action = QAction("退出(&X)", self)
        exit_action.setShortcut(QKeySequence.StandardKey.Quit)
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

        repo_menu = menu_bar.addMenu("仓库(&R)")
        refresh_action = QAction("刷新全部视图", self)
        refresh_action.setShortcut(QKeySequence(Qt.Key.Key_F5))
        refresh_action.triggered.connect(self._refresh_all_views)
        repo_menu.addAction(refresh_action)
        self._add_repo_dependent_widget(refresh_action)

        repo_menu.addSeparator()

        fetch_all_action = QAction("抓取所有远程(&A)", self)
        fetch_all_action.triggered.connect(self._fetch_all)
        repo_menu.addAction(fetch_all_action)
        self._add_repo_dependent_widget(fetch_all_action)

        fetch_prune_action = QAction("抓取并修剪远程(&P)", self)
        fetch_prune_action.setToolTip("执行 git fetch --prune")
        fetch_prune_action.triggered.connect(self._fetch_prune)
        repo_menu.addAction(fetch_prune_action)
        self._add_repo_dependent_widget(fetch_prune_action)

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

        repo_menu.addSeparator()

        stash_pop_action = QAction("应用最近 Stash (Pop)(&T)", self)
        stash_pop_action.triggered.connect(self._stash_pop)
        repo_menu.addAction(stash_pop_action)
        self._add_repo_dependent_widget(stash_pop_action)

        stash_list_action = QAction("查看 Stash 列表(&L)", self)
        stash_list_action.triggered.connect(self._stash_list)
        repo_menu.addAction(stash_list_action)
        self._add_repo_dependent_widget(stash_list_action)

        repo_menu.addSeparator()

        clean_action = QAction("清理工作区(&W)...", self)
        clean_action.setToolTip("执行 git clean -fd (危险!)")
        clean_action.triggered.connect(self._clean_working_directory_dialog)
        repo_menu.addAction(clean_action)
        self._add_repo_dependent_widget(clean_action)


        help_menu = menu_bar.addMenu("帮助(&H)")

        doc_action = QAction("查看 Git 文档(&D)", self)
        doc_action.triggered.connect(self._open_git_documentation)
        help_menu.addAction(doc_action)

        issue_action = QAction("报告问题(&I)...", self)
        issue_action.triggered.connect(self._open_issue_tracker)
        help_menu.addAction(issue_action)

        help_menu.addSeparator()

        about_action = QAction("关于(&A)", self)
        about_action.triggered.connect(self._show_about_dialog)
        help_menu.addAction(about_action)


    # 创建工具栏
    def _create_toolbar(self):
        toolbar = QToolBar("主要操作")
        toolbar.setIconSize(QSize(24, 24))
        self.addToolBar(toolbar)

        style = self.style()
        refresh_icon = style.standardIcon(QStyle.StandardPixmap.SP_BrowserReload)
        pull_icon = style.standardIcon(QStyle.StandardPixmap.SP_ArrowDown)
        push_icon = style.standardIcon(QStyle.StandardPixmap.SP_ArrowUp)
        fetch_icon = style.standardIcon(QStyle.StandardPixmap.SP_ArrowForward)
        new_branch_icon = style.standardIcon(QStyle.StandardPixmap.SP_FileDialogNewFolder)
        switch_branch_icon = style.standardIcon(QStyle.StandardPixmap.SP_FileDialogDetailedView)
        clear_icon = style.standardIcon(QStyle.StandardPixmap.SP_DialogResetButton)
        stash_icon = style.standardIcon(QStyle.StandardPixmap.SP_DriveHDIcon)


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

        fetch_action = QAction(fetch_icon, "Fetch", self)
        fetch_action.setToolTip("添加 'git fetch' 到序列")
        fetch_action.triggered.connect(lambda: self._add_command_to_sequence("git fetch"))
        toolbar.addAction(fetch_action)
        self._add_repo_dependent_widget(fetch_action)

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

        stash_pop_tb_action = QAction(stash_icon, "Stash Pop", self)
        stash_pop_tb_action.setToolTip("应用最近的 Stash (git stash pop)")
        stash_pop_tb_action.triggered.connect(self._stash_pop)
        toolbar.addAction(stash_pop_tb_action)
        self._add_repo_dependent_widget(stash_pop_tb_action)

        toolbar.addSeparator()

        clear_output_action = QAction(clear_icon, "清空原始输出", self)
        clear_output_action.setToolTip("清空'原始输出'标签页的内容")
        if self.output_display:
             clear_output_action.triggered.connect(self.output_display.clear)
        toolbar.addAction(clear_output_action)


    # 辅助方法：添加命令按钮到布局
    def _add_command_button(self, layout: QHBoxLayout, text: str, tooltip: str, slot, is_repo_dependent: bool = True):
        button = QPushButton(text)
        button.setToolTip(tooltip)
        button.clicked.connect(slot)
        layout.addWidget(button)
        if is_repo_dependent:
            self._add_repo_dependent_widget(button)
        return button

    # 更新仓库状态显示和UI启用状态
    def _update_repo_status(self):
        repo_path = self.git_handler.get_repo_path()
        is_valid = self.git_handler.is_valid_repo()

        display_path = repo_path if repo_path and len(repo_path) < 60 else (f"...{repo_path[-57:]}" if repo_path else "(未选择)")
        if self.repo_label:
            self.repo_label.setText(f"当前仓库: {display_path}")
            self.repo_label.setStyleSheet("" if is_valid else "color: red;")

        self._update_ui_enable_state(is_valid)

        if is_valid:
            if not self._is_busy:
                if self.status_bar: self.status_bar.showMessage(f"正在加载仓库: {repo_path}", 0)
                QApplication.processEvents()
                self._refresh_all_views()
            else:
                 self._update_status_bar_info()
                 logging.info(f"仓库已设置为 {repo_path}，但UI正忙，将在完成后刷新视图。")
        else:
            if self.status_bar and not self._is_busy: self.status_bar.showMessage("请选择或克隆一个有效的 Git 仓库目录", 0)
            if self.status_tree_model: self.status_tree_model.clear_status()
            if self.branch_list_widget: self.branch_list_widget.clear()
            if self.log_table_widget: self.log_table_widget.setRowCount(0)
            if self.diff_text_edit: self.diff_text_edit.clear(); self.diff_text_edit.setPlaceholderText("请选择有效仓库")
            if self.commit_details_textedit: self.commit_details_textedit.clear(); self.commit_details_textedit.setPlaceholderText("请选择有效仓库")
            self._clear_sequence()
            self.current_branch_name_display = "(无效仓库)"
            self._update_status_bar_info()
            self._set_ui_busy(False)
            logging.info("Git 仓库无效，相关 UI 已禁用。")


    # 根据仓库有效性和繁忙状态启用/禁用 UI 元素
    def _update_ui_enable_state(self, enabled: bool):
        pass


    # 更新状态栏显示的仓库和分支信息
    def _update_status_bar_info(self):
        if not self.status_bar or self._is_busy: return

        is_valid = self.git_handler.is_valid_repo()
        repo_path = self.git_handler.get_repo_path()

        repo_path_short = repo_path if repo_path else "(未选择)"
        if repo_path and len(repo_path_short) > 40:
            repo_path_short = f"...{repo_path_short[-37:]}"

        branch_display = self.current_branch_name_display if self.current_branch_name_display else ("(未知)" if is_valid else "(无效仓库)")

        status_message = f"分支: {branch_display} | 仓库: {repo_path_short}"

        self.status_bar.showMessage(status_message, 0)
        logging.debug(f"状态栏更新: {status_message}")


    # 刷新状态、分支和日志视图
    @pyqtSlot()
    def _refresh_all_views(self):
        if self._is_busy:
             logging.debug("UI 正忙，忽略刷新全部视图请求。")
             return

        if not self._check_repo_and_warn("无法刷新视图，仓库无效。"):
            return

        logging.info("正在刷新状态、分支和日志视图...")
        self._set_ui_busy(True)
        QApplication.processEvents()

        self._pending_refreshes = 3
        self._refresh_status_view()
        self._refresh_branch_list()
        self._refresh_log_view()

    # 单个刷新操作完成时调用，检查是否所有刷新都已完成并解除繁忙状态
    def _refresh_operation_finished(self):
        if self._is_busy:
            self._pending_refreshes -= 1
            logging.debug(f"Refresh operation finished. Pending: {self._pending_refreshes}")
            if self._pending_refreshes <= 0:
                logging.debug("所有刷新操作完成，释放繁忙状态。")
                self._set_ui_busy(False)
                self._pending_refreshes = 0


    # 刷新文件状态视图
    @pyqtSlot()
    def _refresh_status_view(self):
        if not self.git_handler or not self.git_handler.is_valid_repo():
             logging.warning("试图刷新状态，但 GitHandler 不可用或仓库无效。")
             if self.status_tree_model: self.status_tree_model.clear_status()
             if self.stage_all_button: self.stage_all_button.setEnabled(False)
             if self.unstage_all_button: self.unstage_all_button.setEnabled(False)
             if self.diff_text_edit: self.diff_text_edit.clear(); self.diff_text_edit.setPlaceholderText("仓库无效")
             self._refresh_operation_finished()
             return

        logging.debug("正在请求 status porcelain...")

        if self.stage_all_button: self.stage_all_button.setEnabled(False)
        if self.unstage_all_button: self.unstage_all_button.setEnabled(False)
        if self.diff_text_edit: self.diff_text_edit.clear(); self.diff_text_edit.setPlaceholderText("正在刷新状态...")

        self.git_handler.get_status_porcelain_async(self._on_status_refreshed)


    # 处理 Git 状态刷新的回调
    @pyqtSlot(int, str, str)
    def _on_status_refreshed(self, return_code: int, stdout: str, stderr: str):
        try:
            if not self.status_tree_model or not self.status_tree_view:
                 logging.error("状态树模型或视图在状态刷新回调时未初始化。")
                 return

            is_valid = self.git_handler.is_valid_repo()

            if self.status_tree_view:
                 self.status_tree_view.setUpdatesEnabled(False)

            enable_stage_all = False
            enable_unstage_all = False

            try:
                if return_code == 0 and is_valid:
                    self.status_tree_model.parse_and_populate(stdout)
                    self.status_tree_view.expandAll()
                    self.status_tree_view.resizeColumnToContents(STATUS_COL_STATUS)
                    min_status_width = self.status_tree_view.fontMetrics().horizontalAdvance("Unmerged ") + 20
                    self.status_tree_view.setColumnWidth(STATUS_COL_STATUS, max(min_status_width, self.status_tree_view.columnWidth(STATUS_COL_STATUS)))

                    has_changes_to_stage = (
                        self.status_tree_model.unstage_root.rowCount() > 0 or
                        self.status_tree_model.untracked_root.rowCount() > 0 or
                        (hasattr(self.status_tree_model, 'unmerged_root') and self.status_tree_model.unmerged_root.rowCount() > 0)
                    )
                    has_staged_changes = self.status_tree_model.staged_root.rowCount() > 0

                    enable_stage_all = has_changes_to_stage
                    enable_unstage_all = has_staged_changes

                elif is_valid:
                    logging.error(f"获取状态失败: RC={return_code}, 错误: {stderr.strip()}")
                    self._append_output(f"❌ 获取 Git 状态失败:\n{stderr.strip()}", QColor("red"))
                    self.status_tree_model.clear_status()
                else:
                     logging.warning("仓库在状态刷新期间变得无效，清空状态视图。")
                     self.status_tree_model.clear_status()

            finally:
                current_enabled_state = is_valid and not self._is_busy
                if self.stage_all_button: self.stage_all_button.setEnabled(enable_stage_all and current_enabled_state)
                if self.unstage_all_button: self.unstage_all_button.setEnabled(enable_unstage_all and current_enabled_state)

                if self.status_tree_view:
                     self.status_tree_view.setUpdatesEnabled(True)

        finally:
             self._refresh_operation_finished()


    # 刷新分支列表
    @pyqtSlot()
    def _refresh_branch_list(self):
        if not self.git_handler or not self.git_handler.is_valid_repo():
             logging.warning("试图刷新分支列表，但 GitHandler 不可用或仓库无效。")
             if self.branch_list_widget: self.branch_list_widget.clear()
             self.current_branch_name_display = "(无效仓库)" if not self.git_handler.is_valid_repo() else "(错误)"
             self._refresh_operation_finished()
             return
        logging.debug("正在请求格式化分支列表...")
        if self.branch_list_widget: self.branch_list_widget.clear()
        self.git_handler.get_branches_formatted_async(self._on_branches_refreshed)


    # 处理 Git 分支列表刷新的回调
    @pyqtSlot(int, str, str)
    def _on_branches_refreshed(self, return_code: int, stdout: str, stderr: str):
        try:
            if not self.branch_list_widget or not self.git_handler:
                 logging.warning("分支列表组件或 GitHandler 在分支刷新回调时无效 (可能在关闭窗口?)。")
                 return

            self.branch_list_widget.clear()
            current_branch_name = None
            is_valid = self.git_handler.is_valid_repo()

            if return_code == 0 and is_valid:
                lines = stdout.strip().splitlines()
                bold_font = QFont(); bold_font.setBold(True)
                remote_color = QColor("gray")
                current_color = QColor("blue")

                for line in lines:
                    if not line: continue
                    is_current = False
                    branch_name = line.strip()

                    if branch_name.startswith('* '):
                        is_current = True
                        branch_name = branch_name[2:].strip()
                        match_detached = re.match(r'\(HEAD detached(?: at)? from (.*?)\)', branch_name)
                        if match_detached:
                             current_branch_name = f"(Detached HEAD at {match_detached.group(1)})"
                        else:
                            current_branch_name = branch_name

                    if not branch_name: continue

                    item = QListWidgetItem(branch_name)
                    if is_current:
                        item.setFont(bold_font)
                        item.setForeground(current_color)
                    elif branch_name.startswith("remotes/"):
                        item.setForeground(remote_color)

                    self.branch_list_widget.addItem(item)

                if current_branch_name and not current_branch_name.startswith("(Detached HEAD"):
                     items = self.branch_list_widget.findItems(current_branch_name, Qt.MatchFlag.MatchExactly)
                     if items:
                          self.branch_list_widget.setCurrentItem(items[0])
                          self.branch_list_widget.scrollToItem(items[0], QAbstractItemView.ScrollHint.PositionAtCenter)

                self.current_branch_name_display = current_branch_name if current_branch_name else ("(无分支?)" if is_valid else "(未知分支)")


            elif is_valid:
                logging.error(f"获取分支失败: RC={return_code}, 错误: {stderr.strip()}")
                self._append_output(f"❌ 获取分支列表失败:\n{stderr.strip()}", QColor("red"))
                self.current_branch_name_display = "(未知分支)"
            elif not is_valid:
                 logging.warning("仓库在分支刷新期间变得无效，清空分支视图。")
                 if self.branch_list_widget: self.branch_list_widget.clear()
                 self.current_branch_name_display = "(无效仓库)"

        finally:
            self._refresh_operation_finished()


    # 刷新提交历史视图
    @pyqtSlot()
    def _refresh_log_view(self):
        if not self.git_handler or not self.git_handler.is_valid_repo():
             logging.warning("试图刷新日志，但 GitHandler 不可用或仓库无效。")
             if self.log_table_widget: self.log_table_widget.setRowCount(0)
             if self.commit_details_textedit: self.commit_details_textedit.clear(); self.commit_details_textedit.setPlaceholderText("仓库无效")
             self._refresh_operation_finished()
             return
        logging.debug("正在请求格式化日志...")
        if self.log_table_widget: self.log_table_widget.setRowCount(0)
        if self.commit_details_textedit: self.commit_details_textedit.clear(); self.commit_details_textedit.setPlaceholderText("正在加载提交历史...")

        log_format = "%h\t%H\t%an\t%ar\t%s"
        self.git_handler.get_log_formatted_async(
            count=200,
            format=log_format,
            extra_args=["--graph", "--decorate"],
            finished_slot=self._on_log_refreshed
        )


    # 处理 Git 日志刷新的回调
    @pyqtSlot(int, str, str)
    def _on_log_refreshed(self, return_code: int, stdout: str, stderr: str):
        try:
            if not self.log_table_widget:
                 logging.error("日志表格组件在日志刷新回调时未初始化。")
                 return

            is_valid = self.git_handler.is_valid_repo()

            if self.commit_details_textedit and self.log_table_widget.rowCount() == 0:
                self.commit_details_textedit.setPlaceholderText("选中上方提交记录以查看详情...")

            if return_code == 0 and is_valid:
                lines = stdout.strip().splitlines()
                self.log_table_widget.setUpdatesEnabled(False)
                self.log_table_widget.setRowCount(0)
                monospace_font = QFont("Courier New")
                valid_rows = 0

                log_line_regex = re.compile(r'^[\\/|*._ -]*\s*([a-fA-F0-9]+)\t([a-fA-F0-9]+)\t(.*?)\t(.*?)\t(.*)$')


                for line in lines:
                    line = line.strip()
                    if not line: continue

                    graph_match = re.match(r'^([\\/|*._ -]+\s*)', line)
                    graph_prefix = graph_match.group(1) if graph_match else ""
                    data_part = line[len(graph_prefix):]

                    match = log_line_regex.match(line)
                    if not match:
                         match = log_line_regex.match(data_part)

                    if match:
                        short_hash = match.group(1)
                        full_hash = match.group(2)
                        author = match.group(3).strip()
                        date = match.group(4).strip()
                        message_and_decorations = match.group(5).strip()

                        decoration_match = re.match(r'^(.*?)\s*(\(.*\))$', message_and_decorations)
                        if decoration_match:
                             message = decoration_match.group(1).strip()
                             decorations = decoration_match.group(2).strip()
                        else:
                             message = message_and_decorations.strip()
                             decorations = ""

                        if not short_hash or not full_hash:
                             logging.warning(f"解析到空 commit hash: {repr(line)}")
                             continue

                        self.log_table_widget.insertRow(valid_rows)
                        hash_item = QTableWidgetItem(f"{graph_prefix}{short_hash} {decorations}".strip())
                        author_item = QTableWidgetItem(author)
                        date_item = QTableWidgetItem(date)
                        message_item = QTableWidgetItem(message)

                        flags = Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled
                        hash_item.setFlags(flags); author_item.setFlags(flags); date_item.setFlags(flags); message_item.setFlags(flags)
                        hash_item.setData(Qt.ItemDataRole.UserRole, full_hash)

                        hash_item.setFont(monospace_font)

                        self.log_table_widget.setItem(valid_rows, LOG_COL_COMMIT, hash_item)
                        self.log_table_widget.setItem(valid_rows, LOG_COL_AUTHOR, author_item)
                        self.log_table_widget.setItem(valid_rows, LOG_COL_DATE, date_item)
                        self.log_table_widget.setItem(valid_rows, LOG_COL_MESSAGE, message_item)

                        valid_rows += 1
                    else:
                        if not re.match(r'^[\s\\/|*._-]+$', line):
                           logging.warning(f"无法解析日志行 (格式可能不完全匹配或缺少数据): {repr(line)}")


                self.log_table_widget.setRowCount(valid_rows)
                self.log_table_widget.setUpdatesEnabled(True)
                logging.info(f"日志表格已填充 {valid_rows} 个有效条目。")
                self.log_table_widget.resizeColumnsToContents()
                self.log_table_widget.horizontalHeader().setSectionResizeMode(LOG_COL_MESSAGE, QHeaderView.ResizeMode.Stretch)


            elif is_valid:
                logging.error(f"获取日志失败: RC={return_code}, 错误: {stderr.strip()}")
                self._append_output(f"❌ 获取提交历史失败:\n{stderr.strip()}", QColor("red"))
                if self.commit_details_textedit: self.commit_details_textedit.setPlaceholderText("获取提交历史失败")
            elif not is_valid:
                 logging.warning("仓库在日志刷新期间变得无效，清空日志视图。")
                 if self.log_table_widget: self.log_table_widget.setRowCount(0)
                 if self.commit_details_textedit: self.commit_details_textedit.clear(); self.commit_details_textedit.setPlaceholderText("仓库无效")

        finally:
            self._refresh_operation_finished()


    # 显示选择或克隆仓库对话框
    def _select_or_clone_repo_dialog(self):
        options = ["选择现有仓库目录", "克隆远程仓库"]
        choice, ok = QInputDialog.getItem(self, "选择操作", "请选择要执行的操作:", options, 0, False)

        if ok:
            if choice == "选择现有仓库目录":
                self._select_existing_repository()
            elif choice == "克隆远程仓库":
                self._clone_repository_dialog()

    # 选择现有仓库目录
    def _select_existing_repository(self):
        start_path = self.git_handler.get_repo_path()
        if not start_path or not os.path.isdir(start_path):
            start_path = os.getcwd()
            potential_git_dir = os.path.join(os.path.expanduser("~"), 'git')
            if os.path.isdir(potential_git_dir): start_path = potential_git_dir
            else:
                potential_dev_dir = os.path.join(os.path.expanduser("~"), 'dev')
                if os.path.isdir(potential_dev_dir): start_path = potential_dev_dir
                else: start_path = os.path.expanduser("~")

        dir_path = QFileDialog.getExistingDirectory(self, "选择 Git 仓库目录", start_path, QFileDialog.Option.ShowDirsOnly)
        if dir_path:
            self._set_repository_path(dir_path)

    # 初始化新仓库对话框
    def _init_repository_here_dialog(self):
        start_path = self.git_handler.get_repo_path()
        if not start_path or not os.path.isdir(start_path):
            start_path = os.getcwd()

        dir_path = QFileDialog.getExistingDirectory(self, "选择要初始化仓库的目录", start_path, QFileDialog.Option.ShowDirsOnly)
        if dir_path:
            git_dir_path = os.path.join(dir_path, ".git")
            if os.path.exists(git_dir_path) and os.path.isdir(git_dir_path):
                 reply = QMessageBox.question(self, "仓库已存在", f"目录 '{os.path.basename(dir_path)}' 似乎已经是一个 Git 仓库。\n是否仍要尝试在此目录执行 'git init'? (不推荐)",
                                             QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No)
                 if reply == QMessageBox.StandardButton.No:
                      self._show_information("操作取消", "初始化操作已取消。")
                      open_existing = QMessageBox.question(self, "打开现有仓库?", f"要打开这个现有的仓库吗?",
                                                            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.Yes)
                      if open_existing == QMessageBox.StandardButton.Yes:
                          self._set_repository_path(dir_path)
                      return
                 else:
                      logging.warning(f"在已有仓库目录 '{dir_path}' 中执行 git init。")

            self.git_handler.set_repo_path(dir_path, check_valid=False)
            self._update_repo_status()
            logging.info(f"请求初始化仓库于: {dir_path}")
            self._run_command_list_sequentially(["git init"], refresh_on_success=False)


    # 克隆远程仓库对话框
    def _clone_repository_dialog(self):
        repo_url, ok = QInputDialog.getText(self, "克隆仓库", "输入远程仓库 URL:", QLineEdit.EchoMode.Normal)
        if ok and repo_url:
            repo_url = repo_url.strip()
            if not repo_url:
                 self._show_warning("克隆失败", "仓库 URL 不能为空。")
                 return

            default_dir_name = ""
            try:
                base = os.path.basename(repo_url.rstrip('/'))
                if base.endswith('.git'): base = base[:-4]
                default_dir_name = re.sub(r'[^\w\-.]+', '', base) or "cloned_repo"
            except Exception: default_dir_name = "cloned_repo"

            start_path = self.git_handler.get_repo_path()
            if not start_path or not os.path.isdir(start_path):
                start_path = os.path.expanduser("~")

            target_dir_tuple = QFileDialog.getSaveFileName(self, "选择克隆目标目录", os.path.join(start_path, default_dir_name))

            if target_dir_tuple and target_dir_tuple[0]:
                 target_path = target_dir_tuple[0]
                 if os.path.exists(target_path):
                     if os.path.isdir(target_path) and os.listdir(target_path):
                          self._show_warning("克隆失败", f"目标目录 '{os.path.basename(target_path)}' 已存在且不为空。请选择一个空目录或新目录名。")
                          return
                     elif not os.path.isdir(target_path):
                         self._show_warning("克隆失败", f"目标路径 '{os.path.basename(target_path)}' 已存在且不是目录。请选择一个目录或新目录名。")
                         return


                 logging.info(f"请求克隆仓库 '{repo_url}' 到 '{target_path}'")

                 clone_parent_dir = os.path.dirname(target_path)
                 clone_dir_name = os.path.basename(target_path)
                 command = ["git", "clone", repo_url, clone_dir_name]

                 self.git_handler.set_repo_path(None)
                 self._update_repo_status()

                 self._append_output(f"\n$ {' '.join(shlex.quote(p) for p in command)}", QColor("darkGray"))
                 self._set_ui_busy(True)
                 try:
                      if clone_parent_dir and not os.path.exists(clone_parent_dir):
                           os.makedirs(clone_parent_dir, exist_ok=True)
                 except OSError as e:
                      logging.error(f"无法创建克隆父目录 '{clone_parent_dir}': {e}")
                      self._show_warning("克隆错误", f"无法创建目录:\n{clone_parent_dir}\n错误: {e}")
                      self._set_ui_busy(False)
                      return

                 self.git_handler.execute_command_async(
                     command,
                     on_finished_slot=lambda rc, so, se, tp=target_path: self._handle_clone_finish(rc, so, se, tp),
                     on_progress_slot=self._handle_clone_progress,
                     cwd=clone_parent_dir
                 )

        elif ok:
             self._show_warning("克隆失败", "仓库 URL 不能为空。")


    # 处理克隆操作完成的回调
    @pyqtSlot(int, str, str, str)
    def _handle_clone_finish(self, return_code, stdout, stderr, target_path):
        if stdout: self._append_output(f"stdout:\n{stdout.strip()}")
        if stderr: self._append_output(f"stderr:\n{stderr.strip()}")

        if return_code == 0:
            self._append_output(f"✅ 克隆成功: '{os.path.basename(target_path)}'", QColor("Green"))
            self._set_repository_path(target_path)
            self._show_information("克隆成功", f"仓库已成功克隆到:\n{target_path}")
        else:
            err_msg = f"❌ 克隆失败 (RC: {return_code}) '{os.path.basename(target_path)}'"
            logging.error(f"克隆失败! 返回码: {return_code}, 标准错误: {stderr.strip()}")
            self._append_output(err_msg, QColor("red"))
            self.git_handler.set_repo_path(None)
            self._update_repo_status()
            self._show_warning("克隆失败", f"克隆仓库时出错。\n查看 '原始输出' 选项卡获取详细信息。")


    # 处理克隆操作的进度消息
    @pyqtSlot(str)
    def _handle_clone_progress(self, message):
        if message and not message.strip().startswith("fatal:") and not message.strip().startswith("error:"):
             if self.status_bar and self._is_busy:
                  display_message = re.sub(r'^(Receiving objects: \d+%|\s*|remote:).*', r'接收进度: \1', message, flags=re.IGNORECASE).strip()
                  if not display_message: display_message = message.strip()
                  self.status_bar.showMessage(f"克隆进度: {display_message}", 0)


    # 设置当前操作的 Git 仓库路径并刷新 UI
    def _set_repository_path(self, dir_path: Optional[str]):
         if not self.git_handler:
             logging.error("设置仓库路径时 GitHandler 未初始化。")
             self._show_warning("内部错误", "Git 处理程序未初始化。")
             return
         try:
             if self.output_display: self.output_display.clear()
             if self.diff_text_edit: self.diff_text_edit.clear(); self.diff_text_edit.setPlaceholderText("...")
             if self.commit_details_textedit: self.commit_details_textedit.clear(); self.commit_details_textedit.setPlaceholderText("...")
             self._clear_sequence()
             if self.status_tree_model: self.status_tree_model.clear_status()
             if self.branch_list_widget: self.branch_list_widget.clear()
             if self.log_table_widget: self.log_table_widget.setRowCount(0)
             self.current_branch_name_display = None
             QApplication.processEvents()

             logging.info(f"尝试设置仓库路径为: {dir_path}")
             self.git_handler.set_repo_path(dir_path)
             self._update_repo_status()

         except ValueError as e:
             self._show_warning("设置仓库失败", str(e))
             logging.error(f"设置仓库路径失败: {e}")
             self.git_handler.set_repo_path(None)
             self._update_repo_status()

         except Exception as e:
              logging.exception("设置仓库时发生意外错误。")
              QMessageBox.critical(self, "意外错误", f"设置仓库时出错: {e}")
              self.git_handler.set_repo_path(None)
              self._update_repo_status()


    # 添加一个 Git 命令或其部分到命令序列
    def _add_command_to_sequence(self, command_to_add: Union[str, list[str]]):
        if isinstance(command_to_add, list):
            command_str = ' '.join(shlex.quote(str(p)) for p in command_to_add)
        elif isinstance(command_to_add, str):
            command_str = command_to_add.strip()
        else:
            logging.warning(f"无效的命令类型传递给 _add_command_to_sequence: {type(command_to_add)}")
            return

        if not command_str:
             logging.debug("尝试添加空命令到序列，忽略。")
             return

        self.current_command_sequence.append(command_str)
        self._update_sequence_display()
        logging.debug(f"命令添加到序列: {command_str}")

    # 添加一个参数到命令序列的最后一行
    def _add_parameter_to_sequence(self, parameter_to_add: str):
        param_str = parameter_to_add.strip()
        if not param_str:
            logging.debug("Attempted to add empty parameter, ignoring.")
            return

        if self.current_command_sequence:
             if not self.current_command_sequence[-1].endswith(f" {param_str}"):
                 self.current_command_sequence[-1] += f" {param_str}"
                 if self.status_bar and not self._is_busy:
                     self.status_bar.showMessage(f"参数 '{param_str}' 已追加到序列最后一行。", 3000)
             else:
                 logging.debug(f"参数 '{param_str}' 已存在于序列最后一行，忽略。")
        else:
            self.current_command_sequence.append(param_str)
            if self.status_bar and not self._is_busy:
                self.status_bar.showMessage(f"参数 '{param_str}' 已添加到序列新行。请手动编辑组合。", 5000)


        self._update_sequence_display()
        logging.debug(f"参数添加到序列: {param_str}")

        dangerous_params = {
            "--hard": "'--hard' 参数通常用于 'git reset'。\n\n请确认您知道此参数的用途，它可能导致工作区和暂存区的更改丢失。\n\n请确保它位于正确的命令之后。",
            "-f": "'-f' 或 '--force' 参数用于强制执行操作。\n\n请确认您知道此参数的用途，它可能覆盖远程分支或本地未合并的分支。\n\n请确保它位于正确的命令之后。",
            "--force": "'-f' 或 '--force' 参数用于强制执行操作。\n\n请确认您知道此参数的用途，它可能覆盖远程分支或本地未合并的分支。\n\n请确保它位于正确的命令之后。",
            "-x": "'-x' 参数通常用于 'git clean'，会删除忽略的文件！\n\n此操作非常危险，可能删除不应删除的文件（如编译输出、依赖项）。\n\n请万分小心使用，并确保它位于 'git clean' 命令之后。"
        }
        if param_str in dangerous_params:
             self._show_warning("警告: 危险参数", dangerous_params[param_str])


    # 当命令序列文本框内容被手动编辑时更新内部序列列表
    @pyqtSlot()
    def _sequence_text_changed(self):
        if self.sequence_display and not self.sequence_display.signalsBlocked():
            text = self.sequence_display.toPlainText()
            self.current_command_sequence = [line.strip() for line in text.splitlines() if line.strip()]

    # 通过对话框获取文件路径并添加到 'git add' 命令
    def _add_files_to_sequence(self):
        if not self._check_repo_and_warn(): return
        files_str, ok = QInputDialog.getText(self, "添加文件到暂存区", "输入要暂存的文件或目录 (用空格分隔，可用引号):\n(例如: src/main.py \"path with spaces/file.txt\" . )", QLineEdit.EchoMode.Normal)
        if ok and files_str:
            try:
                file_list = shlex.split(files_str.strip())
                if file_list:
                    command_parts = ["git", "add", "--"] + [shlex.quote(f) for f in file_list]
                    self._add_command_to_sequence(command_parts)
                else:
                    self._show_information("无操作", "未输入有效的文件或目录。")
            except ValueError as e:
                self._show_warning("输入错误", f"无法解析文件列表: {e}\n请确保引号正确配对。")
                logging.warning(f"无法解析暂存文件输入 '{files_str}': {e}")
        elif ok:
            self._show_information("无操作", "未输入文件或目录。")


    # 通过对话框获取提交信息并添加到 'git commit -m' 命令
    def _add_commit_to_sequence(self):
        if not self._check_repo_and_warn(): return
        has_staged = False
        if self.status_tree_model:
             has_staged = self.status_tree_model.staged_root.rowCount() > 0

        commit_msg, ok = QInputDialog.getMultiLineText(self, "提交暂存的更改", "输入提交信息 (第一行为主题):", "")
        if ok and commit_msg.strip():
            self._add_command_to_sequence(f"git commit -m {shlex.quote(commit_msg.strip())}")
        elif ok and not commit_msg.strip():
             self._show_warning("提交中止", "提交信息不能为空。")


    # 通过对话框获取提交信息并添加到 'git commit -am' 命令
    def _add_commit_am_to_sequence(self):
        if not self._check_repo_and_warn(): return
        has_tracked_changes = False
        if self.status_tree_model:
             has_tracked_changes = (self.status_tree_model.staged_root.rowCount() > 0 or
                                    self.status_tree_model.unstage_root.rowCount() > 0 or
                                    self.status_tree_model.unmerged_root.rowCount() > 0)

        if not has_tracked_changes:
             self._show_warning("无法提交", "没有检测到已跟踪文件的更改（已暂存、未暂存或未合并）。\n'commit -am' 不会提交未跟踪的文件。")
             return

        commit_msg, ok = QInputDialog.getMultiLineText(self, "暂存所有已跟踪文件并提交", "输入提交信息 (第一行为主题):", "")
        if ok and commit_msg.strip():
            self._add_command_to_sequence(f"git commit -am {shlex.quote(commit_msg.strip())}")
        elif ok and not commit_msg.strip():
            self._show_warning("提交中止", "提交信息不能为空。")

    # 通过对话框选择或输入分支/提交添加到 'git merge' 命令
    def _add_merge_to_sequence(self):
        if not self._check_repo_and_warn(): return
        branches = []
        if self.branch_list_widget:
            for i in range(self.branch_list_widget.count()):
                item = self.branch_list_widget.item(i)
                branch_name = item.text().strip()
                if not branch_name.startswith("remotes/") and not branch_name.startswith("("):
                    branch_name = branch_name.lstrip('* ').strip()
                    if branch_name:
                         branches.append(branch_name)

        current_branch = self.current_branch_name_display if self.current_branch_name_display and not self.current_branch_name_display.startswith('(') else ""
        suggested_branches = sorted([b for b in branches if b != current_branch])


        merge_target, ok = QInputDialog.getItem(self, "合并分支/提交", "选择或输入要合并的分支名、标签或提交哈希:", suggested_branches, 0, True)

        if ok and merge_target:
            clean_target = merge_target.strip()
            if not clean_target:
                 self._show_warning("操作取消", "合并目标不能为空。")
                 return
            self._add_command_to_sequence(f"git merge {shlex.quote(clean_target)}")
        elif ok and not merge_target:
            self._show_information("无操作", "合并目标不能为空。")


    # 通过对话框选择或输入引用/路径添加到 'git checkout' 或 'git restore' 命令
    def _add_checkout_to_sequence(self):
        if not self._check_repo_and_warn(): return
        refs = set(["HEAD", "HEAD~1"])

        if self.branch_list_widget:
            for i in range(self.branch_list_widget.count()):
                 item = self.branch_list_widget.item(i)
                 branch_name = item.text().strip()
                 if not branch_name.startswith("("):
                    branch_name = branch_name.lstrip('* ').strip()
                    if branch_name:
                         refs.add(branch_name)

        if self.log_table_widget:
            for r in range(min(20, self.log_table_widget.rowCount())):
                hash_item = self.log_table_widget.item(r, LOG_COL_COMMIT)
                if hash_item:
                    displayed_hash_text = hash_item.text().strip()
                    short_hash_match = re.search(r'\b([a-fA-F0-9]{7,})\b', displayed_hash_text)
                    if short_hash_match:
                         refs.add(short_hash_match.group(1))

        suggested_targets = sorted(list(refs)) + ["-- <file_path>"]

        checkout_target, ok = QInputDialog.getItem(self, "切换/恢复分支/提交/文件", "选择或输入目标 (分支, 标签, 提交, -- <文件路径>):\n例如: main, HEAD~1, remotes/origin/dev, -- README.md", suggested_targets, 0, True)

        if ok and checkout_target:
            clean_target = checkout_target.strip()
            if not clean_target:
                 self._show_warning("操作取消", "切换/恢复目标不能为空。")
                 return

            if clean_target.startswith("--"):
                 path_part = clean_target[2:].strip()
                 if not path_part:
                      self._show_warning("输入错误", "使用 '--' 恢复文件时必须提供文件或目录路径。")
                      return
                 self._add_command_to_sequence(f"git restore -- {shlex.quote(path_part)}")
            else:
                self._add_command_to_sequence(f"git checkout {shlex.quote(clean_target)}")
        elif ok and not checkout_target:
            self._show_information("操作取消", "切换/恢复目标不能为空。")


    # 通过对话框选择模式/目标添加到 'git reset' 命令
    def _add_reset_to_sequence(self):
        if not self._check_repo_and_warn(): return
        options = ["--soft HEAD~1", "--mixed HEAD~1", "--hard HEAD~1", "HEAD", "-- "]
        reset_target, ok = QInputDialog.getItem(self, "重置 (Reset)", "选择模式/目标或输入自定义 (例如: --hard <commit>, -- <file>):", options, 0, True)

        if ok and reset_target:
            clean_target = reset_target.strip()
            if not clean_target:
                 self._show_warning("操作取消", "重置目标不能为空。")
                 return

            if "--hard" in clean_target.split():
                 reply = QMessageBox.warning(self, "⚠️ 危险操作: git reset --hard",
                                              f"命令包含 '--hard'，将丢弃工作区和暂存区匹配的更改！\n目标: '{clean_target}'\n\n此操作通常不可撤销！\n\n确定要添加此命令到序列吗？",
                                              QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
                                              QMessageBox.StandardButton.Cancel)
                 if reply != QMessageBox.StandardButton.Yes:
                      self._show_information("操作取消", "已取消添加 Reset 命令。")
                      return

            if clean_target.startswith("--"):
                 path_part = clean_target[2:].strip()
                 if not path_part:
                      self._show_warning("输入错误", "使用 '--' 时必须提供文件或目录路径。")
                      return
                 self._add_command_to_sequence(f"git reset HEAD -- {shlex.quote(path_part)}")

            else:
                 try:
                      parts = shlex.split(clean_target)
                      if parts:
                           self._add_command_to_sequence(["git", "reset"] + [shlex.quote(p) for p in parts])
                      else:
                           self._show_information("无操作", "未输入有效的重置参数。")
                 except ValueError:
                       self._show_warning("输入错误", "无法解析 reset 参数，请检查引号。")
                       return

        elif ok and not reset_target:
            self._show_information("操作取消", "重置目标不能为空。")

    # 通过对话框选择或输入提交添加到 'git revert' 命令
    def _add_revert_to_sequence(self):
        if not self._check_repo_and_warn(): return
        recent_commits = []
        if self.log_table_widget:
            for r in range(min(10, self.log_table_widget.rowCount())):
                hash_item = self.log_table_widget.item(r, LOG_COL_COMMIT)
                msg_item = self.log_table_widget.item(r, LOG_COL_MESSAGE)
                if hash_item and msg_item:
                    short_hash = hash_item.text().strip().split()[0]
                    msg = msg_item.text()
                    full_hash = hash_item.data(Qt.ItemDataRole.UserRole) or short_hash
                    recent_commits.append(f"{short_hash} - {msg[:50]} | {full_hash}")

        display_items = [item.split(' | ')[0] for item in recent_commits]
        internal_values = {item.split(' | ')[0].strip(): item.split(' | ')[1].strip() for item in recent_commits if ' | ' in item}

        commit_ref_display, ok = QInputDialog.getItem(self, "撤销提交 (Revert)", "选择或输入要撤销的提交 (哈希, ref):", display_items, 0, True)

        if ok and commit_ref_display:
            clean_ref_display = commit_ref_display.strip()
            if not clean_ref_display:
                 self._show_warning("操作取消", "提交引用不能为空。")
                 return

            commit_ref = internal_values.get(clean_ref_display, clean_ref_display)

            logging.info(f"请求撤销提交: {commit_ref}")
            self._add_command_to_sequence(f"git revert {shlex.quote(commit_ref)}")

        elif ok and not commit_ref_display:
            self._show_information("操作取消", "提交引用不能为空。")


    # 通过对话框选择或输入目标添加到 'git rebase' 命令
    def _add_rebase_to_sequence(self):
        if not self._check_repo_and_warn(): return
        targets = set()
        common_bases = ["main", "master", "develop"]

        if self.branch_list_widget:
             for i in range(self.branch_list_widget.count()):
                  item = self.branch_list_widget.item(i)
                  branch_name = item.text().strip()
                  if branch_name.startswith("remotes/") or branch_name in common_bases:
                       targets.add(branch_name.lstrip('* ').strip())

        if self.log_table_widget and self.log_table_widget.rowCount() > 0:
             targets.add(f"HEAD~{min(5, self.log_table_widget.rowCount())}")
             targets.add("HEAD")
             if self.log_table_widget.rowCount() > 1:
                  targets.add(f"HEAD~1")

        suggested_targets = sorted(list(targets)) + ["-i <ref>"]

        rebase_target, ok = QInputDialog.getItem(self, "变基 (Rebase)", "选择或输入变基目标 (例如: main, origin/feature, HEAD~5, -i HEAD~3):", suggested_targets, 0, True)

        if ok and rebase_target:
            clean_target = rebase_target.strip()
            if not clean_target:
                 self._show_warning("操作取消", "变基目标不能为空。")
                 return

            is_interactive = clean_target.startswith("-i") or " --interactive" in clean_target

            confirmation_msg = f"确定要将当前分支变基到 '{clean_target}' 吗？"
            if is_interactive:
                 confirmation_msg += "\n\n这将启动交互式变基。"
            confirmation_msg += "\n\n变基会重写提交历史，可能需要解决冲突。请确保您理解其影响！"
            confirmation_msg += f"\n\n将添加命令: git rebase {clean_target}"


            reply = QMessageBox.question(self, "确认变基", confirmation_msg,
                                        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
                                        QMessageBox.StandardButton.Cancel)

            if reply == QMessageBox.StandardButton.Yes:
                logging.info(f"添加变基命令到序列: git rebase {clean_target}")
                if is_interactive:
                     try:
                         command_parts = shlex.split(f"git rebase {clean_target}")
                         self._add_command_to_sequence(command_parts)
                     except ValueError:
                          self._show_warning("输入错误", "无法解析变基参数，请检查引号。")
                          return
                else:
                     self._add_command_to_sequence(f"git rebase {shlex.quote(clean_target)}")
            else:
                 self._show_information("操作取消", "变基命令未添加到序列。")

        elif ok and not rebase_target:
            self._show_information("操作取消", "变基目标不能为空。")


    # 通过对话框获取消息和选项添加到 'git stash save' 命令
    def _add_stash_save_to_sequence(self):
        if not self._check_repo_and_warn(): return
        has_changes_to_stash = False
        if self.status_tree_model:
             has_changes_to_stash = (self.status_tree_model.staged_root.rowCount() > 0 or
                                     self.status_tree_model.unstage_root.rowCount() > 0 or
                                     self.status_tree_model.untracked_root.rowCount() > 0 or
                                     self.status_tree_model.unmerged_root.rowCount() > 0)
        if not has_changes_to_stash:
             self._show_information("无操作", "工作区和暂存区没有更改可以 Stash。")
             return

        stash_message, ok = QInputDialog.getText(self, "保存工作区 (Stash Save)", "输入 Stash 消息 (可选):", QLineEdit.EchoMode.Normal)
        if ok:
            include_untracked, ok_untracked = QInputDialog.getItem(self, "包含未跟踪文件?", "是否要包含未跟踪的文件 (git stash save -u)?", ["否", "是"], 0, False)

            command_parts = ["git", "stash", "push"]

            if ok_untracked and include_untracked == "是":
                command_parts.append("-u")

            if stash_message.strip():
                command_parts.extend(["-m", stash_message.strip()])

            self._add_command_to_sequence(command_parts)

        elif ok:
             pass

    # 通过对话框获取标签名和消息添加到 'git tag' 命令
    def _add_tag_to_sequence(self):
        if not self._check_repo_and_warn(): return
        tag_name, ok = QInputDialog.getText(self, "创建标签 (Tag)", "输入标签名称 (例如: v1.0.0):", QLineEdit.EchoMode.Normal)
        if ok and tag_name:
            clean_name = tag_name.strip();
            if not clean_name or not re.match(r'^[^\s~^:?*\[\\]+$', clean_name) or clean_name.endswith('.lock') or clean_name.startswith('.') or '..' in clean_name:
                self._show_warning("操作取消", f"标签名称 '{clean_name}' 无效。\n\n请遵循 Git 标签命名规则。")
                return

            message_reply = QMessageBox.question(self, "创建附注标签?", "是否要创建附注标签 (-a) 并添加消息?\n(轻量标签则直接创建)",
                                                 QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                                 QMessageBox.StandardButton.No)

            command_parts = ["git", "tag"]
            if message_reply == QMessageBox.StandardButton.Yes:
                 command_parts.append("-a")
                 tag_message, msg_ok = QInputDialog.getMultiLineText(self, "标签消息", "输入标签的附注消息:", "")
                 if msg_ok:
                     if tag_message.strip():
                          command_parts.extend(["-m", tag_message.strip()])
                 else:
                      self._show_information("操作取消", "附注标签消息输入已取消，仅创建轻量标签。")
                      command_parts = ["git", "tag"]


            command_parts.append(clean_name)

            self._add_command_to_sequence(command_parts)


        elif ok and not tag_name:
            self._show_information("操作取消", "标签名称不能为空。")

    # 通过对话框获取文件和来源添加到 'git restore' 命令
    def _add_restore_to_sequence(self):
        if not self._check_repo_and_warn(): return

        files_str, ok = QInputDialog.getText(self, "恢复文件 (Restore)", "输入要恢复的文件/目录 (用空格分隔，可用引号):\n(例如: src/main.py \"path with spaces/file.txt\" . )", QLineEdit.EchoMode.Normal)

        if ok and files_str:
            try:
                file_list = shlex.split(files_str.strip())
                if file_list:
                     restore_source, source_ok = QInputDialog.getItem(self, "选择恢复来源",
                                                                       "从哪里恢复文件?\n('暂存区': 从暂存区恢复到工作区)\n('HEAD': 从 HEAD 恢复到暂存区，也清空工作区)",
                                                                       ["暂存区 (Worktree)", "HEAD (Staged)"], 0, False)

                     if not source_ok:
                          self._show_information("操作取消", "文件恢复已取消。")
                          return

                     is_staged_source = (restore_source == "HEAD (Staged)")

                     command_parts = ["git", "restore"]
                     if is_staged_source:
                         command_parts.append("--staged")

                     command_parts.append("--")
                     command_parts.extend([shlex.quote(f) for f in file_list])

                     self._add_command_to_sequence(command_parts)
                else:
                    self._show_information("无操作", "未输入有效的文件或目录。")
            except ValueError as e:
                self._show_warning("输入错误", f"无法解析文件列表: {e}\n请确保引号正确配对。")
                logging.warning(f"无法解析 restore file input '{files_str}': {e}")
        elif ok:
            self._show_information("无操作", "未输入文件或目录。")


    # 根据内部序列列表更新文本框内容
    def _update_sequence_display(self):
        if self.sequence_display:
            self.sequence_display.blockSignals(True)
            self.sequence_display.setText("\n".join(self.current_command_sequence))
            self.sequence_display.blockSignals(False)
            cursor = self.sequence_display.textCursor()
            cursor.movePosition(QTextCursor.MoveOperation.End)
            self.sequence_display.setTextCursor(cursor)


    # 清空命令序列构建器
    def _clear_sequence(self):
        self.current_command_sequence = []
        self._update_sequence_display()
        if self.status_bar and not self._is_busy:
            self.status_bar.showMessage("命令序列已清空", 2000)
        logging.info("命令序列已清空。")

    # 执行命令序列构建器中的命令
    def _execute_sequence(self):
        self._sequence_text_changed()
        sequence_to_run = list(self.current_command_sequence)

        if not sequence_to_run:
            self._show_information("提示", "命令序列为空，无需执行。");
            return

        self._run_command_list_sequentially(sequence_to_run)


    # 设置UI的繁忙状态
    def _set_ui_busy(self, busy: bool, force_update: bool = False):
        if not force_update and self._is_busy == busy: return
        self._is_busy = busy

        is_repo_valid = self.git_handler.is_valid_repo()
        should_enable_repo_dependent = is_repo_valid and not busy

        for widget in self._repo_dependent_widgets:
            if widget:
                 widget.setEnabled(should_enable_repo_dependent)

        always_enabled_texts = [
             "选择或克隆仓库(&O)...", "在此初始化新仓库(&I)...", "克隆远程仓库(&C)...",
             "Git 全局配置(&G)...",
             "查看 Git 文档(&D)", "报告问题(&I)...", "关于(&A)",
             "清空原始输出", "退出(&X)"
         ]

        for action in self.findChildren(QAction):
            if action.text() in always_enabled_texts:
                if action.text() == "退出(&X)":
                     action.setEnabled(True)
                else:
                    action.setEnabled(not busy)

        if self.init_button:
            self.init_button.setEnabled(not busy)
        if self.select_repo_button:
            self.select_repo_button.setEnabled(not busy)

        self.shortcut_manager.set_shortcuts_enabled(should_enable_repo_dependent)

        if self.loading_label:
            if busy:
                self.loading_label.show()
                if self.loading_movie and self.loading_movie.isValid():
                     self.loading_movie.start()
                if self.status_bar: self.status_bar.showMessage("⏳ 正在执行...", 0)
            else:
                if self.loading_movie and self.loading_movie.isValid():
                     self.loading_movie.stop()
                self.loading_label.hide()
                if not force_update:
                     self._update_status_bar_info()

        if busy:
            QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        else:
            QApplication.restoreOverrideCursor()

    # 从命令行输入框获取命令并执行
    @pyqtSlot()
    def _execute_command_from_input(self):
        if not self.command_input: return
        command_text = self.command_input.text().strip();
        if not command_text: return
        logging.info(f"用户从命令行输入: {command_text}"); prompt_color = QColor(Qt.GlobalColor.darkCyan)

        if self._is_busy:
             logging.warning("UI 正忙，忽略命令行输入执行请求。")
             self._show_information("操作繁忙", "当前正在执行其他操作，请稍后再试。")
             self._append_output(f"❌ UI 正在忙碌，无法执行命令: {command_text}", QColor("red"))
             self.command_input.clear()
             return


        command_parts_check = []
        is_init_or_clone = False
        try:
            command_parts_check = shlex.split(command_text)
            is_init_or_clone = command_parts_check and command_parts_check[0].lower() == 'git' and len(command_parts_check) > 1 and command_parts_check[1].lower() in ('init', 'clone')
        except ValueError:
             pass


        if not is_init_or_clone and not self._check_repo_and_warn("仓库无效，无法执行命令。"):
             self._append_output(f"❌ 仓库无效，无法执行命令: {command_text}", QColor("red"))
             self.command_input.clear()
             return


        try: command_parts = shlex.split(command_text)
        except ValueError as e:
             self._show_warning("输入错误", f"无法解析命令: {e}");
             self._append_output(f"❌ 解析命令失败: {command_text}\n{e}", QColor("red"))
             self.command_input.clear()
             return

        if not command_parts:
             self.command_input.clear()
             return

        display_cmd = ' '.join(shlex.quote(part) for part in command_parts)
        self._append_output(f"\n$ {display_cmd}", prompt_color)
        self.command_input.clear()

        if is_init_or_clone and command_parts[1].lower() == 'clone':
             target_path = None
             if len(command_parts) > 2:
                 target_path_arg = command_parts[-1]
                 if not os.path.isabs(target_path_arg):
                      current_base_dir = self.git_handler.get_repo_path()
                      if current_base_dir and os.path.isdir(current_base_dir):
                           clone_base_dir = os.path.dirname(current_base_dir)
                           if len(command_parts) > 3 or len(command_parts) == 3:
                                target_path = os.path.join(clone_base_dir, command_parts[-1])
                           else:
                                target_path = os.path.join(clone_base_dir, target_path_arg)

                      else:
                           clone_base_dir = os.getcwd()
                           if len(command_parts) > 3 or len(command_parts) == 3:
                                target_path = os.path.join(clone_base_dir, command_parts[-1])
                           else:
                                target_path = os.path.join(clone_base_dir, target_path_arg)


                 else:
                      target_path = target_path_arg
                      clone_base_dir = os.path.dirname(target_path)
                      if len(command_parts) > 2:
                          command_parts = ["git", "clone", command_parts[2], os.path.basename(target_path)]


                 if not target_path:
                      self._show_warning("克隆错误", "无法确定克隆目标路径。")
                      self._set_ui_busy(False)
                      return

                 if os.path.exists(target_path):
                      if os.path.isdir(target_path) and os.listdir(target_path):
                           self._show_warning("克隆失败", f"目标目录 '{os.path.basename(target_path)}' 已存在且不为空。请选择一个空目录或新目录名。")
                           self._set_ui_busy(False)
                           return
                      elif not os.path.isdir(target_path):
                           self._show_warning("克隆失败", f"目标路径 '{os.path.basename(target_path)}' 已存在且不是目录。请选择一个目录或新目录名。")
                           self._set_ui_busy(False)
                           return

                 try:
                      if clone_base_dir and not os.path.exists(clone_base_dir):
                           os.makedirs(clone_base_dir, exist_ok=True)
                 except OSError as e:
                      logging.error(f"无法创建克隆父目录 '{clone_base_dir}': {e}")
                      self._show_warning("克隆错误", f"无法创建目录:\n{clone_base_dir}\n错误: {e}")
                      self._set_ui_busy(False)
                      return


             else:
                 self._show_warning("克隆命令格式错误", "请提供仓库 URL。")
                 self._set_ui_busy(False)
                 return

             self.git_handler.set_repo_path(None)
             self._update_repo_status()

             self._set_ui_busy(True)
             self.git_handler.execute_command_async(
                 command_parts,
                 on_finished_slot=lambda rc, so, se, tp=target_path: self._handle_clone_finish(rc, so, se, tp),
                 on_progress_slot=self._handle_clone_progress,
                 cwd=clone_base_dir
             )

        elif is_init_or_clone and command_parts[1].lower() == 'init':
             init_dir = None
             if len(command_parts) > 2: init_dir = command_parts[-1]
             init_abs_dir = os.path.abspath(init_dir) if init_dir else os.getcwd()

             git_dir_path = os.path.join(init_abs_dir, ".git")
             if os.path.exists(git_dir_path) and os.path.isdir(git_dir_path):
                 reply = QMessageBox.question(self, "仓库已存在", f"目录 '{os.path.basename(init_abs_dir)}' 似乎已经是一个 Git 仓库。\n是否仍要在此目录执行 'git init'? (不推荐)",
                                             QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No)
                 if reply == QMessageBox.StandardButton.No:
                      self._show_information("操作取消", "初始化操作已取消。")
                      open_existing = QMessageBox.question(self, "打开现有仓库?", f"要打开这个现有的仓库吗?",
                                                            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.Yes)
                      if open_existing == QMessageBox.StandardButton.Yes:
                           self._set_repository_path(init_abs_dir)
                      return
                 else:
                     logging.warning(f"在已有仓库目录 '{init_abs_dir}' 中执行 git init。")

             self.git_handler.set_repo_path(init_abs_dir, check_valid=False)
             self._update_repo_status()

             self._run_command_list_sequentially([command_text], refresh_on_success=False)

        else:
             self._run_command_list_sequentially([command_text], refresh_on_success=True)

    # 双击快捷键列表项时，将其命令序列加载到构建器
    def _load_shortcut_into_builder(self, item: QListWidgetItem = None):
        if not self.shortcut_list_widget: return
        if not item:
            item = self.shortcut_list_widget.currentItem()
            if not item: return

        shortcut_data = item.data(Qt.ItemDataRole.UserRole)
        if shortcut_data and isinstance(shortcut_data, dict) and shortcut_data.get('sequence'):
            name = shortcut_data.get('name', '未知')
            sequence_str = shortcut_data['sequence']
            self.current_command_sequence = [line.strip() for line in sequence_str.strip().splitlines() if line.strip()]
            self._update_sequence_display()
            if self.status_bar and not self._is_busy:
                self.status_bar.showMessage(f"快捷键 '{name}' 已加载到序列构建器", 3000)
            logging.info(f"快捷键 '{name}' 已加载到构建器。")
        else:
             logging.warning("双击了列表项，但未获取到快捷键数据或序列。")


    # 由 ShortcutManager 调用，执行快捷键对应的命令序列
    def _execute_sequence_from_string(self, name: str, sequence_str: str):
        logging.info(f"快捷键触发: Name='{name}', Sequence='{sequence_str[:100]}...'")

        if self._is_busy:
            logging.warning(f"UI 正忙，忽略快捷键 '{name}' 执行请求。")
            self._show_information("操作繁忙", "当前正在执行其他操作，请稍后再试。")
            return

        commands = [line.strip() for line in sequence_str.strip().splitlines() if line.strip()]

        if not commands:
             self._show_warning("快捷键无效", f"快捷键 '{name}' 解析后命令序列为空。")
             logging.warning(f"快捷键 '{name}' 导致命令列表为空。")
             return

        self._run_command_list_sequentially(commands)

    # 暂存所有更改 (git add .)
    @pyqtSlot()
    def _stage_all(self):
        if not self._check_repo_and_warn(): return
        has_changes = False
        if self.status_tree_model:
             has_changes = (
                 self.status_tree_model.unstage_root.rowCount() > 0 or
                 self.status_tree_model.untracked_root.rowCount() > 0 or
                 (hasattr(self.status_tree_model, 'unmerged_root') and self.status_tree_model.unmerged_root.rowCount() > 0)
             )
        if not has_changes:
            self._show_information("无操作", "没有未暂存或未跟踪的文件可供暂存。")
            return
        logging.info("请求暂存所有更改 (git add .)")
        self._run_command_list_sequentially(["git add ."])


    # 撤销所有已暂存文件 (git reset HEAD --)
    @pyqtSlot()
    def _unstage_all(self):
        if not self._check_repo_and_warn(): return
        has_staged = False
        if self.status_tree_model:
             has_staged = self.status_tree_model.staged_root.rowCount() > 0
        if not has_staged:
             self._show_information("无操作", "没有已暂存的文件可供撤销。")
             return
        logging.info("请求撤销全部暂存 (git reset HEAD --)");
        self._run_command_list_sequentially(["git reset HEAD --"])


    # 暂存指定文件
    def _stage_files(self, files: list[str]):
        if not self._check_repo_and_warn() or not files: return
        logging.info(f"请求暂存特定文件: {files}")
        command_parts = ["git", "add", "--"] + [shlex.quote(f) for f in files]
        self._run_command_list_sequentially([ ' '.join(command_parts) ])


    # 撤销暂存指定文件
    def _unstage_files(self, files: list[str]):
        if not self._check_repo_and_warn() or not files: return
        logging.info(f"请求撤销暂存特定文件: {files}")
        command_parts = ["git", "reset", "HEAD", "--"] + [shlex.quote(f) for f in files]
        self._run_command_list_sequentially([ ' '.join(command_parts) ])


    # 显示状态视图的右键菜单
    @pyqtSlot(QPoint)
    def _show_status_context_menu(self, pos: QPoint):
        if not self.status_tree_view or not self.status_tree_model: return

        is_repo_valid = self.git_handler.is_valid_repo() and not self._is_busy
        selected_indexes = self.status_tree_view.selectionModel().selectedIndexes()
        selected_files_data = self.status_tree_model.get_selected_files_data(list(selected_indexes))

        menu = QMenu()
        added_action = False

        files_to_stage = selected_files_data.get(STATUS_UNSTAGED, []) + \
                         selected_files_data.get(STATUS_UNTRACKED, []) + \
                         selected_files_data.get(STATUS_UNMERGED, [])

        if files_to_stage:
            stage_action = QAction("暂存选中项 (+)", self)
            stage_action.setToolTip(f"将 {len(files_to_stage)} 个选中的文件添加到暂存区 (git add)")
            stage_action.triggered.connect(lambda checked=False, files=list(files_to_stage): self._stage_files(files))
            stage_action.setEnabled(is_repo_valid)
            menu.addAction(stage_action)
            added_action = True

        files_to_unstage = selected_files_data.get(STATUS_STAGED, [])
        if files_to_unstage:
            if added_action: menu.addSeparator()
            unstage_action = QAction("撤销暂存选中项 (-)", self)
            unstage_action.setToolTip(f"将 {len(files_to_unstage)} 个选中的文件移出暂存区 (git reset HEAD --)")
            unstage_action.triggered.connect(lambda checked=False, files=list(files_to_unstage): self._unstage_files(files))
            unstage_action.setEnabled(is_repo_valid)
            menu.addAction(unstage_action)
            added_action = True

        files_to_discard_unstaged = selected_files_data.get(STATUS_UNSTAGED, [])
        if files_to_discard_unstaged:
             if added_action: menu.addSeparator()
             discard_action = QAction("丢弃工作区更改...", self)
             discard_action.setToolTip(f"将 {len(files_to_discard_unstaged)} 个选中的文件恢复到暂存区状态 (git restore --)")
             discard_action.triggered.connect(lambda checked=False, files=list(files_to_discard_unstaged): self._discard_changes_dialog(files))
             discard_action.setEnabled(is_repo_valid)
             menu.addAction(discard_action)
             added_action = True

        all_selected_paths = set(p for paths in selected_files_data.values() for p in paths)

        if added_action and len(all_selected_paths) == 1:
             single_file_path = list(all_selected_paths)[0]
             repo_base = self.git_handler.get_repo_path()
             if repo_base:
                 full_path = os.path.join(repo_base, single_file_path)
                 if os.path.isfile(full_path):
                      menu.addSeparator()
                      open_action = QAction(f"打开文件 '{os.path.basename(single_file_path)}'", self)
                      open_action.triggered.connect(lambda checked=False, path=full_path: QDesktopServices.openUrl(QUrl.fromLocalFile(path)))
                      open_action.setEnabled(is_repo_valid)
                      menu.addAction(open_action)

                      open_folder_action = QAction(f"打开所在文件夹", self)
                      open_folder_action.triggered.connect(lambda checked=False, path=os.path.dirname(full_path): QDesktopServices.openUrl(QUrl.fromLocalFile(path)))
                      open_folder_action.setEnabled(is_repo_valid)
                      menu.addAction(open_folder_action)


        current_index = self.status_tree_view.indexAt(pos)
        if current_index.isValid() and not current_index.parent().isValid():
             root_item = self.status_tree_model.itemFromIndex(current_index)
             section_type = root_item.data(Qt.ItemDataRole.UserRole)
             if section_type:
                  all_files_in_section = self.status_tree_model.get_files_in_section(section_type)
                  if all_files_in_section:
                       if added_action: menu.addSeparator()
                       if section_type in [STATUS_UNSTAGED, STATUS_UNTRACKED, STATUS_UNMERGED]:
                            stage_all_in_section_action = QAction(f"暂存此类别所有文件 (+)", self)
                            stage_all_in_section_action.setToolTip(f"暂存 {len(all_files_in_section)} 个文件")
                            stage_all_in_section_action.triggered.connect(lambda checked=False, files=list(all_files_in_section): self._stage_files(files))
                            stage_all_in_section_action.setEnabled(is_repo_valid)
                            menu.addAction(stage_all_in_section_action)
                            added_action = True
                       if section_type == STATUS_STAGED:
                            unstage_all_in_section_action = QAction(f"撤销暂存此类别所有文件 (-)", self)
                            unstage_all_in_section_action.setToolTip(f"撤销暂存 {len(all_files_in_section)} 个文件")
                            unstage_all_in_section_action.triggered.connect(lambda checked=False, files=list(all_files_in_section): self._unstage_files(files))
                            unstage_all_in_section_action.setEnabled(is_repo_valid)
                            menu.addAction(unstage_all_in_section_action)
                            added_action = True
                       if section_type == STATUS_UNSTAGED:
                            discard_all_in_section_action = QAction(f"丢弃此类别所有更改...", self)
                            discard_all_in_section_action.setToolTip(f"丢弃 {len(all_files_in_section)} 个文件的工作区更改")
                            discard_all_in_section_action.triggered.connect(lambda checked=False, files=list(all_files_in_section): self._discard_changes_dialog(files))
                            discard_all_in_section_action.setEnabled(is_repo_valid)
                            menu.addAction(discard_all_in_section_action)
                            added_action = True


        if added_action:
             menu.exec(self.status_tree_view.viewport().mapToGlobal(pos))
        else:
             logging.debug("No applicable actions for selected status items.")


    # 显示确认对话框并执行 git restore -- for selected files
    def _discard_changes_dialog(self, files: list[str]):
        if not self._check_repo_and_warn() or not files: return

        message = f"确定要丢弃以下 {len(files)} 个文件的本地（未暂存）更改吗？\n\n" + "\n".join([f"- {f}" for f in files[:10]] + (["..."] if len(files) > 10 else [])) + \
                  f"\n\n文件将恢复为暂存区中的状态。\n此操作通常不可撤销！"
        reply = QMessageBox.warning(self, "确认丢弃工作区更改", message,
                                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
                                    QMessageBox.StandardButton.Cancel)

        if reply == QMessageBox.StandardButton.Yes:
            logging.info(f"请求丢弃文件更改: {files}")
            command_parts = ["git", "restore", "--"] + [shlex.quote(f) for f in files]
            self._run_command_list_sequentially([ ' '.join(command_parts) ])


    # 处理状态视图选择变化，触发差异显示更新
    @pyqtSlot(QItemSelection, QItemSelection)
    def _status_selection_changed(self, selected: QItemSelection, deselected: QItemSelection):
        if not self.status_tree_view or not self.status_tree_model or not self.diff_text_edit:
             if self.diff_text_edit:
                 self.diff_text_edit.clear(); self.diff_text_edit.setPlaceholderText("")
             return

        if not self._check_repo_and_warn("仓库无效，无法显示差异。"):
             if self.diff_text_edit: self.diff_text_edit.clear(); self.diff_text_edit.setPlaceholderText("仓库无效")
             return

        self.diff_text_edit.clear()
        selected_indexes = self.status_tree_view.selectionModel().selectedIndexes()

        if not selected_indexes:
            self.diff_text_edit.setPlaceholderText("选中已更改的文件以查看差异...");
            return

        selected_files_data = self.status_tree_model.get_selected_files_data(list(selected_indexes))

        all_unique_selected_files = set(p for paths in selected_files_data.values() for p in paths)


        if len(all_unique_selected_files) != 1:
            self.diff_text_edit.setPlaceholderText(f"请选择单个文件以查看差异 ({len(all_unique_selected_files)} 个文件被选中)");
            return

        file_path = list(all_unique_selected_files)[0]
        section_type_priority = [STATUS_UNSTAGED, STATUS_STAGED, STATUS_UNTRACKED, STATUS_UNMERGED]
        section_type_for_diff = None
        for section in section_type_priority:
             if file_path in selected_files_data.get(section, []):
                  section_type_for_diff = section
                  break

        if not file_path or not section_type_for_diff:
            logging.warning(f"Could not retrieve file path ({file_path}) or section type ({section_type_for_diff}) for single selection.");
            self.diff_text_edit.setPlaceholderText("无法获取文件路径或状态...");
            return

        base_name = os.path.basename(file_path)
        repo_base = self.git_handler.get_repo_path()

        if section_type_for_diff == STATUS_UNTRACKED:
             self.diff_text_edit.setPlaceholderText(f"正在加载未跟踪文件 '{base_name}' 的内容...");
             QApplication.processEvents()
             if repo_base:
                 full_path = os.path.join(repo_base, file_path)
                 try:
                      with open(full_path, 'r', encoding='utf-8', errors='ignore') as f: content = f.read()
                      self._display_formatted_diff(self.diff_text_edit, f"--- 未跟踪文件: {file_path} ---\n\n{content}")
                 except Exception as e:
                      logging.error(f"无法读取未跟踪文件 {full_path}: {e}")
                      self.diff_text_edit.setPlainText(f"无法读取未跟踪文件:\n{e}")
                 finally: self.diff_text_edit.setPlaceholderText("")
             else:
                  self.diff_text_edit.setPlainText("错误：无法确定仓库路径以读取未跟踪文件。")
                  self.diff_text_edit.setPlaceholderText("")


        elif self.git_handler:
            staged_diff = (section_type_for_diff == STATUS_STAGED)
            diff_type_name = "暂存区 (Staged)" if staged_diff else "工作区 (Unstaged)" if section_type_for_diff == STATUS_UNSTAGED else "未合并 (Unmerged)"
            self.diff_text_edit.setPlaceholderText(f"正在加载 '{base_name}' 的 {diff_type_name} 差异...");
            QApplication.processEvents()

            diff_command = ["git", "diff", "--no-ext-diff"]
            if staged_diff:
                diff_command.append("--cached")
            elif section_type_for_diff == STATUS_UNSTAGED:
                pass
            elif section_type_for_diff == STATUS_UNMERGED:
                 pass

            diff_command.extend(["--", file_path])

            self.git_handler.execute_command_async(
                diff_command,
                lambda rc, so, se, fp=file_path, sd=staged_diff: self._on_diff_received(rc, so, se, fp, sd)
            )
        else:
            self.diff_text_edit.setPlainText("❌ 内部错误：Git 处理程序不可用。")
            self.diff_text_edit.setPlaceholderText("")


    # 处理 Git diff 命令结果并显示
    @pyqtSlot(int, str, str, str, bool)
    def _on_diff_received(self, return_code: int, stdout: str, stderr: str, file_path: str, staged_diff: bool):
        if not self.diff_text_edit: return
        self.diff_text_edit.setPlaceholderText("");

        if return_code == 0:
            if stdout.strip():
                self._display_formatted_diff(self.diff_text_edit, stdout)
            else:
                compare_target = "HEAD" if staged_diff else "暂存区"
                self.diff_text_edit.setPlainText(f"文件 '{os.path.basename(file_path)}' 与 {compare_target} 没有差异。")
        else:
            if return_code != 0 and stderr and ("file mode changed" in stderr or "unmerged" in stderr.lower()):
                 logging.warning(f"获取差异失败，可能是文件模式变化或未合并文件: {stderr.strip()}")
                 self._display_formatted_diff(self.diff_text_edit, stderr.strip())
            else:
                 error_message = f"❌ 获取 '{os.path.basename(file_path)}' 的差异失败:\n{stderr.strip()}"
                 self.diff_text_edit.setPlainText(error_message)
                 logging.error(f"Git diff 失败 (RC={return_code}) for {file_path}: {stderr.strip()}")

    # 在指定的 QTextEdit 中显示带颜色格式的差异文本
    def _display_formatted_diff(self, target_edit: QTextEdit, diff_text: str):
        if not target_edit: return

        target_edit.clear()
        cursor = target_edit.textCursor()

        default_format = target_edit.currentCharFormat()
        mono_font = QFont("Courier New", default_format.font().pointSize())
        default_format.setFont(mono_font)

        add_format = QTextCharFormat(default_format); add_format.setForeground(QColor("darkGreen")); add_format.setFontWeight(QFont.Weight.Bold)
        del_format = QTextCharFormat(default_format); del_format.setForeground(QColor("red"))
        header_format = QTextCharFormat(default_format); header_format.setForeground(QColor("darkBlue"))
        hunk_header_format = QTextCharFormat(default_format); hunk_header_format.setForeground(QColor("darkCyan"))
        conflict_format = QTextCharFormat(default_format); conflict_format.setForeground(QColor("orange")); conflict_format.setBackground(QColor("#404000")); conflict_format.setFontWeight(QFont.Weight.Bold)

        target_edit.setCurrentCharFormat(default_format)

        lines = diff_text.splitlines()
        for line in lines:
            fmt_to_apply = default_format
            text_to_insert = line

            if line.startswith('diff ') or line.startswith('index ') or line.startswith('--- ') or line.startswith('+++ '):
                fmt_to_apply = header_format
            elif line.startswith('@@ '):
                fmt_to_apply = hunk_header_format
            elif line.startswith('+'):
                fmt_to_apply = add_format
            elif line.startswith('-'):
                fmt_to_apply = del_format
            elif line.startswith(('<<<<<<< ', '=======', '>>>>>>> ')):
                 fmt_to_apply = conflict_format

            cursor.insertText(text_to_insert, fmt_to_apply)
            cursor.insertText("\n", default_format)

        cursor.movePosition(QTextCursor.MoveOperation.Start)
        target_edit.setTextCursor(cursor)
        target_edit.ensureCursorVisible()


    # 双击分支列表项，尝试切换到该分支或基于远程分支创建本地分支
    @pyqtSlot(QListWidgetItem)
    def _branch_double_clicked(self, item: QListWidgetItem):
        if not item or not self._check_repo_and_warn(): return
        branch_name = item.text().strip();
        if not branch_name: return

        if branch_name.startswith("remotes/"):
             remote_parts = branch_name.split('/', 2);
             if len(remote_parts) == 3:
                 remote_branch_name = remote_parts[2];
                 self._create_and_checkout_branch_from_dialog(remote_branch_name, branch_name)
             else:
                  self._show_warning("操作无效", f"无法解析远程分支名称: '{branch_name}'");
             return

        if branch_name.startswith("(Detached HEAD"):
             self._show_information("提示", "当前处于 'Detached HEAD' 状态。\n如需切换到分支，请双击或右键菜单选择一个分支名称。");
             return

        if item.font().bold():
             logging.info(f"已在分支 '{branch_name}'.");
             if self.status_bar and not self._is_busy: self.status_bar.showMessage(f"已在分支 '{branch_name}'", 2000);
             return

        reply = QMessageBox.question(self, "切换分支", f"确定要切换到本地分支 '{branch_name}' 吗？\n\n未提交的更改将被携带（如果可能）。", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel, QMessageBox.StandardButton.Yes)
        if reply == QMessageBox.StandardButton.Yes:
             logging.info(f"请求切换到分支: {branch_name}")
             self._run_command_list_sequentially([f"git checkout {shlex.quote(branch_name)}"])


    # 显示创建新本地分支的对话框
    @pyqtSlot()
    def _create_branch_dialog(self):
        if not self._check_repo_and_warn(): return
        start_point = "HEAD"

        branch_name, ok = QInputDialog.getText(self, "创建新分支", f"输入新分支的名称 (基于 {start_point}):", QLineEdit.EchoMode.Normal)
        if ok and branch_name:
            clean_name = branch_name.strip();
            if not clean_name or not re.match(r'^(?!\.|.*\.\.|.*@\{)[^\s~^:?*\[\\]+$', clean_name) or clean_name.endswith('.lock') or clean_name.startswith('.') or '..' in clean_name or '//' in clean_name:
                 self._show_warning("创建失败", f"分支名称 '{clean_name}' 无效。\n\n请遵循 Git 分支命名规则。")
                 return
            logging.info(f"请求创建新分支: {clean_name} (基于 {start_point})");
            self._run_command_list_sequentially([f"git branch {shlex.quote(clean_name)} {shlex.quote(start_point)}"])
        elif ok and not branch_name:
            self._show_information("创建失败", "分支名称不能为空。")


    # 显示分支列表的右键菜单
    @pyqtSlot(QPoint)
    def _show_branch_context_menu(self, pos: QPoint):
        if not self.branch_list_widget: return

        item = self.branch_list_widget.itemAt(pos);
        if not item: return

        is_repo_valid = self.git_handler.is_valid_repo() and not self._is_busy

        menu = QMenu();
        branch_name = item.text().strip();
        is_remote = branch_name.startswith("remotes/");
        is_current = item.font().bold();
        is_detached = branch_name.startswith("(Detached HEAD");
        added_action = False

        if not is_detached:
            if not is_current and not is_remote:
                checkout_action = QAction(f"切换到 '{branch_name}'", self)
                checkout_action.triggered.connect(lambda checked=False, b=branch_name: self._run_command_list_sequentially([f"git checkout {shlex.quote(b)}"]))
                checkout_action.setEnabled(is_repo_valid)
                menu.addAction(checkout_action)
                added_action = True

                merge_action = QAction(f"合并 '{branch_name}' 到当前分支...", self)
                merge_action.triggered.connect(lambda checked=False, b=branch_name: self._merge_branch_dialog(b))
                merge_action.setEnabled(is_repo_valid)
                menu.addAction(merge_action)
                added_action = True

                rebase_current_action = QAction(f"将当前分支变基到 '{branch_name}'...", self)
                rebase_current_action.triggered.connect(lambda checked=False, b=branch_name: self._rebase_onto_dialog(b))
                rebase_current_action.setEnabled(is_repo_valid)
                menu.addAction(rebase_current_action)
                added_action = True

                rename_action = QAction(f"重命名本地分支 '{branch_name}'...", self)
                rename_action.triggered.connect(lambda checked=False, b=branch_name: self._rename_local_branch_dialog(b))
                rename_action.setEnabled(is_repo_valid)
                menu.addAction(rename_action)
                added_action = True

                delete_action = QAction(f"删除本地分支 '{branch_name}'...", self)
                delete_action.triggered.connect(lambda checked=False, b=branch_name: self._delete_branch_dialog(b, force=False))
                delete_action.setEnabled(is_repo_valid)
                menu.addAction(delete_action)
                added_action = True

                force_delete_action = QAction(f"强制删除本地分支 '{branch_name}'...", self)
                force_delete_action.triggered.connect(lambda checked=False, b=branch_name: self._delete_branch_dialog(b, force=True))
                force_delete_action.setEnabled(is_repo_valid)
                menu.addAction(force_delete_action)
                added_action = True

            elif is_remote:
                 remote_parts = branch_name.split('/', 2);
                 if len(remote_parts) == 3:
                     remote_name = remote_parts[1];
                     remote_branch_name = remote_parts[2];

                     checkout_remote_action = QAction(f"基于此创建并切换本地分支...", self)
                     checkout_remote_action.triggered.connect(lambda checked=False, rbn=remote_branch_name, sp=branch_name: self._create_and_checkout_branch_from_dialog(rbn, sp))
                     checkout_remote_action.setEnabled(is_repo_valid)
                     menu.addAction(checkout_remote_action)
                     added_action = True

                     create_local_action = QAction(f"基于此创建本地分支...", self)
                     create_local_action.triggered.connect(lambda checked=False, rbn=remote_branch_name, sp=branch_name: self._create_branch_from_dialog(rbn, sp))
                     create_local_action.setEnabled(is_repo_valid)
                     menu.addAction(create_local_action)
                     added_action = True

                     merge_remote_action = QAction(f"合并 '{branch_name}' 到当前分支...", self)
                     merge_remote_action.triggered.connect(lambda checked=False, b=branch_name: self._merge_branch_dialog(b))
                     merge_remote_action.setEnabled(is_repo_valid)
                     menu.addAction(merge_remote_action)
                     added_action = True

                     delete_remote_action = QAction(f"删除远程分支 '{remote_name}/{remote_branch_name}'...", self)
                     delete_remote_action.triggered.connect(lambda checked=False, rn=remote_name, rbn=remote_branch_name: self._delete_remote_branch_dialog(rn, rbn))
                     delete_remote_action.setEnabled(is_repo_valid)
                     menu.addAction(delete_remote_action)
                     added_action = True

            if is_current and not is_remote:
                 push_action = QAction(f"推送当前分支 '{branch_name}'...", self)
                 push_action.triggered.connect(lambda checked=False, b=branch_name: self._push_branch_dialog(b))
                 push_action.setEnabled(is_repo_valid)
                 menu.addAction(push_action)
                 added_action = True

                 rename_action = QAction(f"重命名当前分支 '{branch_name}'...", self)
                 rename_action.triggered.connect(lambda checked=False, b=branch_name: self._rename_local_branch_dialog(b))
                 rename_action.setEnabled(is_repo_valid)
                 menu.addAction(rename_action)
                 added_action = True

            if added_action:
                 menu.addSeparator()
                 copy_action = QAction(f"复制名称 '{branch_name}'", self)
                 copy_action.triggered.connect(lambda checked=False, b=branch_name: QApplication.clipboard().setText(b))
                 menu.addAction(copy_action)


        if added_action: menu.exec(self.branch_list_widget.mapToGlobal(pos))
        else: logging.debug(f"No applicable context actions for branch item: {branch_name}")


    # 显示确认对话框并执行 git merge
    def _merge_branch_dialog(self, branch_to_merge: str):
        if not self._check_repo_and_warn(): return
        reply = QMessageBox.question(self, "确认合并", f"确定要将分支 '{branch_to_merge}' 合并到当前分支吗?",
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
                                     QMessageBox.StandardButton.Yes)
        if reply == QMessageBox.StandardButton.Yes:
            logging.info(f"请求合并分支: {branch_to_merge}")
            self._run_command_list_sequentially([f"git merge {shlex.quote(branch_to_merge)}"])

    # 显示确认对话框并执行 git rebase
    def _rebase_onto_dialog(self, base_branch: str):
        if not self._check_repo_and_warn(): return
        reply = QMessageBox.question(self, "确认变基", f"确定要将当前分支变基到 '{base_branch}' 吗?\n\n变基会重写历史记录!",
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
                                     QMessageBox.StandardButton.Cancel)
        if reply == QMessageBox.StandardButton.Yes:
            logging.info(f"请求将当前分支变基到: {base_branch}")
            self._run_command_list_sequentially([f"git rebase {shlex.quote(base_branch)}"])

    # 显示对话框获取新名称并执行 git branch -m
    def _rename_local_branch_dialog(self, old_name: str):
        if not self._check_repo_and_warn(): return
        if old_name.startswith("remotes/"):
             self._show_warning("操作无效", "无法重命名远程跟踪分支。")
             return

        new_name, ok = QInputDialog.getText(self, "重命名本地分支", f"输入 '{old_name}' 的新名称:", QLineEdit.EchoMode.Normal, old_name)
        if ok and new_name:
             clean_new_name = new_name.strip();
             if not clean_new_name or not re.match(r'^(?!\.|.*\.\.|.*@\{)[^\s~^:?*\[\\]+$', clean_new_name) or clean_new_name.endswith('.lock') or clean_new_name.startswith('.') or '..' in clean_new_name or '//' in clean_new_name:
                 self._show_warning("重命名失败", f"新分支名称 '{clean_new_name}' 无效。")
                 return
             if clean_new_name == old_name:
                 self._show_information("提示", "新旧名称相同，无需重命名。")
                 return

             logging.info(f"请求重命名本地分支: {old_name} -> {clean_new_name}");
             self._run_command_list_sequentially([f"git branch -m {shlex.quote(old_name)} {shlex.quote(clean_new_name)}"])
        elif ok and not new_name:
            self._show_warning("重命名失败", "新分支名称不能为空。")

    # 显示对话框选择远程和选项并执行 git push
    def _push_branch_dialog(self, branch_name: str):
        if not self._check_repo_and_warn(): return
        if branch_name.startswith("remotes/") or branch_name.startswith("("):
             self._show_warning("操作无效", "不能直接推送远程跟踪分支或处于 Detached HEAD 状态。请切换到本地分支。")
             return

        remotes_result = self.git_handler.execute_command_sync(["git", "remote"])
        remotes = remotes_result.stdout.strip().splitlines() if remotes_result and remotes_result.returncode == 0 else []
        if not remotes:
            remotes = ["origin"]
            logging.warning("未找到远程仓库，建议使用 'origin'。")

        remote_name, ok_remote = QInputDialog.getItem(self, "选择远程仓库", "推送到哪个远程仓库?", remotes, 0, False)
        if not ok_remote or not remote_name: return

        set_upstream = False
        upstream_reply = QMessageBox.question(self, "设置上游?", f"是否要设置 '{remote_name}/{branch_name}' 为此本地分支的上游跟踪分支 (-u)?",
                                               QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.Yes)
        set_upstream = (upstream_reply == QMessageBox.StandardButton.Yes)

        command = ["git", "push"]
        if set_upstream: command.append("-u")
        command.append(shlex.quote(remote_name))
        command.append(shlex.quote(branch_name))

        logging.info(f"请求推送分支: {' '.join(command)}")
        self._run_command_list_sequentially([' '.join(command)])


    # 显示确认对话框并执行 git branch -d/-D
    def _delete_branch_dialog(self, branch_name: str, force: bool = False):
        if not self._check_repo_and_warn() or not branch_name or branch_name.startswith("remotes/"):
             logging.error(f"无效的本地分支名称用于删除: {branch_name}");
             self._show_warning("操作无效", "请选择一个本地分支进行删除。")
             return

        current_branch_display = self.current_branch_name_display.strip().lstrip('* ') if self.current_branch_name_display else None
        if current_branch_display and branch_name.strip().lower() == current_branch_display.lower():
             self._show_warning("操作无效", f"不能删除当前所在的分支 '{branch_name}'。\n请先切换到其他分支。")
             return

        delete_flag = "-D" if force else "-d"
        action_text = "强制删除" if force else "删除"
        warning_message = f"确定要{action_text}本地分支 '{branch_name}' 吗？"
        if not force: warning_message += "\n\n此操作仅在分支已合并时安全。\n如果分支未合并且需要删除，请使用强制删除 (-D)。"
        warning_message += "\n\n此操作通常不可撤销！"

        reply = QMessageBox.warning(self, f"确认{action_text}本地分支", warning_message,
                                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
                                    QMessageBox.StandardButton.Cancel)

        if reply == QMessageBox.StandardButton.Yes:
             logging.info(f"请求{action_text}本地分支: {branch_name} (使用 {delete_flag})")
             self._run_command_list_sequentially([f"git branch {delete_flag} {shlex.quote(branch_name)}"])


    # 显示确认对话框并执行 git push <remote> --delete <branch>
    def _delete_remote_branch_dialog(self, remote_name: str, branch_name: str):
        if not self._check_repo_and_warn() or not remote_name or not branch_name:
             logging.error(f"无效的远程/分支名称用于删除: {remote_name}/{branch_name}");
             self._show_warning("操作无效", "无法确定远程仓库或分支名称。")
             return
        confirmation_message = f"确定要从远程仓库 '{remote_name}' 删除分支 '{branch_name}' 吗？\n\n将执行: git push {remote_name} --delete {branch_name}\n\n此操作通常不可撤销，并会影响其他协作者！"
        reply = QMessageBox.warning(self, "确认删除远程分支", confirmation_message, QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel, QMessageBox.StandardButton.Cancel)
        if reply == QMessageBox.StandardButton.Yes:
            logging.info(f"请求删除远程分支: {remote_name}/{branch_name}")
            self._run_command_list_sequentially([f"git push {shlex.quote(remote_name)} --delete {shlex.quote(branch_name)}"])

    # 显示对话框获取新名称并执行 git branch <newname> <startpoint>
    def _create_branch_from_dialog(self, suggest_name: str, start_point: str):
         if not self._check_repo_and_warn(): return
         branch_name, ok = QInputDialog.getText(self, "创建本地分支", f"输入新本地分支的名称 (基于 '{start_point}'):", QLineEdit.EchoMode.Normal, suggest_name)
         if ok and branch_name:
            clean_name = branch_name.strip();
            if not clean_name or not re.match(r'^(?!\.|.*\.\.|.*@\{)[^\s~^:?*\[\\]+$', clean_name) or clean_name.endswith('.lock') or clean_name.startswith('.') or '..' in clean_name or '//' in clean_name:
                 self._show_warning("操作失败", f"分支名称 '{clean_name}' 无效。")
                 return
            logging.info(f"请求创建分支: {clean_name} (基于 {start_point})");
            self._run_command_list_sequentially([f"git branch {shlex.quote(clean_name)} {shlex.quote(start_point)}"])
         elif ok and not branch_name:
            self._show_warning("操作失败", "分支名称不能为空。")


    # 显示对话框获取新名称并执行 git checkout -b <newname> <startpoint>
    def _create_and_checkout_branch_from_dialog(self, suggest_name: str, start_point: str):
         if not self._check_repo_and_warn(): return
         branch_name, ok = QInputDialog.getText(self, "创建并切换本地分支", f"输入新本地分支的名称 (基于 '{start_point}'):", QLineEdit.EchoMode.Normal, suggest_name)
         if ok and branch_name:
            clean_name = branch_name.strip();
            if not clean_name or not re.match(r'^(?!\.|.*\.\.|.*@\{)[^\s~^:?*\[\\]+$', clean_name) or clean_name.endswith('.lock') or clean_name.startswith('.') or '..' in clean_name or '//' in clean_name:
                 self._show_warning("操作失败", f"分支名称 '{clean_name}' 无效。")
                 return
            logging.info(f"请求创建并切换到分支: {clean_name} (基于 {start_point})");
            self._run_command_list_sequentially([f"git checkout -b {shlex.quote(clean_name)} {shlex.quote(start_point)}"])
         elif ok and not branch_name:
            self._show_warning("操作失败", "分支名称不能为空。")


    # 处理日志表格选择变化，触发提交详情显示更新
    @pyqtSlot()
    def _log_selection_changed(self):
        if not self.log_table_widget or not self.commit_details_textedit or not self.git_handler:
             if self.commit_details_textedit: self.commit_details_textedit.clear(); self.commit_details_textedit.setPlaceholderText("")
             return

        if not self._check_repo_and_warn("仓库无效，无法显示提交详情。"):
             if self.commit_details_textedit: self.commit_details_textedit.clear(); self.commit_details_textedit.setPlaceholderText("仓库无效");
             return

        selected_items = self.log_table_widget.selectedItems();
        self.commit_details_textedit.clear()

        selected_rows_indices = self.log_table_widget.selectionModel().selectedRows()

        if not selected_rows_indices:
             self.commit_details_textedit.setPlaceholderText("选中上方提交记录以查看详情...");
             return

        first_selected_row_index = selected_rows_indices[0]
        selected_row = first_selected_row_index.row()

        if selected_row < 0:
             self.commit_details_textedit.setPlaceholderText("请选择一个提交记录。"); return

        hash_item = self.log_table_widget.item(selected_row, LOG_COL_COMMIT);
        if hash_item:
            commit_hash = hash_item.data(Qt.ItemDataRole.UserRole)
            if not commit_hash: commit_hash = hash_item.text().strip().split()[0] if hash_item.text() else None


            if commit_hash:
                logging.debug(f"Log selection changed, requesting details for commit: {commit_hash}")
                self.commit_details_textedit.setPlaceholderText(f"正在加载 Commit '{commit_hash[:7]}...' 的详情...");
                QApplication.processEvents()

                self.git_handler.execute_command_async(
                    ["git", "show", "--no-ext-diff", shlex.quote(commit_hash)],
                    lambda rc, so, se, ch=commit_hash: self._on_commit_details_received(rc, so, se, ch)
                )
            else:
                self.commit_details_textedit.setPlaceholderText("无法获取选中提交的 Hash.");
                logging.error(f"无法从日志表格项获取有效 Hash (Row: {selected_row}).")
        else:
            self.commit_details_textedit.setPlaceholderText("无法确定选中的提交项.");
            logging.error(f"无法在日志表格中找到行 {selected_row} 的第 {LOG_COL_COMMIT} 列项。")


    # 处理 Git show 命令结果并显示提交详情
    @pyqtSlot(int, str, str, str)
    def _on_commit_details_received(self, return_code: int, stdout: str, stderr: str, commit_hash: str):
        if not self.commit_details_textedit: return
        self.commit_details_textedit.setPlaceholderText("");

        if return_code == 0:
            if stdout.strip():
                self._display_formatted_diff(self.commit_details_textedit, stdout)
            else:
                 self.commit_details_textedit.setPlainText(f"未获取到提交 '{commit_hash[:7]}' 的详情。")
        else:
            error_message = f"❌ 获取提交 '{commit_hash[:7]}' 详情失败:\n{stderr.strip()}"
            self.commit_details_textedit.setPlainText(error_message)
            logging.error(f"获取 Commit 详情失败 (RC={return_code}) for {commit_hash}: {stderr.strip()}")

    # 执行 git fetch --all
    def _fetch_all(self):
        if not self._check_repo_and_warn(): return
        logging.info("请求抓取所有远程 (git fetch --all)")
        self._run_command_list_sequentially(["git fetch --all"], refresh_on_success=True)

    # 执行 git fetch --prune
    def _fetch_prune(self):
        if not self._check_repo_and_warn(): return
        logging.info("请求抓取并修剪 (git fetch --prune)")
        self._run_command_list_sequentially(["git fetch --prune"], refresh_on_success=True)

    # 执行 git stash pop
    def _stash_pop(self):
        if not self._check_repo_and_warn(): return
        logging.info("请求应用最近的 Stash (git stash pop)")
        self._run_command_list_sequentially(["git stash pop"])

    # 执行 git stash list
    def _stash_list(self):
        if not self._check_repo_and_warn(): return
        logging.info("请求显示 Stash 列表 (git stash list)")
        self._run_command_list_sequentially(["git stash list"], refresh_on_success=False)

    # 显示警告对话框并执行 git clean
    def _clean_working_directory_dialog(self):
        if not self._check_repo_and_warn(): return
        warning_message = ("确定要清理工作区吗？\n\n"
                           "将执行: git clean -fd\n\n"
                           "这将 **永久删除** 所有未跟踪的文件和目录！\n"
                           "（不包括 .gitignore 中忽略的文件）\n\n"
                           "此操作不可撤销！强烈建议先使用 'git clean -fdn' (模拟运行)。")
        reply = QMessageBox.critical(self, "⚠️ 危险操作: 清理工作区", warning_message,
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
                                     QMessageBox.StandardButton.Cancel)
        if reply == QMessageBox.StandardButton.Yes:
             dry_run_reply = QMessageBox.question(self, "执行 Dry Run?", "是否先执行 'git clean -fdn' (模拟运行) 查看将删除哪些文件？",
                                                 QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.Yes)
             if dry_run_reply == QMessageBox.StandardButton.Yes:
                  logging.info("请求模拟清理工作区 (git clean -fdn)")
                  self._run_command_list_sequentially(["git clean -fdn"], refresh_on_success=False)
             else:
                  logging.info("请求清理工作区 (git clean -fd)")
                  self._run_command_list_sequentially(["git clean -fd"])

    # 在浏览器中打开 Git 文档
    def _open_git_documentation(self):
        QDesktopServices.openUrl(QUrl("https://git-scm.com/doc"))

    # 在浏览器中打开项目 Issue Tracker
    def _open_issue_tracker(self):
        QDesktopServices.openUrl(QUrl("https://github.com/424635328/Git-Helper/issues"))

    # 显示对话框选择本地分支并执行 git checkout
    def _run_switch_branch(self):
        if not self._check_repo_and_warn(): return
        branches = []
        if self.branch_list_widget:
            for i in range(self.branch_list_widget.count()):
                item = self.branch_list_widget.item(i)
                branch_name = item.text().strip()
                if not branch_name.startswith(("remotes/", "(")) and not item.font().bold():
                     branch_name = branch_name.lstrip('* ').strip()
                     if branch_name:
                         branches.append(branch_name)

        branch_name, ok = QInputDialog.getItem(self,"切换分支","选择或输入要切换到的本地分支名称:", sorted(branches), 0, True)
        if ok and branch_name:
            clean_name = branch_name.strip()
            if not clean_name:
                 self._show_information("操作取消", "分支名称不能为空。")
                 return
            if clean_name.startswith("remotes/") or clean_name.startswith("("):
                 self._show_warning("操作无效", "请选择一个本地分支进行切换。\n远程跟踪分支请从分支列表右键选择 '基于此创建...'。")
                 return
            self._run_command_list_sequentially([f"git checkout {shlex.quote(clean_name)}"])
        elif ok and not branch_name:
             self._show_information("操作取消", "分支名称不能为空。")


    # 执行 git remote -v
    def _run_list_remotes(self):
        if not self._check_repo_and_warn(): return
        self._run_command_list_sequentially(["git remote -v"], refresh_on_success=False)


    # 显示全局 Git 配置对话框
    def _open_settings_dialog(self):
        dialog = SettingsDialog(self)
        current_name = ""
        current_email = ""
        if self.git_handler:
            try:
                 name_result = self.git_handler.execute_command_sync(["git", "config", "--global", "user.name"])
                 email_result = self.git_handler.execute_command_sync(["git", "config", "--global", "user.email"])

                 if name_result and name_result.returncode == 0: current_name = name_result.stdout.strip()
                 else: logging.warning(f"获取全局 user.name 失败: RC={name_result.returncode if name_result else 'N/A'}, Err={name_result.stderr.strip() if name_result else 'N/A'}")

                 if email_result and email_result.returncode == 0: current_email = email_result.stdout.strip()
                 else: logging.warning(f"获取全局 user.email 失败: RC={email_result.returncode if email_result else 'N/A'}, Err={email_result.stderr.strip() if email_result else 'N/A'}")

                 dialog.name_edit.setText(current_name)
                 dialog.email_edit.setText(current_email)
            except Exception as e: logging.warning(f"获取全局配置时出错: {e}")

        if dialog.exec():
            config_data = dialog.get_data()
            commands_to_run = []

            name_val = config_data.get("user.name")
            email_val = config_data.get("user.email")

            if name_val is not None and name_val.strip() and name_val.strip() != current_name:
                 commands_to_run.append(f"git config --global user.name {shlex.quote(name_val.strip())}")
            if email_val is not None and email_val.strip() and email_val.strip() != current_email:
                 if '@' not in email_val.strip() or '.' not in email_val.strip().split('@')[-1]:
                      self._show_warning("格式警告", f"邮箱 '{email_val.strip()}' 格式似乎不正确，但仍将尝试设置。")
                 commands_to_run.append(f"git config --global user.email {shlex.quote(email_val.strip())}")

            if commands_to_run:
                 confirmation_msg = "将执行以下全局 Git 配置命令:\n\n" + "\n".join(commands_to_run) + "\n\n确定吗？"
                 reply = QMessageBox.question(self, "应用全局配置", confirmation_msg, QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel, QMessageBox.StandardButton.Yes)
                 if reply == QMessageBox.StandardButton.Yes:
                     logging.info(f"执行全局配置命令: {commands_to_run}")
                     if self.git_handler:
                         self._run_command_list_sequentially(commands_to_run, refresh_on_success=False)
                     else:
                         logging.error("GitHandler unavailable for settings.")
                         QMessageBox.critical(self, "错误", "无法执行配置命令 (Git 处理程序不可用)。")
                 else: self._show_information("操作取消", "未应用全局配置更改。")
            else: self._show_information("无更改", "未检测到有效的用户名或邮箱信息变更。")


    # 显示关于对话框
    def _show_about_dialog(self):
        try:
             match = re.search(r'v([\d.]+)', self.windowTitle())
             version = match.group(1) if match else "N/A"
        except Exception: version = "N/A"
        about_text = f"""
<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"><title>简易 Git GUI</title>
<style>
    body {{ font-family: sans-serif; padding: 15px; }} h1 {{ color: #333; }}
    p.version {{ color: #555; font-style: italic; }} h2 {{ color: #444; border-bottom: 1px solid #eee; padding-bottom: 5px; margin-top: 20px; }}
    ul {{ list-style-type: disc; margin-left: 20px; }} li strong {{ color: #005999; }}
    div.footer {{ margin-top: 30px; border-top: 1px solid #eee; padding-top: 10px; font-size: 0.9em; color: #666; }}
    a {{ color: #007bff; text-decoration: none; }} a:hover {{ text-decoration: underline; }}
</style></head><body>
  <h1>简易 Git GUI</h1> <p class="version">版本: {version}</p>
  <p>一个用于可视化、学习和执行 Git 命令的简单图形界面工具。</p>
  <h2>主要功能:</h2>
  <ul>
      <li>仓库选择、初始化、克隆</li> <li>文件状态查看 (暂存/未暂存/未跟踪/冲突)</li>
      <li>文件差异 (Diff) 对比 (暂存区/工作区)</li> <li>提交历史 (Log) 查看与提交详情</li>
      <li>常用命令按钮 (Add, Commit, Pull, Push, Fetch, Branch, Merge, ...)</li>
      <li>命令序列构建与编辑</li> <li>快捷键保存与执行</li>
      <li>分支列表查看与管理 (创建/切换/合并/删除/重命名)</li> <li>Stash 操作 (Save, Pop, List)</li>
      <li>远程仓库操作 (Fetch, Push, Prune, List, Remote Delete)</li> <li>全局 Git 配置</li>
      <li>直接命令执行</li><li>简单的加载动画指示器</li><li>上次仓库路径记忆</li>
  </ul>
  <h2>开发日志 (近期):</h2>
  <ul>
    <li><strong>v1.17</strong> - 实现仓库路径持久化，修复快捷键可能失效问题，改进繁忙状态管理，修复差异对比显示。</li>
    <li><strong>v1.16</strong> - 修复UI繁忙状态管理逻辑，确保命令执行或刷新后UI恢复正常。修复提交详情显示问题。</li>
    <li><strong>v1.15</strong> - 修复多个 AttributeError 和 TypeError，修正 UI 繁忙状态管理和刷新逻辑，完善 git init 的 cwd 处理，修复日志和提交详情的数据获取。</li>
    <li><strong>v1.14</strong> - 修复分支刷新回调安全检查逻辑，优化UI繁忙状态管理和状态栏更新，添加加载动画指示器（需提供动画文件），改进日志解析和显示，优化克隆/初始化流程，增强右键菜单功能。</li>
    <li><strong>v1.13</strong> - 菜单栏增强 (Clone, Init, Fetch All/Prune, Stash, Clean, Docs), 新增 -s, -x, --quiet 参数按钮, 改进 UI 交互与状态更新, 优化对话框与输入校验。</li>
    <li><strong>v1.12</strong> - 增加 rebase 命令构建块</li>
    <li>(更早版本见代码历史)</li>
  </ul>
  <div class="footer">
    <p>作者: GitHub @424635328</p>
    <p>项目地址: <a href="https://github.com/424635328/Git-Helper">https://github.com/424635328/Git-Helper</a></p>
    <p>构建日期: 2025-04-23</p>
  </div>
</body></html>"""
        QMessageBox.about(self, f"关于 简易 Git GUI v{version}", about_text)

    # 处理窗口关闭事件
    def closeEvent(self, event):
        logging.info("应用程序关闭请求。")
        try:
            if self.git_handler and hasattr(self.git_handler, 'get_active_process_count'):
                 active_count = self.git_handler.get_active_process_count()
                 if active_count > 0:
                      logging.warning(f"窗口关闭时仍有 {active_count} 个 Git 操作可能在后台运行。")
                      reply = QMessageBox.question(self, "后台操作仍在运行",
                                                   f"有 {active_count} 个 Git 操作似乎仍在后台运行。\n"
                                                   "立即退出可能会中断它们。\n\n确定要退出吗?",
                                                   QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
                                                   QMessageBox.StandardButton.Cancel)
                      if reply == QMessageBox.StandardButton.Cancel:
                           event.ignore()
                           return
                      else:
                           self.git_handler.terminate_all_processes()
                           logging.info("已请求终止所有活跃 Git 进程。")
            elif self._is_busy:
                 logging.warning("窗口关闭时 UI 处于繁忙状态，但 GitHandler 未报告活跃进程。")

        except Exception as e:
            logging.exception("关闭窗口时检查或终止 Git 操作出错。")

        logging.info("应用程序正在关闭。")
        if self.loading_movie and self.loading_movie.isValid():
            self.loading_movie.stop()
        self._save_current_repo()
        event.accept()