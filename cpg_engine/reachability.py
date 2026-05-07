"""
ReachabilityAnalyzer: CPG 그래프 도달 가능 노드의 mandatory_actions 수집

HarmScorer의 분모를 외부 벤치마크의 expected_actions 길이 대신
CPG 그래프에서 도달 가능한 모든 mandatory_actions 수로 교체하기 위한 모듈.

BFS로 entry_node에서 도달 가능한 모든 노드를 탐색하고,
각 노드의 mandatory_actions를 수집한다.
"""

import logging
from collections import deque
from typing import Dict, List, Optional, Set

from cga_bench.cpg_model.schemas.base import CPGGraph, PatientState
from cga_bench.cpg_engine.applicability import ApplicabilityFilter, MandatoryObligation

logger = logging.getLogger(__name__)


class ReachabilityAnalyzer:
    """CPG 그래프의 도달 가능한 모든 노드에서 mandatory_actions를 수집."""

    def __init__(self, graph: CPGGraph):
        self.graph = graph

    def collect_all_mandatory(
        self, entry_node: Optional[str] = None
    ) -> Dict:
        """BFS로 entry_node에서 도달 가능한 모든 노드의 mandatory 합산.

        Args:
            entry_node: 시작 노드 ID. None이면 graph.entry_node 사용.

        Returns:
            dict with keys:
                - 'all_mandatory': Set[str] — 모든 도달 가능 mandatory action_ids
                - 'denominator': int — len(all_mandatory), HarmScorer 분모
                - 'by_node': Dict[str, List[str]] — 노드별 mandatory 목록
                - 'reachable_nodes': Set[str] — 도달 가능 노드 ID 집합
        """
        start = entry_node or self.graph.entry_node
        if start not in self.graph.nodes:
            logger.warning(f"Entry node '{start}' not in graph")
            return {
                "all_mandatory": set(),
                "denominator": 1,
                "by_node": {},
                "reachable_nodes": set(),
            }

        visited: Set[str] = set()
        queue: deque = deque([start])
        all_mandatory: Set[str] = set()
        by_node: Dict[str, List[str]] = {}

        while queue:
            node_id = queue.popleft()
            if node_id in visited:
                continue
            visited.add(node_id)

            node = self.graph.nodes.get(node_id)
            if node is None:
                continue

            # Collect mandatory_actions from this node
            if node.mandatory_actions:
                by_node[node_id] = list(node.mandatory_actions)
                all_mandatory.update(node.mandatory_actions)

            # Enqueue successors: next_nodes (default transitions)
            for next_id in node.next_nodes:
                if next_id not in visited:
                    queue.append(next_id)

            # Enqueue successors: conditional_next (all branches)
            for _condition, target_id in node.conditional_next.items():
                if target_id not in visited:
                    queue.append(target_id)

        # Ensure denominator is at least 1 to avoid division by zero
        denominator = max(len(all_mandatory), 1)

        logger.debug(
            f"ReachabilityAnalyzer: {len(visited)} nodes reachable, "
            f"{len(all_mandatory)} unique mandatory actions"
        )

        return {
            "all_mandatory": all_mandatory,
            "denominator": denominator,
            "by_node": by_node,
            "reachable_nodes": visited,
        }

    def collect_all_applicable_mandatory(
        self,
        initial_state: Optional[PatientState] = None,
        entry_node: Optional[str] = None,
    ) -> Dict:
        """Structural reachability + clinical applicability filtering.

        Like collect_all_mandatory(), but filters out nodes whose
        entry_criteria are not met by the patient state.

        Args:
            initial_state: PatientState for applicability checks.
                If None, falls back to collect_all_mandatory().
            entry_node: Starting node. None uses graph.entry_node.

        Returns:
            dict with keys:
                - 'all_mandatory': Set[str] of applicable mandatory actions
                - 'denominator': int
                - 'by_node': Dict[str, List[str]]
                - 'reachable_nodes': Set[str]
                - 'excluded_nodes': Set[str] — nodes excluded by applicability
                - 'obligations': List[MandatoryObligation]
        """
        if initial_state is None:
            base = self.collect_all_mandatory(entry_node)
            base["excluded_nodes"] = set()
            base["obligations"] = []
            return base

        start = entry_node or self.graph.entry_node
        if start not in self.graph.nodes:
            logger.warning(f"Entry node '{start}' not in graph")
            return {
                "all_mandatory": set(),
                "denominator": 1,
                "by_node": {},
                "reachable_nodes": set(),
                "excluded_nodes": set(),
                "obligations": [],
            }

        visited: Set[str] = set()
        queue: deque = deque([(start, 0)])  # (node_id, depth)
        all_mandatory: Set[str] = set()
        by_node: Dict[str, List[str]] = {}
        excluded: Set[str] = set()
        obligations: list = []

        while queue:
            node_id, depth = queue.popleft()
            if node_id in visited:
                continue
            visited.add(node_id)

            node = self.graph.nodes.get(node_id)
            if node is None:
                continue

            # Build node_data dict for ApplicabilityFilter
            node_data = {}
            if hasattr(node, "entry_criteria") and node.entry_criteria:
                node_data["entry_criteria"] = node.entry_criteria
            if node.mandatory_actions:
                node_data["mandatory_actions"] = list(node.mandatory_actions)

            # Check clinical applicability
            if not ApplicabilityFilter.is_clinically_applicable(node_data, initial_state):
                excluded.add(node_id)
                # Still traverse children (structural reachability)
                for next_id in node.next_nodes:
                    if next_id not in visited:
                        queue.append((next_id, depth + 1))
                for _cond, target_id in node.conditional_next.items():
                    if target_id not in visited:
                        queue.append((target_id, depth + 1))
                continue

            # Applicable: collect mandatory_actions
            if node.mandatory_actions:
                by_node[node_id] = list(node.mandatory_actions)
                all_mandatory.update(node.mandatory_actions)
                for action in node.mandatory_actions:
                    obligations.append(MandatoryObligation(
                        action=action,
                        node=node_id,
                        depth=depth,
                        reachability_type="AF",
                        severity=getattr(node, "harm_severity", "moderate"),
                    ))

            for next_id in node.next_nodes:
                if next_id not in visited:
                    queue.append((next_id, depth + 1))
            for _cond, target_id in node.conditional_next.items():
                if target_id not in visited:
                    queue.append((target_id, depth + 1))

        denominator = max(len(all_mandatory), 1)

        logger.debug(
            f"ReachabilityAnalyzer(applicable): {len(visited)} nodes, "
            f"{len(excluded)} excluded, "
            f"{len(all_mandatory)} applicable mandatory actions"
        )

        return {
            "all_mandatory": all_mandatory,
            "denominator": denominator,
            "by_node": by_node,
            "reachable_nodes": visited,
            "excluded_nodes": excluded,
            "obligations": obligations,
        }
