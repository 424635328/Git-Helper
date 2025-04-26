# main.py
import sys
import logging
import os
from PyQt6.QtWidgets import QApplication, QMessageBox, QDialog # 移除 QInputDialog, 添加 QDialog
from PyQt6.QtGui import QColor
from PyQt6.QtCore import Qt
from ui.main_window import MainWindow
from theme_dialog import ThemeSelectionDialog # <--- 导入新的对话框类

# 配置日志记录 (保持不变)
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - [%(levelname)s] - %(module)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
    ]
)

# 定义 QSS 文件的目录 (保持不变)
THEMES_DIR = "styles"

# get_available_themes 函数 (保持不变)
def get_available_themes(base_path, themes_subdir):
    """查找指定目录下可用的 QSS 主题文件"""
    themes_path = os.path.join(base_path, themes_subdir)
    available_themes = {}
    if not os.path.isdir(themes_path):
        logging.warning(f"主题目录 '{themes_path}' 不存在。")
        return available_themes

    try:
        for filename in os.listdir(themes_path):
            if filename.lower().endswith(".qss"):
                theme_name = os.path.splitext(filename)[0]
                # 让主题名更友好 (首字母大写，替换下划线)
                friendly_name = theme_name.replace('_', ' ').replace('-', ' ').title()
                available_themes[friendly_name] = filename # 存储 友好名称 -> 文件名
        logging.info(f"找到的主题文件: {list(available_themes.values())}")
    except Exception as e:
        logging.error(f"查找主题文件时出错: {e}", exc_info=True)
        QMessageBox.critical(None, "主题错误", f"查找主题文件时发生错误: {e}")

    return available_themes

if __name__ == '__main__':
    logging.info("应用程序启动...")
    # 注意：在创建 QApplication 之后才能使用 GUI 组件
    app = QApplication(sys.argv)

    base_dir = os.path.dirname(__file__)

    # --- 1. 获取可用主题 ---
    available_themes = get_available_themes(base_dir, THEMES_DIR)
    # 使用友好名称列表给用户选择
    friendly_theme_names = sorted(list(available_themes.keys()))

    selected_qss_file = None
    chosen_theme_name = None # 用于日志记录

    if not friendly_theme_names:
        logging.warning(f"在 '{THEMES_DIR}' 目录下未找到任何 .qss 主题文件。")
        QMessageBox.warning(None, "无主题", f"在 '{THEMES_DIR}' 目录下未找到主题文件。\n应用程序将以默认样式运行。")
        # 如果没有主题必须退出，取消下面的注释
        # QMessageBox.critical(None, "启动错误", f"在 '{THEMES_DIR}' 目录下未找到主题文件。\n应用程序无法启动。")
        # sys.exit(1)
    else:
        # --- 2. 使用自定义对话框让用户选择 ---
        dialog = ThemeSelectionDialog(friendly_theme_names)
        result = dialog.exec() # 显示模态对话框

        # --- 3. 处理用户选择 ---
        if result == QDialog.DialogCode.Accepted:
            chosen_theme_name = dialog.selectedTheme()
            if chosen_theme_name:
                # 根据选择的友好名称找到对应的文件名
                selected_qss_filename = available_themes.get(chosen_theme_name)
                if selected_qss_filename:
                    selected_qss_file = os.path.join(THEMES_DIR, selected_qss_filename)
                    logging.info(f"用户选择了主题: '{chosen_theme_name}' (文件: {selected_qss_filename})")
                else:
                    # 这理论上不应该发生
                    logging.error(f"内部错误: 无法找到主题 '{chosen_theme_name}' 对应的文件名。")
                    QMessageBox.critical(None, "内部错误", "选择的主题无效。")
                    sys.exit(1)
            else:
                 # 这理论上也不应该发生，因为列表非空且有默认选中
                 logging.error("内部错误: 对话框接受但未返回有效选择。")
                 QMessageBox.critical(None, "内部错误", "选择主题时发生未知错误。")
                 sys.exit(1)
        else:
            # 用户点击了 "Cancel" 或关闭了对话框
            logging.info("用户取消了主题选择，应用程序将退出。")
            # 不需要额外的 QMessageBox，因为用户主动取消
            sys.exit(0) # 正常退出

    # --- 4. 加载并应用选中的 QSS 文件 ---
    # 注意：这一步在对话框关闭 *之后* 执行
    if selected_qss_file:
        qss_path = os.path.join(base_dir, selected_qss_file)
        try:
            with open(qss_path, "r", encoding="utf-8") as f:
                _qss = f.read()
                # --- 在这里应用最终的主题样式 ---
                app.setStyleSheet(_qss)
                logging.info(f"已从 {selected_qss_file} 文件应用样式。")
        except FileNotFoundError:
            logging.error(f"样式文件 {selected_qss_file} 未找到 (路径: {qss_path})。")
            QMessageBox.critical(None, "样式错误", f"样式文件 {selected_qss_file} 未找到。\n应用程序将尝试以默认样式启动。")
            # 出错时不退出，尝试无样式启动
            selected_qss_file = None # 清除选择，避免后续问题
        except Exception as e:
            logging.warning(f"应用样式 '{chosen_theme_name}' 失败: {e}")
            QMessageBox.warning(None, "样式错误", f"应用样式文件 {selected_qss_file} 时出错: {e}\n应用程序将尝试以默认样式启动。")
            # 出错时不退出，尝试无样式启动
            selected_qss_file = None # 清除选择
    else:
         # 如果之前没有找到主题或加载失败，则记录信息
        logging.info("未选择或加载主题文件，将使用默认样式运行。")


    # --- 5. 显示主窗口 ---
    main_win = MainWindow()
    # 如果有样式应用失败，主窗口将使用默认样式或部分应用的样式
    main_win.show()

    # --- 6. 运行应用程序事件循环 (保持不变) ---
    try:
        sys.exit(app.exec())
    except SystemExit:
        logging.info("应用程序正常退出。")
    except Exception as e:
        logging.critical(f"应用程序意外退出: {e}", exc_info=True)
        error_message = f"应用程序发生意外错误并即将关闭。\n错误详情: {e}"
        QMessageBox.critical(None, "应用程序错误", error_message)
        sys.exit(1)