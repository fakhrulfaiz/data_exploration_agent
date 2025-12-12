"""Base repository for async SQLAlchemy operations."""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, TypeVar, Generic, Type
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, delete, func
from sqlalchemy.exc import SQLAlchemyError
import logging

logger = logging.getLogger(__name__)

T = TypeVar('T')


class BaseRepository(ABC, Generic[T]):
    """Base repository with async SQLAlchemy operations."""
    
    def __init__(self, session: AsyncSession, model: Type[T]):
        self.session = session
        self.model = model
    
    async def create(self, entity: T) -> bool:
        try:
            self.session.add(entity)
            await self.session.flush()
            return True
        except SQLAlchemyError as e:
            logger.error(f"Error creating {self.model.__name__}: {e}")
            await self.session.rollback()
            raise Exception(f"Failed to create {self.model.__name__}: {e}")
    
    async def find_by_id(self, entity_id: Any, id_field: str = "id") -> Optional[T]:
        """
        Find entity by ID field.
        
        Args:
            entity_id: ID value to search for
            id_field: Name of the ID field (default: "id")
            
        Returns:
            Entity if found, None otherwise
        """
        try:
            stmt = select(self.model).where(getattr(self.model, id_field) == entity_id)
            result = await self.session.execute(stmt)
            return result.scalar_one_or_none()
        except SQLAlchemyError as e:
            logger.error(f"Error finding {self.model.__name__} by {id_field}={entity_id}: {e}")
            raise Exception(f"Failed to find {self.model.__name__}: {e}")
    
    async def update_by_id(
        self, 
        entity_id: Any, 
        update_data: Dict[str, Any], 
        id_field: str = "id"
    ) -> bool:
        """
        Update entity by ID field.
        
        Args:
            entity_id: ID value to search for
            update_data: Dictionary of fields to update
            id_field: Name of the ID field (default: "id")
            
        Returns:
            True if updated, False otherwise
        """
        try:
            stmt = (
                update(self.model)
                .where(getattr(self.model, id_field) == entity_id)
                .values(**update_data)
            )
            result = await self.session.execute(stmt)
            await self.session.flush()
            return result.rowcount > 0
        except SQLAlchemyError as e:
            logger.error(f"Error updating {self.model.__name__} {id_field}={entity_id}: {e}")
            await self.session.rollback()
            raise Exception(f"Failed to update {self.model.__name__}: {e}")
    
    async def delete_by_id(self, entity_id: Any, id_field: str = "id") -> bool:
        try:
            stmt = delete(self.model).where(getattr(self.model, id_field) == entity_id)
            result = await self.session.execute(stmt)
            await self.session.flush()
            return result.rowcount > 0
        except SQLAlchemyError as e:
            logger.error(f"Error deleting {self.model.__name__} {id_field}={entity_id}: {e}")
            await self.session.rollback()
            raise Exception(f"Failed to delete {self.model.__name__}: {e}")
    
    async def delete_many(self, filter_criteria: Dict[str, Any]) -> int:
        """
        Delete multiple entities matching filter criteria.
        
        Args:
            filter_criteria: Dictionary of field:value pairs to filter by
            
        Returns:
            Number of deleted entities
        """
        try:
            stmt = delete(self.model)
            for field, value in filter_criteria.items():
                stmt = stmt.where(getattr(self.model, field) == value)
            
            result = await self.session.execute(stmt)
            await self.session.flush()
            logger.info(f"Deleted {result.rowcount} {self.model.__name__} entities")
            return result.rowcount
        except SQLAlchemyError as e:
            logger.error(f"Error deleting {self.model.__name__} entities: {e}")
            await self.session.rollback()
            raise Exception(f"Failed to delete {self.model.__name__} entities: {e}")
    
    async def find_many(
        self,
        filter_criteria: Optional[Dict[str, Any]] = None,
        limit: Optional[int] = None,
        skip: Optional[int] = None,
        order_by: Optional[List[Any]] = None
    ) -> List[T]:

        try:
            stmt = select(self.model)
            
            if filter_criteria:
                for field, value in filter_criteria.items():
                    stmt = stmt.where(getattr(self.model, field) == value)
            
            if order_by:
                stmt = stmt.order_by(*order_by)
            
            if skip:
                stmt = stmt.offset(skip)
            if limit:
                stmt = stmt.limit(limit)
            
            result = await self.session.execute(stmt)
            return list(result.scalars().all())
        except SQLAlchemyError as e:
            logger.error(f"Error finding {self.model.__name__} entities: {e}")
            raise Exception(f"Failed to find {self.model.__name__} entities: {e}")
    
    async def count(self, filter_criteria: Optional[Dict[str, Any]] = None) -> int:
        """
        Count entities matching filter criteria.
        
        Args:
            filter_criteria: Dictionary of field:value pairs to filter by
            
        Returns:
            Count of matching entities
        """
        try:
            stmt = select(func.count()).select_from(self.model)
            
            if filter_criteria:
                for field, value in filter_criteria.items():
                    stmt = stmt.where(getattr(self.model, field) == value)
            
            result = await self.session.execute(stmt)
            return result.scalar() or 0
        except SQLAlchemyError as e:
            logger.error(f"Error counting {self.model.__name__} entities: {e}")
            return 0
