import {
  FileCode, FileText, FileImage, Folder, FolderOpen,
  Settings, ShieldAlert, FileJson, FileCog, Hash, Braces,
  Binary, Database, Coffee, Palette, FileArchive, Terminal,
  FileType, FileSpreadsheet, BookMarked, type LucideIcon,
} from 'lucide-react';

// Extension (with leading dot) → [icon, Linguist-ish color]. Filenames
// with no extension (Dockerfile, Makefile…) are handled separately.
const BY_EXT: Record<string, [LucideIcon, string]> = {
  // Web / JS ecosystem
  '.ts': [FileCode, '#3178c6'], '.tsx': [FileCode, '#3178c6'],
  '.mts': [FileCode, '#3178c6'], '.cts': [FileCode, '#3178c6'],
  '.js': [FileCode, '#f1e05a'], '.jsx': [FileCode, '#f1e05a'],
  '.mjs': [FileCode, '#f1e05a'], '.cjs': [FileCode, '#f1e05a'],
  '.vue': [FileCode, '#41b883'], '.svelte': [FileCode, '#ff3e00'],
  '.html': [FileCode, '#e34c26'], '.htm': [FileCode, '#e34c26'],
  '.css': [Palette, '#563d7c'], '.scss': [Palette, '#c6538c'],
  '.sass': [Palette, '#c6538c'], '.less': [Palette, '#1d365d'],
  // Python
  '.py': [FileCode, '#3572A5'], '.pyw': [FileCode, '#3572A5'],
  '.pyi': [FileCode, '#3572A5'], '.ipynb': [FileCode, '#da5b0b'],
  // Systems
  '.rs': [FileCog, '#dea584'], '.go': [FileCode, '#00ADD8'],
  '.c': [FileCode, '#555555'], '.h': [FileCode, '#555555'],
  '.cpp': [FileCode, '#f34b7d'], '.cc': [FileCode, '#f34b7d'],
  '.cxx': [FileCode, '#f34b7d'], '.hpp': [FileCode, '#f34b7d'],
  '.cs': [Hash, '#178600'], '.csx': [Hash, '#178600'],
  '.java': [Coffee, '#b07219'], '.kt': [FileCode, '#a97bff'],
  '.kts': [FileCode, '#a97bff'], '.scala': [FileCode, '#c22d40'],
  '.swift': [FileCode, '#f05138'], '.m': [FileCode, '#438eff'],
  '.zig': [FileCode, '#ec915c'], '.dart': [FileCode, '#00b4ab'],
  // Scripting / shells
  '.sh': [Terminal, '#89e051'], '.bash': [Terminal, '#89e051'],
  '.zsh': [Terminal, '#89e051'], '.ps1': [Terminal, '#012456'],
  '.bat': [Terminal, '#c1f12e'], '.cmd': [Terminal, '#c1f12e'],
  '.rb': [FileCode, '#701516'], '.php': [FileCode, '#4F5D95'],
  '.lua': [FileCode, '#000080'], '.pl': [FileCode, '#0298c3'],
  '.r': [FileCode, '#198CE7'],
  // Data / config
  '.json': [FileJson, '#cbcb41'], '.jsonc': [FileJson, '#cbcb41'],
  '.toml': [Settings, '#9c4221'], '.yaml': [Settings, '#cb171e'],
  '.yml': [Settings, '#cb171e'], '.ini': [Settings, '#6d8086'],
  '.xml': [Braces, '#0060ac'], '.csv': [FileSpreadsheet, '#217346'],
  '.tsv': [FileSpreadsheet, '#217346'], '.sql': [Database, '#e38c00'],
  '.db': [Database, '#dad8d8'], '.sqlite': [Database, '#dad8d8'],
  '.graphql': [Braces, '#e10098'], '.proto': [Braces, '#4a90e2'],
  // Build systems
  '.cmake': [FileCog, '#064F8C'], '.gradle': [FileCog, '#02303a'],
  '.mk': [FileCog, '#427819'], '.make': [FileCog, '#427819'],
  '.dockerfile': [FileCog, '#384d54'],
  // Docs
  '.md': [FileText, '#6a9fb5'], '.mdx': [FileText, '#6a9fb5'],
  '.rst': [FileText, '#6a9fb5'], '.txt': [FileText, '#8888a0'],
  '.pdf': [BookMarked, '#e34c26'], '.log': [FileText, '#8888a0'],
  // Images
  '.png': [FileImage, '#a074c4'], '.jpg': [FileImage, '#a074c4'],
  '.jpeg': [FileImage, '#a074c4'], '.gif': [FileImage, '#a074c4'],
  '.webp': [FileImage, '#a074c4'], '.svg': [FileImage, '#ffb13b'],
  '.ico': [FileImage, '#a074c4'], '.bmp': [FileImage, '#a074c4'],
  '.avif': [FileImage, '#a074c4'],
  // Archives / binaries
  '.zip': [FileArchive, '#f1c40f'], '.tar': [FileArchive, '#f1c40f'],
  '.gz': [FileArchive, '#f1c40f'], '.rar': [FileArchive, '#f1c40f'],
  '.7z': [FileArchive, '#f1c40f'], '.exe': [Binary, '#9aa0a6'],
  '.dll': [Binary, '#9aa0a6'], '.wasm': [Binary, '#654ff0'],
  '.gguf': [Binary, '#00b894'], '.bin': [Binary, '#9aa0a6'],
  // Env / secrets
  '.env': [ShieldAlert, '#e17055'],
};

// Whole-filename matches (files without a normal extension).
const BY_NAME: Record<string, [LucideIcon, string]> = {
  'dockerfile': [FileCog, '#384d54'],
  'makefile': [FileCog, '#427819'],
  'cmakelists.txt': [FileCog, '#064F8C'],
  '.gitignore': [Settings, '#f14e32'],
  '.gitattributes': [Settings, '#f14e32'],
  '.editorconfig': [Settings, '#6d8086'],
  'license': [BookMarked, '#cbcb41'],
  'package.json': [FileJson, '#cb3837'],
  'tsconfig.json': [FileJson, '#3178c6'],
};

function lookup(name: string, ext: string): [LucideIcon, string] | undefined {
  const lower = (name || '').toLowerCase();
  if (BY_NAME[lower]) return BY_NAME[lower];
  return BY_EXT[ext.toLowerCase()];
}

export function getFileIcon(
  extension: string = '', isDirectory: boolean = false,
  isOpen: boolean = false, name: string = '',
): LucideIcon {
  if (isDirectory) return isOpen ? FolderOpen : Folder;
  const hit = lookup(name, extension);
  return hit ? hit[0] : FileType;
}

export function getFileColor(extension: string = '', name: string = ''): string {
  const hit = lookup(name, extension);
  return hit ? hit[1] : '#8b8ba7';
}

const IMAGE_EXTS = new Set([
  '.png', '.jpg', '.jpeg', '.gif', '.webp', '.bmp', '.ico', '.avif', '.svg',
]);

/** True for raster/vector images that open in the preview viewer. */
export function isImageFile(pathOrExt: string): boolean {
  const dot = pathOrExt.lastIndexOf('.');
  const ext = dot === -1 ? '' : pathOrExt.slice(dot).toLowerCase();
  return IMAGE_EXTS.has(ext);
}
