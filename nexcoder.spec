# -*- mode: python ; coding: utf-8 -*-

import os
import shutil
import importlib.util
from PyInstaller.utils.hooks import collect_data_files

block_cipher = None

# Include built React assets
ui_data = (
    os.path.join('nexcoder', 'resources', 'ui'),
    os.path.join('nexcoder', 'resources', 'ui')
)

datas = [ui_data]
binaries = []

# pywinpty's hook collects its extension modules and DLLs, but not the helper
# executables required by its Windows PTY backends. Frozen GUI builds need the
# WinPTY agent beside the package at runtime or terminal startup fails before
# PowerShell is created.
winpty_spec = importlib.util.find_spec('winpty')
if winpty_spec and winpty_spec.origin:
    winpty_dir = os.path.dirname(winpty_spec.origin)
    for helper in ('winpty-agent.exe', 'OpenConsole.exe'):
        helper_path = os.path.join(winpty_dir, helper)
        if not os.path.isfile(helper_path):
            raise FileNotFoundError(f'Required pywinpty helper is missing: {helper_path}')
        binaries.append((helper_path, 'winpty'))

# Include runtime app icon if present. The Windows executable icon still uses
# icon.ico when available, but Qt can load PNG for the window/taskbar icon.
if os.path.exists(os.path.join('nexcoder', 'resources', 'icon.png')):
    datas.append((os.path.join('nexcoder', 'resources', 'icon.png'), os.path.join('nexcoder', 'resources')))

# Include default env template if present
if os.path.exists('.env.example'):
    datas.append(('.env.example', '.'))

# Ship language servers and their Node runtime. Keeping the runtime beside the
# modules makes the installed app independent of the user's PATH.
language_servers = os.path.join('language-servers')
language_server_modules = os.path.join(language_servers, 'node_modules')
if not os.path.isdir(language_server_modules):
    raise FileNotFoundError(
        'language-servers/node_modules is missing; run build.py or npm ci first')
datas.append((language_server_modules,
              os.path.join('language-servers', 'node_modules')))
for manifest in ('package.json', 'package-lock.json'):
    datas.append((os.path.join(language_servers, manifest), 'language-servers'))
node_runtime = shutil.which('node')
if not node_runtime:
    raise FileNotFoundError('Node.js is required to package language servers')
datas.append((node_runtime, 'language-servers'))

# Gather any appwrite or package specific data files
datas += collect_data_files('appwrite')
datas += collect_data_files('watchdog')

a = Analysis(
    ['nexcoder/main.py'],
    pathex=[],
    binaries=binaries,
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
