# ==================================================
# !/usr/bin/env python
# @Author: simon.zhang
# @Date: 2025/8/11 16:27
# @FileName: test_ble_connector.py
# @Email: wangfu_zhang@ggec.com.cn
# ==================================================
# PST测试框架中的调用示例
# import sys
#
# from ble_connector import BLEConnector
#
#
# def ble_wakeup_test():
#     """BLE唤醒测试用例"""
#     # 初始化连接器
#     connector = BLEConnector(
#         ble_device_name="S58 0848 LE",
#         hci_device="hci1"
#     )
#
#     # 执行连接测试
#     success = connector.run()
#
#     # 获取测试结果
#     result = connector.get_connection_result()
#     print(f"BLE唤醒测试结果: {'成功' if success else '失败'}")
#     print(f"MAC地址: {result['mac_address']}")
#
#     return success
#
#
# # 集成到PST测试套件
# if __name__ == "__main__":
#     test_result = ble_wakeup_test()
#     sys.exit(0 if test_result else 1)

def loan_calculator():
    loan_amount = float(input(f"请输入贷款金额元："))
    loan_term_months = int(input(f"please input loan term(months):"))
    annual_interest_rate = float(input(f"please input year rate:"))
    #计算月利率
    monthly_interest_rate = annual_interest_rate/12/100

    numerater = loan_amount*monthly_interest_rate*(1+monthly_interest_rate)**loan_term_months
    denominator = (1+monthly_interest_rate)**loan_term_months-1
    monthly_payment = numerater/denominator



    #计算总利息和还款总额
    total_payment = monthly_payment*loan_term_months
    total_interest = total_payment- loan_amount #利息总和

    #格式化输出结果
    print(f"\n=======还款计划========")
    print(f"每月应还:{monthly_payment:.2f}元")
    print(f"利息总额：{total_interest:.2f}元")
    print(f"还款总额：{total_payment:.2f}元")

if  __name__ == "__main__":
    loan_calculator()

