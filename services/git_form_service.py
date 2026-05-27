import copy
import logging
from typing import Dict, Any, List, Tuple
from models.FormCommit import FormCommit
from models.Form import Form
from mongoengine import connect

logger = logging.getLogger("application")


class GitFormService:
    """
    Pure-Python service providing Git-Style version control, JSON patching, and
    3-way merge conflict resolution for Form structures.
    """

    @staticmethod
    def diff(src: Any, dst: Any, path: str = "") -> List[Dict[str, Any]]:
        """
        Recursively calculates the RFC 6902 JSON patch operations required to transform 'src' into 'dst'.
        """
        if type(src) is not type(dst):
            return [{"op": "replace", "path": path or "/", "value": dst}]

        if isinstance(src, dict):
            ops = []
            # Keys removed
            for k in src:
                if k not in dst:
                    ops.append({"op": "remove", "path": f"{path}/{k}"})
            # Keys added or modified
            for k in dst:
                if k not in src:
                    ops.append({"op": "add", "path": f"{path}/{k}", "value": dst[k]})
                else:
                    ops.extend(GitFormService.diff(src[k], dst[k], f"{path}/{k}"))
            return ops

        elif isinstance(src, list):
            # Treat list changes as complete replacements of the list to avoid misalignment
            if src != dst:
                return [{"op": "replace", "path": path or "/", "value": dst}]
            return []

        else:
            if src != dst:
                return [{"op": "replace", "path": path or "/", "value": dst}]
            return []

    @staticmethod
    def patch(src: Any, ops: List[Dict[str, Any]]) -> Any:
        """
        Applies RFC 6902 JSON patch operations to a dictionary structure.
        """
        dst = copy.deepcopy(src)
        for op in ops:
            raw_path = op["path"].strip("/")
            if not raw_path:
                dst = op["value"]
                continue

            path_parts = raw_path.split("/")
            curr = dst

            # Navigate to the parent node
            for part in path_parts[:-1]:
                if isinstance(curr, list):
                    part = int(part)
                elif isinstance(curr, dict) and part not in curr:
                    curr[part] = {}
                curr = curr[part]

            last_part = path_parts[-1]
            if isinstance(curr, list):
                last_part = int(last_part)

            action = op["op"]
            if action in ("add", "replace"):
                if isinstance(curr, list):
                    if last_part == len(curr):
                        curr.append(op["value"])
                    else:
                        curr[last_part] = op["value"]
                else:
                    curr[last_part] = op["value"]
            elif action == "remove":
                if isinstance(curr, list):
                    if 0 <= last_part < len(curr):
                        curr.pop(last_part)
                else:
                    curr.pop(last_part, None)

        return dst

    @staticmethod
    def calculate_3way_merge(
        base: Dict[str, Any], mine: Dict[str, Any], theirs: Dict[str, Any]
    ) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
        """
        Performs a 3-way merge between base (common ancestor), mine (draft), and theirs (server).
        Returns:
            Tuple containing:
            - The merged dictionary (containing auto-merged changes).
            - A list of conflict descriptors, each containing 'path', 'mine_val', 'theirs_val'.
        """
        diff_mine = GitFormService.diff(base, mine)
        diff_theirs = GitFormService.diff(base, theirs)

        # Map paths to operations
        mine_ops_map = {op["path"]: op for op in diff_mine}
        theirs_ops_map = {op["path"]: op for op in diff_theirs}

        merged_ops = []
        conflicts = []

        all_paths = set(mine_ops_map.keys()).union(set(theirs_ops_map.keys()))

        for path in all_paths:
            op_mine = mine_ops_map.get(path)
            op_theirs = theirs_ops_map.get(path)

            if op_mine and not op_theirs:
                # Changes only made in my workspace: auto-apply
                merged_ops.append(op_mine)
            elif op_theirs and not op_mine:
                # Changes only made in server main: auto-apply
                merged_ops.append(op_theirs)
            elif op_mine and op_theirs:
                # Changes made on both sides
                if op_mine == op_theirs:
                    # Identical changes: apply once
                    merged_ops.append(op_mine)
                else:
                    # Conflicting changes!
                    conflicts.append(
                        {
                            "path": path,
                            "mine": (
                                op_mine.get("value")
                                if op_mine["op"] != "remove"
                                else None
                            ),
                            "theirs": (
                                op_theirs.get("value")
                                if op_theirs["op"] != "remove"
                                else None
                            ),
                            "mine_op": op_mine["op"],
                            "theirs_op": op_theirs["op"],
                        }
                    )

        # Apply successful auto-merged operations to base
        merged_result = GitFormService.patch(base, merged_ops)
        return merged_result, conflicts

    @staticmethod
    def get_commit_history(form_id: str, organization_id: str) -> List[FormCommit]:
        """
        Retrieves the complete commit log tree for a specific form within tenant boundary.
        """
        return FormCommit.objects(
            form_id=form_id, organization_id=organization_id
        ).order_by("-created_at")

    @staticmethod
    def reconstruct_form_at_commit(
        form_id: str, commit_id: str, organization_id: str
    ) -> Dict[str, Any]:
        """
        Reconstructs the full form configuration at a specific commit hash by playing
        patches forward from the root commit.
        """
        # Traverse commits backwards to root to assemble the patch pipeline
        commit_pipeline = []
        curr_id = commit_id

        while curr_id:
            commit = FormCommit.objects(
                id=curr_id, organization_id=organization_id
            ).first()
            if not commit:
                break
            commit_pipeline.append(commit)
            curr_id = commit.parent_commit_id

        # Play commits forward starting from empty dictionary base
        result = {}
        for commit in reversed(commit_pipeline):
            result = GitFormService.patch(result, commit.patch)

        return result
