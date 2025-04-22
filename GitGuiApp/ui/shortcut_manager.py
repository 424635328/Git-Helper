import logging
import shlex
from PyQt6.QtWidgets import QListWidget, QListWidgetItem, QMenu, QMessageBox
from PyQt6.QtGui import QKeySequence, QShortcut, QAction
from PyQt6.QtCore import Qt, pyqtSlot, QObject, QPoint

try:
    from .dialogs import ShortcutDialog
except ImportError:
    try:
        from dialogs import ShortcutDialog
    except ImportError:
        logging.error("无法导入 ShortcutDialog。请确保运行环境正确。", exc_info=True)
        class ShortcutDialog(QMessageBox):
             def __init__(self, parent=None, sequence=""):
                 super().__init__(parent)
                 self.setWindowTitle("Error")
                 self.setText("ShortcutDialog placeholder - import failed. Cannot save shortcut.")
                 self.setStandardButtons(QMessageBox.StandardButton.Ok)
             def exec(self): return 0
             def get_data(self): return {"name": "", "shortcut_key": "", "sequence": ""}


class ShortcutManager(QObject):
    """管理应用程序的快捷键加载, 保存, 注册和执行"""

    def __init__(self, main_window, db_handler):
        """
        初始化快捷键管理器。

        Args:
            main_window: MainWindow 的实例，用于访问 UI 元素和执行方法 (包括 git_handler)。
            db_handler: DatabaseHandler 的实例。
        """
        super().__init__(main_window)

        self.main_window = main_window
        self.db_handler = db_handler

        self.shortcuts_map = {}
        self._shortcut_list_widget: QListWidget | None = None

    def set_shortcut_list_widget(self, widget: QListWidget):
         """设置用于显示快捷键的 QListWidget 控件"""
         self._shortcut_list_widget = widget
         logging.debug(f"ShortcutManager: Shortcut list widget set: {widget}")


    def clear_shortcuts(self):
        """清空显示的快捷键列表并注销所有 QShortcut 对象"""
        logging.info("ShortcutManager: Clearing shortcuts display and unregistering.")
        if self._shortcut_list_widget:
             self._shortcut_list_widget.clear()

        for name, shortcut_obj in list(self.shortcuts_map.items()):
            logging.debug(f"Unregistering and deleting old shortcut object: '{name}'")
            try:
                try:
                     shortcut_obj.activated.disconnect(self.trigger_shortcut)
                except TypeError:
                     logging.debug(f"Could not disconnect 'activated' from {name}, might be already disconnected.")
                     try:
                          shortcut_obj.activated.disconnect()
                     except Exception:
                          pass


                shortcut_obj.setEnabled(False)
                shortcut_obj.setParent(None)
                shortcut_obj.deleteLater()
            except Exception as e:
                logging.warning(f"Error during cleanup of old shortcut object '{name}': {e}", exc_info=True)
            del self.shortcuts_map[name]

        logging.info("ShortcutManager: All QShortcut objects unregistered and map cleared.")


    def save_shortcut_dialog(self):
        """弹出对话框让用户保存当前序列为快捷键"""
        current_sequence_list = self.main_window.current_command_sequence
        if not current_sequence_list:
            QMessageBox.warning(self.main_window, "无法保存", "当前命令序列为空。")
            return

        final_sequence_to_save = "\n".join(current_sequence_list)
        logging.debug(f"Sequence string to save: {repr(final_sequence_to_save)}")

        dialog = ShortcutDialog(self.main_window, sequence=final_sequence_to_save)
        if dialog.exec():
            data = dialog.get_data()
            name = data.get("name", "").strip()
            shortcut_key = data.get("shortcut_key", "").strip()

            if not name or not shortcut_key:
                QMessageBox.warning(self.main_window, "保存失败", "快捷键名称和组合不能为空。")
                return

            logging.info(f"准备保存快捷键 '{name}' ({shortcut_key}).")
            logging.debug(f"Sequence content: {repr(final_sequence_to_save)}")

            try:
                if shortcut_key.lower() != 'none' and shortcut_key != "":
                    qks = QKeySequence.fromString(shortcut_key, QKeySequence.SequenceFormat.NativeText)
                    if qks.isEmpty():
                         raise ValueError(f"无效的快捷键格式: '{shortcut_key}'")

            except Exception as e:
                QMessageBox.warning(self.main_window, "保存失败", f"无效的快捷键格式: '{shortcut_key}'. 请使用例如 'Ctrl+S', 'Alt+Shift+X' 等格式。详情: {e}")
                logging.error(f"保存快捷键时，QKeySequence 解析失败: {e}", exc_info=True)
                return

            if self.db_handler.save_shortcut(name, final_sequence_to_save, shortcut_key):
                QMessageBox.information(self.main_window, "成功", f"快捷键 '{name}' ({shortcut_key}) 已保存。")
                self.load_and_register_shortcuts()
                self.main_window._clear_sequence()
            else:
                 QMessageBox.critical(self.main_window, "保存失败", f"无法保存快捷键 '{name}'。请检查名称或快捷键组合是否已存在，或查看日志了解详情。")
                 logging.error(f"数据库保存快捷键 '{name}' ({shortcut_key}) 失败.")


    def load_and_register_shortcuts(self):
        """从数据库加载快捷键并注册 QShortcut"""
        list_widget = self._shortcut_list_widget
        if not list_widget:
             logging.error("Shortcut list widget not set in ShortcutManager. Cannot load/register shortcuts.")
             return

        self.clear_shortcuts()

        shortcuts_data_list = self.db_handler.load_shortcuts()
        logging.info(f"从数据库加载了 {len(shortcuts_data_list)} 个快捷键数据。")

        is_repo_valid = self.main_window.git_handler.is_valid_repo() if self.main_window.git_handler else False

        registered_count = 0
        for i, shortcut_data in enumerate(shortcuts_data_list):
            name = shortcut_data.get('name', f'Unnamed_{i}')
            sequence_str = shortcut_data.get('sequence', '')
            key_str = shortcut_data.get('shortcut_key', '').strip()

            logging.debug(f"Processing shortcut #{i+1}: Name='{name}', Key='{key_str}', Sequence={repr(sequence_str[:50])}...")

            item = QListWidgetItem(f"{name} ({key_str})")
            item.setData(Qt.ItemDataRole.UserRole, shortcut_data)
            list_widget.addItem(item)

            try:
                if key_str.lower() != 'none' and key_str != "":
                    q_key_sequence = QKeySequence.fromString(key_str, QKeySequence.SequenceFormat.NativeText)

                    if not q_key_sequence.isEmpty():
                        shortcut = QShortcut(q_key_sequence, self.main_window)
                        shortcut.activated.connect(lambda data=shortcut_data: self.trigger_shortcut(data))
                        shortcut.setContext(Qt.ShortcutContext.WindowShortcut)
                        shortcut.setEnabled(is_repo_valid)
                        self.shortcuts_map[name] = shortcut
                        registered_count += 1
                        logging.info(f"成功注册快捷键: {name} ({key_str})")
                    else:
                         logging.warning(f"无法解析快捷键字符串 '{key_str}' 为有效的 QKeySequence ({name}). 快捷键未注册。")
                else:
                     logging.debug(f"快捷键 '{name}' 配置为无快捷键 ('{key_str}'), 未注册QShortcut对象。")

            except Exception as e:
                logging.error(f"注册快捷键 '{name}' ({key_str}) 失败: {e}", exc_info=True)

        logging.info(f"ShortcutManager: 成功注册 {registered_count} 个 QShortcut 对象。")


    @pyqtSlot(dict)
    def trigger_shortcut(self, shortcut_data: dict):
        """通过快捷键数据字典触发命令执行"""
        if not self.main_window.git_handler or not self.main_window.git_handler.is_valid_repo():
             logging.debug("Shortcut triggered but repo invalid.")
             return

        name = shortcut_data.get('name', '未知名称')
        sequence_str = shortcut_data.get('sequence', '')

        if not sequence_str.strip():
            logging.warning(f"Shortcut '{name}' triggered but sequence is empty.")
            self.main_window._show_information("无操作", f"快捷键 '{name}' 没有关联的命令序列。")
            return


        logging.debug(f"ShortcutManager: 快捷键 '{name}' ({shortcut_data.get('shortcut_key', 'N/A')}) 被触发。Sequence={repr(sequence_str[:50])}...")

        self.main_window._execute_sequence_from_string(name, sequence_str)


    @pyqtSlot(QPoint)
    def show_shortcut_context_menu(self, pos: QPoint):
        """显示快捷键列表的右键菜单"""
        list_widget = self._shortcut_list_widget
        if not list_widget:
             logging.error("Shortcut list widget not set for context menu.")
             return
        item = list_widget.itemAt(pos)
        if not item: return

        menu = QMenu()
        delete_action = QAction("删除", self.main_window)
        delete_action.triggered.connect(lambda checked=False, item=item: self.delete_shortcut(item))
        menu.addAction(delete_action)

        menu.exec(list_widget.viewport().mapToGlobal(pos))

    def delete_shortcut(self, item: QListWidgetItem):
        """删除选中的快捷键"""
        shortcut_data = item.data(Qt.ItemDataRole.UserRole)
        if not shortcut_data or not isinstance(shortcut_data, dict):
            logging.error("Attempted to delete shortcut with invalid item data.")
            return

        name = shortcut_data.get('name', '未知快捷键')
        reply = QMessageBox.question(
            self.main_window, "确认删除", f"确定要删除快捷键 '{name}' 吗？\n\n此操作不可撤销。",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )

        if reply == QMessageBox.StandardButton.Yes:
            if self.db_handler.delete_shortcut(name):
                logging.info(f"用户删除了快捷键 '{name}'. Deleting from UI and manager map.")

                if name in self.shortcuts_map:
                    try:
                        shortcut_obj = self.shortcuts_map[name]
                        try: shortcut_obj.activated.disconnect(self.trigger_shortcut)
                        except TypeError: pass
                        shortcut_obj.setEnabled(False)
                        shortcut_obj.setParent(None)
                        shortcut_obj.deleteLater()
                    except Exception as e:
                         logging.warning(f"Error during cleanup of QShortcut object for '{name}': {e}", exc_info=True)
                    del self.shortcuts_map[name]

                list_widget = self._shortcut_list_widget
                if list_widget:
                    row = list_widget.row(item)
                    if row >= 0:
                        list_widget.takeItem(row)
                        logging.debug(f"Removed item for '{name}' from list widget.")
                    else:
                         logging.warning(f"Could not find item for '{name}' in list widget to remove.")


                QMessageBox.information(self.main_window, "成功", f"快捷键 '{name}' 已删除。")
            else:
                QMessageBox.critical(self.main_window, "删除失败", f"无法从数据库删除快捷键 '{name}'。请查看日志。")
                logging.error(f"数据库删除快捷键 '{name}' 失败.")

    def set_shortcuts_enabled(self, enabled: bool):
        """启用或禁用所有已注册的 QShortcut 对象"""
        logging.debug(f"ShortcutManager: Setting shortcuts enabled state to: {enabled} for {len(self.shortcuts_map)} registered shortcuts.")
        for name, shortcut_obj in list(self.shortcuts_map.items()):
            try:
                if isinstance(shortcut_obj, QObject) and not shortcut_obj.isBeingDestroyed():
                     shortcut_obj.setEnabled(enabled)
                else:
                     logging.warning(f"Shortcut object for '{name}' seems invalid or deleted, skipping setEnabled.")
                     if name in self.shortcuts_map:
                          del self.shortcuts_map[name]

            except Exception as e:
                logging.error(f"Error setting enabled state for shortcut '{name}': {e}", exc_info=True)