# src/git_utils.py
import subprocess
import sys
import os # Added for cwd default? No, cwd is passed explicitly. # 为 cwd 的默认值添加？不，cwd 是显式传递的。

def run_git_command(command_list, cwd=None):
    """
    运行 Git 命令并返回状态码、stdout 和 stderr。
    参数:
        command_list: 包含命令及其参数的列表。
        cwd: 可选，指定运行命令的工作目录。
    """
    process = None  # 初始化 process 变量
    try:
        print(f"\n> 执行命令: {' '.join(command_list)}") # 打印实际执行的命令
        process = subprocess.run(
            command_list,
            capture_output=True,
            text=True,
            check=True, # 如果命令返回非零状态码则抛出 CalledProcessError
            encoding="utf-8",
            cwd=cwd # 指定工作目录
        )
        # 对于成功执行的命令，返回状态码0，stdout，stderr
        return process.returncode, process.stdout, process.stderr
    except FileNotFoundError:
        print("\n **错误**: 未找到 git 命令。请确保 Git 已安装并配置到系统的 PATH 中。")
        # 使用 sys.exit 退出程序，因为没有 git 就无法继续
        sys.exit(1)
    except subprocess.CalledProcessError as e:
        # 当 check=True 时，非零状态码会触发此异常
        print(f"\n **错误**: 命令 '{' '.join(command_list)}' 执行失败，错误代码: {e.returncode}")
        # 打印 stdout 和 stderr
        if e.stdout:
            print("\n--- stdout ---")
            print(e.stdout)
        if e.stderr:
            print("\n--- stderr ---")
            print(e.stderr)

        # 返回异常的状态码和输出
        return e.returncode, e.stdout, e.stderr
    except Exception as e:
        # 捕获其他可能的异常
        print(f"\n **错误**: 执行命令时发生未知错误: {e}")
        return 1, "", str(e) # 返回一个非零状态码表示失败