import React, { useEffect } from 'react';
import { GitBranch } from 'lucide-react';
import { useGitStore } from '../../store/useGitStore';
import { useProjectStore } from '../../store/useProjectStore';
import { gitBranch } from '../../services/bridge';

export default function BranchBadge() {
  const { status } = useGitStore();
  const { projectPath } = useProjectStore();
  const [branchName, setBranchName] = React.useState<string>('');

  useEffect(() => {
    if (projectPath) {
      gitBranch(projectPath).then((res: any) => {
        if (res && res.success && res.branch) {
          setBranchName(res.branch);
        }
      });
    } else {
      setBranchName('');
    }
  }, [projectPath, status]);

  if (!branchName) return null;

  return (
    <div className="badge badge-purple select-none" style={{ gap: 'var(--space-1)', padding: '4px 8px' }}>
      <GitBranch size={12} />
      <span className="font-medium" style={{ fontSize: 'var(--font-size-xs)' }}>{branchName}</span>
    </div>
  );
}
