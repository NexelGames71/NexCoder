import type { AgentArtifact } from '../types';
import { deleteArtifactFile, readFile, writeFile } from './bridge';

const ARTIFACT_INDEX_PATH = '.nexcoder/artifacts/index.json';

interface ArtifactIndexFile {
  version: 1;
  updatedAt: number;
  artifacts: AgentArtifact[];
}

function slugify(value: string): string {
  return value
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '')
    .slice(0, 64) || 'artifact';
}

function stableHash(value: string): string {
  let hash = 0;
  for (let index = 0; index < value.length; index += 1) {
    hash = ((hash << 5) - hash + value.charCodeAt(index)) | 0;
  }
  return Math.abs(hash).toString(36);
}

export function suggestedArtifactPath(artifact: AgentArtifact): string {
  return `.nexcoder/artifacts/${slugify(artifact.title)}-${stableHash(artifact.id)}.md`;
}

export function serializeArtifactMarkdown(artifact: AgentArtifact): string {
  const meta = [
    '<!-- nexcoder-artifact',
    JSON.stringify({
      id: artifact.id,
      runId: artifact.runId,
      type: artifact.type,
      createdAt: artifact.createdAt,
      updatedAt: artifact.updatedAt,
      files: artifact.files,
    }, null, 2),
    'nexcoder-artifact -->',
    '',
  ];
  return `${meta.join('\n')}${artifact.content.trimEnd()}\n`;
}

function normalizeArtifact(artifact: AgentArtifact): AgentArtifact {
  return {
    ...artifact,
    savedPath: artifact.savedPath || suggestedArtifactPath(artifact),
    updatedAt: artifact.updatedAt || Date.now(),
  };
}

export async function loadProjectArtifacts(): Promise<AgentArtifact[]> {
  const result = await readFile(ARTIFACT_INDEX_PATH);
  if (!result?.success || !result.content) return [];

  try {
    const parsed = JSON.parse(result.content) as Partial<ArtifactIndexFile>;
    if (!Array.isArray(parsed.artifacts)) return [];
    return parsed.artifacts.map(normalizeArtifact)
      .sort((a, b) => b.updatedAt - a.updatedAt);
  } catch (error) {
    console.warn('[Artifacts] Could not parse artifact index', error);
    return [];
  }
}

export async function persistProjectArtifacts(artifacts: AgentArtifact[]): Promise<boolean> {
  const normalized = artifacts.map(normalizeArtifact)
    .sort((a, b) => b.updatedAt - a.updatedAt);
  const indexFile: ArtifactIndexFile = {
    version: 1,
    updatedAt: Date.now(),
    artifacts: normalized,
  };

  const indexResult = await writeFile(ARTIFACT_INDEX_PATH, `${JSON.stringify(indexFile, null, 2)}\n`);
  if (!indexResult?.success) return false;

  await Promise.all(normalized.map(async (artifact) => {
    if (!artifact.savedPath) return;
    const result = await writeFile(artifact.savedPath, serializeArtifactMarkdown(artifact));
    if (!result?.success) {
      console.warn('[Artifacts] Could not write artifact markdown', artifact.savedPath, result?.error);
    }
  }));
  return true;
}

export async function persistSingleArtifact(artifact: AgentArtifact): Promise<AgentArtifact | null> {
  const normalized = normalizeArtifact({
    ...artifact,
    status: artifact.status === 'draft' ? 'generated' : artifact.status,
  });
  const result = await writeFile(normalized.savedPath || suggestedArtifactPath(normalized), serializeArtifactMarkdown(normalized));
  if (!result?.success) return null;
  return {
    ...normalized,
    savedPath: result.path || normalized.savedPath,
    updatedAt: Date.now(),
  };
}

export async function deletePersistedArtifactFile(artifact: AgentArtifact): Promise<boolean> {
  const path = artifact.savedPath || suggestedArtifactPath(artifact);
  const result = await deleteArtifactFile(path);
  return Boolean(result?.success);
}

export async function deletePersistedArtifactFiles(artifacts: AgentArtifact[]): Promise<void> {
  await Promise.all(artifacts.map(async (artifact) => {
    const ok = await deletePersistedArtifactFile(artifact);
    if (!ok) {
      console.warn('[Artifacts] Could not delete artifact markdown', artifact.savedPath || suggestedArtifactPath(artifact));
    }
  }));
  const result = await deleteArtifactFile(ARTIFACT_INDEX_PATH);
  if (!result?.success) {
    console.warn('[Artifacts] Could not delete artifact index', result?.error);
  }
}
