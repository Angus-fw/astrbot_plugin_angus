from astrbot.api.event import AstrMessageEvent, MessageEventResult
from astrbot.api.star import Context, Star, register
from astrbot.api.message_components import *
from astrbot.api.event.filter import command, command_group, EventMessageType, PermissionType
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
from .utils import load_reminder_data, parse_datetime, save_reminder_data, is_outdated
from .scheduler import ReminderScheduler
from .tools import ReminderTools
import httpx
import psutil
import time
from .status_tools import ServerStatusTools
from .setu_tools import SetuTools
from .keyword_reply import KeywordReplyManager
from .active_conversation import ActiveConversation
from .reminder_system import ReminderSystem

@register("astrbot_plugin_angus", "angus", "这是一个为 AstrBot 开发的综合功能插件合集,集成了多个实用功能,包括智能提醒、主动对话、涩图功能和服务器状态监控等", "1.1.1")
class Main(Star):
    @classmethod
    def info(cls):
        return {
            "name": "astrbot_plugin_angus",
            "version": "1.1.1",
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
        
        # 初始化调度器
        self.scheduler_manager = ReminderScheduler(context, {}, "", self.unique_session)
        
        # 初始化工具
        self.tools = ReminderTools(self)
        
        # 记录配置信息
        logger.info(f"智能提醒插件启动成功，会话隔离：{'启用' if self.unique_session else '禁用'}")

        # 在插件初始化时根据配置决定是否启动主动对话功能
        if self.config.get("enable_active_conversation", False):
            self.active_conversation = ActiveConversation(context)
        else:
            self.active_conversation = None

        self.cd = 10  # 默认冷却时间为 10 秒
        self.last_usage = {} # 存储每个用户上次使用指令的时间
        self.semaphore = asyncio.Semaphore(10)  # 限制并发请求数量为 10

        # 初始化关键词回复管理器
        self.keyword_manager = KeywordReplyManager(os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "data"), self.config)

        self.status_tools = ServerStatusTools(enable_server_status=getattr(self, 'enable_server_status', True))

        self.setu_tools = SetuTools(enable_setu=self.enable_setu, cd=10)

        # 初始化提醒系统
        self.reminder_system = ReminderSystem(context, self.config, self.scheduler_manager, self.tools)

    @command("添加自定义回复")
    async def add_reply(self, event: AstrMessageEvent):
        '''添加自定义回复'''
        # 如需权限判断，请在此处手动判断 event 权限
        full_message = event.get_message_str()
        result = self.keyword_manager.add_keyword_reply(full_message)
        yield event.plain_result(result)

    @command("查看自定义回复")
    async def list_replies(self, event: AstrMessageEvent):
        '''查看自定义回复'''
        result = self.keyword_manager.list_keyword_replies()
        yield event.plain_result(result)

    @command("删除自定义回复")
    async def delete_reply(self, event: AstrMessageEvent, keyword: str):
        '''删除自定义回复'''
        # 如需权限判断，请在此处手动判断 event 权限
        result = self.keyword_manager.delete_keyword_reply(keyword)
        yield event.plain_result(result)

    @command("列出对话概率")
    async def list_prob_command(self, event: AstrMessageEvent):
        """列出当前主动对话概率"""
        if not self.active_conversation:
            yield event.plain_result("主动对话功能未启用")
            return
        result = self.active_conversation.get_probability_info()
        yield event.plain_result(result)

    @command("列出语句")
    async def list_trigger_command(self, event: AstrMessageEvent):
        """列出当前触发语句"""
        if not self.active_conversation:
            yield event.plain_result("主动对话功能未启用")
            return
        result = self.active_conversation.list_triggers()
        yield event.plain_result(result)

    @command("添加语句")
    async def add_trigger_command(self, event: AstrMessageEvent, trigger: str):
        """添加触发语句"""
        if not self.active_conversation:
            yield event.plain_result("主动对话功能未启用")
            return
        result = self.active_conversation.add_trigger(trigger)
        yield event.plain_result(result)

    @command("删除语句")
    async def del_trigger_command(self, event: AstrMessageEvent, index: int):
        """删除触发语句"""
        if not self.active_conversation:
            yield event.plain_result("主动对话功能未启用")
            return
        result = self.active_conversation.delete_trigger(index)
        yield event.plain_result(result)

    @command("设置概率")
    async def set_prob_command(self, event: AstrMessageEvent, prob: float):
        """设置主动对话概率"""
        if not self.active_conversation:
            yield event.plain_result("主动对话功能未启用")
            return
        result = self.active_conversation.set_probability(prob)
        yield event.plain_result(result)

    @command("设置对话平台")
    async def set_platform_command(self, event: AstrMessageEvent, platform: str):
        """设置使用的平台"""
        if not self.active_conversation:
            yield event.plain_result("主动对话功能未启用")
            return
        result = self.active_conversation.set_platform(platform)
        yield event.plain_result(result)

    @command("列出平台")
    async def list_platform_command(self, event: AstrMessageEvent):
        """列出当前平台设置"""
        if not self.active_conversation:
            yield event.plain_result("主动对话功能未启用")
            return
        result = self.active_conversation.get_platform_info()
        yield event.plain_result(result)

    @command("添加白名单")
    async def add_target_command(self, event: AstrMessageEvent, target_id: str):
        """添加目标用户ID"""
        if not self.active_conversation:
            yield event.plain_result("主动对话功能未启用")
            return
        result = self.active_conversation.add_target(target_id)
        yield event.plain_result(result)

    @command("删除白名单")
    async def del_target_command(self, event: AstrMessageEvent, target_id: str):
        """删除目标用户ID"""
        if not self.active_conversation:
            yield event.plain_result("主动对话功能未启用")
            return
        result = self.active_conversation.delete_target(target_id)
        yield event.plain_result(result)

    @command("列出白名单")
    async def list_target_command(self, event: AstrMessageEvent):
        """列出当前目标用户ID列表"""
        if not self.active_conversation:
            yield event.plain_result("主动对话功能未启用")
            return
        result = self.active_conversation.list_targets()
        yield event.plain_result(result)

    @command("设置提醒")
    async def set_reminder(self, event, text: str, datetime_str: str, user_name: str = "用户", repeat: str = None, holiday_type: str = None):
        '''设置一个提醒，到时间后会提醒用户'''
        return await self.tools.set_reminder(event, text, datetime_str, user_name, repeat, holiday_type)

    @command("设置任务")
    async def set_task(self, event, text: str, datetime_str: str, repeat: str = None, holiday_type: str = None):
        '''设置一个任务，到时间后会让AI执行该任务'''
        return await self.tools.set_task(event, text, datetime_str, repeat, holiday_type)

    @command("删除提醒")
    async def delete_reminder(self, event, 
                            content: str = None,           # 提醒内容关键词
                            time: str = None,              # 具体时间点 HH:MM
                            weekday: str = None,           # 星期 mon,tue,wed,thu,fri,sat,sun
                            repeat_type: str = None,       # 重复类型 daily,weekly,monthly,yearly
                            date: str = None,              # 具体日期 YYYY-MM-DD
                            all: str = None,               # 是否删除所有 "yes"/"no"
                            task_only: str = "no"          # 是否只删除任务 "yes"/"no"
                            ):
        '''删除符合条件的提醒'''
        return await self.tools.delete_reminder(event, content, time, weekday, repeat_type, date, all, task_only, "no")

    @command("删除任务")
    async def delete_task(self, event, 
                        content: str = None,           # 任务内容关键词
                        time: str = None,              # 具体时间点 HH:MM
                        weekday: str = None,           # 星期 mon,tue,wed,thu,fri,sat,sun
                        repeat_type: str = None,       # 重复类型 daily,weekly,monthly,yearly
                        date: str = None,              # 具体日期 YYYY-MM-DD
                        all: str = None                # 是否删除所有 "yes"/"no"
                        ):
        '''删除符合条件的任务'''
        return await self.tools.delete_reminder(event, content, time, weekday, repeat_type, date, all, "yes", "no")
        
    @command("列表全部")
    async def list_reminders(self, event: AstrMessageEvent):
        '''列出所有提醒和任务'''
        result = await self.reminder_system.list_reminders(event)
        yield event.plain_result(result)

    @command("删除全部")
    async def remove_reminder(self, event: AstrMessageEvent, index: int):
        '''删除提醒或任务'''
        result = await self.reminder_system.remove_reminder(event, index)
        yield event.plain_result(result)

    @command("添加提醒")
    async def add_reminder(self, event: AstrMessageEvent, text: str, time_str: str, week: str = None, repeat: str = None, holiday_type: str = None):
        '''手动添加提醒'''
        result = await self.reminder_system.add_reminder(event, text, time_str, week, repeat, holiday_type, False)
        yield event.plain_result(result)

    @command("添加任务")
    async def add_task(self, event: AstrMessageEvent, text: str, time_str: str, week: str = None, repeat: str = None, holiday_type: str = None):
        '''手动添加任务'''
        result = await self.reminder_system.add_reminder(event, text, time_str, week, repeat, holiday_type, True)
        yield event.plain_result(result)

    @command("帮助")
    async def show_help(self, event: AstrMessageEvent):
        '''显示帮助信息'''
        help_text = self.reminder_system.get_help_text()
        yield event.plain_result(help_text)

    @command("涩涩")
    async def setu(self, event: AstrMessageEvent):
        '''获取涩图'''
        result = await self.setu_tools.get_setu(event)
        if hasattr(result, '__aiter__'):
            async for r in result:
                yield r
        else:
            yield result

    @command("成人")
    async def taisele(self, event: AstrMessageEvent):
        '''获取成人图片'''
        result = await self.setu_tools.get_taisele(event)
        if hasattr(result, '__aiter__'):
            async for r in result:
                yield r
        else:
            yield result

    @command("设置涩图冷却")
    async def set_setu_cd(self, event: AstrMessageEvent, cd: int):
        '''设置涩图冷却'''
        if not self.enable_setu:
            yield event.plain_result("涩图功能已关闭")
            return
        msg = self.setu_tools.set_cd(cd)
        yield event.plain_result(msg)

    @command("zt")
    async def get_zt(self, event: AstrMessageEvent):
        """获取服务器状态---精简版"""
        result = await self.status_tools.get_zt()
        yield event.plain_result(result)

    @command("状态")
    async def get_status(self, event: AstrMessageEvent):
        """获取服务器状态"""
        result = await self.status_tools.get_status()
        yield event.plain_result(result) 