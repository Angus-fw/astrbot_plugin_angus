import datetime
from typing import Union
from astrbot.api.event import AstrMessageEvent
from astrbot.api.star import Context
from astrbot.api import logger
from .utils import parse_datetime, save_reminder_data

class ReminderTools:
    def __init__(self, star_instance):
        self.star = star_instance
        self.context = star_instance.context
        self.reminder_data = star_instance.reminder_data
        self.data_file = star_instance.data_file
        self.scheduler_manager = star_instance.scheduler_manager
        self.unique_session = star_instance.unique_session
    
        # 确保 reminder_data 是一个字典
        if not isinstance(self.reminder_data, dict):
            self.reminder_data = {}
            self.star.reminder_data = self.reminder_data
    
    def get_session_id(self, msg_origin, creator_id=None):
        """
        根据会话隔离设置，获取正确的会话ID
        
        Args:
            msg_origin: 原始会话ID
            creator_id: 创建者ID
            
        Returns:
            str: 处理后的会话ID
        """
        if not self.unique_session:
            return msg_origin
            
        # 如果启用了会话隔离，并且有创建者ID，则在会话ID中添加用户标识
        if creator_id:
            # 在群聊环境中添加用户ID
            if (":GroupMessage:" in msg_origin or 
                "@chatroom" in msg_origin or
                ":ChannelMessage:" in msg_origin):
                # 分割会话ID并在末尾添加用户标识
                parts = msg_origin.rsplit(":", 1)
                if len(parts) == 2:
                    return f"{parts[0]}:{parts[1]}_{creator_id}"
            # 在私聊环境中添加用户ID
            elif ":PrivateMessage:" in msg_origin:
                # 分割会话ID并在末尾添加用户标识
                parts = msg_origin.rsplit(":", 1)
                if len(parts) == 2:
                    return f"{parts[0]}:{parts[1]}_{creator_id}"
            # 其他类型的消息，直接添加用户标识
            else:
                return f"{msg_origin}_{creator_id}"
        
        return msg_origin
    
    async def set_reminder(self, event: Union[AstrMessageEvent, Context], text: str, datetime_str: str, user_name: str = "用户", repeat: str = None, holiday_type: str = None):
        '''设置一个提醒
        
        Args:
            text(string): 提醒内容
            datetime_str(string): 提醒时间，格式为 %Y-%m-%d %H:%M
            user_name(string): 提醒对象名称，默认为"用户"
            repeat(string): 重复类型，可选值：每天，每周，每月，每年，不重复
            holiday_type(string): 可选，节假日类型：workday(仅工作日执行)，holiday(仅法定节假日执行)
        '''
        try:
            if isinstance(event, Context):
                msg_origin = self.context.get_event_queue()._queue[0].session_id
                creator_id = None  # Context 模式下无法获取创建者ID
                creator_name = None
            else:
                raw_msg_origin = event.unified_msg_origin
                creator_id = event.get_sender_id()
                # 获取创建者昵称
                creator_name = event.message_obj.sender.nickname if hasattr(event.message_obj, 'sender') and hasattr(event.message_obj.sender, 'nickname') else None
                
                # 使用会话隔离功能获取会话ID
                msg_origin = self.get_session_id(raw_msg_origin, creator_id)
            
            if msg_origin not in self.reminder_data:
                self.reminder_data[msg_origin] = []
            
            # 处理重复类型和节假日类型的组合
            final_repeat = repeat or "不重复"
            if repeat and holiday_type:
                final_repeat = f"{repeat}_{holiday_type}"
            
            reminder = {
                "text": text,
                "datetime": datetime_str,
                "user_name": user_name,
                "repeat": final_repeat,
                "creator_id": creator_id,
                "creator_name": creator_name,  # 添加创建者昵称
                "is_task": False  # 标记为提醒，不是任务
            }
            
            # 添加提醒到数据中
            self.reminder_data[msg_origin].append(reminder)
            
            # 确保更新到 star_instance
            self.star.reminder_data = self.reminder_data
            
            # 解析时间
            dt = datetime.datetime.strptime(datetime_str, "%Y-%m-%d %H:%M")
            
            # 设置定时任务
            job_result = self.scheduler_manager.add_job(msg_origin, reminder, dt)
            if not job_result:
                logger.error("添加定时提醒失败")
                return "设置提醒失败：无法添加定时提醒"
            
            # 保存提醒数据
            save_result = await save_reminder_data(self.data_file, self.reminder_data)
            if not save_result:
                logger.error("保存提醒数据失败")
                return "设置提醒失败：无法保存提醒数据"
            
            # 构建提示信息
            repeat_str = ""
            if repeat == "每天" and not holiday_type:
                repeat_str = "每天"
            elif repeat == "每天" and holiday_type == "workday":
                repeat_str = "工作日"
            elif repeat == "每天" and holiday_type == "holiday":
                repeat_str = "节假日"
            elif repeat == "每周" and not holiday_type:
                repeat_str = "每周"
            elif repeat == "每周" and holiday_type == "workday":
                repeat_str = "每周工作日"
            elif repeat == "每周" and holiday_type == "holiday":
                repeat_str = "每周节假日"
            elif repeat == "每月" and not holiday_type:
                repeat_str = "每月"
            elif repeat == "每月" and holiday_type == "workday":
                repeat_str = "每月工作日"
            elif repeat == "每月" and holiday_type == "holiday":
                repeat_str = "每月节假日"
            elif repeat == "每年" and not holiday_type:
                repeat_str = "每年"
            elif repeat == "每年" and holiday_type == "workday":
                repeat_str = "每年工作日"
            elif repeat == "每年" and holiday_type == "holiday":
                repeat_str = "每年节假日"
            
            return f"已设置提醒:\n内容: {text}\n时间: {datetime_str}{repeat_str}\n\n使用 /si 列表 查看所有提醒"
            
        except Exception as e:
            logger.error(f"设置提醒时出错: {str(e)}")
            return f"设置提醒时出错：{str(e)}"
    
    async def set_task(self, event: Union[AstrMessageEvent, Context], text: str, datetime_str: str, repeat: str = None, holiday_type: str = None):
        '''设置一个任务，到时间后会让AI执行该任务
        
        Args:
            text(string): 任务内容，AI将执行的操作
            datetime_str(string): 任务执行时间，格式为 %Y-%m-%d %H:%M
            repeat(string): 重复类型，可选值：每天，每周，每月，每年，不重复
            holiday_type(string): 可选，节假日类型：workday(仅工作日执行)，holiday(仅法定节假日执行)
        '''
        try:
            if isinstance(event, Context):
                msg_origin = self.context.get_event_queue()._queue[0].session_id
                creator_id = None  # Context 模式下无法获取创建者ID
                creator_name = None
            else:
                raw_msg_origin = event.unified_msg_origin
                creator_id = event.get_sender_id()
                # 获取创建者昵称
                creator_name = event.message_obj.sender.nickname if hasattr(event.message_obj, 'sender') and hasattr(event.message_obj.sender, 'nickname') else None
                
                # 使用会话隔离功能获取会话ID
                msg_origin = self.get_session_id(raw_msg_origin, creator_id)
            
            if msg_origin not in self.reminder_data:
                self.reminder_data[msg_origin] = []
            
            # 处理重复类型和节假日类型的组合
            final_repeat = repeat or "不重复"
            if repeat and holiday_type:
                final_repeat = f"{repeat}_{holiday_type}"
            
            task = {
                "text": text,
                "datetime": datetime_str,
                "user_name": "用户",  # 任务模式下不需要特别指定用户名
                "repeat": final_repeat,
                "creator_id": creator_id,
                "creator_name": creator_name,  # 添加创建者昵称
                "is_task": True  # 标记为任务，不是提醒
            }
            
            # 添加任务到提醒数据中
            self.reminder_data[msg_origin].append(task)
            
            # 解析时间
            dt = datetime.datetime.strptime(datetime_str, "%Y-%m-%d %H:%M")
            
            # 设置定时任务
            job_result = self.scheduler_manager.add_job(msg_origin, task, dt)
            if not job_result:
                logger.error("添加定时任务失败")
                return "设置任务失败：无法添加定时任务"
            
            # 保存提醒数据
            save_result = await save_reminder_data(self.data_file, self.reminder_data)
            if not save_result:
                logger.error("保存任务数据失败")
                return "设置任务失败：无法保存任务数据"
            
            # 构建提示信息
            repeat_str = ""
            if repeat == "每天" and not holiday_type:
                repeat_str = "每天"
            elif repeat == "每天" and holiday_type == "workday":
                repeat_str = "工作日"
            elif repeat == "每天" and holiday_type == "holiday":
                repeat_str = "节假日"
            elif repeat == "每周" and not holiday_type:
                repeat_str = "每周"
            elif repeat == "每周" and holiday_type == "workday":
                repeat_str = "每周工作日"
            elif repeat == "每周" and holiday_type == "holiday":
                repeat_str = "每周节假日"
            elif repeat == "每月" and not holiday_type:
                repeat_str = "每月"
            elif repeat == "每月" and holiday_type == "workday":
                repeat_str = "每月工作日"
            elif repeat == "每月" and holiday_type == "holiday":
                repeat_str = "每月节假日"
            elif repeat == "每年" and not holiday_type:
                repeat_str = "每年"
            elif repeat == "每年" and holiday_type == "workday":
                repeat_str = "每年工作日"
            elif repeat == "每年" and holiday_type == "holiday":
                repeat_str = "每年节假日"
            
            return f"已设置任务:\n内容: {text}\n时间: {datetime_str}{repeat_str}\n\n使用 /si 列表 查看所有任务"
            
        except Exception as e:
            logger.error(f"设置任务时出错: {str(e)}")
            return f"设置任务时出错：{str(e)}"
    
    async def delete_reminder(self, event: Union[AstrMessageEvent, Context], 
                            content: str = None,           # 任务内容关键词
                            time: str = None,              # 具体时间点 HH:MM
                            weekday: str = None,           # 星期 mon,tue,wed,thu,fri,sat,sun
                            repeat_type: str = None,       # 重复类型 daily,weekly,monthly,yearly
                            date: str = None,              # 具体日期 YYYY-MM-DD
                            all: str = None,               # 是否删除所有 "yes"/"no"
                            task_only: str = "no",       # 是否只删除任务
                            reminder_only: str = "no"    # 是否只删除提醒
                            ):
        '''删除符合条件的提醒或者任务，可组合多个条件进行精确筛选
        
        Args:
            content(string): 可选，提醒或者任务内容包含的关键词
            time(string): 可选，具体时间点，格式为 HH:MM，如 "08:00"
            weekday(string): 可选，星期几，可选值：mon,tue,wed,thu,fri,sat,sun
            repeat_type(string): 可选，重复类型，可选值：每天,每周,每月,每年
            date(string): 可选，具体日期，格式为 YYYY-MM-DD，如 "2024-02-09"
            all(string): 可选，是否删除所有提醒，可选值：yes/no，默认no
            task_only(string): 可选，是否只删除任务，可选值：yes/no，默认no
            reminder_only(string): 可选，是否只删除提醒，可选值：yes/no，默认no
        '''
        try:
            if isinstance(event, Context):
                msg_origin = self.context.get_event_queue()._queue[0].session_id
                creator_id = None
            else:
                raw_msg_origin = event.unified_msg_origin
                creator_id = event.get_sender_id()
                
                # 使用会话隔离功能获取会话ID
                msg_origin = self.get_session_id(raw_msg_origin, creator_id)
            
            # 调试信息：打印所有调度任务
            logger.info("Current jobs in scheduler:")
            for job in self.scheduler_manager.scheduler.get_jobs():
                logger.info(f"Job ID: {job.id}, Next run: {job.next_run_time}, Args: {job.args}")
            
            # 获取提醒列表的副本
            reminders = list(self.reminder_data.get(msg_origin, []))
            if not reminders:
                return "当前没有任何提醒或任务。"
            
            # 用于存储要删除的任务索引
            to_delete = []
            
            # 验证星期格式
            week_map = {
                '周日': 6, '周一': 0, '周二': 1, '周三': 2, 
                '周四': 3, '周五': 4, '周六': 5
            }
            if weekday and weekday not in week_map:
                return "星期格式错误，可选值：周日,周一,周二,周三,周四,周五,周六"
            
            # 验证重复类型
            repeat_types = ["每天", "每周", "每月", "每年"]
            if repeat_type and repeat_type.lower() not in repeat_types:
                return "重复类型错误，可选值：每天,每周,每月,每年"
            
            for i, reminder in enumerate(reminders):
                dt = datetime.datetime.strptime(reminder["datetime"], "%Y-%m-%d %H:%M")
                
                # 检查是否只删除任务或只删除提醒
                is_task_only = task_only and task_only.lower() == "yes"
                is_reminder_only = reminder_only and reminder_only.lower() == "yes"
                
                if is_task_only and not reminder.get("is_task", False):
                    continue
                if is_reminder_only and reminder.get("is_task", False):
                    continue
                
                # 如果指定删除所有，直接添加
                if all and all.lower() == "yes":
                    to_delete.append(i)
                    continue
                
                # 检查各个条件，所有指定的条件都必须满足
                match = True
                
                # 检查内容
                if content and content not in reminder["text"]:
                    match = False
                
                # 检查时间点
                if time:
                    reminder_time = dt.strftime("%H:%M")
                    if reminder_time != time:
                        match = False
                
                # 检查星期
                if weekday:
                    if reminder.get("repeat") == "每周":
                        # 对于每周重复的任务，检查是否在指定星期执行
                        if dt.weekday() != week_map[weekday]:
                            match = False
                    else:
                        # 对于非每周重复的任务，检查日期是否落在指定星期
                        if dt.weekday() != week_map[weekday]:
                            match = False
                
                # 检查重复类型
                if repeat_type:
                    # 获取基础重复类型（去除 holiday_type 部分）
                    base_repeat = reminder.get("repeat", "").split("_")[0]
                    if base_repeat != repeat_type.lower():
                        match = False
                
                # 检查具体日期
                if date:
                    reminder_date = dt.strftime("%Y-%m-%d")
                    if reminder_date != date:
                        match = False
                
                # 如果所有条件都满足，添加到删除列表
                if match:
                    to_delete.append(i)
            
            if not to_delete:
                conditions = []
                if content:
                    conditions.append(f"内容包含{content}")
                if time:
                    conditions.append(f"时间为{time}")
                if weekday:
                    conditions.append(f"在{weekday}")
                if repeat_type:
                    conditions.append(f"重复类型为{repeat_type}")
                if date:
                    conditions.append(f"日期为{date}")
                if task_only:
                    conditions.append("仅任务")
                if reminder_only:
                    conditions.append("仅提醒")
                return f"没有找到符合条件的提醒或任务：{', '.join(conditions)}"
            
            # 从后往前删除，避免索引变化
            deleted_reminders = []
            for i in sorted(to_delete, reverse=True):
                reminder = reminders[i]
                
                # 调试信息：打印正在删除的任务
                logger.info(f"Attempting to delete {'task' if reminder.get('is_task', False) else 'reminder'}: {reminder}")
                
                # 尝试删除所有匹配的任务
                for job in self.scheduler_manager.scheduler.get_jobs():
                    if len(job.args) >= 2 and isinstance(job.args[1], dict):
                        job_reminder = job.args[1]
                        if (job_reminder.get('text') == reminder['text'] and 
                            job_reminder.get('datetime') == reminder['datetime']):
                            try:
                                logger.info(f"Removing job: {job.id}")
                                job.remove()
                            except Exception as e:
                                logger.error(f"Error removing job {job.id}: {str(e)}")
                
                deleted_reminders.append(reminder)
                reminders.pop(i)
            
            # 更新数据
            self.reminder_data[msg_origin] = reminders
            # 确保更新到 star_instance
            self.star.reminder_data = self.reminder_data
            # 保存到文件
            save_result = await save_reminder_data(self.data_file, self.reminder_data)
            if not save_result:
                logger.error("保存提醒数据失败")
                return "删除提醒失败：无法保存提醒数据"
            
            # 调试信息：打印剩余的调度任务
            logger.info("Remaining jobs in scheduler:")
            for job in self.scheduler_manager.scheduler.get_jobs():
                logger.info(f"Job ID: {job.id}, Next run: {job.next_run_time}, Args: {job.args}")
            
            # 生成删除报告
            if len(deleted_reminders) == 1:
                item_type = "任务" if deleted_reminders[0].get("is_task", False) else "提醒"
                return f"已删除{item_type}：{deleted_reminders[0]['text']}"
            else:
                tasks = []
                reminders_list = []
                
                for r in deleted_reminders:
                    if r.get("is_task", False):
                        tasks.append(f"- {r['text']}")
                    else:
                        reminders_list.append(f"- {r['text']}")
                
                result = f"已删除 {len(deleted_reminders)} 个项目："
                
                if tasks:
                    result += f"\n\n任务({len(tasks)}):\n" + "\n".join(tasks)
                
                if reminders_list:
                    result += f"\n\n提醒({len(reminders_list)}):\n" + "\n".join(reminders_list)
                
                return result
            
        except Exception as e:
            logger.error(f"删除提醒时出错: {str(e)}")
            return f"删除提醒或任务时出错：{str(e)}" 
