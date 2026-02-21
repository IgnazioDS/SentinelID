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

async function enrollFrame(frame: string): Promise<any> {
  console.log('apiClient: enrollFrame called with base64 string');

  try {
    const edge = await getEdgeInfo();
    const url = `${edge.base_url}/enroll/frame`;

    console.log(`apiClient: Sending POST request to ${url}`);
    const response = await fetch(url, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${edge.token}`,
      },
      body: JSON.stringify({ frame: frame }),
    });
    console.log('apiClient: Response received:', response);

    if (!response.ok) {
      console.error('apiClient: Response not OK:', response.statusText);
      throw new Error(`Error sending frame: ${response.statusText}`);
    }

    const data = await response.json();
    console.log('apiClient: Response JSON parsed:', data);
    return data;
  } catch (error) {
    console.error('apiClient: Fetch error:', error);
    throw error;
  }
}

const apiClient = {
  enrollFrame,
};

export default apiClient;
