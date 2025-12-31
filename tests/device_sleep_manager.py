import serial
import time
import threading
import logging
from queue import Queue, Empty


class DeviceSleepManager:
    """管理设备睡眠状态的串口控制器"""

    def __init__(self, config, logger=None):
        self.config = config
        self.logger = logger or self._setup_logger()
        self.serial_port = None
        self.reader_thread = None
        self.running = False
        self.log_queue = Queue()
        self.sleep_detected = threading.Event()
        self.wakeup_detected = threading.Event()

    def _setup_logger(self):
        """创建专用的日志记录器"""
        logger = logging.getLogger("DeviceSleepManager")

        # 禁用日志传播，避免重复输出
        logger.propagate = False

        # 如果已有处理器，直接返回
        if logger.hasHandlers():
            return logger

        logger.setLevel(logging.INFO)  # 设置为INFO级别
        formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')

        # 添加控制台处理器
        ch = logging.StreamHandler()
        ch.setLevel(logging.INFO)  # 只显示INFO及以上级别
        ch.setFormatter(formatter)
        logger.addHandler(ch)

        return logger

    def open_serial_port(self):
        """打开串口连接"""
        try:
            self.serial_port = serial.Serial(
                port=self.config["SERIAL_PORT"],
                baudrate=self.config["SERIAL_BAUDRATE"],
                timeout=self.config["SERIAL_TIMEOUT"]
            )
            self.logger.info(f"串口已打开: {self.config['SERIAL_PORT']}")
            return True
        except (serial.SerialException, KeyError) as e:
            self.logger.error(f"串口打开失败: {e}")
            return False

    def close_serial_port(self):
        """关闭串口连接"""
        if self.serial_port and self.serial_port.is_open:
            self.serial_port.close()
            self.logger.info("串口已关闭")

    def start_reading(self):
        """启动串口读取线程"""
        if not self.serial_port or not self.serial_port.is_open:
            self.logger.error("串口未打开，无法启动读取")
            return False

        self.running = True
        self.reader_thread = threading.Thread(target=self._read_serial_data)
        self.reader_thread.daemon = True
        self.reader_thread.start()
        self.logger.info("串口数据读取线程已启动")
        return True

    def stop_reading(self):
        """停止串口读取线程"""
        if self.running:
            self.running = False
            if self.reader_thread and self.reader_thread.is_alive():
                self.reader_thread.join(timeout=2.0)
                self.logger.info("串口数据读取线程已停止")

    def _read_serial_data(self):
        """高效的串口数据读取和处理"""
        buffer = ""
        while self.running:
            try:
                # 非阻塞读取
                data = self.serial_port.read(self.serial_port.in_waiting or 1)
                if data:
                    decoded = data.decode('utf-8', errors='replace')
                    buffer += decoded

                    # 处理完整行
                    while '\n' in buffer:
                        line, buffer = buffer.split('\n', 1)
                        line = line.strip()
                        if line:
                            self._process_line(line)
            except serial.SerialException as e:
                self.logger.error(f"串口读取错误: {e}")
                time.sleep(1)
            except Exception as e:
                self.logger.error(f"串口处理异常: {e}")
                time.sleep(0.5)

        # 处理剩余数据
        if buffer.strip():
            self._process_line(buffer.strip())

    def _process_line(self, line):
        """处理单行日志并检测关键事件"""
        # 不再记录原始串口数据，只检测关键事件
        self.log_queue.put(line)

        # 检测睡眠标志
        if not self.sleep_detected.is_set() and self.config["SLEEP_FLAG"] in line:
            self.sleep_detected.set()
            self.logger.info(f"检测到设备睡眠标志: {self.config['SLEEP_FLAG']}")

        # 检测唤醒标志
        if not self.wakeup_detected.is_set() and self.config["WAKEUP_FLAG"] in line:
            self.wakeup_detected.set()
            self.logger.info(f"检测到设备唤醒标志: {self.config['WAKEUP_FLAG']}")

    def send_sleep_commands(self):
        """发送设备睡眠命令"""
        try:
            for command in self.config["SLEEP_COMMANDS"]:
                self.serial_port.write(command.encode('utf-8'))
                self.logger.info(f"已发送睡眠命令: {command.strip()}")
                time.sleep(0.3)  # 命令间短暂延迟
            return True
        except serial.SerialException as e:
            self.logger.error(f"发送命令失败: {e}")
            return False

    def ensure_device_sleep(self, max_retries=3, timeout=30):
        """
        确保设备进入睡眠状态
        :return: True如果设备进入睡眠，否则False
        """
        if self.sleep_detected.is_set():
            self.logger.info("设备已处于睡眠状态")
            return True

        for attempt in range(1, max_retries + 1):
            self.logger.info(f"尝试让设备进入睡眠 (尝试 {attempt}/{max_retries})")

            if not self.send_sleep_commands():
                continue

            # 等待睡眠标志
            if self.sleep_detected.wait(timeout):
                self.logger.info("设备成功进入睡眠状态")
                return True

            self.logger.warning(f"设备未进入睡眠状态 (尝试 {attempt})")

        self.logger.error(f"错误: 无法使设备进入睡眠状态，经过 {max_retries} 次尝试")
        return False

    def wait_for_wakeup(self, timeout=60):
        """
        等待设备唤醒
        :return: True如果检测到唤醒标志，否则False
        """
        if self.wakeup_detected.is_set():
            self.logger.info("设备已处于唤醒状态")
            return True

        self.logger.info(f"等待设备唤醒，超时: {timeout}秒")
        return self.wakeup_detected.wait(timeout)

    def reset_state(self):
        """重置状态标志"""
        self.sleep_detected.clear()
        self.wakeup_detected.clear()
        # 清空队列
        while not self.log_queue.empty():
            try:
                self.log_queue.get_nowait()
            except Empty:
                break
        self.logger.debug("设备状态已重置")