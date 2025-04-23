# main.py
import sys
import logging
import os # 导入 os 模块用于路径操作
from PyQt6.QtWidgets import QApplication, QMessageBox
from PyQt6.QtGui import QColor
from PyQt6.QtCore import Qt
from ui.main_window import MainWindow

# 配置日志记录
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - [%(levelname)s] - %(module)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout), # 输出到控制台
    ]
)

# 定义 QSS 文件的路径
# 假设 cyberpunk.qss 和 main.py 在同一个目录下
QSS_FILE = "style.qss"

if __name__ == '__main__':
    logging.info("应用程序启动...")
    app = QApplication(sys.argv)

    # 尝试加载 QSS 文件
    qss_path = os.path.join(os.path.dirname(__file__), QSS_FILE) # 构建完整的 QSS 文件路径
    try:
        with open(qss_path, "r") as f:
            _qss = f.read()
            app.setStyleSheet(_qss)
            logging.info(f"已从 {QSS_FILE} 文件应用样式。")
    except FileNotFoundError:
        logging.error(f"样式文件 {QSS_FILE} 未找到。")
        # 可以选择在这里显示一个错误消息给用户
        # QMessageBox.critical(None, "样式错误", f"样式文件 {QSS_FILE} 未找到。")
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