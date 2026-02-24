import { useEffect, useState } from 'react';
import { invoke } from '@tauri-apps/api/core';
import CameraView from './features/camera/CameraView';

interface EdgeInfo {
  base_url: string;
  token: string;
}

function App() {
  const [edgeReady, setEdgeReady] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const initializeEdge = async () => {
    try {
      setError(null);
      await invoke<EdgeInfo>('start_edge');
      setEdgeReady(true);
    } catch (err) {
      setError(String(err));
    }
  };

  useEffect(() => {
    initializeEdge();

    return () => {
      // Kill edge on unmount
      invoke('kill_edge').catch(() => undefined);
    };
  }, []);

  if (error) {
    return (
      <div className="container">
        <h1>Edge Startup Error</h1>
        <p>{error}</p>
        <button onClick={initializeEdge}>Retry</button>
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
