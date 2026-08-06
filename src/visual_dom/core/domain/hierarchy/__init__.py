"""
Hierarchy building modules.

- CoarseHierarchyBuilder: Rules-based hierarchy from CV detections
- LLMHierarchyRefiner: LLM-based refinement of coarse hierarchy
"""

from visual_dom.core.domain.hierarchy.coarse_builder import (
    CoarseHierarchyBuilder,
    TreeNode,
    GroupType,
    build_hierarchy,
)
from visual_dom.core.domain.hierarchy.llm_refiner import LLMHierarchyRefiner, refine_hierarchy

__all__ = [
    "CoarseHierarchyBuilder",
    "TreeNode",
    "GroupType",
    "build_hierarchy",
    "LLMHierarchyRefiner",
    "refine_hierarchy",
]
