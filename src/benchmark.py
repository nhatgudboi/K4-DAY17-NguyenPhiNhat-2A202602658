from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from agent_advanced import AdvancedAgent
from agent_baseline import BaselineAgent
from config import load_config


import json

@dataclass
class BenchmarkRow:
    agent_name: str
    agent_tokens_only: int
    prompt_tokens_processed: int
    recall_score: float
    response_quality: float
    memory_growth_bytes: int
    compactions: int


def load_conversations(path: Path) -> list[dict[str, Any]]:
    """Student TODO: read JSON conversations from disk."""
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def recall_points(answer: str, expected: list[str]) -> float:
    """Student TODO: return 0 / 0.5 / 1 depending on how many expected facts appear."""
    if not expected:
        return 1.0
    ans_lower = answer.lower()
    matches = sum(1 for e in expected if e.lower() in ans_lower)
    if matches == 0:
        return 0.0
    elif matches == len(expected):
        return 1.0
    return 0.5


def heuristic_quality(answer: str, expected: list[str]) -> float:
    """Student TODO: add a lightweight quality score for offline mode."""
    # Since we are offline and generating deterministic text, just return recall_points.
    return recall_points(answer, expected)


def run_agent_benchmark(agent_name: str, agent, conversations: list[dict[str, Any]], config) -> BenchmarkRow:
    """Student TODO: evaluate one agent over many conversations."""
    total_recall = 0.0
    total_quality = 0.0
    recall_count = 0
    memory_growth = 0
    
    seen_threads = set()

    for conv in conversations:
        conv_id = conv["id"]
        user_id = conv["user_id"]
        seen_threads.add(conv_id)
        
        # 1. Feed turns
        for turn in conv["turns"]:
            agent.reply(user_id, conv_id, turn)
            
        # 4. Ask recall in a fresh thread
        recall_thread_id = conv_id + "_recall"
        seen_threads.add(recall_thread_id)
        
        for q in conv.get("recall_questions", []):
            res = agent.reply(user_id, recall_thread_id, q["question"])
            ans = res["reply"]
            expected = q["expected_contains"]
            
            total_recall += recall_points(ans, expected)
            total_quality += heuristic_quality(ans, expected)
            recall_count += 1
            
        # 6. Record memory growth
        if hasattr(agent, "memory_file_size"):
            sz = agent.memory_file_size(user_id)
            if sz > memory_growth:
                memory_growth = sz

    # 2, 3. Track tokens across all seen threads
    total_agent_tokens = sum(agent.token_usage(t) for t in seen_threads)
    total_prompt_tokens = sum(agent.prompt_token_usage(t) for t in seen_threads)
    total_compactions = sum(agent.compaction_count(t) for t in seen_threads)

    # 5. Compute average
    avg_recall = total_recall / recall_count if recall_count > 0 else 0.0
    avg_quality = total_quality / recall_count if recall_count > 0 else 0.0

    return BenchmarkRow(
        agent_name=agent_name,
        agent_tokens_only=total_agent_tokens,
        prompt_tokens_processed=total_prompt_tokens,
        recall_score=avg_recall,
        response_quality=avg_quality,
        memory_growth_bytes=memory_growth,
        compactions=total_compactions
    )


def format_rows(rows: list[BenchmarkRow]) -> str:
    """Student TODO: print a markdown table or tabulated output."""
    try:
        from tabulate import tabulate
    except ImportError:
        tabulate = None

    headers = [
        "Agent", "Agent tokens only", "Prompt tokens processed", 
        "Cross-session recall", "Response quality", 
        "Memory growth (bytes)", "Compactions"
    ]
    table_data = [
        [
            r.agent_name, 
            r.agent_tokens_only, 
            r.prompt_tokens_processed, 
            f"{r.recall_score:.2f}", 
            f"{r.response_quality:.2f}", 
            r.memory_growth_bytes, 
            r.compactions
        ] 
        for r in rows
    ]
    
    if tabulate:
        return tabulate(table_data, headers=headers, tablefmt="github")
    
    # Fallback if tabulate not installed (though it should be)
    out = " | ".join(headers) + "\n" + "-" * 120 + "\n"
    for row in table_data:
        out += " | ".join(map(str, row)) + "\n"
    return out


def main() -> None:
    """Student TODO: run both benchmark suites."""
    config = load_config(Path(__file__).resolve().parent.parent)

    std_path = config.data_dir / "conversations.json"
    long_path = config.data_dir / "advanced_long_context.json"

    std_data = load_conversations(std_path)
    long_data = load_conversations(long_path)

    print("=== Standard Benchmark ===")
    baseline_std = BaselineAgent(config, force_offline=True)
    advanced_std = AdvancedAgent(config, force_offline=True)
    
    row1 = run_agent_benchmark("Baseline", baseline_std, std_data, config)
    row2 = run_agent_benchmark("Advanced", advanced_std, std_data, config)
    print(format_rows([row1, row2]))
    print()

    print("=== Long-Context Stress Benchmark ===")
    baseline_long = BaselineAgent(config, force_offline=True)
    advanced_long = AdvancedAgent(config, force_offline=True)
    
    row3 = run_agent_benchmark("Baseline", baseline_long, long_data, config)
    row4 = run_agent_benchmark("Advanced", advanced_long, long_data, config)
    print(format_rows([row3, row4]))


if __name__ == "__main__":
    main()
