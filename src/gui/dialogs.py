# src/gui/dialogs.py
# GUI 模块，包含各种对话框

from PyQt6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QTextEdit, QPushButton, QLabel, QLineEdit, QDialogButtonBox

class CommitMessageDialog(QDialog):
    """
    用于输入提交信息的对话框。
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        # 设置窗口标题
        self.setWindowTitle("输入提交信息")
        # 设置窗口位置和大小
        self.setGeometry(100, 100, 400, 300)

        # 创建主布局
        layout = QVBoxLayout()

        # 创建文本编辑框用于输入提交信息
        self.message_edit = QTextEdit()
        # 设置占位符文本
        self.message_edit.setPlaceholderText("在此输入提交信息...")
        # 将文本编辑框添加到布局
        layout.addWidget(self.message_edit)

        # 创建按钮框，包含确定和取消按钮
        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        # 连接确定按钮的信号到对话框的接受槽
        button_box.accepted.connect(self.accept)
        # 连接取消按钮的信号到对话框的拒绝槽
        button_box.rejected.connect(self.reject)

        # 将按钮框添加到布局
        layout.addWidget(button_box)
        # 设置对话框的布局
        self.setLayout(layout)

    def get_message(self):
        """获取输入的提交信息"""
        # 返回文本编辑框中的纯文本
        return self.message_edit.toPlainText()

# Add more dialogs as needed, e.g., for remote name, branch name etc.
# A generic text input dialog might also be useful.
# 根据需要添加更多对话框，例如用于远程名称、分支名称等。
# 一个通用的文本输入对话框也可能很有用。
class SimpleTextInputDialog(QDialog):
    """
    用于简单单行文本输入的对话框。
    """
    def __init__(self, title, label, parent=None):
        super().__init__(parent)
        # 设置窗口标题，由参数传入
        self.setWindowTitle(title)
        # 设置窗口位置和大小
        self.setGeometry(100, 100, 300, 150)

        # 创建主布局
        layout = QVBoxLayout()

        # 添加一个标签显示提示文本，由参数传入
        layout.addWidget(QLabel(label))
        # 创建单行文本输入框
        self.text_input = QLineEdit()
        # 将文本输入框添加到布局
        layout.addWidget(self.text_input)

        # 创建按钮框，包含确定和取消按钮
        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        # 连接确定按钮的信号到对话框的接受槽
        button_box.accepted.connect(self.accept)
        # 连接取消按钮的信号到对话框的拒绝槽
        button_box.rejected.connect(self.reject)

        # 将按钮框添加到布局
        layout.addWidget(button_box)
        # 设置对话框的布局
        self.setLayout(layout)

    def get_text(self):
        """获取输入的文本"""
        # 返回单行文本输入框中的文本
        return self.text_input.text()