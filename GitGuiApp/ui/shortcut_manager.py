# ui/shortcut_manager.py
import logging
from PyQt6.QtWidgets import QListWidgetItem, QMenu, QMessageBox
from PyQt6.QtGui import QKeySequence, QShortcut
from PyQt6.QtCore import Qt, pyqtSlot

# 从父级目录导入 dialogs (如果直接运行此文件会报错，但在 main.py 中运行正常)
# 如果遇到导入问题，可能需要调整 sys.path 或使用更明确的包结构
try:
    from .dialogs import ShortcutDialog
except ImportError:
    # Fallback for potential direct execution or different import contexts
    from dialogs import ShortcutDialog


class ShortcutManager:
    """管理应用程序的快捷键加载、保存、注册和执行"""

    def __init__(self, main_window, db_handler, git_handler):
        """
        初始化快捷键管理器。

        Args:
            main_window: MainWindow 的实例，用于访问 UI 元素和执行方法。
            db_handler: DatabaseHandler 的实例。
            git_handler: GitHandler 的实例。
        """
        self.main_window = main_window
        self.db_handler = db_handler
        self.git_handler = git_handler
        self.shortcuts_map = {}  # {name: QShortcut 对象}

    def save_shortcut_dialog(self):
        """弹出对话框让用户保存当前序列为快捷键 (强制使用正确格式)"""
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
                qks = QKeySequence.fromString(shortcut_key, QKeySequence.SequenceFormat.NativeText)
                if qks.isEmpty() and shortcut_key.lower() != 'none':
                     raise ValueError("Invalid key sequence string")
            except Exception:
                QMessageBox.warning(self.main_window, "保存失败", f"无效的快捷键格式: '{shortcut_key}'. 请使用例如 'Ctrl+S', 'Alt+Shift+X' 等格式。")
                return

            if self.db_handler.save_shortcut(name, final_sequence_to_save, shortcut_key):
                QMessageBox.information(self.main_window, "成功", f"快捷键 '{name}' ({shortcut_key}) 已保存。")
                self.load_and_register_shortcuts() # 重新加载
                self.main_window._clear_sequence() # 调用主窗口的方法清空序列
            else:
                 QMessageBox.critical(self.main_window, "保存失败", f"无法保存快捷键 '{name}'。请检查名称或快捷键是否已存在，或查看日志了解详情。")

    def load_and_register_shortcuts(self):
        """从数据库加载快捷键并注册 QShortcut (增加日志)"""
        list_widget = self.main_window.shortcut_list_widget # 获取列表控件引用
        list_widget.clear()

        # 清理旧快捷键
        for name, shortcut_obj in list(self.shortcuts_map.items()):
            try:
                shortcut_obj.setEnabled(False)
                shortcut_obj.setParent(None)
                shortcut_obj.deleteLater()
            except Exception as e:
                logging.warning(f"移除旧快捷键 '{name}' 时出错: {e}")
            del self.shortcuts_map[name] # 使用 del

        shortcuts = self.db_handler.load_shortcuts()
        logging.info(f"从数据库加载了 {len(shortcuts)} 个快捷键数据。")
        is_repo_valid = self.git_handler.is_valid_repo()

        for i, shortcut_data in enumerate(shortcuts):
            name = shortcut_data['name']
            sequence_str = shortcut_data['sequence'] # 保留，以便 lambda 捕获
            key_str = shortcut_data['shortcut_key']

            logging.debug(f"快捷键 #{i+1}: Name='{name}', Key='{key_str}', Sequence={repr(sequence_str)}")

            item = QListWidgetItem(f"{name} ({key_str})")
            item.setData(Qt.ItemDataRole.UserRole, shortcut_data) # 存储完整数据
            list_widget.addItem(item) # 使用引用添加

            try:
                q_key_sequence = QKeySequence.fromString(key_str, QKeySequence.SequenceFormat.NativeText)
                if not q_key_sequence.isEmpty():
                    # 父对象是 main_window
                    shortcut = QShortcut(q_key_sequence, self.main_window)
                    # 连接到 manager 自己的触发方法
                    shortcut.activated.connect(lambda data=shortcut_data: self.trigger_shortcut(data))
                    shortcut.setContext(Qt.ShortcutContext.WindowShortcut)
                    shortcut.setEnabled(is_repo_valid) # 设置初始状态
                    self.shortcuts_map[name] = shortcut # 存储在 manager 内部
                    logging.info(f"成功注册快捷键: {name} ({key_str})")
                else:
                     logging.warning(f"无法解析快捷键字符串 '{key_str}' 为有效的 QKeySequence。")
            except Exception as e:
                logging.error(f"注册快捷键 '{name}' ({key_str}) 失败: {e}")

    def trigger_shortcut(self, shortcut_data: dict):
        """通过快捷键数据字典触发命令执行"""
        name = shortcut_data.get('name', '未知名称')
        sequence_str = shortcut_data.get('sequence', '')
        logging.debug(f"ShortcutManager: 快捷键 '{name}' 被触发。Sequence={repr(sequence_str)}")

        # 调用主窗口的执行逻辑
        self.main_window._execute_sequence_from_string(name, sequence_str)

    def execute_shortcut_from_list(self, item: QListWidgetItem):
        """双击列表项时执行对应的快捷键组合"""
        shortcut_data = item.data(Qt.ItemDataRole.UserRole)
        if shortcut_data and isinstance(shortcut_data, dict):
            self.trigger_shortcut(shortcut_data) # 调用内部触发方法
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
        delete_action = QAction("删除", self.main_window) # 父对象可以是 main_window
        # 使用 lambda 捕获当前 item
        delete_action.triggered.connect(lambda checked=False, item=item: self.delete_shortcut(item))
        menu.addAction(delete_action)

        menu.exec(list_widget.mapToGlobal(pos)) # 使用 list_widget 引用

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
                # 从 manager 的 map 中移除
                if name in self.shortcuts_map:
                    try:
                        shortcut_obj = self.shortcuts_map[name]
                        shortcut_obj.setEnabled(False)
                        shortcut_obj.setParent(None)
                        shortcut_obj.deleteLater()
                    except Exception as e:
                         logging.warning(f"禁用或删除已删除快捷键 '{name}' 时出错: {e}")
                    del self.shortcuts_map[name] # 使用 del

                # 从主窗口的 list widget 中移除
                list_widget = self.main_window.shortcut_list_widget
                row = list_widget.row(item)
                if row >= 0:
                    list_widget.takeItem(row)

                QMessageBox.information(self.main_window, "成功", f"快捷键 '{name}' 已删除。")
            else:
                QMessageBox.critical(self.main_window, "删除失败", f"无法从数据库删除快捷键 '{name}'。请查看日志。")

    def set_shortcuts_enabled(self, enabled: bool):
        """启用或禁用所有已注册的 QShortcut 对象"""
        logging.debug(f"ShortcutManager: Setting shortcuts enabled state to: {enabled}")
        for name, shortcut_obj in self.shortcuts_map.items():
            try:
                shortcut_obj.setEnabled(enabled)
            except Exception as e:
                logging.warning(f"设置快捷键 '{name}' 状态时出错: {e}")