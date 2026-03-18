"""
Visual DOM Evaluator

Main evaluation class that compares predicted DOM against ground truth
and computes all metrics.
"""

import json
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple, Set
from dataclasses import dataclass, field

from .metrics import (
    ElementMetrics,
    OCRMetrics,
    HierarchyMetrics,
    LocatorMetrics,
    calculate_iou,
    calculate_center_distance,
    levenshtein_distance,
    text_similarity,
)


@dataclass
class EvaluationConfig:
    """Configuration for evaluation."""
    # IoU threshold for considering a detection as correct
    iou_threshold: float = 0.5

    # IoU threshold for "good" match (used in detailed analysis)
    iou_good_threshold: float = 0.75

    # Maximum center distance for matching (pixels)
    max_center_distance: float = 50.0

    # Whether to use strict text matching
    strict_text_matching: bool = False

    # Minimum text similarity for OCR match
    min_text_similarity: float = 0.8

    # Element types to evaluate (None = all)
    element_types: Optional[Set[str]] = None

    # Whether to evaluate hierarchy
    evaluate_hierarchy: bool = True

    # Whether to evaluate locators
    evaluate_locators: bool = True


class VisualDOMEvaluator:
    """
    Evaluates Visual DOM predictions against ground truth annotations.

    Usage:
        evaluator = VisualDOMEvaluator()
        results = evaluator.evaluate(predicted_dom, ground_truth_dom)
        print(results.summary())
    """

    def __init__(self, config: Optional[EvaluationConfig] = None):
        self.config = config or EvaluationConfig()

    def evaluate(
        self,
        predicted: Dict[str, Any],
        ground_truth: Dict[str, Any],
    ) -> "EvaluationResult":
        """
        Evaluate predicted DOM against ground truth.

        Args:
            predicted: Predicted DOM JSON (from VisualDOMPipeline + DOMCompiler)
            ground_truth: Ground truth DOM JSON (manually annotated)

        Returns:
            EvaluationResult with all metrics
        """
        result = EvaluationResult()

        # Extract elements from both DOMs
        pred_elements = self._extract_elements(predicted)
        gt_elements = self._extract_elements(ground_truth)

        # 1. Element Detection Metrics
        result.element_metrics = self._evaluate_elements(pred_elements, gt_elements)

        # 2. OCR Metrics
        result.ocr_metrics = self._evaluate_ocr(pred_elements, gt_elements, result.element_metrics.matched_pairs)

        # 3. Hierarchy Metrics
        if self.config.evaluate_hierarchy:
            result.hierarchy_metrics = self._evaluate_hierarchy(predicted, ground_truth)

        # 4. Locator Metrics
        if self.config.evaluate_locators:
            result.locator_metrics = self._evaluate_locators(pred_elements)

        # Store element counts
        result.predicted_count = len(pred_elements)
        result.ground_truth_count = len(gt_elements)

        return result

    def evaluate_batch(
        self,
        predictions: List[Dict[str, Any]],
        ground_truths: List[Dict[str, Any]],
    ) -> "BatchEvaluationResult":
        """
        Evaluate multiple predictions against ground truths.

        Args:
            predictions: List of predicted DOMs
            ground_truths: List of ground truth DOMs

        Returns:
            BatchEvaluationResult with aggregated metrics
        """
        if len(predictions) != len(ground_truths):
            raise ValueError("Number of predictions must match number of ground truths")

        results = []
        for pred, gt in zip(predictions, ground_truths):
            results.append(self.evaluate(pred, gt))

        return BatchEvaluationResult(results)

    def evaluate_from_files(
        self,
        predicted_path: str,
        ground_truth_path: str,
    ) -> "EvaluationResult":
        """Load DOMs from files and evaluate."""
        with open(predicted_path, 'r', encoding='utf-8') as f:
            predicted = json.load(f)
        with open(ground_truth_path, 'r', encoding='utf-8') as f:
            ground_truth = json.load(f)

        return self.evaluate(predicted, ground_truth)

    def _extract_elements(self, dom: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Extract flat list of elements from DOM structure."""
        elements = []

        # Handle different DOM formats
        if "dom" in dom:
            dom_data = dom["dom"]
            # If there's a flat elements list, use it
            if "elements" in dom_data:
                elements = dom_data["elements"]
            # Otherwise traverse hierarchy
            elif "hierarchy" in dom_data:
                self._traverse_hierarchy(dom_data["hierarchy"], elements)
        elif "hierarchy" in dom:
            self._traverse_hierarchy(dom["hierarchy"], elements)
        elif "elements" in dom:
            elements = dom["elements"]

        return elements

    def _traverse_hierarchy(self, node: Dict[str, Any], elements: List[Dict[str, Any]]):
        """Recursively traverse hierarchy and collect elements."""
        if node is None:
            return

        # Add current node (skip root if it's just a container)
        node_id = node.get("id", "")
        if node_id and node_id.upper() != "ROOT":
            elements.append(node)

        # Traverse children
        for child in node.get("children", []):
            self._traverse_hierarchy(child, elements)

    def _evaluate_elements(
        self,
        pred_elements: List[Dict],
        gt_elements: List[Dict],
    ) -> ElementMetrics:
        """Evaluate element detection metrics."""
        metrics = ElementMetrics()

        if not gt_elements:
            metrics.false_positives = len(pred_elements)
            return metrics

        if not pred_elements:
            metrics.false_negatives = len(gt_elements)
            return metrics

        # Match predictions to ground truth using IoU
        matched_gt = set()
        matched_pred = set()

        # Calculate IoU matrix
        iou_matrix = []
        for i, pred in enumerate(pred_elements):
            pred_bounds = pred.get("bounds", [0, 0, 0, 0])
            row = []
            for j, gt in enumerate(gt_elements):
                gt_bounds = gt.get("bounds", [0, 0, 0, 0])
                iou = calculate_iou(pred_bounds, gt_bounds)
                row.append((iou, i, j))
            iou_matrix.extend(row)

        # Sort by IoU descending and greedily match
        iou_matrix.sort(reverse=True, key=lambda x: x[0])

        for iou, pred_idx, gt_idx in iou_matrix:
            if pred_idx in matched_pred or gt_idx in matched_gt:
                continue

            if iou >= self.config.iou_threshold:
                matched_pred.add(pred_idx)
                matched_gt.add(gt_idx)
                metrics.true_positives += 1
                metrics.iou_scores.append(iou)
                metrics.matched_pairs.append((
                    pred_elements[pred_idx].get("id", str(pred_idx)),
                    gt_elements[gt_idx].get("id", str(gt_idx)),
                    iou
                ))

        # Count false positives and negatives
        metrics.false_positives = len(pred_elements) - len(matched_pred)
        metrics.false_negatives = len(gt_elements) - len(matched_gt)

        # Per-class metrics
        self._compute_class_metrics(pred_elements, gt_elements, matched_pred, matched_gt, metrics)

        return metrics

    def _compute_class_metrics(
        self,
        pred_elements: List[Dict],
        gt_elements: List[Dict],
        matched_pred: Set[int],
        matched_gt: Set[int],
        metrics: ElementMetrics,
    ):
        """Compute per-class precision/recall."""
        # Collect unique types
        all_types = set()
        for elem in pred_elements + gt_elements:
            elem_type = elem.get("visual_type") or elem.get("type", "unknown")
            all_types.add(elem_type)

        for elem_type in all_types:
            pred_of_type = [i for i, e in enumerate(pred_elements)
                          if (e.get("visual_type") or e.get("type")) == elem_type]
            gt_of_type = [i for i, e in enumerate(gt_elements)
                        if (e.get("visual_type") or e.get("type")) == elem_type]

            tp = len([i for i in pred_of_type if i in matched_pred])
            fp = len(pred_of_type) - tp
            fn = len([i for i in gt_of_type if i not in matched_gt])

            precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
            recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
            f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0

            metrics.class_metrics[elem_type] = {
                "precision": round(precision, 4),
                "recall": round(recall, 4),
                "f1": round(f1, 4),
                "support": len(gt_of_type),
            }

    def _evaluate_ocr(
        self,
        pred_elements: List[Dict],
        gt_elements: List[Dict],
        matched_pairs: List[Tuple[str, str, float]],
    ) -> OCRMetrics:
        """Evaluate OCR/text recognition metrics."""
        metrics = OCRMetrics()

        # Build lookup maps
        pred_by_id = {e.get("id", ""): e for e in pred_elements}
        gt_by_id = {e.get("id", ""): e for e in gt_elements}

        for pred_id, gt_id, iou in matched_pairs:
            pred_elem = pred_by_id.get(pred_id, {})
            gt_elem = gt_by_id.get(gt_id, {})

            pred_text = pred_elem.get("text") or pred_elem.get("ocr_text") or ""
            gt_text = gt_elem.get("text") or gt_elem.get("ocr_text") or ""

            # Skip if ground truth has no text
            if not gt_text:
                continue

            metrics.total_comparisons += 1

            # Character-level metrics
            metrics.total_chars_gt += len(gt_text)
            metrics.total_chars_pred += len(pred_text)

            dist, ins, dels, subs = levenshtein_distance(pred_text, gt_text)
            metrics.char_insertions += ins
            metrics.char_deletions += dels
            metrics.char_substitutions += subs

            # Word-level metrics
            pred_words = pred_text.split()
            gt_words = gt_text.split()
            metrics.total_words_gt += len(gt_words)
            metrics.total_words_pred += len(pred_words)

            w_dist, w_ins, w_dels, w_subs = levenshtein_distance(
                " ".join(pred_words), " ".join(gt_words)
            )
            metrics.word_insertions += w_ins
            metrics.word_deletions += w_dels
            metrics.word_substitutions += w_subs

            # Exact match
            if pred_text.strip().lower() == gt_text.strip().lower():
                metrics.exact_matches += 1

            # Similarity score
            similarity = text_similarity(pred_text, gt_text)
            metrics.similarity_scores.append(similarity)

        return metrics

    def _evaluate_hierarchy(
        self,
        predicted: Dict[str, Any],
        ground_truth: Dict[str, Any],
    ) -> HierarchyMetrics:
        """Evaluate hierarchy structure metrics."""
        metrics = HierarchyMetrics()

        # Extract hierarchies
        pred_hierarchy = self._get_hierarchy(predicted)
        gt_hierarchy = self._get_hierarchy(ground_truth)

        if not pred_hierarchy or not gt_hierarchy:
            return metrics

        # Build parent maps
        pred_parents = {}
        self._build_parent_map(pred_hierarchy, None, pred_parents)

        gt_parents = {}
        self._build_parent_map(gt_hierarchy, None, gt_parents)

        # Build depth maps
        pred_depths = {}
        self._build_depth_map(pred_hierarchy, 0, pred_depths)

        gt_depths = {}
        self._build_depth_map(gt_hierarchy, 0, gt_depths)

        # Compare parent assignments
        common_ids = set(pred_parents.keys()) & set(gt_parents.keys())
        metrics.total_elements = len(common_ids)

        for elem_id in common_ids:
            if pred_parents[elem_id] == gt_parents[elem_id]:
                metrics.correct_parents += 1

            if elem_id in pred_depths and elem_id in gt_depths:
                metrics.total_depth_comparisons += 1
                if pred_depths[elem_id] == gt_depths[elem_id]:
                    metrics.correct_depths += 1

        # Tree size for normalization
        metrics.tree_size = max(len(pred_parents), len(gt_parents))

        # Simple tree edit distance approximation
        metrics.tree_edit_distance = abs(len(pred_parents) - len(gt_parents))
        metrics.tree_edit_distance += metrics.total_elements - metrics.correct_parents

        return metrics

    def _get_hierarchy(self, dom: Dict[str, Any]) -> Optional[Dict]:
        """Extract hierarchy from DOM."""
        if "dom" in dom and "hierarchy" in dom["dom"]:
            return dom["dom"]["hierarchy"]
        if "hierarchy" in dom:
            return dom["hierarchy"]
        return None

    def _build_parent_map(self, node: Dict, parent_id: Optional[str], parent_map: Dict):
        """Build mapping of element ID to parent ID."""
        if node is None:
            return

        node_id = node.get("id", "")
        if node_id:
            parent_map[node_id] = parent_id

        for child in node.get("children", []):
            self._build_parent_map(child, node_id, parent_map)

    def _build_depth_map(self, node: Dict, depth: int, depth_map: Dict):
        """Build mapping of element ID to tree depth."""
        if node is None:
            return

        node_id = node.get("id", "")
        if node_id:
            depth_map[node_id] = depth

        for child in node.get("children", []):
            self._build_depth_map(child, depth + 1, depth_map)

    def _evaluate_locators(self, elements: List[Dict]) -> LocatorMetrics:
        """Evaluate locator quality metrics."""
        metrics = LocatorMetrics()
        metrics.total_elements = len(elements)

        text_values = []
        id_values = []

        for elem in elements:
            locators = elem.get("locators", {})

            if locators:
                metrics.elements_with_locators += 1

                # Count locator types
                for loc_type in locators.keys():
                    metrics.locator_type_counts[loc_type] = \
                        metrics.locator_type_counts.get(loc_type, 0) + 1

                # Check text locator
                if "text" in locators:
                    metrics.text_locatable += 1
                    text_values.append(locators["text"])

                # Track IDs
                if "id" in locators:
                    id_values.append(locators["id"])

        # Check uniqueness
        metrics.unique_text_locators = len(set(text_values))
        metrics.unique_id_locators = len(set(id_values))

        # Count duplicates
        text_counts = {}
        for t in text_values:
            text_counts[t] = text_counts.get(t, 0) + 1
        metrics.duplicate_locators = sum(1 for c in text_counts.values() if c > 1)

        return metrics


@dataclass
class EvaluationResult:
    """Container for all evaluation results."""
    element_metrics: ElementMetrics = field(default_factory=ElementMetrics)
    ocr_metrics: OCRMetrics = field(default_factory=OCRMetrics)
    hierarchy_metrics: HierarchyMetrics = field(default_factory=HierarchyMetrics)
    locator_metrics: LocatorMetrics = field(default_factory=LocatorMetrics)

    predicted_count: int = 0
    ground_truth_count: int = 0

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "summary": {
                "predicted_elements": self.predicted_count,
                "ground_truth_elements": self.ground_truth_count,
                "overall_f1": self.element_metrics.f1_score,
                "overall_precision": self.element_metrics.precision,
                "overall_recall": self.element_metrics.recall,
            },
            "element_detection": self.element_metrics.to_dict(),
            "ocr": self.ocr_metrics.to_dict(),
            "hierarchy": self.hierarchy_metrics.to_dict(),
            "locators": self.locator_metrics.to_dict(),
        }

    def summary(self) -> str:
        """Generate human-readable summary."""
        lines = [
            "=" * 60,
            "VISUAL DOM EVALUATION RESULTS",
            "=" * 60,
            "",
            f"Elements: {self.predicted_count} predicted, {self.ground_truth_count} ground truth",
            "",
            "--- Element Detection ---",
            f"  Precision:  {self.element_metrics.precision:.2%}",
            f"  Recall:     {self.element_metrics.recall:.2%}",
            f"  F1 Score:   {self.element_metrics.f1_score:.2%}",
            f"  Mean IoU:   {self.element_metrics.mean_iou:.2%}",
            "",
            "--- OCR Accuracy ---",
            f"  Char Accuracy:  {self.ocr_metrics.char_accuracy:.2%}",
            f"  Word Accuracy:  {self.ocr_metrics.word_accuracy:.2%}",
            f"  Exact Match:    {self.ocr_metrics.exact_match_rate:.2%}",
            f"  CER:            {self.ocr_metrics.cer:.4f}",
            f"  WER:            {self.ocr_metrics.wer:.4f}",
            "",
            "--- Hierarchy Structure ---",
            f"  Parent Accuracy:    {self.hierarchy_metrics.parent_accuracy:.2%}",
            f"  Depth Accuracy:     {self.hierarchy_metrics.depth_accuracy:.2%}",
            f"  Structure Sim:      {self.hierarchy_metrics.structure_similarity:.2%}",
            "",
            "--- Locator Quality ---",
            f"  Coverage:           {self.locator_metrics.coverage:.2%}",
            f"  Text Locator Rate:  {self.locator_metrics.text_locator_rate:.2%}",
            f"  Uniqueness Rate:    {self.locator_metrics.uniqueness_rate:.2%}",
            "",
            "=" * 60,
        ]
        return "\n".join(lines)


@dataclass
class BatchEvaluationResult:
    """Aggregated results from multiple evaluations."""
    results: List[EvaluationResult] = field(default_factory=list)

    @property
    def count(self) -> int:
        return len(self.results)

    @property
    def mean_f1(self) -> float:
        if not self.results:
            return 0.0
        return sum(r.element_metrics.f1_score for r in self.results) / len(self.results)

    @property
    def mean_precision(self) -> float:
        if not self.results:
            return 0.0
        return sum(r.element_metrics.precision for r in self.results) / len(self.results)

    @property
    def mean_recall(self) -> float:
        if not self.results:
            return 0.0
        return sum(r.element_metrics.recall for r in self.results) / len(self.results)

    @property
    def mean_iou(self) -> float:
        if not self.results:
            return 0.0
        return sum(r.element_metrics.mean_iou for r in self.results) / len(self.results)

    @property
    def mean_char_accuracy(self) -> float:
        if not self.results:
            return 0.0
        return sum(r.ocr_metrics.char_accuracy for r in self.results) / len(self.results)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "sample_count": self.count,
            "aggregate_metrics": {
                "mean_f1": round(self.mean_f1, 4),
                "mean_precision": round(self.mean_precision, 4),
                "mean_recall": round(self.mean_recall, 4),
                "mean_iou": round(self.mean_iou, 4),
                "mean_char_accuracy": round(self.mean_char_accuracy, 4),
            },
            "per_sample_results": [r.to_dict() for r in self.results],
        }

    def summary(self) -> str:
        lines = [
            "=" * 60,
            f"BATCH EVALUATION RESULTS ({self.count} samples)",
            "=" * 60,
            "",
            "--- Aggregate Metrics ---",
            f"  Mean F1 Score:      {self.mean_f1:.2%}",
            f"  Mean Precision:     {self.mean_precision:.2%}",
            f"  Mean Recall:        {self.mean_recall:.2%}",
            f"  Mean IoU:           {self.mean_iou:.2%}",
            f"  Mean Char Accuracy: {self.mean_char_accuracy:.2%}",
            "",
            "=" * 60,
        ]
        return "\n".join(lines)
