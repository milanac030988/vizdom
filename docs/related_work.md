# Related Work & Research Papers

## Key Papers for Visual DOM Project

### 1. UIED: UI Element Detection (Primary Reference)

**Paper:** "Object Detection for Graphical User Interface: Old Fashioned or Deep Learning or a Combination?"
- **arXiv:** https://arxiv.org/abs/2008.05132
- **GitHub:** https://github.com/MulongXie/UIED
- **Demo:** http://uied.online

**Authors:** Jieshan Chen, Mulong Xie, Zhenchang Xing, Chunyang Chen, et al. (2020)

**Key Findings:**
- Compared 7 detection methods on 50,000+ GUI images
- Pure deep learning (YOLO, Faster-RCNN): F1 ≈ 0.25-0.28
- Pure traditional CV: F1 ≈ 0.27
- **Hybrid approach: F1 ≈ 0.52** (best performance)

**Architecture:**
1. Text detection via OCR (Google Vision API)
2. Non-text detection via traditional CV (edge detection, contours)
3. CNN classifier for element type classification
4. Merge and deduplicate results

**Relevance to Our Project:**
- Validates our hybrid CV + LLM approach
- Provides baseline methods to compare against
- Their coarse-to-fine strategy is useful for hierarchy building
- Dataset methodology can inform our annotation process

**What We Add Beyond UIED:**
- LLM-based semantic hierarchy understanding
- Robot Framework automation integration
- Cross-platform adapter system
- Full automation pipeline (not just detection)

---

### 2. RICO Dataset

**Paper:** "Rico: A Mobile App Dataset for Building Data-Driven Design Applications"
- **Website:** http://interactionmining.org/rico
- **Size:** 72,000+ UI screenshots from 9,700+ Android apps

**Relevance:**
- Large-scale dataset for training/evaluation
- Includes UI hierarchy annotations
- Can be used for pre-training CV models

---

### 3. Screen Recognition

**Paper:** "Screen Recognition: Creating Accessibility Metadata for Mobile Applications from Pixels"
- **Authors:** Xiaoyi Zhang, et al. (Google, 2021)

**Key Ideas:**
- Uses vision models to infer accessibility metadata
- Creates semantic understanding from screenshots
- Similar goal to our Visual DOM generation

---

### 4. GUI Testing with Computer Vision

**Papers:**
- "Humanoid: A Deep Learning-based Approach to Automated Black-box Android App Testing"
- "Widget Detection via Deep Learning Regression"

**Relevance:**
- Prior work on visual GUI testing
- Different approaches we can compare against

---

## Integration Plan

### From UIED, we should adopt:

1. **Coarse-to-fine detection strategy**
   - First detect large containers
   - Then detect elements within containers
   - Improves hierarchy accuracy

2. **Separate text/non-text pipelines**
   - Text: OCR-based (EasyOCR/PaddleOCR)
   - Non-text: CV-based + optional CNN classifier

3. **Their evaluation methodology**
   - IoU-based metrics
   - Per-class accuracy
   - Compare against their baselines

### Our innovations beyond prior work:

1. **LLM for semantic understanding**
   - UIED only detects, doesn't understand structure
   - We use LLM to infer roles, relationships, intent

2. **Automation-ready output**
   - UIAutomator-compatible JSON schema
   - Direct integration with Robot Framework

3. **Multi-platform support**
   - Android (ADB)
   - Desktop (pyautogui)
   - Extensible adapter system

---

## Datasets to Consider

| Dataset | Size | Platform | Use |
|---------|------|----------|-----|
| RICO | 72K images | Android | Pre-training |
| UIED Dataset | 50K images | Mixed | Evaluation |
| Custom Dataset | TBD | Target apps | Fine-tuning |

---

## Citation

```bibtex
@inproceedings{chen2020uied,
  title={Object Detection for Graphical User Interface: Old Fashioned or Deep Learning or a Combination?},
  author={Chen, Jieshan and Xie, Mulong and Xing, Zhenchang and Chen, Chunyang and Xu, Xiwei and Zhu, Liming and Li, Guoqiang},
  booktitle={Proceedings of the 28th ACM Joint Meeting on European Software Engineering Conference and Symposium on the Foundations of Software Engineering},
  year={2020}
}
```
