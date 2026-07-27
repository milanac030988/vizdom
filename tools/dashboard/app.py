"""
VizDOM Dashboard — Streamlit app for dataset generation, benchmarking, and results.

Run with: streamlit run tools/dashboard/app.py
"""

import streamlit as st
import sys
import os
import json
import time
import subprocess
from pathlib import Path
from datetime import datetime

# Add project paths
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))
sys.path.insert(0, str(PROJECT_ROOT / "scripts" / "data_prep"))


def main():
    st.set_page_config(
        page_title="VizDOM Dashboard",
        page_icon=":material/dashboard:",
        layout="wide",
    )

    pages = {
        "VizDOM Pipeline": [
            st.Page(page_overview, title="Overview", icon=":material/dashboard:"),
            st.Page(page_generate, title="Generate Dataset", icon=":material/palette:"),
            st.Page(page_train, title="Train", icon=":material/model_training:"),
        ],
        "Evaluation": [
            st.Page(page_benchmark, title="Benchmark", icon=":material/science:"),
            st.Page(page_results, title="Results", icon=":material/bar_chart:"),
        ],
        "Data": [
            st.Page(page_browser, title="Dataset Browser", icon=":material/image:"),
        ],
    }

    pg = st.navigation(pages)
    pg.run()


def page_overview():
    # Count stats
    data_dir = PROJECT_ROOT / "data"
    output_dir = PROJECT_ROOT / "output"
    datasets = []
    total_samples = 0
    total_elements = 0
    if data_dir.exists():
        for d in data_dir.iterdir():
            if d.is_dir() and (d / "manifest.json").exists():
                with open(d / "manifest.json") as f:
                    manifest = json.load(f)
                train_n = len(manifest.get("train", []))
                test_n = len(manifest.get("test", []))
                total_samples += train_n + test_n
                datasets.append({
                    "name": d.name,
                    "train": train_n,
                    "test": test_n,
                    "config": manifest.get("config", {}),
                })

    benchmarks = sorted(output_dir.glob("benchmark_*.json"), reverse=True) if output_dir.exists() else []
    sessions_dir = output_dir / "sessions" if output_dir.exists() else None
    sessions = sorted(sessions_dir.iterdir(), reverse=True) if sessions_dir and sessions_dir.exists() else []

    # Header
    st.markdown("""
    <div style="text-align:center; padding: 20px 0 10px 0;">
        <h1 style="margin-bottom:0">VizDOM Pipeline</h1>
        <p style="color:gray; font-size:16px; margin-top:5px">
            Visual DOM Generator &mdash; Screenshot to DOM using Computer Vision + LLM
        </p>
    </div>
    """, unsafe_allow_html=True)

    # KPI cards with custom styling
    st.markdown("""
    <style>
    .kpi-card {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        border-radius: 12px; padding: 20px; text-align: center; color: white;
    }
    .kpi-card.green { background: linear-gradient(135deg, #11998e 0%, #38ef7d 100%); }
    .kpi-card.orange { background: linear-gradient(135deg, #f2994a 0%, #f2c94c 100%); }
    .kpi-card.blue { background: linear-gradient(135deg, #2193b0 0%, #6dd5ed 100%); }
    .kpi-value { font-size: 36px; font-weight: 700; margin: 5px 0; }
    .kpi-label { font-size: 13px; opacity: 0.9; text-transform: uppercase; letter-spacing: 1px; }
    </style>
    """, unsafe_allow_html=True)

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.markdown(f"""
        <div class="kpi-card">
            <div class="kpi-label">Datasets</div>
            <div class="kpi-value">{len(datasets)}</div>
            <div class="kpi-label">{total_samples} total samples</div>
        </div>""", unsafe_allow_html=True)
    with col2:
        st.markdown(f"""
        <div class="kpi-card green">
            <div class="kpi-label">Benchmarks</div>
            <div class="kpi-value">{len(benchmarks)}</div>
            <div class="kpi-label">runs completed</div>
        </div>""", unsafe_allow_html=True)
    with col3:
        st.markdown(f"""
        <div class="kpi-card orange">
            <div class="kpi-label">Sessions</div>
            <div class="kpi-value">{len(sessions)}</div>
            <div class="kpi-label">viewer captures</div>
        </div>""", unsafe_allow_html=True)
    with col4:
        st.markdown(f"""
        <div class="kpi-card blue">
            <div class="kpi-label">Templates</div>
            <div class="kpi-value">9</div>
            <div class="kpi-label">UI generators</div>
        </div>""", unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)

    # Two column layout for datasets and benchmarks
    col_a, col_b = st.columns(2)

    with col_a:
        st.markdown("#### :material/folder: Datasets")
        if datasets:
            for ds in datasets:
                config = ds["config"]
                w = config.get("width", "?")
                h = config.get("height", "?")
                mode = config.get("mode", "static")
                with st.container(border=True):
                    c1, c2, c3 = st.columns([3, 1, 1])
                    c1.markdown(f"**{ds['name']}**  \n`{w}x{h}` &bull; {mode}")
                    c2.metric("Train", ds["train"])
                    c3.metric("Test", ds["test"])
        else:
            st.info("No datasets yet. Go to **Generate Dataset** to create one.")

    with col_b:
        st.markdown("#### :material/bar_chart: Recent Benchmarks")
        if benchmarks:
            for bm in benchmarks[:5]:
                with open(bm) as f:
                    bm_data = json.load(f)
                results = bm_data.get("results", [])
                best_f1 = max((r.get("text_f1", 0) for r in results), default=0)
                best_name = ""
                for r in results:
                    if r.get("text_f1", 0) == best_f1:
                        best_name = r["config"]["name"]
                        break

                with st.container(border=True):
                    c1, c2 = st.columns([3, 1])
                    timestamp = bm_data.get("timestamp", "")[:16]
                    c1.markdown(
                        f"**{bm.stem}**  \n"
                        f"`{timestamp}` &bull; {len(results)} configs"
                    )
                    c2.metric("Best F1", f"{best_f1:.0%}", best_name)
        else:
            st.info("No benchmarks yet. Go to **Benchmark** to run one.")

    # Recent sessions
    if sessions:
        st.markdown("<br>", unsafe_allow_html=True)
        st.markdown("#### :material/camera: Recent Sessions")
        cols = st.columns(min(len(sessions), 5))
        for i, session in enumerate(sessions[:5]):
            with cols[i]:
                img_path = session / "screenshot.png"
                info_path = session / "session_info.json"
                if img_path.exists():
                    st.image(str(img_path), use_column_width=True)
                if info_path.exists():
                    with open(info_path) as f:
                        info = json.load(f)
                    st.caption(
                        f"{session.name}  \n"
                        f"{info.get('element_count', '?')} elements &bull; "
                        f"{info.get('ocr_engine', '?')}"
                    )


def page_generate():
    st.title("Generate Dataset")

    tab_static, tab_llm, tab_claude, tab_augment = st.tabs([
        "Static Templates", "LLM Designer (Ollama)", "Claude Designer", "Camera Augmentation",
    ])

    with tab_static:
        st.subheader("Generate from Templates")

        col1, col2 = st.columns(2)

        with col1:
            num_samples = st.slider("Number of samples", 10, 500, 100, step=10)
            width = st.selectbox("Width", [800, 1024, 1280, 1920, 2560], index=3)
            height = st.selectbox("Height", [600, 720, 768, 1080, 1440], index=3)
            seed = st.number_input("Random seed", value=42, min_value=0)

        with col2:
            all_templates = [
                "login", "settings", "dashboard", "toolbar", "dialog",
                "data_table", "form_sidebar", "info_panel", "car_cluster",
            ]
            templates = st.multiselect(
                "Templates", all_templates, default=all_templates,
                help="UI types to generate"
            )

            all_themes = ["light", "dark", "blue", "high_contrast", "green"]
            themes = st.multiselect("Themes", all_themes, default=all_themes)

            train_ratio = st.slider("Train ratio", 0.5, 0.95, 0.8, step=0.05)

        output_name = st.text_input(
            "Dataset name",
            value=f"synthetic_{datetime.now().strftime('%Y%m%d')}",
        )
        output_dir = str(PROJECT_ROOT / "data" / output_name)

        if st.button("🚀 Generate Dataset", type="primary"):
            with st.spinner(f"Generating {num_samples} samples..."):
                progress = st.progress(0, text="Starting...")

                cmd = [
                    str(Path(sys.executable)),
                    str(PROJECT_ROOT / "scripts" / "data_prep" / "generate_synthetic_dataset.py"),
                    "static",
                    "-n", str(num_samples),
                    "--width", str(width),
                    "--height", str(height),
                    "--seed", str(seed),
                    "--train-ratio", str(train_ratio),
                    "-o", output_dir,
                    "--templates",
                ] + templates + ["--themes"] + themes

                process = subprocess.Popen(
                    cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                    text=True, encoding="utf-8", errors="replace",
                )

                log_lines = []
                for line in process.stdout:
                    log_lines.append(line.strip())
                    # Parse progress from output
                    if "/" in line and "[" in line:
                        try:
                            parts = line.split("[")[1].split("/")
                            current = int(parts[0])
                            total = int(parts[1].split("]")[0])
                            progress.progress(
                                current / total,
                                text=f"Generating {current}/{total}..."
                            )
                        except (IndexError, ValueError):
                            pass

                process.wait()
                progress.progress(1.0, text="Done!")

                if process.returncode == 0:
                    st.success(f"Dataset generated: {output_dir}")
                    with st.expander("Generation log"):
                        st.code("\n".join(log_lines[-20:]))
                else:
                    st.error("Generation failed!")
                    st.code("\n".join(log_lines))

    with tab_llm:
        st.subheader("Generate with Local LLM (Ollama)")
        st.markdown("Uses a local LLM to design diverse UI layouts")

        col1, col2 = st.columns(2)
        with col1:
            llm_samples = st.slider("Samples", 5, 50, 10, step=5, key="llm_n")
            llm_width = st.selectbox("Width", [800, 1024, 1920], index=2, key="llm_w")
            llm_height = st.selectbox("Height", [600, 720, 1080], index=2, key="llm_h")
        with col2:
            llm_model = st.selectbox("Ollama model", [
                "qwen2.5:3b", "llama3.1", "qwen2.5:7b", "mistral",
            ])
            llm_train_ratio = st.slider("Train ratio", 0.5, 0.95, 0.8, step=0.05, key="llm_tr")

        llm_output = st.text_input("Dataset name", value="synthetic_llm", key="llm_name")

        if st.button("Generate with LLM", type="primary", key="btn_llm"):
            output_dir = str(PROJECT_ROOT / "data" / llm_output)
            with st.spinner(f"Generating {llm_samples} LLM-designed UIs..."):
                cmd = [
                    str(Path(sys.executable)),
                    str(PROJECT_ROOT / "scripts" / "data_prep" / "generate_synthetic_dataset.py"),
                    "llm",
                    "-n", str(llm_samples),
                    "--width", str(llm_width),
                    "--height", str(llm_height),
                    "--model", llm_model,
                    "--train-ratio", str(llm_train_ratio),
                    "-o", output_dir,
                ]
                result = subprocess.run(
                    cmd, capture_output=True, text=True,
                    encoding="utf-8", errors="replace", timeout=600,
                )
                if result.returncode == 0:
                    st.success(f"Done: {output_dir}")
                    st.code(result.stdout[-500:])
                else:
                    st.error("Failed!")
                    st.code(result.stderr or result.stdout)

    with tab_claude:
        st.subheader("Generate with Claude Code")
        st.markdown("Uses Claude Code CLI for highest quality UI designs")

        col1, col2 = st.columns(2)
        with col1:
            claude_samples = st.slider("Samples", 1, 30, 5, step=1, key="claude_n")
            claude_width = st.selectbox("Width", [800, 1024, 1920], index=2, key="claude_w")
            claude_height = st.selectbox("Height", [600, 720, 1080], index=2, key="claude_h")
        with col2:
            claude_app = st.text_input(
                "App type (leave empty for random)",
                value="", key="claude_app",
                help="e.g. 'car infotainment', 'medical device', 'email client'",
            )
            claude_timeout = st.number_input("Timeout per request (s)", value=90, key="claude_t")

        claude_output = st.text_input("Dataset name", value="synthetic_claude", key="claude_name")

        if st.button("Generate with Claude", type="primary", key="btn_claude"):
            output_dir = str(PROJECT_ROOT / "data" / claude_output)
            with st.spinner(f"Generating {claude_samples} Claude-designed UIs..."):
                cmd = [
                    str(Path(sys.executable)),
                    str(PROJECT_ROOT / "scripts" / "data_prep" / "generate_with_claude.py"),
                    "-n", str(claude_samples),
                    "--width", str(claude_width),
                    "--height", str(claude_height),
                    "--timeout", str(claude_timeout),
                    "-o", output_dir,
                ]
                if claude_app.strip():
                    cmd.extend(["--app-type", claude_app.strip()])

                result = subprocess.run(
                    cmd, capture_output=True, text=True,
                    encoding="utf-8", errors="replace", timeout=claude_timeout * claude_samples + 60,
                )
                if result.returncode == 0:
                    st.success(f"Done: {output_dir}")
                    st.code(result.stdout[-500:])
                else:
                    st.error("Failed!")
                    st.code(result.stderr or result.stdout)

    with tab_augment:
        st.subheader("Camera Augmentation")
        st.markdown("Add camera-capture effects to existing datasets")

        # List available datasets
        data_dir = PROJECT_ROOT / "data"
        datasets = []
        if data_dir.exists():
            for d in data_dir.iterdir():
                if d.is_dir() and (d / "manifest.json").exists():
                    datasets.append(d.name)

        if not datasets:
            st.warning("No datasets available. Generate one first.")
            return

        source_dataset = st.selectbox("Source dataset", datasets)
        source_dir = str(data_dir / source_dataset)

        col1, col2 = st.columns(2)
        with col1:
            intensity = st.slider("Effect intensity", 0.1, 1.0, 0.6, step=0.1)
            variants = st.slider("Variants per image", 1, 5, 2)

        with col2:
            all_effects = [
                "perspective", "noise", "blur", "glare",
                "color_shift", "brightness_gradient", "moire",
                "vignette", "barrel_distortion",
            ]
            effects = st.multiselect("Effects", all_effects, default=all_effects)

        aug_name = f"{source_dataset}_camera"
        output_dir = str(data_dir / aug_name)

        if st.button("🎬 Apply Augmentation", type="primary"):
            with st.spinner("Augmenting..."):
                cmd = [
                    str(Path(sys.executable)),
                    str(PROJECT_ROOT / "scripts" / "data_prep" / "augment_camera.py"),
                    source_dir, "-o", output_dir,
                    "--variants", str(variants),
                    "--intensity", str(intensity),
                    "--effects",
                ] + effects

                result = subprocess.run(
                    cmd, capture_output=True, text=True,
                    encoding="utf-8", errors="replace",
                )

                if result.returncode == 0:
                    st.success(f"Augmentation complete: {output_dir}")
                    st.code(result.stdout)
                else:
                    st.error("Augmentation failed!")
                    st.code(result.stderr or result.stdout)


def page_train():
    st.title("Train Models")

    tab_cv, tab_llm = st.tabs(["CV Model (YOLO)", "LLM Fine-tune (LoRA)"])

    with tab_cv:
        st.subheader("Train CV Element Detector (YOLOv8)")

        # Dataset selection
        data_dir = PROJECT_ROOT / "data"
        datasets = []
        if data_dir.exists():
            for d in data_dir.iterdir():
                if d.is_dir() and (d / "manifest.json").exists():
                    datasets.append(d.name)

        if not datasets:
            st.warning("No datasets available. Generate one first.")
            return

        train_dataset = st.selectbox("Training dataset", datasets, key="cv_ds")

        col1, col2 = st.columns(2)
        with col1:
            yolo_model = st.selectbox("Base model", [
                "yolov8n", "yolov8s", "yolov8m", "yolov8l",
            ], help="n=nano (fast), s=small, m=medium, l=large (accurate)")
            epochs = st.slider("Epochs", 10, 300, 100, step=10)
            batch_size = st.selectbox("Batch size", [8, 16, 32], index=1)
        with col2:
            img_size = st.selectbox("Image size", [640, 800, 1024], index=0)
            use_gpu = st.checkbox("Use GPU", value=True)
            resume = st.checkbox("Resume from checkpoint", value=False)

        st.info(
            "Training requires: `pip install ultralytics`\n\n"
            "Dataset must be in YOLO format. Use `scripts/data_prep/convert_to_yolo.py` to convert."
        )

        if st.button("Start Training", type="primary", key="btn_cv_train"):
            st.warning("CV training integration coming soon. Use CLI for now:")
            st.code(
                f"python scripts/training/cv/train_yolo.py "
                f"--model {yolo_model} --data data/{train_dataset}/yolo/data.yaml "
                f"--epochs {epochs} --batch {batch_size} --imgsz {img_size}"
            )

    with tab_llm:
        st.subheader("Fine-tune LLM for Hierarchy Refinement (LoRA)")

        col1, col2 = st.columns(2)
        with col1:
            base_model = st.selectbox("Base model", [
                "Qwen/Qwen2.5-3B-Instruct",
                "microsoft/Phi-3.5-mini-instruct",
                "google/gemma-2-2b-it",
            ])
            lora_rank = st.selectbox("LoRA rank", [8, 16, 32, 64], index=1)
            lr = st.select_slider("Learning rate", [1e-5, 2e-5, 5e-5, 1e-4, 2e-4], value=2e-4)
        with col2:
            llm_epochs = st.slider("Epochs", 1, 10, 3, key="llm_epochs")
            llm_batch = st.selectbox("Batch size", [1, 2, 4, 8], index=1, key="llm_batch")
            max_len = st.selectbox("Max sequence length", [512, 1024, 2048, 4096], index=2)

        st.info(
            "Training requires: `pip install -e '.[training]'`\n\n"
            "Needs training data in `data/processed/train/` format."
        )

        if st.button("Start Training", type="primary", key="btn_llm_train"):
            st.warning("LLM training integration coming soon. Use CLI for now:")
            st.code(
                f"python scripts/training/finetune_lora.py "
                f"--model {base_model} --data data/processed/train "
                f"--epochs {llm_epochs} --batch {llm_batch} "
                f"--lora-rank {lora_rank} --lr {lr} --max-len {max_len}"
            )


def page_benchmark():
    st.title("Benchmark Pipeline")
    st.caption("Compare OCR engines, upscaling, and SLM configurations against ground truth")

    # Gather available data sources
    data_dir = PROJECT_ROOT / "data"
    datasets = []
    if data_dir.exists():
        for d in data_dir.iterdir():
            if d.is_dir() and (d / "manifest.json").exists():
                datasets.append(d.name)

    sessions_dir = PROJECT_ROOT / "output" / "sessions"
    session_images = []
    if sessions_dir and sessions_dir.exists():
        for s in sorted(sessions_dir.iterdir(), reverse=True)[:10]:
            img = s / "screenshot.png"
            if img.exists():
                session_images.append(str(img))

    # ── Step 1: Test Images ──────────────────────────────────────────
    st.markdown("#### Step 1 &mdash; Select Test Images")

    test_images = []
    gt_files = []

    with st.container(border=True):
        image_source = st.radio(
            "Image source",
            ["From dataset", "From session captures", "Custom path"],
            horizontal=True, label_visibility="collapsed",
        )

        if image_source == "From dataset":
            if not datasets:
                st.warning("No datasets available. Generate one first.")
                return
            col_ds, col_n = st.columns([3, 1])
            with col_ds:
                selected_ds = st.selectbox("Dataset", datasets, label_visibility="collapsed")
            ds_path = data_dir / selected_ds
            with open(ds_path / "manifest.json") as f:
                manifest = json.load(f)
            test_entries = manifest.get("test", [])
            if not test_entries:
                st.warning("No test split in this dataset. Using train samples.")
                test_entries = manifest.get("train", [])
            with col_n:
                max_images = st.number_input(
                    "Images", min_value=1, max_value=min(len(test_entries), 50),
                    value=min(5, len(test_entries)), label_visibility="collapsed",
                )
            for entry in test_entries[:max_images]:
                test_images.append(str(ds_path / entry["image"]))
                gt_files.append(str(ds_path / entry["label"]))
            st.success(f"{len(test_images)} images selected from **{selected_ds}** (with ground truth)")

        elif image_source == "From session captures":
            if not session_images:
                st.warning("No session captures found.")
                return
            selected = st.multiselect(
                "Select sessions", session_images,
                default=session_images[:min(3, len(session_images))],
                format_func=lambda x: Path(x).parent.name,
                label_visibility="collapsed",
            )
            test_images = selected
            if test_images:
                st.success(f"{len(test_images)} session screenshots selected (no ground truth)")

        else:
            col_img, col_gt = st.columns(2)
            with col_img:
                custom_path = st.text_input("Image path", placeholder="path/to/screenshot.png")
            with col_gt:
                gt_path = st.text_input("Ground truth (optional)", placeholder="path/to/labels.json")
            if custom_path:
                test_images = [custom_path]
                if gt_path:
                    gt_files = [gt_path]

    if not test_images:
        return

    # ── Step 2: Pipeline Configurations ──────────────────────────────
    st.markdown("#### Step 2 &mdash; Pipeline Configurations")

    with st.container(border=True):
        col_ocr, col_opts, col_slm = st.columns(3)

        with col_ocr:
            st.markdown("**OCR Engines**")
            ocr_easyocr = st.checkbox("EasyOCR", value=True, key="ocr_easy")
            ocr_tesseract = st.checkbox("Tesseract", value=False, key="ocr_tess")
            ocr_paddleocr = st.checkbox("PaddleOCR", value=False, key="ocr_paddle")

        with col_opts:
            st.markdown("**Options**")
            test_upscale = st.checkbox("Test with/without upscale", value=True)
            conf_threshold = st.select_slider(
                "Confidence threshold",
                options=[0.1, 0.2, 0.3, 0.4, 0.5],
                value=0.3,
            )

        with col_slm:
            st.markdown("**SLM / VLM**")
            test_slm = st.checkbox("Include SLM configs", value=False)
            slm_models = []
            if test_slm:
                slm_models = st.multiselect(
                    "Models", ["qwen2.5:3b", "llama3.1", "minicpm-v"],
                    default=["qwen2.5:3b"], label_visibility="collapsed",
                )

    # Build config list
    ocr_engines = []
    if ocr_easyocr:
        ocr_engines.append("easyocr")
    if ocr_tesseract:
        ocr_engines.append("tesseract")
    if ocr_paddleocr:
        ocr_engines.append("paddleocr")

    configs = []
    for ocr in ocr_engines:
        configs.append({"name": ocr, "ocr_engine": ocr, "confidence_threshold": conf_threshold})
        if test_upscale:
            configs.append({
                "name": f"{ocr}_no_upscale",
                "ocr_engine": ocr,
                "upscale": False,
                "confidence_threshold": conf_threshold,
            })
    if test_slm:
        for model in slm_models:
            configs.append({
                "name": f"easyocr+{model}",
                "ocr_engine": "easyocr",
                "slm_backend": "ollama",
                "slm_model": model,
                "confidence_threshold": conf_threshold,
            })

    # ── Step 3: Run ──────────────────────────────────────────────────
    st.markdown("#### Step 3 &mdash; Run")

    with st.container(border=True):
        total_runs = len(configs) * len(test_images)
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Configurations", len(configs))
        c2.metric("Test Images", len(test_images))
        c3.metric("Total Runs", total_runs)
        c4.metric("Ground Truth", "Yes" if gt_files else "No")

    if not configs:
        st.warning("Select at least one OCR engine.")
        return

    if st.button("Run Benchmark", type="primary", use_container_width=True) and test_images:
        # Save configs to temp file
        config_path = str(PROJECT_ROOT / "output" / "_temp_bench_config.json")
        with open(config_path, 'w') as f:
            json.dump(configs, f)

        all_results = []
        progress = st.progress(0, text="Starting benchmark...")
        total_runs = len(test_images)

        for i, img_path in enumerate(test_images):
            progress.progress(i / total_runs, text=f"Testing {Path(img_path).name}...")

            cmd = [
                str(Path(sys.executable)),
                str(PROJECT_ROOT / "scripts" / "benchmark_pipeline.py"),
                img_path,
                "--configs", config_path,
            ]

            if gt_files and i < len(gt_files):
                cmd.extend(["--ground-truth", gt_files[i]])

            result = subprocess.run(
                cmd, capture_output=True, text=True,
                encoding="utf-8", errors="replace",
                timeout=600,
            )

            if result.returncode == 0:
                # Find the output JSON
                output_files = sorted(
                    (PROJECT_ROOT / "output").glob("benchmark_*.json"),
                    key=lambda f: f.stat().st_mtime, reverse=True,
                )
                if output_files:
                    with open(output_files[0]) as f:
                        bench_data = json.load(f)
                    all_results.append({
                        "image": Path(img_path).name,
                        "results": bench_data.get("results", []),
                    })

        progress.progress(1.0, text="Done!")

        # Clean up
        if os.path.exists(config_path):
            os.unlink(config_path)

        if all_results:
            st.success(f"Benchmark complete: {len(all_results)} images tested")
            _display_benchmark_results(all_results, bool(gt_files))
        else:
            st.error("No results collected")


def _display_benchmark_results(all_results, has_gt):
    """Display benchmark results with charts."""
    import pandas as pd

    # Aggregate results across all images
    config_stats = {}
    for img_result in all_results:
        for r in img_result["results"]:
            name = r["config"]["name"]
            if name not in config_stats:
                config_stats[name] = {
                    "f1_scores": [], "precisions": [], "recalls": [],
                    "ocr_accs": [], "durations": [], "elem_counts": [],
                    "text_counts": [],
                }
            config_stats[name]["f1_scores"].append(r.get("text_f1", 0))
            config_stats[name]["precisions"].append(r.get("text_precision", 0))
            config_stats[name]["recalls"].append(r.get("text_recall", 0))
            config_stats[name]["ocr_accs"].append(r.get("ocr_accuracy", 0))
            config_stats[name]["durations"].append(r.get("duration_ms", 0))
            config_stats[name]["elem_counts"].append(r.get("element_count", 0))
            config_stats[name]["text_counts"].append(r.get("elements_with_text", 0))

    # Build summary table
    rows = []
    for name, stats in config_stats.items():
        import numpy as np
        rows.append({
            "Config": name,
            "Avg F1": np.mean(stats["f1_scores"]),
            "Avg Precision": np.mean(stats["precisions"]),
            "Avg Recall": np.mean(stats["recalls"]),
            "Avg OCR Acc": np.mean(stats["ocr_accs"]),
            "Avg Time (s)": np.mean(stats["durations"]) / 1000,
            "Avg Elements": np.mean(stats["elem_counts"]),
            "Avg Text": np.mean(stats["text_counts"]),
        })

    df = pd.DataFrame(rows)

    # Highlight best
    st.subheader("Summary")
    if has_gt:
        best_f1 = df.loc[df["Avg F1"].idxmax(), "Config"]
        st.metric("Best F1", f"{df['Avg F1'].max():.1%}", delta=best_f1)

    st.dataframe(
        df.style.highlight_max(subset=["Avg F1", "Avg Precision", "Avg Recall", "Avg OCR Acc"])
               .highlight_min(subset=["Avg Time (s)"]),
    )

    # Charts
    if has_gt:
        col1, col2 = st.columns(2)

        with col1:
            st.subheader("Detection Quality")
            chart_df = df[["Config", "Avg F1", "Avg Precision", "Avg Recall"]].set_index("Config")
            st.bar_chart(chart_df)

        with col2:
            st.subheader("Performance")
            time_df = df[["Config", "Avg Time (s)"]].set_index("Config")
            st.bar_chart(time_df)

    col3, col4 = st.columns(2)

    with col3:
        st.subheader("Element Detection")
        elem_df = df[["Config", "Avg Elements", "Avg Text"]].set_index("Config")
        st.bar_chart(elem_df)

    with col4:
        if has_gt:
            st.subheader("OCR Accuracy")
            ocr_df = df[["Config", "Avg OCR Acc"]].set_index("Config")
            st.bar_chart(ocr_df)


def page_results():
    st.title("📈 Benchmark Results")

    output_dir = PROJECT_ROOT / "output"
    benchmarks = sorted(output_dir.glob("benchmark_*.json"), reverse=True) if output_dir.exists() else []

    if not benchmarks:
        st.info("No benchmark results yet. Run a benchmark first.")
        return

    # Select benchmark file
    selected = st.selectbox(
        "Select benchmark",
        benchmarks,
        format_func=lambda f: f.stem,
    )

    with open(selected) as f:
        data = json.load(f)

    st.markdown(f"**Image:** {data.get('image', 'N/A')}")
    st.markdown(f"**Timestamp:** {data.get('timestamp', 'N/A')}")

    if data.get("ground_truth"):
        st.markdown(f"**Ground truth:** {data['ground_truth']} ({data.get('ground_truth_count', '?')} elements)")

    results = data.get("results", [])
    if not results:
        st.warning("No results in this benchmark.")
        return

    import pandas as pd
    import numpy as np

    # Results table
    rows = []
    for r in results:
        rows.append({
            "Config": r["config"]["name"],
            "OCR": r["config"]["ocr_engine"],
            "SLM": r["config"].get("slm_model", "-"),
            "Time (s)": round(r["duration_ms"] / 1000, 1),
            "Elements": r["element_count"],
            "With Text": r["elements_with_text"],
            "Precision": r.get("text_precision", 0),
            "Recall": r.get("text_recall", 0),
            "F1": r.get("text_f1", 0),
            "OCR Acc": r.get("ocr_accuracy", 0),
            "Confidence": r.get("mean_confidence", 0),
        })

    df = pd.DataFrame(rows)

    # Summary cards
    has_gt = data.get("ground_truth") is not None
    if has_gt:
        col1, col2, col3, col4 = st.columns(4)
        best_idx = df["F1"].idxmax()
        col1.metric("Best F1", f"{df.loc[best_idx, 'F1']:.1%}", df.loc[best_idx, "Config"])
        col2.metric("Best Recall", f"{df['Recall'].max():.1%}")
        col3.metric("Fastest", f"{df['Time (s)'].min():.1f}s")
        col4.metric("Configs", len(results))

    st.divider()
    st.subheader("Results Table")
    st.dataframe(
        df.style.format({
            "Precision": "{:.1%}", "Recall": "{:.1%}",
            "F1": "{:.1%}", "OCR Acc": "{:.1%}",
            "Confidence": "{:.2f}",
        }),
    )

    # Charts
    if has_gt:
        col_a, col_b = st.columns(2)
        with col_a:
            st.subheader("Detection Quality")
            chart_df = df[["Config", "F1", "Precision", "Recall"]].set_index("Config")
            st.bar_chart(chart_df)
        with col_b:
            st.subheader("Performance (seconds)")
            st.bar_chart(df[["Config", "Time (s)"]].set_index("Config"))

    col_c, col_d = st.columns(2)
    with col_c:
        st.subheader("Elements Detected")
        st.bar_chart(df[["Config", "Elements", "With Text"]].set_index("Config"))
    with col_d:
        st.subheader("Type Distribution")
        for r in results:
            type_dist = r.get("type_distribution", {})
            if type_dist:
                st.markdown(f"**{r['config']['name']}**: " +
                            ", ".join(f"{k}:{v}" for k, v in sorted(type_dist.items())))

    # Text comparison (if ground truth available)
    if has_gt and data.get("ground_truth_texts"):
        st.divider()
        st.subheader("Text Detection Comparison")

        gt_texts = data["ground_truth_texts"]
        compare_rows = []

        for gt_text in sorted(gt_texts):
            row = {"Ground Truth": gt_text}
            for r in results:
                detected = r.get("detected_texts", [])
                # Find best match
                from difflib import SequenceMatcher
                best_match = ""
                best_sim = 0
                for det in detected:
                    sim = SequenceMatcher(None, gt_text.lower(), det.lower()).ratio()
                    if sim > best_sim:
                        best_sim = sim
                        best_match = det

                if best_sim >= 0.9:
                    row[r["config"]["name"]] = f"✅ {best_match}"
                elif best_sim >= 0.6:
                    row[r["config"]["name"]] = f"⚠️ {best_match} ({best_sim:.0%})"
                else:
                    row[r["config"]["name"]] = "❌ MISS"

            compare_rows.append(row)

        compare_df = pd.DataFrame(compare_rows)
        st.dataframe(compare_df)

    # HTML report link
    html_path = str(selected).replace(".json", ".html")
    if os.path.exists(html_path):
        st.divider()
        col_dl, col_view = st.columns([1, 3])
        with col_dl:
            with open(html_path, "r", encoding="utf-8") as f:
                html_content = f.read()
            st.download_button(
                "Download HTML Report",
                data=html_content,
                file_name=Path(html_path).name,
                mime="text/html",
            )
        with col_view:
            with st.expander("Preview HTML Report"):
                import streamlit.components.v1 as components
                components.html(html_content, height=800, scrolling=True)


def page_browser():
    st.title("🖼️ Dataset Browser")

    data_dir = PROJECT_ROOT / "data"
    datasets = []
    if data_dir.exists():
        for d in data_dir.iterdir():
            if d.is_dir() and (d / "manifest.json").exists():
                datasets.append(d.name)

    if not datasets:
        st.info("No datasets available.")
        return

    selected_ds = st.selectbox("Dataset", datasets)
    ds_path = data_dir / selected_ds

    with open(ds_path / "manifest.json") as f:
        manifest = json.load(f)

    config = manifest.get("config", {})
    st.markdown(
        f"**Resolution:** {config.get('width', '?')}x{config.get('height', '?')} | "
        f"**Train:** {len(manifest.get('train', []))} | "
        f"**Test:** {len(manifest.get('test', []))} | "
        f"**Generated:** {config.get('generated_at', 'N/A')[:19]}"
    )

    split = st.radio("Split", ["train", "test"], horizontal=True)
    entries = manifest.get(split, [])

    if not entries:
        st.warning(f"No {split} images.")
        return

    # Filter by template
    templates = sorted(set(e.get("template", e.get("app_type", "unknown")) for e in entries))
    selected_template = st.selectbox("Filter by template", ["all"] + templates)

    if selected_template != "all":
        entries = [e for e in entries if e.get("template", e.get("app_type", "")) == selected_template]

    st.markdown(f"**{len(entries)} images**")

    # Pagination
    page_size = 6
    total_pages = max(1, (len(entries) + page_size - 1) // page_size)
    page_num = st.slider("Page", 1, total_pages, 1) if total_pages > 1 else 1
    start = (page_num - 1) * page_size
    page_entries = entries[start:start + page_size]

    # Display images in grid
    cols = st.columns(3)
    for i, entry in enumerate(page_entries):
        img_path = ds_path / entry["image"]
        with cols[i % 3]:
            if img_path.exists():
                st.image(str(img_path), use_column_width=True)

            caption = entry.get("name", "")
            template = entry.get("template", entry.get("app_type", ""))
            theme = entry.get("theme", "")
            elem_count = entry.get("element_count", 0)

            st.caption(f"{caption}\n{template} / {theme} — {elem_count} elements")

            # Show ground truth on expand
            label_path = ds_path / entry.get("label", "")
            if label_path.exists():
                with st.expander("Ground truth"):
                    with open(label_path) as f:
                        gt_data = json.load(f)
                    text_elems = [
                        e for e in gt_data.get("elements", [])
                        if e.get("ocr_text")
                    ]
                    st.markdown(f"**{len(gt_data.get('elements', []))} elements** ({len(text_elems)} with text)")
                    for e in text_elems[:10]:
                        st.markdown(f"- `{e['visual_type']}`: {e['ocr_text']}")
                    if len(text_elems) > 10:
                        st.markdown(f"... and {len(text_elems) - 10} more")


if __name__ == "__main__":
    main()
