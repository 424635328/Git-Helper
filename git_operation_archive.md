# 📚 Git 操作档案 - git-helper

欢迎来到 git-helper 的 Git 操作档案！本文件详细解释了 git-helper 菜单中各项操作背后对应的 Git 命令、其用途、潜在风险以及一些使用建议。

通过了解这些底层命令，您可以更深入地理解 git-helper 的工作原理，并在需要时直接使用 Git 命令进行更灵活的操作。

**请注意：** 本文档是对 git-helper 功能所执行的 Git 命令的解释，并不是完整的 Git 命令参考手册。完整的 Git 文档请查阅 [Git 官方文档](https://git-scm.com/doc) 或使用 `git help <command>`。

## 📖 目录

- [基础操作](#基础操作)
  - [[1] 查看仓库状态 (git status)](#1-查看仓库状态-git-status)
  - [[2] 查看提交历史 (git log)](#2-查看提交历史-git-log)
  - [[3] 查看文件差异 (git diff)](#3-查看文件差异-git-diff)
  - [[4] 添加修改 (git add)](#4-添加修改-git-add)
  - [[5] 提交修改 (git commit)](#5-提交修改-git-commit)
- [分支与同步](#分支与同步)
  - [[6] 创建/切换分支 (git checkout / git switch)](#6-创建切换分支-git-checkout--git-switch)
  - [[7] 拉取远程更改 (git pull)](#7-拉取远程更改-git-pull)
  - [[8] 推送本地分支 (git push)](#8-推送本地分支-git-push)
  - [[9] 同步 Fork (Upstream)](#9-同步-fork-upstream)
- [高级操作与管理](#高级操作与管理)
  - [[10] 合并分支 (git merge)](#10-合并分支-git-merge)
  - [[11] 变基分支 (git rebase)](#11-变基分支-git-rebase)
  - [[12] 储藏/暂存修改 (git stash)](#12-储藏暂存修改-git-stash)
  - [[13] 拣选/摘取提交 (git cherry-pick)](#13-拣选摘取提交-git-cherry-pick)
  - [[14] 管理标签 (git tag)](#14-管理标签-git-tag)
  - [[15] 管理远程仓库 (git remote)](#15-管理远程仓库-git-remote)
  - [[16] 删除本地分支 (git branch -d/-D)](#16-删除本地分支-git-branch--d--d)
  - [[17] 删除远程分支 (git push --delete)](#17-删除远程分支-git-push---delete)
  - [[18] 创建 Pull Request](#18-创建-pull-request)
  - [[19] 清理 Commits (git reset --hard)](#19-清理-commits-git-reset---hard)

---

## 基础操作

### [1] 查看仓库状态 (git status)

- **用途:** 显示工作目录和暂存区的状态。它会告诉你哪些文件被修改了但还没有暂存，哪些文件已经被暂存但还没有提交，以及哪些是未被 Git 跟踪的新文件。
- **核心命令:**
  ```bash
  git status
  ```
- **可能的输出:**
  - Changes not staged for commit (已修改但未暂存)
  - Changes to be committed (已暂存)
  - Untracked files (未跟踪文件)
  - 当前所在的分支信息
- **建议:** 这是一个非常常用的命令，在进行任何修改和提交操作之前，先查看状态是个好习惯。

### [2] 查看提交历史 (git log)

- **用途:** 显示项目的提交历史记录。可以查看每个提交的作者、日期、提交信息和哈希值。
- **核心命令 (git-helper 中的选项):**
  - 简洁日志 (`--pretty=oneline --abbrev-commit`):
    ```bash
    git log --pretty=oneline --abbrev-commit
    ```
    每条提交一行，只显示简短哈希和提交信息。
  - 图形化日志 (`--graph --pretty=format:... --all`):
    ```bash
    git log --graph --pretty=format:%C(auto)%h%d %s %C(dim)%an%C(reset) --all
    ```
    以图形方式显示分支和合并历史，并美化输出。`--all` 显示所有分支和标签的历史。
- **建议:** 图形化日志对于理解复杂的分支合并非常有帮助。

### [3] 查看文件差异 (git diff)

- **用途:** 显示两个不同状态之间的文件内容差异。
- **核心命令 (git-helper 中的选项):**
  - 工作目录 vs 暂存区 (`git diff`):
    ```bash
    git diff
    ```
    显示工作目录中已修改但未 `git add` 到暂存区的文件差异。
  - 暂存区 vs 最新提交 (`git diff --staged`):
    ```bash
    git diff --staged
    # 或 git diff --cached
    ```
    显示已 `git add` 到暂存区，但尚未提交的更改与最新提交 (HEAD) 之间的差异。
  - 工作目录 vs 最新提交 (`git diff HEAD`):
    ```bash
    git diff HEAD
    ```
    显示工作目录中所有未提交的更改（包括已暂存和未暂存）与最新提交 (HEAD) 之间的差异。
  - 两个提交/分支之间的差异 (`git diff <commit1> <commit2>`):
    ```bash
    git diff <commit1> <commit2>
    # 例如: git diff main feature-branch
    # 或者 git diff HEAD~1 HEAD # 查看倒数第一个和倒数第二个提交的差异
    ```
    显示指定两个提交、分支或标签之间的差异。
- **建议:** `git diff` 是理解你的改动是否按预期暂存和提交的重要工具。

### [4] 添加修改 (git add)

- **用途:** 将工作目录中的修改或新文件添加到暂存区 (Staging Area)，以便进行下一次提交。
- **核心命令 (git-helper 中的选项):**
  - 添加所有修改或新增的文件 (`git add .`):
    ```bash
    git add .
    ```
    将当前目录及其所有子目录中所有已修改和未跟踪的文件添加到暂存区。
  - 添加指定文件 (`git add <file_name>`):
    ```bash
    git add path/to/your/file.txt
    ```
    将指定的单个文件添加到暂存区。
- **建议:** 在 `git add .` 之前，最好先用 `git status` 查看哪些文件将被添加，或者用 `git diff` 检查未暂存的修改是否符合预期。

### [5] 提交修改 (git commit)

- **用途:** 将暂存区中的所有修改保存为一个新的提交 (Commit)，记录项目的当前状态。
- **核心命令 (git-helper 使用文件方式):**
  ```bash
  git commit --file temp_commit_message.txt
  ```
  git-helper 会将你输入的提交信息写入一个临时文件，然后使用 `--file` 参数来读取提交信息。这有助于处理包含特殊字符或多行内容的提交信息。
- **建议:**
  - 编写清晰、简洁的提交信息是良好的版本控制实践。通常第一行是简短的主题（不超过 50 字符），后面可以空一行，然后是更详细的正文。
  - 确保在提交之前，所有你想包含的修改都已经通过 `git add` 添加到暂存区。

---

## 分支与同步

### [6] 创建/切换分支 (git checkout / git switch)

- **用途:** 用于切换到不同的分支或提交，以及创建新的分支。`git switch` 是一个更现代、更专注于分支切换的命令，推荐使用。git-helper 内部可能使用了 `checkout` 或 `switch`。
- **核心命令 (git-helper 中的选项):**
  - 创建并切换到新分支 (`git checkout -b <branch_name>` 或 `git switch -c <branch_name>`):
    ```bash
    git checkout -b new-feature-branch
    # 或者更推荐的：
    # git switch -c new-feature-branch
    ```
    基于当前分支创建一个新分支，并立即切换到该分支。
  - 切换到已有本地分支 (`git checkout <branch_name>` 或 `git switch <branch_name>`):
    ```bash
    git checkout existing-branch
    # 或者更推荐的：
    # git switch existing-branch
    ```
    切换到已存在的本地分支。如果工作目录或暂存区有未提交的修改，可能会阻止切换，除非这些修改不会与目标分支上的文件冲突（Git 会尝试帮你保留修改）。
- **建议:**
  - 在开始新功能开发或 bug 修复时，总是从一个干净的主分支（如 `main` 或 `master`）创建一个新的特性分支。
  - 切换分支前，最好先提交或储藏 (`git stash`) 当前的修改，以避免潜在的问题。

### [7] 拉取远程更改 (git pull)

- **用途:** 从指定的远程仓库和分支拉取最新代码，并将其合并到当前本地分支。
- **核心命令:**
  ```bash
  git pull <remote_name> <branch_name>
  # 例如: git pull origin main
  ```
  这个命令实际上是两个命令的组合：`git fetch <remote_name> <branch_name>` (下载远程分支的新提交) 和 `git merge <remote_name>/<branch_name>` (将下载的提交合并到当前本地分支)。
  有时，Git 会配置为使用 `rebase` 而不是 `merge` 来集成拉取的更改 (`git pull --rebase`)。
- **可能的输出/问题:**
  - Fast-forward (快进合并): 远程分支领先于本地分支，直接移动本地分支指针。
  - Merge commit (合并提交): 远程和本地分支都有新的提交，创建一个新的合并提交。
  - **Conflict (冲突):** 如果远程和本地分支修改了同一文件的同一部分，会发生合并冲突，需要手动解决。
- **建议:**
  - 经常拉取远程更改，保持本地分支与远程同步，减少冲突。
  - 如果发生冲突，请参考 [合并分支](#10-合并分支-git-merge) 部分的冲突解决指南。
  - 了解你的仓库是否配置为 `merge` 或 `rebase` (`git config pull.rebase`)。

### [8] 推送本地分支 (git push)

- **用途:** 将本地分支的提交上传到指定的远程仓库。
- **核心命令:**
  ```bash
  git push <remote_name> <branch_name>
  # 例如: git push origin feature-branch
  ```
  如果这是你第一次推送这个本地分支，并且希望它跟踪远程同名分支，你可能需要使用 `-u` 参数：
  ```bash
  git push -u <remote_name> <branch_name>
  # 例如: git push -u origin new-feature
  ```
  `-u` (或 `--set-upstream`) 会设置本地分支跟踪远程分支，这样下次可以直接使用 `git pull` 或 `git push` 而无需指定远程仓库和分支名。
- **可能的输出/问题:**
  - 推送成功。
  - Rejected (拒绝): 通常是由于远程分支有你本地没有的提交（即远程分支领先于你），需要先 `git pull` 合并或变基远程更改。
  - 权限问题。
- **建议:**
  - 在推送之前，最好先拉取一次远程更改，确保你的本地分支是基于最新的远程状态。
  - 如果你在非自己的 Fork 仓库上直接推送（例如推送到原始仓库），请确保你有相应的权限。

### [9] 同步 Fork (Upstream)

- **用途:** 这是一个专门针对 Fork 工作流设计的便捷操作。它帮助你从原始仓库（通常配置为 `upstream` 远程仓库）的主分支拉取最新更改，然后将这些更改应用到你的本地主分支，并推送到你自己的 Fork 仓库（通常配置为 `origin` 远程仓库）。这使得你的 Fork 仓库保持与原始仓库同步。
- **git-helper 执行的命令序列:**
  1.  切换到默认主分支 (如 `main`):
      ```bash
      git checkout main
      # 或 git switch main
      ```
  2.  从 `upstream` 远程仓库拉取主分支的最新更改到当前本地分支:
      ```bash
      git pull upstream main
      ```
      这会将 `upstream/main` 的更改合并到你的本地 `main` 分支。
  3.  将更新后的本地主分支推送到 `origin` 远程仓库:
      ```bash
      git push origin main
      ```
- **前提条件:**
  - 你已经 Fork 了原始仓库。
  - 你的 Fork 仓库已经被克隆到本地。
  - 你已经在本地仓库中添加并配置了一个名为 `upstream` 的远程仓库，指向原始仓库的地址。如果没有配置，可以使用 git-helper 的 [管理远程仓库](#15-管理远程仓库-git-remote) 功能中的选项 5 (设置 upstream)。
- **建议:** 定期执行此操作，保持你的 Fork 仓库同步，方便后续基于最新代码创建特性分支和 Pull Request。

---

## 高级操作与管理

_(通过主菜单选项 10 进入)_

### [10] 合并分支 (git merge)

- **用途:** 将一个分支的独立开发历史合并到当前分支。
- **核心命令:**
  ```bash
  git merge <branch_to_merge>
  # 例如: git merge feature-branch
  ```
- **合并类型:**
  - **Fast-forward (快进):** 如果当前分支没有新的提交，而要合并的分支领先于当前分支，Git 会直接将当前分支的指针向前移动到要合并分支的最新提交。不会产生新的合并提交。
  - **Three-way merge (三方合并):** 如果当前分支和要合并的分支都有各自新的提交，Git 会找到它们的共同祖先，然后结合两个分支的修改来创建一个新的合并提交。
- **可能的输出/问题:**
  - 合并成功 (Fast-forward 或创建新的合并提交)。
  - **Conflict (冲突):** 如果两个分支修改了同一文件的同一部分，或者一个分支删除了另一个分支修改的文件，会发生冲突。Git 会在冲突文件中用特殊标记 (`<<<<<<<`, `=======`, `>>>>>>>`) 指出冲突部分，并停止合并过程。
- **冲突解决步骤 (当发生冲突时):**
  1.  使用 `git status` 查看哪些文件发生了冲突。
  2.  手动编辑冲突文件，移除冲突标记，并保留你最终想要的代码。
  3.  使用 `git add <resolved_file>` 将解决冲突后的文件标记为已解决。
  4.  重复步骤 2 和 3，直到所有冲突文件都已解决并添加到暂存区。
  5.  使用 `git commit` 完成合并（Git 会自动生成一个默认的合并提交信息）。
  - **放弃合并:** 如果你想取消当前的合并操作，回到合并之前的状态，可以使用：
    ```bash
    git merge --abort
    ```
- **建议:** 合并是集成代码的标准方式，但在共享分支上变基后进行合并可能会导致问题。了解你的团队通常使用合并还是变基来集成代码。

### [11] 变基分支 (git rebase)

- **用途:** 将一个分支上的提交“移动”或“复制”到另一个分支的顶部，使得提交历史看起来是线性的。这会重写提交历史！
- **核心命令:**
  ```bash
  git rebase <base_branch>
  # 例如: git rebase main
  ```
  这会找到当前分支和 `<base_branch>` 的共同祖先，然后将当前分支上在共同祖先之后的所有提交逐个应用到 `<base_branch>` 的最新提交之上。
- **<span style="color:red; font-weight:bold;">⚠ 极其危险的命令!</span>**
  - **重写历史:** 变基会为当前分支上的每个提交创建一个新的提交，这些新提交的哈希值会不同。原始提交将被丢弃。
  - **切勿对已推送到公共（多人协作）仓库的分支使用:** 如果你变基了一个其他协作者正在基于其工作的分支，他们的历史将与你的不一致，导致他们的后续拉取和推送出现问题。
- **冲突解决步骤 (变基过程中发生冲突):**
  变基过程中也可能发生冲突，解决方式与合并冲突类似，但使用的命令不同：
  1.  Git 会在冲突文件中用标记指出冲突，并暂停变基过程。
  2.  使用 `git status` 查看冲突文件和变基进度。
  3.  手动编辑冲突文件，解决冲突。
  4.  使用 `git add <resolved_file>` 将解决冲突后的文件标记为已解决。
  5.  使用 `git rebase --continue` 继续变基过程。
  - **跳过冲突的提交:** 如果你想完全丢弃当前导致冲突的那个提交，可以使用：
    ```bash
    git rebase --skip
    ```
  - **放弃变基:** 如果你想取消当前的变基操作，回到变基之前的状态，可以使用：
    ```bash
    git rebase --abort
    ```
- **建议:** 变基通常用于清理你自己的本地特性分支，使其基于最新的主分支，然后再合并到主分支（或创建 PR）。在执行变基前，务必了解其原理和风险，并确认你正在操作的是一个私有（未分享给他人）的分支。

### [12] 储藏/暂存修改 (git stash)

- **用途:** 临时保存工作目录和暂存区的修改，以便在不提交的情况下切换到其他任务。这对于需要临时中断当前工作去处理紧急 bug 或切换分支非常有用。
- **核心命令 (git-helper 中的操作):**
  - 储藏当前修改 (`git stash push`):
    ```bash
    git stash push -m "Optional message describing the stash"
    # 或简单的 git stash (效果类似 git stash push)
    ```
    将当前未提交（包括已暂存和未暂存）的修改保存到一个堆栈中，并恢复工作目录到 HEAD 提交的状态。
  - 查看储藏列表 (`git stash list`):
    ```bash
    git stash list
    ```
    列出所有已保存的储藏，格式通常是 `stash@{n}: On branch: ... message`。`stash@{0}` 是最新的。
  - 应用最近的储藏 (`git stash apply`):
    ```bash
    git stash apply
    # 或 git stash apply stash@{n} # 应用指定的储藏
    ```
    将指定的储藏（默认是最新储藏 `stash@{0}`）的应用到当前分支的工作目录。应用后，储藏仍然保留在列表中。
  - 应用并移除最近的储藏 (`git stash pop`):
    ```bash
    git stash pop
    # 或 git stash pop stash@{n} # 应用指定的储藏并尝试移除
    ```
    将指定的储藏（默认是最新储藏 `stash@{0}`）应用到当前分支，并如果应用成功且没有冲突，则从列表中移除该储藏。
  - 删除指定的储藏 (`git stash drop`):
    ```bash
    git stash drop stash@{n}
    # 例如: git stash drop stash@{1} # 删除列表中的第二个储藏
    ```
    从储藏列表中永久删除指定的储藏。
- **可能的输出/问题:**
  - 应用或 pop 储藏时可能发生冲突，需要手动解决。解决冲突后，对于 `pop` 操作，如果冲突发生，储藏不会被自动删除。
- **建议:** `git stash` 是一个方便的工具，但不要把它当作长期存储修改的地方。在你准备好继续之前，尽快将储藏的修改应用并提交。

### [13] 拣选/摘取提交 (git cherry-pick)

- **用途:** 将某个分支上的一个或多个现有提交的应用到当前分支。这会创建新的提交，但内容与原始提交相同。
- **核心命令:**
  ```bash
  git cherry-pick <commit-hash>
  # 例如: git cherry-pick a1b2c3d
  ```
- **使用场景:**
  - 将一个 bug 修复从一个分支应用到多个其他分支（例如，从特性分支拣选到主分支和发布分支）。
  - 从一个废弃的分支中挑选几个有用的提交。
- **可能的输出/问题:**
  - 拣选成功，创建一个新的提交。
  - **Conflict (冲突):** 如果被拣选的提交与当前分支有冲突，需要手动解决。解决冲突后，使用 `git add <resolved_file>` 和 `git cherry-pick --continue` 继续。
  - 如果想放弃当前的拣选操作，使用 `git cherry-pick --abort`。
- **建议:** 拣选会创建新的提交，可能会导致不同分支上有内容相同但哈希不同的提交。谨慎使用，尤其是在可以采用合并或变基的情况下。

### [14] 管理标签 (git tag)

- **用途:** 在提交历史上标记某个重要的点，通常用于发布版本（例如 v1.0, v2.0-beta）。标签是不可移动的引用。
- **核心命令 (git-helper 中的操作):**
  - 列出所有标签 (`git tag`):
    ```bash
    git tag
    # 或 git tag -l "v*" # 列出匹配模式的标签
    ```
  - 创建新标签:
    - 轻量标签 (Lightweight Tag - 只是一个指向特定提交的指针，不包含额外信息):
      ```bash
      git tag <tagname>
      # 默认标记当前 HEAD
      # 例如: git tag v1.0-lw
      # 也可以标记之前的提交: git tag v1.0-beta a1b2c3d
      ```
    - 附注标签 (Annotated Tag - 存储在 Git 数据库中，包含打标签者的名字、email、日期和标签信息，推荐用于发布):
      ```bash
      git tag -a <tagname> -m "Tag Message"
      # 默认标记当前 HEAD
      # 例如: git tag -a v1.0 -m "Version 1.0 release"
      # 也可以标记之前的提交: git tag -a v1.0-rc1 a1b2c3d -m "Release Candidate 1"
      ```
  - 删除本地标签 (`git tag -d`):
    ```bash
    git tag -d <tagname>
    # 例如: git tag -d v1.0-lw
    ```
  - 推送所有本地标签到远程 (`git push --tags`):
    ```bash
    git push <remote_name> --tags
    # 例如: git push origin --tags
    ```
    默认情况下 `git push` 不会推送标签，需要 `--tags` 选项。
  - 删除远程标签 (`git push --delete tag`):
    ```bash
    git push <remote_name> --delete tag <tagname>
    # 例如: git push origin --delete tag v1.0-beta
    ```
- **建议:** 附注标签包含更多信息，更适合用于标记重要的发布版本。标签默认只在本地，记得推送 `--tags` 到远程仓库。

### [15] 管理远程仓库 (git remote)

- **用途:** 管理你的本地仓库与远程仓库之间的连接配置。常见的远程仓库有 `origin` (你的 Fork 仓库) 和 `upstream` (原始仓库)。
- **核心命令 (git-helper 中的操作):**
  - 列出所有远程仓库 (`git remote -v`):
    ```bash
    git remote -v
    ```
    显示已配置的远程仓库名称及其对应的 URL (fetch 和 push 地址)。
  - 添加新的远程仓库 (`git remote add`):
    ```bash
    git remote add <name> <url>
    # 例如: git remote add upstream https://github.com/upstream_owner/upstream_repo.git
    ```
    添加一个名为 `<name>` 的远程仓库，并关联到 `<url>`。
  - 删除指定的远程仓库 (`git remote remove`):
    ```bash
    git remote remove <name>
    # 例如: git remote remove old-remote
    ```
    从配置中移除指定的远程仓库连接。
  - 重命名指定的远程仓库 (`git remote rename`):
    ```bash
    git remote rename <old_name> <new_name>
    # 例如: git remote rename origin my-fork
    ```
    重命名一个已有的远程仓库连接。
  - 设置 `upstream` 仓库: 这是 git-helper 提供的一个子功能，实际上调用了 `git remote add upstream <url>`，方便你快速添加指向原始仓库的 `upstream` 远程。
- **建议:** 保持远程仓库配置清晰，特别是 `origin` 和 `upstream`，这对于 Fork 工作流至关重要。

### [16] 删除本地分支 (git branch -d/-D)

- **用途:** 删除本地仓库中不再需要的分支。
- **核心命令 (git-helper 中的操作):**
  - 安全删除 (`git branch -d`):
    ```bash
    git branch -d <local_branch_name>
    # 例如: git branch -d old-feature
    ```
    只能删除已经完全合并到当前 HEAD 或其上游分支的分支。这是一个安全选项，防止意外丢失未合并的工作。
  - 强制删除 (`git branch -D`):
    ```bash
    git branch -D <local_branch_name>
    # 例如: git branch -D experimental-branch
    ```
    强制删除分支，无论它是否已合并。这可能会导致未合并的提交丢失！
- **可能的错误:**
  - 你不能删除当前所在的分支。
  - 使用 `-d` 删除未合并的分支会失败并提示。
- **建议:** 在删除分支前，确保你不再需要它，或者它的所有重要更改都已经合并或备份到其他地方。优先使用 `-d` 进行安全删除。

### [17] 删除远程分支 (git push --delete)

- **用途:** 删除远程仓库上的指定分支。
- **核心命令:**
  ```bash
  git push <remote_name> --delete <remote_branch_name>
  # 例如: git push origin --delete old-feature
  ```
- **危险性:** 这个操作会永久删除远程仓库上的分支，影响所有协作者。
- **建议:** 在删除远程分支前，务必确认其他协作者不再需要它，并确保你拥有在远程仓库删除分支的权限。

### [18] 创建 Pull Request

- **用途:** 在 GitHub (或其他托管平台) 上发起一个 Pull Request，请求将你的 Fork 仓库中的某个分支的更改合并到原始仓库的某个分支。
- **git-helper 执行的操作:** 这个功能**不会**直接通过 Git 命令创建 PR，而是通过在终端打印或尝试在浏览器中打开一个预填充了相关信息的 URL，引导用户到 GitHub 网站上手动完成 PR 的创建。
- **生成的 URL 格式 (GitHub 示例):**
  ```
  https://github.com/<base_repo>/compare?base=<target_branch>&head=<fork_username>:<source_branch>&title=<pr_title>&body=<pr_body>
  ```
  - `<base_repo>`: 原始仓库名称 (例如 `upstream_owner/upstream_repo`)。
  - `<target_branch>`: 原始仓库中接收更改的目标分支 (例如 `main`)。
  - `<fork_username>`: 你的 GitHub 用户名。
  - `<source_branch>`: 你的 Fork 仓库中包含更改的分支。
  - `<pr_title>`: PR 标题 (会进行 URL 编码)。
  - `<pr_body>`: PR 正文 (会进行 URL 编码)。
- **前提条件:**
  - 你已经 Fork 了原始仓库。
  - 你已经将包含你要贡献的更改的分支推送到你的 Fork 仓库 (`origin`)。
  - `config.yaml` 或程序启动时正确配置了 `fork_username` (你的 GitHub 用户名) 和 `base_repo` (原始仓库名称 `owner/repo`)。
- **建议:** 生成 URL 后，在浏览器中打开它，仔细填写 PR 的详细描述、关联相关的 Issue，并确保符合项目的贡献指南后再提交。

### [19] 清理 Commits (git reset --hard)

- **用途:** 将当前分支的 HEAD 指针移动到指定的提交，并**强制**将暂存区和工作目录的状态重置到该提交。这会丢弃当前 HEAD 之后的所有提交以及工作目录和暂存区中所有未提交的修改。
- **核心命令 (git-helper 中的选项):**

  ```bash
  git reset --hard HEAD~<number_of_commits>
  # 例如: git reset --hard HEAD~2 # 丢弃最近的 2 个提交
  # git reset --hard HEAD~0 # 回到最初状态 (如果仓库只有一个初始提交)
  ```

  `HEAD~<number_of_commits>` 表示当前 HEAD 提交向后数 `<number_of_commits>` 个提交。
- **💥 极其危险的命令!**
  - **永久数据丢失:** `git reset --hard` 会**永久丢弃**所有未推送的、位于目标提交之后的新提交以及本地工作目录和暂存区的修改。这些修改通常无法轻易恢复！
  - **重写历史:** 这也会重写分支历史。
- **使用场景 (非常有限，且需要谨慎):**
  - 撤销最近的几个本地提交，完全放弃这些修改。
  - 清除一个“脏”的工作目录，回到某个干净的提交状态。
- **建议:**
  - **执行此操作前，请务必备份你的代码！** 可以通过复制项目目录或创建一个临时分支来备份 (`git branch backup-before-reset`)。
  - **切勿对已推送到公共（多人协作）仓库的分支使用 `git reset --hard` 后再强制推送 (`git push --force`)!** 这会严重破坏其他协作者的工作流程。只在你自己完全掌握且确定不会影响他人的私有分支上使用。
  - 如果只是想撤销暂存区的修改，使用 `git reset HEAD <file>...`。如果只是想撤销工作目录的修改，使用 `git checkout -- <file>...` 或 `git restore <file>...`。这些是更安全的选择。

---

希望这份档案能帮助你更好地理解 git-helper 各项操作背后的 Git 原理！

[返回 README 主页](README.md)
