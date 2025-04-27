# Curses File Manager

A simple, terminal-based file manager written in Python using the `curses` library. It provides basic functionalities for navigating directories, viewing file details, performing simple file operations, executing Python scripts, and viewing text files.

## Features

* **Single-Pane View:** Displays the contents of the current directory in a single list.
* **Navigation:**
    * Move selection up/down with arrow keys (`↑`/`↓`).
    * Page up/down with `PgUp`/`PgDn`.
    * Enter directories using `Enter` or `→` (Right Arrow).
    * Go to the parent directory using `Backspace`, `←` (Left Arrow), or `u`.
* **File Details:** Shows permissions (e.g., `drwxr-xr-x`), human-readable file size (B, K, M, G, T), and last modification date/time.
* **Visuals:**
    * Border drawn around the file listing area.
    * Color coding for directories (blue), Python scripts/executables (green).
    * Reverse video highlighting for the selected item.
* **File Operations:**
    * **Rename/Move (`r`):** Renames or moves the selected file/directory. Prompts for the new name/path.
    * **Copy (`c`):** Copies the selected **file** (directory copy not yet implemented). Prompts for the destination path/directory. Asks for confirmation if the destination exists.
    * **Delete (`d`):** Deletes the selected **file** or **empty directory**. Requires confirmation (y/N). *Recursive delete for non-empty directories is NOT implemented for safety.*
* **Execute Python Scripts (`Enter` / `→`):** Runs the selected `.py` file using `python3`. Temporarily suspends the file manager to show script output.
* **View Files (`Enter` / `→`):** Opens other selected files using the `less` pager (if installed). Temporarily suspends the file manager.
* **Status Bar:** Displays the current path, item count, basic help, and status/error messages.

## Requirements

* **Python 3.x**
* **`curses` module:** Usually built-in with Python on Linux and macOS. May require separate installation (`libncursesw5-dev` package on Debian/Ubuntu might be needed for *developing* with curses, but usually not just for running).
* **`less` command:** Required for the file viewing functionality (`Enter` on non-Python files). Usually pre-installed on most Linux distributions.

## Installation

1.  **Clone the repository:**
    ```bash
    git clone https://github.com/emphyri0/file_manager
    cd curses-file-manager 
    ```
    

2.  **No extra Python libraries needed!** Uses only standard library modules (`os`, `stat`, `datetime`, `locale`, `curses`, `shutil`, `subprocess`).

## Usage

Run the script from your terminal. It's recommended to use a terminal that supports colors and UTF-8 encoding for the best experience.

```bash
python3 file_manager.py
