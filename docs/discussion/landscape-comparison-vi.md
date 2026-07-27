# Bối cảnh Hiểu GUI: So sánh năm hệ thống

Visual DOM Generator của ta đứng ở đâu giữa OmniParser, Aria-UI, ELAM-7B và Jedi — và, một cách trung thực, đóng góp của ta giờ nằm ở chỗ nào.

!!! warning "Nguồn & độ tin cậy"
    Tổng hợp từ: kho mã OmniParser (microsoft/omniparser), *Aria-UI* (arXiv:2412.16256v1),
     model card ELAM-7B (sparks-solutions/ELAM-7B), và trang dự án OSWorld-G / Jedi
     (*Scaling Computer-Use Grounding via User Interface Decomposition and Synthesis*).
     Mọi con số đều do chính nhóm tác giả từng hệ thống công bố. Các nhận định về pipeline của ta phản ánh trạng thái hiện tại
     của kho `D:\Project\MasterProject`. Đây là ghi chú hỗ trợ ra quyết định, không phải một nghiên cứu benchmark độc lập.

## 1. Tóm tắt trong 60 giây

!!! note "Ba điều quan trọng nhất"
    1. **OmniParser của Microsoft đã độc lập xây dựng đúng kiến trúc của ta** — phát hiện bằng YOLO + OCR + mô hình mô tả để lấy ngữ nghĩa, xuất ra hộp kèm nhãn. Điều này vừa xác nhận trực giác thiết kế của ta, vừa đe dọa tính mới.
    2. **Không hệ thống nào trong bối cảnh này tạo ra cây phân cấp.** OmniParser xuất *danh sách phẳng*; ba mô hình grounding xuất *một điểm*. Cây DOM vẫn thực sự là của ta.
    3. **Tất cả họ nhắm tới agent; ta nhắm tới kiểm thử.** Tính tất định, tái sử dụng, diễn giải được và kiểm chứng là yêu cầu của ta, không phải của họ. Đây là khác biệt thật và bảo vệ được.

## 2. Năm hệ thống

| | |
|---|---|
| **Visual DOM Generator (của ta)** | CV (UIED + OCR + bộ phát hiện symbol/màn hình, YOLO dự kiến) → phân cấp thô theo luật → LLM refiner (Qwen2.5-3b) → trình biên dịch DOM → thư viện Robot Framework.
    Nguyên tắc: CV sở hữu hình học, LLM sở hữu ngữ nghĩa . Đầu ra: cây DOM JSON kiểu UIAutomator. |
| **OmniParser (Microsoft)** | Ảnh chụp → phần tử có cấu trúc. Phát hiện biểu tượng dựa trên YOLO + OCR tích hợp + mô tả bằng Florence-2 (V2; BLIP2 ở V1.5).
    Đầu ra: hộp bao + nhãn ngữ nghĩa + dự đoán khả năng tương tác . V1.5 bổ sung phát hiện biểu tượng nhỏ, chi tiết hơn. V2 phát hành 02/2025. |
| **Aria-UI (HKU / Rhymes AI)** | Grounding thuần thị giác, tuyên bố rõ không dùng HTML/cây trợ năng. Nền: Aria MoE, 3,9B kích hoạt.
    Đầu vào: ảnh + chỉ dẫn NN tự nhiên (+ lịch sử hành động tùy chọn). Đầu ra: điểm chuẩn hóa [0,1000] .
    11,5 triệu mẫu huấn luyện; siêu phân giải tới 3920×2940. |
| **ELAM-7B (sparks-solutions)** | Nền Molmo-7B-D (xương sống Qwen2-7B). Hai nhiệm vụ: định vị hành động, và đánh giá kết quả kỳ vọng trả về PASSED/FAILED . Huấn luyện trên 17.708 chỉ dẫn / 6.230 ảnh UI ô tô . Apache 2.0. |
| **Jedi / OSWorld-G (nghiên cứu grounding)** | Mô hình Jedi-3B/7B + bộ dữ liệu tổng hợp 4 triệu mẫu, xây bằng cách phân rã UI (biểu tượng, thành phần, tài liệu, slide, bảng tính, bố cục).
    Benchmark OSWorld-G: 564 mẫu, gồm khớp văn bản, nhận dạng phần tử, hiểu bố cục, thao tác tinh vi và khả năng từ chối . |

## 3. Ma trận năng lực — bảng then chốt

| Năng lực | Của ta | OmniParser | Aria-UI | ELAM-7B | Jedi |
| --- | --- | --- | --- | --- | --- |
| **Liệt kê toàn bộ phần tử** (“trên màn hình có gì?”) | CÓ | CÓ | không | không | không |
| **Xuất hộp bao** | CÓ | CÓ | chỉ điểm | chỉ điểm | chỉ điểm |
| **Cây phân cấp / DOM** | CÓ | danh sách phẳng | không | không | không |
| **Định vị từ chỉ dẫn NN tự nhiên** (“X ở đâu?”) | qua truy vấn DOM | không | CÓ | CÓ | CÓ |
| **Nhãn ngữ nghĩa / vai trò** | CÓ | CÓ | ngầm định | ngầm định | ngầm định |
| **Đánh giá pass/fail tích hợp** | qua assertion RF | không | không | CÓ | không |
| **Từ chối tường minh** (“không tồn tại”) | theo luật | n/a | yếu | yếu | có đo lường |
| **Tái sử dụng cho nhiều hành động** | CÓ — phân tích 1 lần | CÓ — phân tích 1 lần | suy luận lại mỗi lần | suy luận lại | suy luận lại |
| **Chạy được không cần GPU** | CÓ (nhánh CPU) | một phần | không | không | không |
| **Đối tượng phục vụ** | **Tự động hóa kiểm thử** | Agent | Agent | Kiểm thử HMI | Agent |

!!! note "Cách đọc bảng này"
    Ở đây có hai họ khác biệt: **bộ phân tích (parser)** (của ta, OmniParser) trả lời *“trên màn hình này có gì?”*,
     và **bộ định vị (grounder)** (Aria-UI, ELAM, Jedi) trả lời *“X ở đâu?”*. Chúng bổ trợ nhau, không thay thế nhau.
     Trong họ parser, hàng duy nhất mà ta đứng một mình là **cây phân cấp**.

## 4. Benchmark — và vì sao không được gộp chung

!!! danger "Đừng đặt các con số này vào cùng một cột"
    Mỗi con số dưới đây đến từ **một benchmark khác nhau với độ khó khác nhau**. So sánh trực tiếp là không hợp lệ
     và sẽ là điểm dễ bị phản biện khi bảo vệ luận văn.

| Hệ thống | Benchmark | Điểm | Ghi chú |
| --- | --- | --- | --- |
| ELAM-7B | AutomotiveUI-Bench-4K | 87,6% grounding / 78,2% đánh giá | Chỉ miền ô tô |
| Aria-UI | ScreenSpot | 82,4% | Grounding một bước; dễ nhất trong nhóm này |
| Jedi-7B | OSWorld-G (564 mẫu) | 54,1% | so với UI-TARS-7B 47,5%; thực tế hơn, khó hơn |
| OmniParser V2 | ScreenSpot Pro | 39,5% | Benchmark cố ý làm khó |
| Aria-UI | OSWorld (agentic) | 15,15% | Tỉ lệ hoàn thành tác vụ đầu-cuối |
| Jedi-7B + GPT-4o / + o3 | OSWorld (agentic) | 27,0% / 50,2% | Lần chạy o3 cải thiện từ đường cơ sở 23% |

!!! success "Phát hiện đáng trích dẫn"
    Trên các benchmark dễ, grounding trông gần như đã giải quyết xong (82–88%), nhưng trên benchmark thực tế nó tụt xuống
     **40–54%**, và tỉ lệ thành công agentic đầu-cuối chỉ nằm giữa **15% và 50%**.
     **Grounding không phải nút thắt cổ chai; việc thực thi đáng tin cậy, có cấu trúc và lặp lại được mới là nút thắt.**
     Chính khoảng cách đó là luận cứ cho một DOM tất định trong bối cảnh *kiểm thử*.

## 5. Phát hiện khó chịu: OmniParser

OmniParser không phải một hệ hình cạnh tranh — nó chính là **hệ hình của ta, do Microsoft Research cài đặt**:

| Giai đoạn | Pipeline của ta | OmniParser |
| --- | --- | --- |
| Hình học phần tử | Phát hiện bằng UIED / YOLO | Phát hiện biểu tượng dựa trên YOLO |
| Văn bản | OCR — EasyOCR / PaddleOCR / Tesseract | OCR tích hợp |
| Ngữ nghĩa | LLM refiner + SLM advisor (không bao giờ sinh tọa độ) | Mô tả bằng Florence-2 → mô tả chức năng |
| Tín hiệu bổ sung | Gán visual\_type / vai trò | Dự đoán khả năng tương tác |
| Đầu ra | **DOM JSON phân cấp** | Danh sách phẳng các hộp đã gắn nhãn |

#### Hai cách đọc, cả hai đều đúng

- (Xác nhận) Một phòng nghiên cứu công nghiệp hội tụ về cùng kiến trúc là bằng chứng bên ngoài mạnh mẽ rằng
 “CV sở hữu hình học, mô hình bổ sung ngữ nghĩa” là cách phân rã đúng. Đây là chỗ dựa có thể trích dẫn cho luận điểm trung tâm.

- (Đe dọa tính mới) Nếu OmniParser đã biến ảnh chụp thành hộp có nhãn, thì **phát hiện phần tử không còn là một đóng góp**.
 Hội đồng sẽ hỏi phần còn lại là gì. Ta nên tự trả lời câu đó ngay bây giờ — chứ không phải lúc bảo vệ.

## 6. Vậy đóng góp của ta giờ nằm ở đâu?

Sau khi loại bỏ mọi thứ mà bối cảnh đã cung cấp sẵn, bốn thứ vẫn thực sự là của ta:

| | |
|---|---|
| **1. Dựng cây phân cấp** | Bao hàm, căn chỉnh, liên kết nhãn và quan hệ cha–con — biến danh sách phần tử phẳng thành một cây truy vấn được. Không hệ thống nào trong so sánh này làm điều đó. Đây là luận điểm còn lại mạnh nhất. |
| **2. Định hướng kiểm thử** | Chiến lược locator, assertion và từ khóa Robot Framework. Mọi hệ thống khác nhắm tới agent , mà yêu cầu của agent
  (tự chủ, hoàn thành tác vụ) khác về bản chất so với yêu cầu của kiểm thử (tất định, lặp lại được, chẩn đoán được). |
| **3. Kinh tế của tái sử dụng** | Một DOM phục vụ nhiều locator và assertion; mô hình grounding phải suy luận lại cho từng chỉ dẫn. Trong bộ hồi quy hàng nghìn bước,
  đây là khác biệt giữa một công cụ khả dụng và một công cụ bất khả thi. |
| **4. Khả năng diễn giải** | Một test thất bại phải chẩn đoán được. Cây kiểm tra được với luật truy vết được giải thích vì sao một phần tử được khớp;
  một tọa độ từ hộp đen thì không. |

!!! note "Đề xuất phát biểu đóng góp trong một câu"
    *“Các hệ thống hiện có hoặc liệt kê phần tử dạng phẳng (OmniParser), hoặc định vị một mục tiêu đơn lẻ từ ngôn ngữ (Aria-UI, ELAM, Jedi).
     Công trình này đóng góp tầng còn thiếu — biên dịch các phần tử đã phát hiện thành một cây DOM phân cấp, tái sử dụng được và diễn giải được — và chứng minh
     rằng chính biểu diễn này, chứ không phải grounding theo từng chỉ dẫn, mới là mức trừu tượng phù hợp cho tự động hóa kiểm thử GUI tất định.”*

## 7. Ba lựa chọn chiến lược

| Lựa chọn | Nghĩa là gì | Ưu điểm | Nhược điểm |
| --- | --- | --- | --- |
| **A. Tiếp tục tự xây CV** (giữ nguyên) | Tiếp tục tự cải thiện UIED/OCR/YOLO. | Toàn quyền kiểm soát; không vướng giấy phép bên ngoài. | Cạnh tranh với Microsoft ở đúng khâu *yếu nhất* của ta; lỗi gộp/tách vẫn tồn tại từ tháng 1. |
| **B. Dùng OmniParser làm tầng phát hiện** (khuyến nghị) | Dùng OmniParser cho hộp + nhãn; tập trung công sức vào phân cấp, biên dịch DOM và thư viện RF. | Giảm rủi ro ở khâu yếu nhất; đứng trên một bộ phát hiện được bảo trì và đo đạc; dời đóng góp về nơi ta thực sự mới.   (cập nhật) bộ phát hiện AGPL của nó *không* thêm nghĩa vụ giấy phép mới — ta vốn đã ở trên AGPL qua Ultralytics (xem §9.2). | Phụ thuộc bên ngoài; câu chuyện “tự làm tất cả” bị giảm. |
| **C. Lai / so sánh** (phương án an toàn) | Giữ CV của ta làm mặc định, thêm OmniParser như một backend chọn được, và so sánh thực nghiệm hai bên. | Tạo ra một chương đánh giá thực chất; tránh bị khóa vào giấy phép; giữ mở cả hai hướng. | Tốn công hơn; phải bảo trì hai nhánh mã. |

**Lưu ý:** cả B và C đều cần cùng một mức trừu tượng — một *backend phát hiện* cắm rút được sau một giao diện phần tử ổn định.
Xây giao diện đó là đáng làm bất kể cuối cùng chọn phương án nào.

## 8. Nên mượn gì từ mỗi hệ thống

| Từ | Lấy gì | Vì sao |
| --- | --- | --- |
| OmniParser | **Dự đoán khả năng tương tác** | Đánh dấu phần tử nào thao tác được rất hữu ích cho locator kiểm thử; hiện ta chưa mô hình hóa điều này một cách tường minh. |
| OmniParser | Chính tầng phát hiện (phương án B) | Loại bỏ điểm yếu recall tồn tại đã lâu. |
| Jedi / OSWorld-G | **“Từ chối” như một thuộc tính được đo** | Trong kiểm thử, một dương tính giả (bấm nhầm phần tử rồi “PASS”) tệ hơn một lần thất bại. Khả năng từ chối phải được đo, không được mặc định. |
| Jedi / OSWorld-G | **Bộ phân loại đánh giá 5 hạng mục** | Khớp văn bản, nhận dạng phần tử, hiểu bố cục, thao tác tinh vi, từ chối — một khung sẵn có cho chương đánh giá của ta. |
| Aria-UI | Chia khối cho siêu phân giải | Xử lý đúng bài toán phần tử nhỏ/DPI cao như ADR-008 và ADR-012. |
| Aria-UI + Jedi | **Phương pháp tổng hợp dữ liệu** | Hai nhóm độc lập cùng xác định tổng hợp dữ liệu là chìa khóa (11,5 triệu và 4 triệu mẫu). Điều này xác nhận hướng dataset tổng hợp/YOLO của ta. |
| ELAM-7B | Đánh giá kết quả kỳ vọng (PASSED/FAILED) | Ánh xạ trực tiếp sang từ khóa assertion của Robot Framework cho các kiểm chứng thị giác mờ. |

## 9. Giấy phép & ràng buộc thực tế

### 9.1 Trạng thái giấy phép đã kiểm chứng (xác nhận 20/07/2026)

| Thành phần | Giấy phép | Kiểm chứng bằng cách nào |
| --- | --- | --- |
| Kho mã OmniParser (`microsoft/OmniParser`) | **CC-BY-4.0** | Tệp `LICENSE` của kho |
| Model card OmniParser-v2.0 (tổng thể) | MIT | Model card trên Hugging Face |
| → `icon_detect` (bộ phát hiện) | **AGPL-3.0** | Văn bản AGPL-3.0 chuẩn của FSF trong `icon_detect/LICENSE` |
| → `icon_caption` | MIT | Model card |
| ELAM-7B | Apache 2.0 | Model card |
| Aria-UI, Jedi | chưa kiểm chứng | — |

Microsoft nói rõ: *“Please note that icon\_detect model is under AGPL license, and icon\_caption is under MIT license.”*
Trọng số `icon_detect` là bản tinh chỉnh của YOLOv8, và Ultralytics phân phối YOLOv8 theo AGPL-3.0 — đó là nơi nghĩa vụ này được kế thừa.

### 9.2 Phát hiện làm thay đổi quyết định

!!! danger "Ta vốn đã ở trên AGPL — độc lập với OmniParser"
    Rà soát kho mã cho thấy đề tài **đã phụ thuộc vào Ultralytics**:
     `pyproject.toml` (`ultralytics>=8.0.0`), `requirements-training.txt`,
     `scripts/training/cv/inference_yolo.py` (`from ultralytics import YOLO`) và
     `models/configs/cv_model_registry.py` (đăng ký `yolov8n/s/m`).

    **Hệ quả:** AGPL *không phải* rủi ro riêng của OmniParser mà ta có thể né bằng cách từ chối OmniParser.
     Quyết định dùng YOLO hồi tháng 4 đã đưa AGPL-3.0 vào đề tài rồi. Dùng bộ phát hiện của OmniParser
     **không tạo thêm lớp giấy phép mới** — vẫn là nghĩa vụ ta đang chịu. Điều này làm suy yếu đáng kể
     lập luận về giấy phép để phản đối phương án B.

### 9.3 AGPL-3.0 yêu cầu gì, theo từng kịch bản

| Kịch bản | Ảnh hưởng |
| --- | --- |
| Nghiên cứu luận văn, chạy cục bộ, không phân phối | Không sao — AGPL không kích hoạt với sử dụng riêng tư |
| Công bố mã nguồn luận văn ra công khai | Sản phẩm kết hợp phải được cấp phép **AGPL-3.0** |
| Phát hành thư viện Robot Framework cho người khác dùng | Phải là **AGPL-3.0** |
| Phục vụ qua mạng (dashboard / API / SaaS) | **Điều khoản mạng §13** — phải cung cấp toàn bộ mã nguồn tương ứng cho người dùng |
| Sản phẩm thương mại, mã nguồn đóng | Cần **giấy phép thương mại Ultralytics** (có phí) |

!!! warning "Lưu ý pháp lý — không phải tư vấn pháp luật"
    Việc *trọng số* đã huấn luyện có thuộc phạm vi AGPL hay không, và việc chạy suy luận có tạo ra tác phẩm phái sinh hay không,
     hiện vẫn chưa ngã ngũ về mặt pháp lý; Ultralytics diễn giải theo hướng rộng. Với bất kỳ mục đích nào vượt ra ngoài nghiên cứu học thuật,
     nên tham vấn nhà trường và (nếu liên quan) đơn vị công tác trước khi dựa vào phân tích này.

### 9.4 Lối thoát sang giấy phép dễ dãi, nếu cần

Nếu thư viện Robot Framework có ý định được tái sử dụng ở nơi làm việc hoặc thương mại, cần lên kế hoạch cho một bộ phát hiện
có giấy phép dễ dãi **ngay từ sớm** — đổi bộ phát hiện muộn sẽ rất tốn kém.

- **RT-DETR** (kho gốc `lyuwenyu/RT-DETR`) — Apache 2.0. Đáng chú ý: chính `cv_model_registry.py` của ta đã liệt kê RT-DETR như lựa chọn thiên về độ chính xác.

- **YOLOX** (Megvii) — Apache 2.0

- **DETR** (Meta) — Apache 2.0

!!! danger "Cái bẫy cần tránh"
    Dùng RT-DETR **thông qua gói `ultralytics` thì vẫn là AGPL**. Giấy phép đi theo
     *bản cài đặt*, không đi theo kiến trúc. Muốn đường đi dễ dãi thì phải dùng kho nguồn gốc.

!!! success "Điều này biện minh cho backend phát hiện cắm rút được — gấp đôi"
    Một giao diện phát hiện cắm rút được giờ phục vụ hai mục đích: cho phép so sánh thực nghiệm CV của ta với OmniParser,
     *và* cho phép thay một bộ phát hiện AGPL bằng một bộ dễ dãi mà không phải viết lại pipeline.
     Điều đó khiến nó là hạng mục kỹ thuật đáng làm nhất tiếp theo, bất kể chọn phương án chiến lược nào.

### 9.5 Các ràng buộc thực tế khác

- **Phần cứng:** cả ba mô hình grounding đều cần GPU; nhánh CPU của ta là điểm khác biệt thực sự cho các máy chạy kiểm thử và thiết bị nhúng.

- **Khả năng tái lập:** mọi con số ở đây đều do tác giả tự báo cáo. Bất kỳ số nào ta trích dẫn như sự thật đều nên được tái lập trên ảnh chụp của chính ta trước.

- **Miền dữ liệu:** ELAM chỉ có dữ liệu ô tô; các hệ thống khác tổng quát. Phải kiểm soát yếu tố miền trong mọi so sánh ta thực hiện.

## 10. Khuyến nghị & bước tiếp theo

!!! success "Lộ trình khuyến nghị"
    Theo **phương án C trước mắt, chuyển sang B nếu giấy phép cho phép**: xây một backend phát hiện cắm rút được, chạy song song CV của ta và OmniParser,
     và dời trọng tâm luận văn về **dựng cây phân cấp + biên dịch DOM + tích hợp Robot Framework**,
     nơi bối cảnh hiện tại còn để lại khoảng trống thực sự.

- ~~Giải quyết câu hỏi AGPL cho bộ phát hiện của OmniParser.~~ (đã xong — xem §9)
 Đã xác nhận là AGPL-3.0, nhưng ta **vốn đã** chịu đúng nghĩa vụ đó qua Ultralytics, nên nó không còn chặn phương án B.
 Quyết định còn lại là một quyết định *đề tài*: thư viện RF có bao giờ nhằm tái sử dụng ở nơi làm việc hay thương mại không? Nếu có, hãy lên kế hoạch cho bộ phát hiện dễ dãi ngay (§9.4).

- **Định nghĩa giao diện backend phát hiện** (`detect(image) → elements[]`) để CV của ta, OmniParser và bất kỳ bộ phát hiện dễ dãi nào đều thay thế được cho nhau — giờ được biện minh bởi cả nhu cầu so sánh lẫn tính linh hoạt về giấy phép.

- **Chạy so sánh cùng điều kiện** trên ảnh chụp của ta (máy tính bỏ túi, desktop, Qt): recall, lỗi gộp/tách, độ trễ, CPU và GPU.

- **Áp dụng bộ phân loại OSWorld-G** cho chương đánh giá, bổ sung thêm *độ đúng của cây phân cấp* — chiều mà không benchmark nào ở đây đo, và cũng là nơi chỉ ta mới cạnh tranh được.

- **Viết đoạn văn phát biểu đóng góp** (mục 6) và mang đi trao đổi với GVHD trước khi cài đặt thêm.

- **Ghi lại quyết định** thành một ADR (đề xuất: *ADR-015 — Chiến lược backend phát hiện và định vị đề tài*).

!!! note "Suy nghĩ khép lại"
    Bối cảnh này không phủ định đề tài — nó **làm rõ** đề tài. Phát hiện phần tử giờ đã là một tầng được giải quyết và
     phổ thông hóa, và tiếp tục cạnh tranh ở đó là chiến lược yếu nhất. Những bài toán chưa được giải là
     **cấu trúc, tái sử dụng, khả năng diễn giải và thất bại đáng tin cậy** — tất cả đều quan trọng nhất trong kiểm thử, đúng
     lĩnh vực mà đề tài này vốn đã nhắm tới.
