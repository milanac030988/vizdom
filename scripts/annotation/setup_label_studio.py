"""
Set up Label Studio project for UI element annotation.

Label Studio is a popular open-source annotation tool that supports:
- Bounding box annotation (for CV training)
- Hierarchical labeling (for LLM training)
- Team collaboration
- Export to multiple formats

Usage:
    # Install Label Studio
    pip install label-studio

    # Run setup script
    python scripts/annotation/setup_label_studio.py --project "UI Detection v1"

    # Start Label Studio
    label-studio start
"""

import argparse
import json
import os
from pathlib import Path
from typing import List, Dict

import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from models.configs.cv_model_registry import UI_ELEMENT_CLASSES


# Label Studio labeling config for UI element detection
LABELING_CONFIG_DETECTION = """
<View>
  <Image name="image" value="$image"/>

  <Header value="UI Element Detection"/>
  <RectangleLabels name="ui_elements" toName="image" strokeWidth="2">
    <Label value="button" background="#FF6B6B"/>
    <Label value="text" background="#4ECDC4"/>
    <Label value="icon" background="#45B7D1"/>
    <Label value="input_field" background="#96CEB4"/>
    <Label value="checkbox" background="#FFEAA7"/>
    <Label value="radio_button" background="#DDA0DD"/>
    <Label value="toggle" background="#98D8C8"/>
    <Label value="slider" background="#F7DC6F"/>
    <Label value="dropdown" background="#BB8FCE"/>
    <Label value="image" background="#85C1E9"/>
    <Label value="container" background="#D5DBDB"/>
    <Label value="toolbar" background="#F8B500"/>
    <Label value="navbar" background="#5DADE2"/>
    <Label value="card" background="#FADBD8"/>
    <Label value="list_item" background="#D4E6F1"/>
  </RectangleLabels>

  <Header value="Element Properties"/>
  <Choices name="clickable" toName="image" perRegion="true">
    <Choice value="clickable"/>
    <Choice value="not_clickable"/>
  </Choices>

  <Choices name="editable" toName="image" perRegion="true">
    <Choice value="editable"/>
    <Choice value="not_editable"/>
  </Choices>

  <TextArea name="text_content" toName="image" perRegion="true"
            placeholder="Text content (if any)" rows="1"/>
  <TextArea name="hint" toName="image" perRegion="true"
            placeholder="Hint/placeholder text" rows="1"/>
</View>
"""

# Label Studio config for hierarchy annotation (tree structure)
LABELING_CONFIG_HIERARCHY = """
<View>
  <Image name="image" value="$image"/>

  <Header value="UI Hierarchy Annotation"/>

  <RectangleLabels name="elements" toName="image" strokeWidth="2">
    <Label value="container" background="#D5DBDB"/>
    <Label value="row" background="#AED6F1"/>
    <Label value="column" background="#A9DFBF"/>
    <Label value="form" background="#F9E79F"/>
    <Label value="list" background="#F5B7B1"/>
    <Label value="element" background="#D7BDE2"/>
  </RectangleLabels>

  <Header value="Parent-Child Relations"/>
  <Relations>
    <Relation value="contains"/>
    <Relation value="label_for"/>
    <Relation value="next_to"/>
  </Relations>

  <Header value="Element Role"/>
  <Choices name="role" toName="image" perRegion="true">
    <Choice value="FrameLayout"/>
    <Choice value="LinearLayout"/>
    <Choice value="RelativeLayout"/>
    <Choice value="Button"/>
    <Choice value="TextView"/>
    <Choice value="EditText"/>
    <Choice value="ImageView"/>
    <Choice value="CheckBox"/>
    <Choice value="RecyclerView"/>
    <Choice value="ScrollView"/>
  </Choices>
</View>
"""


def create_project_config(project_name: str, task_type: str = "detection") -> Dict:
    """Create Label Studio project configuration."""

    if task_type == "detection":
        label_config = LABELING_CONFIG_DETECTION
    else:
        label_config = LABELING_CONFIG_HIERARCHY

    return {
        "title": project_name,
        "label_config": label_config,
        "expert_instruction": get_annotation_guidelines(task_type),
    }


def get_annotation_guidelines(task_type: str) -> str:
    """Get annotation guidelines for annotators."""

    if task_type == "detection":
        return """
## UI Element Detection Guidelines

### Goal
Draw bounding boxes around all visible UI elements and classify them.

### Rules
1. **Draw tight boxes** - Minimize whitespace around elements
2. **Include all visible elements** - Even small icons and separators
3. **One box per element** - Don't overlap boxes for the same element
4. **Classify accurately** - Use the most specific class that applies

### Class Definitions
- **button**: Clickable buttons (with text or icon)
- **text**: Static text labels, titles, paragraphs
- **icon**: Small symbolic images (not buttons)
- **input_field**: Text input boxes, search bars
- **checkbox**: Square checkable boxes
- **radio_button**: Round selection buttons
- **toggle**: On/off switches
- **slider**: Draggable range controls
- **dropdown**: Expandable selection menus
- **image**: Photos, illustrations (not icons)
- **container**: Grouped UI areas, cards, panels
- **toolbar**: Action bar with multiple buttons
- **navbar**: Navigation bar (top/bottom)
- **card**: Content cards with shadow/border
- **list_item**: Repeated items in a list

### Properties
- Mark **clickable** if the element responds to taps/clicks
- Mark **editable** if user can type/modify content
- Enter **text_content** for any visible text
- Enter **hint** for placeholder text in inputs
"""
    else:
        return """
## UI Hierarchy Annotation Guidelines

### Goal
Define the parent-child relationships between UI elements.

### Rules
1. **Identify containers** - Mark layout groups (rows, columns, forms)
2. **Draw relations** - Connect parent containers to children
3. **Use label_for** - Connect text labels to their inputs
4. **Assign roles** - Pick the Android-like role for each element

### Hierarchy Types
- **container**: Generic grouping
- **row**: Horizontal arrangement
- **column**: Vertical arrangement
- **form**: Input form group
- **list**: Repeated items
- **element**: Leaf element (no children)

### Tips
- Start from outer containers, work inward
- Group visually aligned elements
- Forms typically contain label+input pairs
"""


def prepare_import_file(images_dir: str, output_file: str) -> int:
    """Prepare JSON file for importing images into Label Studio."""

    images_path = Path(images_dir)
    tasks = []

    for ext in ["*.png", "*.jpg", "*.jpeg"]:
        for img_path in images_path.glob(ext):
            tasks.append({
                "data": {
                    "image": f"/data/local-files/?d={img_path.absolute()}"
                },
                "meta": {
                    "filename": img_path.name
                }
            })

    with open(output_file, "w") as f:
        json.dump(tasks, f, indent=2)

    print(f"Prepared {len(tasks)} images for import: {output_file}")
    return len(tasks)


def export_instructions():
    """Print instructions for exporting annotations."""
    print("""
## Exporting Annotations from Label Studio

### For CV Training (YOLO format):
1. Go to Project Settings > Cloud Storage > Add Source Storage
2. Or export manually: Project > Export > YOLO

### For LLM Training:
1. Export as JSON: Project > Export > JSON
2. Run conversion script:
   python scripts/annotation/convert_labelstudio_to_training.py --input export.json

### API Export:
```python
from label_studio_sdk import Client

ls = Client(url='http://localhost:8080', api_key='YOUR_KEY')
project = ls.get_project(PROJECT_ID)
project.export_tasks(export_type='YOLO', download_path='./export')
```
""")


def main():
    parser = argparse.ArgumentParser(description="Setup Label Studio for UI annotation")
    parser.add_argument("--project", type=str, default="UI Element Detection",
                        help="Project name")
    parser.add_argument("--type", choices=["detection", "hierarchy"],
                        default="detection", help="Annotation task type")
    parser.add_argument("--images", type=str, help="Directory with images to import")
    parser.add_argument("--output", type=str, default="data/annotation_projects",
                        help="Output directory for project files")
    args = parser.parse_args()

    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Create project config
    config = create_project_config(args.project, args.type)

    project_dir = output_dir / args.project.replace(" ", "_").lower()
    project_dir.mkdir(exist_ok=True)

    # Save labeling config
    config_file = project_dir / "labeling_config.xml"
    with open(config_file, "w") as f:
        f.write(config["label_config"])
    print(f"Saved labeling config: {config_file}")

    # Save guidelines
    guidelines_file = project_dir / "guidelines.md"
    with open(guidelines_file, "w") as f:
        f.write(config["expert_instruction"])
    print(f"Saved guidelines: {guidelines_file}")

    # Prepare import file if images provided
    if args.images:
        import_file = project_dir / "import_tasks.json"
        prepare_import_file(args.images, str(import_file))

    print(f"\n{'='*50}")
    print("Label Studio Setup Complete!")
    print(f"{'='*50}")
    print(f"\nProject files saved to: {project_dir}")
    print("\nNext steps:")
    print("1. Install Label Studio: pip install label-studio")
    print("2. Start Label Studio: label-studio start")
    print("3. Create new project and paste the labeling config")
    print("4. Import images from the import_tasks.json file")
    print("\nOr use Label Studio SDK for automation.")

    export_instructions()


if __name__ == "__main__":
    main()
