# main.py
import sys
import logging
from PyQt6.QtWidgets import QApplication, QMessageBox # 导入 QMessageBox 用于错误提示
from ui.main_window import MainWindow # 假设你的主窗口类在这里

# 配置日志记录
logging.basicConfig(
    level=logging.INFO, # 可以调整为 logging.DEBUG 获取更详细信息
    format='%(asctime)s - %(levelname)s - %(module)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout), # 输出到控制台
        # 可以取消注释下面这行，将日志写入文件
        # logging.FileHandler("git_gui_app.log", mode='a', encoding='utf-8')
    ]
)

# 定义样式文件路径
STYLE_SHEET_PATH = "GitGuiAPP/styles/dark_theme.qss"

def load_stylesheet(filepath):
    """加载并返回 QSS 样式文件内容"""
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        logging.error(f"样式文件未找到: {filepath}")
        return None
    except Exception as e:
        logging.error(f"加载样式文件失败: {filepath} - {e}")
        return None

if __name__ == '__main__':
    logging.info("应用程序启动...")
    app = QApplication(sys.argv)

    # 注释掉 setStyle，我们主要通过 QSS 来控制样式
    # app.setStyle('MacOS') # 'Fusion', 'Windows', 'macOS'

    # 加载并应用 QSS 样式
    qss_content = load_stylesheet(STYLE_SHEET_PATH)
    if qss_content:
        app.setStyleSheet(qss_content)
        logging.info("已应用暗色护眼样式。")
    else:
        # 如果样式文件加载失败，可以考虑弹出警告
        logging.warning("未能加载样式文件，使用默认系统样式。")
        # 可选：弹出消息框提示用户
        # QMessageBox.warning(None, "样式加载失败", f"未能加载样式文件: {STYLE_SHEET_PATH}\n应用程序将使用默认样式。")


    main_win = MainWindow()
    main_win.show()

    try:
        sys.exit(app.exec())
    except Exception as e:
        # 使用 QMessageBox 提示用户关键错误
        logging.critical(f"应用程序意外退出: {e}", exc_info=True)
        error_message = f"应用程序发生意外错误并即将关闭。\n错误详情: {e}"
        # 在退出前尝试显示错误信息
        QMessageBox.critical(None, "应用程序错误", error_message)
        sys.exit(1)