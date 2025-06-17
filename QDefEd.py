import re
import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext

class QuakeEntity:
    def __init__(self, name="", rgb=(0.8, 0.1, 0.8), bbox_min=None, bbox_max=None, flags=None, info=""):
        self.name = name
        self.rgb = list(rgb) # Ensure it's mutable
        self.bbox_min = list(bbox_min) if bbox_min is not None else None # Can be None
        self.bbox_max = list(bbox_max) if bbox_max is not None else None # Can be None
        self.flags = flags if flags is not None else []
        self.info = info

    def to_def_string(self):
        """Converts the entity data to a Quake .def file string."""
        rgb_str = f"({self.rgb[0]:.1f} {self.rgb[1]:.1f} {self.rgb[2]:.1f})"

        # Handle BBox values based on presence
        # Requirement 1: Only one '?' in the definition if no BBox values are present
        if self.bbox_min is not None and self.bbox_max is not None:
            bbox_str_combined = f"({self.bbox_min[0]} {self.bbox_min[1]} {self.bbox_min[2]}) ({self.bbox_max[0]} {self.bbox_max[1]} {self.bbox_max[2]})"
        elif self.bbox_min is None and self.bbox_max is None:
            bbox_str_combined = "?"
        else:
            # This case should ideally be prevented by GUI validation, but as a fallback
            # if only one is present, we'll treat them as absent for formatting.
            bbox_str_combined = "?"

        flags_str = " ".join(self.flags)

        # Build the first line parts, including the combined BBox string
        first_line_parts = [self.name, rgb_str, bbox_str_combined]
        if flags_str:
            first_line_parts.append(flags_str)

        first_line = " ".join(first_line_parts)
        info_formatted = self.info.strip()

        return f"/*QUAKED {first_line}\n{info_formatted}\n*/"

    @classmethod
    def from_def_string(cls, def_block):
        """Parses a Quake .def block string and returns a QuakeEntity object."""
        match = re.search(r'/\*QUAKED\s+(.*?)\s*\*/', def_block, re.DOTALL)
        if not match:
            return None

        block_content = match.group(1).strip()

        first_line_end = block_content.find('\n')
        if first_line_end == -1:
            first_line = block_content
            info_here = ""
        else:
            first_line = block_content[:first_line_end].strip()
            info_here = block_content[first_line_end:].strip()

        # Fix: Use regex to correctly tokenize the first line,
        # treating parenthesized groups like "(R G B)" or "(X Y Z)" as single parts.
        # This regex matches either a sequence of non-whitespace characters (\S+)
        # or anything enclosed in parentheses, including the parentheses themselves (\([^\)]*\)).
        parts = re.findall(r'(\([^\)]*\)|\S+)', first_line)

        if not parts:
            return None

        name = parts[0]
        rgb = [0.8, 0.1, 0.8] # Default
        bbox_min = None       # Default
        bbox_max = None       # Default

        parsed_components = set() # To keep track of successfully parsed main components

        i = 1 # Start checking from the second part (after name)

        # 1. Parse RGB
        # Use a more specific regex for RGB values inside parentheses to ensure correct parsing
        if i < len(parts) and re.match(r'^\(\s*\S+\s+\S+\s+\S+\s*\)$', parts[i]):
            try:
                rgb = [float(x) for x in parts[i].strip('()').split()]
                parsed_components.add(parts[i]) # Add the RGB string to parsed_components
                i += 1 # Advance index
            except ValueError:
                pass # If parsing fails, current part is not a valid RGB, it will be treated as a flag.

        # 2. Parse Bounding Box Min and Max
        if i < len(parts): # Check if there are parts left to parse for BBox
            part_bbox_candidate_min = parts[i]

            # Case 1: BBox is '?'
            if part_bbox_candidate_min == "?":
                parsed_components.add(part_bbox_candidate_min) # Add '?' to parsed_components
                i += 1 # Advance index
                # bbox_min and bbox_max remain None, which is correct
            # Case 2: BBox starts with '(X Y Z)'
            # Use a more specific regex for integer coordinates inside parentheses
            elif re.match(r'^\(\s*[-]?\d+\s+[-]?\d+\s+[-]?\d+\s*\)$', part_bbox_candidate_min):
                try:
                    bbox_min = [int(x) for x in part_bbox_candidate_min.strip('()').split()]
                    parsed_components.add(part_bbox_candidate_min)
                    i += 1 # Advance index, expecting bbox_max next

                    # Try to parse bbox_max
                    if i < len(parts):
                        part_bbox_candidate_max = parts[i]
                        if re.match(r'^\(\s*[-]?\d+\s+[-]?\d+\s+[-]?\d+\s*\)$', part_bbox_candidate_max):
                            try:
                                bbox_max = [int(x) for x in part_bbox_candidate_max.strip('()').split()]
                                parsed_components.add(part_bbox_candidate_max)
                                i += 1 # Advance index
                            except ValueError:
                                # Malformed bbox_max, it won't be parsed, and will remain in subsequent flags_raw
                                pass
                        # else: If it's not (X Y Z) for bbox_max, it remains in flags_raw
                except ValueError:
                    # Malformed bbox_min, it won't be parsed, and will remain in subsequent flags_raw
                    pass
            # else: If it's not '?' and not (X Y Z) format, it's not a bbox,
            # and it will be treated as a flag (falls through to flags_raw)

        # Remaining parts are flags (the `parts` list after all main components are consumed)
        # Requirement 2: Omit RGB and BBox strings from flags if they were correctly parsed
        flags = [flag for flag in parts[i:] if flag not in parsed_components]

        return cls(name, rgb, bbox_min, bbox_max, flags, info_here)


class EntityEditorApp:
    def __init__(self, master):
        self.master = master
        master.title("Quake Entity Definition Editor")
        master.geometry("1000x700")

        self.entities = []
        self.current_file_path = None
        self.unsaved_changes = False
        self.selected_entity_index = None # Keep track of the currently selected entity's index

        self._create_widgets()
        self._setup_layout()
        self._create_menu()
        self._clear_entity_details()

    def _create_widgets(self):
        self.entity_list_frame = tk.Frame(self.master, bd=2, relief="groove")
        tk.Label(self.entity_list_frame, text="Entities").pack(pady=5)
        self.entity_listbox = tk.Listbox(self.entity_list_frame, height=20, width=40)
        self.entity_listbox.pack(padx=5, pady=5, fill=tk.BOTH, expand=True)
        # Only bind to when the selection *changes* within the listbox
        self.entity_listbox.bind('<<ListboxSelect>>', self._on_entity_listbox_select)

        self.add_entity_btn = tk.Button(self.entity_list_frame, text="Add New Entity", command=self._add_new_entity)
        self.add_entity_btn.pack(pady=5)
        self.remove_entity_btn = tk.Button(self.entity_list_frame, text="Remove Selected Entity", command=self._remove_selected_entity)
        self.remove_entity_btn.pack(pady=5)

        self.details_frame = tk.Frame(self.master, bd=2, relief="groove")

        tk.Label(self.details_frame, text="Entity Name:").grid(row=0, column=0, sticky="w", padx=5, pady=2)
        self.name_entry = tk.Entry(self.details_frame, width=50)
        self.name_entry.grid(row=0, column=1, sticky="ew", padx=5, pady=2)

        tk.Label(self.details_frame, text="RGB (R G B):").grid(row=1, column=0, sticky="w", padx=5, pady=2)
        self.rgb_entry = tk.Entry(self.details_frame, width=50)
        self.rgb_entry.grid(row=1, column=1, sticky="ew", padx=5, pady=2)

        tk.Label(self.details_frame, text="BBox Min (X Y Z or ?):").grid(row=2, column=0, sticky="w", padx=5, pady=2)
        self.bbox_min_entry = tk.Entry(self.details_frame, width=50)
        self.bbox_min_entry.grid(row=2, column=1, sticky="ew", padx=5, pady=2)

        tk.Label(self.details_frame, text="BBox Max (X Y Z or ?):").grid(row=3, column=0, sticky="w", padx=5, pady=2)
        self.bbox_max_entry = tk.Entry(self.details_frame, width=50)
        self.bbox_max_entry.grid(row=3, column=1, sticky="ew", padx=5, pady=2)

        tk.Label(self.details_frame, text="Flags:").grid(row=4, column=0, sticky="nw", padx=5, pady=2)
        self.flags_listbox = tk.Listbox(self.details_frame, height=5, width=40)
        self.flags_listbox.grid(row=4, column=1, sticky="ew", padx=5, pady=2)
        # Bind right-click for flag selection
        self.flags_listbox.bind('<Button-3>', self._on_flag_right_click)


        self.flag_input_frame = tk.Frame(self.details_frame)
        self.flag_input_frame.grid(row=5, column=1, sticky="ew", padx=5, pady=2)
        self.new_flag_entry = tk.Entry(self.flag_input_frame, width=30)
        self.new_flag_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        tk.Button(self.flag_input_frame, text="Add Flag", command=self._add_flag).pack(side=tk.LEFT, padx=2)
        tk.Button(self.flag_input_frame, text="Remove Flag", command=self._remove_flag).pack(side=tk.LEFT, padx=2)

        tk.Label(self.details_frame, text="Description/Info:").grid(row=6, column=0, sticky="nw", padx=5, pady=2)
        self.info_text = scrolledtext.ScrolledText(self.details_frame, width=60, height=10, wrap=tk.WORD)
        self.info_text.grid(row=6, column=1, sticky="ew", padx=5, pady=2)

        self.apply_btn = tk.Button(self.details_frame, text="Apply Changes to Entity", command=self._apply_entity_changes)
        self.apply_btn.grid(row=7, column=0, columnspan=2, pady=10)

    def _setup_layout(self):
        self.master.grid_rowconfigure(0, weight=1)
        self.master.grid_columnconfigure(0, weight=0)
        self.master.grid_columnconfigure(1, weight=1)

        self.entity_list_frame.grid(row=0, column=0, sticky="nswe", padx=5, pady=5)
        self.details_frame.grid(row=0, column=1, sticky="nswe", padx=5, pady=5)

        self.details_frame.grid_columnconfigure(1, weight=1)

    def _create_menu(self):
        menubar = tk.Menu(self.master)
        self.master.config(menu=menubar)

        file_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="File", menu=file_menu)
        file_menu.add_command(label="New File", command=self._new_file)
        file_menu.add_command(label="Open File...", command=self._open_file)
        file_menu.add_command(label="Save", command=self._save_file)
        file_menu.add_command(label="Save As...", command=self._save_file_as)
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self._on_exit)

    def _new_file(self):
        if self.unsaved_changes:
            if not messagebox.askyesno("Unsaved Changes", "You have unsaved changes. Do you want to discard them and create a new file?"):
                return
        self.entities = []
        self.current_file_path = None
        self.unsaved_changes = False
        self._update_entity_listbox()
        self._clear_entity_details()
        self.master.title("Quake Entity Definition Editor - [New File]")

    def _open_file(self):
        if self.unsaved_changes:
            if not messagebox.askyesno("Unsaved Changes", "You have unsaved changes. Do you want to discard them and open a new file?"):
                return

        file_path = filedialog.askopenfilename(defaultextension=".def",
                                                filetypes=[("Quake Definition Files", "*.def"), ("All Files", "*.*")])
        if file_path:
            try:
                with open(file_path, 'r') as f:
                    content = f.read()

                blocks = re.findall(r'/\*QUAKED\s+(.*?)\s*\*/', content, re.DOTALL)
                new_entities = []
                for block in blocks:
                    entity = QuakeEntity.from_def_string(f"/*QUAKED {block.strip()} */")
                    if entity:
                        new_entities.append(entity)
                self.entities = new_entities
                self.current_file_path = file_path
                self.unsaved_changes = False
                self._update_entity_listbox()
                self._clear_entity_details()
                self.master.title(f"Quake Entity Definition Editor - {file_path}")
            except Exception as e:
                messagebox.showerror("Error", f"Failed to open file: {e}")

    def _save_file(self):
        if not self.current_file_path:
            self._save_file_as()
        else:
            self._write_entities_to_file(self.current_file_path)

    def _save_file_as(self):
        file_path = filedialog.asksaveasfilename(defaultextension=".def",
                                                  filetypes=[("Quake Definition Files", "*.def"), ("All Files", "*.*")])
        if file_path:
            self.current_file_path = file_path
            self._write_entities_to_file(self.current_file_path)

    def _write_entities_to_file(self, file_path):
        try:
            with open(file_path, 'w') as f:
                for entity in self.entities:
                    f.write(entity.to_def_string() + "\n\n")
            self.unsaved_changes = False
            messagebox.showinfo("Save Successful", f"File saved to {file_path}")
            self.master.title(f"Quake Entity Definition Editor - {file_path}")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to save file: {e}")

    def _update_entity_listbox(self):
        self.entity_listbox.delete(0, tk.END)
        for entity in self.entities:
            self.entity_listbox.insert(tk.END, entity.name)

    def _on_entity_listbox_select(self, event):
        # This function is now specifically for handling selection *within* the entity listbox.
        selected_indices = self.entity_listbox.curselection()
        if not selected_indices:
            # If nothing is selected (e.g., list became empty), clear details.
            # Otherwise, retain current details if focus simply moved away.
            if not self.entities: # Only clear if entity list is truly empty
                self._clear_entity_details()
            return

        index = selected_indices[0]
        # Only update if the selected entity has actually changed
        if index != self.selected_entity_index:
            self.selected_entity_index = index
            entity = self.entities[index]
            self._load_entity_details(entity)

    def _load_entity_details(self, entity):
        self.name_entry.delete(0, tk.END)
        self.name_entry.insert(0, entity.name)

        self.rgb_entry.delete(0, tk.END)
        self.rgb_entry.insert(0, f"{entity.rgb[0]} {entity.rgb[1]} {entity.rgb[2]}")

        self.bbox_min_entry.delete(0, tk.END)
        if entity.bbox_min is not None:
            self.bbox_min_entry.insert(0, f"{entity.bbox_min[0]} {entity.bbox_min[1]} {entity.bbox_min[2]}")
        else:
            self.bbox_min_entry.insert(0, "?")

        self.bbox_max_entry.delete(0, tk.END)
        if entity.bbox_max is not None:
            self.bbox_max_entry.insert(0, f"{entity.bbox_max[0]} {entity.bbox_max[1]} {entity.bbox_max[2]}")
        else:
            self.bbox_max_entry.insert(0, "?")

        self.flags_listbox.delete(0, tk.END)
        for flag in entity.flags:
            self.flags_listbox.insert(tk.END, flag)

        self.info_text.delete(1.0, tk.END)
        self.info_text.insert(1.0, entity.info)

    def _clear_entity_details(self):
        self.name_entry.delete(0, tk.END)
        self.rgb_entry.delete(0, tk.END)
        self.bbox_min_entry.delete(0, tk.END)
        self.bbox_max_entry.delete(0, tk.END)
        self.flags_listbox.delete(0, tk.END)
        self.new_flag_entry.delete(0, tk.END)
        self.info_text.delete(1.0, tk.END)
        self.selected_entity_index = None # Reset selected entity index when details are cleared

    def _add_new_entity(self):
        # Default new entity will have None for bbox_min/max, so it will display '?'
        new_entity = QuakeEntity(name="new_entity_name")
        self.entities.append(new_entity)
        self._update_entity_listbox()
        self.entity_listbox.selection_clear(0, tk.END)
        self.entity_listbox.selection_set(tk.END)
        self.entity_listbox.see(tk.END)
        # Manually trigger load for the newly added entity
        self.selected_entity_index = len(self.entities) - 1
        self._load_entity_details(new_entity)
        self.unsaved_changes = True

    def _remove_selected_entity(self):
        selected_indices = self.entity_listbox.curselection()
        if not selected_indices:
            messagebox.showwarning("No Selection", "Please select an entity to remove.")
            return

        if messagebox.askyesno("Confirm Removal", "Are you sure you want to remove the selected entity?"):
            index_to_remove = selected_indices[0]
            del self.entities[index_to_remove]
            self.unsaved_changes = True
            self._update_entity_listbox()
            self._clear_entity_details() # Clear details after removal
            # If there are still entities, select the one closest to the removed one
            if self.entities:
                new_selection_index = min(index_to_remove, len(self.entities) - 1)
                self.entity_listbox.selection_set(new_selection_index)
                self.entity_listbox.see(new_selection_index)
                self.selected_entity_index = new_selection_index
                self._load_entity_details(self.entities[new_selection_index])
            else:
                self.selected_entity_index = None


    def _apply_entity_changes(self):
        if self.selected_entity_index is None:
            messagebox.showwarning("No Entity Selected", "Please select or add an entity first.")
            return

        try:
            current_entity = self.entities[self.selected_entity_index]

            current_entity.name = self.name_entry.get().strip()
            if not current_entity.name:
                raise ValueError("Entity name cannot be empty.")

            rgb_parts = [float(x) for x in self.rgb_entry.get().strip().split()]
            if len(rgb_parts) != 3: raise ValueError("RGB must be 3 numbers.")
            current_entity.rgb = rgb_parts

            bbox_min_str = self.bbox_min_entry.get().strip()
            bbox_max_str = self.bbox_max_entry.get().strip()

            # --- Validation for BBox presence ---
            if (bbox_min_str == "?" and bbox_max_str != "?") or \
               (bbox_min_str != "?" and bbox_max_str == "?"):
                raise ValueError("Both BBox Min and BBox Max must be present OR both must be '?'")

            if bbox_min_str == "?" and bbox_max_str == "?":
                current_entity.bbox_min = None
                current_entity.bbox_max = None
            else:
                try:
                    bbox_min_parts = [int(x) for x in bbox_min_str.split()]
                    if len(bbox_min_parts) != 3: raise ValueError("BBox Min must be 3 integers.")
                    current_entity.bbox_min = bbox_min_parts
                except ValueError:
                    raise ValueError("Invalid format for BBox Min. Use 'X Y Z' or '?'.")

                try:
                    bbox_max_parts = [int(x) for x in bbox_max_str.split()]
                    if len(bbox_max_parts) != 3: raise ValueError("BBox Max must be 3 integers.")
                    current_entity.bbox_max = bbox_max_parts
                except ValueError:
                    raise ValueError("Invalid format for BBox Max. Use 'X Y Z' or '?'.")

            # Flags are managed by _add_flag and _remove_flag, so we don't re-parse them here
            current_entity.info = self.info_text.get(1.0, tk.END).strip()

            self.unsaved_changes = True
            self._update_entity_listbox() # Update listbox to reflect name change if any
            # Re-select the entity to keep the UI consistent
            self.entity_listbox.selection_clear(0, tk.END)
            self.entity_listbox.selection_set(self.selected_entity_index)
            messagebox.showinfo("Changes Applied", "Entity details have been updated.")

        except ValueError as ve:
            messagebox.showerror("Input Error", f"Invalid input: {ve}")
        except Exception as e:
            messagebox.showerror("Error", f"An unexpected error occurred: {e}")

    def _add_flag(self):
        if self.selected_entity_index is None:
            messagebox.showwarning("No Entity Selected", "Please select an entity first.")
            return

        new_flag = self.new_flag_entry.get().strip()
        if new_flag:
            if new_flag not in self.entities[self.selected_entity_index].flags:
                self.entities[self.selected_entity_index].flags.append(new_flag)
                self.flags_listbox.insert(tk.END, new_flag)
                self.new_flag_entry.delete(0, tk.END)
                self.unsaved_changes = True
            else:
                messagebox.showinfo("Duplicate Flag", f"Flag '{new_flag}' already exists for this entity.")
        else:
            messagebox.showwarning("Empty Flag", "Flag name cannot be empty.")

    def _remove_flag(self):
        if self.selected_entity_index is None:
            messagebox.showwarning("No Entity Selected", "Please select an entity first.")
            return

        selected_flag_indices = self.flags_listbox.curselection()
        if not selected_flag_indices:
            messagebox.showwarning("No Flag Selected", "Please select a flag to remove.")
            return

        flag_to_remove = self.flags_listbox.get(selected_flag_indices[0])
        if flag_to_remove in self.entities[self.selected_entity_index].flags:
            self.entities[self.selected_entity_index].flags.remove(flag_to_remove)
            self.flags_listbox.delete(selected_flag_indices[0])
            self.unsaved_changes = True
        else:
            # This case should ideally not happen if the listbox and entity data are in sync
            messagebox.showerror("Error", "Selected flag not found in entity's data.")

    def _on_flag_right_click(self, event):
        # Clear previous selections
        self.flags_listbox.selection_clear(0, tk.END)
        # Get the index of the item clicked
        index = self.flags_listbox.nearest(event.y)
        # Select the item
        self.flags_listbox.selection_set(index)
        # Set the active (highlighted) item to the clicked one
        self.flags_listbox.activate(index)


    def _on_exit(self):
        if self.unsaved_changes:
            if messagebox.askyesno("Unsaved Changes", "You have unsaved changes. Do you want to exit without saving?"):
                self.master.destroy()
        else:
            self.master.destroy()

if __name__ == "__main__":
    root = tk.Tk()
    app = EntityEditorApp(root)
    root.protocol("WM_DELETE_WINDOW", app._on_exit)
    root.mainloop()
