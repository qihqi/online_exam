from sqlalchemy import (Column, Integer, DateTime, String, ForeignKey, Text)
from sqlalchemy.orm import relationship, backref
from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()


class User(Base):

    __tablename__ = 'users'
    uid = Column(Integer, primary_key=True, autoincrement=True)
    nickname = Column(String(20))
    email = Column(String(100))
    access_uuid = Column(String(20))
    preferred_lang = Column(String(20))
    submissions = relationship('Submission', backref=backref('user'))


class Submission(Base):

    __tablename__ = 'submissions'
    uid = Column(Integer, primary_key=True, autoincrement=True)
    prob_id = Column(Integer)
    user_id = Column(Integer,  ForeignKey(User.uid))
    link = Column(Text)

