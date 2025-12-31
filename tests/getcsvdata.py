import pandas as pd
import matplotlib.pyplot as plt


def auto_plot_csv(csv_file):
    """
    自动绘制CSV文件中所有数据的图表
    第一列作为X轴，其余列作为Y轴
    """
    # 读取数据
    df = pd.read_csv(csv_file)

    # 创建图表
    plt.figure(figsize=(10, 6))

    # 自动绘制所有Y轴数据列
    for column in df.columns[1:]:
        plt.plot(df[df.columns[0]], df[column], label=column, marker='o', linewidth=2)

    # 自动设置图表属性
    plt.title(f'Data from {csv_file}')
    plt.xlabel(df.columns[0])
    plt.ylabel('Values')
    plt.legend()
    plt.grid(True, alpha=0.3)
    plt.xticks(rotation=45)
    plt.tight_layout()

    # 显示图表
    plt.show()

    # 打印数据信息
    print(f"数据形状: {df.shape}")
    print(f"绘制的列: {df.columns.tolist()}")


# 使用示例
auto_plot_csv('simoncsv.csv')