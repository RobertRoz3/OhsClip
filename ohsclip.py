import numpy as np
import mss
import cv2
import time
import keyboard
import os
import threading
from queue import Queue

class ScreenRecorder:
    def __init__(self, buffer_seconds=60, fps=30, save_key='f12', save_path=r'C:\Users\osceo\Desktop\Stuff\OhsClip\OhsClip\Testing'):
        self.sct = mss.mss()
        self.buffer_seconds = buffer_seconds
        self.fps = fps
        self.frame_time = 1 / fps
        self.monitor = self.sct.monitors[1]
        self.save_key = save_key
        self.save_path = save_path
        self.is_recording = True
        self.save_lock = threading.Lock()

        self.frame_queue = Queue(maxsize=10)  # Buffer a few frames
        self.buffer_thread = None
        self.buffer_filename = os.path.join(self.save_path, "temp_buffer.mp4")

        os.makedirs(self.save_path, exist_ok=True)

    def capture_screen(self):
        return np.array(self.sct.grab(self.monitor))

    def buffer_recording(self):
        width, height = self.monitor["width"], self.monitor["height"]
        fourcc = cv2.VideoWriter_fourcc(*'avc1')  # H.264 codec
        out = cv2.VideoWriter(self.buffer_filename, fourcc, self.fps, (width, height))

        start_time = time.time()
        frames_written = 0

        while self.is_recording:
            if not self.frame_queue.empty():
                frame = self.frame_queue.get()
                out.write(frame)
                frames_written += 1

                # If buffer duration exceeded, move file pointer back
                if frames_written >= self.buffer_seconds * self.fps:
                    current_pos = out.get(cv2.CAP_PROP_POS_FRAMES)
                    out.set(cv2.CAP_PROP_POS_FRAMES, current_pos - frames_written)
                    frames_written = 0

            time.sleep(0.001)  # Small sleep to prevent CPU hogging

        out.release()

    def save_buffer(self):
        with self.save_lock:
            timestamp = time.strftime("%Y%m%d-%H%M%S")
            output_filename = os.path.join(self.save_path, f"clip_{timestamp}.mp4")
            
            try:
                # Copy the buffer file
                os.system(f'copy "{self.buffer_filename}" "{output_filename}"')
                print(f"Clip saved to {output_filename}")
            except Exception as e:
                print(f"Error saving video: {e}")

    def start_recording(self):
        print(f"Recording started. Press {self.save_key} to save the clip. Press 'q' to quit.")
        
        self.buffer_thread = threading.Thread(target=self.buffer_recording)
        self.buffer_thread.start()

        keyboard.on_press_key(self.save_key, lambda _: threading.Thread(target=self.save_buffer).start())
        keyboard.on_press_key('q', lambda _: self.stop_recording())

        last_time = time.time()
        try:
            while self.is_recording:
                current_time = time.time()
                
                if current_time - last_time >= self.frame_time:
                    frame = self.capture_screen()
                    if not self.frame_queue.full():
                        self.frame_queue.put(frame)
                    last_time = current_time
                
                time.sleep(0.001)  # Small sleep to prevent maxing out CPU
        except Exception as e:
            print(f"Error during recording: {e}")
        finally:
            self.stop_recording()

    def stop_recording(self):
        self.is_recording = False
        if self.buffer_thread:
            self.buffer_thread.join()
        print("Recording stopped.")

# Usage
if __name__ == "__main__":
    recorder = ScreenRecorder()
    recorder.start_recording()