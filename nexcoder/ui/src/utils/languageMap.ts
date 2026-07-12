export function getLanguageFromExtension(extension: string): string {
  const ext = extension.toLowerCase();

  switch (ext) {
    case '.js':
    case '.jsx':
      return 'javascript';
    case '.ts':
    case '.tsx':
      return 'typescript';
    case '.py':
    case '.pyw':
      return 'python';
    case '.rs':
      return 'rust';
    case '.go':
      return 'go';
    case '.html':
    case '.htm':
      return 'html';
    case '.css':
      return 'css';
    case '.json':
      return 'json';
    case '.md':
      return 'markdown';
    case '.toml':
      return 'toml';
    case '.yaml':
    case '.yml':
      return 'yaml';
    case '.sh':
    case '.bash':
      return 'shell';
    case '.bat':
    case '.cmd':
      return 'bat';
    case '.ps1':
      return 'powershell';
    case '.sql':
      return 'sql';
    case '.xml':
      return 'xml';
    case '.cpp':
    case '.cc':
    case '.h':
      return 'cpp';
    case '.c':
      return 'c';
    default:
      return 'plaintext';
  }
}
