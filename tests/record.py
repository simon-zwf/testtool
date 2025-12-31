import tkinter as tk
from tkinter import ttk, colorchooser, filedialog, simpledialog, messagebox
import json
import os

SAVE_FILE = "notes_data.json"  # 固定存储文件

root = tk.Tk()
root.title("简单记事本工具")
root.geometry("800x500")

toolbar = tk.Frame(root, bd=1, relief=tk.RAISED)
toolbar.pack(side=tk.TOP, fill=tk.X)

tree_frame = tk.Frame(root)
tree_frame.pack(side=tk.LEFT, fill=tk.Y)

tree = ttk.Treeview(tree_frame)
tree.pack(fill=tk.Y, expand=True)

text_frame = tk.Frame(root)
text_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)

text_widget = tk.Text(text_frame, wrap=tk.WORD)
text_widget.pack(fill=tk.BOTH, expand=True)

node_contents = {}
current_node = None

# ------------------- 新增/删除节点 -------------------
def add_root_node():
    name = simpledialog.askstring("新增根节点", "请输入根节点名称：")
    if name:
        node_id = tree.insert("", "end", text=name)
        node_contents[node_id] = ""

def add_child_node():
    selected = tree.selection()
    if not selected:
        messagebox.showinfo("提示", "请先选择一个父节点")
        return
    parent = selected[0]
    name = simpledialog.askstring("新增子节点", "请输入子节点名称：")
    if name:
        node_id = tree.insert(parent, "end", text=name)
        node_contents[node_id] = ""

def delete_node():
    selected = tree.selection()
    if not selected:
        messagebox.showinfo("提示", "请先选择要删除的节点")
        return
    node_id = selected[0]
    if messagebox.askyesno("确认删除", f"确定删除 '{tree.item(node_id,'text')}' 及其所有子节点吗？"):
        def delete_recursive(nid):
            for child in tree.get_children(nid):
                delete_recursive(child)
            node_contents.pop(nid, None)
        delete_recursive(node_id)
        tree.delete(node_id)
        global current_node
        if current_node == node_id:
            current_node = None
            text_widget.delete(1.0, tk.END)

# ------------------- 设置颜色 -------------------
def choose_color():
    color = colorchooser.askcolor()[1]
    if color:
        text_widget.tag_configure("colored", foreground=color)
        try:
            text_widget.tag_add("colored", tk.SEL_FIRST, tk.SEL_LAST)
        except tk.TclError:
            messagebox.showinfo("提示", "请先选中文本")

# ------------------- 保存/加载 -------------------
def save_all_data():
    if current_node:
        node_contents[current_node] = text_widget.get(1.0, tk.END)
    data = []

    def build_data(nid):
        return {
            "name": tree.item(nid, "text"),
            "content": node_contents.get(nid, ""),
            "children": [build_data(child) for child in tree.get_children(nid)]
        }

    for root_node in tree.get_children():
        data.append(build_data(root_node))

    with open(SAVE_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

def load_all_data():
    if not os.path.exists(SAVE_FILE):
        return
    with open(SAVE_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)

    def insert_data(parent, node_data):
        node_id = tree.insert(parent, "end", text=node_data["name"])
        node_contents[node_id] = node_data.get("content", "")
        for child in node_data.get("children", []):
            insert_data(node_id, child)

    for node_data in data:
        insert_data("", node_data)

# ------------------- 节点切换 -------------------
def on_tree_select(event):
    global current_node
    selected = tree.selection()
    if selected:
        if current_node:
            node_contents[current_node] = text_widget.get(1.0, tk.END)
        current_node = selected[0]
        text_widget.delete(1.0, tk.END)
        text_widget.insert(tk.END, node_contents.get(current_node, ""))

tree.bind("<<TreeviewSelect>>", on_tree_select)

# ------------------- 节点重命名 -------------------
def rename_node(event=None):
    selected = tree.selection()
    if not selected:
        return
    node_id = selected[0]
    old_name = tree.item(node_id, "text")
    new_name = simpledialog.askstring("重命名节点", "请输入新名称：", initialvalue=old_name)
    if new_name:
        tree.item(node_id, text=new_name)

# 双击节点时重命名
tree.bind("<Double-1>", rename_node)

# ------------------- 右键菜单 -------------------
menu = tk.Menu(tree, tearoff=0)
menu.add_command(label="重命名", command=rename_node)
menu.add_command(label="删除节点", command=delete_node)

def show_context_menu(event):
    selected = tree.identify_row(event.y)
    if selected:
        tree.selection_set(selected)
        menu.post(event.x_root, event.y_root)

tree.bind("<Button-3>", show_context_menu)  # 右键菜单

# ------------------- 工具栏按钮 -------------------
tk.Button(toolbar, text="新增根节点", command=add_root_node).pack(side=tk.LEFT, padx=2, pady=2)
tk.Button(toolbar, text="新增子节点", command=add_child_node).pack(side=tk.LEFT, padx=2, pady=2)
tk.Button(toolbar, text="删除节点", command=delete_node).pack(side=tk.LEFT, padx=2, pady=2)
tk.Button(toolbar, text="设置字体颜色", command=choose_color).pack(side=tk.LEFT, padx=2, pady=2)

# ------------------- 启动/退出 -------------------
def on_close():
    save_all_data()
    root.destroy()

root.protocol("WM_DELETE_WINDOW", on_close)

load_all_data()
root.mainloop()
