from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from config import LabConfig, load_config
from memory_store import estimate_tokens
from model_provider import build_chat_model


@dataclass
class SessionState:
    messages: list[dict[str, str]] = field(default_factory=list)
    token_usage: int = 0
    prompt_tokens_processed: int = 0


class BaselineAgent:
    """Student TODO: implement Agent A.

    Requirements:
    - Within-session memory only
    - No persistent `User.md`
    - Should forget long-term facts across new threads
    """

    def __init__(self, config: LabConfig | None = None, force_offline: bool = False) -> None:
        self.config = config or load_config()
        self.force_offline = force_offline
        self.sessions: dict[str, SessionState] = {}
        self.langchain_agent = None

    def reply(self, user_id: str, thread_id: str, message: str) -> dict[str, Any]:
        """Student TODO: return the agent response and token accounting."""
        # For this lab, we prioritize the offline path unless a live agent is built
        if self.langchain_agent and not self.force_offline:
            pass # Live path not implemented for baseline in this snippet
        
        return self._reply_offline(thread_id, message)

    def token_usage(self, thread_id: str) -> int:
        if thread_id in self.sessions:
            return self.sessions[thread_id].token_usage
        return 0

    def prompt_token_usage(self, thread_id: str) -> int:
        if thread_id in self.sessions:
            return self.sessions[thread_id].prompt_tokens_processed
        return 0

    def compaction_count(self, thread_id: str) -> int:
        # Baseline has no compact memory.
        return 0

    def _reply_offline(self, thread_id: str, message: str) -> dict[str, Any]:
        """Student TODO: implement a simple offline behavior."""
        if thread_id not in self.sessions:
            self.sessions[thread_id] = SessionState()
        session = self.sessions[thread_id]
        
        # Add user message
        session.messages.append({"role": "user", "content": message})
        
        # Calculate prompt context tokens (all messages so far)
        prompt_text = " ".join([m["content"] for m in session.messages])
        prompt_tokens = estimate_tokens(prompt_text)
        session.prompt_tokens_processed += prompt_tokens
        
        # Generate offline response: echo the history so benchmark can find facts if they exist in thread
        history_text = " ".join([m["content"] for m in session.messages if m["role"] == "user"])
        reply_content = f"Offline Baseline Reply. Context: {history_text}"
        
        # Calculate agent tokens for the reply
        agent_tokens = estimate_tokens(reply_content)
        session.token_usage += agent_tokens
        
        # Add agent message
        session.messages.append({"role": "assistant", "content": reply_content})
        
        return {
            "reply": reply_content,
            "token_usage": session.token_usage,
            "prompt_tokens_processed": session.prompt_tokens_processed
        }

    def _maybe_build_langchain_agent(self):
        """Student TODO: optionally wire `create_agent` + `InMemorySaver` here."""
        pass
