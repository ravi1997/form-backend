from typing import Type, TypeVar, List, Optional, Any, Dict, Tuple
from mongoengine.errors import DoesNotExist, ValidationError as MongoValidationError, NotUniqueError
from pydantic import BaseModel
from models.base import BaseDocument
from .exceptions import NotFoundError, ValidationError, ConflictError
from logger.unified_logger import app_logger, error_logger, audit_logger
from schemas.base import PaginatedResult

TModel = TypeVar('TModel', bound=BaseDocument)
TSchema = TypeVar('TSchema', bound=BaseModel)
TCreateSchema = TypeVar('TCreateSchema', bound=BaseModel)
TUpdateSchema = TypeVar('TUpdateSchema', bound=BaseModel)

class BaseService:
    """
    Enterprise-grade Base Service for MongoDB operations using MongoEngine and Pydantic.
    Features strict error handling, optimized pagination, and projection patterns.
    """

    def __init__(self, model: Type[TModel], schema: Type[TSchema]):
        self.model = model
        self.schema = schema

    def _to_schema(self, document: TModel) -> TSchema:
        try:
            if hasattr(document, 'to_dict'):
                doc_dict = document.to_dict()
            else:
                doc_dict = document.to_mongo().to_dict()
            
            if '_id' in doc_dict and 'id' not in doc_dict:
                doc_dict['id'] = str(doc_dict.pop('_id'))
            
            return self.schema.model_validate(doc_dict)
        except Exception as e:
            error_logger.error(f"Schema validation failed for Model {self.model.__name__}: {str(e)}", exc_info=True)
            raise ValidationError(f"Data corruption detected in DB for {self.model.__name__}", details={'error': str(e)})

    def get_by_id(self, doc_id: str, organization_id: str = None, fields: List[str] = None) -> TSchema:
        app_logger.debug(f"Entering get_by_id for {self.model.__name__}: {doc_id} (org: {organization_id})")
        try:
            filters = {'id': doc_id}
            if organization_id:
                filters['organization_id'] = organization_id
                
            query = self.model.objects(**filters)
            if hasattr(self.model, 'is_deleted'):
                query = query.filter(is_deleted=False)
            if fields:
                query = query.only(*fields)
            
            document = query.get()
            result = self._to_schema(document)
            app_logger.debug(f"Exiting get_by_id for {self.model.__name__}: {doc_id} successfully")
            return result
        except (DoesNotExist, ValueError):
            app_logger.warning(f"{self.model.__name__} with id {doc_id} (org: {organization_id}) not found.")
            raise NotFoundError(f"{self.model.__name__} not found")
        except Exception as e:
            error_logger.error(f"Error in get_by_id for {self.model.__name__} {doc_id}: {str(e)}", exc_info=True)
            raise

    def list_paginated(self, page: int = 1, page_size: int = None, sort_by: str = '-created_at', organization_id: str = None, **filters) -> PaginatedResult:
        app_logger.debug(f"Entering list_paginated for {self.model.__name__} (org: {organization_id})")
        from config.settings import settings
        
        # Enforce limits
        page = max(1, page)
        page_size = page_size or settings.DEFAULT_PAGE_SIZE
        page_size = min(page_size, settings.MAX_PAGE_SIZE)
        
        if hasattr(self.model, 'is_deleted'):
            filters.setdefault('is_deleted', False)
        
        if organization_id:
            filters['organization_id'] = organization_id
            
        skip = (page - 1) * page_size
        query = self.model.objects(**filters).order_by(sort_by)
        total = query.count()
        documents = query.skip(skip).limit(page_size)
        
        items = [self._to_schema(doc) for doc in documents]
        
        app_logger.debug(f"Exiting list_paginated for {self.model.__name__} successfully: {len(items)}/{total} items")
        return PaginatedResult(
            items=items,
            total=total,
            page=page,
            page_size=page_size,
            has_next=(skip + page_size < total),
            success=True
        )

    def create(self, create_schema: TCreateSchema) -> TSchema:
        app_logger.info(f"Entering create for {self.model.__name__}")
        try:
            data = create_schema.model_dump(exclude_unset=True)
            document = self.model(**data)
            document.save()
            doc_id = getattr(document, 'id', 'unknown')
            org_id = getattr(document, 'organization_id', 'unknown')
            
            app_logger.info(f"Created {self.model.__name__} with ID {doc_id}")
            audit_logger.info(f"Audit: Created {self.model.__name__} with ID {doc_id} (org: {org_id})")
            
            result = self._to_schema(document)
            app_logger.debug(f"Exiting create for {self.model.__name__} successfully")
            return result
        except NotUniqueError as e:
            app_logger.warning(f"Conflict error creating {self.model.__name__}: {str(e)}")
            raise ConflictError(f"{self.model.__name__} uniqueness constraint failed", details={'error': str(e)})
        except MongoValidationError as e:
            app_logger.warning(f"DB constraint error creating {self.model.__name__}: {str(e)}")
            raise ValidationError(f"Invalid data for {self.model.__name__}", details={'error': str(e)})
        except Exception as e:
            error_logger.error(f"Error creating {self.model.__name__}: {str(e)}", exc_info=True)
            raise

    def update(self, doc_id: str, update_schema: TUpdateSchema, organization_id: str = None) -> TSchema:
        app_logger.info(f"Entering update for {self.model.__name__} {doc_id} (org: {organization_id})")
        try:
            filters = {'id': doc_id}
            if organization_id:
                filters['organization_id'] = organization_id
                
            document = self.model.objects(**filters).get()
            if hasattr(document, 'is_deleted') and document.is_deleted:
                raise DoesNotExist()
            
            update_data = update_schema.model_dump(exclude_unset=True)
            if update_data:
                document.update(**{f"set__{k}": v for k, v in update_data.items()})
                document.reload()
            
            app_logger.info(f"Updated {self.model.__name__} {doc_id} (org: {organization_id})")
            audit_logger.info(f"Audit: Updated {self.model.__name__} {doc_id} (org: {organization_id})")
            
            result = self._to_schema(document)
            app_logger.debug(f"Exiting update for {self.model.__name__} {doc_id} successfully")
            return result
        except (DoesNotExist, ValueError):
            app_logger.warning(f"{self.model.__name__} not found for update: {doc_id}")
            raise NotFoundError(f"{self.model.__name__} not found for update")
        except NotUniqueError as e:
            app_logger.warning(f"Update caused a uniqueness conflict in {self.model.__name__} {doc_id}: {str(e)}")
            raise ConflictError(f"Update caused a uniqueness conflict in {self.model.__name__}", details={'error': str(e)})
        except MongoValidationError as e:
            app_logger.warning(f"Database validation failed on update for {self.model.__name__} {doc_id}: {str(e)}")
            raise ValidationError(f"Database validation failed on update", details={'error': str(e)})
        except Exception as e:
            error_logger.error(f"Error updating {self.model.__name__} {doc_id}: {str(e)}", exc_info=True)
            raise

    def delete(self, doc_id: str, organization_id: str = None, hard_delete: bool = False) -> None:
        app_logger.info(f"Entering delete for {self.model.__name__} {doc_id} (org: {organization_id}, hard: {hard_delete})")
        try:
            filters = {'id': doc_id}
            if organization_id:
                filters['organization_id'] = organization_id
                
            document = self.model.objects(**filters).get()
            if hasattr(document, 'soft_delete') and not hard_delete:
                document.soft_delete()
                app_logger.info(f"Soft deleted {self.model.__name__} {doc_id} (org: {organization_id})")
                audit_logger.info(f"Audit: Soft deleted {self.model.__name__} {doc_id} (org: {organization_id})")
                return None
            
            document.delete()
            app_logger.warning(f"HARD deleted {self.model.__name__} {doc_id} (org: {organization_id})")
            audit_logger.info(f"Audit: HARD deleted {self.model.__name__} {doc_id} (org: {organization_id})")
            return None
        except (DoesNotExist, ValueError):
            app_logger.warning(f"{self.model.__name__} not found for deletion: {doc_id}")
            raise NotFoundError(f"{self.model.__name__} not found for deletion")
        except Exception as e:
            error_logger.error(f"Error deleting {self.model.__name__} {doc_id}: {str(e)}", exc_info=True)
            raise
