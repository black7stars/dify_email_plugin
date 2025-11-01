import imaplib
import socket
import traceback
from collections.abc import Generator
from datetime import datetime, date, timedelta, timezone
from typing import Any

from flanker import mime    # type: ignore
from dify_plugin import Tool  # type: ignore
from dify_plugin.entities.tool import ToolInvokeMessage  # type: ignore

# -------------------- 日志配置 --------------------
import logging
from dify_plugin.config.logger_format import plugin_logger_handler  # type: ignore

logger = logging.getLogger("qq_email_crawler")
logger.setLevel(logging.INFO)
logger.addHandler(plugin_logger_handler)

def _log(tag: str, obj: Any) -> None:
    """格式化并记录日志"""
    msg = f"{tag} | {type(obj)} | {repr(obj)[:200]}"
    logger.info(msg)


# ====================== 时区工具 ======================
CHINA_TZ = timezone(timedelta(hours=8), name="Asia/Shanghai")


def china_today() -> date:
    """返回北京时间下的今天日期"""
    return datetime.now(CHINA_TZ).date()


class QqEmailCrawlerTool(Tool):
    def _invoke(
        self, tool_parameters: dict[str, Any]
    ) -> Generator[ToolInvokeMessage, None, None]:
        try:
            _log("START", "===== 开始抓取（Asia/Shanghai） =====")
            # 1. 凭证
            try:
                email_address = self.runtime.credentials["email_address"]
                auth_code = self.runtime.credentials["authorization_code"]
                _log("CREDS", f"email={email_address}")
            except KeyError as e:
                raise Exception("邮箱凭证未配置或无效，请在插件设置中提供邮箱地址和授权码") from e

            folder_name = tool_parameters.get("folder_name", "INBOX")
            output_format = tool_parameters.get("output_format", "markdown")
            _log("PARAMS", f"folder={folder_name} format={output_format}")

            # 2. 连接（添加超时和DNS解析异常处理）
            try:
                # 设置socket超时（15秒）
                socket.setdefaulttimeout(15)
                _log("SOCKET", "设置15秒超时")
                
                mail = imaplib.IMAP4_SSL("imap.qq.com", 993)
                _log("IMAP", "SSL连接建立")
                mail.login(email_address, auth_code)
                _log("IMAP", "登录成功")
                # 针对 IMAP mailbox 名称做 modified-UTF-7 编码以支持非 ASCII（如中文）
                encoded_folder = self._encode_mailbox(folder_name)
                status, resp = mail.select(encoded_folder)
                _log("IMAP", f"select status={status} resp={resp} folder={folder_name} encoded={encoded_folder}")
                if status != 'OK':
                    # 选择失败时尝试列出可用 mailbox 并尝试一些常见变体（以便自动修正或诊断）
                    try:
                        list_status, mailboxes = mail.list()
                        _log("IMAP_MAILBOXES", f"list_status={list_status} mailboxes={mailboxes}")
                        # 获取 root 列表和 INBOX. 子文件夹列表
                        try:
                            _log("IMAP_LIST", "--- 列出根路径文件夹 ---")
                            root_status, root_list = mail.list(directory="")
                            _log("ROOT_MAILBOXES", f"status={root_status} mailboxes={root_list}")
                            _log("IMAP_LIST", "--- 列出 INBOX 子文件夹 ---")
                            inbox_status, inbox_list = mail.list(directory="INBOX")
                            _log("INBOX_MAILBOXES", f"status={inbox_status} mailboxes={inbox_list}")
                        except Exception as le:
                            _log("LIST_DETAILS_ERROR", f"获取详细列表失败: {le}")

                        # mailboxes 可能为 bytes 列表，解析最后一段作为 mailbox token
                        candidates = []
                        for item in mailboxes or []:
                            try:
                                if isinstance(item, bytes):
                                    s = item.decode('utf-8', errors='replace')
                                else:
                                    s = str(item)
                                # mailbox 名通常在最后的引号里
                                if '"' in s:
                                    token = s.split('"')[-2]
                                else:
                                    token = s.split()[-1]
                                candidates.append(token)
                            except Exception:
                                continue

                        # 如果有候选 mailbox 包含我们编码后的名字或原始名字，尝试 select
                        tried = []
                        for cand in candidates:
                            try:
                                # server 返回的名字可能已是 modified-utf7，因此直接尝试
                                if encoded_folder in cand or folder_name in cand:
                                    _log("IMAP_AUTOTRY", f"尝试用候选 mailbox 选择: {cand}")
                                    s2, r2 = mail.select(cand)
                                    _log("IMAP_AUTOTRY", f"autotry select status={s2} resp={r2} cand={cand}")
                                    if s2 == 'OK':
                                        # 成功，更新状态并立即退出重试
                                        status = s2
                                        resp = r2
                                        _log("IMAP_SELECT", f"使用完整路径选择成功: {cand}")
                                        break
                                    tried.append((cand, s2, r2))
                            except Exception as e:
                                _log("IMAP_AUTOTRY_ERROR", f"尝试 select 候选 {cand} 失败: {e}")

                        # 只有在之前的尝试都失败时才尝试 INBOX 前缀
                        if candidates and status != 'OK' and not any(t[1] == 'OK' for t in tried):
                            prefix_try = f"INBOX.{encoded_folder}"
                            try:
                                _log("IMAP_AUTOTRY", f"尝试 INBOX 前缀: {prefix_try}")
                                s3, r3 = mail.select(prefix_try)
                                _log("IMAP_AUTOTRY", f"prefix select status={s3} resp={r3} pref={prefix_try}")
                                if s3 == 'OK':
                                    status = s3
                                    resp = r3
                            except Exception as e:
                                _log("IMAP_AUTOTRY_ERROR", f"尝试 INBOX 前缀 select 失败: {e}")

                    except Exception as list_e:
                        _log("IMAP_LIST_FAILED", f"列出 mailbox 失败: {list_e}")

                    if status != 'OK':
                        raise Exception(f"选择文件夹失败: status={status} resp={resp} folder={folder_name}")
                
            except socket.gaierror as e:
                raise Exception(f"DNS解析失败，无法连接到QQ邮箱服务器: {e}") from e
            except socket.timeout as e:
                raise Exception(f"连接QQ邮箱服务器超时（15秒）: {e}") from e
            except ConnectionRefusedError as e:
                raise Exception(f"连接被拒绝，无法连接到QQ邮箱服务器: {e}") from e

            # 3. 用北京时间计算“今天”
            today_date = china_today()
            # IMAP 日期格式：05-Oct-2023
            today_str = today_date.strftime("%d-%b-%Y")
            _log("DATE", f"china_today={today_date}  imap_str={today_str}")

            # ① ON 优先
            search_criteria = f'(ON "{today_str}")'
            _log("SEARCH", f"criteria={search_criteria}")
            status, messages = mail.search(None, search_criteria)
            _log("SEARCH", f"ON_status={status} raw_ids={messages}")
            email_ids = messages[0].split()
            _log("SEARCH", f"ON命中数量={len(email_ids)}")

            # ② ON 无结果 → SINCE 兜底
            if not email_ids:
                search_criteria = f'(SINCE "{today_str}")'
                _log("SEARCH", f"兜底criteria={search_criteria}")
                status, messages = mail.search(None, search_criteria)
                _log("SEARCH", f"SINCE_status={status} raw_ids={messages}")
                email_ids = messages[0].split()
                _log("SEARCH", f"SINCE命中数量={len(email_ids)}")

            # ③ 仍为空
            if not email_ids:
                _log("SEARCH", "北京时间今日无邮件，返回空结果")
                yield self.create_text_message(
                    f"【{today_date}（北京时间）】文件夹 `{folder_name}` 未找到任何邮件。"
                )
                return


            # 4. 优化抓取（分批 yield + 日期筛选）
            emails_content = []
            batch_size = 10
            batch_count = 0
            from email.utils import parsedate_to_datetime

            for idx, email_id in enumerate(email_ids, 1):
                _log("PROCESS", f"----- 第 {idx}/{len(email_ids)} 封 -----")
                status, msg_data = mail.fetch(email_id, "(RFC822)")
                raw_email = self._extract_raw_bytes(msg_data)

                # 使用Flanker解析邮件（尽量防护编码问题）
                msg = None
                decode_try = raw_email.decode('utf-8', errors='replace')
                _log("PARSE_INPUT", f"Raw email first line: {decode_try.split('\\n')[0]}")

                try:
                    # 优先使用 from_string
                    msg = mime.from_string(decode_try)
                    _log("PARSE_RESULT", f"from_string 成功，类型: {type(msg)}")
                except Exception as e1:
                    _log("FLANKER_PARSE_ERROR", f"from_string 解析失败: {e1}")
                    # 如果 Flanker 支持 from_bytes，尝试用 bytes 解析
                    try:
                        if hasattr(mime, 'from_bytes'):
                            msg = mime.from_bytes(raw_email)
                            _log("PARSE_RESULT", f"from_bytes 成功，类型: {type(msg)}")
                        else:
                            raise
                    except Exception as e2:
                        _log("FLANKER_PARSE_ERROR", f"from_bytes 解析失败或不可用: {e2}")
                        # 备用：对原始内容做更强预处理后重试
                        try:
                            from email_preprocessor import preprocess_email_for_flanker
                            pre = preprocess_email_for_flanker(decode_try)
                            msg = mime.from_string(pre)
                        except Exception as e3:
                            _log("FLANKER_PARSE_FATAL", f"最终解析失败: {e3}")
                            raise

                # 邮件头日期筛选（只处理当天邮件）
                date_received_raw = None
                if hasattr(msg, 'headers') and isinstance(msg.headers, dict):
                    date_received_raw = msg.headers.get('Date')
                if not date_received_raw and hasattr(msg, 'get_header'):
                    date_received_raw = msg.get_header('Date')
                if not date_received_raw and hasattr(msg, 'content_header'):
                    for key, value in msg.content_header:
                        if key.lower() == 'date':
                            date_received_raw = value
                            break
                # 解析为 datetime
                is_today = True
                try:
                    dt = parsedate_to_datetime(date_received_raw) if date_received_raw else None
                    if dt:
                        dt = dt.astimezone(CHINA_TZ)
                        if dt.date() != today_date:
                            is_today = False
                except Exception as e:
                    _log("DATE_PARSE_ERROR", f"解析邮件日期失败: {e} 原始值: {date_received_raw}")
                if not is_today:
                    continue  # 跳过非当天邮件

                # 获取邮件信息（尽量保证字符串安全）
                subject = (getattr(msg, 'subject', None) or "无主题")
                sender = self._format_sender(msg) or "未知发件人"
                date_received = date_received_raw or '未知日期'
                body = self._get_email_body_flanker(msg) or "[无内容]"

                # 将可能包含非标准字符的字段规范为安全字符串
                subject = self._safe_str(subject)
                sender = self._safe_str(sender)
                date_received = self._safe_str(date_received)
                body = self._safe_str(body)

                formatted = self._format_email_content(
                    subject,
                    sender,
                    date_received,
                    body,
                    output_format,
                )
                emails_content.append(formatted)
                batch_count += 1
                if batch_count % batch_size == 0:
                    yield self.create_text_message(self._merge_emails(emails_content, output_format))
                    emails_content = []

            mail.close()
            mail.logout()
            _log("IMAP", "连接已关闭")

            if emails_content:
                yield self.create_text_message(self._merge_emails(emails_content, output_format))

        except Exception as e:
            _log("FATAL", f"异常类型={type(e)} 消息={e}")
            _log("TRACEBACK", traceback.format_exc())
            error_msg = f"爬取邮件失败: {e}"
            logger.error(error_msg)
            logger.error(f"完整回溯: {traceback.format_exc()}")
            raise Exception(error_msg) from e    # -------------------- Flanker工具函数 --------------------
    def _extract_raw_bytes(self, msg_data: Any) -> bytes:
        """提取邮件原始字节内容。
        
        msg_data 可能的结构:
        1. [(b'1 {1234}', b'实际邮件内容'), b')']  # list 形式
        2. ((b'1 {1234}', b'实际邮件内容'), b')')  # tuple 形式
        """
        _log("EXTRACT", f"msg_data type={type(msg_data)} content={msg_data}")
        
        # 统一处理 list 和 tuple
        if isinstance(msg_data, (list, tuple)) and len(msg_data) > 0:
            first_item = msg_data[0]
            if isinstance(first_item, (list, tuple)) and len(first_item) > 1:
                raw = first_item[1]
                if isinstance(raw, bytes):
                    return raw
            
            # 记录更多信息以便诊断
            _log("EXTRACT_DETAIL", f"first_item type={type(first_item)} content={first_item}")
        
        raise ValueError(f"Invalid message data structure: {type(msg_data)}")
        if isinstance(raw, bytes):
            return raw
        if isinstance(raw, (int, float, str)):
            return str(raw).encode("utf-8", errors="replace")
        return bytes(raw)

    def _encode_mailbox(self, mailbox_name: str) -> str:
        """将 mailbox 名称编码为 IMAP4-modified UTF-7（RFC3501），以支持中文等非 ASCII 名称。

        返回可被 imaplib.select/append 等方法接受的 ASCII-safe 字符串。
        如果编码失败或 mailbox_name 本身已为 ASCII，则返回原始字符串。
        """
        import base64

        def _modified_utf7_encode(s: str) -> str:
            # 实现 IMAP modified UTF-7 的最小编码器（RFC 3501）
            res = []
            buf = []

            def flush_buf():
                if not buf:
                    return
                seg = ''.join(buf)
                # 将非 ASCII 段编码为 UTF-16BE，再 base64，替换 '/' -> ','，去掉尾部 '='
                b = seg.encode('utf-16-be')
                b64 = base64.b64encode(b).decode('ascii')
                b64 = b64.replace('/', ',').rstrip('=')
                res.append('&' + b64 + '-')
                buf.clear()

            for ch in s:
                if ord(ch) >= 0x20 and ord(ch) < 0x7f and ch != '&':
                    # 可打印 ASCII 且非 '&'，先 flush 非 ASCII 缓冲
                    flush_buf()
                    res.append(ch)
                elif ch == '&':
                    flush_buf()
                    res.append('&-')
                else:
                    buf.append(ch)

            flush_buf()
            return ''.join(res)

        try:
            # 如果全部为 ASCII 且不包含 '&'，直接返回
            if all(ord(c) < 128 and c != '&' for c in mailbox_name):
                return mailbox_name

            # 优先使用标准 codec
            try:
                encoded = mailbox_name.encode('imap4-utf-7')
                return encoded.decode('ascii')
            except Exception:
                # codec 不可用或失败，使用自实现的 modified-UTF7 编码
                return _modified_utf7_encode(mailbox_name)
        except Exception as e:
            _log("ENCODE_MAILBOX_ERROR", f"编码 mailbox 失败: {e}; mailbox={mailbox_name}")
            return mailbox_name

    def _format_sender(self, msg) -> str:
        """
        兼容 Flanker Message、MimePart、dict、str 等所有情况，安全返回发件人。
        """
        _log("FORMAT_SENDER", f"msg type={type(msg)}")
        try:
            sender = None
            # 1. Flanker Message 类型
            if hasattr(msg, 'from_addr'):
                sender = msg.from_addr
                _log("SENDER", f"from from_addr: {sender}")
            # 2. 标准 headers 字典
            if not sender and hasattr(msg, 'headers') and isinstance(msg.headers, dict):
                sender = msg.headers.get('From') or msg.headers.get('from')
                _log("SENDER", f"from headers: {sender}")
            # 3. MimePart get_header 方法
            if not sender and hasattr(msg, 'get_header'):
                sender = msg.get_header('from') or msg.get_header('From')
                _log("SENDER", f"from get_header: {sender}")
            # 4. MimePart content_header 属性（list of tuple）
            if not sender and hasattr(msg, 'content_header'):
                for key, value in msg.content_header:
                    if key.lower() == 'from':
                        sender = value
                        break
                _log("SENDER", f"from content_header: {sender}")
            # 5. 直接 dict
            if not sender and isinstance(msg, dict):
                sender = msg.get('From') or msg.get('from')
                _log("SENDER", f"from dict: {sender}")
            # 6. 直接字符串
            if not sender and isinstance(msg, str):
                sender = msg
                _log("SENDER", f"from str: {sender}")
            # 7. 兜底：尝试 msg.headers 属性为 list/tuple
            if (
                not sender
                and hasattr(msg, 'headers')
                and not isinstance(msg, (str, dict))
                and isinstance(msg.headers, (list, tuple))
            ):
                for item in msg.headers:
                    if isinstance(item, tuple) and item[0].lower() == 'from':
                        sender = item[1]
                        break
                _log("SENDER", f"from headers tuple: {sender}")
            # 8. 兜底：尝试 msg.header 属性为 list/tuple
            if (
                not sender
                and hasattr(msg, 'header')
                and not isinstance(msg, (str, dict))
                and isinstance(msg.header, (list, tuple))
            ):
                for item in msg.header:
                    if isinstance(item, tuple) and item[0].lower() == 'from':
                        sender = item[1]
                        break
                _log("SENDER", f"from header tuple: {sender}")
            # 9. 处理列表/元组
            if isinstance(sender, (list, tuple)) and len(sender) > 0:
                sender = sender[0]
            # 10. 处理可能的地址对象
            if hasattr(sender, 'address'):
                name = getattr(sender, 'display_name', None)
                email = getattr(sender, 'address', None)
                if name and email:
                    return f"{name} <{email}>"
                elif email:
                    return email
                elif name:
                    return name
            # 11. 直接字符串
            if sender:
                return str(sender)
            return "未知发件人"
        except Exception as e:
            _log("FORMAT_SENDER_ERROR", f"格式化发件人失败: {e}")
            return "未知发件人"

    def _get_email_body_flanker(self, msg) -> str:
        """使用Flanker获取邮件正文（集成预处理功能）"""
        try:
            body_parts = []
            
            # 获取纯文本正文
            text_body = msg.body
            if text_body:
                # 对文本正文进行预处理
                preprocessed_text = self._preprocess_email_content(str(text_body))
                body_parts.append(preprocessed_text)
            
            # 获取HTML正文（如果没有纯文本）
            if not text_body and hasattr(msg, 'html_body') and msg.html_body:
                # 对HTML正文进行预处理
                import re
                html_text = str(msg.html_body)
                preprocessed_html = self._preprocess_email_content(html_text)
                # 清理HTML标签，保留文本内容
                clean_text = re.sub(r'<[^>]+>', ' ', preprocessed_html)
                # 清理多余空格
                clean_text = re.sub(r'\s+', ' ', clean_text).strip()
                if clean_text:
                    body_parts.append(clean_text)
            
            # 处理多部分邮件
            if hasattr(msg, 'parts') and msg.parts:
                for part in msg.parts:
                    if part.content_type.is_singlepart() and part.content_type.main == 'text':
                        if part.content_type.sub == 'plain' and part.body:
                            preprocessed_part = self._preprocess_email_content(str(part.body))
                            body_parts.append(preprocessed_part)
                        elif part.content_type.sub == 'html' and part.body:
                            # 对HTML部分进行预处理
                            import re
                            html_text = str(part.body)
                            preprocessed_html = self._preprocess_email_content(html_text)
                            clean_text = re.sub(r'<[^>]+>', ' ', preprocessed_html)
                            clean_text = re.sub(r'\s+', ' ', clean_text).strip()
                            if clean_text:
                                body_parts.append(clean_text)
                    elif part.content_type.is_multipart():
                        # 递归处理嵌套的多部分
                        nested_body = self._get_email_body_flanker(part)
                        if nested_body:
                            body_parts.append(nested_body)
            
            return "\n\n".join(body_parts) if body_parts else "[无文本内容]"
            
        except Exception as e:
            _log("FLANKER_BODY_ERROR", f"Error getting body with flanker: {e}")
            return "[邮件内容解析错误]"

    def _format_email_content(self, subject, sender, date, body, format_type):
        if format_type == "markdown":
            return (
                f"## {subject}\n\n"
                f"**发件人:** {sender}\n\n"
                f"**日期:** {date}\n\n"
                f"{body}\n\n---\n"
            )
        if format_type == "html":
            return (
                f"<h2>{subject}</h2>"
                f"<p><strong>发件人:</strong> {sender}</p>"
                f"<p><strong>日期:</strong> {date}</p>"
                f"<div>{body}</div><hr>"
            )
        return (
            f"主题: {subject}\n"
            f"发件人: {sender}\n"
            f"日期: {date}\n\n"
            f"{body}\n\n{'-'*50}\n"
        )

    def _safe_str(self, obj: Any) -> str:
        """安全地将对象转换为字符串，处理编码问题"""
        try:
            if isinstance(obj, str):
                return obj
            return str(obj)
        except (UnicodeEncodeError, UnicodeDecodeError):
            # 如果遇到编码问题，使用repr并清理
            return repr(obj).encode('utf-8', errors='replace').decode('utf-8')

    def _preprocess_email_content(self, content: str) -> str:
        """
        改进预处理邮件内容，处理极端复杂的编码情况
        """
        try:
            import quopri
            import html
            import re

            # 解码 quoted-printable 编码
            try:
                content = quopri.decodestring(content.encode("utf-8")).decode("utf-8", errors="replace")
            except Exception as e:
                _log("PREPROCESS", f"QP解码失败: {e}")

            # 解码 HTML 实体
            try:
                content = html.unescape(content)
            except Exception as e:
                _log("PREPROCESS", f"HTML解码失败: {e}")

            # 清理多余的空格和特殊字符
            content = re.sub(r"\s+", " ", content).strip()
            return content

        except Exception as e:
            _log("PREPROCESS_ERROR", f"预处理失败: {e}")
            return content

    def _merge_emails(self, emails_content, format_type):
        today_str = china_today().strftime("%Y-%m-%d")
        emails_content = [self._safe_str(c) for c in emails_content]
        if format_type == "markdown":
            return f"# QQ邮箱邮件汇总 ({today_str})\n\n" + "\n".join(emails_content)
        if format_type == "html":
            return f"<h1>QQ邮箱邮件汇总 ({today_str})</h1>" + "".join(emails_content)
        return f"QQ邮箱邮件汇总 ({today_str})\n\n" + "\n".join(emails_content)
