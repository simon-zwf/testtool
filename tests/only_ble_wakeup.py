import os
import re
import time
import subprocess
import sys
from datetime import datetime


def run_command(cmd, capture_output=True, check=True, timeout=None):
    """执行系统命令并返回输出和状态"""
    try:
        result = subprocess.run(
            cmd,
            shell=True,
            check=check,
            stdout=subprocess.PIPE if capture_output else None,
            stderr=subprocess.PIPE if capture_output else None,
            text=True,
            timeout=timeout
        )
        if capture_output:
            return result.stdout.strip(), result.stderr.strip(), result.returncode
        return None, None, result.returncode
    except subprocess.CalledProcessError as e:
        if capture_output:
            return e.stdout.strip(), e.stderr.strip(), e.returncode
        return None, None, e.returncode
    except subprocess.TimeoutExpired:
        print(f"命令超时: {cmd}")
        return None, None, -1
    except Exception as e:
        print(f"命令执行异常: {e}")
        return None, None, -2


def reset_bluetooth_adapter(hci_device):
    """重置蓝牙适配器"""
    print(f"重置蓝牙适配器 {hci_device}...")

    # 重置HCI设备
    run_command(f"sudo hciconfig {hci_device} reset", capture_output=False)

    # 发送LE重置命令
    run_command(f"sudo hcitool -i {hci_device} cmd 0x08 0x000E", capture_output=False)
    time.sleep(1)

    # 确保设备重新上线
    run_command(f"sudo hciconfig {hci_device} up", capture_output=False)

    # 检查设备状态
    stdout, _, _ = run_command(f"hciconfig {hci_device} | grep 'UP RUNNING'")
    if stdout:
        print(f"适配器 {hci_device} 重置成功并已启用")
        return True
    else:
        print(f"警告: 适配器 {hci_device} 重置后仍未启用")
        return False


def check_hci_device(hci_device):
    """检查指定的HCI设备是否存在且可用"""
    # 检查设备是否存在
    _, stderr, returncode = run_command(f"hciconfig {hci_device}")
    if returncode != 0:
        print(f"错误: 设备 {hci_device} 不存在或不可用")
        print(f"详细信息: {stderr}")
        return False

    # 检查设备状态
    stdout, _, _ = run_command(f"hciconfig {hci_device} | grep 'UP RUNNING'")
    if not stdout:
        print(f"警告: 设备 {hci_device} 未启用，尝试激活...")
        _, stderr, returncode = run_command(f"sudo hciconfig {hci_device} up")
        if returncode != 0:
            print(f"激活设备失败: {stderr}")
            # 尝试重置适配器
            if reset_bluetooth_adapter(hci_device):
                return True
            return False

    # 确认设备已启用
    stdout, _, _ = run_command(f"hciconfig {hci_device} | grep 'UP RUNNING'")
    if not stdout:
        print(f"错误: 无法激活设备 {hci_device}")
        # 尝试重置适配器
        if reset_bluetooth_adapter(hci_device):
            return True
        return False

    return True


def ble_connect(ble_name, hci_device="hci1", retry_limit=5):
    """
    通过BLE名称连接蓝牙设备
    :param ble_name: 要连接的BLE设备名称
    :param hci_device: 使用的HCI设备
    :param retry_limit: 最大重试次数
    """
    print(f"使用设备: {hci_device}")
    # 验证HCI设备
    if not check_hci_device(hci_device):
        print(f"错误: 设备 {hci_device} 不可用")
        return False

    # 锁文件路径
    lock_file = "/tmp/.ble_lock"

    # 改进的锁机制 - 带超时
    print("检查BLE锁...")
    max_wait_time = 30  # 最大等待时间（秒）
    start_time = time.time()

    while os.path.exists(lock_file):
        print(" L ", end='', flush=True)

        # 检查锁文件是否过期（超过30秒）
        if time.time() - os.path.getmtime(lock_file) > 30:
            print("\n检测到过期锁文件，强制删除...")
            try:
                os.remove(lock_file)
                break
            except Exception as e:
                print(f"删除锁文件失败: {e}")

        # 检查是否超过最大等待时间
        if time.time() - start_time > max_wait_time:
            print(f"\n错误: 超过最大等待时间 ({max_wait_time}秒)，强制继续")
            break

        time.sleep(2)

    # 创建锁文件
    try:
        with open(lock_file, 'w') as f:
            f.write(str(os.getpid()))
        print(f"创建锁文件: {lock_file}")
    except Exception as e:
        print(f"创建锁文件失败: {e}")
        return False

    got_mac = False
    ble_mac = None
    retry_count = 0

    while not got_mac and retry_count < retry_limit:
        print(f"\n尝试 #{retry_count + 1}/{retry_limit}")
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"开始扫描 [{current_time}]")

        # 重置hcitool
        run_command(f"sudo hcitool -i {hci_device} cmd 0x08 0x000E", capture_output=False)
        run_command(f"sudo hcitool -i {hci_device} cmd 0x08 0x000E", capture_output=False)

        # 开始扫描并保存结果
        print("启动扫描...")
        scan_file = f"/tmp/scan_{hci_device}_{os.getpid()}.txt"
        scan_cmd = f"sudo timeout 10 hcitool -i {hci_device} lescan --duplicates > {scan_file} 2>&1"
        _, stderr, returncode = run_command(scan_cmd, timeout=15)

        if returncode != 0:
            print(f"扫描失败: {stderr or '未知错误'}")

        # 在扫描结果中查找设备
        if os.path.exists(scan_file):
            try:
                with open(scan_file, 'r') as f:
                    content = f.read()

                # 查找匹配的MAC地址
                pattern = re.compile(r"((?:[0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}) .*" + re.escape(ble_name))
                matches = pattern.findall(content)

                if matches:
                    ble_mac = matches[-1]  # 取最后一个匹配项
                    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    print(f"找到设备: {ble_name} MAC: {ble_mac} [{current_time}]")
                    got_mac = True
                else:
                    print(f"未找到设备: {ble_name}")
                    # 打印部分扫描结果用于调试
                    if content.strip():
                        print(f"扫描结果预览: {content[:200]}{'...' if len(content) > 200 else ''}")
                    else:
                        print("扫描结果为空")
            except Exception as e:
                print(f"读取扫描文件失败: {e}")
        else:
            print("扫描文件未生成")

        # 清理扫描文件
        if os.path.exists(scan_file):
            try:
                os.remove(scan_file)
            except:
                pass

        retry_count += 1
        time.sleep(1)

    # 检查是否找到MAC
    if not got_mac:
        if os.path.exists(lock_file):
            try:
                os.remove(lock_file)
            except:
                pass
        print(f"\n错误: 超过最大重试次数 {retry_limit}")
        return False

    # 多次尝试连接
    print(f"正在连接 {ble_mac}...")
    connection_established = False
    max_connection_attempts = 5

    for attempt in range(max_connection_attempts):
        # 重置控制器
        run_command(f"sudo hcitool -i {hci_device} cmd 0x08 0x000E", capture_output=False)

        # 尝试连接
        print(f"连接尝试 {attempt + 1}/{max_connection_attempts}")
        cmd = f"sudo hcitool -i {hci_device} lecc --random {ble_mac}"
        stdout, stderr, returncode = run_command(cmd, timeout=15)

        # 安全处理可能的None值
        stdout_str = stdout or ""
        stderr_str = stderr or ""

        # 分析连接结果
        if returncode == 0:
            # 检查是否包含连接句柄
            if "handle" in stdout_str.lower():
                print(f"连接成功! [句柄: {stdout_str.strip()}]")
                connection_established = True
                break
            else:
                print(f"连接命令成功但未获得句柄: {stdout_str}")
        else:
            # 检查错误类型
            error_msg = f"返回码: {returncode}, 错误: {stderr_str or stdout_str or '未知错误'}"

            if "invalid device" in error_msg.lower():
                print(f"致命错误: 设备 {hci_device} 已断开")
                # 尝试重置适配器
                if reset_bluetooth_adapter(hci_device):
                    print("适配器已重置，继续尝试连接")
                else:
                    print("适配器重置失败，放弃连接")
                    break
            elif "timeout" in error_msg.lower():
                print(f"连接超时 [尝试: {attempt + 1}/{max_connection_attempts}]")
            else:
                print(f"连接失败 [尝试: {attempt + 1}/{max_connection_attempts}]: {error_msg}")

        # 每两次尝试后重置适配器
        if attempt > 0 and (attempt + 1) % 2 == 0:
            print("连接多次失败，尝试重置适配器...")
            reset_bluetooth_adapter(hci_device)
            time.sleep(2)

        time.sleep(1)

    # 清理锁文件
    if os.path.exists(lock_file):
        try:
            os.remove(lock_file)
        except:
            pass

    if connection_established:
        print("BLE连接成功建立")
        return True
    else:
        print("错误: 无法建立BLE连接")
        return False


if __name__ == "__main__":
    # 配置参数
    BLE_DEVICE_NAME = "S44 4476 LE"  # BLE设备名称
    HCI_DEVICE = "hci1"  # 蓝牙适配器

    print(f"开始连接BLE设备: {BLE_DEVICE_NAME} 使用适配器: {HCI_DEVICE}")

    # 尝试连接
    success = False
    for i in range(3):  # 最多尝试3次
        print(f"\n===== 连接尝试 {i + 1} =====")
        if ble_connect(BLE_DEVICE_NAME, HCI_DEVICE):
            success = True
            break
        print("连接失败，30秒后重试...")
        time.sleep(30)

    if success:
        print("BLE连接成功!")
        sys.exit(0)
    else:
        print("连接失败，退出程序")
        sys.exit(1)