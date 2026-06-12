from datetime import datetime
from typing import List, Dict, Any, Optional
import networkx as nx
from ..models.FormCommit import FormCommit, Form, Section, SubSection, Question
from ..models.ConceptRegistry import ConceptRegistry
from .base import BaseService

class FormEngineService(BaseService):
    """Service for form versioning, merge, and visibility evaluation"""
    
    def __init__(self):
        super().__init__()
        self.form_graphs = {}  # Cache for form dependency graphs
    
    def create_branch(self, form_id: str, branch_name: str, from_commit_id: str = None) -> str:
        """Create a new branch for a form"""
        form = self.db.forms.find_one({"_id": form_id})
        if not form:
            raise ValueError(f"Form {form_id} not found")
        
        # Get the source commit (default to main branch HEAD)
        if not from_commit_id:
            from_commit_id = form.get("branches", {}).get("main")
        
        if not from_commit_id:
            raise ValueError("No source commit found for branching")
        
        # Update form branches
        update_result = self.db.forms.update_one(
            {"_id": form_id},
            {"$set": {f"branches.{branch_name}": from_commit_id}}
        )
        
        if update_result.modified_count == 0:
            raise ValueError(f"Failed to create branch {branch_name}")
        
        return from_commit_id
    
    def commit_form(self, form_id: str, branch_name: str, message: str, 
                   schema: Dict[str, Any], author_id: str) -> str:
        """Create a new form commit"""
        import hashlib
        import uuid
        
        # Generate commit ID (SHA-like)
        content = json.dumps(schema, sort_keys=True)
        commit_id = hashlib.sha256(f"{form_id}{branch_name}{content}{datetime.now().isoformat()}".encode()).hexdigest()[:40]
        
        # Get parent commits
        form = self.db.forms.find_one({"_id": form_id})
        parent_commit_id = form.get("branches", {}).get(branch_name)
        parent_ids = [parent_commit_id] if parent_commit_id else []
        
        # Create form commit
        form_commit = FormCommit(
            form_id=form_id,
            commit_id=commit_id,
            parent_ids=parent_ids,
            author_id=author_id,
            message=message,
            branch=branch_name,
            schema=schema
        )
        
        # Insert commit
        self.db.form_commits.insert_one(form_commit.dict())
        
        # Update form branch pointer
        self.db.forms.update_one(
            {"_id": form_id},
            {"$set": {f"branches.{branch_name}": commit_id}}
        )
        
        return commit_id
    
    def merge_branches(self, form_id: str, source_branch: str, target_branch: str, 
                      author_id: str) -> Dict[str, Any]:
        """Merge source branch into target branch with conflict resolution"""
        
        # Get branch heads
        form = self.db.forms.find_one({"_id": form_id})
        source_commit_id = form.get("branches", {}).get(source_branch)
        target_commit_id = form.get("branches", {}).get(target_branch)
        
        if not source_commit_id or not target_commit_id:
            raise ValueError("Source or target branch not found")
        
        # Get commit data
        source_commit = self.db.form_commits.find_one({"commit_id": source_commit_id})
        target_commit = self.db.form_commits.find_one({"commit_id": target_commit_id})
        
        # Check for conflicts (simplified - in real implementation would be more complex)
        conflicts = self._detect_merge_conflicts(source_commit, target_commit)
        
        if conflicts:
            # Create pending merge record
            merge_record = {
                "form_id": form_id,
                "source_branch": source_branch,
                "target_branch": target_branch,
                "source_commit": source_commit_id,
                "target_commit": target_commit_id,
                "conflicts": conflicts,
                "status": "pending",
                "created_at": datetime.now(),
                "created_by": author_id
            }
            
            self.db.pending_merges.insert_one(merge_record)
            
            return {
                "status": "conflicts_detected",
                "conflicts": conflicts,
                "merge_id": str(merge_record["_id"])
            }
        
        # No conflicts, perform merge
        merged_schema = self._merge_schemas(source_commit["schema"], target_commit["schema"])
        
        # Create merge commit
        merge_commit_id = self.commit_form(
            form_id=form_id,
            branch=target_branch,
            message=f"Merge {source_branch} into {target_branch}",
            schema=merged_schema,
            author_id=author_id
        )
        
        return {
            "status": "merged",
            "commit_id": merge_commit_id
        }
    
    def _detect_merge_conflicts(self, source_commit: Dict, target_commit: Dict) -> List[Dict]:
        """Detect merge conflicts between two commits"""
        # Simplified conflict detection
        conflicts = []
        
        # Compare schema structures
        source_sections = source_commit.get("schema", {}).get("sections", [])
        target_sections = target_commit.get("schema", {}).get("sections", [])
        
        # Check for structural conflicts
        if len(source_sections) != len(target_sections):
            conflicts.append({
                "type": "structural",
                "message": "Different number of sections"
            })
        
        return conflicts
    
    def _merge_schemas(self, source_schema: Dict, target_schema: Dict) -> Dict:
        """Merge two form schemas"""
        # Simplified merge - in real implementation would be more sophisticated
        merged_schema = target_schema.copy()
        
        # Merge sections (simplified)
        merged_sections = []
        source_sections = source_schema.get("sections", [])
        target_sections = target_schema.get("sections", [])
        
        # Use target sections as base, add new sections from source
        merged_sections.extend(target_sections)
        
        for source_section in source_sections:
            # Check if section exists in target
            section_exists = any(
                s.get("id") == source_section.get("id") 
                for s in target_sections
            )
            if not section_exists:
                merged_sections.append(source_section)
        
        merged_schema["sections"] = merged_sections
        
        return merged_schema
    
    def evaluate_visibility_rules(self, form_schema: Dict, user_context: Dict) -> Dict[str, bool]:
        """Evaluate visibility rules for form elements"""
        visibility_results = {}
        
        def evaluate_rules(rules: Dict, context: Dict) -> bool:
            operator = rules.get("operator", "AND")
            conditions = rules.get("conditions", [])
            
            if not conditions:
                return True
            
            results = []
            for condition in conditions:
                condition_type = condition.get("type")
                
                if condition_type == "role":
                    user_roles = context.get("roles", [])
                    required_roles = condition.get("roles", [])
                    results.append(any(role in user_roles for role in required_roles))
                
                elif condition_type == "group":
                    user_groups = context.get("groups", [])
                    required_groups = condition.get("group_ids", [])
                    results.append(any(group in user_groups for group in required_groups))
                
                elif condition_type == "always_visible":
                    results.append(True)
                
                elif condition_type == "always_hidden":
                    results.append(False)
            
            if operator == "AND":
                return all(results)
            elif operator == "OR":
                return any(results)
            else:
                return True
        
        # Evaluate section visibility
        for section in form_schema.get("sections", []):
            section_id = section.get("id")
            visibility_rules = section.get("visibility_rules", {})
            visibility_results[section_id] = evaluate_rules(visibility_rules, user_context)
            
            # Evaluate sub-section visibility
            for sub_section in section.get("sub_sections", []):
                sub_section_id = sub_section.get("id")
                sub_visibility_rules = sub_section.get("visibility_rules", {})
                visibility_results[sub_section_id] = evaluate_rules(sub_visibility_rules, user_context)
                
                # Evaluate question visibility
                for question in sub_section.get("questions", []):
                    question_id = question.get("id")
                    question_visibility_rules = question.get("visibility_rules", {})
                    visibility_results[question_id] = evaluate_rules(question_visibility_rules, user_context)
        
        return visibility_results
    
    def publish_form(self, form_id: str, branch_name: str = "main") -> str:
        """Publish a form branch to production"""
        form = self.db.forms.find_one({"_id": form_id})
        if not form:
            raise ValueError(f"Form {form_id} not found")
        
        # Get branch head commit
        commit_id = form.get("branches", {}).get(branch_name)
        if not commit_id:
            raise ValueError(f"Branch {branch_name} not found")
        
        # Update production branch
        update_result = self.db.forms.update_one(
            {"_id": form_id},
            {"$set": {"production_branch": branch_name}}
        )
        
        if update_result.modified_count == 0:
            raise ValueError(f"Failed to publish form {form_id}")
        
        return commit_id
