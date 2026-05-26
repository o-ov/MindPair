import json
from typing import Optional, Callable, Awaitable
from sqlalchemy.orm import Session as DBSession

from database import Message
from config import DEFAULT_ROLE_PROMPT_A, DEFAULT_ROLE_PROMPT_B
from services import minimax, deepseek


async def stream_to_callback(async_iter, callback: Callable[[str], Awaitable[None]]):
    full_content = ""
    async for chunk in async_iter:
        full_content += chunk
        await callback(chunk)
    return full_content


class Orchestrator:
    def __init__(
        self,
        db: DBSession,
        session_id: int,
        task: str,
        config_a: dict,
        config_b: dict,
        first_mover: str = "A",
        consensus_rounds: int = 2,
    ):
        self.db = db
        self.session_id = session_id
        self.task = task
        self.config_a = config_a or {}
        self.config_b = config_b or {}
        self.first_mover = first_mover
        self.consensus_rounds = consensus_rounds

        self.round = 0
        self.no_change_count = 0
        self.current_speaker = first_mover
        self.messages = []

        self.system_a = self.config_a.get("system_prompt") or DEFAULT_ROLE_PROMPT_A
        self.system_b = self.config_b.get("system_prompt") or DEFAULT_ROLE_PROMPT_B

    def _build_messages(self, role: str, content: str) -> list[dict]:
        system = self.system_a if role == "A" else self.system_b

        messages = [{"role": "system", "content": system}]

        messages.append({"role": "user", "content": f"任务目标：{self.task}"})

        for msg in self.messages:
            speaker = "产品大神张小龙(MiniMax)" if msg.role == "A" else "产品大神张小龙(DeepSeek)"
            messages.append({"role": "assistant", "content": f"[{speaker}]\n{msg.content}"})

        if content:
            messages.append({"role": "user", "content": content})

        return messages

    def _save_message(self, role: str, content: str):
        msg = Message(
            session_id=self.session_id,
            role=role,
            content=content,
            round=self.round,
        )
        self.db.add(msg)
        self.db.commit()
        self.messages.append(msg)
        return msg

    def _is_proposing_changes(self, content: str) -> bool:
        change_indicators = [
            "建议修改",
            "需要调整",
            "可以优化",
            "改进一下",
            "提议",
            "修改为",
            "优化",
            "改动",
            "调整",
            "完善",
            "不足",
            "问题",
            "风险",
            "需要改进",
        ]
        content_lower = content.lower()
        return any(indicator in content_lower for indicator in change_indicators)

    async def run(self, callback: Callable[[dict], Awaitable[None]]):
        await callback({
            "type": "start",
            "round": self.round,
            "speaker": self.current_speaker,
        })

        first_content = f"请基于以下任务目标，设计一个初步方案：\n\n{self.task}"
        await callback({"type": "thinking", "speaker": self.current_speaker})

        if self.current_speaker == "A":
            stream = minimax.chat(
                self._build_messages("A", first_content),
                temperature=self.config_a.get("temperature", 0.7),
                max_tokens=self.config_a.get("max_tokens", 2048),
            )
        else:
            stream = deepseek.chat(
                self._build_messages("B", first_content),
                temperature=self.config_b.get("temperature", 0.7),
                max_tokens=self.config_b.get("max_tokens", 2048),
            )

        first_response = await stream_to_callback(stream, lambda c: callback({"type": "chunk", "content": c}))
        self._save_message(self.current_speaker, first_response)

        await callback({"type": "message_end", "speaker": self.current_speaker})

        self.current_speaker = "B" if self.current_speaker == "A" else "A"
        self.round += 1
        self.no_change_count = 0

        while True:
            if self.round >= 50:
                await callback({"type": "end", "reason": "max_rounds"})
                break

            await callback({
                "type": "thinking",
                "speaker": self.current_speaker,
            })

            if self.current_speaker == "A":
                prompt = f"基于对方的产品思路和方案，提出你的优化建议和想法：\n\n{self.task}"
                stream = minimax.chat(
                    self._build_messages("A", prompt),
                    temperature=self.config_a.get("temperature", 0.7),
                    max_tokens=self.config_a.get("max_tokens", 2048),
                )
            else:
                prompt = f"基于对方的产品思路和方案，提出你的优化建议和想法：\n\n{self.task}"
                stream = deepseek.chat(
                    self._build_messages("B", prompt),
                    temperature=self.config_b.get("temperature", 0.7),
                    max_tokens=self.config_b.get("max_tokens", 2048),
                )

            response = await stream_to_callback(stream, lambda c: callback({"type": "chunk", "content": c}))
            self._save_message(self.current_speaker, response)

            await callback({"type": "message_end", "speaker": self.current_speaker})

            if not self._is_proposing_changes(response):
                self.no_change_count += 1
                if self.no_change_count >= self.consensus_rounds:
                    await callback({"type": "end", "reason": "consensus"})
                    break
            else:
                self.no_change_count = 0

            self.current_speaker = "B" if self.current_speaker == "A" else "A"
            self.round += 1
