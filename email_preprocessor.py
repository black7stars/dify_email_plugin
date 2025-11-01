import quopri
import html
import re
from typing import Optional


def normalize_email_encoding(raw_email_content: str) -> str:
    """
    预处理极端复杂的邮件编码，使其规范化
    
    处理以下编码问题：
    1. quoted-printable编码
    2. UTF-8编码的特殊字符（如=F0=9F=8C=90）
    3. HTML实体编码（如&#8217;）
    4. 编码残留清理
    
    Args:
        raw_email_content: 原始邮件内容字符串
        
    Returns:
        规范化后的邮件内容
    """
    try:
        # 步骤1: 解码quoted-printable编码
        if '=' in raw_email_content and any(c in raw_email_content for c in ['=\n', '=20', '=3D']):
            try:
                # 先尝试解码QP编码
                decoded_bytes = quopri.decodestring(raw_email_content.encode('utf-8'))
                decoded = decoded_bytes.decode('utf-8', errors='replace')
            except Exception:
                # 如果QP解码失败，使用原始内容
                decoded = raw_email_content
        else:
            decoded = raw_email_content
        
        # 步骤2: 清理UTF-8编码的特殊字符（如=F0=9F=8C=90）
        # 匹配quoted-printable格式的UTF-8字节序列
        def decode_quoted_utf8(match):
            hex_str = match.group(1)
            try:
                # 将十六进制转换为字节，然后解码为UTF-8
                byte_val = bytes.fromhex(hex_str)
                return byte_val.decode('utf-8', errors='replace')
            except (ValueError, UnicodeDecodeError):
                # 如果解码失败，返回原始匹配
                return match.group(0)
        
        # 匹配 =XX 格式的QP编码字节
        decoded = re.sub(r'=([A-Fa-f0-9]{2})', decode_quoted_utf8, decoded)
        
        # 步骤3: 解码HTML实体
        try:
            decoded = html.unescape(decoded)
        except Exception:
            # HTML解码失败时继续处理
            pass
        
        # 步骤4: 移除不影响内容的特殊编码残留
        decoded = re.sub(r'=\n', '', decoded)  # 移除QP换行符
        decoded = re.sub(r'=\s+', ' ', decoded)  # 清理QP空格
        decoded = re.sub(r'\s+', ' ', decoded)  # 规范化空格
        decoded = decoded.strip()
        
        return decoded
        
    except Exception as e:
        # 如果预处理过程中出现任何错误，返回原始内容
        return raw_email_content


def preprocess_email_for_flanker(raw_email_content: str) -> str:
    """
    专门为Flanker库预处理邮件内容
    
    此函数检测极端复杂的编码情况，只在必要时进行预处理
    
    Args:
        raw_email_content: 原始邮件内容
        
    Returns:
        预处理后的邮件内容
    """
    # 检测是否需要预处理
    needs_preprocessing = (
        # 检测quoted-printable编码特征
        '=3D' in raw_email_content or
        '=20' in raw_email_content or
        # 检测UTF-8编码的特殊字符
        any(char in raw_email_content for char in ['=F0', '=E2', '=C2']) or
        # 检测HTML实体
        '&#' in raw_email_content or
        # 检测QP换行符
        '=\n' in raw_email_content
    )
    
    if needs_preprocessing:
        return normalize_email_encoding(raw_email_content)
    else:
        return raw_email_content
