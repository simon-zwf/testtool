import tkinter as tk
from tkinter import scrolledtext, ttk, messagebox
import paramiko
import threading


class SSHClientUI:
    def __init__(self, root):
        self.root = root
        self.root.title("SSH命令执行工具")
        self.root.geometry("800x600")
        self.root.resizable(True, True)

        # 确保中文显示正常
        self.style = ttk.Style()
        self.style.configure("TLabel", font=("SimHei", 10))
        self.style.configure("TButton", font=("SimHei", 10))
        self.style.configure("TEntry", font=("SimHei", 10))

        # 创建主框架
        self.main_frame = ttk.Frame(root, padding="10")
        self.main_frame.pack(fill=tk.BOTH, expand=True)

        # 连接信息区域
        self.connection_frame = ttk.LabelFrame(self.main_frame, text="设备连接信息", padding="10")
        self.connection_frame.pack(fill=tk.X, pady=(0, 10))

        # IP地址
        ttk.Label(self.connection_frame, text="IP地址:").grid(row=0, column=0, sticky=tk.W, pady=5)
        self.ip_entry = ttk.Entry(self.connection_frame, width=20)
        self.ip_entry.grid(row=0, column=1, sticky=tk.W, pady=5, padx=5)
        self.ip_entry.insert(0, "192.168.120.128")  # 默认值

        # 用户名
        ttk.Label(self.connection_frame, text="用户名:").grid(row=0, column=2, sticky=tk.W, pady=5, padx=10)
        self.user_entry = ttk.Entry(self.connection_frame, width=15)
        self.user_entry.grid(row=0, column=3, sticky=tk.W, pady=5)
        self.user_entry.insert(0, "simon")  # 默认值

        # 密码
        ttk.Label(self.connection_frame, text="密码:").grid(row=0, column=4, sticky=tk.W, pady=5, padx=10)
        self.pass_entry = ttk.Entry(self.connection_frame, width=15, show="*")
        self.pass_entry.grid(row=0, column=5, sticky=tk.W, pady=5)
        self.pass_entry.insert(0, "12345")  # 默认值

        # 端口
        ttk.Label(self.connection_frame, text="端口:").grid(row=0, column=6, sticky=tk.W, pady=5, padx=10)
        self.port_entry = ttk.Entry(self.connection_frame, width=5)
        self.port_entry.grid(row=0, column=7, sticky=tk.W, pady=5)
        self.port_entry.insert(0, "22")  # 默认值

        # 连接按钮
        self.connect_btn = ttk.Button(self.connection_frame, text="连接设备", command=self.connect_device)
        self.connect_btn.grid(row=0, column=8, padx=10)

        # 命令输入区域（初始禁用，连接成功后启用）
        self.command_frame = ttk.LabelFrame(self.main_frame, text="命令输入（请先连接设备）", padding="10")
        self.command_frame.pack(fill=tk.X, pady=(0, 10))

        self.command_entry = ttk.Entry(self.command_frame, state=tk.DISABLED)
        self.command_entry.pack(fill=tk.X, side=tk.LEFT, expand=True, padx=(0, 10))
        self.command_entry.insert(0, "ls -l")  # 默认命令

        self.execute_btn = ttk.Button(self.command_frame, text="执行命令", command=self.execute_command,
                                      state=tk.DISABLED)
        self.execute_btn.pack(side=tk.RIGHT)

        # 断开连接按钮
        self.disconnect_btn = ttk.Button(self.command_frame, text="断开连接", command=self.disconnect_device,
                                         state=tk.DISABLED)
        self.disconnect_btn.pack(side=tk.RIGHT, padx=5)

        # 结果显示区域
        self.result_frame = ttk.LabelFrame(self.main_frame, text="执行结果", padding="10")
        self.result_frame.pack(fill=tk.BOTH, expand=True)

        self.result_text = scrolledtext.ScrolledText(self.result_frame, wrap=tk.WORD, font=("SimHei", 10))
        self.result_text.pack(fill=tk.BOTH, expand=True)
        self.result_text.config(state=tk.DISABLED)
        # 添加错误文本样式（红色）
        self.result_text.tag_config("error", foreground="red")

        # 状态栏
        self.status_var = tk.StringVar()
        self.status_var.set("就绪：请先连接设备")
        self.status_bar = ttk.Label(root, textvariable=self.status_var, relief=tk.SUNKEN, anchor=tk.W)
        self.status_bar.pack(side=tk.BOTTOM, fill=tk.X)

        # SSH客户端对象（连接成功后赋值）
        self.ssh = None
        self.is_connected = False  # 连接状态标记

    def update_status(self, message):
        """更新状态栏消息"""
        self.status_var.set(message)
        self.root.update_idletasks()

    def append_result(self, text, is_error=False):
        """向结果区域添加文本"""
        self.result_text.config(state=tk.NORMAL)
        if is_error:
            self.result_text.insert(tk.END, text, "error")
        else:
            self.result_text.insert(tk.END, text)
        self.result_text.insert(tk.END, "\n")
        self.result_text.see(tk.END)
        self.result_text.config(state=tk.DISABLED)

    def connect_device(self):
        """连接SSH设备（在新线程中执行）"""
        # 获取输入信息
        host = self.ip_entry.get().strip()
        username = self.user_entry.get().strip()
        password = self.pass_entry.get().strip()
        port = self.port_entry.get().strip()

        # 验证输入
        if not all([host, username, password, port]):
            messagebox.showerror("输入错误", "连接信息不能为空！")
            return

        try:
            port = int(port)
        except ValueError:
            messagebox.showerror("输入错误", "端口必须是数字！")
            return

        # 禁用连接按钮，防止重复点击
        self.connect_btn.config(state=tk.DISABLED)
        self.update_status("正在连接设备...")
        self.append_result(f"尝试连接 {host}:{port}...")

        # 在新线程中执行连接，避免UI卡顿
        threading.Thread(
            target=self._connect_thread,
            args=(host, username, password, port),
            daemon=True
        ).start()

    def _connect_thread(self, host, username, password, port):
        """连接线程"""
        try:
            # 创建SSH客户端
            self.ssh = paramiko.SSHClient()
            self.ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())

            # 连接设备
            self.ssh.connect(
                hostname=host,
                port=port,
                username=username,
                password=password,
                timeout=10,
                look_for_keys=False,
                allow_agent=False
            )

            # 连接成功：更新状态和UI
            self.is_connected = True
            self.root.after(0, self._on_connect_success)

        except paramiko.AuthenticationException:
            self.append_result("连接失败：用户名或密码错误", is_error=True)
            self.root.after(0, self._on_connect_failed)
        except paramiko.SSHException as e:
            self.append_result(f"连接失败：SSH协议错误 - {str(e)}", is_error=True)
            self.root.after(0, self._on_connect_failed)
        except Exception as e:
            self.append_result(f"连接失败：{str(e)}", is_error=True)
            self.root.after(0, self._on_connect_failed)

    def _on_connect_success(self):
        """连接成功后的UI更新"""
        self.append_result("连接成功！可以输入命令了")
        self.update_status("已连接：可以执行命令")
        # 启用命令输入和执行按钮，更新命令框标题
        self.command_entry.config(state=tk.NORMAL)
        self.execute_btn.config(state=tk.NORMAL)
        self.disconnect_btn.config(state=tk.NORMAL)
        self.command_frame.config(text="命令输入（已连接）")
        # 恢复连接按钮状态（便于重新连接）
        self.connect_btn.config(state=tk.NORMAL)

    def _on_connect_failed(self):
        """连接失败后的UI更新"""
        self.update_status("连接失败：请检查信息后重试")
        self.ssh = None
        self.is_connected = False
        # 恢复连接按钮状态
        self.connect_btn.config(state=tk.NORMAL)

    def disconnect_device(self):
        """断开SSH连接"""
        if self.ssh and self.is_connected:
            try:
                self.ssh.close()
                self.append_result("已断开SSH连接")
            except Exception as e:
                self.append_result(f"断开连接时出错：{str(e)}", is_error=True)

        # 更新状态和UI
        self.is_connected = False
        self.ssh = None
        self.update_status("已断开连接：请重新连接设备")
        self.command_entry.config(state=tk.DISABLED)
        self.execute_btn.config(state=tk.DISABLED)
        self.disconnect_btn.config(state=tk.DISABLED)
        self.command_frame.config(text="命令输入（请先连接设备）")

    def execute_command(self):
        """执行命令（需先连接成功）"""
        if not self.is_connected or not self.ssh:
            messagebox.showerror("错误", "请先连接设备！")
            return

        command = self.command_entry.get().strip()
        if not command:
            messagebox.showwarning("提示", "请输入命令！")
            return

        # 禁用执行按钮，防止重复点击
        self.execute_btn.config(state=tk.DISABLED)
        self.update_status("正在执行命令...")
        self.append_result(f"执行命令：{command}")

        # 在新线程中执行命令
        threading.Thread(
            target=self._execute_thread,
            args=(command,),
            daemon=True
        ).start()

    def _execute_thread(self, command):
        """命令执行线程"""
        try:
            # 执行命令
            stdin, stdout, stderr = self.ssh.exec_command(command)

            # 等待命令执行完成并获取输出
            exit_status = stdout.channel.recv_exit_status()
            output = stdout.read().decode("utf-8", errors="ignore")
            error = stderr.read().decode("utf-8", errors="ignore")

            # 显示结果
            if output:
                self.append_result("输出结果：")
                self.append_result(output)

            if error:
                self.append_result("错误信息：", is_error=True)
                self.append_result(error, is_error=True)

            self.append_result(f"命令执行完成，退出状态：{exit_status}")
            self.update_status("命令执行完成")

        except Exception as e:
            self.append_result(f"命令执行失败：{str(e)}", is_error=True)
            self.update_status("命令执行失败")
        finally:
            # 恢复按钮状态
            self.root.after(0, lambda: self.execute_btn.config(state=tk.NORMAL))


if __name__ == "__main__":
    root = tk.Tk()
    app = SSHClientUI(root)
    root.mainloop()