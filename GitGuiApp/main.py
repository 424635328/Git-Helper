# main.py
import sys
import logging
from PyQt6.QtWidgets import QApplication
from ui.main_window import MainWindow

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


if __name__ == '__main__':
    logging.info("应用程序启动...")
    app = QApplication(sys.argv)

    # 应用一些样式 (可选)
    app.setStyle('Windows') # 'Fusion', 'Windows', 'macOS'

    main_win = MainWindow()
    main_win.show()

    try:
        sys.exit(app.exec())
    except Exception as e:
        logging.critical(f"应用程序意外退出: {e}", exc_info=True)
        sys.exit(1)