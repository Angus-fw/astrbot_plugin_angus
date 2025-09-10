import httpx
import asyncio
import json
from astrbot.api.message_components import At, Plain, Image
from astrbot.api import logger

class SetuTools:
    def __init__(self, enable_setu=True, cd=10):
        self.enable_setu = enable_setu
        self.cd = cd
        self.last_usage = {}
        self.semaphore = asyncio.Semaphore(10)
        self.max_retries = 3
        self.retry_delay = 1.0

    async def fetch_setu(self, retry_count=0):
        """获取普通涩图，带重试机制"""
        try:
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(10.0, connect=5.0, read=10.0),
                limits=httpx.Limits(max_keepalive_connections=5, max_connections=10)
            ) as client:
                resp = await client.get("https://api.lolicon.app/setu/v2?r18=0")
                resp.raise_for_status()
                return resp.json()
        except (httpx.ConnectError, httpx.TimeoutException, httpx.HTTPStatusError) as e:
            if retry_count < self.max_retries:
                logger.warning(f"获取涩图失败，正在重试 ({retry_count + 1}/{self.max_retries}): {str(e)}")
                await asyncio.sleep(self.retry_delay * (retry_count + 1))
                return await self.fetch_setu(retry_count + 1)
            else:
                logger.error(f"获取涩图失败，已达到最大重试次数: {str(e)}")
                raise e
        except Exception as e:
            logger.error(f"获取涩图时发生未知错误: {str(e)}")
            raise e

    async def fetch_taisele(self, retry_count=0):
        """获取R18涩图，带重试机制"""
        try:
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(10.0, connect=5.0, read=10.0),
                limits=httpx.Limits(max_keepalive_connections=5, max_connections=10)
            ) as client:
                resp = await client.get("https://api.lolicon.app/setu/v2?r18=1")
                resp.raise_for_status()
                return resp.json()
        except (httpx.ConnectError, httpx.TimeoutException, httpx.HTTPStatusError) as e:
            if retry_count < self.max_retries:
                logger.warning(f"获取R18涩图失败，正在重试 ({retry_count + 1}/{self.max_retries}): {str(e)}")
                await asyncio.sleep(self.retry_delay * (retry_count + 1))
                return await self.fetch_taisele(retry_count + 1)
            else:
                logger.error(f"获取R18涩图失败，已达到最大重试次数: {str(e)}")
                raise e
        except Exception as e:
            logger.error(f"获取R18涩图时发生未知错误: {str(e)}")
            raise e

    async def get_setu(self, event):
        if not self.enable_setu:
            return event.plain_result("涩图功能已关闭")
        user_id = event.get_sender_id()
        now = asyncio.get_event_loop().time()
        if user_id in self.last_usage and (now - self.last_usage[user_id]) < self.cd:
            remaining_time = self.cd - (now - self.last_usage[user_id])
            return event.plain_result(f"冷却中，请等待 {remaining_time:.1f} 秒后重试。")
        async with self.semaphore:
            try:
                data = await self.fetch_setu()
                if data and data.get('data'):
                    image_url = data['data'][0]['urls']['original']
                    chain = [
                        At(qq=event.get_sender_id()),
                        Plain("给你一张涩图："),
                        Image.fromURL(image_url, size='small'),
                    ]
                    self.last_usage[user_id] = now
                    return event.chain_result(chain)
                else:
                    return event.plain_result("没有找到涩图。")
            except httpx.HTTPStatusError as e:
                logger.error(f"获取涩图HTTP错误: {e.response.status_code}")
                return event.plain_result(f"获取涩图时发生HTTP错误: {e.response.status_code}")
            except httpx.TimeoutException:
                logger.error("获取涩图超时")
                return event.plain_result("获取涩图超时，请稍后重试。")
            except httpx.ConnectError as e:
                logger.error(f"获取涩图连接错误: {e}")
                return event.plain_result("网络连接失败，请检查网络后重试。")
            except httpx.HTTPError as e:
                logger.error(f"获取涩图网络错误: {e}")
                return event.plain_result(f"获取涩图时发生网络错误: {e}")
            except json.JSONDecodeError as e:
                logger.error(f"解析涩图JSON错误: {e}")
                return event.plain_result(f"解析数据时发生错误: {e}")
            except Exception as e:
                logger.exception("获取涩图时发生未知错误:")
                return event.plain_result(f"获取涩图失败，请稍后重试。")

    async def get_taisele(self, event):
        if not self.enable_setu:
            return event.plain_result("涩图功能已关闭")
        user_id = event.get_sender_id()
        now = asyncio.get_event_loop().time()
        if user_id in self.last_usage and (now - self.last_usage[user_id]) < self.cd:
            remaining_time = self.cd - (now - self.last_usage[user_id])
            return event.plain_result(f"冷却中，请等待 {remaining_time:.1f} 秒后重试。")
        async with self.semaphore:
            try:
                data = await self.fetch_taisele()
                if data and data.get('data'):
                    image_url = data['data'][0]['urls']['original']
                    chain = [
                        At(qq=event.get_sender_id()),
                        Plain("给你一张涩图："),
                        Image.fromURL(image_url, size='small'),
                    ]
                    self.last_usage[user_id] = now
                    return event.chain_result(chain)
                else:
                    return event.plain_result("没有找到涩图。")
            except httpx.HTTPStatusError as e:
                logger.error(f"获取R18涩图HTTP错误: {e.response.status_code}")
                return event.plain_result(f"获取涩图时发生HTTP错误: {e.response.status_code}")
            except httpx.TimeoutException:
                logger.error("获取R18涩图超时")
                return event.plain_result("获取涩图超时，请稍后重试。")
            except httpx.ConnectError as e:
                logger.error(f"获取R18涩图连接错误: {e}")
                return event.plain_result("网络连接失败，请检查网络后重试。")
            except httpx.HTTPError as e:
                logger.error(f"获取R18涩图网络错误: {e}")
                return event.plain_result(f"获取涩图时发生网络错误: {e}")
            except json.JSONDecodeError as e:
                logger.error(f"解析R18涩图JSON错误: {e}")
                return event.plain_result(f"解析数据时发生错误: {e}")
            except Exception as e:
                logger.exception("获取R18涩图时发生未知错误:")
                return event.plain_result(f"获取涩图失败，请稍后重试。")

    def set_cd(self, cd: int):
        if cd > 0:
            self.cd = cd
            return f"涩图指令冷却时间已设置为 {cd} 秒。"
        else:
            return "冷却时间必须大于 0。" 