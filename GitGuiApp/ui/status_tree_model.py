# -*- coding: utf-8 -*-
import logging
import os
import re
from typing import Optional, List, Dict, Set
from PyQt6.QtGui import QStandardItemModel, QStandardItem, QIcon, QColor, QFont
from PyQt6.QtCore import Qt, QObject, QModelIndex, QItemSelection
from PyQt6.QtWidgets import QApplication, QStyle

STATUS_STAGED = "已暂存的更改"
STATUS_UNSTAGED = "未暂存的更改"
STATUS_UNTRACKED = "未跟踪的文件"
STATUS_UNMERGED = "未合并 (冲突)"

def get_standard_icon(icon_enum: QStyle.StandardPixmap) -> QIcon:
    try:
        app = QApplication.instance()
        if app:
            style = app.instance().style()
            if style:
                icon = style.standardIcon(icon_enum)
                if icon is not None and not icon.isNull():
                    return icon
                else:
                    logging.warning(f"标准图标枚举 {icon_enum} 返回了空 QIcon 或 None。")
            else:
                 logging.warning(f"无法从 QApplication 获取样式对象以加载图标 {icon_enum}。")
        else:
             logging.warning(f"请求图标 {icon_enum} 时 QApplication 实例不可用。")
    except Exception as e:
        logging.warning(f"获取标准图标 {icon_enum} 时发生异常: {e}", exc_info=True)

    return QIcon()


_STATUS_ICON_CHAR_MAP = {
    "A": QStyle.StandardPixmap.SP_FileDialogNewFolder,
    "M": QStyle.StandardPixmap.SP_DialogSaveButton,
    "D": QStyle.StandardPixmap.SP_TrashIcon,
    "R": QStyle.StandardPixmap.SP_FileDialogDetailedView,
    "C": QStyle.StandardPixmap.SP_FileDialogContentsView,
    "T": QStyle.StandardPixmap.SP_FileDialogInfoView,
    "U": QStyle.StandardPixmap.SP_MessageBoxCritical,
    "?": QStyle.StandardPixmap.SP_MessageBoxQuestion,

    STATUS_STAGED: QStyle.StandardPixmap.SP_DialogYesButton,
    STATUS_UNSTAGED: QStyle.StandardPixmap.SP_DialogNoButton,
    STATUS_UNTRACKED: QStyle.StandardPixmap.SP_FileDialogInfoView,
    STATUS_UNMERGED: QStyle.StandardPixmap.SP_MessageBoxWarning,

    "DEFAULT": QStyle.StandardPixmap.SP_FileIcon,
}


class StatusTreeModel(QStandardItemModel):
    """管理 Git 状态树视图的模型和数据解析"""
    def __init__(self, parent: Optional['QObject'] = None):
        super().__init__(parent)
        self.setHorizontalHeaderLabels(["状态", "文件路径"])

        self.STATUS_ICONS: Dict[str, QIcon] = {}
        for key, enum in _STATUS_ICON_CHAR_MAP.items():
             self.STATUS_ICONS[key] = get_standard_icon(enum)

        self.DEFAULT_ICON = self.STATUS_ICONS.get("DEFAULT", QIcon())

        root_font = QFont()
        root_font.setBold(True)

        self.staged_root: QStandardItem = QStandardItem(STATUS_STAGED)
        self.staged_root.setIcon(self.STATUS_ICONS.get(STATUS_STAGED, self.DEFAULT_ICON))
        self.staged_root.setData(STATUS_STAGED, Qt.ItemDataRole.UserRole)
        self.staged_root.setEditable(False)
        self.staged_root.setFont(root_font)

        self.unstage_root: QStandardItem = QStandardItem(STATUS_UNSTAGED)
        self.unstage_root.setIcon(self.STATUS_ICONS.get(STATUS_UNSTAGED, self.DEFAULT_ICON))
        self.unstage_root.setData(STATUS_UNSTAGED, Qt.ItemDataRole.UserRole)
        self.unstage_root.setEditable(False)
        self.unstage_root.setFont(root_font)

        self.untracked_root: QStandardItem = QStandardItem(STATUS_UNTRACKED)
        self.untracked_root.setIcon(self.STATUS_ICONS.get(STATUS_UNTRACKED, self.DEFAULT_ICON))
        self.untracked_root.setData(STATUS_UNTRACKED, Qt.ItemDataRole.UserRole)
        self.untracked_root.setEditable(False)
        self.untracked_root.setFont(root_font)

        self.unmerged_root: QStandardItem = QStandardItem(STATUS_UNMERGED)
        self.unmerged_root.setIcon(self.STATUS_ICONS.get(STATUS_UNMERGED, self.DEFAULT_ICON))
        self.unmerged_root.setData(STATUS_UNMERGED, Qt.ItemDataRole.UserRole)
        self.unmerged_root.setEditable(False)
        self.unmerged_root.setFont(root_font)

        self.invisibleRootItem().appendRow([self.staged_root, QStandardItem()])
        self.invisibleRootItem().appendRow([self.unstage_root, QStandardItem()])
        self.invisibleRootItem().appendRow([self.untracked_root, QStandardItem()])
        self.invisibleRootItem().appendRow([self.unmerged_root, QStandardItem()])

        for i in range(self.invisibleRootItem().rowCount()):
            placeholder_item = self.invisibleRootItem().child(i, 1)
            if placeholder_item:
                placeholder_item.setEditable(False)
                placeholder_item.setSelectable(False)


    def clear_status(self):
        """清空所有状态项，保留根节点"""
        if self.staged_root: self.staged_root.removeRows(0, self.staged_root.rowCount())
        if self.unstage_root: self.unstage_root.removeRows(0, self.unstage_root.rowCount())
        if self.untracked_root: self.untracked_root.removeRows(0, self.untracked_root.rowCount())
        if self.unmerged_root: self.unmerged_root.removeRows(0, self.unmerged_root.rowCount())
        self._update_root_counts()
        logging.debug("Status model cleared.")


    def parse_and_populate(self, porcelain_output: str):
        """
        解析 'git status --porcelain=v1' 的输出并填充模型。
        v1 格式为 "XY path" 或 "XY orig_path -> new_path"
        """
        self.clear_status()

        lines = porcelain_output.strip().splitlines()

        if not lines:
            logging.info("Git status porcelain 输出为空。")
            self._update_root_counts()
            return

        self.beginResetModel()

        try:
            for line in lines:
                if not line or len(line) < 3:
                    logging.warning(f"跳过无效或过短的状态行: {repr(line)}")
                    continue

                try:
                    status_codes = line[:2]
                    path_part_raw = line[3:]

                    original_path: Optional[str] = None
                    file_path_unescaped = path_part_raw

                    if status_codes[0] in ('R', 'C'):
                        parts = path_part_raw.split(' -> ', 1)
                        if len(parts) == 2:
                            original_path = parts[0].strip()
                            file_path_unescaped = parts[1].strip()
                        else:
                            logging.warning(f"无法正确解析重命名/复制格式行: {repr(line)}")
                            file_path_unescaped = path_part_raw.strip()

                    if file_path_unescaped.startswith('"') and file_path_unescaped.endswith('"'):
                        try:
                            file_path_unescaped = file_path_unescaped[1:-1].encode('latin-1', 'backslashreplace').decode('unicode_escape')
                        except Exception as decode_err:
                             logging.error(f"解码带引号路径 '{file_path_unescaped}' 时出错: {decode_err}. 使用原始路径。")
                             file_path_unescaped = path_part_raw.strip()


                    file_path_data = file_path_unescaped
                    display_path = file_path_unescaped

                    if original_path:
                         display_path = f"{os.path.basename(file_path_unescaped)} (从 {os.path.basename(original_path)})"

                    tooltip = f"状态: {status_codes}\n路径: {file_path_data}"
                    if original_path: tooltip += f"\n原路径: {original_path}"


                    if status_codes == '??':
                        status_text = status_codes
                        icon_char = '?'
                        color = QColor("darkCyan")
                        root = self.untracked_root
                        if root:
                             item_status = QStandardItem(status_text)
                             item_path = QStandardItem(display_path)
                             item_status.setIcon(self.STATUS_ICONS.get(icon_char, self.DEFAULT_ICON))
                             item_status.setForeground(color)
                             item_path.setForeground(color)
                             item_status.setToolTip(tooltip)
                             item_path.setToolTip(tooltip)
                             item_path.setData(file_path_data, Qt.ItemDataRole.UserRole + 1)
                             item_path.setData(True, Qt.ItemDataRole.UserRole + 2)
                             item_status.setEditable(False)
                             item_path.setEditable(False)
                             root.appendRow([item_status, item_path])


                    elif status_codes[0] == 'U' or status_codes[1] == 'U' or status_codes in ('AA', 'DD'):
                         status_text = status_codes
                         icon_char = 'U'
                         color = QColor('red')
                         root = self.unmerged_root
                         if root:
                             item_status = QStandardItem(status_text)
                             item_path = QStandardItem(display_path)
                             item_status.setIcon(self.STATUS_ICONS.get(icon_char, self.DEFAULT_ICON))
                             item_status.setForeground(color)
                             item_path.setForeground(color)
                             item_status.setToolTip(tooltip)
                             item_path.setToolTip(tooltip)
                             item_path.setData(file_path_data, Qt.ItemDataRole.UserRole + 1)
                             item_path.setData(True, Qt.ItemDataRole.UserRole + 2)
                             item_status.setEditable(False)
                             item_path.setEditable(False)
                             root.appendRow([item_status, item_path])


                    else:
                         staged_status_char = status_codes[0]
                         unstaged_status_char = status_codes[1]

                         if staged_status_char != ' ':
                             status_text = status_codes
                             icon_char = staged_status_char
                             color = QColor("darkGreen") if icon_char in 'AC' else QColor("blue") if icon_char in 'M' else QColor("red") if icon_char in 'D' else QColor("purple")
                             root = self.staged_root
                             if root:
                                 item_status = QStandardItem(status_text)
                                 item_path = QStandardItem(display_path)
                                 item_status.setIcon(self.STATUS_ICONS.get(icon_char, self.DEFAULT_ICON))
                                 item_status.setForeground(color)
                                 item_path.setForeground(color)
                                 item_status.setToolTip(tooltip)
                                 item_path.setToolTip(tooltip)
                                 item_path.setData(file_path_data, Qt.ItemDataRole.UserRole + 1)
                                 item_path.setData(True, Qt.ItemDataRole.UserRole + 2)
                                 item_status.setEditable(False)
                                 item_path.setEditable(False)
                                 root.appendRow([item_status, item_path])


                         if unstaged_status_char != ' ' and unstaged_status_char != '?':
                             status_text = status_codes
                             icon_char = unstaged_status_char
                             color = QColor("blue") if icon_char in 'M' else QColor("red") if icon_char in 'D' else None
                             root = self.unstage_root
                             if root:
                                 item_status = QStandardItem(status_text)
                                 item_path = QStandardItem(display_path)
                                 item_status.setIcon(self.STATUS_ICONS.get(icon_char, self.DEFAULT_ICON))
                                 if color:
                                     item_status.setForeground(color)
                                     item_path.setForeground(color)

                                 item_status.setToolTip(tooltip)
                                 item_path.setToolTip(tooltip)
                                 item_path.setData(file_path_data, Qt.ItemDataRole.UserRole + 1)
                                 item_path.setData(True, Qt.ItemDataRole.UserRole + 2)
                                 item_status.setEditable(False)
                                 item_path.setEditable(False)
                                 root.appendRow([item_status, item_path])

                except Exception as e:
                    logging.error(f"解析或处理状态行出错: '{line}' - {e}", exc_info=True)


        finally:
            self.endResetModel()
            self._update_root_counts()


    def _update_root_counts(self):
        """更新根节点显示的计数"""
        if self.staged_root: self.staged_root.setText(f"{STATUS_STAGED} ({self.staged_root.rowCount()})")
        if self.unstage_root: self.unstage_root.setText(f"{STATUS_UNSTAGED} ({self.unstage_root.rowCount()})")
        if self.untracked_root: self.untracked_root.setText(f"{STATUS_UNTRACKED} ({self.untracked_root.rowCount()})")
        if self.unmerged_root: self.unmerged_root.setText(f"{STATUS_UNMERGED} ({self.unmerged_root.rowCount()})")


    def get_files_in_section(self, section_type: str) -> list[str]:
        """获取指定区域下的所有文件真实路径 (去重)"""
        files = set()
        root_item: Optional[QStandardItem] = None

        if section_type == STATUS_STAGED: root_item = self.staged_root
        elif section_type == STATUS_UNSTAGED: root_item = self.unstage_root
        elif section_type == STATUS_UNTRACKED: root_item = self.untracked_root
        elif section_type == STATUS_UNMERGED: root_item = self.unmerged_root
        else:
            logging.warning(f"请求了无效的区段类型: {section_type}")
            return []

        if root_item:
            for row in range(root_item.rowCount()):
                path_item = root_item.child(row, 1)
                if path_item:
                    file_path = path_item.data(Qt.ItemDataRole.UserRole + 1)
                    if file_path:
                        files.add(file_path)
                    else:
                        logging.warning(f"区段 '{section_type}' 中行 {row} 的路径项缺少文件路径数据 (UserRole + 1)。")
        return list(files)


    def get_selected_files_data(self, selected_indices: List[QModelIndex]) -> Dict[str, List[str]]:
        """
        根据 QTreeView 中选中的索引列表，返回按状态分类的唯一文件路径列表。
        这是为了支持 MainWindow 中右键菜单和 Diff 显示的逻辑。
        """
        selected_files: Dict[str, Set[str]] = {
            STATUS_STAGED: set(),
            STATUS_UNSTAGED: set(),
            STATUS_UNTRACKED: set(),
            STATUS_UNMERGED: set()
        }
        processed_rows = set()

        for index in selected_indices:
            if not index.isValid(): continue

            if not index.parent().isValid(): continue

            row = index.row()
            parent_index = index.parent()

            parent_root_row = parent_index.row()
            row_tuple = (parent_root_row, row)
            if row_tuple in processed_rows:
                continue
            processed_rows.add(row_tuple)

            parent_item = self.itemFromIndex(parent_index)
            if not parent_item:
                logging.warning(f"无法从索引获取父项: {parent_index.row()}, {parent_index.column()}")
                continue

            path_item_index = self.index(row, 1, parent_index)
            path_item = self.itemFromIndex(path_item_index)
            if not path_item:
                logging.warning(f"找不到父项 '{parent_item.text()}' 下选中行 {row} 的路径项 (列 1)")
                continue

            file_path = path_item.data(Qt.ItemDataRole.UserRole + 1)
            is_file = path_item.data(Qt.ItemDataRole.UserRole + 2)

            if not is_file or not file_path:
                # It's a directory item or missing file path data, skip for file operations
                if not is_file: logging.debug(f"跳过目录项: {path_item.text()}")
                else: logging.warning(f"父项 '{parent_item.text()}' 下选中行 {row} 的路径项没有文件路径数据 (UserRole + 1)。")
                continue

            section_type = parent_item.data(Qt.ItemDataRole.UserRole)

            if section_type in selected_files:
                selected_files[section_type].add(file_path)
            else:
                 logging.warning(f"选中的文件所属区段类型未知: '{section_type}'. 路径: {file_path}")


        result = {key: list(value) for key, value in selected_files.items()}
        return result
