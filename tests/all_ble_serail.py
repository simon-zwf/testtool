import os
import re
import time
import subprocess
import sys
import serial
from datetime import datetime

# ===================== 配置参数 =====================
CONFIG = {
    # BLE配置
    "BLE_DEVICE_NAME": "S44 4476 LE",  # BLE设备名称
    "HCI_DEVICE": "hci1",  # 蓝牙适配器

    # 串口配置
    "SERIAL_PORT": "/dev/ttyUSB0",  # 串口设备路径
    "SERIAL_BAUDRATE": 912600,  # 波特率
    "SERIAL_TIMEOUT": 1,  # 超时时间(秒)

    # 设备控制命令
    "SLEEP_COMMANDS": [
        "echo DeviceSuspendRequested > /tmp/sonospowercoordinator_USR1_cmd_OVERRIDE\r\n",
        "killall -SIGUSR1 sonospowercoordinator\r\n"
    ],

    # 日志标志
    "SLEEP_FLAG": 'a113x2 SOC turned off',  # 睡眠标志
    "WAKEUP_FLAG": 'BT_WAKEUP fired',  # 唤醒标志

    # 重试次数配置
    "MAX_RETRIES": {
        "ADAPTER_READY": 3,  # 适配器就绪检查重试次数
        "LOCK_ACQUIRE": 3,  # 锁获取重试次数
        "SCAN_DEVICE": 3,  # 设备扫描重试次数
        "CONNECT_DEVICE": 3,  # 连接设备重试次数
        "SLEEP_SEQUENCE": 3,  # 睡眠序列重试次数
        "WAKEUP_VERIFY": 3  # 唤醒验证重试次数
    },

    # 循环测试配置
    "TEST_CYCLES": 5,  # 总测试循环次数
    "CYCLE_DELAY": 10,  # 循环之间延迟(秒)
    "LOG_FILE": "ble_wakeup_test.log"  # 日志文件名
}


# ===================== 日志系统 =====================
class Logger:
    def __init__(self, filename):
        self.terminal = sys.stdout
        self.log = open(filename, "a")

    def write(self, message):
        self.terminal.write(message)
        self.log.write(message)
        self.log.flush()

    def flush(self):
        pass


# ===================== 工具函数 =====================
def run_command(cmd, capture_output=True, timeout=None):
    """执行系统命令并返回输出（带错误处理）"""
    try:
        result = subprocess.run(
            cmd,
            shell=True,
            stdout=subprocess.PIPE if capture_output else None,
            stderr=subprocess.PIPE if capture_output else None,
            text=True,
            timeout=timeout
        )
        if capture_output:
            return result.stdout.strip(), result.stderr.strip()
        return None, None
    except subprocess.TimeoutExpired:
        print(f"[ERROR] 命令超时: {cmd}")
        return "命令执行超时", "超时错误"
    except Exception as e:
        print(f"[ERROR] 命令执行异常: {e}")
        return f"异常: {e}", "执行错误"
    finally:
        time.sleep(0.5)  # 命令执行后短暂延迟


def reset_adapter(hci_device, max_retries=3):
    """重置蓝牙适配器（带重试机制）"""
    for attempt in range(1, max_retries + 1):
        try:
            print(f"[ADAPTER] 重置蓝牙适配器 {hci_device} (尝试 {attempt}/{max_retries})")

            # 重置HCI设备
            run_command(f"sudo hciconfig {hci_device} reset", capture_output=False)

            # 发送LE重置命令
            run_command(f"sudo hcitool -i {hci_device} cmd 0x08 0x000E", capture_output=False)
            time.sleep(1)

            # 确保设备重新上线
            run_command(f"sudo hciconfig {hci_device} up", capture_output=False)

            # 检查重置是否成功
            stdout, _ = run_command(f"hciconfig {hci_device}")
            if "UP RUNNING" in stdout:
                print(f"[ADAPTER] 适配器 {hci_device} 重置成功")
                return True
            else:
                print(f"[ADAPTER] 适配器 {hci_device} 重置后仍未启用")

        except Exception as e:
            print(f"[ERROR] 重置适配器时出错: {e}")

        time.sleep(2)

    print(f"[ERROR] 无法重置适配器 {hci_device} 经过 {max_retries} 次尝试")
    return False


def ensure_adapter_ready(hci_device, max_retries=3):
    """确保适配器可用（带重试机制）"""
    for attempt in range(1, max_retries + 1):
        try:
            print(f"[ADAPTER] 检查适配器 {hci_device} 状态 (尝试 {attempt}/{max_retries})")
            stdout, _ = run_command(f"hciconfig {hci_device}")

            if "UP RUNNING" in stdout:
                print(f"[ADAPTER] 适配器 {hci_device} 已启用")
                return True

            print(f"[ADAPTER] 适配器 {hci_device} 未启用，尝试激活...")
            run_command(f"sudo hciconfig {hci_device} up", capture_output=False)
            time.sleep(2)

            stdout, _ = run_command(f"hciconfig {hci_device}")
            if "UP RUNNING" in stdout:
                print(f"[ADAPTER] 适配器 {hci_device} 激活成功")
                return True

            # 激活失败，尝试重置适配器
            if not reset_adapter(hci_device):
                print("[ADAPTER] 尝试重置适配器失败")

        except Exception as e:
            print(f"[ERROR] 检查适配器状态时出错: {e}")

        time.sleep(2)

    print(f"[ERROR] 无法使适配器 {hci_device} 就绪，经过 {max_retries} 次尝试")
    return False


def acquire_lock(max_wait=30, max_retries=3):
    """获取锁文件（带重试机制）"""
    lock_file = "/tmp/.ble_lock"

    for attempt in range(1, max_retries + 1):
        try:
            print(f"[LOCK] 获取BLE锁 (尝试 {attempt}/{max_retries})")

            start_time = time.time()
            while os.path.exists(lock_file):
                print(" L ", end='', flush=True)

                # 检查是否超时
                if time.time() - start_time > max_wait:
                    print(f"\n[LOCK] 等待锁超时 ({max_wait}秒)，强制继续")
                    break

                # 检查锁是否过期（>30秒）
                if time.time() - os.path.getmtime(lock_file) > 30:
                    print("\n[LOCK] 检测到过期锁，删除")
                    try:
                        os.remove(lock_file)
                        break
                    except Exception as e:
                        print(f"[ERROR] 删除锁失败: {e}")

                time.sleep(2)

            # 创建锁文件
            with open(lock_file, "w") as f:
                f.write(str(os.getpid()))
            print(f"\n[LOCK] 创建锁文件: {lock_file}")
            return lock_file

        except Exception as e:
            print(f"[ERROR] 获取锁失败: {e}")
            time.sleep(2)

    print(f"[ERROR] 无法获取锁，经过 {max_retries} 次尝试")
    return None


def release_lock(lock_file):
    """释放锁文件（带错误处理）"""
    if lock_file and os.path.exists(lock_file):
        try:
            os.remove(lock_file)
            print(f"[LOCK] 释放锁文件: {lock_file}")
        except Exception as e:
            print(f"[ERROR] 释放锁文件失败: {e}")
    else:
        print("[LOCK] 无锁文件可释放")


def scan_device(ble_name, hci_device, max_retries=3):
    """扫描设备获取MAC地址（带重试和错误处理）"""
    for attempt in range(1, max_retries + 1):
        try:
            print(f"\n[SCAN] 扫描设备 {ble_name} (尝试 {attempt}/{max_retries})")

            # 确保适配器就绪
            if not ensure_adapter_ready(hci_device):
                print("[SCAN] 适配器不可用，无法扫描")
                continue

            # 重置适配器
            reset_adapter(hci_device)

            # 创建临时扫描文件
            scan_file = f"/tmp/ble_scan_{os.getpid()}.txt"

            # 执行扫描命令
            scan_cmd = f"sudo timeout 10 hcitool -i {hci_device} lescan --duplicates > {scan_file} 2>&1"
            stdout, stderr = run_command(scan_cmd, timeout=15)

            # 检查扫描是否成功
            if stderr and "Invalid device" in stderr:
                print("[SCAN] 扫描失败：适配器无效，尝试重置...")
                reset_adapter(hci_device)
                continue

            # 读取扫描结果
            if not os.path.exists(scan_file):
                print("[SCAN] 扫描文件未生成")
                continue

            try:
                with open(scan_file, 'r') as f:
                    content = f.read()

                # 查找匹配的MAC地址
                pattern = re.compile(r"((?:[0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}) .*" + re.escape(ble_name))
                matches = pattern.findall(content)

                if matches:
                    ble_mac = matches[-1]
                    print(f"[SCAN] 找到设备: {ble_name} MAC: {ble_mac}")
                    return ble_mac
                else:
                    print(f"[SCAN] 未找到设备: {ble_name}")
                    # 打印部分扫描结果用于调试
                    if content.strip():
                        print(f"[SCAN] 扫描内容预览: {content[:200]}{'...' if len(content) > 200 else ''}")
                    else:
                        print("[SCAN] 扫描结果为空")
            except Exception as e:
                print(f"[ERROR] 读取扫描文件失败: {e}")
            finally:
                # 清理扫描文件
                try:
                    os.remove(scan_file)
                except:
                    pass

        except Exception as e:
            print(f"[ERROR] 扫描设备时出错: {e}")

        time.sleep(2)

    print(f"[ERROR] 超过最大扫描重试次数 {max_retries}")
    return None


def connect_device(ble_mac, hci_device, max_retries=3):
    """执行连接命令并打印结果（带错误处理）"""
    if not ble_mac:
        print("[CONNECT] 无效的MAC地址，跳过连接")
        return None, None

    for attempt in range(1, max_retries + 1):
        try:
            print(f"\n[CONNECT] 执行连接命令 (尝试 {attempt}/{max_retries})")

            # 确保适配器就绪
            if not ensure_adapter_ready(hci_device):
                print("[CONNECT] 适配器不可用，无法连接")
                continue

            # 重置控制器
            run_command(f"sudo hcitool -i {hci_device} cmd 0x08 0x000E", capture_output=False)

            # 执行连接命令
            cmd = f"sudo hcitool -i {hci_device} lecc --random {ble_mac}"
            print(f"[CONNECT] 执行命令: {cmd}")
            stdout, stderr = run_command(cmd, timeout=15)

            # 打印完整输出
            print("[CONNECT] 命令输出:")
            print(f"  STDOUT: {stdout}")
            print(f"  STDERR: {stderr}")

            # 返回输出结果
            return stdout, stderr

        except Exception as e:
            print(f"[ERROR] 连接设备时出错: {e}")
            # 出错后重置适配器
            reset_adapter(hci_device)

        time.sleep(2)

    print(f"[ERROR] 超过最大连接尝试次数 {max_retries}")
    return None, None


def open_serial_port(port, baudrate=115200, timeout=1):
    """打开串口连接（带错误处理）"""
    try:
        ser = serial.Serial(
            port=port,
            baudrate=baudrate,
            bytesize=serial.EIGHTBITS,
            parity=serial.PARITY_NONE,
            stopbits=serial.STOPBITS_ONE,
            timeout=timeout
        )
        print(f"[SERIAL] 串口 {port} 已打开")
        return ser
    except serial.SerialException as e:
        print(f"[ERROR] 打开串口 {port} 失败: {e}")
        print("[TIPS] 请检查：")
        print("  1. 串口设备是否存在")
        print("  2. 当前用户是否有访问权限（可能需要加入dialout组）")
        print("  3. 是否有其他程序占用了串口")
        return None
    except Exception as e:
        print(f"[ERROR] 打开串口时发生未知错误: {e}")
        return None


def send_serial_commands(ser, commands):
    """通过串口发送命令（带错误处理）"""
    if not ser or not ser.is_open:
        print("[SERIAL] 串口未打开，无法发送命令")
        return False

    try:
        for cmd in commands:
            # 移除命令中的换行符用于显示
            clean_cmd = cmd.replace('\r', '\\r').replace('\n', '\\n')
            print(f"[SERIAL] 发送命令: {clean_cmd}")

            # 实际发送命令（包含换行符）
            ser.write(cmd.encode('utf-8'))

            # 命令间短暂延迟
            time.sleep(0.5)

        print("[SERIAL] 所有命令已发送")
        return True
    except serial.SerialException as e:
        print(f"[ERROR] 串口通信错误: {e}")
        return False
    except Exception as e:
        print(f"[ERROR] 发送串口命令失败: {e}")
        return False


def wait_for_serial_message(ser, pattern, timeout=30):
    """等待串口出现特定消息（带超时和调试输出）"""
    if not ser or not ser.is_open:
        print("[SERIAL] 串口未打开，无法读取")
        return False

    start_time = time.time()
    compiled_pattern = re.compile(pattern)
    buffer = ""

    print(f"[SERIAL] 等待消息: '{pattern}' (超时: {timeout}秒)")

    while time.time() - start_time < timeout:
        try:
            # 读取串口数据
            if ser.in_waiting > 0:
                data = ser.readline().decode('utf-8', errors='ignore')
                if data:
                    # 打印接收到的原始数据（用于调试）
                    clean_data = data.replace('\r', '\\r').replace('\n', '\\n')
                    print(f"[SERIAL] 接收: {clean_data.strip()}")

                    buffer += data

                    # 检查是否匹配模式
                    if compiled_pattern.search(buffer):
                        print(f"[SERIAL] 找到匹配消息: '{pattern}'")
                        return True
        except serial.SerialException as e:
            print(f"[ERROR] 串口读取错误: {e}")
            time.sleep(0.1)
        except Exception as e:
            print(f"[ERROR] 读取串口时出错: {e}")
            time.sleep(0.1)

        # 短暂休眠减少CPU占用
        time.sleep(0.1)

    print(f"[SERIAL] 超时: 未找到消息 '{pattern}'")
    return False


def put_device_to_sleep(ser, max_retries=3):
    """使设备进入睡眠状态（带重试机制）"""
    for attempt in range(1, max_retries + 1):
        print(f"\n[SLEEP] 尝试使设备进入睡眠 (尝试 {attempt}/{max_retries})")

        # 发送睡眠命令
        if not send_serial_commands(ser, CONFIG["SLEEP_COMMANDS"]):
            continue

        # 等待睡眠标志
        if wait_for_serial_message(ser, CONFIG["SLEEP_FLAG"], timeout=10):
            print("[SLEEP] 设备已进入睡眠状态")
            return True

        print("[SLEEP] 未检测到睡眠标志，重试...")
        time.sleep(2)

    print("[ERROR] 无法使设备进入睡眠状态")
    return False


def verify_device_wakeup(ser, max_retries=3):
    """验证设备是否唤醒（带重试机制）"""
    for attempt in range(1, max_retries + 1):
        print(f"\n[WAKEUP] 验证设备唤醒 (尝试 {attempt}/{max_retries})")

        # 等待唤醒标志
        if wait_for_serial_message(ser, CONFIG["WAKEUP_FLAG"], timeout=15):
            print("[WAKEUP] 设备已唤醒")
            return True

        print("[WAKEUP] 未检测到唤醒标志，重试...")
        time.sleep(2)

    print("[ERROR] 未检测到设备唤醒")
    return False


# ===================== 主测试流程 =====================
def run_full_test_cycle(cycle_num):
    """运行完整的测试周期"""
    print(f"\n{'=' * 60}")
    print(f"开始测试周期 #{cycle_num}")
    print(f"{'=' * 60}")

    cycle_success = False
    start_time = time.time()

    try:
        # 1. 确保适配器就绪
        if not ensure_adapter_ready(CONFIG["HCI_DEVICE"], CONFIG["MAX_RETRIES"]["ADAPTER_READY"]):
            print("[CYCLE] 错误: 适配器不可用，跳过此周期")
            return False

        # 2. 获取锁
        lock_file = acquire_lock(max_retries=CONFIG["MAX_RETRIES"]["LOCK_ACQUIRE"])
        if not lock_file:
            print("[CYCLE] 警告: 无法获取锁，继续执行")

        try:
            # 3. 扫描设备获取MAC
            ble_mac = scan_device(
                CONFIG["BLE_DEVICE_NAME"],
                CONFIG["HCI_DEVICE"],
                CONFIG["MAX_RETRIES"]["SCAN_DEVICE"]
            )

            if not ble_mac:
                print("[CYCLE] 错误: 无法获取MAC地址，跳过此周期")
                return False

            # 4. 打开串口
            ser = open_serial_port(
                CONFIG["SERIAL_PORT"],
                CONFIG["SERIAL_BAUDRATE"],
                CONFIG["SERIAL_TIMEOUT"]
            )

            if not ser:
                print("[CYCLE] 错误: 无法打开串口，跳过此周期")
                return False

            try:
                # 5. 使设备进入睡眠
                if not put_device_to_sleep(ser, CONFIG["MAX_RETRIES"]["SLEEP_SEQUENCE"]):
                    print("[CYCLE] 错误: 无法使设备进入睡眠，跳过此周期")
                    return False

                # 6. 执行BLE连接（唤醒设备）
                connect_result = connect_device(
                    ble_mac,
                    CONFIG["HCI_DEVICE"],
                    CONFIG["MAX_RETRIES"]["CONNECT_DEVICE"]
                )

                # 7. 验证设备唤醒
                if verify_device_wakeup(ser, CONFIG["MAX_RETRIES"]["WAKEUP_VERIFY"]):
                    print("[CYCLE] 设备成功唤醒!")
                    cycle_success = True
                else:
                    print("[CYCLE] 错误: 未检测到设备唤醒")

            finally:
                # 关闭串口
                try:
                    if ser.is_open:
                        ser.close()
                        print("[SERIAL] 串口已关闭")
                except Exception as e:
                    print(f"[ERROR] 关闭串口时出错: {e}")
        finally:
            # 释放锁
            release_lock(lock_file)

    except Exception as e:
        print(f"[ERROR] 测试周期发生未处理异常: {e}")

    # 计算周期耗时
    duration = time.time() - start_time
    print(f"[CYCLE] 测试周期 #{cycle_num} 完成, 耗时: {duration:.2f}秒")
    print(f"[CYCLE] 状态: {'成功' if cycle_success else '失败'}")
    print(f"{'-' * 60}\n")

    return cycle_success


def main():
    # 设置日志系统
    sys.stdout = Logger(CONFIG["LOG_FILE"])

    # 打印配置信息
    print(f"\n{'=' * 60}")
    print(f"BLE唤醒测试程序 - 开始时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'=' * 60}")
    print("配置参数:")
    for key, value in CONFIG.items():
        if key == "SLEEP_COMMANDS":
            print(f"  SLEEP_COMMANDS: ")
            for i, cmd in enumerate(value):
                clean_cmd = cmd.replace('\r', '\\r').replace('\n', '\\n')
                print(f"    {i + 1}. {clean_cmd}")
        elif isinstance(value, dict):
            print(f"  {key}:")
            for subkey, subvalue in value.items():
                print(f"    {subkey}: {subvalue}")
        else:
            print(f"  {key}: {value}")
    print(f"{'=' * 60}\n")

    # 运行多个测试周期
    success_count = 0
    for cycle in range(1, CONFIG["TEST_CYCLES"] + 1):
        if run_full_test_cycle(cycle):
            success_count += 1

        # 如果不是最后一次循环，添加延迟
        if cycle < CONFIG["TEST_CYCLES"]:
            print(f"[MAIN] 等待 {CONFIG['CYCLE_DELAY']}秒后进行下一个周期...")
            time.sleep(CONFIG["CYCLE_DELAY"])

    # 最终报告
    print(f"\n{'=' * 60}")
    print(f"测试完成: {success_count}/{CONFIG['TEST_CYCLES']} 个周期成功")
    print(f"成功率: {success_count / CONFIG['TEST_CYCLES'] * 100:.2f}%")

    if success_count == CONFIG["TEST_CYCLES"]:
        print("所有测试周期均成功!")
        sys.exit(0)
    else:
        print("部分测试周期失败")
        sys.exit(1)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n[MAIN] 程序被用户中断")
        sys.exit(1)
    except Exception as e:
        print(f"[MAIN] 发生未处理异常: {e}")
        sys.exit(1)