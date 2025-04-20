# src/gui/dialogs.py

from PyQt6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QTextEdit, QPushButton, QLabel, QLineEdit, QDialogButtonBox

class CommitMessageDialog(QDialog):
    """
    用于输入提交信息的对话框。
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("输入提交信息")
        self.setGeometry(100, 100, 400, 300)

        layout = QVBoxLayout()

        self.message_edit = QTextEdit()
        self.message_edit.setPlaceholderText("在此输入提交信息...")
        layout.addWidget(self.message_edit)

        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)

        layout.addWidget(button_box)
        self.setLayout(layout)

    def get_message(self):
        """获取输入的提交信息"""
        return self.message_edit.toPlainText()

# Add more dialogs as needed, e.g., for remote name, branch name etc.
# A generic text input dialog might also be useful.
class SimpleTextInputDialog(QDialog):
    """
    用于简单单行文本输入的对话框。
    """
    def __init__(self, title, label, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setGeometry(100, 100, 300, 150)

        layout = QVBoxLayout()

        layout.addWidget(QLabel(label))
        self.text_input = QLineEdit()
        layout.addWidget(self.text_input)

        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)

        layout.addWidget(button_box)
        self.setLayout(layout)

    def get_text(self):
        """获取输入的文本"""
        return self.text_input.text()