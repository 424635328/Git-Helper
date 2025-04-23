# core/db_handler.py
# -*- coding: utf-8 -*-
import sqlite3
import os
import sys  # 导入 sys
import logging
from typing import Union

# 如果主应用程序未配置日志，则配置日志 (可以在主应用中统一配置)
# logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# >>> 新增 resource_path 函数 <<<
def resource_path(relative_path):
    """ Get absolute path to resource, works for dev and for PyInstaller """
    try:
        # PyInstaller creates a temp folder and stores path in _MEIPASS
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)

# 定义数据库文件所在的目录和完整路径 (使用 resource_path)
# >>> 修改了 DB_DIR 和 DB_PATH 的定义 <<<
# 我们仍然定义 DB_DIR 的相对名称，但在 DB_PATH 中使用 resource_path 来获取其绝对路径
DB_DIR_NAME = "database" # 定义相对目录名称
DB_PATH = resource_path(os.path.join(DB_DIR_NAME, "shortcuts.db"))

class DatabaseHandler:
    """处理快捷键组合的数据库操作"""

    def __init__(self, db_path=DB_PATH):
        try:
            # 使用 resource_path 获取数据库目录的绝对路径
            db_dir_abs_path = os.path.dirname(db_path) # 使用传入的 db_path (已经通过 resource_path 处理)
            # 确保数据库文件所在的目录存在
            os.makedirs(db_dir_abs_path, exist_ok=True)
            self.db_path = db_path
            logging.info(f"数据库路径设置为: {self.db_path}") # 记录实际使用的路径
            self._create_table()
        except OSError as e:
            logging.error(f"创建数据库目录失败 '{os.path.dirname(db_path)}': {e}")
            self.db_path = None # 表示数据库路径无效
            # 考虑在此处抛出更明确的异常，例如 FileNotFoundError 或 PermissionError
            # raise FileNotFoundError(f"无法创建数据库目录: {os.path.dirname(db_path)}") from e


    def _get_connection(self):
        """获取数据库连接"""
        if not self.db_path:
            logging.error("数据库路径未设置或无效，无法获取连接。")
            return None
        try:
            conn = sqlite3.connect(self.db_path, timeout=5) # 5 秒超时
            conn.row_factory = sqlite3.Row # 返回字典形式的行
            return conn
        except sqlite3.Error as e:
            logging.error(f"数据库连接错误 ({self.db_path}): {e}")
            return None

    def _close_connection(self, conn):
        """安全关闭数据库连接。"""
        # 代码与之前相同
        if conn:
            try:
                conn.close()
            except sqlite3.Error as e:
                logging.error(f"关闭数据库连接时出错: {e}")

    def _create_table(self):
        """创建 shortcuts 表 (如果不存在)"""
        conn = self._get_connection()
        if not conn: return
        try:
            with conn: # 使用 'with conn' 实现自动提交/回滚
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS shortcuts (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        name TEXT UNIQUE NOT NULL,
                        sequence TEXT NOT NULL,
                        shortcut_key TEXT UNIQUE NOT NULL
                    )
                """)
            logging.info(f"数据库表 'shortcuts' 检查/创建 成功 ({self.db_path}).")
        except sqlite3.Error as e:
            logging.error(f"创建 'shortcuts' 表失败 ({self.db_path}): {e}")
        finally:
            self._close_connection(conn) # 使用辅助函数关闭连接

    def save_shortcut(self, name: str, sequence: str, shortcut_key: str) -> bool:
        """保存或更新快捷键组合"""
        # 代码与之前相同
        conn = self._get_connection()
        if not conn: return False
        success = False
        try:
            with conn:
                # 检查名称或快捷键是否已被 *其他* 条目使用
                cursor_check = conn.execute(
                    "SELECT id FROM shortcuts WHERE (name = ? OR shortcut_key = ?) AND NOT (name = ? AND shortcut_key = ?)",
                    (name, shortcut_key, name, shortcut_key)
                )
                existing = cursor_check.fetchone()
                if existing:
                     logging.warning(f"保存快捷键失败：名称 '{name}' 或快捷键 '{shortcut_key}' 已被其他条目使用。")
                     return False # 表示冲突

                # 插入或替换逻辑：基于唯一的名称进行插入或替换
                conn.execute(
                    """
                    INSERT INTO shortcuts (name, sequence, shortcut_key)
                    VALUES (?, ?, ?)
                    ON CONFLICT(name) DO UPDATE SET
                        sequence = excluded.sequence,
                        shortcut_key = excluded.shortcut_key
                    """,
                    (name, sequence, shortcut_key)
                )
            logging.info(f"快捷键 '{name}' ({shortcut_key}) 已保存。")
            success = True
        except sqlite3.IntegrityError as e:
            logging.warning(f"保存快捷键 '{name}' ({shortcut_key}) 时发生完整性错误（可能是快捷键冲突？）: {e}")
        except sqlite3.Error as e:
            logging.error(f"保存快捷键 '{name}' 失败: {e}")
        finally:
            self._close_connection(conn)
        return success

    def load_shortcuts(self) -> list[dict]:
        """加载所有快捷键组合"""
        # 代码与之前相同
        conn = self._get_connection()
        if not conn: return []
        shortcuts = []
        try:
            cursor = conn.execute("SELECT name, sequence, shortcut_key FROM shortcuts ORDER BY name")
            shortcuts = [dict(row) for row in cursor.fetchall()]
            logging.info(f"成功加载 {len(shortcuts)} 个快捷键。")
        except sqlite3.Error as e:
            logging.error(f"加载快捷键失败: {e}")
        finally:
            self._close_connection(conn)
        return shortcuts

    def delete_shortcut(self, name: str) -> bool:
        """删除指定名称的快捷键"""
        # 代码与之前相同
        conn = self._get_connection()
        if not conn: return False
        success = False
        rows_affected = 0
        try:
            with conn:
                cursor = conn.execute("DELETE FROM shortcuts WHERE name = ?", (name,))
                rows_affected = cursor.rowcount
            if rows_affected > 0:
                logging.info(f"快捷键 '{name}' 已删除。")
                success = True
            else:
                logging.warning(f"未找到要删除的快捷键 '{name}'。")
                success = False
        except sqlite3.Error as e:
            logging.error(f"删除快捷键 '{name}' 失败: {e}")
        finally:
            self._close_connection(conn)
        return success

    # 修改了这一行的类型提示
    def get_shortcut_by_key(self, shortcut_key: str) -> Union[dict, None]:
        """根据快捷键字符串获取快捷键信息"""
        # 代码与之前相同
        conn = self._get_connection()
        if not conn: return None
        shortcut_data = None
        try:
            cursor = conn.execute(
                "SELECT name, sequence, shortcut_key FROM shortcuts WHERE shortcut_key = ?",
                (shortcut_key,)
            )
            row = cursor.fetchone()
            if row:
                shortcut_data = dict(row)
        except sqlite3.Error as e:
            logging.error(f"通过快捷键 '{shortcut_key}' 获取数据失败: {e}")
        finally:
            self._close_connection(conn)
        return shortcut_data