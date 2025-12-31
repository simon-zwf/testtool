# ==================================================
# !/usr/bin/env python
# @Author: simon.zhang
# @Date: 2025/9/22 10:50
# @FileName: ble_scan.py
# @Email: wangfu_zhang@ggec.com.cn
# ==================================================
import asyncio
import tkinter as tk
from tkinter import ttk, scrolledtext
from bleak import BleakScanner, BleakClient
from bleak.backends.characteristic import BleakGATTCharacteristic


# ------------------- 核心功能：扫描设备 + 解析服务/特征 -------------------
class BluetoothScanner:
    def __init__(self, log_callback):
        self.log = log_callback  # 日志回调函数（用于UI显示）
        self.devices = []  # 扫描到的设备列表
        self.connected_client = None  # 当前连接的客户端

    # 扫描周围蓝牙设备
    async def scan_devices(self, timeout=10):
        self.log("开始扫描蓝牙设备...（请确保设备处于配对模式）")
        self.devices = await BleakScanner.discover(timeout=timeout)
        if not self.devices:
            self.log("未扫描到任何蓝牙设备")
            return []
        # 格式化设备信息
        device_list = []
        for i, dev in enumerate(self.devices):
            name = dev.name or "未知设备"
            addr = dev.address
            rssi = f"（信号强度：{dev.rssi} dBm）"
            device_list.append(f"{i + 1}. {name} | {addr} {rssi}")
            self.log(f"发现设备：{name}（{addr}）")
        return device_list

    # 连接设备并解析服务和特征UUID
    async def connect_and_discover(self, device_index):
        if device_index < 0 or device_index >= len(self.devices):
            self.log("无效的设备索引")
            return None

        target_device = self.devices[device_index]
        self.log(f"正在连接设备：{target_device.name or '未知设备'}（{target_device.address}）")

        try:
            # 断开之前的连接
            if self.connected_client and self.connected_client.is_connected:
                await self.connected_client.disconnect()

            # 连接设备
            async with BleakClient(target_device.address) as client:
                self.connected_client = client
                if not await client.is_connected():
                    self.log("连接失败")
                    return None

                self.log(f"连接成功！正在解析服务和特征...")
                services = await client.get_services()  # 获取所有服务
                result = []

                # 遍历所有服务和特征
                for service in services:
                    service_uuid = service.uuid
                    service_info = f"\n【服务 UUID】: {service_uuid}"

                    # 遍历该服务下的所有特征
                    characteristics = []
                    for char in service.characteristics:
                        # 特征属性（如可读、可写、通知等）
                        props = []
                        if char.properties.read:
                            props.append("读")
                        if char.properties.write:
                            props.append("写")
                        if char.properties.notify:
                            props.append("通知")
                        props_str = "|".join(props) if props else "无属性"

                        char_info = f"  - 特征 UUID: {char.uuid}（属性：{props_str}）"
                        characteristics.append(char_info)

                    service_info += "\n" + "\n".join(characteristics)
                    result.append(service_info)
                    self.log(f"解析服务完成：{service_uuid}")

                return "\n".join(result)

        except Exception as e:
            self.log(f"连接或解析失败：{str(e)}")
            return None


# ------------------- GUI 界面：集成扫描和解析功能 -------------------
class ScannerGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("蓝牙设备扫描与UUID解析工具")
        self.root.geometry("800x600")

        # 初始化扫描器
        self.scanner = BluetoothScanner(self.update_log)

        # 创建UI组件
        self.create_widgets()

    def create_widgets(self):
        # 顶部按钮区
        btn_frame = ttk.Frame(self.root)
        btn_frame.pack(pady=10, fill=tk.X, padx=20)

        ttk.Button(btn_frame, text="扫描设备", command=self.start_scan).pack(side=tk.LEFT, padx=5)
        ttk.Label(btn_frame, text="选择设备索引：").pack(side=tk.LEFT, padx=5)
        self.device_index = ttk.Entry(btn_frame, width=5)
        self.device_index.pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="连接并解析UUID", command=self.start_discover).pack(side=tk.LEFT, padx=5)

        # 设备列表区
        ttk.Label(self.root, text="扫描到的设备：").pack(anchor=tk.W, padx=20)
        self.device_listbox = scrolledtext.ScrolledText(self.root, height=8)
        self.device_listbox.pack(fill=tk.X, padx=20, pady=5)

        # UUID解析结果区
        ttk.Label(self.root, text="服务与特征UUID解析结果：").pack(anchor=tk.W, padx=20)
        self.result_text = scrolledtext.ScrolledText(self.root, height=15)
        self.result_text.pack(fill=tk.BOTH, expand=True, padx=20, pady=5)

        # 日志区
        ttk.Label(self.root, text="日志：").pack(anchor=tk.W, padx=20)
        self.log_text = scrolledtext.ScrolledText(self.root, height=5)
        self.log_text.pack(fill=tk.X, padx=20, pady=5)

    # 更新日志到UI
    def update_log(self, message):
        self.log_text.insert(tk.END, message + "\n")
        self.log_text.see(tk.END)

    # 开始扫描设备（异步任务包装）
    def start_scan(self):
        self.device_listbox.delete(1.0, tk.END)
        self.update_log("启动扫描...")

        # 异步执行扫描
        async def scan_task():
            devices = await self.scanner.scan_devices()
            if devices:
                self.device_listbox.insert(tk.END, "\n".join(devices))

        asyncio.run(scan_task())

    # 连接并解析UUID（异步任务包装）
    def start_discover(self):
        self.result_text.delete(1.0, tk.END)
        try:
            index = int(self.device_index.get()) - 1  # 转换为0-based索引
        except ValueError:
            self.update_log("请输入有效的设备索引（如1、2）")
            return

        # 异步执行连接和解析
        async def discover_task():
            result = await self.scanner.connect_and_discover(index)
            if result:
                self.result_text.insert(tk.END, result)

        asyncio.run(discover_task())


# 启动程序
if __name__ == "__main__":
    root = tk.Tk()
    app = ScannerGUI(root)
    root.mainloop()
