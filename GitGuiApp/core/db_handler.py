# core/db_handler.py
# -*- coding: utf-8 -*-
import sqlite3
import os
import logging
import sys
import appdirs # 导入 appdirs 库
from typing import Union

# 如果主应用程序未配置日志，则配置日志
# logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# 定义数据库文件所在的目录名和文件名
# 这些是相对于应用程序数据目录的名称，而不是项目源目录
DB_DIR_NAME = "database"
DB_FILENAME = "shortcuts.db"

# 定义应用程序名称，用于确定用户数据目录
APP_NAME = "GitGuiApp" # 请根据你的应用程序名称修改

class DatabaseHandler:
    """处理快捷键组合的数据库操作"""

    def __init__(self):
        """
        初始化数据库处理器，确定数据库文件的实际路径。
        数据库文件将存储在用户应用程序数据目录中以保证持久化。
        """
        # 使用 appdirs 确定用户应用程序数据目录
        # 这是一个跨平台获取持久化存储路径的标准方法
        # user_data_dir(appname, appauthor, ...)
        # appauthor 是可选的，但建议填写
        # ensure_dir=True 会确保返回的目录是存在的 (appdirs v1.4.4+)
        # 如果你的 appdirs 版本较低，可能需要手动 os.makedirs
        try:
            # 获取用户数据目录，并在其下创建应用名称子目录
            app_data_base = appdirs.user_data_dir(APP_NAME)
            # 构建完整的数据库目录和文件路径
            self.db_dir = os.path.join(app_data_base, DB_DIR_NAME)
            self.db_path = os.path.join(self.db_dir, DB_FILENAME)

            logging.info(f"Determined persistent database path: {self.db_path}")

            # 确保数据库目录存在。这对于第一次运行应用程序时创建目录非常重要。
            os.makedirs(self.db_dir, exist_ok=True)
            logging.info(f"Database directory '{self.db_dir}' checked/created successfully.")

            # 创建数据库表 (如果不存在)
            self._create_table()

        except Exception as e: # 捕获 appdirs 可能抛出的异常或 os.makedirs 的 OSError
            logging.error(f"Failed to initialize database handler: {e}")
            # 设置 db_path 为 None 以指示后续数据库操作将失败
            self.db_path = None


    def _get_connection(self):
        """获取数据库连接"""
        if not self.db_path:
            logging.error("数据库路径未设置或无效，无法获取连接。")
            return None
        # 检查文件是否存在（可选，但有助于区分目录创建失败和文件不存在）
        # if not os.path.exists(self.db_path):
        #     logging.warning(f"Database file not found at {self.db_path}. It will be created on first save/table creation.")

        try:
            # 考虑添加连接超时
            # check_same_thread=False 是必需的，如果从多个线程访问同一个连接
            # 但对于典型的 GUI 应用，主线程处理所有数据库操作时，保持 True (默认) 更安全。
            # 如果遇到多线程问题，可以考虑连接池或使用 check_same_thread=False (但要注意并发写入)
            conn = sqlite3.connect(self.db_path, timeout=5) # 5 秒超时
            conn.row_factory = sqlite3.Row # 返回字典形式的行
            return conn
        except sqlite3.Error as e:
            logging.error(f"数据库连接错误 ({self.db_path}): {e}")
            return None

    def _close_connection(self, conn):
        """安全关闭数据库连接。"""
        if conn:
            try:
                conn.close()
            except sqlite3.Error as e:
                logging.error(f"关闭数据库连接时出错: {e}")

    def _create_table(self):
        """创建 shortcuts 表 (如果不存在)"""
        # 在 __init__ 中调用时，已经确保了 self.db_path 有效
        conn = self._get_connection()
        if not conn:
            logging.error("无法获取连接来创建表。")
            return
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
            # 这里不应该设置 self.db_path = None，因为目录和文件路径本身是有效的，只是创建表失败了
        finally:
            self._close_connection(conn) # 使用辅助函数关闭连接

    # 以下方法 (save_shortcut, load_shortcuts, delete_shortcut, get_shortcut_by_key)
    # 逻辑与之前相同，它们都依赖于 self._get_connection() 来获取有效的连接，
    # 而 _get_connection() 现在使用持久化路径 self.db_path。
    # 因此，这些方法的实现不需要改变。
    # 只是为了完整性，将它们保留在这里。

    def save_shortcut(self, name: str, sequence: str, shortcut_key: str) -> bool:
        """保存或更新快捷键组合"""
        conn = self._get_connection()
        if not conn: return False
        success = False
        try:
            with conn:
                # 检查名称或快捷键是否已被 *其他* 条目使用
                # 注意：这个检查在并发写入时可能有竞态条件，但在单用户桌面应用中通常不是问题。
                # 如果 shortcut_key 已经存在于另一个名称下，INSERT OR REPLACE ON CONFLICT(name) 不会阻止 Unique 约束错误。
                # 所以我们在这里再次检查或依赖 IntegrityError 捕获。依赖 IntegrityError 更简洁。
                # 原来的预检查逻辑有点复杂且不能完全防止竞态条件，我们移除它，依赖 DB 的 UNIQUE 约束。

                 # 首先检查是否是快捷键冲突 (这是一个更强的约束)
                cursor_key_check = conn.execute(
                    "SELECT id, name FROM shortcuts WHERE shortcut_key = ? AND name != ?",
                    (shortcut_key, name)
                )
                key_conflict_item = cursor_key_check.fetchone()
                if key_conflict_item:
                    logging.warning(f"保存快捷键失败：快捷键 '{shortcut_key}' 已被条目 '{key_conflict_item['name']}' (ID: {key_conflict_item['id']}) 使用。")
                    return False # 快捷键冲突，且不是当前要更新的条目 (如果name匹配的话)

                # 然后尝试插入或替换。如果 name 存在，则更新。如果 name 不存在，则插入。
                # 如果此时 shortcut_key 还是冲突 (例如并发写入，或者快捷键没变但名称变了导致新的名称冲突)，
                # 将由 IntegrityError 捕获。
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
            # 如果 UNIQUE 约束失败，最可能是 shortcut_key 冲突
            logging.warning(f"保存快捷键 '{name}' ({shortcut_key}) 时发生完整性错误（可能是快捷键冲突？）: {e}")
            success = False # 确保返回 False
        except sqlite3.Error as e:
            logging.error(f"保存快捷键 '{name}' 失败: {e}")
            success = False # 确保返回 False
        finally:
            self._close_connection(conn)
        return success

    def load_shortcuts(self) -> list[dict]:
        """加载所有快捷键组合"""
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
                success = False # 如果未找到则明确设为 False
        except sqlite3.Error as e:
            logging.error(f"删除快捷键 '{name}' 失败: {e}")
            success = False # 确保返回 False
        finally:
            self._close_connection(conn)
        return success

    def get_shortcut_by_key(self, shortcut_key: str) -> Union[dict, None]:
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