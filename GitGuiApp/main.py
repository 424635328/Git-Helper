import sys
import os
import logging
from PyQt6.QtWidgets import QApplication, QMessageBox, QDialog
from PyQt6.QtGui import QColor, QIcon
from PyQt6.QtCore import Qt
from ui.main_window import MainWindow
from theme_dialog import ThemeSelectionDialog


def resource_path(relative_path):
  """ 获取资源的绝对路径，适用于开发环境和 PyInstaller 打包后的环境 """
  try:
    base_path = sys._MEIPASS
  except AttributeError:
    base_path = os.path.abspath(os.path.dirname(__file__))
  return os.path.join(base_path, relative_path)


logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - [%(levelname)s] - %(module)s:%(lineno)d - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
    ]
)


THEMES_DIR_NAME = "styles"


def get_available_themes(themes_subdir_name):
    """查找指定相对目录下可用的 QSS 主题文件"""
    themes_path = resource_path(themes_subdir_name)
    available_themes = {}

    if not os.path.isdir(themes_path):
        logging.warning(f"主题目录 '{themes_path}' 不存在或不是一个目录。")
        return available_themes

    logging.info(f"开始在目录 '{themes_path}' 中查找主题文件...")
    try:
        for filename in os.listdir(themes_path):
            if filename.lower().endswith(".qss"):
                theme_name = os.path.splitext(filename)[0]
                friendly_name = theme_name.replace('_', ' ').replace('-', ' ').title()
                relative_qss_path = os.path.join(themes_subdir_name, filename).replace('\\', '/')
                available_themes[friendly_name] = relative_qss_path
                logging.debug(f"找到主题: '{friendly_name}' -> '{relative_qss_path}'")
        logging.info(f"查找完成，找到 {len(available_themes)} 个主题。")
    except Exception as e:
        logging.error(f"在目录 '{themes_path}' 查找主题文件时出错: {e}", exc_info=True)

    return available_themes


if __name__ == '__main__':
    logging.info("应用程序启动...")

    app = QApplication(sys.argv)
    
    icon_relative_path = "icons/app_icon.png" # 定义图标相对路径
    icon_absolute_path = resource_path(icon_relative_path)

    if os.path.exists(icon_absolute_path):
        app.setWindowIcon(QIcon(icon_absolute_path)) # 设置图标
        logging.info(f"应用程序图标已设置: {icon_absolute_path}")
    else:
        logging.warning(f"应用程序图标文件未找到: {icon_absolute_path}. 将使用默认图标。")
        # 你也可以在这里决定是否要弹出一个警告，但通常不必要
        QMessageBox.warning(None, "图标缺失", f"找不到应用程序图标文件:\n{icon_relative_path}")

    available_themes = get_available_themes(THEMES_DIR_NAME)
    friendly_theme_names = sorted(list(available_themes.keys()))

    selected_qss_relative_path = None
    chosen_theme_name = None

    if not friendly_theme_names:
        logging.warning(f"在 '{THEMES_DIR_NAME}' 目录下未找到任何 .qss 主题文件。将使用默认样式。")
        QMessageBox.warning(None, "无主题", f"在 '{THEMES_DIR_NAME}' 目录下未找到主题文件。\n应用程序将以默认样式运行。")
    else:
        try:
            dialog = ThemeSelectionDialog(friendly_theme_names)
            result = dialog.exec()
        except Exception as e:
             logging.error(f"显示主题选择对话框时出错: {e}", exc_info=True)
             QMessageBox.critical(None, "界面错误", f"无法显示主题选择对话框: {e}\n应用程序将退出。")
             sys.exit(1)

        if result == QDialog.DialogCode.Accepted:
            chosen_theme_name = dialog.selectedTheme()
            if chosen_theme_name:
                selected_qss_relative_path = available_themes.get(chosen_theme_name)
                if selected_qss_relative_path:
                    logging.info(f"用户选择了主题: '{chosen_theme_name}' (相对路径: {selected_qss_relative_path})")
                else:
                    logging.error(f"内部错误: 无法在 available_themes 中找到主题 '{chosen_theme_name}' 对应的相对路径。")
                    QMessageBox.critical(None, "内部错误", f"选择的主题 '{chosen_theme_name}' 无效。\n应用程序将退出。")
                    sys.exit(1)
            else:
                 logging.error("内部错误: 主题选择对话框返回接受，但未提供有效的主题名称。")
                 QMessageBox.critical(None, "内部错误", "选择主题时发生未知错误。\n应用程序将退出。")
                 sys.exit(1)
        else:
            logging.info("用户取消了主题选择，应用程序将退出。")
            sys.exit(0)

    applied_style = False
    if selected_qss_relative_path:
        qss_absolute_path = resource_path(selected_qss_relative_path)
        logging.info(f"尝试从绝对路径加载样式: {qss_absolute_path}")
        try:
            with open(qss_absolute_path, "r", encoding="utf-8") as f:
                _qss = f.read()
                app.setStyleSheet(_qss)
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
         logging.info("未应用任何自定义主题，将使用 Qt 默认样式运行。")


    try:
        main_win = MainWindow()
        main_win.show()
        logging.info("主窗口已显示。")
    except Exception as e:
        logging.critical(f"创建或显示主窗口时出错: {e}", exc_info=True)
        QMessageBox.critical(None, "启动错误", f"无法初始化主界面: {e}\n应用程序将退出。")
        sys.exit(1)

    logging.info("进入 Qt 事件循环...")
    try:
        exit_code = app.exec()
        logging.info(f"Qt 事件循环结束，退出码: {exit_code}")
        sys.exit(exit_code)
    except SystemExit as e:
        if e.code == 0:
            logging.info("应用程序正常退出 (SystemExit code 0)。")
        else:
            logging.warning(f"应用程序通过 sys.exit({e.code}) 退出。")
    except Exception as e:
        logging.critical(f"应用程序在事件循环中意外崩溃: {e}", exc_info=True)
        try:
            QMessageBox.critical(None, "严重错误", f"应用程序遇到严重错误并即将关闭。\n\n错误: {e}")
        except Exception as final_e:
            logging.error(f"在显示最终错误消息时也发生错误: {final_e}")
        sys.exit(1)
        
        