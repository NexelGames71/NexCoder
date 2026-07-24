import React, { type CSSProperties, type ComponentType } from 'react';

import fileIconUrl from 'material-icon-theme/icons/file.svg';
import folderIconUrl from 'material-icon-theme/icons/folder.svg';
import folderOpenIconUrl from 'material-icon-theme/icons/folder-open.svg';
import pythonIconUrl from 'material-icon-theme/icons/python.svg';
import pythonMiscIconUrl from 'material-icon-theme/icons/python-misc.svg';
import javascriptIconUrl from 'material-icon-theme/icons/javascript.svg';
import typescriptIconUrl from 'material-icon-theme/icons/typescript.svg';
import reactIconUrl from 'material-icon-theme/icons/react.svg';
import vueIconUrl from 'material-icon-theme/icons/vue.svg';
import svelteIconUrl from 'material-icon-theme/icons/svelte.svg';
import htmlIconUrl from 'material-icon-theme/icons/html.svg';
import cssIconUrl from 'material-icon-theme/icons/css.svg';
import sassIconUrl from 'material-icon-theme/icons/sass.svg';
import rustIconUrl from 'material-icon-theme/icons/rust.svg';
import goIconUrl from 'material-icon-theme/icons/go.svg';
import cIconUrl from 'material-icon-theme/icons/c.svg';
import cppIconUrl from 'material-icon-theme/icons/cpp.svg';
import csharpIconUrl from 'material-icon-theme/icons/csharp.svg';
import javaIconUrl from 'material-icon-theme/icons/java.svg';
import kotlinIconUrl from 'material-icon-theme/icons/kotlin.svg';
import swiftIconUrl from 'material-icon-theme/icons/swift.svg';
import rubyIconUrl from 'material-icon-theme/icons/ruby.svg';
import phpIconUrl from 'material-icon-theme/icons/php.svg';
import luaIconUrl from 'material-icon-theme/icons/lua.svg';
import dartIconUrl from 'material-icon-theme/icons/dart.svg';
import zigIconUrl from 'material-icon-theme/icons/zig.svg';
import scalaIconUrl from 'material-icon-theme/icons/scala.svg';
import rIconUrl from 'material-icon-theme/icons/r.svg';
import perlIconUrl from 'material-icon-theme/icons/perl.svg';
import objectiveCIconUrl from 'material-icon-theme/icons/objective-c.svg';
import powershellIconUrl from 'material-icon-theme/icons/powershell.svg';
import consoleIconUrl from 'material-icon-theme/icons/console.svg';
import jsonIconUrl from 'material-icon-theme/icons/json.svg';
import yamlIconUrl from 'material-icon-theme/icons/yaml.svg';
import tomlIconUrl from 'material-icon-theme/icons/toml.svg';
import xmlIconUrl from 'material-icon-theme/icons/xml.svg';
import databaseIconUrl from 'material-icon-theme/icons/database.svg';
import tableIconUrl from 'material-icon-theme/icons/table.svg';
import graphqlIconUrl from 'material-icon-theme/icons/graphql.svg';
import protoIconUrl from 'material-icon-theme/icons/proto.svg';
import markdownIconUrl from 'material-icon-theme/icons/markdown.svg';
import documentIconUrl from 'material-icon-theme/icons/document.svg';
import pdfIconUrl from 'material-icon-theme/icons/pdf.svg';
import imageIconUrl from 'material-icon-theme/icons/image.svg';
import svgIconUrl from 'material-icon-theme/icons/svg.svg';
import audioIconUrl from 'material-icon-theme/icons/audio.svg';
import videoIconUrl from 'material-icon-theme/icons/video.svg';
import fontIconUrl from 'material-icon-theme/icons/font.svg';
import zipIconUrl from 'material-icon-theme/icons/zip.svg';
import exeIconUrl from 'material-icon-theme/icons/exe.svg';
import dllIconUrl from 'material-icon-theme/icons/dll.svg';
import webassemblyIconUrl from 'material-icon-theme/icons/webassembly.svg';
import settingsIconUrl from 'material-icon-theme/icons/settings.svg';
import lockIconUrl from 'material-icon-theme/icons/lock.svg';
import gitIconUrl from 'material-icon-theme/icons/git.svg';
import npmIconUrl from 'material-icon-theme/icons/npm.svg';
import yarnIconUrl from 'material-icon-theme/icons/yarn.svg';
import pnpmIconUrl from 'material-icon-theme/icons/pnpm.svg';
import nodeIconUrl from 'material-icon-theme/icons/nodejs.svg';
import dockerIconUrl from 'material-icon-theme/icons/docker.svg';
import tsconfigIconUrl from 'material-icon-theme/icons/tsconfig.svg';
import viteIconUrl from 'material-icon-theme/icons/vite.svg';
import eslintIconUrl from 'material-icon-theme/icons/eslint.svg';
import prettierIconUrl from 'material-icon-theme/icons/prettier.svg';
import babelIconUrl from 'material-icon-theme/icons/babel.svg';
import tailwindIconUrl from 'material-icon-theme/icons/tailwindcss.svg';
import webpackIconUrl from 'material-icon-theme/icons/webpack.svg';
import rollupIconUrl from 'material-icon-theme/icons/rollup.svg';
import vitestIconUrl from 'material-icon-theme/icons/vitest.svg';
import jestIconUrl from 'material-icon-theme/icons/jest.svg';
import gradleIconUrl from 'material-icon-theme/icons/gradle.svg';
import cmakeIconUrl from 'material-icon-theme/icons/cmake.svg';
import makefileIconUrl from 'material-icon-theme/icons/makefile.svg';
import jupyterIconUrl from 'material-icon-theme/icons/jupyter.svg';
import readmeIconUrl from 'material-icon-theme/icons/readme.svg';
import licenseIconUrl from 'material-icon-theme/icons/license.svg';
import editorconfigIconUrl from 'material-icon-theme/icons/editorconfig.svg';

import folderSrcIconUrl from 'material-icon-theme/icons/folder-src.svg';
import folderSrcOpenIconUrl from 'material-icon-theme/icons/folder-src-open.svg';
import folderTestIconUrl from 'material-icon-theme/icons/folder-test.svg';
import folderTestOpenIconUrl from 'material-icon-theme/icons/folder-test-open.svg';
import folderImagesIconUrl from 'material-icon-theme/icons/folder-images.svg';
import folderImagesOpenIconUrl from 'material-icon-theme/icons/folder-images-open.svg';
import folderNodeIconUrl from 'material-icon-theme/icons/folder-node.svg';
import folderNodeOpenIconUrl from 'material-icon-theme/icons/folder-node-open.svg';
import folderGitIconUrl from 'material-icon-theme/icons/folder-git.svg';
import folderGitOpenIconUrl from 'material-icon-theme/icons/folder-git-open.svg';
import folderGithubIconUrl from 'material-icon-theme/icons/folder-github.svg';
import folderGithubOpenIconUrl from 'material-icon-theme/icons/folder-github-open.svg';
import folderDistIconUrl from 'material-icon-theme/icons/folder-dist.svg';
import folderDistOpenIconUrl from 'material-icon-theme/icons/folder-dist-open.svg';
import folderDocsIconUrl from 'material-icon-theme/icons/folder-docs.svg';
import folderDocsOpenIconUrl from 'material-icon-theme/icons/folder-docs-open.svg';
import folderPublicIconUrl from 'material-icon-theme/icons/folder-public.svg';
import folderPublicOpenIconUrl from 'material-icon-theme/icons/folder-public-open.svg';
import folderComponentsIconUrl from 'material-icon-theme/icons/folder-components.svg';
import folderComponentsOpenIconUrl from 'material-icon-theme/icons/folder-components-open.svg';
import folderConfigIconUrl from 'material-icon-theme/icons/folder-config.svg';
import folderConfigOpenIconUrl from 'material-icon-theme/icons/folder-config-open.svg';
import folderScriptsIconUrl from 'material-icon-theme/icons/folder-scripts.svg';
import folderScriptsOpenIconUrl from 'material-icon-theme/icons/folder-scripts-open.svg';
import folderApiIconUrl from 'material-icon-theme/icons/folder-api.svg';
import folderApiOpenIconUrl from 'material-icon-theme/icons/folder-api-open.svg';
import folderServerIconUrl from 'material-icon-theme/icons/folder-server.svg';
import folderServerOpenIconUrl from 'material-icon-theme/icons/folder-server-open.svg';
import folderClientIconUrl from 'material-icon-theme/icons/folder-client.svg';
import folderClientOpenIconUrl from 'material-icon-theme/icons/folder-client-open.svg';
import folderDatabaseIconUrl from 'material-icon-theme/icons/folder-database.svg';
import folderDatabaseOpenIconUrl from 'material-icon-theme/icons/folder-database-open.svg';

interface FileIconProps {
  size?: number | string;
  className?: string;
  style?: CSSProperties;
  'aria-label'?: string;
}

export type FileIconComponent = ComponentType<FileIconProps>;

function createMaterialIcon(source: string, displayName: string): FileIconComponent {
  const MaterialIcon = ({ size = 16, className, style, 'aria-label': ariaLabel }: FileIconProps) => (
    React.createElement('img', {
      src: source,
      className,
      width: size,
      height: size,
      alt: ariaLabel ?? '',
      'aria-hidden': ariaLabel ? undefined : true,
      draggable: false,
      style: {
        display: 'block',
        flexShrink: 0,
        objectFit: 'contain',
        ...style,
      },
    })
  );
  MaterialIcon.displayName = `${displayName}FileIcon`;
  return MaterialIcon;
}

type IconDefinition = [FileIconComponent, string];
type FolderDefinition = [FileIconComponent, FileIconComponent];

const icon = (source: string, name: string, color: string): IconDefinition => [
  createMaterialIcon(source, name),
  color,
];

const FileIcon = createMaterialIcon(fileIconUrl, 'Default');
const FolderIcon = createMaterialIcon(folderIconUrl, 'Folder');
const FolderOpenIcon = createMaterialIcon(folderOpenIconUrl, 'FolderOpen');

const ICONS = {
  python: icon(pythonIconUrl, 'Python', '#4b8bbe'),
  pythonMisc: icon(pythonMiscIconUrl, 'PythonMisc', '#4b8bbe'),
  javascript: icon(javascriptIconUrl, 'JavaScript', '#f7df1e'),
  typescript: icon(typescriptIconUrl, 'TypeScript', '#3178c6'),
  react: icon(reactIconUrl, 'React', '#61dafb'),
  vue: icon(vueIconUrl, 'Vue', '#41b883'),
  svelte: icon(svelteIconUrl, 'Svelte', '#ff3e00'),
  html: icon(htmlIconUrl, 'HTML', '#e44d26'),
  css: icon(cssIconUrl, 'CSS', '#42a5f5'),
  sass: icon(sassIconUrl, 'Sass', '#cc6699'),
  rust: icon(rustIconUrl, 'Rust', '#dea584'),
  go: icon(goIconUrl, 'Go', '#00add8'),
  c: icon(cIconUrl, 'C', '#659ad2'),
  cpp: icon(cppIconUrl, 'Cpp', '#00599c'),
  csharp: icon(csharpIconUrl, 'CSharp', '#9b4f96'),
  java: icon(javaIconUrl, 'Java', '#f89820'),
  kotlin: icon(kotlinIconUrl, 'Kotlin', '#a97bff'),
  swift: icon(swiftIconUrl, 'Swift', '#f05138'),
  ruby: icon(rubyIconUrl, 'Ruby', '#cc342d'),
  php: icon(phpIconUrl, 'PHP', '#777bb4'),
  lua: icon(luaIconUrl, 'Lua', '#000080'),
  dart: icon(dartIconUrl, 'Dart', '#00b4ab'),
  zig: icon(zigIconUrl, 'Zig', '#f7a41d'),
  scala: icon(scalaIconUrl, 'Scala', '#dc322f'),
  r: icon(rIconUrl, 'R', '#198ce7'),
  perl: icon(perlIconUrl, 'Perl', '#0298c3'),
  objectiveC: icon(objectiveCIconUrl, 'ObjectiveC', '#438eff'),
  powershell: icon(powershellIconUrl, 'PowerShell', '#2b579a'),
  console: icon(consoleIconUrl, 'Console', '#89e051'),
  json: icon(jsonIconUrl, 'JSON', '#fbc02d'),
  yaml: icon(yamlIconUrl, 'YAML', '#cb171e'),
  toml: icon(tomlIconUrl, 'TOML', '#9c4221'),
  xml: icon(xmlIconUrl, 'XML', '#ff9800'),
  database: icon(databaseIconUrl, 'Database', '#42a5f5'),
  table: icon(tableIconUrl, 'Table', '#66bb6a'),
  graphql: icon(graphqlIconUrl, 'GraphQL', '#e10098'),
  proto: icon(protoIconUrl, 'Proto', '#4a90e2'),
  markdown: icon(markdownIconUrl, 'Markdown', '#519aba'),
  document: icon(documentIconUrl, 'Document', '#90a4ae'),
  pdf: icon(pdfIconUrl, 'PDF', '#f40f02'),
  image: icon(imageIconUrl, 'Image', '#a074c4'),
  svg: icon(svgIconUrl, 'SVG', '#ffb13b'),
  audio: icon(audioIconUrl, 'Audio', '#ffca28'),
  video: icon(videoIconUrl, 'Video', '#ab47bc'),
  font: icon(fontIconUrl, 'Font', '#607d8b'),
  zip: icon(zipIconUrl, 'Archive', '#f1c40f'),
  exe: icon(exeIconUrl, 'Executable', '#90a4ae'),
  dll: icon(dllIconUrl, 'Library', '#90a4ae'),
  wasm: icon(webassemblyIconUrl, 'WebAssembly', '#654ff0'),
  settings: icon(settingsIconUrl, 'Settings', '#90a4ae'),
  lock: icon(lockIconUrl, 'Lock', '#ffca28'),
  git: icon(gitIconUrl, 'Git', '#f14e32'),
  npm: icon(npmIconUrl, 'Npm', '#cb3837'),
  yarn: icon(yarnIconUrl, 'Yarn', '#2c8ebb'),
  pnpm: icon(pnpmIconUrl, 'Pnpm', '#f9ad00'),
  node: icon(nodeIconUrl, 'Node', '#83cd29'),
  docker: icon(dockerIconUrl, 'Docker', '#2496ed'),
  tsconfig: icon(tsconfigIconUrl, 'TsConfig', '#3178c6'),
  vite: icon(viteIconUrl, 'Vite', '#bd34fe'),
  eslint: icon(eslintIconUrl, 'Eslint', '#4b32c3'),
  prettier: icon(prettierIconUrl, 'Prettier', '#56b3b4'),
  babel: icon(babelIconUrl, 'Babel', '#f9dc3e'),
  tailwind: icon(tailwindIconUrl, 'Tailwind', '#38bdf8'),
  webpack: icon(webpackIconUrl, 'Webpack', '#8dd6f9'),
  rollup: icon(rollupIconUrl, 'Rollup', '#ec4a3f'),
  vitest: icon(vitestIconUrl, 'Vitest', '#729b1b'),
  jest: icon(jestIconUrl, 'Jest', '#99425b'),
  gradle: icon(gradleIconUrl, 'Gradle', '#02303a'),
  cmake: icon(cmakeIconUrl, 'CMake', '#064f8c'),
  makefile: icon(makefileIconUrl, 'Makefile', '#6d8086'),
  jupyter: icon(jupyterIconUrl, 'Jupyter', '#f37626'),
  readme: icon(readmeIconUrl, 'Readme', '#42a5f5'),
  license: icon(licenseIconUrl, 'License', '#ffca28'),
  editorconfig: icon(editorconfigIconUrl, 'EditorConfig', '#90a4ae'),
} as const;

const BY_EXT: Record<string, IconDefinition> = {
  '.ts': ICONS.typescript, '.mts': ICONS.typescript, '.cts': ICONS.typescript,
  '.tsx': ICONS.react, '.js': ICONS.javascript, '.mjs': ICONS.javascript,
  '.cjs': ICONS.javascript, '.jsx': ICONS.react, '.vue': ICONS.vue,
  '.svelte': ICONS.svelte, '.html': ICONS.html, '.htm': ICONS.html,
  '.css': ICONS.css, '.scss': ICONS.sass, '.sass': ICONS.sass, '.less': ICONS.css,
  '.py': ICONS.python, '.pyw': ICONS.python, '.pyi': ICONS.python,
  '.ipynb': ICONS.jupyter, '.rs': ICONS.rust, '.go': ICONS.go,
  '.c': ICONS.c, '.h': ICONS.c, '.cpp': ICONS.cpp, '.cc': ICONS.cpp,
  '.cxx': ICONS.cpp, '.hpp': ICONS.cpp, '.cs': ICONS.csharp, '.csx': ICONS.csharp,
  '.java': ICONS.java, '.kt': ICONS.kotlin, '.kts': ICONS.kotlin,
  '.swift': ICONS.swift, '.m': ICONS.objectiveC, '.mm': ICONS.objectiveC,
  '.rb': ICONS.ruby, '.php': ICONS.php, '.lua': ICONS.lua, '.dart': ICONS.dart,
  '.zig': ICONS.zig, '.scala': ICONS.scala, '.r': ICONS.r, '.pl': ICONS.perl,
  '.sh': ICONS.console, '.bash': ICONS.console, '.zsh': ICONS.console,
  '.fish': ICONS.console, '.ps1': ICONS.powershell, '.psm1': ICONS.powershell,
  '.psd1': ICONS.powershell, '.bat': ICONS.console, '.cmd': ICONS.console,
  '.json': ICONS.json, '.jsonc': ICONS.json, '.yaml': ICONS.yaml, '.yml': ICONS.yaml,
  '.toml': ICONS.toml, '.ini': ICONS.settings, '.cfg': ICONS.settings,
  '.conf': ICONS.settings, '.xml': ICONS.xml, '.csv': ICONS.table, '.tsv': ICONS.table,
  '.sql': ICONS.database, '.db': ICONS.database, '.sqlite': ICONS.database,
  '.sqlite3': ICONS.database, '.graphql': ICONS.graphql, '.gql': ICONS.graphql,
  '.proto': ICONS.proto, '.gradle': ICONS.gradle, '.cmake': ICONS.cmake,
  '.mk': ICONS.makefile, '.make': ICONS.makefile, '.md': ICONS.markdown,
  '.mdx': ICONS.markdown, '.rst': ICONS.document, '.txt': ICONS.document,
  '.log': ICONS.document, '.pdf': ICONS.pdf, '.png': ICONS.image,
  '.jpg': ICONS.image, '.jpeg': ICONS.image, '.jpe': ICONS.image,
  '.jfif': ICONS.image, '.gif': ICONS.image, '.webp': ICONS.image,
  '.bmp': ICONS.image, '.dib': ICONS.image, '.ico': ICONS.image,
  '.avif': ICONS.image, '.heic': ICONS.image, '.heif': ICONS.image,
  '.tif': ICONS.image, '.tiff': ICONS.image, '.svg': ICONS.svg,
  '.mp3': ICONS.audio, '.wav': ICONS.audio, '.ogg': ICONS.audio,
  '.oga': ICONS.audio, '.flac': ICONS.audio, '.m4a': ICONS.audio,
  '.aac': ICONS.audio, '.opus': ICONS.audio, '.weba': ICONS.audio,
  '.mid': ICONS.audio, '.midi': ICONS.audio, '.mp4': ICONS.video,
  '.webm': ICONS.video, '.mov': ICONS.video, '.m4v': ICONS.video,
  '.ogv': ICONS.video, '.avi': ICONS.video, '.mkv': ICONS.video,
  '.wmv': ICONS.video, '.ttf': ICONS.font, '.otf': ICONS.font,
  '.woff': ICONS.font, '.woff2': ICONS.font, '.zip': ICONS.zip,
  '.tar': ICONS.zip, '.gz': ICONS.zip, '.tgz': ICONS.zip, '.rar': ICONS.zip,
  '.7z': ICONS.zip, '.exe': ICONS.exe, '.msi': ICONS.exe, '.dll': ICONS.dll,
  '.so': ICONS.dll, '.dylib': ICONS.dll, '.wasm': ICONS.wasm,
  '.lock': ICONS.lock, '.env': ICONS.settings,
};

const BY_NAME: Record<string, IconDefinition> = {
  'package.json': ICONS.npm,
  'package-lock.json': ICONS.npm,
  'npm-shrinkwrap.json': ICONS.npm,
  'yarn.lock': ICONS.yarn,
  'pnpm-lock.yaml': ICONS.pnpm,
  'pnpm-workspace.yaml': ICONS.pnpm,
  'pyproject.toml': ICONS.pythonMisc,
  'pipfile': ICONS.pythonMisc,
  'pipfile.lock': ICONS.pythonMisc,
  'poetry.lock': ICONS.pythonMisc,
  'cargo.toml': ICONS.rust,
  'cargo.lock': ICONS.rust,
  'go.mod': ICONS.go,
  'go.sum': ICONS.go,
  'dockerfile': ICONS.docker,
  'makefile': ICONS.makefile,
  'gnumakefile': ICONS.makefile,
  'cmakelists.txt': ICONS.cmake,
  '.gitignore': ICONS.git,
  '.gitattributes': ICONS.git,
  '.gitmodules': ICONS.git,
  '.editorconfig': ICONS.editorconfig,
  '.npmrc': ICONS.npm,
  '.yarnrc': ICONS.yarn,
  '.yarnrc.yml': ICONS.yarn,
  'license': ICONS.license,
  'license.md': ICONS.license,
  'license.txt': ICONS.license,
};

const FOLDER_ICONS: Record<string, FolderDefinition> = {
  src: [createMaterialIcon(folderSrcIconUrl, 'SourceFolder'), createMaterialIcon(folderSrcOpenIconUrl, 'SourceFolderOpen')],
  source: [createMaterialIcon(folderSrcIconUrl, 'SourceFolder'), createMaterialIcon(folderSrcOpenIconUrl, 'SourceFolderOpen')],
  test: [createMaterialIcon(folderTestIconUrl, 'TestFolder'), createMaterialIcon(folderTestOpenIconUrl, 'TestFolderOpen')],
  tests: [createMaterialIcon(folderTestIconUrl, 'TestFolder'), createMaterialIcon(folderTestOpenIconUrl, 'TestFolderOpen')],
  __tests__: [createMaterialIcon(folderTestIconUrl, 'TestFolder'), createMaterialIcon(folderTestOpenIconUrl, 'TestFolderOpen')],
  assets: [createMaterialIcon(folderImagesIconUrl, 'AssetsFolder'), createMaterialIcon(folderImagesOpenIconUrl, 'AssetsFolderOpen')],
  images: [createMaterialIcon(folderImagesIconUrl, 'ImagesFolder'), createMaterialIcon(folderImagesOpenIconUrl, 'ImagesFolderOpen')],
  node_modules: [createMaterialIcon(folderNodeIconUrl, 'NodeModulesFolder'), createMaterialIcon(folderNodeOpenIconUrl, 'NodeModulesFolderOpen')],
  '.git': [createMaterialIcon(folderGitIconUrl, 'GitFolder'), createMaterialIcon(folderGitOpenIconUrl, 'GitFolderOpen')],
  '.github': [createMaterialIcon(folderGithubIconUrl, 'GithubFolder'), createMaterialIcon(folderGithubOpenIconUrl, 'GithubFolderOpen')],
  dist: [createMaterialIcon(folderDistIconUrl, 'DistributionFolder'), createMaterialIcon(folderDistOpenIconUrl, 'DistributionFolderOpen')],
  build: [createMaterialIcon(folderDistIconUrl, 'BuildFolder'), createMaterialIcon(folderDistOpenIconUrl, 'BuildFolderOpen')],
  docs: [createMaterialIcon(folderDocsIconUrl, 'DocsFolder'), createMaterialIcon(folderDocsOpenIconUrl, 'DocsFolderOpen')],
  documentation: [createMaterialIcon(folderDocsIconUrl, 'DocsFolder'), createMaterialIcon(folderDocsOpenIconUrl, 'DocsFolderOpen')],
  public: [createMaterialIcon(folderPublicIconUrl, 'PublicFolder'), createMaterialIcon(folderPublicOpenIconUrl, 'PublicFolderOpen')],
  components: [createMaterialIcon(folderComponentsIconUrl, 'ComponentsFolder'), createMaterialIcon(folderComponentsOpenIconUrl, 'ComponentsFolderOpen')],
  config: [createMaterialIcon(folderConfigIconUrl, 'ConfigFolder'), createMaterialIcon(folderConfigOpenIconUrl, 'ConfigFolderOpen')],
  configs: [createMaterialIcon(folderConfigIconUrl, 'ConfigFolder'), createMaterialIcon(folderConfigOpenIconUrl, 'ConfigFolderOpen')],
  scripts: [createMaterialIcon(folderScriptsIconUrl, 'ScriptsFolder'), createMaterialIcon(folderScriptsOpenIconUrl, 'ScriptsFolderOpen')],
  api: [createMaterialIcon(folderApiIconUrl, 'ApiFolder'), createMaterialIcon(folderApiOpenIconUrl, 'ApiFolderOpen')],
  server: [createMaterialIcon(folderServerIconUrl, 'ServerFolder'), createMaterialIcon(folderServerOpenIconUrl, 'ServerFolderOpen')],
  backend: [createMaterialIcon(folderServerIconUrl, 'BackendFolder'), createMaterialIcon(folderServerOpenIconUrl, 'BackendFolderOpen')],
  client: [createMaterialIcon(folderClientIconUrl, 'ClientFolder'), createMaterialIcon(folderClientOpenIconUrl, 'ClientFolderOpen')],
  frontend: [createMaterialIcon(folderClientIconUrl, 'FrontendFolder'), createMaterialIcon(folderClientOpenIconUrl, 'FrontendFolderOpen')],
  database: [createMaterialIcon(folderDatabaseIconUrl, 'DatabaseFolder'), createMaterialIcon(folderDatabaseOpenIconUrl, 'DatabaseFolderOpen')],
  db: [createMaterialIcon(folderDatabaseIconUrl, 'DatabaseFolder'), createMaterialIcon(folderDatabaseOpenIconUrl, 'DatabaseFolderOpen')],
};

function lookupByName(name: string): IconDefinition | undefined {
  const lower = name.toLowerCase();
  if (BY_NAME[lower]) return BY_NAME[lower];
  if (lower.startsWith('readme')) return ICONS.readme;
  if (lower.startsWith('license') || lower.startsWith('copying')) return ICONS.license;
  if (lower.startsWith('changelog') || lower.startsWith('changes')) return ICONS.markdown;
  if (lower.startsWith('.env')) return ICONS.settings;
  if (lower.startsWith('dockerfile') || /^compose(?:\..+)?\.ya?ml$/.test(lower)) return ICONS.docker;
  if (/^requirements(?:[-_.].*)?\.txt$/.test(lower)) return ICONS.pythonMisc;
  if (/^tsconfig(?:\..+)?\.json$/.test(lower) || /^jsconfig(?:\..+)?\.json$/.test(lower)) return ICONS.tsconfig;
  if (/^vite\.config\./.test(lower)) return ICONS.vite;
  if (/^webpack\.config\./.test(lower)) return ICONS.webpack;
  if (/^rollup\.config\./.test(lower)) return ICONS.rollup;
  if (/^(eslint\.config\.|\.eslintrc)/.test(lower)) return ICONS.eslint;
  if (/^(prettier\.config\.|\.prettierrc)/.test(lower)) return ICONS.prettier;
  if (/^(babel\.config\.|\.babelrc)/.test(lower)) return ICONS.babel;
  if (/^tailwind\.config\./.test(lower)) return ICONS.tailwind;
  if (/^vitest\.config\./.test(lower)) return ICONS.vitest;
  if (/^jest\.config\./.test(lower)) return ICONS.jest;
  return undefined;
}

function lookup(name: string, extension: string): IconDefinition | undefined {
  const byName = lookupByName(name || '');
  if (byName) return byName;
  const normalizedExtension = extension || (() => {
    const dot = name.lastIndexOf('.');
    return dot >= 0 ? name.slice(dot) : '';
  })();
  return BY_EXT[normalizedExtension.toLowerCase()];
}

export function getFileIcon(
  extension: string = '',
  isDirectory: boolean = false,
  isOpen: boolean = false,
  name: string = '',
): FileIconComponent {
  if (isDirectory) {
    const folderDefinition = FOLDER_ICONS[name.toLowerCase()];
    if (folderDefinition) return isOpen ? folderDefinition[1] : folderDefinition[0];
    return isOpen ? FolderOpenIcon : FolderIcon;
  }
  return lookup(name, extension)?.[0] ?? FileIcon;
}

/**
 * Retained for the existing explorer/tab API. Material icons contain their own
 * colors, while the returned value colors legacy/fallback glyph containers.
 */
export function getFileColor(extension: string = '', name: string = ''): string {
  return lookup(name, extension)?.[1] ?? '#90a4ae';
}

export type FilePreviewKind = 'text' | 'image' | 'audio' | 'video' | 'pdf' | 'font' | 'binary';

const IMAGE_EXTS = new Set([
  '.png', '.jpg', '.jpeg', '.jpe', '.jfif', '.gif', '.webp', '.bmp', '.dib',
  '.ico', '.avif', '.svg', '.tif', '.tiff', '.heic', '.heif',
]);
const AUDIO_EXTS = new Set([
  '.mp3', '.wav', '.ogg', '.oga', '.flac', '.m4a', '.aac', '.opus', '.weba', '.mid', '.midi',
]);
const VIDEO_EXTS = new Set([
  '.mp4', '.webm', '.mov', '.m4v', '.ogv', '.avi', '.mkv', '.wmv',
]);
const FONT_EXTS = new Set(['.ttf', '.otf', '.woff', '.woff2']);
const BINARY_EXTS = new Set([
  '.zip', '.tar', '.gz', '.tgz', '.bz2', '.xz', '.rar', '.7z',
  '.exe', '.msi', '.dll', '.so', '.dylib', '.wasm',
  '.db', '.sqlite', '.sqlite3', '.class', '.jar', '.pyc',
  '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx', '.odt', '.ods', '.odp', '.epub',
]);

function extensionOf(pathOrExt: string): string {
  const normalized = pathOrExt.toLowerCase().split(/[?#]/, 1)[0];
  const slash = Math.max(normalized.lastIndexOf('/'), normalized.lastIndexOf('\\'));
  const dot = normalized.lastIndexOf('.');
  return dot > slash ? normalized.slice(dot) : '';
}

/** Classify files before reading them so binary content never enters Monaco as text. */
export function getFilePreviewKind(pathOrExt: string): FilePreviewKind {
  const ext = extensionOf(pathOrExt);
  if (IMAGE_EXTS.has(ext)) return 'image';
  if (AUDIO_EXTS.has(ext)) return 'audio';
  if (VIDEO_EXTS.has(ext)) return 'video';
  if (ext === '.pdf') return 'pdf';
  if (FONT_EXTS.has(ext)) return 'font';
  if (BINARY_EXTS.has(ext)) return 'binary';
  return 'text';
}

/** True for raster/vector images that open in the image viewer. */
export function isImageFile(pathOrExt: string): boolean {
  return getFilePreviewKind(pathOrExt) === 'image';
}

export function isBinaryPreviewFile(pathOrExt: string): boolean {
  return getFilePreviewKind(pathOrExt) !== 'text';
}
