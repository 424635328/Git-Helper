# main.py

import sys
import os
import subprocess
import tempfile
import shutil
import atexit
from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QPushButton, QMessageBox, QLabel, QSizePolicy
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont, QIcon

# --- 配置 ---
ENTRANCE_EXE_NAME = 'EntranceRunner.exe' if sys.platform == "win32" else 'EntranceRunner'
SUBDIR_EXE_NAME = 'FlashGit.exe' if sys.platform == "win32" else 'FlashGit'
APP_ICON_RELATIVE_PATH = os.path.join('GitGuiApp', 'icons', 'app_icon.ico')

temp_dirs_to_clean = []
def cleanup_temp_dirs():
    """程序退出时清理所有创建的临时目录"""
    print("--- 程序退出，开始清理临时目录 ---")
    while temp_dirs_to_clean:
        temp_dir = temp_dirs_to_clean.pop()
        if os.path.exists(temp_dir) and os.path.isdir(temp_dir):
            try:
                shutil.rmtree(temp_dir, ignore_errors=True)
                print(f"已清理临时目录: {temp_dir}")
            except Exception as e:
                print(f"警告：清理临时目录 {temp_dir} 时出错: {e}")
        else:
             print(f"信息：临时目录不存在或不是目录，无需清理: {temp_dir}")
    print("--- 临时目录清理完毕 ---")
atexit.register(cleanup_temp_dirs)


class ScriptRunnerWindow(QWidget):
    def __init__(self):
        super().__init__()
        print("ScriptRunnerWindow __init__ called.")
        self.initUI()
        # 应用赛博朋克样式
        self.applyCyberpunkStyles()

    def initUI(self):
        print("ScriptRunnerWindow initUI called.")
        # 使用中文标题
        self.setWindowTitle('应用程序启动器')
        self.setGeometry(300, 300, 500, 300) # 窗口尺寸

        print(f"尝试设置窗口图标，相对路径: {APP_ICON_RELATIVE_PATH}")
        icon_path = self._get_resource_path(APP_ICON_RELATIVE_PATH)
        if os.path.exists(icon_path) and os.path.isfile(icon_path):
            try:
                self.setWindowIcon(QIcon(icon_path))
                print(f"窗口图标已成功设置: {icon_path}")
            except Exception as e_icon:
                 print(f"警告: 设置窗口图标时出错: {e_icon} (文件路径: {icon_path})")
        else:
            print(f"警告: 找不到窗口图标文件或路径不是文件: {icon_path}")
        # --------------------

        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(35, 35, 35, 35)
        main_layout.setSpacing(25)

        # 使用中文标签
        title_label = QLabel("选择要启动的程序")
        title_label.setObjectName("titleLabel") # QSS 使用这个名字
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        main_layout.addWidget(title_label)

        # --- 按钮 (使用中文文本) ---
        btn_entrance = QPushButton(f'控制台程序') # 中文按钮文本
        btn_entrance.setObjectName("actionButton") # QSS 使用这个名字
        btn_entrance.setToolTip(f"启动内嵌的 {ENTRANCE_EXE_NAME} (控制台界面)") # 中文提示
        btn_entrance.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        btn_entrance.clicked.connect(self.run_entrance_app)
        main_layout.addWidget(btn_entrance)

        btn_subdir_main = QPushButton(f'图形界面程序') # 中文按钮文本
        btn_subdir_main.setObjectName("actionButton") # QSS 使用这个名字
        btn_subdir_main.setToolTip(f"启动内嵌的 {SUBDIR_EXE_NAME} (图形用户界面)") # 中文提示
        btn_subdir_main.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        btn_subdir_main.clicked.connect(self.run_subdir_app)
        main_layout.addWidget(btn_subdir_main)
        # --------------------

        self.setLayout(main_layout)
        print("ScriptRunnerWindow initUI finished.")

    def applyCyberpunkStyles(self):
        """应用赛博朋克风格的 QSS 样式"""
        print("Applying Cyberpunk Styles...")
        # ... QSS 样式代码保持不变 ...
        style_sheet = """
            /* === Main Window === */
            QWidget {
                background-color: #0d0d0d;
                color: #e0e0e0;
                /* 如果中文字体显示不好，可以换成 'Microsoft YaHei UI', 'SimSun', sans-serif */
                font-family: 'Microsoft YaHei UI', 'Consolas', 'Lucida Console', 'Courier New', monospace;
            }

            /* === Title Label === */
            QLabel#titleLabel {
                color: #00ffff; /* Neon Cyan */
                /* 中文可能不需要这么大的字号或间距，可调整 */
                font-size: 24px;
                font-weight: bold;
                qproperty-alignment: AlignCenter;
                padding-bottom: 30px;
                border-bottom: 1px solid #333;
                letter-spacing: 2px; /* 减小字母间距 */
                /* text-transform: uppercase; */ /* 中文不需要大写转换 */
            }

            /* === Action Buttons === */
            QPushButton#actionButton {
                background-color: transparent;
                color: #ff00ff; /* Neon Magenta */
                border: 2px solid #ff00ff;
                padding: 15px 20px;
                /* 中文字号可调整 */
                font-size: 16px;
                font-weight: bold;
                /* text-transform: uppercase; */ /* 中文不需要 */
                outline: none;
                margin-top: 15px;
                /* letter-spacing: 1px; */ /* 中文可能不需要 */
                border-radius: 0px;
            }

            /* Button Hover State */
            QPushButton#actionButton:hover {
                background-color: rgba(255, 0, 255, 0.1);
                color: #ffffff;
                border: 2px solid #ffffff;
            }

            /* Button Pressed State */
            QPushButton#actionButton:pressed {
                background-color: rgba(255, 0, 255, 0.3);
                color: #0d0d0d;
                border: 2px solid #ff00ff;
            }

            /* === ToolTips === */
            QToolTip {
                background-color: #1a1a1a;
                color: #39ff14; /* Neon Lime Green */
                border: 1px solid #39ff14;
                padding: 6px;
                opacity: 230;
                font-size: 13px;
                border-radius: 0px;
                /* 确保提示的字体也支持中文 */
                font-family: 'Microsoft YaHei UI', sans-serif;
            }

            /* === Message Boxes (保持风格，文本由代码设置) === */
            QMessageBox {
                background-color: #111;
                font-family: 'Microsoft YaHei UI', 'Consolas', monospace;
            }
            QMessageBox QLabel { /* The message text */
                color: #00ffff; /* Neon Cyan text */
                font-size: 14px;
                min-width: 300px;
                padding: 15px;
            }
             QMessageBox QPushButton { /* Buttons inside message box */
                background-color: #222;
                color: #39ff14; /* Lime Green text */
                border: 1px solid #39ff14;
                padding: 8px 18px;
                border-radius: 0px;
                font-size: 13px;
                min-width: 90px;
                min-height: 30px;
                font-weight: bold;
                /* text-transform: uppercase; */ /* 中文不需要 */
             }
             QMessageBox QPushButton:hover {
                background-color: #333;
                border: 1px solid #90ee90;
                color: #90ee90;
             }
             QMessageBox QPushButton:pressed {
                 background-color: #111;
                 color: #39ff14;
             }
        """
        self.setStyleSheet(style_sheet)
        print("Cyberpunk Styles Applied.")

    def _get_base_path(self):
        """获取资源文件的基础路径（打包后是_MEIPASS，否则是脚本目录）"""
        if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
            base = sys._MEIPASS
            print(f"_get_base_path (frozen): {base}")
            return base
        else:
            base = os.path.dirname(os.path.abspath(__file__))
            print(f"_get_base_path (script): {base}")
            return base

    def _get_resource_path(self, relative_path):
        """计算资源的绝对路径"""
        base_path = self._get_base_path()
        resource_path = os.path.normpath(os.path.join(base_path, relative_path))
        print(f"Calculated resource path for '{relative_path}': {resource_path}")
        return resource_path

    def _run_executable(self, exe_name_in_bundle):
        """ 查找、提取并运行嵌入的可执行文件 """
        print(f"_run_executable called for bundled exe: {exe_name_in_bundle}")
        temp_dir = None
        extracted_exe_path = None # 在 finally 中可能需要访问

        # --- 获取原始工作目录 (关键改动) ---
        # 这是用户运行主程序 (FlashGit.exe) 时所在的目录，
        # 我们假设这里就是用户想要操作的 Git 仓库根目录。
        original_cwd = os.getcwd()
        print(f"主程序启动时的工作目录 (预期 Git 仓库路径): {original_cwd}")
        # ---------------------------------

        try:
            # 获取内嵌可执行文件的路径
            embedded_exe_path = self._get_resource_path(exe_name_in_bundle)
            if not os.path.exists(embedded_exe_path) or not os.path.isfile(embedded_exe_path):
                # 中文错误消息
                QMessageBox.warning(self, '错误 - 资源未找到',
                                    f'无法在程序包内找到所需的资源文件或路径不是文件：\n<b>{exe_name_in_bundle}</b>'
                                    f'<br><br>请检查打包配置 (--add-data "{exe_name_in_bundle};.").')
                print(f"错误：嵌入的资源未找到或不是文件 - {embedded_exe_path}")
                return

            # 创建临时目录用于存放提取出的 exe
            pid = os.getpid()
            prefix = f"{os.path.splitext(exe_name_in_bundle)[0]}_{pid}_"
            temp_dir = tempfile.mkdtemp(prefix=prefix)
            print(f"创建临时目录: {temp_dir}")
            temp_dirs_to_clean.append(temp_dir) # 注册以便程序退出时清理

            # 构造提取后的 exe 的完整路径
            extracted_exe_path = os.path.join(temp_dir, exe_name_in_bundle)
            print(f"准备提取到: {extracted_exe_path}")

            # 将内嵌的 exe 复制到临时目录
            shutil.copy2(embedded_exe_path, extracted_exe_path)
            print(f"成功提取 {exe_name_in_bundle} 到临时目录。")

            print(f"尝试启动提取后的程序: {extracted_exe_path}")
            # --- 修改这里：使用原始工作目录作为子进程的 CWD (关键改动) ---
            # 这样子进程 (EntranceRunner.exe) 就能在其期望的 Git 仓库目录下运行
            print(f"将为子进程设置工作目录 (CWD): {original_cwd}")
            process = subprocess.Popen([extracted_exe_path], cwd=original_cwd)
            # ----------------------------------------------------
            print(f"已启动进程 PID: {process.pid} (对应程序: {os.path.basename(extracted_exe_path)})，工作目录设置为 {original_cwd}")

            print("子程序已启动，正在关闭主选择窗口...")
            self.close() # 启动子程序后关闭启动器窗口

        except PermissionError as pe:
             # 中文错误消息
             error_message = f'权限错误：无法提取或运行 <b>{exe_name_in_bundle}</b>。<br>'\
                             f'可能原因：临时目录写入权限不足 ({temp_dir})，或杀毒软件阻止。<br><br><pre>错误详情: {pe}</pre>'
             QMessageBox.critical(self, '权限错误', error_message)
             print(f"权限错误: {pe}")
             import traceback
             traceback.print_exc()
        except FileNotFoundError as fnfe:
             # 中文错误消息
             # 确保 extracted_exe_path 在此作用域可见
             err_path = extracted_exe_path if extracted_exe_path else "未知路径"
             error_message = f'文件未找到错误：无法启动提取后的文件 <b>{err_path}</b>。<br><br><pre>错误详情: {fnfe}</pre>'
             QMessageBox.critical(self, '文件未找到错误', error_message)
             print(f"文件未找到错误: {fnfe}")
             import traceback
             traceback.print_exc()
        except Exception as e:
            # 中文错误消息
            error_message = f'处理或启动嵌入程序 <b>{exe_name_in_bundle}</b> 时发生未知错误：<br><br><pre>错误详情: {e}</pre>'
            QMessageBox.critical(self, '未知错误', error_message)
            print(f"错误: 处理/启动 {exe_name_in_bundle} 时发生未知错误: {e}")
            import traceback
            traceback.print_exc()
        # finally 块不需要，因为临时目录清理已由 atexit 处理

    def run_entrance_app(self):
        """启动嵌入的控制台程序 (EntranceRunner.exe)"""
        print("run_entrance_app called.")
        self._run_executable(ENTRANCE_EXE_NAME)

    def run_subdir_app(self):
        """启动嵌入的图形界面程序 (FlashGit.exe)"""
        print("run_subdir_app called.")
        self._run_executable(SUBDIR_EXE_NAME)

if __name__ == '__main__':
    print("--- 程序启动 ---")
    try:
        print("初始化应用程序...")
        app = QApplication(sys.argv)
        print("应用程序已初始化。")

        print("创建启动窗口...")
        window = ScriptRunnerWindow()
        print("启动窗口已创建。")

        print("显示窗口...")
        window.show()
        print("窗口已显示。")

        print("进入主事件循环...")
        exit_code = app.exec()
        print(f"事件循环结束，退出码: {exit_code}")
        sys.exit(exit_code)

    except Exception as e:
        print("\n!!! 程序启动时发生严重错误 !!!")
        import traceback
        traceback.print_exc()
        # 尝试使用 tkinter 显示错误，作为备用方案
        try:
            import tkinter as tk
            from tkinter import messagebox
            root = tk.Tk()
            root.withdraw() # 隐藏 tkinter 主窗口
            messagebox.showerror("启动错误", f"程序启动时发生严重错误:\n\n{e}\n\n请查看控制台获取详细信息。")
            root.destroy()
        except Exception:
             # 如果 tkinter 也失败，则使用 input 阻塞
             input(f"程序启动时发生严重错误: {e}\n按 Enter 键退出...")

    finally:
        # 注意: atexit 注册的 cleanup_temp_dirs 会在这里之后被调用
        print("--- 程序即将退出 (atexit 清理将执行) ---")