from fastapi import FastAPI, Depends, HTTPException
from sqlalchemy import create_engine, Column, Integer, String, JSON, Date, Float, DateTime, Boolean, LargeBinary, Time
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.dialects.postgresql import ARRAY
import json
from datetime import datetime
from typing import Dict, Any
from fastapi.middleware.cors import CORSMiddleware
import bcrypt

from contextlib import asynccontextmanager
from app.core.config import settings
from app.api.v1.api import api_router
from app.db.supabase import supabase_client  # Add this import

async def lifespan(app: FastAPI):
    # Startup - verify database connection
    try:
        response = supabase_client.table('forms').select("count", count='exact').execute()
        print("Database connection successful!")
    except Exception as e:
        print(f"Failed to connect to database: {str(e)}")
        raise e
    
    yield
    # Shutdown
    print("Shutting down...")


# Database setup
DATABASE_URL = "postgresql://postgres:qnqkjqniswqj@db.flpmacyijdakjsgyhjtg.supabase.co/postgres"
engine = create_engine(DATABASE_URL, connect_args={"sslmode": "require"})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# Load form definition
def load_form_definition():
    with open('app/form_definitions/user_form.json', 'r') as f:
        return json.load(f)

# Enhanced type mapping for dynamic table generation
TYPE_MAPPING = {
    # Basic types
    "text": String,
    "email": String,
    "password": String,  # Will be hashed before storage
    "number": Float,
    "tel": String,
    "url": String,
    "search": String,
    "textarea": String,
    
    # Complex types
    "select": JSON,  # Store as JSON to handle options
    "radio": String,
    "checkbox": ARRAY(String),  # Store as PostgreSQL array
    
    # Date and Time types
    "date": Date,
    "time": Time,
    "datetime-local": DateTime,
    "month": String,
    "week": String,
    
    # Special types
    "file": String,  # Store file path/URL
    "hidden": String,
    "range": Float,
    "color": String,
    "rating": Integer,
    "toggle": Boolean,
    "image": String,  # Store image path/URL
}

def generate_table_class(form_definition: dict):
    table_name = f"form_{form_definition['form_id']}_data"
    
    # Create column definitions
    columns = {
        "__tablename__": table_name,
        "id": Column(Integer, primary_key=True, index=True),
        "created_at": Column(DateTime, default=datetime.utcnow),
        "updated_at": Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    }
    
    # Add columns based on form fields
    for field in form_definition["form_data"]:
        field_type = TYPE_MAPPING.get(field["type"], String)
        
        # Special handling for certain types
        if field["type"] == "password":
            # Add salt column for password fields
            salt_column_name = f"{field['id']}_salt"
            columns[salt_column_name] = Column(LargeBinary)
        
        columns[field["id"]] = Column(field_type)
    
    return type(table_name, (Base,), columns)

# Create FastAPI app
app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:8000","http://localhost:3001","http://localhost:3002", "http://localhost:8001"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


app.include_router(api_router, prefix="/api/v1")

# Dependency
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# Load form definition and create table
form_definition = load_form_definition()
DynamicTable = generate_table_class(form_definition)
Base.metadata.create_all(bind=engine)

# Dynamic CRUD endpoints
@app.post(f"/api/forms/{form_definition['form_id']}/data")
async def create_record(data: Dict[str, Any], db: Session = Depends(get_db)):
    processed_data = {}
    
    for field in form_definition["form_data"]:
        field_id = field["id"]
        field_value = data.get(field_id)
        
        if field_value is None:
            continue
            
        if field["type"] == "password":
            # Hash password
            salt = bcrypt.gensalt()
            hashed = bcrypt.hashpw(field_value.encode('utf-8'), salt)
            processed_data[field_id] = hashed
            processed_data[f"{field_id}_salt"] = salt
        elif field["type"] == "checkbox":
            # Store checkbox values as array
            processed_data[field_id] = field_value if isinstance(field_value, list) else [field_value]
        elif field["type"] in ["select", "radio"]:
            # Validate against available options
            if field_value in field["options"]:
                processed_data[field_id] = field_value
        else:
            processed_data[field_id] = field_value
    
    db_record = DynamicTable(**processed_data)
    db.add(db_record)
    db.commit()
    db.refresh(db_record)
    return db_record

@app.get(f"/api/forms/{form_definition['form_id']}/data/{{record_id}}")
async def get_record(record_id: int, db: Session = Depends(get_db)):
    record = db.query(DynamicTable).filter(DynamicTable.id == record_id).first()
    if not record:
        raise HTTPException(status_code=404, detail="Record not found")
    return record

@app.get(f"/api/forms/{form_definition['form_id']}/data")
async def list_records(skip: int = 0, limit: int = 10, db: Session = Depends(get_db)):
    records = db.query(DynamicTable).offset(skip).limit(limit).all()
    return records

@app.put(f"/api/forms/{form_definition['form_id']}/data/{{record_id}}")
async def update_record(record_id: int, data: Dict[str, Any], db: Session = Depends(get_db)):
    record = db.query(DynamicTable).filter(DynamicTable.id == record_id).first()
    if not record:
        raise HTTPException(status_code=404, detail="Record not found")
    
    for key, value in data.items():
        setattr(record, key, value)
    
    db.commit()
    db.refresh(record)
    return record

@app.delete(f"/api/forms/{form_definition['form_id']}/data/{{record_id}}")
async def delete_record(record_id: int, db: Session = Depends(get_db)):
    record = db.query(DynamicTable).filter(DynamicTable.id == record_id).first()
    if not record:
        raise HTTPException(status_code=404, detail="Record not found")
    
    db.delete(record)
    db.commit()
    return {"status": "success", "message": "Record deleted"}