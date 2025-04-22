# ui/status_tree_model.py
import logging
import os
import re
from PyQt6.QtGui import QStandardItemModel, QStandardItem, QIcon, QColor, QFont
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication, QStyle

# 定义状态常量
STATUS_STAGED = "Staged Changes"
STATUS_UNSTAGED = "Unstaged Changes"
STATUS_UNTRACKED = "Untracked Files"

# --- Use Standard Qt Icons ---

# Helper function to get standard icons gracefully
def get_standard_icon(icon_enum, fallback_text="[ ]"):
    """Safely get a standard Qt icon or return an empty QIcon."""
    try:
        # Ensure QApplication instance exists before accessing style
        app = QApplication.instance()
        if app:
            style = app.style()
            if style:
                icon = style.standardIcon(icon_enum)
                # Check if the icon is valid before returning
                if not icon.isNull():
                    return icon
                else:
                    # Log if standardIcon returned a null icon
                    logging.warning(f"Got null QIcon for standard icon enum {icon_enum}.")
            else:
                 logging.warning(f"Could not get style object from QApplication to load icon {icon_enum}.")
        else:
            # This case should be less likely if called from __init__ of a QObject/QWidget context
             logging.warning(f"QApplication instance not available when requesting icon {icon_enum}.")
    except Exception as e:
        logging.warning(f"Exception getting standard icon {icon_enum}: {e}", exc_info=True)

    # Fallback to an empty QIcon if any issue occurs
    return QIcon()


# !!! FIX: Define the mapping globally, but fetch icons in __init__ !!!
# Map Git status codes to Qt standard *Pixmap Enums* (not icons yet)
# Key represents the code as seen in git status --porcelain=v1 (XY format)
# Prioritize the most significant status for the icon if a file is both staged and unstaged.
_STATUS_ICON_MAP = {
    # Exact XY matches first for priority
    " M": QStyle.StandardPixmap.SP_DialogSaveButton,    # Staged Modified
    "MM": QStyle.StandardPixmap.SP_DialogSaveButton,    # Staged Modified + Unstaged Modified (Show modified)
    "AM": QStyle.StandardPixmap.SP_FileDialogNewFolder, # Staged Added + Unstaged Modified (Show added)
    "AD": QStyle.StandardPixmap.SP_MessageBoxWarning,   # Staged Added + Unstaged Deleted (Show warning)
    " D": QStyle.StandardPixmap.SP_TrashIcon,           # Staged Deleted
    " R": QStyle.StandardPixmap.SP_FileDialogDetailedView, # Staged Renamed
    " C": QStyle.StandardPixmap.SP_FileDialogContentsView, # Staged Copied
    "UU": QStyle.StandardPixmap.SP_MessageBoxCritical, # Unmerged (Conflict)
    "??": QStyle.StandardPixmap.SP_MessageBoxQuestion, # Untracked
    # Fallbacks based on single char (less specific) - Use space for index/worktree distinction
    " A": QStyle.StandardPixmap.SP_FileDialogNewFolder, # Added (only staged)
    "M ": QStyle.StandardPixmap.SP_DialogSaveButton,    # Modified (only unstaged) - Use same as staged M
    "D ": QStyle.StandardPixmap.SP_TrashIcon,           # Deleted (only unstaged) - Use same as staged D
    # Root nodes
    STATUS_STAGED: QStyle.StandardPixmap.SP_DialogYesButton,
    STATUS_UNSTAGED: QStyle.StandardPixmap.SP_DialogNoButton,
    STATUS_UNTRACKED: QStyle.StandardPixmap.SP_FileDialogInfoView,
    # Default fallback Icon
    "DEFAULT": QStyle.StandardPixmap.SP_FileIcon,
}

class StatusTreeModel(QStandardItemModel):
    """管理 Git 状态树视图的模型和数据解析"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setHorizontalHeaderLabels(["Status", "File Path"])

        # !!! FIX: Fetch icons here using the global map !!!
        self.STATUS_ICONS = {
            key: get_standard_icon(enum) for key, enum in _STATUS_ICON_MAP.items() if key != "DEFAULT"
        }
        self.DEFAULT_ICON = get_standard_icon(_STATUS_ICON_MAP["DEFAULT"])
        # Add fallback logic within the class if needed, e.g., ensure keys exist
        for key in _STATUS_ICON_MAP.keys():
            if key not in self.STATUS_ICONS and key != "DEFAULT":
                logging.warning(f"Icon for status key '{key}' could not be loaded.")
                self.STATUS_ICONS[key] = self.DEFAULT_ICON # Use default if loading failed


        # 创建顶层节点 (文件夹) with icons and bold font
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

        # Add root items to the model using invisibleRootItem()
        # Add placeholder item for the second column of root nodes
        self.invisibleRootItem().appendRow([self.staged_root, QStandardItem()])
        self.invisibleRootItem().appendRow([self.unstage_root, QStandardItem()])
        self.invisibleRootItem().appendRow([self.untracked_root, QStandardItem()])

        # Ensure the placeholder items are not editable/selectable if needed
        for i in range(self.invisibleRootItem().rowCount()):
            placeholder_item = self.invisibleRootItem().child(i, 1)
            if placeholder_item:
                placeholder_item.setEditable(False)
                placeholder_item.setSelectable(False)


    def clear_status(self):
        """清空所有状态，保留根节点"""
        # Check if root items exist before trying to remove rows
        if self.staged_root: self.staged_root.removeRows(0, self.staged_root.rowCount())
        if self.unstage_root: self.unstage_root.removeRows(0, self.unstage_root.rowCount())
        if self.untracked_root: self.untracked_root.removeRows(0, self.untracked_root.rowCount())
        self._update_root_counts() # Update counts even when clearing


    def parse_and_populate(self, porcelain_output: str):
        """解析 'git status --porcelain=v1' 的输出并填充模型 (with icons)"""
        self.clear_status() # Start with empty roots

        staged_count = 0
        unstage_count = 0
        untracked_count = 0
        lines = porcelain_output.strip().splitlines()

        if not lines:
            logging.info("Git status porcelain output is empty.")
            self._update_root_counts() # Ensure counts are 0
            return

        # Use lists to batch add items later (minor optimization)
        items_to_add = {STATUS_STAGED: [], STATUS_UNSTAGED: [], STATUS_UNTRACKED: []}

        for line in lines:
            if not line or len(line) < 3: # Need at least XY and space
                logging.warning(f"Skipping invalid status line: {repr(line)}")
                continue
            try:
                status_codes = line[:2] # XY codes
                path_part = line[3:]    # Path part after 'XY '
                original_path = None
                file_path = ""
                display_path = ""

                # Handle renames/copies first (R/C in index or worktree)
                if status_codes[0] in ('R', 'C') or status_codes[1] in ('R', 'C'):
                    # Format is 'XY <original> -> <new>'
                    parts = path_part.split(' -> ', 1)
                    if len(parts) == 2:
                        original_path = parts[0].strip()
                        file_path = parts[1].strip()
                        # Improve display for renames/copies
                        display_path = f"{file_path} (从 {os.path.basename(original_path)})"
                    else:
                        # Fallback if format is unexpected
                        file_path = path_part.strip()
                        display_path = file_path
                        logging.warning(f"Could not parse rename/copy format correctly: {repr(line)}")
                else:
                    # Normal case
                    file_path = path_part.strip()
                    display_path = file_path

                # Handle paths with quotes (Git outputs paths with special chars in quotes)
                # This uses a simple approach, might need refinement for escaped quotes inside.
                if file_path.startswith('"') and file_path.endswith('"'):
                    try:
                        # Decode using recommended escape sequence handling
                        file_path = file_path[1:-1].encode('latin-1', 'backslashreplace').decode('unicode_escape')
                        # Apply same decoding to display path if needed, or just use file_path
                        display_path = file_path # Use unescaped path for display too
                    except Exception as decode_err:
                         logging.error(f"Error decoding quoted path '{file_path}': {decode_err}")
                         # Keep original quoted path as fallback
                         file_path = file_path[1:-1]
                         display_path = file_path


                # Determine icon and tooltip based on combined status XY
                # Prioritize exact XY match from the loaded icons
                icon = self.STATUS_ICONS.get(status_codes, self.DEFAULT_ICON)

                # If no exact XY match, try fallback based on individual X or Y
                if icon == self.DEFAULT_ICON and status_codes != '??': # Don't fallback for untracked
                    staged_icon = self.STATUS_ICONS.get(status_codes[0] + " ", None) # Check X status (e.g., 'M ')
                    unstaged_icon = self.STATUS_ICONS.get(" " + status_codes[1], None) # Check Y status (e.g., ' M')
                    # Prioritize staged icon, then unstaged, then default
                    icon = staged_icon or unstaged_icon or self.DEFAULT_ICON

                tooltip = f"状态: {status_codes}, 路径: {file_path}"
                if original_path: tooltip += f", 原路径: {original_path}"

                # Set color for conflicts
                color = None
                if status_codes == 'UU':
                    color = QColor('red') # Highlight conflicts

                # --- Create QStandardItems ---
                # Status Item (Column 0)
                item_status = QStandardItem(status_codes)
                item_status.setIcon(icon)
                item_status.setToolTip(tooltip)
                item_status.setEditable(False)
                if color: item_status.setForeground(color)

                # Path Item (Column 1)
                item_path = QStandardItem(display_path)
                item_path.setData(file_path, Qt.ItemDataRole.UserRole + 1) # Store real, unquoted path for actions
                item_path.setToolTip(tooltip)
                item_path.setEditable(False)
                if color: item_path.setForeground(color)


                # --- Add items to the correct section list ---
                added_to_section = False # Flag to track if added anywhere

                # 1. Untracked Files
                if status_codes == '??':
                    item_path.setData("??", Qt.ItemDataRole.UserRole + 4) # Mark specific type
                    items_to_add[STATUS_UNTRACKED].append([item_status, item_path])
                    untracked_count += 1
                    added_to_section = True

                # 2. Unmerged/Conflicts
                elif status_codes == 'UU':
                    # Show primarily in Unstaged, but represents changes in both
                    item_path.setData("UU", Qt.ItemDataRole.UserRole + 3) # Mark specific type (Unstaged view)
                    items_to_add[STATUS_UNSTAGED].append([item_status, item_path])
                    unstage_count += 1
                    added_to_section = True
                    # Also add a representation to Staged (as index has 'U')
                    item_path_staged_copy = item_path.clone()
                    item_status_staged_copy = item_status.clone()
                    item_path_staged_copy.setData(" U", Qt.ItemDataRole.UserRole + 2) # Mark specific type (Staged view)
                    items_to_add[STATUS_STAGED].append([item_status_staged_copy, item_path_staged_copy])
                    staged_count += 1
                    # Note: Counts might double for UU files, adjust if needed, but showing in both sections is correct.

                # 3. Staged / Unstaged Changes (Regular cases)
                else:
                    # Check Staged status (Index - first char X)
                    if status_codes[0] != ' ':
                        # Create clones if the file needs to appear in both sections
                        if status_codes[1] != ' ':
                            item_path_staged_copy = item_path.clone()
                            item_status_staged_copy = item_status.clone()
                        else: # Only staged change, use original items
                            item_path_staged_copy = item_path
                            item_status_staged_copy = item_status

                        item_path_staged_copy.setData(status_codes[0], Qt.ItemDataRole.UserRole + 2) # Mark with staged code
                        items_to_add[STATUS_STAGED].append([item_status_staged_copy, item_path_staged_copy])
                        staged_count += 1
                        added_to_section = True

                    # Check Unstaged status (Worktree - second char Y)
                    if status_codes[1] != ' ':
                        # Use original items if only unstaged, or clone if already added to staged
                        if status_codes[0] != ' ':
                             item_path_unstaged_copy = item_path.clone()
                             item_status_unstaged_copy = item_status.clone()
                        else: # Only unstaged change
                             item_path_unstaged_copy = item_path
                             item_status_unstaged_copy = item_status

                        item_path_unstaged_copy.setData(status_codes[1], Qt.ItemDataRole.UserRole + 3) # Mark with unstaged code
                        items_to_add[STATUS_UNSTAGED].append([item_status_unstaged_copy, item_path_unstaged_copy])
                        unstage_count += 1
                        added_to_section = True

                if not added_to_section:
                    logging.warning(f"Status line did not match any section: {repr(line)}")

            except Exception as e:
                logging.error(f"Error parsing status line: '{line}' - {e}", exc_info=True)
                continue # Skip to next line on error

        # --- Batch append items to the model ---
        self.beginResetModel() # Signal start of major change (might be overkill)
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
            self.endResetModel() # Signal end of major change

        self._update_root_counts() # Update counts after adding all items
        logging.info(f"Status parsed: Staged({staged_count}), Unstaged({unstage_count}), Untracked({untracked_count})")


    def _update_root_counts(self):
        """更新根节点显示的计数"""
        # Check root items exist before setting text
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
            logging.warning(f"Invalid section type requested: {section_type}")
            return []

        if root_item:
            for row in range(root_item.rowCount()):
                # Get path item (column 1)
                path_item = root_item.child(row, 1)
                if path_item:
                    # Retrieve path from UserRole+1
                    file_path = path_item.data(Qt.ItemDataRole.UserRole + 1)
                    if file_path:
                        files.add(file_path)
                    else:
                        logging.warning(f"Path item in section '{section_type}', row {row} is missing file path data.")
        return list(files)


    def get_selected_files(self, selected_indexes) -> dict[str, list[str]]:
        """
        根据 QTreeView 中选中的索引，返回按状态分类的唯一文件路径列表。
        返回: {'Staged Changes': [...], 'Unstaged Changes': [...], 'Untracked Files': [...]}
        """
        selected_files = { STATUS_STAGED: set(), STATUS_UNSTAGED: set(), STATUS_UNTRACKED: set() }
        processed_rows = set() # Keep track of rows processed to avoid duplicates from multi-column selection

        for index in selected_indexes:
            if not index.isValid(): continue

            row = index.row()
            parent_index = index.parent() # Index of the parent item (e.g., staged_root)
            if not parent_index.isValid(): continue # Skip if it's a root node itself or invalid

            # Check if we already processed this row via another column's index
            row_tuple = (parent_index, row)
            if row_tuple in processed_rows: continue
            processed_rows.add(row_tuple)

            parent_item = self.itemFromIndex(parent_index)
            if not parent_item: continue

             # Get the path item from column 1 of this row
            path_item_index = self.index(row, 1, parent_index)
            path_item = self.itemFromIndex(path_item_index)
            if not path_item:
                logging.warning(f"Could not find path item for selected row {row} under parent {parent_item.text()}")
                continue

            file_path = path_item.data(Qt.ItemDataRole.UserRole + 1)
            if not file_path:
                logging.warning(f"Path item for selected row {row} under parent {parent_item.text()} has no file path data.")
                continue

            # Determine section and add the unique path
            section_type = parent_item.data(Qt.ItemDataRole.UserRole)
            if section_type == STATUS_STAGED:
                selected_files[STATUS_STAGED].add(file_path)
            elif section_type == STATUS_UNSTAGED:
                selected_files[STATUS_UNSTAGED].add(file_path)
            elif section_type == STATUS_UNTRACKED:
                selected_files[STATUS_UNTRACKED].add(file_path)

        # Convert sets back to lists for the return value
        result = {key: list(value) for key, value in selected_files.items()}
        logging.debug(f"Selected files categorized: {result}")
        return result