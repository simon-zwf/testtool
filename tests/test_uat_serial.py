import serial
import time
from datetime import datetime

# 配置参数（完全适配pyserial 3.5）
SERIAL_PORT = "COM7"
BAUDRATE = 115200  # 必须与设备一致
TIMEOUT = 2  # 读取超时（秒）
LOG_FILE = "serial_complete_log.txt"
GO_TO_SLEEP = 'a113x2 SOC turned off' # sleep标志

# 要发送的指令（根据设备要求调整换行符）
COMMANDS = [
    "echo DeviceSuspendRequested > /tmp/sonospowercoordinator_USR1_cmd_OVERRIDE\r\n",  # 用\r\n尝试
    "killall -SIGUSR1 sonospowercoordinator\r\n"
]


def log(message, is_serial=False):
    """日志输出到控制台和文件"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    tag = "[串口数据] " if is_serial else ""
    log_msg = f"[{timestamp}] {tag}{message}"
    print(log_msg)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(log_msg + "\n")


def main():
    # 清空旧日志
    with open(LOG_FILE, "w") as f:
        f.write("=== 新会话开始 ===\n")
    log("工具启动，准备连接串口...")

    try:
        # pyserial 3.5 必须用整数设置停止位（1=1个停止位）
        ser = serial.Serial(
            port=SERIAL_PORT,
            baudrate=BAUDRATE,
            timeout=TIMEOUT,
            parity=serial.PARITY_NONE,
            stopbits=1,  # 关键：3.5版本只能用整数，不能用STOPBITS_1
            bytesize=8,  # 8位数据位（直接用整数更兼容）
            xonxoff=False,
            rtscts=False
        )

        if not ser.is_open:
            ser.open()
        log(f"成功打开串口 {SERIAL_PORT}，参数：波特率={BAUDRATE}, 停止位=1, 数据位=8")

        # 清空缓冲区
        ser.reset_input_buffer()
        ser.reset_output_buffer()
        time.sleep(2)  # 等待设备初始化

        # 发送指令
        for i, cmd in enumerate(COMMANDS, 1):
            ser.write(cmd.encode('utf-8'))
            log(f"已发送指令 {i}：{cmd.strip()}")
            time.sleep(3)  # 等待设备响应

        # 持续监听串口数据（60秒）
        log("开始监听设备响应...")
        wakeup_found = False
        start_time = time.time()

        while time.time() - start_time < 60:
            # 读取所有可用数据（不依赖换行符）
            data = ser.read(ser.in_waiting or 1)  # 即使没有数据也尝试读1字节
            if data:
                # 优先字符串解码，失败则用十六进制
                try:
                    text = data.decode('utf-8', errors='replace')
                    log(text, is_serial=True)
                    if GO_TO_SLEEP in text:
                        wakeup_found = True
                        log(f"✅ check out UUT into sleep：{GO_TO_SLEEP}")
                except:
                    log(f"[十六进制] {data.hex()}", is_serial=True)
            time.sleep(0.1)

        # 结束检查
        if wakeup_found:
            log("设备sleep成功")
        else:
            log("❌ 未检测到sleep标识，请检查设备状态")

        ser.close()
        log(f"串口 {SERIAL_PORT} 已关闭")

    except Exception as e:
        log(f"发生错误：{str(e)}")


if __name__ == "__main__":
    main()
    log("工具运行结束")
