from . import form_bp
import csv
import io
import json
import zipfile
from datetime import datetime
from routes.v1.form.helper import get_current_user, has_form_permission
from routes.v1.form import form_bp
from flask import Response, request, jsonify
from flask_jwt_extended import jwt_required
from mongoengine import DoesNotExist
from models import Form
from models import Form, FormResponse


# -------------------- Helper for Export --------------------
def generate_form_csv(form, responses):
    """
    Generates CSV content for a specific form and its responses.
    """
    headers = ["response_id", "submitted_by", "submitted_at", "status"]
    field_mapping = []  # List of {qid, sid, is_repeatable}

    if form.versions:
        latest_version = form.versions[-1]
        for section in latest_version.sections:
            sid = str(section.id)
            prefix = f"{section.title} - " if len(latest_version.sections) > 1 else ""

            for question in section.questions:
                qid = str(question.id)
                label = f"{prefix}{question.label}"
                headers.append(label)
                field_mapping.append(
                    {
                        "qid": qid,
                        "sid": sid,
                        "is_repeatable": section.is_repeatable_section,
                    }
                )
    else:
        headers.append("data")

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(headers)

    for r in responses:
        row = [
            str(r.id),
            r.submitted_by,
            r.submitted_at.isoformat() if r.submitted_at else "",
            r.status or "submitted",
        ]

        if not form.versions:
            row.append(json.dumps(r.data))
        else:
            for mapping in field_mapping:
                sid = mapping["sid"]
                qid = mapping["qid"]

                section_data = r.data.get(sid)

                val = ""
                if section_data:
                    if mapping["is_repeatable"]:
                        if isinstance(section_data, list):
                            values = [str(entry.get(qid, "")) for entry in section_data]
                            val = " | ".join(values)
                    else:
                        if isinstance(section_data, dict):
                            val = str(section_data.get(qid, ""))

                row.append(val)

        writer.writerow(row)

    return output.getvalue()


# -------------------- Export to CSV --------------------
@form_bp.route("/<form_id>/export/csv", methods=["GET"])
@jwt_required()
def export_responses_csv(form_id):
    try:
        form = Form.objects.get(id=form_id)
        current_user = get_current_user()
        if not has_form_permission(current_user, form, "view"):
            return jsonify({"error": "Unauthorized to export"}), 403

        responses = FormResponse.objects(form=form.id)
        csv_content = generate_form_csv(form, responses)

        return Response(
            csv_content,
            mimetype="text/csv",
            headers={
                "Content-Disposition": f"attachment;filename=form_{form_id}_responses.csv"
            },
        )
    except DoesNotExist:
        return jsonify({"error": "Form not found"}), 404


@form_bp.route("/<form_id>/export/json", methods=["GET"])
@jwt_required()
def export_form_with_responses(form_id):
    try:
        form = Form.objects.get(id=form_id)
        current_user = get_current_user()
        if not has_form_permission(current_user, form, "view"):
            return jsonify({"error": "Unauthorized"}), 403

        responses = FormResponse.objects(form=form.id)
        data = {
            "form_metadata": {
                "id": str(form.id),
                "title": form.title,
                "slug": form.slug,
                "created_by": form.created_by,
                "created_at": str(form.created_at),
                "status": form.status,
                "is_public": form.is_public,
            },
            "responses": [r.to_mongo().to_dict() for r in responses],
        }
        return Response(json.dumps(data, default=str), mimetype="application/json")
    except DoesNotExist:
        return jsonify({"error": "Form not found"}), 404


# -------------------- Bulk Export --------------------
@form_bp.route("/export/bulk", methods=["POST"])
@jwt_required()
def export_bulk_responses():
    try:
        data = request.get_json()
        form_ids = data.get("form_ids", [])
        if not form_ids:
            return jsonify({"error": "Missing form_ids"}), 400

        current_user = get_current_user()

        # Memory buffer for ZIP
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
            for fid in form_ids:
                try:
                    form = Form.objects.get(id=fid)
                except DoesNotExist:
                    continue  # Skip if not found

                if not has_form_permission(current_user, form, "view"):
                    continue  # Skip unauthorized

                responses = FormResponse.objects(form=form.id)
                csv_content = generate_form_csv(form, responses)

                # Sanitize filename
                safe_title = "".join(
                    [c for c in form.title if c.isalnum() or c in (" ", "_", "-")]
                ).strip()
                filename = f"{safe_title}_{fid[:8]}.csv"
                zip_file.writestr(filename, csv_content)

        zip_buffer.seek(0)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        return Response(
            zip_buffer.getvalue(),
            mimetype="application/zip",
            headers={
                "Content-Disposition": f"attachment;filename=bulk_export_{timestamp}.zip"
            },
        )
    except Exception as e:
        return jsonify({"error": str(e)}), 400
