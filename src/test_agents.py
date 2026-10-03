from __future__ import annotations

from pathlib import Path

from agent_advanced import AdvancedAgent
from agent_baseline import BaselineAgent
from config import load_config


from config import LabConfig
from model_provider import ProviderConfig
from memory_store import UserProfileStore, CompactMemoryManager

def make_config(tmp_path: Path):
    """Student TODO: build an isolated config for tests."""
    return LabConfig(
        base_dir=tmp_path,
        data_dir=tmp_path / "data",
        state_dir=tmp_path / "state",
        compact_threshold_tokens=20,
        compact_keep_messages=2,
        model=ProviderConfig("openai", "model", 0.0, "key"),
        judge_model=ProviderConfig("openai", "model", 0.0, "key")
    )


def test_user_markdown_read_write_edit(tmp_path: Path) -> None:
    """Student TODO: verify `User.md` can be created, updated, and edited."""
    store = UserProfileStore(tmp_path / "profiles")
    
    # Write and read
    store.write_text("user1", "name: Alice\nlocation: Hanoi")
    content = store.read_text("user1")
    assert "Alice" in content
    
    # Edit
    changed = store.edit_text("user1", "location: Hanoi", "location: HCM")
    assert changed is True
    
    content2 = store.read_text("user1")
    assert "HCM" in content2
    assert "Hanoi" not in content2


def test_compact_trigger(tmp_path: Path) -> None:
    """Student TODO: verify long threads trigger compaction."""
    cm = CompactMemoryManager(threshold_tokens=10, keep_messages=2)
    
    # Feed long strings
    long_msg = "This is a very very very long message that definitely exceeds ten tokens." * 5
    cm.append("t1", "user", long_msg)
    cm.append("t1", "assistant", long_msg)
    cm.append("t1", "user", long_msg)
    
    assert cm.compaction_count("t1") > 0


def test_cross_session_recall(tmp_path: Path) -> None:
    """Student TODO: verify advanced remembers across sessions and baseline does not."""
    config = make_config(tmp_path)
    
    baseline = BaselineAgent(config, force_offline=True)
    advanced = AdvancedAgent(config, force_offline=True)
    
    # Thread 1: provide fact
    baseline.reply("user1", "thread1", "Mình tên là Tester.")
    advanced.reply("user1", "thread1", "Mình tên là Tester.")
    
    # Thread 2: ask for fact
    res_b = baseline.reply("user1", "thread2", "Mình tên gì?")
    res_a = advanced.reply("user1", "thread2", "Mình tên gì?")
    
    assert "Tester" not in res_b["reply"]
    assert "Tester" in res_a["reply"]


def test_compact_reduces_prompt_load_on_long_thread(tmp_path: Path) -> None:
    """Student TODO: compare prompt load of baseline vs advanced on a long thread."""
    config = make_config(tmp_path)
    
    baseline = BaselineAgent(config, force_offline=True)
    advanced = AdvancedAgent(config, force_offline=True)
    
    for i in range(15):
        msg = f"Long message padding to simulate tokens number {i} " * 5
        baseline.reply("user1", "thread_long", msg)
        advanced.reply("user1", "thread_long", msg)
        
    p_base = baseline.prompt_token_usage("thread_long")
    p_adv = advanced.prompt_token_usage("thread_long")
    
    assert p_adv < p_base
    assert advanced.compaction_count("thread_long") > 0
