import React, { useEffect, useMemo, useState } from 'react';
import {
  Bot,
  Check,
  CircleAlert,
  Cloud,
  Code2,
  Download,
  FileArchive,
  LayoutTemplate,
  Network,
  Palette,
  Power,
  RefreshCw,
  Search,
  ShieldCheck,
  Star,
  Trash2,
  UploadCloud,
  Wrench,
} from 'lucide-react';
import './ExtensionsPanel.css';

type MarketplaceSection = 'discover' | 'installed' | 'updates' | 'recommended' | 'categories' | 'publishers';
type ExtensionCategory =
  | 'language'
  | 'developer'
  | 'editor'
  | 'export'
  | 'agent'
  | 'mesh'
  | 'template';
type PermissionRisk = 'low' | 'medium' | 'high';

interface ExtensionPermission {
  label: string;
  risk: PermissionRisk;
}

interface MarketplaceExtension {
  id: string;
  name: string;
  initials: string;
  publisher: string;
  category: ExtensionCategory;
  description: string;
  version: string;
  latestVersion?: string;
  compatibility: string;
  installCount: string;
  rating: number;
  reviewCount: number;
  pricing: string;
  runLocation: 'Local' | 'Cloud optional' | 'Cloud service';
  permissions: ExtensionPermission[];
  changelog: string[];
  screenshots: string[];
  tags: string[];
  recommended?: boolean;
}

interface InstalledExtensionState {
  installedVersion: string;
  enabled: boolean;
}

const STORAGE_KEY = 'nexcoder_extensions_state';

const SECTIONS: Array<{ id: MarketplaceSection; label: string }> = [
  { id: 'discover', label: 'Discover' },
  { id: 'installed', label: 'Installed' },
  { id: 'updates', label: 'Updates' },
  { id: 'recommended', label: 'Recommended' },
  { id: 'categories', label: 'Categories' },
  { id: 'publishers', label: 'Publishers' },
];

const CATEGORY_LABELS: Record<ExtensionCategory, string> = {
  language: 'Language Support',
  developer: 'Developer Tools',
  editor: 'Editor Tools',
  export: 'Export Tools',
  agent: 'Agent Extensions',
  mesh: 'Agent Mesh Roles',
  template: 'Project Templates',
};

const CATEGORY_ICONS: Record<ExtensionCategory, React.ComponentType<{ size?: number }>> = {
  language: Code2,
  developer: Wrench,
  editor: Palette,
  export: FileArchive,
  agent: Bot,
  mesh: Network,
  template: LayoutTemplate,
};

const CATALOG: MarketplaceExtension[] = [
  {
    id: 'nexa.python-plus',
    name: 'Python Pro Support',
    initials: 'PY',
    publisher: 'Nexa Labs',
    category: 'language',
    description: 'Python language support with formatters, tests, virtualenv detection, and agent context providers.',
    version: '1.4.0',
    latestVersion: '1.4.0',
    compatibility: 'NexCoder 0.8+',
    installCount: '18.2K',
    rating: 4.8,
    reviewCount: 212,
    pricing: 'Free',
    runLocation: 'Local',
    permissions: [
      { label: 'Read workspace files', risk: 'low' },
      { label: 'Run approved commands', risk: 'medium' },
      { label: 'Register Agent Mode tools', risk: 'medium' },
    ],
    changelog: ['Added Python 3.14 detection.', 'Improved pytest task discovery.'],
    screenshots: ['LSP diagnostics', 'Virtual environment picker'],
    tags: ['python', 'formatter', 'pytest', 'agent context'],
    recommended: true,
  },
  {
    id: 'nexa.appwrite',
    name: 'Appwrite Studio',
    initials: 'AW',
    publisher: 'Nexa Labs',
    category: 'developer',
    description: 'Appwrite Explorer, collection inspection, permission audits, deployment commands, and a specialist agent.',
    version: '0.9.2',
    latestVersion: '1.0.0',
    compatibility: 'NexCoder 0.8+',
    installCount: '7.6K',
    rating: 4.7,
    reviewCount: 98,
    pricing: 'Free beta',
    runLocation: 'Cloud optional',
    permissions: [
      { label: 'Read workspace files', risk: 'low' },
      { label: 'Access the network', risk: 'medium' },
      { label: 'Run approved commands', risk: 'medium' },
      { label: 'Register specialist agent', risk: 'high' },
    ],
    changelog: ['Added database permission scanner.', 'Added documentation context pack.'],
    screenshots: ['Collection explorer', 'Permission risk report'],
    tags: ['appwrite', 'database', 'deploy', 'security'],
    recommended: true,
  },
  {
    id: 'nexa.docker-workflows',
    name: 'Docker Workflows',
    initials: 'DK',
    publisher: 'Nexa Labs',
    category: 'developer',
    description: 'Dockerfile linting, compose tasks, image build helpers, and container-aware agent actions.',
    version: '1.1.0',
    latestVersion: '1.1.0',
    compatibility: 'NexCoder 0.8+',
    installCount: '11.4K',
    rating: 4.6,
    reviewCount: 143,
    pricing: 'Free',
    runLocation: 'Local',
    permissions: [
      { label: 'Read workspace files', risk: 'low' },
      { label: 'Write workspace files', risk: 'medium' },
      { label: 'Run approved commands', risk: 'medium' },
    ],
    changelog: ['Compose profile detection.', 'Safer generated Dockerfiles.'],
    screenshots: ['Compose service view', 'Build command preview'],
    tags: ['docker', 'compose', 'deployment'],
  },
  {
    id: 'nexa.markdown-pdf',
    name: 'Markdown to PDF',
    initials: 'PDF',
    publisher: 'Nexa Labs',
    category: 'export',
    description: 'Export Markdown documentation to PDF with project branding and generated table of contents.',
    version: '0.6.5',
    latestVersion: '0.6.5',
    compatibility: 'NexCoder 0.8+',
    installCount: '5.9K',
    rating: 4.5,
    reviewCount: 64,
    pricing: 'Free',
    runLocation: 'Local',
    permissions: [
      { label: 'Read workspace files', risk: 'low' },
      { label: 'Write workspace files', risk: 'medium' },
    ],
    changelog: ['Improved code block pagination.', 'Added dark-theme export preset.'],
    screenshots: ['Export preview', 'PDF theme presets'],
    tags: ['markdown', 'pdf', 'docs'],
  },
  {
    id: 'nexa.security-reviewer',
    name: 'Security Reviewer Agent',
    initials: 'SR',
    publisher: 'Nexa Labs',
    category: 'mesh',
    description: 'Agent Mesh role for permission checks, dependency risk review, secret scanning, and auth-flow audits.',
    version: '0.8.0',
    latestVersion: '0.8.0',
    compatibility: 'NexCoder 0.8+',
    installCount: '9.1K',
    rating: 4.9,
    reviewCount: 131,
    pricing: 'Premium',
    runLocation: 'Local',
    permissions: [
      { label: 'Read workspace files', risk: 'low' },
      { label: 'Access the network', risk: 'medium' },
      { label: 'Register Agent Mesh role', risk: 'high' },
    ],
    changelog: ['Added Appwrite ruleset.', 'Added high-risk workflow classifier.'],
    screenshots: ['Security review report', 'Permission graph'],
    tags: ['security', 'agent mesh', 'review'],
    recommended: true,
  },
  {
    id: 'nexa.test-engineer',
    name: 'Test Engineer Agent',
    initials: 'TE',
    publisher: 'Nexa Labs',
    category: 'mesh',
    description: 'Specialist agent for test planning, regression coverage, smoke tests, and flaky failure triage.',
    version: '0.7.3',
    latestVersion: '0.7.3',
    compatibility: 'NexCoder 0.8+',
    installCount: '8.4K',
    rating: 4.7,
    reviewCount: 104,
    pricing: 'Free beta',
    runLocation: 'Local',
    permissions: [
      { label: 'Read workspace files', risk: 'low' },
      { label: 'Write workspace files', risk: 'medium' },
      { label: 'Run approved commands', risk: 'medium' },
      { label: 'Register Agent Mesh role', risk: 'high' },
    ],
    changelog: ['Added Playwright smoke workflow.', 'Improved pytest recommendations.'],
    screenshots: ['Coverage gap list', 'Validation plan'],
    tags: ['testing', 'pytest', 'playwright', 'agent mesh'],
  },
  {
    id: 'nexa.ai-browser-template',
    name: 'AI Browser Template',
    initials: 'BT',
    publisher: 'Nexa Labs',
    category: 'template',
    description: 'Project template for Electron-style browser apps with assistant panel, auth hooks, and automation safety rails.',
    version: '0.5.0',
    latestVersion: '0.5.0',
    compatibility: 'NexCoder 0.8+',
    installCount: '3.2K',
    rating: 4.6,
    reviewCount: 41,
    pricing: 'Free',
    runLocation: 'Local',
    permissions: [
      { label: 'Write workspace files', risk: 'medium' },
      { label: 'Register project template', risk: 'low' },
    ],
    changelog: ['Added browser automation risk prompts.', 'Added Appwrite auth starter.'],
    screenshots: ['Template preview', 'Generated project tree'],
    tags: ['template', 'browser', 'assistant'],
    recommended: true,
  },
  {
    id: 'nexa.neon-db-architect',
    name: 'Database Architect Agent',
    initials: 'DB',
    publisher: 'Nexa Labs',
    category: 'agent',
    description: 'Database schema review, migration planning, indexing suggestions, and backend data-flow context.',
    version: '0.4.1',
    latestVersion: '0.4.1',
    compatibility: 'NexCoder 0.8+',
    installCount: '4.8K',
    rating: 4.4,
    reviewCount: 57,
    pricing: 'Free beta',
    runLocation: 'Cloud optional',
    permissions: [
      { label: 'Read workspace files', risk: 'low' },
      { label: 'Access the network', risk: 'medium' },
      { label: 'Register specialist agent', risk: 'high' },
    ],
    changelog: ['Added SQL migration reviewer.', 'Added Appwrite collection advisor.'],
    screenshots: ['Schema review', 'Index recommendations'],
    tags: ['database', 'schema', 'agent'],
  },
];

function loadInstalledState(): Record<string, InstalledExtensionState> {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    return raw ? JSON.parse(raw) : {};
  } catch {
    return {};
  }
}

function saveInstalledState(state: Record<string, InstalledExtensionState>) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
}

function hasHighRiskPermission(extension: MarketplaceExtension): boolean {
  return extension.permissions.some((permission) => permission.risk === 'high');
}

function versionFor(extension: MarketplaceExtension): string {
  return extension.latestVersion || extension.version;
}

export default function ExtensionsPanel() {
  const [section, setSection] = useState<MarketplaceSection>('discover');
  const [category, setCategory] = useState<ExtensionCategory | 'all'>('all');
  const [query, setQuery] = useState('');
  const [installed, setInstalled] = useState<Record<string, InstalledExtensionState>>(() => loadInstalledState());
  const [selectedId, setSelectedId] = useState(CATALOG[0]?.id || '');

  useEffect(() => {
    saveInstalledState(installed);
  }, [installed]);

  const selected = CATALOG.find((extension) => extension.id === selectedId) || CATALOG[0];

  const filtered = useMemo(() => {
    const normalizedQuery = query.trim().toLowerCase();
    return CATALOG.filter((extension) => {
      const state = installed[extension.id];
      if (section === 'installed' && !state) return false;
      if (section === 'updates' && (!state || state.installedVersion === versionFor(extension))) return false;
      if (section === 'recommended' && !extension.recommended) return false;
      if (category !== 'all' && extension.category !== category) return false;
      if (!normalizedQuery) return true;
      return [
        extension.name,
        extension.publisher,
        extension.description,
        CATEGORY_LABELS[extension.category],
        extension.tags.join(' '),
      ].join(' ').toLowerCase().includes(normalizedQuery);
    });
  }, [category, installed, query, section]);

  useEffect(() => {
    if (filtered.length > 0 && !filtered.some((extension) => extension.id === selectedId)) {
      setSelectedId(filtered[0].id);
    }
  }, [filtered, selectedId]);

  const updateExtension = (extension: MarketplaceExtension, next: InstalledExtensionState | null) => {
    setInstalled((current) => {
      const copy = { ...current };
      if (next) copy[extension.id] = next;
      else delete copy[extension.id];
      return copy;
    });
  };

  const handleInstall = (extension: MarketplaceExtension) => {
    if (hasHighRiskPermission(extension)) {
      const permissionText = extension.permissions
        .map((permission) => `- ${permission.label} (${permission.risk})`)
        .join('\n');
      const approved = window.confirm(`Install ${extension.name}?\n\nThis extension requests:\n${permissionText}`);
      if (!approved) return;
    }
    updateExtension(extension, { installedVersion: versionFor(extension), enabled: true });
  };

  const handleUpdate = (extension: MarketplaceExtension) => {
    updateExtension(extension, {
      installedVersion: versionFor(extension),
      enabled: installed[extension.id]?.enabled ?? true,
    });
  };

  const installedState = selected ? installed[selected.id] : null;
  const updateAvailable = Boolean(selected && installedState && installedState.installedVersion !== versionFor(selected));
  const CategoryIcon = selected ? CATEGORY_ICONS[selected.category] : Code2;

  return (
    <div className="sidebar-panel extensions-panel">
      <div className="sidebar-header">
        <span>Extensions</span>
        <span title="Publisher tools" aria-label="Publisher tools">
          <UploadCloud size={13} />
        </span>
      </div>

      <div className="extensions-search">
        <Search size={12} />
        <input
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="Search marketplace"
        />
      </div>

      <div className="extensions-sections" role="tablist" aria-label="Extensions sections">
        {SECTIONS.map((item) => (
          <button
            key={item.id}
            type="button"
            className={section === item.id ? 'active' : ''}
            onClick={() => setSection(item.id)}
          >
            {item.label}
          </button>
        ))}
      </div>

      {(section === 'categories' || category !== 'all') && (
        <div className="extensions-categories">
          <button type="button" className={category === 'all' ? 'active' : ''} onClick={() => setCategory('all')}>
            All
          </button>
          {(Object.keys(CATEGORY_LABELS) as ExtensionCategory[]).map((id) => (
            <button
              key={id}
              type="button"
              className={category === id ? 'active' : ''}
              onClick={() => setCategory(id)}
            >
              {CATEGORY_LABELS[id].replace(' Support', '').replace(' Tools', '')}
            </button>
          ))}
        </div>
      )}

      <div className="extensions-content">
        <div className="extensions-list">
          {filtered.length === 0 ? (
            <div className="extensions-empty">No extensions match this view.</div>
          ) : filtered.map((extension) => {
            const state = installed[extension.id];
            const Icon = CATEGORY_ICONS[extension.category];
            return (
              <button
                key={extension.id}
                type="button"
                className={`extension-list-item ${selected?.id === extension.id ? 'active' : ''}`}
                onClick={() => setSelectedId(extension.id)}
              >
                <span className="extension-avatar">{extension.initials}</span>
                <span className="extension-list-copy">
                  <span className="extension-title-row">
                    <span>{extension.name}</span>
                    {state && <Check size={12} />}
                  </span>
                  <span className="extension-meta-row">
                    <Icon size={11} />
                    {extension.publisher}
                  </span>
                </span>
              </button>
            );
          })}
        </div>

        {selected && (
          <div className="extension-detail">
            <div className="extension-detail-head">
              <span className="extension-detail-avatar">{selected.initials}</span>
              <div>
                <h3>{selected.name}</h3>
                <p>{selected.publisher}</p>
              </div>
            </div>

            <p className="extension-description">{selected.description}</p>

            <div className="extension-stats">
              <span><Star size={11} /> {selected.rating.toFixed(1)} ({selected.reviewCount})</span>
              <span><Download size={11} /> {selected.installCount}</span>
              <span><CategoryIcon size={11} /> {CATEGORY_LABELS[selected.category]}</span>
            </div>

            <div className="extension-actions">
              {!installedState ? (
                <button type="button" className="btn btn-primary" onClick={() => handleInstall(selected)}>
                  Install
                </button>
              ) : (
                <>
                  {updateAvailable && (
                    <button type="button" className="btn btn-primary" onClick={() => handleUpdate(selected)}>
                      <RefreshCw size={12} /> Update
                    </button>
                  )}
                  <button
                    type="button"
                    className="btn btn-ghost"
                    onClick={() => updateExtension(selected, {
                      installedVersion: installedState.installedVersion,
                      enabled: !installedState.enabled,
                    })}
                  >
                    <Power size={12} /> {installedState.enabled ? 'Disable' : 'Enable'}
                  </button>
                  <button
                    type="button"
                    className="btn btn-ghost"
                    onClick={() => {
                      if (window.confirm(`Uninstall ${selected.name}?`)) updateExtension(selected, null);
                    }}
                  >
                    <Trash2 size={12} /> Uninstall
                  </button>
                </>
              )}
            </div>

            <div className="extension-facts">
              <div><span>Version</span><strong>{installedState?.installedVersion || selected.version}</strong></div>
              <div><span>Latest</span><strong>{versionFor(selected)}</strong></div>
              <div><span>Compatibility</span><strong>{selected.compatibility}</strong></div>
              <div><span>Runs</span><strong>{selected.runLocation}</strong></div>
              <div><span>Pricing</span><strong>{selected.pricing}</strong></div>
            </div>

            <div className="extension-section-title">Permissions</div>
            <div className="extension-permissions">
              {selected.permissions.map((permission) => (
                <span key={permission.label} className={`permission-chip ${permission.risk}`}>
                  {permission.risk === 'high' && <CircleAlert size={11} />}
                  {permission.label}
                </span>
              ))}
            </div>

            <div className="extension-section-title">Changelog</div>
            <ul className="extension-list-text">
              {selected.changelog.map((item) => <li key={item}>{item}</li>)}
            </ul>

            <div className="extension-section-title">Screenshots</div>
            <div className="extension-screenshots">
              {selected.screenshots.map((item) => <span key={item}>{item}</span>)}
            </div>

            {section === 'publishers' && (
              <div className="publisher-flow">
                <div className="extension-section-title">Publishing Beta</div>
                <ol>
                  <li>Create developer account</li>
                  <li>Register publisher</li>
                  <li>Validate .nexext package</li>
                  <li>Automated security scan</li>
                  <li>Review permissions</li>
                  <li>Publish to curated beta</li>
                </ol>
                <div className="publisher-revenue"><ShieldCheck size={12} /> Suggested split: Developer 80%, Nexa 20%</div>
                <div className="publisher-revenue"><Cloud size={12} /> Private business extensions supported later</div>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
