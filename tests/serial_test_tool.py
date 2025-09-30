import serial
import serial.tools.list_ports
import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox, filedialog
import threading
import time
import re
import os
from datetime import datetime

try:
    import pandas as pd

    HAS_PANDAS = True
except ImportError:
    HAS_PANDAS = False


class SerialTestTool:
    def __init__(self, root):
        self.root = root
        self.root.title("串口协议测试工具")
        self.root.geometry("1000x700")

        # 串口相关变量
        self.serial_port = None
        self.is_connected = False

        # 测试用例相关变量
        self.test_cases = []
        self.current_test_index = 0
        self.batch_testing = False
        self.stop_batch_test = False

        # 检查pandas是否可用
        if not HAS_PANDAS:
            messagebox.showwarning("警告",
                                   "未安装pandas库，无法导入Excel文件。\n\n请使用以下命令安装：\npip install pandas openpyxl")

        # 创建界面
        self.create_widgets()

        # 自动刷新可用串口
        self.refresh_ports()

    def create_widgets(self):
        # 创建主框架
        main_frame = ttk.Frame(self.root)
        main_frame.pack(fill="both", expand=True, padx=10, pady=5)

        # 串口设置框架
        port_frame = ttk.LabelFrame(main_frame, text="串口设置")
        port_frame.pack(fill="x", pady=5)

        ttk.Label(port_frame, text="串口:").grid(row=0, column=0, padx=5, pady=5, sticky="w")
        self.port_combo = ttk.Combobox(port_frame, width=15)
        self.port_combo.grid(row=0, column=1, padx=5, pady=5)

        ttk.Button(port_frame, text="刷新", command=self.refresh_ports).grid(row=0, column=2, padx=5, pady=5)

        ttk.Label(port_frame, text="波特率:").grid(row=0, column=3, padx=5, pady=5, sticky="w")
        self.baud_combo = ttk.Combobox(port_frame, width=10, values=["9600", "19200", "38400", "57600", "115200","2000000"])
        self.baud_combo.set("115200")
        self.baud_combo.grid(row=0, column=4, padx=5, pady=5)

        ttk.Label(port_frame, text="响应等待时间(秒):").grid(row=0, column=5, padx=5, pady=5, sticky="w")
        self.wait_time_entry = ttk.Entry(port_frame, width=5)
        self.wait_time_entry.insert(0, "1")
        self.wait_time_entry.grid(row=0, column=6, padx=5, pady=5)

        self.connect_btn = ttk.Button(port_frame, text="打开串口", command=self.toggle_connection)
        self.connect_btn.grid(row=0, column=7, padx=5, pady=5)

        # 创建左右分栏
        paned_window = ttk.PanedWindow(main_frame, orient=tk.HORIZONTAL)
        paned_window.pack(fill="both", expand=True, pady=5)

        # 左侧单条测试框架
        left_frame = ttk.Frame(paned_window)
        paned_window.add(left_frame, weight=1)

        single_test_frame = ttk.LabelFrame(left_frame, text="单条测试")
        single_test_frame.pack(fill="both", expand=True, pady=5)

        ttk.Label(single_test_frame, text="发送数据:").grid(row=0, column=0, padx=5, pady=5, sticky="w")
        self.send_data_entry = ttk.Entry(single_test_frame, width=40)
        self.send_data_entry.grid(row=0, column=1, columnspan=2, padx=5, pady=5, sticky="we")

        ttk.Button(single_test_frame, text="导入发送数据", command=self.import_send_data).grid(row=0, column=3, padx=5,
                                                                                               pady=5)

        ttk.Label(single_test_frame, text="预期返回:").grid(row=1, column=0, padx=5, pady=5, sticky="w")
        self.expected_data_entry = ttk.Entry(single_test_frame, width=40)
        self.expected_data_entry.grid(row=1, column=1, columnspan=2, padx=5, pady=5, sticky="we")

        ttk.Button(single_test_frame, text="导入预期数据", command=self.import_expected_data).grid(row=1, column=3,
                                                                                                   padx=5, pady=5)

        # 单条测试按钮
        self.test_btn = ttk.Button(single_test_frame, text="开始测试", command=self.run_single_test, state="disabled")
        self.test_btn.grid(row=2, column=0, columnspan=4, padx=5, pady=10)

        # 单条测试结果框架
        single_result_frame = ttk.LabelFrame(single_test_frame, text="单条测试结果")
        single_result_frame.grid(row=3, column=0, columnspan=4, sticky="we", padx=5, pady=5)

        self.single_result_var = tk.StringVar()
        self.single_result_var.set("未测试")
        ttk.Label(single_result_frame, textvariable=self.single_result_var, font=("Arial", 12)).pack(pady=5)

        # 详情按钮
        self.single_detail_btn = ttk.Button(single_result_frame, text="查看详情", command=self.show_single_details,
                                            state="disabled")
        self.single_detail_btn.pack(pady=5)

        # 存储单条测试详情
        self.single_test_details = ""

        # 右侧批量测试框架
        right_frame = ttk.Frame(paned_window)
        paned_window.add(right_frame, weight=1)

        batch_test_frame = ttk.LabelFrame(right_frame, text="批量测试")
        batch_test_frame.pack(fill="both", expand=True, pady=5)

        # 批量测试控制按钮
        control_frame = ttk.Frame(batch_test_frame)
        control_frame.pack(fill="x", padx=5, pady=5)

        ttk.Button(control_frame, text="导入测试用例", command=self.import_test_cases).pack(side=tk.LEFT, padx=5)
        self.start_batch_btn = ttk.Button(control_frame, text="开始批量测试", command=self.start_batch_test,
                                          state="disabled")
        self.start_batch_btn.pack(side=tk.LEFT, padx=5)
        self.stop_batch_btn = ttk.Button(control_frame, text="停止测试", command=self.stop_batch_test, state="disabled")
        self.stop_batch_btn.pack(side=tk.LEFT, padx=5)
        ttk.Button(control_frame, text="导出测试结果", command=self.export_test_results).pack(side=tk.LEFT, padx=5)

        # 批量测试进度
        progress_frame = ttk.Frame(batch_test_frame)
        progress_frame.pack(fill="x", padx=5, pady=5)

        ttk.Label(progress_frame, text="进度:").pack(side=tk.LEFT)
        self.progress_var = tk.StringVar()
        self.progress_var.set("0/0")
        ttk.Label(progress_frame, textvariable=self.progress_var).pack(side=tk.LEFT, padx=5)

        self.progress_bar = ttk.Progressbar(progress_frame, mode='determinate')
        self.progress_bar.pack(fill="x", expand=True, padx=5)

        # 批量测试结果表格
        results_frame = ttk.Frame(batch_test_frame)
        results_frame.pack(fill="both", expand=True, padx=5, pady=5)

        # 创建树形视图显示测试结果
        columns = ("序号", "发送数据", "预期结果", "实际结果", "状态")
        self.results_tree = ttk.Treeview(results_frame, columns=columns, show="headings", height=10)

        for col in columns:
            self.results_tree.heading(col, text=col)
            self.results_tree.column(col, width=100)

        # 添加滚动条
        scrollbar = ttk.Scrollbar(results_frame, orient=tk.VERTICAL, command=self.results_tree.yview)
        self.results_tree.configure(yscrollcommand=scrollbar.set)

        self.results_tree.pack(side=tk.LEFT, fill="both", expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # 日志框架
        log_frame = ttk.LabelFrame(main_frame, text="通信日志")
        log_frame.pack(fill="both", expand=True, pady=5)

        self.log_text = scrolledtext.ScrolledText(log_frame, height=10)
        self.log_text.pack(fill="both", expand=True, padx=5, pady=5)
        self.log_text.config(state="disabled")

    def refresh_ports(self):
        ports = [port.device for port in serial.tools.list_ports.comports()]
        self.port_combo['values'] = ports
        if ports:
            self.port_combo.set(ports[0])

    def toggle_connection(self):
        if not self.is_connected:
            self.open_serial()
        else:
            self.close_serial()

    def open_serial(self):
        port = self.port_combo.get()
        baudrate = self.baud_combo.get()

        if not port:
            messagebox.showerror("错误", "请选择串口")
            return

        try:
            self.serial_port = serial.Serial(port, int(baudrate), timeout=1)
            self.is_connected = True
            self.connect_btn.config(text="关闭串口")
            self.test_btn.config(state="normal")
            self.start_batch_btn.config(state="normal")
            self.log_message(f"已连接到串口 {port}，波特率 {baudrate}")
        except Exception as e:
            messagebox.showerror("错误", f"无法打开串口: {str(e)}")

    def close_serial(self):
        if self.serial_port and self.serial_port.is_open:
            self.serial_port.close()
        self.is_connected = False
        self.connect_btn.config(text="打开串口")
        self.test_btn.config(state="disabled")
        self.start_batch_btn.config(state="disabled")
        self.log_message("串口已关闭")

    def import_send_data(self):
        file_path = filedialog.askopenfilename(title="选择发送数据文件",
                                               filetypes=[("Text files", "*.txt"), ("All files", "*.*")])
        if file_path:
            try:
                with open(file_path, 'r') as file:
                    data = file.read().strip()
                    self.send_data_entry.delete(0, tk.END)
                    self.send_data_entry.insert(0, data)
            except Exception as e:
                messagebox.showerror("错误", f"读取文件失败: {str(e)}")

    def import_expected_data(self):
        file_path = filedialog.askopenfilename(title="选择预期数据文件",
                                               filetypes=[("Text files", "*.txt"), ("All files", "*.*")])
        if file_path:
            try:
                with open(file_path, 'r') as file:
                    data = file.read().strip()
                    self.expected_data_entry.delete(0, tk.END)
                    self.expected_data_entry.insert(0, data)
            except Exception as e:
                messagebox.showerror("错误", f"读取文件失败: {str(e)}")

    def import_test_cases(self):
        if not HAS_PANDAS:
            messagebox.showerror("错误",
                                 "未安装pandas库，无法导入Excel文件。\n\n请使用以下命令安装：\npip install pandas openpyxl")
            return

        file_path = filedialog.askopenfilename(
            title="选择测试用例文件",
            filetypes=[("Excel files", "*.xlsx"), ("CSV files", "*.csv"), ("All files", "*.*")]
        )

        if not file_path:
            return

        try:
            # 清空现有测试用例
            self.test_cases = []
            for item in self.results_tree.get_children():
                self.results_tree.delete(item)

            # 根据文件扩展名选择读取方式
            if file_path.endswith('.csv'):
                df = pd.read_csv(file_path, header=None)
            else:
                df = pd.read_excel(file_path, header=None)

            # 确保至少有两列数据
            if df.shape[1] < 2:
                messagebox.showerror("错误", "文件必须至少包含两列数据（发送数据和预期返回数据）")
                return

            # 遍历每一行，提取发送数据和预期返回数据
            for i, row in df.iterrows():
                send_data = str(row[0]).strip()
                expected_data = str(row[1]).strip()

                # 跳过空行
                if not send_data or not expected_data:
                    continue

                # 清理数据中的非十六进制字符，但保留空格
                send_data = self.normalize_hex_with_spaces(send_data)
                expected_data = self.normalize_hex_with_spaces(expected_data)

                if send_data and expected_data:
                    self.test_cases.append({
                        'index': len(self.test_cases) + 1,
                        'send': send_data,
                        'expected': expected_data,
                        'actual': '',
                        'status': '待测试'
                    })

                    # 添加到结果树
                    self.results_tree.insert("", "end", values=(
                        len(self.test_cases),
                        send_data[:30] + "..." if len(send_data) > 30 else send_data,
                        expected_data[:30] + "..." if len(expected_data) > 30 else expected_data,
                        "",
                        "待测试"
                    ))

            if not self.test_cases:
                messagebox.showwarning("警告", "未找到有效的测试用例")
                return

            self.log_message(f"已导入 {len(self.test_cases)} 条测试用例")
            self.progress_var.set(f"0/{len(self.test_cases)}")
            self.progress_bar['maximum'] = len(self.test_cases)
            self.progress_bar['value'] = 0

        except Exception as e:
            messagebox.showerror("错误", f"导入测试用例失败: {str(e)}")
            import traceback
            traceback.print_exc()

    def run_single_test(self):
        if not self.is_connected:
            messagebox.showerror("错误", "请先打开串口")
            return

        send_data = self.send_data_entry.get().strip()
        expected_data = self.expected_data_entry.get().strip()

        if not send_data:
            messagebox.showerror("错误", "请输入发送数据")
            return

        if not expected_data:
            messagebox.showerror("错误", "请输入预期返回数据")
            return

        # 在新线程中运行测试，避免界面冻结
        threading.Thread(target=self.do_single_test, args=(send_data, expected_data), daemon=True).start()

    def do_single_test(self, send_data, expected_data):
        self.test_btn.config(state="disabled")
        self.single_result_var.set("测试中...")

        try:
            # 清理接收缓冲区
            self.serial_port.reset_input_buffer()

            # 转换发送数据格式
            send_bytes = self.hex_string_to_bytes(send_data)
            if send_bytes is None:
                self.single_result_var.set("发送数据格式错误")
                self.test_btn.config(state="normal")
                return

            # 发送数据
            self.log_message(f"单条测试发送: {send_data}")
            self.serial_port.write(send_bytes)

            # 等待并读取响应
            wait_time = float(self.wait_time_entry.get() or 1)
            time.sleep(wait_time)
            received_bytes = self.serial_port.read_all()

            # 转换接收到的数据为十六进制字符串
            received_hex = self.bytes_to_hex_string(received_bytes)
            self.log_message(f"单条测试接收: {received_hex}")

            # 比较结果
            expected_normalized = self.normalize_hex(expected_data)
            received_normalized = self.normalize_hex(received_hex)

            if expected_normalized == received_normalized:
                self.single_result_var.set("测试结果: PASS")
                self.single_test_details = f"预期: {expected_data}\n实际: {received_hex}\n\n数据匹配成功！"
            else:
                self.single_result_var.set("测试结果: FAILURE")
                self.single_test_details = f"预期: {expected_data}\n实际: {received_hex}\n\n数据不匹配！"

            self.single_detail_btn.config(state="normal")

        except Exception as e:
            self.single_result_var.set(f"测试错误: {str(e)}")
            self.log_message(f"单条测试错误: {str(e)}")

        self.test_btn.config(state="normal")

    def start_batch_test(self):
        if not self.test_cases:
            messagebox.showwarning("警告", "请先导入测试用例")
            return

        if not self.is_connected:
            messagebox.showerror("错误", "请先打开串口")
            return

        self.batch_testing = True
        self.stop_batch_test = False
        self.start_batch_btn.config(state="disabled")
        self.stop_batch_btn.config(state="normal")

        # 在新线程中运行批量测试
        threading.Thread(target=self.do_batch_test, daemon=True).start()

    def do_batch_test(self):
        total_cases = len(self.test_cases)
        passed_cases = 0

        for i, test_case in enumerate(self.test_cases):
            if self.stop_batch_test:
                break

            # 更新进度
            self.progress_var.set(f"{i + 1}/{total_cases}")
            self.progress_bar['value'] = i + 1
            self.root.update()

            try:
                # 清理接收缓冲区
                self.serial_port.reset_input_buffer()

                # 转换发送数据格式
                send_bytes = self.hex_string_to_bytes(test_case['send'])
                if send_bytes is None:
                    test_case['status'] = '数据格式错误'
                    test_case['actual'] = '无效的发送数据'
                    self.update_test_result(i, test_case)
                    continue

                # 发送数据
                self.log_message(f"批量测试 [{i + 1}/{total_cases}] 发送: {test_case['send']}")
                self.serial_port.write(send_bytes)

                # 等待并读取响应
                wait_time = float(self.wait_time_entry.get() or 1)
                time.sleep(wait_time)
                received_bytes = self.serial_port.read_all()

                # 转换接收到的数据为十六进制字符串
                received_hex = self.bytes_to_hex_string(received_bytes)
                self.log_message(f"批量测试 [{i + 1}/{total_cases}] 接收: {received_hex}")

                # 比较结果
                expected_normalized = self.normalize_hex(test_case['expected'])
                received_normalized = self.normalize_hex(received_hex)

                if expected_normalized == received_normalized:
                    test_case['status'] = 'PASS'
                    passed_cases += 1
                else:
                    test_case['status'] = 'FAILURE'

                test_case['actual'] = received_hex
                self.update_test_result(i, test_case)

            except Exception as e:
                test_case['status'] = f'错误: {str(e)}'
                test_case['actual'] = '测试执行错误'
                self.update_test_result(i, test_case)
                self.log_message(f"批量测试 [{i + 1}/{total_cases}] 错误: {str(e)}")

        # 更新最终结果
        self.log_message(f"批量测试完成: 通过 {passed_cases}/{total_cases}")
        self.batch_testing = False
        self.start_batch_btn.config(state="normal")
        self.stop_batch_btn.config(state="disabled")

    def stop_batch_test(self):
        self.stop_batch_test = True
        self.log_message("批量测试已停止")

    def update_test_result(self, index, test_case):
        # 更新测试用例状态
        self.test_cases[index] = test_case

        # 更新结果树
        item_id = self.results_tree.get_children()[index]
        self.results_tree.item(item_id, values=(
            test_case['index'],
            test_case['send'][:30] + "..." if len(test_case['send']) > 30 else test_case['send'],
            test_case['expected'][:30] + "..." if len(test_case['expected']) > 30 else test_case['expected'],
            test_case['actual'][:30] + "..." if len(test_case['actual']) > 30 else test_case['actual'],
            test_case['status']
        ))

        # 根据状态设置行颜色
        if test_case['status'] == 'PASS':
            self.results_tree.item(item_id, tags=('pass',))
        elif test_case['status'] == 'FAILURE':
            self.results_tree.item(item_id, tags=('fail',))
        elif '错误' in test_case['status']:
            self.results_tree.item(item_id, tags=('error',))

        # 配置标签样式
        self.results_tree.tag_configure('pass', background='#d4edda')
        self.results_tree.tag_configure('fail', background='#f8d7da')
        self.results_tree.tag_configure('error', background='#fff3cd')

    def export_test_results(self):
        if not self.test_cases:
            messagebox.showwarning("警告", "没有测试结果可导出")
            return

        file_path = filedialog.asksaveasfilename(
            title="保存测试结果",
            defaultextension=".csv",
            filetypes=[("CSV files", "*.csv"), ("Excel files", "*.xlsx"), ("All files", "*.*")]
        )

        if not file_path:
            return

        try:
            if HAS_PANDAS:
                # 使用pandas导出
                df = pd.DataFrame(self.test_cases)
                df = df[['index', 'send', 'expected', 'actual', 'status']]

                if file_path.endswith('.xlsx'):
                    df.to_excel(file_path, index=False)
                else:
                    df.to_csv(file_path, index=False)
            else:
                # 如果没有pandas，使用CSV模块
                import csv
                with open(file_path, 'w', newline='', encoding='utf-8') as file:
                    writer = csv.writer(file)
                    # 写入标题行
                    writer.writerow(['序号', '发送数据', '预期结果', '实际结果', '状态'])

                    # 写入测试结果
                    for test_case in self.test_cases:
                        writer.writerow([
                            test_case['index'],
                            test_case['send'],
                            test_case['expected'],
                            test_case['actual'],
                            test_case['status']
                        ])

            self.log_message(f"测试结果已导出到: {file_path}")
            messagebox.showinfo("成功", f"测试结果已成功导出到: {file_path}")

        except Exception as e:
            messagebox.showerror("错误", f"导出测试结果失败: {str(e)}")

    def show_single_details(self):
        detail_window = tk.Toplevel(self.root)
        detail_window.title("单条测试详情")
        detail_window.geometry("500x300")

        text_widget = scrolledtext.ScrolledText(detail_window, wrap=tk.WORD)
        text_widget.pack(fill="both", expand=True, padx=10, pady=10)
        text_widget.insert("1.0", self.single_test_details)
        text_widget.config(state="disabled")

    def log_message(self, message):
        self.log_text.config(state="normal")
        self.log_text.insert(tk.END, f"{time.strftime('%H:%M:%S')} - {message}\n")
        self.log_text.see(tk.END)
        self.log_text.config(state="disabled")

    def hex_string_to_bytes(self, hex_string):
        """将十六进制字符串转换为字节数据"""
        # 移除所有非十六进制字符
        hex_string = re.sub(r'[^0-9A-Fa-f]', '', hex_string)

        # 检查长度是否为偶数
        if len(hex_string) % 2 != 0:
            return None

        try:
            return bytes.fromhex(hex_string)
        except ValueError:
            return None

    def bytes_to_hex_string(self, byte_data):
        """将字节数据转换为十六进制字符串"""
        return ' '.join(f'{b:02X}' for b in byte_data)

    def normalize_hex(self, hex_string):
        """标准化十六进制字符串（移除所有非十六进制字符并转换为大写）"""
        return re.sub(r'[^0-9A-Fa-f]', '', hex_string).upper()

    def normalize_hex_with_spaces(self, hex_string):
        """标准化十六进制字符串，但保留空格"""
        # 移除所有非十六进制字符和空格
        hex_string = re.sub(r'[^0-9A-Fa-f\s]', '', hex_string)
        # 转换为大写
        hex_string = hex_string.upper()
        # 压缩多余的空格
        hex_string = re.sub(r'\s+', ' ', hex_string).strip()
        return hex_string


if __name__ == "__main__":
    root = tk.Tk()
    app = SerialTestTool(root)
    root.mainloop()