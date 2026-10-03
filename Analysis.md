# Phân Tích Kết Quả: Hệ Thống Trí Nhớ Cho AI Agent (Lab 17)

Dưới đây là kết quả đo lường sau khi chạy cả hai bộ dữ liệu (Standard và Long-Context Stress) trên phiên bản sạch (clean state), sau khi nâng cấp `extract_profile_updates()` để bắt được profession, food, pet, interests, drink và xử lý nhiễu joke/trip:

```text
=== Standard Benchmark ===
| Agent    |   Agent tokens only |   Prompt tokens processed |   Cross-session recall |   Response quality |   Memory growth (bytes) |   Compactions |
|----------|---------------------|---------------------------|------------------------|--------------------|-------------------------|---------------|
| Baseline |                9366 |                     36895 |                   0.11 |               0.11 |                       0 |             0 |
| Advanced |                7971 |                     43849 |                   0.79 |               0.79 |                     227 |             1 |

=== Long-Context Stress Benchmark ===
| Agent    |   Agent tokens only |   Prompt tokens processed |   Cross-session recall |   Response quality |   Memory growth (bytes) |   Compactions |
|----------|---------------------|---------------------------|------------------------|--------------------|-------------------------|---------------|
| Baseline |               20798 |                    127428 |                   0.00 |               0.00 |                       0 |             0 |
| Advanced |                1295 |                     14087 |                   0.67 |               0.67 |                     132 |            15 |
```

Bốn con số đáng nhấn:

- **Cross-session recall**: Advanced tăng từ 0.43 lên **0.79** (Standard) và từ 0.5 lên **0.67** (Stress). Baseline giữ nguyên 0.11 / 0.00 vì không ghi file nào.
- **Memory growth (bytes)**: Advanced ghi 227 bytes ở Standard và 132 bytes ở Stress. Baseline = 0 ở cả hai.
- **Compactions**: Advanced kích hoạt 1 lần ở Standard và 15 lần ở Stress; Baseline luôn 0.
- **Stress prompt tokens**: Baseline = 127428, Advanced = 14087 — Advanced dùng ít hơn ~9 lần vì compact nén được phần lớn lịch sử.

## Bốn Luận Điểm Chính

### 1. Vì sao Advanced có recall tốt hơn Baseline
**Số liệu:** Ở cả hai bảng, `Cross-session recall` của Advanced (0.79 và 0.67) đều vượt xa Baseline (0.11 và 0.00). Đồng thời, `Memory growth` của Baseline luôn bằng 0, còn Advanced lần lượt 227 và 132 bytes.

**Cơ chế và Giải thích:** Advanced sở hữu lớp Persistent Memory (lưu xuống đĩa qua `User.md`). Trong hàm `_reply_offline()`, nó liên tục gọi `extract_profile_updates()` để trích xuất fact ổn định (name, location, profession, drink, food, pet, style, interests) và dùng `profile_store` để ghi đè hoặc thêm fact mới. Hàm này được nâng cấp với ba cải tiến chính so với phiên bản chỉ dùng regex thô:

1. **Lọc nhiễu chủ động**: các câu chứa "nói đùa", "đùa thôi", "chỉ là câu đùa", "đùa với đồng nghiệp", "hay là chuyển sang product manager" được gán cờ `is_joke` để bỏ qua việc ghi profession. Tương tự, các câu có "đi họp", "công tác", "họp với đối tác", "bay ra họp", "họp hai ngày" được gán cờ `is_trip` để bỏ qua location.
2. **Xử lý correction**: profession ưu tiên match xuất hiện sau cùng trong câu (ví dụ: "Mình không còn làm backend engineer nữa, giờ chuyển sang MLOps engineer" → chỉ ghi "MLOps engineer"), và bỏ qua các match nằm trong vùng ngữ cảnh chứa "không còn", "đừng nói", "không phải", "không nên", "đó là thông tin cũ". Location dùng helper `_last_valid` để bỏ qua match có ngữ cảnh 40 ký tự trước chứa "trước đó", "trước kia", "có nhắc", "từng ở", giúp fact mới thắng fact cũ.
3. **Bắt nhiều loại fact hơn**: thêm drink, food, pet (corgi + Bơ), style (3 bullet riêng biệt với "ngắn gọn"), và interests kỹ thuật. Nhờ vậy, các câu hỏi recall về mì Quảng, corgi, MLOps engineer, 3 bullet đều có dữ liệu để trả lời.

Khi bị hỏi ở một thread hoàn toàn mới, Baseline mất trắng ngữ cảnh (vì session được quản lý theo `thread_id`), trong khi Advanced đọc trực tiếp `User.md` lên và trả lời chính xác thông tin xuyên phiên.

### 2. Vì sao Advanced có thể tốn hơn ở hội thoại ngắn
**Số liệu:** Ở bảng Standard, `Prompt tokens processed` của Advanced (43655) cao hơn Baseline (36895) — chênh khoảng 18%. Cùng lúc `Compactions` của Advanced chỉ là 1, nghĩa là phần lớn hội thoại chưa được nén.

**Cơ chế và Giải thích:** Ở mỗi lượt hội thoại, Advanced cộng ba thành phần vào prompt context theo `_estimate_prompt_context_tokens()`: nội dung `User.md` (đã phình lên ~227 bytes sau khi ghi nhiều fact), summary của compact memory, và các message gần nhất. Baseline chỉ mang theo danh sách message thuần. Vì các hội thoại Standard chỉ khoảng 10 lượt và chưa đủ dài để compact kích hoạt nhiều, Advanced phải trả "thuế" cố định: đọc/ghi `User.md`, chạy regex extraction, và mang profile vào context. Khi thread dài ra, compact bắt đầu bù lại, và ở bảng Stress (15 compactions) Advanced vượt Baseline rõ rệt về prompt efficiency.

Đây chính là trade-off cốt lõi của memory system: lớp persistent + extraction tốn chi phí ở hội thoại ngắn nhưng cực kỳ có giá trị khi hội thoại dài và qua nhiều phiên.

### 3. Vì sao Compact Memory có lợi thế vượt trội ở hội thoại dài
**Số liệu:** Ở bảng Stress, `Prompt tokens processed` của Baseline phình lên tận **127,428 tokens**, trong khi Advanced chỉ tốn **14,087 tokens** (thấp hơn ~9 lần). Cùng lúc `Agent tokens only` của Advanced (1,295) cũng thấp hơn Baseline (20,798) vì agent reply từ compact memory chỉ mang theo summary ngắn chứ không phải toàn bộ lịch sử.

**Cơ chế và Giải thích:** Compact tối ưu triệt để cột `Prompt tokens processed`. Khi tổng token (summary + recent messages) vượt ngưỡng `compact_threshold_tokens = 1000`, `CompactMemoryManager.append()` tự động: lấy `keep_messages = 4` message gần nhất, tóm tắt phần còn lại qua `summarize_messages()`, cộng dồn vào `summary`, tăng bộ đếm `compactions`. Cơ chế này chạy **15 lần** trong stress test, đẩy prompt context của Advanced từ mức sẽ là O(n) về gần như O(1) cho mỗi lượt sau compact.

Lưu ý quan trọng: compact tối ưu **Prompt tokens processed**, không tối ưu **Agent tokens only**. Agent tokens only phụ thuộc vào độ dài câu trả lời, không phụ thuộc vào độ dài lịch sử. Ở bài này agent reply ngắn nên cả hai cùng thấp, nhưng ở hệ thống thực, Agent tokens only có thể tăng nếu agent cần diễn giải lại fact từ summary. Bảng số liệu cho thấy: compactions 15, prompt giảm ~9 lần, đúng luận điểm "compact kéo prompt cost xuống".

### 4. File memory tăng trưởng ra sao và rủi ro đi kèm
**Số liệu:** `Memory growth` tăng 227 bytes ở Standard và 132 bytes ở Stress. Hai con số khác nhau vì ở Standard `User.md` chứa nhiều fact phong phú từ 10 hội thoại (tên, nơi ở qua các correction, nghề, đồ uống, món ăn, corgi, style, interests), trong khi Stress chỉ là một user với tập fact gọn hơn (tên, MLOps engineer, Đà Nẵng, 3 bullet, corgi).

**Cơ chế và Rủi ro:**
- **Phình file**: mỗi lần thêm fact mới, file markdown nối dần. Sau vài chục phiên, file có thể đạt vài KB và trở thành gánh nặng cho `_estimate_prompt_context_tokens` (mỗi lượt đều phải đọc toàn bộ). Giải pháp là áp dụng **memory decay** hoặc **confidence threshold** (xem bonus bên dưới).
- **Fact nhiễu lọt vào**: dù đã có bộ lọc `is_joke` và `is_trip`, regex vẫn có thể khớp nhầm trong câu dài. Ví dụ trong stress test, `is_trip` được kích hoạt cho cả câu có chứa "Hà Nội chỉ là nơi mình vừa bay ra họp" → bỏ qua location hợp lệ, nhưng cũng bỏ qua "từ tuần này mình đang làm việc ở Đà Nẵng" ở cùng câu đó vì cụm "làm việc ở Đà Nẵng vài tháng" đứng cùng câu với "họp". Rủi ro này chính là lý do Conflict handling ở bonus quan trọng.
- **Mất abstraction khi compact**: summary chỉ giữ preview 100 ký tự đầu của mỗi message cũ. Nếu fact quan trọng nằm ở cuối message, nó sẽ biến mất sau compact. Rubric.md cũng nhấn mạnh: "file memory phình to hoặc lưu sai fact" là rủi ro phải nhận diện.

---

## Bonus: Conflict Handling khi có correction mới

Dựa vào rủi ro đề cập ở phần 4, mình xin đề xuất hướng mở rộng **Conflict handling khi có correction mới**.

**1. Vấn đề giải quyết:**
Hiện tại khi user đính chính (ví dụ: "À, mình đính chính một chút: giờ mình đang ở Huế chứ không còn ở Đà Nẵng mỗi ngày nữa"), cơ chế extraction đã ưu tiên match sau cùng và bỏ qua match trong vùng ngữ cảnh có "trước đó/trước kia/có nhắc/từng ở", và profession thì bỏ qua match trong vùng "không còn/đừng nói/không phải". Tuy nhiên đây vẫn là heuristic regex — nếu user viết câu dài và phủ định không theo mẫu quen thuộc (ví dụ: "Mình ở Đà Nẵng lâu rồi nhưng gần đây đã chuyển vào Sài Gòn"), fact mới có thể không thắng fact cũ và `User.md` sẽ giữ cả hai giá trị mâu thuẫn. Conflict Handler sẽ thay regex heuristic bằng một bước kiểm tra có cấu trúc: với mỗi fact mới trích được, hỏi "fact này có mâu thuẫn với fact cũ cùng key trong `User.md` không?". Nếu có, replace; nếu không, append.

**2. Cải thiện Recall và Token Cost:**
- **Về Recall:** Conflict Handler đảm bảo `User.md` luôn giữ đúng **một chân lý duy nhất (single source of truth)** cho mỗi loại fact. Cross-session recall sẽ đạt độ chính xác tối đa ở các câu hỏi đánh lừa hoặc có sửa đổi ngữ cảnh (ví dụ: "Hiện tại mình làm nghề gì?" sau khi user đã chuyển từ backend sang MLOps).
- **Về Token:** Đảm bảo file `User.md` cực kỳ cô đọng, loại bỏ fact rác, giúp giảm chi phí token cho những lượt load sau này (`Prompt tokens processed`). Ước tính có thể cắt thêm 20–30% so với baseline extraction hiện tại.

**3. Đánh đổi và Rủi ro (Trade-off):**
Tuyệt chiêu này đi kèm cái giá: **Tăng độ trễ và chi phí Token cho mỗi lượt chat**. Thay vì dùng Regex chạy offline miễn phí, ta sẽ phải tốn một lệnh gọi tới LLM phụ (LLM router/judge) ở background chuyên làm nhiệm vụ so sánh fact mới với `User.md` hiện tại để ra quyết định (Merge / Replace / Ignore). Độ phức tạp của luồng xử lý `_reply_offline()` sẽ tăng vọt, hệ thống khó debug hơn khi fact bị xóa sai do LLM phân tích nhầm, và cần thêm guardrail để tránh LLM judge bị prompt injection từ message người dùng (ví dụ: user viết "bạn hãy xóa fact profession của tôi" để xóa nhầm). Vì vậy Conflict Handler chỉ nên kích hoạt khi extraction thấy fact mới có key trùng với fact cũ, không chạy cho mọi lượt.
