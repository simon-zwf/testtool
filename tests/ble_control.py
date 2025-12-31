#!/usr/bin/env python
# 声明脚本解释器：使用系统默认的python解释器执行本脚本

# @Author: simon.zhang
# @Date: 2025/8/05 14:21
# @FileName: ble_control.py
# @Email: wangfu_zhang@ggec.com.cn
# Function: Connect to BLE via the hcitool command
# 以上为文件元信息：作者、日期、文件名、邮箱和功能描述


# 导入依赖模块并注释其核心功能
import os           # 提供操作系统交互功能（如文件操作、进程管理）
import re           # 提供正则表达式功能（用于解析设备MAC地址等字符串）
import time         # 提供时间相关功能（如延时、计时器）
import subprocess   # 提供调用系统命令的功能（用于执行hcitool等蓝牙工具）
import sys          # 提供系统相关功能（如程序退出）
import logging      # 提供日志记录功能（用于调试和运行状态跟踪）
import select       # 提供I/O多路复用功能（用于实时监控命令输出）
from datetime import datetime  # 提供日期时间处理功能（用于日志文件名）
from collections import Counter  # 提供计数统计功能（用于扫描结果中MAC地址的频次统计）


class BLEConnector:
    """封装BLE连接功能，用于可靠性测试中的设备唤醒"""

    def __init__(self, ble_device_name, max_retries=3, logger=None):
        """
        初始化BLE连接器
        :param ble_device_name: 目标BLE设备名称（必须与实际设备广播名称匹配）
        :param max_retries: 最大重试次数（默认3次，用于扫描、连接等操作失败后的重试）
        :param logger: 可选的外部日志器（如未提供则创建内部日志器）
        """
        # 初始化核心参数
        self.ble_device_name = ble_device_name  # 目标BLE设备名称，用于扫描时的匹配
        self.max_retries = max_retries          # 所有可重试操作的默认最大重试次数

        # 配置日志系统：优先使用外部提供的日志器，如无则创建内部日志器
        self.logger = logger or self._setup_logger()

        # 自动检测系统中的USB蓝牙适配器（排除虚拟设备，确保硬件有效性）
        self.hci_device = self._detect_usb_bluetooth_dongle()
        self.logger.info(f"使用蓝牙适配器: {self.hci_device}")

        # 连接过程状态跟踪变量
        self.connection_success = False  # 记录最终连接结果
        self.lock_file = None            # 存储锁文件路径，用于进程间互斥
        self.ble_mac = None              # 存储扫描到的目标设备MAC地址
        self.scan_process = None         # 存储扫描进程对象，用于后续终止操作

        # 初始化时确保蓝牙适配器可用，如不可用则退出程序
        if not self.ensure_adapter_ready():
            self.logger.error("蓝牙适配器不可用，退出程序")
            sys.exit(1)  # 非0状态码表示程序异常退出

    def _setup_logger(self):
        """配置日志器：同时输出到控制台（INFO级别）和文件（DEBUG级别）"""
        # 创建名为"BLEConnector"的日志器实例
        logger = logging.getLogger("BLEConnector")
        logger.setLevel(logging.INFO)  # 设置日志器的基础级别为INFO

        # 清除已有的日志处理器（防止多个处理器导致日志重复输出）
        if logger.hasHandlers():
            # 遍历并移除所有现有处理器
            for handler in logger.handlers[:]:
                logger.removeHandler(handler)
                handler.close()  # 关闭处理器释放资源

        # 定义日志格式：包含时间戳、日志级别、日志器名称和消息
        formatter = logging.Formatter(
            '%(asctime)s - %(levelname)s - %(name)s - %(message)s',  # 格式字符串
            datefmt='%Y-%m-%d %H:%M:%S'  # 日期时间格式
        )

        # 1. 创建控制台日志处理器（将INFO及以上级别日志输出到终端）
        ch = logging.StreamHandler()
        ch.setLevel(logging.INFO)       # 控制台只输出INFO及以上级别
        ch.setFormatter(formatter)      # 应用定义的日志格式
        logger.addHandler(ch)           # 将处理器添加到日志器

        # 2. 创建文件日志处理器（将DEBUG及以上级别日志输出到文件，用于后续调试）
        # 日志文件名包含日期，实现按日分割日志
        log_file = f"ble_connector_{datetime.now().strftime('%Y%m%d')}.log"
        fh = logging.FileHandler(log_file)
        fh.setLevel(logging.DEBUG)      # 文件记录DEBUG及以上所有级别
        fh.setFormatter(formatter)      # 应用定义的日志格式
        logger.addHandler(fh)           # 将处理器添加到日志器

        return logger  # 返回配置好的日志器

    def _detect_usb_bluetooth_dongle(self):
        """检测系统中的USB蓝牙适配器（排除虚拟设备），
         返回第一个可用的USB蓝牙设备名称（如hci0）"""
        try:
            # 执行hciconfig命令获取所有蓝牙设备信息（hciconfig是Linux蓝牙工具）
            result = subprocess.run(
                ['hciconfig'],            # 要执行的命令
                capture_output=True,      # 捕获标准输出和错误
                text=True,                # 输出为字符串格式而非字节
                timeout=10                # 命令执行超时时间（10秒）
            )
            # 检查命令执行结果：非0返回码表示失败（如hciconfig未安装）
            if result.returncode != 0:
                self.logger.error("获取蓝牙设备信息失败")
                sys.exit(1)  # 无法获取设备信息，程序无法继续，退出

            # 解析hciconfig输出以提取USB蓝牙设备
            output = result.stdout  # 获取命令标准输出内容
            lines = output.split('\n')  # 按行分割输出内容

            usb_devices = []        # 存储所有USB蓝牙设备
            current_device = None   # 临时存储当前处理的设备名称

            for line in lines:
                # 1. 检查行是否代表蓝牙设备：格式为"hciX:"（X为数字，如hci0:）
                if ':' in line and line.strip().startswith('hci'):
                    parts = line.split(':')  # 将"hci0:"分割为["hci0", ""]
                    current_device = parts[0].strip()  # 提取设备名称（如hci0）

                    # 检查设备是否为USB类型（排除虚拟设备，USB设备有"Bus: USB"标识）
                    if 'Bus: USB' in line:
                        usb_devices.append(current_device)  # 添加到USB设备列表
                        self.logger.info(f"发现USB蓝牙设备: {current_device}")

                # 2. 检查当前设备是否处于活动状态（UP RUNNING）
                elif current_device and 'UP RUNNING' in line:
                    # 如果活动设备在USB设备列表中，优先选择此设备（即插即用且已激活）
                    if current_device in usb_devices:
                        self.logger.info(f"选择处于UP状态的USB设备: {current_device}")
                        return current_device  # 直接返回活动的USB设备，无需继续搜索

            # 如果未找到活动的USB设备但存在USB设备，选择第一个USB设备
            if usb_devices:
                selected = usb_devices[0]
                self.logger.info(f"选择USB蓝牙设备: {selected}")
                return selected

            # 未找到USB蓝牙设备（可能未插入或驱动未识别）
            self.logger.error("未找到USB蓝牙适配器")
            sys.exit(1)  # 无可用适配器，程序无法继续，退出

        except Exception as e:
            self.logger.error(f"检测USB蓝牙适配器时出错: {e}")
            sys.exit(1)  # 发生异常，程序无法继续，退出

    def _run_command(self, cmd, timeout=30):
        """
        通用系统命令执行函数：支持超时控制、实时日志记录，返回命令执行结果
        :param cmd: 要执行的系统命令（字符串格式，如"hciconfig hci0 up"）
        :param timeout: 命令执行超时时间（秒，默认30）
        :return: stdout（命令标准输出）, stderr（命令错误输出）, return_code（返回码）, timed_out（是否超时）
        """
        self.logger.debug(
            f"执行命令: {cmd}")  # 记录要执行的命令（DEBUG级别，仅在文件日志中可见）

        try:
            # 创建子进程执行命令：shell=True允许执行复杂命令（如管道、重定向）
            process = subprocess.Popen(
                cmd,
                shell=True,
                stdout=subprocess.PIPE,  # 将标准输出重定向到管道
                stderr=subprocess.PIPE,  # 将错误输出重定向到管道
                text=True                # 输出为字符串格式
            )

            # 初始化输出存储字典：分别存储stdout和stderr内容
            outputs = {"stdout": [], "stderr": []}
            fds = [process.stdout, process.stderr]  # 要监控的文件描述符（标准输出和错误）

            start_time = time.time()  # 记录命令开始执行的时间
            timed_out = False         # 标记是否超时

            # 循环监控文件描述符，直到所有流关闭或超时
            while fds and not timed_out:
                # 计算剩余超时时间（防止累积误差）
                time_remaining = timeout - (time.time() - start_time)
                if time_remaining <= 0:
                    timed_out = True  # 超时标记设为True
                    break             # 跳出循环

                # 使用select监控文件描述符：等待可读事件，超时时间为剩余时间
                ready, _, _ = select.select(fds, [], [], time_remaining)
                if not ready:
                    continue  # 无就绪描述符，继续等待

                # 处理可读的文件描述符（stdout或stderr）
                for fd in ready:
                    try:
                        line = fd.readline().strip()  # 读取一行并去除首尾空白
                        if line:  # 如果读取到内容（非空行）
                            if fd == process.stdout:  # 区分标准输出和错误输出
                                self.logger.debug(f"STDOUT: {line}")
                                outputs["stdout"].append(line)
                            else:
                                self.logger.debug(f"STDERR: {line}")
                                outputs["stderr"].append(line)
                        else:  # 空行表示流已关闭（EOF），从监控列表中移除
                            fds.remove(fd)
                    except Exception as e:
                        self.logger.warning(f"读取输出时出错: {e}")
                        if fd in fds:
                            fds.remove(fd)

            # 处理命令超时：终止子进程并清理资源
            if timed_out:
                process.terminate()  # 首先尝试优雅终止
                try:
                    process.wait(timeout=2)  # 等待2秒让进程终止
                except subprocess.TimeoutExpired:
                    process.kill()  # 优雅终止失败，强制杀死进程
                self.logger.error(f"命令超时: {cmd}")
                return "", "命令执行超时", -1, True

            # 命令正常完成，获取进程返回码
            return_code = process.wait()

            # 将输出列表合并为字符串（用换行符连接各行）
            stdout = "\n".join(outputs["stdout"])
            stderr = "\n".join(outputs["stderr"])

            self.logger.debug(f"命令返回码: {return_code}")
            return stdout, stderr, return_code, False  # 返回正常执行结果

        except Exception as e:
            # 捕获命令执行过程中的异常（如创建子进程失败）
            self.logger.error(f"命令执行异常: {e}")
            return f"异常: {e}", "执行错误", -1, False

    def _retry_operation(self, operation_func, operation_name, *args, **kwargs):
        """
        通用重试操作函数：为任何操作提供"失败重试+指数退避等待"逻辑
        指数退避：重试间隔随尝试次数呈2^n增长（最大30秒），避免频繁重试消耗资源
        :param operation_func: 要执行的目标函数（如扫描、连接、重置适配器）
        :param operation_name: 操作名称（用于日志，如"扫描设备"）
        :param *args: 传递给目标函数的位置参数（如扫描不需要额外参数）
        :param *kwargs: 传递给目标函数的关键字参数，支持max_retries覆盖默认重试次数
        :return: 成功时返回目标函数的返回值；所有重试失败则返回None
        """
        # 优先使用kwargs中的max_retries，如未提供则使用类初始化时的默认值
        max_retries = kwargs.pop('max_retries', self.max_retries)

        # 循环执行重试：从1到max_retries次尝试
        for attempt in range(1, max_retries + 1):
            try:
                self.logger.info(f"执行{operation_name}（尝试 {attempt}/{max_retries}）")

                # 调用目标函数，传递位置参数和关键字参数
                result = operation_func(*args, **kwargs)

                # 判断操作是否成功：结果非False或None即视为成功（不同操作返回值不同）
                if result is not False and result is not None:
                    return result  # 成功，返回结果

                # 操作失败且未达到最大重试次数，计算等待时间后重试
                if attempt < max_retries:
                    # 指数退避：2^attempt秒，最大30秒
                    wait_time = min(2** attempt, 30)
                    self.logger.info(f"等待{wait_time}秒后重试")
                    time.sleep(wait_time)  # 等待指定时间

            except Exception as e:
                # 捕获目标函数执行过程中的异常（如扫描时的文件读取错误）
                self.logger.error(f"执行{operation_name}时出错: {e}")
                # 未达到最大重试次数则等待后重试
                if attempt < max_retries:
                    wait_time = min(2 **attempt, 30)
                    self.logger.info(f"等待{wait_time}秒后重试")
                    time.sleep(wait_time)

        # 所有重试尝试均失败
        self.logger.error(f"错误: 超过最大重试次数 {max_retries}")
        return None

    def reset_adapter(self):
        """重置蓝牙适配器：down->reset->up，将适配器恢复到初始状态（解决部分连接异常）"""

        # 内部实现函数：封装重置逻辑（传递给_retry_operation进行重试）
        def _reset_impl():
            try:
                # 1. 关闭蓝牙适配器（down命令）
                self._run_command(f"sudo hciconfig {self.hci_device} down")
                time.sleep(1)  # 等待1秒确保命令执行完成

                # 2. 执行适配器重置（reset命令）
                self._run_command(f"sudo hciconfig {self.hci_device} reset")
                time.sleep(2)  # 等待2秒确保重置完成

                # 3. 重新启用适配器（up命令）
                self._run_command(f"sudo hciconfig {self.hci_device} up")
                time.sleep(2)  # 等待2秒确保启用完成

                # 4. 检查重置后适配器是否处于UP RUNNING状态（验证重置成功）
                stdout, _, _, _ = self._run_command(f"hciconfig {self.hci_device}")

                if "UP RUNNING" in stdout:
                    self.logger.info(f"适配器 {self.hci_device} 重置成功")
                    return True  # 重置成功
                else:
                    self.logger.warning(f"适配器状态异常: {stdout}")
                    return False  # 重置失败

            except Exception as e:
                self.logger.error(f"重置适配器时出错: {e}")
                return False  # 发生异常，重置失败

        # 调用通用重试函数执行重置操作（重试逻辑由_retry_operation处理）
        return self._retry_operation(_reset_impl, "重置适配器")

    def ensure_adapter_ready(self):
        """确保蓝牙适配器处于可用状态（UP RUNNING）：如未激活则尝试激活"""

        # 内部实现函数：封装适配器状态检查和激活逻辑
        def _ensure_impl():
            try:
                # 1. 首先检查当前适配器状态
                stdout, _, _, _ = self._run_command(f"hciconfig {self.hci_device}")

                # 如已处于UP RUNNING状态则返回成功
                if "UP RUNNING" in stdout:
                    self.logger.info(f"适配器 {self.hci_device} 已启用")
                    return True

                # 2. 适配器未激活，尝试用up命令激活
                self.logger.warning(f"适配器 {self.hci_device} 未启用，尝试激活...")
                self._run_command(f"sudo hciconfig {self.hci_device} up")
                time.sleep(2)  # 等待2秒确保激活命令执行完成

                # 3. 激活后再次检查状态
                stdout, _, _, _ = self._run_command(f"hciconfig {self.hci_device}")
                if "UP RUNNING" in stdout:
                    self.logger.info(f"适配器 {self.hci_device} 激活成功")
                    return True  # 激活成功
                else:
                    self.logger.warning(f"激活后适配器状态: {stdout}")
                    return False  # 激活失败

            except Exception as e:
                self.logger.error(f"检查适配器状态时出错: {e}")
                return False  # 发生异常，状态检查失败

        # 调用通用重试函数确保适配器就绪（激活失败时重试）
        return self._retry_operation(_ensure_impl, "确保适配器就绪")

    def acquire_lock(self):
        """获取蓝牙适配器操作锁：防止多个进程操作同一适配器导致冲突"""

        # 内部实现函数：封装锁获取逻辑
        def _acquire_impl():
            try:
                # 锁文件路径：位于/tmp目录，通过适配器名称区分（避免多个适配器锁冲突）
                lock_file = f"/tmp/.ble_lock_{self.hci_device}"
                max_wait = 30  # 最大等待时间（秒）

                start_time = time.time()
                # 循环检查锁文件是否存在（存在表示其他进程正在使用适配器）
                while os.path.exists(lock_file):
                    # 检查等待时间是否超过max_wait，超时则强制继续（防止死锁）
                    if time.time() - start_time > max_wait:
                        self.logger.warning(f"等待锁超时（{max_wait}秒），强制继续")
                        break

                    # 检查锁文件是否过期（创建超过30秒，视为进程异常退出遗留）
                    if time.time() - os.path.getmtime(lock_file) > 30:
                        self.logger.warning("检测到过期锁，删除")
                        try:
                            os.remove(lock_file)  # 删除过期锁文件
                            break
                        except Exception as e:
                            self.logger.error(f"删除锁文件失败: {e}")

                    time.sleep(1)  # 每秒检查一次锁文件状态，减少CPU占用

                # 创建新锁文件：写入当前进程PID（便于排查持有锁的进程）
                with open(lock_file, "w") as f:
                    f.write(str(os.getpid()))
                self.logger.info(f"创建锁文件: {lock_file}")
                return lock_file  # 返回锁文件路径供后续释放

            except Exception as e:
                self.logger.error(f"获取锁失败: {e}")
                return None  # 获取锁失败

        # 调用通用重试函数获取锁（获取失败时重试）
        return self._retry_operation(_acquire_impl, "获取锁")

    def release_lock(self):
        """释放蓝牙适配器操作锁：操作完成后清理锁文件，允许其他进程使用"""
        # 检查锁文件是否存在（避免重复释放）
        if self.lock_file and os.path.exists(self.lock_file):
            try:
                os.remove(self.lock_file)  # 删除锁文件
                self.logger.info(f"释放锁文件: {self.lock_file}")
            except Exception as e:
                self.logger.error(f"释放锁文件失败: {e}")
        else:
            self.logger.info("无锁文件可释放")

    def scan_device(self):
        """扫描BLE设备：实时监控扫描结果，发现目标设备名称后立即停止，返回设备MAC地址"""
        scan_file = None  # 在函数级别定义变量，供finally块使用

        def _scan_impl():
            nonlocal scan_file  # 使用nonlocal关键字修改外部变量
            # 预编译MAC地址正则表达式：匹配BLE设备MAC格式（xx:xx:xx:xx:xx:xx，不区分大小写）
            mac_pattern = re.compile(r"((?:[0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}) (.*)")

            try:
                # 1. 首先停止所有可能残留的hcitool进程（避免干扰当前扫描）
                self._run_command("sudo pkill -f hcitool", timeout=5)
                time.sleep(2)  # 等待2秒确保进程终止

                # 2. 重置适配器（清理之前的扫描状态，提高扫描成功率）
                self.reset_adapter()
                time.sleep(2)  # 等待2秒确保重置完成

                # 3. 创建临时扫描文件：存储lescan命令的输出（进程间数据共享）
                scan_file = f"ble_scan_{os.getpid()}_{int(time.time())}.txt"

                # 4. 启动BLE扫描进程：lescan命令（--duplicates保留重复扫描结果用于信号强度判断）
                scan_cmd = f"sudo hcitool -i {self.hci_device} lescan --duplicates > {scan_file} 2>&1"
                self.scan_process = subprocess.Popen(
                    scan_cmd,
                    shell=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True
                )
                # 5. 配置扫描超时和结果监控
                scan_timeout = 30  # 扫描超时时间（秒）
                start_time = time.time()
                found_device = None  # 存储找到的设备MAC地址

                # 实时监控扫描文件以查找目标设备
                while time.time() - start_time < scan_timeout:
                    # 检查扫描进程是否意外退出（在超时前终止）
                    if self.scan_process.poll() is not None:
                        break
                    # 检查临时扫描文件是否存在（进程启动可能有延迟）
                    if os.path.exists(scan_file):
                        try:
                            # 读取扫描文件当前内容
                            with open(scan_file, 'r', errors='ignore') as f:
                                content = f.read()

                            # 逐行解析扫描结果以匹配目标设备
                            lines = content.splitlines()
                            for line in lines:
                                # 用正则表达式提取MAC地址和设备名称
                                match = mac_pattern.match(line)
                                if match and self.ble_device_name in match.group(2):
                                    # 找到目标设备：提取MAC地址
                                    found_device = match.group(1)
                                    self.logger.info(
                                        f"实时发现设备: {self.ble_device_name} MAC: {found_device}")
                                    # 找到设备后立即停止扫描进程
                                    self.scan_process.terminate()
                                    try:
                                        self.scan_process.wait(timeout=2)
                                    except subprocess.TimeoutExpired:
                                        self.scan_process.kill()
                                    return found_device  # 返回找到的MAC地址

                        except Exception as e:
                            self.logger.warning(f"读取扫描文件时出错: {e}")

                    time.sleep(0.5)  # 每0.5秒检查一次扫描结果，平衡实时性和CPU占用

                # 6. 扫描超时：停止扫描进程（防止进程残留）
                if self.scan_process.poll() is None:
                    self.scan_process.terminate()
                    try:
                        self.scan_process.wait(timeout=2)
                    except subprocess.TimeoutExpired:
                        self.scan_process.kill()

                # 7. 超时后再次检查扫描文件（设备可能在最后一刻被扫描到）
                if os.path.exists(scan_file):
                    try:
                        with open(scan_file, 'r') as f:
                            content = f.read()

                        # 收集所有匹配目标设备名称的扫描结果（MAC + 设备名称）
                        matches = []
                        for line in content.splitlines():
                            match = mac_pattern.match(line)
                            if match and self.ble_device_name in match.group(2):
                                matches.append((match.group(1), match.group(2)))
                                self.logger.debug(f"发现匹配设备: {match.group(1)} - {match.group(2)}")

                        # 如果有多个匹配结果，选择出现次数最多的MAC（信号最强，被扫描到次数最多）
                        if matches:
                            mac_counter = Counter(mac for mac, _ in matches)  # 统计MAC出现次数
                            ble_mac = mac_counter.most_common(1)[0][0]  # 获取出现次数最多的MAC
                            self.logger.info(f"扫描完成，发现设备: {self.ble_device_name} MAC: {ble_mac}")
                            return ble_mac  # 返回最可能的MAC地址

                    except Exception as e:
                        self.logger.error(f"读取扫描文件失败: {e}")

                # 8. 未找到目标设备
                self.logger.warning(f"未找到设备: {self.ble_device_name}")
                return False  # 返回False表示扫描失败

            except Exception as e:
                self.logger.error(f"扫描设备时出错: {e}")
                return False  # 发生异常，返回失败
            finally:
                # 无论扫描成功/失败/异常，确保清理残留进程和临时文件
                self._run_command("sudo pkill -f hcitool", timeout=5)

        try:
            return self._retry_operation(_scan_impl, "扫描设备")
        finally:
            # 确保删除临时扫描文件
            if scan_file and os.path.exists(scan_file):
                try:
                    os.remove(scan_file)
                    self.logger.debug(f"删除临时扫描文件: {scan_file}")
                except Exception as e:
                    self.logger.warning(f"删除扫描文件 {scan_file} 失败: {e}")

    def connect_device(self, ble_mac):
        """执行BLE设备连接：使用hcitool lecc命令连接到目标设备（需要MAC地址）"""

        # 内部实现函数：封装连接逻辑
        def _connect_impl():
            # 首先检查MAC地址是否有效（避免因参数无效导致连接失败）
            if not ble_mac:
                self.logger.error("无效的MAC地址，跳过连接")
                return False

            try:
                # 1. 停止所有蓝牙相关进程（清理之前的连接残留）
                self.logger.info("停止所有蓝牙相关进程")
                self._run_command("sudo pkill -f hcitool", timeout=5)
                time.sleep(2)  # 等待2秒确保进程终止

                # 2. 重置适配器（恢复初始状态，解决连接残留问题）
                self.logger.info("重置蓝牙适配器状态")
                self._run_command(f"sudo hciconfig {self.hci_device} reset", timeout=10)
                time.sleep(2)  # 等待2秒确保重置完成

                # 3. 执行BLE连接命令：lecc（LE连接命令）
                self.logger.info(f"使用hcitool连接设备 {ble_mac}")
                # --random参数表示使用随机地址类型连接
                cmd = f"sudo timeout 30 hcitool -i {self.hci_device} lecc --random {ble_mac}"
                # 执行命令，超时设为35秒（比内部命令超时多5秒，避免误判超时）
                stdout, stderr, return_code, timed_out = self._run_command(cmd, timeout=35)

                # 4. 记录详细的连接命令结果（用于调试）
                self.logger.debug(f"连接命令结果: 超时={timed_out}, 返回码={return_code}")
                self.logger.debug(f"标准输出: {stdout}")
                self.logger.debug(f"错误输出: {stderr}")

                # 5. 判断连接是否成功：成功连接会返回"Connection handle"
                if "Connection handle" in stdout:
                    self.logger.info("连接成功!")
                    return True  # 连接成功
                # 处理常见的连接失败情况
                elif "Could not create connection" in stderr:
                    self.logger.error(f"连接失败: {stderr.strip()}")
                elif "Connection timed out" in stderr:
                    self.logger.error(f"连接超时: {stderr.strip()}")
                else:
                    # 未知状态：使用返回码辅助判断
                    self.logger.warning(f"未知连接状态: 返回码={return_code}")

                return False  # 连接失败，返回False

            except Exception as e:
                self.logger.error(f"连接设备时出错: {e}")
                return False  # 发生异常，返回失败

        return self._retry_operation(_connect_impl, "连接设备")

    def run(self):
        """执行完整的BLE连接流程：获取锁->扫描设备->连接设备->释放锁"""
        self.logger.info(f"=== 开始BLE设备连接: {self.ble_device_name} ===")

        try:
            # 1. 获取操作锁：防止多个进程并发操作蓝牙适配器
            self.lock_file = self.acquire_lock()
            if not self.lock_file:
                self.logger.warning("警告: 无法获取锁，继续执行（存在并发风险）")

            # 2. 扫描目标设备获取MAC地址（没有MAC地址无法连接）
            self.ble_mac = self.scan_device()
            if not self.ble_mac:
                self.logger.error("错误: 无法找到设备MAC地址，连接流程终止")
                return False  # 返回False表示扫描失败，无法继续连接

            # 3. 使用获取到的MAC地址连接设备
            self.connection_success = self.connect_device(self.ble_mac)
            if self.connection_success:
                self.logger.info("BLE设备连接成功，流程完成")
                return True  # 返回True表示整个流程成功
            else:
                self.logger.error("错误: 找到设备MAC地址但连接失败")
                return False  # 返回False表示连接失败

        except Exception as e:
            # 捕获连接流程中的意外异常
            self.logger.error(f"主连接流程异常: {e}")
            return False  # 发生异常，返回失败
        finally:
            # 4. 无论连接成功/失败/异常，都释放锁（避免锁残留）
            self.release_lock()
            self.logger.info("=== BLE连接流程完成 ===")

    def get_connection_result(self):
        """获取最终的BLE连接结果：返回包含连接状态、设备MAC和适配器名称的字典"""
        return {
            "success": self.connection_success,  # 连接是否成功
            "mac_address": self.ble_mac,         # 设备MAC地址（如已扫描到）
            "hci_device": self.hci_device        # 使用的蓝牙适配器名称
        }


# ==================================================
# !/usr/bin/env python
# @Author: simon.zhang
# @Date: 2025/8/05 14:21
# @FileName: ble_control.py
# @Email: wangfu_zhang@ggec.com.cn
# Function: Connect to BLE via the hcitool command
# ==================================================

# Import dependent modules with comments on their core functions
import os
import re
import time
import subprocess
import sys
import logging
import select
from datetime import datetime
import fcntl
from collections import Counter  # For counting statistics

from Python.Test_Cases.Low_Power_Sequence.LPS_modules import thread_terminal_logging


class BLEConnector:
    """Encapsulates BLE connection functionality for device wake-up in reliability testing"""

    def __init__(self, ble_device_name, max_retries=3, logger=None):
        """
        Initialize BLE connector
        :param ble_device_name: Target BLE device name (must match actual device broadcast name)
        :param max_retries: Maximum number of retries (default 3, for retry after failed operations like scanning, connecting)
        :param logger: Optional external logger (creates internal one if not provided)
        """
        # Validation for an empty device name
        if not ble_device_name or not isinstance(ble_device_name, str) or ble_device_name.strip() == "":
            raise ValueError(f"BLE device name cannot be empty, Received:'{ble_device_name}")
        # Initialize core parameters
        self.ble_device_name = ble_device_name  # Target BLE device name, used for matching during scanning
        self.max_retries = max_retries  # Default maximum retry count for all retryable operations

        # Configure logging system: prefer externally provided logger, create internal one if none
        # self.logger = logger or self._setup_logger()

        # Automatically detect USB Bluetooth adapter in the system (exclude virtual devices to ensure hardware validity)
        self.hci_device = self._detect_usb_bluetooth_dongle()
        #self.logger.info(f"Using Bluetooth adapter: {self.hci_device}")
        thread_terminal_logging("UUT", "info", f"Using Bluetooth adapter:{self.hci_device}")

        # Connection process state tracking variables
        self.connection_success = False
        self.lock_file = None
        self.ble_mac = None
        self.scan_process = None
        self.lock_fd = None  # Used to store the file descriptor

        # Ensure Bluetooth adapter is available during initialization, exit if unavailable
        if not self.ensure_adapter_ready():
            #self.logger.error("Bluetooth adapter unavailable, exiting program")
            thread_terminal_logging("UUT", "error", f"Bluetooth adapter unavailable, exiting program")
            sys.exit(1)
    #
    # def _setup_logger(self):
    #     """Configure logger: output to both console (INFO level) and file (DEBUG level)"""
    #     # Create logger instance with name "BLEConnector"
    #     logger = logging.getLogger("BLEConnector")
    #     logger.setLevel(logging.INFO)
    #
    #     # Clear existing log handlers (prevent duplicate logging from multiple handlers)
    #     if logger.hasHandlers():
    #         for handler in logger.handlers[:]:
    #             logger.removeHandler(handler)
    #             handler.close()  # Close handler to release resources
    #
    #     # Define log format: includes timestamp, log level, and message
    #     formatter = logging.Formatter(
    #         '%(asctime)s - %(levelname)s - %(name)s - %(message)s',  # Fixed: added space after %(name)s
    #         datefmt='%Y-%m-%d %H:%M:%S'
    #     )
    #
    #     # 1. Create console log handler (outputs INFO and above level logs to terminal)
    #     ch = logging.StreamHandler()
    #     ch.setLevel(logging.INFO)
    #     ch.setFormatter(formatter)
    #     logger.addHandler(ch)
    #
    #     # 2. Create file log handler (outputs DEBUG and above level logs to file for later debugging)
    #     log_file = f"ble_connector_{datetime.now().strftime('%Y%m%d')}.log"  # Log filename includes date
    #     fh = logging.FileHandler(log_file)
    #     fh.setLevel(logging.DEBUG)
    #     fh.setFormatter(formatter)
    #     logger.addHandler(fh)
    #
    #     return logger  # return the configure logger

    def _detect_usb_bluetooth_dongle(self):
        """Detect USB Bluetooth adapters in the system (exclude virtual devices),
         returns first available USB Bluetooth device name (e.g., hci0)"""
        try:
            # Execute hciconfig command to get all Bluetooth device information (hciconfig is Linux Bluetooth tool)
            result = subprocess.run(
                ['hciconfig'],
                capture_output=True,
                text=True,
                timeout=10
            )
            # Check command execution result: non-zero return code indicates failure (e.g., hciconfig not installed)
            if result.returncode != 0:
                self.logger.error("Failed to retrieve Bluetooth device information")
                sys.exit(1)

            # Parse hciconfig output to extract USB Bluetooth devices
            output = result.stdout
            lines = output.split('\n')

            usb_devices = []
            current_device = None

            for line in lines:
                # 1. Check if line represents a Bluetooth device: format "hciX:" (X is number, e.g., hci0:)
                if ':' in line and line.strip().startswith('hci'):
                    parts = line.split(':')  # Split "hci0:" into ["hci0", ""]
                    current_device = parts[0].strip()  # Extract device name (e.g., hci0)

                    # Check if device is USB type (exclude virtual devices, USB devices have "Bus: USB" identifier)
                    if 'Bus: USB' in line:
                        usb_devices.append(current_device)  # Add to USB device list
                        self.logger.info(f"Found USB Bluetooth device: {current_device}")

                # 2. Check if current device is active (UP RUNNING)
                elif current_device and 'UP RUNNING' in line:
                    # If active device is in USB device list, prefer this device (plug-and-play and already active)
                    if current_device in usb_devices:
                        self.logger.info(f"Selecting UP state USB device: {current_device}")
                        return current_device  # Return active USB device directly, no need to continue searching

            # If no active USB device found but USB devices exist, select first USB device
            if usb_devices:
                selected = usb_devices[0]
                self.logger.info(f"Selecting USB Bluetooth device: {selected}")
                return selected

            # No USB Bluetooth devices found (may not be inserted or driver not recognized)
            self.logger.error("No USB Bluetooth dongle found")
            sys.exit(1)

        except Exception as e:
            self.logger.error(f"Error detecting USB Bluetooth dongle: {e}")
            sys.exit(1)

    def _run_command(self, cmd, timeout=30):
        """
        Universal system command execution function: supports timeout control, real-time logging, returns command execution results
        :param cmd: System command to execute (string format, e.g., "hciconfig hci0 up")
        :param timeout: Command execution timeout in seconds (default 30)
        :return: stdout (command standard output), stderr (command error output), return_code (return code), timed_out (whether timeout occurred)
        """
        self.logger.debug(
            f"Executing command: {cmd}")  # Log command to execute (DEBUG level, only visible in file logs)

        try:
            # Create subprocess to execute command: shell=True allows complex commands (e.g., pipes, redirects)
            process = subprocess.Popen(
                cmd,
                shell=True,  # Allow execution of commands containing complex syntax such as pipelines and redirects
                stdout=subprocess.PIPE,  # Redirect standard output to pipe
                stderr=subprocess.PIPE,  # Redirect error output to pipe
                text=True
            )

            # Initialize output storage dictionary: stores stdout and stderr contents separately
            outputs = {"stdout": [], "stderr": []}
            fds = [process.stdout, process.stderr]  # File descriptors to monitor (stdout and stderr)

            start_time = time.time()
            timed_out = False

            # Loop to monitor file descriptors until all streams close or timeout
            while fds and not timed_out:
                # Calculate remaining timeout time (prevent cumulative error)
                time_remaining = timeout - (time.time() - start_time)
                if time_remaining <= 0:  # remaining time <=0 ,judged as timeout
                    timed_out = True #Timeout marker
                    break

                # Use select to monitor file descriptors: wait for readable events with remaining time as timeout
                ready, _, _ = select.select(fds, [], [], time_remaining)
                if not ready:
                    continue  #No output, continue waiting

                # Process readable file descriptors (stdout or stderr)
                for fd in ready:
                    try:
                        line = fd.readline().strip()  # Read one line and remove leading/trailing whitespace
                        if line:  # If content was read (non-empty line)
                            if fd == process.stdout:  # Distinguish between stdout and stderr
                                self.logger.debug(f"STDOUT: {line}")
                                outputs["stdout"].append(line)
                            else:
                                self.logger.debug(f"STDERR: {line}")
                                outputs["stderr"].append(line)
                        else:  # Empty line indicates stream closed (EOF), remove from monitoring list
                            fds.remove(fd)
                    except Exception as e:
                        self.logger.warning(f"Error reading output: {e}")
                        if fd in fds:
                            fds.remove(fd)

            # Handle command timeout: terminate subprocess and clean up resources
            if timed_out:
                process.terminate()  # First try graceful termination
                try:
                    process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    process.kill()
                self.logger.error(f"Command timed out: {cmd}")
                return "", "Command execution timed out", -1, True

            # Command completed normally, get process return code
            return_code = process.wait()

            # Combine output lists into strings (join lines with newlines)
            stdout = "\n".join(outputs["stdout"])
            stderr = "\n".join(outputs["stderr"])

            self.logger.debug(f"Command return code: {return_code}")
            return stdout, stderr, return_code, False  # Return normal execution results

        except Exception as e:
            # Catch exceptions during command execution (e.g., failed to create subprocess)
            self.logger.error(f"Command execution exception: {e}")
            return f"Exception: {e}", "Execution error", -1, False

    def _retry_operation(self, operation_func, operation_name, *args, **kwargs):
        """
        Universal retry operation function: provides "failure retry + exponential backoff waiting" logic for any operation
        Exponential backoff: retry interval grows as 2^n with each attempt (maximum 30 seconds), avoiding frequent retries consuming resources
        :param operation_func: Target function to execute (e.g., scanning, connecting, resetting adapter)
        :param operation_name: Operation name (for logging, e.g., "scan device")
        :param *args: Positional arguments passed to target function (e.g., no additional arguments for scanning)
        :param *kwargs: Keyword arguments passed to target function, supports max_retries to override default retry count
        :return: Return value of target function when successful; None if all retries fail
        """
        # Prefer max_retries from kwargs, use class initialization default if not provided
        max_retries = kwargs.pop('max_retries', self.max_retries)

        # Loop to perform retries: from 1 to max_retries attempts
        for attempt in range(1, max_retries + 1):
            try:
                self.logger.info(f"Performing {operation_name} (attempt {attempt}/{max_retries})")

                # Call target function with positional and keyword arguments
                result = operation_func(*args, **kwargs)

                # Determine if operation succeeded: result is considered successful if not False or None (different operations have different return values)
                if result is not False and result is not None:
                    return result  # Success, return result

                # Operation failed and not reached maximum retries, calculate wait time and retry
                if attempt < max_retries:
                    wait_time = min(2 ** attempt, 30)  # Exponential backoff: 2^attempt seconds, maximum 30 seconds
                    self.logger.info(f"Waiting {wait_time} seconds before retry")
                    time.sleep(wait_time)  # Wait for specified time

            except Exception as e:
                # Catch exceptions during target function execution (e.g., file read errors during scanning)
                self.logger.error(f"Error performing {operation_name}: {e}")
                # Wait and retry if not reached maximum retries
                if attempt < max_retries:
                    wait_time = min(2 ** attempt, 30)
                    self.logger.info(f"Waiting {wait_time} seconds before retry")
                    time.sleep(wait_time)

        # All retry attempts exhausted with failure
        self.logger.error(f"Error: Exceeded maximum retry count {max_retries}")
        return None  # All retries hava failed,and the upper layer will handle it accordingly(such as terminating the process)

    def reset_adapter(self):
        """Reset Bluetooth adapter: down->reset->up, restore adapter to initial state (resolve some connection anomalies)"""

        # Internal implementation function: encapsulates reset logic (passed to _retry_operation for retries)
        def _reset_impl():
            try:
                # 1. Turn off Bluetooth adapter (down command)
                self._run_command(f"sudo hciconfig {self.hci_device} down")
                time.sleep(1)

                # 2. Perform adapter reset (reset command)
                self._run_command(f"sudo hciconfig {self.hci_device} reset")
                time.sleep(2) # wait for 2s to allow time for hardware reset

                # 3. Re-enable adapter (up command)
                self._run_command(f"sudo hciconfig {self.hci_device} up")
                time.sleep(2) # wait for 2s to ensure activation is complete

                # 4. Check if adapter is in UP RUNNING state after reset (verify reset success)
                stdout, _, _, _ = self._run_command(f"hciconfig {self.hci_device}")

                if "UP RUNNING" in stdout:
                    self.logger.info(f"Adapter {self.hci_device} reset successful")
                    return True  # single reset successful
                else:
                    self.logger.warning(f"Adapter state abnormal: {stdout}")
                    return False # exception occurred,reset failed

            except Exception as e:
                self.logger.error(f"Error resetting adapter: {e}")
                return False

        # Call universal retry function to perform reset operation (retry logic handled by _retry_operation)
        return self._retry_operation(_reset_impl, "reset adapter")

    def ensure_adapter_ready(self):
        """Ensure Bluetooth adapter is in usable state (UP RUNNING): attempt activation if not active"""

        # Internal implementation function: encapsulates adapter state check and activation logic
        def _ensure_impl():
            try:
                # 1. First check current adapter state
                stdout, _, _, _ = self._run_command(f"hciconfig {self.hci_device}")

                # Return success if already in UP RUNNING state
                if "UP RUNNING" in stdout:
                    self.logger.info(f"Adapter {self.hci_device} is already enabled")
                    return True

                # 2. Adapter not active, attempt activation with up command
                self.logger.warning(f"Adapter {self.hci_device} not enabled, attempting activation...")
                self._run_command(f"sudo hciconfig {self.hci_device} up")
                time.sleep(2)  # wait for 2 seconds to ensure activation is complete

                # 3. Check state again after activation
                stdout, _, _, _ = self._run_command(f"hciconfig {self.hci_device}")
                if "UP RUNNING" in stdout:
                    self.logger.info(f"Adapter {self.hci_device} activation successful")
                    return True # activation successful
                else:
                    self.logger.warning(f"Adapter state after activation: {stdout}")
                    return False  # abnormal Status after activation，failed

            except Exception as e:
                self.logger.error(f"Error checking adapter state: {e}")
                return False

        # Call universal retry function to ensure adapter readiness (retry on activation failure)
        return self._retry_operation(_ensure_impl, "ensure adapter ready")


    def acquire_lock(self, max_retries=3):
        """Acquire lock file (uses fcntl to implement reliable inter-process file locking)"""

        def _acquire_lock_impl():
            lock_file = f"/tmp/.ble_lock_{self.hci_device}"
            max_wait = 30  # Maximum waiting time in seconds

            try:
                # Open or create the lock file
                # os.O_CREAT: Create file if it doesn't exist; os.O_RDWR: Read-write mode; 0o644: File permission (owner r/w, others r)
                fd = os.open(lock_file, os.O_CREAT | os.O_RDWR, 0o644)

                # Attempt to acquire a non-blocking exclusive lock
                try:
                    # fcntl.LOCK_EX: Exclusive lock (only one process can hold it at a time)
                    # fcntl.LOCK_NB: Non-blocking mode (raise error immediately if lock is held)
                    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    # Lock acquired successfully, write PID to the file
                    os.ftruncate(fd, 0)  # Clear the file content (remove historical PID)
                    os.write(fd, str(os.getpid()).encode())  # Write current process PID for debugging
                    self.logger.info(f"Created lock file: {lock_file}")
                    self.lock_fd = fd  # Save file descriptor for subsequent release
                    return lock_file

                except BlockingIOError:
                    # Lock is held by another process, enter waiting logic
                    self.logger.info("Lock is held by another process, waiting...")

                    start_time = time.time()
                    # Retry every 0.1 seconds until timeout (balances response speed and CPU usage)
                    while time.time() - start_time < max_wait:
                        try:
                            # Retry acquiring the non-blocking exclusive lock
                            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                            os.ftruncate(fd, 0)  # Clear file content
                            os.write(fd, str(os.getpid()).encode())  # Write current process PID
                            self.logger.info(f"Created lock file: {lock_file}")
                            self.lock_fd = fd
                            return lock_file

                        except BlockingIOError:
                            time.sleep(0.1)  # Short delay to reduce CPU consumption

                    # Timeout occurred, clean up resources
                    os.close(fd)  # Close file descriptor to avoid leakage
                    self.logger.warning(f"Lock waiting timed out ({max_wait}s), proceeding forcefully")
                    return None

            except Exception as e:
                self.logger.error(f"Failed to acquire lock: {e}")
                return None

        # Call the universal retry function (retry on acquisition failure)
        return self._retry_operation(_acquire_lock_impl, "acquire lock", max_retries=max_retries)


    def release_lock(self):
        """Release the lock file (with error handling)"""
        # Release the fcntl lock first (kernel-level lock release)
        if hasattr(self, 'lock_fd') and self.lock_fd is not None:
            try:
                fcntl.flock(self.lock_fd, fcntl.LOCK_UN)  # LOCK_UN: Release the held lock
                os.close(self.lock_fd)  # Close file descriptor to free system resources
                self.lock_fd = None  # Reset to indicate no active lock
                self.logger.info("Successfully released fcntl lock")
            except Exception as e:
                self.logger.error(f"Failed to release fcntl lock: {e}")

        # Delete the lock file (retain original cleanup logic)
        if self.lock_file and os.path.exists(self.lock_file):
            try:
                os.remove(self.lock_file)  # Delete the lock file to avoid residual files
                self.logger.info(f"Released lock file: {self.lock_file}")
                self.lock_file = None  # Reset to indicate no lock file exists
            except Exception as e:
                self.logger.error(f"Failed to release lock file: {e}")
        else:
            self.logger.info("No lock file to release")

    def scan_device(self):
        """Scan for BLE devices: monitor scan results in real-time, stop immediately when target device name is found, return device MAC address"""
        scan_file = None  # Define variable at function level

        def _scan_impl():
            nonlocal scan_file  # Use nonlocal to modify the outer variable
            # Precompile MAC address regular expression: matches BLE device MAC format (xx:xx:xx:xx:xx:xx, case-insensitive)
            mac_pattern = re.compile(r"((?:[0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}) (.*)")

            try:
                # 1. First stop all possible remaining hcitool processes (avoid interfering with current scan)
                self._run_command("sudo pkill -f hcitool", timeout=5)
                time.sleep(2)  # Wait 2 seconds to ensure processes terminate

                # 2. Reset adapter (clean previous scan state, improve scan success rate)
                self.reset_adapter()
                time.sleep(2)

                # 3. Create temporary scan file: stores output of lescan command (inter-process data sharing)
                scan_file = f"ble_scan_{os.getpid()}_{int(time.time())}.txt"

                # 4. Start BLE scanning process: lescan command (--duplicates keeps duplicate scan results for signal strength judgment)
                scan_cmd = f"sudo hcitool -i {self.hci_device} lescan --duplicates > {scan_file} 2>&1"
                self.scan_process = subprocess.Popen(
                    scan_cmd,
                    shell=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True
                )
                # 5. Configure scan timeout and result monitoring
                scan_timeout = 30
                start_time = time.time()
                found_device = None

                # Monitor scan file in real-time to find target device
                while time.time() - start_time < scan_timeout:
                    # Check if scan process exited unexpectedly (terminated before timeout)
                    if self.scan_process.poll() is not None:
                        break
                    # Check if temporary scan file exists (process startup may have delay)
                    if os.path.exists(scan_file):
                        try:
                            # Read current content of scan file
                            with open(scan_file, 'r', errors='ignore') as f:
                                content = f.read()

                            # Parse scan results line by line to match target device
                            lines = content.splitlines()
                            for line in lines:
                                # Extract MAC address and device name with regular expression
                                match = mac_pattern.match(line)
                                if match and self.ble_device_name in match.group(2):
                                    # Target device found: extract MAC address
                                    found_device = match.group(1)
                                    self.logger.info(
                                        f"Found device in real-time: {self.ble_device_name} MAC: {found_device}")
                                    # Stop scan process immediately after finding device
                                    self.scan_process.terminate()
                                    try:
                                        self.scan_process.wait(timeout=2)
                                    except subprocess.TimeoutExpired:
                                        self.scan_process.kill()
                                    return found_device

                        except Exception as e:
                            self.logger.warning(f"Error reading scan file: {e}")

                    time.sleep(0.5)  # Check scan results every 0.5 seconds, balance real-time performance and CPU usage

                # 6. Scan timeout: stop scan process (prevent process leftover)
                if self.scan_process.poll() is None:
                    self.scan_process.terminate()
                    try:
                        self.scan_process.wait(timeout=2)
                    except subprocess.TimeoutExpired:
                        self.scan_process.kill()

                # 7. Check scan file again after timeout (device might be scanned at the last moment)
                if os.path.exists(scan_file):
                    try:
                        with open(scan_file, 'r') as f:
                            content = f.read()

                        # Collect all scan results matching target device name (MAC + device name)
                        matches = []
                        for line in content.splitlines():
                            match = mac_pattern.match(line)
                            if match and self.ble_device_name in match.group(2):
                                matches.append((match.group(1), match.group(2)))
                                self.logger.debug(f"Found matching device: {match.group(1)} - {match.group(2)}")

                        # If multiple matching results, select MAC with most occurrences (strongest signal, scanned most times)
                        if matches:
                            mac_counter = Counter(mac for mac, _ in matches)  # Count MAC occurrences
                            ble_mac = mac_counter.most_common(1)[0][0]  # Get MAC with most occurrences
                            self.logger.info(f"Scan completed, found device: {self.ble_device_name} MAC: {ble_mac}")
                            return ble_mac   # return BLE MAC

                    except Exception as e:
                        self.logger.error(f"Failed to read scan file: {e}")

                # 8. Target device not found
                self.logger.warning(f"Device not found: {self.ble_device_name}")
                return False

            except Exception as e:
                self.logger.error(f"Error scanning for device: {e}")
                return False
            finally:
                # Ensure cleanup of leftover processes and temporary files regardless of scan success/failure/exception
                self._run_command("sudo pkill -f hcitool", timeout=5)

        try:
            return self._retry_operation(_scan_impl, "scan device")
        finally:
            # Ensure temporary scan file is deleted
            if scan_file and os.path.exists(scan_file):
                try:
                    os.remove(scan_file)
                    self.logger.debug(f"Deleted temporary scan file: {scan_file}")
                except Exception as e:
                    self.logger.warning(f"Failed to delete scan file {scan_file}: {e}")

    def connect_device(self, ble_mac):
        """Perform BLE device connection: use hcitool lecc command to connect to target device (requires MAC address)"""

        # Internal implementation function: encapsulates connection logic
        def _connect_impl():
            # First check if MAC address is valid (avoid connection failure due to invalid parameters)
            if not ble_mac:
                self.logger.error("Invalid MAC address, skipping connection")
                return False

            try:
                # 1. Stop all Bluetooth-related processes (clean up previous connection leftovers)
                self.logger.info("Stopping all Bluetooth-related processes")
                self._run_command("sudo pkill -f hcitool", timeout=5)
                time.sleep(2)

                # 2. Reset adapter (restore initial state, resolve connection leftover issues)
                self.logger.info("Resetting Bluetooth adapter state")
                self._run_command(f"sudo hciconfig {self.hci_device} reset", timeout=10)
                time.sleep(2)

                # 3. Execute BLE connection command: lecc (LE Connection Command)
                self.logger.info(f"Connecting to device {ble_mac} using hcitool")
                cmd = f"sudo timeout 30 hcitool -i {self.hci_device} lecc --random {ble_mac}"
                # Execute command with timeout set to 35 seconds (5 seconds more than internal command timeout to avoid false timeout judgment)
                stdout, stderr, return_code, timed_out = self._run_command(cmd, timeout=35)

                # 4. Record detailed connection command results (for debugging)
                self.logger.debug(f"Connection command results: timed_out={timed_out}, return_code={return_code}")
                self.logger.debug(f"STDOUT: {stdout}")
                self.logger.debug(f"STDERR: {stderr}")

                # 5. Determine if connection succeeded: successful connection returns "Connection handle"
                if "Connection handle" in stdout:
                    self.logger.info("Connection successful!")
                    return True
                # Handle common connection failure cases
                elif "Could not create connection" in stderr:
                    self.logger.error(f"Connection failed: {stderr.strip()}")
                elif "Connection timed out" in stderr:
                    self.logger.error(f"Connection timed out: {stderr.strip()}")
                else:
                    # Unknown state: use return code for auxiliary judgment
                    self.logger.warning(f"Unknown connection state: return_code={return_code}")

                return False  # Return False for connection failure

            except Exception as e:
                self.logger.error(f"Error connecting to device: {e}")
                return False

        return self._retry_operation(_connect_impl, "connect device")

    def run(self):
        """Perform complete BLE connection process: acquire lock->scan for device->connect to device->release lock"""
        self.logger.info(f"=== Starting BLE device connection: {self.ble_device_name} ===")

        try:
            # 1. Acquire operation lock: prevent concurrent operation on Bluetooth adapter by multiple processes
            self.lock_file = self.acquire_lock()
            if not self.lock_file:
                self.logger.warning("Warning: Could not acquire lock, proceeding (potential concurrency risk)")

            # 2. Scan for target device to get MAC address (cannot connect without MAC address)
            self.ble_mac = self.scan_device()
            if not self.ble_mac:
                self.logger.error("Could not find device MAC address, connection process terminated")
                return False  # return False to indicate scan failure,unable to continue connection

            # 3. Connect to device using acquired MAC address
            self.connection_success = self.connect_device(self.ble_mac)
            if self.connection_success:
                self.logger.info("BLE device connection successful, process completed")
                return True   # return True indicates that the entire process is successful
            else:
                self.logger.error("Found device MAC address but connection failed")
                return False  # Return false to indicate connection failure

        except Exception as e:
            # Catch unexpected exceptions in connection process
            self.logger.error(f"Exception in main connection process: {e}")
            return False
        finally:
            # 4. Release lock regardless of connection success/failure/exception (avoid lock leftover)
            self.release_lock()
            self.logger.info("=== BLE connection process completed ===")

    def get_connection_result(self):
        """Get final BLE connection result: returns dictionary containing connection status, device MAC, and adapter name"""
        return {
            "success": self.connection_success,
            "mac_address": self.ble_mac,
            "hci_device": self.hci_device
        }

