# ELAM-7B và Pipeline Visual DOM

Phân tích một mô hình VLM chuyên cho kiểm thử GUI và ý nghĩa của nó đối với kiến trúc "CV trước, sinh DOM".

!!! warning "Nguồn & độ tin cậy"
    Thông tin về ELAM-7B được lấy từ model card trên Hugging Face
     (`sparks-solutions/ELAM-7B`). Các con số benchmark là do chính nhóm tác giả công bố, đo trên
     miền giao diện *ô tô (automotive)*. Các nhận định về pipeline Visual DOM phản ánh trạng thái hiện tại
     của kho mã `D:\Project\MasterProject`. Hãy xem đây là ghi chú hỗ trợ ra quyết định, không phải một
     nghiên cứu benchmark đã được kiểm chứng.

## 1. ELAM-7B là gì

**ELAM (Evaluative Large Action Model)** là một mô hình ngôn ngữ–thị giác (VLM) được tinh chỉnh
cho tự động hóa kiểm thử GUI. Thay vì mô tả màn hình, nó *hành động* trên màn hình: cho một ảnh chụp
và một chỉ dẫn bằng tiếng Anh, nó trả về vị trí cần chạm và liệu kết quả kỳ vọng có đúng hay không.

| | | |
|---|---|---|
| **Mô hình nền** |  | Molmo-7B-D (AllenAI), xây trên xương sống Qwen2-7B. Molmo được chọn nhờ khả năng chỉ điểm / định vị (grounding) gốc. |
| **Nhiệm vụ 1 — Định vị hành động** | 87.6% | Ảnh + chỉ dẫn → tọa độ chạm của phần tử mục tiêu. |
| **Nhiệm vụ 2 — Đánh giá kết quả** | 78.2% | Kiểm tra trạng thái UI, trả về PASSED / FAILED + tọa độ phần tử. |
| **Giấy phép** | Apache 2.0 | Dùng được cho thương mại. Cần transformers ≥ 4.48.2, bf16, trust_remote_code=True . |

- **Đầu vào / đầu ra:** ảnh chụp UI + văn bản tiếng Anh → tọa độ `[x, y]` đã chuẩn hóa (0–1) kèm văn bản giải thích.

- **Dữ liệu huấn luyện:** 17.708 chỉ dẫn trên 6.230 ảnh UI **ô tô** (chữ tiếng Đức & tiếng Anh; prompt tiếng Anh).

- **Benchmark:** AutomotiveUI-Bench-4K — Định vị hành động 87,6%; Định vị kết quả kỳ vọng 77,5%; Đánh giá kết quả kỳ vọng 78,2%.

## 2. Pipeline của chúng ta tóm gọn

Visual DOM Generator chuyển một ảnh chụp màn hình thành **cây DOM JSON** kiểu Android UIAutomator,
để một thư viện Robot Framework có thể định vị và tương tác với phần tử — ngay cả khi không có cây trợ năng (accessibility tree).

- **Nguyên tắc thiết kế:** *CV lo hình học, LLM lo ngữ nghĩa*. LLM bị cấm tuyệt đối việc tự "bịa" ra tọa độ.

- **Phân cấp 3 tầng:** bộ dựng thô dựa trên luật → tinh chỉnh bằng LLM → trình biên dịch DOM.

- **Ngăn xếp phát hiện:** UIED + OCR (EasyOCR / PaddleOCR / Tesseract, hai engine + phóng đại), cùng các bộ phát hiện biểu tượng / màn hình mới và một SLM advisor.

- **Đầu ra:** một cây phân cấp tái sử dụng được và có thể kiểm tra — không phải chỉ một điểm chạm.

- **Hướng còn dang dở (04/2026):** thêm **YOLO** như một bộ phát hiện tùy chọn, và xem xét liệu các mẫu hình agentic có hữu ích không.

## 3. Mâu thuẫn cốt lõi: hai lựa chọn trái ngược

!!! note "Ý chính cần nhớ"
    ELAM và pipeline của chúng ta đưa ra **hai lựa chọn kiến trúc trái ngược về việc "ai sở hữu hình học".**
     ELAM để mô hình nơ-ron trực tiếp sinh tọa độ (grounding đầu-cuối). Chúng ta cố ý giữ tọa độ ở tầng CV
     tất định và chỉ cho LLM chạm vào *ý nghĩa*. Chính khác biệt duy nhất này chi phối mọi đánh đổi bên dưới.

Điều đó khiến ELAM không hẳn là một "mảnh ghép cắm vào" mà giống một **hệ hình (paradigm) cạnh tranh** hơn —
và đó chính là điểm khiến nó có giá trị cho luận văn của bạn: nó cho bạn một đối thủ cụ thể, đã công bố, để định vị đóng góp của mình.

## 4. So sánh trực diện

| Tiêu chí | Pipeline Visual DOM (của ta) | ELAM-7B |
| --- | --- | --- |
| Ai sinh ra tọa độ | CV tất định (UIED/OCR/YOLO) | Chính VLM (grounding) |
| Đầu ra chính | Cây phân cấp DOM đầy đủ (JSON) | Một điểm chạm / phán quyết pass-fail |
| Khả năng tái sử dụng | Một DOM phục vụ nhiều hành động & kiểm chứng | Suy luận lại cho từng chỉ dẫn |
| Khả năng diễn giải | Cao — cây kiểm tra được, luật truy vết được | Thấp hơn — hộp đen đầu-cuối + lời giải thích |
| Tài nguyên tính toán | Chạy được trên CPU; LLM tùy chọn/nhỏ | VLM 7B, gần như bắt buộc GPU + bf16 |
| Bằng chứng theo miền | UI tổng quát/tùy biến (Qt, OpenGL, máy tính…) | Mạnh ở UI *ô tô*; miền tổng quát chưa chứng minh |
| Đánh giá tích hợp sẵn | Qua các từ khóa assertion của RF | Sẵn "Đánh giá kết quả kỳ vọng" (PASSED/FAILED) |
| Độ chín của số liệu | Nội bộ, đang thực hiện | Benchmark đã công bố (tác giả tự báo cáo) |
| Giấy phép | Mã nguồn của ta | Apache 2.0 (dùng lại được) |

## 5. Bốn cách ELAM có thể được tận dụng

### A. Làm đường cơ sở (baseline) để so sánh (khuyến nghị)

Cách dùng gọn gàng và ít rủi ro nhất. ELAM cho bạn một đối thủ đã công bố, giấy phép Apache, có benchmark công khai.
So sánh pipeline DOM với nó — về độ chính xác, chi phí tính toán, khả năng tái sử dụng và diễn giải — tạo nên một chương
"nghiên cứu liên quan" và "đánh giá" mạnh, đồng thời làm sắc nét lập luận *vì sao* biểu diễn trung gian dạng DOM là xứng đáng.

### B. Làm tầng đánh giá / kiểm chứng (nhiều hứa hẹn)

Nhiệm vụ "Đánh giá kết quả kỳ vọng" của ELAM (`PASSED`/`FAILED` + tọa độ) ánh xạ gần như trực tiếp
sang các từ khóa assertion trong Robot Framework của bạn. Bạn có thể giữ DOM dựa trên CV để định vị và hành động, đồng thời
mượn kiểu kiểm chứng của VLM cho những assertion thị giác khó diễn đạt ("banner cảnh báo có hiển thị không?").

### C. Làm SLM advisor / bộ tinh chỉnh (khả thi)

Bạn đã có tầng SLM-advisor (ADR-009) rà soát đầu ra CV. Một VLM có khả năng grounding có thể đối chiếu chéo hoặc sửa DOM —
nhưng lưu ý điểm ma sát triết lý: nếu nó bắt đầu sinh tọa độ, nó vượt qua lằn ranh "mô hình không được sinh tọa độ" của bạn.
Dùng được, nhưng phải giới hạn ở việc *rà soát*, không phải *tạo ra* hình học.

### D. Làm tín hiệu để xem lại kiến trúc (rủi ro cao)

Nếu một VLM 7B đạt grounding ~88% theo kiểu đầu-cuối, ta buộc phải tự hỏi liệu ngăn xếp CV-trước dạng module có còn hợp lý.
Câu trả lời trung thực cho luận văn là một chữ *"có, với điều kiện"* bảo vệ được: khả năng tái sử dụng DOM, thân thiện CPU,
diễn giải được, không cần suy luận GPU cho từng hành động, và tạo ra cây đầy đủ (không chỉ một điểm). Hãy nêu lập luận này một cách
rõ ràng thay vì mặc định.

## 6. Rủi ro & hạn chế

!!! danger "Khoảng cách miền dữ liệu"
    ELAM được huấn luyện và đo trên UI **ô tô**. Con số 87,6% *không* đảm bảo chuyển giao được sang
     máy tính bỏ túi, ứng dụng desktop, hay bề mặt Qt/OpenGL. Mọi so sánh phải kiểm soát yếu tố miền, nếu không sẽ bất công cho cả hai phía.

- **Chi phí tính toán:** VLM 7B cần GPU hỗ trợ bf16; nhánh CV của bạn chạy được trên CPU. Điều này quan trọng với một công cụ kiểm thử "chạy được ở mọi nơi".

- **Không có phân cấp:** ELAM trả về điểm/phán quyết, không phải cây có cấu trúc — bạn mất đi DOM tái sử dụng vốn là nền tảng cho thư viện RF.

- **Chỉ prompt tiếng Anh;** đầu ra tọa độ chuẩn hóa 0–1, cần ánh xạ ngược về pixel.

- **Khả năng tái lập:** số liệu benchmark là do tác giả tự báo cáo; cần tái lập độc lập trên ảnh của chính bạn trước khi trích dẫn như sự thật.

## 7. Khuyến nghị

!!! success "Quan điểm đề xuất"
    Áp dụng ELAM-7B như một đường cơ sở và một module đánh giá tùy chọn, không phải để thay thế pipeline DOM.

    Nó củng cố luận văn theo hai cách cùng lúc: (1) một đối thủ đã công bố, đáng tin, giúp hợp thức hóa bài toán của bạn;
     và (2) một năng lực kiểm chứng thị giác có sẵn để gắn vào phía Robot Framework. Hãy giữ DOM CV-trước làm đóng góp cốt lõi;
     dùng ELAM để xác định và bảo vệ ranh giới của nó.

## 8. Câu hỏi mở & bước tiếp theo

- **Quyết định phạm vi:** ELAM là baseline so sánh, module tích hợp, hay cả hai? (Khuyến nghị: cả hai, theo thứ tự đó.)

- **Benchmark công bằng:** Có thể chạy ELAM trên một tập nhỏ ảnh chụp của *chính ta* (máy tính bỏ túi, desktop, Qt) và đo độ chính xác grounding so với đầu ra CV+DOM không?

- **Phần cứng:** Ta có GPU đủ VRAM + bf16 để chạy suy luận 7B ở tốc độ dùng được không?

- **Điểm tích hợp:** Nếu áp dụng nhiệm vụ đánh giá, nó nằm ở đâu — bên trong các từ khóa assertion của RF, hay là một bước kiểm tra sau DOM?

- **Định hình luận văn:** Viết một đoạn văn súc tích: "Vì sao biểu diễn trung gian dạng DOM vượt trội hơn grounding VLM trực tiếp cho *trường hợp của ta*." Đây là hạt nhân học thuật.
