# ==================================================
# !/usr/bin/env python
# @Author: simon.zhang
# @Date: 2025/12/29 13:53
# @FileName: uut_console_monitor.py
# @Email: wangfu_zhang@ggec.com.cn
# ==================================================
#!/usr/bin/env python3
"""
UUT睡眠测试 - Python终极解决方案 (完整Telnet协商)
确保与Perle IOLAN Terminal Server的完全兼容，捕获完整日志。
"""

import socket
import time
from datetime import datetime

def handle_telnet_negotiation(sock):
    """
    核心函数：处理Telnet协议协商。
    读取并逐一响应服务器发送的所有选项请求，直到协商完成。
    """
    print("   [协商] 开始处理Telnet选项协商...")
    sock.settimeout(2)  # 为协商阶段设置较短超时
    negotiation_done = False
    bytes_processed = 0

    while not negotiation_done:
        try:
            # 读取数据，期待收到协商指令或真实数据
            data = sock.recv(1024)
            if not data:
                print("   [协商] 连接已关闭。")
                break

            # 分析接收到的字节
            i = 0
            while i < len(data):
                # Telnet 指令以 0xFF (IAC) 开头
                if data[i] == 0xFF and i + 2 < len(data):
                    cmd = data[i + 1]
                    opt = data[i + 2]
                    # 打印收到的指令（用于调试）
                    cmd_map = {253: 'DO', 254: 'DONT', 251: 'WILL', 252: 'WONT'}
                    opt_map = {24: 'TTYPE(24)', 32: 'NAWS(32)', 35: 'LINEMODE(35)', 39: 'NEWENV(39)'}
                    cmd_str = cmd_map.get(cmd, str(cmd))
                    opt_str = opt_map.get(opt, str(opt))
                    # print(f"   [协商] 收到: IAC {cmd_str} {opt_str}") # 调试时可打开

                    # --- 关键：构造并发送标准回应 ---
                    response = bytearray()
                    response.append(0xFF)  # IAC

                    if cmd == 253:  # DO -> 回应 WONT
                        response.append(252)  # WONT
                        response.append(opt)
                    elif cmd == 251:  # WILL -> 回应 DONT
                        response.append(254)  # DONT
                        response.append(opt)
                    # 其他情况（如 IAC SB ... IAC SE）暂时简单跳过
                    # 对于Terminal Server，通常只需回应 DO/WILL

                    if response:
                        sock.send(response)
                        # print(f"   [协商] 发送回应: {response.hex()}") # 调试时可打开

                    i += 3  # 跳过这个完整的 IAC 指令 (3字节)
                    bytes_processed += 3
                else:
                    # 收到的不是 IAC 指令，可能是普通数据或子协商开始
                    # 如果遇到普通可打印字符，可能意味着协商结束了
                    if data[i] > 31 and data[i] < 127:
                        # 收到了可打印字符（如提示符），协商可能已完成
                        # print(f"   [协商] 收到首个数据字节: {chr(data[i])} (0x{data[i]:02x})")
                        # 将这部分数据（可能包含提示符）存起来，返回给主函数
                        remaining_data = data[i:]
                        negotiation_done = True
                        break
                    else:
                        # 其他控制字符或不可打印字符，继续处理
                        i += 1
                        bytes_processed += 1

            # 一个小延迟，避免过于密集的收发
            time.sleep(0.05)

        except socket.timeout:
            # 2秒内没有收到新的协商指令，假设协商已完成
            print(f"   [协商] 超时，无新指令。共处理 {bytes_processed} 字节协商数据。")
            negotiation_done = True
            remaining_data = b''
        except Exception as e:
            print(f"   [协商] 处理过程中发生错误: {e}")
            break

    print(f"   [协商] Telnet协商阶段结束。")
    # 恢复一个较长的超时，用于后续数据传输
    sock.settimeout(10)
    # 返回协商后可能已经收到的第一批真实数据
    return remaining_data if 'remaining_data' in locals() else b''

def main():
    HOST = "200.1.1.4"
    PORT = 10006
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_filename = f"UUT_PYTHON_FINAL_{timestamp}.log"

    print("=" * 60)
    print("UUT睡眠测试 - Python完整Telnet协商版")
    print(f"时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"日志: {log_filename}")
    print("=" * 60)

    sock = None

    try:
        # 1. 建立TCP连接
        print(f"\n[1] 连接到 {HOST}:{PORT} ...")
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(15)
        sock.connect((HOST, PORT))
        print("   ✓ TCP连接成功")

        # 2. 关键步骤：处理Telnet协商
        print(f"[2] 与Terminal Server进行Telnet握手...")
        early_data = handle_telnet_negotiation(sock)
        # 协商后，立即发送一个换行，激活动态提示符
        sock.send(b'\n')
        time.sleep(1.5)  # 等待设备响应并输出可能的登录信息

        # 3. 打开日志文件
        with open(log_filename, 'w', encoding='utf-8', errors='ignore') as f:
            f.write("=== UUT设备控制台日志  ===\n")
            f.write(f"时间: {datetime.now()}\n")
            f.write(f"目标: {HOST}:{PORT}\n")
            f.write("=" * 60 + "\n\n")

            # 4. 捕获并记录初始输出（登录提示符等）
            print(f"[3] 捕获初始输出...")
            initial_output = b""  # 回车，如果设备已经sleep唤醒设备，如果UUT已经是正常运行状态，就相当输入一个回车，
            time.sleep(10)  # 等待设备启动完成
            sock.settimeout(3)
            try:
                while True:
                    chunk = sock.recv(4096)
                    if chunk:
                        initial_output += chunk
                    else:
                        break
            except socket.timeout:
                pass

            all_output = early_data + initial_output
            if all_output:
                try:
                    text = all_output.decode('utf-8', errors='ignore')
                    f.write("[初始连接输出]\n")
                    f.write(text)
                    if not text.endswith('\n'):
                        f.write('\n')
                    f.write("-" * 50 + "\n")
                    print(f"   捕获到初始输出，长度: {len(text)} 字符")
                    if '#' in text:
                        print("   ✓ 发现命令提示符 (#)")
                except:
                    f.write(f"[初始数据 (原始字节)]\n{all_output.hex()}\n")
            else:
                print("   警告：未捕获到初始输出。")

            # 5. 发送睡眠命令并捕获输出 (关键！)
            commands = [
                "echo DeviceSuspendRequested > /tmp/sonospowercoordinator_USR1_cmd_OVERRIDE",
                "killall -SIGUSR1 sonospowercoordinator"
            ]

            for idx, cmd in enumerate(commands, 1):
                print(f"\n[4.{idx}] 发送命令: {cmd}")
                f.write(f"[命令{idx}] {cmd}\n")

                # 发送命令
                sock.send((cmd + '\n').encode('utf-8'))
                # **关键等待**：给予设备充分的时间执行命令并产生输出
                wait_time = 2 if idx == 1 else 8  # 第二条命令需要更长时间
                print(f"   等待 {wait_time} 秒捕获输出...")
                time.sleep(wait_time)

                # 主动、密集地读取所有可用的输出
                cmd_output = b""
                sock.settimeout(2)
                try:
                    # 尝试多次读取，直到没有新数据
                    for _ in range(5):
                        try:
                            chunk = sock.recv(8192)
                            if chunk:
                                cmd_output += chunk
                            else:
                                time.sleep(0.2)
                        except socket.timeout:
                            break
                        except BlockingIOError:
                            break
                except Exception as e:
                    print(f"   读取命令输出时发生错误: {e}")

                if cmd_output:
                    try:
                        text = cmd_output.decode('utf-8', errors='ignore')
                        f.write(text)
                        if not text.endswith('\n'):
                            f.write('\n')
                        print(f"   捕获输出: {len(text)} 字符")
                        # 实时检查关键日志
                        if "powCoord:" in text:
                            print("   ✓ 发现电源管理日志")
                        if idx == 2 and "[AOCPU RTC]: alarm val=" in text:
                            print("   ✓ 发现RTC定时器设置")
                        if idx == 2 and "SOC turned off" in text:
                            print("   ✓ 发现设备关机确认")
                    except:
                        f.write(f"[命令{idx}输出 (原始字节)]\n{cmd_output.hex()}\n")
                else:
                    print("   警告：未捕获到命令输出。")
                    f.write("(无输出)\n")
                f.flush()  # 确保写入文件

            # 6. 进入静默监控模式
            print(f"\n[5] 进入静默监控模式 (300秒)...")
            print("   请开始执行WiFi/BLE唤醒测试。")
            print("   按 Ctrl+C 停止监控。")
            f.write("\n" + "=" * 60 + "\n")
            f.write("[开始静默监控 - 无任何数据发送]\n")
            f.write("=" * 60 + "\n\n")

            sock.setblocking(False)  # 设置为非阻塞，用于静默监控
            start_monitor = time.time()
            monitor_duration = 300
            last_activity = start_monitor

            try:
                while time.time() - start_monitor < monitor_duration:
                    try:
                        data = sock.recv(8192)
                        if data:
                            last_activity = time.time()
                            text = data.decode('utf-8', errors='ignore')
                            f.write(text)
                            f.flush()
                            # 可选：在控制台显示唤醒信号
                            if "WIFI_WAKEUP fired" in text:
                                alert = f"\n[!!!] 检测到 WiFi 唤醒！\n"
                                print(alert)
                                f.write(alert)
                            elif "BLE_WAKEUP fired" in text:
                                alert = f"\n[!!!] 检测到 BLE 唤醒！\n"
                                print(alert)
                                f.write(alert)
                    except BlockingIOError:
                        # 没有数据是正常情况
                        time.sleep(0.5)
                    except KeyboardInterrupt:
                        print("\n[用户中断监控]")
                        break
                    # 每分钟打印一次状态
                    if time.time() - last_activity > 60:
                        elapsed = int(time.time() - start_monitor)
                        print(f"   [状态] 已监控 {elapsed} 秒，等待唤醒...")
                        last_activity = time.time()
            except KeyboardInterrupt:
                print("\n[监控被用户中断]")

            # 保存日志结尾
            f.write("\n" + "=" * 60 + "\n")
            f.write(f"监控结束: {datetime.now()}\n")
            f.write(f"总监控时长: {int(time.time() - start_monitor)} 秒\n")
            f.write("=" * 60 + "\n")

        print(f"\n[完成] 所有日志已保存至: {log_filename}")

    except socket.timeout:
        print(f"\n[错误] 连接或读取超时")
    except ConnectionRefusedError:
        print(f"\n[错误] 连接被拒绝")
    except Exception as e:
        print(f"\n[错误] 发生异常: {e}")
        import traceback
        traceback.print_exc()
    finally:
        if sock:
            sock.close()
            print("连接已关闭")

if __name__ == "__main__":
    main()




