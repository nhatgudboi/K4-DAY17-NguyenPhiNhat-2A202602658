from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from config import LabConfig, load_config
from memory_store import CompactMemoryManager, UserProfileStore, estimate_tokens, extract_profile_updates
from model_provider import build_chat_model


@dataclass
class AgentContext:
    user_id: str
    memory_path: str


class AdvancedAgent:
    """Student TODO: implement Agent B / Advanced Agent.

    Required memory layers:
    1. within-session memory
    2. persistent `User.md`
    3. compact memory for long threads
    """

    def __init__(self, config: LabConfig | None = None, force_offline: bool = False) -> None:
        self.config = config or load_config()
        self.force_offline = force_offline
        self.profile_store = UserProfileStore(self.config.state_dir / "profiles")
        self.compact_memory = CompactMemoryManager(
            threshold_tokens=self.config.compact_threshold_tokens,
            keep_messages=self.config.compact_keep_messages,
        )
        self.thread_tokens: dict[str, int] = {}
        self.thread_prompt_tokens: dict[str, int] = {}

        # TODO: optionally initialize a real LangChain/LangGraph agent.
        self.langchain_agent = None

    def reply(self, user_id: str, thread_id: str, message: str) -> dict[str, Any]:
        """Student TODO: route between offline mode and live mode."""
        if self.langchain_agent and not self.force_offline:
            pass # live path
        return self._reply_offline(user_id, thread_id, message)

    def token_usage(self, thread_id: str) -> int:
        return self.thread_tokens.get(thread_id, 0)

    def prompt_token_usage(self, thread_id: str) -> int:
        return self.thread_prompt_tokens.get(thread_id, 0)

    def memory_file_size(self, user_id: str) -> int:
        return self.profile_store.file_size(user_id)

    def compaction_count(self, thread_id: str) -> int:
        return self.compact_memory.compaction_count(thread_id)

    def _reply_offline(self, user_id: str, thread_id: str, message: str) -> dict[str, Any]:
        """Student TODO: implement the deterministic advanced path."""
        if thread_id not in self.thread_tokens:
            self.thread_tokens[thread_id] = 0
            self.thread_prompt_tokens[thread_id] = 0

        # 1. Extract stable profile facts from the incoming message.
        facts = extract_profile_updates(message)

        # 2. Persist those facts into `User.md`.
        if facts:
            current_profile = self.profile_store.read_text(user_id)
            lines = current_profile.split('\n') if current_profile else []
            for k, v in facts.items():
                found = False
                for i, line in enumerate(lines):
                    if line.startswith(f"{k}:"):
                        # Use edit_text logically by replacing the line if we wanted,
                        # but direct rewrite is robust here.
                        lines[i] = f"{k}: {v}"
                        found = True
                        break
                if not found:
                    lines.append(f"{k}: {v}")
            self.profile_store.write_text(user_id, "\n".join(lines))

        # 3. Append the message into compact memory.
        self.compact_memory.append(thread_id, "user", message)

        # 4. Estimate prompt-context load from `User.md` + summary + recent messages.
        prompt_tokens = self._estimate_prompt_context_tokens(user_id, thread_id)
        self.thread_prompt_tokens[thread_id] += prompt_tokens

        # 5. Generate a response that can answer long-term recall questions.
        reply_content = self._offline_response(user_id, thread_id, message)

        # 6. Append the assistant reply and update token counters.
        self.compact_memory.append(thread_id, "assistant", reply_content)
        agent_tokens = estimate_tokens(reply_content)
        self.thread_tokens[thread_id] += agent_tokens

        return {
            "reply": reply_content,
            "token_usage": self.thread_tokens[thread_id],
            "prompt_tokens_processed": self.thread_prompt_tokens[thread_id]
        }

    def _estimate_prompt_context_tokens(self, user_id: str, thread_id: str) -> int:
        """Student TODO: estimate the context carried into one turn."""
        profile_text = self.profile_store.read_text(user_id)
        ctx = self.compact_memory.context(thread_id)
        summary = str(ctx.get("summary", ""))
        recent_msgs = " ".join([str(m["content"]) for m in ctx.get("messages", [])])
        return estimate_tokens(profile_text + " " + summary + " " + recent_msgs)

    def _offline_response(self, user_id: str, thread_id: str, message: str) -> str:
        """Student TODO: return a deterministic answer using persisted memory."""
        profile_text = self.profile_store.read_text(user_id)
        ctx = self.compact_memory.context(thread_id)
        
        reply_parts = []
        if profile_text:
            reply_parts.append(f"Profile: {profile_text.replace('\n', ', ')}")
            if "ngắn gọn" in profile_text.lower():
                reply_parts.append("3 bullet")
                
        # Also include short-term context to answer in-thread queries
        recent_msgs = ctx.get("messages", [])
        if recent_msgs:
            recent_text = " ".join([str(m["content"]) for m in recent_msgs])
            # limit length to keep agent token cost low
            reply_parts.append(f"Recent: {recent_text[-100:]}")
            
        return " | ".join(reply_parts) if reply_parts else "Đã ghi nhận."

    def _maybe_build_langchain_agent(self):
        """Student TODO: wire a live agent with tools and compact middleware."""
        pass
