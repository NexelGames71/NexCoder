import React, { useState } from 'react';
import { Files, Search, GitBranch, Play, MessageSquareText } from 'lucide-react';
import FileExplorer from './FileExplorer';
import SearchPanel from './SearchPanel';
import GitPanel from './GitPanel';
import TasksPanel from './TasksPanel';
import ChatHistoryPanel from './ChatHistoryPanel';
import './Sidebar.css';

interface SidebarProps {
  isCollapsed: boolean;
}

export default function Sidebar({ isCollapsed }: SidebarProps) {
  const [activeTab, setActiveTab] = useState<'explorer' | 'search' | 'git' | 'tasks' | 'chats'>('explorer');

  if (isCollapsed) return null;

  const renderActivePanel = () => {
    switch (activeTab) {
      case 'explorer':
        return <FileExplorer />;
      case 'search':
        return <SearchPanel />;
      case 'git':
        return <GitPanel />;
      case 'tasks':
        return <TasksPanel />;
      case 'chats':
        return <ChatHistoryPanel />;
      default:
        return <FileExplorer />;
    }
  };

  return (
    <div className="sidebar-container h-full">
      {/* Sidebar Icon Tabs */}
      <div className="sidebar-tabs">
        <button
          className={`sidebar-tab-btn ${activeTab === 'explorer' ? 'active' : ''}`}
          onClick={() => setActiveTab('explorer')}
        >
          <Files size={18} />
        </button>
        <button
          className={`sidebar-tab-btn ${activeTab === 'search' ? 'active' : ''}`}
          onClick={() => setActiveTab('search')}
        >
          <Search size={18} />
        </button>
        <button
          className={`sidebar-tab-btn ${activeTab === 'git' ? 'active' : ''}`}
          onClick={() => setActiveTab('git')}
        >
          <GitBranch size={18} />
        </button>
        <button
          className={`sidebar-tab-btn ${activeTab === 'tasks' ? 'active' : ''}`}
          onClick={() => setActiveTab('tasks')}
        >
          <Play size={18} />
        </button>
        <button
          className={`sidebar-tab-btn ${activeTab === 'chats' ? 'active' : ''}`}
          onClick={() => setActiveTab('chats')}
        >
          <MessageSquareText size={18} />
        </button>
      </div>

      {/* Active panel content */}
      <div className="sidebar-content">
        {renderActivePanel()}
      </div>
    </div>
  );
}
