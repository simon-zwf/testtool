# ==================================================
# !/usr/bin/env python
# @Author: simon.zhang
# @Date: 2025/9/4 16:19
# @FileName: bt_reconnect_linux.py
# @Email: wangfu_zhang@ggec.com.cn
# ==================================================
import subprocess
import time
import logging
import re
from datetime import datetime
import signal  # 兼容低版本Python的超时控制


class ClassicBluetoothReconnectTester:
    def __init__(self, target_device_name, hci_device="hci0", max_retry=3):
        """
        经典蓝牙自动回连测试器（全自动化，无需手动执行trust）
        :param target_device_name: 目标设备名称（如"Infinix AI Glasses"）
        :param hci_device: 蓝牙适配器（通过hciconfig查看，如hci0/hci1）
        :param max_retry: 关键操作重试次数（默认3次）
        """
        self.target_name = target_device_name  # 目标设备名称
        self.hci_device = hci_device  # 蓝牙适配器
        self.max_retry = max_retry  # 重试次数
        self.target_mac = None  # 目标设备MAC地址（扫描后获取）
        self.logger = self._setup_logger()  # 日志系统

    def _setup_logger(self):
        """配置日志：同时输出到控制台和文件，便于问题排查"""
        logger = logging.getLogger("ClassicBTReconnectTest")
        logger.setLevel(logging.INFO)
        formatter = logging.Formatter(
            "%(asctime)s - %(levelname)s - %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        )

        # 控制台输出
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)

        # 日志文件输出（按时间命名，避免覆盖）
        log_filename = f"bt_reconnect_test_{datetime.now().strftime('%Y%m%d%H%M%S')}.log"
        file_handler = logging.FileHandler(log_filename, encoding="utf-8")
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

        return logger

    def _handle_timeout(self, signum, frame):
        """超时信号处理函数（兼容低版本Python，替代Popen的timeout参数）"""
        raise subprocess.TimeoutExpired("命令执行超时", 0)

    def _run_command(self, cmd, timeout=30, is_bluetoothctl=False, wait_time=0):
        """
        执行系统命令（核心工具函数）
        :param cmd: 命令字符串
        :param timeout: 总超时时间（秒）
        :param is_bluetoothctl: 是否为bluetoothctl交互式命令
        :param wait_time: 命令执行后的等待时间（如扫描时等待10秒）
        :return: (stdout, stderr, returncode)
        """
        self.logger.debug(f"执行命令：{cmd}（超时{timeout}秒，等待{wait_time}秒）")
        try:
            # 设置超时信号（仅Unix/Linux有效）
            signal.signal(signal.SIGALRM, self._handle_timeout)
            signal.alarm(timeout)

            if is_bluetoothctl:
                # 处理bluetoothctl交互式命令（如扫描、配对）
                process = subprocess.Popen(
                    ["sudo", "bluetoothctl"],
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True  # 输出为字符串（兼容低版本Python，替代universal_newlines=True）
                )

                # 发送初始命令（如power on、scan on）
                process.stdin.write(cmd + "\n")
                process.stdin.flush()

                # 等待指定时间（如扫描持续10秒）
                if wait_time > 0:
                    self.logger.info(f"等待{wait_time}秒（执行中...）")
                    time.sleep(wait_time)
                    # 发送结束命令（如扫描后关闭scan）
                    if "scan on" in cmd:
                        process.stdin.write("scan off\n")
                        process.stdin.flush()
                        time.sleep(1)  # 等待关闭扫描的响应

                # 发送退出命令并获取输出
                process.stdin.write("quit\n")
                process.stdin.flush()
                stdout, stderr = process.communicate()
                returncode = process.returncode

            else:
                # 处理普通命令（如hciconfig、rfcomm）
                result = subprocess.run(
                    cmd,
                    shell=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True
                )
                stdout = result.stdout
                stderr = result.stderr
                returncode = result.returncode

            # 取消超时信号
            signal.alarm(0)
            self.logger.debug(f"命令结果：stdout={stdout.strip()}, stderr={stderr.strip()}, returncode={returncode}")
            return stdout, stderr, returncode

        except subprocess.TimeoutExpired:
            self.logger.error(f"命令超时（{timeout}秒）：{cmd}")
            return "", f"Command timeout after {timeout}s", -1
        except Exception as e:
            self.logger.error(f"命令执行异常：{str(e)}")
            return "", str(e), -1
        finally:
            # 确保超时信号被取消，避免影响后续操作
            signal.alarm(0)

    def _retry_operation(self, func, *args, **kwargs):
        """通用重试逻辑：关键操作失败后自动重试"""
        # 获取方法中指定的重试次数，如未指定则使用默认值
        max_retry = kwargs.pop('max_retry', self.max_retry)

        for attempt in range(1, max_retry + 1):
            self.logger.info(f"执行操作（尝试{attempt}/{max_retry}）：{func.__name__}")
            result = func(*args, **kwargs)
            if result:
                return True
            # 未到最大重试次数，等待后重试（等待时间指数增长：2^1, 2^2, ...）
            if attempt < max_retry:
                wait_time = 2 ** attempt
                self.logger.warning(f"操作失败，等待{wait_time}秒后重试")
                time.sleep(wait_time)
        self.logger.error(f"操作失败（已达最大重试次数{max_retry}）：{func.__name__}")
        return False

    def scan_target_device(self):
        """扫描目标设备，获取MAC地址（支持模糊匹配，确保扫描时长）"""
        self.logger.info(f"开始扫描目标设备：{self.target_name}")

        # 扫描命令：仅发送power on和scan on（避免bluetoothctl不支持sleep）
        scan_cmd = "power on\nscan on"
        # 执行扫描：总超时20秒，扫描持续10秒（足够覆盖大多数设备的广播间隔）
        stdout, stderr, returncode = self._run_command(
            scan_cmd,
            timeout=20,
            is_bluetoothctl=True,
            wait_time=10  # 核心：扫描持续10秒
        )

        # 检查扫描命令是否执行成功
        if returncode != 0:
            self.logger.error(f"扫描命令执行失败，错误信息：{stderr}")
            return False

        # 打印完整扫描结果（调试用，便于确认是否扫描到设备）
        self.logger.debug(f"完整扫描结果：\n{stdout}")

        # 正则匹配设备MAC地址和名称（经典蓝牙格式：XX:XX:XX:XX:XX:XX 设备名）
        mac_pattern = re.compile(r"((?:[0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2})\s+(.+)")
        matched_devices = mac_pattern.findall(stdout)

        # 模糊匹配目标设备（忽略大小写，避免名称差异）
        target_name_lower = self.target_name.lower()
        for mac, name in matched_devices:
            if target_name_lower in name.strip().lower():
                self.target_mac = mac
                self.logger.info(f"找到目标设备：名称={name.strip()}, MAC={self.target_mac}")
                return True

        # 未找到目标设备
        self.logger.error(f"未扫描到目标设备：{self.target_name}（请确认设备已开启可发现模式）")
        return False

    def connect_target_device(self):
        """自动配对→信任→连接（核心：配对成功后强制执行trust，无需手动操作）"""
        if not self.target_mac:
            self.logger.error("未获取目标设备MAC地址，无法执行连接")
            return False

        self.logger.info(f"开始连接目标设备：MAC={self.target_mac}")

        # --------------------------
        # 步骤1：自动配对（首次配对/已配对均兼容）
        # --------------------------
        pair_cmd = f"power on\npair {self.target_mac}"
        stdout_pair, stderr_pair, returncode_pair = self._run_command(
            pair_cmd,
            timeout=30,  # 配对超时30秒（足够处理PIN码验证）
            is_bluetoothctl=True,
            wait_time=5  # 配对后等待5秒，确保BlueZ状态同步
        )

        # 配对结果判断：覆盖“首次配对成功”和“已配对”场景（不区分大小写）
        pair_success_keywords = ["pairing successful", "already paired", "is already paired"]
        is_paired = any(keyword in stdout_pair.lower() for keyword in pair_success_keywords)
        if not is_paired:
            self.logger.error(f"配对失败！输出：stdout={stdout_pair.strip()}, stderr={stderr_pair.strip()}")
            return False
        self.logger.info("配对成功（或设备已提前配对）")

        # --------------------------
        # 步骤2：配对成功后自动执行trust（关键！无需手动操作）
        # --------------------------
        trust_cmd = f"trust {self.target_mac}"
        stdout_trust, stderr_trust, returncode_trust = self._run_command(
            trust_cmd,
            timeout=15,
            is_bluetoothctl=True,
            wait_time=2  # 信任后等待2秒，确保状态更新
        )

        # 信任结果判断：覆盖“首次信任成功”和“已信任”场景
        trust_success_keywords = ["trusted: yes", "trust succeeded", "already trusted"]
        is_trusted = any(keyword in stdout_trust.lower() for keyword in trust_success_keywords)
        if not is_trusted:
            self.logger.error(f"信任失败！输出：stdout={stdout_trust.strip()}, stderr={stderr_trust.strip()}")
            return False
        self.logger.info("信任成功（或设备已提前信任）")

        # --------------------------
        # 步骤3：自动建立连接
        # --------------------------
        connect_cmd = f"connect {self.target_mac}"
        stdout_connect, stderr_connect, returncode_connect = self._run_command(
            connect_cmd,
            timeout=20,
            is_bluetoothctl=True,
            wait_time=3  # 连接后等待3秒，确保链路稳定
        )

        # 连接结果判断：覆盖“连接成功”场景
        connect_success_keywords = ["connected: yes", "connection successful"]
        is_connected = any(keyword in stdout_connect.lower() for keyword in connect_success_keywords)
        if not is_connected:
            self.logger.error(f"连接失败！输出：stdout={stdout_connect.strip()}, stderr={stderr_connect.strip()}")
            return False
        self.logger.info("设备连接成功，已建立稳定链路")

        return True

    def toggle_bluetooth_adapter(self, action):
        """切换蓝牙适配器状态（up=开启，down=关闭），模拟断连/重连"""
        if action not in ["up", "down"]:
            self.logger.error(f"无效的适配器操作：{action}（仅支持up/down）")
            return False

        self.logger.info(f"切换蓝牙适配器状态：{self.hci_device} → {action}")
        # 执行hciconfig命令切换适配器状态
        cmd = f"sudo hciconfig {self.hci_device} {action}"
        stdout, stderr, returncode = self._run_command(cmd, timeout=10)

        if returncode == 0:
            # 状态切换后等待3秒，确保硬件响应完成
            time.sleep(3)
            self.logger.info(f"适配器状态切换成功：{action}")
            return True
        else:
            self.logger.error(f"适配器状态切换失败！错误信息：{stderr}")
            return False

    def check_reconnect_status(self):
        """检查设备是否自动回连成功（核心测试点）"""
        if not self.target_mac:
            self.logger.error("未获取目标设备MAC地址，无法检查回连状态")
            return False

        self.logger.info(f"检查目标设备回连状态：MAC={self.target_mac}")
        # 通过bluetoothctl info查看设备当前连接状态
        info_cmd = f"info {self.target_mac}"
        stdout, stderr, returncode = self._run_command(
            info_cmd,
            timeout=15,
            is_bluetoothctl=True
        )

        if returncode != 0:
            self.logger.error(f"获取设备状态失败！错误信息：{stderr}")
            return False

        # 判断是否回连成功（关键：检查"Connected: yes"）
        if "connected: yes" in stdout.lower():
            self.logger.info("✅ 设备自动回连成功！")
            return True
        else:
            self.logger.error(f"❌ 设备未自动回连！当前状态：\n{stdout.strip()}")
            return False

    def run_full_test(self):
        """执行完整测试流程：扫描→连接→断连→重连→验证回连"""
        self.logger.info("=" * 60)
        self.logger.info("          经典蓝牙自动回连测试开始          ")
        self.logger.info("=" * 60)

        test_result = False
        try:
            # 步骤1：扫描目标设备（重试3次）
            if not self._retry_operation(self.scan_target_device):
                raise Exception("扫描目标设备失败，终止测试")

            # 步骤2：连接目标设备（重试3次）
            if not self._retry_operation(self.connect_target_device):
                raise Exception("连接目标设备失败，终止测试")

            # 步骤3：模拟断连（关闭蓝牙适配器）
            if not self._retry_operation(self.toggle_bluetooth_adapter, "down"):
                raise Exception("关闭蓝牙适配器失败，无法模拟断连")

            # 步骤4：模拟重连（打开蓝牙适配器）
            if not self._retry_operation(self.toggle_bluetooth_adapter, "up"):
                raise Exception("打开蓝牙适配器失败，无法模拟重连")

            # 步骤5：等待设备回连（给设备5秒回连时间，可根据设备调整）
            self.logger.info("等待5秒，让设备自动发起回连...")
            time.sleep(5)

            # 步骤6：验证回连结果（重试2次，避免瞬间状态延迟）
            if self._retry_operation(self.check_reconnect_status, max_retry=2):
                test_result = True
            else:
                raise Exception("设备未自动回连，测试失败")

        except Exception as e:
            self.logger.error(f"测试流程异常中断：{str(e)}")
            test_result = False
        finally:
            # 测试结束，断开设备连接（避免占用资源）
            if self.target_mac:
                self._run_command(f"bluetoothctl disconnect {self.target_mac}")
            self.logger.info("=" * 60)
            self.logger.info(f"          经典蓝牙自动回连测试结束：{'成功' if test_result else '失败'}          ")
            self.logger.info("=" * 60)

        return test_result


# ------------------- 测试入口（需修改为你的设备信息） -------------------
if __name__ == "__main__":
    # --------------------------
    # 请根据你的实际情况修改以下参数！
    # --------------------------
    TARGET_DEVICE_NAME = "Infinix AI Glasses"  # 目标设备名称（需与蓝牙广播名称一致）
    BLUETOOTH_ADAPTER = "hci1"  # 蓝牙适配器（通过hciconfig查看，如hci0/hci1）
    MAX_RETRY_TIMES = 3  # 关键操作最大重试次数

    # 初始化测试器并执行测试
    tester = ClassicBluetoothReconnectTester(
        target_device_name=TARGET_DEVICE_NAME,
        hci_device=BLUETOOTH_ADAPTER,
        max_retry=MAX_RETRY_TIMES
    )
    # 执行完整测试（测试结果：True=成功，False=失败）
    final_result = tester.run_full_test()
    # 退出码：0=成功，1=失败（便于集成到自动化测试平台）
    exit(0 if final_result else 1)
