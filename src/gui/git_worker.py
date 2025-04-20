# src/gui/git_worker.py

from PyQt6.QtCore import QObject, QThread, pyqtSignal, QByteArray, QProcess
import subprocess
import sys
import os
import io
import traceback # Import traceback for detailed error logging

# Import specific wrapper function if needed for special handling (like PR)
# from .git_wrappers import wrapper_create_pull_request

class GitWorker(QObject):
    """
    在单独线程中运行 Git 命令的 Worker。
    """
    finished = pyqtSignal()
    error = pyqtSignal(str)
    output = pyqtSignal(str)
    command_start = pyqtSignal(str)

    _open_url_signal_instance = None # Class attribute to hold the signal instance? No, instance attribute is better.

    def __init__(self, command_list=None, cwd=None, input_data=None, task_func=None, project_root=None, open_url_signal=None, *args, **kwargs):
        super().__init__()
        self._command_list = command_list
        self._cwd = cwd # Working directory for subprocess
        self._input_data = input_data # If command needs stdin input
        self._task_func = task_func # Callable wrapper function
        self._task_args = args # Positional args for task_func
        self._task_kwargs = kwargs # Keyword args for task_func
        self._project_root = project_root # Project root passed from MainWindow

        # Store the actual signal instance passed from MainWindow
        self._open_url_signal_instance = open_url_signal


    def run(self):
        """
        在线程中执行任务。
        Ensures finished signal is always emitted.
        """
        final_code = 1 # Assume failure by default

        try:
            if self._task_func:
                # Execute a specific Python function (a wrapper)
                task_name = getattr(self._task_func, '__name__', 'anonymous_task')
                self.command_start.emit(f"Running task: {task_name}")
                print(f"\n> Running task: {task_name}") # Console log

                # Combine initial kwargs with worker context (project_root, signals etc.)
                # Ensure worker context doesn't overwrite initial user input kwargs if names clash
                task_kwargs_with_context = self._task_kwargs.copy()
                task_kwargs_with_context['project_root'] = self._project_root
                # Pass the signal instance itself if it exists
                if self._open_url_signal_instance:
                     task_kwargs_with_context['open_url_signal'] = self._open_url_signal_instance
                # Add any other context needed by wrappers here

                try:
                    # Call the wrapper function with unpacked args and combined kwargs
                    result = self._task_func(*self._task_args, **task_kwargs_with_context)

                    # Assuming wrapper returns (stdout, stderr, returncode)
                    if isinstance(result, tuple) and len(result) == 3:
                         out, err, code = result
                         final_code = code

                         # --- Handle Specific Wrapper Outputs / Signals ---
                         # Import the specific wrapper function here to check its identity
                         try:
                              from .git_wrappers import wrapper_create_pull_request
                              if self._task_func == wrapper_create_pull_request and code == 0 and out:
                                   # Assuming the URL is the primary output of the PR wrapper (in 'out')
                                   # Emit the signal so the main window can open the browser
                                   # Use the stored signal instance
                                   if self._open_url_signal_instance:
                                        self._open_url_signal_instance.emit(out)
                                   # Also emit the output text itself
                                   self.output.emit("PR URL generated:")
                                   self.output.emit(out) # Emit the URL string as output

                              # General case: Emit standard output/error from wrapper result
                              else:
                                   if out:
                                       self.output.emit(out)
                                   if err:
                                       self.error.emit("--- STDERR ---\n" + err)

                         except ImportError:
                              # Handle case where wrapper_create_pull_request might not be importable
                              # Just emit the output/error returned by the wrapper
                              if out: self.output.emit(out)
                              if err: self.error.emit("--- STDERR ---\n" + err)

                    else:
                          # If the wrapper function doesn't return the standard tuple
                          self.output.emit("Task returned non-standard result:")
                          self.output.emit(str(result))
                          final_code = 0 # Assume success if wrapper ran without exception but returned non-standard result

                except Exception as e:
                    # Catch exceptions that happen *inside* the wrapper function
                    error_msg = f"Error executing task '{task_name}': {e}\n{traceback.format_exc()}"
                    self.error.emit(error_msg)
                    final_code = 1


            elif self._command_list:
                # Execute a direct Git command using Popen for streaming output
                command_str = ' '.join(self._command_list)
                self.command_start.emit(f"Executing command: {command_str}")
                # print(f"\n> 执行命令: {command_str}") # Console log

                process = None # Initialize process outside try to ensure it exists in finally

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
                        # This might block if the process doesn't read from stdin immediately
                        # Consider using threads for writing to stdin if it's a complex interaction
                        process.stdin.write(self._input_data)
                        process.stdin.close()

                    # Read output line by line and emit signals
                    # Simple sequential read - consider threaded readers for robustness
                    # Use a timeout or check process.poll() if possible to avoid indefinite blocking
                    stdout_reader = iter(process.stdout.readline, '') if process.stdout else None
                    stderr_reader = iter(process.stderr.readline, '') if process.stderr else None

                    # Read stdout fully, then stderr fully
                    if stdout_reader:
                        for line in stdout_reader:
                            self.output.emit(line.rstrip())

                    if stderr_reader:
                         for line in stderr_reader:
                             self.error.emit(line.rstrip())

                    if process.stdout: process.stdout.close()
                    if process.stderr: process.stderr.close()

                    return_code = process.wait() # Wait for the process to finish
                    final_code = return_code

                    if return_code != 0:
                        # Command failed - error already emitted line by line
                        pass # Final status message emitted later


                except FileNotFoundError:
                    err_msg = "**Error**: Git command not found. Please ensure Git is installed and in your PATH."
                    self.error.emit(err_msg)
                    final_code = 1 # Ensure non-zero code

                except Exception as e:
                    # Catch exceptions during subprocess execution or output reading
                    err_msg = f"An error occurred during command execution: {e}\n{traceback.format_exc()}"
                    self.error.emit(err_msg)
                    final_code = 1

                finally:
                     # Ensure subprocess is cleaned up if something went wrong after Popen
                     if process and process.poll() is None: # Check if process is still running
                         try:
                             print(f"Warning: Process is still running, attempting termination: {' '.join(self._command_list)}", file=sys.stderr)
                             process.terminate() # Attempt graceful termination
                             process.wait(timeout=1) # Wait a bit
                             if process.poll() is None:
                                 print(f"Warning: Process did not terminate, attempting kill: {' '.join(self._command_list)}", file=sys.stderr)
                                 process.kill() # Force kill
                                 process.wait()
                         except Exception as term_e:
                              print(f"Error during process termination: {term_e}", file=sys.stderr)


            else:
                err_msg = "No command or task function specified for the worker."
                self.error.emit(err_msg)
                final_code = 1

        except Exception as e:
             # Catch any remaining unexpected exceptions outside the inner blocks
             err_msg = f"An unexpected critical error occurred in worker: {e}\n{traceback.format_exc()}"
             self.error.emit(err_msg)
             final_code = 1


        # --- Final Status Report ---
        if final_code != 0:
             self.output.emit(f"<span style='color:red; font-weight:bold;'>Operation finished with errors (code {final_code}).</span>")
        else:
             self.output.emit(f"<span style='color:green;'>Operation finished successfully (code {final_code}).</span>")

        self.finished.emit() # Signal completion