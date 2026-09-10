#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
main()
 │
 ├─ 1. 获取 Excel 文件路径（命令行参数 或 弹文件选择框）
 │
 ├─ 2. create_dashboard(excel_path)
 │    │
 │    ├─ 循环处理 4 个固定 Sheet：
 │    │     DAQ / Power / SoftwareReading / GeminiPower
 │    │
 │    │    ├─ load_sheet_data()      读 Excel，自动探测表头行
 │    │    ├─ drop_useless_columns() 删掉"扫描编号/序号"等无关列
 │    │    ├─ prepare_time_column()  统一把时间列重命名为 Timestamp
 │    │    │      （DAQ 特殊：丢掉日期列，只用时间列）
 │    │    │
 │    │    └─ 按 Sheet 类型分派绘图：
 │    │         ├─ plot_daq()              → 按"Section"分组画多曲线图
 │    │         │    （靠顶部的 SECTION_MAP 字典，把测点名映射到 CPU/Radio/AMP 等区域）
 │    │         ├─ plot_power()            → 找 Power(w) 列画功率曲线（兼容 kW×1000）
 │    │         ├─ plot_software_reading() → 拆成两张图（系统指标组 / 放大器通道组）
 │    │         └─ plot_gemini_power()     → 画 D1_Pwr_Front / D2_Pwr_Rear 两条线
 │    │
 │    │    每张图都走同一个出口：
 │    │    create_multi_curve_image() ──→ matplotlib 画图
 │    │                                   └─ 存成 PNG → base64 编码字符串
 │    │
 │    └─ 3. generate_html(all_data)
 │         ├─ 拼接菜单 HTML（有子图的生成父子二级菜单）
 │         ├─ 拼接图表内容区 div（图片是 base64 内嵌，无需外部文件）
 │         └─ 写文件 dashboard_all_sheets.html + 自动用浏览器打开
"""
# ========== 关键：先设置 Matplotlib 后端，避免 Tkinter 冲突 ==========
import matplotlib
matplotlib.use('Agg')

import os
import sys
import argparse
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import io
import base64
import tkinter as tk
from tkinter import filedialog
import webbrowser
import re

# ========== 映射表（仅用于 DAQ） ==========
SECTION_MAP = {
    # CPU Section
    '101_U1_CPU': 'CPU Section',
    '102_U2_DDR': 'CPU Section',
    '103_U3_DDR': 'CPU Section',
    '104_U4_Emmc': 'CPU Section',
    '105_NTC1': 'CPU Section',
    '106_NTC2': 'CPU Section',
    '114_Heatsink': 'CPU Section',
    # Radio Section
    '107_U44_BHRadio': 'Radio Section',
    '108_U46_FEM': 'Radio Section',
    '109_U48_FEM': 'Radio Section',
    '113_L27_RNIND': 'Radio Section',
    '113_Q1': 'Radio Section',  # 添加
    # AMP Section
    '110_U28_GAMP': 'AMP Section',
    '111_U26_RMBAMP': 'AMP Section',
    '112_U27_LMBAMP': 'AMP Section',
    '201_U5_AMP1': 'AMP Section',
    '202_U6_AMP2': 'AMP Section',
    '203_U7_AMP3': 'AMP Section',
    '205_U9_AMP5': 'AMP Section',
    # Transducers Section
    '301_FGemini': 'Transducers Section',
    '302_RGemini': 'Transducers Section',
    '303_LMB': 'Transducers Section',
    '304_RMB': 'Transducers Section',
    '306_LDMR': 'Transducers Section',
    '307_RUMR': 'Transducers Section',
    '308_RDMR': 'Transducers Section',
    '310_DT': 'Transducers Section',
    '311_LT': 'Transducers Section',
    '312_RT': 'Transducers Section',
    '313_CT': 'Transducers Section',
    # Enclosure Section
    '314_FEnclosureTop': 'Enclosure Section',
    '315_REnclosureRigh': 'Enclosure Section',
    '316_REnclosureTop': 'Enclosure Section',
    '317_REnclosureLeft': 'Enclosure Section',
    # Rear Enclosure
    '206_BR1': 'Rear Enclosure',
    '207_L20': 'Rear Enclosure',
    '208_T1': 'Rear Enclosure',
    '209_Q8': 'Rear Enclosure',
    '210_U12': 'Rear Enclosure',
    '211_L4': 'Rear Enclosure',
    '212_U10': 'Rear Enclosure',
    '213_L26': 'Rear Enclosure',
    '214_U71': 'Rear Enclosure',
    # Ambient
    'ENV': 'Ambient Section',
    'Tent': 'Ambient Section',
}


def get_section(col_name):
    return SECTION_MAP.get(col_name.strip(), 'Other')


def detect_header_row(excel_path, sheet_name):
    """检测表头行（包含测点编号或 'Timestamp'）"""
    df_raw = pd.read_excel(excel_path, sheet_name=sheet_name, header=None)
    for idx, row in df_raw.iterrows():
        row_str = ' '.join([str(x) for x in row if pd.notna(x)])
        if re.search(r'\d{3}_', row_str) or 'Timestamp' in row_str or '时间' in row_str:
            return idx
    return 0


def load_sheet_data(excel_path, sheet_name):
    if sheet_name == 'DAQ':
        header_row = detect_header_row(excel_path, sheet_name)
        print(f"  {sheet_name}: 检测到表头行 {header_row}")
        df = pd.read_excel(excel_path, sheet_name=sheet_name, header=header_row)
    else:
        print(f"  {sheet_name}: 使用第一行作为表头")
        df = pd.read_excel(excel_path, sheet_name=sheet_name, header=0)
    return df


def drop_useless_columns(df, sheet_name):
    """删除不需要的列（扫描编号、Index 等）"""
    if sheet_name == 'DAQ':
        drop_keywords = ['扫描编号', '编号', '序号', 'No.']
    elif sheet_name == 'SoftwareReading':
        drop_keywords = ['Index', '索引']
    else:
        drop_keywords = []
    cols_to_drop = [c for c in df.columns if any(k in str(c) for k in drop_keywords)]
    if cols_to_drop:
        df.drop(columns=cols_to_drop, inplace=True)
        print(f" 删除列: {cols_to_drop}")
    return df


def prepare_time_column(df, sheet_name):
    """
    准备时间列：
    - DAQ：忽略第一列（日期），使用第二列（时间）
    - 其他：直接使用第一列作为时间
    仅重命名，不解析时间
    """
    if sheet_name == 'DAQ':
        first_col = df.columns[0]
        df.drop(columns=[first_col], inplace=True)
        print(f"    DAQ: 忽略第一列 '{first_col}'，使用第二列作为时间")
        time_col = df.columns[0]
    else:
        time_col = df.columns[0]
        print(f"    {sheet_name}: 使用第一列 '{time_col}' 作为时间")

    if time_col != 'Timestamp':
        df.rename(columns={time_col: 'Timestamp'}, inplace=True)
        time_col = 'Timestamp'
    return df, time_col


def create_multi_curve_image(df, time_col, cols, title, ylabel='数值'):
    """
    绘制曲线：横轴为数据点索引，标签使用时间列的原始字符串
    不解析时间，不修改数据
    """
    n = len(df)
    x = np.arange(n)
    fig, ax = plt.subplots(figsize=(12, 6))

    plotted = False
    for col in cols:
        if col in df.columns:
            y = pd.to_numeric(df[col], errors='coerce')
            if y.notna().any():
                ax.plot(x, y, label=col, linewidth=1.2, alpha=0.8)
                plotted = True

    if not plotted:
        plt.close(fig)
        return None

    ax.set_title(title, fontsize=14)
    ax.set_xlabel('time')
    ax.set_ylabel(ylabel)

    # 横轴标签：直接使用时间列的原始字符串
    time_labels = df[time_col].astype(str).tolist()
    step = max(1, n // 50)
    tick_positions = list(range(0, n, step))
    tick_labels = [time_labels[i] for i in tick_positions if i < len(time_labels)]

    ax.set_xticks(tick_positions)
    ax.set_xticklabels(tick_labels, rotation=45, ha='right', fontsize=8)

    ax.legend(loc='best', fontsize=8, ncol=2)
    ax.grid(True, linestyle='--', alpha=0.5)
    plt.tight_layout()

    buf = io.BytesIO()
    plt.savefig(buf, format='png', dpi=100, bbox_inches='tight')
    buf.seek(0)
    img_b64 = base64.b64encode(buf.read()).decode('utf-8')
    plt.close(fig)
    return img_b64


def plot_daq(df, time_col):
    """DAQ 按 Section 分组绘图"""
    grouped = {}
    for col in df.columns:
        if col == time_col:
            continue
        sec = get_section(col)
        grouped.setdefault(sec, []).append(col)
    images = {}
    for sec, cols in grouped.items():
        if cols:
            img = create_multi_curve_image(df, time_col, cols, sec, ylabel='(°C)')
            if img:
                images[sec] = img
    return images


def plot_power(df, time_col):
    """Power 绘图：优先使用 Power(w) 列（单位瓦特）"""
    # 尝试查找 Power(w) 列
    power_w_col = None
    power_kw_col = None
    for col in df.columns:
        col_clean = str(col).strip()
        if col_clean in ['Power(w)', 'Power (w)', 'Power(W)', 'Power (W)']:
            power_w_col = col
            break
        if 'kw' in col_clean.lower():
            power_kw_col = col

    if power_w_col is not None:
        y_col = power_w_col
        ylabel = '(W)'
        title = 'Power (W)'
    elif power_kw_col is not None:
        # 使用 kW 列，但乘以1000转换为 W
        df_copy = df.copy()
        df_copy['Power_W'] = pd.to_numeric(df_copy[power_kw_col], errors='coerce') * 1000
        y_col = 'Power_W'
        ylabel = '(W)'
        title = 'Power (W)'
    else:
        print("    Power: 未找到功率列")
        return {}

    img = create_multi_curve_image(df, time_col, [y_col], title, ylabel=ylabel)
    return {'Power': img} if img else {}


def plot_software_reading(df, time_col):
    """
    SoftwareReading：拆分成两个独立图表，在菜单中作为子项
    图1：CPU, SOC, MOTION, Z0SOCT, WIFIT
    图2：U5A, U5B, U6A, U6B, U7A, U8A, U8B, U9A, U9B
    """
    print(f"    SoftwareReading 时间列前5个原始值: {df[time_col].head(5).tolist()}")

    # 定义两组列
    group1_cols = ['CPU', 'SOC', 'MOTION', 'Z0SOCT', 'WIFIT']
    group2_cols = ['U5A', 'U5B', 'U6A', 'U6B', 'U7A', 'U8A', 'U8B', 'U9A', 'U9B']

    # 检查哪些列实际存在
    available_group1 = [c for c in group1_cols if c in df.columns]
    available_group2 = [c for c in group2_cols if c in df.columns]

    images = {}

    # 生成图1
    if available_group1:
        print(f"    图1 (CPU组): {available_group1}")
        img1 = create_multi_curve_image(
            df, time_col, available_group1,
            ' System_Metrics',  # 图表标题
            ylabel='data'
        )
        if img1:
            images[' System_Metrics'] = img1  # 这个字符串会作为子菜单名称
    else:
        print(" 警告: 图1 (CPU组) 没有任何可用列")

    # 生成图2
    if available_group2:
        print(f"  图2 (U5A~U9B组): {available_group2}")
        img2 = create_multi_curve_image(
            df, time_col, available_group2,
            'Amplifier_Channels ',
            ylabel='data'
        )
        if img2:
            images['Amplifier_Channels '] = img2
    else:
        print(" 警告: 图2 (U5A~U9B组) 没有任何可用列")

    return images

def plot_gemini_power(df, time_col):
    """GeminiPower：绘制 D1_Pwr_Front 和 D2_Pwr_Rear"""
    # 可选：打印前几个时间值以验证原始数据
    print(f"    GeminiPower 时间列前5个原始值: {df[time_col].head(5).tolist()}")

    target = ['D1_Pwr_Front', 'D2_Pwr_Rear']
    available = [c for c in target if c in df.columns]
    if not available:
        print("    GeminiPower: 未找到 D1_Pwr_Front 或 D2_Pwr_Rear")
        return {}
    img = create_multi_curve_image(df, time_col, available, 'Gemini Power', ylabel='(W)')
    return {'GeminiPower': img} if img else {}


def create_dashboard(excel_path):
    sheets = ['DAQ', 'Power', 'SoftwareReading', 'GeminiPower']
    all_data = {}

    for sheet in sheets:
        print(f"\n处理工作表: {sheet}")
        try:
            df = load_sheet_data(excel_path, sheet)
            df = drop_useless_columns(df, sheet)
            df, time_col = prepare_time_column(df, sheet)

            if sheet == 'DAQ':
                images = plot_daq(df, time_col)
            elif sheet == 'Power':
                images = plot_power(df, time_col)
            elif sheet == 'SoftwareReading':
                images = plot_software_reading(df, time_col)
            elif sheet == 'GeminiPower':
                images = plot_gemini_power(df, time_col)
            else:
                images = {}
            all_data[sheet] = {'images': images}
        except Exception as e:
            print(f"  处理 {sheet} 出错: {e}")
            all_data[sheet] = {'images': {}}

    generate_html(all_data)


def generate_html(all_data):
    menu_items = ''
    content_divs = ''

    for sheet_name, data in all_data.items():
        images = data.get('images', {})
        if not images:
            continue
        sheet_id = sheet_name.replace(' ', '_')

        if sheet_name == 'DAQ':
            menu_items += f'''
            <li class="parent-item" data-target="{sheet_id}">
                <span class="parent-label">{sheet_name}</span>
                <ul class="child-menu">
            '''
            for section_name in images.keys():
                menu_items += f'<li class="child-item" data-parent="{sheet_id}" data-section="{section_name}">{section_name}</li>'
            menu_items += '</ul></li>'

            for section_name, img_b64 in images.items():
                content_divs += f'''
                <div id="content-{sheet_id}-{section_name}" class="chart-content" style="display:none;">
                    <h3>{section_name}</h3>
                    <img src="data:image/png;base64,{img_b64}" style="width:100%;">
                </div>
                '''
        else:
            # 对于非 DAQ 的 sheet，如果 images 有多个键，则生成子菜单；否则直接显示
            if len(images) > 1:
                # 生成子菜单
                menu_items += f'''
                    <li class="parent-item" data-target="{sheet_id}">
                        <span class="parent-label">{sheet_name}</span>
                        <ul class="child-menu">
                    '''
                for sub_name in images.keys():
                    menu_items += f'<li class="child-item" data-parent="{sheet_id}" data-section="{sub_name}">{sub_name}</li>'
                menu_items += '</ul></li>'

                for sub_name, img_b64 in images.items():
                    content_divs += f'''
                        <div id="content-{sheet_id}-{sub_name}" class="chart-content" style="display:none;">
                            <h3>{sub_name}</h3>
                            <img src="data:image/png;base64,{img_b64}" style="width:100%;">
                        </div>
                        '''
            else:
                # 只有一个图，直接显示
                img_b64 = list(images.values())[0]
                menu_items += f'<li class="parent-item" data-target="{sheet_id}"><span class="parent-label">{sheet_name}</span></li>'
                content_divs += f'''
                    <div id="content-{sheet_id}" class="chart-content" style="display:none;">
                        <h3>{sheet_name}</h3>
                        <img src="data:image/png;base64,{img_b64}" style="width:100%;">
                    </div>
                    '''

    if not menu_items:
        print("错误：没有生成任何有效图表。")
        return

    html_template = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <title>多工作表 Dashboard</title>
        <style>
            * {{ margin: 0; padding: 0; box-sizing: border-box; }}
            body {{ font-family: 'Segoe UI', Arial, sans-serif; background: #f0f2f5; height: 100vh; display: flex; }}
            .sidebar {{
                width: 260px;
                background: #2c3e50;
                color: #ecf0f1;
                padding: 20px 0;
                overflow-y: auto;
                flex-shrink: 0;
                height: 100vh;
                position: sticky;
                top: 0;
            }}
            .sidebar h2 {{
                text-align: center;
                font-weight: 300;
                font-size: 20px;
                padding-bottom: 20px;
                border-bottom: 1px solid #34495e;
                margin-bottom: 15px;
                color: #ecf0f1;
            }}
            .sidebar ul {{ list-style: none; padding: 0; }}
            .sidebar li {{
                padding: 12px 25px;
                cursor: pointer;
                transition: background 0.2s;
                border-left: 4px solid transparent;
                font-size: 15px;
            }}
            .sidebar li:hover {{ background: #34495e; }}
            .sidebar li.active {{
                background: #1abc9c;
                border-left-color: #16a085;
                color: #fff;
                font-weight: 600;
            }}
            .sidebar .parent-item .child-menu {{
                display: none;
                padding-left: 20px;
            }}
            .sidebar .parent-item.open .child-menu {{
                display: block;
            }}
            .sidebar .child-item {{
                font-size: 13px;
                padding: 8px 25px;
            }}
            .main-content {{
                flex: 1;
                padding: 30px;
                overflow-y: auto;
                height: 100vh;
            }}
            .chart-content {{
                background: white;
                border-radius: 12px;
                padding: 20px;
                box-shadow: 0 4px 12px rgba(0,0,0,0.08);
                margin-bottom: 20px;
            }}
            .chart-content h3 {{
                margin-bottom: 15px;
                color: #333;
            }}
            .chart-content img {{
                width: 100%;
                height: auto;
            }}
            @media (max-width: 768px) {{
                body {{ flex-direction: column; }}
                .sidebar {{ width: 100%; height: auto; position: relative; }}
                .sidebar ul {{ display: flex; flex-wrap: wrap; justify-content: center; }}
                .sidebar li {{ padding: 8px 15px; font-size: 13px; border-left: none; border-bottom: 3px solid transparent; }}
                .sidebar li.active {{ border-bottom-color: #1abc9c; }}
                .main-content {{ height: auto; padding: 15px; }}
            }}
        </style>
    </head>
    <body>
        <div class="sidebar">
            <h2>Dashboard</h2>
            <ul>
                {menu_items}
            </ul>
        </div>
        <div class="main-content">
            {content_divs}
        </div>
        <script>
            document.querySelectorAll('.parent-item').forEach(parent => {{
                parent.addEventListener('click', function(e) {{
                    if (e.target.closest('.child-item')) return;
                    this.classList.toggle('open');
                    document.querySelectorAll('.chart-content').forEach(c => c.style.display = 'none');
                    const target = this.dataset.target;
                    const children = this.querySelectorAll('.child-item');
                    if (children.length > 0) {{
                        const firstChild = children[0];
                        const section = firstChild.dataset.section;
                        const content = document.getElementById('content-' + target + '-' + section);
                        if (content) content.style.display = 'block';
                        children.forEach(c => c.classList.remove('active'));
                        firstChild.classList.add('active');
                    }} else {{
                        const content = document.getElementById('content-' + target);
                        if (content) content.style.display = 'block';
                    }}
                    document.querySelectorAll('.parent-item').forEach(p => p.classList.remove('active'));
                    this.classList.add('active');
                }});
            }});
            document.querySelectorAll('.child-item').forEach(child => {{
                child.addEventListener('click', function(e) {{
                    e.stopPropagation();
                    const parent = this.closest('.parent-item');
                    const target = parent.dataset.target;
                    const section = this.dataset.section;
                    document.querySelectorAll('.chart-content').forEach(c => c.style.display = 'none');
                    const content = document.getElementById('content-' + target + '-' + section);
                    if (content) content.style.display = 'block';
                    parent.querySelectorAll('.child-item').forEach(c => c.classList.remove('active'));
                    this.classList.add('active');
                    document.querySelectorAll('.parent-item').forEach(p => p.classList.remove('active'));
                    parent.classList.add('active');
                }});
            }});
            // 默认展开第一个
            const firstParent = document.querySelector('.parent-item');
            if (firstParent) {{
                firstParent.classList.add('active');
                const target = firstParent.dataset.target;
                const children = firstParent.querySelectorAll('.child-item');
                if (children.length > 0) {{
                    firstParent.classList.add('open');
                    const firstChild = children[0];
                    firstChild.classList.add('active');
                    const section = firstChild.dataset.section;
                    const content = document.getElementById('content-' + target + '-' + section);
                    if (content) content.style.display = 'block';
                }} else {{
                    const content = document.getElementById('content-' + target);
                    if (content) content.style.display = 'block';
                }}
            }}
        </script>
    </body>
    </html>
    """

    output_file = 'dashboard_all_sheets.html'
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(html_template)

    abs_path = os.path.abspath(output_file)
    print(f"\n✅ 已生成 Dashboard: {abs_path}")
    try:
        webbrowser.open('file://' + abs_path)
    except:
        pass


def select_file_dialog():
    root = tk.Tk()
    root.withdraw()
    file_path = filedialog.askopenfilename(
        title="选择 Excel 数据文件",
        filetypes=[("Excel files", "*.xlsx *.xls"), ("All files", "*.*")]
    )
    root.destroy()
    return file_path if file_path else None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('excel_file', nargs='?', help='Excel 文件路径')
    args = parser.parse_args()
    excel_path = args.excel_file
    if not excel_path:
        print("未指定文件，正在打开文件选择对话框...")
        excel_path = select_file_dialog()
        if not excel_path:
            print("❌ 未选择文件，退出。")
            sys.exit(1)
    if not os.path.exists(excel_path):
        print(f"❌ 文件不存在：{excel_path}")
        sys.exit(1)
    print(f"处理文件：{excel_path}")
    create_dashboard(excel_path)


if __name__ == '__main__':
    main()