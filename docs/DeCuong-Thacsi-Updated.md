# ĐẠI HỌC QUỐC GIA TP.HCM
# TRƯỜNG ĐẠI HỌC KHOA HỌC TỰ NHIÊN

---

**Nguyễn Huỳnh Trí Cương**

**Mã số học viên: 23C11001**

---

# ĐỀ CƯƠNG NGHIÊN CỨU ĐỀ TÀI LUẬN VĂN THẠC SĨ

**Tên đề tài:** Xây dựng Visual DOM từ ảnh chụp màn hình ứng dụng kỹ thuật thị giác máy tính và mô hình ngôn ngữ nhỏ phục vụ kiểm thử giao diện tự động

**Ngành:** Khoa học máy tính

**Mã số ngành:**

---

**Xác nhận của giảng viên hướng dẫn**

(Ký tên và ghi rõ họ tên)

Họ tên: …………………………

---

**TP. HCM, tháng 04 năm 2025**

---

## Mục lục

1. [Giới thiệu tổng quan](#1-giới-thiệu-tổng-quan)
2. [Mục đích nghiên cứu của luận văn](#2-mục-đích-nghiên-cứu-của-luận-văn)
3. [Đối tượng nghiên cứu](#3-đối-tượng-nghiên-cứu)
4. [Các phương pháp nghiên cứu](#4-các-phương-pháp-nghiên-cứu)
5. [Nội dung và phạm vi nghiên cứu](#5-nội-dung-và-phạm-vi-nghiên-cứu)
6. [Nơi thực hiện đề tài](#6-nơi-thực-hiện-đề-tài)
7. [Thời gian thực hiện](#7-thời-gian-thực-hiện)
8. [Tài liệu tham khảo](#8-tài-liệu-tham-khảo)

---

## 1. Giới thiệu tổng quan

Kiểm thử giao diện người dùng (GUI Testing) là một phần quan trọng trong quy trình kiểm thử phần mềm. Các công cụ phổ biến hiện nay như Selenium, Appium, hay UIAutomator sử dụng hướng tiếp cận **object-based**, tức là thao tác với các thành phần giao diện thông qua thuộc tính nội tại (ID, class, structure) được expose bởi hệ thống hoặc framework.

Tuy nhiên, **object-based** gặp nhiều hạn chế khi áp dụng trong các môi trường thực tế:

### 1.1. Hạn chế trên Windows/Linux Desktop

Trên Windows hoặc Linux, việc truy xuất thông tin từ UI component thường đòi hỏi hệ thống hỗ trợ accessibility API (như Windows UIAutomation).

Trong các trường hợp không có hỗ trợ sẵn, một phương pháp thường dùng là phát triển một dynamic library (.dll trên Windows hoặc .so trên Linux), gọi là **agent**, rồi inject agent này vào process của AUT (Application Under Test). Agent sẽ chạy trong cùng không gian tiến trình với AUT, cho phép truy cập trực tiếp vào memory space hoặc UI component hierarchy để thu thập thông tin.

Cách tiếp cận này tiềm ẩn nhiều rủi ro:
- Gây ảnh hưởng đến các luồng (thread) đang chạy của AUT, có thể làm sai lệch hành vi so với môi trường chạy thực tế.
- Tăng nguy cơ xảy ra lỗi về đồng bộ, race condition hoặc crash nếu không được kiểm soát tốt.
- Việc duy trì và phát triển agent phù hợp với nhiều loại AUT cho các platform và framework khác nhau là phức tạp và tốn công sức.

### 1.2. Hạn chế trên Linux Desktop Apps

Trên Linux desktop apps, việc automation phụ thuộc mạnh vào từng UI toolkit (GTK, Qt…), không có một chuẩn chung tương đương như trên Windows.

### 1.3. Hạn chế trên Android

Trên Android, framework như UIAutomator hoạt động hiệu quả với các app dùng View tiêu chuẩn. Nhưng với các ứng dụng native Android phát triển bằng Qt, C++, CGI… hoặc render giao diện bằng OpenGL, các thành phần UI không thể được truy cập bởi UIAutomator vì không tồn tại accessibility tree hoặc DOM structure — hoàn toàn không thể kiểm thử theo hướng object-based.

### 1.4. Hướng tiếp cận Image-based

Vì những hạn chế này, hướng tiếp cận **image-based GUI testing** đang ngày càng được quan tâm. Phương pháp này sử dụng kỹ thuật Computer Vision để nhận diện, xác định vị trí và tương tác với các thành phần giao diện giống như cách con người nhìn vào và thao tác, mà không cần truy xuất nội tại vào ứng dụng.

### 1.5. Đề xuất mới: Visual DOM

Các công trình như UIED (ESEC/FSE 2020) và nghiên cứu của Chen et al. (arXiv:2008.05132) đã cho thấy khả năng kết hợp giữa kỹ thuật thị giác máy tính truyền thống và học sâu trong việc phát hiện thành phần UI từ ảnh giao diện.

**Luận văn này đề xuất một hướng tiếp cận mới: xây dựng Visual DOM** — một cấu trúc dữ liệu dạng cây (tree structure) mô tả các thành phần giao diện được trích xuất hoàn toàn từ ảnh chụp màn hình, tương tự như DOM (Document Object Model) trong web development. Visual DOM kết hợp:

1. **Computer Vision Pipeline**: Sử dụng các kỹ thuật xử lý ảnh truyền thống (edge detection, contour analysis) để phát hiện vùng UI.

2. **OCR Integration**: Tích hợp nhận dạng ký tự quang học (EasyOCR) để trích xuất nội dung văn bản từ các thành phần giao diện.

3. **Small Language Model (SLM) Refinement**: Sử dụng mô hình ngôn ngữ nhỏ (như Qwen2.5-3B) để tinh chỉnh phân loại ngữ nghĩa và xây dựng cấu trúc phân cấp của các thành phần UI.

Đây là hướng đi tiềm năng cho các hệ thống không hỗ trợ accessibility, ứng dụng embedded, hoặc multi-platform.

---

## 2. Mục đích nghiên cứu của luận văn

### 2.1. Tính cấp thiết

Việc xây dựng hệ thống kiểm thử giao diện không phụ thuộc nền tảng đang là một yêu cầu ngày càng phổ biến, đặc biệt trong các hệ thống nhúng (embedded), automotive, mobile native. Hướng image-based có tiềm năng giải quyết bài toán này, nhưng các giải pháp hiện tại thường:
- Chỉ hỗ trợ template matching đơn giản
- Không cung cấp thông tin ngữ nghĩa về các thành phần UI
- Khó khăn trong việc xây dựng test case có tính tái sử dụng cao

### 2.2. Mục tiêu lý thuyết

- Nghiên cứu các thuật toán Computer Vision phù hợp cho việc nhận diện và phân loại các thành phần giao diện người dùng (UI components).
- Nghiên cứu khả năng ứng dụng Small Language Model (SLM) trong việc hiểu ngữ nghĩa và phân loại thành phần UI.
- Đề xuất khái niệm **Visual DOM** — cấu trúc dữ liệu mô tả giao diện được trích xuất từ hình ảnh.

### 2.3. Mục tiêu thực nghiệm

- **Xây dựng Visual DOM Generator**: Pipeline chuyển đổi ảnh chụp màn hình thành cấu trúc DOM dạng JSON, bao gồm thông tin về loại, vị trí, và nội dung của từng thành phần UI.
- **Xây dựng Robot Framework Library**: Thư viện mở rộng cho Robot Framework hỗ trợ kiểm thử giao diện dựa trên Visual DOM.
- **Đánh giá thực nghiệm**: Thử nghiệm trên nhiều nền tảng khác nhau (Windows, Linux, Android) để đánh giá tính hiệu quả và khả năng ứng dụng thực tiễn.

---

## 3. Đối tượng nghiên cứu

### 3.1. Phương pháp kiểm thử giao diện

- Các phương pháp kiểm thử giao diện người dùng (GUI Testing) theo hướng object-based và image-based.
- Hạn chế của phương pháp object-based trong việc kiểm thử:
  - Ứng dụng desktop (.NET, Java) cần automation interface như Windows Automation hoặc phải inject code.
  - Ứng dụng Linux tùy thuộc vào UI toolkit (GTK, Qt).
  - Ứng dụng Android dùng UIAutomator không tương thích với giao diện vẽ bằng Qt/C++/OpenGL.

### 3.2. Kỹ thuật Computer Vision cho GUI

- Các phương pháp phát hiện vùng (region detection): edge detection, contour analysis, morphological operations.
- Các phương pháp phân đoạn ảnh (image segmentation) áp dụng cho giao diện.
- Kỹ thuật nhận dạng văn bản (OCR) trong ngữ cảnh giao diện người dùng.

### 3.3. Mô hình ngôn ngữ cho GUI Understanding

- Small Language Models (SLM) và khả năng ứng dụng trong phân loại UI.
- Vision-Language Models (VLM) và khả năng phát hiện thành phần giao diện.
- Prompt engineering cho bài toán GUI element classification.

### 3.4. Sản phẩm đầu ra

- Khái niệm và cấu trúc Visual DOM.
- Thư viện mở rộng cho Robot Framework hỗ trợ kiểm thử GUI đa nền tảng.

---

## 4. Các phương pháp nghiên cứu

### 4.1. Nghiên cứu lý thuyết

Tổng hợp các hướng tiếp cận image-based hiện có, bao gồm:
- Các công cụ hỗ trợ: OpenCV, EasyOCR, Tesseract
- Các phương pháp: Template Matching, Feature Detection, Deep Learning-based Detection
- Các mô hình ngôn ngữ nhỏ: Qwen2.5, Llama, Phi

### 4.2. Thực nghiệm kỹ thuật

#### 4.2.1. CV Evidence Extraction Pipeline

Xây dựng pipeline trích xuất thông tin từ ảnh sử dụng các kỹ thuật:

**Kỹ thuật Computer Vision truyền thống:**
- **Edge Detection**: Sử dụng Canny edge detector để phát hiện cạnh của các thành phần UI.
- **Contour Analysis**: Phân tích đường viền để xác định vùng bao (bounding box) của các element.
- **Morphological Operations**: Áp dụng erosion, dilation để xử lý nhiễu và tách vùng chồng lấn.
- **Color-based Segmentation**: Phân tích màu sắc để phân loại thành phần (button, input field, text).

**Kỹ thuật nhận dạng văn bản (OCR):**
- **EasyOCR**: Sử dụng cho nhận dạng text đa ngôn ngữ với độ chính xác cao.
- **Text Region Detection**: Phát hiện và nhóm các vùng chứa văn bản.
- **Text-to-Element Association**: Liên kết văn bản với thành phần UI tương ứng.

#### 4.2.2. Coarse Hierarchy Builder

Xây dựng cấu trúc phân cấp thô (coarse hierarchy) dựa trên quy tắc:
- **Spatial Analysis**: Phân tích vị trí tương đối giữa các element.
- **Containment Detection**: Xác định quan hệ cha-con dựa trên bounding box.
- **Grouping Rules**: Nhóm các element có liên quan theo logic giao diện.

#### 4.2.3. LLM Hierarchy Refinement

Sử dụng Small Language Model để tinh chỉnh phân loại:
- **Element Type Classification**: Phân loại chính xác loại element (button, input, label, icon...).
- **Semantic Understanding**: Hiểu ngữ nghĩa của element dựa trên context và nội dung text.
- **Hierarchy Optimization**: Tối ưu cấu trúc cây phân cấp dựa trên logic UI.

**Mô hình sử dụng:**
- Qwen2.5-3B (chạy local qua Ollama)
- JSON mode để đảm bảo output có cấu trúc

#### 4.2.4. Nghiên cứu Vision-Language Models

Đánh giá khả năng của các VLM trong việc phát hiện UI element:
- **Florence-2** (Microsoft): Đánh giá khả năng OCR và object detection.
- **Qwen2-VL**: Đánh giá khả năng hiểu và mô tả giao diện.
- So sánh với phương pháp CV truyền thống.

### 4.3. Đánh giá và kiểm chứng

- Đo độ chính xác phát hiện element (precision, recall).
- Đo độ chính xác phân loại element type.
- Đo hiệu năng (thời gian xử lý) trên các cấu hình phần cứng khác nhau.
- Thử nghiệm trên các hệ thống thực tế: Windows Calculator, Android apps, Linux desktop apps.

### 4.4. Công cụ sử dụng

- **Ngôn ngữ lập trình**: Python 3.9+
- **Computer Vision**: OpenCV, NumPy, Pillow
- **OCR**: EasyOCR
- **LLM Runtime**: Ollama (local inference)
- **LLM Models**: Qwen2.5-3B-Instruct
- **VLM Models**: Florence-2, Qwen2-VL (nghiên cứu)
- **Testing Framework**: Robot Framework
- **Môi trường thử nghiệm**: Windows 10/11, Linux (Ubuntu), Android Emulator

---

## 5. Nội dung và phạm vi nghiên cứu

### 5.1. Nội dung chính

#### 5.1.1. Xây dựng Visual DOM Generator

**Mục tiêu**: Chuyển đổi ảnh chụp màn hình thành cấu trúc DOM dạng JSON.

**Kiến trúc hệ thống:**

```
                    ┌─────────────────────────┐
                    │    Ảnh chụp màn hình    │
                    │      (Screenshot)       │
                    └────────────┬────────────┘
                                 │
            ┌────────────────────┴────────────────────┐
            │                                         │
            ▼                                         ▼
┌───────────────────────────┐         ┌───────────────────────────┐
│  TRÍCH XUẤT ĐẶC TRƯNG CV  │         │  NHẬN DẠNG VĂN BẢN (OCR)  │
│  ───────────────────────  │         │  ───────────────────────  │
│  • Phát hiện cạnh (Canny) │         │  • EasyOCR Engine         │
│  • Phân tích đường viền   │         │  • Trích xuất tọa độ text │
│  • Xử lý hình thái học    │         │  • Hỗ trợ đa ngôn ngữ     │
└─────────────┬─────────────┘         └─────────────┬─────────────┘
              │                                     │
              └──────────────┬──────────────────────┘
                             │
                             ▼
              ┌─────────────────────────────────┐
              │    XÂY DỰNG CẤU TRÚC THÔ       │
              │   ─────────────────────────    │
              │  • Phân tích không gian        │
              │  • Phát hiện quan hệ chứa đựng │
              │  • Phân loại theo quy tắc      │
              └───────────────┬─────────────────┘
                              │
                              ▼
              ┌─────────────────────────────────┐
              │     TINH CHỈNH BẰNG LLM        │
              │   ─────────────────────────    │
              │  • Mô hình: Qwen2.5-3B         │
              │  • Runtime: Ollama (cục bộ)    │
              │  • Phân loại ngữ nghĩa         │
              │  • Tối ưu cấu trúc cây         │
              └───────────────┬─────────────────┘
                              │
                              ▼
              ┌─────────────────────────────────┐
              │          VISUAL DOM            │
              │         (JSON Output)          │
              └───────────────┬─────────────────┘
                              │
                              ▼
              ┌─────────────────────────────────┐
              │   THƯ VIỆN ROBOT FRAMEWORK     │
              │  • Click Element By Text        │
              │  • Input Text To Field          │
              │  • Verify Element Exists        │
              └─────────────────────────────────┘
```

**Bảng tóm tắt các giai đoạn xử lý:**

| Giai đoạn | Tên | Công nghệ / Thuật toán |
|:---------:|-----|------------------------|
| 1 | Trích xuất đặc trưng CV | OpenCV: Canny, Contour, Morphology |
| 2 | Nhận dạng văn bản | EasyOCR (đa ngôn ngữ) |
| 3 | Xây dựng cấu trúc thô | Rules-based, Spatial Analysis |
| 4 | Tinh chỉnh LLM | Qwen2.5-3B qua Ollama (JSON mode) |
| 5 | Biên dịch DOM | Tree Builder, JSON Exporter |

**Cấu trúc Visual DOM JSON:**

```json
{
  "screen": {
    "width": 1920,
    "height": 1080,
    "title": "Application Name"
  },
  "elements": [
    {
      "id": "elem_001",
      "type": "button",
      "bbox": [100, 200, 200, 250],
      "text": "Submit",
      "confidence": 0.95,
      "children": []
    },
    {
      "id": "elem_002",
      "type": "input_field",
      "bbox": [100, 100, 300, 140],
      "text": "",
      "placeholder": "Enter name",
      "children": []
    }
  ]
}
```

#### 5.1.2. Xây dựng Robot Framework Library

**Mục tiêu**: Cung cấp các keywords để thao tác với giao diện dựa trên Visual DOM.

**Các keywords chính:**

| Keyword | Mô tả |
|---------|-------|
| `Capture And Analyze Screen` | Chụp màn hình và tạo Visual DOM |
| `Click Element By Text` | Click vào element có text chỉ định |
| `Click Element By Type` | Click vào element theo loại (button, input...) |
| `Input Text To Field` | Nhập text vào input field |
| `Verify Element Exists` | Kiểm tra element tồn tại |
| `Get Element Location` | Lấy vị trí của element |
| `Wait For Element` | Chờ element xuất hiện |

**Ví dụ sử dụng:**

```robotframework
*** Settings ***
Library    VisualLibrary

*** Test Cases ***
Test Calculator Addition
    Capture And Analyze Screen
    Click Element By Text    7
    Click Element By Text    +
    Click Element By Text    3
    Click Element By Text    =
    Verify Element Contains Text    10
```

#### 5.1.3. Đánh giá và so sánh

- So sánh độ chính xác với phương pháp object-based truyền thống
- Đánh giá trên nhiều loại ứng dụng:
  - Windows desktop applications
  - Linux desktop applications (GTK, Qt)
  - Android applications (standard và OpenGL-based)
  - Embedded systems với custom UI

### 5.2. Phạm vi nghiên cứu

**Trong phạm vi:**
- Tập trung vào thao tác kiểm thử cơ bản: click, input text, verify existence
- Hỗ trợ các loại element phổ biến: button, input field, text label, checkbox, dropdown, icon
- Giao diện tĩnh và semi-dynamic (có animation đơn giản)

**Ngoài phạm vi:**
- Không đi sâu vào kiểm thử hiệu năng (performance testing)
- Không xử lý các giao diện 3D hoặc game
- Không hỗ trợ video/streaming content
- Không đi sâu vào nghiệp vụ phức tạp (business logic testing)

---

## 6. Nơi thực hiện đề tài

Công ty **Bosch Global Software Technologies** – nơi người viết đang làm việc và phát triển hệ thống kiểm thử tự động mã nguồn mở **RobotFramework-AIO**, hiện đang được công bố công khai trên GitHub.

Đề tài có tiềm năng được tích hợp vào RobotFramework-AIO như một thư viện mở rộng, phục vụ cho các dự án kiểm thử tự động trong ngành automotive và embedded systems.

---

## 7. Thời gian thực hiện

| Giai đoạn | Nội dung | Thời gian |
|-----------|----------|-----------|
| 1 | Nghiên cứu lý thuyết và thiết kế kiến trúc | Tháng 5/2025 |
| 2 | Xây dựng CV Evidence Extraction Pipeline | Tháng 6/2025 |
| 3 | Xây dựng Coarse Hierarchy Builder | Tháng 6-7/2025 |
| 4 | Tích hợp LLM Refinement | Tháng 7/2025 |
| 5 | Xây dựng Robot Framework Library | Tháng 8/2025 |
| 6 | Đánh giá và thử nghiệm | Tháng 9/2025 |
| 7 | Viết luận văn và hoàn thiện | Tháng 10/2025 |

- **Bắt đầu**: Tháng 5/2025
- **Kết thúc dự kiến**: Tháng 10/2025

---

## 8. Tài liệu tham khảo

### 8.1. Các công trình nghiên cứu chính

1. **Mulong Xie et al.**, "UIED: A Hybrid Tool for GUI Element Detection," *ESEC/FSE 2020*.
   - Công trình nền tảng về kết hợp CV và deep learning cho GUI detection.

2. **Chen et al.**, "Object Detection for Graphical User Interface: Old Fashioned or Deep Learning or a Combination?" *arXiv:2008.05132*, 2020.
   - Nghiên cứu so sánh các phương pháp phát hiện UI element.

3. **Andrea Stocco et al.**, "Visual Web Test Repair," *ESEC/FSE 2018*.
   - Nghiên cứu về visual testing và tự động sửa test case.

4. **Leotta et al.**, "Visual vs. DOM-based Web Locators: An Empirical Study," *ICWE 2014*.
   - So sánh thực nghiệm giữa visual và DOM-based locators.

5. **Xiao et al.**, "IconNet: A Deep Neural Network for Icon Recognition," *CHI 2021*.
   - Mô hình deep learning cho nhận dạng icon trong GUI.

### 8.2. Mô hình ngôn ngữ và thị giác

6. **Qwen Team**, "Qwen2.5 Technical Report," *Alibaba Group*, 2024.
   - https://arxiv.org/abs/2412.15115
   - Mô hình ngôn ngữ nhỏ được sử dụng cho LLM refinement.

7. **Xiao et al.**, "Florence-2: Advancing a Unified Representation for a Variety of Vision Tasks," *Microsoft*, 2024.
   - https://arxiv.org/abs/2311.06242
   - Vision-Language Model được nghiên cứu cho GUI element detection.

8. **Wang et al.**, "Qwen2-VL: Enhancing Vision-Language Model's Perception of the World at Any Resolution," *Alibaba*, 2024.
   - https://arxiv.org/abs/2409.12191
   - VLM được đánh giá trong nghiên cứu.

### 8.3. Công cụ và thư viện

9. **OpenCV Library Documentation**
   - https://docs.opencv.org
   - Thư viện xử lý ảnh chính.

10. **EasyOCR**
    - https://github.com/JaidedAI/EasyOCR
    - Thư viện OCR đa ngôn ngữ.

11. **Robot Framework User Guide**
    - https://robotframework.org
    - Framework kiểm thử tự động.

12. **Ollama**
    - https://ollama.ai
    - Runtime cho chạy LLM local.

### 8.4. Tài liệu bổ sung

13. **"Image-based Approaches for Automating GUI Testing of Interactive Web-based Applications"**
    - Tổng quan về các phương pháp image-based testing.

14. **Chang et al.**, "GUI Testing: Pitfalls and Solutions," *IEEE Software*, 2010.
    - Các thách thức trong GUI testing.

15. **Memon et al.**, "GUI Testing: Myths, Problems, and Solutions," *IEEE Computer*, 2002.
    - Nền tảng lý thuyết về GUI testing.

---

## Phụ lục: Kết quả nghiên cứu sơ bộ

### A. So sánh các Vision-Language Models cho GUI Detection

Trong quá trình nghiên cứu, các VLM sau đã được đánh giá:

| Model | Button Detection | Text Detection | Inference Time | Kết luận |
|-------|------------------|----------------|----------------|----------|
| Florence-2-base | ❌ Không detect riêng | ✅ Tốt (OCR) | 4.6s | Phù hợp cho OCR |
| Florence-2-large | ❌ Không detect riêng | ✅ Tốt (OCR) | 235s | Chậm, không cải thiện |
| Qwen2-VL-2B | ❌ Hallucinated coords | ✅ Mô tả tốt | ~30s | Không phù hợp |
| Qwen2-VL-7B | ❌ Hallucinated coords | ✅ Mô tả tốt | ~27s | Không phù hợp |

**Kết luận**: VLM tổng quát không phù hợp cho việc phát hiện chính xác bounding box của UI element. Phương pháp kết hợp CV + OCR + SLM cho kết quả tốt hơn.

### B. Kiến trúc đề xuất vs. Phương pháp hiện có

| Tiêu chí | UIED (2020) | Đề xuất của luận văn |
|----------|-------------|---------------------|
| CV Pipeline | Flood-fill, edge detection | Edge detection, contour analysis, morphological ops |
| Text Detection | EAST + CRNN | EasyOCR (đơn giản hơn, hiệu quả tương đương) |
| Classification | CNN (ResNet50) | Small LLM (Qwen2.5-3B) |
| Output | Bounding boxes + types | **Visual DOM** (cấu trúc cây + metadata) |
| Runtime | Cần GPU cho deep learning | Có thể chạy CPU (SLM qua Ollama) |

---

*Đề cương này được cập nhật dựa trên kết quả nghiên cứu và thực nghiệm thực tế trong quá trình phát triển hệ thống.*
