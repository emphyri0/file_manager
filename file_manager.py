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
import subprocess # Needed for execution
import shutil # Needed for copy/move and which

# --- Configuration / Thresholds ---
WARN_CPU_PERCENT = 60.0; CRIT_CPU_PERCENT = 80.0; WARN_MEM_PERCENT = 70.0; CRIT_MEM_PERCENT = 85.0
WARN_SWAP_PERCENT = 30.0; CRIT_SWAP_PERCENT = 60.0; WARN_DISK_PERCENT = 75.0; CRIT_DISK_PERCENT = 90.0
WARN_CPU_TEMP = 65.0; CRIT_CPU_TEMP = 75.0; WARN_LOAD_MULT = 0.7; CRIT_LOAD_MULT = 1.0

# --- Helper Functions for Formatting ---

def format_permissions(mode):
    """Converts st_mode to 'drwxrwxrwx' string."""
    perms = []
    perms.append('d' if stat.S_ISDIR(mode) else '-' if stat.S_ISREG(mode) else 'l' if stat.S_ISLNK(mode) else '?')
    perms.append('r' if mode & stat.S_IRUSR else '-'); perms.append('w' if mode & stat.S_IWUSR else '-'); perms.append('x' if mode & stat.S_IXUSR else '-')
    perms.append('r' if mode & stat.S_IRGRP else '-'); perms.append('w' if mode & stat.S_IWGRP else '-'); perms.append('x' if mode & stat.S_IXGRP else '-')
    perms.append('r' if mode & stat.S_IROTH else '-'); perms.append('w' if mode & stat.S_IWOTH else '-'); perms.append('x' if mode & stat.S_IXOTH else '-')
    return "".join(perms)

def format_size(size_bytes):
    """Converts bytes to human-readable string (K, M, G, T)."""
    if size_bytes is None or size_bytes < 0: return "     ?" # Placeholder for errors/unknown/dirs
    if size_bytes < 1024: return f"{size_bytes: >6d}B"
    for unit in ['K', 'M', 'G', 'T']:
        size_bytes /= 1024.0
        if size_bytes < 1024.0:
            return f"{size_bytes: >5.1f}{unit}"
    return f"{size_bytes: >5.1f}T"

def format_mtime(timestamp):
    """Formats modification timestamp."""
    if timestamp is None: return "---- -- --:--"
    try:
        dt_object = datetime.datetime.fromtimestamp(timestamp)
        return dt_object.strftime("%b %d %H:%M")
    except ValueError: # Handle potential invalid timestamps
        return "Invalid Date"


# --- Data Fetching Function ---

def get_directory_contents(path):
    """Gets directory contents with details, sorted (dirs first)."""
    items = []
    try:
        for item_name in os.listdir(path):
            full_path = os.path.join(path, item_name)
            # Include full path in details for easier operations later
            item_details = {"name": item_name, "is_dir": False, "size": None, "mtime": None, "mode": 0, "path": full_path}
            try:
                # Use lstat to avoid following symlinks for basic info
                st = os.lstat(full_path)
                item_details["is_dir"] = stat.S_ISDIR(st.st_mode)
                # Size -1 for dirs, None for inaccessible items
                item_details["size"] = st.st_size if not item_details["is_dir"] else -1
                item_details["mtime"] = st.st_mtime
                item_details["mode"] = st.st_mode
                items.append(item_details)
            except (PermissionError, FileNotFoundError, OSError):
                 # Mark as inaccessible but still list it
                 item_details["name"] = item_name + " [?]"
                 # Keep other details as None/0
                 items.append(item_details)
    except PermissionError:
        return None # Indicate permission error on the directory itself
    except FileNotFoundError:
        return [] # Indicate directory not found

    # Sort: directories first, then files, both alphabetically case-insensitive
    items.sort(key=lambda x: (not x["is_dir"], x["name"].lower()))
    return items

# --- Helper Function for User Input ---

def prompt_user(stdscr, y, x, prompt_text):
    """Prompts user for input on the bottom line."""
    curses.echo() # Turn echo on so user sees input
    curses.nocbreak() # Set terminal to cooked mode for normal input
    stdscr.keypad(0) # Turn keypad off during input

    max_y, max_x = stdscr.getmaxyx()
    prompt_line_y = max_y -1
    # Clear the prompt line
    stdscr.move(prompt_line_y, 0)
    stdscr.clrtoeol()
    stdscr.addstr(prompt_line_y, 0, prompt_text)
    stdscr.refresh()

    input_str = None # Default to None
    try:
        # Get user input (bytes), decode to string
        stdscr.move(prompt_line_y, len(prompt_text)) # Move cursor to input position
        input_bytes = stdscr.getstr() # Reads from current cursor pos until newline
        input_str = input_bytes.decode(locale.getpreferredencoding(False)).strip()
    except Exception:
        input_str = None # Handle errors during input

    # Restore terminal settings
    curses.noecho()
    curses.cbreak() # Back to cbreak mode
    stdscr.keypad(1)
    # Clear the prompt line again
    stdscr.move(prompt_line_y, 0)
    stdscr.clrtoeol()

    # Return None if input was empty or only whitespace
    return input_str if input_str else None

def confirm_action(stdscr, y, x, prompt_text):
    """Asks for Y/N confirmation."""
    max_y, max_x = stdscr.getmaxyx()
    prompt_line_y = max_y - 1
    answer = prompt_user(stdscr, prompt_line_y, 0, prompt_text + " (y/N): ")
    return answer is not None and answer.lower() == 'y'


# --- Main Application Function ---

def main(stdscr):
    # --- Initial Curses Setup ---
    curses.curs_set(0); stdscr.nodelay(0); stdscr.keypad(1)
    has_colors = curses.has_colors()
    if has_colors:
        try:
            curses.start_color(); curses.use_default_colors()
            curses.init_pair(1, curses.COLOR_WHITE, -1) # Default
            curses.init_pair(2, curses.COLOR_BLACK, curses.COLOR_WHITE) # Highlight
            curses.init_pair(3, curses.COLOR_BLUE, -1) # Directory
            curses.init_pair(4, curses.COLOR_GREEN, -1) # Executable / Python script
            curses.init_pair(5, curses.COLOR_RED, -1) # Error/Warn text color
        except curses.error: has_colors = False
    # Safe color/attribute functions
    def safe_attron(attr):
        if has_colors: stdscr.attron(attr)
    def safe_attroff(attr):
        if has_colors: stdscr.attroff(attr)
    def safe_color_pair(pair_num):
         return curses.color_pair(pair_num) if has_colors else 0

    # --- State Variables ---
    current_path = os.getcwd()
    selected_index = 0
    scroll_offset = 0
    status_message = ""
    contents_cache = []

    # --- Force Refresh Function ---
    def refresh_contents(path_to_refresh, select_name=None):
        nonlocal contents_cache, selected_index, scroll_offset, status_message
        # Store status before refresh unless it's just "Refreshed."
        prev_status = status_message if "Refreshed." not in status_message else ""

        new_contents = get_directory_contents(path_to_refresh)
        if new_contents is None:
            status_message = f"Error refreshing: Permission denied: {path_to_refresh}"
            contents_cache = []
        else:
            contents_cache = new_contents
            # Restore previous status unless it was empty, otherwise show "Refreshed."
            status_message = prev_status or "Refreshed."

        selected_index = 0
        scroll_offset = 0
        if select_name and contents_cache:
            for i, item in enumerate(contents_cache):
                if item["name"] == select_name:
                    selected_index = i
                    # Adjust scroll offset if needed to make selected item visible
                    list_height = stdscr.getmaxyx()[0] - 4 # Account for borders
                    if list_height > 0:
                        if selected_index < scroll_offset: scroll_offset = selected_index
                        elif selected_index >= scroll_offset + list_height: scroll_offset = selected_index - list_height + 1
                    break

    # --- Initial Data Load ---
    refresh_contents(current_path) # Use refresh function for initial load
    if not contents_cache and "denied" not in status_message.lower():
        status_message = "Directory is empty."


    # --- Main Loop ---
    while True:
        # Get current content cache
        contents = contents_cache
        # Ensure selected_index stays within bounds
        if not contents: selected_index = 0
        else: selected_index = max(0, min(selected_index, len(contents) - 1))

        # --- Drawing ---
        stdscr.erase()
        max_y, max_x = stdscr.getmaxyx()

        # Define list box area coordinates
        list_box_y = 1          # Start below header
        list_box_x = 0
        list_box_height = max_y - 2 # End above status line
        list_box_width = max_x

        # Check if terminal is too small for box + content
        if list_box_height < 3 or list_box_width < 20:
             try: stdscr.addstr(0, 0, "Terminal too small!")
             except: pass
             stdscr.refresh(); key = stdscr.getch()
             if key == ord('q'): break
             continue # Skip rest of loop if too small

        # Header: Current Path (Stays at top)
        header_str = f"Path: {current_path}"
        try:
            safe_attron(curses.A_BOLD); stdscr.addstr(0, 0, header_str[:max_x-1]); safe_attroff(curses.A_BOLD)
        except curses.error: pass

        # --- Draw the Border ---
        border_attr = curses.A_NORMAL
        try:
            stdscr.addch(list_box_y, list_box_x, curses.ACS_ULCORNER, border_attr)
            stdscr.addch(list_box_y, list_box_x + list_box_width - 1, curses.ACS_URCORNER, border_attr)
            stdscr.addch(list_box_y + list_box_height - 1, list_box_x, curses.ACS_LLCORNER, border_attr)
            stdscr.addch(list_box_y + list_box_height - 1, list_box_x + list_box_width - 1, curses.ACS_LRCORNER, border_attr)
            stdscr.hline(list_box_y, list_box_x + 1, curses.ACS_HLINE, list_box_width - 2, border_attr)
            stdscr.hline(list_box_y + list_box_height - 1, list_box_x + 1, curses.ACS_HLINE, list_box_width - 2, border_attr)
            stdscr.vline(list_box_y + 1, list_box_x, curses.ACS_VLINE, list_box_height - 2, border_attr)
            stdscr.vline(list_box_y + 1, list_box_x + list_box_width - 1, curses.ACS_VLINE, list_box_height - 2, border_attr)
        except curses.error: pass

        # --- Content: Directory Listing (Inside the border) ---
        content_y_start = list_box_y + 1
        content_x_start = list_box_x + 1
        content_height = list_box_height - 2 # Available lines inside border
        content_width = list_box_width - 2   # Available columns inside border

        # Define column widths based on available content_width
        perm_width = 10; size_width = 7; date_width = 12
        # Margins inside the border: 1 between cols = 3 total internal margins
        filename_width = max(10, content_width - perm_width - size_width - date_width - 3)

        # Adjust scroll_offset based on selection and content_height
        if selected_index < scroll_offset: scroll_offset = selected_index
        elif selected_index >= scroll_offset + content_height: scroll_offset = selected_index - content_height + 1

        # Define column start positions (relative to content_x_start)
        name_x = content_x_start
        perm_x = name_x + filename_width + 1
        size_x = perm_x + perm_width + 1
        date_x = size_x + size_width + 1

        # Draw visible items
        for i in range(content_height):
            item_index = scroll_offset + i
            # Check index validity before accessing contents
            if 0 <= item_index < len(contents):
                item = contents[item_index]
                perm_str = format_permissions(item.get('mode', 0))
                size_str = format_size(item.get('size', -1) if not item.get('is_dir') else -1)
                date_str = format_mtime(item.get('mtime'))
                display_name = item.get("name", "?")
                is_python_script = display_name.endswith(".py") and not item.get("is_dir")

                if item.get("is_dir"): display_name += "/"
                display_name = display_name[:filename_width] # Truncate name to fit

                # Determine base attributes (color, etc.)
                base_attr = curses.A_NORMAL
                if item.get("is_dir"): base_attr |= safe_color_pair(3) # Directory color
                elif is_python_script: base_attr |= safe_color_pair(4) # Python script color
                elif item.get('mode', 0) & (stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH): base_attr |= safe_color_pair(4) # Other executable color

                # Determine final attributes (highlight if selected)
                line_attr = base_attr
                current_line_y = content_y_start + i
                if item_index == selected_index:
                    line_attr = safe_color_pair(2) # Highlight attribute

                # Draw the line column by column safely
                try:
                    # Draw full line background if highlighted first
                    if item_index == selected_index:
                        stdscr.addstr(current_line_y, name_x, ' ' * content_width, line_attr)

                    # Draw Name
                    stdscr.addstr(current_line_y, name_x, display_name.ljust(filename_width), line_attr)

                    # Draw other columns (use base_attr for text color unless selected)
                    draw_attr = base_attr if item_index != selected_index else line_attr
                    if perm_x + perm_width <= content_x_start + content_width: # Check if column fits
                         stdscr.addstr(current_line_y, perm_x, perm_str, draw_attr)
                    if size_x + size_width <= content_x_start + content_width:
                         stdscr.addstr(current_line_y, size_x, size_str.rjust(size_width), draw_attr) # Right-align size
                    if date_x + date_width <= content_x_start + content_width:
                         stdscr.addstr(current_line_y, date_x, date_str, draw_attr)
                except curses.error: pass # Ignore drawing errors (e.g., off edge)
            else:
                break # Stop if no more items to draw

        # Footer/Status Line (Stays at bottom)
        status_line_y = max_y - 1
        stdscr.move(status_line_y, 0); stdscr.clrtoeol() # Clear previous status
        if status_message:
            # Use red text for errors/denied messages
            msg_attr = safe_color_pair(5) | curses.A_BOLD if "denied" in status_message.lower() or "error" in status_message.lower() else curses.A_NORMAL
            safe_attron(msg_attr); stdscr.addstr(status_line_y, 0, status_message[:max_x-1]); safe_attroff(msg_attr)
        else:
            # Display help text
            help_str = "q:Quit Enter/→:Open/Run(.py)/View Bksp/←/u:Up | r:Rename c:Copy d:Delete"
            stdscr.addstr(status_line_y, 0, help_str[:max_x-1])

        stdscr.refresh()

        # --- Input Handling ---
        key = stdscr.getch()
        action_status = "" # Reset action status for this loop iteration


        # --- Navigation ---
        if key == ord('q'): break
        elif key == curses.KEY_UP: selected_index = max(0, selected_index - 1)
        elif key == curses.KEY_DOWN: selected_index = min(len(contents) - 1 if contents else 0, selected_index + 1)
        elif key == curses.KEY_PPAGE:
             selected_index = max(0, selected_index - content_height); # Use content_height for page scroll
             if selected_index < scroll_offset: scroll_offset = selected_index
        elif key == curses.KEY_NPAGE:
             selected_index = min(len(contents) - 1 if contents else 0, selected_index + content_height);
             if selected_index >= scroll_offset + content_height: scroll_offset = max(0, selected_index - content_height + 1)

        # --- Enter / Execute / View ---
        elif key in [curses.KEY_ENTER, ord('\n'), curses.KEY_RIGHT]:
             if contents and 0 <= selected_index < len(contents): # Check if list is not empty and index is valid
                selected_item = contents[selected_index]
                item_name = selected_item["name"]
                item_path = selected_item["path"]
                is_dir = selected_item["is_dir"]

                if "[?]" in item_name: action_status = f"Cannot open inaccessible item: {item_name}"
                elif is_dir:
                    # Enter directory
                    new_contents_check = get_directory_contents(item_path)
                    if new_contents_check is not None:
                        current_path = item_path; refresh_contents(current_path) # Refresh resets index/scroll
                    elif os.path.isdir(item_path): action_status = f"Permission denied: {item_path}"
                    else: action_status = f"Cannot open: {item_name}" # Should be rare if is_dir was True
                elif item_name.endswith(".py"):
                    # Execute Python Script
                    action_status = f"Executing '{item_name}'..."
                    stdscr.addstr(status_line_y, 0, action_status[:max_x-1]); stdscr.refresh()
                    script_failed = False
                    try:
                        curses.endwin() # Suspend curses
                        print(f"\n--- Running '{item_path}' ---")
                        result = subprocess.run(['python3', item_path], check=False)
                        print(f"\n--- Script finished with exit code {result.returncode} ---")
                        input("--- Press Enter to return ---")
                        # Status message set after re-init
                    except FileNotFoundError:
                         print("\nError: 'python3' command not found."); input("--- Press Enter ---")
                         script_failed = True; action_status = "Error: python3 not found."
                    except Exception as e:
                         print(f"\nError running script: {e}"); input("--- Press Enter ---")
                         script_failed = True; action_status = f"Error running script: {e}"
                    finally:
                         # Re-initialize curses screen after endwin()
                         stdscr = curses.initscr()
                         curses.noecho(); curses.cbreak(); stdscr.keypad(True)
                         if has_colors: curses.start_color(); curses.use_default_colors() # Re-init colors
                         stdscr.clear() # Clear screen before redraw
                         if not script_failed and 'result' in locals(): # Check if result exists
                              action_status = f"Returned from '{item_name}' (code: {result.returncode})."
                         # Set status *before* calling refresh
                         status_message = action_status
                         refresh_contents(current_path, select_name=item_name) # Refresh content cache & status

                else:
                    # --- View Text File ---
                    action_status = f"Viewing '{item_name}'..."
                    stdscr.addstr(status_line_y, 0, action_status[:max_x-1]); stdscr.refresh()
                    view_failed = False
                    less_path = shutil.which('less') # Find path to less command
                    if less_path:
                        try:
                            curses.endwin()
                            print(f"\n--- Viewing '{item_path}' (Press 'q' in less to exit) ---")
                            subprocess.run([less_path, item_path]) # Run less
                            action_status = f"Closed viewer for '{item_name}'."
                        except Exception as e:
                             print(f"\nError running less: {e}"); input("--- Press Enter ---")
                             view_failed = True; action_status = f"Error viewing file: {e}"
                        finally:
                            # Re-initialize curses screen after endwin()
                            stdscr = curses.initscr()
                            curses.noecho(); curses.cbreak(); stdscr.keypad(True)
                            if has_colors: curses.start_color(); curses.use_default_colors()
                            stdscr.clear()
                            status_message = action_status # Set status *before* refresh
                            refresh_contents(current_path, select_name=item_name) # Refresh, reselect
                    else:
                        # less command not found
                        action_status = "Error: 'less' command not found. Cannot view file."
                        curses.flash() # Signal error visually

        # --- Go Up Directory ---
        elif key in [curses.KEY_BACKSPACE, ord('\b'), curses.KEY_LEFT, ord('u')]:
             parent_path = os.path.normpath(os.path.join(current_path, os.pardir))
             if parent_path != current_path: # Check if we are not at root
                 old_basename = os.path.basename(current_path)
                 new_contents_check = get_directory_contents(parent_path) # Test access
                 if new_contents_check is not None:
                     current_path = parent_path; refresh_contents(current_path, select_name=old_basename)
                 else: action_status = f"Permission denied: {parent_path}"

        # --- File Operations (Delete, Rename, Copy) ---
        elif key == ord('d'): # Delete
            if contents and 0 <= selected_index < len(contents):
                item = contents[selected_index]
                if "[?]" in item["name"]: action_status = f"Cannot delete inaccessible item."; continue
                prompt = f"DELETE '{item['name']}'?"
                if confirm_action(stdscr, status_line_y, 0, prompt):
                    try:
                        prev_idx = selected_index # Store index before delete
                        if item["is_dir"]:
                            # Check if empty before attempting rmdir
                            if not os.listdir(item["path"]):
                                os.rmdir(item["path"]); action_status = f"Directory '{item['name']}' deleted."
                            else: action_status = f"Error: Dir '{item['name']}' not empty."
                        else:
                            os.remove(item["path"]); action_status = f"File '{item['name']}' deleted."
                        # Only refresh if status doesn't contain 'Error'
                        if "Error" not in action_status:
                            status_message = action_status # Set success status before refresh
                            refresh_contents(current_path)
                            selected_index = max(0, min(prev_idx, len(contents_cache) - 1)) # Try to keep selection nearby
                    except Exception as e: action_status = f"Error deleting: {e}"
                else: action_status = "Delete cancelled."
        elif key == ord('r'): # Rename / Move
            if contents and 0 <= selected_index < len(contents):
                item = contents[selected_index]
                if "[?]" in item["name"]: action_status = f"Cannot rename inaccessible item."; continue
                prompt = f"New name/path for '{item['name']}': "
                destination = prompt_user(stdscr, status_line_y, 0, prompt)
                if destination:
                    if os.path.sep not in destination: dest_path = os.path.join(current_path, destination)
                    else: dest_path = os.path.normpath(os.path.join(current_path, destination))
                    if item["path"] == dest_path: action_status = "Source and destination are same."; continue
                    try:
                        shutil.move(item["path"], dest_path)
                        action_status = f"Moved/Renamed to '{destination}'."
                        status_message = action_status # Set status before refresh
                        refresh_contents(current_path, select_name=os.path.basename(dest_path))
                    except Exception as e: action_status = f"Error moving: {e}"
                else: action_status = "Rename/Move cancelled."
        elif key == ord('c'): # Copy File
            if contents and 0 <= selected_index < len(contents):
                item = contents[selected_index]
                if "[?]" in item["name"]: action_status = f"Cannot copy inaccessible item."; continue
                if item["is_dir"]: action_status = "Directory copy not implemented."; continue
                prompt = f"Copy '{item['name']}' TO (path/dir): "
                destination = prompt_user(stdscr, status_line_y, 0, prompt)
                if destination:
                    dest_path = os.path.normpath(os.path.join(current_path, destination))
                    # Handle destination being a directory
                    if os.path.isdir(dest_path): dest_path = os.path.join(dest_path, item["name"])
                    if item["path"] == dest_path: action_status = "Source and destination are same."; continue
                    if os.path.exists(dest_path):
                         if not confirm_action(stdscr, status_line_y, 0, f"'{os.path.basename(dest_path)}' exists. Overwrite?"):
                              action_status = "Copy cancelled."; continue
                    try:
                        shutil.copy2(item["path"], dest_path) # copy2 preserves metadata
                        action_status = f"Copied to '{destination}'."
                        status_message = action_status # Set status before refresh
                        refresh_contents(current_path, select_name=item["name"]) # Reselect original
                    except Exception as e: action_status = f"Error copying: {e}"
                else: action_status = "Copy cancelled."

        # Set status message for the *next* loop iteration if it was set by an action
        status_message = action_status or status_message


# --- Main execution ---
if __name__ == "__main__":
    try: locale.setlocale(locale.LC_ALL, '') # Set locale for correct encoding/chars
    except locale.Error: pass
    # curses.wrapper handles initial setup and final cleanup (endwin)
    curses.wrapper(main)
