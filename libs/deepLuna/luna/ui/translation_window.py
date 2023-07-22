import contextlib
import os
import shutil
import time

from functools import cmp_to_key

import tkinter as tk
from tkinter.ttk import (
    Style,
    Treeview,
)

from libs.deepLuna.luna.constants import Constants
from libs.deepLuna.luna.readable_exporter import ReadableExporter
from libs.deepLuna.luna.translation_db import TranslationDb


class TranslationWindow:

    # Constants for TK event masks
    TKSTATE_SHIFT = 0x0001
    TKSTATE_CAPS = 0x0002
    TKSTATE_CTRL = 0x0004
    TKSTATE_L_ALT = 0x0008

    def __init__(self, root):
        # Cache TK root
        self._root = root

        # Reference for warning dialog handles
        self._warning = None
        self._conflict_dialog = None
        self._charswap_map_editor = None

        # Currently loaded scene / string
        self._loaded_scene = None
        self._loaded_offset = None

        # Try and load the translation DB from file
        self._translation_db = TranslationDb.from_file(
            Constants.DATABASE_PATH)

        # Configure UI
        self._root.resizable(height=False, width=False)
        self._root.title("deepLuna — Editor")

        # Configure style vars
        self.load_style()

        # Translation percentage UI
        self.init_translation_percent_ui()

        # Container for editing zone
        # Used by scene selector tree, line selector, tl line view
        self.frame_editing = tk.Frame(self._root, borderwidth=1)

        # Scene selector tree
        self.init_scene_selector_tree()

        # Line selector
        self.init_line_selector()

        # Selected line orig/tl/comments
        self.init_tl_line_view()

        # Hook close function to prompt save
        self._root.protocol("WM_DELETE_WINDOW", self.on_close)

        # Scan update dir for any new files
        self.import_legacy_updates()
        self.import_updates()

        # Init total translated percent field
        self.update_global_tl_percent()

    def update_global_tl_percent(self):
        percent_translated = self._translation_db.translated_percent()
        self.percent_translated_global.delete("1.0", tk.END)
        self.percent_translated_global.insert(
            "1.0", "%.1f%%" % percent_translated)

    def update_selected_scene_tl_percent(self):
        # If there's no scene loaded, do nothing
        if not self._loaded_scene:
            return

        # How many lines are actually TLd
        scene_lines = self._translation_db.lines_for_scene(self._loaded_scene)
        idx = 0
        translated_count = 0
        for line in scene_lines:
            tl_info = self._translation_db.tl_line_with_hash(line.jp_hash)
            if tl_info.en_text:
                translated_count += 1
            idx += 1

        # Update UI
        self.percent_translated_day.delete("1.0", tk.END)
        self.percent_translated_day.insert(
            "1.0",
            str(round(translated_count*100/max(idx, 1), 1))+"%")
        self._name_day.set(self._loaded_scene + ": ")

    def on_close(self):
        # Prompt to save the DB
        self._warning = tk.Toplevel(self._root)
        self._warning.title("deepLuna")
        self._warning.resizable(height=False, width=False)
        self._warning.attributes("-topmost", True)
        self._warning.grab_set()

        # Warning text
        warning_message = tk.Label(
            self._warning,
            text="WARNING: Do you want to close without saving?"
        )
        warning_message.grid(row=0, column=0, pady=5)

        # Buttons
        self.frame_quit_buttons = tk.Frame(self._warning, borderwidth=2)
        quit_and_save_button = tk.Button(
            self.frame_quit_buttons,
            text="Save and Quit",
            width=15,
            command=self.save_and_quit
        )
        quit_and_save_button.grid(row=0, column=0, padx=5, pady=10)
        quit_button = tk.Button(
            self.frame_quit_buttons,
            text="Quit",
            width=15,
            command=self.quit_editor
        )
        quit_button.grid(row=0, column=1, padx=5, pady=10)
        self.frame_quit_buttons.grid(row=1, column=0, pady=5)

    def save_and_quit(self):
        # Save DB
        with open(Constants.DATABASE_PATH, 'wb+') as output:
            output.write(self._translation_db.as_json().encode('utf-8'))

        # Exit
        self.quit_editor()

    def close_warning(self):
        if self._warning:
            self._warning.grab_release()
            self._warning.destroy()
            self._warning = None

    def quit_editor(self):
        self.close_warning()
        self._root.destroy()

    def init_tl_line_view(self):
        self.text_frame = tk.Frame(self.frame_editing, borderwidth=20)

        # Original JP text field
        self.labels_txt_orig = tk.Label(
            self.text_frame, text="Original text:")
        self.labels_txt_orig.grid(row=1, column=1)
        self.text_orig = tk.Text(
            self.text_frame,
            width=60,
            height=10,
            borderwidth=5,
            highlightbackground="#A8A8A8"
        )
        self.text_orig.config(state=tk.DISABLED)
        self.text_orig.grid(row=2, column=1)

        # Translated text field
        self.labels_txt_trad = tk.Label(
            self.text_frame, text="Translated text:")
        self.labels_txt_trad.grid(row=3, column=1)
        self.text_translated = tk.Text(
            self.text_frame,
            width=60,
            height=10,
            borderwidth=5,
            highlightbackground="#A8A8A8"
        )
        self.text_translated.grid(row=4, column=1)

        # Comments field
        self.labels_txt_comment = tk.Label(
            self.text_frame, text="Comments:")
        self.labels_txt_comment.grid(row=5, column=1)
        self.text_comment = tk.Text(
            self.text_frame,
            width=60,
            height=2,
            borderwidth=5,
            highlightbackground="#A8A8A8"
        )
        self.text_comment.grid(row=6, column=1)

        # Text buttons
        self.frame_buttons = tk.Frame(self.text_frame, borderwidth=10)

        # Update current line
        self.button_save_line = tk.Button(
            self.frame_buttons,
            text="Update Line",
            command=self.save_line
        )
        self.button_save_line.grid(row=1, column=1, padx=2)

        # Save DB
        self.button_save_file = tk.Button(
            self.frame_buttons,
            text="Save DB",
            command=self.save_translation_table
        )
        self.button_save_file.grid(row=1, column=2, padx=2)

        # Pack new script_text mrg
        self.button_insert_translation = tk.Button(
            self.frame_buttons,
            text="Insert",
            command=self.insert_translation
        )
        self.button_insert_translation.grid(row=1, column=3, padx=2, pady=2)

        # Edit character swap mapping
        self.button_edit_charswap_map = tk.Button(
            self.frame_buttons,
            text="Configure Charswap",
            command=self.edit_charswap_map
        )
        self.button_edit_charswap_map.grid(row=1, column=4, padx=2, pady=2)

        # Re-scan import dir
        self.button_search_text = tk.Button(
            self.frame_buttons,
            text="Re-Import Updates",
            command=self.import_updates
        )
        self.button_search_text.grid(row=2, column=1, padx=2, pady=2)

        # Export selected scene
        self.button_export_page = tk.Button(
            self.frame_buttons,
            text="Export scene",
            command=self.export_page
        )
        self.button_export_page.grid(row=2, column=2, padx=2, pady=2)

        # Export _all_ scenes
        self.button_export_all = tk.Button(
            self.frame_buttons,
            text="Export all",
            command=self.export_all_pages
        )
        self.button_export_all.grid(row=2, column=3, padx=2)

        # Pack button region
        self.frame_buttons.grid(row=7, column=1)

        # Toggle options frame
        self.frame_options = tk.Frame(self.text_frame, borderwidth=10)

        # Should the text be charswapped for non-EN languages?
        self.text_swapText = tk.Label(self.frame_options, text="Swap text")
        self.text_swapText.grid(row=0, column=0)

        self.var_swapText = tk.BooleanVar()
        self.var_swapText.set(False)

        self.option_swapText = tk.Checkbutton(
            self.frame_options,
            variable=self.var_swapText,
            onvalue=True,
            offvalue=False
        )
        self.option_swapText.grid(row=0, column=1)

        # Pack all containers
        self.frame_options.grid(row=8, column=1)
        self.text_frame.pack(side=tk.LEFT)
        self.frame_editing.grid(row=2, column=1)

    def edit_charswap_map(self):
        self._charswap_map_editor = tk.Toplevel(self._root)
        self._charswap_map_editor.resizable(height=False, width=False)
        self._charswap_map_editor.title("Edit swap table")
        self._charswap_map_editor.grab_set()

        tk.Label(
            self._charswap_map_editor,
            text="Enter the character pairs to be swapped\n"
                 "One pair per line, separated by a comma"
        ).grid(row=0, column=0)

        self.swap_text_zone = tk.Text(
            self._charswap_map_editor,
            width=20,
            height=25,
            borderwidth=5,
            highlightbackground="#A8A8A8"
        )
        self.swap_text_zone.grid(row=1, column=0)

        # Initialize text area with existing map
        existing_map = self._translation_db.get_charswap_map()
        existing_map_text = "\n".join([
            f"{k},{v}"
            for k, v in existing_map.items()
        ])
        self.swap_text_zone.delete("1.0", tk.END)
        self.swap_text_zone.insert("1.0", existing_map_text)

        swap_frame_buttons = tk.Frame(
            self._charswap_map_editor, borderwidth=10)

        swap_ok_button = tk.Button(
            swap_frame_buttons,
            text="Save",
            command=self.save_charswap_config
        )
        swap_ok_button.grid(row=0, column=0)

        swap_warning_button = tk.Button(
            swap_frame_buttons,
            text="Cancel",
            command=self.close_charswap_editor
        )
        swap_warning_button.grid(row=0, column=1, pady=10)
        swap_frame_buttons.grid(row=2, column=0)

    def save_charswap_config(self):
        # Retrieve the new settings text
        swap_conf_text = self.swap_text_zone.get("1.0", tk.END)

        # Split out the entries
        swap_map = {}
        for line in swap_conf_text.split("\n"):
            # Ignore blanks
            if not line:
                continue

            # Split on comma
            split_line = line.split(",")
            if len(split_line) != 2:
                print(f"Invalid charswap entry '{line}', ignoring")
                continue
            swap_map[split_line[0].strip()] = split_line[1].strip()

        # Write the swap map to the TL DB
        self._translation_db.set_charswap_map(swap_map)

        # Save DB to persist config
        self.save_translation_table()

        # Close dialog
        self.close_charswap_editor()

    def close_charswap_editor(self):
        if self._charswap_map_editor:
            self._charswap_map_editor.grab_release()
            self._charswap_map_editor.destroy()
            self._charswap_map_editor = None

    def save_line(self):
        # Is a valid string loaded
        if self._loaded_offset is None:
            return

        # Check the active scene is valid
        if self._loaded_scene not in self._translation_db.scene_names():
            return

        # Get the line info for the selected offset
        scene_lines = self._translation_db.lines_for_scene(self._loaded_scene)
        selected_line = scene_lines[self._loaded_offset]

        # Extract the new tl/comment
        new_tl = self.text_translated.get("1.0", tk.END).strip("\n")
        new_comment = self.text_comment.get("1.0", tk.END).strip("\n")

        # Write them back to the translation DB
        self._translation_db.set_translation_and_comment_for_hash(
            selected_line.jp_hash,
            new_tl,
            new_comment
        )

        # Mark the line as green
        self.listbox_offsets.itemconfig(self._loaded_offset, bg='#BCECC8')

        # Update TL $
        self.update_global_tl_percent()
        self.update_selected_scene_tl_percent()

    def save_translation_table(self):
        # Write out the translation DB to file
        with open(Constants.DATABASE_PATH, 'wb+') as output:
            output.write(self._translation_db.as_json().encode('utf-8'))

    def insert_translation(self):
        # Export the script as an MZP
        mzp_data = self._translation_db.generate_script_text_mrg(
            perform_charswap=self.var_swapText.get())

        # Write to file
        current_time = time.strftime('%Y%m%d-%H%M%S')
        output_filename = f"script_text_translated{current_time}.mrg"
        with open(output_filename, 'wb+') as f:
            f.write(mzp_data)

        print(f"Exported translation to {output_filename}")

        # Dialog
        self._warning = tk.Toplevel(self._root)
        self._warning.title("Injection Complete")
        self._warning.resizable(height=False, width=False)
        self._warning.attributes("-topmost", True)
        self._warning.grab_set()

        # Set message
        warning_message = tk.Label(
            self._warning,
            text=f"Script injected to {output_filename}",
            justify=tk.LEFT
        )
        warning_message.grid(row=0, column=0, padx=5, pady=5)

        # Button choices
        warning_button = tk.Button(
            self._warning,
            text="OK",
            command=self.close_warning
        )
        warning_button.grid(row=1, column=0, pady=10)

    def export_page(self):
        self._translation_db.export_scene(
            self._loaded_scene, Constants.EXPORT_DIRECTORY)

        # Dialog
        self._warning = tk.Toplevel(self._root)
        self._warning.title("Export Complete")
        self._warning.resizable(height=False, width=False)
        self._warning.attributes("-topmost", True)
        self._warning.grab_set()

        # Set message
        warning_message = tk.Label(
            self._warning,
            text=f"Exported scene f{self._loaded_scene} "
                 f"to {Constants.EXPORT_DIRECTORY}",
            justify=tk.LEFT
        )
        warning_message.grid(row=0, column=0, padx=5, pady=5)

        # Button choices
        warning_button = tk.Button(
            self._warning,
            text="OK",
            command=self.close_warning
        )
        warning_button.grid(row=1, column=0, pady=10)

    def export_all_pages(self):
        for scene in self._translation_db.scene_names():
            self._translation_db.export_scene(
                scene, Constants.EXPORT_DIRECTORY)

        # Dialog
        self._warning = tk.Toplevel(self._root)
        self._warning.title("Export Complete")
        self._warning.resizable(height=False, width=False)
        self._warning.attributes("-topmost", True)
        self._warning.grab_set()

        # Set message
        warning_message = tk.Label(
            self._warning,
            text=f"Exported all scenes to {Constants.EXPORT_DIRECTORY}",
            justify=tk.LEFT
        )
        warning_message.grid(row=0, column=0, padx=5, pady=5)

        # Button choices
        warning_button = tk.Button(
            self._warning,
            text="OK",
            command=self.close_warning
        )
        warning_button.grid(row=1, column=0, pady=10)

    def import_updates(self):
        # Any goodies for us in the update folder?
        candidate_files = []
        for basedir, dirs, files in os.walk(Constants.IMPORT_DIRECTORY):
            for filename in files:
                # Ignore non-text files
                if not filename.endswith(".txt"):
                    continue

                candidate_files.append(os.path.join(basedir, filename))

        # Generate a diff
        import_diff = self._translation_db.parse_update_file_list(
            candidate_files)

        # Apply non-conflict data immediately
        self._translation_db.apply_diff(import_diff)

        # Clear out the input files
        for basedir, dirs, files in os.walk(Constants.IMPORT_DIRECTORY):
            for dirname in dirs:
                shutil.rmtree(os.path.join(basedir, dirname))
                pass
            for filename in files:
                os.unlink(os.path.join(basedir, filename))
                pass

        # If there are no conflicts, we are done
        if not import_diff.any_conflicts():
            return

        self.show_conflict_resolution(import_diff)

    def show_conflict_resolution(self, diff):
        # Cache the active conflict set
        self._active_conflicts = {
            sha: entry_group
            for sha, entry_group
            in diff.entries_by_sha.items()
            if not entry_group.is_unique()
        }

        print(f"Conflict count: {len(self._active_conflicts)} ")

        # Prompt to save the DB
        self._conflict_dialog = tk.Toplevel(self._root)
        self._conflict_dialog.title("Resolve Conflicts")
        self._conflict_dialog.resizable(height=True, width=True)
        self._conflict_dialog.attributes("-topmost", True)
        self._conflict_dialog.grab_set()

        # Warning text
        warning_message = tk.Label(
            self._conflict_dialog,
            text=f"Import detected {len(self._active_conflicts)} conflicts"
        )
        warning_message.grid(row=0, column=0, pady=5)

        # Conflict entries
        self._conflict_listboxes = []
        frame_listboxes = tk.Frame(self._conflict_dialog, borderwidth=2)
        ordered_hashes = sorted(self._active_conflicts.keys())
        for jp_hash in ordered_hashes:
            jp_text = self._translation_db.tl_line_with_hash(jp_hash).jp_text
            entry_group = self._active_conflicts[jp_hash]
            tk.Label(
                frame_listboxes,
                text=f"{jp_hash}\n{jp_text.rstrip()}"
            ).grid(row=len(self._conflict_listboxes)*2, column=0)

            # Create a listbox to select the correct tl
            option_listbox = tk.Listbox(
                frame_listboxes,
                height=len(entry_group.entries),
                exportselection=False,
                selectmode=tk.SINGLE
            )
            option_listbox.grid(
                row=len(self._conflict_listboxes)*2+1,
                column=0,
                pady=5,
                sticky="nswe"
            )

            # Populate
            idx = 0
            for entry in entry_group.entries:
                option_listbox.insert(
                    idx,
                    f"{os.path.basename(entry.filename)}:L{entry.line}: "
                    f"{entry.en_text}"
                )
                idx += 1

            # Cache a reference
            self._conflict_listboxes.append(option_listbox)
        frame_listboxes.grid_columnconfigure(0, weight=1)
        frame_listboxes.grid(row=1, column=0, pady=5, sticky="nsew")

        # Buttons
        frame_quit_buttons = tk.Frame(self._conflict_dialog, borderwidth=2)
        quit_and_save_button = tk.Button(
            frame_quit_buttons,
            text="Commit Changes",
            width=15,
            command=self.commit_conflict_resolution
        )
        quit_and_save_button.grid(row=0, column=0, padx=5, pady=10)
        quit_button = tk.Button(
            frame_quit_buttons,
            text="Cancel",
            width=15,
            command=self.dismiss_conflict_resolution
        )
        quit_button.grid(row=0, column=1, padx=5, pady=10)
        frame_quit_buttons.grid(row=2, column=0, pady=5)

        self._conflict_dialog.grid_columnconfigure(0, weight=1)
        self._conflict_dialog.grid_rowconfigure(0, weight=0)
        self._conflict_dialog.grid_rowconfigure(1, weight=1)
        self._conflict_dialog.grid_rowconfigure(2, weight=0)

    def commit_conflict_resolution(self):
        # Iterate each of the selectors, and if something is selected commit it
        ordered_hashes = sorted(self._active_conflicts.keys())
        for i in range(len(ordered_hashes)):
            jp_hash = ordered_hashes[i]
            entry_group = self._active_conflicts[jp_hash]

            listbox = self._conflict_listboxes[i]
            selected_indexes = listbox.curselection()
            if not selected_indexes:
                continue

            selected_index = selected_indexes[0]
            selected_tl = entry_group.entries[selected_index]

            print(f"Commit conflict {jp_hash}: {selected_tl.en_text}")
            self._translation_db.set_translation_and_comment_for_hash(
                jp_hash, selected_tl.en_text, selected_tl.comment)

        # Close the dialog
        self.dismiss_conflict_resolution()

    def dismiss_conflict_resolution(self):
        if self._conflict_dialog:
            self._conflict_dialog.grab_release()
            self._conflict_dialog.destroy()
            self._conflict_dialog = None

    def import_legacy_updates(self):
        # Scan the legacy update folder for old-style files
        for basedir, dirs, files in os.walk(Constants.LEGACY_IMPORT_DIRECTORY):
            for filename in files:
                # Ignore non-text files
                if not filename.endswith(".txt"):
                    continue

                # Import the changes from the file
                try:
                    absolute_path = os.path.join(basedir, filename)
                    self._translation_db.import_legacy_update_file(
                        absolute_path)

                    # If we successfully loaded it, delete it.
                    os.unlink(absolute_path)
                except AssertionError as e:
                    print(
                        f"Failed to apply updates from {filename}: "
                        f"{e}"
                    )

    def init_line_selector(self):
        self.line_selector_frame = tk.Frame(self.frame_editing, borderwidth=20)

        # Header label
        self.label_offsets = tk.Label(
            self.line_selector_frame,
            text="Original text offsets:")
        self.label_offsets.pack()

        # Listbox containing list of page: text offset
        self.listbox_offsets = tk.Listbox(
            self.line_selector_frame,
            height=32,
            width=18,
            exportselection=False,
            selectmode=tk.SINGLE
        )
        self.listbox_offsets.bind('<Button-1>', self.load_translation_line)
        self.listbox_offsets.bind('<Return>', self.load_translation_line)
        self.listbox_offsets.pack(side=tk.LEFT, fill=tk.BOTH)
        self.scrollbar_offsets = tk.Scrollbar(self.line_selector_frame)
        self.scrollbar_offsets.pack(side=tk.RIGHT, fill=tk.BOTH)

        self.listbox_offsets.config(yscrollcommand=self.scrollbar_offsets.set)
        self.scrollbar_offsets.config(command=self.listbox_offsets.yview)

        self.line_selector_frame.pack(side=tk.LEFT)

    @staticmethod
    def compare_scenes(in_a, in_b):
        """
        Compare function for scene names that sorts integer fragments properly.
        """
        def decimal_extract(val):
            ret = []
            is_chr = True
            acc = ""
            for c in val:
                if '0' <= c and c <= '9':
                    # If there was a character acc, append it
                    if is_chr and acc:
                        ret.append(acc)
                        acc = ""

                    # Now in non-char acc mode
                    is_chr = False
                    acc += c
                else:
                    # If there was a non-char acc, apend it
                    if not is_chr and acc:
                        ret.append(int(acc))
                        acc = ""

                    # Now in char mode
                    is_chr = True
                    acc += c

            # Handle trailing acc value
            if acc:
                ret.append(acc if is_chr else int(acc))

            return ret

        scene_a = decimal_extract(in_a)
        scene_b = decimal_extract(in_b)

        i = 0
        for i in range(max(len(scene_a), len(scene_b))):
            # Longer is greater
            if i >= len(scene_a):
                return -1
            if i >= len(scene_b):
                return 1

            # If the types match, direct compare
            val_a = scene_a[i]
            val_b = scene_b[i]
            if type(val_a) is type(val_b):
                if val_a < val_b:
                    return -1
                if val_a > val_b:
                    return 1
            else:
                # If the types don't match, compare on the lex order of
                # type names
                type_a_name = str(type(val_a))
                type_b_name = str(type(val_b))
                if type_a_name < type_b_name:
                    return -1
                if type_a_name > type_b_name:
                    return 1

        # If we get all the way here, they are equal
        return 0

    def init_scene_selector_tree(self):
        self.frame_tree = tk.Frame(self.frame_editing, borderwidth=20)
        self.scene_tree = Treeview(
            self.frame_tree,
            height=21,
            style="smallFont.Treeview"
        )
        self.scene_tree.column('#0', anchor='w', width=320)
        self.scene_tree.heading('#0', text='Game text', anchor='center')

        # Add all of the scene names to the treeview
        scene_names = self._translation_db.scene_names()
        ciel_scenes = [name for name in scene_names if '_CIEL' in name]
        arc_scenes = [name for name in scene_names if '_ARC' in name]
        qa_scenes = [name for name in scene_names if 'QA' in name]
        misc_scenes = [
            name for name in scene_names
            if name not in set(ciel_scenes + arc_scenes + qa_scenes)]

        # Create top level categories
        categories = [
            ('Arcueid', 'arc'),
            ('Ciel', 'ciel'),
            ('QA', 'qa'),
            ('Misc', 'misc'),
        ]
        for category_name, category_id in categories:
            self.scene_tree.insert(
                '',
                tk.END,
                text=category_name,
                iid=category_id,
                open=False
            )

        # Helper fun to add arc/ciel scenes, which are by-day
        def insert_day_scene_tree(root, scene_names):
            # Create day holders
            day_names = sorted(list(set([
                v.split('_')[0] for v in scene_names])))
            for day in day_names:
                self.scene_tree.insert(
                    root,
                    tk.END,
                    text=f"Day {day}",
                    iid=f"{root}_{day}",
                    open=False
                )

            # Add arc scenes to appropriate days
            sorted_scenes = sorted(
                scene_names, key=cmp_to_key(self.compare_scenes))
            for scene in sorted_scenes:
                scene_day = scene.split('_')[0]
                self.scene_tree.insert(
                    f"{root}_{scene_day}",
                    tk.END,
                    text=scene,
                    iid=scene,
                    open=False
                )

        insert_day_scene_tree('arc', arc_scenes)
        insert_day_scene_tree('ciel', ciel_scenes)

        # Helper fun to insert the non-day scenes
        def insert_non_day_scene_tree(root, scene_names):
            sorted_scenes = sorted(
                scene_names, key=cmp_to_key(self.compare_scenes))
            for scene in sorted_scenes:
                self.scene_tree.insert(
                    root,
                    tk.END,
                    text=scene,
                    iid=scene,
                    open=False
                )

        insert_non_day_scene_tree('qa', qa_scenes)
        insert_non_day_scene_tree('misc', misc_scenes)

        # Double-click scenes to load
        self.scene_tree.bind('<Double-Button-1>', self.load_scene)

        self.scene_tree.grid(row=0, column=0, padx=5, pady=5, sticky='nsew')
        self.frame_tree.pack(side=tk.LEFT)

    def load_scene(self, _event):
        # Get the selected scene id
        scene = self.scene_tree.focus()

        # If this isn't a real scene (e.g. a day header), do nothing
        if scene not in self._translation_db.scene_names():
            return

        # Clear old data from offsets list
        self.listbox_offsets.delete(0, tk.END)

        # Add new entries for each translation offset
        scene_lines = self._translation_db.lines_for_scene(scene)
        idx = 0
        translated_count = 0
        for line in scene_lines:
            modifiers = []
            if line.has_ruby:
                modifiers.append('*')
            if line.is_glued:
                modifiers.append('+')
            if line.is_choice:
                modifiers.append('?')
            self.listbox_offsets.insert(
                idx,
                "%03d: %05d %s" % (
                    line.page_number,
                    line.offset,
                    ''.join(modifiers)
                )
            )
            tl_info = self._translation_db.tl_line_with_hash(line.jp_hash)
            if tl_info.en_text:
                self.listbox_offsets.itemconfig(idx, bg='#BCECC8')
                translated_count += 1
            idx += 1

        # Cache the selected scene
        self._loaded_scene = scene

        # Update current day translated percent
        self.update_global_tl_percent()
        self.update_selected_scene_tl_percent()

    def load_translation_line(self, _event):
        # Get the selected line indexes
        # (multiple selection possible, but ignored)
        selected_indexes = self.listbox_offsets.curselection()
        if not selected_indexes:
            return

        # Check the active scene is valid
        if self._loaded_scene not in self._translation_db.scene_names():
            return

        # Cache the offset
        self._loaded_offset = selected_indexes[0]

        # Load the relevant line info from the scene
        scene_lines = self._translation_db.lines_for_scene(self._loaded_scene)
        selected_line = scene_lines[self._loaded_offset]

        # Get the translation data for this JP hash
        tl_info = self._translation_db.tl_line_with_hash(selected_line.jp_hash)

        # Update the text fields
        with self.editable_orig_text():
            self.text_orig.delete("1.0", tk.END)
            self.text_translated.delete("1.0", tk.END)
            self.text_comment.delete("1.0", tk.END)

            self.text_orig.insert("1.0", tl_info.jp_text)
            self.text_translated.insert("1.0", tl_info.en_text or "")
            self.text_comment.insert("1.0", tl_info.comment or "")

    @contextlib.contextmanager
    def editable_orig_text(self):
        self.text_orig.config(state=tk.NORMAL)
        try:
            yield None
        finally:
            self.text_orig.config(state=tk.DISABLED)

    def init_translation_percent_ui(self):
        # Name of currently loaded day
        self._name_day = tk.StringVar()
        self._name_day.set('No day loaded ')

        # UI containers
        self.frame_info = tk.Frame(self._root, borderwidth=20)
        self.frame_local_tl = tk.Frame(self.frame_info, borderwidth=10)
        self.frame_global_tl = tk.Frame(self.frame_info, borderwidth=10)

        # Label showing the translation percentage for the loaded day
        self.label_percent_translated_day = tk.Label(
            self.frame_local_tl,
            textvariable=self._name_day
        )
        self.label_percent_translated_day.grid(row=0, column=0)

        # Counter box with the translation percentage for the loaded day
        self.percent_translated_day = tk.Text(
            self.frame_local_tl,
            width=6,
            height=1,
            borderwidth=5,
            highlightbackground="#A8A8A8"
        )
        self.percent_translated_day.bind("<Key>", self.on_keyevent)
        self.percent_translated_day.grid(row=0, column=1)

        # Pack the local TL percentage area
        self.frame_local_tl.grid(row=0, column=0, padx=10)

        # Global tl stats label
        self.label_percent_translated_global = tk.Label(
            self.frame_global_tl,
            text="Translated text: "
        )
        self.label_percent_translated_global.grid(row=0, column=0)

        # Global tl stats counter
        self.percent_translated_global = tk.Text(
            self.frame_global_tl,
            width=6,
            height=1,
            borderwidth=5,
            highlightbackground="#A8A8A8"
        )
        self.percent_translated_global.bind("<Key>", self.on_keyevent)
        self.percent_translated_global.grid(row=0, column=1)
        self.frame_global_tl.grid(row=0, column=1, padx=10)

        # Pack top info frame
        self.frame_info.grid(row=1, column=1)

    def load_style(self):
        self._style = Style()
        self._style.theme_use('clam')
        self._style.configure(
            "blue.Horizontal.TProgressbar",
            foreground='green',
            background='green'
        )
        self._style.configure(
            "smallFont.Treeview",
            font='TkDefaultFont 11',
            rowheight=24
        )
        self._style.configure(
            "smallFont.Treeview.Heading",
            font='TkDefaultFont 11'
        )

    def on_keyevent(self, event):
        # Ctrl-C exits
        if event.state == self.TKSTATE_CTRL and event.keysym == 'c':
            return None

        # Alt-c exits
        if event.state == self.TKSTATE_L_ALT and event.keysym == 'c':
            return None

        # No clue what these are for, Haka.
        if event.char in ['\uf700', '\uf701', '\uf701', '\uf701']:
            return None

        return "break"
