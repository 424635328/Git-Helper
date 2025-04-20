# src/gui/git_worker.py

from PyQt6.QtCore import QObject, QThread, pyqtSignal
import subprocess
import sys
import os
import io

# Make sure wrapper functions are imported or accessible.
# In this structure, GitWorker doesn't directly import wrappers,
# it receives the callable function. But it needs to know *about*
# wrapper_create_pull_request specifically to emit the signal.
# A better design might be the wrapper emitting the signal directly if it has access,
# or using a different mechanism. Let's keep it simple for now by checking the callable.

# Need to import the specific wrapper function here to check its identity
# from .git_wrappers import wrapper_create_pull_request

class GitWorker(QObject):
    """
    在单独线程中运行 Git 命令的 Worker。
    """
    finished = pyqtSignal() # Operation finished signal
    error = pyqtSignal(str) # Error message signal (per line or aggregated)
    output = pyqtSignal(str) # Standard output signal (per line or aggregated)
    command_start = pyqtSignal(str) # Command start signal

    # Add a signal specifically for opening a URL, connected by the main window
    open_url_signal = pyqtSignal(str) # This signal should be passed from MainWindow


    def __init__(self, command_list=None, cwd=None, input_data=None, task_func=None, project_root=None, open_url_signal=None, *args, **kwargs):
        super().__init__()
        self._command_list = command_list
        self._cwd = cwd # Working directory
        self._input_data = input_data # If command needs stdin input
        self._task_func = task_func # If not running command_list directly, but calling a specific function
        self._task_args = args
        self._task_kwargs = kwargs
        self._project_root = project_root # Project root passed from MainWindow

        # Store the signal instance passed from MainWindow
        if open_url_signal:
             self.open_url_signal = open_url_signal # Replace the default signal instance


    def run(self):
        """
        在线程中执行任务。
        """
        final_out = ""
        final_err = ""
        final_code = 1 # Assume failure by default

        try:
            if self._task_func:
                # Execute a specific Python function (a wrapper)
                self.command_start.emit(f"Running task: {self._task_func.__name__}")
                print(f"\n> Running task: {self._task_func.__name__}") # Console log

                # Pass project_root and the open_url_signal to the wrapper
                # Add open_url_signal to kwargs passed to task_func
                self._task_kwargs['project_root'] = self._project_root
                self._task_kwargs['open_url_signal'] = self.open_url_signal # Pass the signal

                result = self._task_func(*self._task_args, **self._task_kwargs)

                # Assuming wrapper returns (stdout, stderr, returncode)
                if isinstance(result, tuple) and len(result) == 3:
                     out, err, code = result
                     final_out = out
                     final_err = err
                     final_code = code

                     # --- Handle Specific Wrapper Outputs ---
                     # If the task was PR creation and succeeded, emit the URL
                     # Need to compare task_func identity, requires importing it here
                     from .git_wrappers import wrapper_create_pull_request # Import specific wrapper

                     if self._task_func == wrapper_create_pull_request and code == 0 and out:
                          # Assuming the URL is the primary output of the PR wrapper
                          # Emit the URL so the main window can open the browser
                          self.open_url_signal.emit(out)
                          # Also emit the output text itself
                          self.output.emit("PR URL generated:")
                          self.output.emit(out) # Emit the URL string as output

                     # General case: Emit standard output/error from wrapper result
                     else:
                          if out:
                              self.output.emit(out)
                          if err:
                              self.error.emit("--- STDERR ---\n" + err) # Indicate stderr

                else:
                    # If the wrapper function doesn't return the standard tuple
                    # Just emit whatever it returned as output
                    self.output.emit("Task returned non-standard result:")
                    self.output.emit(str(result))
                    final_out = str(result) # Capture for logging
                    final_code = 0 # Assume success if wrapper ran without exception but returned non-standard result

            elif self._command_list:
                # Execute a direct Git command using Popen for streaming output
                command_str = ' '.join(self._command_list)
                self.command_start.emit(f"Executing command: {command_str}")
                print(f"\n> 执行命令: {command_str}") # Console log

                try:
                    process = subprocess.Popen(
                        self._command_list,
                        cwd=self._cwd or self._project_root, # Use provided cwd or project root
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        stdin=subprocess.PIPE if self._input_data else None,
                        text=True,
                        encoding="utf-8",
                        bufsize=1 # Line buffering
                    )

                    # Send input data if provided
                    if self._input_data and process.stdin:
                        process.stdin.write(self._input_data)
                        process.stdin.close()

                    # Read output line by line and emit signals
                    # Using separate threads for stdout/stderr readers is safer for real-time
                    # For simplicity here, we read sequentially, might block if one stream is huge
                    # before the other finishes.
                    stdout_reader = iter(process.stdout.readline, '') if process.stdout else None
                    stderr_reader = iter(process.stderr.readline, '') if process.stderr else None

                    # Interleave reading or just read stdout then stderr
                    # Let's read stdout then stderr fully before waiting for process end
                    # Or, process output and error in separate loops or helper functions
                    # Simple approach: read stdout, then stderr
                    if stdout_reader:
                        for line in stdout_reader:
                            self.output.emit(line.strip())
                            final_out += line # Also capture for logging

                    if stderr_reader:
                         for line in stderr_reader:
                             self.error.emit(line.strip()) # Emit stderr separately
                             final_err += line # Also capture for logging

                    if process.stdout: process.stdout.close()
                    if process.stderr: process.stderr.close()


                    return_code = process.wait() # Wait for the process to finish
                    final_code = return_code

                    if return_code != 0:
                        # Command failed - error already emitted line by line
                        pass # Error message was emitted during reading


                except FileNotFoundError:
                    err_msg = "**Error**: Git command not found. Please ensure Git is installed and in your PATH."
                    self.error.emit(err_msg)
                    final_err += err_msg
                    final_code = 1 # Ensure non-zero code

                except Exception as e:
                    err_msg = f"An error occurred during command execution: {e}"
                    self.error.emit(err_msg)
                    final_err += err_msg
                    final_code = 1 # Ensure non-zero code

            else:
                err_msg = "No command or task function specified for the worker."
                self.error.emit(err_msg)
                final_err += err_msg
                final_code = 1 # Ensure non-zero code

        except Exception as e:
             # Catch exceptions during task_func call or initial setup
             err_msg = f"An unexpected error occurred in worker: {e}"
             self.error.emit(err_msg)
             final_err += err_msg
             final_code = 1 # Ensure non-zero code


        # --- Final Status Report ---
        if final_code != 0:
             self.output.emit(f"<span style='color:red; font-weight:bold;'>Operation finished with errors (code {final_code}).</span>")
             # Optional: Show a message box on critical errors
             # QMessageBox.critical(None, "Operation Failed", "See output for details.") # Cannot show message box from non-GUI thread
             # Signal to main thread to show message box instead
        else:
             self.output.emit(f"<span style='color:green;'>Operation finished successfully (code {final_code}).</span>")

        # Optional: Log final aggregated output/error to console
        # print(f"\n--- Worker Finalized (Code: {final_code}) ---")
        # if final_out: print("Final STDOUT:\n", final_out)
        # if final_err: print("Final STDERR:\n", final_err)
        # print("---------------------------------------------")

        self.finished.emit() # Signal completion