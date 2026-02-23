import { invoke } from '@tauri-apps/api/tauri';

interface EdgeInfo {
  base_url: string;
  token: string;
}

let edgeInfo: EdgeInfo | null = null;

async function getEdgeInfo(): Promise<EdgeInfo> {
  if (!edgeInfo) {
    edgeInfo = await invoke<EdgeInfo>('get_edge_info');
  }
  return edgeInfo;
}

async function post(path: string, body: unknown): Promise<any> {
  const edge = await getEdgeInfo();
  const res = await fetch(`${edge.base_url}/api/v1${path}`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${edge.token}`,
    },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    throw new Error(`API ${path} failed: ${res.status} ${res.statusText}`);
  }
  return await res.json();
}

const apiClient = {
  startEnroll: () => post('/enroll/start', {}),
  enrollFrame: (sessionId: string, frame: string) => post('/enroll/frame', { session_id: sessionId, frame }),
  commitEnroll: (sessionId: string, label: string) => post('/enroll/commit', { session_id: sessionId, label }),
  resetEnroll: (sessionId: string) => post('/enroll/reset', { session_id: sessionId }),
  startAuth: () => post('/auth/start', {}),
  authFrame: (sessionId: string, frame: string) => post('/auth/frame', { session_id: sessionId, frame }),
  finishAuth: (sessionId: string) => post('/auth/finish', { session_id: sessionId }),
};

export default apiClient;
