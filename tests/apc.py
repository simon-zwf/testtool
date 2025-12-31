# ==================================================
# !/usr/bin/env python
# @Author: simon.zhang
# @Date: 2025/12/12 10:20
# @FileName: apc.py
# @Email: wangfu_zhang@ggec.com.cn
# ==================================================
# !/usr/bin/env python3
"""
APC PDU控制脚本 - 极简版本
"""

import sys
import time
import telnetlib

# APC配置
RACK_IPS = {
    '1': '200.1.1.15',
    '2': '200.1.1.16',
    '5': '200.1.1.52',
}

USERNAME = "apc"
PASSWORD = "apc"


def control_apc(port, command, rack):
    """控制APC电源"""
    # 获取目标IP
    if rack in ['1', 'rack1']:
        target_ip = RACK_IPS['1']
    elif rack in ['2', 'rack2']:
        target_ip = RACK_IPS['2']
    elif rack in ['5', 'rack5']:
        target_ip = RACK_IPS['5']
    else:
        print(f"错误: 不支持的rack: {rack}")
        return False

    try:
        # 连接
        tn = telnetlib.Telnet(target_ip, timeout=5)

        # 登录
        tn.read_until(b"User Name :")
        tn.write(USERNAME.encode() + b"\r")

        tn.read_until(b"Password  :")
        tn.write(PASSWORD.encode() + b"\r")

        tn.read_until(b"apc>", timeout=5)

        # 执行命令
        cmd_map = {'on': 'olOn', 'off': 'olOff', 'reboot': 'olReboot'}
        if port == 'all':
            cmd = f"{cmd_map[command]} 9\r"
        else:
            cmd = f"{cmd_map[command]} {port}\r"

        tn.write(cmd.encode())
        time.sleep(1)

        # 检查响应
        response = tn.read_very_eager().decode()
        tn.close()

        return "Success" in response or "E000" in response

    except Exception as e:
        print(f"错误: {e}")
        return False


if __name__ == "__main__":
    if len(sys.argv) != 4:
        print("用法: python3 apc.py <端口> <on|off|reboot> <rack>")
        sys.exit(1)

    port, command, rack = sys.argv[1], sys.argv[2], sys.argv[3]

    if control_apc(port, command, rack):
        print("成功")
        sys.exit(0)
    else:
        print("失败")
        sys.exit(1)