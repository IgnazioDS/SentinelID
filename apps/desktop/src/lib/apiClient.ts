const API_BASE_URL = 'http://localhost:8000/api/v1';

async function enrollFrame(frame: string): Promise<any> {
  console.log('apiClient: enrollFrame called with base64 string');

  try {
    console.log(`apiClient: Sending POST request to ${API_BASE_URL}/enroll/frame`);
    const response = await fetch(`${API_BASE_URL}/enroll/frame`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
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
