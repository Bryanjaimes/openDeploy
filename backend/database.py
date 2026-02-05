from sqlalchemy import create_engine, Column, Integer, String, DateTime, JSON, func
from sqlalchemy.orm import DeclarativeBase, sessionmaker
import datetime
import os

DATABASE_URL = os.getenv("OPENDEPLOY_DATABASE_URL", "sqlite:///./opendeploy.db")

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


class Prediction(Base):
    __tablename__ = "predictions"

    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(DateTime, server_default=func.now())
    model = Column(String, index=True)
    input = Column(String)
    result = Column(JSON)


def init_db():
    Base.metadata.create_all(bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
