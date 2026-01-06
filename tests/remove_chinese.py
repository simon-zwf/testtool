# ==================================================
# !/usr/bin/env python
# @Author: simon.zhang
# @Date: 2025/10/23 15:30
# @FileName: remove_chinese.py
# @Email: wangfu_zhang@ggec.com.cn
# ==================================================
"""
功能：分离中英文
步骤：加载原始文件-》通过正则分别提取中英文-》提取出来写入文件
"""
import  re

def remove_chinese():
    input_file = "F:/other/midschoolword.txt"
    chinese_output = "chinese_only.txt"
    english_output = "english_only.txt"
    # 打开源文件
    with open(input_file, "r", encoding='utf-8') as f:
        text = f.read()
    # 通过正则表达式分别提示中英文
    # 4e00	十六进制数，对应汉字 “一”（最简单的汉字之一）从 “一” 到 “鿿” 之间的所有字符 → 覆盖了几乎所有常用汉字
    chinese_text = "".join(re.findall(r'[\u4e00-\u9fff]+' ,text))
    # 把所有非字母删掉
    english_text = re.sub(r'[^\a-zA-Z]','', text)
    # 把提取出来中文和英文分别写入文件
    with open(chinese_output, 'w', encoding="utf-8") as f:
        f.write(chinese_text)

    with open(english_output, "w", encoding="utf-8") as f:
        f.write(english_text)

    # 打印输出
    print(f"output chinese, {chinese_output}")
    print(f"output english, {english_output}")

if __name__ == "__main__":
    remove_chinese()
