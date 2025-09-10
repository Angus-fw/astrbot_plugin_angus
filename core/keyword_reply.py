import os
import json
from astrbot.api import logger
from astrbot.api.star import StarTools

class KeywordReplyManager:
    def __init__(self, data_dir=None, config=None):
        # 保存配置
        self.config = config or {}
        self.enable = self.config.get('enable_keyword_reply', True)
        
        # 设置数据目录
        if data_dir is None:
            data_dir = StarTools.get_data_dir("astrbot_plugin_angus")
        self.keyword_config_path = os.path.join(data_dir, "keyword_reply_config.json")
        self.keyword_map = self._load_keyword_config()
        logger.info(f"关键词回复配置文件路径：{self.keyword_config_path}")

    def _load_keyword_config(self) -> dict:
        try:
            if not os.path.exists(self.keyword_config_path):
                return {}
            with open(self.keyword_config_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"关键词回复配置加载失败: {str(e)}")
            return {}

    def _save_keyword_config(self, data: dict):
        try:
            with open(self.keyword_config_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"关键词回复配置保存失败: {str(e)}")

    def parse_add_command(self, message: str) -> tuple[str, str, str]:
        """解析添加关键词回复的命令
        
        Args:
            message: 完整的命令消息
            
        Returns:
            tuple: (错误消息或None, 关键词, 回复内容)
        """
        # 清理消息中的空白字符
        message = message.strip()
        # logger.info(f"正在解析命令：{message}")
        
        command_prefixes = [
            "/si 添加回复",
            "si 添加回复",
            "添加回复 ",
            "/si 添加关键词",
            "si 添加关键词",
            "添加关键词 ",
            "/si 添加",
            "si 添加",
            "添加 "
        ]
        
        # 检查是否包含任何命令前缀
        has_prefix = False
        for prefix in command_prefixes:
            # logger.info(f"检查前缀：{prefix}")
            if message.startswith(prefix):
                args = message[len(prefix):].strip()
                has_prefix = True
                # logger.info(f"找到匹配的前缀：{prefix}，剩余参数：{args}")
                break
        
        if not has_prefix:
            logger.warning(f"未找到匹配的命令前缀：{message}")
            return "❌ 格式错误，请在消息前添加命令前缀：\"si 添加回复\"", "", ""
            
        # 检查是否包含冒号分隔符
        if ":" not in args:
            logger.warning(f"参数中未找到冒号分隔符：{args}")
            return "❌ 格式错误，正确格式：si 添加回复 关键字:回复内容", "", ""
            
        parts = args.split(":", 1)
        if len(parts) != 2:
            logger.warning(f"参数分割后长度不正确：{parts}")
            return "❌ 格式错误，正确格式：si 添加回复 关键字:回复内容", "", ""
            
        keyword = parts[0].strip()
        reply = parts[1].strip()
        
        if not keyword:
            logger.warning("关键字为空")
            return "❌ 关键字不能为空", "", ""
        if not reply:
            logger.warning("回复内容为空")
            return "❌ 回复内容不能为空", "", ""
            
        # logger.info(f"成功解析命令：关键字={keyword}, 回复={reply}")
        return None, keyword, reply

    def add_keyword_reply(self, message: str) -> str:
        """添加关键词回复
        
        Args:
            message: 完整的命令消息
            
        Returns:
            str: 操作结果消息
        """
        if not self.enable:
            return "关键词回复功能已关闭"
            
        error, keyword, reply = self.parse_add_command(message)
        if error:
            return error
            
        if not keyword:
            return "❌ 关键字不能为空"
            
        self.keyword_map[keyword.lower()] = reply
        self._save_keyword_config(self.keyword_map)
        return f"✅ 已添加关键词回复： [{keyword}] -> {reply}"

    def list_keyword_replies(self) -> str:
        """列出所有关键词回复
        
        Returns:
            str: 格式化的关键词回复列表
        """
        if not self.enable:
            return "关键词回复功能已关闭"
            
        if not self.keyword_map:
            return "暂无自定义回复"
        msg = "当前关键词回复列表：\n" + "\n".join(
            [f"{i+1}. [{k}] -> {v}" for i, (k, v) in enumerate(self.keyword_map.items())]
        )
        return msg

    def delete_keyword_reply(self, keyword: str) -> str:
        """删除关键词回复
        
        Args:
            keyword: 要删除的关键词
            
        Returns:
            str: 操作结果消息
        """
        if not self.enable:
            return "关键词回复功能已关闭"
            
        keyword = keyword.strip().lower()
        if keyword not in self.keyword_map:
            return f"❌ 未找到关键词：{keyword}"
        del self.keyword_map[keyword]
        self._save_keyword_config(self.keyword_map)
        return f"✅ 已删除关键词：{keyword}"

    def get_reply(self, msg: str) -> str:
        """获取关键词对应的回复
        
        Args:
            msg: 消息内容
            
        Returns:
            str: 对应的回复，如果没有匹配则返回None
        """
        if not self.enable or not msg:
            return None
            
        # 去除前后空格并转小写
        msg = msg.strip().lower()
        if not msg:
            return None
            
        # 精确匹配
        if msg in self.keyword_map:
            logger.info(f"关键词回复命中：{msg} -> {self.keyword_map[msg]}")
            return self.keyword_map[msg]
            
        return None 