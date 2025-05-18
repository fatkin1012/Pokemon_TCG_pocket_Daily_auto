import sys
import time
import subprocess
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
import os
import signal

class CodeChangeHandler(FileSystemEventHandler):
    def __init__(self, target_file):
        self.target_file = target_file
        self.process = None
        self.start_process()

    def start_process(self):
        if self.process:
            # 在 Windows 上使用 taskkill 確保進程被終止
            subprocess.run(['taskkill', '/F', '/T', '/PID', str(self.process.pid)], 
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        print("\n正在啟動程式...")
        self.process = subprocess.Popen([sys.executable, self.target_file])

    def on_modified(self, event):
        if event.src_path.endswith('.py'):
            print(f"\n檢測到文件變更: {event.src_path}")
            self.start_process()

def main():
    if len(sys.argv) < 2:
        print("使用方法: python monitor.py <target_script.py>")
        sys.exit(1)

    target_file = sys.argv[1]
    if not os.path.exists(target_file):
        print(f"錯誤: 找不到文件 {target_file}")
        sys.exit(1)

    # 設置監控
    event_handler = CodeChangeHandler(target_file)
    observer = Observer()
    observer.schedule(event_handler, path='.', recursive=False)
    observer.start()

    print(f"開始監控文件變更... (按 Ctrl+C 停止)")
    
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n停止監控...")
        if event_handler.process:
            event_handler.process.terminate()
        observer.stop()
    observer.join()

if __name__ == "__main__":
    main()
