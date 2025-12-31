import pyvisa
import time
import csv
import random
import sys
import os
from typing import Optional, List, Tuple
import pytest
from unittest.mock import MagicMock, patch

# 全局配置
DEBUG_MODE = True  # 设置为True使用虚拟设备，False连接真实设备
VIRTUAL_DEVICE_ID = "USB0::0xFFFF::0x1234::MY_VIRTUAL::INSTR"


def connect_to_instrument(debug: bool = DEBUG_MODE) -> Optional[pyvisa.Resource]:
    """连接测量仪器（支持虚拟设备）"""
    try:
        if debug:
            print("===== 调试模式：使用虚拟设备 =====")
            # 创建虚拟设备
            virtual_device = VirtualDevice(VIRTUAL_DEVICE_ID)
            print(f"已创建虚拟设备: {VIRTUAL_DEVICE_ID}")
            return virtual_device

        print("===== 连接真实设备模式 =====")
        rm = pyvisa.ResourceManager()

        # 显示PyVISA信息
        print(f"PyVISA版本: {pyvisa.__version__}")
        print(f"PyVISA后端: {rm}")

        # 列出所有可用设备
        resources = rm.list_resources()
        print(f"检测到的设备: {resources}")

        if not resources:
            print("未检测到设备！")
            return None

        # 连接第一个检测到的设备
        device = rm.open_resource(resources[0])
        device.timeout = 5000  # 设置超时5秒
        idn = device.query("*IDN?")  # 查询设备ID
        print(f"已连接: {idn.strip()}")
        return device

    except pyvisa.VisaIOError as e:
        print(f"连接失败: {e}")
        return None


def measure_voltage(device: pyvisa.Resource,
                    num_samples: int = 10,
                    interval: float = 0.5) -> List[Tuple[str, float]]:
    """测量电压并记录数据"""
    results = []

    # 配置测量
    device.write(":CONF:VOLT:DC")  # 配置直流电压测量

    print(f"开始采集 {num_samples} 个电压样本...")
    for i in range(num_samples):
        try:
            device.write(":READ?")  # 执行单次测量
            voltage_str = device.read().strip()

            # 尝试将读数转换为浮点数
            try:
                voltage = float(voltage_str)
            except ValueError:
                print(f"警告: 无法解析电压值 '{voltage_str}'，使用默认值0.0")
                voltage = 0.0

            timestamp = time.strftime("%Y-%m-%d %H:%M:%S")

            print(f"采样 {i + 1}/{num_samples}: {voltage:.6f} V")
            results.append((timestamp, voltage))

            time.sleep(interval)

        except pyvisa.VisaIOError as e:
            print(f"采样 {i + 1}/{num_samples} 时出错: {e}")
            # 添加错误标记的数据点
            timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
            results.append((timestamp, -9999.0))  # 使用特殊值标记错误

    return results


def save_to_csv(data: List[Tuple[str, float]],
                filename: str = "measurement_results.csv") -> None:
    """保存数据到CSV文件"""
    try:
        with open(filename, 'w', newline='') as file:
            writer = csv.writer(file)
            writer.writerow(["Timestamp", "Voltage (V)"])
            writer.writerows(data)
        print(f"数据已保存至 {filename}")
        print(f"共保存 {len(data)} 条记录")
    except IOError as e:
        print(f"保存文件时出错: {e}")


class VirtualDevice:
    """虚拟设备类，模拟真实设备的行为"""

    def __init__(self, resource_name: str):
        self.resource_name = resource_name
        self.timeout = 5000
        self._voltage_range = (0.0, 10.0)  # 模拟电压范围
        self._last_voltage = 5.0  # 初始电压值

    def write(self, command: str):
        """模拟发送命令到设备"""
        if DEBUG_MODE:
            print(f"[VIRTUAL] 发送命令: {command}")

    def read(self) -> str:
        """模拟从设备读取数据"""
        if DEBUG_MODE:
            # 生成略微变化的电压值
            voltage = self._last_voltage + random.uniform(-0.1, 0.1)
            # 保持在合理范围内
            voltage = max(self._voltage_range[0], min(voltage, self._voltage_range[1]))
            self._last_voltage = voltage
            return f"{voltage:.6f}"

    def query(self, command: str) -> str:
        """模拟查询命令（写+读）"""
        self.write(command)
        return self.read()

    def close(self):
        """模拟关闭设备连接"""
        if DEBUG_MODE:
            print("[VIRTUAL] 关闭设备连接")

    def __repr__(self):
        return f"<VirtualDevice: {self.resource_name}>"


def run_measurement():
    """运行主测量程序"""
    print("\n===== 仪器控制程序启动 =====")

    # 连接仪器
    instrument = connect_to_instrument()

    if not instrument:
        print("无法连接设备，程序退出")
        return

    try:
        # 执行测量
        measurement_data = measure_voltage(
            instrument,
            num_samples=5,  # 调试时使用较少的样本
            interval=0.3
        )

        # 保存结果
        save_to_csv(measurement_data)

    except Exception as e:
        print(f"程序执行出错: {e}")
        import traceback
        traceback.print_exc()

    finally:
        # 断开连接
        instrument.close()
        print("已断开仪器连接")
        print("===== 程序结束 =====")


# pytest测试用例
def test_no_device():
    """测试无设备连接的情况"""
    with patch('pyvisa.ResourceManager') as mock_rm:
        # 配置模拟对象
        mock_rm_instance = mock_rm.return_value
        mock_rm_instance.list_resources.return_value = []

        # 调用函数
        device = connect_to_instrument(debug=False)

        # 断言
        assert device is None, "没有设备时应返回None"
        print("测试无设备情况通过")


def test_virtual_device():
    """测试虚拟设备"""
    # 创建虚拟设备
    device = VirtualDevice(VIRTUAL_DEVICE_ID)

    # 测试ID查询
    idn = device.query("*IDN?")
    print(f"虚拟设备ID查询: {idn}")

    # 测试测量
    device.write(":CONF:VOLT:DC")
    voltage = device.read()
    print(f"虚拟设备电压测量: {voltage}")

    assert voltage is not None, "应返回电压值"
    print("测试虚拟设备通过")


def test_measurement_logic():
    """测试测量逻辑"""
    # 创建虚拟设备
    device = VirtualDevice(VIRTUAL_DEVICE_ID)

    # 执行测量
    data = measure_voltage(device, num_samples=3, interval=0.1)

    # 验证结果
    assert len(data) == 3, "应返回3个数据点"
    for timestamp, voltage in data:
        assert isinstance(timestamp, str), "时间戳应为字符串"
        assert isinstance(voltage, float), "电压值应为浮点数"
        assert -10.0 <= voltage <= 10.0, "电压值应在合理范围内"

    print(f"测量数据: {data}")
    print("测试测量逻辑通过")


def test_save_to_csv():
    """测试保存到CSV"""
    # 创建测试数据
    test_data = [
        ("2023-01-01 10:00:00", 3.1415),
        ("2023-01-01 10:00:01", 2.7182),
        ("2023-01-01 10:00:02", 1.6180)
    ]

    # 保存到临时文件
    test_filename = "test_output.csv"
    save_to_csv(test_data, test_filename)

    # 验证文件内容
    try:
        with open(test_filename, 'r') as file:
            content = file.read()
            print(f"CSV文件内容:\n{content}")

            # 验证标题行
            assert "Timestamp,Voltage (V)" in content

            # 验证数据行
            for timestamp, voltage in test_data:
                assert timestamp in content
                assert str(voltage) in content

        print("测试保存CSV通过")
    finally:
        # 清理测试文件
        if os.path.exists(test_filename):
            os.remove(test_filename)


def run_tests():
    """运行所有测试"""
    print("\n===== 开始运行测试 =====")
    # 使用pytest运行当前模块中的所有测试
    import pytest
    result = pytest.main(["-v", __file__])
    print("===== 测试完成 =====")
    return result == 0


if __name__ == "__main__":
    # 检查命令行参数
    if "--test" in sys.argv:
        # 运行测试模式
        success = run_tests()
        sys.exit(0 if success else 1)
    else:
        # 运行主测量程序
        run_measurement()
