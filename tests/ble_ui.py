import sys
import asyncio
import json
from datetime import datetime
from typing import List, Dict, Any

from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout,
                             QHBoxLayout, QPushButton, QListWidget, QTreeWidget,
                             QTreeWidgetItem, QTextEdit, QLabel, QSplitter,
                             QTabWidget, QGroupBox, QLineEdit, QMessageBox,
                             QProgressBar, QComboBox, QTableWidget, QTableWidgetItem,
                             QHeaderView, QFormLayout, QFrame, QDialog, QStackedWidget)
from PyQt5.QtCore import Qt, QTimer, pyqtSignal, QThread, pyqtSlot
from PyQt5.QtGui import QFont, QColor

import bleak
from bleak import BleakScanner, BleakClient
from bleak.backends.characteristic import BleakGATTCharacteristic
from bleak.backends.service import BleakGATTService


class BLEWorker(QThread):
    """异步BLE操作的工作线程"""
    device_discovered = pyqtSignal(dict)
    scan_completed = pyqtSignal()
    connected = pyqtSignal(bool)
    services_discovered = pyqtSignal(list)
    data_received = pyqtSignal(str, bytes)
    log_message = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self.scanner = None
        self.client = None
        self.devices = {}
        self.is_scanning = False

    def scan_devices(self):
        self.is_scanning = True
        self.start()

    def stop_scan(self):
        self.is_scanning = False

    def connect_device(self, address):
        self.address = address
        self.start()

    def disconnect_device(self):
        if self.client and self.client.is_connected:
            self.start()

    def read_characteristic(self, service_uuid, char_uuid):
        self.service_uuid = service_uuid
        self.char_uuid = char_uuid
        self.start()

    def write_characteristic(self, service_uuid, char_uuid, data):
        self.service_uuid = service_uuid
        self.char_uuid = char_uuid
        self.write_data = data
        self.start()

    def run(self):
        if hasattr(self, 'address'):
            asyncio.run(self._connect_device())
        elif hasattr(self, 'service_uuid'):
            if hasattr(self, 'write_data'):
                asyncio.run(self._write_characteristic())
            else:
                asyncio.run(self._read_characteristic())
        else:
            asyncio.run(self._scan_devices())

    async def _scan_devices(self):
        """扫描BLE设备"""
        try:
            self.log_message.emit("开始扫描BLE设备...")

            def detection_callback(device, advertisement_data):
                if device.address not in self.devices:
                    device_info = {
                        'name': device.name or "Unknown",
                        'address': device.address,
                        'rssi': device.rssi,
                        'advertisement_data': advertisement_data,
                        'details': str(advertisement_data)
                    }
                    self.devices[device.address] = device_info
                    self.device_discovered.emit(device_info)

            self.scanner = BleakScanner(detection_callback=detection_callback)
            await self.scanner.start()

            # 扫描10秒
            await asyncio.sleep(10)
            await self.scanner.stop()

            self.log_message.emit(f"扫描完成，发现 {len(self.devices)} 个设备")
            self.scan_completed.emit()

        except Exception as e:
            self.log_message.emit(f"扫描错误: {str(e)}")

    async def _connect_device(self):
        """连接设备并发现服务"""
        try:
            self.log_message.emit(f"正在连接设备: {self.address}")
            self.client = BleakClient(self.address)

            await self.client.connect()
            self.log_message.emit("连接成功！")

            # 获取服务
            services = await self.client.get_services()
            services_list = []

            for service in services:
                service_info = {
                    'uuid': service.uuid,
                    'handle': service.handle,
                    'description': str(service),
                    'characteristics': []
                }

                for char in service.characteristics:
                    char_info = {
                        'uuid': char.uuid,
                        'handle': char.handle,
                        'properties': char.properties,
                        'description': str(char)
                    }
                    service_info['characteristics'].append(char_info)

                services_list.append(service_info)

            self.services_discovered.emit(services_list)
            self.connected.emit(True)

        except Exception as e:
            self.log_message.emit(f"连接错误: {str(e)}")
            self.connected.emit(False)

    async def _read_characteristic(self):
        """读取特征值"""
        try:
            if self.client and self.client.is_connected:
                data = await self.client.read_gatt_char(self.char_uuid)
                self.data_received.emit('read', data)
                self.log_message.emit(f"读取成功: {data.hex()}")
        except Exception as e:
            self.log_message.emit(f"读取错误: {str(e)}")

    async def _write_characteristic(self):
        """写入特征值"""
        try:
            if self.client and self.client.is_connected:
                # 尝试将输入转换为字节
                if isinstance(self.write_data, str):
                    if self.write_data.startswith('0x'):
                        data = bytes.fromhex(self.write_data[2:])
                    else:
                        data = self.write_data.encode('utf-8')
                else:
                    data = self.write_data

                await self.client.write_gatt_char(self.char_uuid, data)
                self.log_message.emit(f"写入成功: {data.hex()}")
        except Exception as e:
            self.log_message.emit(f"写入错误: {str(e)}")


class CharacteristicWidget(QWidget):
    """特征操作界面"""
    readRequested = pyqtSignal(str, str)  # service_uuid, char_uuid
    writeRequested = pyqtSignal(str, str, bytes)  # service_uuid, char_uuid, data

    def __init__(self, char_info, service_uuid):
        super().__init__()
        self.char_info = char_info
        self.service_uuid = service_uuid
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout()

        # 特征信息
        info_group = QGroupBox("特征信息")
        info_layout = QFormLayout()

        info_layout.addRow("UUID:", QLabel(self.char_info['uuid']))
        info_layout.addRow("Handle:", QLabel(str(self.char_info['handle'])))
        info_layout.addRow("属性:", QLabel(', '.join(self.char_info['properties'])))

        info_group.setLayout(info_layout)
        layout.addWidget(info_group)

        # 读取操作
        if 'read' in self.char_info['properties']:
            read_group = QGroupBox("读取数据")
            read_layout = QVBoxLayout()

            self.read_result = QTextEdit()
            self.read_result.setReadOnly(True)
            self.read_result.setMaximumHeight(100)

            read_btn = QPushButton("读取")
            read_btn.clicked.connect(self.on_read)

            read_layout.addWidget(self.read_result)
            read_layout.addWidget(read_btn)
            read_group.setLayout(read_layout)
            layout.addWidget(read_group)

        # 写入操作
        if 'write' in self.char_info['properties'] or 'write-without-response' in self.char_info['properties']:
            write_group = QGroupBox("写入数据")
            write_layout = QVBoxLayout()

            format_label = QLabel("格式:")
            self.format_combo = QComboBox()
            self.format_combo.addItems(["文本", "十六进制", "十进制"])
            self.format_combo.currentTextChanged.connect(self.on_format_changed)

            self.write_input = QLineEdit()
            self.write_input.setPlaceholderText("输入要写入的数据")

            format_layout = QHBoxLayout()
            format_layout.addWidget(format_label)
            format_layout.addWidget(self.format_combo)

            write_btn = QPushButton("写入")
            write_btn.clicked.connect(self.on_write)

            write_layout.addLayout(format_layout)
            write_layout.addWidget(QLabel("数据:"))
            write_layout.addWidget(self.write_input)
            write_layout.addWidget(write_btn)
            write_group.setLayout(write_layout)
            layout.addWidget(write_group)

        layout.addStretch()
        self.setLayout(layout)

    def on_read(self):
        """发送读取请求"""
        self.readRequested.emit(self.service_uuid, self.char_info['uuid'])

    def on_write(self):
        """发送写入请求"""
        text = self.write_input.text().strip()
        if not text:
            return

        data = None
        format_type = self.format_combo.currentText()

        try:
            if format_type == "十六进制":
                # 移除0x前缀和空格
                hex_str = text.replace('0x', '').replace(' ', '')
                data = bytes.fromhex(hex_str)
            elif format_type == "十进制":
                # 以逗号分隔的数字
                numbers = [int(x.strip()) for x in text.split(',')]
                data = bytes(numbers)
            else:  # 文本
                data = text.encode('utf-8')

            if data:
                self.writeRequested.emit(self.service_uuid, self.char_info['uuid'], data)
        except Exception as e:
            print(f"数据格式错误: {e}")

    def on_format_changed(self, text):
        """更改数据格式时更新提示文本"""
        if text == "十六进制":
            self.write_input.setPlaceholderText("例如: 0x01 0x02 0x03 或 010203")
        elif text == "十进制":
            self.write_input.setPlaceholderText("例如: 1, 2, 3, 255")
        else:
            self.write_input.setPlaceholderText("输入要写入的文本")


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.ble_worker = BLEWorker()
        self.current_device = None
        self.current_characteristic = None
        self.current_service_uuid = None
        self.init_ui()
        self.connect_signals()

    def init_ui(self):
        self.setWindowTitle("BLE Connect Tool - 类似nRF Connect")
        self.setGeometry(100, 100, 1200, 800)

        # 中央部件
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        # 主布局
        main_layout = QHBoxLayout()
        central_widget.setLayout(main_layout)

        # 左侧面板 - 设备列表
        left_panel = QWidget()
        left_layout = QVBoxLayout()

        # 扫描控制
        scan_group = QGroupBox("设备扫描")
        scan_layout = QVBoxLayout()

        self.scan_btn = QPushButton("开始扫描")
        self.scan_btn.clicked.connect(self.start_scan)

        self.stop_btn = QPushButton("停止扫描")
        self.stop_btn.clicked.connect(self.stop_scan)
        self.stop_btn.setEnabled(False)

        self.device_list = QListWidget()
        self.device_list.itemClicked.connect(self.on_device_selected)

        scan_layout.addWidget(self.scan_btn)
        scan_layout.addWidget(self.stop_btn)
        scan_layout.addWidget(QLabel("设备列表:"))
        scan_layout.addWidget(self.device_list)
        scan_group.setLayout(scan_layout)
        left_layout.addWidget(scan_group)

        # 设备信息
        info_group = QGroupBox("设备信息")
        info_layout = QFormLayout()

        self.device_name_label = QLabel("-")
        self.device_address_label = QLabel("-")
        self.device_rssi_label = QLabel("-")

        info_layout.addRow("名称:", self.device_name_label)
        info_layout.addRow("地址:", self.device_address_label)
        info_layout.addRow("信号强度:", self.device_rssi_label)

        info_group.setLayout(info_layout)
        left_layout.addWidget(info_group)

        # 设备操作按钮
        btn_group = QWidget()
        btn_layout = QHBoxLayout()

        self.advertise_btn = QPushButton("查看广播信息")
        self.advertise_btn.clicked.connect(self.show_advertisement)
        self.advertise_btn.setEnabled(False)

        self.connect_btn = QPushButton("连接设备")
        self.connect_btn.clicked.connect(self.connect_device)
        self.connect_btn.setEnabled(False)

        self.disconnect_btn = QPushButton("断开连接")
        self.disconnect_btn.clicked.connect(self.disconnect_device)
        self.disconnect_btn.setEnabled(False)

        btn_layout.addWidget(self.advertise_btn)
        btn_layout.addWidget(self.connect_btn)
        btn_layout.addWidget(self.disconnect_btn)
        btn_group.setLayout(btn_layout)
        left_layout.addWidget(btn_group)

        left_panel.setLayout(left_layout)
        left_panel.setMinimumWidth(350)

        # 右侧面板 - 服务和特征
        right_panel = QWidget()
        right_layout = QVBoxLayout()

        # 标签页
        self.tab_widget = QTabWidget()

        # 服务标签页
        self.services_tree = QTreeWidget()
        self.services_tree.setHeaderLabels(["UUID", "句柄", "描述"])
        self.services_tree.itemClicked.connect(self.on_service_selected)

        # 特征标签页
        self.char_tab = QWidget()
        char_layout = QVBoxLayout()
        self.char_stack = QStackedWidget()
        char_layout.addWidget(self.char_stack)
        self.char_tab.setLayout(char_layout)

        # 日志标签页
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)

        self.tab_widget.addTab(self.services_tree, "服务")
        self.tab_widget.addTab(self.char_tab, "特征操作")
        self.tab_widget.addTab(self.log_text, "日志")

        right_layout.addWidget(self.tab_widget)
        right_panel.setLayout(right_layout)

        # 分割器
        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(left_panel)
        splitter.addWidget(right_panel)
        splitter.setSizes([400, 800])

        main_layout.addWidget(splitter)

        # 状态栏
        self.statusBar().showMessage("就绪")

    def connect_signals(self):
        """连接信号和槽"""
        self.ble_worker.device_discovered.connect(self.add_device)
        self.ble_worker.scan_completed.connect(self.on_scan_completed)
        self.ble_worker.connected.connect(self.on_device_connected)
        self.ble_worker.services_discovered.connect(self.show_services)
        self.ble_worker.data_received.connect(self.on_data_received)
        self.ble_worker.log_message.connect(self.log_message)

    def start_scan(self):
        """开始扫描"""
        self.device_list.clear()
        self.scan_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.log_message("开始扫描BLE设备...")
        self.ble_worker.scan_devices()

    def stop_scan(self):
        """停止扫描"""
        self.ble_worker.stop_scan()
        self.scan_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.log_message("扫描已停止")

    def on_scan_completed(self):
        """扫描完成后的处理"""
        self.scan_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.log_message(f"扫描完成，共发现 {self.device_list.count()} 个设备")

    def add_device(self, device_info):
        """添加设备到列表"""
        name = device_info['name']
        address = device_info['address']
        rssi = device_info['rssi']

        # 按RSSI强度排序插入
        item_text = f"{name} ({address}) RSSI: {rssi}"

        # 找到合适的位置插入
        for i in range(self.device_list.count()):
            item = self.device_list.item(i)
            text = item.text()
            # 提取现有的RSSI值
            if "RSSI:" in text:
                try:
                    existing_rssi = int(text.split("RSSI:")[1].strip())
                    if rssi > existing_rssi:  # RSSI越大信号越好
                        self.device_list.insertItem(i, item_text)
                        return
                except:
                    pass

        # 如果没有找到合适位置，添加到末尾
        self.device_list.addItem(item_text)

    def on_device_selected(self, item):
        """设备被选中"""
        text = item.text()
        # 从文本中提取地址
        address_start = text.find('(') + 1
        address_end = text.find(')')
        address = text[address_start:address_end]

        # 查找设备信息
        for dev_info in self.ble_worker.devices.values():
            if dev_info['address'] == address:
                self.current_device = dev_info
                self.update_device_info(dev_info)
                break

        self.advertise_btn.setEnabled(True)
        self.connect_btn.setEnabled(True)
        self.disconnect_btn.setEnabled(False)

    def update_device_info(self, device_info):
        """更新设备信息显示"""
        self.device_name_label.setText(device_info['name'])
        self.device_address_label.setText(device_info['address'])
        self.device_rssi_label.setText(str(device_info['rssi']))

    def show_advertisement(self):
        """显示广播信息"""
        if self.current_device:
            dialog = QDialog(self)
            dialog.setWindowTitle("广播信息")
            dialog.setGeometry(200, 200, 600, 400)

            layout = QVBoxLayout()
            text_edit = QTextEdit()
            text_edit.setPlainText(self.current_device['details'])
            text_edit.setReadOnly(True)

            layout.addWidget(text_edit)
            dialog.setLayout(layout)
            dialog.exec_()

    def connect_device(self):
        """连接设备"""
        if self.current_device:
            self.log_message(f"正在连接设备: {self.current_device['address']}")
            self.connect_btn.setEnabled(False)
            self.disconnect_btn.setEnabled(True)
            self.ble_worker.connect_device(self.current_device['address'])

    def disconnect_device(self):
        """断开设备连接"""
        self.ble_worker.disconnect_device()
        self.connect_btn.setEnabled(True)
        self.disconnect_btn.setEnabled(False)
        self.log_message("已断开连接")

    def on_device_connected(self, success):
        """设备连接结果"""
        if success:
            self.log_message("设备连接成功")
            self.statusBar().showMessage("设备已连接")
        else:
            self.log_message("设备连接失败")
            self.connect_btn.setEnabled(True)
            self.disconnect_btn.setEnabled(False)

    def show_services(self, services):
        """显示服务"""
        self.services_tree.clear()

        for service in services:
            service_item = QTreeWidgetItem([
                service['uuid'],
                str(service['handle']),
                service['description']
            ])
            service_item.setData(0, Qt.UserRole, service)

            for char in service['characteristics']:
                char_item = QTreeWidgetItem([
                    char['uuid'],
                    str(char['handle']),
                    ', '.join(char['properties'])
                ])
                char_item.setData(0, Qt.UserRole, {'char': char, 'service_uuid': service['uuid']})
                service_item.addChild(char_item)

            self.services_tree.addTopLevelItem(service_item)

    def on_service_selected(self, item, column):
        """服务或特征被选中"""
        data = item.data(0, Qt.UserRole)
        if data and 'char' in data:  # 这是特征
            char_info = data['char']
            service_uuid = data['service_uuid']
            self.current_characteristic = char_info
            self.current_service_uuid = service_uuid
            self.show_characteristic_operations(char_info, service_uuid)

    def show_characteristic_operations(self, char_info, service_uuid):
        """显示特征操作界面"""
        # 移除旧的widgets
        while self.char_stack.count():
            widget = self.char_stack.widget(0)
            self.char_stack.removeWidget(widget)

        # 添加新的操作界面
        char_widget = CharacteristicWidget(char_info, service_uuid)
        char_widget.readRequested.connect(self.on_read_characteristic)
        char_widget.writeRequested.connect(self.on_write_characteristic)
        self.char_stack.addWidget(char_widget)
        self.tab_widget.setCurrentIndex(1)  # 切换到特征标签页

    def on_read_characteristic(self, service_uuid, char_uuid):
        """处理读取特征请求"""
        self.ble_worker.read_characteristic(service_uuid, char_uuid)

    def on_write_characteristic(self, service_uuid, char_uuid, data):
        """处理写入特征请求"""
        self.ble_worker.write_characteristic(service_uuid, char_uuid, data)

    def on_data_received(self, operation, data):
        """处理接收到的数据"""
        if operation == 'read':
            hex_str = data.hex()
            ascii_str = ''.join(chr(b) if 32 <= b < 127 else '.' for b in data)

            result = f"HEX: {hex_str}\n"
            result += f"ASCII: {ascii_str}\n"
            result += f"长度: {len(data)} 字节"

            # 在当前特征操作界面显示结果
            current_widget = self.char_stack.currentWidget()
            if current_widget and hasattr(current_widget, 'read_result'):
                current_widget.read_result.setPlainText(result)

            self.log_message(f"读取到数据: {hex_str}")

    def log_message(self, message):
        """记录日志"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log_text.append(f"[{timestamp}] {message}")
        self.statusBar().showMessage(message)


def main():
    app = QApplication(sys.argv)

    # 设置应用样式
    app.setStyle('Fusion')

    window = MainWindow()
    window.show()

    sys.exit(app.exec_())


if __name__ == "__main__":
    main()