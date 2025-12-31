import asyncio
import time
from ble_scan import scan_for_ble_devices
from ble_control_no_scan import BLEConnector

async def get_address_by_serial(serial_to_find):
    # 扫描BLE设备，调用ble_scan.py里面的方法
    devices = await scan_for_ble_devices(timeout=15.0)
    #遍历结果查找指定serial_number
    for device in devices:
        if device.get("serial_number") == serial_to_find:
            return device["address"]
    return None


#BLE连接部分
def test_no_scan(ble_mac_address):
    bleconnector = BLEConnector(ble_mac_address)
    bleconnector.run()


if __name__ == "__main__":
    serial_number = "804AF2B00848E"  # 我的设备SN码
    address = None
    max_retries = 5
    for attempt in range(1, max_retries + 1):
        print(f"--- 尝试连接设备 ({attempt}/{max_retries}) ---")
            # 1. 尝试获取地址
        address = asyncio.run(get_address_by_serial(serial_number))

        if address:
                # 2. 如果找到地址，执行连接/控制，然后跳出循环
            print(f"✅ 找到设备 {serial_number} 对应的 Address: {address}")
            # test_no_scan(address)
            break
        else:
             # 3. 如果未找到，打印信息
            print(f"❌ 未找到 Serial Number {serial_number} 对应的设备.")
            if attempt < max_retries:
                # 在下次尝试前等待一段时间，避免过于频繁的扫描
                print("等待 5 秒后重试...")
                time.sleep(5)

    if not address:
        print(f"🚨 达到最大重试次数 {max_retries}，仍未找到设备 {serial_number}。程序结束。")
