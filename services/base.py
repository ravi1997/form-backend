from typing import Type, TypeVar, List, Optional, Any, Dict, Tuple
from mongoengine.errors import DoesNotExist, ValidationError as MongoValidationError, NotUniqueError
from pydantic import BaseModel
from models.base import BaseDocument
from .exceptions import NotFoundError, ValidationError, ConflictError
from logger import get_logger, error_logger
from schemas.base import PaginatedResult

logger = get_logger(__name__)

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
            return self._to_schema(document)
        except (DoesNotExist, ValueError):
            logger.debug(f"{self.model.__name__} with id {doc_id} (org: {organization_id}) not found.")
            raise NotFoundError(f"{self.model.__name__} not found")

    def list_paginated(self, page: int = 1, page_size: int = None, sort_by: str = '-created_at', organization_id: str = None, **filters) -> PaginatedResult:
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
        
        return PaginatedResult(
            items=items,
            total=total,
            page=page,
            page_size=page_size,
            has_next=(skip + page_size < total),
            success=True
        )

    def create(self, create_schema: TCreateSchema) -> TSchema:
        try:
            data = create_schema.model_dump(exclude_unset=True)
            document = self.model(**data)
            document.save()
            logger.info(f"Created {self.model.__name__} with ID {getattr(document, 'id', 'unknown')}")
            return self._to_schema(document)
        except NotUniqueError as e:
            logger.warning(f"Conflict error creating {self.model.__name__}: {str(e)}")
            raise ConflictError(f"{self.model.__name__} uniqueness constraint failed", details={'error': str(e)})
        except MongoValidationError as e:
            logger.warning(f"DB constraint error creating {self.model.__name__}: {str(e)}")
            raise ValidationError(f"Invalid data for {self.model.__name__}", details={'error': str(e)})

    def update(self, doc_id: str, update_schema: TUpdateSchema, organization_id: str = None) -> TSchema:
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
            logger.info(f"Updated {self.model.__name__} {doc_id} (org: {organization_id})")
            return self._to_schema(document)
        except (DoesNotExist, ValueError):
            raise NotFoundError(f"{self.model.__name__} not found for update")
        except NotUniqueError as e:
            raise ConflictError(f"Update caused a uniqueness conflict in {self.model.__name__}", details={'error': str(e)})
        except MongoValidationError as e:
            raise ValidationError(f"Database validation failed on update", details={'error': str(e)})

    def delete(self, doc_id: str, organization_id: str = None, hard_delete: bool = False) -> None:
        try:
            filters = {'id': doc_id}
            if organization_id:
                filters['organization_id'] = organization_id
                
            document = self.model.objects(**filters).get()
            if hasattr(document, 'soft_delete') and not hard_delete:
                document.soft_delete()
                logger.info(f"Soft deleted {self.model.__name__} {doc_id} (org: {organization_id})")
                return None
            
            document.delete()
            logger.warning(f"HARD deleted {self.model.__name__} {doc_id} (org: {organization_id})")
            return None
        except (DoesNotExist, ValueError):
            raise NotFoundError(f"{self.model.__name__} not found for deletion")
