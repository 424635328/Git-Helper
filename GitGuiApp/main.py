# main.py
import sys
import logging
from PyQt6.QtWidgets import QApplication, QMessageBox
from PyQt6.QtGui import QColor # Import QColor to use in QSS string
from PyQt6.QtCore import Qt # Import Qt to use in QSS string
from ui.main_window import MainWindow

# 配置日志记录
logging.basicConfig(
    level=logging.DEBUG, # Adjusted to DEBUG for more detailed info during development
    format='%(asctime)s - [%(levelname)s] - %(module)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout), # 输出到控制台
        # logging.FileHandler("git_gui_app.log", mode='a', encoding='utf-8') # Optional: log to file
    ]
)

# Define the Cyberpunk style QSS directly as a string
CYBERPUNK_QSS = """
/* General Styles */
QMainWindow, QWidget {
    background-color: #1e1e1e; /* Dark background */
    color: #cccccc; /* Light gray text */
    font-family: "Segoe UI", "Arial", sans-serif; /* Prefer common system fonts */
    font-size: 10pt;
}

QLabel {
    color: #cccccc; /* Ensure label text is readable */
}

/* Buttons */
QPushButton {
    background-color: #333333; /* Dark gray button background */
    color: #cccccc; /* Light text color */
    border: 1px solid #555555; /* Subtle dark border */
    padding: 5px 10px; /* Padding around text */
    border-radius: 3px; /* Slightly rounded corners */
    outline: none; /* Remove default focus outline */
}

QPushButton:hover {
    border-color: #00ffff; /* Neon blue border on hover */
    color: #00ffff; /* Neon blue text on hover */
}

QPushButton:pressed {
    background-color: #00ffff; /* Fill with neon blue on press */
    color: #1e1e1e; /* Dark text on neon background */
    border-color: #00ffff;
}

QPushButton:disabled {
    background-color: #282828; /* Darker background when disabled */
    color: #888888; /* Faded text color */
    border-color: #444444;
}

/* Line Edits and Text Edits */
QLineEdit, QTextEdit {
    background-color: #282828; /* Darker input background */
    color: #cccccc; /* Light text color */
    border: 1px solid #555555; /* Subtle dark border */
    padding: 4px; /* Padding inside the input box */
    border-radius: 3px; /* Slightly rounded corners */
    selection-background-color: #ff00ff; /* Neon pink selection background */
    selection-color: #1e1e1e; /* Dark text on selection */
    outline: none; /* Remove default focus outline */
}

QLineEdit:focus, QTextEdit:focus {
    border-color: #ff00ff; /* Neon pink border on focus */
}

/* List, Tree, and Table Views */
QListWidget, QTreeView, QTableWidget {
    background-color: #1e1e1e; /* Dark background */
    color: #cccccc; /* Light text color */
    border: 1px solid #333333; /* Darker border for view containers */
    selection-background-color: #00ffff; /* Neon blue selection background */
    selection-color: #1e1e1e; /* Dark text on selection */
    alternate-background-color: #282828; /* Slightly different row background */
    outline: none;
}

QHeaderView::section {
    background-color: #333333; /* Dark header background */
    color: #cccccc; /* Light header text */
    padding: 4px;
    border: 1px solid #1e1e1e; /* Dark border for separation */
    border-right-color: #333333; /* Avoid double border */
    border-bottom-color: #333333;
}

QTreeView::branch {
    /* No specific styling for branches for simplicity, inherits view styles */
}

/* Tab Widget */
QTabWidget::pane { /* The content frame */
    border: 1px solid #333333;
    background-color: #1e1e1e;
}

QTabWidget::tab-bar {
    left: 5px; /* Offset the tab bar */
}

QTabBar::tab {
    background: #282828; /* Dark tab background */
    border: 1px solid #333333;
    border-bottom-color: #1e1e1e; /* Match pane border for continuity */
    border-top-left-radius: 4px;
    border-top-right-radius: 4px;
    min-width: 8ex; /* Minimum width for tabs */
    padding: 5px 10px;
    color: #cccccc;
}

QTabBar::tab:selected {
    background: #1e1e1e; /* Background color matches pane when selected */
    border-bottom-color: #1e1e1e; /* Hide bottom border when selected */
    border-color: #00ffff; /* Neon blue border for selected tab */
    font-weight: bold;
}

QTabBar::tab:hover:!selected {
    color: #00ffff; /* Neon blue text on hover for non-selected */
}

QTabBar::tab:!selected {
    margin-top: 2px; /* Slightly lower non-selected tabs */
}


/* Status Bar */
QStatusBar {
    background-color: #333333; /* Dark status bar background */
    color: #cccccc; /* Light text */
    border-top: 1px solid #ff00ff; /* Neon pink top border */
    padding: 2px;
}

QStatusBar QLabel {
    color: #cccccc; /* Ensure label text color within status bar */
}

/* Tool Bar */
QToolBar {
    background-color: #333333; /* Dark toolbar background */
    border: none;
    padding: 0;
    spacing: 5px; /* Space between toolbar items */
}

QToolButton { /* Items in a QToolBar are QToolButtons */
    background: transparent;
    border: 1px solid transparent; /* Transparent border for spacing/hover effect */
    padding: 4px;
    color: #cccccc; /* Text color if any */
    border-radius: 3px;
}

QToolButton:hover {
    border-color: #ff00ff; /* Neon pink border on hover */
    color: #ff00ff; /* Neon pink color on hover */
}

QToolButton:pressed {
    background-color: #ff00ff; /* Fill with neon pink on press */
    color: #1e1e1e; /* Dark text on neon */
    border-color: #ff00ff;
}

QToolButton:disabled {
    color: #888888; /* Faded text color */
    border-color: transparent;
}

/* Scroll Bars */
QScrollBar:vertical {
    border: 1px solid #282828;
    background: #1e1e1e;
    width: 10px;
    margin: 0px;
}

QScrollBar::handle:vertical {
    background: #555555; /* Dark gray handle */
    min-height: 20px;
    border-radius: 4px;
}

QScrollBar::handle:vertical:hover {
    background: #00ffff; /* Neon blue handle on hover */
}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0px; /* Remove default add/sub buttons */
}

QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
    background: none;
}

QScrollBar:horizontal {
    border: 1px solid #282828;
    background: #1e1e1e;
    height: 10px;
    margin: 0px;
}

QScrollBar::handle:horizontal {
    background: #555555; /* Dark gray handle */
    min-width: 20px;
    border-radius: 4px;
}

QScrollBar::handle:horizontal:hover {
    background: #ff00ff; /* Neon pink handle on hover */
}

QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
    width: 0px; /* Remove default add/sub buttons */
}

QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {
    background: none;
}

/* Context Menu and MenuBar */
QMenu {
    background-color: #282828; /* Dark background for dropdown menus */
    color: #cccccc; /* Light text */
    border: 1px solid #555555; /* Subtle border */
}

QMenu::item {
    padding: 5px 20px 5px 5px; /* Adjust padding */
}

QMenu::item:selected {
    background-color: #333333; /* Darker background on hover */
    border-left: 2px solid #00ffff; /* Neon blue left border on hover */
    margin-left: -2px; /* Compensate for border width */
    color: #00ffff; /* Neon blue text on hover */
}

QMenu::separator {
    height: 1px;
    background: #555555; /* Separator line */
    margin: 4px 10px;
}

QMenuBar {
    background-color: #333333; /* Dark background for the menu bar */
    color: #cccccc; /* Light text for top-level menus */
    border-bottom: 1px solid #ff00ff; /* Neon pink bottom border to stand out */
}

QMenuBar::item {
    padding: 5px 10px; /* Padding for top-level menu items */
    background: transparent; /* Transparent background */
    color: #cccccc; /* Default text color */
}

QMenuBar::item:selected {
    background-color: #282828; /* Darker background on hover/selection */
    color: #00ffff; /* Neon blue text on hover/selection */
}

QMenuBar::item:pressed {
    background-color: #1e1e1e; /* Even darker on press */
}
"""


if __name__ == '__main__':
    logging.info("应用程序启动...")
    app = QApplication(sys.argv)

    try:
        app.setStyleSheet(CYBERPUNK_QSS)
        logging.info("已应用赛博朋克风格样式。")
    except Exception as e:
         logging.warning(f"应用样式失败: {e}")


    main_win = MainWindow()
    main_win.show()

    try:
        sys.exit(app.exec())
    except Exception as e:
        logging.critical(f"应用程序意外退出: {e}", exc_info=True)
        error_message = f"应用程序发生意外错误并即将关闭。\n错误详情: {e}"
        QMessageBox.critical(None, "应用程序错误", error_message)
        sys.exit(1)