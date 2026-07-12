import os
from typing import Dict, Any


def resolve_path(project_root: str, path: str) -> str:
    # If path is absolute, return it; otherwise join with project_root
    if os.path.isabs(path):
        return path
    return os.path.normpath(os.path.join(project_root or '', path))


def read_file(args: Dict[str, Any]) -> Dict[str, Any]:
    path = args.get('path') or args.get('file')
    project_root = args.get('project_root')
    if not path:
        raise ValueError('read_file requires path')
    resolved = resolve_path(project_root, path)
    if not os.path.exists(resolved):
        # Try to suggest a sibling under project_root
        suggestions = []
        if project_root and os.path.isdir(project_root):
            for root, dirs, files in os.walk(project_root):
                if os.path.basename(path) in files:
                    suggestions.append(os.path.relpath(os.path.join(root, os.path.basename(path)), project_root))
        return {'found': False, 'path': resolved, 'suggestions': suggestions}
    with open(resolved, 'r', encoding='utf-8', errors='replace') as f:
        content = f.read()
    return {'found': True, 'path': resolved, 'content': content}
