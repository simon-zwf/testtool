# ==================================================
# !/usr/bin/env python
# @Author: simon.zhang
# @Date: 2025/10/23 15:30
# @FileName: remove_chinese.py
# @Email: wangfu_zhang@ggec.com.cn
# ==================================================
import re

def remove_chinese():
    input_file = "F:/other/midschoolword.txt"
    chinese_output = "chinese_only.txt"
    english_output = "english_only.txt"
   #打开源文件
    with open(input_file, 'r', encoding="UTF-8") as f:
        text = f.read()
   #分别通过正则表达式提示中文和英文
    chinese_text = "".join(re.findall(r'[\u4e00-\u9fff]+',text))
    english_text = re.sub(r'[^\a-zA-Z]','', text)
    #把提取出来中文和英文写入文件
    with open(chinese_output,'w',encoding="UTF-8") as f:
        f.write(chinese_text)
    with open(english_output, 'w', encoding="UTF-8") as f:
        f.write(english_text)

    #打印输出
    print(f"输出中文，{chinese_output}")
    print(f"输出英文，{english_output}")
if __name__ == "__main__":
    remove_chinese()
