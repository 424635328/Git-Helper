# ui/dialogs.py
import logging
from PyQt6.QtWidgets import (
    QDialog, QLineEdit, QTextEdit, QFormLayout, QHBoxLayout,
    QPushButton, QDialogButtonBox, QLabel
)
from PyQt6.QtGui import QKeySequence # ShortcutDialog 可能需要
from PyQt6.QtCore import Qt # 可能需要

# 可选：为这个模块配置单独的日志记录器，或保持简单
# logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

class ShortcutDialog(QDialog):
    """用于输入快捷键名称和组合的对话框"""
    def __init__(self, parent=None, name="", sequence="", shortcut_key=""):
        super().__init__(parent)
        self.setWindowTitle("保存/编辑快捷键组合")
        self.setModal(True)
        self.setMinimumWidth(350) # 设置最小宽度

        layout = QFormLayout(self)

        self.name_edit = QLineEdit(name)
        self.sequence_edit = QTextEdit(sequence)
        self.sequence_edit.setReadOnly(True) # 序列在此对话框中不可编辑
        self.sequence_edit.setMaximumHeight(100)
        self.shortcut_edit = QLineEdit(shortcut_key)
        self.shortcut_edit.setPlaceholderText("例如: Ctrl+Alt+S (区分大小写)")

        layout.addRow("名称:", self.name_edit)
        layout.addRow("命令序列:", self.sequence_edit)
        layout.addRow("快捷键:", self.shortcut_edit)

        # 标准按钮 QDialogButtonBox
        button_box = QDialogButtonBox(
             QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        # 重命名 Save 按钮文本为 "确定" (如果需要)
        save_button = button_box.button(QDialogButtonBox.StandardButton.Save)
        if save_button:
            save_button.setText("确定")

        button_box.accepted.connect(self.accept) # Save 按钮触发 accept
        button_box.rejected.connect(self.reject) # Cancel 按钮触发 reject
        layout.addRow(button_box) # 将按钮盒添加到布局


    def get_data(self):
        """获取用户输入的数据"""
        return {
            "name": self.name_edit.text().strip(),
            "sequence": self.sequence_edit.toPlainText().strip(),
            "shortcut_key": self.shortcut_edit.text().strip()
        }


class SettingsDialog(QDialog):
    """用于配置 Git 用户名和邮箱的对话框"""
    def __init__(self, parent=None, current_name="", current_email=""):
        super().__init__(parent)
        self.setWindowTitle("Git 全局配置")
        self.setMinimumWidth(400)

        layout = QFormLayout(self)

        self.name_edit = QLineEdit(current_name)
        self.email_edit = QLineEdit(current_email)

        layout.addRow("全局用户名 (user.name):", self.name_edit)
        layout.addRow("全局邮箱 (user.email):", self.email_edit)
        layout.addWidget(QLabel("注意：这里设置的是全局配置 (`--global`)。"))

        # 标准按钮 QDialogButtonBox
        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addRow(button_box)

    def get_data(self):
        """获取用户输入的配置"""
        return {
            "user.name": self.name_edit.text().strip(),
            "user.email": self.email_edit.text().strip()
        }

# 你也可以在这里添加其他未来可能需要的对话框类