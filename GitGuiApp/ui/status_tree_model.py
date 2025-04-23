# ui/status_tree_model.py
import logging
import os
import re
from typing import Optional
from PyQt6.QtGui import QStandardItemModel, QStandardItem, QIcon, QColor, QFont
from PyQt6.QtCore import Qt, QObject
from PyQt6.QtWidgets import QApplication, QStyle

# 定义状态常量
STATUS_STAGED = "已暂存的更改"
STATUS_UNSTAGED = "未暂存的更改"
STATUS_UNTRACKED = "未跟踪的文件"
STATUS_UNMERGED = "未合并 (冲突)"


# 安全获取标准 Qt 图标或返回一个空的 QIcon
def get_standard_icon(icon_enum: QStyle.StandardPixmap, fallback_text="[ ]") -> QIcon:
    """安全获取标准 Qt 图标或返回一个空的 QIcon。"""
    try:
        app = QApplication.instance()
        if app:
            style = app.style()
            if style:
                icon = style.standardIcon(icon_enum)
                if not icon.isNull():
                    return icon
                else:
                    logging.warning(f"标准图标枚举 {icon_enum} 返回了空 QIcon。")
            else:
                 logging.warning(f"无法从 QApplication 获取样式对象以加载图标 {icon_enum}。")
        else:
             logging.warning(f"请求图标 {icon_enum} 时 QApplication 实例不可用。")
    except Exception as e:
        logging.warning(f"获取标准图标 {icon_enum} 时发生异常: {e}", exc_info=True)

    return QIcon()


# 将 Git 状态码映射到 Qt 标准像素图枚举
_STATUS_ICON_MAP = {
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

        self.STATUS_ICONS = {
            key: get_standard_icon(enum)
            for key, enum in _STATUS_ICON_MAP.items()
            if isinstance(key, str) and (len(key) == 1 or key in [STATUS_STAGED, STATUS_UNSTAGED, STATUS_UNTRACKED, STATUS_UNMERGED])
        }
        self.DEFAULT_ICON = get_standard_icon(_STATUS_ICON_MAP["DEFAULT"])

        # 修正: 移除 'X' 和 'Y'，因为它们不是单字符状态码
        expected_single_chars = "ACDMRTUX??" # 原始字符串
        expected_single_chars_corrected = "".join(c for c in expected_single_chars if c not in 'XY') # 移除 XY

        for char in expected_single_chars_corrected:
            if char not in self.STATUS_ICONS:
                logging.warning(f"状态字符 '{char}' 的图标未在映射中找到，使用默认图标。")
                self.STATUS_ICONS[char] = self.DEFAULT_ICON


        font = QFont()
        font.setBold(True)

        self.staged_root: Optional[QStandardItem] = QStandardItem(STATUS_STAGED)
        self.staged_root.setIcon(self.STATUS_ICONS.get(STATUS_STAGED, self.DEFAULT_ICON))
        self.staged_root.setData(STATUS_STAGED, Qt.ItemDataRole.UserRole)
        self.staged_root.setEditable(False)
        self.staged_root.setFont(font)

        self.unstage_root: Optional[QStandardItem] = QStandardItem(STATUS_UNSTAGED)
        self.unstage_root.setIcon(self.STATUS_ICONS.get(STATUS_UNSTAGED, self.DEFAULT_ICON))
        self.unstage_root.setData(STATUS_UNSTAGED, Qt.ItemDataRole.UserRole)
        self.unstage_root.setEditable(False)
        self.unstage_root.setFont(font)

        self.untracked_root: Optional[QStandardItem] = QStandardItem(STATUS_UNTRACKED)
        self.untracked_root.setIcon(self.STATUS_ICONS.get(STATUS_UNTRACKED, self.DEFAULT_ICON))
        self.untracked_root.setData(STATUS_UNTRACKED, Qt.ItemDataRole.UserRole)
        self.untracked_root.setEditable(False)
        self.untracked_root.setFont(font)

        self.unmerged_root: Optional[QStandardItem] = QStandardItem(STATUS_UNMERGED)
        self.unmerged_root.setIcon(self.STATUS_ICONS.get(STATUS_UNMERGED, self.DEFAULT_ICON))
        self.unmerged_root.setData(STATUS_UNMERGED, Qt.ItemDataRole.UserRole)
        self.unmerged_root.setEditable(False)
        self.unmerged_root.setFont(font)


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
        """解析 'git status --porcelain=v1' 的输出并填充模型 (带图标和颜色)"""
        self.clear_status()

        staged_count = 0
        unstage_count = 0
        untracked_count = 0
        unmerged_count = 0

        lines = porcelain_output.strip().splitlines()

        if not lines:
            logging.info("Git status porcelain 输出为空。")
            self._update_root_counts()
            return

        try:
            self.beginResetModel()

            for line in lines:
                if not line or len(line) < 3:
                    logging.warning(f"跳过无效的状态行: {repr(line)}")
                    continue

                try:
                    status_codes = line[:2]
                    path_part = line[3:]
                    original_path: Optional[str] = None
                    file_path = ""
                    display_path = ""

                    if status_codes[0] in ('R', 'C') or status_codes[1] in ('R', 'C'):
                        parts = path_part.split(' -> ', 1)
                        if len(parts) == 2:
                            original_path = parts[0].strip()
                            file_path = parts[1].strip()
                            display_path = f"{os.path.basename(file_path)} (从 {os.path.basename(original_path)})"
                        else:
                            file_path = path_part.strip()
                            display_path = file_path
                            logging.warning(f"无法正确解析重命名/复制格式: {repr(line)}")
                    else:
                        file_path = path_part.strip()
                        display_path = file_path

                    if file_path.startswith('"') and file_path.endswith('"'):
                        try:
                            file_path = file_path[1:-1].encode('latin-1', 'backslashreplace').decode('unicode_escape')
                            display_path = file_path
                        except Exception as decode_err:
                             logging.error(f"解码带引号路径 '{file_path}' 时出错: {decode_err}")

                    tooltip = f"状态: {status_codes}, 路径: {file_path}"
                    if original_path: tooltip += f", 原路径: {original_path}"


                    items_to_add = [] # 列表来存储 (status_code_disp, display_path_disp, file_path_data, icon_char, color_apply, tooltip_apply) 元组

                    # 未跟踪的文件 (??)
                    if status_codes == '??':
                        icon_char = '?'
                        color: Optional[QColor] = QColor("darkCyan")
                        items_to_add.append((status_codes, display_path, file_path, icon_char, color, tooltip))
                        untracked_count += 1


                    # 未合并 (冲突) (UU, AA, DD, AU, UD, UA, DU)
                    elif status_codes[0] == 'U' or status_codes[1] == 'U':
                         icon_char = 'U'
                         color = QColor('red')
                         items_to_add.append((status_codes, display_path, file_path, icon_char, color, tooltip))
                         unmerged_count += 1


                    # 同时有已暂存和未暂存更改 (X != ' ', Y != '?', 非冲突) (如 MM, MT, ...)
                    # 需要创建两行，分别添加到已暂存和未暂存区段
                    elif status_codes[0] != ' ' and status_codes[1] != '?':
                         # 已暂存区段
                         staged_icon_char = status_codes[0]
                         staged_color = QColor("darkGreen") if staged_icon_char in 'AC' else QColor("blue") if staged_icon_char in 'M' else QColor("red") if staged_icon_char in 'D' else QColor("purple")
                         items_to_add.append((status_codes, display_path, file_path, staged_icon_char, staged_color, tooltip))
                         staged_count += 1

                         # 未暂存区段
                         unstage_icon_char = status_codes[1]
                         unstage_color = QColor("blue") if unstage_icon_char in 'M' else QColor("red") if unstage_icon_char in 'D' else None
                         items_to_add.append((status_codes, display_path, file_path, unstage_icon_char, unstage_color, tooltip))
                         unstage_count += 1


                    # 仅已暂存更改 (X != ' ', Y = ' ')
                    elif status_codes[0] != ' ' and status_codes[1] == ' ':
                        icon_char = status_codes[0]
                        color = QColor("darkGreen") if icon_char in 'AC' else QColor("blue") if icon_char in 'M' else QColor("red") if icon_char in 'D' else QColor("purple")
                        items_to_add.append((status_codes, display_path, file_path, icon_char, color, tooltip))
                        staged_count += 1


                    # 仅未暂存更改 (X = ' ', Y != '?', Y != ' ')
                    elif status_codes[0] == ' ' and status_codes[1] != '?':
                         icon_char = status_codes[1]
                         color = QColor("blue") if icon_char in 'M' else QColor("red") if icon_char in 'D' else None
                         items_to_add.append((status_codes, display_path, file_path, icon_char, color, tooltip))
                         unstage_count += 1

                    # 未处理的未知状态
                    else:
                        logging.warning(f"未处理的 Git 状态行: {repr(line)}")
                        continue


                    # --- 添加项到模型 ---
                    for status_code_disp, display_path_disp, file_path_data, icon_char_apply, color_apply, tooltip_apply in items_to_add:
                         item_status_obj = QStandardItem(status_code_disp)
                         item_path_obj = QStandardItem(display_path_disp)

                         item_status_obj.setIcon(self.STATUS_ICONS.get(icon_char_apply, self.DEFAULT_ICON))
                         if color_apply:
                             item_status_obj.setForeground(color_apply)
                             item_path_obj.setForeground(color_apply)

                         item_status_obj.setToolTip(tooltip_apply)
                         item_path_obj.setToolTip(tooltip_apply)
                         item_path_obj.setData(file_path_data, Qt.ItemDataRole.UserRole + 1)
                         item_status_obj.setEditable(False)
                         item_path_obj.setEditable(False)
                         target_root = None
                         if status_code_disp == '??':
                             target_root = self.untracked_root
                         elif status_code_disp[0] == 'U' or status_code_disp[1] == 'U':
                             target_root = self.unmerged_root
                         elif icon_char_apply == status_code_disp[0] and status_code_disp[0] != ' ': 
                              target_root = self.staged_root
                         elif icon_char_apply == status_code_disp[1] and status_code_disp[1] != ' ':
                             target_root = self.unstage_root
                         if not target_root:
                             logging.warning(f"无法确定状态码 '{status_code_disp}' 的目标区段。")
                             continue 


                         target_root.appendRow([item_status_obj, item_path_obj])


                except Exception as e:
                    logging.error(f"解析或处理状态行出错: '{line}' - {e}", exc_info=True)
                    continue

        finally:
            self.endResetModel()


        self._update_root_counts()
        logging.info(f"状态已解析: 已暂存({staged_count}), 未暂存({unstage_count}), 未跟踪({untracked_count}), 未合并({unmerged_count})")


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
        if section_type == STATUS_STAGED and self.staged_root: root_item = self.staged_root
        elif section_type == STATUS_UNSTAGED and self.unstage_root: root_item = self.unstage_root
        elif section_type == STATUS_UNTRACKED and self.untracked_root: root_item = self.untracked_root
        elif section_type == STATUS_UNMERGED and self.unmerged_root: root_item = self.unmerged_root
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
                        logging.warning(f"区段 '{section_type}' 中行 {row} 的路径项缺少文件路径数据。")
        return list(files)


    def get_selected_files(self, selected_indices: list) -> dict[str, list[str]]:
        """
        根据 QTreeView 中选中的索引，返回按状态分类的唯一文件路径列表。
        返回: {'已暂存的更改': [...], '未暂存的更改': [...], '未跟踪的文件': [...], '未合并 (冲突)': [...]}
        """
        selected_files: dict[str, set[str]] = {
            STATUS_STAGED: set(),
            STATUS_UNSTAGED: set(),
            STATUS_UNTRACKED: set(),
            STATUS_UNMERGED: set()
        }
        processed_rows = set()

        for index in selected_indices:
            if not index.isValid(): continue

            row = index.row()
            parent_index = index.parent()
            if not parent_index.isValid(): continue

            row_tuple = (parent_index.row(), row)
            if row_tuple in processed_rows: continue
            processed_rows.add(row_tuple)

            parent_item = self.itemFromIndex(parent_index)
            if not parent_item: continue

            path_item_index = self.index(row, 1, parent_index)
            path_item = self.itemFromIndex(path_item_index)
            if not path_item:
                logging.warning(f"找不到父项 {parent_item.text()} 下选中行 {row} 的路径项")
                continue

            file_path = path_item.data(Qt.ItemDataRole.UserRole + 1)
            if not file_path:
                logging.warning(f"父项 {parent_item.text()} 下选中行 {row} 的路径项没有文件路径数据。")
                continue

            section_type = parent_item.data(Qt.ItemDataRole.UserRole)
            if section_type in selected_files:
                selected_files[section_type].add(file_path)
            else:
                 logging.warning(f"未知的区段类型 '{section_type}' 用于选中的文件。")


        result = {key: list(value) for key, value in selected_files.items()}
        logging.debug(f"选中的文件已分类: {result}")
        return result