import asyncio
import sys
import json
from bleak import BleakScanner, BleakClient
from bleak.backends.scanner import AdvertisementData
from bleak.backends.device import BLEDevice
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
                             QTextEdit, QLineEdit, QPushButton, QLabel, QComboBox,
                             QGroupBox, QSplitter, QFileDialog, QMessageBox, QStatusBar)
from PyQt5.QtCore import Qt, QThread, pyqtSignal
from PyQt5.QtGui import QFont, QTextCursor

# 默认测试用例
DEFAULT_TEST_CASES = [
    {
        "name": "广播数据包长度",
        "manufacturer_id": 0x042,  # Google Company ID
        "manufacturer_data": "09020430141000006F041FDADA7F017E58AE93CD8F16030335FD",
        "expect": "18FF4209020430141000006F030BE4E47F01F44EFD00001110030335FD"
    },
    # 其他测试用例...
]


class BLEBroadcastWorker(QThread):
    """BLE广播工作线程"""
    log_signal = pyqtSignal(str)
    status_signal = pyqtSignal(str)
    result_signal = pyqtSignal(str, bool, str)

    def __init__(self, test_cases, device_name_filter="", scan_timeout=10):
        super().__init__()
        self.test_cases = test_cases
        self.device_name_filter = device_name_filter
        self.scan_timeout = scan_timeout
        self.is_running = False

    def run(self):
        self.is_running = True
        asyncio.run(self.run_broadcast_tests())

    async def run_broadcast_tests(self):
        """运行所有广播测试"""
        for test_case in self.test_cases:
            if not self.is_running:
                break

            self.log_signal.emit(f"开始测试: {test_case['name']}")
            self.status_signal.emit(f"正在测试: {test_case['name']}")

            # 扫描设备并检查广播数据
            received_data = await self.scan_for_broadcasts(test_case)

            # 检查结果
            expected_data = test_case['expect'].replace(' ', '').upper()
            if received_data:
                self.log_signal.emit(f"接收到数据: {received_data}")
                self.log_signal.emit(f"期望数据: {expected_data}")

                # 比较接收到的数据和期望数据
                if received_data == expected_data:
                    self.log_signal.emit("✓ 测试通过")
                    self.result_signal.emit(test_case['name'], True, received_data)
                else:
                    self.log_signal.emit("✗ 测试失败 - 数据不匹配")
                    self.result_signal.emit(test_case['name'], False, received_data)
            else:
                self.log_signal.emit("✗ 测试失败 - 未接收到数据")
                self.result_signal.emit(test_case['name'], False, "")

            await asyncio.sleep(2)  # 测试间隔

        self.status_signal.emit("测试完成")
        self.log_signal.emit("=== 所有测试完成 ===")

    async def scan_for_broadcasts(self, test_case):
        """扫描特定格式的广播数据"""
        received_data = None
        manufacturer_id = test_case.get('manufacturer_id', 0x042)  # 默认Google Company ID

        def callback(device: BLEDevice, advertisement_data: AdvertisementData):
            nonlocal received_data
            # 检查设备名称过滤
            if self.device_name_filter and not (device.name and self.device_name_filter in device.name):
                return

            # 检查制造商数据
            if advertisement_data.manufacturer_data:
                for mid, data in advertisement_data.manufacturer_data.items():
                    if mid == manufacturer_id:
                        hex_data = data.hex().upper()
                        self.log_signal.emit(f"发现匹配的制造商数据: {hex_data}")
                        received_data = hex_data
                        break

        scanner = BleakScanner(callback)
        await scanner.start()

        # 等待指定时间或直到收到数据
        for _ in range(self.scan_timeout * 10):  # 每0.1秒检查一次
            if received_data or not self.is_running:
                break
            await asyncio.sleep(0.1)

        await scanner.stop()
        return received_data

    def stop(self):
        self.is_running = False


class BLEBroadcastWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.test_cases = DEFAULT_TEST_CASES.copy()
        self.worker = None
        self.init_ui()

    def init_ui(self):
        self.setWindowTitle('BLE广播测试工具')
        self.setGeometry(100, 100, 1000, 700)

        # 中央部件
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        # 主布局
        main_layout = QVBoxLayout(central_widget)

        # 控制面板
        control_group = QGroupBox("控制面板")
        control_layout = QHBoxLayout(control_group)

        self.device_filter_edit = QLineEdit()
        self.device_filter_edit.setPlaceholderText("设备名称过滤器 (可选)")
        control_layout.addWidget(QLabel("设备过滤器:"))
        control_layout.addWidget(self.device_filter_edit)

        self.timeout_edit = QLineEdit("10")
        self.timeout_edit.setMaximumWidth(50)
        control_layout.addWidget(QLabel("超时(秒):"))
        control_layout.addWidget(self.timeout_edit)

        self.start_btn = QPushButton("开始扫描")
        self.start_btn.clicked.connect(self.start_scan)
        control_layout.addWidget(self.start_btn)

        self.stop_btn = QPushButton("停止扫描")
        self.stop_btn.clicked.connect(self.stop_scan)
        self.stop_btn.setEnabled(False)
        control_layout.addWidget(self.stop_btn)

        main_layout.addWidget(control_group)

        # 测试用例区域
        test_case_group = QGroupBox("测试用例配置")
        test_case_layout = QVBoxLayout(test_case_group)

        self.test_case_combo = QComboBox()
        self.update_test_case_combo()
        self.test_case_combo.currentIndexChanged.connect(self.load_test_case)
        test_case_layout.addWidget(self.test_case_combo)

        # 制造商ID和数据编辑
        id_data_layout = QHBoxLayout()

        id_group = QGroupBox("制造商ID")
        id_layout = QVBoxLayout(id_group)
        self.manufacturer_id_edit = QLineEdit("66")  # 0x42 = 66
        id_layout.addWidget(self.manufacturer_id_edit)

        data_group = QGroupBox("制造商数据")
        data_layout = QVBoxLayout(data_group)
        self.manufacturer_data_edit = QTextEdit()
        data_layout.addWidget(self.manufacturer_data_edit)

        id_data_layout.addWidget(id_group)
        id_data_layout.addWidget(data_group)
        test_case_layout.addLayout(id_data_layout)

        # 期望结果编辑
        expect_group = QGroupBox("期望结果")
        expect_layout = QVBoxLayout(expect_group)
        self.expect_edit = QTextEdit()
        expect_layout.addWidget(self.expect_edit)

        test_case_layout.addWidget(expect_group)

        # 测试用例操作按钮
        test_case_btn_layout = QHBoxLayout()
        self.add_btn = QPushButton("添加测试用例")
        self.add_btn.clicked.connect(self.add_test_case)
        test_case_btn_layout.addWidget(self.add_btn)

        self.update_btn = QPushButton("更新测试用例")
        self.update_btn.clicked.connect(self.update_test_case)
        test_case_btn_layout.addWidget(self.update_btn)

        self.delete_btn = QPushButton("删除测试用例")
        self.delete_btn.clicked.connect(self.delete_test_case)
        test_case_btn_layout.addWidget(self.delete_btn)

        test_case_layout.addLayout(test_case_btn_layout)

        main_layout.addWidget(test_case_group)

        # 日志区域
        log_group = QGroupBox("扫描日志")
        log_layout = QVBoxLayout(log_group)
        self.log_edit = QTextEdit()
        self.log_edit.setReadOnly(True)
        log_layout.addWidget(self.log_edit)

        main_layout.addWidget(log_group)

        # 状态栏
        self.statusBar = QStatusBar()
        self.setStatusBar(self.statusBar)
        self.statusBar.showMessage("就绪")

    def update_test_case_combo(self):
        self.test_case_combo.clear()
        for i, test_case in enumerate(self.test_cases):
            self.test_case_combo.addItem(f"{i + 1}. {test_case['name']}")

    def load_test_case(self):
        index = self.test_case_combo.currentIndex()
        if 0 <= index < len(self.test_cases):
            test_case = self.test_cases[index]
            self.manufacturer_id_edit.setText(str(test_case.get('manufacturer_id', 66)))
            self.manufacturer_data_edit.setPlainText(test_case.get('manufacturer_data', ''))
            self.expect_edit.setPlainText(test_case.get('expect', ''))

    def add_test_case(self):
        name = f"测试用例 {len(self.test_cases) + 1}"
        try:
            manufacturer_id = int(self.manufacturer_id_edit.text())
        except ValueError:
            manufacturer_id = 66  # 默认Google Company ID

        manufacturer_data = self.manufacturer_data_edit.toPlainText().strip()
        expect_data = self.expect_edit.toPlainText().strip()

        if not manufacturer_data or not expect_data:
            QMessageBox.warning(self, "警告", "制造商数据和期望数据不能为空")
            return

        self.test_cases.append({
            "name": name,
            "manufacturer_id": manufacturer_id,
            "manufacturer_data": manufacturer_data,
            "expect": expect_data
        })

        self.update_test_case_combo()
        self.test_case_combo.setCurrentIndex(len(self.test_cases) - 1)
        self.log(f"已添加测试用例: {name}")

    def update_test_case(self):
        index = self.test_case_combo.currentIndex()
        if index < 0 or index >= len(self.test_cases):
            return

        try:
            manufacturer_id = int(self.manufacturer_id_edit.text())
        except ValueError:
            manufacturer_id = 66  # 默认Google Company ID

        manufacturer_data = self.manufacturer_data_edit.toPlainText().strip()
        expect_data = self.expect_edit.toPlainText().strip()

        if not manufacturer_data or not expect_data:
            QMessageBox.warning(self, "警告", "制造商数据和期望数据不能为空")
            return

        self.test_cases[index]['manufacturer_id'] = manufacturer_id
        self.test_cases[index]['manufacturer_data'] = manufacturer_data
        self.test_cases[index]['expect'] = expect_data

        self.update_test_case_combo()
        self.test_case_combo.setCurrentIndex(index)
        self.log(f"已更新测试用例: {self.test_cases[index]['name']}")

    def delete_test_case(self):
        index = self.test_case_combo.currentIndex()
        if index < 0 or index >= len(self.test_cases):
            return

        name = self.test_cases[index]['name']
        self.test_cases.pop(index)

        self.update_test_case_combo()
        if self.test_cases:
            self.test_case_combo.setCurrentIndex(0 if index == 0 else index - 1)
        self.log(f"已删除测试用例: {name}")

    def start_scan(self):
        if self.worker and self.worker.isRunning():
            return

        device_filter = self.device_filter_edit.text().strip()
        try:
            timeout = int(self.timeout_edit.text())
        except ValueError:
            timeout = 10

        self.worker = BLEBroadcastWorker(self.test_cases, device_filter, timeout)
        self.worker.log_signal.connect(self.log)
        self.worker.status_signal.connect(self.statusBar.showMessage)
        self.worker.result_signal.connect(self.handle_test_result)
        self.worker.finished.connect(self.scan_finished)

        self.start_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)

        self.log("=== 开始扫描 ===")
        self.worker.start()

    def stop_scan(self):
        if self.worker and self.worker.isRunning():
            self.worker.stop()
            self.worker.wait()

    def scan_finished(self):
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.statusBar.showMessage("扫描完成")

    def handle_test_result(self, test_name, passed, received_data):
        color = "green" if passed else "red"
        self.log(f"<font color='{color}'>测试结果: {test_name} - {'通过' if passed else '失败'}</font>")

    def log(self, message):
        self.log_edit.append(message)
        self.log_edit.moveCursor(QTextCursor.End)

    def closeEvent(self, event):
        if self.worker and self.worker.isRunning():
            self.worker.stop()
            self.worker.wait()
        event.accept()


if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = BLEBroadcastWindow()
    window.show()
    sys.exit(app.exec_())


