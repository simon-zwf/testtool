#!/bin/bash
# UUT睡眠测试 - Shell脚本版 (最可靠)
# 使用系统telnet客户端处理所有协议协商

HOST="200.1.1.4"
PORT="10006"
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
LOG_FILE="UUT_SHELL_${TIMESTAMP}.log"

echo "========================================"
echo "UUT睡眠测试 - Shell脚本版"
echo "开始时间: $(date)"
echo "日志文件: $LOG_FILE"
echo "========================================"

{
    # 写入日志头
    echo "=== UUT设备控制台日志 (Shell脚本版) ==="
    echo "测试开始: $(date)"
    echo "目标: $HOST:$PORT"
    echo "========================================"
    echo ""
    
    # 使用telnet连接，并发送命令
    # 注意：这里用 sleep 给每个命令足够的执行时间
    (
        sleep 2  # 等待连接建立
        echo ""  # 发送回车
        sleep 1
        echo "echo DeviceSuspendRequested > /tmp/sonospowercoordinator_USR1_cmd_OVERRIDE"
        sleep 3  # 重要：给命令执行和输出留足时间
        echo "killall -SIGUSR1 sonospowercoordinator"
        sleep 8  # 非常重要：给设备输出睡眠日志留足时间
        # 此后不再发送任何字符，完全静默
        # 保持连接打开以接收后续唤醒日志
        sleep 300  # 静默监控300秒（可调整）
    ) | telnet "$HOST" "$PORT" 2>&1
    
    echo ""
    echo "========================================"
    echo "测试结束: $(date)"
    echo "========================================"
} > "$LOG_FILE"

echo ""
echo "测试完成！"
echo "请检查日志文件: $LOG_FILE"
echo ""
echo "快速检查命令:"
echo "  tail -n 100 $LOG_FILE"
echo "  grep -n 'RTC\|WIFI_WAKEUP\|BLE_WAKEUP' $LOG_FILE"
