# main-Gui.py
import sys
import os
from PyQt6.QtWidgets import QApplication, QMessageBox

# 仅导入 config 字典和新的非交互式加载函数
from src.config_manager import config, check_git_repo_and_origin, complete_config_load

# 导入主窗口类
from src.gui.main_window import MainWindow

if __name__ == "__main__":
    # 确定脚本所在的目录，并将其作为项目根目录传递
    # Git 命令将在 MainWindow 内部检测到的实际仓库路径下执行
    project_root = os.path.dirname(os.path.abspath(__file__))
    # print(f"Project root (script location): {project_root}") # Debug

    # 不再在此处加载配置
    # load_config("config.yaml") # REMOVED

    app = QApplication(sys.argv)

    # 创建主窗口，传入脚本根目录（MainWindow 会用它进行初始路径检查）
    main_window = MainWindow(project_root=project_root)
    main_window.show()

    # 启动 Qt 事件循环
    sys.exit(app.exec())