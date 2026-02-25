export interface ProgressParts {
  done: number;
  total: number;
  percent: number;
}

export function extractProgressParts(progressText?: string): ProgressParts | null {
  if (!progressText) return null;
  const match = progressText.match(/(\d+)\s*\/\s*(\d+)/);
  if (!match) return null;

  const done = Number(match[1]);
  const total = Number(match[2]);
  if (!Number.isFinite(done) || !Number.isFinite(total) || total <= 0) {
    return null;
  }

  const percent = Math.min(100, Math.max(0, (done / total) * 100));
  return { done, total, percent };
}

export function enrollmentPercent(acceptedFrames: number, targetFrames: number): number {
  if (!Number.isFinite(acceptedFrames) || !Number.isFinite(targetFrames) || targetFrames <= 0) {
    return 0;
  }
  return Math.min(100, Math.max(0, (acceptedFrames / targetFrames) * 100));
}
