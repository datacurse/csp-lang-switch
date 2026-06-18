# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec for the end-user csp-lang-switch.exe.

Builds a single-file Windows executable that bundles:

  * `src/lang.py` as the entrypoint
  * the install + plugins pipeline modules
  * `versions/<ver>/langs/english/` stock (ui + plugins) per supported version
  * every community pack under each supported version tree

Bundled paths use the `langs/<version>/` prefix at runtime.

Build:    pyinstaller csp-lang-switch.spec
Outputs:  dist/csp-lang-switch.exe
"""

from pathlib import Path

from PyInstaller.utils.hooks import collect_all

block_cipher = None

_ctk_datas, _ctk_binaries, _ctk_hidden = collect_all("customtkinter")

SUPPORTED_VERSIONS = ("5.0.0", "5.0.4")

OFFICIAL_LANGS = {
    "japanese",
    "english",
    "korean",
    "chinese_t",
    "french",
    "spanish",
    "german",
    "thai",
    "indonesian",
    "portuguese_b",
    "chinese_s",
}


a = Analysis(
    ['src/lang.py'],
    pathex=['src'],
    binaries=_ctk_binaries,
    datas=_ctk_datas,
    hiddenimports=[
        'install',
        'plugins',
        'gui_i18n',
        'gui_picker',
        'version',
        'pefile',
        'customtkinter',
        'tkinter',
        'tkinter.messagebox',
        *_ctk_hidden,
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

for ver in SUPPORTED_VERSIONS:
    langs = Path("versions") / ver / "langs"
    if not langs.is_dir():
        continue
    english = langs / "english"
    for sub in ("ui", "plugins"):
        folder = english / sub
        if folder.is_dir() and any(folder.rglob("*")):
            a.datas += Tree(str(folder), prefix=f"langs/{ver}/english/{sub}")

    for lang_dir in sorted(langs.iterdir()):
        if not lang_dir.is_dir() or lang_dir.name in OFFICIAL_LANGS:
            continue
        if any((lang_dir / sub).is_dir() for sub in ("ui", "plugins")):
            a.datas += Tree(str(lang_dir), prefix=f"langs/{ver}/{lang_dir.name}")


pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)


exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='csp-lang-switch',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    uac_admin=False,
    icon=None,
)
