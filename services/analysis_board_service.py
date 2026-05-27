import math
from typing import Dict, Any, List, Optional, Tuple
from pydantic import BaseModel
from mongoengine import QuerySet
from models.AnalysisBoard import AnalysisBoard, AnalysisNode
from models.Response import FormResponse
from services.base import BaseService
from schemas.analysis_board import AnalysisBoardSchema, AnalysisNodeSchema
from logger.unified_logger import app_logger, error_logger, audit_logger
from extensions import redis_client


class AnalysisBoardService(BaseService):
    def __init__(self):
        super().__init__(model=AnalysisBoard, schema=AnalysisBoardSchema)

    def execute_board(self, board_id: str, organization_id: str) -> Dict[str, Any]:
        """
        Executes the entire visual calculation nodes graph of an Analysis Board.
        Utilizes Redis-backed result caching, evicted on new form response events.
        """
        app_logger.info(
            f"Executing Analysis Board: {board_id} for org {organization_id}"
        )

        # 1. Check Redis Cache
        cache_key = f"analysis_board:cache:{organization_id}:{board_id}"
        try:
            cached = redis_client.get(cache_key)
            if cached:
                import json

                app_logger.info(
                    f"Returning cached execution results for board {board_id}"
                )
                return json.loads(cached)
        except Exception as cache_err:
            app_logger.warning(f"Failed to read Analysis Board cache: {cache_err}")

        # 2. Retrieve Board from DB
        board_doc = self.model.objects(
            id=board_id, organization_id=organization_id, is_deleted=False
        ).first()
        if not board_doc:
            from utils.exceptions import NotFoundError

            raise NotFoundError(f"Analysis Board {board_id} not found")

        # 3. Topological Sort of Nodes based on 'inputs' dependency graph
        nodes_dict = {str(node.id): node for node in board_doc.nodes}
        execution_order = self._resolve_topological_order(board_doc.nodes)

        # 4. Process Nodes in Sequence
        results = {}
        for node_id in execution_order:
            node = nodes_dict[node_id]
            try:
                results[node_id] = self._execute_single_node(
                    node, results, organization_id
                )
            except Exception as node_err:
                error_logger.error(
                    f"Error executing node {node.title} ({node_id}): {node_err}",
                    exc_info=True,
                )
                results[node_id] = {"error": str(node_err)}

        # 5. Cache Results
        try:
            import json

            redis_client.setex(cache_key, 3600, json.dumps(results))  # Cache for 1 hour
        except Exception as cache_err:
            app_logger.warning(f"Failed to set Analysis Board cache: {cache_err}")

        return results

    def clear_board_cache(self, board_id: str, organization_id: str):
        """Evict the cached results of this Analysis Board."""
        cache_key = f"analysis_board:cache:{organization_id}:{board_id}"
        try:
            redis_client.delete(cache_key)
            app_logger.info(f"Evicted cache for Analysis Board {board_id}")
        except Exception as err:
            app_logger.warning(f"Failed to clear Analysis Board cache: {err}")

    def _resolve_topological_order(self, nodes: List[AnalysisNode]) -> List[str]:
        """Performs a topological sort on calculation nodes based on their inputs dependencies."""
        graph = {}
        in_degree = {}

        # Initialize graph
        for node in nodes:
            nid = str(node.id)
            graph[nid] = []
            in_degree[nid] = 0

        # Build graph edges (inputs represent parent dependencies)
        for node in nodes:
            nid = str(node.id)
            for parent_id in node.inputs:
                pid = str(parent_id)
                if pid in graph:
                    graph[pid].append(nid)
                    in_degree[nid] += 1

        # Kahn's Algorithm
        queue = [nid for nid in in_degree if in_degree[nid] == 0]
        order = []

        while queue:
            curr = queue.pop(0)
            order.append(curr)
            for neighbor in graph[curr]:
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)

        if len(order) != len(nodes):
            # Circular dependency detected, fallback to standard database order
            app_logger.warning(
                "Circular dependency detected in calculation nodes graph! Falling back to raw list order."
            )
            return [str(node.id) for node in nodes]

        return order

    def _execute_single_node(
        self, node: AnalysisNode, resolved_parent_results: Dict[str, Any], org_id: str
    ) -> Any:
        """Runs the calculation logic for a single node."""
        func = node.function_id.upper()

        # Basic MongoDB aggregations
        DB_AGG_FUNCTIONS = {"SUM", "COUNT", "AVERAGE", "MIN", "MAX", "STD_DEV"}

        if func in DB_AGG_FUNCTIONS:
            return self._run_db_aggregation(node, org_id)

        elif func == "CORRELATION":
            return self._run_pearson_correlation(node, org_id)

        elif func == "FREQ_DIST":
            return self._run_frequency_distribution(node, org_id)

        # Graph calculations (linked formulas)
        elif func in ("RATIO", "DIFFERENCE", "PERCENT"):
            if not node.inputs or len(node.inputs) < 2:
                return {
                    "error": f"Function {func} requires at least 2 parent node inputs"
                }

            val_a = self._extract_node_value(
                resolved_parent_results.get(str(node.inputs[0]))
            )
            val_b = self._extract_node_value(
                resolved_parent_results.get(str(node.inputs[1]))
            )

            if val_a is None or val_b is None:
                return None

            if isinstance(val_a, dict) and "error" in val_a:
                return val_a
            if isinstance(val_b, dict) and "error" in val_b:
                return val_b

            try:
                if func == "RATIO":
                    return float(val_a) / float(val_b) if float(val_b) != 0.0 else None
                elif func == "DIFFERENCE":
                    return float(val_a) - float(val_b)
                elif func == "PERCENT":
                    return (
                        (float(val_a) / float(val_b)) * 100.0
                        if float(val_b) != 0.0
                        else None
                    )
            except Exception as calc_err:
                return {"error": f"Calculation error: {calc_err}"}

        return {"error": f"Unsupported function: {func}"}

    def _run_db_aggregation(self, node: AnalysisNode, org_id: str) -> Optional[float]:
        """Performs highly optimized Mongo aggregations on form responses."""
        match_query = {
            "form": node.target_form_id,
            "is_deleted": False,
            "organization_id": org_id,
        }
        # Mix in any segment pre-filters
        if node.filters:
            for key, val in node.filters.items():
                match_query[f"data.{key}"] = val

        pipeline = [{"$match": match_query}]

        func = node.function_id.upper()
        field = f"$data.{node.target_field_id}"

        # Map operator
        if func == "COUNT":
            op = {"$sum": 1}
        elif func == "SUM":
            op = {"$sum": {"$toDouble": field}}
        elif func == "AVERAGE":
            op = {"$avg": {"$toDouble": field}}
        elif func == "MIN":
            op = {"$min": {"$toDouble": field}}
        elif func == "MAX":
            op = {"$max": {"$toDouble": field}}
        elif func == "STD_DEV":
            op = {"$stdDevPop": {"$toDouble": field}}
        else:
            return None

        pipeline.append({"$group": {"_id": None, "result": op}})

        results = list(FormResponse.objects.aggregate(*pipeline))
        if not results:
            return 0.0 if func in ("COUNT", "SUM") else None

        return results[0].get("result")

    def _run_pearson_correlation(
        self, node: AnalysisNode, org_id: str
    ) -> Optional[float]:
        """Computes Pearson Correlation natively and efficiently over multiple numerical fields."""
        if not node.secondary_field_id:
            raise ValueError("Correlation function requires a secondary_field_id")

        match_query = {
            "form": node.target_form_id,
            "is_deleted": False,
            "organization_id": org_id,
        }
        if node.filters:
            for key, val in node.filters.items():
                match_query[f"data.{key}"] = val

        field_x = f"$data.{node.target_field_id}"
        field_y = f"$data.{node.secondary_field_id}"

        # Clean/filter out nulls, project numeric conversions
        pipeline = [
            {"$match": match_query},
            {"$project": {"x": {"$toDouble": field_x}, "y": {"$toDouble": field_y}}},
            {
                "$group": {
                    "_id": None,
                    "sum_x": {"$sum": "$x"},
                    "sum_y": {"$sum": "$y"},
                    "sum_x2": {"$sum": {"$multiply": ["$x", "$x"]}},
                    "sum_y2": {"$sum": {"$multiply": ["$y", "$y"]}},
                    "sum_xy": {"$sum": {"$multiply": ["$x", "$y"]}},
                    "n": {"$sum": 1},
                }
            },
        ]

        results = list(FormResponse.objects.aggregate(*pipeline))
        if not results:
            return None

        stats = results[0]
        n = stats["n"]
        if n < 2:
            return None  # mathematically undefined for n < 2

        sum_x = stats["sum_x"]
        sum_y = stats["sum_y"]
        sum_x2 = stats["sum_x2"]
        sum_y2 = stats["sum_y2"]
        sum_xy = stats["sum_xy"]

        numerator = (n * sum_xy) - (sum_x * sum_y)
        denominator_term = (n * sum_x2 - (sum_x**2)) * (n * sum_y2 - (sum_y**2))

        if denominator_term <= 0:
            return None

        r = numerator / math.sqrt(denominator_term)
        return round(r, 4)

    def _run_frequency_distribution(
        self, node: AnalysisNode, org_id: str
    ) -> Dict[str, int]:
        """Semantic word split occurrences counter inside textual form responses."""
        match_query = {
            "form": node.target_form_id,
            "is_deleted": False,
            "organization_id": org_id,
        }
        if node.filters:
            for key, val in node.filters.items():
                match_query[f"data.{key}"] = val

        # Project and unwind words using MongoDB split logic
        field = f"$data.{node.target_field_id}"
        pipeline = [
            {"$match": match_query},
            {"$project": {"words": {"$split": [{"$toLower": field}, " "]}}},
            {"$unwind": "$words"},
            {"$group": {"_id": "$words", "count": {"$sum": 1}}},
            {"$sort": {"count": -1}},
            {"$limit": 50},
        ]

        results = list(FormResponse.objects.aggregate(*pipeline))
        # Remove empty words, punctuation, etc.
        freq = {}
        for r in results:
            word = str(r["_id"]).strip(",.?!()\"';:")
            if word and len(word) > 2:  # skip extremely short stop-words
                freq[word] = freq.get(word, 0) + r["count"]

        return freq

    def _extract_node_value(self, result: Any) -> Optional[float]:
        """Gracefully resolves a float value from complex node result envelopes."""
        if result is None:
            return None
        if isinstance(result, (int, float)):
            return float(result)
        if isinstance(result, dict) and "result" in result:
            return float(result["result"])
        return None

    @classmethod
    def evict_caches_for_form(cls, form_id: str, organization_id: str):
        """
        Evicts cached results for all Analysis Boards targeting a specific form.
        """
        app_logger.info(
            f"Evicting Analysis Board caches for form {form_id} in org {organization_id}"
        )
        try:
            from models.AnalysisBoard import AnalysisBoard

            # Find all boards in the organization
            boards = AnalysisBoard.objects(
                organization_id=organization_id, is_deleted=False
            )
            evicted_count = 0
            for board in boards:
                # Check if any node in the board targets this form
                targets_form = any(
                    str(node.target_form_id) == str(form_id) for node in board.nodes
                )
                if targets_form:
                    cache_key = (
                        f"analysis_board:cache:{organization_id}:{str(board.id)}"
                    )
                    redis_client.delete(cache_key)
                    app_logger.info(
                        f"Evicted cache for Analysis Board {board.id} due to submission on form {form_id}"
                    )
                    evicted_count += 1
            app_logger.info(
                f"Evicted {evicted_count} analysis board caches for form {form_id}"
            )
        except Exception as e:
            error_logger.error(
                f"Failed to evict Analysis Board caches for form {form_id}: {e}",
                exc_info=True,
            )
