from flask import Blueprint, request, jsonify
from datetime import datetime
from ..services.form_engine import FormEngineService
from ..services.form_service import FormService

form_bp = Blueprint('forms', __name__, url_prefix='/api/internal/v1/forms')

form_engine = FormEngineService()
form_service = FormService()

@form_bp.route('/<form_id>/branches', methods=['POST'])
def create_branch(form_id):
    """Create a new branch for a form"""
    try:
        data = request.get_json()
        branch_name = data.get('branch_name')
        from_commit_id = data.get('from_commit_id')
        author_id = data.get('author_id')
        
        if not branch_name:
            return jsonify({"error": "branch_name is required"}), 400
        
        commit_id = form_engine.create_branch(
            form_id=form_id,
            branch_name=branch_name,
            from_commit_id=from_commit_id
        )
        
        return jsonify({
            "success": True,
            "branch_name": branch_name,
            "commit_id": commit_id
        })
    
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@form_bp.route('/<form_id>/branches/<branch_name>', methods=['DELETE'])
def delete_branch(form_id, branch_name):
    """Delete a form branch"""
    try:
        # Implementation would remove branch from form document
        return jsonify({
            "success": True,
            "message": f"Branch {branch_name} deleted"
        })
    
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@form_bp.route('/<form_id>/commits', methods=['POST'])
def commit_form(form_id):
    """Create a new form commit"""
    try:
        data = request.get_json()
        branch_name = data.get('branch_name', 'main')
        message = data.get('message')
        schema = data.get('schema')
        author_id = data.get('author_id')
        
        if not all([message, schema, author_id]):
            return jsonify({"error": "message, schema, and author_id are required"}), 400
        
        commit_id = form_engine.commit_form(
            form_id=form_id,
            branch_name=branch_name,
            message=message,
            schema=schema,
            author_id=author_id
        )
        
        return jsonify({
            "success": True,
            "commit_id": commit_id,
            "branch": branch_name
        })
    
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@form_bp.route('/<form_id>/publish', methods=['POST'])
def publish_form(form_id):
    """Publish a form branch to production"""
    try:
        data = request.get_json()
        branch_name = data.get('branch_name', 'main')
        
        commit_id = form_engine.publish_form(
            form_id=form_id,
            branch_name=branch_name
        )
        
        return jsonify({
            "success": True,
            "commit_id": commit_id,
            "published_branch": branch_name
        })
    
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@form_bp.route('/<form_id>/merge', methods=['POST'])
def merge_branches(form_id):
    """Merge source branch into target branch"""
    try:
        data = request.get_json()
        source_branch = data.get('source_branch')
        target_branch = data.get('target_branch')
        author_id = data.get('author_id')
        
        if not all([source_branch, target_branch, author_id]):
            return jsonify({"error": "source_branch, target_branch, and author_id are required"}), 400
        
        result = form_engine.merge_branches(
            form_id=form_id,
            source_branch=source_branch,
            target_branch=target_branch,
            author_id=author_id
        )
        
        return jsonify(result)
    
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@form_bp.route('/<form_id>/diff', methods=['GET'])
def get_form_diff(form_id):
    """Get diff between two form commits"""
    try:
        commit1 = request.args.get('commit1')
        commit2 = request.args.get('commit2')
        
        if not all([commit1, commit2]):
            return jsonify({"error": "commit1 and commit2 are required"}), 400
        
        # Implementation would compare two commits
        return jsonify({
            "success": True,
            "diff": "Diff implementation would go here"
        })
    
    except Exception as e:
        return jsonify({"error": str(e)}), 500
