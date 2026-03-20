from flask import Blueprint, jsonify, request
from flasgger import swag_from
from flask_jwt_extended import jwt_required

external_api_bp = Blueprint("external_api", __name__)


@external_api_bp.route("/uhid/<string:uhid>", methods=["GET"])
@swag_from({
    "tags": [
        "External_Api"
    ],
    "responses": {
        "200": {
            "description": "Success"
        }
    },
    "parameters": [
        {
            "name": "uhid",
            "in": "path",
            "type": "string",
            "required": True
        }
    ]
})
@jwt_required()
def get_uhid_details(uhid):
    """
    Fetch details of UHID (Empty Route Placeholder).
    """
    return jsonify({"message": f"UHID details for {uhid}", "data": {}}), 200


@external_api_bp.route("/employee/<string:employee_id>", methods=["GET"])
@swag_from({
    "tags": [
        "External_Api"
    ],
    "responses": {
        "200": {
            "description": "Success"
        }
    },
    "parameters": [
        {
            "name": "employee_id",
            "in": "path",
            "type": "string",
            "required": True
        }
    ]
})
@jwt_required()
def get_employee_details(employee_id):
    """
    Fetch details of EMPLOYEE (Empty Route Placeholder).
    """
    return jsonify({"message": f"Employee details for {employee_id}", "data": {}}), 200


@external_api_bp.route("/mail", methods=["POST"])
@swag_from({
    "tags": [
        "External_Api"
    ],
    "responses": {
        "200": {
            "description": "Success"
        }
    }
})
@jwt_required()
def send_mail():
    """
    Send mail (Empty Route Placeholder).
    """
    data = request.get_json()
    return jsonify({"message": "Mail sent successfully", "data": data or {}}), 200


@external_api_bp.route("/sms", methods=["POST"])
@swag_from({
    "tags": [
        "External_Api"
    ],
    "responses": {
        "200": {
            "description": "Success"
        }
    }
})
@jwt_required()
def send_sms():
    """
    Send SMS (Empty Route Placeholder).
    """
    data = request.get_json()
    return jsonify({"message": "SMS sent successfully", "data": data or {}}), 200
