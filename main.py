import dearpygui.dearpygui as dpg
from ppadb.client import Client as AdbClient
import threading
import time
import io
import pytesseract
from PIL import Image
import os
import json
import base64
import subprocess
import sys
import socket
import cv2
import numpy as np
from pathlib import Path
import win32gui
import win32api
import win32con
import ctypes
from ctypes import wintypes
import traceback

# 全局變量
adb_client = None
device = None
is_connected = False
is_running = False
current_task = None
EMULATOR_TITLE = "MuMu模拟器12"  # 根據實際使用的模擬器修改

# 字體設定
FONT_PATH = os.path.join(os.environ.get('SystemRoot', 'C:\\Windows'), 'Fonts', 'msjh.ttc')
if not os.path.exists(FONT_PATH):
    FONT_PATH = os.path.join(os.environ.get('SystemRoot', 'C:\\Windows'), 'Fonts', 'mingliu.ttc')

# 任務定義
TASKS = {
    "daily_login": {
        "name": "每日登入",
        "enabled": True
    },
    "collect_rewards": {
        "name": "領取獎勵",
        "enabled": True
    },
    "daily_battles": {
        "name": "每日對戰",
        "enabled": True
    }
}

# 模擬器端口列表
EMULATOR_PORTS = [16384, 5555, 7555, 62001]

class WindowNotFoundError(Exception):
    pass

class GameAutomation:
    def __init__(self):
        self.last_click_time = 0
        self.hwnd = None
        self.load_button_positions()
        
    def find_window(self):
        """尋找模擬器視窗"""
        self.hwnd = win32gui.FindWindow(None, EMULATOR_TITLE)
        if not self.hwnd:
            raise WindowNotFoundError(f"找不到視窗: {EMULATOR_TITLE}")
        return self.hwnd
        
    def get_window_rect(self):
        """獲取視窗位置和大小"""
        if not self.hwnd:
            self.find_window()
        return win32gui.GetWindowRect(self.hwnd)
        
    def window_to_screen(self, x, y):
        """將視窗內座標轉換為螢幕座標"""
        left, top, _, _ = self.get_window_rect()
        return left + x, top + y

    def load_button_positions(self):
        """載入按鈕位置配置"""
        self.button_positions = {
            "登入獎勵": {"x": 500, "y": 500},  # 這些座標是相對於視窗的座標
            "確認": {"x": 600, "y": 600},
            "獎勵": {"x": 400, "y": 400},
            "一鍵領取": {"x": 700, "y": 500},
            "對戰": {"x": 300, "y": 500},
            "開始": {"x": 500, "y": 600}
        }
        
        # 嘗試從配置文件載入
        config_file = "button_positions.json"
        if os.path.exists(config_file):
            try:
                with open(config_file, 'r', encoding='utf-8') as f:
                    self.button_positions.update(json.load(f))
            except Exception as e:
                log_error(f"載入按鈕配置失敗: {str(e)}")

    def save_button_positions(self):
        """儲存按鈕位置到文件"""
        try:
            with open("button_positions.json", 'w', encoding='utf-8') as f:
                json.dump(self.button_positions, f, ensure_ascii=False, indent=2)
        except Exception as e:
            log_error(f"儲存按鈕配置失敗: {str(e)}")

    def click_position(self, x, y):
        """在模擬器視窗內點擊指定位置"""
        try:
            if not self.hwnd:
                self.find_window()
                
            # 確保視窗存在
            if not win32gui.IsWindow(self.hwnd):
                raise WindowNotFoundError("模擬器視窗已關閉")
                
            # 將視窗內座標轉換為螢幕座標
            screen_x, screen_y = self.window_to_screen(x, y)
            
            # 發送滑鼠事件
            lparam = win32api.MAKELONG(x, y)
            win32gui.PostMessage(self.hwnd, win32con.WM_LBUTTONDOWN, win32con.MK_LBUTTON, lparam)
            time.sleep(0.1)
            win32gui.PostMessage(self.hwnd, win32con.WM_LBUTTONUP, 0, lparam)
            
            log_info(f"點擊視窗內位置: ({x}, {y})")
            return True
            
        except WindowNotFoundError as e:
            log_error(f"找不到模擬器視窗: {str(e)}")
            return False
        except Exception as e:
            log_error(f"點擊失敗: {str(e)}")
            return False

    def save_current_position(self, button_name):
        """儲存當前滑鼠位置作為按鈕位置"""
        try:
            if not self.hwnd:
                self.find_window()
                
            # 獲取當前滑鼠位置
            cursor_pos = win32gui.GetCursorPos()
            # 獲取視窗位置
            window_rect = self.get_window_rect()
            
            # 計算相對於視窗的座標
            rel_x = cursor_pos[0] - window_rect[0]
            rel_y = cursor_pos[1] - window_rect[1]
            
            # 儲存座標
            self.button_positions[button_name] = {"x": rel_x, "y": rel_y}
            self.save_button_positions()
            
            log_info(f"已儲存按鈕 '{button_name}' 的位置: ({rel_x}, {rel_y})")
            return True
            
        except Exception as e:
            log_error(f"儲存位置失敗: {str(e)}")
            return False

    def wait_and_click(self, target, max_retries=3):
        """等待並點擊目標"""
        log_info(f"尋找並點擊: {target}")
        
        # 檢查是否有預設位置
        if target in self.button_positions:
            pos = self.button_positions[target]
            return self.click_position(pos["x"], pos["y"])
            
        return False

    def capture_window(self):
        """擷取模擬器視窗畫面"""
        try:
            if not self.hwnd:
                self.find_window()
                
            # 獲取視窗大小
            left, top, right, bottom = self.get_window_rect()
            width = right - left
            height = bottom - top
            
            # 創建設備上下文
            hwndDC = win32gui.GetWindowDC(self.hwnd)
            mfcDC = win32gui.CreateDCFromHandle(hwndDC)
            saveDC = win32gui.CreateCompatibleDC(mfcDC)
            
            # 創建位圖
            saveBitMap = win32gui.CreateCompatibleBitmap(mfcDC, width, height)
            win32gui.SelectObject(saveDC, saveBitMap)
            
            # 複製畫面
            win32gui.BitBlt(saveDC, 0, 0, width, height, mfcDC, 0, 0, win32con.SRCCOPY)
            
            # 轉換為 PIL Image
            bmpinfo = saveBitMap.GetInfo()
            bmpstr = saveBitMap.GetBitmapBits(True)
            im = Image.frombuffer('RGB',
                                (bmpinfo['bmWidth'], bmpinfo['bmHeight']),
                                bmpstr, 'raw', 'BGRX', 0, 1)
            
            # 清理資源
            win32gui.DeleteObject(saveBitMap.GetHandle())
            win32gui.DeleteDC(saveDC)
            win32gui.DeleteDC(mfcDC)
            win32gui.ReleaseDC(self.hwnd, hwndDC)
            
            return im
            
        except Exception as e:
            log_error(f"擷取視窗畫面失敗: {str(e)}")
            return None

# 日誌函數
def log_info(message):
    """記錄信息"""
    if dpg.does_item_exist("log_window"):
        dpg.add_text(f"[INFO] {message}", parent="log_window")
        
def log_warning(message):
    """記錄警告"""
    if dpg.does_item_exist("log_window"):
        dpg.add_text(f"[WARNING] {message}", color=[255, 255, 0], parent="log_window")
        
def log_error(message):
    """記錄錯誤"""
    if dpg.does_item_exist("log_window"):
        dpg.add_text(f"[ERROR] {message}", color=[255, 0, 0], parent="log_window")

# ADB 路徑配置
def get_adb_path():
    """獲取 ADB 執行檔路徑"""
    # 首先檢查環境變量
    if 'ANDROID_HOME' in os.environ:
        sdk_path = os.environ['ANDROID_HOME']
        adb_path = os.path.join(sdk_path, 'platform-tools', 'adb.exe')
        if os.path.exists(adb_path):
            return adb_path
    
    # 檢查常見的安裝路徑
    common_paths = [
        r"C:\Program Files (x86)\Android\android-sdk\platform-tools\adb.exe",
        r"C:\Program Files\Android\android-sdk\platform-tools\adb.exe",
        # MuMu 模擬器的 ADB 路徑
        r"C:\Program Files\MuMu\emulator\nemu\vmonitor\bin\adb.exe",
        r"C:\Program Files (x86)\MuMu\emulator\nemu\vmonitor\bin\adb.exe",
    ]
    
    for path in common_paths:
        if os.path.exists(path):
            return path
            
    # 如果都找不到，使用當前目錄下的 adb
    current_dir = os.path.dirname(os.path.abspath(__file__))
    adb_path = os.path.join(current_dir, "adb.exe")
    if os.path.exists(adb_path):
        return adb_path
        
    return None

def check_adb_server():
    """檢查 ADB 服務器狀態"""
    try:
        # 嘗試通過 socket 連接 ADB 服務器
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(1)
        result = sock.connect_ex(('127.0.0.1', 5037))
        sock.close()
        
        if result == 0:
            log_info("ADB 服務器正在運行")
            return True
        else:
            log_warning("ADB 服務器未運行")
            return False
    except Exception as e:
        log_error(f"檢查 ADB 服務器時出錯: {str(e)}")
        return False

def wait_for_adb_server(timeout=10):
    """等待 ADB 服務器完全啟動"""
    start_time = time.time()
    while time.time() - start_time < timeout:
        try:
            if check_adb_server():
                # 再等待一秒確保服務器完全就緒
                time.sleep(1)
                return True
        except:
            pass
        time.sleep(0.5)
    return False

def start_adb_server():
    """啟動 ADB 服務器"""
    adb_path = get_adb_path()
    if not adb_path:
        log_error("找不到 ADB 執行檔")
        return False
        
    try:
        log_info(f"使用 ADB 路徑: {adb_path}")
        
        # 檢查是否已有 ADB 服務器運行
        try:
            subprocess.run([adb_path, 'version'], 
                         capture_output=True, text=True, timeout=5)
            log_info("檢測到現有 ADB 服務器")
        except:
            log_warning("無法檢測 ADB 版本，可能沒有運行中的服務器")
        
        # 先嘗試停止現有的 ADB 服務器
        log_info("正在停止現有的 ADB 服務器...")
        try:
            subprocess.run([adb_path, 'kill-server'], timeout=5)
            time.sleep(2)
            log_info("成功停止 ADB 服務器")
        except Exception as e:
            log_warning(f"停止 ADB 服務器時出錯: {str(e)}")
        
        # 啟動新的 ADB 服務器
        log_info("正在啟動新的 ADB 服務器...")
        try:
            result = subprocess.run([adb_path, 'start-server'], 
                                  capture_output=True, text=True, timeout=5)
            log_info(f"啟動命令輸出: {result.stdout.strip()}")
            if result.stderr:
                log_warning(f"啟動警告: {result.stderr.strip()}")
        except Exception as e:
            log_error(f"啟動 ADB 服務器失敗: {str(e)}")
            return False
        
        # 等待服務器啟動
        log_info("等待 ADB 服務器啟動...")
        if not wait_for_adb_server(30):
            log_error("ADB 服務器啟動超時")
            return False
            
        # 驗證服務器是否正常運行
        try:
            version_result = subprocess.run([adb_path, 'version'], 
                                         capture_output=True, text=True, timeout=5)
            log_info(f"ADB 版本信息:\n{version_result.stdout.strip()}")
            
            devices_result = subprocess.run([adb_path, 'devices'], 
                                         capture_output=True, text=True, timeout=5)
            log_info(f"已連接設備:\n{devices_result.stdout.strip()}")
        except Exception as e:
            log_error(f"驗證 ADB 服務器時出錯: {str(e)}")
            return False
            
        log_info("ADB 服務器已成功啟動")
        return True
        
    except subprocess.TimeoutExpired:
        log_error("啟動 ADB 服務器超時")
        return False
    except Exception as e:
        log_error(f"啟動 ADB 服務器時發生錯誤: {str(e)}")
        return False

def create_adb_client(host, port, max_retries=3):
    """創建 ADB 客戶端，帶重試機制"""
    for attempt in range(max_retries):
        try:
            log_info(f"===== 開始第 {attempt + 1} 次嘗試創建 ADB 客戶端 =====")
            
            # 嘗試通過 ADB 命令直接連接
            adb_path = get_adb_path()
            if adb_path:
                try:
                    # 直接嘗試連接，不做其他檢查
                    subprocess.run([adb_path, 'connect', f'{host}:{port}'], 
                                capture_output=True, text=True, timeout=5)
                except Exception as e:
                    log_error(f"ADB 連接命令執行失敗: {str(e)}")
            
            # 創建 ADB 客戶端並返回
            client = AdbClient(host=host, port=port)
            return client
            
        except Exception as e:
            log_warning(f"創建 ADB 客戶端失敗 (嘗試 {attempt + 1}/{max_retries})")
            log_error(f"錯誤詳情: {str(e)}")
            if attempt < max_retries - 1:
                log_info("等待 1 秒後重試...")
                time.sleep(1)
            else:
                log_error("已達到最大重試次數")
                return None
    return None

def debug_adb_connection(host, port):
    """調試 ADB 連接"""
    try:
        log_info(f"正在測試 ADB 連接 {host}:{port}")
        
        # 檢查 ADB 服務器狀態
        if not check_adb_server():
            log_warning("ADB 服務器未運行，嘗試啟動...")
            if not start_adb_server():
                log_error("無法啟動 ADB 服務器")
                return False
        
        # 測試端口是否開放
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(2)
        result = sock.connect_ex((host, port))
        if result == 0:
            log_info(f"端口 {port} 已開放")
        else:
            log_error(f"端口 {port} 未開放")
            return False
        sock.close()
        
        # 嘗試創建 ADB 客戶端
        client = create_adb_client(host, port)
        if not client:
            return False
        
        # 列出所有設備
        try:
            devices = client.devices()
            log_info(f"找到 {len(devices)} 個設備:")
            for device in devices:
                log_info(f"  - 設備 ID: {device.serial}")
                # 獲取設備屬性
                try:
                    props = device.get_properties()
                    log_info(f"    設備信息:")
                    log_info(f"    - 產品: {props.get('ro.product.model', 'unknown')}")
                    log_info(f"    - 製造商: {props.get('ro.product.manufacturer', 'unknown')}")
                    log_info(f"    - Android 版本: {props.get('ro.build.version.release', 'unknown')}")
                except:
                    log_warning("無法獲取設備詳細信息")
        except Exception as e:
            log_error(f"列出設備失敗: {str(e)}")
            return False
            
        return True
    except Exception as e:
        log_error(f"調試過程出錯: {str(e)}")
        return False

def scan_emulator_ports(host="127.0.0.1"):
    """掃描指定主機上的模擬器端口"""
    log_info(f"開始掃描主機 {host} 的模擬器端口...")
    for port in EMULATOR_PORTS:
        try:
            log_info(f"正在測試端口 {port}...")
            client = AdbClient(host=host, port=port)
            devices = client.devices()
            if devices:
                log_info(f"在端口 {port} 上找到設備")
                return client, devices[0]
            else:
                log_info(f"端口 {port} 可連接但未找到設備")
        except Exception as e:
            log_info(f"端口 {port} 連接失敗: {str(e)}")
    return None, None

def scan_for_emulator():
    """掃描所有可能的模擬器連接"""
    log_info("開始掃描模擬器...")
    
    # 首先嘗試本地連接
    client, device = scan_emulator_ports("127.0.0.1")
    if client and device:
        return client, device
        
    # 嘗試模擬器內部IP
    client, device = scan_emulator_ports("10.0.2.15")
    if client and device:
        return client, device
    
    log_warning("未找到模擬器，請確保模擬器已啟動")
    return None, None

def update_connection_status(status: bool, message: str):
    """更新連接狀態顯示"""
    try:
        if not dpg.is_dearpygui_running():
            return
            
        status_text = "已連接" if status else "未連接"
        status_color = [0, 255, 0, 255] if status else [255, 0, 0, 255]
        
        if dpg.does_item_exist("connection_status"):
            dpg.set_item_label("connection_status", f"連接狀態: {status_text}")
        if dpg.does_item_exist("connection_status_color"):
            dpg.configure_item("connection_status_color", default_value=status_color)
        
        # 記錄日誌
        if status:
            log_info(message)
        else:
            log_warning(message)
    except Exception as e:
        print(f"更新狀態顯示時出錯: {str(e)}")
        print(traceback.format_exc())

def connect_adb_callback():
    """連接 ADB 的回調函數"""
    global adb_client, device, is_connected
    
    try:
        if not dpg.does_item_exist("adb_address_input"):
            log_error("GUI 元件尚未初始化")
            return
            
        # 獲取用戶輸入的地址
        adb_address = dpg.get_value("adb_address_input")
        if not adb_address:
            log_error("請輸入 ADB 地址")
            return
            
        log_info(f"正在嘗試連接到: {adb_address}")
        
        if ":" not in adb_address:
            log_error("無效的 ADB 地址格式，應為 'host:port'")
            return
            
        host, port = adb_address.split(":")
        try:
            port = int(port)
        except ValueError:
            log_error("端口必須是數字")
            return
            
        # 檢查 ADB 服務器狀態
        if not check_adb_server():
            log_info("ADB 服務器未運行，嘗試啟動...")
            if not start_adb_server():
                log_error("無法啟動 ADB 服務器")
                update_connection_status(False, "ADB 服務器啟動失敗")
                return
                
        # 等待 ADB 服務器完全啟動
        if not wait_for_adb_server(timeout=10):
            log_error("ADB 服務器啟動超時")
            update_connection_status(False, "ADB 服務器啟動超時")
            return
            
        # 嘗試直接通過 ADB 命令連接
        adb_path = get_adb_path()
        if adb_path:
            try:
                # 先嘗試斷開所有連接
                subprocess.run([adb_path, 'disconnect'], capture_output=True, text=True, timeout=5)
                # 然後連接到指定地址
                result = subprocess.run([adb_path, 'connect', f'{host}:{port}'], 
                                     capture_output=True, text=True, timeout=5)
                log_info(f"ADB 連接結果: {result.stdout.strip()}")
                if result.stderr:
                    log_warning(f"ADB 警告: {result.stderr.strip()}")
            except Exception as e:
                log_error(f"執行 ADB 命令時出錯: {str(e)}")
                
        # 創建 ADB 客戶端
        adb_client = create_adb_client(host, port)
        if not adb_client:
            log_error("無法創建 ADB 客戶端")
            update_connection_status(False, "ADB 客戶端創建失敗")
            return
            
        # 檢查設備連接
        try:
            devices = adb_client.devices()
            if not devices:
                log_warning("未找到已連接的設備")
                update_connection_status(False, "未找到設備")
                return
                
            device = devices[0]  # 使用第一個找到的設備
            is_connected = True
            update_connection_status(True, f"成功連接到設備: {device.serial}")
            
            # 更新按鈕狀態
            dpg.configure_item("start_task_button", enabled=True)
            dpg.configure_item("debug_button", enabled=True)
            dpg.configure_item("stop_task_button", enabled=False)
            
        except Exception as e:
            log_error(f"檢查設備時出錯: {str(e)}")
            update_connection_status(False, "設備檢查失敗")
            
    except Exception as e:
        print(f"連接過程出錯: {str(e)}")
        print(traceback.format_exc())
        is_connected = False
        device = None
        update_connection_status(False, "連接失敗")

def disconnect_adb_callback():
    global adb_client, device, is_connected, is_running
    if is_connected:
        is_running = False
        device = None
        adb_client = None
        is_connected = False
        update_connection_status(False, "已斷開連接")
        dpg.configure_item("start_task_button", enabled=False)

def execute_daily_tasks():
    global is_running, current_task
    automation = GameAutomation()
    
    try:
        # 首先尋找模擬器視窗
        try:
            automation.find_window()
        except WindowNotFoundError:
            log_error(f"找不到模擬器視窗: {EMULATOR_TITLE}")
            return
            
        while is_running:
            # 執行每個已啟用的任務
            for task_id, task_info in TASKS.items():
                if not task_info["enabled"] or not is_running:
                    continue
                    
                current_task = task_info["name"]
                log_info(f"開始執行任務: {current_task}")
                
                if task_id == "daily_login":
                    # 處理每日登入
                    automation.wait_and_click("登入獎勵")
                    time.sleep(1)
                    automation.wait_and_click("確認")
                    
                elif task_id == "collect_rewards":
                    # 處理領取獎勵
                    automation.wait_and_click("獎勵")
                    time.sleep(1)
                    automation.wait_and_click("一鍵領取")
                    
                elif task_id == "daily_battles":
                    # 處理每日對戰
                    automation.wait_and_click("對戰")
                    time.sleep(1)
                    automation.wait_and_click("開始")
                    
                time.sleep(2)  # 等待動畫完成
                
            is_running = False
            log_info("所有任務完成")
            
    except Exception as e:
        log_error(f"任務執行出錯: {str(e)}")
        is_running = False
    finally:
        current_task = None
        dpg.configure_item("start_task_button", enabled=True)
        dpg.configure_item("stop_task_button", enabled=False)

def start_daily_tasks_callback():
    global is_running
    if not is_connected:
        log_warning("請先連接到模擬器")
        return
        
    is_running = True
    dpg.configure_item("start_task_button", enabled=False)
    dpg.configure_item("stop_task_button", enabled=True)
    
    # 在新線程中執行任務
    thread = threading.Thread(target=execute_daily_tasks)
    thread.daemon = True
    thread.start()

def stop_daily_tasks_callback():
    global is_running
    is_running = False
    log_info("正在停止任務...")

def toggle_task_callback(sender):
    task_id = dpg.get_item_user_data(sender)
    TASKS[task_id]["enabled"] = dpg.get_value(sender)

def auto_connect():
    """自動連接模擬器的函數"""
    if not is_connected:
        connect_adb_callback()

def debug_button_callback():
    """調試按鈕回調函數"""
    try:
        if not dpg.does_item_exist("adb_address_input"):
            log_error("GUI 元件尚未初始化")
            return
            
        adb_address = dpg.get_value("adb_address_input")
        if not adb_address:
            log_error("請輸入 ADB 地址")
            return
            
        if ":" not in adb_address:
            log_error("無效的 ADB 地址格式，應為 'host:port'")
            return
            
        host, port = adb_address.split(":")
        try:
            port = int(port)
        except ValueError:
            log_error("端口必須是數字")
            return
            
        debug_adb_connection(host, port)
    except Exception as e:
        print(f"調試過程出錯: {str(e)}")
        print(traceback.format_exc())
        log_error(f"調試過程出錯: {str(e)}")

def adb_tools_callback():
    """ADB 工具按鈕回調"""
    adb_path = get_adb_path()
    if not adb_path:
        log_error("找不到 ADB 執行檔，請確保已安裝 Android SDK 或模擬器")
        return
        
    log_info("===== ADB 工具診斷 =====")
    log_info(f"ADB 路徑: {adb_path}")
    
    # 檢查 ADB 服務器
    if check_adb_server():
        log_info("ADB 服務器狀態: 運行中")
    else:
        log_warning("ADB 服務器狀態: 未運行")
        if start_adb_server():
            log_info("成功啟動 ADB 服務器")
        else:
            log_error("無法啟動 ADB 服務器")
            return
    
    try:
        # 執行 adb devices -l 獲取詳細設備信息
        result = subprocess.run([adb_path, 'devices', '-l'], 
                              capture_output=True, text=True, timeout=5)
        log_info("已連接的設備:")
        log_info(result.stdout)
        
        # 檢查 MuMu 模擬器端口
        ports_to_check = [16384, 5555, 7555]
        for port in ports_to_check:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(1)
            result = sock.connect_ex(('127.0.0.1', port))
            status = "開放" if result == 0 else "關閉"
            log_info(f"端口 {port} 狀態: {status}")
            sock.close()
            
        # 嘗試通過 adb connect 連接模擬器
        log_info("嘗試連接模擬器...")
        result = subprocess.run([adb_path, 'connect', '127.0.0.1:16384'], 
                              capture_output=True, text=True, timeout=5)
        log_info(result.stdout)
        
    except subprocess.TimeoutExpired:
        log_error("執行 ADB 命令超時")
    except Exception as e:
        log_error(f"執行 ADB 命令失敗: {str(e)}")

def save_position_callback():
    """儲存當前滑鼠位置作為按鈕位置"""
    button_name = dpg.get_value("button_name_input")
    if button_name:
        automation = GameAutomation()
        automation.save_current_position(button_name)
    else:
        log_warning("請輸入按鈕名稱")

def select_window_callback():
    """選擇模擬器視窗"""
    global EMULATOR_TITLE
    title = dpg.get_value("window_title_input")
    if title:
        EMULATOR_TITLE = title
        try:
            automation = GameAutomation()
            automation.find_window()
            log_info(f"成功找到視窗: {title}")
        except WindowNotFoundError:
            log_error(f"找不到視窗: {title}")
    else:
        log_warning("請輸入視窗標題")

# 在 dpg.create_viewport() 之前添加以下代碼：
dpg.create_context()

# 添加中文字體支援
with dpg.font_registry():
    with dpg.font(FONT_PATH, 18) as default_font:
        dpg.add_font_range_hint(dpg.mvFontRangeHint_Chinese_Full)
    with dpg.font(FONT_PATH, 20) as title_font:
        dpg.add_font_range_hint(dpg.mvFontRangeHint_Chinese_Full)

# 設定默認字體
dpg.bind_font(default_font)

# 在 dpg.create_context() 之後，創建主視窗之前添加以下代碼：
with dpg.theme() as global_theme:
    with dpg.theme_component(dpg.mvAll):
        dpg.add_theme_color(dpg.mvThemeCol_Text, [255, 255, 255])
        dpg.add_theme_color(dpg.mvThemeCol_WindowBg, [36, 36, 36])
        dpg.add_theme_color(dpg.mvThemeCol_FrameBg, [48, 48, 48])
        dpg.add_theme_color(dpg.mvThemeCol_Button, [59, 59, 59])
        dpg.add_theme_color(dpg.mvThemeCol_ButtonHovered, [79, 79, 79])
        dpg.add_theme_color(dpg.mvThemeCol_ButtonActive, [89, 89, 89])

dpg.bind_theme(global_theme)

# 創建主視窗
with dpg.window(label="寶可夢 TCG 每日助手", width=600, height=500, tag="main_window"):
    dpg.bind_item_font("main_window", title_font)
    
    with dpg.group(horizontal=True):
        dpg.add_text("ADB 連接設定")
        dpg.add_text("連接狀態: 未連接", tag="connection_status")
        dpg.add_color_edit(default_value=[255, 0, 0, 255], tag="connection_status_color", 
                          no_inputs=True, no_picker=True, alpha_preview=0, enabled=False)
    
    with dpg.group(horizontal=True):
        dpg.add_input_text(label="ADB 地址", default_value="127.0.0.1:16384", 
                          tag="adb_address_input", width=200)
        dpg.add_button(label="自動掃描", callback=connect_adb_callback)
        dpg.add_button(label="手動連接", callback=connect_adb_callback)
        dpg.add_button(label="斷開", callback=disconnect_adb_callback)
        dpg.add_button(label="調試連接", callback=debug_button_callback, 
                      tag="debug_button", enabled=True)
        dpg.add_button(label="ADB工具", callback=adb_tools_callback, 
                      tag="adb_tools_button")
    
    dpg.add_separator()
    
    dpg.add_text("任務設定:")
    for task_id, task_info in TASKS.items():
        dpg.add_checkbox(label=task_info["name"], default_value=task_info["enabled"],
                        callback=toggle_task_callback, user_data=task_id)
    
    dpg.add_separator()
    
    with dpg.group(horizontal=True):
        dpg.add_button(label="開始每日任務", callback=start_daily_tasks_callback,
                      enabled=False, tag="start_task_button")
        dpg.add_button(label="停止任務", callback=stop_daily_tasks_callback,
                      enabled=False, tag="stop_task_button")
    
    dpg.add_separator()
    
    dpg.add_text("日誌:")
    with dpg.child_window(height=-100, tag="log_window"):
        pass

    with dpg.group(horizontal=True):
        dpg.add_input_text(label="按鈕名稱", tag="button_name_input", width=200)
        dpg.add_button(label="儲存當前位置", callback=save_position_callback)

    with dpg.group(horizontal=True):
        dpg.add_input_text(label="視窗標題", default_value=EMULATOR_TITLE, 
                          tag="window_title_input", width=200)
        dpg.add_button(label="選擇視窗", callback=select_window_callback)

dpg.create_viewport(title='寶可夢 TCG 每日助手', width=620, height=550)
dpg.setup_dearpygui()
dpg.show_viewport()
dpg.set_primary_window("main_window", True)
dpg.start_dearpygui()
dpg.destroy_context()
