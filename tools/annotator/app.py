"""
Simple web-based UI annotation tool.

A lightweight alternative to Label Studio for quick annotation tasks.

Usage:
    pip install flask
    python tools/annotator/app.py --images data/raw/screenshots --output data/annotations

Then open http://localhost:5000 in your browser.
"""

import argparse
import json
import os
from pathlib import Path
from flask import Flask, render_template_string, request, jsonify, send_file

app = Flask(__name__)

# Global config
CONFIG = {
    "images_dir": None,
    "output_dir": None,
    "current_index": 0,
    "images": [],
}

# UI Element classes
CLASSES = [
    {"id": 0, "name": "button", "color": "#FF6B6B"},
    {"id": 1, "name": "text", "color": "#4ECDC4"},
    {"id": 2, "name": "icon", "color": "#45B7D1"},
    {"id": 3, "name": "input_field", "color": "#96CEB4"},
    {"id": 4, "name": "checkbox", "color": "#FFEAA7"},
    {"id": 5, "name": "radio_button", "color": "#DDA0DD"},
    {"id": 6, "name": "toggle", "color": "#98D8C8"},
    {"id": 7, "name": "slider", "color": "#F7DC6F"},
    {"id": 8, "name": "dropdown", "color": "#BB8FCE"},
    {"id": 9, "name": "image", "color": "#85C1E9"},
    {"id": 10, "name": "container", "color": "#D5DBDB"},
    {"id": 11, "name": "toolbar", "color": "#F8B500"},
    {"id": 12, "name": "navbar", "color": "#5DADE2"},
    {"id": 13, "name": "card", "color": "#FADBD8"},
    {"id": 14, "name": "list_item", "color": "#D4E6F1"},
]

HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>UI Annotator</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { font-family: Arial, sans-serif; background: #1a1a2e; color: #eee; }
        .container { display: flex; height: 100vh; }

        .sidebar { width: 250px; background: #16213e; padding: 15px; overflow-y: auto; }
        .sidebar h2 { margin-bottom: 15px; color: #4ECDC4; }

        .class-btn {
            display: block; width: 100%; padding: 10px; margin: 5px 0;
            border: 2px solid transparent; border-radius: 5px;
            cursor: pointer; text-align: left; font-size: 14px;
        }
        .class-btn.selected { border-color: #fff; }
        .class-btn:hover { opacity: 0.8; }

        .main { flex: 1; display: flex; flex-direction: column; }

        .toolbar {
            background: #16213e; padding: 10px 20px;
            display: flex; align-items: center; gap: 15px;
        }
        .toolbar button {
            padding: 8px 16px; border: none; border-radius: 5px;
            cursor: pointer; font-size: 14px;
        }
        .toolbar .nav-btn { background: #4ECDC4; color: #000; }
        .toolbar .save-btn { background: #2ecc71; color: #fff; }
        .toolbar .delete-btn { background: #e74c3c; color: #fff; }
        .toolbar span { color: #888; }

        .canvas-container {
            flex: 1; position: relative; overflow: hidden;
            display: flex; align-items: center; justify-content: center;
            background: #0f0f1a;
        }
        #canvas { cursor: crosshair; }

        .annotations-panel {
            width: 300px; background: #16213e; padding: 15px; overflow-y: auto;
        }
        .annotations-panel h3 { margin-bottom: 10px; color: #4ECDC4; }
        .annotation-item {
            background: #1a1a2e; padding: 10px; margin: 5px 0;
            border-radius: 5px; font-size: 12px;
        }
        .annotation-item .delete-box {
            float: right; color: #e74c3c; cursor: pointer;
        }

        .shortcuts { margin-top: 20px; font-size: 12px; color: #888; }
        .shortcuts div { margin: 5px 0; }
        .shortcuts kbd {
            background: #333; padding: 2px 6px; border-radius: 3px;
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="sidebar">
            <h2>Classes</h2>
            <div id="classes"></div>

            <div class="shortcuts">
                <h4>Shortcuts</h4>
                <div><kbd>1-9</kbd> Select class</div>
                <div><kbd>A/D</kbd> Prev/Next image</div>
                <div><kbd>S</kbd> Save</div>
                <div><kbd>Delete</kbd> Remove last box</div>
                <div><kbd>Esc</kbd> Cancel drawing</div>
            </div>
        </div>

        <div class="main">
            <div class="toolbar">
                <button class="nav-btn" onclick="prevImage()">← Prev</button>
                <span id="image-info">Image 1 / 1</span>
                <button class="nav-btn" onclick="nextImage()">Next →</button>
                <button class="save-btn" onclick="save()">💾 Save</button>
                <button class="delete-btn" onclick="deleteLastBox()">🗑 Delete Last</button>
                <span id="status"></span>
            </div>

            <div class="canvas-container">
                <canvas id="canvas"></canvas>
            </div>
        </div>

        <div class="annotations-panel">
            <h3>Annotations</h3>
            <div id="annotations-list"></div>
        </div>
    </div>

    <script>
        const CLASSES = {{ classes | tojson }};
        let currentClass = 0;
        let currentImage = null;
        let imageIndex = 0;
        let images = [];
        let annotations = [];
        let isDrawing = false;
        let startX, startY;
        let canvas, ctx;

        function init() {
            canvas = document.getElementById('canvas');
            ctx = canvas.getContext('2d');

            // Render class buttons
            const classesDiv = document.getElementById('classes');
            CLASSES.forEach((cls, i) => {
                const btn = document.createElement('button');
                btn.className = 'class-btn' + (i === 0 ? ' selected' : '');
                btn.style.background = cls.color;
                btn.style.color = '#000';
                btn.textContent = `${i+1}. ${cls.name}`;
                btn.onclick = () => selectClass(i);
                classesDiv.appendChild(btn);
            });

            // Canvas events
            canvas.addEventListener('mousedown', startDraw);
            canvas.addEventListener('mousemove', drawing);
            canvas.addEventListener('mouseup', endDraw);
            canvas.addEventListener('mouseleave', endDraw);

            // Keyboard shortcuts
            document.addEventListener('keydown', handleKey);

            // Load images
            loadImages();
        }

        function selectClass(i) {
            currentClass = i;
            document.querySelectorAll('.class-btn').forEach((btn, idx) => {
                btn.classList.toggle('selected', idx === i);
            });
        }

        function loadImages() {
            fetch('/api/images')
                .then(r => r.json())
                .then(data => {
                    images = data.images;
                    imageIndex = data.current_index;
                    loadCurrentImage();
                });
        }

        function loadCurrentImage() {
            if (images.length === 0) return;

            const img = new Image();
            img.onload = () => {
                currentImage = img;
                canvas.width = img.width;
                canvas.height = img.height;
                redraw();
                updateInfo();
                loadAnnotations();
            };
            img.src = '/api/image/' + images[imageIndex];
        }

        function loadAnnotations() {
            fetch('/api/annotations/' + images[imageIndex])
                .then(r => r.json())
                .then(data => {
                    annotations = data.annotations || [];
                    redraw();
                    updateAnnotationsList();
                });
        }

        function redraw() {
            if (!currentImage) return;
            ctx.drawImage(currentImage, 0, 0);

            annotations.forEach((ann, i) => {
                const cls = CLASSES[ann.class_id];
                ctx.strokeStyle = cls.color;
                ctx.lineWidth = 2;
                ctx.strokeRect(ann.x, ann.y, ann.w, ann.h);

                ctx.fillStyle = cls.color;
                ctx.fillRect(ann.x, ann.y - 20, ctx.measureText(cls.name).width + 10, 20);
                ctx.fillStyle = '#000';
                ctx.font = '12px Arial';
                ctx.fillText(cls.name, ann.x + 5, ann.y - 6);
            });
        }

        function startDraw(e) {
            isDrawing = true;
            const rect = canvas.getBoundingClientRect();
            startX = e.clientX - rect.left;
            startY = e.clientY - rect.top;
        }

        function drawing(e) {
            if (!isDrawing) return;

            const rect = canvas.getBoundingClientRect();
            const x = e.clientX - rect.left;
            const y = e.clientY - rect.top;

            redraw();

            ctx.strokeStyle = CLASSES[currentClass].color;
            ctx.lineWidth = 2;
            ctx.setLineDash([5, 5]);
            ctx.strokeRect(startX, startY, x - startX, y - startY);
            ctx.setLineDash([]);
        }

        function endDraw(e) {
            if (!isDrawing) return;
            isDrawing = false;

            const rect = canvas.getBoundingClientRect();
            const endX = e.clientX - rect.left;
            const endY = e.clientY - rect.top;

            const x = Math.min(startX, endX);
            const y = Math.min(startY, endY);
            const w = Math.abs(endX - startX);
            const h = Math.abs(endY - startY);

            if (w > 5 && h > 5) {
                annotations.push({
                    class_id: currentClass,
                    x: Math.round(x),
                    y: Math.round(y),
                    w: Math.round(w),
                    h: Math.round(h)
                });
                redraw();
                updateAnnotationsList();
            }
        }

        function updateAnnotationsList() {
            const list = document.getElementById('annotations-list');
            list.innerHTML = annotations.map((ann, i) => `
                <div class="annotation-item">
                    <span class="delete-box" onclick="deleteBox(${i})">✕</span>
                    <strong style="color:${CLASSES[ann.class_id].color}">${CLASSES[ann.class_id].name}</strong><br>
                    x:${ann.x} y:${ann.y} w:${ann.w} h:${ann.h}
                </div>
            `).join('');
        }

        function deleteBox(i) {
            annotations.splice(i, 1);
            redraw();
            updateAnnotationsList();
        }

        function deleteLastBox() {
            if (annotations.length > 0) {
                annotations.pop();
                redraw();
                updateAnnotationsList();
            }
        }

        function updateInfo() {
            document.getElementById('image-info').textContent =
                `Image ${imageIndex + 1} / ${images.length}: ${images[imageIndex]}`;
        }

        function save() {
            fetch('/api/save', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({
                    image: images[imageIndex],
                    annotations: annotations,
                    width: canvas.width,
                    height: canvas.height
                })
            })
            .then(r => r.json())
            .then(data => {
                document.getElementById('status').textContent = '✓ Saved!';
                setTimeout(() => {
                    document.getElementById('status').textContent = '';
                }, 2000);
            });
        }

        function prevImage() {
            if (imageIndex > 0) {
                imageIndex--;
                loadCurrentImage();
            }
        }

        function nextImage() {
            if (imageIndex < images.length - 1) {
                imageIndex++;
                loadCurrentImage();
            }
        }

        function handleKey(e) {
            if (e.key >= '1' && e.key <= '9') {
                const i = parseInt(e.key) - 1;
                if (i < CLASSES.length) selectClass(i);
            } else if (e.key === 'a' || e.key === 'A') {
                prevImage();
            } else if (e.key === 'd' || e.key === 'D') {
                nextImage();
            } else if (e.key === 's' || e.key === 'S') {
                save();
            } else if (e.key === 'Delete' || e.key === 'Backspace') {
                deleteLastBox();
            } else if (e.key === 'Escape') {
                isDrawing = false;
                redraw();
            }
        }

        init();
    </script>
</body>
</html>
"""


@app.route('/')
def index():
    return render_template_string(HTML_TEMPLATE, classes=CLASSES)


@app.route('/api/images')
def get_images():
    return jsonify({
        "images": CONFIG["images"],
        "current_index": CONFIG["current_index"]
    })


@app.route('/api/image/<filename>')
def get_image(filename):
    image_path = Path(CONFIG["images_dir"]) / filename
    return send_file(image_path)


@app.route('/api/annotations/<filename>')
def get_annotations(filename):
    stem = Path(filename).stem
    ann_file = Path(CONFIG["output_dir"]) / f"{stem}.json"

    if ann_file.exists():
        with open(ann_file) as f:
            return jsonify(json.load(f))

    return jsonify({"annotations": []})


@app.route('/api/save', methods=['POST'])
def save_annotations():
    data = request.json
    filename = data["image"]
    stem = Path(filename).stem

    # Save as JSON (internal format)
    json_file = Path(CONFIG["output_dir"]) / f"{stem}.json"
    with open(json_file, "w") as f:
        json.dump(data, f, indent=2)

    # Also save as YOLO format
    yolo_file = Path(CONFIG["output_dir"]) / f"{stem}.txt"
    width = data["width"]
    height = data["height"]

    lines = []
    for ann in data["annotations"]:
        # Convert to YOLO format (normalized center coords)
        x_center = (ann["x"] + ann["w"] / 2) / width
        y_center = (ann["y"] + ann["h"] / 2) / height
        w_norm = ann["w"] / width
        h_norm = ann["h"] / height

        lines.append(f"{ann['class_id']} {x_center:.6f} {y_center:.6f} {w_norm:.6f} {h_norm:.6f}")

    with open(yolo_file, "w") as f:
        f.write("\n".join(lines))

    return jsonify({"status": "ok", "saved": str(json_file)})


def main():
    parser = argparse.ArgumentParser(description="Simple UI Annotator")
    parser.add_argument("--images", type=str, required=True, help="Images directory")
    parser.add_argument("--output", type=str, required=True, help="Output directory")
    parser.add_argument("--port", type=int, default=5000, help="Server port")
    args = parser.parse_args()

    CONFIG["images_dir"] = args.images
    CONFIG["output_dir"] = args.output

    # Create output directory
    Path(args.output).mkdir(parents=True, exist_ok=True)

    # Find images
    images_path = Path(args.images)
    CONFIG["images"] = []
    for ext in ["*.png", "*.jpg", "*.jpeg"]:
        CONFIG["images"].extend([f.name for f in images_path.glob(ext)])
    CONFIG["images"].sort()

    print(f"\nSimple UI Annotator")
    print(f"==================")
    print(f"Images: {len(CONFIG['images'])} files in {args.images}")
    print(f"Output: {args.output}")
    print(f"\nOpen http://localhost:{args.port} in your browser")
    print("Press Ctrl+C to stop\n")

    app.run(host='0.0.0.0', port=args.port, debug=False)


if __name__ == "__main__":
    main()
