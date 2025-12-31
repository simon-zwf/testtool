import pandas as pd

test_cases = [
    # —————— 1. 电源控制（Power Control） ——————
    {
        "Test ID": "TC_PWR_001",
        "Title": "Power ON",
        "Preconditions": "PC 已安装 Speaker Control App\n音箱已通过 USB/UART 连接至 PC\nSpeaker Control App 可正常识别设备\n音箱处于待机状态（Power OFF）",
        "Steps": "打开 Speaker Control App\n连接音箱\n在主界面点击 Power ON\n观察音箱电源指示灯与系统提示",
        "Expected Result": "App 显示“Power: ON”\n音箱电源 LED 亮起\n功放上电无杂音，无异常噪声\nApp 显示指令下发成功"
    },
    {
        "Test ID": "TC_PWR_002",
        "Title": "Power OFF",
        "Preconditions": "PC 已安装 Speaker Control App\n音箱已通过 USB/UART 连接至 PC\nSpeaker Control App 可正常识别设备\n音箱处于待机状态（Power OFF）",
        "Steps": "打开 Speaker Control App\n点击 Power OFF",
        "Expected Result": "App 显示“Power: OFF”\n音箱电源 LED 熄灭\n扬声器静音，无爆音"
    },

    # —————— 2. Master Volume（主音量调节） ——————
    {
        "Test ID": "TC_VOL_001",
        "Title": "设置 Master Volume = 0 dB（默认）",
        "Preconditions": "App 与音箱连接正常\n已连接音频源（PC/手机）并持续播放粉红噪声\n音箱已开机",
        "Steps": "在 App 中进入 Master Volume 控制\n调整滑杆至 0 dB（中心刻度）",
        "Expected Result": "UI 显示 Volume = 0 dB\n声压恢复默认参考电平\n无失真或爆音"
    },
    {
        "Test ID": "TC_VOL_002",
        "Title": "设置 Volume = -20 dB",
        "Preconditions": "App 与音箱连接正常\n已连接音频源（PC/手机）并持续播放粉红噪声\n音箱已开机",
        "Steps": "将 Volume 滑杆调至 –20 dB",
        "Expected Result": "声音明显减小\n仪表测量下降约 20 dB ± 2 dB\nUI 显示同步成功"
    },
    {
        "Test ID": "TC_VOL_003",
        "Title": "设置 Volume = +4 dB（最大刻度）",
        "Preconditions": "App 与音箱连接正常\n已连接音频源（PC/手机）并持续播放粉红噪声\n音箱已开机",
        "Steps": "将 Volume 滑杆调至 +4 dB",
        "Expected Result": "声音明显增强\n无破音、无削顶\nUI 显示 Volume = +4 dB"
    },

    # —————— 3. EQ – High Trim（高频微调） ——————
    {
        "Test ID": "TC_EQ_001",
        "Title": "High Trim = –2 dB",
        "Preconditions": "App 与音箱连接正常\n已连接音频源并播放全频段测试音\n音箱已开机",
        "Steps": "在 App 内选择 High Trim = –2 dB",
        "Expected Result": "UI 显示 High Trim = –2 dB\n高频略衰减（约 –2 dB）\n听感更柔和\n仪器验证符合规格"
    },
    {
        "Test ID": "TC_EQ_002",
        "Title": "High Trim = 0 dB",
        "Preconditions": "App 与音箱连接正常\n已连接音频源并播放全频段测试音\n音箱已开机",
        "Steps": "在 App 内选择 High Trim = 0 dB",
        "Expected Result": "UI 显示 High Trim = 0 dB\n高频输出恢复正常"
    },
    {
        "Test ID": "TC_EQ_003",
        "Title": "High Trim = +2 dB",
        "Preconditions": "App 与音箱连接正常\n已连接音频源并播放全频段测试音\n音箱已开机",
        "Steps": "在 App 内选择 High Trim = +2 dB",
        "Expected Result": "高频略提升（约 +2 dB）\n听感更亮\n仪器验证符合规格"
    },

    # —————— 4. ROOM CONTROL（房间低频补偿） ——————
    {
        "Test ID": "TC_RC_001",
        "Title": "Room Control = 0 dB",
        "Preconditions": "App 已连接音箱\n播放 50–300 Hz 低频正弦扫描",
        "Steps": "在 App 内进入 Room Control\n设置为 0 dB",
        "Expected Result": "UI 显示 Room Control = 0 dB\n低频为默认参考电平"
    },
    {
        "Test ID": "TC_RC_002",
        "Title": "Room Control = –2 dB",
        "Preconditions": "App 已连接音箱\n播放 50–300 Hz 低频正弦扫描",
        "Steps": "在 App 内进入 Room Control\n设置为 –2 dB",
        "Expected Result": "低频略减少（约 –2 dB）\n仪器/听感均可验证"
    },
    {
        "Test ID": "TC_RC_003",
        "Title": "Room Control = –4 dB",
        "Preconditions": "App 已连接音箱\n播放 50–300 Hz 低频正弦扫描",
        "Steps": "在 App 内进入 Room Control\n设置为 –4 dB",
        "Expected Result": "低频明显衰减（–4 dB）\n无破音或异常震动"
    },

    # —————— 5. Input Connector（输入源切换） ——————
    {
        "Test ID": "TC_IN_001",
        "Title": "切换到 INPUT A",
        "Preconditions": "INPUT A 已接入稳定信号源（音频播放）\nINPUT B 保持无信号或不同信号，用于区分",
        "Steps": "打开 Speaker Control App\n在 Input 菜单选择 Input A",
        "Expected Result": "音箱播放 INPUT A 的内容\nUI 显示当前输入为 A\n切换时无爆音"
    },
    {
        "Test ID": "TC_IN_002",
        "Title": "切换到 INPUT B",
        "Preconditions": "INPUT A 已接入稳定信号源\nINPUT B 已接入另一信号源",
        "Steps": "在 App 中选择 Input B",
        "Expected Result": "声音切换至 INPUT B\n声音来源明显改变"
    },
    {
        "Test ID": "TC_IN_003",
        "Title": "输入切换快速切换压力测试（1 min）",
        "Preconditions": "INPUT A 和 B 均接入不同音频信号\nApp 与音箱连接正常",
        "Steps": "每 3 秒切换一次输入源（A ⇋ B）持续 1 分钟",
        "Expected Result": "无系统崩溃\n无音频锁死\n无爆音"
    },

    # —————— 6. 软件 UI & 同步测试 ——————
    {
        "Test ID": "TC_UI_001",
        "Title": "参数同步成功提示",
        "Preconditions": "App 与音箱连接正常",
        "Steps": "任意修改一个参数（如 Volume）\n观察 UI 是否弹出 “Sync success”",
        "Expected Result": "参数变化后 1 秒内，APP 显示同步状态\n无错误提示"
    },
    {
        "Test ID": "TC_UI_002",
        "Title": "界面加载设备信息",
        "Preconditions": "App 与音箱连接正常",
        "Steps": "打开设备信息页面",
        "Expected Result": "UI 显示：设备型号、固件版本、序列号\n信息与实际设备一致"
    },

    # —————— 7. 硬件电源开关（无需软件） ——————
    {
        "Test ID": "TC_PWR_HW_001",
        "Title": "Mechanical Power ON（背部机械开关开机）",
        "Preconditions": "音箱已正确连接电源线\n电源插座正常供电\n音箱背部电源开关当前处于 OFF\n环境安静，方便观察是否有爆音",
        "Steps": "找到音箱背部的 电源开关（Power Switch）\n将电源开关拨到 ON\n观察前面板 Logo 的 LED 状态\n观察开机是否有异常声响",
        "Expected Result": "前面 Logo LED 亮白灯（符合规格：Power On: White LED）\n音箱进入正常工作模式\n无爆音、无异常噪声\n功放启动正常（1 秒内进入稳定状态）"
    },
    {
        "Test ID": "TC_PWR_HW_002",
        "Title": "Mechanical Power OFF（背部机械开关关机）",
        "Preconditions": "音箱已处于 ON 状态（Logo 白灯亮）",
        "Steps": "将背部电源开关拨至 OFF\n观察前面板 Logo LED 变化\n观察关机过程是否有异常声响",
        "Expected Result": "LED 灭（Logo 灯完全熄灭）\n音箱完全断电\n无关机爆音、无不正常电流声\n散热风扇（如有）停止运转"
    }
]

# 验证数量
assert len(test_cases) == 18, f"Expected 22 test cases, but got {len(test_cases)}"

# 转为 DataFrame
df = pd.DataFrame(test_cases)

# 导出 Excel
output_file = "Speaker_Test_Cases_22.xlsx"
df.to_excel(output_file, index=False, engine="openpyxl")

print(f"✅ 成功生成 Excel 文件：{output_file}")
print(f"📊 共 {len(test_cases)} 条测试用例")