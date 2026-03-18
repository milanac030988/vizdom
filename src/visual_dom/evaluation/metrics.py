"""
Evaluation Metrics for Visual DOM

This module provides various metrics for evaluating the quality of
Visual DOM detection, OCR accuracy, hierarchy structure, and locator quality.
"""

from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Tuple, Set
import numpy as np
from difflib import SequenceMatcher


def calculate_iou(box1: List[int], box2: List[int]) -> float:
    """
    Calculate Intersection over Union (IoU) between two bounding boxes.

    Args:
        box1: [x1, y1, x2, y2] format
        box2: [x1, y1, x2, y2] format

    Returns:
        IoU value between 0 and 1
    """
    x1 = max(box1[0], box2[0])
    y1 = max(box1[1], box2[1])
    x2 = min(box1[2], box2[2])
    y2 = min(box1[3], box2[3])

    if x2 <= x1 or y2 <= y1:
        return 0.0

    intersection = (x2 - x1) * (y2 - y1)
    area1 = (box1[2] - box1[0]) * (box1[3] - box1[1])
    area2 = (box2[2] - box2[0]) * (box2[3] - box2[1])
    union = area1 + area2 - intersection

    return intersection / union if union > 0 else 0.0


def calculate_center_distance(box1: List[int], box2: List[int]) -> float:
    """Calculate Euclidean distance between box centers."""
    cx1 = (box1[0] + box1[2]) / 2
    cy1 = (box1[1] + box1[3]) / 2
    cx2 = (box2[0] + box2[2]) / 2
    cy2 = (box2[1] + box2[3]) / 2
    return np.sqrt((cx1 - cx2) ** 2 + (cy1 - cy2) ** 2)


@dataclass
class ElementMetrics:
    """
    Element Detection Metrics

    Evaluates how well the system detects UI elements by comparing
    predicted bounding boxes against ground truth annotations.

    Metrics:
    - Precision: TP / (TP + FP) - How many predictions are correct
    - Recall: TP / (TP + FN) - How many ground truths are found
    - F1 Score: 2 * (P * R) / (P + R) - Harmonic mean
    - Mean IoU: Average IoU of matched elements
    - Mean Average Precision (mAP): Area under PR curve
    """

    true_positives: int = 0
    false_positives: int = 0
    false_negatives: int = 0

    iou_scores: List[float] = field(default_factory=list)
    matched_pairs: List[Tuple[str, str, float]] = field(default_factory=list)  # (pred_id, gt_id, iou)

    # Per-class metrics
    class_metrics: Dict[str, Dict[str, float]] = field(default_factory=dict)

    @property
    def precision(self) -> float:
        """Precision = TP / (TP + FP)"""
        total = self.true_positives + self.false_positives
        return self.true_positives / total if total > 0 else 0.0

    @property
    def recall(self) -> float:
        """Recall = TP / (TP + FN)"""
        total = self.true_positives + self.false_negatives
        return self.true_positives / total if total > 0 else 0.0

    @property
    def f1_score(self) -> float:
        """F1 = 2 * (Precision * Recall) / (Precision + Recall)"""
        p, r = self.precision, self.recall
        return 2 * p * r / (p + r) if (p + r) > 0 else 0.0

    @property
    def mean_iou(self) -> float:
        """Average IoU of matched elements"""
        return np.mean(self.iou_scores) if self.iou_scores else 0.0

    @property
    def accuracy(self) -> float:
        """Overall accuracy = TP / (TP + FP + FN)"""
        total = self.true_positives + self.false_positives + self.false_negatives
        return self.true_positives / total if total > 0 else 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "true_positives": self.true_positives,
            "false_positives": self.false_positives,
            "false_negatives": self.false_negatives,
            "precision": round(self.precision, 4),
            "recall": round(self.recall, 4),
            "f1_score": round(self.f1_score, 4),
            "mean_iou": round(self.mean_iou, 4),
            "accuracy": round(self.accuracy, 4),
            "class_metrics": self.class_metrics,
        }


@dataclass
class OCRMetrics:
    """
    OCR/Text Recognition Metrics

    Evaluates text recognition accuracy by comparing predicted text
    against ground truth text annotations.

    Metrics:
    - Character Error Rate (CER): Edit distance at character level
    - Word Error Rate (WER): Edit distance at word level
    - Exact Match Rate: Percentage of perfectly matched texts
    - Similarity Score: Average text similarity (0-1)
    """

    total_chars_gt: int = 0
    total_chars_pred: int = 0
    char_insertions: int = 0
    char_deletions: int = 0
    char_substitutions: int = 0

    total_words_gt: int = 0
    total_words_pred: int = 0
    word_insertions: int = 0
    word_deletions: int = 0
    word_substitutions: int = 0

    exact_matches: int = 0
    total_comparisons: int = 0

    similarity_scores: List[float] = field(default_factory=list)

    @property
    def cer(self) -> float:
        """Character Error Rate = (I + D + S) / total_chars_gt"""
        total_errors = self.char_insertions + self.char_deletions + self.char_substitutions
        return total_errors / self.total_chars_gt if self.total_chars_gt > 0 else 0.0

    @property
    def wer(self) -> float:
        """Word Error Rate = (I + D + S) / total_words_gt"""
        total_errors = self.word_insertions + self.word_deletions + self.word_substitutions
        return total_errors / self.total_words_gt if self.total_words_gt > 0 else 0.0

    @property
    def exact_match_rate(self) -> float:
        """Percentage of texts that match exactly"""
        return self.exact_matches / self.total_comparisons if self.total_comparisons > 0 else 0.0

    @property
    def mean_similarity(self) -> float:
        """Average similarity score (0-1)"""
        return np.mean(self.similarity_scores) if self.similarity_scores else 0.0

    @property
    def char_accuracy(self) -> float:
        """Character-level accuracy = 1 - CER (clamped to 0)"""
        return max(0.0, 1.0 - self.cer)

    @property
    def word_accuracy(self) -> float:
        """Word-level accuracy = 1 - WER (clamped to 0)"""
        return max(0.0, 1.0 - self.wer)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "cer": round(self.cer, 4),
            "wer": round(self.wer, 4),
            "char_accuracy": round(self.char_accuracy, 4),
            "word_accuracy": round(self.word_accuracy, 4),
            "exact_match_rate": round(self.exact_match_rate, 4),
            "mean_similarity": round(self.mean_similarity, 4),
            "total_comparisons": self.total_comparisons,
        }


@dataclass
class HierarchyMetrics:
    """
    Hierarchy/Structure Metrics

    Evaluates how well the predicted DOM tree structure matches
    the ground truth hierarchy.

    Metrics:
    - Parent Accuracy: Correct parent assignments
    - Tree Edit Distance: Minimum edits to transform predicted to GT tree
    - Depth Accuracy: Correct depth level assignments
    - Sibling Order Accuracy: Correct ordering of sibling elements
    """

    correct_parents: int = 0
    total_elements: int = 0

    correct_depths: int = 0
    total_depth_comparisons: int = 0

    correct_sibling_orders: int = 0
    total_sibling_comparisons: int = 0

    tree_edit_distance: int = 0
    tree_size: int = 0

    @property
    def parent_accuracy(self) -> float:
        """Percentage of elements with correct parent assignment"""
        return self.correct_parents / self.total_elements if self.total_elements > 0 else 0.0

    @property
    def depth_accuracy(self) -> float:
        """Percentage of elements at correct depth level"""
        return self.correct_depths / self.total_depth_comparisons if self.total_depth_comparisons > 0 else 0.0

    @property
    def sibling_order_accuracy(self) -> float:
        """Percentage of sibling pairs in correct order"""
        return self.correct_sibling_orders / self.total_sibling_comparisons if self.total_sibling_comparisons > 0 else 0.0

    @property
    def normalized_edit_distance(self) -> float:
        """Tree edit distance normalized by tree size"""
        return self.tree_edit_distance / self.tree_size if self.tree_size > 0 else 0.0

    @property
    def structure_similarity(self) -> float:
        """Overall structure similarity = 1 - normalized_edit_distance"""
        return max(0.0, 1.0 - self.normalized_edit_distance)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "parent_accuracy": round(self.parent_accuracy, 4),
            "depth_accuracy": round(self.depth_accuracy, 4),
            "sibling_order_accuracy": round(self.sibling_order_accuracy, 4),
            "tree_edit_distance": self.tree_edit_distance,
            "normalized_edit_distance": round(self.normalized_edit_distance, 4),
            "structure_similarity": round(self.structure_similarity, 4),
        }


@dataclass
class LocatorMetrics:
    """
    Locator Quality Metrics

    Evaluates the quality and reliability of generated locators
    for UI automation.

    Metrics:
    - Uniqueness Rate: Percentage of locators that uniquely identify elements
    - Stability Score: How stable locators are across similar screens
    - Coverage: Percentage of elements with usable locators
    - Preferred Locator Usage: Distribution of locator types used
    """

    total_elements: int = 0
    elements_with_locators: int = 0

    unique_text_locators: int = 0
    unique_id_locators: int = 0
    unique_type_index_locators: int = 0

    # Locator type distribution
    locator_type_counts: Dict[str, int] = field(default_factory=dict)

    # Elements that can be located by text (preferred)
    text_locatable: int = 0

    # Duplicate locator count (problematic)
    duplicate_locators: int = 0

    @property
    def coverage(self) -> float:
        """Percentage of elements with at least one locator"""
        return self.elements_with_locators / self.total_elements if self.total_elements > 0 else 0.0

    @property
    def text_locator_rate(self) -> float:
        """Percentage of elements locatable by text (most readable)"""
        return self.text_locatable / self.total_elements if self.total_elements > 0 else 0.0

    @property
    def uniqueness_rate(self) -> float:
        """Percentage of locators that are unique"""
        total_unique = self.unique_text_locators + self.unique_id_locators
        return total_unique / self.elements_with_locators if self.elements_with_locators > 0 else 0.0

    @property
    def duplicate_rate(self) -> float:
        """Percentage of elements with duplicate/ambiguous locators"""
        return self.duplicate_locators / self.total_elements if self.total_elements > 0 else 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "coverage": round(self.coverage, 4),
            "text_locator_rate": round(self.text_locator_rate, 4),
            "uniqueness_rate": round(self.uniqueness_rate, 4),
            "duplicate_rate": round(self.duplicate_rate, 4),
            "locator_type_distribution": self.locator_type_counts,
            "total_elements": self.total_elements,
        }


def levenshtein_distance(s1: str, s2: str) -> Tuple[int, int, int, int]:
    """
    Calculate Levenshtein distance with operation counts.

    Returns:
        (total_distance, insertions, deletions, substitutions)
    """
    if len(s1) < len(s2):
        return levenshtein_distance(s2, s1)

    if len(s2) == 0:
        return len(s1), 0, len(s1), 0

    previous_row = range(len(s2) + 1)
    insertions = deletions = substitutions = 0

    for i, c1 in enumerate(s1):
        current_row = [i + 1]
        for j, c2 in enumerate(s2):
            # Calculate costs
            insert_cost = previous_row[j + 1] + 1
            delete_cost = current_row[j] + 1
            substitute_cost = previous_row[j] + (c1 != c2)

            min_cost = min(insert_cost, delete_cost, substitute_cost)
            current_row.append(min_cost)

        previous_row = current_row

    # Approximate operation counts (not exact but useful)
    total = previous_row[-1]
    # Use SequenceMatcher for better operation breakdown
    matcher = SequenceMatcher(None, s1, s2)
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == 'replace':
            substitutions += max(i2 - i1, j2 - j1)
        elif tag == 'delete':
            deletions += i2 - i1
        elif tag == 'insert':
            insertions += j2 - j1

    return total, insertions, deletions, substitutions


def text_similarity(s1: str, s2: str) -> float:
    """Calculate text similarity ratio (0-1)."""
    if not s1 and not s2:
        return 1.0
    if not s1 or not s2:
        return 0.0
    return SequenceMatcher(None, s1.lower(), s2.lower()).ratio()
