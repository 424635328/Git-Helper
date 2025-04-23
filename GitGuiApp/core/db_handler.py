# core/db_handler.py
# -*- coding: utf-8 -*-
import sqlite3
import os
import logging
import sys # 导入 sys 模块
from typing import Union # 导入 Union

# 如果主应用程序未配置日志，则配置日志
# logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# 定义数据库文件所在的目录名和文件名
DB_DIR_NAME = "database"
DB_FILENAME = "shortcuts.db"

class DatabaseHandler:
    """处理快捷键组合的数据库操作"""

    def __init__(self): # 移除 db_path 参数，因为我们会在内部计算路径
        """
        初始化数据库处理器，确定数据库文件的实际路径。
        在 PyInstaller --onefile 模式下，路径会在临时目录中。
        """
        # 确定应用程序的根目录
        # getattr(sys, 'frozen', False) 检查是否运行在 PyInstaller/cx_Freeze 等冻结环境中
        # hasattr(sys, '_MEIPASS') 检查是否是 PyInstaller 的 --onefile 模式
        if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
            # 运行在 PyInstaller --onefile 模式下
            # 数据文件被提取到 sys._MEIPASS
            # --add-data "database:." 意味着 'database' 目录在 _MEIPASS 的根目录下
            base_path = sys._MEIPASS
            logging.info(f"Running in PyInstaller bundle. Base path: {base_path}")
        else:
            # 作为标准 Python 脚本运行
            # 数据库目录相对于脚本文件本身
            # os.path.dirname(__file__) 获取当前脚本的目录
            # os.path.abspath() 确保获取绝对路径，避免相对路径问题
            base_path = os.path.dirname(os.path.abspath(__file__))
            # 如果脚本位于某个子目录 (e.g., core/), 需要找到项目的根目录
            # 这里的假设是 database 目录和 core/ 目录在同一个父目录
            # 实际应用中，你可能需要根据你的项目结构调整 base_path 的确定方式
            # 例如，向上查找一个特定的标记文件 (.git, requirements.txt 等)
            # 对于大多数情况，假设 database 目录在与主脚本 (main.py) 同一层级是合理的，
            # 但如果 db_handler.py 在 core/ 目录下，而 database 在项目根目录，
            # 那么 base_path 可能需要调整。
            # 假设你的项目结构是这样的：
            # YourApp/
            # ├── main.py
            # ├── core/
            # │   └── db_handler.py
            # ├── database/
            # │   └── shortcuts.db
            # 那么当运行 db_handler.py 时，__file__ 是 YourApp/core/db_handler.py
            # os.path.dirname(__file__) 是 YourApp/core/
            # os.path.dirname(os.path.dirname(__file__)) 才是 YourApp/
            # 我们需要 YourApp/ 作为 base_path
            try:
                # 尝试获取项目根目录 (向上两级，如果 db_handler 在 core/ 目录下)
                # 这是基于你的 GitHub 路径 E:/GitHub/Git-Helper/GitGuiApp/main.py 和 core/db_handler.py 的推测
                # 如果你的结构不同，请调整这里
                 project_root = os.path.dirname(os.path.dirname(base_path))
                 # 检查项目根目录下是否有 database 目录作为 sanity check (可选)
                 potential_db_dir = os.path.join(project_root, DB_DIR_NAME)
                 if os.path.exists(potential_db_dir) or not os.path.exists(os.path.join(base_path, DB_DIR_NAME)):
                     base_path = project_root
                     logging.info(f"Adjusted base path to project root: {base_path}")
                 else:
                      # 如果 core/db_handler.py 运行，且 database 在 core/ 同一级，base_path 需要是 core/ 的父级
                      # 但如果 database 目录本身就在 core/ 旁边，那么从 core/ 向上两级是对的。
                      # 这个逻辑有点脆弱，依赖于特定的目录结构。
                      # 最安全的方式是让外部（如 main.py）在初始化 DatabaseHandler 时提供一个 base_path，
                      # 或者在 DatabaseHandler 内部通过更可靠的方式确定项目根目录。
                      # 鉴于你的 PyInstaller command 指向 E:/GitHub/Git-Helper/GitGuiApp/main.py
                      # 并且 --add-data "database:." 意味着 database 应该在 main.py 同一级
                      # 那么当运行脚本时，我们期望 database 也在 main.py 同一级。
                      # __file__ 在 db_handler.py 里是 .../GitGuiApp/core/db_handler.py
                      # dirname(__file__) 是 .../GitGuiApp/core/
                      # dirname(dirname(__file__)) 是 .../GitGuiApp/
                      # 所以 base_path 应该是 dirname(dirname(os.path.abspath(__file__)))
                       base_path = os.path.dirname(os.path.dirname(base_path))
                       logging.info(f"Calculated base path based on core/ subdir: {base_path}")

            except Exception as e:
                 logging.warning(f"Could not reliably determine project root, using script dir as base: {base_path}. Error: {e}")
                 # Fallback to script directory if project root determination fails
                 pass # Keep base_path as os.path.dirname(os.path.abspath(__file__)) if adjustment fails

            logging.info(f"Running as script. Base path: {base_path}")


        # 构建完整的数据库目录和文件路径
        self.db_dir = os.path.join(base_path, DB_DIR_NAME)
        self.db_path = os.path.join(self.db_dir, DB_FILENAME)

        logging.info(f"Final determined database path: {self.db_path}")

        try:
            # 确保数据库文件所在的目录存在。
            # 这对于 PyInstaller --onefile 也很重要，特别是如果数据库文件
            # 在第一次运行时才创建，或者数据目录本身是通过 --add-data 复制进去的。
            os.makedirs(self.db_dir, exist_ok=True)
            logging.info(f"数据库目录 '{self.db_dir}' 检查/创建 成功.")
            self._create_table() # 使用确定的 self.db_path 进行表创建
        except OSError as e:
            logging.error(f"创建数据库目录失败 '{self.db_dir}': {e}")
            # 设置 db_path 为 None 以指示连接将失败
            self.db_path = None


    def _get_connection(self):
        """获取数据库连接"""
        if not self.db_path:
            logging.error("数据库路径未设置或无效，无法获取连接。")
            return None
        try:
            # 考虑添加连接超时
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
        conn = self._get_connection()
        if not conn: return False
        success = False
        try:
            with conn:
                # 检查名称或快捷键是否已被 *其他* 条目使用
                # 注意：这个检查在并发写入时可能有竞态条件，但在单用户桌面应用中通常不是问题。
                cursor_check = conn.execute(
                    "SELECT id FROM shortcuts WHERE (name = ? OR shortcut_key = ?) AND NOT (name = ? AND shortcut_key = ?)",
                    (name, shortcut_key, name, shortcut_key)
                )
                existing = cursor_check.fetchone()
                if existing:
                     # 如果存在冲突，检查是名称冲突还是快捷键冲突
                     name_conflict_check = conn.execute("SELECT id FROM shortcuts WHERE name = ?", (name,)).fetchone()
                     key_conflict_check = conn.execute("SELECT id FROM shortcuts WHERE shortcut_key = ?", (shortcut_key,)).fetchone()

                     if name_conflict_check and key_conflict_check and name_conflict_check['id'] == key_conflict_check['id']:
                         # 名称和快捷键都存在，并且是同一个条目，这应该由 ON CONFLICT 处理 (更新)
                         pass # 继续执行 INSERT OR REPLACE

                     elif name_conflict_check and key_conflict_check and name_conflict_check['id'] != key_conflict_check['id']:
                          # 名称和快捷键存在，但属于不同的条目
                          logging.warning(f"保存快捷键失败：名称 '{name}' 被条目 ID {name_conflict_check['id']} 使用，快捷键 '{shortcut_key}' 被条目 ID {key_conflict_check['id']} 使用。")
                          return False # 同时冲突，且是不同条目

                     elif name_conflict_check:
                         # 名称冲突，但快捷键不冲突（或快捷键是新的）
                          # 这种情况 ON CONFLICT (name) DO UPDATE 会处理
                         pass # 继续执行 INSERT OR REPLACE

                     elif key_conflict_check:
                          # 快捷键冲突，但名称不冲突
                          # 这个应该直接返回 False，因为 shortcut_key 有 UNIQUE 约束，INSERT OR REPLACE 依赖 name
                          logging.warning(f"保存快捷键失败：快捷键 '{shortcut_key}' 已被条目 ID {key_conflict_check['id']} 使用。")
                          return False # 快捷键冲突

                # 插入或替换：如果名称已存在，则更新该条目；如果名称不存在，则插入新条目。
                # 注意：如果 shortcut_key 已经存在于另一个名称下，这里的 ON CONFLICT(name) 不会阻止 Unique 约束错误，
                # 所以上面的预检查是必要的。
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
            # 捕获 Unique 约束错误，这可能是 shortcut_key 冲突导致的，即使上面做了预检查
            # 例如，预检查通过了，但在执行 INSERT 之前，另一个进程插入了相同的 shortcut_key
            logging.warning(f"保存快捷键 '{name}' ({shortcut_key}) 时发生完整性错误（可能是快捷键冲突或并发问题）: {e}")
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
            # SELECT 通常不需要 'with conn'，但使用它也无妨
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