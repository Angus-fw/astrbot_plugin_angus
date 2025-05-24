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
        os.makedirs(os.path.join(data_dir, "reminders"), exist_ok=True)
        self.data_file = os.path.join(data_dir, "reminders", "reminder_data.json")
        
        # 初始化数据存储
        self.reminder_data = load_reminder_data(self.data_file)

    async def list_reminders(self, event: AstrMessageEvent):
        '''列出所有提醒和任务'''
        creator_id = event.get_sender_id()
        raw_msg_origin = event.unified_msg_origin
        msg_origin = self.tools.get_session_id(raw_msg_origin, creator_id) if self.unique_session else raw_msg_origin
            
        reminders = self.reminder_data.get(msg_origin, [])
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
                
                prompt += "\n\n同时告诉用户可以使用/删除全部 <序号>删除提醒或任务，或者直接命令你来删除。直接发出对话内容，就是你说的话，不要有其他的背景描述。"
                
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

    def _format_reminder_list(self, reminders):
        reminder_str = "当前的提醒和任务：\n"
        
        reminders_list = [r for r in reminders if not r.get("is_task", False)]
        tasks_list = [r for r in reminders if r.get("is_task", False)]
        
        if reminders_list:
            reminder_str += "\n提醒：\n"
            for i, reminder in enumerate(reminders_list):
                reminder_str += f"{i+1}. {reminder['text']} - {reminder['datetime']}\n"
        
        if tasks_list:
            reminder_str += "\n任务：\n"
            for i, task in enumerate(tasks_list):
                reminder_str += f"{len(reminders_list)+i+1}. {task['text']} - {task['datetime']}\n"
        
        reminder_str += "\n使用 /si rm <序号> 删除提醒或任务"
        return reminder_str

    async def remove_reminder(self, event: AstrMessageEvent, index: int):
        '''删除提醒或任务'''
        creator_id = event.get_sender_id()
        raw_msg_origin = event.unified_msg_origin
        msg_origin = self.tools.get_session_id(raw_msg_origin, creator_id) if self.unique_session else raw_msg_origin
            
        reminders = self.reminder_data.get(msg_origin, [])
        if not reminders:
            return "没有设置任何提醒或任务。"
            
        if index < 1 or index > len(reminders):
            return "序号无效。"
            
        job_id = f"reminder_{msg_origin}_{index-1}"
        
        try:
            self.scheduler_manager.remove_job(job_id)
            logger.info(f"Successfully removed job: {job_id}")
        except JobLookupError:
            logger.error(f"Job not found: {job_id}")
            
        removed = reminders.pop(index - 1)
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

    async def add_reminder(self, event: AstrMessageEvent, text: str, time_str: str, week: str = None, repeat: str = None, holiday_type: str = None, is_task: bool = False):
        '''添加提醒或任务'''
        try:
            item_type = "任务" if is_task else "提醒"
            
            # 获取用户ID和昵称的安全方法
            creator_id = None
            creator_name = "用户"
            
            # 尝试多种方式获取用户ID
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
            
            # 获取会话ID
            raw_msg_origin = event.unified_msg_origin
            msg_origin = self.tools.get_session_id(raw_msg_origin, creator_id) if self.unique_session else raw_msg_origin
            
            # 初始化该消息来源的提醒列表（如果不存在）
            if msg_origin not in self.reminder_data:
                self.reminder_data[msg_origin] = []
            
            datetime_str = parse_datetime(time_str)
            week_map = {
                '0': 0, '1': 1, '2': 2, '3': 3, 
                '4': 4, '5': 5, '6': 6
            }
            
            if week and week.lower() not in week_map:
                if week.lower() in ["daily", "weekly", "monthly", "yearly"] or week.lower() in ["workday", "holiday"]:
                    if repeat:
                        holiday_type = repeat
                        repeat = week
                    else:
                        repeat = week
                    week = None
                    logger.info(f"已将'{week}'识别为重复类型，默认使用今天作为开始日期")
                else:
                    return "星期格式错误，可选值：mon,tue,wed,thu,fri,sat,sun"

            if repeat:
                parts = repeat.split()
                if len(parts) == 2 and parts[1] in ["workday", "holiday"]:
                    repeat = parts[0]
                    holiday_type = parts[1]

            repeat_types = ["daily", "weekly", "monthly", "yearly"]
            if repeat and repeat.lower() not in repeat_types:
                return "重复类型错误，可选值：daily,weekly,monthly,yearly"
                
            holiday_types = ["workday", "holiday"]
            if holiday_type and holiday_type.lower() not in holiday_types:
                return "节假日类型错误，可选值：workday(仅工作日执行)，holiday(仅法定节假日执行)"

            dt = datetime.strptime(datetime_str, "%Y-%m-%d %H:%M")
            
            if week:
                target_weekday = week_map[week.lower()]
                current_weekday = dt.weekday()
                days_ahead = target_weekday - current_weekday
                if days_ahead <= 0:
                    days_ahead += 7
                dt += timedelta(days=days_ahead)
            
            final_repeat = repeat.lower() if repeat else "none"
            if repeat and holiday_type:
                final_repeat = f"{repeat.lower()}_{holiday_type.lower()}"
            
            item = {
                "text": text,
                "datetime": dt.strftime("%Y-%m-%d %H:%M"),
                "user_name": "用户" if is_task else creator_id,
                "repeat": final_repeat,
                "creator_id": creator_id,
                "creator_name": creator_name,
                "is_task": is_task
            }
            
            self.reminder_data[msg_origin].append(item)
            self.scheduler_manager.add_job(msg_origin, item, dt)
            await save_reminder_data(self.data_file, self.reminder_data)
            
            week_names = ['周一', '周二', '周三', '周四', '周五', '周六', '周日']
            start_str = f"从{week_names[dt.weekday()]}开始，" if week else ""
            
            repeat_str = self._get_repeat_str(repeat, holiday_type)
            
            return f"已设置{item_type}:\n内容: {text}\n时间: {dt.strftime('%Y-%m-%d %H:%M')}\n{start_str}{repeat_str}\n\n使用 //列表全部 查看所有提醒和任务"
            
        except Exception as e:
            return f"设置{item_type}时出错：{str(e)}"

    def _get_repeat_str(self, repeat, holiday_type):
        if not repeat:
            return "一次性"
            
        base_str = {
            "daily": "每天",
            "weekly": "每周",
            "monthly": "每月",
            "yearly": "每年"
        }.get(repeat, "")
        
        if not holiday_type:
            return f"{base_str}重复"
            
        holiday_str = {
            "workday": "但仅工作日触发",
            "holiday": "但仅法定节假日触发"
        }.get(holiday_type, "")
        
        return f"{base_str}重复，{holiday_str}"

    def get_help_text(self):
        '''获取帮助信息'''
        return """提醒与任务功能指令说明：

【提醒】：到时间后会提醒你做某事
【任务】：到时间后AI会自动执行指定的操作

1. 添加提醒：
   提醒 <内容> <时间> [开始星期] [重复类型] [--holiday_type=...]
   例如：

   - 添加提醒 吃饭 8:05 0 daily (从周日开始每天)
   - 添加提醒 开会 8:05 1 weekly (每周一)
   - 添加提醒 交房租 8:05 fr5i monthly (从周五开始每月)
   - 添加提醒 上班打卡 8:30 daily workday (每个工作日，法定节假日不触发)
   - 添加提醒 休息提醒 9:00 daily holiday (每个法定节假日触发)

2. 添加任务：
   任务 <内容> <时间> [开始星期] [重复类型] [--holiday_type=...]
   例如：
   - 添加任务 发送天气预报 8:00
   - 添加任务 汇总今日新闻 18:00 daily
   - 添加任务 推送工作安排 9:00 1 0 workday (每周一工作日推送)

3. 查看提醒和任务：
   列出全部 - 列出所有提醒和任务

4. 删除提醒或任务：
   删除全部 <序号> - 删除指定提醒或任务

5. 星期可选值：
   - 1: 周一
   - 2: 周二
   - 3: 周三
   - 4: 周四
   - 5: 周五
   - 6: 周六
   - 0: 周日

6. 重复类型：
   - daily: 每天重复
   - weekly: 每周重复
   - monthly: 每月重复
   - yearly: 每年重复

7. 节假日类型：
   - workday: 仅工作日触发（法定节假日不触发）
   - holiday: 仅法定节假日触发

8. AI智能提醒与任务
   正常对话即可，AI会自己设置提醒或任务，但需要AI支持LLM

9. 会话隔离功能
   {session_isolation_status}
   - 关闭状态：群聊中所有成员共享同一组提醒和任务
   - 开启状态：群聊中每个成员都有自己独立的提醒和任务

注：时间格式为 HH:MM 或 HHMM，如 8:05 或 0805
法定节假日数据来源：http://timor.tech/api/holiday""".format(
            session_isolation_status="当前已开启会话隔离" if self.unique_session else "当前未开启会话隔离"
        ) 