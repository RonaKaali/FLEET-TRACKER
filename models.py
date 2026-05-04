import sys
from datetime import datetime
from sqlalchemy import Column, Integer, String, Float, DateTime, create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

Base = declarative_base()

class Employee(Base):
    __tablename__ = "employees"
    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    health_status = Column(String, default="aktif")
    lat = Column(Float, nullable=True)
    lon = Column(Float, nullable=True)
    last_seen = Column(DateTime, nullable=True)

    def __repr__(self):
        return f"<Employee {self.id}:{self.name}>"

class Asset(Base):
    __tablename__ = "assets"
    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    description = Column(String, default="")
    lat = Column(Float, nullable=True)
    lon = Column(Float, nullable=True)
    last_update = Column(DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f"<Asset {self.id}:{self.name}>"

class LocationLog(Base):
    __tablename__ = "location_logs"
    id = Column(Integer, primary_key=True)
    entity_type = Column(String, nullable=False)  # "employees" atau "assets"
    entity_id = Column(Integer, nullable=False)
    lat = Column(Float, nullable=False)
    lon = Column(Float, nullable=False)
    timestamp = Column(DateTime, default=datetime.utcnow)
    address = Column(String, nullable=True)

    def __repr__(self):
        return f"<LocationLog {self.entity_type}:{self.entity_id} @ {self.lat},{self.lon}>"

engine = create_engine("sqlite:///fleet.db", echo=False)
SessionLocal = sessionmaker(bind=engine)

def init_db():
    """Create tables if they do not exist."""
    Base.metadata.create_all(bind=engine)

def get_session():
    return SessionLocal()
