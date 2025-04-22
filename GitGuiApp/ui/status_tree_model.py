import logging
import os
import re # Import re for parsing paths and log graphs
from PyQt6.QtGui import QStandardItemModel, QStandardItem, QIcon, QColor, QFont
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication, QStyle


# 定义状态常量
STATUS_STAGED = "Staged Changes"
STATUS_UNSTAGED = "Unstaged Changes"
STATUS_UNTRACKED = "Untracked Files"


# Helper function to get standard icons gracefully
def get_standard_icon(icon_enum, fallback_text="[ ]"):
    """Safely get a standard Qt icon or return an empty QIcon."""
    try:
        app = QApplication.instance()
        # Check if app and style are available
        if app and app.style():
            icon = app.style().standardIcon(icon_enum)
            if not icon.isNull():
                return icon
            # If icon is null but app/style exist, maybe the enum is not supported?
            logging.debug(f"Standard icon {icon_enum} is null.") # Debug instead of warning, might be normal
        else:
             # This warning indicates the function was called before the GUI environment was fully ready
             logging.warning(f"Could not get standard icon {icon_enum} (QApplication or Style unavailable?)")

    except Exception as e:
        # Catch any other unexpected errors during icon retrieval
        logging.warning(f"Exception getting standard icon {icon_enum}: {e}")

    return QIcon() # Fallback to empty icon


# Map Git status codes to Qt standard icons
# Key represents the code as seen in git status --porcelain=v1 (XY format)
# We prioritize the most significant status for the icon if a file is both staged and unstaged.
# Using common standard pixmaps. Find their enum values in Qt documentation (e.g., enum QStyle::StandardPixmap)
STATUS_ICONS = {
    # Exact XY matches first for priority
    " M": get_standard_icon(QStyle.StandardPixmap.SP_DialogSaveButton),    # Staged Modified
    "MM": get_standard_icon(QStyle.StandardPixmap.SP_DialogSaveButton),    # Staged Modified + Unstaged Modified (Show modified)
    "AM": get_standard_icon(QStyle.StandardPixmap.SP_FileDialogNewFolder), # Staged Added + Unstaged Modified (Show added)
    "AD": get_standard_icon(QStyle.StandardPixmap.SP_MessageBoxWarning),   # Staged Added + Unstaged Deleted (Show warning/conflict-like)
    " D": get_standard_icon(QStyle.StandardPixmap.SP_TrashIcon),           # Staged Deleted
    " R": get_standard_icon(QStyle.StandardPixmap.SP_FileDialogDetailedView), # Staged Renamed
    " C": get_standard_icon(QStyle.StandardPixmap.SP_FileDialogContentsView), # Staged Copied
    "UU": get_standard_icon(QStyle.StandardPixmap.SP_MessageBoxCritical), # Unmerged (Conflict)
    "??": get_standard_icon(QStyle.StandardPixmap.SP_MessageBoxQuestion), # Untracked

    # Fallbacks based on single char (less specific) - Use space for index/worktree distinction
    # These are mostly covered by XY, but good to have explicit single char keys
    "A ": get_standard_icon(QStyle.StandardPixmap.SP_FileDialogNewFolder), # Added (only worktree) - unlikely in porcelain v1 unless git add -N
    "M ": get_standard_icon(QStyle.StandardPixmap.SP_DialogSaveButton),    # Modified (only worktree)
    "D ": get_standard_icon(QStyle.StandardPixmap.SP_TrashIcon),           # Deleted (only worktree)
    " U": get_standard_icon(QStyle.StandardPixmap.SP_MessageBoxWarning),   # Unmerged (index U) - conflicts

    # Root nodes icons
    STATUS_STAGED: get_standard_icon(QStyle.StandardPixmap.SP_DialogYesButton),
    STATUS_UNSTAGED: get_standard_icon(QStyle.StandardPixmap.SP_DialogNoButton),
    STATUS_UNTRACKED: get_standard_icon(QStyle.StandardPixmap.SP_FileDialogInfoView),
}

# Default icon if status code is unknown
DEFAULT_ICON = get_standard_icon(QStyle.StandardPixmap.SP_FileIcon)


class StatusTreeModel(QStandardItemModel):
    """管理 Git 状态树视图的模型和数据解析"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setHorizontalHeaderLabels(["Status", "File Path"])

        # 创建顶层节点 (文件夹) with icons and bold font
        font = QFont()
        font.setBold(True)

        self.staged_root = QStandardItem(STATUS_STAGED)
        self.staged_root.setIcon(STATUS_ICONS.get(STATUS_STAGED, QIcon()))
        self.staged_root.setData(STATUS_STAGED, Qt.ItemDataRole.UserRole) # Store section type
        self.staged_root.setEditable(False)
        self.staged_root.setFont(font)


        self.unstage_root = QStandardItem(STATUS_UNSTAGED)
        self.unstage_root.setIcon(STATUS_ICONS.get(STATUS_UNSTAGED, QIcon()))
        self.unstage_root.setData(STATUS_UNSTAGED, Qt.ItemDataRole.UserRole) # Store section type
        self.unstage_root.setEditable(False)
        self.unstage_root.setFont(font)


        self.untracked_root = QStandardItem(STATUS_UNTRACKED)
        self.untracked_root.setIcon(STATUS_ICONS.get(STATUS_UNTRACKED, QIcon()))
        self.untracked_root.setData(STATUS_UNTRACKED, Qt.ItemDataRole.UserRole) # Store section type
        self.untracked_root.setEditable(False)
        self.untracked_root.setFont(font)


        # Add root items to the model using invisibleRootItem()
        # The second item in the row for root nodes is just a placeholder
        self.invisibleRootItem().appendRow([self.staged_root, QStandardItem()])
        self.invisibleRootItem().appendRow([self.unstage_root, QStandardItem()])
        self.invisibleRootItem().appendRow([self.untracked_root, QStandardItem()])

        # Initial count update
        self._update_root_counts()


    def clear_status(self):
        """清空所有状态，保留根节点"""
        logging.debug("Clearing status tree model.")
        if self.staged_root: self.staged_root.removeRows(0, self.staged_root.rowCount())
        if self.unstage_root: self.unstage_root.removeRows(0, self.unstage_root.rowCount())
        if self.untracked_root: self.untracked_root.removeRows(0, self.untracked_root.rowCount())
        self._update_root_counts()


    def parse_and_populate(self, porcelain_output: str):
        """解析 'git status --porcelain=v1' 的输出并填充模型 (with icons)"""
        self.clear_status() # Clear existing data

        staged_count = 0
        unstage_count = 0
        untracked_count = 0

        lines = porcelain_output.strip().splitlines()
        if not lines:
            logging.info("Git status porcelain output is empty.")
            self._update_root_counts()
            return

        items_to_add = {STATUS_STAGED: [], STATUS_UNSTAGED: [], STATUS_UNTRACKED: []}

        for line in lines:
            if not line or len(line) < 3:
                 logging.warning(f"Skipping malformed status line (too short): {repr(line)}")
                 continue # Skip empty or too short lines

            try:
                status_codes = line[:2] # X and Y codes
                # The path starts at index 3, handle potential rename/copy syntax
                path_part_raw = line[3:]

                original_path = None
                file_path = ""
                display_path = ""

                # Handle renames/copies first (R or C in X or Y)
                # Porcelain v1 rename/copy format: 'R<xy> <orig> -> <new>' or 'C<xy> <orig> -> <new>'
                # status_codes[0] is index status, status_codes[1] is worktree status
                # R/C can appear in either X or Y, but for 'R ... -> ...' format, it's usually X.
                if status_codes[0] in ('R', 'C'):
                    parts = path_part_raw.split(' -> ', 1)
                    if len(parts) == 2:
                        original_path_quoted = parts[0].strip()
                        file_path_quoted = parts[1].strip()

                        # Unquote paths if they are enclosed in double quotes
                        if original_path_quoted.startswith('"') and original_path_quoted.endswith('"'):
                            original_path = original_path_quoted[1:-1].encode('latin-1').decode('unicode_escape')
                        else:
                            original_path = original_path_quoted

                        if file_path_quoted.startswith('"') and file_path_quoted.endswith('"'):
                             file_path = file_path_quoted[1:-1].encode('latin-1').decode('unicode_escape')
                        else:
                             file_path = file_path_quoted

                        # Display the new path and indicate it was from a rename/copy
                        display_path = f"{file_path} (from {os.path.basename(original_path) if original_path else '?'})"

                    else:
                        # Malformed rename/copy line
                        file_path = path_part_raw.strip()
                        display_path = file_path
                        logging.warning(f"Could not parse R/C line format: {repr(line)}")
                else:
                    # Not a rename/copy, standard path parsing
                    file_path_quoted = path_part_raw.strip()
                    # Unquote path if needed
                    if file_path_quoted.startswith('"') and file_path_quoted.endswith('"'):
                        file_path = file_path_quoted[1:-1].encode('latin-1').decode('unicode_escape')
                    else:
                        file_path = file_path_quoted
                    display_path = file_path # For non-renames, display path is just the file path


                # Determine icon and tooltip based on combined status XY
                icon = STATUS_ICONS.get(status_codes, DEFAULT_ICON)

                # Fallback if exact XY match not found or if a single char gives a better icon
                # E.g., " M" is Staged Modified (Index M, Worktree space) - icon comes from " M"
                # "MM" is Staged Modified, Unstaged Modified - icon comes from "MM"
                # If " M" or "MM" weren't in map, could check "M " (Unstaged) or " A" (Staged) etc.
                # The current map is fairly comprehensive for common XY, fallback to single char lookup if needed
                if icon == DEFAULT_ICON:
                    staged_icon_key = status_codes[0] + " " # e.g. "M "
                    unstaged_icon_key = " " + status_codes[1] # e.g. " M"
                    # Prioritize staged icon if available, then unstaged, then default
                    icon = STATUS_ICONS.get(staged_icon_key, STATUS_ICONS.get(unstaged_icon_key, DEFAULT_ICON))


                tooltip = f"Status: {status_codes}, Path: {file_path}"
                color = None # Default color

                # Set specific colors for certain statuses
                if status_codes == 'UU': color = QColor('red') # Conflict
                elif status_codes == '??': color = QColor('gray') # Untracked can be dimmed


                # Create QStandardItems for status and path
                item_status = QStandardItem(status_codes)
                item_status.setIcon(icon)
                item_status.setToolTip(tooltip)
                item_status.setEditable(False)
                if color: item_status.setForeground(color)

                item_path = QStandardItem(display_path) # Use display path for the tree view text
                item_path.setData(file_path, Qt.ItemDataRole.UserRole + 1) # Store real file path
                item_path.setToolTip(tooltip)
                item_path.setEditable(False)
                if color: item_path.setForeground(color)


                # Add items to the correct section list(s) based on status codes (X for staged, Y for unstaged/untracked)
                if status_codes == '??':
                    # Untracked files only appear in the untracked section
                    item_path.setData("??", Qt.ItemDataRole.UserRole + 4) # Mark as untracked type
                    items_to_add[STATUS_UNTRACKED].append([item_status, item_path])
                    untracked_count += 1
                elif status_codes == 'UU':
                    # Unmerged files appear in both staged and unstaged sections
                    # Use a copy for the other section as items belong to one parent at a time
                    item_path_copy = item_path.clone()
                    item_status_copy = item_status.clone()

                    # Add to Unstaged section (represents working copy state)
                    item_path.setData("U", Qt.ItemDataRole.UserRole + 3) # Mark with unstaged 'U' code
                    items_to_add[STATUS_UNSTAGED].append([item_status, item_path])
                    unstage_count += 1

                    # Add to Staged section (represents index state)
                    item_path_copy.setData("U", Qt.ItemDataRole.UserRole + 2) # Mark with staged 'U' code
                    items_to_add[STATUS_STAGED].append([item_status_copy, item_path_copy])
                    staged_count += 1
                else:
                    # Handle other status codes (Modified, Added, Deleted, Renamed, Copied)
                    # X code indicates staged changes (Index)
                    if status_codes[0] != ' ':
                        # Create a copy for the staged section if needed
                        item_path_staged = item_path.clone() if status_codes[1] != ' ' else item_path
                        item_status_staged = item_status.clone() if status_codes[1] != ' ' else item_status
                        item_path_staged.setData(status_codes[0], Qt.ItemDataRole.UserRole + 2) # Mark with staged code
                        items_to_add[STATUS_STAGED].append([item_status_staged, item_status_staged if item_path_staged is item_status_staged else item_path_staged]) # Ensure path item is added

                        staged_count += 1

                    # Y code indicates unstaged changes (Worktree)
                    if status_codes[1] != ' ':
                        # Create a copy for the unstaged section if needed
                        item_path_unstaged = item_path.clone() if status_codes[0] != ' ' and status_codes[0] != 'U' else item_path # Avoid cloning again if it's the original UU item
                        item_status_unstaged = item_status.clone() if status_codes[0] != ' ' and status_codes[0] != 'U' else item_status

                        item_path_unstaged.setData(status_codes[1], Qt.ItemDataRole.UserRole + 3) # Mark with unstaged code
                        items_to_add[STATUS_UNSTAGED].append([item_status_unstaged, item_status_unstaged if item_path_unstaged is item_status_unstaged else item_path_unstaged]) # Ensure path item is added
                        unstage_count += 1

            except Exception as e:
                logging.error(f"Error parsing status line: '{line}' - {e}", exc_info=True)

        # Batch append items to the model for potentially better performance
        # Note: ensure items are added as [status_item, path_item] pairs
        for item_pair in items_to_add[STATUS_STAGED]:
            if len(item_pair) == 2 and isinstance(item_pair[0], QStandardItem) and isinstance(item_pair[1], QStandardItem):
                self.staged_root.appendRow(item_pair)
            else:
                 logging.error(f"Invalid item pair format for staged section: {item_pair}")

        for item_pair in items_to_add[STATUS_UNSTAGED]:
             if len(item_pair) == 2 and isinstance(item_pair[0], QStandardItem) and isinstance(item_pair[1], QStandardItem):
                self.unstage_root.appendRow(item_pair)
             else:
                  logging.error(f"Invalid item pair format for unstaged section: {item_pair}")

        for item_pair in items_to_add[STATUS_UNTRACKED]:
             if len(item_pair) == 2 and isinstance(item_pair[0], QStandardItem) and isinstance(item_pair[1], QStandardItem):
                self.untracked_root.appendRow(item_pair)
             else:
                  logging.error(f"Invalid item pair format for untracked section: {item_pair}")


        self._update_root_counts() # Update counts displayed in root nodes
        logging.info(f"Status parsed: Staged({staged_count}), Unstaged({unstage_count}), Untracked({untracked_count})")


    def _update_root_counts(self):
        """更新根节点显示的计数"""
        if self.staged_root: self.staged_root.setText(f"{STATUS_STAGED} ({self.staged_root.rowCount()})")
        if self.unstage_root: self.unstage_root.setText(f"{STATUS_UNSTAGED} ({self.unstage_root.rowCount()})")
        if self.untracked_root: self.untracked_root.setText(f"{STATUS_UNTRACKED} ({self.untracked_root.rowCount()})")


    def get_files_in_section(self, section_type: str) -> list[str]:
        """获取指定区域下的所有文件路径 (去重)"""
        files = set()
        root_item = None
        if section_type == STATUS_STAGED: root_item = self.staged_root
        elif section_type == STATUS_UNSTAGED: root_item = self.unstage_root
        elif section_type == STATUS_UNTRACKED: root_item = self.untracked_root
        else:
            logging.warning(f"Unknown section type requested: {section_type}")
            return []

        if root_item:
            for row in range(root_item.rowCount()):
                # Get the item in the path column (column 1)
                path_item = root_item.child(row, 1)
                if path_item:
                    # Retrieve the real file path stored in UserRole + 1
                    file_path = path_item.data(Qt.ItemDataRole.UserRole + 1)
                    if file_path:
                        files.add(file_path)

        return list(files)


    def get_selected_files(self, selected_indexes) -> dict:
        """
        根据 QTreeView 中选中的索引，返回按状态分类的文件列表。
        Handles multi-selection and ensures each unique file path is listed once per relevant section.
        返回: {'Staged Changes': [...], 'Unstaged Changes': [...], 'Untracked Files': [...]}
        """
        selected_files = {
            STATUS_STAGED: [],
            STATUS_UNSTAGED: [],
            STATUS_UNTRACKED: []
        }
        processed_paths_in_section = { # Track paths already added *per section*
            STATUS_STAGED: set(),
            STATUS_UNSTAGED: set(),
            STATUS_UNTRACKED: set()
        }

        for index in selected_indexes:
            # Ensure the index is valid and not a root node itself
            item = self.itemFromIndex(index)
            if not item or not item.parent() or item.parent() not in [self.staged_root, self.unstage_root, self.untracked_root]:
                 continue # Skip root nodes or invalid items

            # Get the parent section type
            parent_item = item.parent()
            section_type = parent_item.data(Qt.ItemDataRole.UserRole)

            # Ensure we get the real file path from the path item (column 1) for this row
            # regardless of which column (0 or 1) was actually clicked/selected.
            path_item_index = self.index(index.row(), 1, parent_item.index())
            path_item = self.itemFromIndex(path_item_index)

            if not path_item: continue # Should not happen for valid file items

            file_path = path_item.data(Qt.ItemDataRole.UserRole + 1) # Get the real file path

            if file_path and section_type in selected_files:
                 # Add the file path to the correct section if not already added in this section
                 if file_path not in processed_paths_in_section[section_type]:
                      selected_files[section_type].append(file_path)
                      processed_paths_in_section[section_type].add(file_path)
            elif not file_path:
                 logging.warning(f"Could not get file path from item data for index: {index.row()}, {index.column()} in section {section_type}")


        logging.debug(f"Selected files by section: {selected_files}")
        return selected_files