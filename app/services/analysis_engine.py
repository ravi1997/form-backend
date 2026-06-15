from datetime import datetime
import json
from typing import List, Dict, Any, Optional
import networkx as nx
from celery import Celery
try:
    from models.Analysis import Analysis, Node, Edge, Graph
    from services.base import BaseService
except ImportError:  # pragma: no cover - fallback for package-style imports
    from ..models.Analysis import Analysis, Node, Edge, Graph
    from .base import BaseService
from services.llm_service import LLMService

# Configure Celery
celery_app = Celery('analysis_engine', broker='redis://localhost:6379/0')

class AnalysisEngineService(BaseService):
    """Service for DAG execution and analysis processing"""
    
    def __init__(self):
        super().__init__()
        self.node_registry = self._initialize_node_registry()
    
    def _initialize_node_registry(self) -> Dict[str, Dict]:
        """Initialize registry of built-in node types"""
        return {
            # Data Sources
            "form_responses": {
                "name": "Form Responses",
                "description": "Load form response data",
                "input_ports": [],
                "output_ports": [{"id": "output", "data_type": "dataframe"}],
                "handler": self._handle_form_responses
            },
            "csv_upload": {
                "name": "CSV Upload", 
                "description": "Upload and parse CSV data",
                "input_ports": [],
                "output_ports": [{"id": "output", "data_type": "dataframe"}],
                "handler": self._handle_csv_upload
            },
            "manual_data_entry": {
                "name": "Manual Data Entry",
                "description": "Inline data table editor",
                "input_ports": [],
                "output_ports": [{"id": "output", "data_type": "dataframe"}],
                "handler": self._handle_manual_data_entry
            },
            "llm_prompt": {
                "name": "LLM Prompt",
                "description": "Generate structured output from a prompt and table context",
                "input_ports": [{"id": "input", "data_type": "dataframe"}],
                "output_ports": [{"id": "output", "data_type": "json"}],
                "handler": self._handle_llm_prompt
            },
            
            # Transforms
            "filter": {
                "name": "Filter",
                "description": "Filter rows by condition",
                "input_ports": [{"id": "input", "data_type": "dataframe"}],
                "output_ports": [{"id": "output", "data_type": "dataframe"}],
                "handler": self._handle_filter
            },
            "sort": {
                "name": "Sort",
                "description": "Sort rows by column(s)",
                "input_ports": [{"id": "input", "data_type": "dataframe"}],
                "output_ports": [{"id": "output", "data_type": "dataframe"}],
                "handler": self._handle_sort
            },
            "group_by": {
                "name": "Group By",
                "description": "Group rows + aggregate",
                "input_ports": [{"id": "input", "data_type": "dataframe"}],
                "output_ports": [{"id": "output", "data_type": "dataframe"}],
                "handler": self._handle_group_by
            },
            
            # Outputs
            "table_output": {
                "name": "Table Output",
                "description": "Render a data table",
                "input_ports": [{"id": "input", "data_type": "dataframe"}],
                "output_ports": [],
                "handler": self._handle_table_output
            },
            "kpi_value": {
                "name": "KPI Value",
                "description": "Single numeric KPI",
                "input_ports": [{"id": "input", "data_type": "dataframe"}],
                "output_ports": [],
                "handler": self._handle_kpi_value
            }
        }
    
    def validate_graph(self, graph: Graph) -> Dict[str, Any]:
        """Validate analysis graph for cycles and connectivity"""
        try:
            # Build NetworkX graph
            G = nx.DiGraph()
            
            # Add nodes
            for node in graph.nodes:
                G.add_node(node.id, **node.dict())
            
            # Add edges
            for edge in graph.edges:
                G.add_edge(edge.from_node, edge.to_node, **edge.dict())
            
            # Check for cycles
            if not nx.is_directed_acyclic_graph(G):
                cycles = list(nx.simple_cycles(G))
                return {
                    "valid": False,
                    "error": "Cycle detected",
                    "cycles": cycles
                }
            
            # Check connectivity
            if not nx.is_weakly_connected(G):
                return {
                    "valid": False,
                    "error": "Disconnected graph"
                }
            
            # Get topological order
            try:
                topo_order = list(nx.topological_sort(G))
            except nx.NetworkXError:
                return {
                    "valid": False,
                    "error": "Cannot determine topological order"
                }
            
            return {
                "valid": True,
                "topological_order": topo_order,
                "graph": G
            }
            
        except Exception as e:
            return {
                "valid": False,
                "error": str(e)
            }
    
    @celery_app.task
    def execute_analysis(self, analysis_id: str, run_id: str = None) -> Dict[str, Any]:
        """Execute an analysis graph"""
        from ..models.AnalysisRun import AnalysisRun
        from ..models.AnalysisResult import AnalysisResult
        
        # Get analysis
        analysis = self.db.analyses.find_one({"_id": analysis_id})
        if not analysis:
            raise ValueError(f"Analysis {analysis_id} not found")
        
        # Validate graph
        validation = self.validate_graph(analysis["graph"])
        if not validation["valid"]:
            raise ValueError(f"Invalid graph: {validation['error']}")
        
        # Create analysis run
        if not run_id:
            from bson.objectid import ObjectId
            run_id = str(ObjectId())
        
        analysis_run = AnalysisRun(
            analysis_id=analysis_id,
            org_id=analysis["org_id"],
            trigger="manual",
            triggered_by="system",
            status="running",
            started_at=datetime.now(),
            celery_task_id=execute_analysis.request.id
        )
        
        self.db.analysis_runs.insert_one(analysis_run.dict())
        
        try:
            # Execute nodes in topological order
            G = validation["graph"]
            topo_order = validation["topological_order"]
            
            node_results = {}
            
            for node_id in topo_order:
                node_data = G.nodes[node_id]
                node_type = node_data.get("type")
                
                # Get node handler
                node_info = self.node_registry.get(node_type)
                if not node_info:
                    raise ValueError(f"Unknown node type: {node_type}")
                
                # Execute node
                handler = node_info["handler"]
                result = handler(node_data, node_results)
                
                node_results[node_id] = {
                    "status": "completed",
                    "started_at": datetime.now(),
                    "completed_at": datetime.now(),
                    "result": result
                }
                
                # Store result if output node
                if not node_info.get("output_ports"):
                    analysis_result = AnalysisResult(
                        run_id=run_id,
                        analysis_id=analysis_id,
                        org_id=analysis["org_id"],
                        node_id=node_id,
                        output_type="dataframe",
                        data=result,
                        row_count=len(result) if isinstance(result, list) else 1,
                        column_definitions=self._get_column_definitions(result)
                    )
                    
                    self.db.analysis_results.insert_one(analysis_result.dict())
            
            # Update analysis run status
            self.db.analysis_runs.update_one(
                {"_id": run_id},
                {
                    "$set": {
                        "status": "completed",
                        "completed_at": datetime.now(),
                        "node_statuses": node_results
                    }
                }
            )
            
            # Update analysis last run
            self.db.analyses.update_one(
                {"_id": analysis_id},
                {"$set": {"last_run_id": run_id}}
            )
            
            return {
                "status": "completed",
                "run_id": run_id,
                "node_results": node_results
            }
            
        except Exception as e:
            # Update analysis run status to failed
            self.db.analysis_runs.update_one(
                {"_id": run_id},
                {
                    "$set": {
                        "status": "failed",
                        "completed_at": datetime.now(),
                        "error_summary": str(e)
                    }
                }
            )
            
            raise
    
    def _handle_form_responses(self, node_data: Dict, context: Dict) -> List[Dict]:
        """Handle form responses data source node"""
        form_id = node_data.get("properties", {}).get("form_id")
        if not form_id:
            raise ValueError("Form ID required for form responses node")
        
        # Get form responses
        responses = self.db.form_responses.find({"form_id": form_id})
        
        # Convert to list of dictionaries
        result = []
        for response in responses:
            result.append({
                "response_id": str(response["_id"]),
                "submitted_at": response.get("submitted_at"),
                "answers": response.get("answers", {})
            })
        
        return result
    
    def _handle_csv_upload(self, node_data: Dict, context: Dict) -> List[Dict]:
        """Handle CSV upload data source node"""
        # Simplified implementation
        return [{"id": 1, "name": "Sample Data", "value": 100}]
    
    def _handle_manual_data_entry(self, node_data: Dict, context: Dict) -> List[Dict]:
        """Handle manual data entry data source node"""
        data = node_data.get("properties", {}).get("data", [])
        return data

    def _handle_llm_prompt(self, node_data: Dict, context: Dict) -> Dict[str, Any]:
        """Handle LLM prompt transform node."""
        input_key = node_data.get("input_ports", [{}])[0].get("input")
        input_data = context.get(input_key) if input_key else None
        properties = node_data.get("properties", {})
        prompt_template = properties.get("prompt_template")
        if not prompt_template:
            raise ValueError("prompt_template is required for llm_prompt nodes")

        context_rows = input_data or properties.get("data", []) or []
        context_text = json.dumps(context_rows, default=str, indent=2)[:12000]
        prompt = prompt_template.format(
            data=context_text,
            title=node_data.get("title", "LLM Prompt"),
            config=json.dumps(properties.get("config", {}), default=str),
        )
        raw_result = LLMService.generate_text(prompt, context_text)

        parsed = raw_result
        if isinstance(raw_result, str):
            try:
                parsed = json.loads(raw_result)
            except Exception:
                parsed = {"text": raw_result}

        return {
            "type": "llm",
            "prompt": prompt,
            "input_rows": len(context_rows) if isinstance(context_rows, list) else 0,
            "result": parsed,
        }
    
    def _handle_filter(self, node_data: Dict, context: Dict) -> List[Dict]:
        """Handle filter transform node"""
        input_data = context.get(node_data.get("input_ports", [{}])[0].get("input"))
        if not input_data:
            return []
        
        # Get filter conditions
        conditions = node_data.get("properties", {}).get("conditions", [])
        
        # Apply filters (simplified)
        filtered_data = []
        for item in input_data:
            include = True
            for condition in conditions:
                field = condition.get("field")
                operator = condition.get("operator", "equals")
                value = condition.get("value")
                
                if field in item:
                    item_value = item[field]
                    if operator == "equals" and item_value != value:
                        include = False
                        break
                    elif operator == "not_equals" and item_value == value:
                        include = False
                        break
            
            if include:
                filtered_data.append(item)
        
        return filtered_data
    
    def _handle_sort(self, node_data: Dict, context: Dict) -> List[Dict]:
        """Handle sort transform node"""
        input_data = context.get(node_data.get("input_ports", [{}])[0].get("input"))
        if not input_data:
            return []
        
        # Get sort configuration
        sort_by = node_data.get("properties", {}).get("sort_by", [])
        
        # Sort data
        sorted_data = sorted(input_data, key=lambda x: [
            x.get(field, "") for field in sort_by
        ])
        
        return sorted_data
    
    def _handle_group_by(self, node_data: Dict, context: Dict) -> List[Dict]:
        """Handle group by transform node"""
        input_data = context.get(node_data.get("input_ports", [{}])[0].get("input"))
        if not input_data:
            return []
        
        # Get group configuration
        group_by = node_data.get("properties", {}).get("group_by", [])
        aggregates = node_data.get("properties", {}).get("aggregates", [])
        
        # Group data (simplified)
        groups = {}
        for item in input_data:
            key = tuple(item.get(field, "") for field in group_by)
            if key not in groups:
                groups[key] = []
            groups[key].append(item)
        
        # Apply aggregates
        result = []
        for key, items in groups.items():
            group_result = {field: value for field, value in zip(group_by, key)}
            
            for aggregate in aggregates:
                field = aggregate.get("field")
                operation = aggregate.get("operation", "count")
                
                if operation == "count":
                    group_result[f"{field}_count"] = len(items)
                elif operation == "sum":
                    values = [item.get(field, 0) for item in items]
                    group_result[f"{field}_sum"] = sum(values)
                elif operation == "average":
                    values = [item.get(field, 0) for item in items]
                    group_result[f"{field}_avg"] = sum(values) / len(values) if values else 0
            
            result.append(group_result)
        
        return result
    
    def _handle_table_output(self, node_data: Dict, context: Dict) -> Dict:
        """Handle table output node"""
        input_data = context.get(node_data.get("input_ports", [{}])[0].get("input"))
        
        return {
            "type": "table",
            "data": input_data,
            "columns": self._get_column_definitions(input_data)
        }
    
    def _handle_kpi_value(self, node_data: Dict, context: Dict) -> Dict:
        """Handle KPI value output node"""
        input_data = context.get(node_data.get("input_ports", [{}])[0].get("input"))
        
        # Get KPI configuration
        field = node_data.get("properties", {}).get("field")
        operation = node_data.get("properties", {}).get("operation", "sum")
        
        if not input_data or not field:
            return {"value": 0}
        
        values = [item.get(field, 0) for item in input_data]
        
        if operation == "sum":
            value = sum(values)
        elif operation == "average":
            value = sum(values) / len(values) if values else 0
        elif operation == "count":
            value = len(values)
        else:
            value = 0
        
        return {
            "type": "kpi",
            "value": value,
            "field": field,
            "operation": operation
        }
    
    def _get_column_definitions(self, data: List[Dict]) -> List[Dict]:
        """Get column definitions from data"""
        if not data:
            return []
        
        columns = []
        sample_item = data[0]
        
        for key, value in sample_item.items():
            columns.append({
                "name": key,
                "type": type(value).__name__,
                "label": key.replace("_", " ").title()
            })
        
        return columns
