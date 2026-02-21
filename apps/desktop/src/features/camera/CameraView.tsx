import React, { useRef, useEffect } from 'react';
import apiClient from '../../lib/apiClient';

const CameraView: React.FC = () => {
  const videoRef = useRef<HTMLVideoElement>(null);

  useEffect(() => {
    async function getCamera() {
      if (navigator.mediaDevices && navigator.mediaDevices.getUserMedia) {
        try {
          const stream = await navigator.mediaDevices.getUserMedia({ video: true });
          if (videoRef.current) {
            videoRef.current.srcObject = stream;
          }
        } catch (error) {
          console.error("Error accessing the camera: ", error);
        }
      }
    }

    getCamera();

    return () => {
      if (videoRef.current && videoRef.current.srcObject) {
        const stream = videoRef.current.srcObject as MediaStream;
        stream.getTracks().forEach(track => track.stop());
      }
    }
  }, []);

  const captureFrame = async () => {
    if (videoRef.current) {
      const canvas = document.createElement('canvas');
      canvas.width = videoRef.current.videoWidth;
      canvas.height = videoRef.current.videoHeight;
      const context = canvas.getContext('2d');
      if (context) {
        context.drawImage(videoRef.current, 0, 0, canvas.width, canvas.height);
        const dataUrl = canvas.toDataURL('image/jpeg');
        try {
          const response = await apiClient.enrollFrame(dataUrl);
          console.log('Frame sent successfully:', response);
        } catch (error) {
          console.error('Error sending frame:', error);
        }
      }
    }
  };

  return (
    <div>
      <h2>Camera Feed</h2>
      <video ref={videoRef} autoPlay playsInline width="640" height="480"></video>
      <button onClick={captureFrame}>Enroll Frame</button>
    </div>
  );
};

export default CameraView;
