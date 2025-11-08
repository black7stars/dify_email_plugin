#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
字符串初始化清洁脚本
用于处理大型字符串文件（约8MB），采用流式处理方式
"""

import re
import os
import sys
from typing import Generator, List, Tuple


class StringCleaner:
    """字符串清洁器类，用于处理大型文本文件"""
    
    def __init__(self):
        # 定义邮件内容清洁模式
        self.patterns = {
            # URL链接 - 包括各种邮件跟踪链接
            'url': re.compile(r'https?://[^\s]+'),
            # 邮件跟踪链接模式 - 常见的邮件服务商跟踪链接
            'tracking_urls': re.compile(r'https?://[a-zA-Z0-9.-]*resend-links\.com[^\s]+'),
            # emoji表情符号
            'emoji': re.compile(r'[\U00010000-\U0010ffff]', flags=re.UNICODE),
            # HTML标签
            'html_tags': re.compile(r'<[^>]+>'),
            # 邮件头信息模式
            'email_headers': re.compile(r'^\s*(发件人|日期|主题|收件人|已发送|转发):.*$', re.MULTILINE | re.IGNORECASE),
            # 邮件分隔线
            'email_separators': re.compile(r'_{10,}'),
            # 邮件转发标记
            'forward_markers': re.compile(r'^\s*转发:\s*\[.*\]\s*$', re.MULTILINE | re.IGNORECASE),
            # 特殊字符（保留基本的标点符号）
            'special_chars': re.compile(r'[^\w\s.,!?;:()\-@#%&*+/=]'),
            # 多个连续空格
            'multiple_spaces': re.compile(r'\s+'),
            # 图片引用标记（常见的图片引用格式）
            'image_references': re.compile(r'\[图片\]|\[图像\]|\[image\]|\.(jpg|jpeg|png|gif|bmp|webp)', re.IGNORECASE),
        }
    
    def clean_text(self, text: str) -> str:
        """清洁单个文本块"""
        if not text.strip():
            return ""
        
        # 应用所有清洁模式
        cleaned = text
        for pattern_name, pattern in self.patterns.items():
            if pattern_name == 'multiple_spaces':
                cleaned = pattern.sub(' ', cleaned)
            else:
                cleaned = pattern.sub('', cleaned)
        
        return cleaned.strip()
    
    def split_into_sentences(self, text: str) -> List[str]:
        """将文本分割成句子"""
        # 简单的句子分割，基于标点符号
        sentences = re.split(r'[.!?]+', text)
        return [s.strip() for s in sentences if s.strip()]
    
    def process_file_streaming(self, input_file: str, output_file: str, 
                              batch_size: int = 5, flush_interval: int = 3) -> Tuple[int, int]:
        """
        流式处理文件
        
        Args:
            input_file: 输入文件路径
            output_file: 输出文件路径
            batch_size: 每批次处理的句子数量
            flush_interval: 每处理多少个批次就刷新输出
            
        Returns:
            Tuple[int, int]: 处理的句子总数和批次数量
        """
        if not os.path.exists(input_file):
            raise FileNotFoundError(f"输入文件不存在: {input_file}")
        
        total_sentences = 0
        total_batches = 0
        current_batch_count = 0
        
        # 确保输出目录存在
        os.makedirs(os.path.dirname(output_file) if os.path.dirname(output_file) else '.', exist_ok=True)
        
        with open(input_file, 'r', encoding='utf-8') as infile, \
             open(output_file, 'w', encoding='utf-8') as outfile:
            
            buffer = ""
            sentence_buffer = []
            
            for line_num, line in enumerate(infile, 1):
                buffer += line
                
                # 分割成句子
                sentences = self.split_into_sentences(buffer)
                
                # 如果句子数量足够一个批次，处理它们
                while len(sentences) >= batch_size:
                    batch_sentences = sentences[:batch_size]
                    buffer = ' '.join(sentences[batch_size:])
                    
                    # 处理这个批次的句子
                    cleaned_batch = []
                    for sentence in batch_sentences:
                        cleaned = self.clean_text(sentence)
                        if cleaned:  # 只保留非空句子
                            cleaned_batch.append(cleaned)
                    
                    # 添加到句子缓冲区
                    sentence_buffer.extend(cleaned_batch)
                    total_sentences += len(cleaned_batch)
                    total_batches += 1
                    current_batch_count += 1
                    
                    # 检查是否需要刷新输出
                    if current_batch_count >= flush_interval:
                        self._flush_buffer(sentence_buffer, outfile)
                        sentence_buffer = []
                        current_batch_count = 0
                        print(f"已处理 {total_batches} 个批次，{total_sentences} 个句子")
                    
                    # 更新句子列表
                    sentences = self.split_into_sentences(buffer)
            
            # 处理剩余的句子
            if sentences:
                cleaned_sentences = [self.clean_text(s) for s in sentences if self.clean_text(s)]
                sentence_buffer.extend(cleaned_sentences)
                total_sentences += len(cleaned_sentences)
                total_batches += 1
            
            # 刷新剩余的缓冲区内容
            if sentence_buffer:
                self._flush_buffer(sentence_buffer, outfile)
                print(f"最终处理: {total_batches} 个批次，{total_sentences} 个句子")
        
        return total_sentences, total_batches
    
    def _flush_buffer(self, sentence_buffer: List[str], outfile) -> None:
        """将缓冲区内容写入文件"""
        if sentence_buffer:
            outfile.write('\n'.join(sentence_buffer) + '\n')
            outfile.flush()  # 强制刷新缓冲区，重置环境时间计数
            os.fsync(outfile.fileno())  # 确保数据写入磁盘


def main():
    """主函数"""
    if len(sys.argv) != 3:
        print("用法: python string_init.py <输入文件> <输出文件>")
        print("示例: python string_init.py input.txt cleaned_output.txt")
        sys.exit(1)
    
    input_file = sys.argv[1]
    output_file = sys.argv[2]
    
    cleaner = StringCleaner()
    
    try:
        print(f"开始处理文件: {input_file}")
        print("清洁模式:")
        print("  - 移除URL链接")
        print("  - 移除emoji表情")
        print("  - 移除特殊字符")
        print("  - 移除HTML标签")
        print("  - 规范化空格")
        print(f"批次设置: 每批次5个句子，每3个批次刷新输出")
        print("-" * 50)
        
        total_sentences, total_batches = cleaner.process_file_streaming(
            input_file, output_file, batch_size=5, flush_interval=3
        )
        
        print("-" * 50)
        print(f"处理完成!")
        print(f"总处理批次: {total_batches}")
        print(f"总处理句子: {total_sentences}")
        print(f"输出文件: {output_file}")
        
    except Exception as e:
        print(f"处理过程中发生错误: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
