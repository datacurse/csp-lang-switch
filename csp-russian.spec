# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec for the end-user csp-russian.exe.

Builds a single-file Windows executable that bundles:

  * `src/lang.py` as the entrypoint
  * the four pipeline modules (install / plugins / tools / materials)
  * the patched Russian build, `langs/russian/` (ui / plugins / tools /
    materials)
  * `langs/english/ui/` (so reverting the main UI works with no network)

Outputs:  dist/csp-russian.exe

Build:    pyinstaller csp-russian.spec
"""

block_cipher = None


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
        'pefile',
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

# Bundle the read-only patched build + the english stock UI as data trees.
# These end up at sys._MEIPASS/<prefix>/... at runtime, which lang.py reads
# via DATA_ROOT.
a.datas += Tree('langs/russian',     prefix='langs/russian')
a.datas += Tree('langs/english/ui',  prefix='langs/english/ui')


pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)


exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='csp-russian',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,                   # UPX often miscompresses ; keep off
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,                # we need a console for the menu
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    uac_admin=False,             # don't force UAC at launch: status/menu
                                 # don't need admin; ensure_admin() in
                                 # install.py re-launches elevated only when
                                 # the user commits to a switch.
    icon=None,
)
