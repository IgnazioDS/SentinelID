import { useEffect, useState } from 'react';
import { invoke } from '@tauri-apps/api/tauri';
import CameraView from './features/camera/CameraView';

interface EdgeInfo {
  base_url: string;
  token: string;
}

function App() {
  const [edgeReady, setEdgeReady] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function initializeEdge() {
      try {
        console.log('App: Starting edge process...');
        const edgeInfo = await invoke<EdgeInfo>('start_edge');
        console.log('App: Edge started at', edgeInfo.base_url);
        setEdgeReady(true);
      } catch (err) {
        console.error('App: Failed to start edge:', err);
        setError(String(err));
      }
    }

    initializeEdge();

    return () => {
      // Kill edge on unmount
      invoke('kill_edge').catch(err => console.error('App: Failed to kill edge:', err));
    };
  }, []);

  if (error) {
    return (
      <div className="container">
        <h1>Error</h1>
        <p>Failed to start edge service: {error}</p>
      </div>
    );
  }

  if (!edgeReady) {
    return (
      <div className="container">
        <h1>Loading...</h1>
        <p>Starting edge service...</p>
      </div>
    );
  }

  return (
    <div className="container">
      <h1>Welcome to SentinelID</h1>
      <CameraView />
    </div>
  )
}

export default App
