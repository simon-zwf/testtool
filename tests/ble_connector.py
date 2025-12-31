#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
重构版BLE连接器
用于可靠性测试中的设备唤醒
优化了代码结构、错误处理和资源管理
"""

# 导入依赖模块，注释各模块核心作用
import os               # 用于文件系统操作（如创建/删除文件、检查文件存在性）
import re               # 用于正则表达式匹配（如提取蓝牙设备MAC地址）
import time             # 用于时间控制（如等待、超时计算）
import subprocess       # 用于执行系统命令（如hciconfig、hcitool等蓝牙工具命令）
import sys              # 用于系统级操作（如程序退出、获取系统信息）
import logging          # 用于日志记录（调试、信息、错误等级别日志）
import select           # 用于I/O多路复用（高效监听多个文件描述符的读写事件）
from datetime import datetime  # 用于日期时间处理（如日志文件命名、锁过期判断）
from collections import Counter  # 用于计数统计（如扫描时统计设备MAC出现次数，判断信号强度）
import fcntl

class BLEConnector:
    """封装BLE连接功能，用于可靠性测试中的设备唤醒"""

    def __init__(self, ble_device_name, max_retries=3, logger=None):
        """
        初始化BLE连接器
        :param ble_device_name: 目标BLE设备名称（需与实际设备广播名称一致）
        :param max_retries: 最大重试次数 (默认3次，用于扫描、连接等操作失败后的重试)
        :param logger: 可选的外部日志记录器（若未传入则内部自动创建）
        """
        # 初始化核心参数
        self.ble_device_name = ble_device_name  # 目标BLE设备名称，用于扫描时匹配
        self.max_retries = max_retries          # 所有可重试操作的默认最大重试次数

        # 配置日志系统：优先使用外部传入的logger，无则调用内部_setup_logger创建
        self.logger = logger or self._setup_logger()

        # 自动检测系统中的USB蓝牙适配器（排除虚拟设备，确保硬件有效性）
        self.hci_device = self._detect_usb_bluetooth_dongle()
        self.logger.info(f"使用蓝牙适配器: {self.hci_device}")

        # 连接过程状态跟踪变量
        self.connection_success = False  # 最终连接是否成功的标记
        self.lock_file = None            # 锁文件路径（用于防止多进程并发操作蓝牙适配器）
        self.ble_mac = None              # 存储扫描到的目标设备MAC地址（BLE连接需MAC地址）
        self.scan_process = None         # 存储扫描进程对象（用于后续控制扫描进程的终止）
        self.lock_fd = None

        # 初始化阶段确保蓝牙适配器处于可用状态，不可用则退出程序
        if not self.ensure_adapter_ready():
            self.logger.error("蓝牙适配器不可用，退出程序")
            sys.exit(1)

    def _setup_logger(self):
        """配置日志记录器：同时输出到控制台（INFO级别）和文件（DEBUG级别）"""
        # 创建日志器实例，名称为"BLEConnector"
        logger = logging.getLogger("BLEConnector")
        logger.setLevel(logging.DEBUG)  # 日志器基础级别设为DEBUG（捕获所有级别日志）

        # 清除现有日志处理器（避免重复添加处理器导致日志重复输出）
        if logger.hasHandlers():
            for handler in logger.handlers[:]:
                logger.removeHandler(handler)
                handler.close()  # 关闭处理器释放资源

        # 定义日志格式：包含时间、日志级别、日志内容
        formatter = logging.Formatter(
            '%(asctime)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'  # 时间格式：年-月-日 时:分:秒
        )

        # 1. 创建控制台日志处理器（输出INFO及以上级别日志到终端）
        ch = logging.StreamHandler()
        ch.setLevel(logging.INFO)       # 控制台仅显示INFO及更高级别（过滤DEBUG）
        ch.setFormatter(formatter)      # 应用日志格式
        logger.addHandler(ch)           # 将控制台处理器添加到日志器

        # 2. 创建文件日志处理器（输出DEBUG及以上级别日志到文件，便于后续调试）
        log_file = f"ble_connector_{datetime.now().strftime('%Y%m%d')}.log"  # 日志文件名含日期
        fh = logging.FileHandler(log_file)
        fh.setLevel(logging.DEBUG)      # 文件记录所有DEBUG及以上级别日志
        fh.setFormatter(formatter)      # 应用日志格式
        logger.addHandler(fh)           # 将文件处理器添加到日志器

        return logger  # 返回配置好的日志器

    def _detect_usb_bluetooth_dongle(self):
        """检测系统中的USB蓝牙适配器（排除虚拟设备），返回第一个可用的USB蓝牙设备名（如hci0）"""
        try:
            # 执行hciconfig命令获取所有蓝牙设备信息（hciconfig是Linux蓝牙工具）
            result = subprocess.run(
                ['hciconfig'],            # 要执行的命令
                capture_output=True,     # 捕获命令的stdout和stderr
                text=True,               # 输出结果以字符串形式返回（而非字节流）
                timeout=10               # 命令执行超时时间（10秒，防止卡死）
            )
            # 检查命令执行结果：返回码非0表示命令执行失败（如hciconfig未安装）
            if result.returncode != 0:
                self.logger.error("无法获取蓝牙设备信息")
                sys.exit(1)

            # 解析hciconfig输出结果，提取USB蓝牙设备
            output = result.stdout  # 命令的标准输出（包含所有蓝牙设备信息）
            lines = output.split('\n')  # 按行分割输出内容，逐行解析

            usb_devices = []  # 存储所有检测到的USB蓝牙设备（排除虚拟设备）
            current_device = None  # 临时存储当前解析到的蓝牙设备名（如hci0）

            for line in lines:
                # 1. 判断是否为蓝牙设备行：格式为"hciX:"（X为数字，如hci0:）
                if ':' in line and line.strip().startswith('hci'):
                    parts = line.split(':')  # 分割"hci0:"为["hci0", ""]
                    current_device = parts[0].strip()  # 提取设备名（如hci0）

                    # 检查该设备是否为USB类型（排除虚拟设备，USB设备含"Bus: USB"标识）
                    if 'Bus: USB' in line:
                        usb_devices.append(current_device)  # 加入USB设备列表
                        self.logger.info(f"找到USB蓝牙设备: {current_device}")

                # 2. 判断当前设备是否处于激活状态（UP RUNNING）
                elif current_device and 'UP RUNNING' in line:
                    # 若当前激活的设备在USB设备列表中，优先选择该设备（即插即用且已激活）
                    if current_device in usb_devices:
                        self.logger.info(f"选择UP状态的USB设备: {current_device}")
                        return current_device  # 直接返回激活的USB设备，无需继续查找

            # 若未找到激活的USB设备，但存在USB设备列表，选择第一个USB设备
            if usb_devices:
                selected = usb_devices[0]
                self.logger.info(f"选择USB蓝牙设备: {selected}")
                return selected

            # 未找到任何USB蓝牙设备（可能未插入或驱动未识别）
            self.logger.error("未找到USB蓝牙dongle")
            sys.exit(1)

        except Exception as e:
            # 捕获检测过程中的所有异常（如命令超时、解析错误等）
            self.logger.error(f"检测USB蓝牙dongle时出错: {e}")
            sys.exit(1)

    def _run_command(self, cmd, timeout=30):
        """
        通用系统命令执行函数：支持超时控制、实时日志记录，返回命令执行结果
        :param cmd: 要执行的系统命令（字符串形式，如"hciconfig hci0 up"）
        :param timeout: 命令执行超时时间（默认30秒）
        :return: stdout（命令标准输出）、stderr（命令错误输出）、return_code（返回码）、timed_out（是否超时）
        """
        self.logger.debug(f"执行命令: {cmd}")  # 记录要执行的命令（DEBUG级别，仅文件日志可见）

        try:
            # 创建子进程执行命令：shell=True允许执行复杂命令（如管道、重定向）
            process = subprocess.Popen(
                cmd,
                shell=True,
                stdout=subprocess.PIPE,  # 重定向标准输出到管道
                stderr=subprocess.PIPE,  # 重定向错误输出到管道
                text=True                # 输出以字符串形式返回
            )

            # 初始化输出存储字典：分别存储stdout和stderr的内容
            outputs = {"stdout": [], "stderr": []}
            fds = [process.stdout, process.stderr]  # 要监听的文件描述符（stdout和stderr）

            start_time = time.time()  # 记录命令开始执行时间（用于计算超时）
            timed_out = False         # 超时标记

            # 循环监听文件描述符，直到所有流关闭或超时
            while fds and not timed_out:
                # 计算剩余超时时间（防止累计误差）
                time_remaining = timeout - (time.time() - start_time)
                if time_remaining <= 0:  # 剩余时间<=0，判定为超时
                    timed_out = True
                    break

                # 使用select监听文件描述符：等待可读事件，超时时间为剩余时间
                # select.select(rlist, wlist, xlist, timeout)：rlist=要监听的可读流
                ready, _, _ = select.select(fds, [], [], time_remaining)
                if not ready:  # 无可读事件且未超时，继续循环等待
                    continue

                # 处理可读的文件描述符（stdout或stderr）
                for fd in ready:
                    try:
                        line = fd.readline().strip()  # 读取一行内容并去除首尾空白
                        if line:  # 若读取到内容（非空行）
                            if fd == process.stdout:  # 区分stdout和stderr
                                self.logger.debug(f"STDOUT: {line}")  # 记录标准输出
                                outputs["stdout"].append(line)
                            else:
                                self.logger.debug(f"STDERR: {line}")  # 记录错误输出
                                outputs["stderr"].append(line)
                        else:  # 读取到空行表示流已关闭（EOF），从监听列表中移除
                            fds.remove(fd)
                    except Exception as e:
                        # 捕获读取流时的异常（如流已关闭）
                        self.logger.warning(f"读取输出时出错: {e}")
                        if fd in fds:
                            fds.remove(fd)

            # 处理命令超时情况：终止子进程并清理资源
            if timed_out:
                process.terminate()  # 先尝试优雅终止进程
                try:
                    # 等待2秒确认进程终止，未终止则强制杀死
                    process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    process.kill()  # 强制杀死进程
                self.logger.error(f"命令超时: {cmd}")
                return "", "命令执行超时", -1, True  # 返回超时结果

            # 命令正常结束，获取进程返回码
            return_code = process.wait()

            # 合并输出列表为字符串（每行用换行符连接）
            stdout = "\n".join(outputs["stdout"])
            stderr = "\n".join(outputs["stderr"])

            self.logger.debug(f"命令返回码: {return_code}")  # 记录命令返回码
            return stdout, stderr, return_code, False  # 返回正常执行结果

        except Exception as e:
            # 捕获命令执行过程中的异常（如创建子进程失败）
            self.logger.error(f"命令执行异常: {e}")
            return f"异常: {e}", "执行错误", -1, False

    def _retry_operation(self, operation_func, operation_name, *args, **kwargs):
        """
        通用重试操作函数：为任意操作提供「失败重试 + 指数退避等待」逻辑
        指数退避：重试间隔随次数增加呈2^n增长（最大30秒），避免频繁重试占用资源
        :param operation_func: 要执行的目标函数（如扫描、连接、重置适配器）
        :param operation_name: 操作名称（用于日志记录，如"扫描设备"）
        :param *args: 传给目标函数的位置参数（如扫描时无需额外参数）
        :param **kwargs: 传给目标函数的关键字参数，支持max_retries覆盖默认重试次数
        :return: 目标函数成功时的返回值；所有重试失败则返回None
        """
        # 优先使用kwargs中的max_retries，无则使用类初始化时的默认值
        max_retries = kwargs.pop('max_retries', self.max_retries)

        # 循环执行重试：从1到max_retries次
        for attempt in range(1, max_retries + 1):
            try:
                self.logger.info(f"执行 {operation_name} (尝试 {attempt}/{max_retries})")

                # 调用目标函数，传入位置参数和关键字参数
                result = operation_func(*args, **kwargs)

                # 判断操作是否成功：结果不为False和None即视为成功（不同操作返回值不同）
                if result is not False and result is not None:
                    return result  # 成功则返回结果，终止重试

                # 操作失败且未到最大重试次数，计算等待时间后重试
                if attempt < max_retries:
                    wait_time = min(2 ** attempt, 30)  # 指数退避：2^attempt秒，最大30秒
                    self.logger.info(f"等待 {wait_time} 秒后重试")
                    time.sleep(wait_time)  # 等待指定时间

            except Exception as e:
                # 捕获目标函数执行过程中的异常（如扫描时文件读取错误）
                self.logger.error(f"{operation_name} 执行出错: {e}")
                # 未到最大重试次数则等待后重试
                if attempt < max_retries:
                    wait_time = min(2 ** attempt, 30)
                    self.logger.info(f"等待 {wait_time} 秒后重试")
                    time.sleep(wait_time)

            # 所有重试次数用完仍失败
        self.logger.error(f"错误: 超过最大重试次数 {max_retries}")
        return None

    def reset_adapter(self):
        """重置蓝牙适配器：关闭->重置->启用，恢复适配器初始状态（解决部分连接异常）"""

        # 内部实现函数：封装重置逻辑（用于传给_retry_operation进行重试）
        def _reset_impl():
            try:
                # 1. 关闭蓝牙适配器（down命令）
                self._run_command(f"sudo hciconfig {self.hci_device} down")
                time.sleep(1)  # 等待1秒确保操作生效

                # 2. 执行适配器重置（reset命令）
                self._run_command(f"sudo hciconfig {self.hci_device} reset")
                time.sleep(2)  # 重置后等待2秒

                # 3. 重新启用适配器（up命令）
                self._run_command(f"sudo hciconfig {self.hci_device} up")
                time.sleep(2)  # 启用后等待2秒确保状态稳定

                # 4. 检查重置后适配器是否处于UP RUNNING状态（验证重置成功）
                stdout, _, _, _ = self._run_command(f"hciconfig {self.hci_device}")

                if "UP RUNNING" in stdout:
                    self.logger.info(f"适配器 {self.hci_device} 重置成功")
                    return True  # 重置成功返回True
                else:
                    self.logger.warning(f"适配器状态异常: {stdout}")
                    return False  # 状态异常返回False

            except Exception as e:
                self.logger.error(f"重置适配器时出错: {e}")
                return False

        # 调用通用重试函数，执行重置操作（重试逻辑由_retry_operation处理）
        return self._retry_operation(_reset_impl, "重置适配器")

    def ensure_adapter_ready(self):
        """确保蓝牙适配器处于可用状态（UP RUNNING）：未激活则尝试激活"""

        # 内部实现函数：封装适配器状态检查和激活逻辑
        def _ensure_impl():
            try:
                # 1. 先检查当前适配器状态
                stdout, _, _, _ = self._run_command(f"hciconfig {self.hci_device}")

                # 若已处于UP RUNNING状态，直接返回成功
                if "UP RUNNING" in stdout:
                    self.logger.info(f"适配器 {self.hci_device} 已启用")
                    return True

                # 2. 适配器未激活，尝试执行up命令激活
                self.logger.warning(f"适配器 {self.hci_device} 未启用，尝试激活...")
                self._run_command(f"sudo hciconfig {self.hci_device} up")
                time.sleep(2)  # 等待2秒确保激活生效

                # 3. 再次检查激活后的状态
                stdout, _, _, _ = self._run_command(f"hciconfig {self.hci_device}")
                if "UP RUNNING" in stdout:
                    self.logger.info(f"适配器 {self.hci_device} 激活成功")
                    return True
                else:
                    self.logger.warning(f"激活后适配器状态: {stdout}")
                    return False

            except Exception as e:
                self.logger.error(f"检查适配器状态时出错: {e}")
                return False

        # 调用通用重试函数，确保适配器就绪（激活失败时重试）
        return self._retry_operation(_ensure_impl, "确保适配器就绪")

    def acquire_lock(self, max_retries=3):
        """获取锁文件（使用fcntl实现可靠的跨进程文件锁）
        适配场景：单蓝牙USB Dongle多进程竞争，确保同一时间仅一个进程操作适配器
        参数：max_retries - 获锁失败重试次数（默认3次，覆盖系统瞬时错误）
        返回：锁文件路径（成功）/ None（失败）
        """

        # 内部实现函数：封装单次获锁逻辑，便于外层重试机制（_retry_operation）调用
        # 优势：重试时仅重复获锁逻辑，不重复参数定义等无关代码
        def _acquire_lock_impl():
            # 1. 生成锁文件路径：与蓝牙适配器强绑定，避免多适配器冲突
            # 路径规则：/tmp目录（系统临时目录，自动清理）+ 适配器标识（如hci1）
            # 场景适配：若PC插多个蓝牙Dongle（hci0/hci1），各自锁文件独立，不互相干扰
            lock_file = f"/tmp/.ble_lock_{self.hci_device}"
            # 2. 最大等待时间：30秒（避免进程因锁长期占用而无限阻塞，符合测试“快速失败”原则）
            max_wait = 30

            try:
                # 3. 打开/创建锁文件：核心系统调用，为后续fcntl锁做准备
                # os.O_CREAT：文件不存在则创建（首次获锁时自动生成文件）
                # os.O_RDWR：读写模式（需写入进程PID用于调试，需读取文件状态）
                # 0o644：文件权限（所有者可读写，其他用户只读）——确保多进程可访问文件，避免权限拒绝
                fd = os.open(lock_file, os.O_CREAT | os.O_RDWR, 0o644)

                # 4. 尝试非阻塞获取独占锁：fcntl核心操作，内核级保障独占性
                try:
                    # fcntl.LOCK_EX：独占锁（同一时间仅一个进程可持有，杜绝多进程并发操作蓝牙）
                    # fcntl.LOCK_NB：非阻塞模式（获锁失败时立即抛错，不阻塞进程，便于后续等待逻辑）
                    # 场景适配：若锁被占用，进程可继续执行等待重试，而非卡住不动
                    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)

                    # 5. 获锁成功：清理文件残留+写入进程PID（便于调试锁占用问题）
                    os.ftruncate(fd, 0)  # 清空文件原有内容（避免历史PID残留，导致调试误判）
                    os.write(fd, str(os.getpid()).encode())  # 写入当前进程PID（如“12345”）
                    # 调试价值：后续若锁异常，可通过cat /tmp/.ble_lock_hci1查看“哪个进程持有锁”

                    # 6. 更新实例属性：记录锁状态，为后续释放锁做准备
                    self.logger.info(f"创建锁文件: {lock_file}")  # 日志记录获锁成功，便于问题追溯
                    self.lock_fd = fd  # 保存文件描述符（解锁时需用此fd调用fcntl.LOCK_UN）
                    self.lock_file = lock_file  # 保存锁文件路径（释放时需用此路径删除文件）

                    return lock_file  # 返回路径，标识获锁成功（外层重试机制会终止重试）

                # 7. 获锁失败：锁已被其他进程持有，进入等待重试逻辑
                except BlockingIOError:
                    self.logger.info("锁已被其他进程持有，等待...")  # 日志提示等待状态，便于观察测试流程
                    start_time = time.time()  # 记录等待开始时间，用于计算超时

                    # 循环等待：每0.1秒重试一次，平衡“响应速度”与“CPU占用”
                    # 0.1秒间隔：既保证锁释放后能快速响应（不耽误测试流程），又避免频繁重试占用CPU
                    while time.time() - start_time < max_wait:
                        try:
                            # 再次尝试非阻塞获锁（锁释放后可立即捕获，无延迟）
                            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)

                            # 获锁成功：重复步骤5-6（清理残留+更新属性）
                            os.ftruncate(fd, 0)
                            os.write(fd, str(os.getpid()).encode())
                            self.logger.info(f"创建锁文件: {lock_file}")
                            self.lock_fd = fd
                            self.lock_file = lock_file

                            return lock_file  # 获锁成功，返回路径

                        # 再次获锁失败：短暂休眠后重试（避免CPU空转）
                        except BlockingIOError:
                            time.sleep(0.1)

                    # 8. 等待超时：主动清理资源，避免泄漏
                    os.close(fd)  # 关闭文件描述符（系统资源有限，不关闭会导致泄漏）
                    self.logger.warning(f"等待锁超时 ({max_wait}秒)，强制继续")
                    return None  # 超时返回None，标识获锁失败（外层重试机制会继续重试）

            # 9. 捕获其他异常（如文件权限不足、系统调用失败等）
            except Exception as e:
                self.logger.error(f"获取锁失败: {e}")  # 日志记录错误详情（如“Permission denied”），便于调试
                return None  # 异常返回None，标识获锁失败

        # 10. 调用通用重试函数：获锁失败时重试max_retries次（默认3次）
        # 场景适配：覆盖系统瞬时错误（如USB Dongle临时无响应导致的获锁失败），提高测试成功率
        return self._retry_operation(_acquire_lock_impl, "获取锁", max_retries=max_retries)
    # 修改 release_lock 方法
    def release_lock(self):
        """释放锁文件（带错误处理）
        核心逻辑：先释放内核锁（避免死锁），再删除锁文件（清理残留），确保资源彻底释放
        """
        # -------------------------- 第一步：释放fcntl内核级锁 --------------------------
        # hasattr判断：防止self.lock_fd未初始化（如未获锁就调用释放）导致的属性错误
        # self.lock_fd is not None：确保仅释放“已持有”的锁，避免重复释放
        if hasattr(self, 'lock_fd') and self.lock_fd is not None:
            try:
                # 释放独占锁：fcntl.LOCK_UN（解锁标识，内核会标记锁为可用）
                # 关键：解锁后其他进程才能获取锁，避免多进程阻塞
                fcntl.flock(self.lock_fd, fcntl.LOCK_UN)
                os.close(self.lock_fd)  # 关闭文件描述符（释放系统资源，避免泄漏）
                self.lock_fd = None  # 重置属性为None，标识“已无锁”（避免重复释放）
                self.logger.info("释放fcntl内核锁成功")  # 日志记录解锁成功，便于流程追溯

            # 捕获解锁异常（如文件描述符已失效、锁已被内核自动释放）
            except Exception as e:
                self.logger.error(f"释放fcntl锁失败: {e}")  # 仅记录错误，不中断后续清理（删除文件仍需执行）

        # -------------------------- 第二步：删除锁文件（清理残留） --------------------------
        # self.lock_file：确保锁文件路径已初始化（已获锁）
        # os.path.exists(self.lock_file)：确保文件实际存在（避免删除不存在的文件）
        if self.lock_file and os.path.exists(self.lock_file):
            try:
                os.remove(self.lock_file)  # 删除锁文件（避免/tmp目录堆积残留，占用磁盘空间）
                self.logger.info(f"释放锁文件: {self.lock_file}")  # 日志记录文件删除成功
                self.lock_file = None  # 重置属性为None，标识“已无锁文件”（避免重复删除）

            # 捕获删除异常（如文件被其他进程占用、权限不足）
            except Exception as e:
                self.logger.error(f"释放锁文件失败: {e}")  # 记录错误，不中断流程（后续测试仍可执行）

        # 无锁可释放的场景（如未获锁就调用释放）
        else:
            self.logger.info("无锁文件可释放")

    def scan_device(self):
        """扫描BLE设备：实时监控扫描结果，找到目标设备名后立即停止，返回设备MAC地址"""

        # 内部实现函数：封装扫描逻辑
        def _scan_impl():
            # 预编译MAC地址正则表达式：匹配BLE设备MAC格式（xx:xx:xx:xx:xx:xx，大小写不敏感）
            mac_pattern = re.compile(r"((?:[0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}) (.*)")

            try:
                # 1. 先停止所有可能残留的hcitool进程（避免影响当前扫描）
                self._run_command("sudo pkill -f hcitool", timeout=5)
                time.sleep(2)  # 等待2秒确保进程终止

                # 2. 重置适配器（清理之前的扫描状态，提高扫描成功率）
                self.reset_adapter()
                time.sleep(2)

                # 3. 创建临时扫描文件：存储lescan命令的输出（进程间共享数据）
                # 文件名包含当前进程PID和时间戳，避免多进程扫描文件冲突
                scan_file = f"ble_scan_{os.getpid()}_{int(time.time())}.txt"

                # 4. 启动BLE扫描进程：lescan命令（--duplicates保留重复扫描结果，便于信号强度判断）
                scan_cmd = f"sudo hcitool -i {self.hci_device} lescan --duplicates > {scan_file} 2>&1"
                self.scan_process = subprocess.Popen(
                    scan_cmd,
                    shell=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True
                )

                # 5. 配置扫描超时和结果监控
                scan_timeout = 30  # 扫描最大超时时间（30秒，避免无限扫描）
                start_time = time.time()  # 记录扫描开始时间
                found_device = None  # 存储找到的目标设备MAC地址

                # 实时监控扫描文件，查找目标设备
                while time.time() - start_time < scan_timeout:
                    # 检查扫描进程是否已意外退出（非超时终止）
                    if self.scan_process.poll() is not None:
                        break

                    # 检查临时扫描文件是否存在（进程启动可能有延迟）
                    if os.path.exists(scan_file):
                        try:
                            # 读取扫描文件当前内容
                            with open(scan_file, 'r') as f:
                                content = f.read()

                            # 逐行解析扫描结果，匹配目标设备
                            lines = content.splitlines()
                            for line in lines:
                                # 用正则表达式提取MAC地址和设备名
                                match = mac_pattern.match(line)
                                if match and self.ble_device_name in match.group(2):
                                    # 找到目标设备：提取MAC地址
                                    found_device = match.group(1)
                                    self.logger.info(f"实时找到设备: {self.ble_device_name} MAC: {found_device}")
                                    # 找到设备后立即停止扫描进程
                                    self.scan_process.terminate()
                                    try:
                                        self.scan_process.wait(timeout=2)  # 等待进程终止
                                    except subprocess.TimeoutExpired:
                                        self.scan_process.kill()  # 强制杀死进程
                                    return found_device  # 返回找到的MAC地址

                        except Exception as e:
                            # 捕获读取扫描文件时的异常（如文件被占用）
                            self.logger.warning(f"读取扫描文件时出错: {e}")

                    time.sleep(0.5)  # 每0.5秒检查一次扫描结果，平衡实时性和CPU占用

                # 6. 扫描超时：停止扫描进程（防止进程残留）
                if self.scan_process.poll() is None:
                    self.scan_process.terminate()
                    try:
                        self.scan_process.wait(timeout=2)
                    except subprocess.TimeoutExpired:
                        self.scan_process.kill()

                # 7. 超时后再次检查扫描文件（可能最后一刻扫描到设备）
                if os.path.exists(scan_file):
                    try:
                        with open(scan_file, 'r') as f:
                            content = f.read()

                        # 收集所有匹配目标设备名的扫描结果（MAC+设备名）
                        matches = []
                        for line in content.splitlines():
                            match = mac_pattern.match(line)
                            if match and self.ble_device_name in match.group(2):
                                matches.append((match.group(1), match.group(2)))
                                self.logger.debug(f"找到匹配设备: {match.group(1)} - {match.group(2)}")

                        # 若有多个匹配结果，选择出现次数最多的MAC（信号最强，扫描到次数多）
                        if matches:
                            mac_counter = Counter(mac for mac, _ in matches)  # 统计MAC出现次数
                            ble_mac = mac_counter.most_common(1)[0][0]  # 获取出现次数最多的MAC
                            self.logger.info(f"扫描完成找到设备: {self.ble_device_name} MAC: {ble_mac}")
                            return ble_mac

                    except Exception as e:
                        self.logger.error(f"读取扫描文件失败: {e}")

                # 8. 未找到目标设备
                self.logger.warning(f"未找到设备: {self.ble_device_name}")
                return False

            except Exception as e:
                self.logger.error(f"扫描设备时出错: {e}")
                return False
            finally:
                # 无论扫描成功/失败/异常，都确保清理残留进程和临时文件
                # 停止所有hcitool进程（防止扫描进程残留）
                self._run_command("sudo pkill -f hcitool", timeout=5)
                # 清理临时扫描文件（避免磁盘占用）
                try:
                    # 检查scan_file变量是否已定义且文件存在
                    if 'scan_file' in locals() and os.path.exists(scan_file):
                        os.remove(scan_file)
                except:
                    pass  # 清理失败不抛出异常，避免影响主流程

        # 调用通用重试函数，执行扫描操作（扫描失败时重试）
        return self._retry_operation(_scan_impl, "扫描设备")

    def connect_device(self, ble_mac):
        """执行BLE设备连接：使用hcitool lecc命令连接目标设备（需MAC地址）"""

        # 内部实现函数：封装连接逻辑
        def _connect_impl():
            # 先检查MAC地址是否有效（避免无效参数导致连接失败）
            if not ble_mac:
                self.logger.error("无效的MAC地址，跳过连接")
                return False

            try:
                # 1. 停止所有蓝牙相关进程（清理之前的连接残留）
                self.logger.info("停止所有蓝牙相关进程")
                self._run_command("sudo pkill -f hcitool", timeout=5)
                time.sleep(2)

                # 2. 重置适配器（恢复初始状态，解决连接残留问题）
                self.logger.info("重置蓝牙适配器状态")
                self._run_command(f"sudo hciconfig {self.hci_device} reset", timeout=10)
                time.sleep(2)

                # 3. 执行BLE连接命令：lecc（LE Connection Command）
                # --random：表示目标设备使用随机MAC地址（BLE设备常见地址类型）
                self.logger.info(f"使用hcitool连接设备 {ble_mac}")
                cmd = f"sudo timeout 30 hcitool -i {self.hci_device} lecc --random {ble_mac}"
                # 执行命令，超时时间设为35秒（比命令内部timeout多5秒，避免外层超时误判）
                stdout, stderr, return_code, timed_out = self._run_command(cmd, timeout=35)

                # 4. 记录连接命令的详细结果（便于调试）
                self.logger.debug(f"连接命令结果: timed_out={timed_out}, return_code={return_code}")
                self.logger.debug(f"STDOUT: {stdout}")
                self.logger.debug(f"STDERR: {stderr}")

                # 5. 判断连接是否成功：成功连接会返回"Connection handle"（连接句柄）
                if "Connection handle" in stdout:
                    self.logger.info("连接成功!")
                    return True
                # 处理常见连接失败情况
                elif "Could not create connection" in stderr:
                    self.logger.error(f"连接失败: {stderr.strip()}")
                elif "Connection timed out" in stderr:
                    self.logger.error(f"连接超时: {stderr.strip()}")
                else:
                    # 未知状态：通过返回码辅助判断
                    self.logger.warning(f"未知连接状态: return_code={return_code}")

                return False  # 连接失败返回False

            except Exception as e:
                self.logger.error(f"连接设备时出错: {e}")
                return False

        # 调用通用重试函数，执行连接操作（连接失败时重试）
        return self._retry_operation(_connect_impl, "连接设备")

    def run(self):
        """执行完整的BLE连接流程：获取锁->扫描设备->连接设备->释放锁"""
        self.logger.info(f"=== 开始连接BLE设备: {self.ble_device_name} ===")

        try:
            # 1. 获取操作锁：防止多进程并发操作蓝牙适配器
            self.lock_file = self.acquire_lock()
            if not self.lock_file:
                self.logger.warning("警告: 无法获取锁，继续执行（可能存在并发风险）")

            # 2. 扫描目标设备，获取MAC地址（无MAC地址无法连接）
            self.ble_mac = self.scan_device()
            if not self.ble_mac:
                self.logger.error("无法找到设备MAC地址，连接流程终止")
                return False

            # 3. 使用获取到的MAC地址连接设备
            self.connection_success = self.connect_device(self.ble_mac)
            if self.connection_success:
                self.logger.info("BLE设备连接成功，流程完成")
                return True
            else:
                self.logger.error("找到设备MAC地址，但连接失败")
                return False

        except Exception as e:
            # 捕获连接流程中的未预料异常
            self.logger.error(f"主连接流程发生异常: {e}")
            return False
        finally:
            # 4. 无论连接成功/失败/异常，都必须释放锁（避免锁残留）
            self.release_lock()
            self.logger.info("=== BLE连接流程完成 ===")

    def get_connection_result(self):
        """获取BLE连接最终结果：返回包含连接状态、设备MAC、适配器名的字典"""
        return {
            "success": self.connection_success,  # 布尔值：True=连接成功，False=失败
            "mac_address": self.ble_mac,        # 字符串：目标设备MAC地址（失败为None）
            "hci_device": self.hci_device       # 字符串：使用的蓝牙适配器名（如hci0）
        }


# 使用示例：当脚本直接运行时执行以下代码
if __name__ == "__main__":
    # 1. 创建BLE连接器实例：目标设备名为"0848 LE"，最大重试次数3次
    connector = BLEConnector(ble_device_name="0848 LE", max_retries=3)

    # 2. 执行完整的连接流程（获取锁->扫描->连接->释放锁）
    success = connector.run()

    # 3. 获取并打印连接结果
    result = connector.get_connection_result()
    print(f"连接结果: {result}")