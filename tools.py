import datetime
from typing import Union
from astrbot.api.event import AstrMessageEvent
from astrbot.api.star import Context
from astrbot.api import logger
from .utils import parse_datetime, save_reminder_data
import re

class ReminderTools:
    def __init__(self, star_instance):
        self.star_instance = star_instance
        self.unique_session = star_instance.unique_session
    
    def get_session_id(self, raw_msg_origin: str, creator_id: str) -> str:
        """获取会话ID，用于会话隔离"""
        if not self.unique_session:
            return raw_msg_origin
        return f"{raw_msg_origin}_{creator_id}"
    
    async def set_reminder(self, event: AstrMessageEvent, text: str, datetime_str: str, user_name: str = "用户", repeat: str = None, holiday_type: str = None):
        """设置提醒"""
        try:
            # 将datetime_str转换为HH:MM格式
            dt = datetime.strptime(datetime_str, "%Y-%m-%d %H:%M")
            time_str = dt.strftime("%H:%M")
            
            # 调用ReminderSystem的add_reminder方法
            result = await self.star_instance.reminder_system.add_reminder(
                event=event,
                text=text,
                time_str=time_str,
                week=None,
                repeat=repeat,
                holiday_type=holiday_type,
                is_task=False
            )
            return result
        except Exception as e:
            logger.error(f"设置提醒时出错: {str(e)}")
            return f"设置提醒时出错：{str(e)}"
    
    async def set_task(self, event: AstrMessageEvent, text: str, datetime_str: str, repeat: str = None, holiday_type: str = None):
        """设置任务"""
        try:
            # 将datetime_str转换为HH:MM格式
            dt = datetime.strptime(datetime_str, "%Y-%m-%d %H:%M")
            time_str = dt.strftime("%H:%M")
            
            # 调用ReminderSystem的add_reminder方法
            result = await self.star_instance.reminder_system.add_reminder(
                event=event,
                text=text,
                time_str=time_str,
                week=None,
                repeat=repeat,
                holiday_type=holiday_type,
                is_task=True
            )
            return result
        except Exception as e:
            logger.error(f"设置任务时出错: {str(e)}")
            return f"设置任务时出错：{str(e)}"
    
    async def delete_reminder(self, event: AstrMessageEvent, 
                            content: str = None,           # 提醒内容关键词
                            time: str = None,              # 具体时间点 HH:MM
                            weekday: str = None,           # 星期 mon,tue,wed,thu,fri,sat,sun
                            repeat_type: str = None,       # 重复类型 daily,weekly,monthly,yearly
                            date: str = None,              # 具体日期 YYYY-MM-DD
                            all: str = None,               # 是否删除所有 "yes"/"no"
                            task_only: str = "no",         # 是否只删除任务 "yes"/"no"
                            reminder_only: str = "no"      # 是否只删除提醒 "yes"/"no"
                            ):
        """删除提醒或任务"""
        try:
            # 获取会话ID
            creator_id = event.get_sender_id()
            raw_msg_origin = event.unified_msg_origin
            msg_origin = self.get_session_id(raw_msg_origin, creator_id) if self.unique_session else raw_msg_origin
            
            # 获取所有提醒和任务
            reminders = self.star_instance.reminder_system.reminder_data.get(msg_origin, [])
            if not reminders:
                return "没有找到任何提醒或任务。"
            
            # 如果指定了删除全部
            if all and all.lower() == "yes":
                if task_only.lower() == "yes":
                    # 只删除任务
                    to_delete = [(i, r) for i, r in enumerate(reminders) if r.get("is_task", False)]
                elif reminder_only.lower() == "yes":
                    # 只删除提醒
                    to_delete = [(i, r) for i, r in enumerate(reminders) if not r.get("is_task", False)]
                else:
                    # 删除所有
                    to_delete = list(enumerate(reminders))
            else:
                # 根据条件筛选
                to_delete = []
                for i, r in enumerate(reminders):
                    if task_only.lower() == "yes" and not r.get("is_task", False):
                        continue
                    if reminder_only.lower() == "yes" and r.get("is_task", False):
                        continue
                
                    match = True
                    if content and content.lower() not in r["text"].lower():
                        match = False
                    if time and time not in r["datetime"]:
                        match = False
                    if date and date not in r["datetime"]:
                        match = False
                    if weekday:
                        dt = datetime.strptime(r["datetime"], "%Y-%m-%d %H:%M")
                        week_map = {'mon': 0, 'tue': 1, 'wed': 2, 'thu': 3, 'fri': 4, 'sat': 5, 'sun': 6}
                        if dt.weekday() != week_map.get(weekday.lower()):
                            match = False
                    if repeat_type and repeat_type.lower() not in r.get("repeat", "none").lower():
                        match = False
                
                    if match:
                        to_delete.append((i, r))
            
            if not to_delete:
                return "没有找到符合条件的提醒或任务。"
            
            # 从后往前删除，避免索引变化
            deleted = []
            for i, r in sorted(to_delete, reverse=True):
                try:
                    await self.star_instance.reminder_system.remove_reminder(event, i + 1)
                    deleted.append(r)
                except Exception as e:
                    logger.error(f"删除提醒/任务时出错: {str(e)}")

            if not deleted:
                return "删除操作未成功执行。"
            
            # 生成删除报告
            tasks = [r for r in deleted if r.get("is_task", False)]
            reminders = [r for r in deleted if not r.get("is_task", False)]
            
            report = []
            if tasks:
                report.append(f"已删除 {len(tasks)} 个任务:")
                for t in tasks:
                    report.append(f"- {t['text']} (时间: {t['datetime']})")
            if reminders:
                report.append(f"已删除 {len(reminders)} 个提醒:")
                for r in reminders:
                    report.append(f"- {r['text']} (时间: {r['datetime']})")
                
            return "\n".join(report)
            
        except Exception as e:
            logger.error(f"删除提醒/任务时出错: {str(e)}")
            return f"删除提醒/任务时出错：{str(e)}" 