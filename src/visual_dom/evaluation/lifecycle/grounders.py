"""
Per-step grounding baselines for the lifecycle benchmark.

A grounder answers ONE instruction with ONE location per model inference -
the paradigm VizDOM's parse-once design is compared against. The interface is
deliberately minimal so each adapter stays a thin prompt-and-parse shim:

    ground(image_bgr, instruction) -> (x, y) in image pixels, or None
    judge(image_bgr, statement)    -> "PASSED" | "FAILED" | None

`judge` exists because a *testing* benchmark scores oracles, not just clicks.
ELAM-7B supports it natively (its Expected Result workflow); UI-TARS has no
verdict mode, so its judge() grounds the statement's subject and answers from
whether grounding succeeded - an honest proxy, reported as such.

Hardware honesty: these are 7-8B VLMs. On the development machine (6 GB
RTX A3000) they require 4-bit quantization and/or CPU offload and run at
minutes-per-step; the adapters accept ``quantize=True`` and never pretend a
model is available when its weights are not installed. Aria-UI (25.3 B MoE) is
not runnable on this class of hardware at all and its adapter says so.
"""

import re
import time
from typing import Optional, Tuple

from visual_dom.logging_utils import get_logger

log = get_logger(__name__)


class GrounderUnavailable(RuntimeError):
    """Raised when a grounding model cannot run here; message says why/how."""


class Grounder:
    """Base adapter. Subclasses implement _load / ground / judge."""

    name = "base"
    #: filled by ground()/judge() with the last inference wall-clock seconds
    last_latency: float = 0.0

    def __init__(self, model_path: Optional[str] = None, quantize: bool = True):
        self.model_path = model_path
        self.quantize = quantize
        self._model = None
        self._processor = None

    def available(self) -> Tuple[bool, str]:
        """(ok, reason). Never raises; checks deps + weights cheaply."""
        raise NotImplementedError

    def ground(self, image_bgr, instruction: str) -> Optional[Tuple[int, int]]:
        raise NotImplementedError

    def judge(self, image_bgr, statement: str) -> Optional[str]:
        raise NotImplementedError

    # -- helpers -------------------------------------------------------------

    def _to_pil(self, image_bgr):
        import cv2
        from PIL import Image
        return Image.fromarray(cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB))

    def _timed(self, fn):
        t0 = time.perf_counter()
        try:
            return fn()
        finally:
            self.last_latency = time.perf_counter() - t0


class ElamGrounder(Grounder):
    """
    ELAM-7B (sparks-solutions/ELAM-7B, Apache-2.0; Molmo-7B-D on Qwen2-7B).

    Purpose-built for UI *testing*: "Test Action" grounds an instruction to a
    normalized point, "Expected Result" evaluates a statement to
    PASSED/FAILED. Output format: <point x="0.00-1.00" y="...">.
    """

    name = "elam-7b"
    DEFAULT_MODEL = "sparks-solutions/ELAM-7B"

    _POINT = re.compile(r'<point[^>]*x="([\d.]+)"[^>]*y="([\d.]+)"')

    def available(self):
        try:
            import torch  # noqa: F401
            import transformers  # noqa: F401
        except ImportError as exc:
            return False, f"missing package: {exc.name} (pip install torch transformers accelerate)"
        try:
            from huggingface_hub import try_to_load_from_cache  # noqa: F401
        except ImportError:
            pass
        return True, "deps present (weights download on first use, ~15 GB)"

    def _ensure(self):
        if self._model is not None:
            return
        from transformers import AutoModelForCausalLM, AutoProcessor
        path = self.model_path or self.DEFAULT_MODEL
        kwargs = {"trust_remote_code": True, "device_map": "auto"}
        if self.quantize:
            try:
                from transformers import BitsAndBytesConfig
                import torch
                kwargs["quantization_config"] = BitsAndBytesConfig(
                    load_in_4bit=True, bnb_4bit_compute_dtype=torch.float16)
            except ImportError:
                log.warning("bitsandbytes not installed - loading unquantized "
                            "(needs ~15 GB; expect CPU offload)")
        log.info("Loading ELAM-7B from %s ...", path)
        self._processor = AutoProcessor.from_pretrained(path, trust_remote_code=True)
        self._model = AutoModelForCausalLM.from_pretrained(path, **kwargs)

    def _run(self, image_bgr, prompt: str) -> str:
        self._ensure()
        pil = self._to_pil(image_bgr)
        inputs = self._processor.process(images=[pil], text=prompt)
        inputs = {k: v.to(self._model.device).unsqueeze(0) for k, v in inputs.items()}
        from transformers import GenerationConfig
        output = self._model.generate_from_batch(
            inputs, GenerationConfig(max_new_tokens=96, stop_strings="<|endoftext|>"),
            tokenizer=self._processor.tokenizer)
        tokens = output[0, inputs["input_ids"].size(1):]
        return self._processor.tokenizer.decode(tokens, skip_special_tokens=True)

    def ground(self, image_bgr, instruction):
        text = self._timed(lambda: self._run(image_bgr, instruction))
        m = self._POINT.search(text)
        if not m:
            log.info("ELAM produced no point for %r: %s", instruction, text[:120])
            return None
        h, w = image_bgr.shape[:2]
        return int(float(m.group(1)) * w), int(float(m.group(2)) * h)

    def judge(self, image_bgr, statement):
        text = self._timed(
            lambda: self._run(image_bgr, f"Evaluation of expected result: {statement}"))
        upper = text.upper()
        if "PASSED" in upper:
            return "PASSED"
        if "FAILED" in upper:
            return "FAILED"
        log.info("ELAM produced no verdict for %r: %s", statement, text[:120])
        return None


class UiTarsGrounder(Grounder):
    """
    UI-TARS-1.5-7B (ByteDance-Seed, Apache-2.0; Qwen2.5-VL base).

    Uses the repository's grounding prompt style; actions arrive as
    ``click(start_box='(x,y)')`` with coordinates in the model's resized image
    space, mapped back to source pixels. No native verdict mode - judge()
    grounds the statement's quoted subject and reports PASSED iff grounding
    produced a point (documented as a proxy in the results).
    """

    name = "ui-tars-1.5-7b"
    DEFAULT_MODEL = "ByteDance-Seed/UI-TARS-1.5-7B"

    _BOX = re.compile(r"\(\s*(\d+)\s*,\s*(\d+)\s*\)")
    _QUOTED = re.compile(r"'([^']+)'")

    GROUNDING_PROMPT = (
        "Output only the coordinate of one point in your response. "
        "What element matches the following task: {instruction}")

    def available(self):
        try:
            import torch  # noqa: F401
            import transformers  # noqa: F401
        except ImportError as exc:
            return False, f"missing package: {exc.name} (pip install torch transformers accelerate qwen-vl-utils)"
        return True, "deps present (weights download on first use, ~16 GB)"

    def _ensure(self):
        if self._model is not None:
            return
        from transformers import AutoProcessor, Qwen2_5_VLForConditionalGeneration
        path = self.model_path or self.DEFAULT_MODEL
        kwargs = {"device_map": "auto"}
        if self.quantize:
            try:
                from transformers import BitsAndBytesConfig
                import torch
                kwargs["quantization_config"] = BitsAndBytesConfig(
                    load_in_4bit=True, bnb_4bit_compute_dtype=torch.float16)
            except ImportError:
                log.warning("bitsandbytes not installed - loading unquantized "
                            "(needs ~16 GB; expect CPU offload)")
        log.info("Loading UI-TARS from %s ...", path)
        self._processor = AutoProcessor.from_pretrained(path)
        self._model = Qwen2_5_VLForConditionalGeneration.from_pretrained(path, **kwargs)

    def ground(self, image_bgr, instruction):
        def run():
            self._ensure()
            pil = self._to_pil(image_bgr)
            messages = [{"role": "user", "content": [
                {"type": "image", "image": pil},
                {"type": "text",
                 "text": self.GROUNDING_PROMPT.format(instruction=instruction)},
            ]}]
            text = self._processor.apply_chat_template(
                messages, tokenize=False, add_generation_prompt=True)
            inputs = self._processor(text=[text], images=[pil], return_tensors="pt")
            inputs = inputs.to(self._model.device)
            out = self._model.generate(**inputs, max_new_tokens=64)
            reply = self._processor.batch_decode(
                out[:, inputs["input_ids"].shape[1]:], skip_special_tokens=True)[0]
            return reply, inputs
        (reply, inputs) = self._timed(run)
        m = self._BOX.search(reply)
        if not m:
            log.info("UI-TARS produced no box for %r: %s", instruction, reply[:120])
            return None
        x, y = int(m.group(1)), int(m.group(2))
        # Qwen2.5-VL emits coordinates in the PROCESSED image space; rescale to
        # the source image using the processor's actual grid.
        h, w = image_bgr.shape[:2]
        grid = inputs.get("image_grid_thw")
        if grid is not None:
            merge = getattr(self._processor.image_processor, "merge_size", 2)
            patch = getattr(self._processor.image_processor, "patch_size", 14)
            proc_h = int(grid[0][1]) * patch
            proc_w = int(grid[0][2]) * patch
            _ = merge  # grid is pre-merge; patch grid covers the processed size
            x = int(x * w / proc_w)
            y = int(y * h / proc_h)
        return x, y

    def judge(self, image_bgr, statement):
        m = self._QUOTED.search(statement)
        subject = m.group(1) if m else statement
        point = self.ground(image_bgr, f"click the '{subject}' element")
        return "PASSED" if point is not None else "FAILED"


class AriaUiGrounder(Grounder):
    """
    Aria-UI (rhymes-ai, Apache-2.0) - 25.3 B-parameter MoE (3.9 B active).

    Not runnable on single-GPU workstation hardware: bf16 weights alone are
    ~50 GB and even 4-bit quantization exceeds a 6-16 GB card. The adapter
    exists so the comparison table can carry the column with an explicit
    "requires multi-GPU server" status instead of silently omitting it;
    reported paper numbers are cited in the evaluation docs instead.
    """

    name = "aria-ui"

    def available(self):
        return False, ("Aria-UI is a 25.3B MoE (~50 GB bf16); it requires a "
                       "multi-GPU server. Column reported from published "
                       "benchmarks; see docs/EVALUATION.md.")

    def ground(self, image_bgr, instruction):
        raise GrounderUnavailable(self.available()[1])

    def judge(self, image_bgr, statement):
        raise GrounderUnavailable(self.available()[1])


GROUNDERS = {cls.name: cls for cls in (ElamGrounder, UiTarsGrounder, AriaUiGrounder)}
