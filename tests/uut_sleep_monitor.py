# ==================================================
# !/usr/bin/env python3
# @Author: simon.zhang
# @Date: 2025/12/29 13:53
# @FileName: uut_console_monitor.py  
# @Email: wangfu_zhang@ggec.com.cn
# ==================================================
#!/usr/bin/env python3
"""
UUT睡眠测试 - Python完整Telnet协商版
增加设备状态检测和更健壮的错误处理
"""

import socket
import time
import sys
from datetime import datetime

def handle_telnet_negotiation(sock):
    """处理Telnet协议协商"""
    print("   [协商] 开始处理Telnet选项协商...")
    sock.settimeout(2)
    negotiation_done = False
    bytes_processed = 0

    while not negotiation_done:
        try:
            data = sock.recv(1024)
            if not data:
                print("   [协商] 连接已关闭。")
                break

            i = 0
            while i < len(data):
                if data[i] == 0xFF and i + 2 < len(data):
                    cmd = data[i + 1]
                    opt = data[i + 2]
                    response = bytearray()
                    response.append(0xFF)

                    if cmd == 253:  # DO -> WONT
                        response.append(252)
                        response.append(opt)
                    elif cmd == 251:  # WILL -> DONT
                        response.append(254)
                        response.append(opt)

                    if response:
                        sock.send(response)
                    i += 3
                    bytes_processed += 3
                else:
                    if data[i] > 31 and data[i] < 127:
                        remaining_data = data[i:]
                        negotiation_done = True
                        break
                    else:
                        i += 1
                        bytes_processed += 1

            time.sleep(0.05)

        except socket.timeout:
            print(f"   [协商] 超时，无新指令。共处理 {bytes_processed} 字节协商数据。")
            negotiation_done = True
            remaining_data = b''
        except Exception as e:
            print(f"   [协商] 处理过程中发生错误: {e}")
            break

    print(f"   [协商] Telnet协商阶段结束。")
    sock.settimeout(10)
    return remaining_data if 'remaining_data' in locals() else b''

def safe_send(sock, data):
    """安全发送数据，处理连接断开的情况"""
    try:
        sock.send(data)
        return True
    except BrokenPipeError:
        print("   [错误] 连接已断开（Broken pipe）")
        return False
    except Exception as e:
        print(f"   [错误] 发送数据失败: {e}")
        return False

def safe_recv(sock, timeout=3):
    """安全接收数据"""
    sock.settimeout(timeout)
    data = b""
    try:
        while True:
            chunk = sock.recv(4096)
            if not chunk:
                break
            data += chunk
    except socket.timeout:
        pass
    except ConnectionResetError:
        print("   [错误] 连接被重置")
    except Exception as e:
        print(f"   [错误] 接收数据失败: {e}")
    return data

def check_device_status(sock):
    """
    检测设备状态
    返回: (is_connected, is_running)
    """
    print("   [状态检测] 发送回车检测设备响应...")
    
    # 发送回车检测设备
    if not safe_send(sock, b'\r\n'):
        return False, False
    
    time.sleep(3)
    
    # 尝试读取设备输出
    data = safe_recv(sock, 2)
    
    if data:
        try:
            text = data.decode('utf-8', errors='ignore')
            
            # 检查是否有任何响应
            if len(text.strip()) == 0:
                print("   ⚠ 设备无响应（有连接但无数据）")
                return True, False
            
            # 检查设备运行的关键指标
            running_indicators = [
                "SOC turned on",
                "Begin resume", 
                "# ",  # shell提示符
                "$ ",  # shell提示符
                "login:",
                "root@",
                "PM: suspend",
                "powCoord:",
                "Welcome to",
                "BusyBox"
            ]
            
            for indicator in running_indicators:
                if indicator in text:
                    print(f"   ✓ 发现设备运行指标: {indicator}")
                    return True, True
            
            # 如果有输出但不是运行指标
            print(f"   ⚠ 设备有响应但未发现运行指标，输出: {text[:100]}")
            return True, False
            
        except:
            print("   ⚠ 设备响应数据解码失败")
            return True, False
    else:
        print("   ⚠ 设备无响应")
        return True, False  # 连接正常但设备无响应

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
        
        # 3. 打开日志文件
        with open(log_filename, 'w', encoding='utf-8', errors='ignore') as f:
            f.write("=== UUT设备控制台日志 ===\n")
            f.write(f"时间: {datetime.now()}\n")
            f.write(f"目标: {HOST}:{PORT}\n")
            f.write("=" * 60 + "\n\n")

            # 4. 检测设备状态
            print(f"\n[3] 检测UUT设备状态...")
            connection_ok, device_running = check_device_status(sock)
            
            if not connection_ok:
                print("\n[错误] Terminal Server连接异常！")
                print("请检查：")
                print("1. Terminal Server是否正常运行")
                print("2. 网络连接是否正常")
                f.write("[错误] Terminal Server连接异常\n")
                return
            
            if not device_running:
                print("\n[!] 警告：UUT设备可能未运行或已关机！")
                print("[!] 建议检查：")
                print("    1. 设备是否开机")
                print("    2. 设备是否充电")
                print("    3. 设备是否正常启动")
                f.write("[警告] 设备可能未运行\n")
                
                # 询问是否继续（改进的输入处理）
                print("\n是否继续测试？")
                print("  y - 继续测试（即使设备可能关机）")
                print("  n - 中止测试")
                
                try:
                    response = input("请输入选择 (y/n): ").strip().lower()
                except (EOFError, KeyboardInterrupt):
                    print("\n输入中断，中止测试")
                    response = 'n'
                
                if response not in ['y', 'yes']:
                    print("测试中止")
                    f.write("[测试中止] 用户选择中止\n")
                    return
                else:
                    print("继续测试...")
                    f.write("[注意] 设备状态检测未通过，但继续测试\n")
            
            # 5. 等待设备完全就绪
            print("\n[4] 等待设备完全就绪...")
            safe_send(sock, b'\r\n')
            time.sleep(5)
            
            # 6. 捕获初始输出
            print(f"[5] 捕获初始输出...")
            initial_output = safe_recv(sock)
            
            if early_data:
                initial_output = early_data + initial_output
            
            if initial_output:
                try:
                    text = initial_output.decode('utf-8', errors='ignore')
                    f.write("[初始连接输出]\n")
                    f.write(text)
                    if not text.endswith('\n'):
                        f.write('\n')
                    f.write("-" * 50 + "\n")
                    print(f"   捕获到初始输出，长度: {len(text)} 字符")
                except:
                    f.write(f"[初始数据 (原始字节)]\n{initial_output.hex()}\n")
            else:
                print("   警告：未捕获到初始输出。")

            # 7. 发送睡眠命令并捕获输出
            commands = [
                ("echo DeviceSuspendRequested > /tmp/sonospowercoordinator_USR1_cmd_OVERRIDE", 2),
                ("killall -SIGUSR1 sonospowercoordinator", 8)
            ]

            for idx, (cmd, wait_time) in enumerate(commands, 1):
                print(f"\n[6.{idx}] 发送命令: {cmd}")
                f.write(f"[命令{idx}] {cmd}\n")

                # 发送命令
                cmd_bytes = (cmd + '\n').encode('utf-8')
                if not safe_send(sock, cmd_bytes):
                    print("   [错误] 发送命令失败，连接可能已断开")
                    f.write("(发送命令失败，连接断开)\n")
                    break
                
                print(f"   等待 {wait_time} 秒捕获输出...")
                time.sleep(wait_time)

                cmd_output = safe_recv(sock, 2)
                
                if cmd_output:
                    try:
                        text = cmd_output.decode('utf-8', errors='ignore')
                        f.write(text)
                        if not text.endswith('\n'):
                            f.write('\n')
                        print(f"   捕获输出: {len(text)} 字符")
                        
                        # 检查关键日志
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
                f.flush()

            # 8. 进入静默监控模式
            print(f"\n[7] 进入静默监控模式 (300秒)...")
            print("   请开始执行WiFi/BLE唤醒测试。")
            print("   按 Ctrl+C 停止监控。")
            f.write("\n" + "=" * 60 + "\n")
            f.write("[开始静默监控 - 无任何数据发送]\n")
            f.write("=" * 60 + "\n\n")

            sock.setblocking(False)
            start_monitor = time.time()
            monitor_duration = 300

            try:
                while time.time() - start_monitor < monitor_duration:
                    try:
                        data = sock.recv(8192)
                        if data:
                            try:
                                text = data.decode('utf-8', errors='ignore')
                                f.write(text)
                                f.flush()
                                
                                if "WIFI_WAKEUP" in text:
                                    alert = f"\n[!!!] 检测到 WiFi 唤醒！\n"
                                    print(alert)
                                    f.write(alert)
                            except:
                                pass
                    except BlockingIOError:
                        time.sleep(0.5)
                    except (ConnectionResetError, BrokenPipeError):
                        print("   [错误] 监控期间连接断开")
                        break
                        
                    elapsed = int(time.time() - start_monitor)
                    if elapsed % 60 == 0 and elapsed > 0:
                        print(f"   [状态] 已监控 {elapsed} 秒，等待唤醒...")
                        
            except KeyboardInterrupt:
                print("\n[监控被用户中断]")

            # 监控结束前发送退出命令（尝试优雅退出shell）
            print("\n[8] 尝试退出shell...")
            try:
                sock.setblocking(True)
                sock.settimeout(2)
                safe_send(sock, b'exit\n')
                time.sleep(1)
                final_output = safe_recv(sock, 1)
                if final_output:
                    f.write(final_output.decode('utf-8', errors='ignore'))
            except:
                pass

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
