# ui/status_tree_model.py
import logging
import os
import re
from PyQt6.QtGui import QStandardItemModel, QStandardItem, QIcon, QColor, QFont
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication, QStyle

# 定义状态常量
STATUS_STAGED = "已暂存的更改"
STATUS_UNSTAGED = "未暂存的更改"
STATUS_UNTRACKED = "未跟踪的文件"

# --- 使用标准 Qt 图标 ---

# 安全获取标准 Qt 图标或返回一个空的 QIcon
def get_standard_icon(icon_enum, fallback_text="[ ]"):
    """安全获取标准 Qt 图标或返回一个空的 QIcon。"""
    try:
        # 确保 QApplication 实例存在，然后才能访问样式
        app = QApplication.instance()
        if app:
            style = app.style()
            if style:
                icon = style.standardIcon(icon_enum)
                # 检查图标是否有效后再返回
                if not icon.isNull():
                    return icon
                else:
                    # 如果 standardIcon 返回空图标则记录警告
                    logging.warning(f"标准图标枚举 {icon_enum} 返回了空 QIcon。")
            else:
                 logging.warning(f"无法从 QApplication 获取样式对象以加载图标 {icon_enum}。")
        else:
            # 在 QObject/QWidget 上下文的 __init__ 中调用时，这种情况应该不太可能发生
             logging.warning(f"请求图标 {icon_enum} 时 QApplication 实例不可用。")
    except Exception as e:
        logging.warning(f"获取标准图标 {icon_enum} 时发生异常: {e}", exc_info=True)

    # 如果发生任何问题，回退到空 QIcon
    return QIcon()


# !!! FIX: 全局定义映射，但在 __init__ 中获取图标 !!!
# 将 Git 状态码映射到 Qt 标准 *像素图枚举* (还不是图标)
# 键表示在 git status --porcelain=v1 中看到的代码 (XY 格式)
# 如果一个文件既已暂存又未暂存，则优先显示最显著的状态对应的图标。
_STATUS_ICON_MAP = {
    # 先匹配确切的 XY，以确定优先级
    " M": QStyle.StandardPixmap.SP_DialogSaveButton,    # 已暂存 修改
    "MM": QStyle.StandardPixmap.SP_DialogSaveButton,    # 已暂存 修改 + 未暂存 修改 (显示修改)
    "AM": QStyle.StandardPixmap.SP_FileDialogNewFolder, # 已暂存 添加 + 未暂存 修改 (显示添加)
    "AD": QStyle.StandardPixmap.SP_MessageBoxWarning,   # 已暂存 添加 + 未暂存 删除 (显示警告)
    " D": QStyle.StandardPixmap.SP_TrashIcon,           # 已暂存 删除
    " R": QStyle.StandardPixmap.SP_FileDialogDetailedView, # 已暂存 重命名
    " C": QStyle.StandardPixmap.SP_FileDialogContentsView, # 已暂存 复制
    "UU": QStyle.StandardPixmap.SP_MessageBoxCritical, # 未合并 (冲突)
    "??": QStyle.StandardPixmap.SP_MessageBoxQuestion, # 未跟踪
    # 基于单字符的回退 (不太具体) - 使用空格区分索引/工作树
    " A": QStyle.StandardPixmap.SP_FileDialogNewFolder, # 添加 (仅已暂存)
    "M ": QStyle.StandardPixmap.SP_DialogSaveButton,    # 修改 (仅未暂存) - 与已暂存 修改 使用相同图标
    "D ": QStyle.StandardPixmap.SP_TrashIcon,           # 删除 (仅未暂存) - 与已暂存 删除 使用相同图标
    # 根节点
    STATUS_STAGED: QStyle.StandardPixmap.SP_DialogYesButton,
    STATUS_UNSTAGED: QStyle.StandardPixmap.SP_DialogNoButton,
    STATUS_UNTRACKED: QStyle.StandardPixmap.SP_FileDialogInfoView,
    # 默认回退图标
    "DEFAULT": QStyle.StandardPixmap.SP_FileIcon,
}

class StatusTreeModel(QStandardItemModel):
    """管理 Git 状态树视图的模型和数据解析"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setHorizontalHeaderLabels(["状态", "文件路径"])

        # !!! FIX: 在此处使用全局映射获取图标 !!!
        self.STATUS_ICONS = {
            key: get_standard_icon(enum) for key, enum in _STATUS_ICON_MAP.items() if key != "DEFAULT"
        }
        self.DEFAULT_ICON = get_standard_icon(_STATUS_ICON_MAP["DEFAULT"])
        # 如果需要，在类中添加回退逻辑，例如确保键存在
        for key in _STATUS_ICON_MAP.keys():
            if key not in self.STATUS_ICONS and key != "DEFAULT":
                logging.warning(f"状态键 '{key}' 的图标无法加载。")
                self.STATUS_ICONS[key] = self.DEFAULT_ICON # 如果加载失败则使用默认图标


        # 创建顶层节点 (文件夹)，带有图标和粗体字体
        font = QFont()
        font.setBold(True)

        self.staged_root = QStandardItem(STATUS_STAGED)
        self.staged_root.setIcon(self.STATUS_ICONS.get(STATUS_STAGED, self.DEFAULT_ICON))
        self.staged_root.setData(STATUS_STAGED, Qt.ItemDataRole.UserRole)
        self.staged_root.setEditable(False)
        self.staged_root.setFont(font)

        self.unstage_root = QStandardItem(STATUS_UNSTAGED)
        self.unstage_root.setIcon(self.STATUS_ICONS.get(STATUS_UNSTAGED, self.DEFAULT_ICON))
        self.unstage_root.setData(STATUS_UNSTAGED, Qt.ItemDataRole.UserRole)
        self.unstage_root.setEditable(False)
        self.unstage_root.setFont(font)

        self.untracked_root = QStandardItem(STATUS_UNTRACKED)
        self.untracked_root.setIcon(self.STATUS_ICONS.get(STATUS_UNTRACKED, self.DEFAULT_ICON))
        self.untracked_root.setData(STATUS_UNTRACKED, Qt.ItemDataRole.UserRole)
        self.untracked_root.setEditable(False)
        self.untracked_root.setFont(font)

        # 使用 invisibleRootItem() 将根项添加到模型
        # 为根节点的第二列添加占位符项
        self.invisibleRootItem().appendRow([self.staged_root, QStandardItem()])
        self.invisibleRootItem().appendRow([self.unstage_root, QStandardItem()])
        self.invisibleRootItem().appendRow([self.untracked_root, QStandardItem()])

        # 如果需要，确保占位符项不可编辑/不可选择
        for i in range(self.invisibleRootItem().rowCount()):
            placeholder_item = self.invisibleRootItem().child(i, 1)
            if placeholder_item:
                placeholder_item.setEditable(False)
                placeholder_item.setSelectable(False)


    def clear_status(self):
        """清空所有状态，保留根节点"""
        # 在尝试移除行之前检查根节点是否存在
        if self.staged_root: self.staged_root.removeRows(0, self.staged_root.rowCount())
        if self.unstage_root: self.unstage_root.removeRows(0, self.unstage_root.rowCount())
        if self.untracked_root: self.untracked_root.removeRows(0, self.untracked_root.rowCount())
        self._update_root_counts() # 即使在清空时也更新计数


    def parse_and_populate(self, porcelain_output: str):
        """解析 'git status --porcelain=v1' 的输出并填充模型 (带图标)"""
        self.clear_status() # 从空根节点开始

        staged_count = 0
        unstage_count = 0
        untracked_count = 0
        lines = porcelain_output.strip().splitlines()

        if not lines:
            logging.info("Git status porcelain 输出为空。")
            self._update_root_counts() # 确保计数为 0
            return

        # 使用列表以便稍后批量添加项 (微小优化)
        items_to_add = {STATUS_STAGED: [], STATUS_UNSTAGED: [], STATUS_UNTRACKED: []}

        for line in lines:
            if not line or len(line) < 3: # 至少需要 XY 和空格
                logging.warning(f"跳过无效的状态行: {repr(line)}")
                continue
            try:
                status_codes = line[:2] # XY 代码
                path_part = line[3:]    # 'XY ' 后面的路径部分
                original_path = None
                file_path = ""
                display_path = ""

                # 先处理重命名/复制 (索引或工作树中的 R/C)
                if status_codes[0] in ('R', 'C') or status_codes[1] in ('R', 'C'):
                    # 格式为 'XY <原始> -> <新>'
                    parts = path_part.split(' -> ', 1)
                    if len(parts) == 2:
                        original_path = parts[0].strip()
                        file_path = parts[1].strip()
                        # 改进重命名/复制的显示
                        display_path = f"{file_path} (从 {os.path.basename(original_path)})"
                    else:
                        # 如果格式异常则回退
                        file_path = path_part.strip()
                        display_path = file_path
                        logging.warning(f"无法正确解析重命名/复制格式: {repr(line)}")
                else:
                    # 普通情况
                    file_path = path_part.strip()
                    display_path = file_path

                # 处理带引号的路径 (Git 输出带有特殊字符的路径时使用引号)
                # 这使用了一个简单的方法，对于内部转义的引号可能需要改进。
                if file_path.startswith('"') and file_path.endswith('"'):
                    try:
                        # 使用推荐的转义序列处理进行解码
                        file_path = file_path[1:-1].encode('latin-1', 'backslashreplace').decode('unicode_escape')
                        # 如果需要，对显示路径应用相同的解码，或者直接使用 file_path
                        display_path = file_path # 也对显示使用未转义的路径
                    except Exception as decode_err:
                         logging.error(f"解码带引号路径 '{file_path}' 时出错: {decode_err}")
                         # 回退到原始带引号的路径
                         file_path = file_path[1:-1]
                         display_path = file_path


                # 根据组合状态 XY 确定图标和提示信息
                # 优先使用已加载图标中的确切 XY 匹配
                icon = self.STATUS_ICONS.get(status_codes, self.DEFAULT_ICON)

                # 如果没有确切的 XY 匹配，尝试基于单个 X 或 Y 进行回退
                if icon == self.DEFAULT_ICON and status_codes != '??': # 不回退未跟踪文件
                    staged_icon = self.STATUS_ICONS.get(status_codes[0] + " ", None) # 检查 X 状态 (例如，'M ')
                    unstaged_icon = self.STATUS_ICONS.get(" " + status_codes[1], None) # 检查 Y 状态 (例如，' M')
                    # 优先使用已暂存图标，然后是未暂存，然后是默认
                    icon = staged_icon or unstaged_icon or self.DEFAULT_ICON

                tooltip = f"状态: {status_codes}, 路径: {file_path}"
                if original_path: tooltip += f", 原路径: {original_path}"

                # 为冲突设置颜色
                color = None
                if status_codes == 'UU':
                    color = QColor('red') # 突出显示冲突

                # --- 创建 QStandardItem ---
                # 状态项 (列 0)
                item_status = QStandardItem(status_codes)
                item_status.setIcon(icon)
                item_status.setToolTip(tooltip)
                item_status.setEditable(False)
                if color: item_status.setForeground(color)

                # 路径项 (列 1)
                item_path = QStandardItem(display_path)
                item_path.setData(file_path, Qt.ItemDataRole.UserRole + 1) # 存储真实、未加引号的路径以进行操作
                item_path.setToolTip(tooltip)
                item_path.setEditable(False)
                if color: item_path.setForeground(color)


                # --- 将项添加到正确的区段列表 ---
                added_to_section = False # 标志，用于跟踪是否已添加到任何区段

                # 1. 未跟踪的文件
                if status_codes == '??':
                    item_path.setData("??", Qt.ItemDataRole.UserRole + 4) # 标记特定类型
                    items_to_add[STATUS_UNTRACKED].append([item_status, item_path])
                    untracked_count += 1
                    added_to_section = True

                # 2. 未合并/冲突
                elif status_codes == 'UU':
                    # 主要显示在未暂存中，但也表示两者的变化
                    item_path.setData("UU", Qt.ItemDataRole.UserRole + 3) # 标记特定类型 (未暂存视图)
                    items_to_add[STATUS_UNSTAGED].append([item_status, item_path])
                    unstage_count += 1
                    added_to_section = True
                    # 同时也在已暂存中添加一个表示 (因为索引有 'U')
                    item_path_staged_copy = item_path.clone()
                    item_status_staged_copy = item_status.clone()
                    item_path_staged_copy.setData(" U", Qt.ItemDataRole.UserRole + 2) # 标记特定类型 (已暂存视图)
                    items_to_add[STATUS_STAGED].append([item_status_staged_copy, item_path_staged_copy])
                    staged_count += 1
                    # 注意: 对于 UU 文件，计数可能会加倍，如果需要可以调整，但在两个区段中显示是正确的。

                # 3. 已暂存 / 未暂存的更改 (常规情况)
                else:
                    # 检查已暂存状态 (索引 - 第一个字符 X)
                    if status_codes[0] != ' ':
                        # 如果文件需要在两个区段中都出现，则创建克隆
                        if status_codes[1] != ' ':
                            item_path_staged_copy = item_path.clone()
                            item_status_staged_copy = item_status.clone()
                        else: # 仅已暂存更改，使用原始项
                            item_path_staged_copy = item_path
                            item_status_staged_copy = item_status

                        item_path_staged_copy.setData(status_codes[0], Qt.ItemDataRole.UserRole + 2) # 用已暂存代码标记
                        items_to_add[STATUS_STAGED].append([item_status_staged_copy, item_status_staged_copy, item_path_staged_copy]) # Fix: Added item_status_staged_copy twice, should be [item_status_staged_copy, item_path_staged_copy]
                        staged_count += 1
                        added_to_section = True

                    # 检查未暂存状态 (工作树 - 第二个字符 Y)
                    if status_codes[1] != ' ':
                        # 如果仅未暂存则使用原始项，如果已添加到已暂存则克隆
                        if status_codes[0] != ' ':
                             item_path_unstaged_copy = item_path.clone()
                             item_status_unstaged_copy = item_status.clone()
                        else: # 仅未暂存更改
                             item_path_unstaged_copy = item_path
                             item_status_unstaged_copy = item_status

                        item_path_unstaged_copy.setData(status_codes[1], Qt.ItemDataRole.UserRole + 3) # 用未暂存代码标记
                        items_to_add[STATUS_UNSTAGED].append([item_status_unstaged_copy, item_path_unstaged_copy])
                        unstage_count += 1
                        added_to_section = True

                if not added_to_section:
                    logging.warning(f"状态行未匹配任何区段: {repr(line)}")

            except Exception as e:
                logging.error(f"解析状态行出错: '{line}' - {e}", exc_info=True)
                continue # 出错时跳到下一行

        # --- 批量将项追加到模型 ---
        self.beginResetModel() # 发出重大更改开始的信号 (可能有点过度)
        try:
            if self.staged_root:
                for item_pair in items_to_add[STATUS_STAGED]:
                    self.staged_root.appendRow(item_pair)
            if self.unstage_root:
                for item_pair in items_to_add[STATUS_UNSTAGED]:
                    self.unstage_root.appendRow(item_pair)
            if self.untracked_root:
                for item_pair in items_to_add[STATUS_UNTRACKED]:
                    self.untracked_root.appendRow(item_pair)
        finally:
            self.endResetModel() # 发出重大更改结束的信号

        self._update_root_counts() # 添加所有项后更新计数
        logging.info(f"状态已解析: 已暂存({staged_count}), 未暂存({unstage_count}), 未跟踪({untracked_count})")


    def _update_root_counts(self):
        """更新根节点显示的计数"""
        # 在设置文本之前检查根节点是否存在
        if self.staged_root: self.staged_root.setText(f"{STATUS_STAGED} ({self.staged_root.rowCount()})")
        if self.unstage_root: self.unstage_root.setText(f"{STATUS_UNSTAGED} ({self.unstage_root.rowCount()})")
        if self.untracked_root: self.untracked_root.setText(f"{STATUS_UNTRACKED} ({self.untracked_root.rowCount()})")


    def get_files_in_section(self, section_type: str) -> list[str]:
        """获取指定区域下的所有文件真实路径 (去重)"""
        files = set()
        root_item = None
        if section_type == STATUS_STAGED and self.staged_root: root_item = self.staged_root
        elif section_type == STATUS_UNSTAGED and self.unstage_root: root_item = self.unstage_root
        elif section_type == STATUS_UNTRACKED and self.untracked_root: root_item = self.untracked_root
        else:
            logging.warning(f"请求了无效的区段类型: {section_type}")
            return []

        if root_item:
            for row in range(root_item.rowCount()):
                # 获取路径项 (列 1)
                path_item = root_item.child(row, 1)
                if path_item:
                    # 从 UserRole+1 获取路径
                    file_path = path_item.data(Qt.ItemDataRole.UserRole + 1)
                    if file_path:
                        files.add(file_path)
                    else:
                        logging.warning(f"区段 '{section_type}' 中行 {row} 的路径项缺少文件路径数据。")
        return list(files)


    def get_selected_files(self, selected_indexes) -> dict[str, list[str]]:
        """
        根据 QTreeView 中选中的索引，返回按状态分类的唯一文件路径列表。
        返回: {'已暂存的更改': [...], '未暂存的更改': [...], '未跟踪的文件': [...]}
        """
        selected_files = { STATUS_STAGED: set(), STATUS_UNSTAGED: set(), STATUS_UNTRACKED: set() }
        processed_rows = set() # 跟踪已处理的行，以避免多列选择造成的重复

        for index in selected_indexes:
            if not index.isValid(): continue

            row = index.row()
            parent_index = index.parent() # 父项 (例如，staged_root) 的索引
            if not parent_index.isValid(): continue # 如果它本身是根节点或无效则跳过

            # 检查是否已经通过另一列的索引处理过此行
            row_tuple = (parent_index, row)
            if row_tuple in processed_rows: continue
            processed_rows.add(row_tuple)

            parent_item = self.itemFromIndex(parent_index)
            if not parent_item: continue

             # 从此行的列 1 获取路径项
            path_item_index = self.index(row, 1, parent_index)
            path_item = self.itemFromIndex(path_item_index)
            if not path_item:
                logging.warning(f"找不到父项 {parent_item.text()} 下选中行 {row} 的路径项")
                continue

            file_path = path_item.data(Qt.ItemDataRole.UserRole + 1)
            if not file_path:
                logging.warning(f"父项 {parent_item.text()} 下选中行 {row} 的路径项没有文件路径数据。")
                continue

            # 确定区段并添加唯一路径
            section_type = parent_item.data(Qt.ItemDataRole.UserRole)
            if section_type == STATUS_STAGED:
                selected_files[STATUS_STAGED].add(file_path)
            elif section_type == STATUS_UNSTAGED:
                selected_files[STATUS_UNSTAGED].add(file_path)
            elif section_type == STATUS_UNTRACKED:
                selected_files[STATUS_UNTRACKED].add(file_path)

        # 将集合转换回列表作为返回值
        result = {key: list(value) for key, value in selected_files.items()}
        logging.debug(f"选中的文件已分类: {result}")
        return result