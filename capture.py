import cv2
import threading
import queue
import time

class Capture:
    def __init__(self, camera_index=0):
        """Initialize the camera capture with threading support."""
        self.cap = cv2.VideoCapture(camera_index)
        if not self.cap.isOpened():
            raise ValueError(f"Failed to open camera {camera_index}")
            
        # Set camera properties
        self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        self.cap.set(cv2.CAP_PROP_FPS, 30)
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        
        # Initialize threading components
        self.frame_queue = queue.Queue(maxsize=2)
        self.stopped = False
        
        # Start frame capture thread
        self.thread = threading.Thread(target=self._capture_frames)
        self.thread.daemon = True
        self.thread.start()
    
    def _capture_frames(self):
        """Continuously capture frames in a separate thread."""
        while not self.stopped:
            if not self.frame_queue.full():
                ret, frame = self.cap.read()
                if ret:
                    # Clear queue before putting new frame
                    while not self.frame_queue.empty():
                        try:
                            self.frame_queue.get_nowait()
                        except queue.Empty:
                            break
                    self.frame_queue.put(frame)
            time.sleep(0.01)  # Small sleep to prevent excessive CPU usage
    
    def get_frame(self):
        """Get the most recent frame."""
        if self.stopped:
            return None
            
        try:
            frame = self.frame_queue.get_nowait()
            return frame
        except queue.Empty:
            return None
    
    def release(self):
        """Stop the capture thread and release resources."""
        self.stopped = True
        if self.thread.is_alive():
            self.thread.join()
        if self.cap.isOpened():
            self.cap.release()
