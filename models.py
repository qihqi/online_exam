from sqlalchemy import (Column, Integer, DateTime, String, ForeignKey, Text, Boolean)
from sqlalchemy.orm import relationship, backref
from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()


class User(Base):

    __tablename__ = 'users'
    uid = Column(Integer, primary_key=True, autoincrement=True)
    nickname = Column(String(20))
    email = Column(String(100))
    access_uuid = Column(String(32))
    preferred_lang = Column(String(20))
    submissions = relationship('Submission', backref=backref('user'))
    start_timestamp = Column(DateTime)


class Submission(Base):

    __tablename__ = 'submissions'
    uid = Column(Integer, primary_key=True, autoincrement=True)
    prob_id = Column(Integer)
    user_id = Column(Integer,  ForeignKey(User.uid))
    link = Column(Text)
    language = Column(Text)
    timestamp = Column(DateTime)
    scores = relationship('Score', backref=backref('submission'))


class Score(Base):

    __tablename__ = 'scores'
    uid = Column(Integer, primary_key=True, autoincrement=True)
    submission_id = Column(Integer,  ForeignKey(Submission.uid))
    grader = Column(String(50))
    timestamp = Column(DateTime)
    score = Column(Integer)
    comment = Column(Text)


class ExamPaper(Base):

    __tablename__ = 'exams'
    uid = Column(Integer, primary_key=True, autoincrement=True)
    test_name = Column(String(20))
    language = Column(String(20))
    link = Column(Text)
    is_active = Column(Boolean)
