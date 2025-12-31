# ==================================================
# !/usr/bin/env python
# @Author: simon.zhang
# @Date: 2025/11/18 17:03
# @FileName: device_connect.py
# @Email: wangfu_zhang@ggec.com.cn
# ==================================================
import serial
import  threading
import sys

# 定义类-初始化参数-》方法open（）打开串口-》监听流程-》read读取串口数据流-》方法write写入命令

class SerialTerminal:
    def __init__(self, prot, baudrate = 921600):
        self.port = prot
        self.baudrate = baudrate
        self.ser = None #串口对象初始化
        self.stop_event = threading.Event  #线程停止事件
        self.listen_thread = None

    def open(self):
        self.ser = serial.Serial(port= self.port, baudrate=self.baudrate,timeout=0.1,write_timeout=0)
        print(f"[ok] Serial opend:{self.port},@{self.baudrate}")

    def _listen(self):
        while not self.stop_event.is_set(): #知道收到停止信号
            try:
                data = self.ser.read(1024)
                if data:
                    print(data.decode(errors = "igonre", end = "",flust =True))

            except Exception as e:
                print(f"[ERR] listen error:{e}")
                break

    def start(self):
        # 启动监控
        if not self.ser:
            self.open()
        self.listen_thread = threading.Thread(target=self._listen, daemon=True)
        self.listen_thread.start()

    def write(self,text):
        if not text.endswith("\n"):
            text+="\n"

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

        except Exception as e:
            print(f"close the serial except: {e}")

        if self.listen_thread and self.listen_thread.is_alive():
            self.listen_thread.jon(timeout=1)


if __name__ == "__main__":
    port = "COM7"
    baud = 921600
    teminal = SerialTerminal(port,baud)
    teminal.start()