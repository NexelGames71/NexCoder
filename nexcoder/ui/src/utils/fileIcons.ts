import { 
  FileCode, FileText, FileImage, Folder, FolderOpen,
  Settings, ShieldAlert, GitBranch, Terminal, Eye,
  FileJson, FileSpreadsheet, Package, Code
} from 'lucide-react';
import React from 'react';

export function getFileIcon(extension: string = '', isDirectory: boolean = false, isOpen: boolean = false) {
  if (isDirectory) {
    return isOpen ? FolderOpen : Folder;
  }

  const ext = extension.toLowerCase();

  switch (ext) {
    case '.ts':
    case '.tsx':
    case '.js':
    case '.jsx':
      return Code;
    case '.json':
      return FileJson;
    case '.css':
    case '.scss':
    case '.less':
      return FileCode;
    case '.html':
    case '.htm':
      return FileCode;
    case '.py':
    case '.pyw':
      return FileCode;
    case '.rs':
      return FileCode;
    case '.go':
      return FileCode;
    case '.md':
      return FileText;
    case '.png':
    case '.jpg':
    case '.jpeg':
    case '.gif':
    case '.ico':
    case '.svg':
    case '.webp':
      return FileImage;
    case '.toml':
    case '.yaml':
    case '.yml':
    case '.ini':
      return Settings;
    case '.env':
    case '.local':
      return ShieldAlert;
    default:
      return FileText;
  }
}

export function getFileColor(extension: string = '') {
  const ext = extension.toLowerCase();

  switch (ext) {
    case '.ts':
    case '.tsx':
      return '#3178c6'; // TypeScript Blue
    case '.js':
    case '.jsx':
      return '#f1e05a'; // JS Yellow
    case '.py':
      return '#3572A5'; // Python Blue
    case '.rs':
      return '#dea584'; // Rust Orange
    case '.go':
      return '#00ADD8'; // Go Cyan
    case '.json':
      return '#00b894'; // Green
    case '.css':
      return '#563d7c'; // CSS Purple
    case '.html':
      return '#e34c26'; // HTML Red
    case '.md':
      return '#8888a0'; // Grey
    case '.env':
      return '#e17055'; // Danger Orange
    default:
      return '#8888a0';
  }
}
