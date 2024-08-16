import numpy as np
import mss
import cv2
import time
import keyboard
import os
import threading
import atexit
import shutil
import subprocess
from queue import Queue
import tempfile

class CircularVideoBuffer:
    def __init__(self, filename, fps, width, height, buffer_seconds):
        self.filename = filename
        self.fps = fps
        self.width = width
        self.height = height
        self.buffer_frames = buffer_seconds * fps
        self.frame_count = 0
        self.ffmpeg_process = None
        self.temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.raw')
        self.temp_filename = self.temp_file.name
        self.initialize_writer()

    def initialize_writer(self):
        if self.ffmpeg_process is not None:
            self.ffmpeg_process.terminate()
            self.ffmpeg_process.wait()

        gpu_option = self.detect_gpu()

        command = ['ffmpeg', '-y']

        if gpu_option:
            command.extend(gpu_option)

        command.extend([
            '-f', 'rawvideo',
            '-vcodec', 'rawvideo',
            '-s', f'{self.width}x{self.height}',
            '-pix_fmt', 'bgr24',
            '-r', str(self.fps),
            '-i', self.temp_filename,
            '-an',
            '-c:v', 'h264_nvenc' if gpu_option else 'libx264',
            '-preset', 'llhq' if gpu_option else 'ultrafast',
            '-b:v', '5M',
            '-maxrate', '10M',
            '-bufsize', '15M',
            '-f', 'mp4',
            self.filename
        ])

        try:
            self.ffmpeg_process = subprocess.Popen(command, stdin=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
            print(f"FFmpeg command: {' '.join(command)}")
            
            # Check if the process started successfully
            if self.ffmpeg_process.poll() is not None:
                raise Exception("FFmpeg process failed to start")
            
        except Exception as e:
            print(f"Failed to start FFmpeg process with GPU acceleration: {str(e)}")
            print("Falling back to CPU encoding...")
            self.initialize_cpu_writer()

    def initialize_cpu_writer(self):
        command = [
            'ffmpeg', '-y',
            '-f', 'rawvideo',
            '-vcodec', 'rawvideo',
            '-s', f'{self.width}x{self.height}',
            '-pix_fmt', 'bgr24',
            '-r', str(self.fps),
            '-i', self.temp_filename,
            '-an',
            '-c:v', 'libx264',
            '-preset', 'ultrafast',
            '-b:v', '5M',
            '-maxrate', '10M',
            '-bufsize', '15M',
            '-f', 'mp4',
            self.filename
        ]

        try:
            self.ffmpeg_process = subprocess.Popen(command, stdin=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
            print(f"FFmpeg CPU encoding command: {' '.join(command)}")
        except Exception as e:
            raise Exception(f"Failed to start FFmpeg process with CPU encoding: {str(e)}")

    def detect_gpu(self):
        try:
            subprocess.check_output(['nvidia-smi'])
            print("NVIDIA GPU detected, attempting to use NVENC")
            return ['-hwaccel', 'cuda']
        except:
            print("NVIDIA GPU not detected or drivers not up to date")
            return None

    def write_frame(self, frame):
        if self.frame_count >= self.buffer_frames:
            self.temp_file.seek(0)
            self.frame_count = 0
        
        try:
            if frame.dtype != np.uint8:
                frame = frame.astype(np.uint8)
            if frame.shape[2] == 4:  # If RGBA, convert to BGR
                frame = cv2.cvtColor(frame, cv2.COLOR_RGBA2BGR)
            
            self.temp_file.write(frame.tobytes())
            self.temp_file.flush()  # Ensure data is written to disk
            self.frame_count += 1
        except Exception as e:
            print(f"Error writing frame: {str(e)}")
            self.initialize_writer()

    def get_buffer(self):
        self.temp_file.flush()
        self.ffmpeg_process.stdin.close()
        self.ffmpeg_process.wait()
        
        stderr = self.ffmpeg_process.stderr.read()
        if "Conversion failed!" in stderr:
            print(f"FFmpeg encountered an error: {stderr}")
            return None
        
        if os.path.getsize(self.filename) == 0:
            print("Error: Output file is empty")
            return None
        
        return self.filename

    def release(self):
        if self.temp_file:
            self.temp_file.close()
        if self.ffmpeg_process:
            self.ffmpeg_process.terminate()
            self.ffmpeg_process.wait()
        if os.path.exists(self.temp_filename):
            os.unlink(self.temp_filename)

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
        self.frame_queue = Queue(maxsize=10)
        self.buffer_thread = None
        self.buffer_filename = os.path.join(self.save_path, "temp_buffer.mp4")
        self.circular_buffer = None
        atexit.register(self.cleanup)
        os.makedirs(self.save_path, exist_ok=True)


    def cleanup(self):
        if os.path.exists(self.buffer_filename):
            try:
                os.remove(self.buffer_filename)
                print(f"Temporary buffer file {self.buffer_filename} removed.")
            except Exception as e:
                print(f"Error removing temporary buffer file: {e}")

    def capture_screen(self):
        screenshot = np.array(self.sct.grab(self.monitor))
        return cv2.cvtColor(screenshot, cv2.COLOR_RGBA2BGR)

    def buffer_recording(self):
        width, height = self.monitor["width"], self.monitor["height"]
        self.circular_buffer = CircularVideoBuffer(self.buffer_filename, self.fps, width, height, self.buffer_seconds)
        
        while self.is_recording:
            if not self.frame_queue.empty():
                frame = self.frame_queue.get()
                self.circular_buffer.write_frame(frame)
            time.sleep(0.001)
        
        self.circular_buffer.release()

    def save_buffer(self):
        with self.save_lock:
            timestamp = time.strftime("%Y%m%d-%H%M%S")
            output_filename = os.path.join(self.save_path, f"clip_{timestamp}.mp4")
            
            try:
                buffer_file = self.circular_buffer.get_buffer()
                if buffer_file and os.path.exists(buffer_file):
                    shutil.copy2(buffer_file, output_filename)
                    print(f"Clip saved to {output_filename}")
                else:
                    print("Failed to save clip: Buffer file is invalid or empty")
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
                
                time.sleep(0.001)
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
    try:
        recorder = ScreenRecorder()
        recorder.start_recording()
    except Exception as e:
        print(f"Error: {str(e)}")
        print("\nTroubleshooting steps:")
        print("1. Ensure FFmpeg is installed and added to your system PATH.")
        print("2. Verify that you have a supported NVIDIA or AMD GPU with up-to-date drivers.")
        print("3. If the issue persists, please check the error message and consult the documentation.")