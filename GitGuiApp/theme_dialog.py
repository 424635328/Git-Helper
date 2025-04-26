# theme_dialog.py
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QLabel, QListWidget, QDialogButtonBox,
    QListWidgetItem, QApplication
)
from PyQt6.QtCore import Qt, QSize
from PyQt6.QtGui import QIcon # 可选，如果以后想加图标

# --- 为选择对话框本身定义一个基础的暗色 QSS ---
# 这个 QSS 会在主样式加载前应用，确保对话框看起来协调
DIALOG_STYLE = """
QDialog {
    background-color: #242424; /* 比主背景稍浅 */
    color: #e0e0e0;
    border: 1px solid #555555;
    font-size: 10pt;
    min-width: 300px; /* 给对话框一个最小宽度 */
}

QLabel {
    color: #e0e0e0;
    padding: 10px 5px 5px 10px; /* 调整标签内边距 */
    font-weight: bold;
    background-color: transparent;
}

QListWidget {
    background-color: #282828; /* 列表背景 */
    color: #e0e0e0;
    border: 1px solid #555555;
    border-radius: 4px;
    padding: 5px;
    outline: none; /* 移除焦点轮廓 */
    min-height: 150px; /* 列表最小高度 */
}

QListWidget::item {
    padding: 8px 10px; /* 项目内边距 */
    color: #e0e0e0;
    border-radius: 3px; /* 项目轻微圆角 */
}

QListWidget::item:hover {
    background-color: rgba(0, 255, 255, 0.15); /* 半透明霓虹青 */
    color: #ffffff;
}

QListWidget::item:selected {
    background-color: #007777; /* 青色选中背景 */
    color: #ffffff; /* 白色选中文本 */
    border: 1px solid #00ffff; /* 霓虹青边框 */
    padding: 7px 9px; /* 调整选中项padding以适应边框 */
}

/* --- Dialog Button Box --- */
QDialogButtonBox {
    background-color: transparent;
    padding-top: 10px;
}

/* --- Buttons within DialogButtonBox --- */
QDialogButtonBox QPushButton {
    background-color: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #3a3a3a, stop:1 #303030);
    color: #e0e0e0;
    border: 1px solid #555555;
    padding: 7px 20px; /* 按钮内边距 */
    border-radius: 5px;
    min-width: 80px; /* 按钮最小宽度 */
    outline: none;
}

QDialogButtonBox QPushButton:hover {
    background-color: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #484848, stop:1 #404040);
    border: 1px solid #00ffff; /* 霓虹青边框 */
    color: #00ffff;
}

QDialogButtonBox QPushButton:pressed {
    background-color: #00aaaa;
    color: #ffffff;
    border: 1px solid #00ffff;
}

QDialogButtonBox QPushButton:focus { /* 添加 :focus 状态 */
    border: 1px solid #ff00ff; /* 焦点状态用霓虹粉 */
}

QDialogButtonBox QPushButton:default { /* 'OK' 按钮通常是 default */
    font-weight: bold;
    border: 1px solid #00ffff; /* 默认按钮给个青色边框 */
}
"""


class ThemeSelectionDialog(QDialog):
    def __init__(self, theme_names, parent=None):
        super().__init__(parent)
        self.setWindowTitle("选择主题")
        self.setModal(True) # 确保是模态对话框

        # --- 应用基础对话框样式 ---
        # 注意：这里应用的样式只针对这个对话框本身，
        # 主题选择完成后，app.setStyleSheet() 会覆盖全局样式
        self.setStyleSheet(DIALOG_STYLE)

        self._selected_theme = None
        self._theme_names = theme_names

        # --- Layout ---
        layout = QVBoxLayout(self)
        layout.setContentsMargins(15, 15, 15, 15) # 增加外边距
        layout.setSpacing(10) # 控件间距

        # --- Widgets ---
        self.label = QLabel("请选择一个应用程序主题风格:")
        self.list_widget = QListWidget()
        self.list_widget.setAlternatingRowColors(False) # 禁用交替行颜色，用 hover/selected

        for name in self._theme_names:
            item = QListWidgetItem(name)
            # 可选：为项目设置图标
            # item.setIcon(QIcon("path/to/icon.png"))
            self.list_widget.addItem(item)

        # 设置默认选中第一项
        if self.list_widget.count() > 0:
            self.list_widget.setCurrentRow(0)

        self.button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)

        # --- Add Widgets to Layout ---
        layout.addWidget(self.label)
        layout.addWidget(self.list_widget)
        layout.addWidget(self.button_box)

        # --- Connections ---
        self.button_box.accepted.connect(self.accept)
        self.button_box.rejected.connect(self.reject)
        # 双击列表项也视为接受
        self.list_widget.itemDoubleClicked.connect(self.accept)

    def accept(self):
        """当用户点击 OK 或双击时调用"""
        current_item = self.list_widget.currentItem()
        if current_item:
            self._selected_theme = current_item.text()
        super().accept() # 调用父类的 accept 来关闭对话框并返回 Accepted

    def selectedTheme(self):
        """返回用户选择的主题名称"""
        return self._selected_theme

# --- 可选：用于独立测试对话框外观 ---
if __name__ == '__main__':
    import sys
    app = QApplication(sys.argv)
    # 模拟一些主题名称
    test_themes = ["Dark Neon", "Light Solar", "Oceanic Blue", "Forest Green"]
    dialog = ThemeSelectionDialog(test_themes)
    if dialog.exec() == QDialog.DialogCode.Accepted:
        print(f"Selected theme: {dialog.selectedTheme()}")
    else:
        print("Selection cancelled.")
    sys.exit()