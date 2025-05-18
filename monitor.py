import time
import sys
import os
import subprocess
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

class RestartHandler(FileSystemEventHandler):
    def __init__(self):
        self.process = None
        self.start_app()
    
    def start_app(self):
        if self.process:
            self.process.terminate()
            self.process.wait()
        print("\nStarting application...")
        self.process = subprocess.Popen([sys.executable, 'main.py'])
    
    def on_modified(self, event):
        if event.src_path.endswith('.py'):
            print(f"\nFile {event.src_path} has been modified. Restarting...")
            self.start_app()

def main():
    event_handler = RestartHandler()
    observer = Observer()
    observer.schedule(event_handler, '.', recursive=False)
    observer.start()
    
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nStopping application...")
        observer.stop()
        if event_handler.process:
            event_handler.process.terminate()
    observer.join()

if __name__ == "__main__":
    main()
