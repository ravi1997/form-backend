"""
engines/analysis_engine.py
DAG (Directed Acyclic Graph) execution engine for analysis pipelines.
Supports node-based workflows with proper execution ordering and error handling.
"""

import logging
import networkx as nx
from typing import Dict, Any, List, Optional, Set, Tuple
from datetime import datetime, timezone
from enum import Enum
from models.analysis import Analysis, AnalysisRun, AnalysisResult
from services.analysis_run_service import AnalysisRunService
from utils.exceptions import StateTransitionError, ValidationError
from logger.unified_logger import audit_logger, app_logger

logger = logging.getLogger(__name__)


class NodeStatus(Enum):
    """Node execution status."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class AnalysisEngine:
    """
    DAG execution engine for analysis pipelines.
    Handles node execution, dependency resolution, and error isolation.
    """

    def __init__(self):
        self.run_service = AnalysisRunService()
        self.node_executors = {
            # Data Sources
            "form_responses": self._execute_form_responses,
            "csv_upload": self._execute_csv_upload,
            "manual_data_entry": self._execute_manual_data_entry,
            "cross_form_join": self._execute_cross_form_join,
            "external_api_fetch": self._execute_external_api_fetch,
            
            # Transforms
            "filter": self._execute_filter,
            "sort": self._execute_sort,
            "group_by": self._execute_group_by,
            "join": self._execute_join,
            "calculate_column": self._execute_calculate_column,
            "pivot": self._execute_pivot,
            "unpivot": self._execute_unpivot,
            "rename_columns": self._execute_rename_columns,
            "select_columns": self._execute_select_columns,
            "deduplicate": self._execute_deduplicate,
            "fill_missing": self._execute_fill_missing,
            
            # Aggregations
            "count": self._execute_count,
            "sum": self._execute_sum,
            "average": self._execute_average,
            "min_max": self._execute_min_max,
            "median": self._execute_median,
            "percentile": self._execute_percentile,
            "frequency": self._execute_frequency,
            "cross_tabulation": self._execute_cross_tabulation,
            
            # Outputs
            "table_output": self._execute_table_output,
            "kpi_value": self._execute_kpi_value,
            "bar_chart_data": self._execute_bar_chart_data,
            "line_chart_data": self._execute_line_chart_data,
            "pie_chart_data": self._execute_pie_chart_data,
            "export_node": self._execute_export_node,
            
            # LLM Analysis
            "llm_analysis": self._execute_llm_analysis,
        }

    def validate_graph(self, graph: Dict[str, Any]) -> Tuple[bool, List[str]]:
        """
        Validate the analysis graph structure.
        
        Args:
            graph: Analysis graph with nodes and edges
            
        Returns:
            Tuple of (is_valid, error_messages)
        """
        errors = []
        
        try:
            # Check basic structure
            if not isinstance(graph, dict):
                errors.append("Graph must be a dictionary")
                return False, errors
                
            if 'nodes' not in graph or 'edges' not in graph:
                errors.append("Graph must contain 'nodes' and 'edges'")
                return False, errors
                
            nodes = graph['nodes']
            edges = graph['edges']
            
            if not isinstance(nodes, list) or not isinstance(edges, list):
                errors.append("Nodes and edges must be lists")
                return False, errors
            
            # Create NetworkX graph for validation
            G = nx.DiGraph()
            
            # Add nodes
            for node in nodes:
                if not isinstance(node, dict):
                    errors.append(f"Node must be a dictionary: {node}")
                    continue
                    
                if 'id' not in node:
                    errors.append(f"Node missing 'id': {node}")
                    continue
                    
                node_id = node['id']
                node_type = node.get('type')
                
                if not node_type:
                    errors.append(f"Node {node_id} missing 'type'")
                    continue
                    
                if node_type not in self.node_executors:
                    errors.append(f"Unknown node type: {node_type}")
                    continue
                
                G.add_node(node_id, **node)
            
            # Add edges
            for edge in edges:
                if not isinstance(edge, dict):
                    errors.append(f"Edge must be a dictionary: {edge}")
                    continue
                    
                if 'source' not in edge or 'target' not in edge:
                    errors.append(f"Edge missing 'source' or 'target': {edge}")
                    continue
                    
                source = edge['source']
                target = edge['target']
                
                if source not in G.nodes:
                    errors.append(f"Edge source node not found: {source}")
                    continue
                    
                if target not in G.nodes:
                    errors.append(f"Edge target node not found: {target}")
                    continue
                
                G.add_edge(source, target)
            
            # Check for cycles
            if not nx.is_directed_acyclic_graph(G):
                errors.append("Graph contains cycles")
                return False, errors
            
            # Check for disconnected nodes (except sources)
            all_nodes = set(G.nodes())
            source_nodes = {node for node, degree in G.in_degree() if degree == 0}
            sink_nodes = {node for node, degree in G.out_degree() if degree == 0}
            
            # All nodes should be reachable from source nodes
            for source_node in source_nodes:
                reachable = set(nx.descendants(G, source_node)) | {source_node}
                disconnected = all_nodes - reachable
                if disconnected:
                    errors.append(f"Nodes disconnected from source {source_node}: {disconnected}")
            
            # Must have at least one source and one sink
            if not source_nodes:
                errors.append("No source nodes found (nodes with no incoming edges)")
                
            if not sink_nodes:
                errors.append("No sink nodes found (nodes with no outgoing edges)")
            
            return len(errors) == 0, errors
            
        except Exception as e:
            logger.error(f"Graph validation error: {str(e)}", exc_info=True)
            errors.append(f"Validation error: {str(e)}")
            return False, errors

    def execute_analysis(
        self,
        analysis: Analysis,
        organization_id: str,
        trigger: str = "manual",
        triggered_by: str = None
    ) -> AnalysisRun:
        """
        Execute an analysis pipeline.
        
        Args:
            analysis: Analysis object to execute
            organization_id: Organization ID
            trigger: Trigger type ("manual", "scheduled", "reactive")
            triggered_by: User ID who triggered the execution
            
        Returns:
            AnalysisRun object with execution results
            
        Raises:
            ValidationError: If graph is invalid
            StateTransitionError: If execution fails
        """
        try:
            # Validate graph
            is_valid, errors = self.validate_graph(analysis.graph)
            if not is_valid:
                raise ValidationError(f"Invalid analysis graph: {'; '.join(errors)}")
            
            # Create analysis run
            run = self.run_service.create_run(
                analysis_id=str(analysis.id),
                organization_id=organization_id,
                trigger=trigger,
                triggered_by=triggered_by
            )
            
            # Execute the graph
            execution_context = {
                "run_id": str(run.id),
                "organization_id": organization_id,
                "analysis_id": str(analysis.id),
                "node_results": {},
                "node_errors": {},
                "execution_order": []
            }
            
            try:
                # Get execution order
                nodes = analysis.graph['nodes']
                edges = analysis.graph['edges']
                execution_order = self._get_execution_order(nodes, edges)
                
                # Execute nodes in order
                for node_batch in execution_order:
                    for node_id in node_batch:
                        self._execute_node(
                            node_id=node_id,
                            node_config=next(n for n in nodes if n['id'] == node_id),
                            execution_context=execution_context,
                            analysis=analysis
                        )
                
                # Update run status
                run.status = "completed"
                run.completed_at = datetime.now(timezone.utc)
                run.save()
                
                audit_logger.info(
                    f"AUDIT: Analysis {analysis.id} executed successfully, run {run.id}"
                )
                
                return run
                
            except Exception as e:
                # Update run status on failure
                run.status = "failed"
                run.completed_at = datetime.now(timezone.utc)
                run.error_summary = str(e)
                run.save()
                
                logger.error(f"Analysis execution failed for {analysis.id}: {str(e)}", exc_info=True)
                raise StateTransitionError(f"Analysis execution failed: {str(e)}")
                
        except Exception as e:
            logger.error(f"Failed to execute analysis {analysis.id}: {str(e)}", exc_info=True)
            raise

    def _get_execution_order(self, nodes: List[Dict], edges: List[Dict]) -> List[List[str]]:
        """
        Get execution order using topological sorting with parallel execution.
        
        Returns:
            List of node batches that can be executed in parallel
        """
        G = nx.DiGraph()
        
        # Add nodes
        for node in nodes:
            G.add_node(node['id'], **node)
        
        # Add edges
        for edge in edges:
            G.add_edge(edge['source'], edge['target'])
        
        # Get topological levels
        execution_order = []
        levels = {}
        
        # Calculate levels for each node
        for node in nx.topological_sort(G):
            if G.in_degree(node) == 0:
                levels[node] = 0
            else:
                levels[node] = max(levels[pred] for pred in G.predecessors(node)) + 1
        
        # Group nodes by level
        level_groups = {}
        for node, level in levels.items():
            if level not in level_groups:
                level_groups[level] = []
            level_groups[level].append(node)
        
        # Convert to list of batches
        max_level = max(level_groups.keys()) if level_groups else 0
        for level in range(max_level + 1):
            execution_order.append(level_groups.get(level, []))
        
        return execution_order

    def _execute_node(
        self,
        node_id: str,
        node_config: Dict[str, Any],
        execution_context: Dict[str, Any],
        analysis: Analysis
    ) -> None:
        """
        Execute a single node.
        """
        try:
            node_type = node_config['type']
            
            # Update node status
            if 'node_statuses' not in execution_context:
                execution_context['node_statuses'] = {}
            
            execution_context['node_statuses'][node_id] = {
                'status': NodeStatus.RUNNING.value,
                'started_at': datetime.now(timezone.utc).isoformat()
            }
            
            # Get input data from dependencies
            input_data = self._get_node_input_data(node_id, execution_context, analysis)
            
            # Execute node
            executor = self.node_executors.get(node_type)
            if not executor:
                raise ValueError(f"Unknown node type: {node_type}")
            
            result = executor(
                node_config=node_config,
                input_data=input_data,
                execution_context=execution_context,
                analysis=analysis
            )
            
            # Store result
            execution_context['node_results'][node_id] = result
            execution_context['node_statuses'][node_id]['status'] = NodeStatus.COMPLETED.value
            execution_context['node_statuses'][node_id]['completed_at'] = datetime.now(timezone.utc).isoformat()
            execution_context['execution_order'].append(node_id)
            
            logger.info(f"Successfully executed node {node_id} of type {node_type}")
            
        except Exception as e:
            # Store error
            if 'node_errors' not in execution_context:
                execution_context['node_errors'] = {}
            
            execution_context['node_errors'][node_id] = str(e)
            execution_context['node_statuses'][node_id]['status'] = NodeStatus.FAILED.value
            execution_context['node_statuses'][node_id]['error'] = str(e)
            
            logger.error(f"Failed to execute node {node_id}: {str(e)}", exc_info=True)
            raise

    def _get_node_input_data(
        self,
        node_id: str,
        execution_context: Dict[str, Any],
        analysis: Analysis
    ) -> Dict[str, Any]:
        """
        Get input data for a node from its dependencies.
        """
        input_data = {}
        
        # Find edges that target this node
        edges = analysis.graph['edges']
        incoming_edges = [edge for edge in edges if edge['target'] == node_id]
        
        for edge in incoming_edges:
            source_node = edge['source']
            port = edge.get('port', 'output')
            
            if source_node in execution_context['node_results']:
                input_data[port] = execution_context['node_results'][source_node]
            else:
                raise ValueError(f"Input data not found for node {source_node}")
        
        return input_data

    # Node Executors - Data Sources
    def _execute_form_responses(self, node_config, input_data, execution_context, analysis):
        """Execute form responses data source node."""
        try:
            form_id = node_config.get('config', {}).get('form_id')
            if not form_id:
                raise ValueError("Form ID is required for form responses node")
            
            from models.response import FormResponse
            from models.form import FormCommit
            
            # Get the production commit for the form
            form = Form.objects(id=form_id, is_deleted=False).first()
            if not form:
                raise ValueError(f"Form {form_id} not found")
            
            production_commit_id = form.branches.get(form.production_branch)
            if not production_commit_id:
                raise ValueError(f"Form {form_id} has no production version")
            
            # Query form responses
            responses = FormResponse.objects(
                form_id=form_id,
                commit_id=production_commit_id,
                status="submitted",
                is_deleted=False
            )
            
            # Apply filters if any
            filters = node_config.get('config', {}).get('filters', {})
            if filters:
                for field, value in filters.items():
                    if field.startswith('answers.'):
                        responses = responses.filter(**{f"answers__{field[8:]}__value": value})
                    else:
                        responses = responses.filter(**{field: value})
            
            # Convert to table format
            columns = []
            data = []
            
            # Get all unique answer keys from responses
            answer_keys = set()
            for response in responses:
                if response.answers:
                    for key in response.answers.keys():
                        answer_keys.add(key)
            
            # Build columns
            columns.extend([
                {"name": "id", "type": "string", "label": "Response ID"},
                {"name": "respondent_id", "type": "string", "label": "Respondent ID"},
                {"name": "submitted_at", "type": "datetime", "label": "Submitted At"},
                {"name": "is_anonymous", "type": "boolean", "label": "Anonymous"}
            ])
            
            for key in sorted(answer_keys):
                columns.append({"name": key, "type": "string", "label": key})
            
            # Build data rows
            for response in responses:
                row = {
                    "id": str(response.id),
                    "respondent_id": str(response.respondent_id) if response.respondent_id else "",
                    "submitted_at": response.submitted_at.isoformat() if response.submitted_at else "",
                    "is_anonymous": response.is_anonymous
                }
                
                if response.answers:
                    for key in answer_keys:
                        answer = response.answers.get(key)
                        if answer:
                            row[key] = answer.get('display_value', str(answer.get('value', '')))
                        else:
                            row[key] = ""
                
                data.append(row)
            
            return {
                "type": "table",
                "data": data,
                "columns": columns,
                "row_count": len(data)
            }
            
        except Exception as e:
            logger.error(f"Error executing form responses node: {str(e)}", exc_info=True)
            raise

    def _execute_csv_upload(self, node_config, input_data, execution_context, analysis):
        """Execute CSV upload data source node."""
        try:
            file_path = node_config.get('config', {}).get('file_path')
            if not file_path:
                raise ValueError("File path is required for CSV upload node")
            
            import pandas as pd
            import os
            
            if not os.path.exists(file_path):
                raise ValueError(f"File not found: {file_path}")
            
            # Read CSV file
            df = pd.read_csv(file_path)
            
            # Convert to table format
            columns = []
            for col in df.columns:
                dtype = str(df[col].dtype)
                if 'int' in dtype:
                    col_type = "number"
                elif 'float' in dtype:
                    col_type = "number"
                elif 'datetime' in dtype:
                    col_type = "datetime"
                elif 'bool' in dtype:
                    col_type = "boolean"
                else:
                    col_type = "string"
                
                columns.append({"name": col, "type": col_type, "label": col})
            
            # Convert data to records
            data = df.to_dict('records')
            
            return {
                "type": "table",
                "data": data,
                "columns": columns,
                "row_count": len(data)
            }
            
        except Exception as e:
            logger.error(f"Error executing CSV upload node: {str(e)}", exc_info=True)
            raise

    def _execute_manual_data_entry(self, node_config, input_data, execution_context, analysis):
        """Execute manual data entry node."""
        try:
            data = node_config.get('config', {}).get('data', [])
            columns = node_config.get('config', {}).get('columns', [])
            
            if not data or not columns:
                return {
                    "type": "table",
                    "data": [],
                    "columns": [],
                    "row_count": 0
                }
            
            return {
                "type": "table",
                "data": data,
                "columns": columns,
                "row_count": len(data)
            }
            
        except Exception as e:
            logger.error(f"Error executing manual data entry node: {str(e)}", exc_info=True)
            raise

    def _execute_cross_form_join(self, node_config, input_data, execution_context, analysis):
        """Execute cross-form join node."""
        try:
            form_ids = node_config.get('config', {}).get('form_ids', [])
            join_key = node_config.get('config', {}).get('join_key', 'id')
            
            if len(form_ids) < 2:
                raise ValueError("At least 2 form IDs are required for cross-form join")
            
            # Get responses for each form
            all_data = {}
            for form_id in form_ids:
                form_responses = self._execute_form_responses(
                    {'config': {'form_id': form_id}}, 
                    {}, 
                    execution_context, 
                    analysis
                )
                all_data[form_id] = form_responses
            
            # Perform join (simplified - in production, use proper join logic)
            if len(all_data) == 2:
                form1_id, form2_id = form_ids[:2]
                data1 = all_data[form1_id]['data']
                data2 = all_data[form2_id]['data']
                
                # Create join key dictionaries
                dict1 = {row[join_key]: row for row in data1 if join_key in row}
                dict2 = {row[join_key]: row for row in data2 if join_key in row}
                
                # Perform inner join
                joined_data = []
                for key in dict1:
                    if key in dict2:
                        joined_row = {**dict1[key], **dict2[key]}
                        joined_data.append(joined_row)
                
                # Combine columns
                columns1 = all_data[form1_id]['columns']
                columns2 = all_data[form2_id]['columns']
                
                # Remove duplicate join key columns
                columns = columns1 + [col for col in columns2 if col['name'] != join_key]
                
                return {
                    "type": "table",
                    "data": joined_data,
                    "columns": columns,
                    "row_count": len(joined_data)
                }
            else:
                # For more than 2 forms, return first form's data
                first_form_id = form_ids[0]
                return all_data[first_form_id]
                
        except Exception as e:
            logger.error(f"Error executing cross-form join node: {str(e)}", exc_info=True)
            raise

    def _execute_external_api_fetch(self, node_config, input_data, execution_context, analysis):
        """Execute external API fetch node."""
        try:
            import requests
            
            url = node_config.get('config', {}).get('url')
            method = node_config.get('config', {}).get('method', 'GET')
            headers = node_config.get('config', {}).get('headers', {})
            params = node_config.get('config', {}).get('params', {})
            body = node_config.get('config', {}).get('body', {})
            
            if not url:
                raise ValueError("URL is required for external API fetch")
            
            # Make API request
            response = requests.request(
                method=method,
                url=url,
                headers=headers,
                params=params,
                json=body if method in ['POST', 'PUT', 'PATCH'] else None,
                timeout=30
            )
            
            response.raise_for_status()
            data = response.json()
            
            # Try to convert to table format if it's a list of objects
            if isinstance(data, list) and data and isinstance(data[0], dict):
                # Extract columns from first item
                columns = []
                for key in data[0].keys():
                    columns.append({"name": key, "type": "string", "label": key})
                
                return {
                    "type": "table",
                    "data": data,
                    "columns": columns,
                    "row_count": len(data)
                }
            else:
                # Return as single value
                return {
                    "type": "value",
                    "value": data
                }
                
        except Exception as e:
            logger.error(f"Error executing external API fetch node: {str(e)}", exc_info=True)
            raise

    # Node Executors - Transforms
    def _execute_filter(self, node_config, input_data, execution_context, analysis):
        """Execute filter transform node."""
        try:
            input_table = input_data.get('output', {})
            if not input_table or 'data' not in input_table:
                raise ValueError("No input data provided to filter node")
            
            data = input_table['data']
            columns = input_table['columns']
            
            filter_conditions = node_config.get('config', {}).get('conditions', [])
            
            if not filter_conditions:
                return input_table
            
            filtered_data = []
            for row in data:
                include_row = True
                for condition in filter_conditions:
                    field = condition.get('field')
                    operator = condition.get('operator', 'equals')
                    value = condition.get('value')
                    
                    if field not in row:
                        include_row = False
                        break
                    
                    row_value = row[field]
                    
                    # Apply filter condition
                    if operator == 'equals':
                        if row_value != value:
                            include_row = False
                            break
                    elif operator == 'not_equals':
                        if row_value == value:
                            include_row = False
                            break
                    elif operator == 'contains':
                        if value not in str(row_value):
                            include_row = False
                            break
                    elif operator == 'greater_than':
                        try:
                            if float(row_value) <= float(value):
                                include_row = False
                                break
                        except (ValueError, TypeError):
                            include_row = False
                            break
                    elif operator == 'less_than':
                        try:
                            if float(row_value) >= float(value):
                                include_row = False
                                break
                        except (ValueError, TypeError):
                            include_row = False
                            break
                
                if include_row:
                    filtered_data.append(row)
            
            return {
                "type": "table",
                "data": filtered_data,
                "columns": columns,
                "row_count": len(filtered_data)
            }
            
        except Exception as e:
            logger.error(f"Error executing filter node: {str(e)}", exc_info=True)
            raise

    def _execute_sort(self, node_config, input_data, execution_context, analysis):
        """Execute sort transform node."""
        try:
            input_table = input_data.get('output', {})
            if not input_table or 'data' not in input_table:
                raise ValueError("No input data provided to sort node")
            
            data = input_table['data']
            columns = input_table['columns']
            
            sort_fields = node_config.get('config', {}).get('sort_fields', [])
            
            if not sort_fields:
                return input_table
            
            # Sort data
            def sort_key(row):
                key_parts = []
                for field_config in sort_fields:
                    field = field_config.get('field')
                    direction = field_config.get('direction', 'asc')
                    
                    value = row.get(field, '')
                    # Try to convert to number for numeric sorting
                    try:
                        value = float(value)
                    except (ValueError, TypeError):
                        pass
                    
                    if direction == 'desc':
                        value = -value if isinstance(value, (int, float)) else value
                    
                    key_parts.append(value)
                
                return tuple(key_parts)
            
            sorted_data = sorted(data, key=sort_key)
            
            return {
                "type": "table",
                "data": sorted_data,
                "columns": columns,
                "row_count": len(sorted_data)
            }
            
        except Exception as e:
            logger.error(f"Error executing sort node: {str(e)}", exc_info=True)
            raise

    def _execute_group_by(self, node_config, input_data, execution_context, analysis):
        """Execute group by transform node."""
        try:
            input_table = input_data.get('output', {})
            if not input_table or 'data' not in input_table:
                raise ValueError("No input data provided to group by node")
            
            data = input_table['data']
            columns = input_table['columns']
            
            group_fields = node_config.get('config', {}).get('group_fields', [])
            aggregations = node_config.get('config', {}).get('aggregations', [])
            
            if not group_fields:
                return input_table
            
            # Group data
            groups = {}
            for row in data:
                # Create group key
                group_key = tuple(row.get(field, '') for field in group_fields)
                
                if group_key not in groups:
                    groups[group_key] = []
                groups[group_key].append(row)
            
            # Apply aggregations
            result_data = []
            for group_key, group_rows in groups.items():
                result_row = {}
                
                # Add group fields
                for i, field in enumerate(group_fields):
                    result_row[field] = group_key[i]
                
                # Apply aggregations
                for agg in aggregations:
                    field = agg.get('field')
                    operation = agg.get('operation', 'count')
                    output_field = agg.get('output_field', f"{field}_{operation}")
                    
                    values = [row.get(field) for row in group_rows if field in row]
                    
                    if operation == 'count':
                        result_row[output_field] = len(values)
                    elif operation == 'sum':
                        try:
                            result_row[output_field] = sum(float(v) for v in values if v is not None)
                        except (ValueError, TypeError):
                            result_row[output_field] = 0
                    elif operation == 'average':
                        try:
                            numeric_values = [float(v) for v in values if v is not None]
                            result_row[output_field] = sum(numeric_values) / len(numeric_values) if numeric_values else 0
                        except (ValueError, TypeError, ZeroDivisionError):
                            result_row[output_field] = 0
                    elif operation == 'min':
                        try:
                            result_row[output_field] = min(float(v) for v in values if v is not None)
                        except (ValueError, TypeError):
                            result_row[output_field] = None
                    elif operation == 'max':
                        try:
                            result_row[output_field] = max(float(v) for v in values if v is not None)
                        except (ValueError, TypeError):
                            result_row[output_field] = None
                
                result_data.append(result_row)
            
            # Build result columns
            result_columns = []
            for field in group_fields:
                col_def = next((col for col in columns if col['name'] == field), 
                             {'name': field, 'type': 'string', 'label': field})
                result_columns.append(col_def)
            
            for agg in aggregations:
                output_field = agg.get('output_field', f"{agg.get('field')}_{agg.get('operation')}")
                result_columns.append({
                    'name': output_field,
                    'type': 'number',
                    'label': output_field
                })
            
            return {
                "type": "table",
                "data": result_data,
                "columns": result_columns,
                "row_count": len(result_data)
            }
            
        except Exception as e:
            logger.error(f"Error executing group by node: {str(e)}", exc_info=True)
            raise

    def _execute_join(self, node_config, input_data, execution_context, analysis):
        """Execute join transform node."""
        try:
            # This node expects multiple inputs (left and right tables)
            left_input = input_data.get('left', {})
            right_input = input_data.get('right', {})
            
            if not left_input or not right_input:
                raise ValueError("Join node requires both left and right inputs")
            
            left_data = left_input.get('data', [])
            right_data = right_input.get('data', [])
            left_columns = left_input.get('columns', [])
            right_columns = right_input.get('columns', [])
            
            join_type = node_config.get('config', {}).get('join_type', 'inner')
            left_key = node_config.get('config', {}).get('left_key')
            right_key = node_config.get('config', {}).get('right_key')
            
            if not left_key or not right_key:
                raise ValueError("Join keys are required")
            
            # Create dictionaries for faster lookup
            left_dict = {row[left_key]: row for row in left_data if left_key in row}
            right_dict = {row[right_key]: row for row in right_data if right_key in row}
            
            joined_data = []
            
            if join_type == 'inner':
                # Inner join
                for key in left_dict:
                    if key in right_dict:
                        joined_row = {**left_dict[key], **right_dict[key]}
                        joined_data.append(joined_row)
            elif join_type == 'left':
                # Left join
                for key in left_dict:
                    joined_row = {**left_dict[key]}
                    if key in right_dict:
                        joined_row.update(right_dict[key])
                    joined_data.append(joined_row)
            elif join_type == 'right':
                # Right join
                for key in right_dict:
                    joined_row = {**right_dict[key]}
                    if key in left_dict:
                        joined_row.update(left_dict[key])
                    joined_data.append(joined_row)
            elif join_type == 'full':
                # Full outer join
                all_keys = set(left_dict.keys()) | set(right_dict.keys())
                for key in all_keys:
                    joined_row = {}
                    if key in left_dict:
                        joined_row.update(left_dict[key])
                    if key in right_dict:
                        joined_row.update(right_dict[key])
                    joined_data.append(joined_row)
            
            # Combine columns, avoiding duplicates
            combined_columns = left_columns.copy()
            left_col_names = {col['name'] for col in left_columns}
            
            for col in right_columns:
                if col['name'] not in left_col_names:
                    combined_columns.append(col)
            
            return {
                "type": "table",
                "data": joined_data,
                "columns": combined_columns,
                "row_count": len(joined_data)
            }
            
        except Exception as e:
            logger.error(f"Error executing join node: {str(e)}", exc_info=True)
            raise

    def _execute_calculate_column(self, node_config, input_data, execution_context, analysis):
        """Execute calculate column transform node."""
        try:
            input_table = input_data.get('output', {})
            if not input_table or 'data' not in input_table:
                raise ValueError("No input data provided to calculate column node")
            
            data = input_table['data']
            columns = input_table['columns']
            
            calculations = node_config.get('config', {}).get('calculations', [])
            
            if not calculations:
                return input_table
            
            # Add new columns
            for calc in calculations:
                column_name = calc.get('column_name')
                expression = calc.get('expression')
                
                if not column_name or not expression:
                    continue
                
                # Add column definition
                columns.append({
                    'name': column_name,
                    'type': 'number',
                    'label': column_name
                })
                
                # Calculate values for each row
                for row in data:
                    try:
                        # Simple expression evaluation (in production, use proper expression parser)
                        result = self._evaluate_expression(expression, row)
                        row[column_name] = result
                    except Exception:
                        row[column_name] = None
            
            return {
                "type": "table",
                "data": data,
                "columns": columns,
                "row_count": len(data)
            }
            
        except Exception as e:
            logger.error(f"Error executing calculate column node: {str(e)}", exc_info=True)
            raise

    def _execute_pivot(self, node_config, input_data, execution_context, analysis):
        """Execute pivot transform node."""
        try:
            input_table = input_data.get('output', {})
            if not input_table or 'data' not in input_table:
                raise ValueError("No input data provided to pivot node")
            
            data = input_table['data']
            columns = input_table['columns']
            
            index_field = node_config.get('config', {}).get('index_field')
            columns_field = node_config.get('config', {}).get('columns_field')
            values_field = node_config.get('config', {}).get('values_field')
            aggregation = node_config.get('config', {}).get('aggregation', 'sum')
            
            if not all([index_field, columns_field, values_field]):
                raise ValueError("Index, columns, and values fields are required for pivot")
            
            # Group by index field
            pivot_data = {}
            for row in data:
                index_value = row.get(index_field, '')
                column_value = row.get(columns_field, '')
                value = row.get(values_field, 0)
                
                if index_value not in pivot_data:
                    pivot_data[index_value] = {}
                
                if column_value not in pivot_data[index_value]:
                    pivot_data[index_value][column_value] = []
                
                try:
                    numeric_value = float(value)
                    pivot_data[index_value][column_value].append(numeric_value)
                except (ValueError, TypeError):
                    pass
            
            # Apply aggregation
            result_data = []
            all_columns = set()
            
            for index_value, columns_dict in pivot_data.items():
                result_row = {index_field: index_value}
                
                for column_value, values in columns_dict.items():
                    all_columns.add(column_value)
                    
                    if aggregation == 'sum':
                        result_row[column_value] = sum(values)
                    elif aggregation == 'average':
                        result_row[column_value] = sum(values) / len(values) if values else 0
                    elif aggregation == 'count':
                        result_row[column_value] = len(values)
                    elif aggregation == 'min':
                        result_row[column_value] = min(values) if values else 0
                    elif aggregation == 'max':
                        result_row[column_value] = max(values) if values else 0
                
                result_data.append(result_row)
            
            # Build result columns
            result_columns = [
                {'name': index_field, 'type': 'string', 'label': index_field}
            ]
            
            for col in sorted(all_columns):
                result_columns.append({
                    'name': col,
                    'type': 'number',
                    'label': col
                })
            
            return {
                "type": "table",
                "data": result_data,
                "columns": result_columns,
                "row_count": len(result_data)
            }
            
        except Exception as e:
            logger.error(f"Error executing pivot node: {str(e)}", exc_info=True)
            raise

    def _execute_unpivot(self, node_config, input_data, execution_context, analysis):
        """Execute unpivot transform node."""
        try:
            input_table = input_data.get('output', {})
            if not input_table or 'data' not in input_table:
                raise ValueError("No input data provided to unpivot node")
            
            data = input_table['data']
            columns = input_table['columns']
            
            index_fields = node_config.get('config', {}).get('index_fields', [])
            value_fields = node_config.get('config', {}).get('value_fields', columns)
            variable_name = node_config.get('config', {}).get('variable_name', 'variable')
            value_name = node_config.get('config', {}).get('value_name', 'value')
            
            if not index_fields:
                raise ValueError("At least one index field is required for unpivot")
            
            unpivoted_data = []
            
            for row in data:
                for value_field in value_fields:
                    unpivoted_row = {}
                    
                    # Add index fields
                    for index_field in index_fields:
                        unpivoted_row[index_field] = row.get(index_field, '')
                    
                    # Add variable and value
                    unpivoted_row[variable_name] = value_field
                    unpivoted_row[value_name] = row.get(value_field, 0)
                    
                    unpivoted_data.append(univoted_row)
            
            # Build result columns
            result_columns = []
            for field in index_fields:
                col_def = next((col for col in columns if col['name'] == field), 
                             {'name': field, 'type': 'string', 'label': field})
                result_columns.append(col_def)
            
            result_columns.extend([
                {'name': variable_name, 'type': 'string', 'label': variable_name},
                {'name': value_name, 'type': 'number', 'label': value_name}
            ])
            
            return {
                "type": "table",
                "data": unpivoted_data,
                "columns": result_columns,
                "row_count": len(unpivoted_data)
            }
            
        except Exception as e:
            logger.error(f"Error executing unpivot node: {str(e)}", exc_info=True)
            raise

    def _execute_rename_columns(self, node_config, input_data, execution_context, analysis):
        """Execute rename columns transform node."""
        try:
            input_table = input_data.get('output', {})
            if not input_table or 'data' not in input_table:
                raise ValueError("No input data provided to rename columns node")
            
            data = input_table['data']
            columns = input_table['columns']
            
            column_mappings = node_config.get('config', {}).get('column_mappings', {})
            
            if not column_mappings:
                return input_table
            
            # Rename columns
            new_columns = []
            for col in columns:
                old_name = col['name']
                new_name = column_mappings.get(old_name, old_name)
                
                new_col = col.copy()
                new_col['name'] = new_name
                new_col['label'] = new_name
                new_columns.append(new_col)
            
            # Rename data keys
            new_data = []
            for row in data:
                new_row = {}
                for old_key, value in row.items():
                    new_key = column_mappings.get(old_key, old_key)
                    new_row[new_key] = value
                new_data.append(new_row)
            
            return {
                "type": "table",
                "data": new_data,
                "columns": new_columns,
                "row_count": len(new_data)
            }
            
        except Exception as e:
            logger.error(f"Error executing rename columns node: {str(e)}", exc_info=True)
            raise

    def _execute_select_columns(self, node_config, input_data, execution_context, analysis):
        """Execute select columns transform node."""
        try:
            input_table = input_data.get('output', {})
            if not input_table or 'data' not in input_table:
                raise ValueError("No input data provided to select columns node")
            
            data = input_table['data']
            columns = input_table['columns']
            
            selected_columns = node_config.get('config', {}).get('selected_columns', [])
            
            if not selected_columns:
                return input_table
            
            # Filter columns
            new_columns = [col for col in columns if col['name'] in selected_columns]
            
            # Filter data
            new_data = []
            for row in data:
                new_row = {key: value for key, value in row.items() if key in selected_columns}
                new_data.append(new_row)
            
            return {
                "type": "table",
                "data": new_data,
                "columns": new_columns,
                "row_count": len(new_data)
            }
            
        except Exception as e:
            logger.error(f"Error executing select columns node: {str(e)}", exc_info=True)
            raise

    def _execute_deduplicate(self, node_config, input_data, execution_context, analysis):
        """Execute deduplicate transform node."""
        try:
            input_table = input_data.get('output', {})
            if not input_table or 'data' not in input_table:
                raise ValueError("No input data provided to deduplicate node")
            
            data = input_table['data']
            columns = input_table['columns']
            
            deduplicate_fields = node_config.get('config', {}).get('deduplicate_fields', [])
            
            if not deduplicate_fields:
                # Remove completely duplicate rows
                seen = set()
                unique_data = []
                for row in data:
                    # Create tuple of all values for comparison
                    row_tuple = tuple(row.items())
                    if row_tuple not in seen:
                        seen.add(row_tuple)
                        unique_data.append(row)
                
                return {
                    "type": "table",
                    "data": unique_data,
                    "columns": columns,
                    "row_count": len(unique_data)
                }
            else:
                # Remove duplicates based on specified fields
                seen_values = set()
                unique_data = []
                
                for row in data:
                    # Create tuple of specified field values
                    key_values = tuple(row.get(field, '') for field in deduplicate_fields)
                    
                    if key_values not in seen_values:
                        seen_values.add(key_values)
                        unique_data.append(row)
                
                return {
                    "type": "table",
                    "data": unique_data,
                    "columns": columns,
                    "row_count": len(unique_data)
                }
            
        except Exception as e:
            logger.error(f"Error executing deduplicate node: {str(e)}", exc_info=True)
            raise

    def _execute_fill_missing(self, node_config, input_data, execution_context, analysis):
        """Execute fill missing transform node."""
        try:
            input_table = input_data.get('output', {})
            if not input_table or 'data' not in input_table:
                raise ValueError("No input data provided to fill missing node")
            
            data = input_table['data']
            columns = input_table['columns']
            
            fill_rules = node_config.get('config', {}).get('fill_rules', [])
            
            if not fill_rules:
                return input_table
            
            # Apply fill rules
            filled_data = []
            for row in data:
                filled_row = row.copy()
                
                for rule in fill_rules:
                    field = rule.get('field')
                    strategy = rule.get('strategy', 'value')
                    value = rule.get('value')
                    
                    if field in filled_row and (filled_row[field] is None or filled_row[field] == ''):
                        if strategy == 'value':
                            filled_row[field] = value
                        elif strategy == 'mean':
                            # Calculate mean of non-null values
                            values = [r.get(field) for r in data if r.get(field) is not None]
                            try:
                                numeric_values = [float(v) for v in values if v is not None]
                                if numeric_values:
                                    filled_row[field] = sum(numeric_values) / len(numeric_values)
                            except (ValueError, TypeError, ZeroDivisionError):
                                pass
                        elif strategy == 'median':
                            # Calculate median of non-null values
                            values = [r.get(field) for r in data if r.get(field) is not None]
                            try:
                                numeric_values = [float(v) for v in values if v is not None]
                                if numeric_values:
                                    sorted_values = sorted(numeric_values)
                                    n = len(sorted_values)
                                    median = sorted_values[n // 2] if n % 2 == 1 else (sorted_values[n // 2 - 1] + sorted_values[n // 2]) / 2
                                    filled_row[field] = median
                            except (ValueError, TypeError, IndexError):
                                pass
                        elif strategy == 'forward_fill':
                            # Use previous non-null value
                            prev_value = None
                            for prev_row in filled_data:
                                if field in prev_row and prev_row[field] is not None:
                                    prev_value = prev_row[field]
                                    break
                            if prev_value is not None:
                                filled_row[field] = prev_value
                
                filled_data.append(filled_row)
            
            return {
                "type": "table",
                "data": filled_data,
                "columns": columns,
                "row_count": len(filled_data)
            }
            
        except Exception as e:
            logger.error(f"Error executing fill missing node: {str(e)}", exc_info=True)
            raise

    # Node Executors - Aggregations
    def _execute_count(self, node_config, input_data, execution_context, analysis):
        """Execute count aggregation node."""
        try:
            input_table = input_data.get('output', {})
            if not input_table or 'data' not in input_table:
                return {"type": "value", "value": 0}
            
            data = input_table['data']
            count_field = node_config.get('config', {}).get('field')
            
            if count_field:
                # Count non-null values in specified field
                count = sum(1 for row in data if row.get(count_field) is not None)
            else:
                # Count all rows
                count = len(data)
            
            return {"type": "value", "value": count}
            
        except Exception as e:
            logger.error(f"Error executing count node: {str(e)}", exc_info=True)
            raise

    def _execute_sum(self, node_config, input_data, execution_context, analysis):
        """Execute sum aggregation node."""
        try:
            input_table = input_data.get('output', {})
            if not input_table or 'data' not in input_table:
                return {"type": "value", "value": 0}
            
            data = input_table['data']
            field = node_config.get('config', {}).get('field')
            
            if not field:
                raise ValueError("Field is required for sum aggregation")
            
            total = 0
            for row in data:
                value = row.get(field)
                if value is not None:
                    try:
                        total += float(value)
                    except (ValueError, TypeError):
                        pass
            
            return {"type": "value", "value": total}
            
        except Exception as e:
            logger.error(f"Error executing sum node: {str(e)}", exc_info=True)
            raise

    def _execute_average(self, node_config, input_data, execution_context, analysis):
        """Execute average aggregation node."""
        try:
            input_table = input_data.get('output', {})
            if not input_table or 'data' not in input_table:
                return {"type": "value", "value": 0}
            
            data = input_table['data']
            field = node_config.get('config', {}).get('field')
            
            if not field:
                raise ValueError("Field is required for average aggregation")
            
            values = []
            for row in data:
                value = row.get(field)
                if value is not None:
                    try:
                        values.append(float(value))
                    except (ValueError, TypeError):
                        pass
            
            if not values:
                return {"type": "value", "value": 0}
            
            average = sum(values) / len(values)
            return {"type": "value", "value": round(average, 6)}
            
        except Exception as e:
            logger.error(f"Error executing average node: {str(e)}", exc_info=True)
            raise

    def _execute_min_max(self, node_config, input_data, execution_context, analysis):
        """Execute min/max aggregation node."""
        try:
            input_table = input_data.get('output', {})
            if not input_table or 'data' not in input_table:
                return {"type": "value", "value": {"min": 0, "max": 0}}
            
            data = input_table['data']
            field = node_config.get('config', {}).get('field')
            
            if not field:
                raise ValueError("Field is required for min/max aggregation")
            
            values = []
            for row in data:
                value = row.get(field)
                if value is not None:
                    try:
                        values.append(float(value))
                    except (ValueError, TypeError):
                        pass
            
            if not values:
                return {"type": "value", "value": {"min": 0, "max": 0}}
            
            min_val = min(values)
            max_val = max(values)
            
            return {"type": "value", "value": {"min": min_val, "max": max_val}}
            
        except Exception as e:
            logger.error(f"Error executing min/max node: {str(e)}", exc_info=True)
            raise

    def _execute_median(self, node_config, input_data, execution_context, analysis):
        """Execute median aggregation node."""
        try:
            input_table = input_data.get('output', {})
            if not input_table or 'data' not in input_table:
                return {"type": "value", "value": 0}
            
            data = input_table['data']
            field = node_config.get('config', {}).get('field')
            
            if not field:
                raise ValueError("Field is required for median aggregation")
            
            values = []
            for row in data:
                value = row.get(field)
                if value is not None:
                    try:
                        values.append(float(value))
                    except (ValueError, TypeError):
                        pass
            
            if not values:
                return {"type": "value", "value": 0}
            
            sorted_values = sorted(values)
            n = len(sorted_values)
            
            if n % 2 == 1:
                median = sorted_values[n // 2]
            else:
                median = (sorted_values[n // 2 - 1] + sorted_values[n // 2]) / 2
            
            return {"type": "value", "value": round(median, 6)}
            
        except Exception as e:
            logger.error(f"Error executing median node: {str(e)}", exc_info=True)
            raise

    def _execute_percentile(self, node_config, input_data, execution_context, analysis):
        """Execute percentile aggregation node."""
        try:
            input_table = input_data.get('output', {})
            if not input_table or 'data' not in input_table:
                return {"type": "value", "value": 0}
            
            data = input_table['data']
            field = node_config.get('config', {}).get('field')
            percentile = node_config.get('config', {}).get('percentile', 50)
            
            if not field:
                raise ValueError("Field is required for percentile aggregation")
            
            if not 0 <= percentile <= 100:
                raise ValueError("Percentile must be between 0 and 100")
            
            values = []
            for row in data:
                value = row.get(field)
                if value is not None:
                    try:
                        values.append(float(value))
                    except (ValueError, TypeError):
                        pass
            
            if not values:
                return {"type": "value", "value": 0}
            
            sorted_values = sorted(values)
            n = len(sorted_values)
            
            if n == 0:
                return {"type": "value", "value": 0}
            
            # Calculate percentile index
            index = (percentile / 100) * (n - 1)
            
            if index.is_integer():
                percentile_value = sorted_values[int(index)]
            else:
                # Linear interpolation
                lower_index = int(index)
                upper_index = lower_index + 1
                weight = index - lower_index
                
                if upper_index >= n:
                    percentile_value = sorted_values[lower_index]
                else:
                    percentile_value = (sorted_values[lower_index] * (1 - weight) + 
                                     sorted_values[upper_index] * weight)
            
            return {"type": "value", "value": round(percentile_value, 6)}
            
        except Exception as e:
            logger.error(f"Error executing percentile node: {str(e)}", exc_info=True)
            raise

    def _execute_frequency(self, node_config, input_data, execution_context, analysis):
        """Execute frequency aggregation node."""
        try:
            input_table = input_data.get('output', {})
            if not input_table or 'data' not in input_table:
                return {"type": "table", "data": [], "columns": [], "row_count": 0}
            
            data = input_table['data']
            field = node_config.get('config', {}).get('field')
            
            if not field:
                raise ValueError("Field is required for frequency aggregation")
            
            # Count frequency of each value
            frequency = {}
            for row in data:
                value = row.get(field, '')
                if value is not None:
                    frequency[value] = frequency.get(value, 0) + 1
            
            # Convert to table format
            result_data = []
            for value, count in frequency.items():
                result_data.append({
                    'value': value,
                    'count': count,
                    'percentage': round(count / len(data) * 100, 2) if data else 0
                })
            
            # Sort by count (descending)
            result_data.sort(key=lambda x: x['count'], reverse=True)
            
            columns = [
                {'name': 'value', 'type': 'string', 'label': 'Value'},
                {'name': 'count', 'type': 'number', 'label': 'Count'},
                {'name': 'percentage', 'type': 'number', 'label': 'Percentage (%)'}
            ]
            
            return {
                "type": "table",
                "data": result_data,
                "columns": columns,
                "row_count": len(result_data)
            }
            
        except Exception as e:
            logger.error(f"Error executing frequency node: {str(e)}", exc_info=True)
            raise

    def _execute_cross_tabulation(self, node_config, input_data, execution_context, analysis):
        """Execute cross-tabulation aggregation node."""
        try:
            input_table = input_data.get('output', {})
            if not input_table or 'data' not in input_table:
                return {"type": "table", "data": [], "columns": [], "row_count": 0}
            
            data = input_table['data']
            row_field = node_config.get('config', {}).get('row_field')
            column_field = node_config.get('config', {}).get('column_field')
            value_field = node_config.get('config', {}).get('value_field', 'count')
            aggregation = node_config.get('config', {}).get('aggregation', 'count')
            
            if not row_field or not column_field:
                raise ValueError("Row and column fields are required for cross-tabulation")
            
            # Build cross-tabulation matrix
            cross_tab = {}
            row_values = set()
            column_values = set()
            
            for row in data:
                row_val = row.get(row_field, '')
                col_val = row.get(column_field, '')
                
                row_values.add(row_val)
                column_values.add(col_val)
                
                if row_val not in cross_tab:
                    cross_tab[row_val] = {}
                
                if col_val not in cross_tab[row_val]:
                    cross_tab[row_val][col_val] = []
                
                if aggregation == 'count':
                    cross_tab[row_val][col_val].append(1)
                else:
                    value = row.get(value_field, 0)
                    try:
                        numeric_value = float(value)
                        cross_tab[row_val][col_val].append(numeric_value)
                    except (ValueError, TypeError):
                        pass
            
            # Apply aggregation and build result
            result_data = []
            sorted_rows = sorted(row_values)
            sorted_cols = sorted(column_values)
            
            for row_val in sorted_rows:
                result_row = {'row': row_val}
                
                for col_val in sorted_cols:
                    values = cross_tab[row_val].get(col_val, [])
                    
                    if aggregation == 'count':
                        result_row[col_val] = len(values)
                    elif aggregation == 'sum':
                        result_row[col_val] = sum(values) if values else 0
                    elif aggregation == 'average':
                        result_row[col_val] = sum(values) / len(values) if values else 0
                    elif aggregation == 'min':
                        result_row[col_val] = min(values) if values else 0
                    elif aggregation == 'max':
                        result_row[col_val] = max(values) if values else 0
                
                result_data.append(result_row)
            
            # Build columns
            result_columns = [{'name': 'row', 'type': 'string', 'label': 'Row'}]
            for col_val in sorted_cols:
                result_columns.append({
                    'name': col_val,
                    'type': 'number',
                    'label': str(col_val)
                })
            
            return {
                "type": "table",
                "data": result_data,
                "columns": result_columns,
                "row_count": len(result_data)
            }
            
        except Exception as e:
            logger.error(f"Error executing cross-tabulation node: {str(e)}", exc_info=True)
            raise

    # Node Executors - Outputs
    def _execute_table_output(self, node_config, input_data, execution_context, analysis):
        """Execute table output node."""
        try:
            input_table = input_data.get('output', {})
            if not input_table:
                return {
                    "type": "table",
                    "data": [],
                    "columns": [],
                    "row_count": 0
                }
            
            return {
                "type": "table",
                "data": input_table.get('data', []),
                "columns": input_table.get('columns', []),
                "row_count": input_table.get('row_count', 0)
            }
            
        except Exception as e:
            logger.error(f"Error executing table output node: {str(e)}", exc_info=True)
            raise

    def _execute_kpi_value(self, node_config, input_data, execution_context, analysis):
        """Execute KPI value output node."""
        try:
            input_value = input_data.get('output', {})
            
            if isinstance(input_value, dict):
                value = input_value.get('value', 0)
            else:
                value = input_value if input_value is not None else 0
            
            # Apply formatting if specified
            format_config = node_config.get('config', {}).get('format', {})
            
            if format_config:
                decimal_places = format_config.get('decimal_places', 2)
                prefix = format_config.get('prefix', '')
                suffix = format_config.get('suffix', '')
                
                try:
                    value = float(value)
                    formatted_value = f"{prefix}{round(value, decimal_places)}{suffix}"
                    return {
                        "type": "value",
                        "value": value,
                        "formatted_value": formatted_value
                    }
                except (ValueError, TypeError):
                    pass
            
            return {"type": "value", "value": value}
            
        except Exception as e:
            logger.error(f"Error executing KPI value node: {str(e)}", exc_info=True)
            raise

    def _execute_bar_chart_data(self, node_config, input_data, execution_context, analysis):
        """Execute bar chart data output node."""
        try:
            input_table = input_data.get('output', {})
            if not input_table or 'data' not in input_table:
                return {
                    "type": "chart_data",
                    "chart_type": "bar",
                    "data": [],
                    "labels": []
                }
            
            data = input_table['data']
            label_field = node_config.get('config', {}).get('label_field')
            value_field = node_config.get('config', {}).get('value_field')
            
            if not label_field or not value_field:
                raise ValueError("Label and value fields are required for bar chart")
            
            # Extract chart data
            labels = []
            values = []
            
            for row in data:
                label = row.get(label_field, '')
                value = row.get(value_field, 0)
                
                try:
                    numeric_value = float(value)
                    labels.append(str(label))
                    values.append(numeric_value)
                except (ValueError, TypeError):
                    pass
            
            return {
                "type": "chart_data",
                "chart_type": "bar",
                "data": values,
                "labels": labels
            }
            
        except Exception as e:
            logger.error(f"Error executing bar chart data node: {str(e)}", exc_info=True)
            raise

    def _execute_line_chart_data(self, node_config, input_data, execution_context, analysis):
        """Execute line chart data output node."""
        try:
            input_table = input_data.get('output', {})
            if not input_table or 'data' not in input_table:
                return {
                    "type": "chart_data",
                    "chart_type": "line",
                    "data": [],
                    "labels": []
                }
            
            data = input_table['data']
            x_field = node_config.get('config', {}).get('x_field')
            y_field = node_config.get('config', {}).get('y_field')
            
            if not x_field or not y_field:
                raise ValueError("X and Y fields are required for line chart")
            
            # Sort data by X field for line chart
            sorted_data = sorted(data, key=lambda x: x.get(x_field, ''))
            
            # Extract chart data
            labels = []
            values = []
            
            for row in sorted_data:
                x_value = row.get(x_field, '')
                y_value = row.get(y_field, 0)
                
                try:
                    numeric_y = float(y_value)
                    labels.append(str(x_value))
                    values.append(numeric_y)
                except (ValueError, TypeError):
                    pass
            
            return {
                "type": "chart_data",
                "chart_type": "line",
                "data": values,
                "labels": labels
            }
            
        except Exception as e:
            logger.error(f"Error executing line chart data node: {str(e)}", exc_info=True)
            raise

    def _execute_pie_chart_data(self, node_config, input_data, execution_context, analysis):
        """Execute pie chart data output node."""
        try:
            input_table = input_data.get('output', {})
            if not input_table or 'data' not in input_table:
                return {
                    "type": "chart_data",
                    "chart_type": "pie",
                    "data": [],
                    "labels": []
                }
            
            data = input_table['data']
            label_field = node_config.get('config', {}).get('label_field')
            value_field = node_config.get('config', {}).get('value_field')
            
            if not label_field or not value_field:
                raise ValueError("Label and value fields are required for pie chart")
            
            # Extract chart data
            labels = []
            values = []
            
            for row in data:
                label = row.get(label_field, '')
                value = row.get(value_field, 0)
                
                try:
                    numeric_value = float(value)
                    if numeric_value > 0:  # Pie chart doesn't show negative values
                        labels.append(str(label))
                        values.append(numeric_value)
                except (ValueError, TypeError):
                    pass
            
            return {
                "type": "chart_data",
                "chart_type": "pie",
                "data": values,
                "labels": labels
            }
            
        except Exception as e:
            logger.error(f"Error executing pie chart data node: {str(e)}", exc_info=True)
            raise

    def _execute_export_node(self, node_config, input_data, execution_context, analysis):
        """Execute export node."""
        try:
            input_table = input_data.get('output', {})
            if not input_table:
                return {"type": "export", "status": "queued", "file_path": ""}
            
            export_format = node_config.get('config', {}).get('format', 'csv')
            filename = node_config.get('config', {}).get('filename', f"export_{execution_context['run_id']}")
            
            # Create export job
            from services.analysis_service import analysis_service
            
            export = analysis_service.create_export(
                analysis_id=execution_context['analysis_id'],
                organization_id=execution_context['organization_id'],
                format=export_format,
                created_by=execution_context.get('triggered_by')
            )
            
            return {
                "type": "export",
                "status": "queued",
                "export_id": str(export.id),
                "format": export_format,
                "filename": filename
            }
            
        except Exception as e:
            logger.error(f"Error executing export node: {str(e)}", exc_info=True)
            raise

    def _evaluate_expression(self, expression: str, row: Dict[str, Any]) -> Any:
        """Simple expression evaluator for calculate column node."""
        try:
            # Replace field references with actual values
            for field, value in row.items():
                if isinstance(value, (int, float)):
                    expression = expression.replace(f"{{{field}}}", str(value))
                else:
                    expression = expression.replace(f"{{{field}}}", f"'{value}'")
            
            # Simple safe evaluation (in production, use proper expression parser)
            allowed_names = {}
            allowed_values = {
                'abs': abs,
                'round': round,
                'min': min,
                'max': max,
                'sum': sum,
                'len': len
            }
            
            # Create safe namespace
            namespace = {**allowed_names, **allowed_values}
            
            # Evaluate expression
            result = eval(expression, {"__builtins__": {}}, namespace)
            return result
            
        except Exception as e:
            logger.warning(f"Error evaluating expression '{expression}': {e}")
            return None

    def _execute_llm_analysis(self, node_config, input_data, execution_context, analysis):
        """Execute LLM analysis node."""
        try:
            input_table = input_data.get('output', {})
            
            # Get LLM configuration
            llm_config = node_config.get('config', {})
            provider = llm_config.get('provider', 'openai')
            model_id = llm_config.get('model_id', 'gpt-4')
            prompt = llm_config.get('prompt', '')
            template_id = llm_config.get('template_id')
            temperature = llm_config.get('temperature', 0.7)
            max_tokens = llm_config.get('max_tokens', 1000)
            output_format = llm_config.get('output_format', 'text')
            variables = llm_config.get('variables', {})
            
            if not prompt:
                raise ValueError("Prompt is required for LLM analysis node")
            
            # Prepare input data for LLM
            if input_table and 'data' in input_table:
                # Convert table data to text format
                data_text = self._format_data_for_llm(input_table)
                variables['input_data'] = data_text
            else:
                variables['input_data'] = "No input data provided"
            
            # Get LLM service
            from services.llm_service import LLMService
            llm_service = LLMService()
            
            # Generate completion
            import asyncio
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
            try:
                result = loop.run_until_complete(
                    llm_service.generate_completion(
                        prompt=prompt,
                        provider=llm_service.LLMProvider(provider),
                        model_id=model_id,
                        temperature=temperature,
                        max_tokens=max_tokens,
                        template_id=template_id,
                        template_vars=variables,
                        user_id=execution_context.get('triggered_by'),
                        organization_id=execution_context['organization_id']
                    )
                )
            finally:
                loop.close()
            
            # Parse result based on output format
            content = result.get('content', '')
            
            if output_format == 'json':
                try:
                    parsed_content = json.loads(content)
                    return {
                        "type": "json",
                        "data": parsed_content,
                        "metadata": {
                            "provider": provider,
                            "model": model_id,
                            "usage": result.get('usage', {}),
                            "cost": result.get('cost', 0.0)
                        }
                    }
                except json.JSONDecodeError:
                    # Fallback to text if JSON parsing fails
                    return {
                        "type": "text",
                        "content": content,
                        "metadata": {
                            "provider": provider,
                            "model": model_id,
                            "usage": result.get('usage', {}),
                            "cost": result.get('cost', 0.0),
                            "parse_error": "Failed to parse JSON output"
                        }
                    }
            elif output_format == 'table':
                try:
                    # Try to parse as table data
                    table_data = self._parse_llm_table_response(content)
                    return {
                        "type": "table",
                        "data": table_data.get('data', []),
                        "columns": table_data.get('columns', []),
                        "row_count": len(table_data.get('data', [])),
                        "metadata": {
                            "provider": provider,
                            "model": model_id,
                            "usage": result.get('usage', {}),
                            "cost": result.get('cost', 0.0)
                        }
                    }
                except Exception:
                    # Fallback to text
                    return {
                        "type": "text",
                        "content": content,
                        "metadata": {
                            "provider": provider,
                            "model": model_id,
                            "usage": result.get('usage', {}),
                            "cost": result.get('cost', 0.0),
                            "parse_error": "Failed to parse table output"
                        }
                    }
            else:  # text format
                return {
                    "type": "text",
                    "content": content,
                    "metadata": {
                        "provider": provider,
                        "model": model_id,
                        "usage": result.get('usage', {}),
                        "cost": result.get('cost', 0.0)
                    }
                }
                
        except Exception as e:
            logger.error(f"Error executing LLM analysis node: {str(e)}", exc_info=True)
            raise

    def _format_data_for_llm(self, input_table: Dict[str, Any]) -> str:
        """Format table data for LLM consumption."""
        try:
            data = input_table.get('data', [])
            columns = input_table.get('columns', [])
            
            if not data:
                return "No data available"
            
            # Create header row
            header = " | ".join([col.get('label', col.get('name', '')) for col in columns])
            
            # Create data rows (limit to first 100 rows to avoid token limits)
            rows = []
            for row in data[:100]:
                row_values = []
                for col in columns:
                    col_name = col.get('name', '')
                    value = row.get(col_name, '')
                    row_values.append(str(value))
                rows.append(" | ".join(row_values))
            
            # Combine into table format
            table_text = f"{header}\n{'-' * len(header)}\n"
            table_text += "\n".join(rows)
            
            if len(data) > 100:
                table_text += f"\n\n... and {len(data) - 100} more rows"
            
            return table_text
            
        except Exception as e:
            logger.error(f"Error formatting data for LLM: {str(e)}", exc_info=True)
            return "Error formatting data"

    def _parse_llm_table_response(self, content: str) -> Dict[str, Any]:
        """Parse LLM response as table data."""
        try:
            # Try to parse as JSON first
            try:
                data = json.loads(content)
                if isinstance(data, dict) and 'data' in data and 'columns' in data:
                    return data
                elif isinstance(data, list):
                    # Assume it's a list of row objects
                    if data:
                        columns = []
                        first_row = data[0]
                        for key in first_row.keys():
                            columns.append({
                                'name': key,
                                'type': 'string',
                                'label': key.title()
                            })
                        return {
                            'data': data,
                            'columns': columns
                        }
            except json.JSONDecodeError:
                pass
            
            # Try to parse as markdown table
            lines = content.strip().split('\n')
            if len(lines) >= 3:
                # Check if it looks like a markdown table
                header_line = lines[0]
                separator_line = lines[1]
                
                if '|' in header_line and '|' in separator_line:
                    # Parse markdown table
                    headers = [h.strip() for h in header_line.split('|')[1:-1]]
                    columns = []
                    for header in headers:
                        columns.append({
                            'name': header.lower().replace(' ', '_'),
                            'type': 'string',
                            'label': header
                        })
                    
                    data = []
                    for line in lines[2:]:
                        if '|' in line:
                            values = [v.strip() for v in line.split('|')[1:-1]]
                            if len(values) == len(headers):
                                row = {}
                                for i, header in enumerate(headers):
                                    row[header.lower().replace(' ', '_')] = values[i]
                                data.append(row)
                    
                    if data:
                        return {
                            'data': data,
                            'columns': columns
                        }
            
            # If all parsing fails, return empty table
            return {
                'data': [],
                'columns': []
            }
            
        except Exception as e:
            logger.error(f"Error parsing LLM table response: {str(e)}", exc_info=True)
            return {
                'data': [],
                'columns': []
            }