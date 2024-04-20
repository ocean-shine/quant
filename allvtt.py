import os
import re


current_path = os.path.dirname(__file__)


def merge_vtt_files(en_path, zh_path, output_path):
    # 读取英文和中文字幕文件
    with open(en_path, 'r', encoding='utf-8') as en_file:
        en_lines = en_file.readlines()

    try:
        with open(zh_path, 'r', encoding='utf-8') as zh_file:
            zh_lines = zh_file.readlines()
    except:
        return

    # 合并字幕
    merged_lines = []
    en_index = 0
    zh_index = 0
    while en_index < len(en_lines) and zh_index < len(zh_lines):
        en_line = en_lines[en_index].strip()
        zh_line = zh_lines[zh_index].strip()

        if 'Language:' in en_line or 'Language:' in zh_line:
            # 跳过语言标签行
            en_index += 1
            zh_index += 1
            continue

        if '-->' in en_line and '-->' in zh_line:
            # 合并时间戳行
            merged_lines.append(en_line.strip() + '\n')
            # 获取下一行，即字幕文本行
            en_index += 1
            zh_index += 1
            en_text_line = en_lines[en_index].strip()
            zh_text_line = zh_lines[zh_index].strip()
            # 合并字幕文本行
            merged_lines.append(f'{en_text_line} <v> {zh_text_line}</v>\n')
            en_index += 1
            zh_index += 1
        elif en_line.strip() == '' and zh_line.strip() == '':
            # 如果两个文件都有空行，则合并空行
            merged_lines.append('\n')
            en_index += 1
            zh_index += 1
        else:
            # 如果不是时间戳行，则可能是其他元数据，直接添加
            merged_lines.append(en_line + '\n')
            merged_lines.append(zh_line + '\n')
            en_index += 1
            zh_index += 1

    # 写入合并后的字幕文件
    with open(output_path, 'w', encoding='utf-8') as output_file:
        output_file.writelines(merged_lines)

def list_all_files_in_folder(root_folder):
    all_files = {}
    
    for foldername, subfolders, filenames in os.walk(root_folder):
        for filename in filenames:
            file_path = os.path.join(foldername, filename)
            all_files[filename] = file_path
    
    return all_files


# 使用脚本
root_folder = current_path # 替换为你的根文件夹路径
# find_and_merge_subtitles(root_folder)
# print(root_folder)

import os

def find_vtt_files_in_subfolders(startpath):
    for root, dirs, files in os.walk(startpath):
        for file in files:
            if file.endswith(".en.vtt"):
                en_file = os.path.join(root, file)
                zh_file = en_file.replace(".en.vtt", ".zh-CN.vtt")
                all_file = en_file.replace(".en.vtt", ".all.vtt")
                merge_vtt_files(en_file, zh_file, all_file)
               

# 使用函数，传入你的起始路径
find_vtt_files_in_subfolders(root_folder)

