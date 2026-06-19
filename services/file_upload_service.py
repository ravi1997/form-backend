"""
services/file_upload_service.py
Service for handling file uploads with resumable uploads (tus protocol).
"""

import os
import hashlib
import uuid
import shutil
import subprocess
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Optional, List
from mongoengine import Q
from logger.unified_logger import (
    app_logger,
    error_logger,
    audit_logger,
    get_logger,
    log_performance,
)
from logger.sla import enforce_sla
from services.base import BaseService
from services.tenant_service import TenantService
from utils.exceptions import NotFoundError, ValidationError, StateTransitionError
from models.response import FileUpload
from models.form import Form
from models.auth import User
from schemas.file import FileUploadSchema, FileChunkSchema

logger = get_logger(__name__)


class FileUploadService(BaseService):
    """
    Service for handling file uploads with resumable uploads using tus protocol.
    """

    def __init__(self):
        super().__init__(model=FileUpload, schema=FileUploadSchema)
        self.upload_dir = os.environ.get('UPLOADS_ROOT', '/var/uploads')
        self.max_file_sizes = {
            'pdf': int(os.environ.get('MAX_UPLOAD_SIZE_PDF', 50 * 1024 * 1024)),  # 50MB
            'video': int(os.environ.get('MAX_UPLOAD_SIZE_VIDEO', 300 * 1024 * 1024)),  # 300MB
            'image': int(os.environ.get('MAX_UPLOAD_SIZE_IMAGE', 50 * 1024 * 1024)),  # 50MB
            'other': int(os.environ.get('MAX_UPLOAD_SIZE_OTHER', 100 * 1024 * 1024))  # 100MB
        }
        self.chunk_size = 5 * 1024 * 1024  # 5MB chunks

    def _validate_file_type(self, file_name: str, mime_type: str) -> str:
        """
        Validate file type and return categorized type.
        """
        file_ext = os.path.splitext(file_name)[1].lower()
        
        # PDF files
        if file_ext == '.pdf' or mime_type == 'application/pdf':
            return 'pdf'
        
        # Image files
        image_mimes = [
            'image/jpeg', 'image/jpg', 'image/png', 'image/gif', 
            'image/webp', 'image/bmp', 'image/tiff'
        ]
        if mime_type in image_mimes or file_ext in ['.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp', '.tiff']:
            return 'image'
        
        # Video files
        video_mimes = [
            'video/mp4', 'video/mpeg', 'video/quicktime', 'video/x-msvideo',
            'video/x-ms-wmv', 'video/webm', 'video/ogg'
        ]
        if mime_type in video_mimes or file_ext in ['.mp4', '.mpeg', '.mov', '.avi', '.wmv', '.webm', '.ogv']:
            return 'video'
        
        # Everything else
        return 'other'

    def _validate_file_size(self, file_size: int, file_type: str) -> None:
        """
        Validate file size against type limits.
        """
        max_size = self.max_file_sizes.get(file_type, self.max_file_sizes['other'])
        
        if file_size > max_size:
            raise ValidationError(
                f"File size ({file_size} bytes) exceeds maximum allowed size "
                f"for {file_type} files ({max_size} bytes)"
            )

    def _generate_file_path(self, organization_id: str, file_id: str, original_filename: str) -> str:
        """
        Generate secure file path for storage.
        """
        # Create directory structure: uploads/org_id/year/month/day/
        today = datetime.now(timezone.utc)
        date_path = today.strftime('%Y/%m/%d')
        
        org_dir = os.path.join(self.upload_dir, str(organization_id), date_path)
        os.makedirs(org_dir, exist_ok=True)
        
        # Generate safe filename
        file_ext = os.path.splitext(original_filename)[1]
        safe_filename = f"{file_id}{file_ext}"
        
        return os.path.join(org_dir, safe_filename)

    def _calculate_checksum(self, file_path: str) -> str:
        """
        Calculate SHA-256 checksum of a file.
        """
        sha256_hash = hashlib.sha256()
        with open(file_path, 'rb') as f:
            for chunk in iter(lambda: f.read(4096), b""):
                sha256_hash.update(chunk)
        return sha256_hash.hexdigest()

    def _validate_file_signature(self, file_path: str, file_type: str) -> None:
        """
        Validate the actual file signature before marking an upload complete.
        """
        with open(file_path, "rb") as handle:
            header = handle.read(16)

        if file_type == "pdf" and not header.startswith(b"%PDF"):
            raise ValidationError("File content does not match the declared PDF type")

        if file_type == "image":
            png = header.startswith(b"\x89PNG\r\n\x1a\n")
            jpeg = header.startswith(b"\xff\xd8\xff")
            gif = header.startswith(b"GIF87a") or header.startswith(b"GIF89a")
            if not (png or jpeg or gif):
                raise ValidationError(
                    "File content does not match the declared image type"
                )

        if file_type == "video":
            mp4 = len(header) >= 12 and header[4:8] == b"ftyp"
            quicktime = header[4:8] == b"ftyp" and header[8:12] in {
                b"qt  ",
                b"moov",
            }
            if not (mp4 or quicktime):
                raise ValidationError(
                    "File content does not match the declared video type"
                )

    def _run_virus_scan(self, file_path: str) -> None:
        """
        Run an antivirus scan against a completed upload.
        """
        clamscan = shutil.which("clamscan")
        if not clamscan:
            raise ValidationError("Virus scanner is unavailable on this server")

        result = subprocess.run(
            [clamscan, "--no-summary", file_path],
            capture_output=True,
            text=True,
            check=False,
        )

        if result.returncode == 0:
            return
        if result.returncode == 1:
            raise ValidationError("Uploaded file failed virus scan")

        raise ValidationError(
            f"Virus scan could not complete successfully: {result.stderr.strip()}"
        )

    def initiate_upload(
        self,
        organization_id: str,
        file_name: str,
        file_size: int,
        mime_type: str,
        form_id: str = None,
        response_id: str = None,
        question_id: str = None,
        user_context: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """
        Initiate a new file upload (tus protocol).
        """
        try:
            # Validate file type and size
            file_type = self._validate_file_type(file_name, mime_type)
            self._validate_file_size(file_size, file_type)
            
            # Check tenant quota
            TenantService().check_storage_quota(organization_id, file_size)
            
            # Generate upload ID
            upload_id = str(uuid.uuid4())
            
            # Create file upload record
            upload_data = {
                'organization_id': organization_id,
                'form_id': form_id,
                'response_id': response_id,
                'question_id': question_id,
                'original_filename': file_name,
                'file_type': file_type,
                'mime_type': mime_type,
                'file_size_bytes': file_size,
                'upload_status': 'pending',
                'upload_offset': 0,
                'uploaded_by': user_context.get('user_id') if user_context else None,
                'checksum_sha256': None,
                'virus_scan_status': 'pending'
            }
            
            file_upload = FileUpload(**upload_data)
            file_upload.save()
            
            audit_logger.info(
                f"AUDIT: File upload initiated for {file_name} ({file_size} bytes) "
                f"by {(user_context or {}).get('user_id', 'anonymous')}"
            )
            
            return {
                'upload_id': str(file_upload.id),
                'upload_url': f"/api/v1/files/{file_upload.id}/upload",
                'chunk_size': self.chunk_size,
                'file_type': file_type,
                'max_file_size': self.max_file_sizes[file_type]
            }
            
        except Exception as e:
            error_logger.error(f"Failed to initiate file upload: {str(e)}", exc_info=True)
            raise

    def upload_chunk(
        self,
        upload_id: str,
        chunk_data: bytes,
        chunk_offset: int,
        is_final: bool = False,
        user_context: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """
        Upload a chunk of data for a resumable upload.
        """
        try:
            # Get upload record
            file_upload = FileUpload.objects(
                id=upload_id,
                is_deleted=False
            ).first()
            
            if not file_upload:
                raise NotFoundError("File upload not found")
            
            # Validate upload status
            if file_upload.upload_status == 'complete':
                raise ValidationError("File upload is already complete")
            
            if file_upload.upload_status == 'failed':
                raise ValidationError("File upload has failed. Please restart the upload.")
            
            # Validate chunk offset
            if chunk_offset != file_upload.upload_offset:
                raise ValidationError(
                    f"Chunk offset mismatch. Expected {file_upload.upload_offset}, got {chunk_offset}"
                )
            
            # Generate file path if not exists
            if not file_upload.file_path:
                file_path = self._generate_file_path(
                    file_upload.organization_id,
                    str(file_upload.id),
                    file_upload.original_filename
                )
                file_upload.file_path = file_path
                file_upload.upload_status = 'uploading'
                file_upload.save()
            
            # Write chunk to file
            mode = 'ab' if chunk_offset > 0 else 'wb'
            with open(file_upload.file_path, mode) as f:
                f.seek(chunk_offset)
                f.write(chunk_data)
            
            # Update upload progress
            new_offset = chunk_offset + len(chunk_data)
            file_upload.upload_offset = new_offset
            
            if is_final:
                file_upload.virus_scan_status = 'pending'
                file_upload.checksum_sha256 = self._calculate_checksum(file_upload.file_path)
                self._validate_file_signature(
                    file_upload.file_path,
                    file_upload.file_type,
                )
                self._run_virus_scan(file_upload.file_path)
                file_upload.virus_scan_status = 'clean'
                file_upload.upload_status = 'complete'
                
                # Update tenant storage usage
                TenantService().record_file_upload(
                    file_upload.organization_id,
                    file_upload.file_size_bytes
                )
            
            file_upload.save()
            
            return {
                'upload_id': upload_id,
                'next_offset': new_offset,
                'upload_complete': is_final,
                'progress': round((new_offset / file_upload.file_size_bytes) * 100, 2)
            }
            
        except Exception as e:
            error_logger.error(f"Failed to upload chunk: {str(e)}", exc_info=True)
            
            # Mark upload as failed
            FileUpload.objects(id=upload_id).update(
                upload_status='failed',
                upload_offset=0
            )
            
            raise

    def get_upload_info(
        self,
        upload_id: str,
        user_context: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """
        Get information about an upload.
        """
        file_upload = FileUpload.objects(
            id=upload_id,
            is_deleted=False
        ).first()
        
        if not file_upload:
            raise NotFoundError("File upload not found")
        
        return {
            'upload_id': upload_id,
            'file_name': file_upload.original_filename,
            'file_size': file_upload.file_size_bytes,
            'file_type': file_upload.file_type,
            'mime_type': file_upload.mime_type,
            'upload_status': file_upload.upload_status,
            'upload_offset': file_upload.upload_offset,
            'progress': round((file_upload.upload_offset / file_upload.file_size_bytes) * 100, 2) if file_upload.file_size_bytes > 0 else 0,
            'created_at': file_upload.created_at.isoformat(),
            'updated_at': file_upload.updated_at.isoformat()
        }

    def complete_upload(
        self,
        upload_id: str,
        user_context: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """
        Mark an upload as complete and perform final validation.
        """
        try:
            file_upload = FileUpload.objects(
                id=upload_id,
                is_deleted=False
            ).first()
            
            if not file_upload:
                raise NotFoundError("File upload not found")
            
            if file_upload.upload_status == 'complete':
                return {'upload_id': upload_id, 'status': 'already_complete'}
            
            # Verify file size
            if os.path.exists(file_upload.file_path):
                actual_size = os.path.getsize(file_upload.file_path)
                if actual_size != file_upload.file_size_bytes:
                    raise ValidationError(
                        f"File size mismatch. Expected {file_upload.file_size_bytes}, got {actual_size}"
                    )
                file_upload.virus_scan_status = 'pending'
                self._validate_file_signature(file_upload.file_path, file_upload.file_type)
                self._run_virus_scan(file_upload.file_path)
            
            # Mark as complete
            file_upload.upload_status = 'complete'
            file_upload.virus_scan_status = 'clean'
            file_upload.checksum_sha256 = self._calculate_checksum(file_upload.file_path)
            file_upload.save()
            
            # Update tenant storage usage
            TenantService().record_file_upload(
                file_upload.organization_id,
                file_upload.file_size_bytes
            )
            
            audit_logger.info(
                f"AUDIT: File upload completed for {file_upload.original_filename} "
                f"by {(user_context or {}).get('user_id', 'anonymous')}"
            )
            
            return {
                'upload_id': upload_id,
                'file_id': upload_id,
                'file_name': file_upload.original_filename,
                'file_size': file_upload.file_size_bytes,
                'checksum': file_upload.checksum_sha256,
                'status': 'complete'
            }
            
        except Exception as e:
            error_logger.error(f"Failed to complete upload: {str(e)}", exc_info=True)
            raise

    def cancel_upload(
        self,
        upload_id: str,
        user_context: Dict[str, Any] = None
    ) -> None:
        """
        Cancel an upload and delete the file.
        """
        try:
            file_upload = FileUpload.objects(
                id=upload_id,
                is_deleted=False
            ).first()
            
            if not file_upload:
                raise NotFoundError("File upload not found")
            
            # Delete file if exists
            if file_upload.file_path and os.path.exists(file_upload.file_path):
                os.remove(file_upload.file_path)
            
            # Mark upload as failed
            file_upload.upload_status = 'failed'
            file_upload.save()
            
            audit_logger.info(
                f"AUDIT: File upload cancelled for {file_upload.original_filename} "
                f"by {(user_context or {}).get('user_id', 'anonymous')}"
            )
            
        except Exception as e:
            error_logger.error(f"Failed to cancel upload: {str(e)}", exc_info=True)
            raise

    def get_file_url(
        self,
        file_id: str,
        organization_id: str,
        user_context: Dict[str, Any] = None
    ) -> str:
        """
        Generate a secure URL for accessing a file.
        """
        file_upload = FileUpload.objects(
            id=file_id,
            organization_id=organization_id,
            upload_status='complete',
            is_deleted=False
        ).first()
        
        if not file_upload:
            raise NotFoundError("File not found")
        
        # Generate signed URL with expiration
        from datetime import datetime, timedelta
        import jwt
        from config.settings import settings
        
        payload = {
            'file_id': str(file_upload.id),
            'organization_id': organization_id,
            'exp': datetime.utcnow() + timedelta(hours=1)  # 1 hour expiration
        }
        
        token = jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm='HS256')
        
        return f"/api/v1/files/{file_upload.id}/download?token={token}"

    def list_files(
        self,
        organization_id: str,
        form_id: str = None,
        response_id: str = None,
        file_type: str = None,
        limit: int = 50,
        offset: int = 0
    ) -> List[Dict[str, Any]]:
        """
        List uploaded files with filtering.
        """
        query = FileUpload.objects(
            organization_id=organization_id,
            upload_status='complete',
            is_deleted=False
        ).order_by('-created_at')
        
        if form_id:
            query = query.filter(form_id=form_id)
        
        if response_id:
            query = query.filter(response_id=response_id)
        
        if file_type:
            query = query.filter(file_type=file_type)
        
        files = query.skip(offset).limit(limit)
        
        return [
            {
                'file_id': str(file.id),
                'file_name': file.original_filename,
                'file_size': file.file_size_bytes,
                'file_type': file.file_type,
                'mime_type': file.mime_type,
                'upload_status': file.upload_status,
                'created_at': file.created_at.isoformat(),
                'checksum': file.checksum_sha256
            }
            for file in files
        ]

    def delete_file(
        self,
        file_id: str,
        organization_id: str,
        user_context: Dict[str, Any] = None
    ) -> None:
        """
        Delete a file upload.
        """
        try:
            file_upload = FileUpload.objects(
                id=file_id,
                organization_id=organization_id,
                is_deleted=False
            ).first()
            
            if not file_upload:
                raise NotFoundError("File not found")
            
            # Delete physical file
            if file_upload.file_path and os.path.exists(file_upload.file_path):
                os.remove(file_upload.file_path)
            
            # Soft delete record
            file_upload.is_deleted = True
            file_upload.deleted_at = datetime.now(timezone.utc)
            file_upload.save()
            
            # Update tenant storage usage
            TenantService().record_file_deletion(
                organization_id,
                file_upload.file_size_bytes
            )
            
            audit_logger.info(
                f"AUDIT: File {file_upload.original_filename} deleted "
                f"by {(user_context or {}).get('user_id', 'anonymous')}"
            )
            
        except Exception as e:
            error_logger.error(f"Failed to delete file: {str(e)}", exc_info=True)
            raise

    def cleanup_expired_uploads(self) -> Dict[str, Any]:
        """
        Clean up expired and incomplete uploads.
        """
        try:
            # Find uploads that are pending for more than 24 hours
            expiry_time = datetime.now(timezone.utc) - timedelta(hours=24)
            
            expired_uploads = FileUpload.objects(
                upload_status__in=['pending', 'uploading', 'failed'],
                created_at__lt=expiry_time,
                is_deleted=False
            )
            
            deleted_count = 0
            total_size = 0
            
            for upload in expired_uploads:
                # Delete physical file
                if upload.file_path and os.path.exists(upload.file_path):
                    os.remove(upload.file_path)
                
                total_size += upload.file_size_bytes
                deleted_count += 1
                
                # Mark as deleted
                upload.is_deleted = True
                upload.deleted_at = datetime.now(timezone.utc)
                upload.save()
            
            app_logger.info(f"Cleaned up {deleted_count} expired uploads ({total_size} bytes)")
            
            return {
                'deleted_count': deleted_count,
                'total_size_bytes': total_size,
                'cleanup_time': datetime.now(timezone.utc).isoformat()
            }
            
        except Exception as e:
            error_logger.error(f"Failed to cleanup expired uploads: {str(e)}", exc_info=True)
            raise
