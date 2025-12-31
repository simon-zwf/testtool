from enum import Enum, auto
import logging
import  logging.config
import yaml
from pyexpat.errors import messages
import os
log_dir = os.path.dirname("logs/power.log")  # 提取文件夹路径
os.makedirs(log_dir, exist_ok=True)  # 自动创建文件夹
# # 配置日志：同时输出到控制台和文件，设置日志格式
# logging.basicConfig(
#     level=logging.INFO,  # 日志级别：DEBUG < INFO < WARNING < ERROR
#     format="%(asctime)s - %(levelname)s - %(message)s",  # 日志格式：时间 - 级别 - 消息
#     handlers=[
#         logging.StreamHandler(),  # 输出到控制台
#         logging.FileHandler("../logs/power_state.log", encoding="utf-8")  # 输出到文件
#     ]
# )




def setup_logging():
    log_config_file = "../config/logging_config.yaml"
    try:
        with open(log_config_file, 'r', encoding = "UTF-8") as f:
            log_config = yaml.safe_load(f)
        logging.config.dictConfig(log_config)
        logging.info("日志系统已通过配置文件初始化")
    except FileNotFoundError:
        print("错误：日志配置文件 logging_config.yaml 未找到")
    except Exception as e:
        print(f"错误：加载日志配置失败 - {str(e)}")

class PowerState(Enum):
    OFF = auto()
    SLEEP = auto()
    IDLE = auto()
    ON= auto


class DeviceController:
    def __init__(self):
        self.state = PowerState.IDLE
        self.logger = logging.getLogger("device console")
        self.logger.info(f"初始化设备控制器，初始状态: {self.state.name}")

    def transition(self, new_state):
        allowed = {
            PowerState.IDLE: [PowerState.OFF, PowerState.SLEEP],
            PowerState.SLEEP: [PowerState.IDLE],
            PowerState.OFF: [PowerState.IDLE]
        }
        if new_state in allowed.get(self.state, []):
            old_state = self.state
            self.state = new_state
            #print(f"状态转换成功: {old_state.name} -> {new_state.name}")
            self.logger.info(f"状态转换成功: {old_state.name} -> {new_state.name}")
            self.logger.debug(f'this debug{old_state.name} -> {new_state.name}')


            return True
        #print(f"状态转换失败: 不允许从 {self.state.name} 转换到 {new_state.name}")
        self.logger.info(f'状态转换失败: 不允许从 {self.state.name} 转换到 {new_state.name}')
        return False

    def get_current_state(self):
        return self.state.name

class TestFalseInput(Exception):
    pass

# 完整测试
if __name__ == "__main__":
    setup_logging()
    controller = DeviceController()
    controller.get_current_state()
    controller.transition(PowerState.SLEEP)
    # print("初始状态:", controller.get_current_state())
    # print(controller.transition(PowerState.SLEEP))  # 成功
    # print(controller.transition(PowerState.OFF))    # 失败
    # print(controller.transition(PowerState.IDLE))   # 成功
    # print(controller.transition(PowerState.OFF))    # 成功
    # print(controller.transition(PowerState.SLEEP))  # 失败
    # print("最终状态:", controller.get_current_state())