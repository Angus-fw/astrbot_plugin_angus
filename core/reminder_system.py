from datetime import datetime, timedelta
import os
import json
from typing import Union
from apscheduler.schedulers.base import JobLookupError
from astrbot.api import logger
from astrbot.api.event import MessageChain, AstrMessageEvent
from astrbot.core.message.message_event_result import MessageChain
from .utils import load_reminder_data, parse_datetime, save_reminder_data, is_outdated
from astrbot.api.star import StarTools
from .tools import ReminderTools

class ReminderSystem:
    def __init__(self, context, config, scheduler_manager, tools, data_dir=None):
        self.context = context
        self.config = config
        self.scheduler_manager = scheduler_manager
        self.tools = tools
        self.unique_session = config.get("unique_session", False)
        
        # 使用StarTools获取数据目录
        if data_dir is None:
            data_dir = StarTools.get_data_dir("astrbot_plugin_angus")
        self.data_file = os.path.join(data_dir, "reminder_data.json")
        
        # 初始化数据存储
        self.reminder_data = load_reminder_data(self.data_file)
        
        # 确保 tools 属性被正确初始化
        if not hasattr(self.tools, 'get_session_id'):
            self.tools = ReminderTools(self)

    async def list_reminders(self, event: AstrMessageEvent, week: str = None):
        '''列出所有提醒和任务'''
        try:
            # 获取用户ID
            creator_id = None
            if hasattr(event, 'get_user_id'):
                creator_id = event.get_user_id()
            elif hasattr(event, 'get_sender_id'):
                creator_id = event.get_sender_id()
            elif hasattr(event, 'sender') and hasattr(event.sender, 'user_id'):
                creator_id = event.sender.user_id
            elif hasattr(event.message_obj, 'sender'):
                creator_id = getattr(event.message_obj.sender, 'user_id', None)
            
            raw_msg_origin = week if week else event.unified_msg_origin
            
            # 使用 tools.get_session_id 获取正确的会话ID
            msg_origin = self.tools.get_session_id(raw_msg_origin, creator_id)
            
            # 重新加载提醒数据
            self.reminder_data = load_reminder_data(self.data_file)
            
            # 获取所有相关的提醒
            reminders = []
            for key in self.reminder_data:
                # 检查是否是当前用户的所有提醒
                if key.endswith(f"_{creator_id}") or key == msg_origin:
                    reminders.extend(self.reminder_data[key])
            
            if not reminders:
                return "当前没有设置任何提醒或任务。"
            
            provider = self.context.get_using_provider()
            if provider:
                try:
                    reminder_items = []
                    task_items = []
                    
                    for r in reminders:
                        if r.get("is_task", False):
                            task_items.append(f"- {r['text']} (时间: {r['datetime']})")
                        else:
                            reminder_items.append(f"- {r['text']} (时间: {r['datetime']})")
                    
                    prompt = "请帮我整理并展示以下提醒和任务列表，用自然的语言表达：\n"
                    
                    if reminder_items:
                        prompt += f"\n提醒列表：\n" + "\n".join(reminder_items)
                    
                    if task_items:
                        prompt += f"\n\n任务列表：\n" + "\n".join(task_items)
                    
                    prompt += "\n\n同时告诉用户可以使用 /si 删除 <序号> 删除提醒或任务，或者直接命令你来删除。直接发出对话内容，就是你说的话，不要有其他的背景描述。"
                    
                    response = await provider.text_chat(
                        prompt=prompt,
                        session_id=event.session_id,
                        contexts=[]
                    )
                    return response.completion_text
                except Exception as e:
                    logger.error(f"在list_reminders中调用LLM时出错: {str(e)}")
                    return self._format_reminder_list(reminders)
            else:
                return self._format_reminder_list(reminders)
        except Exception as e:
            logger.error(f"列出提醒时出错: {str(e)}")
            return f"列出提醒时出错：{str(e)}"

    def _format_reminder_list(self, reminders):
        if not reminders:
            return "当前没有设置任何提醒或任务。"
            
        reminder_str = "当前的提醒和任务：\n"
        
        reminders_list = [r for r in reminders if not r.get("is_task", False)]
        tasks_list = [r for r in reminders if r.get("is_task", False)]
        
        if reminders_list:
            reminder_str += "\n提醒：\n"
            for i, reminder in enumerate(reminders_list, 1):
                repeat_str = ""
                if reminder.get("repeat") == "weekly_workday":
                    repeat_str = " (每周工作日)"
                elif reminder.get("repeat") == "每周":
                    repeat_str = " (每周)"
                elif reminder.get("repeat") == "每天":
                    repeat_str = " (每天)"
                elif reminder.get("repeat") == "每月":
                    repeat_str = " (每月)"
                elif reminder.get("repeat") == "每年":
                    repeat_str = " (每年)"
                reminder_str += f"{i}. {reminder['text']} - {reminder['datetime']}{repeat_str}\n"
        
        if tasks_list:
            reminder_str += "\n任务：\n"
            for i, task in enumerate(tasks_list, 1):
                repeat_str = ""
                if task.get("repeat") == "weekly_workday":
                    repeat_str = " (每周工作日)"
                elif task.get("repeat") == "每周":
                    repeat_str = " (每周)"
                elif task.get("repeat") == "每天":
                    repeat_str = " (每天)"
                elif task.get("repeat") == "每月":
                    repeat_str = " (每月)"
                elif task.get("repeat") == "每年":
                    repeat_str = " (每年)"
                reminder_str += f"{len(reminders_list)+i}. {task['text']} - {task['datetime']}{repeat_str}\n"
        
        reminder_str += "\n使用 /si 删除 <序号> 删除提醒或任务"
        return reminder_str

    async def remove_reminder(self, event: AstrMessageEvent, index: int, week: str = None):
        '''删除提醒或任务'''
        try:
            # 获取用户ID
            creator_id = None
            if hasattr(event, 'get_user_id'):
                creator_id = event.get_user_id()
            elif hasattr(event, 'get_sender_id'):
                creator_id = event.get_sender_id()
            elif hasattr(event, 'sender') and hasattr(event.sender, 'user_id'):
                creator_id = event.sender.user_id
            elif hasattr(event.message_obj, 'sender'):
                creator_id = getattr(event.message_obj.sender, 'user_id', None)
            
            raw_msg_origin = week if week else event.unified_msg_origin
            
            # 使用 tools.get_session_id 获取正确的会话ID
            msg_origin = self.tools.get_session_id(raw_msg_origin, creator_id)
            
            # 重新加载提醒数据
            self.reminder_data = load_reminder_data(self.data_file)
            
            # 获取所有相关的提醒
            reminders = []
            for key in self.reminder_data:
                if key.endswith(f"_{creator_id}") or key == msg_origin:
                    reminders.extend(self.reminder_data[key])
            
            if not reminders:
                return "没有设置任何提醒或任务。"
                
            if index < 1 or index > len(reminders):
                return "序号无效。"
            
            # 找到要删除的提醒
            removed = reminders[index - 1]
            
            # 从原始数据中删除
            for key in self.reminder_data:
                if key.endswith(f"_{creator_id}") or key == msg_origin:
                    for i, reminder in enumerate(self.reminder_data[key]):
                        if (reminder['text'] == removed['text'] and 
                            reminder['datetime'] == removed['datetime']):
                            self.reminder_data[key].pop(i)
                            break
            
            # 删除定时任务
            job_id = f"reminder_{msg_origin}_{index-1}"
            try:
                self.scheduler_manager.remove_job(job_id)
                logger.info(f"Successfully removed job: {job_id}")
            except JobLookupError:
                logger.error(f"Job not found: {job_id}")
            
            # 保存更新后的数据
            await save_reminder_data(self.data_file, self.reminder_data)
            
            is_task = removed.get("is_task", False)
            item_type = "任务" if is_task else "提醒"
            
            provider = self.context.get_using_provider()
            if provider:
                prompt = f"用户删除了一个{item_type}，内容是'{removed['text']}'。请用自然的语言确认删除操作。直接发出对话内容，就是你说的话，不要有其他的背景描述。"
                response = await provider.text_chat(
                    prompt=prompt,
                    session_id=event.session_id,
                    contexts=[]
                )
                return response.completion_text
            else:
                return f"已删除{item_type}：{removed['text']}"
                
        except Exception as e:
            logger.error(f"删除提醒时出错: {str(e)}")
            return f"删除提醒时出错：{str(e)}"

    async def add_reminder(self, event: AstrMessageEvent, text: str, time_str: str, week: str = None, repeat: str = None, holiday_type: str = None, is_task: bool = False):
        '''添加提醒或任务'''
        try:
            # 获取用户ID
            creator_id = None
            creator_name = "用户"
            
            # 尝试多种方式获取用户ID和昵称
            if hasattr(event, 'get_user_id'):
                creator_id = event.get_user_id()
            elif hasattr(event, 'get_sender_id'):
                creator_id = event.get_sender_id()
            elif hasattr(event, 'sender') and hasattr(event.sender, 'user_id'):
                creator_id = event.sender.user_id
            elif hasattr(event.message_obj, 'sender'):
                creator_id = getattr(event.message_obj.sender, 'user_id', None)
            
            # 尝试多种方式获取用户昵称
            if hasattr(event, 'get_sender'):
                sender = event.get_sender()
                if isinstance(sender, dict):
                    creator_name = sender.get("nickname", creator_name)
                elif hasattr(sender, 'nickname'):
                    creator_name = sender.nickname or creator_name
            elif hasattr(event.message_obj, 'sender'):
                sender = event.message_obj.sender
                if isinstance(sender, dict):
                    creator_name = sender.get("nickname", creator_name)
                elif hasattr(sender, 'nickname'):
                    creator_name = sender.nickname or creator_name
            
            # 使用 tools.get_session_id 获取正确的会话ID
            msg_origin = self.tools.get_session_id(event.unified_msg_origin, creator_id)
            item_type = "任务" if is_task else "提醒"
            
            # 如果提供了重复类型但没有提供星期，自动处理
            week_days = ['周日', '周一', '周二', '周三', '周四', '周五', '周六']
            if week and week not in week_days and not repeat:
                if week in ["每天", "每周", "每月", "每年"]:
                    repeat = week
                    week = None  # 将 week 重置，因为它不是有效的星期

            # 解析时间
            try:
                dt_str = parse_datetime(time_str, week)
            except ValueError as e:
                return str(e)  # 返回具体的错误信息
            
            # 处理重复类型
            repeat_str, _ = self._get_repeat_str(repeat, holiday_type, week)
            
            # 构建提醒数据
            reminder = {
                "text": text,
                "datetime": dt_str,
                "user_name": creator_name,
                "repeat": repeat_str,
                "creator_id": creator_id,
                "creator_name": creator_name,
                "is_task": is_task
            }
            
            # 如果指定了节假日类型，添加到重复类型中
            if holiday_type:
                reminder["repeat"] = f"{repeat_str}_{holiday_type}"
            
            # 添加到提醒数据中
            if msg_origin not in self.reminder_data:
                self.reminder_data[msg_origin] = []
            self.reminder_data[msg_origin].append(reminder)
            
            # 保存数据
            await save_reminder_data(self.data_file, self.reminder_data)
            
            # 添加定时任务
            dt = datetime.strptime(dt_str, "%Y-%m-%d %H:%M")
            if not self.scheduler_manager.add_job(msg_origin, reminder, dt):
                return "添加定时任务失败"
            
            # 使用AI生成回复
            provider = self.context.get_using_provider()
            if provider:
                try:
                    prompt = f'用户设置了一个{"任务" if is_task else "提醒"}，内容为"{text}"，时间为{dt_str}，{repeat_str}。请用自然的语言回复用户，确认设置成功。'
                    response = await provider.text_chat(
                        prompt=prompt,
                        session_id=event.session_id,
                        contexts=[]
                    )
                    return response.completion_text
                except Exception as e:
                    logger.error(f"在add_reminder中调用LLM时出错: {str(e)}")
                    return f'好的，您的"{text}"已设置成功，时间为{dt_str}，{repeat_str}。'
            else:
                return f'好的，您的"{text}"已设置成功，时间为{dt_str}，{repeat_str}。'
                
        except Exception as e:
            logger.error(f"添加提醒时出错: {str(e)}")
            return f"添加提醒时出错：{str(e)}"

    def _get_repeat_str(self, repeat, holiday_type, week):
        if not repeat:
            return "一次性", ""
            
        base_str = {
            "每天": "每天",
            "每周": "每周",
            "每月": "每月",
            "每年": "每年"
        }.get(repeat, "一次性")
        
        if not week:
            return base_str, base_str
        
        if not holiday_type:
            return f"{base_str}重复，{week}", base_str
            
        holiday_str = {
            "workday": "仅工作日",
            "holiday": "仅节假日"
        }.get(holiday_type, "")
        
        return f"{base_str}重复，{holiday_str}，{week}", base_str

    def get_help_text(self):
        return "🌟 Angus 插件合集帮助：\n\n" + \
               "⏰ 智能提醒与任务系统：\n" + \
               "1. 添加提醒：/si 添加提醒 <内容> <时间> [开始星期/明天/后天] [重复类型] [--holiday_type=...]\n" + \
               "2. 添加任务：/si 添加任务 <内容> <时间> [开始星期/明天/后天] [重复类型] [--holiday_type=...]\n" + \
               "3. 查看全部：/si 列表\n" + \
               "4. 删除指定：/si 删除 <序号>\n\n" + \
               "🤖 主动对话系统：\n" + \
               "1. 设置概率：/si 设置概率 <概率值>\n" + \
               "2. 查看概率：/si 列出对话概率\n" + \
               "3. 查看语句：/si 列出语句\n" + \
               "4. 添加语句：/si 添加语句 <语句>\n" + \
               "5. 删除语句：/si 删除语句 <编号>\n" + \
               "6. 添加白名单：/si 添加白名单 <用户ID>\n" + \
               "7. 删除白名单：/si 删除白名单 <用户ID>\n" + \
               "8. 查看白名单：/si 列出白名单\n\n" + \
               "🔞 涩图功能：\n" + \
               "1. 随机涩图：/si setu\n" + \
               "2. R18涩图：/si taisele\n" + \
               "3. 设置冷却：/si 设置涩图冷却 <秒数>\n\n" + \
               "🖥️ 服务器状态：\n" + \
               "1. 精简状态：/si zt\n" + \
               "2. 详细状态：/si 状态\n\n" + \
               "📝 关键词回复：\n" + \
               "1. 添加回复：/si 添加回复 <关键字:内容>\n" + \
               "2. 查看回复：/si 查看回复\n" + \
               "3. 删除回复：/si 删除回复 <关键字>\n\n" + \
               "💡 使用说明：\n" + \
               "- 所有命令都以 /si 开头\n" + \
               "- 时间格式：HH:MM 或 YYYY-MM-DD HH:MM\n" + \
               "- 时间关键词：明天、后天\n" + \
               "- 重复类型：每天、每周、每月、每年\n" + \
               "- 节假日类型：workday(仅工作日)、holiday(仅节假日)\n" + \
               "- 更多帮助：/si help"

__all__ = ['ReminderSystem']
