"""
Student model
กำหนด structure ของ table students
"""
from sqlalchemy import Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from db.database import Base


class Student(Base):
    """
    Model สำหรับ table students
    """
    __tablename__ = "students"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    age: Mapped[int] = mapped_column(Integer, nullable=False)
    major: Mapped[str] = mapped_column(String(100), nullable=False)
    
    def __repr__(self) -> str:
        return f"<Student(id={self.id}, name='{self.name}', age={self.age}, major='{self.major}')>"