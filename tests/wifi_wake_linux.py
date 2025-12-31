# ==================================================
# !/usr/bin/env python
# @Author: simon.zhang
# @Date: 2025/8/11 10:33
# @FileName: wifi_wolsentor.py
# @Email: wangfu_zhang@ggec.com.cn
# 功能：实现Wake-on-LAN（网络唤醒）功能，通过发送魔术包唤醒支持WOL的设备
# ==================================================

import socket  # 用于创建网络套接字，实现UDP广播通信 can
import time  # 用于控制发送间隔，避免请求过于密集
import logging  # 用于日志记录，方便调试和查看执行状态


class WolSender:
    """WOL（网络唤醒）工具类：封装魔术包生成、发送及批量唤醒逻辑"""

    def __init__(self, mac_address, broadcast_ip='255.255.255.255', port=9):
        """
        类初始化方法：初始化唤醒目标的核心参数，并配置日志

        参数说明：
        - mac_address: 目标设备的MAC地址（必须，格式如 '80:4a:f2:b0:08:48'）
          （MAC地址是设备唯一标识，魔术包需基于MAC地址生成）
        - broadcast_ip: 广播IP地址（可选，默认 '255.255.255.255'）
          （广播IP用于向局域网内所有设备发送，确保目标设备能接收）
        - port: 唤醒端口（可选，默认 9，9是WOL标准端口）
        """
        # 保存实例参数，供后续方法调用
        self.mac_address = mac_address  # 目标设备MAC地址
        self.broadcast_ip = broadcast_ip  # 局域网广播IP
        self.port = port  # WOL通信端口
        # 初始化日志记录器（调用下方setup_logger方法）
        self.logger = self.setup_logger()

    @staticmethod
    def setup_logger():
        """
        静态方法：配置日志记录器（独立于实例，可直接通过类调用）
        功能：定义日志格式、输出位置（控制台），方便查看执行状态和错误信息
        """
        # 1. 创建日志器实例，命名为'WolSender'（区分其他模块日志）
        logger = logging.getLogger('WolSender')
        # 2. 设置日志级别为INFO（只记录INFO及以上级别日志：INFO、WARNING、ERROR）
        logger.setLevel(logging.INFO)
        # 3. 定义日志格式：[时间] - [日志级别] -[日志器实例名】 [日志内容]
        formatter = logging.Formatter('%(asctime)s - %(levelname)s -%(name)s- %(message)s')
        # 4. 创建控制台处理器（日志输出到控制台）
        ch = logging.StreamHandler()
        # 5. 为控制台处理器绑定日志格式
        ch.setFormatter(formatter)
        # 6. 为日志器添加控制台处理器（日志最终通过处理器输出）
        logger.addHandler(ch)

        # 返回配置好的日志器，供实例使用
        return logger

    def send_magic_packet(self):
        """
        核心方法：生成并发送WOL魔术包（单次唤醒请求）
        魔术包格式：6个0xFF（唤醒标识） + 16次重复的目标设备MAC地址（定位设备）
        返回值：True（发送成功）/ False（发送失败）
        """
        # 初始化套接字为None，避免finally块中变量未定义的风险
        sock = None
        try:
            # -------------------------- 1. 处理MAC地址：转换为字节格式 --------------------------
            # 移除MAC地址中的冒号（如 '80:4a:f2:b0:08:48' → '804af2b00848'）
            # 再将16进制字符串转换为字节序列（用于生成魔术包）
            mac_bytes = bytes.fromhex(self.mac_address.replace(':', ''))

            # -------------------------- 2. 生成WOL魔术包 --------------------------
            # 魔术包标准格式：6个0xFF字节 + 16次重复的MAC字节（确保设备能识别）
            magic_packet = b'\xff' * 6 + mac_bytes * 16

            # -------------------------- 3. 创建UDP广播套接字 --------------------------
            # socket.AF_INET：使用IPv4协议
            # socket.SOCK_DGRAM：使用UDP协议（无连接，适合广播，效率高）
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            # 设置套接字选项：允许发送广播包（UDP默认不允许广播，需手动开启）
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)

            # -------------------------- 4. 发送魔术包 --------------------------
            # 发送到指定的广播IP和端口（元组格式：(IP, 端口)）
            sock.sendto(magic_packet, (self.broadcast_ip, self.port))
            # 记录成功日志
            self.logger.info(f"魔术包已发送到 {self.mac_address} "
                             f"(广播地址: {self.broadcast_ip}, 端口: {self.port})")

            # 发送成功，返回True
            return True

        # -------------------------- 5. 异常捕获与处理 --------------------------
        except (socket.error, ValueError) as e:
            # 区分错误类型：ValueError→MAC格式错误（如冒号数量不对、非16进制字符）
            #              socket.error→网络错误（如端口被占用、无网络连接）
            error_type = "MAC地址格式错误" if isinstance(e, ValueError) else "网络发送失败"
            # 记录错误日志（包含具体错误信息）
            self.logger.error(f"{error_type}: {e}")
            # 发送失败，返回False
            return False

        # -------------------------- 6. 资源释放：确保套接字关闭 --------------------------
        finally:
            # 判断套接字是否已创建（避免未创建时调用close()报错）
            if 'sock' in locals():
                sock.close()

    def send_wakeup_packets(self, count=5, interval=1):
        """
        批量唤醒方法：多次发送魔术包（提高唤醒成功率，应对网络丢包）
        参数说明：
        - count: 单次唤醒序列的发送次数（可选，默认5次）
        - interval: 每次发送的时间间隔（可选，默认1秒）
        返回值：True（至少1次发送成功）/ False（全部发送失败）
        """
        # 记录批量唤醒开始日志
        self.logger.info(f"开始向设备 {self.mac_address} 发送唤醒包序列...")

        # 初始化成功计数器（统计成功发送的魔术包数量）
        success_count = 0
        # 循环发送指定次数的魔术包
        for i in range(count):
            # 调用单次发送方法，成功则计数器+1
            if self.send_magic_packet():
                success_count += 1
            # 非最后一次发送时，等待指定间隔（避免短时间内请求过于密集）
            if i < count - 1:
                time.sleep(interval)

        # 记录批量唤醒结束日志（包含成功/总次数）
        self.logger.info(f"唤醒包序列发送完成. 成功发送: {success_count}/{count}个包")
        # 只要有1次成功就返回True（表示唤醒请求已发出）
        return success_count > 0