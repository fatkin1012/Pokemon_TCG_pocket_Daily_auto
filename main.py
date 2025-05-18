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
from pathlib import Path

# 全局變量
adb_client = None
device = None
is_connected = False
is_running = False
current_task = None

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
        return result == 0
    except:
        return False

def wait_for_adb_server(timeout=30):
    """等待 ADB 服務器完全啟動"""
    start_time = time.time()
    while time.time() - start_time < timeout:
        try:
            # 嘗試連接 ADB 服務器
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(1)
            result = sock.connect_ex(('127.0.0.1', 5037))
            sock.close()
            
            if result == 0:
                # 再等待一秒確保服務器完全就緒
                time.sleep(1)
                return True
                
            time.sleep(1)
        except:
            time.sleep(1)
            continue
    return False

def start_adb_server():
    """啟動 ADB 服務器"""
    adb_path = get_adb_path()
    if not adb_path:
        log_error("找不到 ADB 執行檔")
        return False
        
    try:
        log_info(f"使用 ADB 路徑: {adb_path}")
        # 先嘗試停止現有的 ADB 服務器
        subprocess.run([adb_path, 'kill-server'], timeout=5)
        time.sleep(2)
        
        # 啟動新的 ADB 服務器
        subprocess.run([adb_path, 'start-server'], timeout=5)
        
        # 等待服務器啟動
        log_info("等待 ADB 服務器啟動...")
        if not wait_for_adb_server(30):
            log_error("ADB 服務器啟動超時")
            return False
            
        log_info("ADB 服務器已成功啟動")
        return True
        
    except subprocess.TimeoutExpired:
        log_error("啟動 ADB 服務器超時")
        return False
    except Exception as e:
        log_error(f"啟動 ADB 服務器失敗: {str(e)}")
        return False

def create_adb_client(host, port, max_retries=3):
    """創建 ADB 客戶端，帶重試機制"""
    for attempt in range(max_retries):
        try:
            log_info(f"嘗試創建 ADB 客戶端 (第 {attempt + 1} 次嘗試)...")
            client = AdbClient(host=host, port=port)
            # 測試連接
            version = client.version()
            log_info(f"ADB 版本: {version}")
            return client
        except Exception as e:
            log_warning(f"創建 ADB 客戶端失敗 (嘗試 {attempt + 1}/{max_retries}): {str(e)}")
            if attempt < max_retries - 1:
                log_info("等待 3 秒後重試...")
                time.sleep(3)
                # 重新啟動 ADB 服務器
                if not start_adb_server():
                    log_error("重新啟動 ADB 服務器失敗")
                    return None
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
    dpg.configure_item("connection_status", default_value=f"連接狀態: {'已連接' if status else '未連接'}")
    dpg.set_value("connection_status_color", [0, 255, 0, 255] if status else [255, 0, 0, 255])
    log_info(message)

def connect_adb_callback():
    global adb_client, device, is_connected
    
    try:
        # 確保 ADB 服務器運行
        if not check_adb_server():
            log_warning("ADB 服務器未運行，嘗試啟動...")
            if not start_adb_server():
                log_error("無法啟動 ADB 服務器")
                return
        
        # 首先嘗試使用用戶輸入的地址
        adb_address = dpg.get_value("adb_address_input")
        log_info(f"正在嘗試連接到: {adb_address}")
        
        if adb_address and ":" in adb_address:
            host, port = adb_address.split(":")
            port = int(port)
            log_info(f"解析地址: 主機={host}, 端口={port}")
            
            # 進行連接調試
            if debug_adb_connection(host, port):
                adb_client = create_adb_client(host, port)
                if adb_client:
                    devices = adb_client.devices()
                    if devices:
                        device = devices[0]
                        is_connected = True
                        update_connection_status(True, f"成功連接到設備: {device.serial}")
                        dpg.configure_item("start_task_button", enabled=True)
                        dpg.configure_item("debug_button", enabled=True)
                        return
                    else:
                        log_warning("ADB 服務正常但未找到設備")
        
        # 如果用戶輸入的地址無效，進行自動掃描
        log_info("開始自動掃描可用的模擬器...")
        adb_client, device = scan_for_emulator()
        
        if adb_client and device:
            is_connected = True
            dpg.set_value("adb_address_input", f"{adb_client.host}:{adb_client.port}")
            update_connection_status(True, f"成功連接到設備: {device.serial}")
            dpg.configure_item("start_task_button", enabled=True)
            dpg.configure_item("debug_button", enabled=True)
        else:
            update_connection_status(False, "未找到模擬器，請確保模擬器已啟動")
            
    except Exception as e:
        log_error(f"連接過程出錯: {str(e)}")
        is_connected = False
        device = None

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
    automation = GameAutomation(device)
    
    try:
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
                    automation.wait_and_click("確認")
                    
                elif task_id == "collect_rewards":
                    # 處理領取獎勵
                    automation.wait_and_click("獎勵")
                    automation.wait_and_click("一鍵領取")
                    
                elif task_id == "daily_battles":
                    # 處理每日對戰
                    automation.wait_and_click("對戰")
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
    adb_address = dpg.get_value("adb_address_input")
    if ":" in adb_address:
        host, port = adb_address.split(":")
        port = int(port)
        debug_adb_connection(host, port)
    else:
        log_error("無效的 ADB 地址格式")

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

with dpg.window(label="寶可夢 TCG 每日助手", width=600, height=500, tag="main_window"):
    with dpg.group(horizontal=True):
        dpg.add_text("ADB 連接設定:")
        dpg.add_text("未連接", tag="connection_status", color=[255, 0, 0, 255])
        dpg.add_color_edit(default_value=[255, 0, 0, 255], tag="connection_status_color", 
                          no_inputs=True, no_picker=True, alpha_preview=0, enabled=False)
    
    with dpg.group(horizontal=True):
        dpg.add_input_text(label="ADB 地址", default_value="127.0.0.1:16384", tag="adb_address_input", width=200)
        dpg.add_button(label="自動掃描", callback=connect_adb_callback)
        dpg.add_button(label="手動連接", callback=connect_adb_callback)
        dpg.add_button(label="斷開", callback=disconnect_adb_callback)
        dpg.add_button(label="調試連接", callback=debug_button_callback, tag="debug_button", enabled=True)
        dpg.add_button(label="ADB工具", callback=adb_tools_callback, tag="adb_tools_button")
    
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

# 設置全局默認字體
dpg.bind_font(default_font)

# 設置視窗標題字體
dpg.bind_item_font("main_window", title_font)

dpg.create_viewport(title='寶可夢 TCG 每日助手', width=620, height=550)
dpg.setup_dearpygui()
dpg.show_viewport()
dpg.set_primary_window("main_window", True)
dpg.start_dearpygui()
dpg.destroy_context()
