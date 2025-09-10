import datetime
import json
import os
import aiohttp
from astrbot.api import logger
from astrbot.api.star import StarTools

def parse_datetime(datetime_str: str, week: str = None) -> str:
    '''解析时间字符串，支持简单时间格式，可选择星期
    
    Args:
        datetime_str: 时间字符串，格式为 HH:MM 或 HHMM
        week: 星期几，可选值：周日,周一,周二,周三,周四,周五,周六
    '''
    try:
        today = datetime.datetime.now()
        
        # 处理输入字符串，去除多余空格
        datetime_str = datetime_str.strip()
        
        # 解析时间
        try:
            hour, minute = map(int, datetime_str.split(':'))
        except ValueError:
            try:
                # 尝试处理无冒号格式 (如 "0805")
                if len(datetime_str) == 4:
                    hour = int(datetime_str[:2])
                    minute = int(datetime_str[2:])
                else:
                    raise ValueError()
            except:
                raise ValueError("时间格式错误，请使用 HH:MM 格式（如 8:05）或 HHMM 格式（如 0805）")
        
        if not (0 <= hour <= 23 and 0 <= minute <= 59):
            raise ValueError("时间超出范围")
            
        # 设置时间
        dt = today.replace(hour=hour, minute=minute, second=0, microsecond=0)
        
        # 优先处理 "明天" 和 "后天"
        if week == "明天":
            dt += datetime.timedelta(days=1)
        elif week == "后天":
            dt += datetime.timedelta(days=2)
        # 如果指定了星期几
        elif week:
            week_map = {
                '周日': 6, '周一': 0, '周二': 1, '周三': 2, 
                '周四': 3, '周五': 4, '周六': 5
            }
            if week not in week_map:
                raise ValueError("星期格式错误，可选值：周日,周一,周二,周三,周四,周五,周六")
            
            # 计算目标日期
            current_weekday = dt.weekday()
            target_weekday = week_map[week]
            days_ahead = target_weekday - current_weekday
            # 修正逻辑：只有在今天时间已过才跳到下周，否则就是本周
            if days_ahead < 0 or (days_ahead == 0 and dt <= today):
                days_ahead += 7
            dt = dt + datetime.timedelta(days=days_ahead)
        # 如果没有指定星期几，且时间已过，设置为明天
        elif dt <= today:
            dt = dt + datetime.timedelta(days=1)
            logger.info(f"设置的时间已过，自动调整为明天: {dt.strftime('%Y-%m-%d %H:%M')}")
        
        return dt.strftime("%Y-%m-%d %H:%M")
        
    except Exception as e:
        if isinstance(e, ValueError):
            raise e
        raise ValueError("时间格式错误，请使用 HH:MM 格式（如 8:05）或 HHMM 格式（如 0805）")

def is_outdated(reminder: dict) -> bool:
    '''检查提醒是否过期'''
    if "datetime" in reminder and reminder["datetime"]:  # 确保datetime存在且不为空
        try:
            reminder_time = datetime.datetime.strptime(reminder["datetime"], "%Y-%m-%d %H:%M")
            current_time = datetime.datetime.now()
            # 如果提醒时间已经过去，则认为过期
            is_expired = reminder_time <= current_time
            if is_expired:
                logger.info(f"提醒已过期: {reminder.get('text', '')} 时间: {reminder['datetime']}")
            return is_expired
        except ValueError:
            # 如果日期格式不正确，记录错误并返回False
            logger.error(f"提醒的日期时间格式错误: {reminder.get('datetime', '')}")
            return False
    return False

def load_reminder_data(data_file: str) -> dict:
    '''加载提醒数据'''
    try:
        # 确保数据目录存在
        data_dir = os.path.dirname(data_file)
        if data_dir and not os.path.exists(data_dir):
            os.makedirs(data_dir, exist_ok=True)
            logger.info(f"创建数据目录: {data_dir}")
        
        # 如果文件不存在或为空，创建新的空数据文件
        if not os.path.exists(data_file) or os.path.getsize(data_file) == 0:
            with open(data_file, "w", encoding='utf-8') as f:
                json.dump({}, f, ensure_ascii=False, indent=2)
            return {}
        
        # 尝试读取并解析JSON数据
        try:
            with open(data_file, "r", encoding='utf-8') as f:
                content = f.read().strip()
                if not content:  # 如果文件为空
                    return {}
                data = json.loads(content)
                if not isinstance(data, dict):
                    logger.error("提醒数据格式错误，重置为空字典")
                    return {}
                return data
        except json.JSONDecodeError as e:
            logger.error(f"JSON解析错误: {str(e)}，重置提醒数据")
            # 备份损坏的文件
            if os.path.exists(data_file):
                backup_file = f"{data_file}.bak"
                try:
                    os.rename(data_file, backup_file)
                    logger.info(f"已备份损坏的数据文件到: {backup_file}")
                except Exception as e:
                    logger.error(f"备份数据文件失败: {str(e)}")
            
            # 创建新的空数据文件
            with open(data_file, "w", encoding='utf-8') as f:
                json.dump({}, f, ensure_ascii=False, indent=2)
            return {}
            
    except Exception as e:
        logger.error(f"加载提醒数据失败: {str(e)}")
        return {}

async def save_reminder_data(data_file: str, reminder_data: dict) -> bool:
    '''保存提醒数据
    
    Args:
        data_file: 数据文件路径
        reminder_data: 提醒数据字典
        
    Returns:
        bool: 保存是否成功
    '''
    try:
        # 确保数据目录存在
        data_dir = os.path.dirname(data_file)
        if data_dir and not os.path.exists(data_dir):
            os.makedirs(data_dir, exist_ok=True)
            logger.info(f"创建数据目录: {data_dir}")
        
        # 在保存前清理过期的一次性任务和无效数据
        for group in list(reminder_data.keys()):
            # 只清理过期的一次性任务，保留其他类型的提醒
            reminder_data[group] = [
                r for r in reminder_data[group] 
                if "datetime" in r and r["datetime"] and  # 确保datetime字段存在且不为空
                   not (r.get("repeat", "none") in ["不重复", "none"] and is_outdated(r))  # 只清理过期的一次性任务
            ]
            # 如果群组没有任何提醒了，删除这个群组的条目
            if not reminder_data[group]:
                del reminder_data[group]
        
        # 确保数据是有效的字典格式
        if not isinstance(reminder_data, dict):
            logger.error("提醒数据格式错误，重置为空字典")
            reminder_data = {}
        
        # 保存数据
        with open(data_file, "w", encoding='utf-8') as f:
            json.dump(reminder_data, f, ensure_ascii=False, indent=2)
        
        logger.info(f"成功保存提醒数据到: {data_file}")
        return True
        
    except Exception as e:
        logger.error(f"保存提醒数据失败: {str(e)}")
        return False

# 法定节假日相关功能
class HolidayManager:
    def __init__(self):
        # 使用 StarTools 获取数据目录
        data_dir = StarTools.get_data_dir("astrbot_plugin_angus")
        os.makedirs(data_dir, exist_ok=True)
        self.holiday_cache_file = os.path.join(data_dir, "holiday_cache.json")
        self.holiday_data = self._load_holiday_data()
        
    def _load_holiday_data(self) -> dict:
        """加载节假日数据缓存"""
        if not os.path.exists(self.holiday_cache_file):
            return {}
        
        try:
            with open(self.holiday_cache_file, "r", encoding='utf-8') as f:
                data = json.load(f)
                
            # 检查数据是否过期（缓存超过30天更新一次）
            if "last_update" in data:
                last_update = datetime.datetime.fromisoformat(data["last_update"])
                now = datetime.datetime.now()
                if (now - last_update).days > 30:
                    logger.info("节假日数据缓存已过期，需要更新")
                    return {}
                    
            return data
        except Exception as e:
            logger.error(f"加载节假日数据缓存失败: {e}")
            return {}
    
    async def _save_holiday_data(self):
        """保存节假日数据缓存"""
        try:
            # 添加最后更新时间
            self.holiday_data["last_update"] = datetime.datetime.now().isoformat()
            
            with open(self.holiday_cache_file, "w", encoding='utf-8') as f:
                json.dump(self.holiday_data, f, ensure_ascii=False)
        except Exception as e:
            logger.error(f"保存节假日数据缓存失败: {e}")
            
    async def fetch_holiday_data(self, year: int = None, retry_count: int = 0) -> dict:
        """获取指定年份的节假日数据，带重试机制
        
        Args:
            year: 年份，默认为当前年份
            retry_count: 当前重试次数
            
        Returns:
            dict: 节假日数据，格式为 {日期字符串: 布尔值}
                  布尔值说明: True-法定节假日, False-调休工作日（需要补班的周末）
        """
        if year is None:
            year = datetime.datetime.now().year
            
        # 如果缓存中已有数据则直接返回
        year_key = str(year)
        if year_key in self.holiday_data and "data" in self.holiday_data[year_key]:
            return self.holiday_data[year_key]["data"]
            
        # 否则从API获取
        max_retries = 3
        retry_delay = 1.0
        
        try:
            # 使用 http://timor.tech/api/holiday/year/{year} 接口获取数据
            url = f"http://timor.tech/api/holiday/year/{year}"
            
            # 创建带有超时和连接限制的会话
            timeout = aiohttp.ClientTimeout(total=10, connect=5)
            connector = aiohttp.TCPConnector(limit=10, limit_per_host=5)
            
            async with aiohttp.ClientSession(timeout=timeout, connector=connector) as session:
                async with session.get(url) as response:
                    if response.status != 200:
                        logger.error(f"获取节假日数据失败，状态码: {response.status}")
                        return {}
                        
                    json_data = await response.json()
                    
                    if json_data.get("code") != 0:
                        logger.error(f"获取节假日数据失败: {json_data.get('msg')}")
                        return {}
                    
                    holiday_data = {}
                    for date_str, info in json_data.get("holiday", {}).items():
                        holiday_data[date_str] = info.get("holiday")
                    
                    # 缓存数据
                    if year_key not in self.holiday_data:
                        self.holiday_data[year_key] = {}
                    self.holiday_data[year_key]["data"] = holiday_data
                    await self._save_holiday_data()
                    
                    return holiday_data
                    
        except (aiohttp.ClientError, asyncio.TimeoutError) as e:
            if retry_count < max_retries:
                logger.warning(f"获取节假日数据失败，正在重试 ({retry_count + 1}/{max_retries}): {str(e)}")
                await asyncio.sleep(retry_delay * (retry_count + 1))
                return await self.fetch_holiday_data(year, retry_count + 1)
            else:
                logger.error(f"获取节假日数据失败，已达到最大重试次数: {str(e)}")
                return {}
        except Exception as e:
            logger.error(f"获取节假日数据时发生未知错误: {e}")
            return {}
    
    async def is_holiday(self, date: datetime.datetime = None) -> bool:
        """判断指定日期是否为法定节假日
        
        Args:
            date: 日期，默认为当天
            
        Returns:
            bool: 是否为法定节假日
        """
        if date is None:
            date = datetime.datetime.now()
            
        year = date.year
        # 获取完整日期和不含年份的日期
        full_date_str = date.strftime("%Y-%m-%d")
        short_date_str = date.strftime("%m-%d")
        
        # 获取该年份的节假日数据
        holiday_data = await self.fetch_holiday_data(year)
        
        # 判断是否在节假日数据中，使用不含年份的短日期格式
        if short_date_str in holiday_data:
            # 如果值为True，表示法定节假日
            is_holiday = holiday_data[short_date_str] == True
            return is_holiday
            
        # 如果不在特殊日期列表中，则根据是否为周末判断
        if date.weekday() >= 5:  # 5和6分别是周六和周日
            return True
            
        return False
    
    async def is_workday(self, date: datetime.datetime = None) -> bool:
        """判断指定日期是否为工作日
        
        Args:
            date: 日期，默认为当天
            
        Returns:
            bool: 是否为工作日
        """
        if date is None:
            date = datetime.datetime.now()
            
        year = date.year
        # 获取完整日期和不含年份的日期
        full_date_str = date.strftime("%Y-%m-%d")
        short_date_str = date.strftime("%m-%d")
        
        # 获取该年份的节假日数据
        holiday_data = await self.fetch_holiday_data(year)
        
        # 判断是否在节假日数据中，使用不含年份的短日期格式
        if short_date_str in holiday_data:
            # 如果值为False，表示调休工作日（需要补班的周末）
            # 如果值为True，表示法定节假日
            is_workday = holiday_data[short_date_str] == False
            return is_workday
            
        # 如果是周末且不在节假日数据中，则不是工作日
        if date.weekday() >= 5:  # 5和6分别是周六和周日
            return False
            
        return True 
