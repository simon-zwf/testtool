import socket
import time
import logging


class WolSender:
    def __init__(self, mac_address, broadcast_ip='255.255.255.255', port=9):
        self.mac_address = mac_address
        self.broadcast_ip = broadcast_ip
        self.port = port
        self.logger = self.setup_logger()

    def setup_logger(self):
        logger = logging.getLogger('WolSender')
        logger.setLevel(logging.INFO)
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')

        # 控制台处理器
        ch = logging.StreamHandler()
        ch.setFormatter(formatter)
        logger.addHandler(ch)

        # 文件处理器
        fh = logging.FileHandler('wol_sender.log')
        fh.setFormatter(formatter)
        logger.addHandler(fh)

        return logger

    def send_magic_packet(self, count=3, interval=1):
        """发送魔术包唤醒设备"""
        # 转换MAC地址格式
        mac_bytes = bytes.fromhex(self.mac_address.replace(':', ''))

        # 创建魔术包 (6×0xFF + 16×MAC地址)
        magic_packet = b'\xff' * 6 + mac_bytes * 16

        # 创建UDP套接字
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)

        try:
            for i in range(count):
                # 发送魔术包
                sock.sendto(magic_packet, (self.broadcast_ip, self.port))
                self.logger.info(f"已发送魔术包 #{i + 1} 到 {self.mac_address} (广播地址: {self.broadcast_ip})")

                # 如果不是最后一次发送，等待间隔
                if i < count - 1:
                    time.sleep(interval)
            return True
        except socket.error as e:
            self.logger.error(f"发送失败: {e}")
            return False
        finally:
            sock.close()

    def find_broadcast_address(self):
        """尝试获取正确的广播地址"""
        try:
            # 获取默认接口的广播地址
            import netifaces
            gateways = netifaces.gateways()
            default_interface = gateways['default'][netifaces.AF_INET][1]

            addrs = netifaces.ifaddresses(default_interface)
            broadcast = addrs[netifaces.AF_INET][0].get('broadcast')
            return broadcast or '255.255.255.255'
        except:
            return '255.255.255.255'

    def find_name(self, name, address, book):
        """
         Batch wake-up method: Send magic packets multiple times (improve success rate against network packet loss)
        :param name:Number of magic packets to send in single wake-up sequence
        :param address:
        :param book:
        :return:
        """
if __name__ == "__main__":
    # 使用示例 - 替换为您的MAC地址
    sender = WolSender(mac_address='80:4a:f2:b0:08:48')

    # 自动获取广播地址（如果可能）
    broadcast_ip = sender.find_broadcast_address()
    sender.broadcast_ip = broadcast_ip

    # 发送魔术包
    if sender.send_magic_packet(count=5, interval=20):
        print("唤醒包发送成功！")
    else:
        print("唤醒包发送失败。")

# ==================================================
# !/usr/bin/env python
# @Author: simon.zhang
# @Date: 2025/8/17 10:33
# @FileName: wifi_wolsender.py
# @Email: wangfu_zhang@ggec.com.cn
# Function: Implement Wake-on-LAN (WOL) functionality to wake up WOL-supported devices by sending magic packets
# ==================================================

import socket
import time
import logging
from datetime import datetime
import sys
import os

# Add path for importing LPS_modules
currdir = os.getcwd()
projdir = currdir.split("/Python")
lpsmoduledir = projdir[0] + "/Python/Test_Cases/Low_Power_Sequence" if len(projdir) > 1 else currdir
sys.path.append(lpsmoduledir)

# Import logging function from LPS_modules
try:
    from LPS_modules import thread_terminal_logging
except ImportError:
    # Fallback function if import fails (for standalone usage)
    def thread_terminal_logging(uut_name, level, message):
        print(f"[{uut_name}] {level.upper()}: {message}")


#
# class TerminalLogHandler(logging.Handler):
#     """Custom logging handler that outputs to terminal log via thread_terminal_logging"""
#     def __init__(self, uut_name="UUT"):
#         super().__init__()
#         self.uut_name = uut_name
#
#     def emit(self, record):
#         try:
#             msg = self.format(record)
#             level = record.levelname.lower()
#             # Map logging levels to terminal log levels
#             if level == 'debug':
#                 level = 'debug'
#             elif level == 'info':
#                 level = 'info'
#             elif level == 'warning':
#                 level = 'warning'
#             elif level in ('error', 'critical'):
#                 level = 'error'
#             else:
#                 level = 'info'
#             # Add debug logging for emit calls (but avoid recursion by using print for debug)
#             if 'DEBUG' in msg or '[DEBUG]' in msg:
#                 print(f"[TerminalLogHandler] Emitting log: {level} - {msg[:100]}...")
#             thread_terminal_logging(self.uut_name, level, msg)
#         except Exception as e:
#             print(f"[TerminalLogHandler] Exception in emit: {type(e).__name__}: {e}")
#             self.handleError(record)


class WolSender:
    """WOL (Wake-on-LAN) Tool Class: Encapsulates logic for magic packet generation and sending"""

    def __init__(self, mac_address, broadcast_ip='255.255.255.255', port=9, uut_name="UUT"):
        """
        Class Initialization Method: Initialize core parameters for the target device to wake up and configure logging
        Args:
            mac_address: MAC address of the target device (required, format e.g. '80:4a:f2:b0:08:48')
            broadcast_ip: Broadcast IP address (optional, default '255.255.255.255')
            port: Wake-up port (optional, default 9; 9 is the standard WOL port)
            uut_name: UUT name for terminal logging (optional, default "UUT")
        """
        # Validate MAC address is not None or empty
        if not mac_address or mac_address is None or (isinstance(mac_address, str) and mac_address.strip() == ''):
            raise ValueError(f"MAC address cannot be None or empty. Received: {mac_address}")

        self.mac_address = mac_address  # Store target device's MAC address
        self.broadcast_ip = broadcast_ip  # Store LAN broadcast IP address
        self.port = port  # Store target UDP port for WOL
        self.uut_name = uut_name  # Store UUT name for terminal logging
        # self.logger = self.setup_logger()  # Initialize logger for operation tracking

    # def setup_logger(self):
    #     """
    #     Instance Method: Configure logger with terminal log handler
    #     """
    #     logger = logging.getLogger(f'WolSender_{id(self)}')  # Create unique logger instance
    #     logger.setLevel(logging.DEBUG)  # Set base log level to DEBUG (captures all levels)
    #
    #     # Clear existing handlers to avoid duplicate logs in repeated calls
    #     if logger.hasHandlers():
    #         for handler in logger.handlers[:]:
    #             logger.removeHandler(handler)
    #             handler.close()
    #
    #     # Define log format: timestamp + log level + logger name + message
    #     formatter = logging.Formatter(
    #         '%(asctime)s - %(levelname)s - %(name)s - %(message)s',
    #         datefmt='%Y-%m-%d %H:%M:%S'
    #     )
    #
    #     # Configure console handler (outputs INFO and above to console)
    #     ch = logging.StreamHandler()
    #     ch.setLevel(logging.INFO)
    #     ch.setFormatter(formatter)
    #     logger.addHandler(ch)
    #
    #     # Configure terminal log handler (outputs all levels to terminal log)
    #     terminal_handler = TerminalLogHandler(uut_name=self.uut_name)
    #     terminal_handler.setLevel(logging.DEBUG)
    #     terminal_handler.setFormatter(formatter)
    #     logger.addHandler(terminal_handler)
    #
    #     # Configure file handler (outputs DEBUG and above to daily log file)
    #     log_file = f"wol_sender_{datetime.now().strftime('%Y%m%d')}.log"  # Log file named by date
    #     fh = logging.FileHandler(log_file)
    #     fh.setLevel(logging.DEBUG)
    #     fh.setFormatter(formatter)
    #     logger.addHandler(fh)
    #
    #     return logger

    def send_magic_packet(self, count=3, interval=1):
        """
        Core Method: Generate and send WOL magic packets multiple times
        Args:
            count: Number of times to send the magic packet (default 3)
            interval: Time interval between sends in seconds (default 1)
        Return Value: True (at least one send successful) / False (all sends failed)
        """
        self.logger.debug(
            f"[DEBUG] send_magic_packet ENTRY: count={count}, interval={interval}, mac={self.mac_address}")
        self.logger.info(f"===Starting to send {count} wake-up packets to device {self.mac_address}===")

        success_count = 0  # Track number of successful packet sends
        self.logger.debug(f"[DEBUG] send_magic_packet: Initialized success_count={success_count}")

        for i in range(count):  # Loop to send packets 'count' times
            self.logger.debug(f"[DEBUG] send_magic_packet: Starting loop iteration {i + 1}/{count}")
            try:
                # Remove colons from MAC address and convert to byte array (required for magic packet)
                self.logger.debug(f"[DEBUG] send_magic_packet: Converting MAC address to bytes")
                mac_bytes = bytes.fromhex(self.mac_address.replace(':', ''))
                # Construct standard WOL magic packet: 6 bytes of 0xFF + 16 repetitions of MAC address bytes
                magic_packet = b'\xff' * 6 + mac_bytes * 16
                self.logger.debug(
                    f"[DEBUG] send_magic_packet: Magic packet constructed, length={len(magic_packet)} bytes")

                # Create UDP socket (AF_INET = IPv4, SOCK_DGRAM = UDP protocol)
                self.logger.debug(f"[DEBUG] send_magic_packet: Creating UDP socket")
                sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                # Enable broadcast mode for the socket (required to send to broadcast IP)
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
                self.logger.debug(f"[DEBUG] send_magic_packet: Socket created and broadcast enabled")

                # Send magic packet to specified broadcast IP and port (tuple format required by sendto)
                self.logger.debug(
                    f"[DEBUG] send_magic_packet: About to call sendto() to {self.broadcast_ip}:{self.port}")
                bytes_sent = sock.sendto(magic_packet, (self.broadcast_ip, self.port))
                self.logger.debug(f"[DEBUG] send_magic_packet: sendto() returned, bytes_sent={bytes_sent}")
                sock.close()  # Close socket immediately after sending to free resources
                self.logger.debug(f"[DEBUG] send_magic_packet: Socket closed successfully")

                success_count += 1  # Increment success counter
                self.logger.info(f"Magic packet #{i + 1} sent to {self.mac_address} "
                                 f"(Broadcast Address: {self.broadcast_ip}, Port: {self.port})")
                self.logger.debug(f"[DEBUG] send_magic_packet: success_count incremented to {success_count}")

            # Handle specific exceptions: MAC format errors (ValueError) or network issues (socket.error)
            except (socket.error, ValueError) as e:
                error_type = "MAC Address Format Error" if isinstance(e, ValueError) else "Network Send Failed"
                self.logger.error(f"{error_type} on attempt #{i + 1}: {e}")
                self.logger.debug(
                    f"[DEBUG] send_magic_packet: Exception caught in iteration {i + 1}, success_count={success_count}")
            except Exception as e:
                self.logger.error(f"Unexpected exception on attempt #{i + 1}: {type(e).__name__}: {e}")
                self.logger.debug(
                    f"[DEBUG] send_magic_packet: Unexpected exception in iteration {i + 1}, success_count={success_count}")

            # Add delay between packets (skip after last packet in the loop)
            if i < count - 1:
                self.logger.debug(f"[DEBUG] send_magic_packet: Sleeping {interval}s before next packet")
                time.sleep(interval)
                self.logger.debug(f"[DEBUG] send_magic_packet: Sleep completed, continuing loop")
            else:
                self.logger.debug(f"[DEBUG] send_magic_packet: Last iteration, skipping sleep")

        # Log summary of all send attempts
        self.logger.info(f"===Packet sending completed. Successfully sent: {success_count}/{count} packets===")
        self.logger.debug(f"[DEBUG] send_magic_packet: Loop completed, success_count={success_count}, count={count}")

        # Return True if at least one packet was sent successfully
        return_value = success_count > 0
        self.logger.debug(
            f"[DEBUG] send_magic_packet: Calculating return value: success_count > 0 = {success_count} > 0 = {return_value}")
        self.logger.debug(f"[DEBUG] send_magic_packet: About to RETURN {return_value}")
        return return_value