#!/usr/bin/env python3

from dify_plugin import DifyPluginEnv, Plugin  # type: ignore

if __name__ == "__main__":
    # 创建配置
    config = DifyPluginEnv()
    
    # 创建插件实例
    plugin = Plugin(config)
    
    # 启动插件
    plugin.run()
