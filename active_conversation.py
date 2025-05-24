import asyncio
import random
import json as _json
from datetime import datetime, timedelta
from astrbot.api import logger
from astrbot.core.platform.astrbot_message import AstrBotMessage, MessageMember, MessageType
from astrbot.core.platform.platform_metadata import PlatformMetadata
from astrbot.api.event import AstrMessageEvent
from astrbot.core.message.components import Plain
from astrbot.core.message.message_event_result import MessageChain
import os
import json
from astrbot.core.star.star_handler import star_handlers_registry, EventType
from astrbot.api.star import StarTools

DEFAULT_TRIGGERS = [
    "你现在感觉有点无聊，想跟朋友打个招呼吧？那就去和你的朋友问声好吧！",
    "你想知道你朋友最近的学习情况，现在向他询问吧。",
    "你想知道你朋友今天过得怎么样，现在就询问他吧。",
    "你正在看书，特别想和你朋友分享，现在向他分享吧。",
    "你正在逛街，想和你朋友分享，现在向他分享吧。",
    "你刚刚听了一首很棒的歌，迫不及待地想推荐给你的朋友，现在告诉他吧！",
    "你突然想起了一个好笑的笑话，觉得你的朋友一定会喜欢，现在讲给他听吧！",
    "你最近想看电影，想问问你的朋友有没有兴趣一起看,现在问问他吧。",
    "你正在做一道新菜，想问问你的朋友喜欢什么样的口味，现在问问他吧。",
    "你刚完成了一项任务，感到很有成就感，想和你的朋友分享这份喜悦。现在向他分享吧。",
    "你发现了一个很有趣的小知识，觉得你的朋友可能会感兴趣，现在告诉他吧！",
    "你最近在计划一次旅行，想问问你的朋友有没有什么好的建议。现在向他询问吧。",
    "你今天的心情很好，想和你的朋友聊聊天，分享一下你的快乐，现在向他分享吧。",
    "你刚刚学到了一项新技能，想问问你的朋友有没有兴趣一起学习，现在问问他吧。",
    "你正在思考人生的一些问题，想找你的朋友聊聊，听听他的看法，现在找他开启话题吧。",
    "你发现了一家新开的餐厅，想问问你的朋友要不要一起去尝尝，现在问问他吧。",
    "你刚刚完成了一次运动，感觉很棒，想鼓励你的朋友也一起来锻炼，现在找他开启话题吧",
    "你今天看到了一幅美丽的风景，想用文字描述给你朋友听，让他也感受一下，现在找他开启话题吧。"
]

class ActiveConversation:
    def __init__(self, context, data_dir=None):
        self.context = context
        self.prob = 0.1  # 主动对话概率1%
        self.triggers = DEFAULT_TRIGGERS.copy()
        if data_dir is None:
            data_dir = StarTools.get_data_dir("astrbot_plugin_angus")
        self.CONFIG_PATH = os.path.join(data_dir, "active_conversation.json")
        self.target_ids = self._load_targets()  # 从文件加载
        self.timer_task = None
        self.last_trigger_time = None  # 记录上次触发时间
        asyncio.create_task(self.initialize())

    def _save_targets(self):
        try:
            with open(self.CONFIG_PATH, "w", encoding="utf-8") as f:
                json.dump({"target_ids": self.target_ids}, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"保存目标用户ID失败: {e}")

    def _load_targets(self):
        try:
            with open(self.CONFIG_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data.get("target_ids", [])
        except Exception:
            return []

    def _detect_platform(self, target_id: str) -> str:
        # 简单规则：如果是QQ号全数字，返回aiocqhttp，否则默认wechatpadpro
        if target_id.isdigit():
            return "aiocqhttp"
        # 你可以根据实际ID特征扩展更多平台判断
        return "wechatpadpro"

    async def initialize(self):
        if not self.target_ids or all(not tid for tid in self.target_ids):
            logger.warning("目标用户ID列表为空，未启动主动对话功能")
            return
        self.timer_task = asyncio.create_task(self._timer_loop())
        logger.info("主动对话定时器已启动")

    async def _timer_loop(self):
        while True:
            try:
                current_time = datetime.now()
                if 7 <= current_time.hour < 24:
                    if (self.last_trigger_time is None or 
                        current_time - self.last_trigger_time >= timedelta(hours=1)):
                        if random.random() < self.prob:
                            logger.info(f"触发主动对话检查 - 当前时间: {current_time.strftime('%H:%M:%S')}, "
                                      f"概率: {self.prob}, 上次触发: "
                                      f"{self.last_trigger_time.strftime('%H:%M:%S') if self.last_trigger_time else '无'}")
                            await self._initiate_conversation()
                            self.last_trigger_time = current_time
                else:
                    logger.debug(f"当前时间 {current_time.strftime('%H:%M:%S')} 不在允许的对话时间范围内(07:00-24:00)")
            except Exception as e:
                logger.error(f"主动对话出错: {e}")
            await asyncio.sleep(60)

    async def _initiate_conversation(self):
        conversation = None  # 初始化conversation变量
        if not self.triggers:
            logger.warning("没有可用的触发语句")
            return
        if not self.target_ids:
            logger.warning("没有目标用户ID")
            return

        provider = self.context.get_using_provider()
        if not provider:
            logger.error("未找到可用的 LLM 提供商")
            return

        for target_id in self.target_ids:
            safe_target_id = target_id.replace(':', '_')
            platform = self._detect_platform(target_id)
            unified_msg = f"{platform}:FriendMessage:{safe_target_id}"
            try:
                # 获取或创建会话
                curr_cid = await self.context.conversation_manager.get_curr_conversation_id(unified_msg)
                if not curr_cid:
                    curr_cid = await self.context.conversation_manager.new_conversation(unified_msg)
                conversation = await self.context.conversation_manager.get_conversation(unified_msg, curr_cid)

                # 获取最近的对话历史
                recent_context = []
                if conversation and conversation.history:
                    recent_context = _json.loads(conversation.history)[-5:]  # 取最近5条

                # 优先用个性化触发语句，否则用默认
                personalized_trigger = None
                if recent_context:
                    # 构造prompt
                    prompt = (
                        f"请根据以下用户（ID: {target_id}）的历史对话，生成一句适合开启新话题的问候或聊天语句，要求自然、贴近用户兴趣：\n"
                        + "\n".join([f"{item['role']}: {item['content']}" for item in recent_context])
                    )
                else:
                    # 没有历史对话时，依然为每个用户构造带ID的个性化prompt
                    prompt = f"请为用户（ID: {target_id}）生成一句自然、友好、个性化的问候语，避免和其他用户完全一样。可以结合ID特征、随机元素或幽默风格。"
                try:
                    llm_resp = await provider.text_chat(prompt=prompt, session_id=curr_cid)
                    if llm_resp.completion_text:
                        personalized_trigger = llm_resp.completion_text.strip()
                except Exception as e:
                    logger.warning(f"生成个性化触发语句失败: {e}")

                trigger = personalized_trigger or random.choice(self.triggers)

                mock_message = AstrBotMessage()
                mock_message.type = MessageType.FRIEND_MESSAGE
                mock_message.message = [Plain(trigger)]
                mock_message.sender = MessageMember(user_id=safe_target_id)
                mock_message.self_id = safe_target_id
                mock_message.session_id = unified_msg
                mock_message.message_str = trigger
                mock_event = AstrMessageEvent(
                    message_str=trigger,
                    message_obj=mock_message,
                    platform_meta=PlatformMetadata(
                        name=platform,
                        description=f"模拟的{platform}平台"
                    ),
                    session_id=unified_msg
                )

                context = []
                system_prompt = ""
                if conversation:
                    context = _json.loads(conversation.history) if conversation.history else []
                    persona_id = conversation.persona_id
                    if persona_id == "[%None]":
                        system_prompt = ""
                    else:
                        try:
                            personas = self.context.provider_manager.personas
                            persona_obj = None
                            if personas:
                                for p in personas:
                                    if p.get('id') == persona_id:
                                        persona_obj = p
                                        break
                            if persona_obj:
                                system_prompt = persona_obj.get('prompt', '')
                        except Exception as e:
                            logger.warning(f"获取 AstrBot 分配人格失败: {e}")

                context.append({"role": "user", "content": trigger})
                llm_req = mock_event.request_llm(
                    prompt=trigger,
                    session_id=curr_cid,
                    contexts=context,
                    system_prompt=system_prompt,
                    conversation=conversation
                )
                mock_event.set_extra("provider_request", llm_req)
                response = await provider.text_chat(**llm_req.__dict__)
                handlers = star_handlers_registry.get_handlers_by_event_type(EventType.OnLLMResponseEvent)
                for handler in handlers:
                    try:
                        await handler.handler(mock_event, response)
                    except Exception as e:
                        logger.error(f"处理LLM响应时出错: {e}")

                if not response.completion_text:
                    logger.error("LLM 响应为空")
                    continue

                context.append({"role": "assistant", "content": response.completion_text})
                if conversation:
                    conversation.history = _json.dumps(context)
                    await self.context.conversation_manager.update_conversation(
                        unified_msg,
                        conversation.cid,
                        context
                    )
                await self.context.send_message(unified_msg, MessageChain().message(response.completion_text))
                logger.info(f"已发送主动对话({safe_target_id}): {trigger} -> {response.completion_text}")
            except Exception as e:
                logger.error(f"主动对话出错({safe_target_id}): {str(e)}")
                continue

    async def shutdown(self):
        """关闭主动对话定时器"""
        if self.timer_task:
            self.timer_task.cancel()

    def add_trigger(self, trigger: str) -> str:
        """添加触发语句"""
        self.triggers.append(trigger)
        return f"已添加触发语句: {trigger}"

    def delete_trigger(self, index: int) -> str:
        """删除触发语句"""
        if index < 1 or index > len(self.triggers):
            return "无效的触发语句索引"
        deleted = self.triggers.pop(index-1)
        return f"已删除触发语句: {deleted}"

    def list_triggers(self) -> str:
        """列出所有触发语句"""
        if not self.triggers:
            return "当前没有触发语句"
        msg = "当前的触发语句:\n"
        for i, trigger in enumerate(self.triggers):
            msg += f"{i+1}. {trigger}\n"
        return msg

    def set_probability(self, prob: float) -> str:
        """设置主动对话概率"""
        if prob < 0 or prob > 1:
            return "概率值必须在 0 到 1 之间"
        self.prob = prob
        return f"已设置主动对话概率为: {prob}"

    def get_probability_info(self) -> str:
        """获取当前主动对话概率信息"""
        msg = f"当前主动对话概率为: {self.prob}\n"
        msg += "对话时间限制：早7点到晚24点\n"
        msg += "两次对话最小间隔：1小时"
        if self.last_trigger_time:
            msg += f"\n上次触发时间：{self.last_trigger_time.strftime('%Y-%m-%d %H:%M:%S')}"
        return msg

    def set_platform(self, platform: str) -> str:
        return "平台已自动识别，无需手动设置。"

    def get_platform_info(self) -> str:
        msg = "平台已自动识别，无需手动设置。\n"
        msg += "支持的平台类型：\n"
        msg += "1. wechatpadpro - 微信平板专业版\n"
        msg += "2. aiocqhttp - QQ机器人"
        return msg

    async def add_target(self, target_id: str) -> str:
        """添加目标用户ID"""
        if target_id in self.target_ids:
            return f"目标用户ID已存在: {target_id}"
        self.target_ids.append(target_id)
        self._save_targets()
        await self.restart_timer()
        return f"已添加目标用户ID: {target_id}"

    async def delete_target(self, target_id: str) -> str:
        """删除目标用户ID"""
        if target_id not in self.target_ids:
            return f"目标用户ID不存在: {target_id}"
        self.target_ids.remove(target_id)
        self._save_targets()
        await self.restart_timer()
        return f"已删除目标用户ID: {target_id}"

    def list_targets(self) -> str:
        """列出所有目标用户ID"""
        msg = "当前目标用户ID列表：\n"
        for i, tid in enumerate(self.target_ids):
            msg += f"{i+1}. {tid}\n"
        return msg

    async def restart_timer(self):
        await self.shutdown()
        await self.initialize()

    def add_trigger(self, trigger: str) -> str:
        """添加触发语句"""
        self.triggers.append(trigger)
        return f"已添加触发语句: {trigger}"

    def delete_trigger(self, index: int) -> str:
        """删除触发语句"""
        if index < 1 or index > len(self.triggers):
            return "无效的触发语句索引"
        deleted = self.triggers.pop(index-1)
        return f"已删除触发语句: {deleted}"

    def list_triggers(self) -> str:
        """列出所有触发语句"""
        if not self.triggers:
            return "当前没有触发语句"
        msg = "当前的触发语句:\n"
        for i, trigger in enumerate(self.triggers):
            msg += f"{i+1}. {trigger}\n"
        return msg 