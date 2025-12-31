#!/usr/bin/env python3
"""
蓝牙回连测试（简化版）：关闭→打开→OCR识别设备名
"""

import time
import logging
import subprocess
import sys
import os
from PIL import Image
import pytesseract

# 日志配置
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - [简化版] %(message)s',
    handlers=[
        logging.FileHandler("bluetooth_reconnect_simple.log", encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)

# 配置Tesseract路径（Windows需修改，Mac/Linux一般无需）
TESSERACT_PATH = r'C:\Program Files\Tesseract-OCR\tesseract.exe'  # 替换为你的安装路径
pytesseract.pytesseract.tesseract_cmd = TESSERACT_PATH


class BluetoothTester:
    def __init__(self, bluetooth_x, bluetooth_y, device_name, ocr_area):
        self.bluetooth_x = bluetooth_x      # 蓝牙按钮点击坐标
        self.bluetooth_y = bluetooth_y
        self.device_name = device_name      # 目标设备名（如“Infinix AI Glasses”）
        self.ocr_area = ocr_area            # 蓝牙文字OCR区域（x1,y1,x2,y2）
        self.screenshot = "control_center.png"
        self.logger = logging.getLogger(__name__)

    def run_adb(self, cmd):
        """执行ADB命令，返回（输出、错误、退出码）"""
        try:
            res = subprocess.run(
                cmd, shell=True, capture_output=True, text=True, timeout=15
            )
            return res.stdout.strip(), res.stderr.strip(), res.returncode
        except Exception as e:
            return "", str(e), -1

    def open_control_center(self):
        """从右上角下滑打开控制中心"""
        self.logger.info("→ 打开控制中心（右上角下滑）")
        stdout, _, rc = self.run_adb("adb shell wm size")
        width, height = 1080, 2340  # 默认尺寸
        if rc == 0 and "Physical size" in stdout:
            try:
                width, height = map(int, re.search(r"(\d+)x(\d+)", stdout).groups())
            except:
                pass
        # 滑动参数：右上角→下滑30%高度
        swipe_cmd = f"adb shell input swipe {int(width*0.9)} 10 {int(width*0.9)} {int(height*0.3)} 500"
        _, stderr, rc = self.run_adb(swipe_cmd)
        time.sleep(2)  # 等待展开
        return rc == 0

    def capture_screenshot(self):
        """截图控制中心并拉取到电脑"""
        self.logger.info("→ 截图控制中心")
        # 手机端截图
        _, err1, rc1 = self.run_adb(f"adb shell screencap -p /sdcard/{self.screenshot}")
        if rc1 != 0:
            self.logger.error(f"手机截图失败: {err1}")
            return False
        # 拉取到电脑
        _, err2, rc2 = self.run_adb(f"adb pull /sdcard/{self.screenshot} .")
        if rc2 != 0:
            self.logger.error(f"拉取截图失败: {err2}")
            return False
        # 删除手机端截图
        self.run_adb(f"adb shell rm /sdcard/{self.screenshot}")
        return os.path.exists(self.screenshot)

    def ocr_detect_device(self):
        """OCR识别蓝牙旁是否显示设备名"""
        if not self.capture_screenshot():
            return False
        try:
            with Image.open(self.screenshot) as img:
                x1, y1, x2, y2 = self.ocr_area
                crop = img.crop((x1, y1, x2, y2))  # 裁剪文字区域
                text = pytesseract.image_to_string(crop, lang='chi_sim+eng').strip()
                self.logger.info(f"OCR识别结果: [{text}]")
                return self.device_name in text
        except Exception as e:
            self.logger.error(f"OCR失败: {str(e)}")
            return False

    def tap_bluetooth(self, action):
        """点击蓝牙按钮"""
        self.logger.info(f"→ 点击蓝牙（{action}），坐标: ({self.bluetooth_x}, {self.bluetooth_y})")
        _, err, rc = self.run_adb(f"adb shell input tap {self.bluetooth_x} {self.bluetooth_y}")
        time.sleep(2)  # 等待状态切换
        return rc == 0

    def run_single_test(self):
        """单次测试：开控制中心→关蓝牙→开蓝牙→OCR识别"""
        try:
            # 1. 开控制中心
            if not self.open_control_center():
                return False, "控制中心打开失败"
            # 2. 关蓝牙（设备必然断开）
            if not self.tap_bluetooth("关闭"):
                return False, "关闭蓝牙失败"
            # 3. 开蓝牙（开始回连）
            if not self.tap_bluetooth("打开"):
                return False, "打开蓝牙失败"
            # 4. 给3秒回连时间
            self.logger.info("→ 等待设备回连（3秒）")
            time.sleep(3)
            # 5. OCR识别是否回连
            is_connected = self.ocr_detect_device()
            return is_connected, "回连成功" if is_connected else "回连失败"
        except Exception as e:
            return False, f"测试异常: {str(e)}"

    def run_tests(self, total=5):
        """多次测试并输出报告"""
        success = 0
        self.logger.info("="*60)
        self.logger.info("[简化版] 蓝牙回连测试启动")
        self.logger.info(f"目标设备: {self.device_name} | 蓝牙坐标: ({self.bluetooth_x}, {self.bluetooth_y})")
        self.logger.info(f"OCR区域: {self.ocr_area} | 测试次数: {total}")
        self.logger.info("="*60)

        for i in range(1, total+1):
            self.logger.info(f"\n=== 第 {i}/{total} 次测试 ===")
            is_ok, msg = self.run_single_test()
            if is_ok:
                success += 1
                self.logger.info(f"→ ✅ {msg}")
            else:
                self.logger.info(f"→ ❌ {msg}")
            time.sleep(3)  # 循环间隔

        # 报告
        self.logger.info("\n" + "="*60)
        self.logger.info(f"总测试: {total} | 成功: {success}")
        rate = (success / total) * 100 if total > 0 else 0
        self.logger.info(f"成功率: {rate:.2f}%")
        final = success == total
        self.logger.info("✅ 所有回连成功" if final else "❌ 存在回连失败")
        self.logger.info("="*60)

        # 删除临时截图
        if os.path.exists(self.screenshot):
            os.remove(self.screenshot)
        return final


def main():
    # 检查依赖
    try:
        import pytesseract
        from PIL import Image  # Pillow 的 Image 需从 PIL 导入
    except ImportError:
        print("请安装依赖：pip install pytesseract pillow")
        sys.exit(1)

    # 参数校验
    if len(sys.argv) < 6:
        print("用法：python 脚本.py 蓝牙X 蓝牙Y OCRx1 OCRy1 OCRx2 OCRy2 [设备名]")
        print("示例：python 脚本.py 762 740 730 630 900 700 \"Infinix AI Glasses\"")
        sys.exit(1)

    # 解析参数
    try:
        bt_x = int(sys.argv[1])
        bt_y = int(sys.argv[2])
        ocr_x1 = int(sys.argv[3])
        ocr_y1 = int(sys.argv[4])
        ocr_x2 = int(sys.argv[5])
        ocr_y2 = int(sys.argv[6])
        device = sys.argv[7] if len(sys.argv) > 7 else "Infinix AI Glasses"
        ocr_area = (ocr_x1, ocr_y1, ocr_x2, ocr_y2)
    except ValueError:
        print("坐标必须为整数！")
        sys.exit(1)

    # 运行测试
    tester = BluetoothTester(bt_x, bt_y, device, ocr_area)
    result = tester.run_tests(total=5)
    sys.exit(0 if result else 1)


if __name__ == "__main__":
    main()