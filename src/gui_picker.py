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
from tkinter import StringVar, filedialog

import customtkinter as ctk

import gui_i18n as i18n
from common import celsys_base_has_csp, set_celsys_base

_STATUS_OK = ("#2d6a4f", "#52b788")
_STATUS_ERR = ("#9b2226", "#e5383b")
# The interface is always Russian; English UI is no longer offered.
_GUI_LANG = "ru"
# Default pipelines shown in status summary.
_SWITCH_PIPELINES = ("main-ui", "plugins")


# ---------------------------------------------------------------------------
# Window size — edit these (logical pixels; CTk applies DPI scaling)
# ---------------------------------------------------------------------------
WINDOW_WIDTH = 400
WINDOW_HEIGHT = 340
# Status text wrap; None = WINDOW_WIDTH minus horizontal padding
STATUS_WRAP_WIDTH: int | None = None


def _status_wrap_width() -> int:
    if STATUS_WRAP_WIDTH is not None:
        return STATUS_WRAP_WIDTH
    return max(200, WINDOW_WIDTH - 32)


def _apply_window_size(root: ctk.CTk) -> None:
    width, height = WINDOW_WIDTH, WINDOW_HEIGHT
    try:
        root.update_idletasks()
        sw = root.winfo_screenwidth()
        sh = root.winfo_screenheight()
        x = max(0, (sw - width) // 2)
        y = max(24, (sh - height) // 2)
        root.geometry(f"{width}x{height}+{x}+{y}")
        root.minsize(width, height)
    except Exception:
        root.geometry(f"{width}x{height}")


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
        detect_installed_csp_version,
        discover_community_packs,
        discover_official_languages,
        detected_csp_product_version,
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
    root.title(i18n.t(gui_lang, "window_title"))
    root.grid_columnconfigure(0, weight=1)
    _apply_window_size(root)

    selected = StringVar(master=root, value="")
    selected_version = StringVar(
        master=root, value=getattr(args, "csp_version", SUPPORTED_VERSIONS[0])
    )
    choice_map: dict[str, LanguageChoice] = {}

    detected_version = getattr(args, "detected_csp_version", None)
    raw_product_version = getattr(args, "raw_csp_product_version", None)
    version_blocked = False
    version_warning: str | None = None

    content = ctk.CTkFrame(root, fg_color="transparent")
    content.grid(row=0, column=0, sticky="ew", padx=12, pady=(12, 4))
    content.grid_columnconfigure(0, weight=1)
    main = content

    footer = ctk.CTkFrame(root, fg_color="transparent")
    footer.grid(row=1, column=0, sticky="ew", padx=12, pady=(0, 10))
    footer.grid_columnconfigure(0, weight=1)

    def _display_celsys_base() -> str:
        saved = getattr(args, "celsys_base", None)
        return saved or i18n.default_celsys_base_display()

    celsys_label = ctk.CTkLabel(
        main,
        text=i18n.t(gui_lang, "choose_celsys_folder"),
        font=ctk.CTkFont(size=14, weight="bold"),
    )
    celsys_label.pack(anchor="w", pady=(0, 4))

    celsys_row = ctk.CTkFrame(main, fg_color="transparent")
    celsys_row.pack(fill="x", pady=(0, 8))
    celsys_row.grid_columnconfigure(0, weight=1)

    celsys_path = ctk.CTkEntry(
        celsys_row,
        state="readonly",
        font=ctk.CTkFont(size=12),
    )
    celsys_path.grid(row=0, column=0, sticky="ew", padx=(0, 8))

    def _set_celsys_display() -> None:
        celsys_path.configure(state="normal")
        celsys_path.delete(0, "end")
        celsys_path.insert(0, _display_celsys_base())
        celsys_path.configure(state="readonly")

    def _apply_celsys_base(path: str | None) -> None:
        args.celsys_base = path
        set_celsys_base(path)
        i18n.save_celsys_base(settings_file, path)
        _set_celsys_display()
        args.detected_csp_version = detect_installed_csp_version(args.csp)
        args.raw_csp_product_version = detected_csp_product_version(args.csp)
        nonlocal detected_version, raw_product_version, version_blocked, version_warning
        detected_version = args.detected_csp_version
        raw_product_version = args.raw_csp_product_version
        if detected_version:
            selected_version.set(detected_version)
            set_active_version(detected_version)
            args.csp_version = detected_version
        _refresh_version_state()
        refresh()

    def browse_celsys_folder() -> None:
        if busy:
            return
        picked = filedialog.askdirectory(
            parent=root,
            title=i18n.t(gui_lang, "choose_celsys_folder_title"),
            initialdir=_display_celsys_base(),
        )
        if not picked:
            return
        base = Path(picked)
        if not celsys_base_has_csp(base):
            _set_status(i18n.t(gui_lang, "err_celsys_invalid"), kind="err")
            return
        custom = None if base == Path(i18n.default_celsys_base_display()) else str(base)
        _apply_celsys_base(custom)

    browse_btn = ctk.CTkButton(
        celsys_row,
        text=i18n.t(gui_lang, "btn_browse"),
        width=90,
        command=browse_celsys_folder,
    )
    browse_btn.grid(row=0, column=1, sticky="e")

    version_label = ctk.CTkLabel(
        main,
        text=i18n.t(gui_lang, "choose_csp_version"),
        font=ctk.CTkFont(size=14, weight="bold"),
    )
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
        version_row,
        text="",
        anchor="w",
        font=ctk.CTkFont(size=12),
        text_color="gray50",
    )
    version_hint.pack(side="left", padx=(10, 0))

    choose_label = ctk.CTkLabel(
        main,
        text=i18n.t(gui_lang, "choose_language"),
        font=ctk.CTkFont(size=14, weight="bold"),
    )
    choose_label.pack(anchor="w", pady=(0, 6))

    lang_box = ctk.CTkFrame(main, corner_radius=8)
    lang_box.pack(fill="x")
    lang_inner = ctk.CTkFrame(lang_box, fg_color="transparent")
    lang_inner.pack(fill="x", padx=8, pady=6)

    status_label = ctk.CTkLabel(
        footer,
        text=i18n.t(gui_lang, "checking_status"),
        wraplength=_status_wrap_width(),
        justify="left",
        anchor="w",
        font=ctk.CTkFont(size=12),
    )
    status_label.grid(row=0, column=0, sticky="w", pady=(0, 8))

    busy = False

    buttons = ctk.CTkFrame(footer, fg_color="transparent")
    buttons.grid(row=1, column=0, sticky="w")
    apply_btn = ctk.CTkButton(
        buttons, text=i18n.t(gui_lang, "btn_apply"), command=lambda: apply_selected()
    )
    apply_btn.pack(side="left")

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
                text=i18n.t(gui_lang, "csp_version_auto", version=detected_version)
            )
        else:
            version_hint.configure(text="")

        if raw_product_version and detected_version is None:
            version_blocked = True
            version_warning = i18n.t(
                gui_lang,
                "err_csp_version_unsupported",
                installed=raw_product_version,
                supported=_supported_list(),
            )
        elif detected_version and selected_version.get() != detected_version:
            version_blocked = True
            version_warning = i18n.t(
                gui_lang,
                "err_csp_version_mismatch",
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
                lang_inner,
                text=i18n.t(gui_lang, "no_official"),
                font=ctk.CTkFont(size=12),
            ).pack(anchor="w")
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
                lang_inner,
                text=label,
                variable=selected,
                value=key,
                radiobutton_width=18,
                radiobutton_height=18,
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
        browse_btn.configure(state=state)
        if on:
            _set_status(i18n.t(gui_lang, "switching"))

    def refresh(
        final_message: str | None = None,
        final_kind: str = "normal",
    ) -> None:
        if not root.winfo_exists():
            return
        statuses: dict[str, str] = {}
        error: str | None = None
        try:
            statuses = classify_all(args)
        except (SystemExit, Exception) as e:
            error = str(e) if e.args else e.__class__.__name__
        try:
            _build_language_list(_active_key(statuses))
            if final_message is not None:
                _set_status(final_message, kind=final_kind)
            elif version_warning:
                _set_status(version_warning, kind="err")
            elif error is not None:
                _set_status(
                    i18n.localize_error(
                        gui_lang,
                        error,
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
        except Exception as exc:
            _set_status(str(exc), kind="err")

    def _resize_for_status() -> None:
        if root.winfo_exists() and root.winfo_viewable():
            _apply_window_size(root)

    def _localize_error(msg: str) -> str:
        return i18n.localize_error(
            gui_lang,
            msg,
            version=selected_version.get(),
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
        _resize_for_status()

    def _selected_pipelines() -> set[str]:
        return {"main-ui", "plugins"}

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
            pipelines=_selected_pipelines(),
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

    def initial_load() -> None:
        _set_celsys_display()
        if detected_version:
            selected_version.set(detected_version)
            set_active_version(detected_version)
            args.csp_version = detected_version
        else:
            set_active_version(selected_version.get())
            args.csp_version = selected_version.get()
        try:
            _refresh_version_state()
            refresh()
            _apply_window_size(root)
        except Exception as exc:
            _set_status(str(exc), kind="err")

    root.after(1, initial_load)
    root.mainloop()
