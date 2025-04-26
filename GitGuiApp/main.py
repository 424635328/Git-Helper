import sys
import os
import logging
from PyQt6.QtWidgets import QApplication, QMessageBox, QDialog
from PyQt6.QtGui import QColor # 保留，即使在此文件中未使用，以防子模块需要
from PyQt6.QtCore import Qt    # 保留，理由同上
from ui.main_window import MainWindow # 假设 MainWindow 在 ui/main_window.py
from theme_dialog import ThemeSelectionDialog # 假设在同级目录

# ==============================================================================
# 资源路径辅助函数 (关键！用于 PyInstaller 打包)
# ==============================================================================
def resource_path(relative_path):
  """ 获取资源的绝对路径，适用于开发环境和 PyInstaller 打包后的环境 """
  try:
    # PyInstaller 创建一个临时文件夹并将路径存储在 _MEIPASS
    base_path = sys._MEIPASS
    # print(f"[调试] 使用 _MEIPASS 路径: {base_path}") # 取消注释以调试
  except AttributeError:
    # 未在 PyInstaller 环境中运行（例如开发环境），使用此脚本所在的目录
    base_path = os.path.abspath(os.path.dirname(__file__))
    # print(f"[调试] 使用脚本目录路径: {base_path}") # 取消注释以调试

  # print(f"[调试] 拼接路径: {base_path} 和 {relative_path}") # 取消注释以调试
  return os.path.join(base_path, relative_path)

# ==============================================================================
# 日志配置 (保持不变)
# ==============================================================================
logging.basicConfig(
    level=logging.DEBUG, # 可以根据需要调整为 logging.INFO
    format='%(asctime)s - [%(levelname)s] - %(module)s:%(lineno)d - %(message)s', # 添加行号
    handlers=[
        logging.StreamHandler(sys.stdout),
        # 可以考虑添加 FileHandler 将日志写入文件
        # logging.FileHandler("app.log", encoding='utf-8')
    ]
)

# ==============================================================================
# 常量定义
# ==============================================================================
# 定义 QSS 文件的相对目录名 (用于 resource_path)
THEMES_DIR_NAME = "styles"

# ==============================================================================
# 主题查找函数 (已修改以使用 resource_path)
# ==============================================================================
def get_available_themes(themes_subdir_name):
    """查找指定相对目录下可用的 QSS 主题文件"""
    # 使用 resource_path 获取主题目录的绝对路径
    themes_path = resource_path(themes_subdir_name)
    available_themes = {} # 字典: 友好名称 -> 相对路径 (例如 "styles/dark.qss")

    if not os.path.isdir(themes_path):
        logging.warning(f"主题目录 '{themes_path}' 不存在或不是一个目录。")
        return available_themes

    logging.info(f"开始在目录 '{themes_path}' 中查找主题文件...")
    try:
        for filename in os.listdir(themes_path):
            if filename.lower().endswith(".qss"):
                theme_name = os.path.splitext(filename)[0]
                # 创建用户友好的名称
                friendly_name = theme_name.replace('_', ' ').replace('-', ' ').title()
                # 构建相对于基础路径的 *相对路径* (重要!)
                relative_qss_path = os.path.join(themes_subdir_name, filename).replace('\\', '/') # 统一用斜杠
                available_themes[friendly_name] = relative_qss_path
                logging.debug(f"找到主题: '{friendly_name}' -> '{relative_qss_path}'")
        logging.info(f"查找完成，找到 {len(available_themes)} 个主题。")
    except Exception as e:
        logging.error(f"在目录 '{themes_path}' 查找主题文件时出错: {e}", exc_info=True)
        # 在应用启动早期，可能还无法显示 QMessageBox，这里只记录日志
        # QMessageBox.critical(None, "主题错误", f"查找主题文件时发生错误: {e}")

    return available_themes

# ==============================================================================
# 主程序入口
# ==============================================================================
if __name__ == '__main__':
    logging.info("应用程序启动...")

    # 必须先创建 QApplication 实例才能使用 GUI 组件
    app = QApplication(sys.argv)

    # --- 1. 获取可用主题 ---
    available_themes = get_available_themes(THEMES_DIR_NAME)
    friendly_theme_names = sorted(list(available_themes.keys()))

    selected_qss_relative_path = None # 存储用户选择的主题的相对路径
    chosen_theme_name = None          # 存储用户选择的主题的友好名称

    if not friendly_theme_names:
        logging.warning(f"在 '{THEMES_DIR_NAME}' 目录下未找到任何 .qss 主题文件。将使用默认样式。")
        QMessageBox.warning(None, "无主题", f"在 '{THEMES_DIR_NAME}' 目录下未找到主题文件。\n应用程序将以默认样式运行。")
        # 注意：这里没有退出，允许程序以默认样式启动
    else:
        # --- 2. 使用自定义对话框让用户选择 ---
        try:
            dialog = ThemeSelectionDialog(friendly_theme_names)
            result = dialog.exec() # 显示模态对话框
        except Exception as e:
             logging.error(f"显示主题选择对话框时出错: {e}", exc_info=True)
             QMessageBox.critical(None, "界面错误", f"无法显示主题选择对话框: {e}\n应用程序将退出。")
             sys.exit(1)

        # --- 3. 处理用户选择 ---
        if result == QDialog.DialogCode.Accepted:
            chosen_theme_name = dialog.selectedTheme()
            if chosen_theme_name:
                # 根据选择的友好名称找到对应的相对路径
                selected_qss_relative_path = available_themes.get(chosen_theme_name)
                if selected_qss_relative_path:
                    logging.info(f"用户选择了主题: '{chosen_theme_name}' (相对路径: {selected_qss_relative_path})")
                else:
                    # 理论上不应发生，因为列表来自 available_themes 的键
                    logging.error(f"内部错误: 无法在 available_themes 中找到主题 '{chosen_theme_name}' 对应的相对路径。")
                    QMessageBox.critical(None, "内部错误", f"选择的主题 '{chosen_theme_name}' 无效。\n应用程序将退出。")
                    sys.exit(1)
            else:
                 # 理论上不应发生，因为对话框有默认选项且非空
                 logging.error("内部错误: 主题选择对话框返回接受，但未提供有效的主题名称。")
                 QMessageBox.critical(None, "内部错误", "选择主题时发生未知错误。\n应用程序将退出。")
                 sys.exit(1)
        else:
            # 用户点击了 "Cancel" 或关闭了对话框
            logging.info("用户取消了主题选择，应用程序将退出。")
            sys.exit(0) # 用户主动取消，正常退出

    # --- 4. 加载并应用选中的 QSS 文件 (如果用户选择了) ---
    applied_style = False
    if selected_qss_relative_path:
        # 使用 resource_path 获取 QSS 文件的绝对路径用于读取
        qss_absolute_path = resource_path(selected_qss_relative_path)
        logging.info(f"尝试从绝对路径加载样式: {qss_absolute_path}")
        try:
            with open(qss_absolute_path, "r", encoding="utf-8") as f:
                _qss = f.read()
                app.setStyleSheet(_qss) # 应用样式到整个应用程序
                logging.info(f"成功应用样式 '{chosen_theme_name}'。")
                applied_style = True
        except FileNotFoundError:
            logging.error(f"样式文件未找到! 相对路径: '{selected_qss_relative_path}', 计算的绝对路径: '{qss_absolute_path}'。")
            QMessageBox.critical(None, "样式错误", f"无法找到样式文件:\n{selected_qss_relative_path}\n\n应用程序将尝试以默认样式启动。")
        except OSError as e:
             logging.error(f"读取样式文件时发生 OS 错误: {e}. 文件路径: '{qss_absolute_path}'", exc_info=True)
             QMessageBox.critical(None, "样式错误", f"读取样式文件时出错: {e}\n\n应用程序将尝试以默认样式启动。")
        except Exception as e:
            logging.error(f"应用样式 '{chosen_theme_name}' (路径: {qss_absolute_path}) 时发生未知错误: {e}", exc_info=True)
            QMessageBox.warning(None, "样式错误", f"应用样式文件时出错: {e}\n\n应用程序将尝试以默认样式启动。")

    if not applied_style:
         # 如果没有选择主题，或加载失败
         logging.info("未应用任何自定义主题，将使用 Qt 默认样式运行。")


    # --- 5. 创建并显示主窗口 ---
    try:
        main_win = MainWindow() # 创建主窗口实例
        main_win.show()         # 显示主窗口
        logging.info("主窗口已显示。")
    except Exception as e:
        logging.critical(f"创建或显示主窗口时出错: {e}", exc_info=True)
        QMessageBox.critical(None, "启动错误", f"无法初始化主界面: {e}\n应用程序将退出。")
        sys.exit(1)

    # --- 6. 运行应用程序事件循环 ---
    logging.info("进入 Qt 事件循环...")
    try:
        exit_code = app.exec()
        logging.info(f"Qt 事件循环结束，退出码: {exit_code}")
        sys.exit(exit_code)
    except SystemExit as e:
        # 区分是程序内部调用 sys.exit 还是事件循环的自然退出
        if e.code == 0:
            logging.info("应用程序正常退出 (SystemExit code 0)。")
        else:
            logging.warning(f"应用程序通过 sys.exit({e.code}) 退出。")
    except Exception as e:
        # 捕获事件循环期间未处理的异常
        logging.critical(f"应用程序在事件循环中意外崩溃: {e}", exc_info=True)
        # 尝试显示最后的消息，但不保证一定成功
        try:
            QMessageBox.critical(None, "严重错误", f"应用程序遇到严重错误并即将关闭。\n\n错误: {e}")
        except Exception as final_e:
            logging.error(f"在显示最终错误消息时也发生错误: {final_e}")
        sys.exit(1) # 以非零码退出表示错误