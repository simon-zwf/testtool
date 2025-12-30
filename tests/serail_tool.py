import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox, filedialog
import serial
import serial.tools.list_ports
from threading import Thread, Event, Lock
import queue
import os
import datetime
import time


class SerialTool:
    def __init__(self, root):
        self.root = root
        self.root.title("串口通信工具 v2.9（修复版）")
        self.root.geometry("800x650")
        self.root.resizable(True, True)

        # 串口相关变量
        self.serial_port = None
        self.serial_thread = None
        self.stop_event = Event()
        self.data_queue = queue.Queue(maxsize=1000)
        self.serial_lock = Lock()  # 串口操作锁，防止并发访问
        self.receive_buffer = b''  # 接收数据缓冲区，用于合并短时间内的数据包

        # 日志保存相关变量
        self.save_log = False
        self.log_file_path = ""
        self.log_file = None

        # 显示选项
        self.hex_display_var = tk.BooleanVar(value=True)  # 十六进制显示
        self.timestamp_var = tk.BooleanVar(value=True)  # 时间戳显示
        self.hex_send_var = tk.BooleanVar(value=False)  # 十六进制发送
        self.show_receive_var = tk.BooleanVar(value=True)  # 显示接收数据

        # 发送历史相关变量
        self.send_history = []  # 存储发送历史
        self.max_history_size = 20  # 最大历史记录数量

        # 创建UI
        self.create_widgets()

        # 初始扫描可用串口
        self.scan_ports()

        # 启动数据更新线程
        self.update_thread = Thread(target=self.update_ui, daemon=True)
        self.update_thread.start()

        # 关闭窗口时清理资源
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)

    def create_widgets(self):
        # 创建主框架
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)

        # 串口设置区域
        settings_frame = ttk.LabelFrame(main_frame, text="串口设置", padding="10")
        settings_frame.pack(fill=tk.X, padx=5, pady=5)

        # 串口选择
        ttk.Label(settings_frame, text="串口:").grid(row=0, column=0, sticky=tk.W, padx=5, pady=5)
        self.port_combobox = ttk.Combobox(settings_frame, width=15, state="readonly")
        self.port_combobox.grid(row=0, column=1, sticky=tk.W, padx=5, pady=5)

        # 刷新按钮
        self.refresh_btn = ttk.Button(settings_frame, text="刷新", width=8, command=self.scan_ports)
        self.refresh_btn.grid(row=0, column=2, padx=5, pady=5)

        # 波特率选择
        ttk.Label(settings_frame, text="波特率:").grid(row=0, column=3, sticky=tk.W, padx=5, pady=5)
        self.baud_combobox = ttk.Combobox(settings_frame, width=10, values=[
            "300", "600", "1200", "2400", "4800", "9600",
            "14400", "19200", "28800", "38400", "57600", "115200", "921600", "2000000"
        ], state="readonly")
        self.baud_combobox.set("9600")
        self.baud_combobox.grid(row=0, column=4, sticky=tk.W, padx=5, pady=5)

        # 打开/关闭串口按钮
        self.connect_btn = ttk.Button(settings_frame, text="打开串口", command=self.toggle_connection)
        self.connect_btn.grid(row=0, column=5, padx=5, pady=5)

        # 显示选项区域
        display_frame = ttk.LabelFrame(main_frame, text="显示选项", padding="10")
        display_frame.pack(fill=tk.X, padx=5, pady=5)

        # 显示选项复选框
        self.timestamp_check = ttk.Checkbutton(display_frame, text="显示时间戳", variable=self.timestamp_var)
        self.timestamp_check.pack(side=tk.LEFT, padx=5, pady=5)

        self.hex_display_check = ttk.Checkbutton(display_frame, text="十六进制显示", variable=self.hex_display_var)
        self.hex_display_check.pack(side=tk.LEFT, padx=5, pady=5)

        self.show_receive_check = ttk.Checkbutton(display_frame, text="显示接收数据", variable=self.show_receive_var)
        self.show_receive_check.pack(side=tk.LEFT, padx=5, pady=5)

        # 日志保存设置区域
        log_frame = ttk.LabelFrame(main_frame, text="日志保存", padding="10")
        log_frame.pack(fill=tk.X, padx=5, pady=5)

        # 日志路径选择
        ttk.Label(log_frame, text="保存路径:").grid(row=0, column=0, sticky=tk.W, padx=5, pady=5)
        self.log_path_entry = ttk.Entry(log_frame, width=40, state="readonly")
        self.log_path_entry.grid(row=0, column=1, sticky=tk.W, padx=5, pady=5)

        # 选择路径按钮
        self.select_path_btn = ttk.Button(log_frame, text="选择路径", command=self.select_log_path)
        self.select_path_btn.grid(row=0, column=2, padx=5, pady=5)

        # 开启/关闭保存按钮
        self.toggle_log_btn = ttk.Button(log_frame, text="开启保存", command=self.toggle_log_save)
        self.toggle_log_btn.grid(row=0, column=3, padx=5, pady=5)

        # 发送区域
        send_frame = ttk.LabelFrame(main_frame, text="发送数据", padding="10")
        send_frame.pack(fill=tk.X, padx=5, pady=5)

        # 发送选项框架
        send_options_frame = ttk.Frame(send_frame)
        send_options_frame.pack(fill=tk.X, padx=5, pady=5)

        self.hex_send_checkbox = ttk.Checkbutton(send_options_frame, text="十六进制发送", variable=self.hex_send_var)
        self.hex_send_checkbox.pack(side=tk.LEFT, padx=5, pady=5)

        # 历史记录按钮
        self.history_btn = ttk.Button(send_options_frame, text="发送历史", command=self.show_send_history)
        self.history_btn.pack(side=tk.RIGHT, padx=5, pady=5)

        # 发送输入框架
        send_input_frame = ttk.Frame(send_frame)
        send_input_frame.pack(fill=tk.X, padx=5, pady=5)

        self.send_entry = ttk.Entry(send_input_frame)
        self.send_entry.pack(fill=tk.X, padx=5, pady=5, side=tk.LEFT, expand=True)
        self.send_entry.bind("<Return>", self.send_data)

        # 添加上下箭头键绑定，用于浏览历史记录
        self.send_entry.bind("<Up>", self.prev_history)
        self.send_entry.bind("<Down>", self.next_history)

        self.send_btn = ttk.Button(send_input_frame, text="发送", command=self.send_data)
        self.send_btn.pack(padx=5, pady=5, side=tk.RIGHT)

        # 接收区域
        receive_frame = ttk.LabelFrame(main_frame, text="接收数据", padding="10")
        receive_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        self.receive_text = scrolledtext.ScrolledText(
            receive_frame, wrap=tk.WORD, state=tk.DISABLED, font=("Consolas", 10)
        )
        self.receive_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        # 按钮框架
        button_frame = ttk.Frame(receive_frame)
        button_frame.pack(side=tk.BOTTOM, fill=tk.X, padx=5, pady=5)

        # 清空接收区按钮
        self.clear_btn = ttk.Button(button_frame, text="清空接收区", command=self.clear_receive)
        self.clear_btn.pack(side=tk.LEFT, padx=5, pady=5)

        # 清空所有接收数据按钮（包括日志）
        self.clear_all_btn = ttk.Button(button_frame, text="清空所有接收数据", command=self.clear_all_receive)
        self.clear_all_btn.pack(side=tk.RIGHT, padx=5, pady=5)

        # 状态栏
        self.status_var = tk.StringVar(value="就绪 | 未连接 | 日志未保存")
        status_bar = ttk.Label(self.root, textvariable=self.status_var, relief=tk.SUNKEN, anchor=tk.W)
        status_bar.pack(side=tk.BOTTOM, fill=tk.X)

        # 历史记录浏览索引
        self.history_index = -1  # -1 表示当前不在浏览历史

    def scan_ports(self):
        """扫描可用的串口"""
        ports = [port.device for port in serial.tools.list_ports.comports()]
        self.port_combobox['values'] = ports
        if ports:
            self.port_combobox.current(0)
            self.status_var.set(f"找到 {len(ports)} 个可用串口 | 未连接 | 日志未保存")
        else:
            self.status_var.set("未找到可用串口 | 未连接 | 日志未保存")

    def toggle_connection(self):
        """打开或关闭串口连接"""
        if self.serial_port and self.serial_port.is_open:
            self.close_serial()
        else:
            self.open_serial()

    def open_serial(self):
        """打开串口"""
        port = self.port_combobox.get()
        baudrate = self.baud_combobox.get()

        if not port:
            messagebox.showerror("错误", "请选择串口")
            return

        try:
            self.serial_port = serial.Serial(
                port=port,
                baudrate=int(baudrate),
                bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE,
                timeout=1,
                write_timeout=2  # 添加写入超时，防止写入操作永久阻塞
            )

            # 清空接收缓冲区
            self.receive_buffer = b''

            # 启动读取线程
            self.stop_event.clear()
            self.serial_thread = Thread(target=self.read_serial, daemon=True)
            self.serial_thread.start()

            self.connect_btn.config(text="关闭串口")
            log_status = "日志保存中" if self.save_log else "日志未保存"
            self.status_var.set(f"已连接 {port} @ {baudrate} | 运行中 | {log_status}")
            self.add_to_receive(f"已连接到串口 {port} @ {baudrate}bps\n")

        except Exception as e:
            messagebox.showerror("连接错误", f"无法打开串口:\n{str(e)}")
            self.status_var.set(f"连接失败 | 错误 | 日志未保存")

    def close_serial(self):
        """关闭串口"""
        if self.serial_port:
            self.stop_event.set()
            if self.serial_thread and self.serial_thread.is_alive():
                self.serial_thread.join(timeout=1.0)

            try:
                if self.serial_port.is_open:
                    self.serial_port.close()
            except Exception as e:
                self.add_to_receive(f"关闭串口时出错: {str(e)}\n")

            port = self.port_combobox.get()
            self.add_to_receive(f"已断开与 {port} 的连接\n")

        # 关闭串口时同步关闭日志保存
        self.stop_log_save()
        self.connect_btn.config(text="打开串口")
        self.status_var.set("已断开连接 | 就绪 | 日志未保存")

    def read_serial(self):
        """从串口读取数据的线程（降低CPU占用）"""
        while not self.stop_event.is_set() and self.serial_port and self.serial_port.is_open:
            try:
                if self.serial_port.in_waiting > 0:
                    data = self.serial_port.read(self.serial_port.in_waiting)
                    if data:
                        # 将数据添加到缓冲区
                        self.receive_buffer += data

                        # 检查是否有完整的数据包（根据时间间隔判断）
                        # 这里我们假设如果50ms内没有新数据，就认为是一个完整的数据包
                        time.sleep(0.05)  # 等待50ms看是否有更多数据

                        # 再次检查是否有新数据
                        if self.serial_port.in_waiting > 0:
                            # 如果有新数据，继续读取并添加到缓冲区
                            more_data = self.serial_port.read(self.serial_port.in_waiting)
                            self.receive_buffer += more_data

                        # 将缓冲区数据放入队列并清空缓冲区
                        if self.receive_buffer:
                            # 队列满时丢弃旧数据，避免阻塞
                            if self.data_queue.full():
                                try:
                                    self.data_queue.get_nowait()
                                except queue.Empty:
                                    pass
                                self.data_queue.put(self.receive_buffer)
                            else:
                                self.data_queue.put(self.receive_buffer)

                            # 清空缓冲区
                            self.receive_buffer = b''
                else:
                    time.sleep(0.05)  # 降低循环频率，减少CPU占用
            except Exception as e:
                if not self.stop_event.is_set():  # 如果不是主动停止
                    self.data_queue.put(f"[读取错误] {str(e)}\n".encode())
                break

    def format_received_data(self, data):
        current_time = datetime.datetime.now().strftime("%H:%M:%S.%f")[:-3]
        display_parts = []
        if self.timestamp_var.get():
            display_parts.append(f"[{current_time}]")
        display_parts.append("收←")

        if self.hex_display_var.get():
            # 十六进制显示逻辑
            hex_part = " ".join([f"{b:02X}" for b in data])
            display_parts.append(hex_part)
        else:
            # ASCII 文本显示逻辑（不可打印字符用 '.' 代替）
            ascii_part = "".join([chr(b) if 32 <= b <= 126 else '.' for b in data])
            display_parts.append(ascii_part)

        return " ".join(display_parts) + "\n"

    def update_ui(self):
        """更新UI的线程（批量处理+降低刷新频率）"""
        while True:
            try:
                # 批量获取队列数据，减少UI刷新次数
                data_batch = []
                try:
                    while True:
                        data = self.data_queue.get_nowait()
                        data_batch.append(data)
                except queue.Empty:
                    pass

                if data_batch:
                    for data in data_batch:
                        if isinstance(data, bytes):
                            # 如果启用了显示接收数据，则格式化并显示
                            if self.show_receive_var.get():
                                display_text = self.format_received_data(data)
                                self.add_to_receive(display_text, tag="recv")

                            # 日志写入（不受显示选项影响）
                            if self.save_log and self.log_file:
                                try:
                                    # 即使不显示，也写入日志
                                    if not self.show_receive_var.get():
                                        display_text = self.format_received_data(data)
                                    self.log_file.write(display_text)
                                except Exception as e:
                                    self.add_to_receive(f"[日志错误] 写入失败: {str(e)}\n", tag="error")
                                    self.stop_log_save()
                        else:
                            # 处理错误信息（字符串形式），错误信息始终显示
                            self.add_to_receive(data.decode('utf-8', errors='replace'), tag="error")
                time.sleep(0.1)  # 降低UI更新频率，提升流畅度
            except Exception as e:
                self.add_to_receive(f"[UI错误] {str(e)}\n", tag="error")

    def add_to_send_history(self, data_str):
        """添加数据到发送历史"""
        if data_str and data_str not in self.send_history:
            self.send_history.insert(0, data_str)  # 添加到开头

            # 限制历史记录数量
            if len(self.send_history) > self.max_history_size:
                self.send_history.pop()  # 移除最旧的一条记录

    def prev_history(self, event=None):
        """浏览上一条历史记录"""
        if not self.send_history:
            return

        if self.history_index < len(self.send_history) - 1:
            self.history_index += 1
            self.send_entry.delete(0, tk.END)
            self.send_entry.insert(0, self.send_history[self.history_index])

        return "break"  # 阻止默认行为

    def next_history(self, event=None):
        """浏览下一条历史记录"""
        if not self.send_history:
            return

        if self.history_index > 0:
            self.history_index -= 1
            self.send_entry.delete(0, tk.END)
            self.send_entry.insert(0, self.send_history[self.history_index])
        elif self.history_index == 0:
            self.history_index = -1
            self.send_entry.delete(0, tk.END)

        return "break"  # 阻止默认行为

    def show_send_history(self):
        """显示发送历史窗口"""
        if not self.send_history:
            messagebox.showinfo("发送历史", "暂无发送历史记录")
            return

        # 创建历史记录窗口
        history_window = tk.Toplevel(self.root)
        history_window.title("发送历史")
        history_window.geometry("400x300")
        history_window.transient(self.root)
        history_window.grab_set()

        # 创建框架
        main_frame = ttk.Frame(history_window, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)

        # 标题
        ttk.Label(main_frame, text="发送历史记录（双击选择）", font=("", 10, "bold")).pack(pady=5)

        # 历史列表
        history_frame = ttk.Frame(main_frame)
        history_frame.pack(fill=tk.BOTH, expand=True, pady=5)

        history_listbox = tk.Listbox(history_frame, font=("Consolas", 9))
        scrollbar = ttk.Scrollbar(history_frame, orient=tk.VERTICAL, command=history_listbox.yview)
        history_listbox.configure(yscrollcommand=scrollbar.set)

        # 填充历史记录
        for i, item in enumerate(self.send_history):
            history_listbox.insert(tk.END, f"{i + 1}. {item}")

        history_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # 双击选择事件
        def on_double_click(event):
            selection = history_listbox.curselection()
            if selection:
                index = selection[0]
                selected_text = self.send_history[index]
                self.send_entry.delete(0, tk.END)
                self.send_entry.insert(0, selected_text)
                history_window.destroy()

        history_listbox.bind("<Double-Button-1>", on_double_click)

        # 按钮框架
        button_frame = ttk.Frame(main_frame)
        button_frame.pack(fill=tk.X, pady=5)

        # 清除历史按钮
        def clear_history():
            if messagebox.askyesno("确认", "确定要清除所有发送历史记录吗？"):
                self.send_history.clear()
                history_window.destroy()

        ttk.Button(button_frame, text="清除历史", command=clear_history).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="关闭", command=history_window.destroy).pack(side=tk.RIGHT, padx=5)

    def safe_serial_write(self, data):
        """安全的串口写入方法，处理超时和异常"""
        with self.serial_lock:  # 确保串口操作是线程安全的
            if not self.serial_port or not self.serial_port.is_open:
                raise Exception("串口未连接")

            try:
                # 尝试写入数据
                written = self.serial_port.write(data)
                self.serial_port.flush()  # 确保数据被发送
                return written
            except serial.SerialTimeoutException:
                # 写入超时
                raise Exception("写入超时，请检查串口连接")
            except Exception as e:
                # 其他异常
                raise Exception(f"写入失败: {str(e)}")

    def send_data(self, event=None):
        """发送数据（支持十六进制/ASCII模式）"""
        if not self.serial_port or not self.serial_port.is_open:
            messagebox.showerror("错误", "串口未连接")
            return

        data_str = self.send_entry.get()
        if not data_str:
            return

        try:
            current_time = datetime.datetime.now().strftime("%H:%M:%S.%f")[:-3]
            if self.hex_send_var.get():
                # 十六进制发送逻辑
                hex_str = data_str.replace(" ", "")
                if len(hex_str) % 2 != 0:
                    self.add_to_receive(f"[{current_time}] [发送错误] 十六进制长度必须为偶数: {data_str}\n",
                                        tag="error")
                    return
                try:
                    data = bytes.fromhex(hex_str)

                    # 使用安全的串口写入方法
                    written_bytes = self.safe_serial_write(data)

                    # 格式化发送显示 - 只显示十六进制
                    display_parts = []
                    if self.timestamp_var.get():
                        display_parts.append(f"[{current_time}]")
                    display_parts.append("发→")

                    hex_display = " ".join([f"{b:02X}" for b in data])
                    display_parts.append(hex_display)

                    self.add_to_receive(" ".join(display_parts) + "\n", tag="send")

                    # 日志写入
                    if self.save_log and self.log_file:
                        try:
                            self.log_file.write(" ".join(display_parts) + "\n")
                        except Exception as e:
                            self.add_to_receive(f"[日志错误] 发送内容写入失败: {str(e)}\n", tag="error")
                            self.stop_log_save()

                    # 添加到发送历史
                    self.add_to_send_history(data_str)
                    # 重置历史索引
                    self.history_index = -1

                except ValueError:
                    self.add_to_receive(f"[{current_time}] [发送错误] 无效的十六进制字符: {data_str}\n", tag="error")
            else:
                # ASCII模式发送逻辑 - 直接发送字符串
                # 添加换行符，因为通常命令需要换行来执行
                data = (data_str + '\r\n').encode('utf-8')

                # 使用安全的串口写入方法
                written_bytes = self.safe_serial_write(data)

                # 格式化发送显示 - 显示原始字符串
                display_parts = []
                if self.timestamp_var.get():
                    display_parts.append(f"[{current_time}]")
                display_parts.append("发→")

                # 在ASCII模式下，显示原始字符串而不是十六进制
                display_parts.append(data_str)

                self.add_to_receive(" ".join(display_parts) + "\n", tag="send")

                # 日志写入
                if self.save_log and self.log_file:
                    try:
                        self.log_file.write(" ".join(display_parts) + "\n")
                    except Exception as e:
                        self.add_to_receive(f"[日志错误] 发送内容写入失败: {str(e)}\n", tag="error")
                        self.stop_log_save()

                # 添加到发送历史
                self.add_to_send_history(data_str)
                # 重置历史索引
                self.history_index = -1

            # 注意：这里不再清空输入框，保持内容不变
            # 用户可以选择按回车再次发送相同内容

        except Exception as e:
            error_msg = f"[{current_time}] [发送错误] {str(e)}\n"
            self.add_to_receive(error_msg, tag="error")

            # 如果是超时错误，自动关闭串口
            if "超时" in str(e):
                self.add_to_receive(f"[{current_time}] [系统] 检测到超时错误，自动关闭串口连接\n", tag="error")
                self.close_serial()

    def add_to_receive(self, text, tag=None):
        """添加文本到接收区域，支持标签"""
        # 确保在UI线程中执行
        self.root.after(0, self._add_to_receive_ui, text, tag)

    def _add_to_receive_ui(self, text, tag=None):
        """在UI线程中添加文本到接收区域"""
        self.receive_text.config(state=tk.NORMAL)
        if tag:
            self.receive_text.insert(tk.END, text, tag)
        else:
            self.receive_text.insert(tk.END, text)
        self.receive_text.see(tk.END)
        self.receive_text.config(state=tk.DISABLED)

    def clear_receive(self):
        """清空接收区域"""
        self.receive_text.config(state=tk.NORMAL)
        self.receive_text.delete(1.0, tk.END)
        self.receive_text.config(state=tk.DISABLED)

    def clear_all_receive(self):
        """清空所有接收数据（包括日志）"""
        # 清空接收区域
        self.clear_receive()

        # 如果日志文件已打开，关闭并重新创建（清空内容）
        if self.save_log and self.log_file and self.log_file_path:
            try:
                self.log_file.close()
                # 重新创建文件（清空内容）
                self.log_file = open(self.log_file_path, 'w', encoding='utf-8')
                self.add_to_receive(f"已清空所有接收数据和日志文件\n", tag="send")
            except Exception as e:
                self.add_to_receive(f"[日志错误] 清空日志文件失败: {str(e)}\n", tag="error")

        self.add_to_receive("所有接收数据和日志已清空\n", tag="send")

    def select_log_path(self):
        """选择日志保存路径"""
        default_filename = f"serial_log_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
        file_path = filedialog.asksaveasfilename(
            defaultextension=".txt",
            filetypes=[("文本文件", "*.txt"), ("所有文件", "*.*")],
            initialfile=default_filename,
            title="选择日志保存路径"
        )
        if file_path:
            self.log_file_path = file_path
            self.log_path_entry.config(state=tk.NORMAL)
            self.log_path_entry.delete(0, tk.END)
            self.log_path_entry.insert(0, file_path)
            self.log_path_entry.config(state=tk.readonly)
            self.status_var.set(
                f"{self.status_var.get().split('|')[0]} | {self.status_var.get().split('|')[1]} | 已选择路径")

    def toggle_log_save(self):
        """切换日志保存状态"""
        if not self.log_file_path:
            messagebox.showwarning("提示", "请先选择日志保存路径")
            return

        if not self.save_log:
            # 开启日志保存
            try:
                self.log_file = open(self.log_file_path, 'a', encoding='utf-8')
                self.save_log = True
                self.toggle_log_btn.config(text="关闭保存")
                self.add_to_receive(f"已开始保存日志到: {self.log_file_path}\n", tag="send")
                # 更新状态栏
                if self.serial_port and self.serial_port.is_open:
                    port_baud = self.status_var.get().split('|')[1].strip()
                    self.status_var.set(f"{self.status_var.get().split('|')[0]} | {port_baud} | 日志保存中")
                else:
                    self.status_var.set(
                        f"{self.status_var.get().split('|')[0]} | {self.status_var.get().split('|')[1]} | 日志保存中")
            except Exception as e:
                messagebox.showerror("日志错误", f"无法打开日志文件:\n{str(e)}")
                self.save_log = False
        else:
            # 关闭日志保存
            self.stop_log_save()

    def stop_log_save(self):
        """停止日志保存并关闭文件"""
        if self.save_log and self.log_file:
            try:
                self.log_file.close()
            except Exception as e:
                self.add_to_receive(f"关闭日志文件时出错: {str(e)}\n")
            self.log_file = None
            self.save_log = False
            self.toggle_log_btn.config(text="开启保存")
            self.add_to_receive(f"已停止保存日志（文件：{self.log_file_path}）\n", tag="send")
            # 更新状态栏
            if self.serial_port and self.serial_port.is_open:
                port_baud = self.status_var.get().split('|')[1].strip()
                self.status_var.set(f"{self.status_var.get().split('|')[0]} | {port_baud} | 日志未保存")
            else:
                self.status_var.set(
                    f"{self.status_var.get().split('|')[0]} | {self.status_var.get().split('|')[1]} | 日志未保存")

    def on_closing(self):
        """关闭窗口时的清理"""
        self.stop_log_save()
        self.close_serial()
        self.root.destroy()


if __name__ == "__main__":
    root = tk.Tk()
    app = SerialTool(root)

    # 配置标签样式（发送为蓝色、接收为绿色、错误为红色）
    app.receive_text.tag_config("send", foreground="blue")
    app.receive_text.tag_config("recv", foreground="green")
    app.receive_text.tag_config("error", foreground="red")

    root.mainloop()