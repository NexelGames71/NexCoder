import React, { useEffect, useState } from 'react';
import { Files, Search, GitBranch, ListChecks, Network, Puzzle } from 'lucide-react';
import FileExplorer from './FileExplorer';
import SearchPanel from './SearchPanel';
import GitPanel from './GitPanel';
import TasksPanel from './TasksPanel';
import MeshPanel from './MeshPanel';
import ExtensionsPanel from './ExtensionsPanel';
import './Sidebar.css';

interface SidebarProps {
  isCollapsed: boolean;
}

type TabId = 'explorer' | 'search' | 'git' | 'extensions' | 'tasks' | 'mesh';

// Activity bar order: Explorer, Search, Source Control, Extensions,
// Agent Tasks, Agent Mesh. Chat history lives in the AI panel.
const TABS: { id: TabId; icon: any; title: string }[] = [
  { id: 'explorer', icon: Files, title: 'Explorer' },
  { id: 'search', icon: Search, title: 'Search' },
  { id: 'git', icon: GitBranch, title: 'Source Control' },
  { id: 'extensions', icon: Puzzle, title: 'Extensions' },
  { id: 'tasks', icon: ListChecks, title: 'Agent Tasks' },
  { id: 'mesh', icon: Network, title: 'Agent Mesh' },
];

export default function Sidebar({ isCollapsed }: SidebarProps) {
  const [activeTab, setActiveTab] = useState<TabId>('explorer');

  useEffect(() => {
    const validTabs = new Set(TABS.map((tab) => tab.id));
    const handleShowTab = (event: Event) => {
      const tabId = String((event as CustomEvent<{ tabId?: string }>).detail?.tabId || 'explorer');
      if (validTabs.has(tabId as TabId)) {
        setActiveTab(tabId as TabId);
      }
    };
    window.addEventListener('nexcoder:show-sidebar-tab', handleShowTab);
    return () => window.removeEventListener('nexcoder:show-sidebar-tab', handleShowTab);
  }, []);

  if (isCollapsed) return null;

  const renderActivePanel = () => {
    switch (activeTab) {
      case 'explorer':
        return <FileExplorer />;
      case 'search':
        return <SearchPanel />;
      case 'git':
        return <GitPanel />;
      case 'extensions':
        return <ExtensionsPanel />;
      case 'tasks':
        return <TasksPanel />;
      case 'mesh':
        return <MeshPanel />;
      default:
        return <FileExplorer />;
    }
  };

  return (
    <div className="sidebar-container h-full">
      {/* Activity bar */}
      <div className="sidebar-tabs">
        {TABS.map(({ id, icon: Icon, title }) => (
          <button
            key={id}
            className={`sidebar-tab-btn ${activeTab === id ? 'active' : ''}`}
            onClick={() => setActiveTab(id)}
            title={title}
          >
            <Icon size={18} />
          </button>
        ))}
      </div>

      {/* Active panel content */}
      <div className="sidebar-content">
        {renderActivePanel()}
      </div>
    </div>
  );
}
