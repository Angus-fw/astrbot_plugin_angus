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

    async def fetch_setu(self):
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get("https://api.lolicon.app/setu/v2?r18=0")
            resp.raise_for_status()
            return resp.json()

    async def fetch_taisele(self):
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get("https://api.lolicon.app/setu/v2?r18=1")
            resp.raise_for_status()
            return resp.json()

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
                if data['data']:
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
                return event.plain_result(f"获取涩图时发生HTTP错误: {e.response.status_code}")
            except httpx.TimeoutException:
                return event.plain_result("获取涩图超时，请稍后重试。")
            except httpx.HTTPError as e:
                return event.plain_result(f"获取涩图时发生网络错误: {e}")
            except json.JSONDecodeError as e:
                return event.plain_result(f"解析JSON时发生错误: {e}")
            except Exception as e:
                logger.exception("Setu command error:")
                return event.plain_result(f"发生未知错误: {e}")

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
                if data['data']:
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
                return event.plain_result(f"获取涩图时发生HTTP错误: {e.response.status_code}")
            except httpx.TimeoutException:
                return event.plain_result("获取涩图超时，请稍后重试。")
            except httpx.HTTPError as e:
                return event.plain_result(f"获取涩图时发生网络错误: {e}")
            except json.JSONDecodeError as e:
                return event.plain_result(f"解析JSON时发生错误: {e}")
            except Exception as e:
                logger.exception("Setu command error:")
                return event.plain_result(f"发生未知错误: {e}")

    def set_cd(self, cd: int):
        if cd > 0:
            self.cd = cd
            return f"涩图指令冷却时间已设置为 {cd} 秒。"
        else:
            return "冷却时间必须大于 0。" 