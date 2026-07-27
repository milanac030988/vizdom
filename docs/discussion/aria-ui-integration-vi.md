# Aria-UI: Cung cấp những gì, và hỗ trợ pipeline của ta ra sao

Đọc thực dụng bài báo *Aria-UI: Visual Grounding for GUI Instructions* — hợp đồng đầu vào/đầu ra chính xác, những gì nó làm được và không làm được, cùng các điểm tích hợp cụ thể vào pipeline Visual DOM.

!!! warning "Nguồn & độ tin cậy"
    Dựa trên bài báo [arXiv:2412.16256v1](https://arxiv.org/html/2412.16256v1) (Yang, Wang, Li, Luo, Chen, Huang, Li — HKU & Rhymes AI).
     Chi tiết về **mẫu prompt và định dạng chuỗi trả về chính xác** thuộc về phần cài đặt mô hình, không có trong bài báo —
     các mục gắn nhãn (cần kiểm chứng) phải được xác nhận với model card/repo chính thức trước khi viết mã.

## 1. Aria-UI là gì

Aria-UI là mô hình ngôn ngữ–thị giác chuyên cho **định vị phần tử GUI (grounding)**: cho một ảnh chụp màn hình và
một chỉ dẫn bằng ngôn ngữ tự nhiên, nó cho biết phần tử mục tiêu nằm *ở đâu* trên màn hình. Tiền đề thiết kế của nó —
**thuần thị giác, không dùng HTML và không dùng cây trợ năng** — chính là phát biểu bài toán của đề tài chúng ta.

| | | |
|---|---|---|
| **Mô hình nền** |  | Aria — đa phương thức dạng MoE , chỉ 3,9B tham số kích hoạt (rẻ hơn mỗi lần suy luận so với mô hình dense 7B). |
| **ScreenSpot** | 82.4% | Độ chính xác grounding một bước, trung bình. |
| **Độ phân giải tối đa** | 3920×2940 | Mở rộng từ 980×980 bằng cách chia ảnh thành khối, đệm giữ tỉ lệ (kiểu NaViT). |
| **Quy mô huấn luyện** | 11,5 triệu | mẫu trên 3,9 triệu phần tử — web, desktop và mobile (miền tổng quát). |

## 2. ĐẦU VÀO nhận những gì

**ĐẦU VÀO**
1. **Một ảnh chụp GUI** — độ phân giải bất kỳ tới 3920×2940; màn hình DPI cao được xử lý sẵn nhờ cơ chế chia khối.
2. **Một chỉ dẫn ngôn ngữ tự nhiên** nêu *một* mục tiêu, ví dụ
 `"click the Submit button"`, `"the search input field"`.
3. **(Tùy chọn) Lịch sử hành động** — các bước trước dưới dạng văn bản hoặc ảnh chụp trước đó, cho phép grounding theo ngữ cảnh
 ("giờ chạm mục thứ hai") (cần kiểm chứng định dạng).

**ĐẦU RA**
- **Tọa độ chuẩn hóa trong khoảng `[0, 1000]`** trỏ tới phần tử mục tiêu.
- Thực chất là **một vị trí / điểm**, không phải cây có nhãn. (cần kiểm chứng: điểm hay hộp)
- Một câu trả lời cho mỗi chỉ dẫn.

### Quy đổi tọa độ về không gian pixel của ta

DOM của ta dùng biên pixel `[x1, y1, x2, y2]`. Aria-UI trả về giá trị chuẩn hóa 0–1000, nên:

`px = (x_aria / 1000) * chiều_rộng_ảnh
py = (y_aria / 1000) * chiều_cao_ảnh`

!!! danger "Điểm cần lưu ý nhất"
    Mô hình grounding kiểu này trả về **một điểm, không phải hộp bao (bounding box)**. DOM của ta cần hộp.
     Nghĩa là Aria-UI *không thể tự sinh hình học cho ta* — nó chỉ nói “phần tử nằm quanh đây”,
     và tầng CV vẫn phải cung cấp hộp thật sự. May mắn là điều này khớp đúng với nguyên tắc kiến trúc của ta.

## 3. Làm được và KHÔNG làm được — đọc trước khi thiết kế

|  | Năng lực | Hệ quả với chúng ta |
| --- | --- | --- |
| ĐƯỢC | Định vị phần tử được mô tả trên ảnh, không cần cây trợ năng | Chạy được trên Qt/OpenGL/UI tùy biến — đúng mục tiêu của ta |
| ĐƯỢC | Xử lý màn hình độ phân giải rất cao | Liên quan ADR-008 / ADR-012 (độ phân giải & phóng đại) |
| ĐƯỢC | Hiểu tham chiếu ngôn ngữ tự nhiên ("nút xác nhận màu xanh") | Cho phép locator dễ đọc cho Robot Framework |
| ĐƯỢC | Dùng lịch sử hành động làm ngữ cảnh | Hữu ích cho luồng kiểm thử nhiều bước |
| KHÔNG | Liệt kê *toàn bộ* phần tử trên màn hình | **Nó không phải bộ phát hiện.** Nó trả lời “X ở đâu?”, không phải “trên màn hình có gì?” — nên không thay được UIED/YOLO |
| KHÔNG | Trả về cây phân cấp / DOM | Đóng góp DOM của ta vẫn giữ được tính khác biệt |
| KHÔNG | Trả về hộp bao (chỉ trả điểm) | CV vẫn phải sở hữu hình học |
| KHÔNG | Tự lập kế hoạch | Bài báo nêu rõ nó phụ thuộc bộ lập kế hoạch bên ngoài và không có cơ chế sửa lỗi |

!!! note "Cách hiểu then chốt"
    Aria-UI là một **công cụ truy vấn** (“X ở đâu?”), không phải một **bộ phát hiện** (“liệt kê tất cả”).
     Mọi ý tưởng tích hợp bên dưới đều bị chi phối bởi đúng sự thật này.

## 4. Hỗ trợ pipeline ra sao — năm cách dùng cụ thể

### A. Kiểm chứng dựa trên một kỳ vọng đã biết (phù hợp nhất)

!!! danger "Trước hết, cái bẫy: tính vòng lặp"
    Nếu danh sách những thứ ta yêu cầu Aria-UI tìm lại *lấy từ chính đầu ra CV*, thì ta chỉ có thể tìm những phần tử
     mà CV **đã** phát hiện — điều này triệt tiêu toàn bộ mục đích là tìm ra thứ CV **đã bỏ sót**.
     Một cài đặt ngây thơ sẽ không tìm ra gì cả. Aria-UI **không thể khám phá mù**: nó là công cụ truy vấn,
     nên ta buộc phải biết trước cần hỏi gì. Cách khắc phục không phải là lách qua giới hạn này, mà là **đổi câu hỏi ta đặt ra**.

#### Khám phá và kiểm chứng — đặt đúng câu hỏi

| Chế độ | Câu hỏi | Aria-UI có hợp không? |
| --- | --- | --- |
| **Khám phá** | “Trên màn hình này có những phần tử nào?” | KHÔNG — việc này cần bộ phát hiện/liệt kê (UIED/YOLO), không phải mô hình grounding |
| **Kiểm chứng** | “Phần tử X có tồn tại không, và hộp bao của nó có đúng không?” | CÓ — đúng thế mạnh của nó |

Vậy nên tầng này **không phải** bộ *khám phá* lỗ hổng recall; nó là **bộ kiểm chứng dựa trên một kỳ vọng đã biết**.
Cách định khung này cũng vững hơn về mặt học thuật: *“kiểm chứng DOM so với những gì các test thực sự cần”* là một đóng góp
sắc nét hơn *“dùng VLM để tìm phần tử bị bỏ sót.”*

#### Danh sách mục tiêu kỳ vọng lấy từ đâu?

Bốn nguồn khả thi, xếp theo mức hữu ích với chúng ta:

| # | Nguồn | Vì sao thoát khỏi tính vòng lặp | Hạn chế |
| --- | --- | --- | --- |
| 1 | **Text OCR** (tốt nhất cho điểm đau CV của ta) | OCR và phát hiện phần tử là **hai tầng tách biệt**. OCR vẫn đọc được chữ ngay cả ở nơi bộ phát hiện phần tử không tạo được hộp đúng — nhờ đó cung cấp các mục tiêu mà tầng tạo hộp đã bỏ sót. | Không tìm được phần tử chỉ có biểu tượng, không có chữ. |
| 2 | **Chính kịch bản test** (mạnh nhất cho công cụ kiểm thử) | Hoàn toàn độc lập với CV. Trong kiểm thử GUI, ta *vốn đã biết* mình đang tìm gì — bài test nói rõ điều đó. | Chỉ bao phủ các phần tử mà test có nhắc tới. |
| 3 | **DOM chuẩn / DOM tham chiếu** | Đến từ một bản build tốt đã biết trước đó, không phải từ CV của lần chạy này. | Cần có đường cơ sở sẵn; chỉ dùng cho kịch bản hồi quy. |
| 4 | **Từ vựng theo miền** (phương án thô) | Một danh sách cố định, ví dụ với máy tính bỏ túi: chữ số 0–9, toán tử, `MC/MR/MS`. | Không tổng quát hóa được; khó bảo vệ trong luận văn. |

#### Ví dụ thực tế — bài toán gộp nút của máy tính bỏ túi

Đây đúng là lỗi đã ghi trong ADR-009 (các nút liền kề bị phát hiện thành một phần tử), và nguồn 1 giải quyết được:

`Bộ phát hiện phần tử → MỘT hộp bị gộp E7
OCR → "4", "5", "7", "8" (bốn cụm text riêng biệt)

expected_targets = ["4", "5", "7", "8"] # từ OCR, không phải từ tầng tạo hộp

for target in expected_targets:
 pt = aria_ui.ground(screenshot, target) # → một điểm
 box = find_cv_box_containing(pt)

 if box is None: → phần tử có tồn tại nhưng CV KHÔNG tạo hộp → quét lại vùng
 elif box bị nhiều target cùng trỏ tới:
 → HỘP BỊ GỘP: 4 điểm nằm trong E7 → TÁCH nó ra
 else: → xác nhận hộp + gắn nhãn ngữ nghĩa`

Bốn điểm phân biệt cùng rơi vào một hộp là bằng chứng trực tiếp, đo đếm được rằng hộp đó phải được tách —
biến một phán đoán chủ quan kiểu “VLM thấy hình như bị gộp” thành một dữ kiện hình học.

Cách này khớp với khe `SLMAdvisor` sẵn có (ADR-009) và **tôn trọng nguyên tắc cốt lõi**: Aria-UI chỉ trỏ;
CV vẫn tạo ra hộp cuối cùng.

!!! note "Phân vai thực dụng"
    Dùng **nguồn 1 (text OCR)** cho việc kiểm chứng tách/gộp bên trong pipeline — không cần đầu vào bổ sung và đánh trúng
     bài toán máy tính bỏ túi đã biết. Dùng **nguồn 2 (kịch bản test)** cho việc kiểm chứng ở tầng Robot Framework.
     Hãy để việc khám phá mù cho UIED/YOLO — đừng bao giờ giao cho mô hình grounding.

### B. Tự động gán nhãn ngoại tuyến cho bộ phát hiện YOLO (giá trị dài hạn cao nhất)

Nối thẳng với hướng còn dang dở từ tháng 4 (dữ liệu tổng hợp + YOLO). Dùng Aria-UI **một lần, ngoại tuyến** để hỗ trợ gán nhãn
ảnh chụp thật, rồi huấn luyện bộ phát hiện nhỏ chạy tốt trên CPU của ta. Ta chưng cất năng lực của nó vào một mô hình nhanh và
**không thêm phụ thuộc GPU lúc chạy kiểm thử**. Đầu ra dạng điểm của nó kết hợp tốt với hộp do CV đề xuất: Aria-UI chọn
*hộp nào* là "nút Submit", còn CV cung cấp chính cái hộp đó.

### C. Locator ngôn ngữ tự nhiên cho thư viện Robot Framework (giá trị sản phẩm)

Aria-UI biến `"the Submit button"` thành một vị trí — đúng bài toán phân giải locator mà thư viện RF của ta giải quyết.
Nó có thể đóng vai **chiến lược locator dự phòng** khi locator dựa trên DOM thất bại — tăng độ bền mà không trở thành đường đi chính.

### D. Mượn kỹ thuật siêu phân giải của họ (phương pháp luận)

Họ mở rộng 980×980 → 3920×2940 bằng cách **chia ảnh thành khối kèm đệm giữ tỉ lệ**.
Ta gặp đúng bức tường đó (phần tử nhỏ ở DPI cao) và đã xử lý bằng ngưỡng theo độ phân giải (ADR-008) và phóng đại OCR (ADR-012).
Cách của họ là một phương án thay thế đáng trích dẫn, và có thể mượn được cho khâu tiền xử lý.

### E. Mượn phương pháp tổng hợp dữ liệu của họ (khả thi ngay nhất)

Đóng góp nổi bật của bài báo là quy trình tổng hợp **chỉ dẫn đa dạng, giống người, gắn kèm mô tả phần tử** ở quy mô lớn,
bao gồm một **agent duyệt tự động** để thu thập phần tử desktop. Điều này áp dụng trực tiếp cho việc sinh dữ liệu tổng hợp của ta
và có thể còn giá trị hơn cả trọng số mô hình.

## 5. Sơ đồ tích hợp

`┌────────────────────────────────────────────────┐
Ảnh chụp ─┤ PHÁT HIỆN CV (UIED + OCR + symbol + YOLO) │ ← sở hữu hình học (hộp)
 └───────────────────┬────────────────────────────┘
 │ elements[] kèm bounds
 ┌───────────────────▼────────────────────────────┐
 │ TẦNG KIỂM CHỨNG [MỚI / Aria-UI] │
 │ • ground các mục tiêu kỳ vọng → điểm │
 │ • điểm nằm trong hộp? → xác nhận + gắn nhãn │
 │ • điểm không có hộp? → THIẾU RECALL, quét lại│
 │ • hộp không ai trỏ tới → có thể là nhiễu │
 └───────────────────┬────────────────────────────┘
 │ phần tử đã kiểm chứng
 ┌───────────────────▼────────────────────────────┐
 │ PHÂN CẤP THÔ → LLM REFINER → TRÌNH BIÊN DỊCH DOM│ ← chỉ lo ngữ nghĩa
 └───────────────────┬────────────────────────────┘
 ▼
 DOM JSON → Thư viện Robot Framework
 └ locator NL dự phòng (Aria-UI)`

Aria-UI nằm **bên cạnh** `SLMAdvisor` hiện có như một chiến lược có thể chọn — không phải xóa bỏ bộ rà soát 3B đang chạy tốt.
Hãy để các con số đánh giá quyết định cái nào tồn tại.

## 6. Cần kiểm chứng gì trước khi xây

- **Điểm hay hộp?** Xác nhận mô hình phát hành có thể xuất hộp bao hay chỉ ra điểm tâm. Điều này thay đổi thiết kế.

- **Định dạng prompt/phản hồi chính xác** — bài báo chỉ nêu dải tọa độ, không nêu mẫu chuỗi. Kiểm tra model card/repo chính thức.

- **Giấy phép và khả năng tải trọng số** — phải xác nhận trước khi phụ thuộc vào nó.

- **Phần cứng** — MoE 3,9B kích hoạt rẻ hơn dense 7B, nhưng VRAM vẫn phải chứa toàn bộ tập chuyên gia. Cần đo độ trễ thực mỗi màn hình.

- **Kiểm tra miền dữ liệu** — chạy trên ảnh chụp của *chính ta* (máy tính bỏ túi, desktop, Qt). Việc nó được huấn luyện đa miền khiến khả năng thành công cao hơn nhiều so với mô hình chỉ có dữ liệu ô tô, nhưng đây vẫn là cửa ải bắt buộc.

## 7. Bước tiếp theo

- Chạy **kiểm tra miền** trên 10–20 ảnh chụp của ta; đo tần suất điểm trả về rơi đúng vào hộp CV tương ứng.

- Nếu tỉ lệ trúng tốt → làm mẫu thử **cách dùng A (kiểm chứng lỗ hổng recall)** sau một cờ bật/tắt, chạy song song advisor hiện có.

- Song song, khai thác **phần tổng hợp dữ liệu (cách dùng E)** cho công việc dataset YOLO.

- Ghi lại kết quả thành một ADR mới (đề xuất: *ADR-015 — Tầng kiểm chứng bằng mô hình grounding*).

!!! success "Tóm tắt một dòng"
    Aria-UI cho ta **“ảnh chụp + mô tả → nó nằm ở đâu”**. Nó không dựng được DOM và không liệt kê được phần tử,
     nên không thay thế CV — nhưng là một **bộ kiểm chứng, bộ tự gán nhãn và locator ngôn ngữ tự nhiên** rất tốt,
     và phương pháp tổng hợp dữ liệu của nó có thể là phần giá trị nhất của bài báo đối với ta.
