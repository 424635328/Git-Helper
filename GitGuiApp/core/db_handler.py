# -*- coding: utf-8 -*-
import sqlite3
import os
import sys
import logging
from typing import Union, List, Dict, Optional

def resource_path(relative_path: str) -> str:
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(os.path.dirname(os.path.dirname(__file__))) # 定位到项目根目录或包含 core 的目录
        # 或者，如果脚本直接在项目根目录运行，使用下面的行
        # base_path = os.path.abspath(".")

    return os.path.join(base_path, relative_path)

class DatabaseHandler:

    def __init__(self, db_path: Optional[str] = None):
        if db_path is None:
            # 关键修改：使用 resource_path 来定位数据库文件
            # "database/shortcuts.db" 对应 --add-data "database:." 的打包结构
            self.db_path = resource_path(os.path.join("database", "shortcuts.db"))
        else:
            self.db_path = db_path

        try:
            os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
            self._create_table()
        except OSError as e:
            logging.error(f"创建数据库目录失败 '{os.path.dirname(self.db_path)}': {e}")
            self.db_path = None
        except Exception as e:
             logging.error(f"初始化数据库处理器时发生未知错误: {e}")
             self.db_path = None


    def _get_connection(self) -> Optional[sqlite3.Connection]:
        if not self.db_path:
            logging.error("数据库路径未设置或无效，无法获取连接。")
            return None
        try:
            conn = sqlite3.connect(self.db_path, timeout=5)
            conn.row_factory = sqlite3.Row
            return conn
        except sqlite3.Error as e:
            logging.error(f"数据库连接错误 ({self.db_path}): {e}")
            return None

    def _close_connection(self, conn: Optional[sqlite3.Connection]):
        if conn:
            try:
                conn.close()
            except sqlite3.Error as e:
                logging.error(f"关闭数据库连接时出错: {e}")

    def _create_table(self):
        conn = self._get_connection()
        if not conn: return
        try:
            with conn:
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
            self._close_connection(conn)

    def save_shortcut(self, name: str, sequence: str, shortcut_key: str) -> bool:
        conn = self._get_connection()
        if not conn: return False
        success = False
        try:
            with conn:
                cursor_check = conn.execute(
                    "SELECT id FROM shortcuts WHERE (name = ? OR shortcut_key = ?) AND NOT (name = ? AND shortcut_key = ?)",
                    (name, shortcut_key, name, shortcut_key)
                )
                existing = cursor_check.fetchone()
                if existing:
                     logging.warning(f"保存快捷键失败：名称 '{name}' 或快捷键 '{shortcut_key}' 已被其他条目使用。")
                     return False

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
            logging.warning(f"保存快捷键 '{name}' ({shortcut_key}) 时发生完整性错误: {e}")
        except sqlite3.Error as e:
            logging.error(f"保存快捷键 '{name}' 失败: {e}")
        finally:
            self._close_connection(conn)
        return success

    def load_shortcuts(self) -> List[Dict]:
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

    def get_shortcut_by_key(self, shortcut_key: str) -> Optional[Dict]:
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