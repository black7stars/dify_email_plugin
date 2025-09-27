import imaplib
from typing import Any

from dify_plugin import ToolProvider    # type: ignore
from dify_plugin.errors.tool import ToolProviderCredentialValidationError   # type: ignore


class QqEmailCrawlerProvider(ToolProvider):
    def _validate_credentials(self, credentials: dict[str, Any]) -> None:
        """
        验证QQ邮箱凭证是否有效
        """
        email_address = credentials.get("email_address")
        auth_code = credentials.get("authorization_code")

        if not email_address or not auth_code:
            raise ToolProviderCredentialValidationError("邮箱地址和授权码不能为空")

        try:
            # 连接到QQ邮箱IMAP服务器
            imap_server = imaplib.IMAP4_SSL("imap.qq.com", 993)
            # 尝试登录
            imap_server.login(email_address, auth_code)
            # 关闭连接
            imap_server.logout()
        except Exception as e:
            raise ToolProviderCredentialValidationError(f"邮箱凭证验证失败: {e}")
