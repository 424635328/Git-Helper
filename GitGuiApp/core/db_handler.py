# core/db_handler.py
import sqlite3
import os
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

DB_DIR = "database"
DB_PATH = os.path.join(DB_DIR, "shortcuts.db")

class DatabaseHandler:
    """处理快捷键组合的数据库操作"""

    def __init__(self, db_path=DB_PATH):
        os.makedirs(os.path.dirname(db_path), exist_ok=True) # 确保目录存在
        self.db_path = db_path
        self._create_table()

    def _get_connection(self):
        """获取数据库连接"""
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row # 返回字典形式的行
            return conn
        except sqlite3.Error as e:
            logging.error(f"数据库连接错误: {e}")
            return None

    def _create_table(self):
        """创建 shortcuts 表 (如果不存在)"""
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
            logging.info("数据库表 'shortcuts' 检查/创建 成功。")
        except sqlite3.Error as e:
            logging.error(f"创建 'shortcuts' 表失败: {e}")
        finally:
            if conn:
                conn.close()

    def save_shortcut(self, name: str, sequence: str, shortcut_key: str) -> bool:
        """保存或更新快捷键组合"""
        conn = self._get_connection()
        if not conn: return False
        try:
            with conn:
                # 尝试更新，如果名称或快捷键已存在
                cursor = conn.execute(
                    "UPDATE shortcuts SET sequence = ?, shortcut_key = ? WHERE name = ?",
                    (sequence, shortcut_key, name)
                )
                if cursor.rowcount == 0: # 如果没有更新（名称不存在），则插入新记录
                     cursor = conn.execute(
                        "UPDATE shortcuts SET sequence = ?, name = ? WHERE shortcut_key = ?",
                        (sequence, name, shortcut_key)
                     )
                     if cursor.rowcount == 0: # 快捷键也不存在，插入
                        conn.execute(
                            "INSERT INTO shortcuts (name, sequence, shortcut_key) VALUES (?, ?, ?)",
                            (name, sequence, shortcut_key)
                        )
            logging.info(f"快捷键 '{name}' ({shortcut_key}) 已保存。")
            return True
        except sqlite3.IntegrityError:
            logging.warning(f"保存快捷键 '{name}' ({shortcut_key}) 失败：名称或快捷键已存在。")
            return False
        except sqlite3.Error as e:
            logging.error(f"保存快捷键 '{name}' 失败: {e}")
            return False
        finally:
            if conn:
                conn.close()

    def load_shortcuts(self) -> list[dict]:
        """加载所有快捷键组合"""
        conn = self._get_connection()
        if not conn: return []
        shortcuts = []
        try:
            with conn:
                cursor = conn.execute("SELECT name, sequence, shortcut_key FROM shortcuts ORDER BY name")
                shortcuts = [dict(row) for row in cursor.fetchall()]
            logging.info(f"成功加载 {len(shortcuts)} 个快捷键。")
        except sqlite3.Error as e:
            logging.error(f"加载快捷键失败: {e}")
        finally:
            if conn:
                conn.close()
        return shortcuts

    def delete_shortcut(self, name: str) -> bool:
        """删除指定名称的快捷键"""
        conn = self._get_connection()
        if not conn: return False
        try:
            with conn:
                cursor = conn.execute("DELETE FROM shortcuts WHERE name = ?", (name,))
            if cursor.rowcount > 0:
                logging.info(f"快捷键 '{name}' 已删除。")
                return True
            else:
                logging.warning(f"未找到要删除的快捷键 '{name}'。")
                return False
        except sqlite3.Error as e:
            logging.error(f"删除快捷键 '{name}' 失败: {e}")
            return False
        finally:
            if conn:
                conn.close()

    def get_shortcut_by_key(self, shortcut_key: str) -> dict | None:
        """根据快捷键字符串获取快捷键信息"""
        conn = self._get_connection()
        if not conn: return None
        shortcut_data = None
        try:
            with conn:
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
            if conn:
                conn.close()
        return shortcut_data