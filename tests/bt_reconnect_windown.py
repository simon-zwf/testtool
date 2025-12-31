import subprocess
import time
import logging
import re
from datetime import datetime

# --------------------------
# 关键参数（必须确认！）
# --------------------------
TARGET_DEVICE_NAME = "Infinix AI Glasses"  # 设备在UI中显示的完整名称（复制粘贴，避免空格/大小写错误）
SCAN_DURATION = 25  # 扫描时长（25秒，覆盖设备广播周期）
ADAPTER_START_DELAY = 8  # 蓝牙适配器启动后等待时间（确保硬件就绪）

# --------------------------
# 日志配置（显示所有扫描到的设备，便于调试）
# --------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler(f"win_bt_final_test_{datetime.now().strftime('%Y%m%d%H%M%S')}.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


def run_admin_powershell(cmd, timeout=60):
    """以管理员权限执行PowerShell命令（关键：确保扫描权限）"""
    try:
        # 创建管理员权限的进程（必须用ShellExecuteEx，确保权限）
        import ctypes
        from ctypes import wintypes

        # 定义结构体（用于ShellExecuteEx）
        class SHELLEXECUTEINFO(ctypes.Structure):
            _fields_ = [
                ("cbSize", wintypes.DWORD),
                ("fMask", wintypes.DWORD),
                ("hwnd", wintypes.HWND),
                ("lpVerb", ctypes.c_char_p),
                ("lpFile", ctypes.c_char_p),
                ("lpParameters", ctypes.c_char_p),
                ("lpDirectory", ctypes.c_char_p),
                ("nShow", ctypes.c_int),
                ("hInstApp", wintypes.HINSTANCE),
                ("lpIDList", ctypes.c_void_p),
                ("lpClass", ctypes.c_char_p),
                ("hKeyClass", wintypes.HKEY),
                ("dwHotKey", wintypes.DWORD),
                ("hIcon", wintypes.HANDLE),
                ("hProcess", wintypes.HANDLE)
            ]

        sei = SHELLEXECUTEINFO()
        sei.cbSize = ctypes.sizeof(SHELLEXECUTEINFO)
        sei.fMask = 0x00000040  # SEE_MASK_NOCLOSEPROCESS
        sei.lpVerb = b"runas"  # 管理员权限
        sei.lpFile = b"powershell.exe"
        # 将命令写入临时文件（避免命令过长导致参数传递失败）
        temp_cmd_file = f"C:\\temp_bt_scan_{datetime.now().strftime('%Y%m%d%H%M%S')}.ps1"
        with open(temp_cmd_file, "w", encoding="utf-8") as f:
            f.write(cmd)
        sei.lpParameters = f"-ExecutionPolicy Bypass -File \"{temp_cmd_file}\"".encode("utf-8")
        sei.nShow = 0  # 隐藏窗口

        # 执行命令
        if ctypes.windll.shell32.ShellExecuteExW(ctypes.byref(sei)) == 0:
            raise Exception(f"获取管理员权限失败，错误码：{ctypes.GetLastError()}")

        # 等待命令执行完成
        ctypes.windll.kernel32.WaitForSingleObject(sei.hProcess, timeout * 1000)
        # 获取命令输出（通过临时文件存储结果）
        output_file = temp_cmd_file.replace(".ps1", "_output.txt")
        time.sleep(2)
        if ctypes.windll.kernel32.GetFileAttributesW(output_file) != 0xFFFFFFFF:
            with open(output_file, "r", encoding="utf-8") as f:
                stdout = f.read()
        else:
            stdout = "未获取到输出"

        # 清理临时文件
        ctypes.windll.kernel32.CloseHandle(sei.hProcess)
        subprocess.run(f"del \"{temp_cmd_file}\" \"{output_file}\"", shell=True, stdout=subprocess.PIPE)

        return stdout, 0
    except Exception as e:
        logger.error(f"命令执行异常：{str(e)}")
        return str(e), -1


class WinBluetoothFinalTester:
    def __init__(self, target_name):
        self.target_name = target_name.strip()  # 去除名称前后空格（避免匹配错误）
        self.target_mac = None

    def scan_target_device(self):
        """
        终极扫描逻辑：
        1. 同时扫描经典蓝牙+BLE设备
        2. 用底层API捕捉所有广播（和UI逻辑一致）
        3. 输出所有扫描到的设备，便于调试
        """
        logger.info(f"🔍 开始扫描（持续{SCAN_DURATION}秒，覆盖经典蓝牙+BLE）...")

        # PowerShell扫描命令（关键：用BluetoothLEAdvertisementWatcher捕捉所有广播）
        # 修正后的 PowerShell 扫描命令（关键：转义所有大括号）
        ps_cmd = f"""
            # 确保蓝牙服务启动
            Start-Service bthserv -ErrorAction SilentlyContinue;
            Start-Sleep -Seconds {ADAPTER_START_DELAY};  # 等待适配器就绪

            # 初始化BLE扫描器（捕捉BLE设备）
            $bleWatcher = New-Object Windows.Devices.Bluetooth.Advertisement.BluetoothLEAdvertisementWatcher;
            $allDevices = @();  # 存储所有扫描到的设备（去重）

            # 注册BLE设备发现事件
            Register-ObjectEvent -InputObject $bleWatcher -EventName Received -Action {{
                $addr = $EventArgs.BluetoothAddress.ToString('X2') -replace '..(?!$)', '$0:';
                $name = $EventArgs.Advertisement.LocalName.Trim() ?: "未知设备($addr)";
                # 去重：同一MAC只保留一个
                if (-not $global:allDevices.Where({{ $_.Address -eq $addr }})) {{
                    $global:allDevices += [PSCustomObject]@{{
                        Type = "BLE设备";
                        Name = $name;
                        Address = $addr;
                        Time = Get-Date -Format "HH:mm:ss"
                    }};
                }}
            }} | Out-Null;

            # 扫描经典蓝牙设备（已绑定+未绑定）
            Start-Job -ScriptBlock {{
                $classicDevices = Get-PnpDevice -Class Bluetooth -ErrorAction SilentlyContinue | Where-Object {{ $_.Status -eq 'OK' }};
                foreach ($dev in $classicDevices) {{
                    $addr = $dev.PNPClass -match '([0-9A-Fa-f:]{{17}})' ? $matches[1] : $dev.InstanceId.Substring(-17);
                    $name = $dev.Name.Trim() ?: "未知经典设备($addr)";
                    if (-not $global:allDevices.Where({{ $_.Address -eq $addr }})) {{
                        $global:allDevices += [PSCustomObject]@{{
                            Type = "经典蓝牙";
                            Name = $name;
                            Address = $addr;
                            Time = Get-Date -Format "HH:mm:ss"
                        }};
                    }}
                }}
            }} | Out-Null;

            # 开始扫描
            $bleWatcher.Start();
            Start-Sleep -Seconds {SCAN_DURATION};
            $bleWatcher.Stop();

            # 输出所有扫描到的设备（方便调试）
            Write-Host "`n===== 扫描到的所有设备 =====`n";
            $global:allDevices | Sort-Object Type, Name | Format-Table -AutoSize;

            # 查找目标设备（模糊匹配，忽略大小写）
            $target = $global:allDevices | Where-Object {{ $_.Name -like '*{self.target_name}*' -or $_.Address -like '*{self.target_name}*' }};
            if ($target) {{
                Write-Host "`n===== 找到目标设备 =====`n";
                $target | Format-Table -AutoSize;
                # 输出MAC地址（供代码解析）
                Write-Output "TARGET_MAC=$($target.Address)";
            }} else {{
                Write-Host "`n===== 未找到目标设备：{self.target_name} =====`n";
                Write-Output "TARGET_MAC=NOT_FOUND";
            }}
        """

        # 执行扫描命令（必须管理员权限）
        stdout, returncode = run_admin_powershell(ps_cmd, timeout=SCAN_DURATION + 20)
        logger.info(f"扫描命令输出：`n{stdout}`n")

        # 解析扫描结果，提取目标设备MAC
        mac_match = re.search(r"TARGET_MAC=([0-9A-Fa-f:]{17}|NOT_FOUND)", stdout)
        if mac_match and mac_match.group(1) != "NOT_FOUND":
            self.target_mac = mac_match.group(1)
            logger.info(f"✅ 成功找到目标设备，MAC={self.target_mac}")
            return True
        else:
            # 显示所有扫描到的设备，帮助用户确认是否真的没扫到
            logger.error(f"❌ 未找到目标设备：{self.target_name}")
            logger.error(
                "请核对：1. 设备名称是否和UI完全一致（含空格/特殊字符）；2. 设备是否已开启可发现模式；3. 扫描时长是否足够")
            return False


# --------------------------
# 测试入口（必须管理员权限运行！）
# --------------------------
if __name__ == "__main__":
    # ！！！关键：复制UI中显示的设备完整名称（比如UI显示“Infinix AI Glasses ”，要带末尾空格）
    TARGET_NAME = "Infinix AI Glasses"  # 替换为UI中显示的完整名称！！！

    tester = WinBluetoothFinalTester(target_name=TARGET_NAME)
    # 仅执行扫描（先解决扫描问题，再后续处理连接）
    scan_result = tester.scan_target_device()

    if scan_result:
        logger.info("🎉 扫描成功！后续可添加连接/回连逻辑")
    else:
        logger.info("⚠️  扫描失败，请按日志提示核对设备信息和状态")