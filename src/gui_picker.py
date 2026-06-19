#!/usr/bin/env python3
"""
gui_picker.py
=============
CustomTkinter language picker for csp-lang-switch.
"""

from __future__ import annotations

import threading
import tkinter as tk
from argparse import Namespace
from pathlib import Path
from tkinter import StringVar

import customtkinter as ctk

import gui_i18n as i18n

_STATUS_OK = ("#2d6a4f", "#52b788")
_STATUS_ERR = ("#9b2226", "#e5383b")
# The interface is always Russian; English UI is no longer offered.
_GUI_LANG = "ru"
# Both subsystems are always switched together as a single choice.
_SWITCH_PIPELINES = ("main-ui", "plugins")


def _fit_window(root: ctk.CTk, main: ctk.CTkFrame, footer: ctk.CTkFrame) -> None:
    """Size the window to its content, accounting for CustomTkinter DPI scaling."""
    root.update_idletasks()
    root.update()
    root.update_idletasks()
    width = max(root.winfo_reqwidth(), main.winfo_reqwidth() + 24)
    height = max(root.winfo_reqheight(), main.winfo_reqheight() + 16)
    w = root._reverse_window_scaling(width)
    h = root._reverse_window_scaling(height)
    root.geometry(f"{w}x{h}")
    root.update_idletasks()
    x = max(0, (root.winfo_screenwidth() - width) // 2)
    y = max(0, (root.winfo_screenheight() - height) // 2)
    root.geometry(f"{w}x{h}+{x}+{y}")
    root.resizable(False, False)


def run_picker(args: Namespace, settings_file: Path) -> None:
    from lang import (
        ORIGINAL,
        UNKNOWN,
        WARNINGS,
        LanguageChoice,
        build_switch_argv,
        choice_display,
        classify_all,
        cmd_switch,
        discover_community_packs,
        discover_official_languages,
        is_official_state,
        official_id_from_state,
        set_active_version,
        summary_for_gui,
    )
    from version import SUPPORTED_VERSIONS
    from common import is_admin, run_elevated_sync

    gui_lang = _GUI_LANG

    ctk.set_appearance_mode("system")
    ctk.set_default_color_theme("blue")

    root = ctk.CTk()
    root.withdraw()
    root.title(i18n.t(gui_lang, "window_title"))
    root.grid_rowconfigure(0, weight=0)
    root.grid_columnconfigure(0, weight=0)

    selected = StringVar(value="")
    selected_version = StringVar(value=getattr(args, "csp_version", SUPPORTED_VERSIONS[0]))
    choice_map: dict[str, LanguageChoice] = {}

    detected_version = getattr(args, "detected_csp_version", None)
    raw_product_version = getattr(args, "raw_csp_product_version", None)
    version_blocked = False
    version_warning: str | None = None

    main = ctk.CTkFrame(root, fg_color="transparent")
    main.grid(row=0, column=0, sticky="nw", padx=12, pady=8)

    version_label = ctk.CTkLabel(
        main, text=i18n.t(gui_lang, "choose_csp_version"),
        font=ctk.CTkFont(size=14, weight="bold"))
    version_label.pack(anchor="w", pady=(0, 4))

    version_row = ctk.CTkFrame(main, fg_color="transparent")
    version_row.pack(fill="x", pady=(0, 8))

    version_combo = ctk.CTkComboBox(
        version_row,
        values=list(SUPPORTED_VERSIONS),
        variable=selected_version,
        width=120,
        state="readonly",
    )
    version_combo.pack(side="left")

    version_hint = ctk.CTkLabel(
        version_row, text="",
        font=ctk.CTkFont(size=12), text_color="gray50")
    version_hint.pack(side="left", padx=(10, 0))

    choose_label = ctk.CTkLabel(
        main, text=i18n.t(gui_lang, "choose_language"),
        font=ctk.CTkFont(size=14, weight="bold"))
    choose_label.pack(anchor="w", pady=(0, 6))

    lang_box = ctk.CTkFrame(main, corner_radius=8)
    lang_box.pack(fill="x")
    lang_inner = ctk.CTkFrame(lang_box, fg_color="transparent")
    lang_inner.pack(fill="x", padx=10, pady=8)

    status_label = ctk.CTkLabel(
        main, text=i18n.t(gui_lang, "checking_status"),
        wraplength=420, justify="left", font=ctk.CTkFont(size=12))
    status_label.pack(anchor="w", pady=(8, 0))

    progress = ctk.CTkProgressBar(main, mode="indeterminate")
    busy = False

    buttons = ctk.CTkFrame(main, fg_color="transparent")
    buttons.pack(fill="x", pady=(8, 0))
    apply_btn = ctk.CTkButton(buttons, text=i18n.t(gui_lang, "btn_apply"),
                              command=lambda: apply_selected())
    apply_btn.pack(side="right")
    refresh_btn = ctk.CTkButton(
        buttons, text=i18n.t(gui_lang, "btn_refresh"), fg_color="transparent",
        border_width=1, command=lambda: refresh())
    refresh_btn.pack(side="right", padx=(0, 8))
    close_btn = ctk.CTkButton(
        buttons, text=i18n.t(gui_lang, "btn_close"), fg_color="transparent",
        border_width=1, command=root.destroy)
    close_btn.pack(side="right", padx=(0, 8))

    def _supported_list() -> str:
        return ", ".join(SUPPORTED_VERSIONS)

    def _installed_label() -> str:
        if raw_product_version:
            return raw_product_version
        if detected_version:
            return detected_version
        return "?"

    def _refresh_version_state() -> None:
        nonlocal version_blocked, version_warning
        version_blocked = False
        version_warning = None

        if detected_version:
            version_hint.configure(
                text=i18n.t(gui_lang, "csp_version_auto", version=detected_version))
        else:
            version_hint.configure(text="")

        if raw_product_version and detected_version is None:
            version_blocked = True
            version_warning = i18n.t(
                gui_lang, "err_csp_version_unsupported",
                installed=raw_product_version,
                supported=_supported_list(),
            )
        elif detected_version and selected_version.get() != detected_version:
            version_blocked = True
            version_warning = i18n.t(
                gui_lang, "err_csp_version_mismatch",
                selected=selected_version.get(),
                installed=_installed_label(),
            )

        apply_btn.configure(state="disabled" if version_blocked else "normal")

    def _ordered_choices() -> list[LanguageChoice]:
        """Russian (community) first, then English (official). Nothing else."""
        out: list[LanguageChoice] = []
        communities = discover_community_packs()
        for cid in sorted(communities, key=lambda c: (0 if c == "russian" else 1, c)):
            out.append(communities[cid])
        officials = discover_official_languages(args.csp)
        if "english" in officials:
            out.append(officials["english"])
        return out

    def _active_key(statuses: dict[str, str]) -> str | None:
        """Map the current main-UI state to a language list key, if known."""
        state = statuses.get("main-ui")
        if not state or state == UNKNOWN:
            return None
        if state == ORIGINAL:
            return "official:english"
        if is_official_state(state):
            return f"official:{official_id_from_state(state)}"
        return f"community:{state}"

    def _build_language_list(active: str | None) -> None:
        for child in lang_inner.winfo_children():
            child.destroy()
        choice_map.clear()
        ordered = _ordered_choices()
        if not ordered:
            ctk.CTkLabel(
                lang_inner, text=i18n.t(gui_lang, "no_official"),
                font=ctk.CTkFont(size=12)).pack(anchor="w")
            selected.set("")
            return
        preselect: str | None = None
        for choice in ordered:
            key = f"{choice.kind}:{choice.id}"
            choice_map[key] = choice
            label = choice_display(choice, gui_lang)
            if key == active:
                label = f"{label} ({i18n.t(gui_lang, 'now_active')})"
                preselect = key
            ctk.CTkRadioButton(
                lang_inner, text=label, variable=selected, value=key,
                radiobutton_width=18, radiobutton_height=18,
                font=ctk.CTkFont(size=13),
            ).pack(anchor="w", pady=3, padx=2)
        selected.set(preselect or f"{ordered[0].kind}:{ordered[0].id}")

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
        if not version_blocked:
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

    def refresh(
        final_message: str | None = None, final_kind: str = "normal",
    ) -> None:
        if not root.winfo_exists():
            return
        statuses: dict[str, str] = {}
        error: str | None = None
        try:
            statuses = classify_all(args)
        except SystemExit as e:
            error = str(e)
        try:
            _build_language_list(_active_key(statuses))
            if final_message is not None:
                _set_status(final_message, kind=final_kind)
            elif version_warning:
                _set_status(version_warning, kind="err")
            elif error is not None:
                _set_status(
                    i18n.localize_error(
                        gui_lang, error,
                        version=selected_version.get(),
                    ),
                    kind="err",
                )
            else:
                visible = {n: statuses[n] for n in _SWITCH_PIPELINES if n in statuses}
                if visible:
                    _set_status(summary_for_gui(visible, gui_lang))
        except tk.TclError:
            pass

    def _localize_error(msg: str) -> str:
        return i18n.localize_error(
            gui_lang, msg, version=selected_version.get(),
        )

    def _finish_apply(error: str | None) -> None:
        _set_busy(False)
        if error:
            _set_status(_localize_error(error), kind="err")
            return
        restart = i18n.t(gui_lang, "restart_csp")
        if WARNINGS:
            notes = "\n".join(w.strip() for w in WARNINGS)
            refresh(f"{notes}\n\n{restart}", final_kind="ok")
        else:
            refresh(restart, final_kind="ok")

    def apply_selected() -> None:
        if busy or version_blocked:
            return
        key = selected.get()
        choice = choice_map.get(key)
        if not choice:
            _set_status(i18n.t(gui_lang, "err_no_language"), kind="err")
            return

        switch_args = Namespace(
            target=choice.id,
            csp=args.csp,
            csp_version=selected_version.get(),
            dry_run=False,
            force=getattr(args, "force", False),
            keep_open=False,
            from_gui=True,
            pipelines=set(_SWITCH_PIPELINES),
        )
        _set_busy(True)
        root.update()

        # UAC must run on the main thread; a background thread often fails silently.
        if not is_admin():
            rc, err = run_elevated_sync(build_switch_argv(switch_args))
            _finish_apply(err if rc != 0 else None)
            return

        def work() -> None:
            error: str | None = None
            try:
                cmd_switch(switch_args)
            except SystemExit as e:
                error = str(e) if e.args else ""

            root.after(0, lambda: _finish_apply(error))

        threading.Thread(target=work, daemon=True).start()

    def on_version_change(_value: str) -> None:
        ver = selected_version.get()
        set_active_version(ver)
        args.csp_version = ver
        i18n.save_csp_version(settings_file, ver)
        _refresh_version_state()
        refresh()

    version_combo.configure(command=on_version_change)

    if detected_version:
        selected_version.set(detected_version)
        set_active_version(detected_version)
        args.csp_version = detected_version
    else:
        set_active_version(selected_version.get())
        args.csp_version = selected_version.get()

    _refresh_version_state()
    refresh()
    _fit_window(root, main, buttons)
    root.deiconify()
    root.mainloop()
