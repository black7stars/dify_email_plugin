import imaplib
import socket
import re
from typing import Any

from dify_plugin import ToolProvider    # type: ignore
from dify_plugin.errors.tool import ToolProviderCredentialValidationError   # type: ignore


class QqEmailCrawlerProvider(ToolProvider):
    def _validate_credentials(self, credentials: dict[str, Any]) -> None:
        """
        验证QQ邮箱凭证是否有效
        """
        email_address = credentials.get("email_address", "").strip()
        auth_code = credentials.get("authorization_code", "").strip()

        # 基本格式验证
        if not email_address or not auth_code:
            raise ToolProviderCredentialValidationError("邮箱地址和授权码不能为空")

        # 改进邮箱格式验证
        email_pattern = r'^[a-zA-Z0-9._%+-]+@qq\.com$'
        if not re.match(email_pattern, email_address, re.IGNORECASE):
            raise ToolProviderCredentialValidationError("请输入有效的QQ邮箱地址（格式：username@qq.com）")

        # 放宽授权码长度限制
        if len(auth_code) < 8 or len(auth_code) > 32:
            raise ToolProviderCredentialValidationError(f"授权码长度应在8-32位之间，当前为{len(auth_code)}位")

        try:
            # 设置socket超时（10秒）
            socket.setdefaulttimeout(10)
            
            # 连接到QQ邮箱IMAP服务器
            imap_server = imaplib.IMAP4_SSL("imap.qq.com", 993)
            
            # 尝试登录
            imap_server.login(email_address, auth_code)
            
            # 关闭连接
            imap_server.logout()
            
        except socket.timeout:
            raise ToolProviderCredentialValidationError("连接QQ邮箱服务器超时（10秒），请检查网络连接或稍后重试")
        except imaplib.IMAP4.error as e:
            error_msg = str(e)
            print(f"IMAP详细错误信息: {error_msg}")  # 调试信息
            
            # 处理QQ邮箱特定的错误信息
            if "ACCOUNT IS ABNORMAL" in error_msg.upper():
                raise ToolProviderCredentialValidationError(
                    "账户异常：QQ邮箱账户可能被限制或异常。\n"
                    "请登录QQ邮箱网页版检查账户状态，或联系QQ邮箱客服"
                )
            elif "SERVICE IS NOT OPEN" in error_msg.upper():
                raise ToolProviderCredentialValidationError(
                    "IMAP服务未开启：请先开启QQ邮箱的IMAP服务。\n"
                    "操作步骤：\n"
                    "1. 登录QQ邮箱网页版\n"
                    "2. 点击【设置】->【账户】\n"
                    "3. 找到【POP3/IMAP/SMTP/Exchange/CardDAV/CalDAV服务】\n"
                    "4. 开启【IMAP/SMTP服务】\n"
                    "5. 按照提示获取授权码"
                )
            elif "PASSWORD IS INCORRECT" in error_msg.upper():
                raise ToolProviderCredentialValidationError(
                    "密码/授权码错误：请确认授权码是否正确。\n"
                    "注意：授权码不是QQ邮箱登录密码，需要单独生成"
                )
            elif "LOGIN FREQUENCY LIMITED" in error_msg.upper():
                raise ToolProviderCredentialValidationError(
                    "登录频率受限：短时间内登录尝试次数过多。\n"
                    "请等待一段时间后重试，或检查是否有其他应用在使用此邮箱"
                )
            elif "SYSTEM IS BUSY" in error_msg.upper():
                raise ToolProviderCredentialValidationError(
                    "系统繁忙：QQ邮箱服务器暂时繁忙。\n"
                    "请稍后重试"
                )
            elif "AUTHENTICATIONFAILED" in error_msg.upper():
                raise ToolProviderCredentialValidationError(
                    "认证失败：邮箱地址或授权码错误。请确认：\n"
                    "1. 邮箱地址是否正确\n"
                    "2. 授权码是否正确（注意大小写）\n"
                    "3. QQ邮箱的IMAP服务是否已开启\n"
                    "4. 授权码是否已过期"
                )
            elif "LOGIN" in error_msg.upper():
                raise ToolProviderCredentialValidationError(
                    "登录失败：请确认授权码是否正确且未过期。\n"
                    "如需重新获取授权码，请登录QQ邮箱网页版 -> 设置 -> 账户 -> POP3/IMAP/SMTP/Exchange/CardDAV/CalDAV服务 -> 开启IMAP/SMTP服务"
                )
            elif "SSL" in error_msg.upper():
                raise ToolProviderCredentialValidationError("SSL连接失败，请检查网络环境或尝试更换网络")
            else:
                raise ToolProviderCredentialValidationError(f"IMAP服务器返回错误: {error_msg}")
        except ConnectionRefusedError:
            raise ToolProviderCredentialValidationError("无法连接到QQ邮箱服务器（连接被拒绝），请检查：\n1. 网络连接\n2. 防火墙设置\n3. 代理设置")
        except Exception as e:
            error_type = type(e).__name__
            raise ToolProviderCredentialValidationError(
                f"验证过程中发生意外错误：{error_type}: {str(e)}\n"
                "请检查网络连接和系统配置"
            )
