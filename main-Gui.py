# main-Gui.py
import sys
import os
from PyQt6.QtWidgets import QApplication

# Import config loading
from src.config_manager import load_config, config, extract_repo_name_from_upstream_url

# Import the MainWindow class from your gui module
from src.gui.main_window import MainWindow

if __name__ == "__main__":
    # Determine the project root directory
    # Assumes main.py is in the root
    project_root = os.path.dirname(os.path.abspath(__file__))
    print(f"Project root determined as: {project_root}") # Console log

    # Load configuration
    # Pass project_root to load_config if config.yaml is relative to root
    load_config("config.yaml") # Load from config.yaml in the root

    # In GUI, initial user input for username/repo might be handled
    # via a settings dialog or be read from config only.
    # For this GUI version, we won't prompt on console at startup like the CLI.
    # The values loaded in 'config' will be used and can potentially be edited via GUI later.
    # You might want to add a dialog here if config is missing critical info.

    app = QApplication(sys.argv)

    # Create and show the main window
    # Pass the project root to the MainWindow so it knows where the Git repo is
    # assuming the script is run from the repo root or needs to operate on a repo at project_root
    main_window = MainWindow(project_root=project_root)
    main_window.show()

    # Start the application event loop
    sys.exit(app.exec())