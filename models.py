from sqlalchemy import Column, Integer, String, DateTime, Float
from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()

class User(Base):
    __tablename__ = 'users'
    
    id = Column(Integer, primary_key=True)
    email = Column(String, unique=True)
    subscription_tier = Column(String, default='free')
    pages_used_this_month = Column(Integer, default=0)
    subscription_start = Column(DateTime)
    subscription_end = Column(DateTime)
    stripe_customer_id = Column(String)

class Transaction(Base):
    __tablename__ = 'transactions'
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer)
    amount = Column(Float)
    date = Column(DateTime)
    status = Column(String) 