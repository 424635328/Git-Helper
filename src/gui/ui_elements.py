# src/ui_elements.py
import os
from PyQt6.QtWidgets import (
    QMenuBar, QMenu, QToolBar,
    QApplication, QStyle, QMessageBox # 导入需要的 QtWidgets
)
# 从 QtGui 导入 QAction, QIcon, QKeySequence (QKeySequence 需要 QtGui)
from PyQt6.QtGui import QAction, QIcon, QKeySequence

# 从 QtCore 导入 QSize, Qt # 导入需要的 QtCore 模块
from PyQt6.QtCore import QSize, Qt

# 导入 Config Manager 函数 (如果需要访问 config 来调整 UI 元素)
from src.config_manager import config


# --- 图标路径定义 (从 main_window.py 移过来) ---
# 确保这个路径相对于 ui_elements.py 是正确的
ICON_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "icons")
def get_icon_path(name):
    path = os.path.join(ICON_DIR, f"{name}.png")
    # 可以添加文件存在检查和默认图标逻辑
    # if not os.path.exists(path):
    #     print(f"警告: 图标未找到 {path}")
    #     # 返回一个默认图标或者 None
    #     return QApplication.style().standardIcon(QStyle.StandardPixmap.SP_FileIcon) # 示例：返回一个默认文件图标
    return path

class UIElementsCreator:
    def __init__(self, main_window, action_refs_dict):
        """
        初始化 UI 元素创建器。

        Args:
            main_window: QMainWindow 的实例，用于连接 Action 的 triggered 信号和获取菜单栏/工具栏。
            action_refs_dict: 一个字典，用于存储创建的 QAction 的引用。
        """
        self.main_window = main_window
        self._action_refs = action_refs_dict # 使用 MainWindow 提供的字典
        self.style = QApplication.style() # 获取 QStyle 对象

    def create_actions(self):
        """创建 QAction 对象，使用标准或主题图标"""
        # 这里的 Action 名称 (字典的 key) 需要与 MainWindow 中 _update_ui_after_config_load 方法中引用的名称一致
        action_dict = self._action_refs # 使用传入的字典

        # 文件
        action_dict["exit"] = QAction(self.style.standardIcon(QStyle.StandardPixmap.SP_DialogCloseButton), "退出(&X)", self.main_window)
        action_dict["exit"].setShortcut(QKeySequence.StandardKey.Quit)
        action_dict["exit"].triggered.connect(self.main_window.close)

        # 基础操作
        action_dict["status"] = QAction(QIcon.fromTheme("view-refresh", self.style.standardIcon(QStyle.StandardPixmap.SP_MessageBoxInformation)), "查看状态(&S)", self.main_window)
        action_dict["status"].triggered.connect(self.main_window.handle_status_action)
        action_dict["log"] = QAction(QIcon.fromTheme("document-open-recent", self.style.standardIcon(QStyle.StandardPixmap.SP_FileIcon)), "查看日志(&L)...", self.main_window)
        action_dict["log"].triggered.connect(self.main_window.handle_log_action)
        action_dict["diff"] = QAction(QIcon.fromTheme("svn-update", self.style.standardIcon(QStyle.StandardPixmap.SP_MessageBoxQuestion)), "查看差异(&D)...", self.main_window)
        action_dict["diff"].triggered.connect(self.main_window.handle_diff_action)
        action_dict["add"] = QAction(self.style.standardIcon(QStyle.StandardPixmap.SP_FileDialogNewFolder), "添加更改(&A)...", self.main_window)
        action_dict["add"].triggered.connect(self.main_window.handle_add_action)
        action_dict["commit"] = QAction(self.style.standardIcon(QStyle.StandardPixmap.SP_DialogSaveButton), "提交更改(&C)...", self.main_window)
        action_dict["commit"].setShortcut(QKeySequence("Ctrl+S"))
        action_dict["commit"].triggered.connect(self.main_window.handle_commit_action)

        # 分支与同步
        action_dict["branch"] = QAction(QIcon.fromTheme("network-wired", self.style.standardIcon(QStyle.StandardPixmap.SP_ComputerIcon)), "创建/切换分支...", self.main_window)
        action_dict["branch"].triggered.connect(self.main_window.handle_create_switch_branch_action)
        action_dict["pull"] = QAction(self.style.standardIcon(QStyle.StandardPixmap.SP_ArrowDown), "拉取更改...", self.main_window)
        action_dict["pull"].triggered.connect(self.main_window.handle_pull_action)
        action_dict["push"] = QAction(self.style.standardIcon(QStyle.StandardPixmap.SP_ArrowUp), "推送分支...", self.main_window)
        action_dict["push"].triggered.connect(self.main_window.handle_push_action)
        action_dict["sync"] = QAction(self.style.standardIcon(QStyle.StandardPixmap.SP_BrowserReload), "同步 Fork", self.main_window)
        action_dict["sync"].triggered.connect(self.main_window.handle_sync_fork_action)
        action_dict["sync"].setEnabled(False) # 初始禁用

        # 高级操作
        action_dict["merge"] = QAction(QIcon.fromTheme("svn-commit", self.style.standardIcon(QStyle.StandardPixmap.SP_CommandLink)), "合并分支...", self.main_window)
        action_dict["merge"].triggered.connect(self.main_window.handle_merge_action)
        action_dict["rebase"] = QAction(self.style.standardIcon(QStyle.StandardPixmap.SP_BrowserReload), "变基分支...", self.main_window)
        action_dict["rebase"].triggered.connect(self.main_window.handle_rebase_action)
        action_dict["stash"] = QAction(QIcon.fromTheme("document-save-as", self.style.standardIcon(QStyle.StandardPixmap.SP_DialogSaveButton)), "管理储藏...", self.main_window)
        action_dict["stash"].triggered.connect(self.main_window.handle_stash_action)
        action_dict["pr"] = QAction(QIcon.fromTheme("mail-forward", self.style.standardIcon(QStyle.StandardPixmap.SP_DialogApplyButton)), "创建 Pull Request...", self.main_window)
        action_dict["pr"].triggered.connect(self.main_window.handle_create_pull_request_action)
        action_dict["pr"].setEnabled(False) # 初始禁用
        action_dict["tags"] = QAction(QIcon.fromTheme("stock_bookmark", self.style.standardIcon(QStyle.StandardPixmap.SP_DialogHelpButton)), "管理标签...", self.main_window)
        action_dict["tags"].triggered.connect(self.main_window.handle_manage_tags_action)
        action_dict["remotes"] = QAction(QIcon.fromTheme("network-server", self.style.standardIcon(QStyle.StandardPixmap.SP_DriveNetIcon)), "管理远程仓库...", self.main_window)
        action_dict["remotes"].triggered.connect(self.main_window.handle_manage_remotes_action)
        action_dict["delete_local_branch"] = QAction(QIcon.fromTheme("edit-delete", self.style.standardIcon(QStyle.StandardPixmap.SP_TrashIcon)), "删除本地分支...", self.main_window)
        action_dict["delete_local_branch"].triggered.connect(self.main_window.handle_delete_local_branch_action)
        action_dict["delete_remote_branch"] = QAction(QIcon.fromTheme("edit-delete", self.style.standardIcon(QStyle.StandardPixmap.SP_TrashIcon)), "删除远程分支...", self.main_window)
        action_dict["delete_remote_branch"].triggered.connect(self.main_window.handle_delete_remote_branch_action)
        action_dict["cherry_pick"] = QAction(QIcon.fromTheme("edit-copy", self.style.standardIcon(QStyle.StandardPixmap.SP_FileDialogContentsView)), "挑选提交...", self.main_window)
        action_dict["cherry_pick"].triggered.connect(self.main_window.handle_cherry_pick_action)
        action_dict["clean_commits"] = QAction(self.style.standardIcon(QStyle.StandardPixmap.SP_DialogResetButton), "清理提交...", self.main_window)
        action_dict["clean_commits"].triggered.connect(self.main_window.handle_clean_commits_action)


        # 设置
        action_dict["reload"] = QAction(self.style.standardIcon(QStyle.StandardPixmap.SP_BrowserReload), "重新加载配置", self.main_window)
        action_dict["reload"].triggered.connect(lambda: self.main_window._load_initial_config(self.main_window.project_root))
        action_dict["show_config"] = QAction(self.style.standardIcon(QStyle.StandardPixmap.SP_FileDialogInfoView), "显示当前配置", self.main_window)
        action_dict["show_config"].triggered.connect(self.main_window.show_config_info_action)

    def create_menu_bar(self):
        """创建菜单栏并添加 Actions"""
        menu_bar = self.main_window.menuBar() # 从 MainWindow 获取菜单栏

        file_menu = menu_bar.addMenu("&文件")
        file_menu.addAction(self._action_refs["exit"])

        basic_menu = menu_bar.addMenu("基础操作(&B)")
        basic_menu.addAction(self._action_refs["status"])
        basic_menu.addAction(self._action_refs["log"])
        basic_menu.addAction(self._action_refs["diff"])
        basic_menu.addSeparator()
        basic_menu.addAction(self._action_refs["add"])
        basic_menu.addAction(self._action_refs["commit"])

        branch_menu = menu_bar.addMenu("分支与同步(&N)")
        branch_menu.addAction(self._action_refs["branch"])
        branch_menu.addSeparator()
        branch_menu.addAction(self._action_refs["pull"])
        branch_menu.addAction(self._action_refs["push"])
        branch_menu.addAction(self._action_refs["sync"])

        advanced_menu = menu_bar.addMenu("高级操作(&V)")
        advanced_menu.addAction(self._action_refs["merge"])
        advanced_menu.addAction(self._action_refs["rebase"])
        advanced_menu.addAction(self._action_refs["stash"])
        advanced_menu.addAction(self._action_refs["cherry_pick"])
        advanced_menu.addSeparator()
        advanced_menu.addAction(self._action_refs["tags"])
        advanced_menu.addAction(self._action_refs["remotes"])
        advanced_menu.addSeparator()
        advanced_menu.addAction(self._action_refs["delete_local_branch"])
        advanced_menu.addAction(self._action_refs["delete_remote_branch"])
        advanced_menu.addSeparator()
        advanced_menu.addAction(self._action_refs["pr"])
        advanced_menu.addSeparator()
        advanced_menu.addAction(self._action_refs["clean_commits"])


        settings_menu = menu_bar.addMenu("设置(&T)")
        settings_menu.addAction(self._action_refs["reload"])
        settings_menu.addAction(self._action_refs["show_config"])

    def create_tool_bar(self):
        """创建工具栏并添加常用 Actions"""
        toolbar = QToolBar("主工具栏")
        toolbar.setIconSize(QSize(24, 24)) # 图标建议大小
        self.main_window.addToolBar(toolbar) # 添加到 MainWindow

        # 添加常用操作
        toolbar.addAction(self._action_refs["status"])
        toolbar.addAction(self._action_refs["pull"])
        toolbar.addAction(self._action_refs["push"])
        toolbar.addAction(self._action_refs["sync"])
        toolbar.addSeparator()
        toolbar.addAction(self._action_refs["add"])
        toolbar.addAction(self._action_refs["commit"])
        toolbar.addSeparator()
        toolbar.addAction(self._action_refs["branch"])
        toolbar.addAction(self._action_refs["pr"])
        # 可以添加更多...
        # toolbar.addSeparator()
        # toolbar.addAction(self._action_refs["reload"])