# -*- coding: utf-8 -*-
import logging
from PyQt6.QtWidgets import QListWidgetItem, QMenu, QMessageBox
from PyQt6.QtGui import QKeySequence, QShortcut, QAction
from PyQt6.QtCore import Qt, pyqtSlot

try:
    from .dialogs import ShortcutDialog
except ImportError:
    from dialogs import ShortcutDialog


class ShortcutManager:
    """管理应用程序的快捷键加载、保存、注册和执行"""

    def __init__(self, main_window, db_handler, git_handler):
        self.main_window = main_window
        self.db_handler = db_handler
        self.git_handler = git_handler
        self.shortcuts_map = {}

    def save_shortcut_dialog(self):
        """弹出对话框让用户保存当前序列为快捷键"""
        current_sequence_list = self.main_window.current_command_sequence
        if not current_sequence_list:
            QMessageBox.warning(self.main_window, "无法保存", "当前命令序列为空。")
            return

        final_sequence_to_save = "\n".join(current_sequence_list)
        logging.info(f"构建待保存的序列字符串 (带换行符): {repr(final_sequence_to_save)}")

        dialog = ShortcutDialog(self.main_window, sequence=final_sequence_to_save)
        if dialog.exec():
            data = dialog.get_data()
            name = data["name"]
            shortcut_key = data["shortcut_key"]

            if not name or not shortcut_key:
                QMessageBox.warning(self.main_window, "保存失败", "快捷键名称和组合不能为空。")
                return

            logging.info(f"准备保存快捷键 '{name}' ({shortcut_key}). 序列: {repr(final_sequence_to_save)}")

            try:
                # 允许 'None' 作为特殊关键字表示无快捷键绑定
                if shortcut_key.lower() != 'none':
                    qks = QKeySequence.fromString(shortcut_key, QKeySequence.SequenceFormat.NativeText)
                    if qks.isEmpty():
                         raise ValueError("Invalid key sequence string")
            except Exception:
                QMessageBox.warning(self.main_window, "保存失败", f"无效的快捷键格式: '{shortcut_key}'. 请使用例如 'Ctrl+S', 'Alt+Shift+X' 或 'None' 等格式。")
                return

            if self.db_handler.save_shortcut(name, final_sequence_to_save, shortcut_key):
                QMessageBox.information(self.main_window, "成功", f"快捷键 '{name}' ({shortcut_key}) 已保存。")
                self.load_and_register_shortcuts()
                # 注意: 这里不应直接清空主窗口的 sequence builder，让用户决定是否保存后清空
                # self.main_window._clear_sequence()
            else:
                 QMessageBox.critical(self.main_window, "保存失败", f"无法保存快捷键 '{name}'。请检查名称或快捷键是否已存在，或查看日志了解详情。")

    def load_and_register_shortcuts(self):
        """从数据库加载快捷键并注册 QShortcut"""
        list_widget = self.main_window.shortcut_list_widget
        list_widget.clear()

        for name, shortcut_obj in list(self.shortcuts_map.items()):
            try:
                shortcut_obj.setEnabled(False)
                shortcut_obj.setParent(None)
                shortcut_obj.deleteLater()
            except Exception as e:
                logging.warning(f"移除旧快捷键 '{name}' 时出错: {e}")
            del self.shortcuts_map[name]

        shortcuts = self.db_handler.load_shortcuts()
        logging.info(f"从数据库加载了 {len(shortcuts)} 个快捷键数据。")
        # 初始状态取决于主窗口当前的仓库和繁忙状态
        initial_enabled_state = self.main_window.git_handler.is_valid_repo() and not self.main_window._is_busy


        for i, shortcut_data in enumerate(shortcuts):
            name = shortcut_data['name']
            sequence_str = shortcut_data['sequence']
            key_str = shortcut_data['shortcut_key']

            logging.debug(f"快捷键 #{i+1}: Name='{name}', Key='{key_str}', Sequence={repr(sequence_str)}")

            item = QListWidgetItem(f"{name} ({key_str})")
            item.setData(Qt.ItemDataRole.UserRole, shortcut_data)
            list_widget.addItem(item)

            # 只注册有绑定键的快捷键
            if key_str and key_str.lower() != 'none':
                try:
                    q_key_sequence = QKeySequence.fromString(key_str, QKeySequence.SequenceFormat.NativeText)
                    if not q_key_sequence.isEmpty():
                        shortcut = QShortcut(q_key_sequence, self.main_window)
                        shortcut.activated.connect(lambda data=shortcut_data: self.trigger_shortcut(data))
                        shortcut.setContext(Qt.ShortcutContext.ApplicationShortcut) # Changed to ApplicationShortcut
                        shortcut.setEnabled(initial_enabled_state) # 设置初始状态
                        self.shortcuts_map[name] = shortcut
                        logging.info(f"成功注册快捷键: {name} ({key_str})")
                    else:
                         logging.warning(f"无法解析快捷键字符串 '{key_str}' 为有效的 QKeySequence。")
                except Exception as e:
                    logging.error(f"注册快捷键 '{name}' ({key_str}) 失败: {e}")
            else:
                 logging.debug(f"快捷键 '{name}' 没有绑定键 ('{key_str}'), 只在列表显示。")


    def trigger_shortcut(self, shortcut_data: dict):
        """通过快捷键数据字典触发命令执行"""
        name = shortcut_data.get('name', '未知名称')
        sequence_str = shortcut_data.get('sequence', '')
        logging.debug(f"ShortcutManager: 快捷键 '{name}' 被触发。Sequence={repr(sequence_str)}")

        # 在触发时，再次检查主窗口是否忙或仓库是否有效
        # 主窗口的 _execute_sequence_from_string 也会检查，但这里可以提前阻止执行
        if self.main_window._is_busy:
             logging.warning(f"UI 正忙，忽略快捷键 '{name}' 执行请求。")
             self.main_window._show_information("操作繁忙", "当前正在执行其他操作，请稍后再试。")
             return

        commands = [line.strip() for line in sequence_str.strip().splitlines() if line.strip()]
        is_init_or_clone = commands and commands[0].strip().lower().startswith(("git init", "git clone"))

        if not is_init_or_clone and (not self.main_window.git_handler or not self.main_window.git_handler.is_valid_repo()):
             self.main_window._show_warning("操作无效", f"无法执行快捷键 '{name}'，需要有效仓库。");
             logging.warning(f"快捷键 '{name}' 执行失败，仓库无效。")
             return


        # 调用主窗口的执行逻辑 (主窗口会处理繁忙状态的设置)
        self.main_window._execute_sequence_from_string(name, sequence_str)


    def execute_shortcut_from_list(self, item: QListWidgetItem):
        """双击列表项时执行对应的快捷键组合"""
        shortcut_data = item.data(Qt.ItemDataRole.UserRole)
        if shortcut_data and isinstance(shortcut_data, dict):
            self.trigger_shortcut(shortcut_data)
        elif shortcut_data:
             logging.error(f"快捷键列表项数据格式错误，期望字典，得到: {type(shortcut_data)}")
        else:
             logging.warning("双击了列表项，但未获取到快捷键数据。")

    def show_shortcut_context_menu(self, pos):
        """显示快捷键列表的右键菜单"""
        list_widget = self.main_window.shortcut_list_widget
        item = list_widget.itemAt(pos)
        if not item:
            return

        menu = QMenu()
        delete_action = QAction("删除", self.main_window)
        delete_action.triggered.connect(lambda checked=False, item=item: self.delete_shortcut(item))
        menu.addAction(delete_action)

        menu.exec(list_widget.mapToGlobal(pos))

    def delete_shortcut(self, item: QListWidgetItem):
        """删除选中的快捷键"""
        shortcut_data = item.data(Qt.ItemDataRole.UserRole)
        if not shortcut_data: return
        name = shortcut_data.get('name', '未知快捷键')
        reply = QMessageBox.question(
            self.main_window, "确认删除", f"确定要删除快捷键 '{name}' 吗？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )

        if reply == QMessageBox.StandardButton.Yes:
            if self.db_handler.delete_shortcut(name):
                logging.info(f"用户删除了快捷键 '{name}'。")
                if name in self.shortcuts_map:
                    try:
                        shortcut_obj = self.shortcuts_map[name]
                        shortcut_obj.setEnabled(False)
                        shortcut_obj.setParent(None)
                        shortcut_obj.deleteLater()
                    except Exception as e:
                         logging.warning(f"禁用或删除已删除快捷键 '{name}' 的 QShortcut 对象时出错: {e}")
                    del self.shortcuts_map[name]

                list_widget = self.main_window.shortcut_list_widget
                row = list_widget.row(item)
                if row >= 0:
                    list_widget.takeItem(row)

                QMessageBox.information(self.main_window, "成功", f"快捷键 '{name}' 已删除。")
            else:
                QMessageBox.critical(self.main_window, "删除失败", f"无法从数据库删除快捷键 '{name}'。请查看日志。")

    def set_shortcuts_enabled(self, enabled: bool):
        """启用或禁用所有已注册的 QShortcut 对象"""
        logging.debug(f"ShortcutManager: Setting QShortcut enabled state to: {enabled}")
        for name, shortcut_obj in list(self.shortcuts_map.items()): 
            try:
                if shortcut_obj: 
                     shortcut_obj.setEnabled(enabled)
            except Exception as e:
                logging.warning(f"设置快捷键 '{name}' QShortcut 状态时出错: {e}")