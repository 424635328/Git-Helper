# src/basic_operations.py
from src.utils import clear_screen
from src.git_utils import run_git_command
from src.config_manager import config # 导入配置
import os # 用于文件路径处理

def show_status():
    """显示仓库状态"""
    clear_screen()
    print("=====================================================")
    print(" [1] 查看仓库状态")
    print("=====================================================")
    print("\n")

    print(" 正在获取仓库状态...")
    return_code, stdout, stderr = run_git_command(["git", "status"])

    # run_git_command 已经处理了错误打印，这里只在成功时打印 stdout
    if return_code == 0:
        print(stdout)

    input("\n按任意键继续...")

def show_log():
    """显示提交历史"""
    clear_screen()
    print("=====================================================")
    print(" [2] 查看提交历史")
    print("=====================================================")
    print("\n")
    print("请选择日志格式：")
    print(" [1]  简洁日志 (一行一条)")
    print(" [2]  图形化日志 (显示分支合并图)")
    print("\n")

    log_choice = input(" 请选择 (1 或 2): ")
    command = ["git", "log"]

    if log_choice == "1":
        command.extend(["--pretty=oneline", "--abbrev-commit"]) # abbrev-commit 缩短 hash
    elif log_choice == "2":
        command.extend(["--graph", "--pretty=format:%C(auto)%h%d %s %C(dim)%an%C(reset)", "--all"]) # 美化图形日志，显示所有分支
    else:
        print("\n **错误**: 无效的选择，将使用默认日志格式。")
        input("按任意键继续...")
        return # 无效选择，直接返回

    print("\n 正在获取提交历史...")
    # 使用 Popen 运行命令，并直接将输出流式打印到控制台，以便处理长日志
    import subprocess # 需要导入 subprocess 用于 Popen
    try:
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8")
        while True:
            output = process.stdout.readline()
            if output == '' and process.poll() is not None:
                break
            if output:
                print(output.strip()) # 打印日志行

        # 检查是否有错误输出
        stderr = process.stderr.read()
        if stderr:
             print("\n--- 错误输出 ---")
             print(stderr.strip())

        return_code = process.wait() # 等待进程结束并获取返回码

        if return_code != 0:
             print(f"\n **错误**: 查看日志失败，错误代码: {return_code}")

    except FileNotFoundError:
         print("\n **错误**: 未找到 git 命令。请确保 Git 已安装并配置到系统的 PATH 中。")
    except Exception as e:
         print(f"\n **错误**: 执行命令时发生未知错误: {e}")

    input("\n按任意键继续...")


def show_diff():
    """显示文件差异"""
    clear_screen()
    print("=====================================================")
    print(" [3] 查看文件差异")
    print("=====================================================")
    print("\n")
    print("请选择要查看的差异：")
    print(" [1]  工作目录 vs 暂存区 (已修改但未 add 的文件)")
    print(" [2]  暂存区 vs 最新提交 (git add . 后准备 commit 的修改)")
    print(" [3]  工作目录 vs 最新提交 (所有未 commit 的修改)")
    print(" [4]  两个提交/分支 之间的差异 (例如: main...feature)")
    print("\n")

    diff_choice = input(" 请选择 (1-4): ")
    command = ["git", "diff"]

    if diff_choice == "1":
        # git diff (工作区 vs 暂存区) - 这是默认行为，不需要额外参数
        pass
    elif diff_choice == "2":
        command.append("--staged") # 或者 --cached (暂存区 vs HEAD)
    elif diff_choice == "3":
         command.append("HEAD") # 工作区 vs HEAD
    elif diff_choice == "4":
        commit1 = input(" 请输入第一个提交哈希或分支名: ")
        if not commit1:
            print("\n **错误**: 必须输入第一个提交/分支名称！ 操作已取消。")
            input("\n按任意键继续...")
            return
        commit2 = input(" 请输入第二个提交哈希或分支名 (默认为当前 HEAD): ")
        if not commit2:
            command.extend([commit1, "HEAD"])
        else:
            command.extend([commit1, commit2])
    else:
        print("\n **错误**: 无效的选择！ 操作已取消。")
        input("\n按任意键继续...")
        return

    print("\n 正在获取文件差异...")
    # Diff 输出也可能很长，使用 Popen
    import subprocess # 需要导入 subprocess 用于 Popen
    try:
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8")
        while True:
            output = process.stdout.readline()
            if output == '' and process.poll() is not None:
                break
            if output:
                # git diff 输出中可能包含颜色控制符
                print(output.rstrip()) # rstrip() 移除行尾的换行符，Popen 的 readline 保留了换行符

        stderr = process.stderr.read()
        if stderr:
             print("\n--- 错误输出 ---")
             print(stderr.strip())

        return_code = process.wait()

        if return_code != 0:
             print(f"\n **错误**: 查看差异失败，错误代码: {return_code}")

    except FileNotFoundError:
         print("\n **错误**: 未找到 git 命令。请确保 Git 已安装并配置到系统的 PATH 中。")
    except Exception as e:
         print(f"\n **错误**: 执行命令时发生未知错误: {e}")


    input("\n按任意键继续...")


def add_changes():
    """添加修改
    命令: git add .  (添加所有文件)
         git add <file_name> (添加指定文件)
    """
    clear_screen()
    print("=====================================================")
    print(" [4] 添加修改到暂存区")
    print("=====================================================")
    print("\n")
    print(" 已修改的文件 (使用 git status 查看)")
    print("\n [a]  添加所有已修改或新增的文件")
    print(" [文件名] 添加指定的单个文件 (例如： README.md)")
    print("\n")

    add_target = input(" 请输入选项 (a(所有文件) 或 文件名): ")
    command = ["git", "add"]

    if add_target.lower() == "a":
        command.append(".")
        print("\n 正在添加所有文件到暂存区...")
    elif add_target:
        command.append(add_target)
        print(f"\n 正在添加文件 '{add_target}' 到暂存区...")
    else:
        print("\n **错误**: 输入为空，操作已取消。")
        input("按任意键继续...")
        return

    return_code, stdout, stderr = run_git_command(command)

    # run_git_command 已经处理了错误打印
    if return_code == 0:
         print("\n 文件已成功添加到暂存区。")
    # else: 错误信息已在 run_git_command 中打印

    input("按任意键继续...")


def commit_changes():
    """提交修改
    命令: git commit --file temp_commit_message.txt
    """
    clear_screen()
    print("=====================================================")
    print(" [5] 提交暂存区的修改")
    print("=====================================================")
    print("\n")

    commit_message = input(" 请输入提交信息: ")
    if not commit_message:
        print("\n **错误**: 提交信息不能为空！ 操作已取消。")
        input("按任意键继续...")
        return

    # 写入临时文件，并确保文件编码是 UTF-8
    temp_file_name = "temp_git_commit_message.txt"
    # Get the directory of the current script file (__file__)
    # Then go up one level to the src directory, then up another level to the project root
    # This ensures the temp file is created in the project root
    temp_file_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), temp_file_name)
    try:
        with open(temp_file_path, "w", encoding="utf-8") as f:
            f.write(commit_message)
    except Exception as e:
        print(f"\n**错误**: 创建临时提交信息文件失败: {e}")
        input("按任意键继续...")
        return

    print("\n 正在提交修改...")
    # Use temp_file_name directly as git command expects path relative to cwd
    return_code, stdout, stderr = run_git_command(
        ["git", "commit", "--file", temp_file_name],
        cwd=os.path.dirname(os.path.dirname(__file__)) # Set CWD to project root
    )

    # 提交完成后删除临时文件
    if os.path.exists(temp_file_path):
        os.remove(temp_file_path)

    # run_git_command 已经处理了错误打印
    if return_code == 0:
        print(f"\n 提交成功，提交信息: '{commit_message}'")
    # else: 错误信息已在 run_git_command 中打印

    input("按任意键继续...")