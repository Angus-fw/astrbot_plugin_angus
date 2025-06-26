from astrbot.api.event import AstrMessageEvent, MessageEventResult
from astrbot.api.star import Context, Star, register, StarTools
from astrbot.api.message_components import *
from astrbot.api.event.filter import command, command_group, EventMessageType, PermissionType, event_message_type
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.schedulers.base import JobLookupError
from astrbot.api import logger, AstrBotConfig
from astrbot.api.event import MessageChain
import datetime
import json
import os
from typing import Union
import random
import asyncio
import json as _json
from datetime import datetime, timedelta
import astrbot.api.star as star
from astrbot.core.message.message_event_result import MessageChain
from astrbot.core.platform.astrbot_message import AstrBotMessage, MessageMember, MessageType
from astrbot.core.platform.platform_metadata import PlatformMetadata
from astrbot.core.provider.manager import Personality
from astrbot.core.message.components import Plain
from astrbot.core.star.star_handler import star_handlers_registry, EventType
from .core.utils import load_reminder_data, parse_datetime, save_reminder_data, is_outdated
from .core.scheduler import ReminderScheduler
from .core.tools import ReminderTools
import httpx
import psutil
import time
from .core.status_tools import ServerStatusTools
from .core.setu_tools import SetuTools
from .core.keyword_reply import KeywordReplyManager
from .core.active_conversation import ActiveConversation
from .core.reminder_system import ReminderSystem
from astrbot.api import llm_tool

@register("astrbot_plugin_angus", "angus", "这是一个为 AstrBot 开发的综合功能插件合集,集成了多个实用功能,包括智能提醒、主动对话、涩图功能和服务器状态监控等", "1.1.1")
class Main(Star):
    @classmethod
    def info(cls):
        return {
            "name": "astrbot_plugin_angus",
            "version": "1.1.4",
            "description": "这是一个为 AstrBot 开发的综合功能插件合集,集成了多个实用功能,包括智能提醒、主动对话、涩图功能和服务器状态监控等",
            "author": "angus"
        }

    def __init__(self, context: Context, config: AstrBotConfig = None):
        super().__init__(context)
        
        # 保存配置
        self.config = config or {}
        self.unique_session = self.config.get("unique_session", False)
        self.enable_setu = self.config.get("enable_setu", True)
        self.enable_server_status = self.config.get("enable_server_status", True)
        
        # 初始化数据文件路径
        data_dir = StarTools.get_data_dir("astrbot_plugin_angus")
        os.makedirs(data_dir, exist_ok=True)
        self.data_file = os.path.join(data_dir, "reminder_data.json")
        
        # 加载提醒数据
        self.reminder_data = load_reminder_data(self.data_file)  
        
        # 初始化调度器
        self.scheduler_manager = ReminderScheduler(context, self.reminder_data, self.data_file, self.unique_session)
        
        # 初始化工具
        self.tools = ReminderTools(self)
        
        # 记录配置信息
        logger.info(f"智能提醒插件启动成功，会话隔离：{'启用' if self.unique_session else '禁用'}")

        # 初始化关键词回复管理器
        self.keyword_manager = KeywordReplyManager(data_dir, self.config)

        self.status_tools = ServerStatusTools(enable_server_status=getattr(self, 'enable_server_status', True))

        self.setu_tools = SetuTools(enable_setu=self.enable_setu, cd=10)

        # 初始化提醒系统
        self.reminder_system = ReminderSystem(context, self.config, self.scheduler_manager, self.tools, data_dir)

        # 在插件初始化时根据配置决定是否启动主动对话功能
        if self.config.get("enable_active_conversation", False):
            self.active_conversation = ActiveConversation(context, data_dir)
        else:
            self.active_conversation = None

        self.cd = 10  # 默认冷却时间为 10 秒
        self.last_usage = {} # 存储每个用户上次使用指令的时间
        self.semaphore = asyncio.Semaphore(10)  # 限制并发请求数量为 10

    @event_message_type(EventMessageType.ALL)
    async def handle_message(self, event: AstrMessageEvent):
        """自定义回复"""
        # 只在被@或唤醒时响应
        if not getattr(event, "is_at_or_wake_command", False):
            return

        msg = event.get_message_str().strip().lower()
        # 只进行精确匹配
        if self.keyword_manager and self.keyword_manager.enable:
            reply = self.keyword_manager.get_reply(msg)
            if reply:
                yield event.plain_result(reply)
                return

    @command("si 添加回复")
    async def add_reply(self, event: AstrMessageEvent):
        '''添加自定义回复'''
        # 如需权限判断，请在此处手动判断 event 权限
        full_message = event.get_message_str()
        result = self.keyword_manager.add_keyword_reply(full_message)
        yield event.plain_result(result)

    @command("si 查看回复")
    async def list_replies(self, event: AstrMessageEvent):
        '''查看自定义回复'''
        result = self.keyword_manager.list_keyword_replies()
        yield event.plain_result(result)

    @command("si 删除回复")
    async def delete_reply(self, event: AstrMessageEvent, keyword: str):
        '''删除自定义回复'''
        # 如需权限判断，请在此处手动判断 event 权限
        result = self.keyword_manager.delete_keyword_reply(keyword)
        yield event.plain_result(result)

    @command("si 列出对话概率")
    async def list_prob_command(self, event: AstrMessageEvent):
        """列出当前主动对话概率"""
        if not self.active_conversation:
            yield event.plain_result("主动对话功能未启用")
            return
        result = self.active_conversation.get_probability_info()
        yield event.plain_result(result)

    @command("si 列出语句")
    async def list_trigger_command(self, event: AstrMessageEvent):
        """列出当前触发语句"""
        if not self.active_conversation:
            yield event.plain_result("主动对话功能未启用")
            return
        result = self.active_conversation.list_triggers()
        yield event.plain_result(result)

    @command("si 添加语句")
    async def add_trigger_command(self, event: AstrMessageEvent, trigger: str):
        """添加触发语句"""
        if not self.active_conversation:
            yield event.plain_result("主动对话功能未启用")
            return
        result = self.active_conversation.add_trigger(trigger)
        yield event.plain_result(result)

    @command("si 删除语句")
    async def del_trigger_command(self, event: AstrMessageEvent, index: int):
        """删除触发语句"""
        if not self.active_conversation:
            yield event.plain_result("主动对话功能未启用")
            return
        result = self.active_conversation.delete_trigger(index)
        yield event.plain_result(result)

    @command("si 设置概率")
    async def set_prob_command(self, event: AstrMessageEvent, prob: float):
        """设置主动对话概率"""
        if not self.active_conversation:
            yield event.plain_result("主动对话功能未启用")
            return
        result = self.active_conversation.set_probability(prob)
        yield event.plain_result(result)

    @command("si 添加白名单")
    async def add_target_command(self, event: AstrMessageEvent, target_id: str):
        """添加目标用户ID"""
        if not self.active_conversation:
            yield event.plain_result("主动对话功能未启用")
            return
        result = await self.active_conversation.add_target(target_id)
        yield event.plain_result(result)

    @command("si 删除白名单")
    async def del_target_command(self, event: AstrMessageEvent, target_id: str):
        """删除目标用户ID"""
        if not self.active_conversation:
            yield event.plain_result("主动对话功能未启用")
            return
        result = await self.active_conversation.delete_target(target_id)
        yield event.plain_result(result)

    @command("si 列出白名单")
    async def list_target_command(self, event: AstrMessageEvent):
        """列出当前目标用户ID列表"""
        if not self.active_conversation:
            yield event.plain_result("主动对话功能未启用")
            return
        result = self.active_conversation.list_targets()
        yield event.plain_result(result)

    @command("si 列表")
    async def list_reminders(self, event: AstrMessageEvent):
        '''列出所有提醒和任务'''
        try:
            result = await self.reminder_system.list_reminders(event)
            yield event.plain_result(result)
        except Exception as e:
            logger.error(f"列出提醒时出错: {str(e)}")
            yield event.plain_result(f"列出提醒时出错：{str(e)}")

    @command("si 删除")
    async def remove_reminder(self, event: AstrMessageEvent, index: int):
        '''删除提醒或任务'''
        result = await self.reminder_system.remove_reminder(event, index)
        yield event.plain_result(result)

    @command("si 添加提醒")
    async def add_reminder(self, event: AstrMessageEvent, text: str, time_str: str, week: str = None, repeat: str = None, holiday_type: str = None):
        '''手动添加提醒'''
        result = await self.reminder_system.add_reminder(event, text, time_str, week, repeat, holiday_type, False)
        yield event.plain_result(result)

    @command("si 添加任务")
    async def add_task(self, event: AstrMessageEvent, text: str, time_str: str, week: str = None, repeat: str = None, holiday_type: str = None):
        '''手动添加任务'''
        result = await self.reminder_system.add_reminder(event, text, time_str, week, repeat, holiday_type, True)
        yield event.plain_result(result)

    @command("si help")
    async def show_help(self, event: AstrMessageEvent):
        '''显示帮助信息'''
        help_text = self.reminder_system.get_help_text()
        yield event.plain_result(help_text)

    @command("si setu")
    async def setu(self, event: AstrMessageEvent):
        '''获取涩图'''
        result = await self.setu_tools.get_setu(event)
        if hasattr(result, '__aiter__'):
            async for r in result:
                yield r
        else:
            yield result

    @command("si taisele")
    async def taisele(self, event: AstrMessageEvent):
        '''获取R18图片'''
        result = await self.setu_tools.get_taisele(event)
        if hasattr(result, '__aiter__'):
            async for r in result:
                yield r
        else:
            yield result

    @command("si 设置涩图冷却")
    async def set_setu_cd(self, event: AstrMessageEvent, cd: int):
        '''设置涩图冷却'''
        if not self.enable_setu:
            yield event.plain_result("涩图功能已关闭")
            return
        msg = self.setu_tools.set_cd(cd)
        yield event.plain_result(msg)

    @command("si zt")
    async def get_zt(self, event: AstrMessageEvent):
        """获取服务器状态---精简版"""
        result = await self.status_tools.get_zt()
        yield event.plain_result(result)

    @command("si 状态")
    async def get_status(self, event: AstrMessageEvent):
        """获取服务器状态"""
        result = await self.status_tools.get_status()
        yield event.plain_result(result)

    @llm_tool(name="set_reminder")
    async def set_reminder(self, event, text: str, datetime_str: str, repeat: str = None, holiday_type: str = None):
        '''设置一个提醒
        
        Args:
            text(string): 提醒内容
            datetime_str(string): 提醒时间，格式为 %Y-%m-%d %H:%M
            repeat(string): 重复类型，可选值：每天，每周，每月，每年，不重复
            holiday_type(string): 可选，节假日类型：workday(仅工作日执行)，holiday(仅法定节假日执行)
        '''
        try:
            # 获取用户昵称
            user_name = event.message_obj.sender.nickname if hasattr(event.message_obj, 'sender') and hasattr(event.message_obj.sender, 'nickname') else "用户"
            
            # 调用工具类设置提醒
            result = await self.tools.set_reminder(event, text, datetime_str, user_name, repeat, holiday_type)
            logger.info(f"设置提醒结果: {result}")
            return result
            
        except Exception as e:
            logger.error(f"设置提醒时出错: {str(e)}")
            return f"设置提醒失败：{str(e)}"

    @llm_tool(name="set_task")
    async def set_task(self, event, text: str, datetime_str: str, repeat: str = None, holiday_type: str = None):
        '''设置一个任务，到时间后会让AI执行该任务
        
        Args:
            text(string): 任务内容，AI将执行的操作
            datetime_str(string): 任务执行时间，格式为 %Y-%m-%d %H:%M
            repeat(string): 重复类型，可选值：每天，每周，每月，每年，不重复
            holiday_type(string): 可选，节假日类型：workday(仅工作日执行)，holiday(仅法定节假日执行)
        '''
        try:
            # 确保任务内容包含必要的指令
            if not text.startswith("请调用llm函数"):
                text = f"请调用llm函数，{text}"
            
            # 调用工具类设置任务
            result = await self.tools.set_task(event, text, datetime_str, repeat, holiday_type)
            logger.info(f"设置任务结果: {result}")
            return result
            
        except Exception as e:
            logger.error(f"设置任务时出错: {str(e)}")
            return f"设置任务失败：{str(e)}"

    @llm_tool(name="delete_reminder")
    @llm_tool(name="delete_task")
    async def delete_reminder(self, event, 
                            content: str = None,           # 提醒内容关键词
                            time: str = None,              # 具体时间点 HH:MM
                            weekday: str = None,           # 星期 周日,周一,周二,周三,周四,周五,周六
                            repeat_type: str = None,       # 重复类型 每天,每周,每月,每年
                            date: str = None,              # 具体日期 YYYY-MM-DD
                            all: str = None,               # 是否删除所有 "yes"/"no"
                            task_only: str = "no"          # 是否只删除任务 "yes"/"no"
                            ):
        '''删除符合条件的提醒，可组合多个条件进行精确筛选
        
        Args:
            content(string): 可选，提醒内容包含的关键词
            time(string): 可选，具体时间点，格式为 HH:MM，如 "08:00"
            weekday(string): 可选，星期几，可选值：周日,周一,周二,周三,周四,周五,周六
            repeat_type(string): 可选，重复类型，可选值：每天,每周,每月,每年
            date(string): 可选，具体日期，格式为 YYYY-MM-DD，如 "2024-02-09"
            all(string): 可选，是否删除所有提醒，可选值：yes/no，默认no
            task_only(string): 可选，是否只删除任务，可选值：yes/no，默认no
        '''
        is_task_only = task_only and task_only.lower() == "yes"
        return await self.tools.delete_reminder(event, content, time, weekday, repeat_type, date, all, is_task_only, "no")

    @llm_tool(name="delete_task")
    async def delete_task(self, event, 
                        content: str = None,           # 任务内容关键词
                        time: str = None,              # 具体时间点 HH:MM
                        weekday: str = None,           # 星期 周日,周一,周二,周三,周四,周五,周六
                        repeat_type: str = None,       # 重复类型 每天,每周,每月,每年
                        date: str = None,              # 具体日期 YYYY-MM-DD
                        all: str = None                # 是否删除所有 "yes"/"no"
                        ):
        '''删除符合条件的任务，可组合多个条件进行精确筛选
        
        Args:
            content(string): 可选，任务内容包含的关键词
            time(string): 可选，具体时间点，格式为 HH:MM，如 "08:00"
            weekday(string): 可选，星期几，可选值：周日,周一,周二,周三,周四,周五,周六
            repeat_type(string): 可选，重复类型，可选值：每天,每周,每月,每年
            date(string): 可选，具体日期，格式为 YYYY-MM-DD，如 "2024-02-09"
            all(string): 可选，是否删除所有任务，可选值：yes/no，默认no
        '''
        return await self.tools.delete_reminder(event, content, time, weekday, repeat_type, date, all, "yes", "no")
