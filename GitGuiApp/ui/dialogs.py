# ui/dialogs.py
# -*- coding: utf-8 -*-
import logging
from PyQt6.QtWidgets import (
    QDialog, QLineEdit, QTextEdit, QFormLayout,
    QPushButton, QDialogButtonBox, QLabel
)
from PyQt6.QtCore import Qt
from typing import Optional


class ShortcutDialog(QDialog):
    def __init__(self, parent: Optional[QDialog] = None, name: str = "", sequence: str = "", shortcut_key: str = ""):
        super().__init__(parent)
        self.setWindowTitle("保存/编辑快捷键组合")
        self.setModal(True)
        self.setMinimumWidth(350)

        layout = QFormLayout(self)

        self.name_edit = QLineEdit(name)
        self.sequence_edit = QTextEdit(sequence)
        self.sequence_edit.setReadOnly(True)
        self.sequence_edit.setMaximumHeight(100)
        self.shortcut_edit = QLineEdit(shortcut_key)
        self.shortcut_edit.setPlaceholderText("例如: Ctrl+Alt+S (区分大小写)")

        layout.addRow("名称:", self.name_edit)
        layout.addRow("命令序列:", self.sequence_edit)
        layout.addRow("快捷键:", self.shortcut_edit)

        self._setup_button_box(layout)

    def _setup_button_box(self, layout: QFormLayout):
        self._button_box = QDialogButtonBox(
             QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        save_button = self._button_box.button(QDialogButtonBox.StandardButton.Save)
        if save_button:
            save_button.setText("确定")

        self._button_box.accepted.connect(self.accept)
        self._button_box.rejected.connect(self.reject)
        layout.addRow(self._button_box)

    def get_data(self) -> dict:
        return {
            "name": self.name_edit.text().strip(),
            "sequence": self.sequence_edit.toPlainText().strip(),
            "shortcut_key": self.shortcut_edit.text().strip()
        }


class SettingsDialog(QDialog):
    def __init__(self, parent: Optional[QDialog] = None, current_name: str = "", current_email: str = ""):
        super().__init__(parent)
        self.setWindowTitle("Git 全局配置")
        self.setMinimumWidth(400)

        layout = QFormLayout(self)

        self.name_edit = QLineEdit(current_name)
        self.email_edit = QLineEdit(current_email)

        layout.addRow("全局用户名 (user.name):", self.name_edit)
        layout.addRow("全局邮箱 (user.email):", self.email_edit)
        layout.addWidget(QLabel("注意：这里设置的是全局配置 (`--global`)。"))

        self._setup_button_box(layout)

    def _setup_button_box(self, layout: QFormLayout):
        self._button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        self._button_box.accepted.connect(self.accept)
        self._button_box.rejected.connect(self.reject)
        layout.addRow(self._button_box)

    def get_data(self) -> dict:
        return {
            "user.name": self.name_edit.text().strip(),
            "user.email": self.email_edit.text().strip()
        }