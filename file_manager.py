# -*- coding: utf-8 -*-
import curses
import os
import stat
import pwd
import grp
import datetime
import locale
import socket
import platform
import subprocess
import shutil

# --- Configuration / Thresholds ---
WARN_CPU_PERCENT = 60.0; CRIT_CPU_PERCENT = 80.0; WARN_MEM_PERCENT = 70.0; CRIT_MEM_PERCENT = 85.0
WARN_SWAP_PERCENT = 30.0; CRIT_SWAP_PERCENT = 60.0; WARN_DISK_PERCENT = 75.0; CRIT_DISK_PERCENT = 90.0
WARN_CPU_TEMP = 65.0; CRIT_CPU_TEMP = 75.0; WARN_LOAD_MULT = 0.7; CRIT_LOAD_MULT = 1.0

# --- Helper Functions ---
def format_permissions(mode):
    perms = []
    perms.append('d' if stat.S_ISDIR(mode) else '-' if stat.S_ISREG(mode) else 'l' if stat.S_ISLNK(mode) else '?')
    perms.append('r' if mode & stat.S_IRUSR else '-'); perms.append('w' if mode & stat.S_IWUSR else '-'); perms.append('x' if mode & stat.S_IXUSR else '-')
    perms.append('r' if mode & stat.S_IRGRP else '-'); perms.append('w' if mode & stat.S_IWGRP else '-'); perms.append('x' if mode & stat.S_IXGRP else '-')
    perms.append('r' if mode & stat.S_IROTH else '-'); perms.append('w' if mode & stat.S_IWOTH else '-'); perms.append('x' if mode & stat.S_IXOTH else '-')
    return "".join(perms)
def format_size(size_bytes):
    if size_bytes is None or size_bytes < 0: return "     ?"
    if size_bytes < 1024: return f"{size_bytes: >6d}B"
    for unit in ['K', 'M', 'G', 'T']:
        size_bytes /= 1024.0
        if size_bytes < 1024.0: return f"{size_bytes: >5.1f}{unit}"
    return f"{size_bytes: >5.1f}T"
def format_mtime(timestamp):
    if timestamp is None: return "---- -- --:--"
    try: return datetime.datetime.fromtimestamp(timestamp).strftime("%b %d %H:%M")
    except ValueError: return "Invalid Date"

# --- Data Fetching Function ---
def get_directory_contents(path):
    items = []
    try:
        for item_name in os.listdir(path):
            full_path = os.path.join(path, item_name)
            item_details = {"name": item_name, "is_dir": False, "size": None, "mtime": None, "mode": 0, "path": full_path}
            try:
                st = os.lstat(full_path)
                item_details["is_dir"] = stat.S_ISDIR(st.st_mode)
                item_details["size"] = st.st_size if not item_details["is_dir"] else -1
                item_details["mtime"] = st.st_mtime
                item_details["mode"] = st.st_mode
                items.append(item_details)
            except (PermissionError, FileNotFoundError, OSError):
                 item_details["name"] = item_name + " [?]"; items.append(item_details)
    except PermissionError: return None
    except FileNotFoundError: return []
    items.sort(key=lambda x: (not x["is_dir"], x["name"].lower()))
    return items

# --- Helper Functions for Input/Confirmation ---
def prompt_user(stdscr, y, x, prompt_text):
    curses.echo(); curses.nocbreak(); stdscr.keypad(0)
    max_y, max_x = stdscr.getmaxyx(); prompt_line_y = max_y -1
    stdscr.move(prompt_line_y, 0); stdscr.clrtoeol()
    stdscr.addstr(prompt_line_y, 0, prompt_text); stdscr.refresh()
    input_str = None
    try:
        stdscr.move(prompt_line_y, len(prompt_text)); input_bytes = stdscr.getstr()
        input_str = input_bytes.decode(locale.getpreferredencoding(False)).strip()
    except Exception: input_str = None
    curses.noecho(); curses.cbreak(); stdscr.keypad(1)
    stdscr.move(prompt_line_y, 0); stdscr.clrtoeol()
    return input_str if input_str else None
def confirm_action(stdscr, y, x, prompt_text):
    max_y, max_x = stdscr.getmaxyx(); prompt_line_y = max_y - 1
    answer = prompt_user(stdscr, prompt_line_y, 0, prompt_text + " (y/N): ")
    return answer is not None and answer.lower() == 'y'

# --- Main Application Function ---
def main(stdscr):
    # --- Initial Curses Setup ---
    curses.curs_set(0); stdscr.nodelay(0); stdscr.keypad(1) # Keypad essential for arrows
    curses.cbreak(); curses.noecho() # Set modes explicitly
    has_colors = curses.has_colors()
    if has_colors:
        try:
            curses.start_color(); curses.use_default_colors()
            curses.init_pair(1, curses.COLOR_WHITE, -1); curses.init_pair(2, curses.COLOR_BLACK, curses.COLOR_WHITE)
            curses.init_pair(3, curses.COLOR_BLUE, -1); curses.init_pair(4, curses.COLOR_GREEN, -1)
            curses.init_pair(5, curses.COLOR_RED, -1)
        except curses.error: has_colors = False
    def safe_attron(attr):
        if has_colors: stdscr.attron(attr)
    def safe_attroff(attr):
        if has_colors: stdscr.attroff(attr)
    def safe_color_pair(pair_num):
         return curses.color_pair(pair_num) if has_colors else 0

    # --- State Variables ---
    current_path = os.getcwd(); selected_index = 0; scroll_offset = 0
    status_message = ""; contents_cache = []

    # --- Force Refresh Function ---
    def refresh_contents(path_to_refresh, select_name=None):
        nonlocal contents_cache, selected_index, scroll_offset, status_message
        prev_status = status_message if "Refreshed." not in status_message else ""
        new_contents = get_directory_contents(path_to_refresh)
        if new_contents is None:
            status_message = f"Error refreshing: Permission denied: {path_to_refresh}"; contents_cache = []
        else:
            contents_cache = new_contents; status_message = prev_status or "Refreshed."
        selected_index = 0; scroll_offset = 0
        if select_name and contents_cache:
            for i, item in enumerate(contents_cache):
                if item["name"] == select_name:
                    selected_index = i
                    # Check if stdscr is valid before getting maxyx
                    try:
                        list_height = stdscr.getmaxyx()[0] - 4
                        if list_height > 0:
                            if selected_index < scroll_offset: scroll_offset = selected_index
                            elif selected_index >= scroll_offset + list_height: scroll_offset = selected_index - list_height + 1
                    except: pass # Ignore if stdscr is invalid (e.g., during init)
                    break

    # --- Initial Data Load ---
    refresh_contents(current_path)
    if not contents_cache and "denied" not in status_message.lower():
        status_message = "Directory is empty."

    # --- Main Loop ---
    while True:
        contents = contents_cache
        if not contents: selected_index = 0
        else: selected_index = max(0, min(selected_index, len(contents) - 1))

        # --- Drawing ---
        stdscr.erase()
        max_y, max_x = stdscr.getmaxyx()
        list_box_y = 1; list_box_x = 0; list_box_height = max_y - 2; list_box_width = max_x
        if list_box_height < 3 or list_box_width < 20:
             try: stdscr.addstr(0, 0, "Terminal too small!")
             except: pass
             stdscr.refresh(); key = stdscr.getch()
             if key == ord('q'): break
             continue

        header_str = f"Path: {current_path}"
        try: safe_attron(curses.A_BOLD); stdscr.addstr(0, 0, header_str[:max_x-1]); safe_attroff(curses.A_BOLD)
        except curses.error: pass

        border_attr = curses.A_NORMAL
        try: # Draw Border
            stdscr.addch(list_box_y, list_box_x, curses.ACS_ULCORNER, border_attr); stdscr.addch(list_box_y, list_box_x + list_box_width - 1, curses.ACS_URCORNER, border_attr)
            stdscr.addch(list_box_y + list_box_height - 1, list_box_x, curses.ACS_LLCORNER, border_attr); stdscr.addch(list_box_y + list_box_height - 1, list_box_x + list_box_width - 1, curses.ACS_LRCORNER, border_attr)
            stdscr.hline(list_box_y, list_box_x + 1, curses.ACS_HLINE, list_box_width - 2, border_attr); stdscr.hline(list_box_y + list_box_height - 1, list_box_x + 1, curses.ACS_HLINE, list_box_width - 2, border_attr)
            stdscr.vline(list_box_y + 1, list_box_x, curses.ACS_VLINE, list_box_height - 2, border_attr); stdscr.vline(list_box_y + 1, list_box_x + list_box_width - 1, curses.ACS_VLINE, list_box_height - 2, border_attr)
        except curses.error: pass

        content_y_start = list_box_y + 1; content_x_start = list_box_x + 1
        content_height = list_box_height - 2; content_width = list_box_width - 2
        perm_width = 10; size_width = 7; date_width = 12
        filename_width = max(10, content_width - perm_width - size_width - date_width - 3)
        name_x = content_x_start; perm_x = name_x + filename_width + 1; size_x = perm_x + perm_width + 1; date_x = size_x + size_width + 1

        if selected_index < scroll_offset: scroll_offset = selected_index
        elif selected_index >= scroll_offset + content_height: scroll_offset = selected_index - content_height + 1

        for i in range(content_height): # Draw list content
            item_index = scroll_offset + i
            if 0 <= item_index < len(contents):
                item = contents[item_index]; perm_str = format_permissions(item.get('mode', 0))
                size_str = format_size(item.get('size', -1) if not item.get('is_dir') else -1); date_str = format_mtime(item.get('mtime'))
                display_name = item.get("name", "?"); is_python_script = display_name.endswith(".py") and not item.get("is_dir")
                if item.get("is_dir"): display_name += "/"; display_name = display_name[:filename_width]
                base_attr = curses.A_NORMAL
                if item.get("is_dir"): base_attr |= safe_color_pair(3)
                elif is_python_script: base_attr |= safe_color_pair(4)
                elif item.get('mode', 0) & (stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH): base_attr |= safe_color_pair(4)
                line_attr = base_attr; current_line_y = content_y_start + i
                if item_index == selected_index: line_attr = safe_color_pair(2)
                try:
                    if item_index == selected_index: stdscr.addstr(current_line_y, name_x, ' ' * content_width, line_attr)
                    stdscr.addstr(current_line_y, name_x, display_name.ljust(filename_width), line_attr)
                    draw_attr = base_attr if item_index != selected_index else line_attr
                    if perm_x + perm_width <= content_x_start + content_width: stdscr.addstr(current_line_y, perm_x, perm_str, draw_attr)
                    if size_x + size_width <= content_x_start + content_width: stdscr.addstr(current_line_y, size_x, size_str.rjust(size_width), draw_attr)
                    if date_x + date_width <= content_x_start + content_width: stdscr.addstr(current_line_y, date_x, date_str, draw_attr)
                except curses.error: pass
            else: break

        status_line_y = max_y - 1
        stdscr.move(status_line_y, 0); stdscr.clrtoeol()
        if status_message:
            msg_attr = safe_color_pair(5) | curses.A_BOLD if "denied" in status_message.lower() or "error" in status_message.lower() else curses.A_NORMAL
            safe_attron(msg_attr); stdscr.addstr(status_line_y, 0, status_message[:max_x-1]); safe_attroff(msg_attr)
        else:
            help_str = "q:Quit Enter/→:Open/Run(.py)/View Bksp/←/u:Up | r:Rename c:Copy d:Delete"
            stdscr.addstr(status_line_y, 0, help_str[:max_x-1])

        stdscr.refresh()

        # --- Input Handling ---
        key = stdscr.getch()
        action_status = "" # Reset action status

        # --- Navigation ---
        if key == ord('q'): break
        elif key == curses.KEY_UP: selected_index = max(0, selected_index - 1)
        elif key == curses.KEY_DOWN: selected_index = min(len(contents) - 1 if contents else 0, selected_index + 1)
        elif key == curses.KEY_PPAGE:
             selected_index = max(0, selected_index - content_height);
             if selected_index < scroll_offset: scroll_offset = selected_index
        elif key == curses.KEY_NPAGE:
             selected_index = min(len(contents) - 1 if contents else 0, selected_index + content_height);
             if selected_index >= scroll_offset + content_height: scroll_offset = max(0, selected_index - content_height + 1)

        # --- Enter / Execute / View ---
        elif key in [curses.KEY_ENTER, ord('\n'), curses.KEY_RIGHT]:
             if contents and 0 <= selected_index < len(contents):
                selected_item = contents[selected_index]; item_name = selected_item["name"]; item_path = selected_item["path"]; is_dir = selected_item["is_dir"]
                if "[?]" in item_name: action_status = f"Cannot open inaccessible item: {item_name}"
                elif is_dir:
                    new_contents_check = get_directory_contents(item_path)
                    if new_contents_check is not None: current_path = item_path; refresh_contents(current_path)
                    elif os.path.isdir(item_path): action_status = f"Permission denied: {item_path}"
                    else: action_status = f"Cannot open: {item_name}"
                elif item_name.endswith(".py"):
                    action_status = f"Executing '{item_name}'..."; stdscr.addstr(status_line_y, 0, action_status[:max_x-1]); stdscr.refresh();
                    try:
                        # *** USE def_prog_mode / reset_prog_mode ***
                        curses.def_prog_mode() # Save current terminal state
                        curses.endwin()        # Suspend curses
                        print(f"\n--- Running '{item_path}' ---")
                        result = subprocess.run(['python3', item_path], check=False)
                        print(f"\n--- Script finished with exit code {result.returncode} ---")
                        input("--- Press Enter to return ---")
                        curses.reset_prog_mode() # Restore terminal state
                        stdscr.clear() # Clear screen needed after reset
                        stdscr.refresh() # Refresh to apply restored state
                        action_status = f"Returned from '{item_name}' (code: {result.returncode})."
                        refresh_contents(current_path, select_name=item_name) # Refresh content cache
                    except FileNotFoundError:
                         # Need to handle state if endwin() was called but run failed
                         curses.reset_prog_mode(); stdscr.refresh(); curses.flash()
                         action_status = "Error: 'python3' command not found."
                    except Exception as e:
                         curses.reset_prog_mode(); stdscr.refresh(); curses.flash()
                         action_status = f"Error running script: {e}"

                else: # View other files
                    action_status = f"Viewing '{item_name}'..."; stdscr.addstr(status_line_y, 0, action_status[:max_x-1]); stdscr.refresh();
                    less_path = shutil.which('less')
                    if less_path:
                        try:
                            # *** USE def_prog_mode / reset_prog_mode ***
                            curses.def_prog_mode()
                            curses.endwin()
                            # print(f"\n--- Viewing '{item_path}' (Press 'q' in less to exit) ---") # Optional message
                            subprocess.run([less_path, item_path]) # Run less
                            curses.reset_prog_mode()
                            stdscr.clear()
                            stdscr.refresh()
                            action_status = f"Closed viewer for '{item_name}'."
                            refresh_contents(current_path, select_name=item_name)
                        except Exception as e:
                             curses.reset_prog_mode(); stdscr.refresh(); curses.flash()
                             action_status = f"Error viewing file: {e}"
                    else: action_status = "Error: 'less' command not found."; curses.flash()

        # --- Go Up Directory ---
        elif key in [curses.KEY_BACKSPACE, ord('\b'), curses.KEY_LEFT, ord('u')]:
             parent_path = os.path.normpath(os.path.join(current_path, os.pardir))
             if parent_path != current_path:
                 old_basename = os.path.basename(current_path)
                 new_contents_check = get_directory_contents(parent_path)
                 if new_contents_check is not None: current_path = parent_path; refresh_contents(current_path, select_name=old_basename)
                 else: action_status = f"Permission denied: {parent_path}"

        # --- File Operations (Delete, Rename, Copy - unchanged logic) ---
        elif key == ord('d'):
             if contents and 0 <= selected_index < len(contents):
                 item = contents[selected_index]; prev_idx = selected_index
                 if "[?]" in item["name"]: action_status = f"Cannot delete inaccessible item."; continue
                 if confirm_action(stdscr, status_line_y, 0, f"DELETE '{item['name']}'?"):
                     try:
                         if item["is_dir"]:
                             if not os.listdir(item["path"]): os.rmdir(item["path"]); action_status = f"Dir '{item['name']}' deleted."
                             else: action_status = f"Error: Dir '{item['name']}' not empty."
                         else: os.remove(item["path"]); action_status = f"File '{item['name']}' deleted."
                         if "Error" not in action_status: refresh_contents(current_path); selected_index = max(0, min(prev_idx, len(contents_cache) - 1))
                     except Exception as e: action_status = f"Error deleting: {e}"
                 else: action_status = "Delete cancelled."
        elif key == ord('r'):
            if contents and 0 <= selected_index < len(contents):
                item = contents[selected_index]
                if "[?]" in item["name"]: action_status = f"Cannot rename inaccessible item."; continue
                destination = prompt_user(stdscr, status_line_y, 0, f"New name/path for '{item['name']}': ")
                if destination:
                    if os.path.sep not in destination: dest_path = os.path.join(current_path, destination)
                    else: dest_path = os.path.normpath(os.path.join(current_path, destination))
                    if item["path"] == dest_path: action_status = "Source and destination are same."; continue
                    try: shutil.move(item["path"], dest_path); action_status = f"Moved/Renamed to '{destination}'."; refresh_contents(current_path, select_name=os.path.basename(dest_path))
                    except Exception as e: action_status = f"Error moving: {e}"
                else: action_status = "Rename/Move cancelled."
        elif key == ord('c'):
            if contents and 0 <= selected_index < len(contents):
                item = contents[selected_index]
                if "[?]" in item["name"]: action_status = f"Cannot copy inaccessible item."; continue
                if item["is_dir"]: action_status = "Directory copy not implemented."; continue
                destination = prompt_user(stdscr, status_line_y, 0, f"Copy '{item['name']}' TO (path/dir): ")
                if destination:
                    dest_path = os.path.normpath(os.path.join(current_path, destination))
                    if os.path.isdir(dest_path): dest_path = os.path.join(dest_path, item["name"])
                    if item["path"] == dest_path: action_status = "Source and destination are same."; continue
                    if os.path.exists(dest_path):
                         if not confirm_action(stdscr, status_line_y, 0, f"'{os.path.basename(dest_path)}' exists. Overwrite?"): action_status = "Copy cancelled."; continue
                    try: shutil.copy2(item["path"], dest_path); action_status = f"Copied to '{destination}'."; refresh_contents(current_path, select_name=item["name"])
                    except Exception as e: action_status = f"Error copying: {e}"
                else: action_status = "Copy cancelled."

        # Set status message for the *next* loop iteration
        status_message = action_status


# --- Main execution ---
if __name__ == "__main__":
    try: locale.setlocale(locale.LC_ALL, '')
    except locale.Error: pass
    curses.wrapper(main)
