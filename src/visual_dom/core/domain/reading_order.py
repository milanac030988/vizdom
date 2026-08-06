"""
Reading-order (layout order) sorting for UI elements.

Sorts elements the way a person reads a screen: top row first, left-to-right
within a row, then the next row down. A naive ``sort(key=(y, x))`` fails because
elements on the same visual row rarely share an exact top-y (a button at y=100,
its neighbour at y=103). We instead **row-band**: group elements whose vertical
centres fall within a tolerance into a row, order rows top→bottom, and order
elements left→right within each row. This is a lightweight XY-cut.

Two entry points:
    sort_reading_order(items, get_bounds)   -> flat list, reading-ordered
    order_tree(nodes, get_bounds, get_children, set_children)
                                            -> orders each node's children in place

Both are geometry-only (no models), deterministic, and dependency-free so they
can be reused by the CV pipeline and the hierarchy builder alike.
"""

from statistics import median
from typing import Any, Callable, List, Optional, Sequence, Tuple

Bounds = Tuple[int, int, int, int]  # (x1, y1, x2, y2)


def _default_bounds(item: Any) -> Bounds:
    """Bounds accessor that works for objects with .bounds or {'bounds': ...}."""
    if hasattr(item, "bounds"):
        return tuple(item.bounds)  # type: ignore[arg-type]
    if isinstance(item, dict) and "bounds" in item:
        return tuple(item["bounds"])
    raise TypeError(
        "sort_reading_order: item has no .bounds attribute or 'bounds' key; "
        "pass an explicit get_bounds callable."
    )


def sort_reading_order(
    items: Sequence[Any],
    get_bounds: Optional[Callable[[Any], Bounds]] = None,
    row_tol_ratio: float = 0.6,
    min_tol: int = 4,
) -> List[Any]:
    """
    Return ``items`` reordered into reading order (top→bottom, left→right).

    Args:
        items: elements to order. Not mutated; a new list is returned.
        get_bounds: maps an item to (x1, y1, x2, y2). Defaults to ``.bounds`` /
            ``item['bounds']``.
        row_tol_ratio: row-band tolerance as a fraction of the median element
            height. Two elements are on the same row if their vertical centres
            differ by <= max(min_tol, row_tol_ratio * median_height).
        min_tol: floor for the tolerance in pixels (guards tiny/degenerate rows).

    The tolerance scales with element size so it adapts to resolution without
    hard-coded pixel thresholds (consistent with ADR-008).
    """
    n = len(items)
    if n <= 1:
        return list(items)

    gb = get_bounds or _default_bounds
    boxes: List[Bounds] = [gb(it) for it in items]

    heights = [max(1, b[3] - b[1]) for b in boxes]
    tol = max(min_tol, row_tol_ratio * median(heights))

    def cy(i: int) -> float:
        return (boxes[i][1] + boxes[i][3]) / 2.0

    # Visit indices top-to-bottom by vertical centre (tie-break left-to-right).
    order = sorted(range(n), key=lambda i: (cy(i), boxes[i][0]))

    # Greedy row banding. Because `order` is ascending in cy, a new element only
    # ever needs to be tested against the most recent rows; comparing to each
    # row's anchor centre keeps tall elements from chaining unrelated rows.
    rows: List[Tuple[float, List[int]]] = []  # (anchor_cy, indices)
    for i in order:
        c = cy(i)
        placed = False
        for anchor_cy, members in rows:
            if abs(c - anchor_cy) <= tol:
                members.append(i)
                placed = True
                break
        if not placed:
            rows.append((c, [i]))

    result: List[Any] = []
    for _anchor, members in rows:
        members.sort(key=lambda i: boxes[i][0])  # left → right by x1
        result.extend(items[i] for i in members)
    return result


def order_tree(
    root_children: List[Any],
    get_bounds: Optional[Callable[[Any], Bounds]] = None,
    get_children: Callable[[Any], List[Any]] = lambda n: getattr(n, "children", []),
    set_children: Optional[Callable[[Any, List[Any]], None]] = None,
    row_tol_ratio: float = 0.6,
) -> List[Any]:
    """
    Reading-order a tree: order siblings at every level.

    Orders ``root_children`` and, recursively, each node's children so a
    container's children are read top→bottom/left→right *within* that container —
    parents are never interleaved with their own descendants.

    Returns the ordered top-level list. Child lists are reordered in place via
    ``set_children`` (defaults to assigning ``node.children``).
    """
    def _set(node: Any, ordered: List[Any]) -> None:
        if set_children is not None:
            set_children(node, ordered)
        else:
            node.children = ordered  # type: ignore[attr-defined]

    def _recurse(nodes: List[Any]) -> List[Any]:
        ordered = sort_reading_order(nodes, get_bounds, row_tol_ratio=row_tol_ratio)
        for node in ordered:
            kids = get_children(node)
            if kids:
                _set(node, _recurse(kids))
        return ordered

    return _recurse(root_children)
