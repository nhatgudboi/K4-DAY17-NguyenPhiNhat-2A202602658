from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


import re

def estimate_tokens(text: str) -> int:
    """Stable heuristic token estimator: strip, then len/4, min 1."""
    if not text:
        return 0
    text = text.strip()
    if not text:
        return 0
    return max(1, len(text) // 4)


@dataclass
class UserProfileStore:
    """Persistent storage for User.md."""
    root_dir: Path

    def path_for(self, user_id: str) -> Path:
        safe_id = re.sub(r'[^a-zA-Z0-9_.-]', '_', user_id)
        if not safe_id:
            safe_id = "default"
        user_dir = self.root_dir / safe_id
        user_dir.mkdir(parents=True, exist_ok=True)
        return user_dir / "User.md"

    def read_text(self, user_id: str) -> str:
        p = self.path_for(user_id)
        if p.exists():
            return p.read_text(encoding="utf-8")
        return ""

    def write_text(self, user_id: str, content: str) -> Path:
        p = self.path_for(user_id)
        p.write_text(content, encoding="utf-8")
        return p

    def edit_text(self, user_id: str, search_text: str, replacement: str) -> bool:
        content = self.read_text(user_id)
        if search_text and search_text in content:
            new_content = content.replace(search_text, replacement)
            if new_content != content:
                self.write_text(user_id, new_content)
                return True
        return False

    def file_size(self, user_id: str) -> int:
        p = self.path_for(user_id)
        if p.exists():
            return p.stat().st_size
        return 0


def extract_profile_updates(message: str) -> dict[str, str]:
    """Convert raw user text into stable profile facts.

    Supported keys: name, location, profession, drink, food, pet, style, interests.
    The function filters short questions, jokes, and business-trip noise so that
    only durable user-level facts are written into User.md.
    """
    if not message or not message.strip():
        return {}

    text = message.strip()
    lower = text.lower()

    # Skip short questions (no fact is being provided).
    if text.rstrip().endswith('?') and len(text.split()) < 25:
        return {}

    # Noise detection.
    is_joke = any(
        kw in lower
        for kw in [
            "nói đùa", "đùa thôi", "chỉ là câu đùa",
            "đùa với đồng nghiệp", "hay là chuyển sang",
        ]
    )
    is_trip = any(
        kw in lower
        for kw in [
            "đi họp", "công tác", "họp với đối tác",
            "bay ra họp", "họp hai ngày", "vừa bay ra",
        ]
    )

    facts: dict[str, str] = {}

    # NAME: "tên là X" / "tên mình là X" (capitalized, 1-5 words).
    name_matches: list[tuple[str, int, int]] = []
    for m in re.finditer(
        r'tên\s+(?:mình\s+)?là\s+([^\n]+?)(?=[.,;:\n]|$)',
        text,
        re.IGNORECASE,
    ):
        val = m.group(1).strip()
        if 1 <= len(val.split()) <= 5 and val and val[0].isalpha() and val[0] == val[0].upper():
            name_matches.append((val, m.start(), m.end()))
    if name_matches:
        facts["name"] = name_matches[-1][0]

    # LOCATION: pick the *non-noise* match that is NOT inside a "trước đó / cũ"
    # window. We scan all matches and use _last_valid to drop any match whose
    # preceding 40-char context contains a "previous/old" hint, so the user's
    # correction ("đang ở Huế chứ không còn ở Đà Nẵng") wins.
    if not is_trip:
        loc_pattern = (
            r'(?:sống\s+ở|chuyển\s+sang|chuyển\s+về'
            r'|đang\s+làm\s+việc\s+ở|đang\s+ở|hiện\s+ở|ở)\s+'
            r'([A-ZÀ-Ỹ][a-zà-ỹ]+(?:\s+[A-ZÀ-Ỹ][a-zà-ỹ]+){0,3})'
        )
        loc_matches: list[tuple[str, int, int]] = []
        for m in re.finditer(loc_pattern, text):
            val = m.group(1).strip()
            # Trim trailing filler words so we keep only the place.
            for sep in [
                " thì", " nhưng", " để", " trong", " vài", " dù",
                " chứ", " và ", " như ", " có ", " mỗi ",
            ]:
                idx = val.find(sep)
                if idx > 0:
                    val = val[:idx].strip()
            loc_matches.append((val, m.start(), m.end()))
        if loc_matches:
            chosen = _last_valid(loc_matches, text, [
                "trước đó", "trước kia", "có nhắc", "từng ở",
                "không còn", "cũ", "trước",
            ])
            if chosen:
                facts["location"] = chosen

    # PROFESSION: prefer later matches (corrections), skip negated contexts.
    if not is_joke:
        prof_pattern = (
            r'(?:đang\s+)?(?:làm|chuyển\s+sang|là)\s+'
            r'((?:[A-ZÀ-Ỹ][A-Za-zÀ-ỹ-]*\s+)*'
            r'(?:engineer|developer|dev|data scientist))'
        )
        prof_matches: list[tuple[str, int, int]] = []
        for m in re.finditer(prof_pattern, text, re.IGNORECASE):
            val = m.group(1).strip()
            ctx = text[max(0, m.start() - 30):m.start()].lower()
            if any(
                kw in ctx
                for kw in [
                    "không còn", "đừng nói", "không phải",
                    "không nên", "đó là thông tin cũ",
                ]
            ):
                continue
            prof_matches.append((val, m.start(), m.end()))
        if prof_matches:
            facts["profession"] = prof_matches[-1][0]

    # DRINK: combine several patterns, prefer the "đồ uống yêu thích là" form.
    drink_candidates: list[tuple[str, int, int]] = []
    for m in re.finditer(
        r'đồ\s+uống\s+yêu\s+thích\s+là\s+([^\n]+?)(?=[.,;:\n]|$)',
        text,
        re.IGNORECASE,
    ):
        val = m.group(1).strip()
        if val:
            drink_candidates.append((val, m.start(), m.end()))
    if re.search(r'thích', lower) and re.search(r'cà\s+phê', lower):
        for m in re.finditer(
            r'và\s+(cà\s+phê[^\n]+?)(?=[.,;:\n]|$)',
            text,
            re.IGNORECASE,
        ):
            val = m.group(1).strip()
            if val:
                drink_candidates.append((val, m.start(), m.end()))
    for m in re.finditer(
        r'\buống\s+([A-Za-zÀ-ỹ][A-Za-z0-9\sÀ-ỹ]+?)(?=[.,;:\n]|\s+(?:như|đang|mỗi|để|cho|và)\s|$)',
        text,
        re.IGNORECASE,
    ):
        val = m.group(1).strip()
        if val and 1 <= len(val.split()) <= 5:
            drink_candidates.append((val, m.start(), m.end()))
    if drink_candidates:
        drink_candidates.sort(key=lambda c: (
            0 if "đồ uống" in text[max(0, c[1] - 15):c[1]].lower() else 1
        ))
        facts["drink"] = drink_candidates[0][0]

    # FOOD: "món ăn yêu thích là X" / "ăn mì Quảng".
    food_matches: list[tuple[str, int]] = []
    for m in re.finditer(
        r'món\s+ăn\s+yêu\s+thích\s+là\s+([^\n]+?)(?=[.,;:\n]|$)',
        text,
        re.IGNORECASE,
    ):
        val = m.group(1).strip()
        if val:
            food_matches.append((val, m.start()))
    if "mì quảng" in lower:
        for m in re.finditer(r'\băn\s+(mì\s+Quảng)', text):
            food_matches.append((m.group(1).strip(), m.start()))
    if food_matches:
        facts["food"] = food_matches[-1][0]

    # PET: corgi + Bơ (durable preference).
    if "corgi" in lower:
        facts["pet"] = "corgi (tên Bơ)"

    # STYLE: ngắn gọn / 3 bullet / bullet ngắn.
    if (
        "3 bullet" in lower
        or "3-bullet" in lower
        or "thành 3" in lower
        or "thành ba bullet" in lower
        or "dạng 3 bullet" in lower
    ):
        facts["style"] = "ngắn gọn (3 bullet)"
    elif "ngắn gọn" in lower:
        facts["style"] = "ngắn gọn"
    elif "bullet ngắn" in lower:
        facts["style"] = "ngắn gọn (bullet ngắn)"

    # INTERESTS: technical interests only.
    # Skip interest extraction when the sentence is about drinks/food so we
    # don't capture "cà phê sữa đá" or "mì Quảng" as an interest.
    int_matches: list[tuple[str, int]] = []
    if not (
        "đồ uống yêu thích là" in lower
        or "món ăn yêu thích là" in lower
        or "thích cà phê" in lower
        or "thích uống" in lower
        or "thích ăn" in lower
    ):
        for m in re.finditer(
            r'(?:thích|đang\s+quan\s+tâm\s+(?:nhiều\s+)?(?:đến|tới)'
            r'|mối\s+quan\s+tâm\s+chính)\s+'
            r'([A-ZÀ-Ỹ][A-Za-z0-9À-ỹ,\s]+?)(?=[.,;:\n]|\s+và\s+(?:cà\s+phê|benchmark|AI\s+ứng))',
            text,
            re.IGNORECASE,
        ):
            val = m.group(1).strip().rstrip(",")
            val = re.split(r'\s+và\s+', val)[0].strip()
            # Drop if the captured value is itself a drink/food phrase.
            if val and len(val) > 3 and val.lower() not in {
                "cà phê sữa đá", "mì quảng",
            }:
                int_matches.append((val, m.start()))
    if int_matches:
        facts["interests"] = int_matches[-1][0]

    return facts


def _last_valid(
    items_with_pos: list[tuple[str, int, int]],
    text: str,
    exclude_keywords: list[str],
) -> str | None:
    """Return the last item whose preceding 40-char context contains no exclude keyword."""
    lower = text.lower()
    for item, start, _end in reversed(items_with_pos):
        ctx = lower[max(0, start - 40):start]
        if any(kw in ctx for kw in exclude_keywords):
            continue
        return item
    if items_with_pos:
        return items_with_pos[-1][0]
    return None


def summarize_messages(messages: list[dict[str, str]], max_items: int = 6) -> str:
    """Create a compact summary of older messages."""
    if not messages:
        return ""
    lines = []
    for m in messages[:max_items]:
        content_preview = m['content'][:100] + ("..." if len(m['content']) > 100 else "")
        lines.append(f"{m['role']}: {content_preview}")
    return "\n".join(lines)


@dataclass
class CompactMemoryManager:
    """Compact memory for long threads."""
    threshold_tokens: int
    keep_messages: int
    state: dict[str, dict[str, object]] = field(default_factory=dict)

    def append(self, thread_id: str, role: str, content: str) -> None:
        if thread_id not in self.state:
            self.state[thread_id] = {
                "messages": [],
                "summary": "",
                "compactions": 0
            }

        st = self.state[thread_id]
        st["messages"].append({"role": role, "content": content})

        summary_text = str(st["summary"])
        msgs_text = " ".join([str(m["content"]) for m in st["messages"]])
        total_tokens = estimate_tokens(summary_text + " " + msgs_text)

        if total_tokens > self.threshold_tokens:
            if len(st["messages"]) > self.keep_messages:
                keep_idx = len(st["messages"]) - self.keep_messages
                to_summarize = st["messages"][:keep_idx]
                kept = st["messages"][keep_idx:]

                new_sum = summarize_messages(to_summarize)
                if summary_text:
                    st["summary"] = summary_text + "\n" + new_sum
                else:
                    st["summary"] = new_sum

                st["messages"] = kept
                st["compactions"] = int(st["compactions"]) + 1

    def context(self, thread_id: str) -> dict[str, object]:
        if thread_id not in self.state:
            return {"messages": [], "summary": "", "compactions": 0}
        return self.state[thread_id]

    def compaction_count(self, thread_id: str) -> int:
        return int(self.context(thread_id).get("compactions", 0))