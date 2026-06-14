#!/usr/bin/env python3
"""
gui_picker.py
=============
CustomTkinter language picker for csp-lang.
"""

from __future__ import annotations

import sys
import tkinter as tk
from argparse import Namespace
from pathlib import Path
from tkinter import BooleanVar, StringVar, messagebox

import customtkinter as ctk

import gui_i18n as i18n

# Fixed inner height for the language columns (official list scrolls inside).
_LANG_LIST_HEIGHT = 128


def _canvas_bg() -> str:
    color = ctk.ThemeManager.theme["CTkFrame"]["fg_color"]
    if isinstance(color, (list, tuple)):
        return color[1] if ctk.get_appearance_mode() == "Dark" else color[0]
    return color


def _scroll_list(parent, height: int) -> ctk.CTkFrame:
    """Fixed-height scroll area; inner frame holds the radio buttons."""
    outer = ctk.CTkFrame(parent, height=height, fg_color="transparent")
    outer.pack(fill="x", padx=8, pady=(0, 6))
    outer.pack_propagate(False)

    canvas = tk.Canvas(
        outer, height=height, highlightthickness=0, bd=0, bg=_canvas_bg())
    scrollbar = ctk.CTkScrollbar(outer, command=canvas.yview)
    inner = ctk.CTkFrame(canvas, fg_color="transparent")
    window_id = canvas.create_window((0, 0), window=inner, anchor="nw")

    def _on_inner_configure(_event=None) -> None:
        canvas.configure(scrollregion=canvas.bbox("all"))

    def _on_canvas_configure(event) -> None:
        canvas.itemconfigure(window_id, width=event.width)

    def _on_mousewheel(event) -> None:
        canvas.yview_scroll(int(-event.delta / 120), "units")

    inner.bind("<Configure>", _on_inner_configure)
    canvas.bind("<Configure>", _on_canvas_configure)
    canvas.configure(yscrollcommand=scrollbar.set)
    canvas.bind("<Enter>", lambda _e: canvas.bind_all("<MouseWheel>", _on_mousewheel))
    canvas.bind("<Leave>", lambda _e: canvas.unbind_all("<MouseWheel>"))

    canvas.pack(side="left", fill="both", expand=True)
    scrollbar.pack(side="right", fill="y")
    return inner


def _fit_window(root: ctk.CTk, main: ctk.CTkFrame, footer: ctk.CTkFrame) -> None:
    """Size the window to its content, accounting for CustomTkinter DPI scaling."""
    root.update_idletasks()
    root.update()
    height = main.winfo_y() + footer.winfo_y() + footer.winfo_height() + 8
    width = root.winfo_reqwidth()
    w = root._reverse_window_scaling(width)
    h = root._reverse_window_scaling(height)
    root.geometry(f"{w}x{h}")
    root.update_idletasks()
    x = max(0, (root.winfo_screenwidth() - width) // 2)
    y = max(0, (root.winfo_screenheight() - height) // 2)
    root.geometry(f"{w}x{h}+{x}+{y}")
    root.resizable(False, False)


def run_picker(args: Namespace, settings_file: Path) -> None:
    import lang
    from lang import (
        PIPELINES,
        UNKNOWN,
        WARNINGS,
        LanguageChoice,
        classify_all,
        cmd_switch,
        discover_community_packs,
        discover_official_languages,
        pipeline_display_state,
        summary_for_gui,
    )

    ctk.set_appearance_mode("system")
    ctk.set_default_color_theme("blue")

    gui_lang = i18n.load_gui_language(settings_file)
    label_to_code = {i18n.NATIVE_LABELS[c]: c for c in i18n.SUPPORTED}
    gui_labels = [i18n.NATIVE_LABELS[c] for c in i18n.SUPPORTED]

    root = ctk.CTk()
    root.withdraw()
    root.grid_rowconfigure(0, weight=0)
    root.grid_columnconfigure(0, weight=0)

    selected = StringVar(value="")
    choice_map: dict[str, LanguageChoice] = {}
    pipeline_vars: dict[str, BooleanVar] = {}
    pipeline_name_labels: dict[str, ctk.CTkLabel] = {}
    pipeline_status_labels: dict[str, ctk.CTkLabel] = {}

    main = ctk.CTkFrame(root, fg_color="transparent")
    main.grid(row=0, column=0, sticky="nw", padx=12, pady=8)

    top = ctk.CTkFrame(main, fg_color="transparent")
    top.pack(fill="x", pady=(0, 6))
    gui_lang_label = ctk.CTkLabel(top, text=i18n.t(gui_lang, "gui_language"))
    gui_lang_label.pack(side="right", padx=(8, 6))
    gui_lang_combo = ctk.CTkComboBox(
        top, values=gui_labels, width=130, state="readonly",
        command=lambda _v: on_gui_lang_change())
    gui_lang_combo.set(i18n.NATIVE_LABELS[gui_lang])
    gui_lang_combo.pack(side="right")

    choose_label = ctk.CTkLabel(
        main, text=i18n.t(gui_lang, "choose_language"),
        font=ctk.CTkFont(size=14, weight="bold"))
    choose_label.pack(anchor="w")
    blurb_label = ctk.CTkLabel(
        main, text=i18n.t(gui_lang, "choose_blurb"),
        wraplength=500, justify="left", text_color=("gray30", "gray70"),
        font=ctk.CTkFont(size=12))
    blurb_label.pack(anchor="w", pady=(2, 6))

    body = ctk.CTkFrame(main, fg_color="transparent")
    body.pack(fill="x")
    body.columnconfigure(0, weight=1)
    body.columnconfigure(1, weight=1)

    community_box = ctk.CTkFrame(body, corner_radius=8)
    official_box = ctk.CTkFrame(body, corner_radius=8)
    community_box.grid(row=0, column=0, sticky="new", padx=(0, 6))
    official_box.grid(row=0, column=1, sticky="new", padx=(6, 0))

    community_title = ctk.CTkLabel(
        community_box, text=i18n.t(gui_lang, "community_box"),
        font=ctk.CTkFont(weight="bold"))
    community_title.pack(anchor="w", padx=8, pady=(6, 2))
    community_inner = ctk.CTkFrame(
        community_box, fg_color="transparent", height=_LANG_LIST_HEIGHT)
    community_inner.pack(fill="x", padx=8, pady=(0, 6))
    community_inner.pack_propagate(False)

    official_title = ctk.CTkLabel(
        official_box, text=i18n.t(gui_lang, "official_box"),
        font=ctk.CTkFont(weight="bold"))
    official_title.pack(anchor="w", padx=8, pady=(6, 2))
    official_inner = _scroll_list(official_box, _LANG_LIST_HEIGHT)

    subsystems_box = ctk.CTkFrame(main, corner_radius=8)
    subsystems_box.pack(fill="x", pady=(8, 0))
    subsystems_title = ctk.CTkLabel(
        subsystems_box, text=i18n.t(gui_lang, "subsystems_box"),
        font=ctk.CTkFont(weight="bold"))
    subsystems_title.pack(anchor="w", padx=8, pady=(6, 2))
    subsystems_grid = ctk.CTkFrame(subsystems_box, fg_color="transparent")
    subsystems_grid.pack(fill="x", padx=8, pady=(0, 6))
    subsystems_grid.columnconfigure(1, weight=1)

    for i, name in enumerate(PIPELINES):
        pipeline_vars[name] = BooleanVar(value=True)
        ctk.CTkCheckBox(
            subsystems_grid, text="", variable=pipeline_vars[name], width=20,
        ).grid(row=i, column=0, padx=(0, 4), pady=1, sticky="w")
        plabel = ctk.CTkLabel(
            subsystems_grid, text=i18n.pipeline_label(gui_lang, name),
            anchor="w", font=ctk.CTkFont(size=12))
        plabel.grid(row=i, column=1, sticky="w", pady=1)
        pipeline_name_labels[name] = plabel
        slabel = ctk.CTkLabel(
            subsystems_grid, text="…", anchor="e",
            text_color=("gray30", "gray70"), font=ctk.CTkFont(size=12))
        slabel.grid(row=i, column=2, sticky="e", padx=(8, 0), pady=1)
        pipeline_status_labels[name] = slabel

    status_label = ctk.CTkLabel(
        main, text=i18n.t(gui_lang, "checking_status"),
        wraplength=500, justify="left", font=ctk.CTkFont(size=12))
    status_label.pack(anchor="w", pady=(6, 0))

    buttons = ctk.CTkFrame(main, fg_color="transparent")
    buttons.pack(fill="x", pady=(8, 0))
    apply_btn = ctk.CTkButton(buttons, text=i18n.t(gui_lang, "btn_apply"),
                                command=lambda: apply_selected())
    apply_btn.pack(side="right")
    refresh_btn = ctk.CTkButton(
        buttons, text=i18n.t(gui_lang, "btn_refresh"), fg_color="transparent",
        border_width=1, command=lambda: (refresh_choices(), refresh_status()))
    refresh_btn.pack(side="right", padx=(0, 8))
    close_btn = ctk.CTkButton(
        buttons, text=i18n.t(gui_lang, "btn_close"), fg_color="transparent",
        border_width=1, command=root.destroy)
    close_btn.pack(side="right", padx=(0, 8))

    def apply_gui_language(lang: str) -> None:
        nonlocal gui_lang
        gui_lang = i18n.normalize_language(lang)
        root.title(i18n.t(gui_lang, "window_title"))
        gui_lang_label.configure(text=i18n.t(gui_lang, "gui_language"))
        choose_label.configure(text=i18n.t(gui_lang, "choose_language"))
        blurb_label.configure(text=i18n.t(gui_lang, "choose_blurb"))
        community_title.configure(text=i18n.t(gui_lang, "community_box"))
        official_title.configure(text=i18n.t(gui_lang, "official_box"))
        subsystems_title.configure(text=i18n.t(gui_lang, "subsystems_box"))
        for name in PIPELINES:
            pipeline_name_labels[name].configure(
                text=i18n.pipeline_label(gui_lang, name))
        apply_btn.configure(text=i18n.t(gui_lang, "btn_apply"))
        refresh_btn.configure(text=i18n.t(gui_lang, "btn_refresh"))
        close_btn.configure(text=i18n.t(gui_lang, "btn_close"))
        refresh_status()

    def on_gui_lang_change() -> None:
        code = label_to_code.get(gui_lang_combo.get())
        if not code or code == gui_lang:
            return
        i18n.save_gui_language(settings_file, code)
        apply_gui_language(code)

    def add_choice(parent, choice: LanguageChoice) -> None:
        key = f"{choice.kind}:{choice.id}"
        choice_map[key] = choice
        ctk.CTkRadioButton(
            parent, text=choice.display, variable=selected, value=key,
            radiobutton_width=16, radiobutton_height=16,
            font=ctk.CTkFont(size=12),
        ).pack(anchor="w", pady=1)
        if not selected.get():
            selected.set(key)

    def add_official_choice(choice: LanguageChoice) -> None:
        key = f"{choice.kind}:{choice.id}"
        choice_map[key] = choice
        ctk.CTkRadioButton(
            official_inner, text=choice.display, variable=selected, value=key,
            radiobutton_width=16, radiobutton_height=16,
            font=ctk.CTkFont(size=12),
        ).pack(anchor="w", pady=1)
        if not selected.get():
            selected.set(key)

    def refresh_choices() -> None:
        for child in community_inner.winfo_children():
            child.destroy()
        for child in official_inner.winfo_children():
            child.destroy()
        choice_map.clear()
        selected.set("")
        communities = discover_community_packs()
        officials = discover_official_languages(args.csp)
        if communities:
            for choice in communities.values():
                add_choice(community_inner, choice)
        else:
            ctk.CTkLabel(
                community_inner, text=i18n.t(gui_lang, "no_community"),
                font=ctk.CTkFont(size=12)).pack(anchor="w")
        if officials:
            for choice in officials.values():
                add_official_choice(choice)
        else:
            ctk.CTkLabel(
                official_inner, text=i18n.t(gui_lang, "no_official"),
                font=ctk.CTkFont(size=12)).pack(anchor="w")

    def refresh_status() -> None:
        try:
            statuses = classify_all(args)
            prefix = i18n.t(gui_lang, "now_prefix")
            for name in PIPELINES:
                current = statuses.get(name, UNKNOWN)
                pipeline_status_labels[name].configure(
                    text=f"{prefix} {pipeline_display_state(current, gui_lang)}")
            status_label.configure(text=summary_for_gui(statuses, gui_lang))
        except SystemExit as e:
            status_label.configure(text=str(e))
            for name in PIPELINES:
                pipeline_status_labels[name].configure(
                    text=i18n.t(gui_lang, "now_unknown"))

    def apply_selected() -> None:
        key = selected.get()
        choice = choice_map.get(key)
        if not choice:
            messagebox.showerror(
                i18n.t(gui_lang, "err_no_language_title"),
                i18n.t(gui_lang, "err_no_language"))
            return
        enabled = {name for name in PIPELINES if pipeline_vars[name].get()}
        if not enabled:
            messagebox.showerror(
                i18n.t(gui_lang, "err_nothing_title"),
                i18n.t(gui_lang, "err_nothing"))
            return
        labels = ", ".join(
            i18n.pipeline_label(gui_lang, n) for n in PIPELINES if n in enabled)
        if not messagebox.askyesno(
                i18n.t(gui_lang, "confirm_apply_title"),
                i18n.t(gui_lang, "confirm_apply",
                       display=choice.display, labels=labels)):
            return
        args.target = choice.id
        args.pipelines = enabled
        sys.argv = [sys.argv[0], choice.id, "--keep-open"]
        try:
            cmd_switch(args)
        except SystemExit as e:
            if e.code == 0:
                messagebox.showinfo(
                    i18n.t(gui_lang, "elevated_title"),
                    i18n.t(gui_lang, "elevated_body"))
                root.destroy()
                return
            messagebox.showerror(i18n.t(gui_lang, "failed_title"), str(e))
        else:
            restart = i18n.t(gui_lang, "restart_csp", display=choice.display)
            if WARNINGS:
                messagebox.showwarning(
                    i18n.t(gui_lang, "warnings_title"),
                    "\n".join(w.strip() for w in WARNINGS) + "\n\n" + restart)
            else:
                messagebox.showinfo(i18n.t(gui_lang, "done_title"), restart)
        finally:
            args.pipelines = None
            sys.argv = [sys.argv[0]]
            refresh_status()

    apply_gui_language(gui_lang)
    refresh_choices()
    _fit_window(root, main, buttons)
    root.deiconify()
    root.mainloop()
