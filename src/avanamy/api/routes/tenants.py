# src/avanamy/api/routes/tenants.py

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from uuid import UUID

from avanamy.db.database import SessionLocal
from avanamy.models.tenant import Tenant
from pydantic import BaseModel

router = APIRouter(prefix="/tenants", tags=["Tenants"])


# --------------------------
# DB Dependency
# --------------------------
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# --------------------------
# Pydantic Models
# --------------------------
class TenantOut(BaseModel):
    id: UUID
    name: str
    slug: str

    class Config:
        from_attributes = True


# --------------------------
# GET /tenants
# --------------------------
@router.get("/", response_model=list[TenantOut])
def list_tenants(db: Session = Depends(get_db)):
    tenants = db.query(Tenant).order_by(Tenant.name.asc()).all()
    return tenants


# --------------------------
# GET /tenants/{tenant_id}
# --------------------------
@router.get("/{tenant_id}", response_model=TenantOut)
def get_tenant(tenant_id: str, db: Session = Depends(get_db)):
    tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()

    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")

    return tenant
