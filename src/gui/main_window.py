# src/gui/main_window.py

import sys
import os
import webbrowser
from PyQt6.QtWidgets import (
    QMainWindow, QApplication, QWidget, QVBoxLayout, QPushButton,
    QTextEdit, QLabel, QMenuBar, QMenu, QToolBar, QStatusBar, QSplitter,
    QInputDialog, QMessageBox, QLineEdit, QDialog, QDialogButtonBox
)
from PyQt6.QtCore import QThread, pyqtSignal, QTimer, Qt, QObject

# Import the worker and dialogs
from .git_worker import GitWorker
from .dialogs import CommitMessageDialog, SimpleTextInputDialog # Import dialogs

# Import all wrapper functions - Ensure all needed wrappers are in git_wrappers.py
from .git_wrappers import (
    wrapper_show_status,
    wrapper_show_log,
    wrapper_show_diff,
    wrapper_add_changes,
    wrapper_commit_changes,
    wrapper_create_switch_branch,
    wrapper_pull_changes,
    wrapper_push_branch,
    wrapper_sync_fork_sequence,
    wrapper_merge_branch,          # Import the new wrappers
    wrapper_rebase_branch,         # Import the new wrappers
    wrapper_manage_stash,          # Import the new wrappers
    wrapper_cherry_pick_commit,    # Import the new wrappers
    wrapper_manage_tags,           # Import the new wrappers
    wrapper_manage_remotes,        # Import the new wrappers
    wrapper_delete_local_branch,   # Import the new wrappers
    wrapper_delete_remote_branch,  # Import the new wrappers
    wrapper_create_pull_request,   # Import the new wrappers (ensure definition is in git_wrappers.py)
    wrapper_clean_commits,         # Import the new wrappers (ensure definition is in git_wrappers.py)
)


# Import config manager
from src.config_manager import config, load_config, extract_repo_name_from_upstream_url

class MainWindow(QMainWindow):
    # Define a signal for opening a URL, emitted from the worker or a specific handler
    open_url_signal = pyqtSignal(str)

    def __init__(self, project_root, parent=None):
        super().__init__(parent)
        self.project_root = project_root # Store the project root

        self.setWindowTitle("Git Helper GUI")
        self.setGeometry(100, 100, 800, 600)

        # --- Central Widget and Layout ---
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)

        # Output Text Area
        self.output_text = QTextEdit()
        self.output_text.setReadOnly(True)
        self.output_text.append("Git Helper GUI Started.")
        main_layout.addWidget(self.output_text)

        # Status Bar
        self.statusBar = QStatusBar()
        self.setStatusBar(self.statusBar)
        self.statusBar.showMessage("Ready")

        # --- Menu Bar ---
        self._create_menu_bar()

        # --- Worker Thread ---
        self.worker_thread = QThread()
        self.git_worker = None # Will hold the current worker instance

        # --- Connect Signals ---
        # Connect the signal from MainWindow to the slot in MainWindow
        # This signal will be emitted by the worker but handled in the main thread
        self.open_url_signal.connect(self._open_browser)

        # --- Initial Config/Setup ---
        self.show_config_info()

    def _create_menu_bar(self):
        """Creates the application's menu bar."""
        menu_bar = self.menuBar()

        # File Menu
        file_menu = menu_bar.addMenu("&File")
        exit_action = file_menu.addAction("E&xit")
        exit_action.triggered.connect(self.close)

        # Basic Operations Menu (1-5)
        basic_menu = menu_bar.addMenu("&Basic Operations")
        basic_menu.addAction("View &Status").triggered.connect(self.handle_status_action)
        basic_menu.addAction("View &Log...").triggered.connect(self.handle_log_action)
        basic_menu.addAction("View &Diff...").triggered.connect(self.handle_diff_action)
        basic_menu.addAction("&Add Changes...").triggered.connect(self.handle_add_action)
        basic_menu.addAction("&Commit Changes...").triggered.connect(self.handle_commit_action)

        # Branch & Sync Menu (6-9)
        branch_menu = menu_bar.addMenu("&Branch & Sync")
        branch_menu.addAction("Create/Switch Branch...").triggered.connect(self.handle_create_switch_branch_action)
        branch_menu.addAction("Pull Changes...").triggered.connect(self.handle_pull_action)
        branch_menu.addAction("Push Branch...").triggered.connect(self.handle_push_action)
        branch_menu.addAction("Sync Fork (Upstream)").triggered.connect(self.handle_sync_fork_action)

        # Advanced Operations Menu (10-19)
        advanced_menu = menu_bar.addMenu("&Advanced Operations")
        advanced_menu.addAction("Merge Branch...").triggered.connect(self.handle_merge_action)
        advanced_menu.addAction("Rebase Branch... (Dangerous!)").triggered.connect(self.handle_rebase_action)
        advanced_menu.addAction("Manage Stash...").triggered.connect(self.handle_stash_action)
        advanced_menu.addAction("Cherry-Pick Commit...").triggered.connect(self.handle_cherry_pick_action)
        advanced_menu.addAction("Manage Tags...").triggered.connect(self.handle_manage_tags_action)
        advanced_menu.addAction("Manage Remotes...").triggered.connect(self.handle_manage_remotes_action)
        advanced_menu.addAction("Delete Local Branch...").triggered.connect(self.handle_delete_local_branch_action)
        advanced_menu.addAction("Delete Remote Branch...").triggered.connect(self.handle_delete_remote_branch_action)
        advanced_menu.addAction("Create Pull Request...").triggered.connect(self.handle_create_pull_request_action)
        advanced_menu.addAction("Clean Commits... (Extremely Dangerous!)").triggered.connect(self.handle_clean_commits_action)

        # Settings Menu (Optional)
        settings_menu = menu_bar.addMenu("&Settings")
        settings_menu.addAction("Show Current Config").triggered.connect(self.show_config_info)

    def _start_git_worker(self, task_callable=None, command_list=None, input_data=None, **kwargs):
        """Helper to create and start a GitWorker."""
        if self.git_worker and self.worker_thread.isRunning():
             QMessageBox.warning(self, "Operation in Progress", "Another Git operation is currently running. Please wait for it to finish.")
             return

        self.output_text.append(f"\n--- Starting Git Operation ---")
        self.statusBar.showMessage("Running Git operation...")
        self.output_text.verticalScrollBar().setValue(self.output_text.verticalScrollBar().maximum()) # Scroll to bottom

        # Create the worker instance
        self.git_worker = GitWorker(
            command_list=command_list,
            input_data=input_data,
            task_func=task_callable,
            project_root=self.project_root,
            open_url_signal=self.open_url_signal # Pass the signal instance
            # Pass other signals if wrappers need to report granular progress/status
        )

        # Move worker to the thread
        self.git_worker.moveToThread(self.worker_thread)

        # Connect signals from worker to slots in MainWindow
        self.git_worker.finished.connect(self._git_operation_finished)
        self.git_worker.error.connect(self._display_error)
        self.git_worker.output.connect(self._append_output)
        self.git_worker.command_start.connect(self._append_output)

        # Connect the thread's started signal to the worker's run slot
        self.worker_thread.started.connect(self.git_worker.run)

        # Clean up worker and thread when finished
        self.git_worker.finished.connect(self.git_worker.deleteLater)
        self.worker_thread.finished.connect(self.worker_thread.deleteLater)

        # Start the thread
        self.worker_thread.start()

        # Optional: Disable UI elements
        # self.menuBar().setEnabled(False)

    def _append_output(self, text):
        """Appends text to the output area (thread-safe via signal)."""
        self.output_text.append(text)
        self.output_text.verticalScrollBar().setValue(self.output_text.verticalScrollBar().maximum()) # Auto-scroll

    def _display_error(self, text):
        """Appends error text to the output area and updates status bar."""
        self.output_text.append(f"<span style='color:red; font-weight:bold;'>{text}</span>") # Make errors red
        self.statusBar.showMessage("Error during operation.", 5000) # Show for 5 seconds
        self.output_text.verticalScrollBar().setValue(self.output_text.verticalScrollBar().maximum()) # Auto-scroll
        print(f"GUI Error: {text}") # Also print to console for debugging

    def _git_operation_finished(self):
        """Handles cleanup and UI update after a Git operation finishes."""
        # Disconnect signals to avoid potential issues
        try:
            self.git_worker.finished.disconnect(self._git_operation_finished)
            self.git_worker.error.disconnect(self._display_error)
            self.git_worker.output.disconnect(self._append_output)
            self.git_worker.command_start.disconnect(self._append_output)
            # If the PR signal was connected directly to the worker, disconnect it too
            # self.git_worker.open_url_signal.disconnect(self._open_browser) # If it was connected here
        except (TypeError, RuntimeError): # Handle cases where signals might be None or already disconnected
             pass


        self.worker_thread.quit()
        self.worker_thread.wait(5000)
        if self.worker_thread.isRunning():
             self.worker_thread.terminate()
             self.worker_thread.wait()

        self.output_text.append("--- Git Operation Finished ---")
        self.statusBar.showMessage("Ready")
        self.output_text.verticalScrollBar().setValue(self.output_text.verticalScrollBar().maximum()) # Auto-scroll

        # Optional: Re-enable UI elements
        # self.menuBar().setEnabled(True)

    # --- Slots for Menu Actions ---

    # Basic Operations (Existing)
    def handle_status_action(self):
        self._start_git_worker(task_callable=wrapper_show_status)

    def handle_log_action(self):
         log_formats = ["Simple (oneline)", "Graphical"]
         log_format_choice, ok = QInputDialog.getItem(self, "Select Log Format", "Choose log format:", log_formats, 0, False)
         if ok and log_format_choice:
             format_map = {"Simple (oneline)": "oneline", "Graphical": "graph"}
             self._start_git_worker(task_callable=wrapper_show_log, log_format=format_map[log_format_choice])

    def handle_diff_action(self):
         diff_types = ["Working Tree vs Staged", "Staged vs HEAD", "Working Tree vs HEAD", "Between two commits/branches..."]
         diff_type_choice, ok = QInputDialog.getItem(self, "Select Diff Type", "Choose diff type:", diff_types, 0, False)
         if ok and diff_type_choice:
             task_callable = None
             kwargs = {}
             if diff_type_choice == "Working Tree vs Staged":
                  task_callable = wrapper_show_diff
                  kwargs['diff_type'] = "unstaged"
             elif diff_type_choice == "Staged vs HEAD":
                  task_callable = wrapper_show_diff
                  kwargs['diff_type'] = "staged"
             elif diff_type_choice == "Working Tree vs HEAD":
                  task_callable = wrapper_show_diff
                  kwargs['diff_type'] = "working_tree_vs_head"
             elif diff_type_choice == "Between two commits/branches...":
                  commit1, ok1 = QInputDialog.getText(self, "Diff Commits", "Enter first commit/branch:")
                  if not ok1 or not commit1: return
                  commit2, ok2 = QInputDialog.getText(self, "Diff Commits", "Enter second commit/branch (Leave empty for HEAD):")
                  if not ok2: return
                  task_callable = wrapper_show_diff
                  kwargs['diff_type'] = "commits"
                  kwargs['commit1'] = commit1
                  kwargs['commit2'] = commit2 if commit2 else "HEAD"

             if task_callable:
                  self._start_git_worker(task_callable=task_callable, **kwargs)

    def handle_add_action(self):
        add_target, ok = QInputDialog.getText(self, "Add Changes", "Enter file path to add (or '.' for all):", text=".")
        if ok and add_target:
             self._start_git_worker(task_callable=wrapper_add_changes, add_target=add_target)
        elif ok and not add_target:
             QMessageBox.warning(self, "Input Required", "Add target cannot be empty.")

    def handle_commit_action(self):
        dialog = CommitMessageDialog(self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            commit_message = dialog.get_message()
            if commit_message:
                self._start_git_worker(task_callable=wrapper_commit_changes, message=commit_message)
            else:
                QMessageBox.warning(self, "Input Required", "Commit message cannot be empty.")

    # Branch & Sync Operations (Existing)
    def handle_create_switch_branch_action(self):
        branch_action_types = ["Create and Switch", "Switch to Existing"]
        action_choice, ok = QInputDialog.getItem(self, "Branch Operation", "Select action:", branch_action_types, 0, False)

        if ok and action_choice:
             branch_name, ok_name = QInputDialog.getText(self, action_choice, "Enter branch name:")
             if ok_name and branch_name:
                 action_map = {"Create and Switch": "create_and_switch", "Switch to Existing": "switch"}
                 self._start_git_worker(task_callable=wrapper_create_switch_branch, action_type=action_map[action_choice], branch_name=branch_name)
             elif ok_name and not branch_name:
                  QMessageBox.warning(self, "Input Required", "Branch name cannot be empty.")

    def handle_pull_action(self):
         remote_name, ok_remote = QInputDialog.getText(self, "Pull Changes", "Enter remote name (e.g., origin):", text="origin")
         if not ok_remote or not remote_name: return

         branch_name, ok_branch = QInputDialog.getText(self, "Pull Changes", "Enter branch name (e.g., main):", text=config.get("default_branch_name", "main"))
         if not ok_branch or not branch_name: return

         self._start_git_worker(task_callable=wrapper_pull_changes, remote_name=remote_name, branch_name=branch_name)

    def handle_push_action(self):
         remote_name, ok_remote = QInputDialog.getText(self, "Push Branch", "Enter remote name (e.g., origin):", text="origin")
         if not ok_remote or not remote_name: return

         branch_name, ok_branch = QInputDialog.getText(self, "Push Branch", "Enter branch name (e.g., main):")
         if not ok_branch or not branch_name: return

         self._start_git_worker(task_callable=wrapper_push_branch, remote_name=remote_name, branch_name=branch_name)

    def handle_sync_fork_action(self):
         default_branch = config.get("default_branch_name", "main")
         confirm = QMessageBox.question(self, "Confirm Sync Fork",
                                        f"This will sync your local '{default_branch}' branch with upstream and push to origin.\n"
                                        f"Steps:\n"
                                        f"1. Checkout '{default_branch}'\n"
                                        f"2. Pull from upstream '{default_branch}'\n"
                                        f"3. Push to origin '{default_branch}'\n\nProceed?",
                                        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
         if confirm == QMessageBox.StandardButton.Yes:
             self._start_git_worker(task_callable=wrapper_sync_fork_sequence, default_branch=default_branch)

    # --- Advanced Operations Slots (Added empty definitions) ---

    # [10] Merge Branch
    def handle_merge_action(self):
        branch_to_merge, ok = QInputDialog.getText(self, "Merge Branch", "Enter the branch to merge into the current branch:")
        if ok and branch_to_merge:
            self._start_git_worker(task_callable=wrapper_merge_branch, branch_to_merge=branch_to_merge)
        elif ok and not branch_to_merge:
            QMessageBox.warning(self, "Input Required", "Branch name to merge cannot be empty.")

    # [11] Rebase Branch (Dangerous!)
    def handle_rebase_action(self):
        QMessageBox.warning(self, "DANGER!",
                            "Rebasing rewrites commit history! Do NOT rebase branches that have been pushed to a public repository.\n"
                            "Use with extreme caution.",
                            QMessageBox.StandardButton.Ok)

        onto_branch, ok = QInputDialog.getText(self, "Rebase Branch", "Enter the branch to rebase onto (e.g., main):")
        if ok and onto_branch:
            confirm = QMessageBox.question(self, "FINAL WARNING!",
                                           f"Are you ABSOLUTELY SURE you want to rebase the current branch onto '{onto_branch}'?\n"
                                           "This will rewrite history!",
                                           QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                           QMessageBox.StandardButton.No)
            if confirm == QMessageBox.StandardButton.Yes:
                 self._start_git_worker(task_callable=wrapper_rebase_branch, onto_branch=onto_branch)
        elif ok and not onto_branch:
             QMessageBox.warning(self, "Input Required", "Base branch name cannot be empty.")

    # [12] Manage Stash
    def handle_stash_action(self):
        stash_actions = ["List", "Push", "Apply", "Pop", "Drop"]
        stash_action_choice, ok = QInputDialog.getItem(self, "Manage Stash", "Select stash operation:", stash_actions, 0, False)

        if ok and stash_action_choice:
            action_map = {
                "List": "list", "Push": "push", "Apply": "apply", "Pop": "pop", "Drop": "drop"
            }
            selected_action = action_map.get(stash_action_choice)
            kwargs = {"stash_action": selected_action}

            if selected_action in ["apply", "pop", "drop"]:
                stash_ref, ok_ref = QInputDialog.getText(self, f"{stash_action_choice} Stash", f"Enter stash reference (e.g., stash@{{0}}). Leave empty for latest (apply/pop):")
                if not ok_ref: return
                if selected_action == "drop" and not stash_ref:
                     QMessageBox.warning(self, "Input Required", "Stash reference is required for 'Drop'.")
                     return
                kwargs['stash_ref'] = stash_ref

                if selected_action == "drop":
                     confirm_drop = QMessageBox.question(self, "Confirm Drop Stash",
                                                         f"Are you sure you want to permanently drop stash '{stash_ref or 'latest'}'?",
                                                         QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
                     if confirm_drop != QMessageBox.StandardButton.Yes: return

            elif selected_action == "push":
                 message, ok_msg = QInputDialog.getText(self, "Stash Message", "Enter message for stash (Optional):")
                 if not ok_msg: return
                 kwargs['message'] = message

            if selected_action:
                 self._start_git_worker(task_callable=wrapper_manage_stash, **kwargs)

    # [13] Cherry-Pick Commit
    def handle_cherry_pick_action(self):
        commit_hash, ok = QInputDialog.getText(self, "Cherry-Pick Commit", "Enter the commit hash to cherry-pick:")
        if ok and commit_hash:
            self._start_git_worker(task_callable=wrapper_cherry_pick_commit, commit_hash=commit_hash)
        elif ok and not commit_hash:
            QMessageBox.warning(self, "Input Required", "Commit hash cannot be empty.")

    # [14] Manage Tags
    def handle_manage_tags_action(self):
        tag_actions = ["List", "Create", "Delete Local", "Push All", "Delete Remote"]
        tag_action_choice, ok = QInputDialog.getItem(self, "Manage Tags", "Select tag operation:", tag_actions, 0, False)

        if ok and tag_action_choice:
            action_map = {
                "List": "list", "Create": "create", "Delete Local": "delete_local",
                "Push All": "push_all", "Delete Remote": "delete_remote"
            }
            selected_action = action_map.get(tag_action_choice)
            kwargs = {"tag_action": selected_action}

            if selected_action == "create":
                tag_name, ok_name = QInputDialog.getText(self, "Create Tag", "Enter tag name (e.g., v1.0):")
                if not ok_name or not tag_name: return
                kwargs['tag_name'] = tag_name

                tag_type, ok_type = QInputDialog.getItem(self, "Create Tag", "Select tag type:", ["Annotated", "Lightweight"], 0, False)
                if not ok_type: return
                kwargs['tag_type'] = tag_type.lower()

                if kwargs['tag_type'] == "annotated":
                    tag_message, ok_msg = QInputDialog.getText(self, "Create Tag", "Enter tag message (Optional):")
                    if not ok_msg: return
                    kwargs['tag_message'] = tag_message

            elif selected_action in ["delete_local", "delete_remote"]:
                tag_name, ok_name = QInputDialog.getText(self, f"{tag_action_choice} Tag", "Enter tag name:")
                if not ok_name or not tag_name: return
                kwargs['tag_name'] = tag_name

                if selected_action == "delete_remote":
                    remote_name, ok_remote = QInputDialog.getText(self, "Delete Remote Tag", "Enter remote name (e.g., origin):", text="origin")
                    if not ok_remote or not remote_name: return
                    kwargs['remote_name'] = remote_name

                confirm_delete = QMessageBox.question(self, "Confirm Delete Tag",
                                                      f"Are you sure you want to delete {tag_action_choice.lower()} tag '{tag_name}'?",
                                                      QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
                if confirm_delete != QMessageBox.StandardButton.Yes: return

            elif selected_action == "push_all":
                 remote_name, ok_remote = QInputDialog.getText(self, "Push All Tags", "Enter remote name (e.g., origin):", text="origin")
                 if not ok_remote or not remote_name: return
                 kwargs['remote_name'] = remote_name
                 confirm_push = QMessageBox.question(self, "Confirm Push All Tags",
                                                     f"Are you sure you want to push ALL local tags to '{remote_name}'?",
                                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
                 if confirm_push != QMessageBox.StandardButton.Yes: return

            if selected_action:
                 self._start_git_worker(task_callable=wrapper_manage_tags, **kwargs)


    # [15] Manage Remotes
    def handle_manage_remotes_action(self):
        remote_actions = ["List", "Add", "Remove", "Rename", "Set Upstream"]
        remote_action_choice, ok = QInputDialog.getItem(self, "Manage Remotes", "Select remote operation:", remote_actions, 0, False)

        if ok and remote_action_choice:
            action_map = {
                "List": "list", "Add": "add", "Remove": "remove", "Rename": "rename", "Set Upstream": "setup_upstream"
            }
            selected_action = action_map.get(remote_action_choice)
            kwargs = {"remote_action": selected_action}

            if selected_action == "add":
                name, ok_name = QInputDialog.getText(self, "Add Remote", "Enter remote name:")
                if not ok_name or not name: return
                url, ok_url = QInputDialog.getText(self, "Add Remote", "Enter remote URL:")
                if not ok_url or not url: return
                kwargs['name'] = name
                kwargs['url'] = url

            elif selected_action == "remove":
                name, ok_name = QInputDialog.getText(self, "Remove Remote", "Enter remote name to remove:")
                if not ok_name or not name: return
                kwargs['name'] = name
                confirm_remove = QMessageBox.question(self, "Confirm Remove Remote",
                                                     f"Are you sure you want to remove remote '{name}'?",
                                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
                if confirm_remove != QMessageBox.StandardButton.Yes: return

            elif selected_action == "rename":
                old_name, ok_old = QInputDialog.getText(self, "Rename Remote", "Enter current remote name:")
                if not ok_old or not old_name: return
                new_name, ok_new = QInputDialog.getText(self, "Rename Remote", "Enter new remote name:")
                if not ok_new or not new_name: return
                kwargs['old_name'] = old_name
                kwargs['new_name'] = new_name

            elif selected_action == "setup_upstream":
                 default_upstream = config.get("default_upstream_url", "git@github.com:upstream_owner/upstream_repo.git")
                 url, ok_url = QInputDialog.getText(self, "Set Upstream", f"Enter upstream URL (e.g., {default_upstream}):", text=default_upstream)
                 if not ok_url or not url: return
                 kwargs['url'] = url

            if selected_action:
                 self._start_git_worker(task_callable=wrapper_manage_remotes, **kwargs)


    # [16] Delete Local Branch
    def handle_delete_local_branch_action(self):
        branch_name, ok = QInputDialog.getText(self, "Delete Local Branch", "Enter local branch name to delete:")
        if ok and branch_name:
             force_delete = QMessageBox.question(self, "Delete Local Branch",
                                                 f"Delete local branch '{branch_name}'.\n"
                                                 "Delete even if not fully merged (-D)?",
                                                 QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No | QMessageBox.StandardButton.Cancel,
                                                 QMessageBox.StandardButton.No)

             if force_delete == QMessageBox.StandardButton.Cancel: return
             is_force = (force_delete == QMessageBox.StandardButton.Yes)

             confirm = QMessageBox.question(self, "Confirm Delete Local Branch",
                                            f"Are you sure you want to {'FORCE delete' if is_force else 'delete'} local branch '{branch_name}'?",
                                            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
             if confirm == QMessageBox.StandardButton.Yes:
                  self._start_git_worker(task_callable=wrapper_delete_local_branch, branch_name=branch_name, force=is_force)
        elif ok and not branch_name:
             QMessageBox.warning(self, "Input Required", "Branch name cannot be empty.")

    # [17] Delete Remote Branch
    def handle_delete_remote_branch_action(self):
        branch_name, ok = QInputDialog.getText(self, "Delete Remote Branch", "Enter remote branch name to delete:")
        if not ok or not branch_name: return

        remote_name, ok_remote = QInputDialog.getText(self, "Delete Remote Branch", "Enter remote name (e.g., origin):", text="origin")
        if not ok_remote or not remote_name: return

        confirm = QMessageBox.question(self, "Confirm Delete Remote Branch",
                                       f"Are you sure you want to delete remote branch '{branch_name}' from '{remote_name}'?\n"
                                       "This action is PERMANENT!",
                                       QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if confirm == QMessageBox.StandardButton.Yes:
            self._start_git_worker(task_callable=wrapper_delete_remote_branch, branch_name=branch_name, remote_name=remote_name)
        elif ok and not branch_name:
             QMessageBox.warning(self, "Input Required", "Branch name cannot be empty.")

    # [18] Create Pull Request
    def handle_create_pull_request_action(self):
         fork_username = config.get("fork_username", config.get("default_fork_username", "your_github_username"))
         base_repo = config.get("base_repo", config.get("default_base_repo", "upstream_owner/upstream_repo"))
         default_branch = config.get("default_branch_name", "main")

         source_branch, ok_source = QInputDialog.getText(self, "Create Pull Request", "Enter source branch (your branch):")
         if not ok_source or not source_branch: return

         target_branch, ok_target = QInputDialog.getText(self, "Create Pull Request", "Enter target branch (upstream branch):", text=default_branch)
         if not ok_target or not target_branch: return

         confirm = QMessageBox.question(self, "Confirm Create PR",
                                        f"Create PR from '{fork_username}:{source_branch}' to '{base_repo}:{target_branch}'?\n"
                                        f"This will generate a URL and attempt to open your browser.",
                                        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)

         if confirm == QMessageBox.StandardButton.Yes:
             # Call the wrapper. The wrapper generates the URL and emits the signal.
             self._start_git_worker(task_callable=wrapper_create_pull_request,
                                    fork_username=fork_username,
                                    base_repo=base_repo,
                                    source_branch=source_branch,
                                    target_branch=target_branch,
                                    # open_url_signal is passed to worker, worker passes to wrapper
                                    )

    # Slot to open browser - connected via signal
    def _open_browser(self, url):
         """Slot to open a URL in the default browser."""
         try:
             webbrowser.open(url)
             self.output_text.append(f"Attempted to open URL in browser: <a href='{url}'>{url}</a>")
         except Exception as e:
             self.output_text.append(f"Failed to open browser for URL: {url}\nError: {e}")
             self._display_error("Failed to open browser automatically.")

    # [19] Clean Commits (Extremely Dangerous!)
    def handle_clean_commits_action(self):
        QMessageBox.warning(self, "DANGER!",
                            "This operation (git reset --hard) will permanently discard commits and local changes!\n"
                            "Please ensure you have backed up your work.",
                            QMessageBox.StandardButton.Ok)

        num_commits_input, ok = QInputDialog.getText(self, "Clean Commits (DANGEROUS)", "Enter number of recent commits to discard:", text="1")
        if ok:
            try:
                num_commits = int(num_commits_input)
                if num_commits < 0:
                    QMessageBox.critical(self, "Invalid Input", "Number of commits must be non-negative.")
                    return

                confirm = QMessageBox.question(self, "FINAL WARNING!",
                                               f"Are you ABSOLUTELY SURE you want to permanently discard the last {num_commits} commits and all local changes?\n"
                                               "THIS CANNOT BE UNDONE!",
                                               QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                               QMessageBox.StandardButton.No)
                if confirm == QMessageBox.StandardButton.Yes:
                    self._start_git_worker(task_callable=wrapper_clean_commits, num_commits_to_discard=num_commits)

            except ValueError:
                QMessageBox.critical(self, "Invalid Input", "Please enter a valid number.")

    # Placeholder for showing config info in output
    def show_config_info(self):
        self.output_text.append("\n--- Current Configuration ---")
        if config:
            for key, value in config.items():
                 self.output_text.append(f"- <b>{key}:</b> {value}</b>")
        else:
            self.output_text.append("Config is empty or not loaded.")
        self.output_text.append("-----------------------------")


    def closeEvent(self, event):
        """Handle application exit, ensure worker is stopped."""
        if self.git_worker and self.worker_thread.isRunning():
            reply = QMessageBox.question(self, 'Quit',
                                         "A Git operation is in progress. Are you sure you want to quit?",
                                         QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                         QMessageBox.StandardButton.No)
            if reply == QMessageBox.StandardButton.Yes:
                self.worker_thread.quit()
                if not self.worker_thread.wait(2000):
                    self.worker_thread.terminate()
                    self.worker_thread.wait()
                event.accept()
            else:
                event.ignore()
        else:
            event.accept()