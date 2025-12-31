import tkinter as tk
from tkinter import ttk, messagebox

class HexAsciiConverter:
    def __init__(self, root):
        self.root = root
        self.root.title("十六进制与ASCII转换器")
        self.root.geometry("600x400")  # 窗口大小
        self.root.resizable(True, True)  # 允许拉伸

        # 设置样式
        self.style = ttk.Style()
        self.style.configure("TLabel", font=("微软雅黑", 10))
        self.style.configure("TButton", font=("微软雅黑", 10))
        self.style.configure("TEntry", font=("微软雅黑", 10))

        # 创建输入区域
        self.create_input_area()

        # 创建按钮区域
        self.create_buttons()

        # 创建结果区域
        self.create_result_area()

    def create_input_area(self):
        """创建输入框和标签"""
        input_frame = ttk.Frame(self.root, padding=10)
        input_frame.pack(fill=tk.X, padx=10, pady=5)

        # 输入标签
        ttk.Label(input_frame, text="请输入内容：", width=15).grid(
            row=0, column=0, sticky=tk.W, pady=5
        )

        # 输入框（支持多行）
        self.input_text = tk.Text(input_frame, height=6, wrap=tk.WORD)
        self.input_text.grid(
            row=0, column=1, columnspan=2, sticky=tk.EW, pady=5, padx=(0, 10)
        )

        # 滚动条
        scrollbar = ttk.Scrollbar(input_frame, command=self.input_text.yview)
        scrollbar.grid(row=0, column=3, sticky=tk.NS, pady=5)
        self.input_text.config(yscrollcommand=scrollbar.set)

        # 拉伸设置
        input_frame.columnconfigure(1, weight=1)

    def create_buttons(self):
        """创建转换按钮"""
        button_frame = ttk.Frame(self.root, padding=10)
        button_frame.pack(fill=tk.X, padx=10)

        # 十六进制转ASCII按钮
        ttk.Button(
            button_frame,
            text="十六进制 → ASCII",
            command=self.hex_to_ascii
        ).grid(row=0, column=0, padx=10, pady=5)

        # ASCII转十六进制按钮
        ttk.Button(
            button_frame,
            text="ASCII → 十六进制",
            command=self.ascii_to_hex
        ).grid(row=0, column=1, padx=10, pady=5)

        # 清空按钮
        ttk.Button(
            button_frame,
            text="清空",
            command=self.clear_all
        ).grid(row=0, column=2, padx=10, pady=5)

        # 拉伸设置
        button_frame.columnconfigure(0, weight=1)
        button_frame.columnconfigure(1, weight=1)
        button_frame.columnconfigure(2, weight=1)

    def create_result_area(self):
        """创建结果显示区域"""
        result_frame = ttk.Frame(self.root, padding=10)
        result_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        # 结果标签
        ttk.Label(result_frame, text="转换结果：", width=15).grid(
            row=0, column=0, sticky=tk.NW, pady=5
        )

        # 结果框（支持多行）
        self.result_text = tk.Text(result_frame, height=6, wrap=tk.WORD, state=tk.DISABLED)
        self.result_text.grid(
            row=0, column=1, columnspan=2, sticky=tk.NSEW, pady=5, padx=(0, 10)
        )

        # 滚动条
        scrollbar = ttk.Scrollbar(result_frame, command=self.result_text.yview)
        scrollbar.grid(row=0, column=3, sticky=tk.NS, pady=5)
        self.result_text.config(yscrollcommand=scrollbar.set)

        # 拉伸设置
        result_frame.rowconfigure(0, weight=1)
        result_frame.columnconfigure(1, weight=1)

    def hex_to_ascii(self):
        """十六进制转ASCII"""
        hex_str = self.input_text.get("1.0", tk.END).strip()  # 获取输入内容
        if not hex_str:
            messagebox.showwarning("提示", "请输入十六进制内容！")
            return

        try:
            # 处理输入（移除0x前缀和空格）
            hex_str = hex_str.replace("0x", "").replace("0X", "").replace(" ", "")
            # 检查长度是否为偶数
            if len(hex_str) % 2 != 0:
                raise ValueError("十六进制长度必须为偶数")
            # 转换
            ascii_str = bytes.fromhex(hex_str).decode("ascii")
            # 显示结果
            self.show_result(ascii_str)
        except Exception as e:
            messagebox.showerror("转换失败", f"错误：{str(e)}")

    def ascii_to_hex(self):
        """ASCII转十六进制"""
        ascii_str = self.input_text.get("1.0", tk.END).strip()  # 获取输入内容
        if not ascii_str:
            messagebox.showwarning("提示", "请输入ASCII内容！")
            return

        try:
            # 转换为十六进制（空格分隔每个字节，大写显示）
            hex_bytes = ascii_str.encode("ascii").hex()
            hex_str = " ".join([hex_bytes[i:i+2].upper() for i in range(0, len(hex_bytes), 2)])
            # 显示结果
            self.show_result(hex_str)
        except UnicodeEncodeError:
            messagebox.showerror("转换失败", "错误：输入包含非ASCII字符！")
        except Exception as e:
            messagebox.showerror("转换失败", f"错误：{str(e)}")

    def show_result(self, content):
        """显示转换结果"""
        self.result_text.config(state=tk.NORMAL)  # 解锁结果框
        self.result_text.delete("1.0", tk.END)  # 清空现有内容
        self.result_text.insert(tk.END, content)  # 插入新内容
        self.result_text.config(state=tk.DISABLED)  # 锁定结果框

    def clear_all(self):
        """清空输入和结果"""
        self.input_text.delete("1.0", tk.END)
        self.result_text.config(state=tk.NORMAL)
        self.result_text.delete("1.0", tk.END)
        self.result_text.config(state=tk.DISABLED)

if __name__ == "__main__":
    root = tk.Tk()
    app = HexAsciiConverter(root)
    root.mainloop()