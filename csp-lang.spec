# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec for the end-user csp-lang.exe.

Builds a single-file Windows executable that bundles:

  * `src/lang.py` as the entrypoint
  * the four pipeline modules (install / plugins / tools / materials)
  * `versions/<active>/langs/english/` stock (ui + plugins + tools + materials)
  * every community pack under the active version tree

Bundled paths use the `langs/` prefix at runtime (sys._MEIPASS/langs/...).

Build:    pyinstaller csp-lang.spec
Outputs:  dist/csp-lang.exe
"""

from pathlib import Path

block_cipher = None

ACTIVE_VERSION = "5.0.0"
LANGS = Path("versions") / ACTIVE_VERSION / "langs"

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
    binaries=[],
    datas=[],
    hiddenimports=[
        'install',
        'plugins',
        'tools',
        'materials',
        'version',
        'pefile',
        'tkinter',
        'tkinter.ttk',
        'tkinter.messagebox',
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

if LANGS.is_dir():
    english = LANGS / "english"
    for sub in ("ui", "plugins", "tools", "materials"):
        folder = english / sub
        if folder.is_dir() and any(folder.rglob("*")):
            a.datas += Tree(str(folder), prefix=f"langs/english/{sub}")

    for lang_dir in sorted(LANGS.iterdir()):
        if not lang_dir.is_dir() or lang_dir.name in OFFICIAL_LANGS:
            continue
        if any((lang_dir / sub).is_dir() for sub in ("ui", "plugins", "tools", "materials")):
            a.datas += Tree(str(lang_dir), prefix=f"langs/{lang_dir.name}")


pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)


exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='csp-lang',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    uac_admin=False,
    icon=None,
)
