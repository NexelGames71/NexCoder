/** Theme identifiers shared by settings, Monaco, and the IDE shell. */
export const EDITOR_THEME_IDS = [
  'nexcoder',
  'vs-dark',
  'light',
  'hc-black',
  'dark-plus',
  'github-dark',
  'vs',
] as const;

export type EditorTheme = typeof EDITOR_THEME_IDS[number];
export type ShellTheme = Exclude<EditorTheme, 'nexcoder'>;

/**
 * NexCoder uses the unqualified :root variables for its default theme. Every
 * other settings value must stamp the same id on data-theme so index.css can
 * select its dedicated shell palette.
 */
const SHELL_THEME_BY_EDITOR_THEME = {
  nexcoder: null,
  'vs-dark': 'vs-dark',
  light: 'light',
  'hc-black': 'hc-black',
  'dark-plus': 'dark-plus',
  'github-dark': 'github-dark',
  vs: 'vs',
} as const satisfies Record<EditorTheme, ShellTheme | null>;

export function toShellTheme(setting: EditorTheme): ShellTheme | null {
  return SHELL_THEME_BY_EDITOR_THEME[setting];
}
