"""Rap Writer: a Windows desktop notebook for melodic rap and catchy hooks."""
from __future__ import annotations

import json
import os
from pathlib import Path
import queue
import sys
import threading
from copy import deepcopy
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

from lyric_engine import (
    DEFAULT_BLOCKED_WORDS, DEFAULT_MODEL, DEFAULT_SONG_STRUCTURE, LyricRequest,
    GenerationError, GenerationCancelled, ValidationError,
    blocked_hits, missing_good_words, lyric_body, validate_request, generate_lyrics,
    song_structure_issues,
)
from song_structure import SongStructureError, parse_song_structure, validate_song_structure
from idea_engine import IDEA_CHOICES, generate_idea, validate_idea

APP_DIR = Path(__file__).resolve().parent
BG = '#101a20'
PANEL = '#192630'
FIELD = '#263842'
INK = '#edf4f5'
MUTED = '#adc0cc'
ACCENT = '#6ee7c0'
GREEN = '#a8d5b2'
RED = '#ff9393'


def default_settings_path():
    folder = Path.home() / 'Documents' / 'Rap Writer' if getattr(sys, 'frozen', False) else APP_DIR
    return folder / 'settings.json'


def environment_key():
    key = os.environ.get('OPENAI_API_KEY', '').strip()
    if key:
        return key
    if os.name == 'nt':
        import winreg
        for hive, path in ((winreg.HKEY_CURRENT_USER, 'Environment'),
                           (winreg.HKEY_LOCAL_MACHINE, r'SYSTEM\CurrentControlSet\Control\Session Manager\Environment')):
            try:
                with winreg.OpenKey(hive, path) as entry:
                    value, _ = winreg.QueryValueEx(entry, 'OPENAI_API_KEY')
                    if isinstance(value, str) and value.strip():
                        return value.strip()
            except OSError:
                pass
    return ''


class RapWriter(tk.Tk):
    def __init__(self, settings_path=None):
        super().__init__()
        self.title('Rap Writer · Song JSON')
        self.geometry('1220x880')
        self.minsize(1040, 740)
        self.configure(bg=BG)
        self.option_add('*Font', ('Segoe UI', 10))
        self.settings_path = Path(settings_path) if settings_path else default_settings_path()
        self.api_key = environment_key()
        self.events = queue.Queue()
        self.cancel_event = threading.Event()
        self.busy = False
        self.closed = False
        self.active_id = 0
        self.dirty = False
        self.exported_text = ''
        self.fields = {}
        self.last_result = None
        self._form_states = []
        self.custom_sections = list(DEFAULT_SONG_STRUCTURE)
        self.song_structure = None
        self._song_structure_error = ''
        self._active_request = None
        self._draft_map_changed = False
        self._active_job_kind = None
        self._idea_pending_snapshot = None
        self._idea_undo_snapshot = None
        self._recent_ideas = []
        self._applying_idea = False
        self._styles()
        self._build()
        self._load_settings()
        self._refresh_connection()
        self.protocol('WM_DELETE_WINDOW', self._close)
        self.bind('<Control-Return>', lambda e: self.start_generation())
        self.bind('<Control-s>', lambda e: self.save_lyrics())
        self.after(120, self._poll)
        self.after(200, self._update_gate)

    def _styles(self):
        style = ttk.Style(self)
        style.theme_use('clam')
        style.configure('TCombobox', fieldbackground=FIELD, background=FIELD,
                        foreground=INK, arrowcolor=INK, padding=5, borderwidth=0)
        style.map('TCombobox', fieldbackground=[('readonly', FIELD)],
                  foreground=[('readonly', INK)], selectbackground=[('readonly', FIELD)],
                  selectforeground=[('readonly', INK)])
        style.configure('Vertical.TScrollbar', background='#40454b', troughcolor=PANEL,
                        borderwidth=0, arrowcolor=MUTED)
        style.configure('Rap.Horizontal.TProgressbar', background=ACCENT,
                        troughcolor=FIELD, borderwidth=0, thickness=3)

    def label(self, parent, text, size=10, color=INK, bold=False, **kwargs):
        return tk.Label(parent, text=text, bg=parent.cget('bg'), fg=color,
                        font=('Segoe UI', size, 'bold' if bold else 'normal'),
                        anchor='w', **kwargs)

    def button(self, parent, text, command, primary=False):
        return tk.Button(parent, text=text, command=command, relief='flat', bd=0,
                         bg=ACCENT if primary else FIELD, fg=BG if primary else INK,
                         activebackground='#97efd3' if primary else '#354b58',
                         activeforeground=BG if primary else INK,
                         disabledforeground='#777b80', cursor='hand2',
                         padx=15, pady=9, font=('Segoe UI', 10, 'bold'))

    def text_field(self, parent, name, height=3):
        frame = tk.Frame(parent, bg=FIELD)
        box = tk.Text(frame, height=height, bg=FIELD, fg=INK, insertbackground=ACCENT,
                      selectbackground='#315d58', relief='flat', bd=0, wrap='word',
                      padx=10, pady=6, undo=True, font=('Segoe UI', 10))
        scrollbar = ttk.Scrollbar(frame, orient='vertical', command=box.yview)
        box.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side='right', fill='y')
        box.pack(side='left', fill='both', expand=True)
        frame.pack(fill='x', pady=(4, 8))
        self.fields[name] = box
        return box

    def _build(self):
        header = tk.Frame(self, bg=BG, padx=26, pady=14)
        header.pack(fill='x')
        brand_row = tk.Frame(header, bg=BG)
        brand_row.pack(fill='x')
        left_title = tk.Frame(brand_row, bg=BG)
        left_title.pack(side='left')
        self.label(left_title, 'RAP WRITER', 22, bold=True).pack(anchor='w')
        self.label(left_title, 'Melodic flows. Hooks that stay with you.', 10, MUTED).pack(anchor='w', pady=(3, 0))
        self.connection_btn = self.button(brand_row, 'Connection', self.connection_dialog)
        self.connection_btn.pack(side='right')
        self.connection_label = self.label(brand_row, '', 9, MUTED)
        self.connection_label.pack(side='right', padx=14)
        idea_row = tk.Frame(header, bg=BG)
        idea_row.pack(fill='x', pady=(10, 0))
        self.idea_btn = self.button(idea_row, 'AI Ideas', self.start_idea_generation, True)
        self.idea_btn.pack(side='right')
        self.undo_idea_btn = self.button(idea_row, 'Undo idea', self.undo_idea)
        self.undo_idea_btn.configure(state='disabled')
        self.undo_idea_btn.pack(side='right', padx=(8, 8))
        self.load_song_btn = self.button(idea_row, 'Load song JSON…', self.load_song_structure)
        self.load_song_btn.pack(side='left')
        self.label(idea_row, 'Fills the brief and direction using your connection.', 9, MUTED,
                   wraplength=410, justify='left').pack(side='left', padx=14, fill='x', expand=True)

        main = tk.Frame(self, bg=BG, padx=24)
        main.pack(fill='both', expand=True)
        main.columnconfigure(0, weight=0, minsize=400)
        main.columnconfigure(1, weight=1)
        main.rowconfigure(0, weight=1)

        sidebar = tk.Frame(main, bg=PANEL, width=410)
        self.sidebar = sidebar
        sidebar.grid(row=0, column=0, sticky='nsew', padx=(0, 18))
        sidebar.grid_propagate(False)
        sidebar.rowconfigure(0, weight=1)
        sidebar.columnconfigure(0, weight=1)
        canvas = tk.Canvas(sidebar, bg=PANEL, highlightthickness=0, width=390)
        self.form_canvas = canvas
        side_scroll = ttk.Scrollbar(sidebar, orient='vertical', command=canvas.yview)
        canvas.configure(yscrollcommand=side_scroll.set)
        canvas.grid(row=0, column=0, sticky='nsew')
        side_scroll.grid(row=0, column=1, sticky='ns')
        form = tk.Frame(canvas, bg=PANEL, padx=18, pady=16)
        form_window = canvas.create_window(0, 0, window=form, anchor='nw')
        form.bind('<Configure>', lambda e: canvas.configure(scrollregion=canvas.bbox('all')))
        canvas.bind('<Configure>', lambda e: canvas.itemconfigure(form_window, width=e.width))
        def scroll_form(event):
            widget = event.widget
            if isinstance(widget, tk.Text):
                return
            if str(widget).startswith(str(sidebar)):
                canvas.yview_scroll(int(-event.delta / 120), 'units')
        self.bind_all('<MouseWheel>', scroll_form, add='+')

        self.label(form, '01  /  THE BRIEF', 10, ACCENT, True).pack(anchor='w', pady=(0, 7))
        self.label(form, 'What do you want to say?', bold=True).pack(anchor='w')
        self.text_field(form, 'topic', 2)
        self.label(form, 'Real details + your own voice', bold=True).pack(anchor='w')
        self.label(form, 'A late drive, an unread text, a win that cost you.', 9, MUTED).pack(anchor='w')
        self.text_field(form, 'details', 2)
        self.label(form, 'Title or hook phrase (optional)', bold=True).pack(anchor='w')
        self.label(form, 'A short phrase people can sing back.', 9, MUTED).pack(anchor='w')
        self.text_field(form, 'hook_note', 1)

        options = tk.Frame(form, bg=PANEL)
        options.pack(fill='x', pady=(0, 10))
        options.columnconfigure(0, weight=1)
        options.columnconfigure(1, weight=1)
        self.style_var = tk.StringVar(value='Melodic rap')
        self.mood_var = tk.StringVar(value='Reflective / hopeful')
        self.structure_var = tk.StringVar(value='Full song')
        self.phrasing_var = tk.StringVar(value='Melodic / pocketed')
        self.rhyme_var = tk.StringVar(value='Internal + end rhymes')
        self.dynamics_var = tk.StringVar(value='Rapped verses / sung hook')
        self.imagery_var = tk.StringVar(value='Concrete / personal')
        option_rows = [
            [('Style', self.style_var, IDEA_CHOICES['style']),
             ('Mood', self.mood_var, IDEA_CHOICES['mood'])],
            [('Flow', self.phrasing_var, IDEA_CHOICES['phrasing']),
             ('Rhymes', self.rhyme_var, IDEA_CHOICES['rhyme_style'])],
            [('Imagery', self.imagery_var, IDEA_CHOICES['imagery'])],
        ]
        for row, option_row in enumerate(option_rows):
            for column, (title, variable, choices) in enumerate(option_row):
                self.label(options, title, 9, MUTED).grid(row=row * 2, column=column, sticky='w')
                ttk.Combobox(options, textvariable=variable, values=choices, state='readonly', width=18).grid(
                    row=row * 2 + 1, column=column, sticky='ew',
                    padx=(0, 8) if column == 0 else (0, 0), pady=(4, 8))
        self.label(options, 'Length', 9, MUTED).grid(row=4, column=1, sticky='w')
        self.structure_box = ttk.Combobox(options, textvariable=self.structure_var, state='readonly', width=18,
                     values=['4-line hook', '8-line hook', '8 lines', '16 lines', '24 lines', '32 lines', 'Full song', 'Custom arrangement'])
        self.structure_box.grid(row=5, column=1, sticky='ew', pady=(4, 8))
        self.label(options, 'Delivery', 9, MUTED).grid(row=6, column=0, columnspan=2, sticky='w')
        ttk.Combobox(options, textvariable=self.dynamics_var, state='readonly', width=36,
                     values=IDEA_CHOICES['dynamics']).grid(
            row=7, column=0, columnspan=2, sticky='ew', pady=(4, 8))
        self.explicit_var = tk.BooleanVar(value=True)
        tk.Checkbutton(options, text='Swearing is fine', variable=self.explicit_var, bg=PANEL,
                       fg=INK, selectcolor=FIELD, activebackground=PANEL, activeforeground=INK,
                       highlightthickness=0).grid(row=8, column=0, columnspan=2, sticky='w')
        self.arrange_btn = self.button(options, 'Song structure…', self.structure_dialog)
        self.arrange_btn.grid(row=9, column=0, columnspan=2, sticky='ew', pady=(10, 0))
        self.clear_song_btn = self.button(options, 'Clear imported song map', self.clear_song_structure)
        self.clear_song_btn.grid(row=10, column=0, columnspan=2, sticky='ew', pady=(6, 0))
        self.clear_song_btn.configure(state='disabled')
        self.song_summary = tk.StringVar(value='Load Song Structure.json from your MIDI arrangement. Musical bars and lyric lines stay separate.')
        self.label(options, '', 9, MUTED, textvariable=self.song_summary, wraplength=340, justify='left').grid(
            row=11, column=0, columnspan=2, sticky='ew', pady=(6, 0))

        self.label(form, '02  /  YOUR WORDS', 10, ACCENT, True).pack(anchor='w', pady=(8, 6))
        self.label(form, 'Blocked words', bold=True).pack(anchor='w')
        self.label(form, 'Never in the result. Separate with commas or new lines.', 9, MUTED).pack(anchor='w')
        blocked = self.text_field(form, 'blocked_words', 2)
        blocked.insert('1.0', DEFAULT_BLOCKED_WORDS)
        blocked.bind('<<Modified>>', self._rules_modified)
        good_heading = tk.Frame(form, bg=PANEL)
        good_heading.pack(fill='x')
        self.label(good_heading, 'Wanted words', bold=True).pack(side='left')
        self.require_var = tk.BooleanVar(value=False)
        tk.Checkbutton(good_heading, text='Require all', variable=self.require_var,
                       command=self._update_gate, bg=PANEL, fg=INK, selectcolor=FIELD,
                       activebackground=PANEL, activeforeground=INK, highlightthickness=0).pack(side='right')
        self.label(form, 'Words / phrases to weave in. Commas or new lines.', 9, MUTED).pack(anchor='w')
        good = self.text_field(form, 'good_words', 2)
        good.bind('<<Modified>>', self._rules_modified)

        action_frame = tk.Frame(sidebar, bg=PANEL, padx=18, pady=10)
        action_frame.grid(row=1, column=0, columnspan=2, sticky='ew')
        self.generate_btn = self.button(action_frame, 'Write my lyrics', self.start_generation, True)
        self.generate_btn.pack(side='left', fill='x', expand=True)
        self.cancel_btn = self.button(action_frame, 'Stop', self.cancel_generation)
        self.cancel_btn.configure(state='disabled')
        self.cancel_btn.pack(side='left', padx=(8, 0))

        notebook = tk.Frame(main, bg=PANEL, padx=22, pady=18)
        notebook.grid(row=0, column=1, sticky='nsew')
        notebook.columnconfigure(0, weight=1)
        notebook.rowconfigure(2, weight=1)
        top = tk.Frame(notebook, bg=PANEL)
        top.grid(row=0, column=0, sticky='ew')
        self.label(top, 'YOUR SONG', 11, ACCENT, True).pack(side='left')
        self.count_label = self.label(top, '0 lines', 9, MUTED)
        self.count_label.pack(side='right')
        self.gate_label = self.label(notebook, 'Write lyrics or paste a draft here to rework it.', 9, MUTED)
        self.gate_label.grid(row=1, column=0, sticky='ew', pady=(6, 12))
        editor_frame = tk.Frame(notebook, bg=PANEL)
        editor_frame.grid(row=2, column=0, sticky='nsew')
        self.editor = tk.Text(editor_frame, bg=PANEL, fg=INK, insertbackground=ACCENT, height=1, width=1,
                              relief='flat', bd=0, wrap='word', undo=True, padx=0, pady=8,
                              font=('Segoe UI', 13), spacing1=3, spacing3=5,
                              selectbackground='#315d58')
        edit_scroll = ttk.Scrollbar(editor_frame, orient='vertical', command=self.editor.yview)
        self.editor.configure(yscrollcommand=edit_scroll.set)
        edit_scroll.pack(side='right', fill='y')
        self.editor.pack(side='left', fill='both', expand=True)
        self.editor.bind('<<Modified>>', self._editor_modified)
        self.editor.bind('<Control-c>', self._copy_selection)
        self.editor.bind('<Control-C>', self._copy_selection)
        self.editor.bind('<<Copy>>', self._copy_selection)
        self.editor.bind('<<Cut>>', self._cut_selection)
        self.editor.bind('<Control-x>', self._cut_selection)
        self.editor.bind('<Control-X>', self._cut_selection)
        self.label(notebook, 'What should the rewrite change?', 10, INK, True).grid(
            row=3, column=0, sticky='w', pady=(12, 4))
        revision_frame = tk.Frame(notebook, bg=FIELD)
        revision_frame.grid(row=4, column=0, sticky='ew')
        self.revision = tk.Text(revision_frame, height=2, bg=FIELD, fg=INK,
                                insertbackground=ACCENT, relief='flat', padx=10, pady=8,
                                wrap='word', font=('Segoe UI', 10))
        self.revision.pack(fill='x')
        tools = tk.Frame(notebook, bg=PANEL)
        tools.grid(row=5, column=0, sticky='ew', pady=(12, 0))
        self.rewrite_btn = self.button(tools, 'Rewrite lyrics', lambda: self.start_generation(True))
        self.rewrite_btn.pack(side='left')
        self.undo_btn = self.button(tools, 'Undo', self.undo_edit)
        self.undo_btn.pack(side='left', padx=(8, 0))
        self.copy_btn = self.button(tools, 'Copy', self.copy_lyrics)
        self.copy_btn.pack(side='right', padx=(8, 0))
        self.save_btn = self.button(tools, 'Save .txt', self.save_lyrics)
        self.save_btn.pack(side='right')

        footer = tk.Frame(self, bg=BG, padx=26, pady=14)
        footer.pack(side='bottom', fill='x', before=main)
        self.status_var = tk.StringVar(value='Ready. Start with a real moment and a hook worth repeating.')
        self.status_label = tk.Label(footer, textvariable=self.status_var, bg=BG, fg=MUTED, anchor='w')
        self.status_label.pack(fill='x')
        self.progressbar = ttk.Progressbar(footer, mode='indeterminate', style='Rap.Horizontal.TProgressbar')
        self.progressbar.pack(fill='x', pady=(8, 0))

    def value(self, name):
        return self.fields[name].get('1.0', 'end-1c').strip()

    def lyrics(self):
        return self.editor.get('1.0', 'end-1c').strip()

    def request(self, rewrite=False):
        if self._song_structure_error:
            raise ValidationError(self._song_structure_error)
        return LyricRequest(topic=self.value('topic'), details=self.value('details'),
                            style=self.style_var.get(), mood=self.mood_var.get(),
                            phrasing=self.phrasing_var.get(), rhyme_style=self.rhyme_var.get(),
                            dynamics=self.dynamics_var.get(), imagery=self.imagery_var.get(),
                            hook_note=self.value('hook_note'),
                            structure=self.structure_text(), explicit=self.explicit_var.get(),
                            blocked_words=self.value('blocked_words'), good_words=self.value('good_words'),
                            require_good_words=self.require_var.get(), model=self.model_var.get(),
                            existing_lyrics=self.lyrics() if rewrite else '',
                            revision_note=self.revision.get('1.0', 'end-1c').strip() if rewrite else '',
                            song_structure=deepcopy(self.song_structure))

    def structure_text(self):
        if self.song_structure is not None:
            return 'Full song'
        if self.structure_var.get() == 'Custom arrangement':
            return '\n'.join(f'{name}: {lines}' for name, lines in self.custom_sections)
        return self.structure_var.get()

    def structure_dialog(self):
        if self.busy:
            return
        if self.song_structure is not None:
            return self.song_map_dialog()
        dialog = tk.Toplevel(self)
        dialog.title('Rap Writer — Song structure')
        dialog.configure(bg=PANEL, padx=24, pady=22)
        dialog.geometry('630x640')
        dialog.minsize(590, 600)
        dialog.transient(self)
        sections = list(self.custom_sections)
        self.label(dialog, 'Build your song', 20, INK, True).pack(anchor='w')
        self.label(dialog, 'Set the sections, their order, and how many lyric lines each gets.', 10, MUTED).pack(anchor='w', pady=(6, 15))
        presets = tk.Frame(dialog, bg=PANEL)
        presets.pack(fill='x', pady=(0, 12))
        def preset(entries):
            sections[:] = entries
            refresh(0)
        self.button(presets, 'Verse + hook', lambda: preset([('Verse 1', 16), ('Hook', 8)])).pack(side='left')
        self.button(presets, 'Full song', lambda: preset(list(DEFAULT_SONG_STRUCTURE))).pack(side='left', padx=8)
        self.button(presets, 'One verse', lambda: preset([('Verse', 16)])).pack(side='left')
        listing = tk.Frame(dialog, bg=PANEL)
        listing.pack(fill='both', expand=True)
        song_list = tk.Listbox(listing, bg=FIELD, fg=INK, selectbackground='#315d58', height=6,
                              selectforeground=INK, relief='flat', bd=0,
                              font=('Segoe UI', 12), activestyle='none', exportselection=False)
        scroll = ttk.Scrollbar(listing, orient='vertical', command=song_list.yview)
        song_list.configure(yscrollcommand=scroll.set)
        scroll.pack(side='right', fill='y')
        song_list.pack(side='left', fill='both', expand=True)
        summary = self.label(dialog, '', 10, ACCENT)
        summary.pack(anchor='w', pady=(8, 10))
        edits = tk.Frame(dialog, bg=PANEL)
        edits.pack(fill='x')
        edits.columnconfigure(0, weight=1)
        self.label(edits, 'Section name', 9, MUTED).grid(row=0, column=0, sticky='w')
        self.label(edits, 'Lyric lines', 9, MUTED).grid(row=0, column=1, sticky='w', padx=(10, 0))
        name_var = tk.StringVar(value='Verse')
        lines_var = tk.StringVar(value='16')
        ttk.Combobox(edits, textvariable=name_var, values=['Intro', 'Hook', 'Verse 1', 'Verse 2', 'Pre-hook', 'Post-hook', 'Bridge', 'Final hook', 'Outro']).grid(row=1, column=0, sticky='ew', pady=(5, 0))
        tk.Spinbox(edits, from_=1, to=64, textvariable=lines_var, width=7, bg=FIELD, fg=INK,
                   buttonbackground=FIELD, insertbackground=ACCENT, relief='flat').grid(row=1, column=1, padx=(10, 0), pady=(5, 0), ipady=7)
        def selected():
            selection = song_list.curselection()
            return selection[0] if selection else None
        def select(event=None):
            index = selected()
            if index is not None:
                name_var.set(sections[index][0])
                lines_var.set(str(sections[index][1]))
        def refresh(index=None):
            song_list.delete(0, 'end')
            for n, (name, lines) in enumerate(sections, 1):
                song_list.insert('end', f'  {n:02d}    {name}    /    {lines} lyric lines')
            total = sum(lines for _, lines in sections)
            summary.configure(text=f'{len(sections)} sections  /  {total} lines total', fg=RED if total > 160 else ACCENT)
            if sections and index is not None:
                song_list.selection_set(min(index, len(sections) - 1))
                select()
        def get_entry():
            name = name_var.get().strip()
            try:
                lines = int(lines_var.get())
            except ValueError:
                lines = 0
            if not name or len(name) > 40 or any(c in name for c in ':[]\r\n'):
                messagebox.showinfo('Section name', 'Use a section name of 1–40 characters, without colons or brackets.', parent=dialog)
                return None
            if not 1 <= lines <= 64:
                messagebox.showinfo('Lines', 'Choose between 1 and 64 lyric lines for this section.', parent=dialog)
                return None
            return name, lines
        def add():
            entry = get_entry()
            if entry:
                if len(sections) >= 12:
                    messagebox.showinfo('Song length', 'Use up to 12 sections.', parent=dialog)
                    return
                sections.append(entry)
                refresh(len(sections) - 1)
        def update():
            index = selected()
            entry = get_entry()
            if index is not None and entry:
                sections[index] = entry
                refresh(index)
        def remove():
            index = selected()
            if index is not None:
                sections.pop(index)
                refresh(index)
        def move(direction):
            index = selected()
            if index is not None and 0 <= index + direction < len(sections):
                sections[index], sections[index + direction] = sections[index + direction], sections[index]
                refresh(index + direction)
        controls = tk.Frame(dialog, bg=PANEL)
        controls.pack(fill='x', pady=(12, 10))
        for title, action in [('Add', add), ('Update', update), ('Remove', remove), ('↑', lambda: move(-1)), ('↓', lambda: move(1))]:
            self.button(controls, title, action).pack(side='left', padx=(0, 7))
        self.label(dialog, 'Count rapped or sung lines, not musical bars. Up to 12 sections / 160 lines.', 9, MUTED).pack(anchor='w')
        self.label(dialog, 'Repeat hooks freely. Generated section order and line counts are checked.', 9, MUTED).pack(anchor='w', pady=(3, 0))
        def apply():
            index = selected()
            if index is not None:
                entry = get_entry()
                if entry is None:
                    return
                sections[index] = entry
            if not sections or sum(lines for _, lines in sections) > 160:
                messagebox.showinfo('Song length', 'Add at least one section and keep the total at 160 lines or fewer.', parent=dialog)
                return
            from lyric_engine import parse_structure
            structure = '\n'.join(f'{name}: {lines}' for name, lines in sections)
            try:
                parse_structure(structure)
                for name, _ in sections:
                    if blocked_hits(name, self.value('blocked_words')):
                        raise ValidationError('A section name uses a blocked word. Rename it before continuing.')
            except ValidationError as error:
                messagebox.showinfo('Check this structure', str(error), parent=dialog)
                return
            self.custom_sections = list(sections)
            self.structure_var.set('Custom arrangement')
            self.arrange_btn.configure(text=f'Song structure…  ({len(sections)} sections)')
            self._save_settings()
            dialog.destroy()
        self.button(dialog, 'Use this structure', apply, True).pack(fill='x', pady=(18, 0))
        song_list.bind('<<ListboxSelect>>', select)
        refresh(0)
        dialog.grab_set()

    @staticmethod
    def _time_label(seconds):
        value = round(seconds)
        return f'{value // 60}:{value % 60:02d}'

    def _sync_song_ui(self):
        active = self.song_structure is not None or bool(self._song_structure_error)
        self.structure_box.configure(state='disabled' if active or self.busy else 'readonly')
        self.clear_song_btn.configure(state='normal' if active and not self.busy else 'disabled')
        if self.song_structure is not None:
            song = self.song_structure
            lines = sum(section['suggested_lines'] for section in song['sections'])
            self.arrange_btn.configure(text=f"View song map…  ({len(song['sections'])} sections)")
            self.song_summary.set(f"{song['title']}\n{song['total_bars']} musical bars · {self._time_label(song['duration_seconds'])} · {lines} lyric lines")
        elif self._song_structure_error:
            self.arrange_btn.configure(text='Song structure…')
            self.song_summary.set('Saved song map needs attention. Load its JSON again or clear the imported map.')
        else:
            self.arrange_btn.configure(text='Song structure…')
            self.song_summary.set('Load Song Structure.json from your MIDI arrangement. Musical bars and lyric lines stay separate.')

    def _apply_song_structure(self, song, save=True):
        if self.busy:
            return False
        validated = validate_song_structure(song) if song is not None else None
        self.song_structure = validated
        self._song_structure_error = ''
        self._active_request = None
        self.last_result = None
        self._draft_map_changed = bool(self.lyrics())
        self._sync_song_ui()
        self._update_gate()
        if save:
            self._save_settings()
        self.status_var.set('Song map loaded. Lyrics will follow its sections, timing and vocal line counts.'
                            if validated is not None else 'Imported song map cleared. Your selected lyric structure is active.')
        return True

    def load_song_structure(self, path=None):
        if self.busy:
            return False
        if path is None:
            path = filedialog.askopenfilename(parent=self, title='Load the MIDI song structure JSON',
                                             filetypes=[('Song structure JSON', '*.json'), ('All files', '*.*')])
        if not path:
            return False
        try:
            source = Path(path)
            if source.stat().st_size > 1_000_000:
                raise SongStructureError('Choose a song JSON file smaller than 1 MB.')
            song = parse_song_structure(source.read_text(encoding='utf-8-sig'))
        except (OSError, UnicodeError, SongStructureError) as error:
            messagebox.showerror('Could not load song JSON', str(error), parent=self)
            return False
        return self._apply_song_structure(song)

    def clear_song_structure(self):
        return self._apply_song_structure(None)

    def song_map_dialog(self):
        if self.busy or self.song_structure is None:
            return
        song = deepcopy(self.song_structure)
        dialog = tk.Toplevel(self)
        dialog.title('Song map · Musical bars and lyric lines')
        dialog.configure(bg=PANEL, padx=20, pady=18)
        dialog.geometry('790x630')
        dialog.minsize(700, 560)
        dialog.transient(self)
        self.label(dialog, song['title'], 18, INK, True, wraplength=720).pack(anchor='w')
        self.label(dialog, f"{song['total_bars']} musical bars · {self._time_label(song['duration_seconds'])} · 4/4", 10, ACCENT).pack(anchor='w', pady=(4, 5))
        self.label(dialog, 'Keep the music map. Set rapped or sung lyric lines per section; instrumental sections use 0.', 9, MUTED, wraplength=650).pack(anchor='w', pady=(0, 10))
        footer = tk.Frame(dialog, bg=PANEL)
        footer.pack(side='bottom', fill='x', pady=(12, 0))
        controls = tk.Frame(dialog, bg=PANEL)
        controls.pack(side='bottom', fill='x', pady=(10, 0))
        self.label(controls, 'Selected section').pack(side='left')
        mode = tk.StringVar(value='lyrics')
        count = tk.StringVar(value='4')
        mode_box = ttk.Combobox(controls, textvariable=mode, values=('lyrics', 'instrumental'), state='readonly', width=13)
        mode_box.pack(side='left', padx=10)
        self.label(controls, 'Lyric lines').pack(side='left')
        count_box = tk.Spinbox(controls, from_=0, to=64, textvariable=count, width=5, bg=FIELD, fg=INK,
                               buttonbackground=FIELD, insertbackground=ACCENT, relief='flat')
        count_box.pack(side='left', padx=8, ipady=7)
        detail = self.label(dialog, '', 9, MUTED, wraplength=650, justify='left', height=5)
        detail.pack(side='bottom', fill='x', pady=(8, 0))
        listing = tk.Frame(dialog, bg=PANEL)
        listing.pack(fill='both', expand=True)
        table = ttk.Treeview(listing, columns=('name', 'bars', 'time', 'mode', 'lines'), show='headings', height=8, selectmode='browse')
        for key, title, width in [('name', 'Section', 180), ('bars', 'Bars', 75), ('time', 'Time', 100), ('mode', 'Vocals', 95), ('lines', 'Lines', 50)]:
            table.heading(key, text=title)
            table.column(key, width=width, minwidth=45)
        scroll = ttk.Scrollbar(listing, orient='vertical', command=table.yview)
        scroll.pack(side='right', fill='y')
        table.configure(yscrollcommand=scroll.set)
        table.pack(side='left', fill='both', expand=True)

        def refresh():
            for index, section in enumerate(song['sections']):
                values = (section['name'], f"{section['start_bar']}–{section['end_bar']}",
                          f"{self._time_label(section['start_seconds'])}–{self._time_label(section['end_seconds'])}",
                          section['vocal_mode'], section['suggested_lines'])
                if table.exists(str(index)):
                    table.item(str(index), values=values)
                else:
                    table.insert('', 'end', iid=str(index), values=values)

        def choose(event=None):
            selected = table.selection()
            if selected:
                section = song['sections'][int(selected[0])]
                mode.set(section['vocal_mode'])
                count.set(str(section['suggested_lines']))
                count_box.configure(state='disabled' if mode.get() == 'instrumental' else 'normal')
                detail.configure(text=f"{section['bars']} musical bars at {section['bpm']:g} BPM · {section['pattern']}\n{section['notes']}\nInstruments: {', '.join(section['instruments']) or 'None'}")

        def mode_changed(event=None):
            count_box.configure(state='disabled' if mode.get() == 'instrumental' else 'normal')
            if mode.get() == 'instrumental':
                count.set('0')
            elif not count.get().isdigit() or int(count.get()) < 1:
                count.set('4')

        def update_selected():
            selected = table.selection()
            if not selected:
                return True
            candidate = deepcopy(song)
            section = candidate['sections'][int(selected[0])]
            try:
                section['vocal_mode'] = mode.get()
                section['suggested_lines'] = 0 if mode.get() == 'instrumental' else int(count.get())
                candidate = validate_song_structure(candidate)
            except (ValueError, SongStructureError) as error:
                messagebox.showinfo('Check lyric lines', str(error), parent=dialog)
                return False
            song.clear()
            song.update(candidate)
            refresh()
            choose()
            return True

        def apply():
            if update_selected() and self._apply_song_structure(song):
                dialog.destroy()

        self.button(controls, 'Apply section', update_selected).pack(side='right')
        self.button(footer, 'Use this song map', apply, True).pack(side='right')
        self.label(footer, 'Up to 160 lyric lines total. Musical bars stay unchanged.', 9, MUTED, wraplength=360).pack(side='left')
        table.bind('<<TreeviewSelect>>', choose)
        mode_box.bind('<<ComboboxSelected>>', mode_changed)
        refresh()
        table.selection_set('0')
        choose()
        dialog.grab_set()
        return dialog

    def _load_settings(self):
        self.model_var = tk.StringVar(value=DEFAULT_MODEL)
        try:
            data = json.loads(self.settings_path.read_text(encoding='utf-8'))
            if not isinstance(data, dict):
                return
            for name, field in self.fields.items():
                if isinstance(data.get(name), str):
                    field.delete('1.0', 'end')
                    field.insert('1.0', data[name])
            for name, var in [('style', self.style_var), ('mood', self.mood_var),
                              ('structure', self.structure_var), ('model', self.model_var),
                              ('phrasing', self.phrasing_var), ('rhyme_style', self.rhyme_var),
                              ('dynamics', self.dynamics_var), ('imagery', self.imagery_var)]:
                if isinstance(data.get(name), str):
                    var.set(data[name])
            if isinstance(data.get('explicit'), bool):
                self.explicit_var.set(data['explicit'])
            if isinstance(data.get('require_good_words'), bool):
                self.require_var.set(data['require_good_words'])
            sections = data.get('custom_sections')
            if isinstance(sections, list) and 1 <= len(sections) <= 12:
                valid = all(isinstance(s, list) and len(s) == 2 and isinstance(s[0], str)
                            and isinstance(s[1], int) and 1 <= s[1] <= 64 for s in sections)
                if valid and sum(s[1] for s in sections) <= 160:
                    self.custom_sections = [(s[0], s[1]) for s in sections]
            if data.get('song_structure') is not None:
                try:
                    self.song_structure = validate_song_structure(data['song_structure'])
                except SongStructureError:
                    self._song_structure_error = 'The saved song map is invalid. Load Song Structure.json again or clear the imported map.'
            elif data.get('song_structure_restore_error') is True:
                self._song_structure_error = 'The saved song map is invalid. Load Song Structure.json again or clear the imported map.'
        except (OSError, ValueError):
            pass
        self._sync_song_ui()

    def _save_settings(self):
        data = {name: self.value(name) for name in self.fields}
        data.update(style=self.style_var.get(), mood=self.mood_var.get(),
                    phrasing=self.phrasing_var.get(), rhyme_style=self.rhyme_var.get(),
                    dynamics=self.dynamics_var.get(), imagery=self.imagery_var.get(),
                    structure=self.structure_var.get(), explicit=self.explicit_var.get(),
                    require_good_words=self.require_var.get(), model=self.model_var.get())
        data['custom_sections'] = self.custom_sections
        try:
            data['song_structure'] = validate_song_structure(self.song_structure) if self.song_structure is not None else None
        except SongStructureError:
            data['song_structure'] = None
            self._song_structure_error = 'The song map is invalid. Load Song Structure.json again or clear the imported map.'
        data['song_structure_restore_error'] = bool(self._song_structure_error)
        try:
            self.settings_path.parent.mkdir(parents=True, exist_ok=True)
            temp = self.settings_path.with_suffix('.tmp')
            temp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding='utf-8')
            temp.replace(self.settings_path)
            return True
        except OSError:
            self.status_var.set('Your preferences could not be saved. You can still write lyrics.')
            return False

    def _refresh_connection(self):
        self.connection_label.configure(text='Key found  /  Uses paid API' if self.api_key
                                         else 'Add your API key to write', fg=GREEN if self.api_key else ACCENT)

    def connection_dialog(self):
        if self.busy:
            return
        dialog = tk.Toplevel(self)
        dialog.title('Rap Writer — Connection')
        dialog.configure(bg=PANEL, padx=24, pady=22)
        dialog.transient(self)
        dialog.resizable(False, False)
        self.label(dialog, 'Connection', 18, INK, True).pack(anchor='w')
        self.label(dialog, 'Writing sends your brief and lyrics to OpenAI. AI Ideas sends idea hints and word rules.', 10, MUTED,
                   wraplength=560, justify='left').pack(anchor='w', pady=(8, 3))
        self.label(dialog, 'Requires internet and API credit. API usage is billed separately.', 10, MUTED).pack(anchor='w')
        self.label(dialog, 'API key (only enter to replace the current key)', 10, INK, True).pack(anchor='w', pady=(20, 6))
        key_entry = tk.Entry(dialog, show='•', width=66, bg=FIELD, fg=INK, insertbackground=ACCENT, relief='flat')
        key_entry.pack(fill='x', ipady=8)
        self.label(dialog, 'Entered keys stay in memory for this session. They are never saved.', 9, MUTED).pack(anchor='w', pady=(5, 15))
        self.label(dialog, 'Model', 10, INK, True).pack(anchor='w', pady=(0, 5))
        model = tk.StringVar(value=self.model_var.get())
        ttk.Combobox(dialog, textvariable=model, values=[DEFAULT_MODEL, 'gpt-5-mini', 'gpt-4.1', 'gpt-4.1-mini', 'gpt-5.4-mini'], width=30).pack(anchor='w')
        self.label(dialog, 'Writing uses 2 requests, up to 4 if a draft needs repairs.', 9, MUTED).pack(anchor='w', pady=(15, 4))
        self.label(dialog, 'AI Ideas uses 1 request, up to 2 if an idea needs fixing.', 9, MUTED).pack(anchor='w', pady=(0, 4))
        self.label(dialog, 'Rap the verses and sing the hook aloud. Make the draft yours.', 9, MUTED).pack(anchor='w')
        actions = tk.Frame(dialog, bg=PANEL)
        actions.pack(fill='x', pady=(20, 0))
        def apply():
            if key_entry.get().strip():
                self.api_key = key_entry.get().strip()
            self.model_var.set(model.get().strip() or DEFAULT_MODEL)
            self._refresh_connection()
            self._save_settings()
            key_entry.delete(0, 'end')
            dialog.destroy()
        self.button(actions, 'Done', apply, True).pack(side='right')
        dialog.grab_set()

    def _rules_modified(self, event):
        if event.widget.edit_modified():
            event.widget.edit_modified(False)
            if self._applying_idea:
                return
            if hasattr(self, 'gate_label') and hasattr(self, 'require_var'):
                self._update_gate()

    def _editor_modified(self, event):
        if self.editor.edit_modified():
            self.editor.edit_modified(False)
            self.dirty = self.lyrics() != self.exported_text
            self._update_gate()

    def _gate_problem(self, text, check_structure=True):
        hits = sorted(set(blocked_hits(text, self.value('blocked_words')) +
                          blocked_hits(lyric_body(text), self.value('blocked_words'))))
        if hits:
            return 'Blocked words found: ' + ', '.join(hits[:8])
        if self.require_var.get():
            missing = missing_good_words(lyric_body(text), self.value('good_words'))
            if missing:
                return 'Required words missing: ' + ', '.join(missing[:8])
        if check_structure and self._song_structure_error:
            return self._song_structure_error
        if check_structure and self.song_structure is not None:
            try:
                issues = song_structure_issues(text, self.song_structure)
            except SongStructureError as error:
                return str(error)
            if issues:
                return issues[0]
        return ''

    def _update_gate(self):
        text = self.lyrics()
        count = len([line for line in lyric_body(text).splitlines() if line.strip()])
        self.count_label.configure(text=f'{count} lyric lines')
        problem = self._gate_problem(text) if text else ''
        if not text:
            label = 'Write lyrics or paste a draft here to rework it.'
        elif problem:
            label = problem
        elif self._draft_map_changed:
            label = 'Song map changed. Review or rewrite this draft for the new timing and sections.'
        else:
            label = 'Word rules passed  /  Try the flow aloud and make it yours.'
        self.gate_label.configure(text=label, fg=RED if problem else GREEN if text else MUTED,
                                  wraplength=max(400, self.editor.winfo_width() - 10))
        state = 'normal' if text and not problem and not self.busy else 'disabled'
        self.copy_btn.configure(state=state)
        self.save_btn.configure(state=state)

    def _idea_variables(self):
        return {'style': self.style_var, 'mood': self.mood_var,
                'phrasing': self.phrasing_var, 'rhyme_style': self.rhyme_var,
                'dynamics': self.dynamics_var, 'imagery': self.imagery_var}

    def _capture_idea_fields(self):
        values = {name: self.fields[name].get('1.0', 'end-1c')
                  for name in ('topic', 'details', 'hook_note', 'good_words')}
        values.update({name: variable.get() for name, variable in self._idea_variables().items()})
        return values

    def _apply_idea_fields(self, values):
        text_names = ('topic', 'details', 'hook_note', 'good_words')
        variables = self._idea_variables()
        names = text_names + tuple(variables)
        if any(not isinstance(values.get(name), str) for name in names):
            raise ValidationError('The idea did not contain every field. Your current brief is unchanged.')
        before = self._capture_idea_fields()

        def write(data):
            for name in text_names:
                field = self.fields[name]
                field.delete('1.0', 'end')
                field.insert('1.0', data[name])
                field.edit_modified(False)
            for name, variable in variables.items():
                variable.set(data[name])

        self._applying_idea = True
        try:
            write(values)
        except Exception:
            write(before)
            raise
        finally:
            self._applying_idea = False
        self._update_gate()

    def start_idea_generation(self):
        if self.busy:
            return
        if not self.api_key:
            self.status_var.set('Add a key in Connection to get a fresh AI idea for your brief.')
            self.connection_dialog()
            return
        snapshot = self._capture_idea_fields()
        # Ideas need only the creative brief and word rules, not a valid lyric or song map.
        request = LyricRequest(**snapshot, blocked_words=self.value('blocked_words'),
                               require_good_words=self.require_var.get(), explicit=self.explicit_var.get(),
                               model=self.model_var.get())
        recent = deepcopy(self._recent_ideas[-8:])
        self.active_id += 1
        job_id = self.active_id
        self.cancel_event = threading.Event()
        cancel = self.cancel_event
        key = self.api_key
        self._active_job_kind = 'idea'
        self._idea_pending_snapshot = snapshot
        self._set_busy(True)
        self.status_var.set('Finding a fresh topic, hook, and writing direction…')

        def worker():
            try:
                idea = generate_idea(request, key, recent_ideas=recent,
                                     progress=lambda text: self.events.put((job_id, 'progress', text)),
                                     cancel=cancel)
                self.events.put((job_id, 'idea', idea))
            except GenerationCancelled:
                self.events.put((job_id, 'cancelled', None))
            except (GenerationError, ValidationError) as error:
                self.events.put((job_id, 'error', str(error)))
            except Exception:
                self.events.put((job_id, 'error', 'The idea could not finish. Your current brief and lyrics are still here. Try again.'))

        try:
            threading.Thread(target=worker, daemon=True).start()
        except Exception:
            self._active_job_kind = None
            self._idea_pending_snapshot = None
            self._set_busy(False)
            self.status_var.set('The idea could not start. Your current brief and lyrics are still here. Try again.')

    def undo_idea(self):
        if self.busy or self._idea_undo_snapshot is None:
            return
        self._apply_idea_fields(self._idea_undo_snapshot)
        self._idea_undo_snapshot = None
        self.undo_idea_btn.configure(state='disabled')
        if self._save_settings():
            self.status_var.set('Previous brief restored. Your lyrics are unchanged.')

    def _finish_idea(self, payload):
        snapshot = self._idea_pending_snapshot
        self._idea_pending_snapshot = None
        self._active_job_kind = None
        self._set_busy(False)
        if self.cancel_event.is_set():
            self.status_var.set('Stopped. Your previous brief and lyrics are still here.')
            return
        if snapshot is None or self._capture_idea_fields() != snapshot:
            self.status_var.set('Your brief changed during the request. Click AI Ideas again for a fresh idea.')
            return
        try:
            idea = validate_idea(payload, blocked_words=self.value('blocked_words'))
            if idea in self._recent_ideas:
                raise ValidationError('That idea repeated a recent one. Click AI Ideas again for something fresh.')
            self._apply_idea_fields(idea)
        except (GenerationError, ValidationError) as error:
            self.status_var.set('The idea could not be applied. Your previous brief and lyrics are still here.')
            messagebox.showerror('Could not finish this idea', str(error), parent=self)
            return
        except Exception:
            self.status_var.set('The idea could not be applied. Your previous brief and lyrics are still here. Try again.')
            return
        self._idea_undo_snapshot = snapshot
        self._recent_ideas = (self._recent_ideas + [deepcopy(idea)])[-8:]
        self.undo_idea_btn.configure(state='normal')
        self.form_canvas.yview_moveto(0)
        if self._save_settings():
            self.status_var.set('Fresh idea ready. Tweak the brief, then choose Write my lyrics when you want a draft.')

    def start_generation(self, rewrite=False):
        if self.busy:
            return
        if rewrite and not self.lyrics():
            self.status_var.set('Paste or write lyrics before choosing Rewrite.')
            return
        try:
            request = self.request(rewrite)
            validate_request(request)
        except (ValidationError, ValueError) as error:
            messagebox.showinfo('Check your brief', str(error), parent=self)
            return
        if not self.api_key:
            self.connection_dialog()
            return
        self._save_settings()
        self.active_id += 1
        job_id = self.active_id
        self.cancel_event = threading.Event()
        cancel = self.cancel_event
        key = self.api_key
        self._active_request = deepcopy(request)
        self._active_job_kind = 'lyrics'
        self._set_busy(True)
        self.status_var.set('Writing a draft, then giving it an editorial pass…')
        def worker():
            try:
                result = generate_lyrics(request, key,
                                         progress=lambda text: self.events.put((job_id, 'progress', text)),
                                         cancel=cancel)
                self.events.put((job_id, 'result', result))
            except GenerationCancelled:
                self.events.put((job_id, 'cancelled', None))
            except (GenerationError, ValidationError) as error:
                self.events.put((job_id, 'error', str(error)))
            except Exception:
                self.events.put((job_id, 'error', 'Something went wrong. Your existing lyrics are still here. Try again.'))
        threading.Thread(target=worker, daemon=True).start()

    def _set_busy(self, busy):
        self.busy = busy
        self.generate_btn.configure(state='disabled' if busy else 'normal')
        self.rewrite_btn.configure(state='disabled' if busy else 'normal')
        self.cancel_btn.configure(state='normal' if busy else 'disabled')
        self.editor.configure(state='disabled' if busy else 'normal')
        self.undo_btn.configure(state='disabled' if busy else 'normal')
        self.arrange_btn.configure(state='disabled' if busy else 'normal')
        self.connection_btn.configure(state='disabled' if busy else 'normal')
        self.load_song_btn.configure(state='disabled' if busy else 'normal')
        self.clear_song_btn.configure(state='disabled' if busy else 'normal')
        self.idea_btn.configure(state='disabled' if busy else 'normal')
        self.undo_idea_btn.configure(state='normal' if self._idea_undo_snapshot is not None and not busy else 'disabled')
        if busy:
            self._form_states = []
            def lock(parent):
                for widget in parent.winfo_children():
                    if isinstance(widget, (tk.Text, ttk.Combobox, tk.Checkbutton)):
                        self._form_states.append((widget, widget.cget('state')))
                        widget.configure(state='disabled')
                    lock(widget)
            lock(self.sidebar)
            self.progressbar.start(14)
        else:
            for widget, state in self._form_states:
                widget.configure(state=state)
            self._form_states = []
            self.progressbar.stop()
        self._sync_song_ui()
        self._update_gate()

    def cancel_generation(self):
        if self.busy:
            self.cancel_event.set()
            self.cancel_btn.configure(state='disabled')
            self.status_var.set('Stopping after the current request returns. No further requests will start.')

    def _poll(self):
        if self.closed:
            return
        try:
            while True:
                job_id, kind, payload = self.events.get_nowait()
                if job_id != self.active_id:
                    continue
                if kind == 'progress':
                    if self.busy and not self.cancel_event.is_set():
                        self.status_var.set(payload)
                elif kind == 'idea':
                    if self.busy and self._active_job_kind == 'idea':
                        self._finish_idea(payload)
                elif kind == 'result':
                    self._active_job_kind = None
                    self._set_busy(False)
                    if self.cancel_event.is_set():
                        self.status_var.set('Stopped. Your previous lyrics are still here.')
                        continue
                    if self._active_request is not None and self.song_structure != self._active_request.song_structure:
                        self.status_var.set('The song map changed during writing. Result withheld; write again for the current map.')
                        continue
                    # Rules may have changed while the model was writing. Gate again on the UI thread.
                    issue = self._gate_problem(payload.lyrics)
                    if issue:
                        self.status_var.set('Your word rules changed during writing. Result withheld; write again.')
                        continue
                    self.editor.edit_separator()
                    self.editor.configure(autoseparators=False)
                    self.editor.delete('1.0', 'end')
                    self.editor.insert('1.0', payload.lyrics)
                    self.editor.configure(autoseparators=True)
                    self.editor.edit_separator()
                    self.last_result = payload
                    self._draft_map_changed = False
                    self.dirty = True
                    self._update_gate()
                    self.status_var.set(f'Ready — edited and checked. {payload.api_calls} requests used. Your ears make the final call.')
                elif kind == 'cancelled':
                    was_idea = self._active_job_kind == 'idea'
                    self._active_job_kind = None
                    self._idea_pending_snapshot = None
                    self._set_busy(False)
                    self.status_var.set('Stopped. Your previous brief and lyrics are still here.' if was_idea else
                                        'Stopped. Your previous lyrics are still here.')
                elif kind == 'error':
                    was_idea = self._active_job_kind == 'idea'
                    self._active_job_kind = None
                    self._idea_pending_snapshot = None
                    self._set_busy(False)
                    if was_idea and self.cancel_event.is_set():
                        self.status_var.set('Stopped. Your previous brief and lyrics are still here.')
                        continue
                    self.status_var.set(payload)
                    messagebox.showerror('Could not finish this idea' if was_idea else 'Could not finish these lyrics', payload, parent=self)
        except queue.Empty:
            pass
        self.after(120, self._poll)

    def _exportable(self):
        text = self.lyrics()
        if not text or self.busy:
            return ''
        issue = self._gate_problem(text)
        if issue:
            self.status_var.set(issue + '. Rewrite or edit before copying or saving.')
            self._update_gate()
            return ''
        return text

    def copy_lyrics(self):
        text = self._exportable()
        if text:
            self.clipboard_clear()
            self.clipboard_append(text)
            self.status_var.set('Lyrics copied.')

    def undo_edit(self):
        if self.busy:
            return
        try:
            self.editor.edit_undo()
            self.status_var.set('Previous edit restored.')
            self._update_gate()
        except tk.TclError:
            self.status_var.set('Nothing to undo yet.')

    def _copy_selection(self, event=None):
        if not self._exportable():
            return 'break'
        try:
            text = self.editor.get('sel.first', 'sel.last')
        except tk.TclError:
            return 'break'
        if self._gate_problem(text, check_structure=False):
            self.status_var.set('Copy the whole song to include every required word.')
            return 'break'
        self.clipboard_clear()
        self.clipboard_append(text)
        return 'break'

    def _cut_selection(self, event=None):
        if not self._exportable():
            return 'break'
        try:
            text = self.editor.get('sel.first', 'sel.last')
        except tk.TclError:
            return 'break'
        if self._gate_problem(text, check_structure=False):
            self.status_var.set('This selection does not contain every required word.')
            return 'break'
        self.clipboard_clear()
        self.clipboard_append(text)
        self.editor.delete('sel.first', 'sel.last')
        return 'break'

    def save_lyrics(self):
        text = self._exportable()
        if not text:
            return
        path = filedialog.asksaveasfilename(parent=self, title='Save your lyrics',
                                          initialdir=str(self.settings_path.parent), initialfile='My rap song.txt',
                                          defaultextension='.txt', filetypes=[('Text file', '*.txt')])
        if path:
            try:
                Path(path).write_text(text + '\n', encoding='utf-8')
            except OSError:
                messagebox.showerror('Could not save', 'Choose a folder you can write to and try again.', parent=self)
                return
            self.exported_text = text
            self.dirty = False
            self.status_var.set('Lyrics saved.')

    def _close(self):
        if self.dirty and self.lyrics():
            response = messagebox.askyesnocancel('Save your lyrics?', 'Save your current lyrics before closing?', parent=self)
            if response is None:
                return
            if response:
                self.save_lyrics()
                if self.dirty:
                    return
        self.cancel_event.set()
        self._save_settings()
        self.closed = True
        self.destroy()


if __name__ == '__main__':
    if os.name == 'nt':
        try:
            import ctypes
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except (AttributeError, OSError):
            pass
    RapWriter().mainloop()
