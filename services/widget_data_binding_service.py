"""
services/widget_data_binding_service.py
Widget data binding service to analysis outputs.
"""

from models.dashboard import DashboardWidget, Dashboard
from models.analysis import Analysis, AnalysisResults
from services.base import BaseService
from schemas.base import InboundPayloadSchema
from pydantic import BaseModel, Field, validator
from typing import List, Optional, Dict, Any, Union
from datetime import datetime, timezone
from logger.unified_logger import app_logger, error_logger, audit_logger
import uuid


class WidgetDataBindingSchema(BaseModel, InboundPayloadSchema):
    widget_id: str
    analysis_id: str
    node_id: str
    widget_type: str
    config: Dict[str, Any] = Field(default_factory=dict)
    filters: Dict[str, Any] = Field(default_factory=dict)
    transformations: List[Dict[str, Any]] = Field(default_factory=list)


class BoundDataSchema(BaseModel):
    widget_id: str
    analysis_id: str
    node_id: str
    data: Any
    metadata: Dict[str, Any] = Field(default_factory=dict)
    timestamp: str
    data_type: str = "raw"


class WidgetDataBindingService(BaseService):
    """Service for managing widget data binding to analysis outputs."""

    def __init__(self):
        super().__init__(model=DashboardWidget, schema=WidgetDataBindingSchema)

    def validate_binding(self, binding_data: WidgetDataBindingSchema, organization_id: str) -> bool:
        """Validate that the data binding is valid."""
        app_logger.debug(f"Entering validate_binding: widget {binding_data.widget_id}")
        
        try:
            # Check if analysis exists and belongs to organization
            analysis = Analysis.objects(
                id=binding_data.analysis_id,
                organization_id=organization_id,
                is_deleted=False
            ).first()
            
            if not analysis:
                from .exceptions import NotFoundError
                app_logger.warning(f"Analysis not found for binding: {binding_data.analysis_id}")
                raise NotFoundError(f"Analysis {binding_data.analysis_id} not found")
            
            # Check if node exists in analysis
            if not self._node_exists_in_analysis(analysis, binding_data.node_id):
                from .exceptions import ValidationError
                app_logger.warning(f"Node not found in analysis: {binding_data.node_id}")
                raise ValidationError(f"Node {binding_data.node_id} not found in analysis {binding_data.analysis_id}")
            
            # Validate widget type compatibility with node output
            self._validate_widget_node_compatibility(binding_data.widget_type, analysis, binding_data.node_id)
            
            app_logger.debug(f"Exiting validate_binding: widget {binding_data.widget_id} successfully")
            return True
            
        except Exception as e:
            if not isinstance(e, (NotFoundError, ValidationError)):
                error_logger.error(
                    f"Error in validate_binding {binding_data.widget_id}: {str(e)}", exc_info=True
                )
            raise

    def _node_exists_in_analysis(self, analysis: Analysis, node_id: str) -> bool:
        """Check if a node exists in the analysis graph."""
        if not analysis.graph or 'nodes' not in analysis.graph:
            return False
        
        for node in analysis.graph['nodes']:
            if node.get('id') == node_id:
                return True
        
        return False

    def _validate_widget_node_compatibility(self, widget_type: str, analysis: Analysis, node_id: str) -> bool:
        """Validate that widget type is compatible with node output type."""
        # Find the node in the analysis graph
        node = None
        for n in analysis.graph.get('nodes', []):
            if n.get('id') == node_id:
                node = n
                break
        
        if not node:
            from .exceptions import ValidationError
            raise ValidationError(f"Node {node_id} not found in analysis")
        
        # Get node output type
        node_type = node.get('type', '')
        output_ports = node.get('output_ports', [])
        
        # Define compatibility matrix
        compatibility = {
            'kpi_card': ['value', 'number', 'count', 'sum', 'average'],
            'bar_chart': ['table', 'dataframe', 'array'],
            'line_chart': ['table', 'dataframe', 'array', 'time_series'],
            'pie_chart': ['table', 'dataframe', 'array'],
            'data_table': ['table', 'dataframe', 'array'],
            'text': ['any'],  # Text widgets can display any data
            'image': ['image_url', 'binary_image'],
            'filter': ['categorical', 'text', 'date']
        }
        
        # Check if widget type is supported
        if widget_type not in compatibility:
            from .exceptions import ValidationError
            raise ValidationError(f"Unsupported widget type: {widget_type}")
        
        # For now, assume compatibility (can be enhanced later)
        app_logger.debug(f"Widget type {widget_type} compatible with node {node_id}")
        return True

    def bind_widget_to_analysis(self, binding_data: WidgetDataBindingSchema, organization_id: str) -> Dict[str, Any]:
        """Bind a widget to an analysis output."""
        app_logger.debug(f"Entering bind_widget_to_analysis: widget {binding_data.widget_id}")
        
        try:
            # Validate binding first
            self.validate_binding(binding_data, organization_id)
            
            # Find the widget in the dashboard
            dashboard = Dashboard.objects(
                organization_id=organization_id,
                is_deleted=False
            ).first()
            
            if not dashboard:
                from .exceptions import NotFoundError
                app_logger.warning(f"No dashboard found for widget binding: {binding_data.widget_id}")
                raise NotFoundError("No dashboard found for widget binding")
            
            # Find the widget
            widget = None
            for w in dashboard.widgets or []:
                if w.id == binding_data.widget_id:
                    widget = w
                    break
            
            if not widget:
                from .exceptions import NotFoundError
                app_logger.warning(f"Widget not found for binding: {binding_data.widget_id}")
                raise NotFoundError(f"Widget {binding_data.widget_id} not found")
            
            # Update widget data source
            if not widget.data_source:
                from models.dashboard import WidgetDataSource
                widget.data_source = WidgetDataSource()
            
            widget.data_source.analysis_id = binding_data.analysis_id
            widget.data_source.node_id = binding_data.node_id
            widget.data_source.filters = binding_data.filters
            widget.data_source.transformations = binding_data.transformations
            
            # Update widget config if provided
            if binding_data.config:
                if not widget.config:
                    from models.dashboard import WidgetConfig
                    widget.config = WidgetConfig()
                
                for key, value in binding_data.config.items():
                    if hasattr(widget.config, key):
                        setattr(widget.config, key, value)
            
            dashboard.save()
            
            audit_logger.info(
                f"Audit: widget bound to analysis {binding_data.widget_id} -> {binding_data.analysis_id}:{binding_data.node_id}"
            )
            
            result = {
                "widget_id": widget.id,
                "analysis_id": str(widget.data_source.analysis_id),
                "node_id": widget.data_source.node_id,
                "widget_type": widget.widget_type,
                "binding_status": "bound",
                "bound_at": datetime.now(timezone.utc).isoformat()
            }
            
            app_logger.debug(f"Exiting bind_widget_to_analysis: widget {binding_data.widget_id} successfully")
            return result
            
        except Exception as e:
            if not isinstance(e, (NotFoundError, ValidationError)):
                error_logger.error(
                    f"Error in bind_widget_to_analysis {binding_data.widget_id}: {str(e)}", exc_info=True
                )
            raise

    def unbind_widget(self, widget_id: str, organization_id: str) -> bool:
        """Unbind a widget from its analysis."""
        app_logger.debug(f"Entering unbind_widget: {widget_id} (org: {organization_id})")
        
        try:
            # Find the dashboard containing the widget
            dashboard = Dashboard.objects(
                organization_id=organization_id,
                is_deleted=False
            ).first()
            
            if not dashboard:
                from .exceptions import NotFoundError
                app_logger.warning(f"No dashboard found for widget unbinding: {widget_id}")
                raise NotFoundError("No dashboard found for widget unbinding")
            
            # Find the widget
            widget = None
            for w in dashboard.widgets or []:
                if w.id == widget_id:
                    widget = w
                    break
            
            if not widget:
                from .exceptions import NotFoundError
                app_logger.warning(f"Widget not found for unbinding: {widget_id}")
                raise NotFoundError(f"Widget {widget_id} not found")
            
            # Clear data source
            if widget.data_source:
                widget.data_source.analysis_id = None
                widget.data_source.node_id = None
                widget.data_source.filters = {}
                widget.data_source.transformations = []
            
            dashboard.save()
            
            audit_logger.info(
                f"Audit: widget unbound from analysis {widget_id}"
            )
            
            app_logger.debug(f"Exiting unbind_widget: {widget_id} successfully")
            return True
            
        except Exception as e:
            if not isinstance(e, NotFoundError):
                error_logger.error(
                    f"Error in unbind_widget {widget_id}: {str(e)}", exc_info=True
                )
            raise

    def get_widget_data(self, widget_id: str, organization_id: str, filters: Optional[Dict[str, Any]] = None) -> BoundDataSchema:
        """Get data for a widget from its bound analysis."""
        app_logger.debug(f"Entering get_widget_data: {widget_id} (org: {organization_id})")
        
        try:
            # Find the dashboard containing the widget
            dashboard = Dashboard.objects(
                organization_id=organization_id,
                is_deleted=False
            ).first()
            
            if not dashboard:
                from .exceptions import NotFoundError
                app_logger.warning(f"No dashboard found for widget data: {widget_id}")
                raise NotFoundError("No dashboard found for widget data")
            
            # Find the widget
            widget = None
            for w in dashboard.widgets or []:
                if w.id == widget_id:
                    widget = w
                    break
            
            if not widget:
                from .exceptions import NotFoundError
                app_logger.warning(f"Widget not found for data: {widget_id}")
                raise NotFoundError(f"Widget {widget_id} not found")
            
            # Check if widget is bound
            if not widget.data_source or not widget.data_source.analysis_id:
                from .exceptions import ValidationError
                app_logger.warning(f"Widget not bound to analysis: {widget_id}")
                raise ValidationError(f"Widget {widget_id} not bound to analysis")
            
            # Get analysis result
            analysis_result = AnalysisResults.objects(
                analysis_id=widget.data_source.analysis_id,
                node_id=widget.data_source.node_id,
                organization_id=organization_id,
                is_deleted=False
            ).order_by("-created_at").first()
            
            if not analysis_result:
                from .exceptions import NotFoundError
                app_logger.warning(f"No analysis result found for widget: {widget_id}")
                raise NotFoundError(f"No analysis result found for widget {widget_id}")
            
            # Apply widget-specific filters and transformations
            data = self._apply_widget_filters(analysis_result.data, widget, filters)
            
            # Transform data based on widget type
            data = self._transform_data_for_widget(data, widget)
            
            result = BoundDataSchema(
                widget_id=widget.id,
                analysis_id=str(widget.data_source.analysis_id),
                node_id=widget.data_source.node_id,
                data=data,
                metadata={
                    "widget_type": widget.widget_type,
                    "analysis_name": analysis_result.analysis_id.name if hasattr(analysis_result, 'analysis_id') else None,
                    "node_type": analysis_result.output_type,
                    "row_count": len(data) if isinstance(data, list) else 1,
                    "created_at": analysis_result.created_at.isoformat()
                },
                timestamp=datetime.now(timezone.utc).isoformat(),
                data_type=analysis_result.output_type
            )
            
            app_logger.debug(f"Exiting get_widget_data: {widget_id} successfully")
            return result
            
        except Exception as e:
            if not isinstance(e, (NotFoundError, ValidationError)):
                error_logger.error(
                    f"Error in get_widget_data {widget_id}: {str(e)}", exc_info=True
                )
            raise

    def _apply_widget_filters(self, data: Any, widget: DashboardWidget, additional_filters: Optional[Dict[str, Any]] = None) -> Any:
        """Apply widget-specific filters to the data."""
        if not data or not widget.data_source:
            return data
        
        # Combine widget filters with additional filters
        all_filters = {}
        if widget.data_source.filters:
            all_filters.update(widget.data_source.filters)
        if additional_filters:
            all_filters.update(additional_filters)
        
        # Apply filters based on data type
        if isinstance(data, list) and data:
            return self._filter_list_data(data, all_filters)
        
        return data

    def _filter_list_data(self, data: List[Any], filters: Dict[str, Any]) -> List[Any]:
        """Filter list-based data."""
        if not filters:
            return data
        
        filtered_data = data.copy()
        
        # Apply basic filters
        for field, value in filters.items():
            if isinstance(value, dict):
                # Handle complex filter conditions
                if 'equals' in value:
                    filtered_data = [item for item in filtered_data if item.get(field) == value['equals']]
                elif 'contains' in value:
                    filtered_data = [item for item in filtered_data if value['contains'] in str(item.get(field, ''))]
                elif 'gt' in value:
                    filtered_data = [item for item in filtered_data if item.get(field, 0) > value['gt']]
                elif 'lt' in value:
                    filtered_data = [item for item in filtered_data if item.get(field, 0) < value['lt']]
            else:
                # Simple equality filter
                filtered_data = [item for item in filtered_data if item.get(field) == value]
        
        return filtered_data

    def _transform_data_for_widget(self, data: Any, widget: DashboardWidget) -> Any:
        """Transform data based on widget type and configuration."""
        if not data or not widget.config:
            return data
        
        widget_type = widget.widget_type
        
        if widget_type == 'kpi_card':
            return self._transform_for_kpi_card(data, widget.config)
        elif widget_type == 'bar_chart':
            return self._transform_for_bar_chart(data, widget.config)
        elif widget_type == 'line_chart':
            return self._transform_for_line_chart(data, widget.config)
        elif widget_type == 'pie_chart':
            return self._transform_for_pie_chart(data, widget.config)
        elif widget_type == 'data_table':
            return self._transform_for_data_table(data, widget.config)
        
        return data

    def _transform_for_kpi_card(self, data: Any, config: Dict[str, Any]) -> Any:
        """Transform data for KPI card widget."""
        if isinstance(data, list) and data:
            # Get aggregation type from config
            aggregation_type = config.get('aggregation_type', 'count')
            value_field = config.get('value_field')
            
            if aggregation_type == 'count':
                return len(data)
            elif aggregation_type == 'sum' and value_field:
                return sum(item.get(value_field, 0) for item in data if isinstance(item.get(value_field), (int, float)))
            elif aggregation_type == 'average' and value_field:
                values = [item.get(value_field, 0) for item in data if isinstance(item.get(value_field), (int, float))]
                return sum(values) / len(values) if values else 0
            elif aggregation_type == 'max' and value_field:
                return max(item.get(value_field, 0) for item in data if isinstance(item.get(value_field), (int, float)))
            elif aggregation_type == 'min' and value_field:
                return min(item.get(value_field, 0) for item in data if isinstance(item.get(value_field), (int, float)))
        
        return data

    def _transform_for_bar_chart(self, data: Any, config: Dict[str, Any]) -> Any:
        """Transform data for bar chart widget."""
        if isinstance(data, list) and data:
            group_by_field = config.get('group_by_field')
            value_field = config.get('value_field')
            
            if group_by_field and value_field:
                # Group data by field
                groups = {}
                for item in data:
                    key = item.get(group_by_field, 'Unknown')
                    value = item.get(value_field, 0)
                    if key in groups:
                        groups[key] += value
                    else:
                        groups[key] = value
                
                # Convert to chart format
                return {
                    "labels": list(groups.keys()),
                    "values": list(groups.values())
                }
        
        return data

    def _transform_for_line_chart(self, data: Any, config: Dict[str, Any]) -> Any:
        """Transform data for line chart widget."""
        if isinstance(data, list) and data:
            # Sort by date/time field if available
            date_field = config.get('date_field', 'created_at')
            value_field = config.get('value_field')
            
            if value_field:
                # Sort by date field
                sorted_data = sorted(data, key=lambda x: x.get(date_field, ''))
                
                return {
                    "dates": [item.get(date_field, '') for item in sorted_data],
                    "values": [item.get(value_field, 0) for item in sorted_data]
                }
        
        return data

    def _transform_for_pie_chart(self, data: Any, config: Dict[str, Any]) -> Any:
        """Transform data for pie chart widget."""
        # Similar to bar chart but for pie charts
        return self._transform_for_bar_chart(data, config)

    def _transform_for_data_table(self, data: Any, config: Dict[str, Any]) -> Any:
        """Transform data for data table widget."""
        if isinstance(data, list) and data:
            # Apply column selection and ordering
            display_columns = config.get('display_columns')
            
            if display_columns:
                # Filter and reorder columns
                filtered_data = []
                for item in data:
                    filtered_item = {col: item.get(col) for col in display_columns if col in item}
                    filtered_data.append(filtered_item)
                
                return filtered_data
        
        return data

    def get_bound_widgets(self, analysis_id: str, organization_id: str) -> List[Dict[str, Any]]:
        """Get all widgets bound to a specific analysis."""
        app_logger.debug(f"Entering get_bound_widgets: analysis {analysis_id} (org: {organization_id})")
        
        try:
            # Find all dashboards in organization
            dashboards = Dashboard.objects(
                organization_id=organization_id,
                is_deleted=False
            )
            
            bound_widgets = []
            
            for dashboard in dashboards:
                for widget in dashboard.widgets or []:
                    if (widget.data_source and 
                        widget.data_source.analysis_id == analysis_id):
                        
                        bound_widgets.append({
                            "widget_id": widget.id,
                            "dashboard_id": str(dashboard.id),
                            "dashboard_name": dashboard.name,
                            "widget_type": widget.widget_type,
                            "node_id": widget.data_source.node_id,
                            "title": widget.title,
                            "is_visible": widget.is_visible
                        })
            
            app_logger.debug(f"Exiting get_bound_widgets: found {len(bound_widgets)} widgets")
            return bound_widgets
            
        except Exception as e:
            error_logger.error(
                f"Error in get_bound_widgets {analysis_id}: {str(e)}", exc_info=True
            )
            raise

    def refresh_widget_data(self, widget_id: str, organization_id: str) -> BoundDataSchema:
        """Force refresh of widget data."""
        app_logger.debug(f"Entering refresh_widget_data: {widget_id} (org: {organization_id})")
        
        try:
            # Get current data
            data = self.get_widget_data(widget_id, organization_id)
            
            # Update timestamp
            data.timestamp = datetime.now(timezone.utc).isoformat()
            
            app_logger.debug(f"Exiting refresh_widget_data: {widget_id} successfully")
            return data
            
        except Exception as e:
            error_logger.error(
                f"Error in refresh_widget_data {widget_id}: {str(e)}", exc_info=True
            )
            raise