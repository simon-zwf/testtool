#!/usr/bin/env python3
"""
Android蓝牙开关自动化测试脚本（简洁版）
只在第一次测试时打开控制中心，后续直接点击蓝牙按钮
"""

import time
import logging
import subprocess
import sys

# 设置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)


class BluetoothToggleTester:
    def __init__(self, bluetooth_x, bluetooth_y):
        self.test_count = 0
        self.success_count = 0
        self.logger = logging.getLogger(__name__)
        self.bluetooth_x = bluetooth_x
        self.bluetooth_y = bluetooth_y

    def run_adb_command(self, command):
        """运行ADB命令"""
        try:
            result = subprocess.run(command, shell=True, capture_output=True, text=True)
            return result.returncode == 0
        except Exception:
            return False

    def get_screen_size(self):
        """获取屏幕尺寸"""
        result = subprocess.run("adb shell wm size", shell=True, capture_output=True, text=True)
        if "Physical size:" in result.stdout:
            size_str = result.stdout.split(": ")[1].strip()
            return map(int, size_str.split("x"))
        return 1080, 2340  # 默认值

    def open_control_center(self, width, height):
        """从屏幕右上角下滑打开控制中心"""
        self.logger.info("打开控制中心")
        start_x = int(width * 0.9)  # 右侧10%位置
        start_y = 10  # 从顶部开始
        end_x = start_x
        end_y = int(height * 0.3)  # 下滑到屏幕30%处

        command = f"adb shell input swipe {start_x} {start_y} {end_x} {end_y} 500"
        return self.run_adb_command(command)

    def tap_bluetooth_button(self):
        """点击蓝牙按钮"""
        self.logger.info(f"点击蓝牙按钮 ({self.bluetooth_x}, {self.bluetooth_y})")
        command = f"adb shell input tap {self.bluetooth_x} {self.bluetooth_y}"
        return self.run_adb_command(command)

    def run_test_cycle(self, count=3):
        """运行完整测试周期"""
        self.logger.info(f"开始蓝牙开关测试，计划执行 {count} 次")

        # 获取屏幕尺寸
        width, height = self.get_screen_size()

        # 第一次测试：打开控制中心并点击蓝牙按钮
        if self.open_control_center(width, height):
            time.sleep(1)  # 等待控制中心展开
            if self.tap_bluetooth_button():
                self.success_count += 1
                self.logger.info("第 1 次测试: 成功")
            else:
                self.logger.error("第 1 次测试: 失败")
        else:
            self.logger.error("第 1 次测试: 打开控制中心失败")

        self.test_count = 1

        # 后续测试：直接点击蓝牙按钮
        for i in range(1, count):
            self.test_count += 1
            self.logger.info(f"开始第 {self.test_count} 次测试")

            if self.tap_bluetooth_button():
                self.success_count += 1
                self.logger.info(f"第 {self.test_count} 次测试: 成功")
            else:
                self.logger.error(f"第 {self.test_count} 次测试: 失败")

            # 等待3秒
            time.sleep(3)

        # 输出测试报告
        self.logger.info("=" * 50)
        self.logger.info(f"测试完成! 成功次数: {self.success_count}/{self.test_count}")
        self.logger.info(f"成功率: {self.success_count / self.test_count * 100:.2f}%")
        self.logger.info("=" * 50)


def main():
    # 检查是否提供了蓝牙按钮坐标
    if len(sys.argv) < 3:
        print("请提供蓝牙按钮的坐标")
        print("用法: python bluetooth_toggle_simple.py <x坐标> <y坐标>")
        print("示例: python bluetooth_toggle_simple.py 728 630")
        sys.exit(1)

    bluetooth_x = int(sys.argv[1])
    bluetooth_y = int(sys.argv[2])

    # 创建测试器实例
    tester = BluetoothToggleTester(bluetooth_x, bluetooth_y)

    # 运行测试
    tester.run_test_cycle(5)


if __name__ == "__main__":
    main()