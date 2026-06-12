from flask import Blueprint, request, jsonify
from datetime import datetime
from ..services.analysis_engine import AnalysisEngineService

analysis_bp = Blueprint('analysis', __name__, url_prefix='/api/internal/v1/analyses')

analysis_engine = AnalysisEngineService()

@analysis_bp.route('/<analysis_id>/run', methods=['POST'])
def run_analysis(analysis_id):
    """Execute an analysis"""
    try:
        # Trigger Celery task
        result = analysis_engine.execute_analysis.delay(analysis_id)
        
        return jsonify({
            "success": True,
            "task_id": result.id,
            "analysis_id": analysis_id
        })
    
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@analysis_bp.route('/<analysis_id>/runs', methods=['GET'])
def get_analysis_runs(analysis_id):
    """Get analysis run history"""
    try:
        runs = list(analysis_engine.db.analysis_runs.find(
            {"analysis_id": analysis_id}
        ).sort("started_at", -1).limit(10))
        
        return jsonify({
            "success": True,
            "runs": runs
        })
    
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@analysis_bp.route('/<analysis_id>/nodes', methods=['GET'])
def get_analysis_nodes(analysis_id):
    """Get analysis node information"""
    try:
        analysis = analysis_engine.db.analyses.find_one({"_id": analysis_id})
        if not analysis:
            return jsonify({"error": "Analysis not found"}), 404
        
        return jsonify({
            "success": True,
            "nodes": analysis.get("graph", {}).get("nodes", []),
            "edges": analysis.get("graph", {}).get("edges", [])
        })
    
    except Exception as e:
        return jsonify({"error": str(e)}), 500
