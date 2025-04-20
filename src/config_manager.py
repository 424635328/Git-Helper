# src/config_manager.py
import yaml
import re
import os # Added for file path check

# 定义一个全局变量来存储配置
config = {}

def extract_repo_name_from_upstream_url(upstream_url):
    """
    从 Upstream 仓库地址中提取原始仓库的名称。

    Args:
      upstream_url: Upstream 仓库的 URL (例如: "https://github.com/owner/repo.git" 或者 "git@github.com:owner/repo.git")

    Returns:
      如果提取成功, 返回原始仓库的名称 (例如: "owner/repo")。
      如果提取失败, 返回 None。
    """
    if not upstream_url:
        return None

    # 修改正则表达式来同时匹配 https 和 git+ssh 协议
    # 注意：这个正则表达式只适用于 GitHub URL
    match = re.search(r"github\.com[:/]([^/]+)/([^.]+)", upstream_url)

    if match:
        owner = match.group(1)
        repo_name = match.group(2)
        return f"{owner}/{repo_name}"
    else:
        return None

def load_config(config_file="config.yaml"):
    """加载配置文件"""
    global config
    print(f"正在加载配置文件: {config_file}")
    config_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), config_file) # 确保从项目根目录加载 config.yaml
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            loaded_config = yaml.safe_load(f)
            if loaded_config:
                config.update(loaded_config) # 使用 update 合并字典
                print("配置文件加载成功。")
            else:
                 print(
                    "警告：配置文件为空或无法加载有效内容。将使用默认设置，某些功能可能无法正常工作。"
                )

    except FileNotFoundError:
        print(
            f"警告：{config_file} 文件未找到于 {config_path}。将使用默认设置，某些功能可能无法正常工作。"
        )
        # config 保持 {} 或已有的默认值
    except yaml.YAMLError as e:
        print(f"警告：加载 {config_file} 文件时发生错误：{e}。将使用默认设置。")
        # config 保持 {} 或已有的默认值
    except Exception as e:
         print(f"警告：加载配置文件时发生未知错误：{e}。")


    # 确保关键配置项存在，如果不存在，设置默认值
    if "default_fork_username" not in config:
        config["default_fork_username"] = "your_github_username"  # 你的 GitHub 用户名
        print("警告：'default_fork_username' 未在 config.yaml 中找到，使用默认值。请编辑 config.yaml。")
    if "default_upstream_url" not in config:
        config["default_upstream_url"] = "git@github.com:upstream_owner/upstream_repo.git" # 上游仓库地址
        print("警告：'default_upstream_url' 未在 config.yaml 中找到，使用默认值。请编辑 config.yaml。")
    if "default_base_repo" not in config:
         # 尝试从Upstream URL中提取，如果失败，就使用一个提示性的默认值
        extracted_base = extract_repo_name_from_upstream_url(config.get("default_upstream_url"))
        config["default_base_repo"] = extracted_base if extracted_base else "upstream_owner/upstream_repo"
        print("警告：'default_base_repo' 未在 config.yaml 中找到，尝试从 'default_upstream_url' 中提取或使用默认值。请编辑 config.yaml。")
    if "default_branch_name" not in config:
        config["default_branch_name"] = "main"  # 默认分支名称
        print("警告: 'default_branch_name' 未在 config.yaml 中找到，使用默认值 'main'.")

    # 初始化运行时可能需要的配置项
    if "fork_username" not in config:
        config["fork_username"] = config["default_fork_username"]
    if "base_repo" not in config:
        config["base_repo"] = config["default_base_repo"]

    # print("当前配置:", config) # 调试用