# src/avanamy/repositories/code_repo_repository.py

"""
Code Repository data access layer.
"""

from __future__ import annotations
from uuid import UUID
from sqlalchemy.orm import Session
from avanamy.models.code_repository import CodeRepository


class CodeRepoRepository:
    """
    Data access methods for CodeRepository model.
    """
    
    @staticmethod
    def create(
        db: Session,
        *,
        tenant_id: str,
        name: str,
        url: str,
        owner_team: str | None = None,
        owner_email: str | None = None,
        github_installation_id: str | None = None,
        access_token_encrypted: str | None = None,
    ) -> CodeRepository:
        """
        Create a new code repository.
        
        Args:
            db: Database session
            tenant_id: Tenant ID
            name: Repository name
            url: Repository URL
            owner_team: Owner team name
            owner_email: Owner email
            github_installation_id: GitHub installation ID
            access_token_encrypted: Encrypted access token
            
        Returns:
            Created repository
        """
        code_repository = CodeRepository(
            tenant_id=tenant_id,
            name=name,
            url=url,
            owner_team=owner_team,
            owner_email=owner_email,
            github_installation_id=github_installation_id,
            access_token_encrypted=access_token_encrypted,
            scan_status="pending",
        )
        
        db.add(code_repository)
        db.commit()
        db.refresh(code_repository)
        
        return code_repository
    
    @staticmethod
    def get_by_id(db: Session, code_repository_id: UUID) -> CodeRepository | None:
        """
        Get code repository by ID.
        
        Args:
            db: Database session
            code_repository_id: Repository UUID
            
        Returns:
            CodeRepository or None
        """
        return db.query(CodeRepository).filter(CodeRepository.id == code_repository_id).first()
    
    @staticmethod
    def get_by_tenant(db: Session, tenant_id: str) -> list[CodeRepository]:
        """
        Get all code repositories for a tenant.
        
        Args:
            db: Database session
            tenant_id: Tenant ID
            
        Returns:
            List of code repositories
        """
        return db.query(CodeRepository).filter(CodeRepository.tenant_id == tenant_id).all()
    
    @staticmethod
    def update(
        db: Session,
        code_repository: CodeRepository,
        **kwargs
    ) -> CodeRepository:
        """
        Update code repository fields.
        
        Args:
            db: Database session
            code_repository: CodeRepository to update
            **kwargs: Fields to update
            
        Returns:
            Updated code repository
        """
        for key, value in kwargs.items():
            if hasattr(code_repository, key):
                setattr(code_repository, key, value)
        
        db.commit()
        db.refresh(code_repository)
        
        return code_repository
    
    @staticmethod
    def delete(db: Session, code_repository: CodeRepository) -> None:
        """
        Delete a code repository.
        
        Args:
            db: Database session
            code_repository: CodeRepository to delete
        """
        db.delete(code_repository)
        db.commit()