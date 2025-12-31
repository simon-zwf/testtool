import time
import logging
import os
import subprocess
import serial
import threading
from queue import Queue, Empty
from ble_control import BLEConnector

# 设备配置
SERIAL_PORT = "/dev/ttyUSB0"
SERIAL_BAUDRATE = 912600
SLEEP_COMMANDS = [
    "echo DeviceSuspendRequested > /tmp/sonospowercoordinator_USR1_cmd_OVERRIDE\r\n",
    "killall -SIGUSR1 sonospowercoordinator\r\n"
]

# 睡眠和唤醒标志
SLEEP_FLAG = 'a113x2 SOC turned off'
WAKEUP_FLAG = 'BT_WAKEUP fired'

# BLE配置
BLE_DEVICE_NAME = "S58 0848 LE"
HCI_DEVICE = "hci1"

# 测试配置
TOTAL_TESTS = 10  # 总共运行100次测试
SLEEP_TIMEOUT = 40  # 等待设备进入睡眠的超时时间（秒）
WAKEUP_TIMEOUT = 40  # 等待设备唤醒的超时时间（秒）

# 添加延迟时间配置
POST_WAKEUP_DELAY = 5  # 检测到唤醒标志后的延迟时间（秒）


class SerialMonitor:
    """串口监视器，用于读取和记录设备日志"""

    def __init__(self, port, baudrate):
        self.port = port
        self.baudrate = baudrate
        self.serial_conn = None
        self.running = False
        self.thread = None
        self.serial_logger = None
        self.sleep_event = threading.Event()
        self.wakeup_event = threading.Event()

    def start(self):
        """启动串口监视器"""
        try:
            # 创建专门的串口日志记录器
            self.serial_logger = logging.getLogger("SerialOutput")
            self.serial_logger.setLevel(logging.DEBUG)

            # 清除现有处理器
            for handler in self.serial_logger.handlers[:]:
                self.serial_logger.removeHandler(handler)

            # 文件处理器（记录所有串口输出）
            file_handler = logging.FileHandler("serial_output.log")
            file_handler.setLevel(logging.DEBUG)
            formatter = logging.Formatter('%(asctime)s - %(message)s')
            file_handler.setFormatter(formatter)
            self.serial_logger.addHandler(file_handler)

            # 禁止传播到根日志器
            self.serial_logger.propagate = False

            # 打开串口连接
            self.serial_conn = serial.Serial(
                port=self.port,
                baudrate=self.baudrate,
                timeout=1
            )

            # 重置事件
            self.sleep_event.clear()
            self.wakeup_event.clear()

            self.running = True
            self.thread = threading.Thread(target=self._read_serial)
            self.thread.daemon = True
            self.thread.start()
            logging.info(f"串口监视器已启动: {self.port}")
            return True
        except Exception as e:
            logging.error(f"启动串口监视器失败: {e}")
            return False

    def stop(self):
        """停止串口监视器"""
        self.running = False
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=2.0)
        if self.serial_conn and self.serial_conn.is_open:
            self.serial_conn.close()
        logging.info("串口监视器已停止")

    def _read_serial(self):
        """读取串口数据并记录到文件"""
        buffer = ""
        while self.running:
            try:
                # 非阻塞读取
                data = self.serial_conn.read(self.serial_conn.in_waiting or 1)
                if data:
                    decoded = data.decode('utf-8', errors='replace')
                    buffer += decoded

                    # 处理完整行
                    while '\n' in buffer:
                        line, buffer = buffer.split('\n', 1)
                        line = line.strip()
                        if line:
                            # 记录所有串口输出到专用日志文件
                            self.serial_logger.debug(line)

                            # 检查是否为睡眠或唤醒标志
                            if SLEEP_FLAG in line:
                                logging.info(f"检测到设备睡眠标志: {line}")
                                self.sleep_event.set()
                            elif WAKEUP_FLAG in line:
                                logging.info(f"检测到设备唤醒标志: {line}")
                                self.wakeup_event.set()
            except Exception as e:
                logging.error(f"读取串口数据时出错: {e}")
                time.sleep(1)

        # 处理剩余数据
        if buffer.strip():
            line = buffer.strip()
            self.serial_logger.debug(line)
            if SLEEP_FLAG in line:
                logging.info(f"检测到设备睡眠标志: {line}")
                self.sleep_event.set()
            elif WAKEUP_FLAG in line:
                logging.info(f"检测到设备唤醒标志: {line}")
                self.wakeup_event.set()

    def wait_for_sleep(self, timeout=SLEEP_TIMEOUT):
        """等待设备进入睡眠状态"""
        logging.info(f"等待设备进入睡眠状态，超时: {timeout}秒")
        return self.sleep_event.wait(timeout)

    def wait_for_wakeup(self, timeout=WAKEUP_TIMEOUT):
        """等待设备唤醒"""
        logging.info(f"等待设备唤醒，超时: {timeout}秒")
        return self.wakeup_event.wait(timeout)

    def reset_events(self):
        """重置事件状态"""
        self.sleep_event.clear()
        self.wakeup_event.clear()
        logging.debug("串口事件已重置")


def setup_logger():
    """配置全局日志系统"""
    # 创建根日志器
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)

    # 清除所有现有处理器
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)

    # 创建格式化器
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')

    # 文件处理器（记录所有INFO及以上级别）
    file_handler = logging.FileHandler("ble_wakeup_test.log")
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    # 控制台处理器（只显示INFO及以上级别）
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # 禁用BLEConnector的日志传播，避免重复日志
    ble_logger = logging.getLogger("ble_control")
    ble_logger.propagate = False

    return logging.getLogger("BLEWakeupTest")


def send_sleep_command(serial_monitor):
    """通过串口发送睡眠命令并等待设备进入睡眠"""
    try:
        # 重置事件状态
        serial_monitor.reset_events()

        # 发送睡眠命令
        for command in SLEEP_COMMANDS:
            serial_monitor.serial_conn.write(command.encode('utf-8'))
            logging.info(f"已发送睡眠命令: {command.strip()}")
            time.sleep(0.3)  # 命令间短暂延迟

        # 等待设备进入睡眠状态
        if serial_monitor.wait_for_sleep():
            logging.info("设备已成功进入睡眠状态")
            return True
        else:
            logging.error("等待设备进入睡眠状态超时")
            return False

    except Exception as e:
        logging.error(f"发送睡眠命令失败: {e}")
        return False


def cleanup_ble_processes():
    """清理可能残留的BLE相关进程"""
    try:
        subprocess.run(["sudo", "pkill", "-f", "hcitool"],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        subprocess.run(["sudo", "pkill", "-f", "bluetoothctl"],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        logging.info("清理残留BLE进程")
    except Exception as e:
        logging.warning(f"清理BLE进程时出错: {e}")


def run_single_test(test_number, serial_monitor):
    """执行单次测试"""
    logging.info(f"开始第 {test_number}/{TOTAL_TESTS} 次测试")

    # 1. 发送睡眠命令并等待设备进入睡眠
    if not send_sleep_command(serial_monitor):
        logging.error("无法使设备进入睡眠状态，跳过本次测试")
        return False

    # 2. 清理可能残留的BLE进程
    cleanup_ble_processes()

    # 3. 尝试通过BLE连接唤醒设备
    ble_connector = BLEConnector(
        ble_device_name=BLE_DEVICE_NAME,
        hci_device=HCI_DEVICE
    )

    # 4. 执行BLE连接
    start_time = time.time()
    ble_success = ble_connector.run()
    ble_elapsed_time = time.time() - start_time

    if ble_success:
        logging.info(f"BLE连接成功，耗时: {ble_elapsed_time:.2f} 秒")
    else:
        logging.info(f"BLE连接失败，耗时: {ble_elapsed_time:.2f} 秒")
        # 即使BLE连接失败，只要设备能唤醒也算成功

    # 5. 等待设备唤醒
    if serial_monitor.wait_for_wakeup():
        logging.info(f"检测到设备唤醒标志，等待 {POST_WAKEUP_DELAY} 秒延迟")
        time.sleep(POST_WAKEUP_DELAY)  # 添加延迟时间
        logging.info(f"第 {test_number} 次测试成功，设备已通过BLE唤醒")
        return True
    else:
        logging.error(f"第 {test_number} 次测试失败，设备未唤醒")
        return False


def main():
    logger = setup_logger()
    logger.info(f"=== 开始BLE唤醒测试 (共 {TOTAL_TESTS} 次) ===")

    # 启动串口监视器
    serial_monitor = SerialMonitor(SERIAL_PORT, SERIAL_BAUDRATE)
    if not serial_monitor.start():
        logger.error("无法启动串口监视器，退出测试")
        return False

    success_count = 0
    failure_count = 0

    try:
        for test_number in range(1, TOTAL_TESTS + 1):
            if run_single_test(test_number, serial_monitor):
                success_count += 1
            else:
                failure_count += 1

            # 打印当前统计信息
            logger.info(f"当前统计: 成功={success_count}, 失败={failure_count}")

            # 如果不是最后一次测试，等待一段时间再继续
            if test_number < TOTAL_TESTS:
                logger.info("等待10秒后继续下一轮测试...")
                time.sleep(10)
    finally:
        # 确保串口监视器被停止
        serial_monitor.stop()

    # 最终测试报告
    logger.info(f"\n{'=' * 50}")
    logger.info(f"测试完成! 总计: {TOTAL_TESTS} 次")
    logger.info(f"成功: {success_count} 次 ({success_count / TOTAL_TESTS * 100:.1f}%)")
    logger.info(f"失败: {failure_count} 次 ({failure_count / TOTAL_TESTS * 100:.1f}%)")
    logger.info(f"{'=' * 50}")

    return success_count > 0


if __name__ == "__main__":
    if main():
        print("测试完成（有成功案例）")
        exit(0)
    else:
        print("所有测试均失败")
        exit(1)