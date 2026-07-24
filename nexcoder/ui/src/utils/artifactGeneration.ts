import type { AgentArtifact } from '../types';
import type { AgentRun } from '../store/useAgentRunStore';

function slugify(value: string): string {
  return value
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '')
    .slice(0, 48) || 'agent-run';
}

function firstLine(value: string): string {
  return value.trim().split(/\r\n|\r|\n/).find(Boolean)?.trim() || 'Agent run';
}

function stepSummary(run: AgentRun): string[] {
  return run.transcript
    .filter((item) => item.kind === 'step')
    .map((item) => {
      if (item.kind !== 'step') return '';
      const target = item.args?.path || item.args?.command || item.args?.pattern || '';
      const status = item.done ? (item.success === false ? 'failed' : 'completed') : 'running';
      return `- ${item.tool}${target ? `: ${String(target)}` : ''} (${status})`;
    })
    .filter(Boolean);
}

function todoSummary(run: AgentRun): string[] {
  return run.todos.map((todo) => `- [${todo.status === 'completed' ? 'x' : ' '}] ${todo.content}`);
}

function baseSections(runId: string, run: AgentRun, prompt: string): string[] {
  const sections = [
    `Run ID: ${runId}`,
    `Status: ${run.status || 'completed'}`,
  ];
  if (prompt.trim()) sections.push('', '## Prompt', prompt.trim());
  if (run.todos.length > 0) sections.push('', '## Plan', ...todoSummary(run));
  const steps = stepSummary(run);
  if (steps.length > 0) sections.push('', '## Actions', ...steps);
  if (run.mutatedFiles.length > 0) {
    sections.push('', '## Files Changed', ...run.mutatedFiles.map((file) => `- ${file}`));
  }
  if (run.finalText.trim()) sections.push('', '## Result', run.finalText.trim());
  return sections;
}

function inferPrimaryType(run: AgentRun, prompt: string): AgentArtifact['type'] {
  if (run.status === 'error') return 'failure_report';
  const lower = prompt.toLowerCase();
  if (/\b(problem|diagnostic|error|quick fix|fix this)\b/.test(lower)) return 'problem_fix_report';
  if (/\b(review|audit)\b/.test(lower)) return 'review_report';
  if (/\b(scan|map|understand this project|codebase)\b/.test(lower)) return 'scan_report';
  const commandText = run.transcript
    .filter((item) => item.kind === 'step' && item.tool === 'run_command')
    .map((item) => item.kind === 'step' ? String(item.args?.command || '') : '')
    .join('\n')
    .toLowerCase();
  if (/\b(test|pytest|vitest|jest|lint|typecheck|tsc|build)\b/.test(commandText)) {
    return 'validation_report';
  }
  return 'run_summary';
}

function artifactTitlePrefix(type: AgentArtifact['type']): string {
  switch (type) {
    case 'failure_report': return 'Failure Report';
    case 'problem_fix_report': return 'Problem Fix Report';
    case 'review_report': return 'Review Report';
    case 'scan_report': return 'Scan Report';
    case 'validation_report': return 'Validation Report';
    case 'patch_summary': return 'Patch Summary';
    case 'implementation_plan': return 'Implementation Plan';
    default: return 'Run Summary';
  }
}

function artifactSummary(type: AgentArtifact['type'], run: AgentRun): string {
  switch (type) {
    case 'failure_report':
      return 'The agent run ended with an error and preserved the prompt, actions, and failure output.';
    case 'problem_fix_report':
      return 'A durable record of the diagnostic, attempted fix, changed files, and result.';
    case 'review_report':
      return 'A durable record of a code review or audit run, including evidence and recommendations.';
    case 'scan_report':
      return 'A durable codebase scan summary with files, actions, and findings from the run.';
    case 'validation_report':
      return 'A durable validation report for build, test, lint, or type-check commands run by the agent.';
    default:
      return run.mutatedFiles.length
        ? 'A durable summary of the agent run, actions, changed files, and result.'
        : 'A durable summary of the agent run, actions, and result.';
  }
}

function commandSections(run: AgentRun): string[] {
  const commands = run.transcript.filter((item) => item.kind === 'step' && item.tool === 'run_command');
  if (!commands.length) return [];
  const sections = ['', '## Command Results'];
  commands.forEach((item) => {
    if (item.kind !== 'step') return;
    const command = String(item.args?.command || item.args?.cmd || 'command');
    sections.push('', `### ${command}`, `Status: ${item.success === false ? 'failed' : item.done ? 'passed' : 'running'}`);
    if (item.output?.length) {
      sections.push('', '```text', ...item.output.slice(-80), '```');
    }
  });
  return sections;
}

export function createRunArtifacts(args: {
  runId: string;
  run: AgentRun;
  projectPath: string;
  prompt: string;
  createdAt?: number;
}): AgentArtifact[] {
  const { runId, run, projectPath, prompt } = args;
  if (run.runActive) return [];
  const now = args.createdAt || Date.now();
  const titleBase = firstLine(prompt || run.finalText);
  const baseId = `${runId}-${slugify(titleBase)}`;
  const artifacts: AgentArtifact[] = [];
  const primaryType = inferPrimaryType(run, prompt);
  const primaryPrefix = artifactTitlePrefix(primaryType);

  const summaryContent = [
    `# ${primaryPrefix}: ${titleBase}`,
    '',
    ...baseSections(runId, run, prompt),
    ...commandSections(run),
  ].join('\n');
  artifacts.push({
    id: `${baseId}-summary`,
    runId,
    projectPath,
    type: primaryType,
    title: `${primaryPrefix}: ${titleBase}`,
    summary: artifactSummary(primaryType, run),
    content: summaryContent,
    createdAt: now,
    updatedAt: now,
    status: 'generated',
    files: run.mutatedFiles,
    sourcePrompt: prompt,
  });

  if (run.mutatedFiles.length > 0) {
    const diffStats = run.transcript
      .filter((item) => item.kind === 'step' && (item.added !== undefined || item.removed !== undefined))
      .map((item) => item.kind === 'step'
        ? `- ${String(item.args?.path || item.tool)}: +${item.added ?? 0} -${item.removed ?? 0}`
        : '')
      .filter(Boolean);
    artifacts.push({
      id: `${baseId}-patch`,
      runId,
      projectPath,
      type: 'patch_summary',
      title: `Patch Summary: ${titleBase}`,
      summary: `${run.mutatedFiles.length} file${run.mutatedFiles.length === 1 ? '' : 's'} changed by this run.`,
      content: [
        `# Patch Summary: ${titleBase}`,
        '',
        `Run ID: ${runId}`,
        '',
        '## Changed Files',
        ...run.mutatedFiles.map((file) => `- ${file}`),
        ...(diffStats.length ? ['', '## Diff Stats', ...diffStats] : []),
        ...(run.finalText.trim() ? ['', '## Agent Notes', run.finalText.trim()] : []),
      ].join('\n'),
      createdAt: now,
      updatedAt: now,
      status: 'generated',
      files: run.mutatedFiles,
      sourcePrompt: prompt,
    });
  }

  const validationCommands = run.transcript.filter((item) => (
    item.kind === 'step'
    && item.tool === 'run_command'
    && /\b(test|pytest|vitest|jest|lint|typecheck|tsc|build)\b/i.test(String(item.args?.command || ''))
  ));
  if (validationCommands.length > 0 && primaryType !== 'validation_report') {
    artifacts.push({
      id: `${baseId}-validation`,
      runId,
      projectPath,
      type: 'validation_report',
      title: `Validation Report: ${titleBase}`,
      summary: `${validationCommands.length} validation command${validationCommands.length === 1 ? '' : 's'} recorded for this run.`,
      content: [
        `# Validation Report: ${titleBase}`,
        '',
        `Run ID: ${runId}`,
        `Status: ${run.status || 'completed'}`,
        ...commandSections(run),
      ].join('\n'),
      createdAt: now,
      updatedAt: now,
      status: 'generated',
      files: run.mutatedFiles,
      sourcePrompt: prompt,
    });
  }

  return artifacts;
}
