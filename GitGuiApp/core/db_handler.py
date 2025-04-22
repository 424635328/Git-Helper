# core/db_handler.py
import sqlite3
import os
import logging

# Configure logging if not already configured by the main application
# logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

DB_DIR = "database"
DB_PATH = os.path.join(DB_DIR, "shortcuts.db")

class DatabaseHandler:
    """处理快捷键组合的数据库操作"""

    def __init__(self, db_path=DB_PATH):
        try:
            # Ensure the directory for the database exists
            os.makedirs(os.path.dirname(db_path), exist_ok=True)
            self.db_path = db_path
            self._create_table()
        except OSError as e:
            logging.error(f"创建数据库目录失败 '{os.path.dirname(db_path)}': {e}")
            # Decide how to handle this - maybe raise the exception?
            # For now, log and continue, but connection attempts will likely fail.
            self.db_path = None # Indicate DB path is invalid


    def _get_connection(self):
        """获取数据库连接"""
        if not self.db_path:
            logging.error("数据库路径未设置或无效，无法获取连接。")
            return None
        try:
            # Consider adding a timeout to connect
            conn = sqlite3.connect(self.db_path, timeout=5) # 5 second timeout
            conn.row_factory = sqlite3.Row # 返回字典形式的行
            return conn
        except sqlite3.Error as e:
            logging.error(f"数据库连接错误 ({self.db_path}): {e}")
            return None

    def _close_connection(self, conn):
        """Safely close the database connection."""
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
            with conn: # Use 'with conn' for automatic commit/rollback
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
            self._close_connection(conn) # Use the helper to close

    def save_shortcut(self, name: str, sequence: str, shortcut_key: str) -> bool:
        """保存或更新快捷键组合"""
        conn = self._get_connection()
        if not conn: return False
        success = False
        try:
            with conn:
                # Check if name or shortcut_key already exists for *other* entries
                cursor_check = conn.execute(
                    "SELECT id FROM shortcuts WHERE (name = ? OR shortcut_key = ?) AND NOT (name = ? AND shortcut_key = ?)",
                    (name, shortcut_key, name, shortcut_key)
                )
                existing = cursor_check.fetchone()
                if existing:
                     logging.warning(f"保存快捷键失败：名称 '{name}' 或快捷键 '{shortcut_key}' 已被其他条目使用。")
                     return False # Indicate conflict

                # Upsert logic: Insert or replace based on unique name
                # Using INSERT OR REPLACE might be simpler if name is the primary unique identifier intended
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
                # The above assumes name is the key identifier. If shortcut_key should also be unique
                # across different names, the initial check is necessary.
            logging.info(f"快捷键 '{name}' ({shortcut_key}) 已保存。")
            success = True
        except sqlite3.IntegrityError as e:
            # This might still happen with ON CONFLICT if there's another UNIQUE constraint failing (e.g., shortcut_key)
            logging.warning(f"保存快捷键 '{name}' ({shortcut_key}) 时发生完整性错误（可能是快捷键冲突？）: {e}")
        except sqlite3.Error as e:
            logging.error(f"保存快捷键 '{name}' 失败: {e}")
        finally:
            self._close_connection(conn)
        return success

    def load_shortcuts(self) -> list[dict]:
        """加载所有快捷键组合"""
        conn = self._get_connection()
        if not conn: return []
        shortcuts = []
        try:
            # No 'with conn' needed for SELECT typically, but doesn't hurt
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
                success = False # Explicitly false if not found
        except sqlite3.Error as e:
            logging.error(f"删除快捷键 '{name}' 失败: {e}")
        finally:
            self._close_connection(conn)
        return success

    def get_shortcut_by_key(self, shortcut_key: str) -> dict | None:
        """根据快捷键字符串获取快捷键信息"""
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