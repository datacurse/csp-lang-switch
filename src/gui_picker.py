#!/usr/bin/env python3
"""
gui_picker.py
=============
CustomTkinter language picker for csp-lang.
"""

from __future__ import annotations

import sys
import threading
import tkinter as tk
from argparse import Namespace
from pathlib import Path
from tkinter import BooleanVar, StringVar

import customtkinter as ctk

import gui_i18n as i18n

# Fixed inner height for the language columns (official list scrolls inside).
_LANG_LIST_HEIGHT = 128
_STATUS_OK = ("#2d6a4f", "#52b788")
_STATUS_ERR = ("#9b2226", "#e5383b")
# Official CSP languages the switcher can apply (others are shown but disabled).
_OFFICIAL_SELECTABLE = frozenset({"english"})


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
        build_switch_argv,
        choice_display,
        classify_all,
        cmd_switch,
        discover_community_packs,
        discover_official_languages,
        pipeline_display_state,
        summary_for_gui,
    )
    from common import is_admin, run_elevated_sync

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
    gui_lang_label.pack(side="left")
    gui_lang_combo = ctk.CTkComboBox(
        top, values=gui_labels, width=130, state="readonly",
        command=lambda _v: on_gui_lang_change())
    gui_lang_combo.set(i18n.NATIVE_LABELS[gui_lang])
    gui_lang_combo.pack(side="left", padx=(6, 0))

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

    progress = ctk.CTkProgressBar(main, mode="indeterminate")
    busy = False

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
        refresh_choices()
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
            parent, text=choice_display(choice, gui_lang), variable=selected, value=key,
            radiobutton_width=16, radiobutton_height=16,
            font=ctk.CTkFont(size=12),
        ).pack(anchor="w", pady=1)
        if not selected.get():
            selected.set(key)

    def add_official_choice(choice: LanguageChoice) -> None:
        key = f"{choice.kind}:{choice.id}"
        selectable = choice.id in _OFFICIAL_SELECTABLE
        if selectable:
            choice_map[key] = choice
        label = choice_display(choice, gui_lang)
        if not selectable:
            label = f"{label} ({i18n.t(gui_lang, 'official_not_yet')})"
        ctk.CTkRadioButton(
            official_inner, text=label, variable=selected, value=key,
            radiobutton_width=16, radiobutton_height=16,
            font=ctk.CTkFont(size=12),
            state="normal" if selectable else "disabled",
        ).pack(anchor="w", pady=1)
        if selectable and not selected.get():
            selected.set(key)

    def _official_choices(officials: dict[str, LanguageChoice]) -> list[LanguageChoice]:
        """English first, then the rest alphabetically by display name."""
        items = list(officials.values())
        items.sort(key=lambda c: (0 if c.id == "english" else 1, c.display.casefold()))
        return items

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
            for choice in _official_choices(officials):
                add_official_choice(choice)
        else:
            ctk.CTkLabel(
                official_inner, text=i18n.t(gui_lang, "no_official"),
                font=ctk.CTkFont(size=12)).pack(anchor="w")

    def _set_status(text: str, *, kind: str = "normal") -> None:
        colors = {
            "normal": ("gray10", "gray90"),
            "ok": _STATUS_OK,
            "err": _STATUS_ERR,
        }
        status_label.configure(text=text, text_color=colors.get(kind, colors["normal"]))

    def _set_busy(on: bool) -> None:
        nonlocal busy
        busy = on
        state = "disabled" if on else "normal"
        apply_btn.configure(state=state)
        refresh_btn.configure(state=state)
        close_btn.configure(state=state)
        if on:
            progress.pack(fill="x", pady=(6, 0))
            progress.start()
            _set_status(i18n.t(gui_lang, "switching"))
        else:
            progress.stop()
            progress.pack_forget()

    def refresh_status(
        final_message: str | None = None, final_kind: str = "normal",
    ) -> None:
        try:
            statuses = classify_all(args)
            prefix = i18n.t(gui_lang, "now_prefix")
            for name in PIPELINES:
                current = statuses.get(name, UNKNOWN)
                pipeline_status_labels[name].configure(
                    text=f"{prefix} {pipeline_display_state(current, gui_lang)}")
            if final_message is not None:
                _set_status(final_message, kind=final_kind)
            else:
                _set_status(summary_for_gui(statuses, gui_lang))
        except SystemExit as e:
            _set_status(i18n.localize_error(gui_lang, str(e)), kind="err")
            for name in PIPELINES:
                pipeline_status_labels[name].configure(
                    text=i18n.t(gui_lang, "now_unknown"))

    def _localize_error(msg: str) -> str:
        return i18n.localize_error(gui_lang, msg)

    def _finish_apply(error: str | None, display: str) -> None:
        _set_busy(False)
        if error:
            _set_status(_localize_error(error), kind="err")
            return
        restart = i18n.t(gui_lang, "restart_csp", display=display)
        if WARNINGS:
            notes = "\n".join(w.strip() for w in WARNINGS)
            refresh_status(f"{notes}\n\n{restart}", final_kind="ok")
        else:
            refresh_status(restart, final_kind="ok")

    def apply_selected() -> None:
        if busy:
            return
        key = selected.get()
        choice = choice_map.get(key)
        if not choice:
            _set_status(i18n.t(gui_lang, "err_no_language"), kind="err")
            return
        enabled = {name for name in PIPELINES if pipeline_vars[name].get()}
        if not enabled:
            _set_status(i18n.t(gui_lang, "err_nothing"), kind="err")
            return

        switch_args = Namespace(
            target=choice.id,
            csp=args.csp,
            dry_run=False,
            force=getattr(args, "force", False),
            keep_open=False,
            from_gui=True,
            pipelines=enabled,
        )
        display = choice_display(choice, gui_lang)
        _set_busy(True)
        root.update()

        # UAC must run on the main thread; a background thread often fails silently.
        if not is_admin():
            rc, err = run_elevated_sync(build_switch_argv(switch_args))
            _finish_apply(err if rc != 0 else None, display)
            return

        def work() -> None:
            error: str | None = None
            try:
                cmd_switch(switch_args)
            except SystemExit as e:
                error = str(e) if e.args else ""

            root.after(0, lambda: _finish_apply(error, display))

        threading.Thread(target=work, daemon=True).start()

    apply_gui_language(gui_lang)
    refresh_choices()
    _fit_window(root, main, buttons)
    root.deiconify()
    root.mainloop()
