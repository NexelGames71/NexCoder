import React, { useState } from 'react';
import { Files, Search, GitBranch, Play, MessageSquareText, ListChecks, Network } from 'lucide-react';
import FileExplorer from './FileExplorer';
import SearchPanel from './SearchPanel';
import GitPanel from './GitPanel';
import TasksPanel from './TasksPanel';
import ChatHistoryPanel from './ChatHistoryPanel';
import MeshPanel from './MeshPanel';
import './Sidebar.css';

interface SidebarProps {
  isCollapsed: boolean;
}

type TabId = 'explorer' | 'search' | 'git' | 'run' | 'chats' | 'tasks' | 'mesh';

// Activity bar order: Explorer, Search, Source Control, Run, Chats,
// Agent Tasks, Agent Mesh.
const TABS: { id: TabId; icon: any; title: string }[] = [
  { id: 'explorer', icon: Files, title: 'Explorer' },
  { id: 'search', icon: Search, title: 'Search' },
  { id: 'git', icon: GitBranch, title: 'Source Control' },
  { id: 'run', icon: Play, title: 'Run' },
  { id: 'chats', icon: MessageSquareText, title: 'Chats' },
  { id: 'tasks', icon: ListChecks, title: 'Agent Tasks' },
  { id: 'mesh', icon: Network, title: 'Agent Mesh' },
];

export default function Sidebar({ isCollapsed }: SidebarProps) {
  const [activeTab, setActiveTab] = useState<TabId>('explorer');

  if (isCollapsed) return null;

  const renderActivePanel = () => {
    switch (activeTab) {
      case 'explorer':
        return <FileExplorer />;
      case 'search':
        return <SearchPanel />;
      case 'git':
        return <GitPanel />;
      case 'run':
      case 'tasks':
        return <TasksPanel />;
      case 'chats':
        return <ChatHistoryPanel />;
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
