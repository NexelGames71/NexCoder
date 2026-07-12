# -*- mode: python ; coding: utf-8 -*-

import os
from PyInstaller.utils.hooks import collect_data_files

block_cipher = None

# Include built React assets
ui_data = (
    os.path.join('nexcoder', 'resources', 'ui'),
    os.path.join('nexcoder', 'resources', 'ui')
)

datas = [ui_data]

# Include runtime app icon if present. The Windows executable icon still uses
# icon.ico when available, but Qt can load PNG for the window/taskbar icon.
if os.path.exists(os.path.join('nexcoder', 'resources', 'icon.png')):
    datas.append((os.path.join('nexcoder', 'resources', 'icon.png'), os.path.join('nexcoder', 'resources')))

# Include default env template if present
if os.path.exists('.env.example'):
    datas.append(('.env.example', '.'))

# Gather any appwrite or package specific data files
datas += collect_data_files('appwrite')
datas += collect_data_files('watchdog')

a = Analysis(
    ['nexcoder/main.py'],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=[
        'PySide6.QtWebEngineWidgets',
        'PySide6.QtWebChannel',
        'appwrite',
        'watchdog',
        'git',
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

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='NexCoder',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False, # Hide console window
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=os.path.join('nexcoder', 'resources', 'icon.ico') if os.path.exists(os.path.join('nexcoder', 'resources', 'icon.ico')) else None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='NexCoder',
)
