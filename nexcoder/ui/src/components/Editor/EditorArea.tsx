import React from 'react';
import { useEditorStateStore } from '../../store/useEditorStateStore';
import { useChatStore } from '../../store/useChatStore';
import { useEditorSettingsStore } from '../../store/useEditorSettingsStore';
import EditorTabs from './EditorTabs';
import MonacoEditor from './MonacoEditor';
import DiffViewer from './DiffViewer';
import WelcomeScreen from './WelcomeScreen';
import ImagePreview from './ImagePreview';
import MediaPreview from './MediaPreview';
import ImplementationPlanView from '../Plan/ImplementationPlanView';
import { getFilePreviewKind } from '../../utils/fileIcons';
import './EditorArea.css';

export default function EditorArea() {
  const { editorGroups, activeGroupId, setActiveGroup } = useEditorStateStore();
  const { pendingDiffs, activeDiffId } = useChatStore();
  const { settings } = useEditorSettingsStore();

  const activeDiff = pendingDiffs.find((diff) => diff.id === activeDiffId) || pendingDiffs[0];

  return (
    <div className="editor-area-container h-full">
      <div className={`editor-groups ${settings.defaultSplitDirection === 'vertical' ? 'vertical' : 'horizontal'}`}>
        {editorGroups.map((group) => {
          const activeFile = group.openFiles.find((file) => file.path === group.activeFilePath) || null;
          const previewKind = activeFile ? getFilePreviewKind(activeFile.path) : 'text';
          const isActiveGroup = activeGroupId === group.id;
          return (
            <div
              key={group.id}
              className={`editor-group ${isActiveGroup ? 'active' : ''}`}
              onMouseDown={() => setActiveGroup(group.id)}
            >
              <EditorTabs groupId={group.id} openFiles={group.openFiles} activeFile={activeFile} />
              <div className="editor-group-body">
                {activeDiff && isActiveGroup ? (
                  <DiffViewer diff={activeDiff} />
                ) : activeFile ? (
                  activeFile.kind === 'implementation_plan' && activeFile.resourceId ? (
                    <ImplementationPlanView planId={activeFile.resourceId} />
                  ) : previewKind === 'image' ? (
                    <ImagePreview key={`${group.id}:${activeFile.path}`} file={activeFile} />
                  ) : previewKind !== 'text' ? (
                    <MediaPreview
                      key={`${group.id}:${activeFile.path}`}
                      file={activeFile}
                      kind={previewKind}
                    />
                  ) : (
                    <MonacoEditor key={`${group.id}:${activeFile.path}`} file={activeFile} />
                  )
                ) : (
                  <WelcomeScreen />
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
