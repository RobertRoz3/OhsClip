import numpy as np
import mss
import cv2
import time
from collections import deque
import keyboard
import os
import threading

class ScreenRecorder:
    def __init__(self, buffer_seconds=60, fps=30, save_key='f12', save_path=r'C:\Users\osceo\Desktop\Stuff\OhsClip\OhsClip\Testing'):
        self.sct = mss.mss()
        self.buffer_size = buffer_seconds * fps
        self.fps = fps
        self.frame_time = 1 / fps
        self.monitor = self.sct.monitors[1]
        self.frame_buffer = deque(maxlen=self.buffer_size)
        self.save_key = save_key
        self.save_path = save_path
        self.is_recording = True

        os.makedirs(self.save_path, exist_ok=True)
    
    def capture_screen(self):
        frame = np.array(self.sct.grab(self.monitor))
        # Compress frame to JPEG to reduce memory usage
        _, buffer = cv2.imencode('.jpg', frame, [int(cv2.IMWRITE_JPEG_QUALITY), 80])
        return buffer.tobytes()
    
    def save_buffer(self):
        if not self.frame_buffer:
            print('No frames to save.')
            return
        
        # Create a copy of the buffer to avoid mutation during iteration
        frames_to_save = list(self.frame_buffer)
        
        timestamp = time.strftime("%Y%m%d-%H%M%S")
        filename = os.path.join(self.save_path, f"clip_{timestamp}.mp4")
        print(f"Saving {len(frames_to_save)} frames to {filename}")

        # Get the first frame to determine dimensions
        first_frame = cv2.imdecode(np.frombuffer(frames_to_save[0], np.uint8), cv2.IMWRITE_JPEG_QUALITY)
        height, width = first_frame.shape[:2]
        
        # Create VideoWriter object
        fourcc = cv2.VideoWriter_fourcc(*'mp4v')
        out = cv2.VideoWriter(filename, fourcc, self.fps, (width, height))
        
        # Write frames to video
        for frame_bytes in frames_to_save:
            frame = cv2.imdecode(np.frombuffer(frame_bytes, np.uint8), cv2.IMWRITE_JPEG_QUALITY)
            out.write(frame)
        
        out.release()
        print(f"Video saved to {filename}")

    def start_recording(self):
        print(f"Recording started. Press {self.save_key} to save the clip. Press 'q' to quit.")
        last_time = time.time()

        keyboard.on_press_key(self.save_key, lambda _: threading.Thread(target=self.save_buffer).start())
        keyboard.on_press_key('q', lambda _: self.stop_recording())

        while self.is_recording:
            current_time = time.time()
            
            # Capture frame if it's time for the next frame
            if current_time - last_time >= self.frame_time:
                frame = self.capture_screen()
                self.frame_buffer.append(frame)
                last_time = current_time
            
            # Small sleep to prevent maxing out CPU
            time.sleep(0.001)

    def stop_recording(self):
        self.is_recording = False
        print("Recording stopped.")

# Usage
if __name__ == "__main__":
    recorder = ScreenRecorder()
    recorder.start_recording()