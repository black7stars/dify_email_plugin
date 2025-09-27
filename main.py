#!/usr/bin/env python3

from dify_plugin import DifyPluginEnv, Plugin  # type: ignore
from provider.qq_email_crawler import QqEmailCrawlerProvider
from tools.qq_email_crawler import QqEmailCrawlerTool

if __name__ == "__main__":
    # 创建配置
    config = DifyPluginEnv()
    
    # 创建插件实例并启动
    plugin = Plugin(config)
    plugin.run()
