#!/usr/bin/env python
# @Author: simon.zhang
# @Date: 2025/11/18 17:03
# @FileName: device_connect.py
# @Email: wangfu_zhang@ggec.com.cn

import serial
import threading
import sys
"""
定义类 SerialTerminal
│
├─ 初始化：port, baudrate, stop_event, ser=None
├─ open()：创建 serial.Serial 对象
├─ start()：启动 _listen 线程（后台监听）
├─ _listen()：循环 read → decode → print（实时输出）
├─ write()：接收用户输入 → encode → ser.write()
└─ close()：stop_event.set() → 关串口 → 等线程退出
│
主程序：
   创建对象 → start() → 进入 input() 循环 → 用户可交互 → 最终 close()
"""

class SerialTerminal:
    def __init__(self, port, baudrate=921600):
        self.port = port
        self.baudrate = baudrate
        self.ser = None   # Serial.serial 对象，初始化
        self.stop_event = threading.Event()   # 用例通知子线程停止
        self.listen_thread = None    # 监控线程引用

    def open(self):
        self.ser = serial.Serial(
            port=self.port,
            baudrate=self.baudrate,
            timeout=0.1,
            write_timeout=0
        )
        print(f"[ok] Serial opened: {self.port}, @{self.baudrate}")

    def _listen(self):
        while not self.stop_event.is_set():
            try:
                data = self.ser.read(1024)
                if data:
                    decoded = data.decode(errors="ignore")
                    print(decoded, end="", flush=True)
            except Exception as e:
                print(f"\n[ERR] listen error: {e}")
                break

    def start(self):
        if not self.ser:
            self.open()
        self.listen_thread = threading.Thread(target=self._listen, daemon=True)
        self.listen_thread.start()

    def write(self, text):
        if not text.endswith("\n"):
            text += "\n"
        try:
            self.ser.write(text.encode())
            self.ser.flush()
        except Exception as e:
            print(f"[ERR] write failed: {e}")

    def close(self):
        self.stop_event.set()
        try:
            if self.ser:
                self.ser.cancel_read()
                self.ser.close()
        except Exception as e:
            print(f"[WARN] close serial exception: {e}")

        if self.listen_thread and self.listen_thread.is_alive():
            self.listen_thread.join(timeout=1)

if __name__ == "__main__":
    port = "COM7"
    baud = 921600
    terminal = SerialTerminal(port, baud)
    terminal.start()

    try:
        # 让主线程等待，避免立即退出
        print("Serial terminal started. Press Ctrl+C to exit.")
        while True:
            user_input = input()  # 可选：支持发送命令
            if user_input.lower() in ('exit', 'quit'):
                break
            terminal.write(user_input)
    except KeyboardInterrupt:
        print("\nExiting...")
    finally:
        terminal.close()