"""Parse Pyroscope "flamebearer" payloads into a call tree and sum CPU time by
function name.

Flamebearer format: ``flamebearer["levels"][depth]`` is a flat array of 4-tuples
``(x_offset_delta, total_ticks, self_ticks, name_index)`` per node, ordered
left-to-right; ``x_offset_delta`` is relative to the end of the previous
sibling at that depth. ``flamebearer["names"][name_index]`` is the symbol.
``metadata.sampleRate`` converts ticks to seconds (``seconds = ticks /
sampleRate``); for the ``process_cpu:...:nanoseconds`` profile type,
``sampleRate`` is ``1_000_000_000`` and ticks are literally nanoseconds.

The same function name can appear as both an ancestor and a descendant of
itself in one call path (confirmed live: a router-level ``receive_payment``
directly wraps a use-case ``receive_payment``, and a store's own ``mget``
wraps redis-py's ``mget``). A node's ``total_ticks`` already includes its
descendants', so naively summing every node with a given name double-counts
that case. ``sum_ticks_by_name``/``sum_ticks_within`` only count the
**outermost** occurrence of a name along each root-to-leaf path.

``iter_levels``/``focus_on`` feed the flame-graph renderer, which highlights
frames by name lookup, independent of tree position. Left alone, that paints
the inner ``mget`` the same color as the outer one -- visually implying the
read is counted twice even though the sum above only counts the outer node's
``total_ticks`` once. Both functions take an optional ``shadow_names`` and tag
each row with a ``shadowed`` flag, computed with the same outermost-occurrence
rule, so the renderer can render a shadowed frame as a plain "other" frame
instead of re-highlighting it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, FrozenSet, Iterable, List, NamedTuple, Tuple


@dataclass
class FlameNode:
    name: str
    total_ticks: int
    self_ticks: int
    start: int
    end: int
    children: List["FlameNode"] = field(default_factory=list)


class _RawNode(NamedTuple):
    start: int
    end: int
    total: int
    self_ticks: int
    name_idx: int


def _parse_level(raw: List[int]) -> List[_RawNode]:
    nodes: List[_RawNode] = []
    x = 0
    for i in range(0, len(raw), 4):
        x += raw[i]
        total, self_ticks, name_idx = raw[i + 1], raw[i + 2], raw[i + 3]
        nodes.append(_RawNode(x, x + total, total, self_ticks, name_idx))
        x += total
    return nodes


def build_tree(payload: Dict[str, Any]) -> FlameNode:
    """Reconstruct the call tree from a flamebearer payload's flat levels."""
    fb = payload["flamebearer"]
    names = fb["names"]
    levels = fb["levels"]
    if not levels or not levels[0]:
        raise ValueError("empty flamebearer: no levels")

    def to_node(rn: _RawNode) -> FlameNode:
        return FlameNode(
            name=names[rn.name_idx],
            total_ticks=rn.total,
            self_ticks=rn.self_ticks,
            start=rn.start,
            end=rn.end,
        )

    root_raw = _parse_level(levels[0])[0]
    root = to_node(root_raw)
    current_level = [root]
    for depth in range(1, len(levels)):
        raw_nodes = _parse_level(levels[depth])
        built = [to_node(rn) for rn in raw_nodes]
        parent_idx = 0
        for child in built:
            while (
                parent_idx < len(current_level) - 1
                and current_level[parent_idx].end <= child.start
            ):
                parent_idx += 1
            current_level[parent_idx].children.append(child)
        current_level = built
    return root


def _shadowed(node: FlameNode, closed: FrozenSet[str], target: FrozenSet[str]) -> bool:
    return node.name in target and node.name in closed


def _close(node: FlameNode, closed: FrozenSet[str], target: FrozenSet[str]) -> FrozenSet[str]:
    return closed | {node.name} if node.name in target else closed


def iter_levels(
    payload: Dict[str, Any],
    shadow_names: Iterable[str] = (),
) -> List[List[Tuple[int, int, int, int, str, bool]]]:
    """Per-depth list of ``(start, end, total_ticks, self_ticks, name, shadowed)``
    spans.

    For consumers (e.g. the flame-graph renderer) that only need each row's
    horizontal extent and resolved name, not the linked :class:`FlameNode` tree.

    ``shadowed`` is True for a node whose name is in ``shadow_names`` and
    already occurred on an ancestor along this root-to-leaf path -- the same
    condition ``sum_ticks_by_name`` uses to skip re-counting it. Empty by
    default, so existing callers that don't pass ``shadow_names`` get
    ``shadowed=False`` on every row.
    """
    target = frozenset(shadow_names)
    root = build_tree(payload)
    rows_by_depth: Dict[int, List[Tuple[int, int, int, int, str, bool]]] = {}

    def walk(node: FlameNode, depth: int, closed: FrozenSet[str]) -> None:
        rows_by_depth.setdefault(depth, []).append(
            (
                node.start,
                node.end,
                node.total_ticks,
                node.self_ticks,
                node.name,
                _shadowed(node, closed, target),
            )
        )
        new_closed = _close(node, closed, target)
        for child in node.children:
            walk(child, depth + 1, new_closed)

    walk(root, 0, frozenset())
    if not rows_by_depth:
        return []
    max_depth = max(rows_by_depth)
    return [
        sorted(rows_by_depth.get(depth, []), key=lambda r: r[0])
        for depth in range(max_depth + 1)
    ]


def sample_rate(payload: Dict[str, Any]) -> float:
    return float(payload["metadata"]["sampleRate"])


def root_total_ticks(payload: Dict[str, Any]) -> int:
    return int(payload["flamebearer"]["levels"][0][1])


def _sum_outermost(roots: Iterable[FlameNode], names: Iterable[str]) -> Dict[str, int]:
    target = set(names)
    totals: Dict[str, int] = {n: 0 for n in target}

    def walk(node: FlameNode, closed: FrozenSet[str]) -> None:
        if node.name in target and node.name not in closed:
            totals[node.name] += node.total_ticks
            closed = closed | {node.name}
        for child in node.children:
            walk(child, closed)

    for root in roots:
        walk(root, frozenset())
    return totals


def outermost_nodes(root: FlameNode, name: str) -> List[FlameNode]:
    """Nodes named ``name``, never descending into an already-matched node's subtree."""
    result: List[FlameNode] = []

    def walk(node: FlameNode) -> None:
        if node.name == name:
            result.append(node)
            return
        for child in node.children:
            walk(child)

    walk(root)
    return result


def sum_ticks_by_name(root: FlameNode, names: Iterable[str]) -> Dict[str, int]:
    """Sum ticks of the outermost occurrence of each target name in the whole tree."""
    return _sum_outermost([root], names)


def sum_ticks_within(nodes: List[FlameNode], names: Iterable[str]) -> Dict[str, int]:
    """Same as :func:`sum_ticks_by_name`, scoped to the given subtrees only."""
    return _sum_outermost(nodes, names)


def focus_on(
    payload: Dict[str, Any],
    name: str,
    shadow_names: Iterable[str] = (),
) -> Tuple[List[List[Tuple[int, int, int, int, str, bool]]], int]:
    """Re-root the call tree at every outermost occurrence of ``name``.

    A full process flame graph spends most of its depth on framework/event-loop
    frames before ever reaching the interesting handler code, so cropping to
    just the subtree(s) under a given function (e.g. ``run_endpoint_function``)
    makes the graph legible. Each occurrence (one per request handled in the
    window) is tiled left-to-right starting at depth 0, in the same
    ``(start, end, total_ticks, self_ticks, name, shadowed)`` row shape
    :func:`iter_levels` returns, so the flame-graph renderer needs no separate
    code path. See :func:`iter_levels` for what ``shadowed``/``shadow_names``
    mean; each occurrence's own subtree is walked independently, so a name
    shadowed inside one occurrence has no bearing on another.

    Returns ``([], 0)`` if ``name`` doesn't occur in this profile.
    """
    target = frozenset(shadow_names)
    root = build_tree(payload)
    occurrences = outermost_nodes(root, name)
    if not occurrences:
        return [], 0

    rows_by_depth: Dict[int, List[Tuple[int, int, int, int, str, bool]]] = {}
    cursor = 0
    for occurrence in occurrences:
        shift = cursor - occurrence.start

        def collect(node: FlameNode, depth: int, closed: FrozenSet[str]) -> None:
            rows_by_depth.setdefault(depth, []).append(
                (
                    node.start + shift,
                    node.end + shift,
                    node.total_ticks,
                    node.self_ticks,
                    node.name,
                    _shadowed(node, closed, target),
                )
            )
            new_closed = _close(node, closed, target)
            for child in node.children:
                collect(child, depth + 1, new_closed)

        collect(occurrence, 0, frozenset())
        cursor += occurrence.total_ticks

    max_depth = max(rows_by_depth)
    levels = [
        sorted(rows_by_depth.get(depth, []), key=lambda r: r[0])
        for depth in range(max_depth + 1)
    ]
    total_ticks = sum(o.total_ticks for o in occurrences)
    return levels, total_ticks
