"""
services/storage_service.py
Storage service for file upload management with quota enforcement.
"""

import os
import uuid
from datetime import datetime
from typing import Dict, Optional, Tuple
from werkzeug.utils import secure_filename
from logger.unified_logger import app_logger, error_logger, audit_logger
from services.storage_quota_service import storage_quota_service
from models.response import FileUpload
from utils.response_helper import error_response


class StorageService:
    """Service for managing file uploads with quota enforcement."""
    
    def __init__(self):
        self.upload_root = os.getenv('UPLOADS_ROOT', '/var/uploads')
        self.max_file_sizes = {
            'pdf': int(os.getenv('MAX_UPLOAD_SIZE_PDF', 50 * 1024 * 1024)),  # 50MB
            'video': int(os.getenv('MAX_UPLOAD_SIZE_VIDEO', 300 * 1024 * 1024)),  # 300MB
            'image': int(os.getenv('MAX_UPLOAD_SIZE_IMAGE', 10 * 1024 * 1024)),  # 10MB
            'other': int(os.getenv('MAX_UPLOAD_SIZE_OTHER', 100 * 1024 * 1024))  # 100MB
        }
        self.allowed_extensions = {
            'pdf': {'pdf'},
            'image': {'png', 'jpg', 'jpeg', 'gif', 'bmp', 'svg', 'webp'},
            'video': {'mp4', 'avi', 'mov', 'wmv', 'flv', 'webm', 'mkv'},
            'audio': {'mp3', 'wav', 'ogg', 'flac', 'aac'},
            'document': {'doc', 'docx', 'xls', 'xlsx', 'ppt', 'pptx', 'txt', 'rtf'},
            'archive': {'zip', 'rar', '7z', 'tar', 'gz'}
        }
    
    def validate_file_upload(self, file, org_id: str) -> Tuple[bool, Dict]:
        """
        Validate file upload against size limits, file types, and storage quota.
        
        Returns:
            Tuple of (is_valid, error_response_dict)
        """
        try:
            # Check if file was provided
            if not file or not file.filename:
                return False, error_response("No file provided", status_code=400)
            
            # Check file size
            file_size = len(file.read())
            file.seek(0)  # Reset file pointer
            
            file_type = self._determine_file_type(file.filename)
            max_size = self.max_file_sizes.get(file_type, self.max_file_sizes['other'])
            
            if file_size > max_size:
                return False, error_response(
                    f"File size exceeds maximum allowed size of {max_size / (1024 * 1024):.1f}MB",
                    status_code=400
                )
            
            # Check file extension
            if not self._is_allowed_extension(file.filename):
                return False, error_response(
                    "File type not allowed",
                    status_code=400
                )
            
            # Check storage quota
            if not storage_quota_service.check_file_upload_allowed(org_id, file_size):
                return False, error_response(
                    "Storage quota exceeded. Please delete some files or contact your administrator.",
                    status_code=400,
                    error_code="STORAGE_QUOTA_EXCEEDED"
                )
            
            return True, {}
            
        except Exception as e:
            error_logger.error(f"Error validating file upload: {e}")
            return False, error_response("File validation failed", status_code=500)
    
    def save_uploaded_file(self, file, org_id: str, user_id: str, 
                           form_id: str = None, response_id: str = None,
                           question_id: str = None) -> Dict:
        """
        Save uploaded file to storage and create database record.
        
        Returns:
            Dictionary with file information
        """
        try:
            # Validate file first
            is_valid, error_response_dict = self.validate_file_upload(file, org_id)
            if not is_valid:
                return error_response_dict
            
            # Generate unique filename
            original_filename = secure_filename(file.filename)
            file_extension = os.path.splitext(original_filename)[1]
            unique_filename = f"{uuid.uuid4()}{file_extension}"
            
            # Create organization directory structure
            org_dir = os.path.join(self.upload_root, str(org_id))
            os.makedirs(org_dir, exist_ok=True)
            
            # Create date-based subdirectory
            date_dir = os.path.join(org_dir, datetime.utcnow().strftime('%Y-%m-%d'))
            os.makedirs(date_dir, exist_ok=True)
            
            # Full file path
            file_path = os.path.join(date_dir, unique_filename)
            relative_path = os.path.join(str(org_id), datetime.utcnow().strftime('%Y-%m-%d'), unique_filename)
            
            # Save file
            file.save(file_path)
            
            # Get file info
            file_size = os.path.getsize(file_path)
            file_type = self._determine_file_type(original_filename)
            mime_type = self._get_mime_type(file_path)
            
            # Create database record
            file_upload = FileUpload(
                org_id=org_id,
                form_id=form_id,
                response_id=response_id,
                question_id=question_id,
                original_filename=original_filename,
                stored_filename=unique_filename,
                file_path=relative_path,
                mime_type=mime_type,
                file_size_bytes=file_size,
                file_type=file_type,
                upload_status='complete',
                uploaded_by=user_id,
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow()
            )
            file_upload.save()
            
            # Update storage quota
            storage_quota_service.record_file_upload(org_id, file_size)
            
            # Log file upload
            audit_logger.info(
                f"File uploaded: {original_filename} ({file_size} bytes) "
                f"for org {org_id} by user {user_id}"
            )
            
            return {
                'file_id': str(file_upload.id),
                'original_filename': original_filename,
                'file_size': file_size,
                'file_type': file_type,
                'mime_type': mime_type,
                'upload_status': 'complete',
                'uploaded_at': file_upload.created_at.isoformat()
            }
            
        except Exception as e:
            error_logger.error(f"Error saving uploaded file: {e}")
            return error_response("File upload failed", status_code=500)
    
    def get_file_info(self, file_id: str, org_id: str) -> Optional[Dict]:
        """
        Get file information by ID.
        """
        try:
            file_upload = FileUpload.objects(
                id=file_id,
                org_id=org_id,
                is_deleted=False
            ).first()
            
            if not file_upload:
                return None
            
            return {
                'file_id': str(file_upload.id),
                'original_filename': file_upload.original_filename,
                'file_size': file_upload.file_size_bytes,
                'file_type': file_upload.file_type,
                'mime_type': file_upload.mime_type,
                'upload_status': file_upload.upload_status,
                'uploaded_at': file_upload.created_at.isoformat(),
                'uploaded_by': str(file_upload.uploaded_by) if file_upload.uploaded_by else None
            }
            
        except Exception as e:
            error_logger.error(f"Error getting file info: {e}")
            return None
    
    def get_file_url(self, file_id: str, org_id: str) -> Optional[str]:
        """
        Generate secure URL for file download.
        """
        try:
            file_upload = FileUpload.objects(
                id=file_id,
                org_id=org_id,
                is_deleted=False
            ).first()
            
            if not file_upload:
                return None
            
            # Generate secure download URL
            # This would integrate with your authentication system
            return f"/api/v1/files/{file_id}/download"
            
        except Exception as e:
            error_logger.error(f"Error generating file URL: {e}")
            return None
    
    def delete_file(self, file_id: str, org_id: str, user_id: str) -> bool:
        """
        Delete a file and update storage quota.
        """
        try:
            file_upload = FileUpload.objects(
                id=file_id,
                org_id=org_id,
                is_deleted=False
            ).first()
            
            if not file_upload:
                return False
            
            # Delete physical file
            full_path = os.path.join(self.upload_root, file_upload.file_path)
            if os.path.exists(full_path):
                os.remove(full_path)
            
            # Update database record
            file_upload.is_deleted = True
            file_upload.deleted_at = datetime.utcnow()
            file_upload.save()
            
            # Update storage quota
            storage_quota_service.record_file_deletion(org_id, file_upload.file_size_bytes or 0)
            
            # Log file deletion
            audit_logger.info(
                f"File deleted: {file_upload.original_filename} ({file_upload.file_size_bytes} bytes) "
                f"for org {org_id} by user {user_id}"
            )
            
            return True
            
        except Exception as e:
            error_logger.error(f"Error deleting file: {e}")
            return False
    
    def get_organization_files(self, org_id: str, limit: int = 100, offset: int = 0) -> Dict:
        """
        Get list of files for an organization.
        """
        try:
            files = FileUpload.objects(
                org_id=org_id,
                is_deleted=False
            ).order_by('-created_at').skip(offset).limit(limit)
            
            file_list = []
            for file in files:
                file_list.append({
                    'file_id': str(file.id),
                    'original_filename': file.original_filename,
                    'file_size': file.file_size_bytes,
                    'file_type': file.file_type,
                    'mime_type': file.mime_type,
                    'upload_status': file.upload_status,
                    'uploaded_at': file.created_at.isoformat(),
                    'uploaded_by': str(file.uploaded_by) if file.uploaded_by else None
                })
            
            total_count = FileUpload.objects(org_id=org_id, is_deleted=False).count()
            
            return {
                'files': file_list,
                'total_count': total_count,
                'limit': limit,
                'offset': offset
            }
            
        except Exception as e:
            error_logger.error(f"Error getting organization files: {e}")
            return {'files': [], 'total_count': 0, 'limit': limit, 'offset': offset}
    
    def _determine_file_type(self, filename: str) -> str:
        """Determine file type based on filename extension."""
        extension = os.path.splitext(filename)[1].lower().lstrip('.')
        
        for file_type, extensions in self.allowed_extensions.items():
            if extension in extensions:
                return file_type
        
        return 'other'
    
    def _is_allowed_extension(self, filename: str) -> bool:
        """Check if file extension is allowed."""
        extension = os.path.splitext(filename)[1].lower().lstrip('.')
        
        for allowed_extensions in self.allowed_extensions.values():
            if extension in allowed_extensions:
                return True
        
        return False
    
    def _get_mime_type(self, file_path: str) -> str:
        """Get MIME type of file."""
        try:
            import magic
            mime = magic.Magic(mime=True)
            return mime.from_file(file_path)
        except ImportError:
            # Fallback to basic MIME type detection
            extension = os.path.splitext(file_path)[1].lower()
            mime_types = {
                '.pdf': 'application/pdf',
                '.png': 'image/png',
                '.jpg': 'image/jpeg',
                '.jpeg': 'image/jpeg',
                '.gif': 'image/gif',
                '.mp4': 'video/mp4',
                '.avi': 'video/x-msvideo',
                '.mov': 'video/quicktime',
                '.mp3': 'audio/mpeg',
                '.wav': 'audio/wav',
                '.doc': 'application/msword',
                '.docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
                '.xls': 'application/vnd.ms-excel',
                '.xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                '.txt': 'text/plain',
                '.zip': 'application/zip',
                '.rar': 'application/x-rar-compressed'
            }
            return mime_types.get(extension, 'application/octet-stream')


# Global storage service instance
storage_service = StorageService()