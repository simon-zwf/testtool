import pyvisa as visa
import threading
import time

def control_instrument(resource, name):
    """线程函数：控制单台仪器的逻辑"""
    rm = visa.ResourceManager('@py')  # 每个线程建议创建独立的ResourceManager
    inst = rm.open_resource(resource)
    try:
        if name == "测量仪":
            print(f"{name}开始测量...")
            inst.write("MEAS:VOLT:DC?")
            time.sleep(2)  # 模拟测量耗时
            volt = inst.read()
            print(f"{name}测量结果：{volt}")
        elif name == "信号源":
            print(f"{name}开始输出信号...")
            inst.write("FREQ 5000")
            inst.write("OUTP ON")
            time.sleep(3)  # 模拟输出持续时间
            inst.write("OUTP OFF")
            print(f"{name}已关闭输出")
    finally:
        inst.close()

# 主逻辑
if __name__ == "__main__":
    rm = visa.ResourceManager('@py')
    resources = rm.list_resources()  # 假设前两个资源是目标仪器
    if len(resources) < 2:
        print("至少需要两台仪器")
        exit()

    # 创建两个线程，分别控制两台仪器
    t1 = threading.Thread(
        target=control_instrument,
        args=(resources[0], "测量仪")
    )
    t2 = threading.Thread(
        target=control_instrument,
        args=(resources[1], "信号源")
    )

    # 启动线程（并行执行）
    t1.start()
    t2.start()

    # 等待所有线程完成
    t1.join()
    t2.join()
    print("所有仪器操作完成")