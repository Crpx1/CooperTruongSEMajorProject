import streamlit as st
import os
import bcrypt
import random
import re
import smtplib
import ssl
from email.message import EmailMessage
import socket
import shutil
import uuid
import datetime
from PIL import Image
import pandas as pd
import html
import google.generativeai as genai
import textwrap
import matplotlib.pyplot as plt
import plotly.express as px
from sklearn.linear_model import LinearRegression
from prophet import Prophet
import numpy as np
from streamlit_autorefresh import st_autorefresh
import sqlalchemy
from sqlalchemy import (create_engine, Column, Integer, String, LargeBinary, ForeignKey,
                        Boolean, REAL, TEXT, UniqueConstraint, Index, func, and_, or_, case, literal_column)
from sqlalchemy.orm import declarative_base, sessionmaker, relationship, backref
from sqlalchemy.exc import IntegrityError as SQLAlchemyIntegrityError, SQLAlchemyError



DATABASE_FILE = "retail_pro_plus_v3.db"
INVENTORY_IMAGE_DIRECTORY = "inventory_images"

try:
    SENDER_EMAIL = st.secrets["email_credentials"]["sender_email"]
    SENDER_APP_PASSWORD = st.secrets["email_credentials"]["app_password"]
    SMTP_SERVER = st.secrets["email_credentials"]["smtp_server"]
    SMTP_PORT = st.secrets["email_credentials"]["smtp_port"]
except KeyError as e:
    st.error(f"Missing secret: {e}. Please check your .streamlit/secrets.toml file.")
    st.stop()


DATABASE_URL = f"sqlite:///{DATABASE_FILE}"
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False}, echo=False)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    email = Column(String, unique=True, nullable=False, index=True)
    password_hash = Column(LargeBinary, nullable=False)
    name = Column(String)

    workspaces_owned = relationship("Workspace", back_populates="owner")
    invitations_sent = relationship("WorkspaceMember", foreign_keys='WorkspaceMember.invited_by_user_id', back_populates="inviter")
    sales_recorded = relationship("Sale", back_populates="recorder")
    memberships = relationship("WorkspaceMember", foreign_keys='WorkspaceMember.user_id', back_populates="user", cascade="all, delete-orphan")
    chat_messages = relationship("WorkspaceMessage", back_populates="user", cascade="all, delete-orphan")



class Workspace(Base):
    __tablename__ = "workspaces"
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    name = Column(String, nullable=False)
    owner_user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    created_at = Column(String, nullable=False)

    owner = relationship("User", back_populates="workspaces_owned")
    members = relationship("WorkspaceMember", back_populates="workspace", cascade="all, delete-orphan")
    inventory_items = relationship("Inventory", back_populates="workspace", cascade="all, delete-orphan")
    sales = relationship("Sale", back_populates="workspace", cascade="all, delete-orphan")
    chat_messages = relationship("WorkspaceMessage", back_populates="workspace", cascade="all, delete-orphan")

class WorkspaceMessage(Base):
    __tablename__ = "workspace_messages"
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    workspace_id = Column(Integer, ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    content = Column(TEXT, nullable=False)
    timestamp = Column(String, nullable=False)

    user = relationship("User", back_populates="chat_messages")
    workspace = relationship("Workspace", back_populates="chat_messages")


class WorkspaceMember(Base):
    __tablename__ = "workspace_members"
    id = Column(Integer, primary_key=True, autoincrement=True)
    workspace_id = Column(Integer, ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), index=True)
    role = Column(String, nullable=False, default='member')
    invited_by_user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"))
    invite_email = Column(String, index=True)
    invite_token = Column(String, unique=True, index=True)
    status = Column(String, nullable=False, default='pending')
    joined_at = Column(String)

    workspace = relationship("Workspace", back_populates="members")
    user = relationship("User", foreign_keys=[user_id], back_populates="memberships")
    inviter = relationship("User", foreign_keys=[invited_by_user_id], back_populates="invitations_sent")

    __table_args__ = (
        Index('idx_workspace_user_accepted_unique', 'workspace_id', 'user_id',
              unique=True,
              sqlite_where=and_(user_id != None, status == 'accepted')),
        Index('idx_workspace_user_pending_unique', 'workspace_id', 'user_id',
              unique=True,
              sqlite_where=and_(user_id != None, status == 'pending', invite_token != None)),
        Index('idx_workspace_pending_email_unique', 'workspace_id', 'invite_email',
              unique=True,
              sqlite_where=and_(invite_email != None, status == 'pending', user_id == None)),
    )


class Inventory(Base):
    __tablename__ = "inventory"
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    workspace_id = Column(Integer, ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False)
    name = Column(String, nullable=False)
    retail_price = Column(REAL)
    stock_level = Column(Integer)
    image_path = Column(String)
    is_active = Column(Boolean, nullable=False, default=True)

    workspace = relationship("Workspace", back_populates="inventory_items")
    sale_items = relationship("SaleItem", back_populates="inventory_item")

    __table_args__ = (
        Index('idx_inventory_workspace_name_active', 'workspace_id', 'name',
              unique=True,
              sqlite_where=(is_active == True)),
    )


class Sale(Base):
    __tablename__ = "sales"
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    workspace_id = Column(Integer, ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False)
    recorded_by_user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    sale_datetime = Column(String, nullable=False)
    total_amount = Column(REAL, nullable=False)

    workspace = relationship("Workspace", back_populates="sales")
    recorder = relationship("User", back_populates="sales_recorded")
    items = relationship("SaleItem", back_populates="sale", cascade="all, delete-orphan")


class SaleItem(Base):
    __tablename__ = "sale_items"
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    sale_id = Column(Integer, ForeignKey("sales.id", ondelete="CASCADE"), nullable=False, index=True)
    inventory_item_id = Column(Integer, ForeignKey("inventory.id", ondelete="RESTRICT"), nullable=False, index=True)
    quantity_sold = Column(Integer, nullable=False)
    price_per_unit_at_sale = Column(REAL, nullable=False)
    discount_percentage = Column(REAL, nullable=False, default=0)
    subtotal = Column(REAL, nullable=False)

    sale = relationship("Sale", back_populates="items")
    inventory_item = relationship("Inventory", back_populates="sale_items")

def row_to_dict(row):
    """Converts a SQLAlchemy model instance into a dictionary."""
    if row is None:
        return None
    d = {}
    for column in row.__table__.columns:
        d[column.name] = getattr(row, column.name)
    return d

def create_database_connection():
    """Provides a SQLAlchemy session."""
    try:
        session = SessionLocal()
        return session
    except SQLAlchemyError as error:
        st.error(f"Database connection error: {error}")
        return None

def start_database():
    """Creates database tables from SQLAlchemy models if they don't exist."""
    try:
        Base.metadata.create_all(bind=engine)
    except SQLAlchemyError as error:
        st.error(f"Database error during initialization: {error}")

def post_workspace_message(workspace_id, user_id, content):
    """Saves a new chat message to the database."""
    session = create_database_connection()
    if session is None:
        st.error("Failed to post message: Cannot connect to the database.")
        return False
    try:
        new_message = WorkspaceMessage(
            workspace_id=workspace_id,
            user_id=user_id,
            content=content,
            timestamp=datetime.datetime.now().isoformat()
        )
        session.add(new_message)
        session.commit()
        return True
    except SQLAlchemyError as e:
        st.error(f"Failed to send message: {e}")
        session.rollback()
        return False
    finally:
        session.close()

def get_workspace_messages(workspace_id, limit=100):
    """Retrieves all messages for a workspace, including the sender's name."""
    session = create_database_connection()
    if session is None: return []
    try:
        messages = session.query(
            WorkspaceMessage.content,
            WorkspaceMessage.timestamp,
            User.name.label("user_name"),
            User.id.label("user_id")
        ).join(User, WorkspaceMessage.user_id == User.id)\
         .filter(WorkspaceMessage.workspace_id == workspace_id)\
         .order_by(WorkspaceMessage.timestamp.asc())\
         .limit(limit)\
         .all()
        return [dict(row._mapping) for row in messages]
    except SQLAlchemyError as e:
        st.error(f"Failed to retrieve messages: {e}")
        return []
    finally:
        session.close()


def get_sales_by_item(workspace_id, days_limit=30):
    """
    Retrieves sales performance for each item in a given period.
    Returns a list of dictionaries with item name, units sold, and total revenue.
    """
    session = create_database_connection()
    if not session: return []
    
    try:
        start_date = datetime.datetime.now() - datetime.timedelta(days=days_limit)
        start_date_iso = start_date.isoformat()

        sales_data = session.query(
            Inventory.name,
            func.sum(SaleItem.quantity_sold).label("total_quantity_sold"),
            func.sum(SaleItem.subtotal).label("total_revenue")
        ).select_from(SaleItem)\
         .join(Sale, Sale.id == SaleItem.sale_id)\
         .join(Inventory, Inventory.id == SaleItem.inventory_item_id)\
         .filter(Sale.workspace_id == workspace_id)\
         .filter(Sale.sale_datetime >= start_date_iso)\
         .group_by(Inventory.name)\
         .order_by(func.sum(SaleItem.quantity_sold).desc())\
         .all()

        return [dict(row._mapping) for row in sales_data]

    except SQLAlchemyError as e:
        st.error(f"Error fetching item sales data: {e}")
        return []
    finally:
        session.close()


def clear_workspace_chat(workspace_id):
    """Deletes all messages for a specific workspace."""
    session = create_database_connection()
    if not session:
        st.error("Failed to clear chat: Cannot connect to the database.")
        return False
    try:
        num_deleted = session.query(WorkspaceMessage).filter_by(workspace_id=workspace_id).delete(synchronize_session=False)
        session.commit()
        st.toast(f"Successfully deleted {num_deleted} chat messages.", icon="🗑️")
        return True
    except SQLAlchemyError as e:
        session.rollback()
        st.error(f"An error occurred while clearing the chat: {e}")
        return False
    finally:
        session.close()

def rename_workspace(workspace_id, new_name, user_id):
    """Renames a workspace after verifying the user is the owner."""
    session = create_database_connection()
    if not session:
        st.error("Failed to rename: Cannot connect to the database.")
        return False

    if not new_name or not new_name.strip():
        st.error("Workspace name cannot be empty.")
        return False

    try:
        workspace = session.query(Workspace).filter_by(id=workspace_id).first()

        if not workspace:
            st.error("Workspace not found.")
            return False

        if workspace.owner_user_id != user_id:
            st.error("You are not authorized to rename this workspace.")
            return False

        workspace.name = new_name.strip()
        session.commit()
        st.success("Workspace renamed successfully!")
        return True
    except SQLAlchemyError as e:
        session.rollback()
        st.error(f"An error occurred while renaming the workspace: {e}")
        return False
    finally:
        session.close()

def refresh_user_workspace_state(user_id):
    """
    Fetches the latest workspace data for the user and updates the session state.
    This handles both name changes and membership removals gracefully.
    """
    fresh_workspaces = get_user_workspaces_from_db(user_id)
    st.session_state.user_workspaces = fresh_workspaces
    
    current_ws_id = st.session_state.get('current_workspace_id')

    if not current_ws_id or not fresh_workspaces:
        if fresh_workspaces:
            st.session_state.current_workspace_id = fresh_workspaces[0]['id']
            st.session_state.current_workspace_name = fresh_workspaces[0]['name']
        else:
            st.session_state.current_workspace_id = None
            st.session_state.current_workspace_name = "N/A"
        return

    current_ws_info = next((ws for ws in fresh_workspaces if ws['id'] == current_ws_id), None)

    if current_ws_info:
        if st.session_state.current_workspace_name != current_ws_info['name']:
            st.session_state.current_workspace_name = current_ws_info['name']
            st.toast(f"Workspace has been renamed to '{current_ws_info['name']}'.", icon="✏️")
    else:
        old_workspace_name = st.session_state.get('current_workspace_name', f"ID {current_ws_id}")
        new_workspace_name = fresh_workspaces[0]['name']
        
        st.session_state['persistent_notification'] = {
            "message": f"You have been removed from '{old_workspace_name}'. You are now in '{new_workspace_name}'.",
            "icon": "ℹ️"
        }
        
        st.session_state.current_workspace_id = fresh_workspaces[0]['id']
        st.session_state.current_workspace_name = new_workspace_name
        
        st.session_state.current_page = "Dashboard"
        st.rerun()

def create_new_workspace(name, owner_user_id):
    session = create_database_connection()
    if session is None: return None
    workspace_id = None
    try:
        new_workspace = Workspace(
            name=name,
            owner_user_id=owner_user_id,
            created_at=datetime.datetime.now().isoformat()
        )
        session.add(new_workspace)
        session.commit()
        workspace_id = new_workspace.id

        if workspace_id:
            add_workspace_team_member(workspace_id, owner_user_id, owner_user_id, role='owner', status='accepted')
        return workspace_id
    except SQLAlchemyError as error:
        st.error(f"DB Error: Failed to create workspace: {error}")
        session.rollback()
    finally:
        session.close()
    return workspace_id


def add_workspace_team_member(workspace_id, user_id, invited_by_user_id, role='member', invite_email=None, invite_token=None, status='pending'):
    session = create_database_connection()
    if session is None: return False
    success = False
    try:
        joined_at = datetime.datetime.now().isoformat() if status == 'accepted' else None
        actual_invitee_user_id = user_id

        if invite_email and not actual_invitee_user_id:
            invited_user_obj = find_user_by_email_in_db(invite_email)
            if invited_user_obj:
                actual_invitee_user_id = invited_user_obj['id']
                existing_member = session.query(WorkspaceMember).filter(
                    WorkspaceMember.workspace_id == workspace_id,
                    WorkspaceMember.user_id == actual_invitee_user_id,
                    or_(
                        WorkspaceMember.status == 'accepted',
                        and_(WorkspaceMember.status == 'pending', WorkspaceMember.invite_token != None)
                    )
                ).first()
                if existing_member:
                    st.info(f"User {invite_email} is already an accepted member or has a pending invitation for this workspace.")
                    return False

        new_member_data = {
            'workspace_id': workspace_id,
            'role': role,
            'invited_by_user_id': invited_by_user_id,
            'status': status,
            'joined_at': joined_at,
            'invite_email': invite_email,
            'invite_token': invite_token,
            'user_id': actual_invitee_user_id
        }

        if actual_invitee_user_id:
            new_member = WorkspaceMember(**new_member_data)
        elif invite_email and invite_token:
            new_member_data.pop('user_id')
            new_member_data.pop('joined_at')
            new_member = WorkspaceMember(**new_member_data)
        else:
            st.error("Cannot add member: Insufficient information for add_workspace_team_member.")
            return False

        session.add(new_member)
        session.commit()
        success = True

    except SQLAlchemyIntegrityError as error:
        session.rollback()
        error_msg_lower = str(error.orig).lower()
        if "unique constraint failed: workspace_members.invite_token" in error_msg_lower:
            st.error("Failed to add member: This invitation token has already been used or generated.")
        elif "unique constraint failed" in error_msg_lower and ("idx_workspace_user_accepted_unique" in error_msg_lower or "idx_workspace_user_pending_unique" in error_msg_lower) :
            st.error(f"This user is already an active or pending member of the workspace.")
        elif "unique constraint failed" in error_msg_lower and "idx_workspace_pending_email_unique" in error_msg_lower:
            st.error(f"A pending invitation already exists for {invite_email} in this workspace.")
        elif "foreign key constraint failed" in error_msg_lower:
            st.error(f"Failed to add member: Invalid workspace or user reference. Details: {error.orig}")
        elif "not null constraint failed: workspace_members.user_id" in error_msg_lower:
             st.error(f"DB Integrity Error: User ID was null when it shouldn't be. Check logic. Error: {error.orig}")
        else:
            st.error(f"DB Integrity Error: Failed to add workspace member: {error.orig}")
    except SQLAlchemyError as error:
        session.rollback()
        st.error(f"DB Error: Failed to add workspace member: {error}")
    finally:
        session.close()
    return success


def remove_workspace_member(workspace_id_to_modify, member_user_id_to_remove, current_user_id_acting):
    session = create_database_connection()
    if session is None:
        st.error("Database connection failed.")
        return False
    try:
        actual_owner_id = get_workspace_owner_user_id(workspace_id_to_modify, db_conn_to_use=session)
        if actual_owner_id is None:
            st.error("Workspace not found or error fetching owner information.")
            return False

        if actual_owner_id != current_user_id_acting:
            st.error("You are not authorized to remove members from this workspace.")
            return False

        if member_user_id_to_remove == current_user_id_acting:
            st.warning("Owners cannot remove themselves from the workspace using this feature.")
            return False

        member_to_delete = session.query(WorkspaceMember).filter_by(
            workspace_id=workspace_id_to_modify,
            user_id=member_user_id_to_remove
        ).first()

        if member_to_delete:
            session.delete(member_to_delete)
            session.commit()
            return True
        else:
            st.warning(f"Could not remove member (User ID: {member_user_id_to_remove}). They might not be a member or were already removed.")
            return False
    except SQLAlchemyError as error:
        st.error(f"Database error while removing member: {error}")
        session.rollback()
        return False
    finally:
        session.close()


def cancel_pending_invite(workspace_id_to_modify, invite_token_to_cancel, current_user_id_acting):
    session = create_database_connection()
    if session is None:
        st.error("Database connection failed.")
        return False
    try:
        actual_owner_id = get_workspace_owner_user_id(workspace_id_to_modify, db_conn_to_use=session)
        if actual_owner_id is None:
            st.error("Workspace not found or error fetching owner information.")
            return False

        if actual_owner_id != current_user_id_acting:
            st.error("You are not authorized to cancel invitations for this workspace.")
            return False

        invite_to_delete = session.query(WorkspaceMember).filter_by(
            workspace_id=workspace_id_to_modify,
            invite_token=invite_token_to_cancel,
            user_id=None,
            status='pending'
        ).first()

        if invite_to_delete:
            session.delete(invite_to_delete)
            session.commit()
            return True
        else:
            st.warning(f"Could not cancel invitation. It might have already been accepted, cancelled, or the token is invalid.")
            return False
    except SQLAlchemyError as error:
        st.error(f"Database error while cancelling invitation: {error}")
        session.rollback()
        return False
    finally:
        session.close()

def get_user_workspaces_from_db(user_id):
    session = create_database_connection()
    if session is None: return []
    workspaces_list = []
    try:
        results = session.query(
            Workspace.id, Workspace.name, Workspace.owner_user_id, WorkspaceMember.role
        ).join(WorkspaceMember, Workspace.id == WorkspaceMember.workspace_id).filter(
            WorkspaceMember.user_id == user_id,
            WorkspaceMember.status == 'accepted'
        ).all()
        workspaces_list = [dict(row._mapping) for row in results]
    except SQLAlchemyError as error:
        st.error(f"DB Error: Failed to get user workspaces: {error}")
    finally:
        session.close()
    return workspaces_list

def find_workspace_in_db(workspace_id):
    session = create_database_connection()
    if session is None: return None
    workspace = None
    try:
        workspace_obj = session.query(Workspace).filter_by(id=workspace_id).first()
        if workspace_obj:
            workspace = row_to_dict(workspace_obj)
    except SQLAlchemyError as error:
        st.error(f"DB Error: Failed to find workspace by ID: {error}")
    finally:
        session.close()
    return workspace

def get_workspace_member_details(workspace_id):
    session = create_database_connection()
    if session is None: return []
    members = []
    try:
        accepted_members = session.query(
            User.id.label('user_id'), User.name, User.email,
            WorkspaceMember.role, WorkspaceMember.status, WorkspaceMember.joined_at
        ).join(User, WorkspaceMember.user_id == User.id).filter(
            WorkspaceMember.workspace_id == workspace_id,
            WorkspaceMember.status == 'accepted'
        ).all()
        members.extend([dict(row._mapping) for row in accepted_members])

        pending_registered = session.query(
            User.id.label('user_id'), User.name, User.email,
            WorkspaceMember.role, WorkspaceMember.status, WorkspaceMember.invite_token
        ).join(User, WorkspaceMember.user_id == User.id).filter(
            WorkspaceMember.workspace_id == workspace_id,
            WorkspaceMember.status == 'pending',
            WorkspaceMember.invite_token != None
        ).all()
        members.extend([dict(row._mapping) for row in pending_registered])

        pending_unregistered = session.query(
            literal_column("null").label('user_id'),
            literal_column("'(Invited User - Not Registered)'").label('name'),
            WorkspaceMember.invite_email.label('email'),
            WorkspaceMember.role,
            WorkspaceMember.status,
            WorkspaceMember.invite_token
        ).filter(
            WorkspaceMember.workspace_id == workspace_id,
            WorkspaceMember.status == 'pending',
            WorkspaceMember.user_id == None,
            WorkspaceMember.invite_email != None
        ).all()
        members.extend([dict(row._mapping) for row in pending_unregistered])

    except SQLAlchemyError as error:
        st.error(f"DB Error fetching workspace members: {error}")
    finally:
        session.close()
    return members


def process_workspace_invitation_token(invite_token, accepting_user_id):
    session = create_database_connection()
    if session is None: return None, "Database connection failed."
    try:
        invite_details = session.query(
            WorkspaceMember.id.label('invite_id'),
            WorkspaceMember.workspace_id,
            WorkspaceMember.invite_email,
            WorkspaceMember.user_id
        ).filter(
            WorkspaceMember.invite_token == invite_token,
            WorkspaceMember.status == 'pending'
        ).first()

        if not invite_details:
            return None, "Invalid or expired invitation token."

        invite_details_dict = dict(invite_details._mapping)
        workspace_id_joined = invite_details_dict['workspace_id']
        invited_original_user_id = invite_details_dict['user_id']
        invite_id_in_db = invite_details_dict['invite_id']

        accepting_user_obj = find_user_by_id_in_db(accepting_user_id, session)
        if not accepting_user_obj:
            return None, "Accepting user not found."

        can_accept = False
        if invited_original_user_id and invited_original_user_id == accepting_user_id:
            can_accept = True
        elif invite_details_dict['invite_email'] and invite_details_dict['invite_email'].lower() == accepting_user_obj['email'].lower():
            can_accept = True

        if not can_accept:
            return None, "This invitation was intended for a different user or email address."

        already_member = session.query(WorkspaceMember).filter_by(
            workspace_id=workspace_id_joined,
            user_id=accepting_user_id,
            status='accepted'
        ).first()

        invite_to_update = session.query(WorkspaceMember).filter_by(id=invite_id_in_db).first()

        if already_member:
            session.delete(invite_to_update)
            session.commit()
            return workspace_id_joined, "You are already a member of this workspace."

        if invited_original_user_id is None and invite_details_dict['invite_email']:
            invite_to_update.user_id = accepting_user_id
            invite_to_update.status = 'accepted'
            invite_to_update.joined_at = datetime.datetime.now().isoformat()
            invite_to_update.invite_token = None
            invite_to_update.invite_email = accepting_user_obj['email']
        else:
            invite_to_update.status = 'accepted'
            invite_to_update.joined_at = datetime.datetime.now().isoformat()
            invite_to_update.invite_token = None

        session.commit()

        other_pending_invites = session.query(WorkspaceMember).filter(
            WorkspaceMember.workspace_id == workspace_id_joined,
            WorkspaceMember.user_id == accepting_user_id,
            WorkspaceMember.status == 'pending',
            WorkspaceMember.id != invite_id_in_db
        ).all()
        for p_invite in other_pending_invites:
            session.delete(p_invite)
        session.commit()

        return workspace_id_joined, "Invitation accepted successfully! You now have access to the workspace."

    except SQLAlchemyError as error:
        if session: session.rollback()
        st.error(f"DB Error: Failed to process invitation: {error}")
        return None, f"Database error: {error}"
    finally:
        if session: session.close()
    return None, "An unexpected error occurred during invitation processing."


def is_user_a_member_of_workspace(user_id, workspace_id, db_conn_to_use=None):
    session = db_conn_to_use if db_conn_to_use else create_database_connection()
    is_member = False
    if session is None: return False
    try:
        member = session.query(WorkspaceMember).filter_by(
            user_id=user_id,
            workspace_id=workspace_id,
            status='accepted'
        ).first()
        if member:
            is_member = True
    except SQLAlchemyError as error:
        st.error(f"DB Error checking workspace membership: {error}")
    finally:
        if session and not db_conn_to_use:
            session.close()
    return is_member

def get_workspace_owner_user_id(workspace_id, db_conn_to_use=None):
    session = db_conn_to_use if db_conn_to_use else create_database_connection()
    owner_id = None
    if session is None: return None
    try:
        workspace = session.query(Workspace.owner_user_id).filter_by(id=workspace_id).first()
        if workspace:
            owner_id = workspace.owner_user_id
    except SQLAlchemyError as error:
        st.error(f"DB Error getting workspace owner: {error}")
    finally:
        if session and not db_conn_to_use:
            session.close()
    return owner_id

def find_user_by_email_in_db(email):
    session = create_database_connection()
    user = None
    if session is None: return None
    try:
        user_obj = session.query(User).filter(func.lower(User.email) == email.lower()).first()
        if user_obj:
            user = row_to_dict(user_obj)
    except SQLAlchemyError as error:
        st.error(f"DB error finding user: {error}")
    finally:
        session.close()
    return user

def find_user_by_id_in_db(user_id, db_conn_to_use=None):
    session = db_conn_to_use if db_conn_to_use else create_database_connection()
    user = None
    if session is None: return None
    try:
        user_obj = session.query(User).filter_by(id=user_id).first()
        if user_obj:
            user = row_to_dict(user_obj)
    except SQLAlchemyError as error:
        st.error(f"DB error finding user by ID: {error}")
    finally:
        if session and not db_conn_to_use:
            session.close()
    return user

def register_new_user(email, password, name):
    session = create_database_connection()
    success = False; user_id = None
    if session is None: return False, None
    try:
        hashed_pw = hash_user_password(password)
        if not hashed_pw: raise ValueError("Password hashing failed.")

        new_user = User(email=email.lower(), password_hash=hashed_pw, name=name)
        session.add(new_user)
        session.commit()
        user_id = new_user.id

        if user_id:
            workspace_name = f"{name.split(' ')[0]}'s Workspace" if name else f"{email.split('@')[0]}'s Workspace"
            default_workspace_id = create_new_workspace(workspace_name, user_id)
            if default_workspace_id:
                success = True
            else:
                st.error("User account created, but failed to create their default workspace. Please contact support.")
                success = True 
        else:
            st.error("Failed to get user ID after registration.")
    except SQLAlchemyIntegrityError:
        session.rollback()
        st.error(f"Email '{email}' already registered.")
    except (SQLAlchemyError, ValueError) as error:
        session.rollback()
        st.error(f"Failed to register user: {error}")
    finally:
        session.close()
    return success, user_id

def update_user_password_in_db(email, new_password):
    session = create_database_connection()
    success = False
    if session is None: return False
    try:
        hashed_pw = hash_user_password(new_password)
        if not hashed_pw: raise ValueError("Password hashing failed.")

        user_to_update = session.query(User).filter(func.lower(User.email) == email.lower()).first()
        if user_to_update:
            user_to_update.password_hash = hashed_pw
            session.commit()
            success = True
        else:
            st.warning("Could not find user to update password.")
    except (SQLAlchemyError, ValueError) as error:
        session.rollback()
        st.error(f"DB Error: Failed to update password: {error}")
    finally:
        session.close()
    return success

def check_if_user_exists(user_id, db_conn):
    user = db_conn.query(User).filter_by(id=user_id).first()
    return user is not None

def add_product(workspace_id, name, retail_price, stock_level, image_path=None, added_by_user_id=None):
    session = create_database_connection()
    success = False
    if session is None: return False
    try:
        if not name: raise ValueError("Item name cannot be empty.")
        price = float(retail_price); stock = int(stock_level)
        if price < 0: raise ValueError("Price cannot be negative.")
        if stock < 0: raise ValueError("Stock level cannot be negative.")

        if added_by_user_id and not is_user_a_member_of_workspace(added_by_user_id, workspace_id, session):
            st.error(f"User (ID: {added_by_user_id}) is not authorized to add items to this workspace (ID: {workspace_id}).")
            return False

        new_product = Inventory(
            workspace_id=workspace_id,
            name=name,
            retail_price=price,
            stock_level=stock,
            image_path=image_path,
            is_active=True
        )
        session.add(new_product)
        session.commit()
        success = True
    except SQLAlchemyIntegrityError as error:
        session.rollback()
        error_str = str(error.orig).lower()
        if "unique constraint failed" in error_str and "idx_inventory_workspace_name_active" in error_str:
            st.error(f"An active item named '{name}' already exists in this workspace.")
        elif "foreign key constraint failed" in error_str and "workspaces" in error_str:
            st.error(f"Failed to add item: The specified workspace (ID: {workspace_id}) does not exist or there's a reference issue. Please ensure you are in a valid workspace.")
        else:
            st.error(f"Failed to add item due to a database constraint: {error.orig}")
    except (SQLAlchemyError, ValueError) as error:
        session.rollback()
        st.error(f"Failed to add item: {error}")
    finally:
        session.close()
    return success

def get_products(workspace_id, search_term="", price_filter="Any", stock_filter="Any", include_inactive=False):
    session = create_database_connection()
    items_list = []
    if session is None: return []
    try:
        query = session.query(Inventory).filter(Inventory.workspace_id == workspace_id)
        if not include_inactive:
            query = query.filter(Inventory.is_active == True)
        if search_term:
            query = query.filter(Inventory.name.ilike(f"%{search_term}%"))

        if price_filter == "< $30":
            query = query.filter(Inventory.retail_price < 30.0)
        elif price_filter == "$30-$100":
            query = query.filter(Inventory.retail_price.between(30.0, 100.0))
        elif price_filter == "> $100":
            query = query.filter(Inventory.retail_price > 100.0)

        if stock_filter == "Low Stock":
            low_thresh = 5
            query = query.filter(Inventory.stock_level > 0, Inventory.stock_level <= low_thresh)
        elif stock_filter == "Out of Stock":
            query = query.filter(Inventory.stock_level <= 0)
        elif stock_filter == "In Stock":
            query = query.filter(Inventory.stock_level > 0)

        results = query.order_by(Inventory.name.asc()).all()
        items_list = [row_to_dict(row) for row in results]
    except SQLAlchemyError as error:
        st.error(f"DB error getting inventory: {error}")
    finally:
        session.close()
    return items_list

def get_product_by_id(item_id, workspace_id, include_inactive=False):
    session = create_database_connection()
    item_dict = None
    if session is None: return None
    try:
        query = session.query(Inventory).filter_by(id=item_id, workspace_id=workspace_id)
        if not include_inactive:
            query = query.filter(Inventory.is_active == True)
        item_obj = query.first()
        if item_obj:
            item_dict = row_to_dict(item_obj)
    except SQLAlchemyError as error:
        st.error(f"DB error getting item by ID: {error}")
    finally:
        session.close()
    return item_dict

def update_product(item_id, workspace_id, name, retail_price, stock_level, image_path=None, is_active=True, updated_by_user_id=None):
    session = create_database_connection()
    success = False
    if session is None: return False
    try:
        if not name: raise ValueError("Item name cannot be empty.")
        price = float(retail_price); stock = int(stock_level)
        if price < 0: raise ValueError("Price cannot be negative.")
        if stock < 0: raise ValueError("Stock level cannot be negative.")

        if updated_by_user_id and not is_user_a_member_of_workspace(updated_by_user_id, workspace_id, session):
            st.error(f"User (ID: {updated_by_user_id}) is not authorized to update items in this workspace (ID: {workspace_id}).")
            return False

        item_to_update = session.query(Inventory).filter_by(id=item_id, workspace_id=workspace_id).first()
        if item_to_update:
            item_to_update.name = name
            item_to_update.retail_price = price
            item_to_update.stock_level = stock
            item_to_update.is_active = is_active
            if image_path is not None:
                item_to_update.image_path = image_path
            session.commit()
            success = True
        else:
            st.warning(f"Item ID {item_id} not found for update in this workspace or no changes were made.")
    except SQLAlchemyIntegrityError as error:
        session.rollback()
        if "UNIQUE constraint failed" in str(error.orig) and "idx_inventory_workspace_name_active" in str(error.orig):
             st.error(f"Another active item named '{name}' already exists in this workspace.")
        else:
             st.error(f"Failed to update item due to a database constraint: {error.orig}")
    except (SQLAlchemyError, ValueError) as error:
        session.rollback()
        st.error(f"Failed to update item: {error}")
    finally:
        session.close()
    return success

def deactivate_product(item_id, workspace_id, deleted_by_user_id=None):
    session = create_database_connection()
    success = False
    if session is None: return False
    try:
        if deleted_by_user_id and not is_user_a_member_of_workspace(deleted_by_user_id, workspace_id, session):
            st.error(f"User (ID: {deleted_by_user_id}) is not authorized to delete items in this workspace (ID: {workspace_id}).")
            return False

        item_to_deactivate = session.query(Inventory).filter_by(id=item_id, workspace_id=workspace_id).first()
        if item_to_deactivate:
            item_to_deactivate.is_active = False
            session.commit()
            success = True
        else:
            st.warning(f"Item ID {item_id} not found in this workspace to deactivate.")
    except SQLAlchemyError as error:
        session.rollback()
        st.error(f"DB Error: Failed to deactivate item: {error}")
    finally:
        session.close()
    return success

def record_new_sale(workspace_id, recorded_by_user_id, cart_items, total_sale_amount):
    session = create_database_connection()
    if session is None: return False
    try:
        if not is_user_a_member_of_workspace(recorded_by_user_id, workspace_id, session):
            st.error(f"User (ID: {recorded_by_user_id}) is not authorized to record sales in this workspace (ID: {workspace_id}).")
            return False

        for item_in_cart in cart_items:
            stock_info = session.query(Inventory.stock_level, Inventory.name, Inventory.is_active).filter_by(
                id=item_in_cart['id'], workspace_id=workspace_id
            ).first()
            if stock_info is None:
                raise ValueError(f"Product '{item_in_cart['name']}' (ID: {item_in_cart['id']}) not found in this workspace.")
            if not stock_info.is_active:
                raise ValueError(f"Product '{item_in_cart['name']}' is currently inactive and cannot be sold.")
            if stock_info.stock_level < item_in_cart['quantity']:
                raise ValueError(f"Not enough stock for '{item_in_cart['name']}'. Available: {stock_info.stock_level}, Requested: {item_in_cart['quantity']}.")

        new_sale = Sale(
            workspace_id=workspace_id,
            recorded_by_user_id=recorded_by_user_id,
            sale_datetime=datetime.datetime.now().isoformat(),
            total_amount=total_sale_amount
        )
        session.add(new_sale)
        session.flush() 

        
        for item_in_cart in cart_items:
            new_sale_item = SaleItem(
                sale_id=new_sale.id,
                inventory_item_id=item_in_cart['id'],
                quantity_sold=item_in_cart['quantity'],
                price_per_unit_at_sale=item_in_cart['price_unit'],
                discount_percentage=item_in_cart.get('discount', 0.0),
                subtotal=item_in_cart['subtotal']
            )
            session.add(new_sale_item)

            
            item_to_update = session.query(Inventory).filter_by(id=item_in_cart['id'], workspace_id=workspace_id).first()
            item_to_update.stock_level -= item_in_cart['quantity']

        session.commit()
        return True
    except ValueError as ve:
        if session: session.rollback()
        st.error(f"Sale Error: {str(ve)}")
        return False
    except SQLAlchemyError as error:
        if session: session.rollback()
        st.error(f"Database Error: Failed to record sale: {error}")
        return False
    finally:
        if session: session.close()


def get_sales_summary_data(workspace_id):
    session = create_database_connection()
    if session is None: return {'today': 0.0, 'this_week': 0.0, 'this_year': 0.0}
    sales_today, sales_this_week, sales_this_year = 0.0, 0.0, 0.0
    today_date = datetime.date.today()
    current_year = today_date.year
    current_iso_week = today_date.isocalendar()
    try:
        all_sales = session.query(Sale.sale_datetime, Sale.total_amount).filter_by(workspace_id=workspace_id).all()
        for sale_row in all_sales:
            try:
                sale_dt_obj = datetime.datetime.fromisoformat(sale_row.sale_datetime)
                sale_date_obj = sale_dt_obj.date()

                if sale_date_obj == today_date:
                    sales_today += sale_row.total_amount

                sale_iso_week = sale_date_obj.isocalendar()
                if sale_iso_week[0] == current_iso_week[0] and sale_iso_week[1] == current_iso_week[1]:
                    sales_this_week += sale_row.total_amount

                if sale_date_obj.year == current_year:
                    sales_this_year += sale_row.total_amount
            except ValueError:
                continue
    except SQLAlchemyError as error:
        st.error(f"Database error fetching sales summary for workspace {workspace_id}: {error}")
    finally:
        session.close()
    return {'today': sales_today, 'this_week': sales_this_week, 'this_year': sales_this_year}


def get_total_units_sold(workspace_id):
    session = create_database_connection()
    if session is None: return 0
    total_quantity = 0
    try:
        result = session.query(func.sum(SaleItem.quantity_sold)).join(Sale).filter(Sale.workspace_id == workspace_id).scalar()
        if result is not None:
            total_quantity = result
    except SQLAlchemyError as error:
        st.error(f"DB error getting total quantity sold: {error}")
    finally:
        session.close()
    return total_quantity

def get_chart_sales_data(workspace_id, period):
    session = create_database_connection()
    if session is None: return None
    try:
        all_sales_records = session.query(Sale.sale_datetime, Sale.total_amount).filter_by(workspace_id=workspace_id).all()
        today_date = datetime.date.today()
        
        if period == "Day":
            hourly_sales_agg = {h: 0.0 for h in range(24)}
            if all_sales_records:
                for record in all_sales_records:
                    try:
                        sale_dt_obj = datetime.datetime.fromisoformat(record.sale_datetime)
                        if sale_dt_obj.date() == today_date:
                            hourly_sales_agg[sale_dt_obj.hour] += record.total_amount
                    except ValueError: continue
            sales_values = [hourly_sales_agg.get(h, 0.0) for h in range(24)]
            data_frame = pd.DataFrame({'Sales': sales_values}, index=pd.Index(range(24), name="Hour of Day (0-23)"))
            return data_frame
        elif period == "Week":
            days_of_week_labels = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
            weekly_sales_agg = {day_label: 0.0 for day_label in days_of_week_labels}
            start_of_current_week = today_date - datetime.timedelta(days=today_date.weekday())
            end_of_current_week = start_of_current_week + datetime.timedelta(days=6)
            if all_sales_records:
                for record in all_sales_records:
                    try:
                        sale_dt_obj = datetime.datetime.fromisoformat(record.sale_datetime)
                        sale_date = sale_dt_obj.date()
                        if start_of_current_week <= sale_date <= end_of_current_week:
                            day_label = days_of_week_labels[sale_date.weekday()]
                            weekly_sales_agg[day_label] += record.total_amount
                    except ValueError: continue
            sales_values_ordered = [weekly_sales_agg.get(day, 0.0) for day in days_of_week_labels]
            ordered_week_index = pd.CategoricalIndex(days_of_week_labels, categories=days_of_week_labels, ordered=True, name="Day of Week")
            data_frame = pd.DataFrame({'Sales': sales_values_ordered}, index=ordered_week_index)
            return data_frame
        elif period == "Year":
            months_of_year_labels = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
            monthly_sales_agg = {month_label: 0.0 for month_label in months_of_year_labels}
            current_year = today_date.year
            if all_sales_records:
                for record in all_sales_records:
                    try:
                        sale_dt_obj = datetime.datetime.fromisoformat(record.sale_datetime)
                        if sale_dt_obj.year == current_year:
                            month_label = months_of_year_labels[sale_dt_obj.month - 1]
                            monthly_sales_agg[month_label] += record.total_amount
                    except ValueError: continue
            sales_values_ordered = [monthly_sales_agg.get(month, 0.0) for month in months_of_year_labels]
            ordered_month_index = pd.CategoricalIndex(months_of_year_labels, categories=months_of_year_labels, ordered=True, name="Month")
            data_frame = pd.DataFrame({'Sales': sales_values_ordered}, index=ordered_month_index)
            return data_frame
    except SQLAlchemyError as error:
        st.error(f"Database error while generating report data for workspace {workspace_id}: {error}")
    except Exception as ex:
        st.error(f"An unexpected error occurred while generating report data: {ex}")
    finally:
        if session: session.close()
    return None

def get_best_sellers(workspace_id, limit=5):
    session = create_database_connection()
    if session is None: return []
    items_list = []
    try:
        results = session.query(
            Inventory.name,
            func.sum(SaleItem.quantity_sold).label('total_quantity_sold'),
            Inventory.image_path,
            Inventory.retail_price,
            Inventory.is_active
        ).join(SaleItem, Inventory.id == SaleItem.inventory_item_id)\
         .join(Sale, SaleItem.sale_id == Sale.id)\
         .filter(Sale.workspace_id == workspace_id, Inventory.workspace_id == workspace_id)\
         .group_by(Inventory.id, Inventory.name, Inventory.image_path, Inventory.retail_price, Inventory.is_active)\
         .order_by(func.sum(SaleItem.quantity_sold).desc())\
         .limit(limit)\
         .all()

        items_list = [dict(row._mapping) for row in results]
    except SQLAlchemyError as error:
        st.error(f"DB error getting best selling items: {error}")
    finally:
        session.close()
    return items_list

def get_product_sales_history(item_id, workspace_id):
    
    try:
        query = sqlalchemy.select(
            Sale.sale_datetime,
            SaleItem.quantity_sold
        ).join(SaleItem, Sale.id == SaleItem.sale_id).where(
            SaleItem.inventory_item_id == item_id,
            Sale.workspace_id == workspace_id
        ).order_by(Sale.sale_datetime.asc())

        with engine.connect() as conn:
            data_frame = pd.read_sql_query(query, conn)

        if 'sale_datetime' in data_frame.columns:
            data_frame['sale_datetime'] = pd.to_datetime(data_frame['sale_datetime'])
        return data_frame
    except SQLAlchemyError as error:
        st.error(f"Prediction failed: Error fetching sales history: {error}")
        return pd.DataFrame()
    except Exception as error:
        st.error(f"Prediction failed: An unexpected error occurred while fetching sales history: {error}")
        return pd.DataFrame()



def prepare_forecasting_data(df_sales_history):
    if df_sales_history.empty or 'quantity_sold' not in df_sales_history.columns:
        return None
    df_daily = df_sales_history.groupby(df_sales_history['sale_datetime'].dt.date)['quantity_sold'].sum().reset_index()
    df_daily.rename(columns={'sale_datetime': 'ds', 'quantity_sold': 'y'}, inplace=True)
    df_daily['ds'] = pd.to_datetime(df_daily['ds'])
    if not df_daily.empty:
        first_sale_date = df_daily['ds'].min()
        today_date = pd.to_datetime(datetime.date.today())
        if first_sale_date <= today_date:
            all_dates_range = pd.date_range(start=first_sale_date, end=today_date, freq='D')
            all_dates_df = pd.DataFrame({'ds': all_dates_range})
            df_daily = pd.merge(all_dates_df, df_daily, on='ds', how='left')
            df_daily['y'].fillna(0, inplace=True)
    return df_daily

def train_sales_forecasting_model(prepared_df):
    if prepared_df is None or len(prepared_df) < 2:
        st.warning("Cannot generate a prediction. At least two days of history are needed.")
        return None
    model = Prophet(daily_seasonality=True)
    try:
        model.fit(prepared_df)
        return model
    except Exception as error:
        st.error(f"Model training failed: {error}")
        return None

def generate_sales_forecast(model):
    if model is None:
        return {"next_day": "N/A", "next_week": "N/A", "next_30_days": "N/A"}
    try:
        future = model.make_future_dataframe(periods=365)
        forecast = model.predict(future)
        last_history_date = model.history_dates.max()
        pred_next_day = max(0, forecast[forecast['ds'] == last_history_date + pd.Timedelta(days=1)]['yhat'].iloc[0])
        preds_week_df = forecast[(forecast['ds'] > last_history_date) & (forecast['ds'] <= last_history_date + pd.Timedelta(days=7))]
        pred_next_week_total = sum(max(0, p) for p in preds_week_df['yhat'])
        preds_30_days_df = forecast[(forecast['ds'] > last_history_date) & (forecast['ds'] <= last_history_date + pd.Timedelta(days=30))]
        pred_next_30_days_total = sum(max(0, p) for p in preds_30_days_df['yhat'])
        return {
            'next_day': round(pred_next_day),
            'next_week': round(pred_next_week_total),
            'next_30_days': round(pred_next_30_days_total)
        }
    except Exception as error:
        st.error(f"Error during prediction generation: {error}")
        return {"next_day": "Error", "next_week": "Error", "next_30_days": "Error"}

def hash_user_password(password):
    if not password: return None
    try: return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())
    except Exception: return None

def check_user_password(plain_password, hashed_password_bytes):
    if not plain_password or not hashed_password_bytes: return False
    try: return bcrypt.checkpw(plain_password.encode('utf-8'), hashed_password_bytes)
    except Exception: return False

def password_meet_req(password):
    errors = []
    if len(password) < 8: errors.append("min 8 characters")
    if not any(char.isupper() for char in password): errors.append("1 uppercase letter")
    if not any(char.isdigit() for char in password): errors.append("1 number")
    if not errors: return True, ""
    return False, "Password must contain: " + ", ".join(errors) + "."

def send_application_email(recipient_email, subject, body):
    if SENDER_APP_PASSWORD == "aaaaaaaaaaaaaaaa" or not SENDER_APP_PASSWORD:
        st.error("CRITICAL: SENDER_APP_PASSWORD is not set correctly. Update it in the script or environment.")
        return False
    msg = EmailMessage()
    msg['Subject'] = subject
    msg['From'] = SENDER_EMAIL
    msg['To'] = recipient_email
    msg.set_content(body)
    context = ssl.create_default_context()
    try:
        with smtplib.SMTP_SSL(SMTP_SERVER, SMTP_PORT, context=context) as server:
            server.login(SENDER_EMAIL, SENDER_APP_PASSWORD)
            server.send_message(msg)
            return True
    except smtplib.SMTPAuthenticationError as error_auth:
        st.error("Email Auth failed. Check SENDER_EMAIL or SENDER_APP_PASSWORD.")
    except (smtplib.SMTPException, socket.gaierror, OSError) as error_smtp:
        st.error(f"Failed to send email due to SMTP/Network issue: {error_smtp}")
    except Exception as error:
        st.error(f"An unexpected error occurred during email sending: {error}")
    return False

def email_workspace_invite(recipient_email, inviter_name, workspace_name, invite_link):
    subject = f"You're invited to join {workspace_name} on Retail Pro+"
    body = f"""Hi,

{inviter_name} has invited you to collaborate on the workspace '{workspace_name}' in Retail Pro+.

To accept this invitation, please click the link below:
{invite_link}

If you don't have a Retail Pro+ account, you'll be prompted to create one.

Thanks,
The Retail Pro+ Team
"""
    return send_application_email(recipient_email, subject, body)

def send_password_reset_link(recipient_email, reset_code):
    subject = "Your Password Reset Code for Retail Pro+"
    body = f"Hi,\n\nYour password reset code is: {reset_code}\n\nPlease use this to reset your password.\n\nThanks,\nThe Retail Pro+ Team"
    return send_application_email(recipient_email, subject, body)

def send_two_factor_auth_code(recipient_email, auth_code):
    subject = "Your Retail Pro+ Login Verification Code"
    body = f"Hi,\n\nYour login verification code is: {auth_code}\n\nThanks,\nThe Retail Pro+ Team"
    return send_application_email(recipient_email, subject, body)

def is_email_valid(email):
    if not email: return False
    return re.match(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$", email) is not None

def secure_html_escape(text):
    if not isinstance(text, str):
        text = str(text)
    return html.escape(text)

def save_uploaded_inventory_image(uploaded_file_obj, workspace_id_for_pathing):
    if uploaded_file_obj is not None:
        try:
            current_save_dir = INVENTORY_IMAGE_DIRECTORY
            if not os.path.exists(current_save_dir):
                os.makedirs(current_save_dir)
            file_extension = os.path.splitext(uploaded_file_obj.name)[1]
            unique_filename = f"{uuid.uuid4()}{file_extension}"
            destination_path = os.path.join(current_save_dir, unique_filename)
            with open(destination_path, "wb") as f:
                f.write(uploaded_file_obj.getbuffer())
            return destination_path
        except Exception as error:
            st.error(f"Error saving uploaded image: {error}")
    return None

def generate_ai_performance_report(workspace_data):
    try:
        api_key = st.secrets.get("GOOGLE_API_KEY")
        if not api_key:
            st.error("Google AI API Key not found. Please add it to your Streamlit secrets.")
            return None
        genai.configure(api_key=api_key)
        generation_config = {
            "temperature": 0.7,
            "top_p": 1,
            "top_k": 1,
            "max_output_tokens": 2048,
        }
        model = genai.GenerativeModel(model_name="gemini-1.5-flash-latest",
                                      generation_config=generation_config)
        prompt = f"""
        Act as a friendly and insightful business analyst for a small retail business.
        I will provide you with a summary of the business's performance data from our system.
        Please generate a clear, concise, and encouraging performance report in Markdown format.

        **Business Performance Data:**
        - Workspace Name: {workspace_data.get('workspace_name', 'N/A')}
        - Sales Today: ${workspace_data.get('sales_today', 0):.2f}
        - Sales This Week: ${workspace_data.get('sales_this_week', 0):.2f}
        - Sales This Year: ${workspace_data.get('sales_this_year', 0):.2f}
        - Total Inventory Items: {workspace_data.get('total_items', 0)}
        - Total Units in Stock: {workspace_data.get('total_stock_units', 0)}
        - Number of Items with Low Stock: {workspace_data.get('low_stock_items', 0)}
        - Number of Items Out of Stock: {workspace_data.get('out_of_stock_items', 0)}
        - Best Selling Items (by quantity): {workspace_data.get('best_sellers_list', 'None')}

        **Your Task:**
        Based on the data above, please write a report with the following sections:

        1.  **Executive Summary:** A brief, one-paragraph overview of the business's current performance.
        2.  **Key Highlights (The Good News):** Use a bulleted list to point out 2-3 positive aspects (e.g., strong weekly sales, popular items). Be encouraging.
        3.  **Areas for Attention (Opportunities):** Use a bulleted list to gently point out 2-3 areas that could be improved (e.g., items out of stock, slow sales today). Frame these as opportunities, not failures.
        4.  **Actionable Suggestions:** Provide a short, bulleted list of 2-3 simple, concrete next steps the business owner could take. For example, 'Consider reordering your best-selling items to avoid stockouts.' or 'Run a small weekend promotion to boost daily sales.'

        Keep the tone professional but easy to understand for someone who is not a data expert.
        """
        response = model.generate_content(prompt)
        return response.text
    except Exception as error:
        return f"An error occurred while generating the AI report: {str(error)}. Please check your API key and configuration."

def show_login_page():
    MAX_LOGIN_ATTEMPTS = 5
    LOCKOUT_DURATION_MINUTES = 5
    
    if 'login_attempts' not in st.session_state:
        st.session_state.login_attempts = {}
        
    st.subheader("Welcome Back")
    st.caption("Please enter your details!")
    
    email_for_check = st.session_state.get('login_email', '').lower()
    if email_for_check:
        user_attempts = st.session_state.login_attempts.get(email_for_check, {})
        locked_until = user_attempts.get('locked_until')
        if locked_until and datetime.datetime.now() < locked_until:
            time_left = locked_until - datetime.datetime.now()
            st.error(f"Too many failed login attempts for this email. Please try again in {time_left.seconds // 60} minutes and {time_left.seconds % 60} seconds.")
            return

    with st.form("login_form"):
        email = st.text_input("Email Address", key="login_email")
        password = st.text_input("Password", type="password", key="login_password")
        login_btn = st.form_submit_button("Sign In", use_container_width=True)

    if st.button("Forgot Password?", key="login_forgot_pwd_link"):
        st.session_state.auth_flow_page = "forgot_password_email"
        st.rerun()
        
    if login_btn:
        if not email or not password:
            st.warning("Email and Password are required.")
        elif not is_email_valid(email):
            st.warning("Please enter a valid email address.")
        else:
            email_lower = email.lower()
            user = find_user_by_email_in_db(email_lower)
            if user and check_user_password(password, user['password_hash']):
                if email_lower in st.session_state.login_attempts:
                    del st.session_state.login_attempts[email_lower]
                auth_code = str(random.randint(100000, 999999))
                if send_two_factor_auth_code(user['email'], auth_code):
                    st.session_state.auth_user_email = user['email']
                    st.session_state.auth_user_data = dict(user)
                    st.session_state.auth_expected_code = auth_code
                    st.session_state.auth_flow_page = "enter_2fa"
                    st.toast(f"Verification code sent to {user['email']}.", icon="✅")
                    st.rerun()
                else:
                    st.error("Failed to send verification code. Please try again.")
            else:
                user_attempts = st.session_state.login_attempts.get(email_lower, {'count': 0, 'locked_until': None})
                user_attempts['count'] += 1
                attempts_left = MAX_LOGIN_ATTEMPTS - user_attempts['count']
                
                if attempts_left > 0:
                    st.error(f"Invalid email or password. You have {attempts_left} attempts remaining before a temporary lockout.")
                else:
                    lockout_time = datetime.datetime.now() + datetime.timedelta(minutes=LOCKOUT_DURATION_MINUTES)
                    user_attempts['locked_until'] = lockout_time
                    st.error(f"Invalid email or password. Too many failed attempts. Your account is locked for {LOCKOUT_DURATION_MINUTES} minutes.")
                
                st.session_state.login_attempts[email_lower] = user_attempts
                

    if st.button("Don't have an account? Sign Up", key="login_signup_link"):
        st.session_state.auth_flow_page = "signup"
        st.rerun()

def show_two_factor_auth_page():
    st.subheader("Enter Verification Code")
    st.caption(f"A 6-digit code was sent to {st.session_state.get('auth_user_email', 'your email')}.")
    with st.form("2fa_form"):
        code = st.text_input("Authentication Code", max_chars=6, key="2fa_code_input")
        verify_btn = st.form_submit_button("Verify & Login")
    if verify_btn:
        if code == st.session_state.get('auth_expected_code'):
            st.session_state.logged_in_user = st.session_state.auth_user_data
            user_id = st.session_state.logged_in_user['id']
            user_workspaces = get_user_workspaces_from_db(user_id)
            st.session_state.user_workspaces = user_workspaces
            if user_workspaces:
                owned_workspaces = [ws for ws in user_workspaces if ws['owner_user_id'] == user_id]
                if owned_workspaces:
                    st.session_state.current_workspace_id = owned_workspaces[0]['id']
                    st.session_state.current_workspace_name = owned_workspaces[0]['name']
                else:
                    st.session_state.current_workspace_id = user_workspaces[0]['id']
                    st.session_state.current_workspace_name = user_workspaces[0]['name']
            else:
                st.error("No accessible workspaces found for your account. Please contact support.")
                for key in ['auth_user_email', 'auth_user_data', 'auth_expected_code', 'auth_flow_page', 'logged_in_user', 'user_workspaces']:
                    if key in st.session_state: del st.session_state[key]
                st.rerun()
                return
            st.session_state.current_page = "Dashboard"
            for key in ['auth_user_email', 'auth_user_data', 'auth_expected_code', 'auth_flow_page']:
                if key in st.session_state: del st.session_state[key]
            st.success("Login successful!"); st.balloons(); st.rerun()
        else: st.error("Invalid authentication code.")
    if st.button("Back to Login", key="2fa_back_to_login"):
        st.session_state.auth_flow_page = "login"; st.rerun()

def show_signup_page():
    st.subheader("Create Account")
    with st.form("signup_form"):
        name = st.text_input("Full Name", key="signup_name")
        email = st.text_input("Email Address", key="signup_email")
        password = st.text_input("Password (min 8 chars, 1 upper, 1 num)", type="password", key="signup_pwd1")
        confirm_password = st.text_input("Confirm Password", type="password", key="signup_pwd2")
        signup_btn = st.form_submit_button("Sign Up")
    if signup_btn:
        if not all([name, email, password, confirm_password]): st.warning("All fields are required.")
        elif not is_email_valid(email): st.warning("Invalid email format.")
        elif password != confirm_password: st.error("Passwords do not match.")
        else:
            is_valid_pwd, pwd_error_msg = password_meet_req(password)
            if not is_valid_pwd: st.error(pwd_error_msg)
            else:
                user_created_successfully, new_user_id = register_new_user(email, password, name)
                if user_created_successfully:
                    st.success("Account and default workspace created! You can now log in.")
                    st.session_state.auth_flow_page = "login"
                    if new_user_id:
                        
                        session = create_database_connection()
                        if session:
                            try:
                                session.query(WorkspaceMember).filter(
                                    WorkspaceMember.invite_email == email.lower(),
                                    WorkspaceMember.user_id == None,
                                    WorkspaceMember.status == 'pending'
                                ).update({'user_id': new_user_id, 'status': 'pending'}, synchronize_session=False) 
                                session.commit()
                                st.info("We found pending workspace invitations for your email. You can accept them after logging in or via the invitation email.")
                            except SQLAlchemyError:
                                session.rollback()
                                pass 
                            finally:
                                session.close()
                    st.rerun()
    if st.button("Already have an account? Sign In", key="signup_to_login_link"):
        st.session_state.auth_flow_page = "login"; st.rerun()

def show_forgot_password_email_page():
    st.subheader("Forgot Your Password?")
    st.caption("Enter your email to receive a password reset code.")
    with st.form("forgot_password_email_form"):
        email = st.text_input("Email Address", key="fp_email_input")
        send_code_btn = st.form_submit_button("Send Reset Code")
    if send_code_btn:
        if not is_email_valid(email): st.warning("Please enter a valid email.")
        else:
            user = find_user_by_email_in_db(email)
            if user:
                reset_code = str(random.randint(100000, 999999))
                if send_password_reset_link(email, reset_code):
                    st.session_state.reset_email = email
                    st.session_state.reset_expected_code = reset_code
                    st.session_state.auth_flow_page = "forgot_password_code"
                    st.toast(f"Reset code sent to {email}.", icon="✅"); st.rerun()
                else: st.error("Failed to send reset code. Try again.")
            else: st.error("Email address not found.")
    if st.button("Back to Login", key="fp_email_back_to_login"):
        st.session_state.auth_flow_page = "login"; st.rerun()

def show_forgot_password_code_page():
    st.subheader("Enter Reset Code")
    st.caption(f"A 6-digit code was sent to {st.session_state.get('reset_email')}.")
    with st.form("forgot_password_code_form"):
        code = st.text_input("Verification Code", max_chars=6, key="fp_code_input")
        verify_code_btn = st.form_submit_button("Verify Code")
    if verify_code_btn:
        if code == st.session_state.get('reset_expected_code'):
            st.session_state.auth_flow_page = "forgot_password_new_pwd"; st.rerun()
        else: st.error("Invalid verification code.")
    if st.button("Back to Login", key="fp_code_back_to_login"):
        st.session_state.auth_flow_page = "login"; st.rerun()

def show_forgot_password_new_pwd_page():
    st.subheader("Set New Password")
    with st.form("new_password_form"):
        new_password = st.text_input("New Password", type="password", key="fp_new_pwd1")
        confirm_new_password = st.text_input("Confirm New Password", type="password", key="fp_new_pwd2")
        reset_pwd_btn = st.form_submit_button("Reset Password")
    if reset_pwd_btn:
        email_to_reset = st.session_state.get('reset_email')
        if not email_to_reset:
            st.error("Session error. Please start reset again."); st.session_state.auth_flow_page = "login"; st.rerun(); return
        if not new_password or not confirm_new_password: st.warning("Both password fields are required.")
        elif new_password != confirm_new_password: st.error("Passwords do not match.")
        else:
            is_valid, pwd_error_msg = password_meet_req(new_password)
            if not is_valid: st.error(pwd_error_msg)
            else:
                if update_user_password_in_db(email_to_reset, new_password):
                    st.success("Password updated! You can now log in.")
                    for key in ['reset_email', 'reset_expected_code']:
                        if key in st.session_state: del st.session_state[key]
                    st.session_state.auth_flow_page = "login"; st.rerun()
    if st.button("Back to Login", key="fp_new_pwd_back_to_login"):
        st.session_state.auth_flow_page = "login"; st.rerun()

def show_dashboard_page():
    if st.session_state.get("show_removal_dialog"):
        dialog_title = st.session_state.get("removal_dialog_title", "Notification")
        dialog_message = st.session_state.get("removal_dialog_message", "Your workspace access has been updated.")
        @st.dialog(title=dialog_title)
        def removal_status_dialog():
            st.write(dialog_message)
            if st.button("OK", key="dialog_ok_button"):
                st.session_state.show_removal_dialog = False
                st.rerun()
        removal_status_dialog()
    if not st.session_state.get("logged_in_user"):
        st.error("Error: User not logged in. Redirecting to login.")
        st.session_state.current_page = "Login"
        st.session_state.auth_flow_page = "login"
        st.rerun()
        return
    user_id = st.session_state.logged_in_user['id']
    user_name_raw = st.session_state.logged_in_user.get('name', 'User').split(" ")[0]
    safe_user_name = secure_html_escape(user_name_raw)
    workspace_id = st.session_state.get('current_workspace_id')
    workspace_name = st.session_state.get('current_workspace_name', "N/A")
    st.header(f"👋 Welcome back, {safe_user_name}!")
    if not workspace_id:
        st.info("Please select or create a workspace from the sidebar to view its dashboard.")
        return
    st.subheader(f"📍 Current Workspace: {workspace_name}")
    st.markdown("---")
    with st.container(border=True):
        st.subheader("📊 Sales Activity")
        sales_summary = get_sales_summary_data(workspace_id)
        columns_sales = st.columns(3)
        columns_sales[0].metric(label="Sales Today", value=f"${sales_summary['today']:.2f}")
        columns_sales[1].metric(label="Sales this Week", value=f"${sales_summary['this_week']:.2f}")
        columns_sales[2].metric(label="Sales this Year", value=f"${sales_summary['this_year']:.2f}")
    st.markdown("---")
    row1_col1, row1_col2 = st.columns(2)
    with row1_col1:
        with st.container(border=True, height=350):
            st.subheader("📦 Stock Overview")
            inventory_items = get_products(workspace_id)
            total_stock_units, total_stock_value, low_stock_items, out_of_stock_items = 0, 0.0, 0, 0
            if inventory_items:
                for item in inventory_items:
                    stock = item.get('stock_level', 0)
                    price = item.get('retail_price', 0.0)
                    total_stock_units += stock
                    total_stock_value += stock * price
                    if stock == 0: out_of_stock_items += 1
                    elif 0 < stock <= 5: low_stock_items +=1
            stock_cols = st.columns(2)
            stock_cols[0].metric(label="Total Units in Stock", value=total_stock_units)
            stock_cols[1].metric(label="Total Stock Value", value=f"${total_stock_value:.2f}")
            stock_cols[0].metric(label="Low Stock Items (<5)", value=low_stock_items, delta=f"{low_stock_items} items", delta_color="inverse" if low_stock_items > 0 else "off")
            stock_cols[1].metric(label="Out of Stock Items", value=out_of_stock_items, delta=f"{out_of_stock_items} items", delta_color="inverse" if out_of_stock_items > 0 else "off")
    with row1_col2:
        with st.container(border=True, height=350):
            st.subheader("🌟 Top 5 Best Sellers")
            best_sellers = get_best_sellers(workspace_id, limit=5)
            if best_sellers:
                for i, item in enumerate(best_sellers):
                    st.markdown(f"**{i+1}. {item.get('name', 'N/A')}** - Sold: *{item.get('total_quantity_sold', 0)}*")
                    if i < len(best_sellers) - 1:
                        st.markdown("""<hr style="margin: 0.5rem 0;" />""", unsafe_allow_html=True)
            else:
                st.info("No sales data yet for this workspace.")
    st.markdown("---")
    st.subheader("📈 Analytics at a Glance")
    analytics_col1, analytics_col2 = st.columns(2)
    with analytics_col1:
        st.markdown("##### Top Products by Quantity Sold")
        total_items_sold = get_total_units_sold(workspace_id)
        best_sellers = get_best_sellers(workspace_id, limit=5)
        if best_sellers and total_items_sold > 0:
            top_5_qty = sum(item['total_quantity_sold'] for item in best_sellers)
            other_qty = total_items_sold - top_5_qty
            labels = [item['name'] for item in best_sellers]
            values = [item['total_quantity_sold'] for item in best_sellers]
            if other_qty > 0:
                labels.append('Other Products')
                values.append(other_qty)
            df_products = pd.DataFrame({'Product': labels, 'Units Sold': values})
            figure = px.pie(df_products,
                          names='Product',
                          values='Units Sold',
                          hole=0.4,
                          color_discrete_sequence=px.colors.sequential.RdBu)
            figure.update_traces(textposition='inside', textinfo='percent', pull=[0.05] * len(df_products))
            figure.update_layout(showlegend=True,
                                   margin=dict(t=0, b=0, l=0, r=0),
                                   legend_title_text='Products')
            st.plotly_chart(figure, use_container_width=True)
        else:
            st.info("No sales data to generate a product chart.")
    with analytics_col2:
        st.markdown("##### Inventory Status")
        inventory_items = get_products(workspace_id)
        if inventory_items:
            total_items = len(inventory_items)
            low_stock_items = len([item for item in inventory_items if 0 < item.get('stock_level', 0) <= 5])
            out_of_stock_items = len([item for item in inventory_items if item.get('stock_level', 0) <= 0])
            healthy_stock_count = total_items - low_stock_items - out_of_stock_items
            status_labels = ['Healthy Stock', 'Low Stock', 'Out of Stock']
            status_values = [healthy_stock_count, low_stock_items, out_of_stock_items]
            data = {label: value for label, value in zip(status_labels, status_values) if value > 0}
            if data:
                df_status = pd.DataFrame(list(data.items()), columns=['Status', 'Item Count'])
                color_map = {
                    'Healthy Stock': '#2ca02c',
                    'Low Stock': '#ff7f0e',
                    'Out of Stock': '#d62728'
                }
                figure = px.pie(df_status,
                              names='Status',
                              values='Item Count',
                              hole=0.4,
                              color='Status',
                              color_discrete_map=color_map)
                figure.update_traces(textposition='inside', textinfo='percent', pull=[0.05] * len(df_status))
                figure.update_layout(showlegend=True,
                                       margin=dict(t=0, b=0, l=0, r=0),
                                       legend_title_text='Status')
                st.plotly_chart(figure, use_container_width=True)
            else:
                st.info("No inventory to generate a status chart.")
        else:
            st.info("No inventory to generate a status chart.")

def show_inventory_page():
    user_id = st.session_state.logged_in_user['id']
    workspace_id = st.session_state.current_workspace_id
    workspace_name = st.session_state.current_workspace_name
    st.header(f"Inventory Management: {secure_html_escape(workspace_name)}")
    def set_active_item(action_type, item_id):
        st.session_state.active_action = action_type
        st.session_state.active_item_id = item_id
    def clear_active_item():
        st.session_state.active_action = None
        st.session_state.active_item_id = None
    if 'active_action' not in st.session_state:
        st.session_state.active_action = None
    if 'active_item_id' not in st.session_state:
        st.session_state.active_item_id = None
    columns_filter = st.columns([2, 1, 1])
    with columns_filter[0]:
        search_term = st.text_input("Search by Product Name", key="inventory_search_st")
    with columns_filter[1]:
        price_filter = st.selectbox("Filter by Price", ["Any", "< $30", "$30-$100", "> $100"], key="inventory_price_filter_st")
    with columns_filter[2]:
        stock_filter = st.selectbox("Filter by Stock", ["Any", "In Stock", "Low Stock", "Out of Stock"], key="inventory_stock_filter_st")
    if st.button("➕ Add New Item", key="toggle_add_item_form_st", on_click=clear_active_item):
        st.session_state.show_add_item_form = not st.session_state.get("show_add_item_form", False)
    if st.session_state.get("show_add_item_form"):
        with st.expander("Add New Item Form", expanded=True):
            with st.form("add_item_form_st", clear_on_submit=True):
                name = st.text_input("Item Name*")
                retail_price = st.number_input("Retail Price ($)*", min_value=0.01, format="%.2f", step=0.01)
                stock_level = st.number_input("Stock Level*", min_value=0, step=1)
                uploaded_image = st.file_uploader("Item Image", type=["png", "jpg", "jpeg", "gif"], key="add_item_uploader")
                submitted_add = st.form_submit_button("Add Item")
                if submitted_add:
                    if not name or retail_price is None or stock_level is None:
                        st.warning("Name, Price, and Stock are required.")
                    else:
                        img_path = save_uploaded_inventory_image(uploaded_image, workspace_id) if uploaded_image else None
                        if add_product(workspace_id, name, retail_price, stock_level, img_path, added_by_user_id=user_id):
                            st.success(f"'{secure_html_escape(name)}' added to {secure_html_escape(workspace_name)}!")
                            st.session_state.show_add_item_form = False
                            st.rerun()
    st.markdown("---")
    inventory_data = get_products(workspace_id, search_term, price_filter, stock_filter)
    if inventory_data:
        for item in inventory_data:
            safe_item_name = secure_html_escape(item['name'])
            stock = item.get('stock_level', 0)
            safe_stock_level = secure_html_escape(stock)
            col1, col2, col3 = st.columns([1.5, 4, 3])
            with col1:
                if item.get('image_path') and os.path.exists(item['image_path']):
                    st.image(item['image_path'], use_container_width=True)
                else:
                    st.image(os.path.join("images", "greybackground.jpg"), use_container_width=True)
            with col2:
                st.markdown(f"##### {safe_item_name}")
                st.caption(f"ID: {item['id']}")
                st.markdown(f"**Price:** ${item.get('retail_price', 0.0):.2f}")
                if stock <= 0:
                    st.markdown(f"<span style='color: #d62728;'>⚫ Out of Stock</span>", unsafe_allow_html=True)
                elif stock <= 10:
                    st.markdown(f"<span style='color: #ff7f0e;'>🟠 Low Stock:</span> {safe_stock_level} units available", unsafe_allow_html=True)
                else:
                    st.markdown(f"<span style='color: #2ca02c;'>🟢 In Stock:</span> {safe_stock_level} units available", unsafe_allow_html=True)
            with col3:
                action_cols = st.columns(2)
                action_cols[0].button("✏️ Edit / Restock", key=f"edit_{item['id']}", use_container_width=True, on_click=set_active_item, args=('edit', item['id']))
                if action_cols[1].button("🗑️ Deactivate", key=f"delete_{item['id']}", use_container_width=True):
                    if deactivate_product(item['id'], workspace_id, deleted_by_user_id=user_id):
                        st.rerun()
                action_cols2 = st.columns(2)
                action_cols2[0].button("📈 Predict Sales", key=f"predict_{item['id']}", use_container_width=True, on_click=set_active_item, args=('predict', item['id']))
                if item.get('image_path') and os.path.exists(item['image_path']):
                    action_cols2[1].button("🖼️ View Image", key=f"view_{item['id']}", use_container_width=True, on_click=set_active_item, args=('view_image', item['id']))
                else:
                    action_cols2[1].button("🖼️ View Image", key=f"view_{item['id']}", use_container_width=True, disabled=True)
            if st.session_state.active_item_id == item['id']:
                if st.session_state.active_action == 'edit':
                    with st.expander(f"✏️ Editing: {safe_item_name}", expanded=True):
                        with st.form(key=f"edit_form_{item['id']}"):
                            edit_name = st.text_input("Name*", value=item['name'])
                            edit_price = st.number_input("Price ($)*", value=float(item['retail_price']), min_value=0.01, format="%.2f")
                            edit_stock = st.number_input("Stock*", value=int(item['stock_level']), min_value=0)
                            edit_img_upload = st.file_uploader("Change Image", type=["png", "jpg", "jpeg"])
                            c1, c2 = st.columns(2)
                            if c1.form_submit_button("Save Changes", use_container_width=True, type="primary"):
                                new_img_path = item.get('image_path')
                                if edit_img_upload:
                                    new_img_path = save_uploaded_inventory_image(edit_img_upload, workspace_id)
                                if update_product(item['id'], workspace_id, edit_name, edit_price, edit_stock, new_img_path):
                                    st.toast(f"'{secure_html_escape(edit_name)}' updated!", icon="✅")
                                    clear_active_item()
                                    st.rerun()
                            if c2.form_submit_button("Cancel", use_container_width=True):
                                clear_active_item()
                                st.rerun()
                elif st.session_state.active_action == 'predict':
                    with st.expander(f"📈 Sales Predictions for {safe_item_name}", expanded=True):
                        with st.spinner("Analyzing historical data..."):
                            sales_history_df = get_product_sales_history(item['id'], workspace_id)
                            prepared_df = prepare_forecasting_data(sales_history_df)
                            model = train_sales_forecasting_model(prepared_df)
                            if model:
                                predictions = generate_sales_forecast(model)
                                pred_cols = st.columns(3)
                                pred_cols[0].metric("Next Day", f"{predictions.get('next_day', 'N/A')} units")
                                pred_cols[1].metric("Next Week", f"{predictions.get('next_week', 'N/A')} units")
                                pred_cols[2].metric("Next 30 Days", f"{predictions.get('next_30_days', 'N/A')} units")
                        st.button("Close", key=f"close_predict_{item['id']}", on_click=clear_active_item)
                elif st.session_state.active_action == 'view_image':
                    with st.expander(f"🖼️ Image for {safe_item_name}", expanded=True):
                        st.image(item['image_path'], use_container_width=True)
                        st.button("Close", key=f"close_view_{item['id']}", on_click=clear_active_item)
            st.divider()
    else:
        st.info(f"No inventory items found in '{secure_html_escape(workspace_name)}' that match your filters.")

def show_sales_page():
    user_id = st.session_state.logged_in_user['id']
    workspace_id = st.session_state.current_workspace_id
    workspace_name = st.session_state.current_workspace_name
    st.header(f"Process New Sale for: {workspace_name}")
    col_left, col_right = st.columns([2, 3])
    with col_left:
        st.subheader("Add Product to Order")
        inventory_items = get_products(workspace_id, stock_filter="In Stock")
        product_options = {
            f"{item['name']} (Stock: {item['stock_level']}, Price: ${item['retail_price']:.2f})": item
            for item in inventory_items
        }
        if not product_options:
            st.warning(f"No products in stock in '{workspace_name}'.")
            return
        selected_product_key = st.selectbox("Find Product", options=list(product_options.keys()), key="sales_prod_select", index=None, placeholder="Choose a product...")
        selected_product_data = product_options.get(selected_product_key)
        if selected_product_data:
            with st.form(key="add_to_cart_form", clear_on_submit=True):
                st.markdown(f"**Selected:** {selected_product_data['name']}")
                st.markdown(f"**Available Stock:** {selected_product_data['stock_level']}")
                st.markdown(f"**Price/Unit:** ${selected_product_data['retail_price']:.2f}")
                max_qty = selected_product_data['stock_level']
                quantity_to_add = st.number_input("Quantity:", min_value=1, value=1, step=1, key="sales_qty_add", max_value=max_qty)
                discount_percent = st.number_input(
                    "Discount (%)",
                    min_value=0.0,
                    max_value=100.0,
                    value=0.0,
                    step=5.0,
                    key="sales_discount_input"
                )
                add_to_order_btn = st.form_submit_button("Add to Order", type="primary", use_container_width=True)
                if add_to_order_btn:
                    original_price = selected_product_data['retail_price']
                    original_subtotal = quantity_to_add * original_price
                    discount_amount = (discount_percent / 100) * original_subtotal
                    final_subtotal = original_subtotal - discount_amount
                    st.session_state.cart.append({
                        'line_item_id': str(uuid.uuid4()),
                        'id': selected_product_data['id'],
                        'name': selected_product_data['name'],
                        'quantity': quantity_to_add,
                        'price_unit': original_price,
                        'discount': discount_percent,
                        'subtotal': final_subtotal
                    })
                    st.rerun()
    with col_right:
        st.subheader("Current Order")
        if not st.session_state.cart:
            st.info("Order is empty.")
        else:
            total_order_price = 0
            header_cols = st.columns([4, 1, 2, 2, 1])
            header_cols[0].markdown("**Product**")
            header_cols[1].markdown("**Qty**")
            header_cols[2].markdown("**Discount**")
            header_cols[3].markdown("**Subtotal**")
            header_cols[4].markdown("**Action**")
            st.markdown("---")
            for item in st.session_state.cart[:]:
                row_cols = st.columns([4, 1, 2, 2, 1])
                row_cols[0].write(f"{item['name']} (@ ${item['price_unit']:.2f})")
                row_cols[1].write(item['quantity'])
                row_cols[2].write(f"{item['discount']:.1f}%")
                row_cols[3].write(f"${item['subtotal']:.2f}")
                if row_cols[4].button("✖️", key=f"remove_item_{item['line_item_id']}", help="Remove this item"):
                    st.session_state.cart.remove(item)
                    st.rerun()
                total_order_price += item['subtotal']
            st.markdown("---")
            st.markdown(f"### Total Price: `${total_order_price:.2f}`")
            col_actions1, col_actions2 = st.columns(2)
            with col_actions1:
                if st.button("Clear Order", key="sales_clear_btn", use_container_width=True):
                    st.session_state.cart = []
                    st.toast("Order cleared.")
                    st.rerun()
            with col_actions2:
                if st.button("Finalise Sale", key="sales_final_btn", type="primary", use_container_width=True, disabled=not st.session_state.cart):
                    if record_new_sale(workspace_id, user_id, st.session_state.cart, total_order_price):
                        st.success("Sale Finalised!")
                        st.balloons()
                        st.session_state.cart = []
                        st.rerun()

def show_reports_page():
    workspace_id = st.session_state.current_workspace_id
    workspace_name = st.session_state.current_workspace_name
    st.header(f"Sales Reports for: {workspace_name}")
    time_period = st.selectbox("Select Time Period:", ("Day", "Week", "Year"), key="report_time_period_selector", index=0)
    report_data_df = get_chart_sales_data(workspace_id, time_period)
    if report_data_df is not None:
        if 'Sales' in report_data_df.columns and (report_data_df['Sales'] == 0).all():
            st.info(f"No sales recorded for '{workspace_name}' for the selected '{time_period}' period.")
        elif report_data_df.empty:
            st.info(f"No data available for '{workspace_name}' for the selected '{time_period}' period.")
        else:
            st.subheader(f"Sales Over The Current {time_period}")
            chart_type = st.radio("Select chart type:", ("Line Chart", "Bar Chart"), key=f"chart_type_display_{time_period}", horizontal=True)
            if chart_type == "Line Chart": st.line_chart(report_data_df)
            else: st.bar_chart(report_data_df)
            with st.expander("View Data Table"): st.dataframe(report_data_df)
    else:
        st.warning(f"Could not display report for '{time_period}' in '{workspace_name}'.")

def show_workspace_management_page():
    user_id = st.session_state.logged_in_user['id']
    workspace_id = st.session_state.current_workspace_id
    workspace_name = st.session_state.current_workspace_name
    current_user_name = st.session_state.logged_in_user.get('name', "User")
    
    st.header(f"Manage Workspace: {workspace_name}")
    
    workspace_details = find_workspace_in_db(workspace_id)
    if not workspace_details:
        st.error("Could not load workspace details. It might have been deleted or an error occurred.")
        return
    
    is_owner = (workspace_details['owner_user_id'] == user_id)

    if is_owner:
        st.subheader("Rename Workspace")
        with st.form("rename_workspace_form"):
            new_workspace_name = st.text_input("New workspace name", value=workspace_name)
            submitted_rename = st.form_submit_button("Rename")
            
            if submitted_rename:
                if new_workspace_name != workspace_name:
                    if rename_workspace(workspace_id, new_workspace_name, user_id):
                        
                        st.session_state.current_workspace_name = new_workspace_name.strip()
                        for ws in st.session_state.user_workspaces:
                            if ws['id'] == workspace_id:
                                ws['name'] = new_workspace_name.strip()
                                break
                        st.rerun()
                else:
                    st.toast("The new name is the same as the current name.")
        st.markdown("---")
   

    if is_owner:
        st.subheader("Invite New Member")
        with st.form("invite_member_form", clear_on_submit=True):
            invitee_email = st.text_input("Email address of user to invite")
            submit_invite = st.form_submit_button("Send Invitation")
            if submit_invite:
                if not is_email_valid(invitee_email):
                    st.warning("Please enter a valid email address.")
                elif invitee_email.lower() == st.session_state.logged_in_user['email'].lower():
                    st.warning("You cannot invite yourself.")
                else:
                    members_for_check = get_workspace_member_details(workspace_id)
                    existing_member = next((m for m in members_for_check if m['email'] and m['email'].lower() == invitee_email.lower()), None)
                    if existing_member:
                        st.warning(f"{invitee_email} is already a member or has a pending invitation ({existing_member['status']}).")
                    else:
                        invite_token = str(uuid.uuid4())
                        app_base_url = st.secrets.get("APP_BASE_URL", "http://localhost:8501")
                        invite_link = f"{app_base_url}?page=accept_invite&token={invite_token}"
                        if add_workspace_team_member(workspace_id, user_id=None, invited_by_user_id=user_id,
                                                   invite_email=invitee_email.lower(), invite_token=invite_token, status='pending'):
                            if email_workspace_invite(invitee_email, current_user_name, workspace_name, invite_link):
                                st.success(f"Invitation sent to {invitee_email}!")
                                st.rerun()
                            else:
                                st.error(f"Invitation record created, but failed to send email to {invitee_email}.")
    
    st.markdown("---")
    st.subheader("Workspace Members & Invitations")
    members = get_workspace_member_details(workspace_id)
    if members:
        header_cols = st.columns([2, 3, 1, 1.5, 1.5])
        header_cols[0].markdown("**Name**")
        header_cols[1].markdown("**Email**")
        header_cols[2].markdown("**Role**")
        header_cols[3].markdown("**Status**")
        if is_owner:
            header_cols[4].markdown("**Action**")
        st.markdown("---")
        for member in members:
            member_user_id = member.get('user_id')
            member_name = member.get('name', member.get('invite_email', 'N/A'))
            member_email = member['email']
            member_role = member['role'].capitalize() if member.get('role') else 'N/A'
            member_status_raw = member['status']
            status_icon = "✅ Accepted" if member_status_raw == 'accepted' else \
                          ("⏳ Pending" if member_status_raw == 'pending' else "❓ Unknown")
            row_cols = st.columns([2, 3, 1, 1.5, 1.5])
            row_cols[0].write(member_name)
            row_cols[1].write(member_email)
            row_cols[2].write(member_role)
            row_cols[3].write(status_icon)
            action_placeholder = row_cols[4]
            if is_owner:
                if member_user_id is not None and member_user_id != user_id:
                    if action_placeholder.button("Remove Member",
                                                 key=f"remove_member_{member_user_id}_{workspace_id}",
                                                 type="secondary",
                                                 use_container_width=True):
                        if remove_workspace_member(workspace_id, member_user_id, user_id):
                            st.success(f"Member '{member_name}' removed successfully.")
                            st.rerun()
                elif member_user_id is None and member_status_raw == 'pending' and member.get('invite_token'):
                    invite_token = member.get('invite_token')
                    if action_placeholder.button("Cancel Invite",
                                                 key=f"cancel_invite_{invite_token}_{workspace_id}",
                                                 type="secondary",
                                                 use_container_width=True):
                        if cancel_pending_invite(workspace_id, invite_token, user_id):
                            st.success(f"Invitation for '{member_email}' cancelled successfully.")
                            st.rerun()
            st.markdown("---")
    else:
        st.info("No members or pending invitations for this workspace yet.")

def show_accept_invite_page():
    st.subheader("Accept Workspace Invitation")

    if st.session_state.get("invite_processed_successfully"):
        st.success("Invitation accepted successfully! You now have access to the workspace.")
        
        newly_joined_workspace_name = st.session_state.get('current_workspace_name', 'your new workspace')
        st.info(f"You will be taken to the dashboard of '{newly_joined_workspace_name}'.")

        if st.button("Go to Dashboard"):
            del st.session_state.invite_processed_successfully
            st.session_state.current_page = "Dashboard"
            st.rerun()
        return 

    
    token = st.query_params.get("token")

    if not st.session_state.logged_in_user:
        st.warning("You need to be logged in to accept an invitation.")
        st.session_state.pending_invite_token_after_login = token
        st.session_state.auth_flow_page = "login"
        st.info("Please log in or sign up. After logging in, the invitation will be processed if it's for your account.")
        if st.button("Go to Login"):
            st.rerun()
        return

    if token:
        user_id = st.session_state.logged_in_user['id']
        st.write("Processing your invitation...") 
        
        workspace_id_joined, message = process_workspace_invitation_token(token, user_id)

        if workspace_id_joined is not None:
            
            st.session_state.invite_processed_successfully = True
            st.query_params.clear() 
            st.rerun()
        else:
            
            st.error(message)
            st.query_params.clear()
    else:
        st.error("No invitation token provided.")

    if st.button("Back to My Dashboard"):
        st.session_state.current_page = "Dashboard"
        if "token" in st.query_params or "page" in st.query_params:
            st.query_params.clear()
        st.rerun()

def show_workspace_chat_page():
    
    st_autorefresh(interval=3000, key="chat_refresher")

    workspace_id = st.session_state.current_workspace_id
    user_id = st.session_state.logged_in_user['id']

    
    owner_id = get_workspace_owner_user_id(workspace_id)
    is_owner = (user_id == owner_id)

    
    col1, col2 = st.columns([3, 1])
    with col1:
        st.header(f"💬 Workspace Chat: {st.session_state.current_workspace_name}")
        st.info("Communicate with your team members in real-time.")
    
    if is_owner:
        with col2:
            st.write("")
            st.write("") 
            if st.button("🗑️ Clear Chat History", use_container_width=True, type="secondary"):
                st.session_state.confirm_chat_clear = True
    
    
    if st.session_state.get("confirm_chat_clear"):
        st.warning("**Are you sure you want to permanently delete all messages in this chat?** This cannot be undone.")
        confirm_col1, confirm_col2 = st.columns(2)
        with confirm_col1:
            if st.button("✅ Yes, delete everything", use_container_width=True, type="primary"):
                if clear_workspace_chat(workspace_id):
                    del st.session_state.confirm_chat_clear
                    st.rerun()
        with confirm_col2:
            if st.button("❌ Cancel", use_container_width=True):
                del st.session_state.confirm_chat_clear
                st.rerun()

    st.markdown("---")

   
    chat_container = st.container(height=500, border=False)
    with chat_container:
        
        if not st.session_state.get("confirm_chat_clear"):
            messages = get_workspace_messages(workspace_id)
            for msg in messages:
                with st.chat_message(name=msg['user_name']):
                    st.markdown(f"**{msg['user_name']}**")
                    st.markdown(msg['content'])
                    ts = datetime.datetime.fromisoformat(msg['timestamp']).strftime('%Y-%m-%d %H:%M')
                    st.caption(f"Sent at {ts}")

    
    if not st.session_state.get("confirm_chat_clear"):
        if prompt := st.chat_input("Say something..."):
            if post_workspace_message(workspace_id, user_id, prompt):
                st.rerun()
            else:
                st.error("Message could not be sent.")
        
def show_performance_report_page():
    st.header("🤖 AI Business Assistant")
    if not st.secrets.get("GOOGLE_API_KEY"):
        st.warning("The AI features require a Google AI API key. Please configure it in your secrets.toml file.")
        st.markdown("""
            **To enable this feature:**
            1.  Create a free API key at [Google AI Studio](https://aistudio.google.com/).
            2.  Create a file named `secrets.toml` in a `.streamlit` folder in your project directory.
            3.  Add `GOOGLE_API_KEY = "YOUR_API_KEY"` to the file.
            4.  Restart your Streamlit app.
        """)
        return
        
    workspace_id = st.session_state.current_workspace_id
    workspace_name = st.session_state.current_workspace_name
    report_tab, chat_tab = st.tabs(["📊 Generate Performance Report", "💬 Chat with AI Analyst"])

    with report_tab:
        st.info("Click the button to get a one-time, AI-generated summary of your business performance.", icon="💡")
        if 'generated_report' not in st.session_state:
            st.session_state.generated_report = ""
        if st.button("Generate My Performance Report", type="primary"):
            with st.spinner("Analyzing your data and consulting the AI analyst... Please wait."):
                sales_summary = get_sales_summary_data(workspace_id)
                inventory_items = get_products(workspace_id)
                best_sellers = get_best_sellers(workspace_id, limit=5)
                total_stock_units, low_stock_items, out_of_stock_items = 0, 0, 0
                if inventory_items:
                    for item in inventory_items:
                        stock = item.get('stock_level', 0)
                        total_stock_units += stock
                        if stock == 0: out_of_stock_items += 1
                        elif 0 < stock <= 5: low_stock_items += 1
                best_sellers_formatted = ", ".join([f"{item['name']} ({item['total_quantity_sold']} sold)" for item in best_sellers]) if best_sellers else "No sales data yet"
                workspace_data = {
                    "workspace_name": workspace_name, "sales_today": sales_summary.get('today', 0),
                    "sales_this_week": sales_summary.get('this_week', 0), "sales_this_year": sales_summary.get('this_year', 0),
                    "total_items": len(inventory_items), "total_stock_units": total_stock_units,
                    "low_stock_items": low_stock_items, "out_of_stock_items": out_of_stock_items,
                    "best_sellers_list": best_sellers_formatted
                }
                report_text = generate_ai_performance_report(workspace_data)
                st.session_state.generated_report = report_text
        if st.session_state.generated_report:
            st.markdown("---")
            st.subheader("Your AI-Generated Business Report")
            st.write(st.session_state.generated_report)
            if st.button("Generate New Report"):
                st.session_state.generated_report = ""
                st.rerun()

    with chat_tab:
        st.info("Ask follow-up questions about your business data, brainstorm ideas, or ask for advice.", icon="💬")
        if st.button("🗑️ Clear Chat History"):
            if "messages" in st.session_state:
                del st.session_state.messages
            if "chat_session" in st.session_state:
                del st.session_state.chat_session
            st.toast("Chat history cleared!", icon="🗑️")
            st.rerun()
            
        if "chat_session" not in st.session_state:
            with st.spinner("Initializing AI Analyst..."):
                try:
                    genai.configure(api_key=st.secrets.get("GOOGLE_API_KEY"))
                    model = genai.GenerativeModel(model_name="gemini-1.5-flash-latest")
                    st.session_state.chat_session = model.start_chat(history=[])
                except Exception as error:
                    st.error(f"Failed to initialize AI chat session: {error}")
                    st.session_state.chat_session = None
                    
        if "messages" not in st.session_state:
            st.session_state.messages = [{"role": "assistant", "content": "Hello! I'm your AI Business Assistant. How can I help you analyze your sales and inventory today?"}]

        for message in st.session_state.messages:
            with st.chat_message(message["role"]):
                st.write(message["content"])

        if prompt := st.chat_input("Ask about your sales, inventory, etc..."):
            if not st.session_state.get("chat_session"):
                st.error("Chat session not initialized. Please refresh.")
                return
                
            st.session_state.messages.append({"role": "user", "content": prompt})
            with st.chat_message("user"):
                st.write(prompt)

            with st.spinner("Gem is analyzing the latest data..."):
                
                sales_summary = get_sales_summary_data(workspace_id)
                item_sales_data = get_sales_by_item(workspace_id, days_limit=30)
                inventory_items = get_products(workspace_id, include_inactive=False)
                
                context_lines = []
                context_lines.append(f"Here is a snapshot of the business data for '{workspace_name}':")
                
                context_lines.append("\n### Overall Sales Summary (All Time)")
                context_lines.append(f"- Sales Today: ${sales_summary.get('today', 0):.2f}")
                context_lines.append(f"- Sales This Week: ${sales_summary.get('this_week', 0):.2f}")
                context_lines.append(f"- Sales This Year: ${sales_summary.get('this_year', 0):.2f}")

                context_lines.append("\n### Top 5 Best-Selling Products (Last 30 Days)")
                if item_sales_data:
                    for d in item_sales_data[:5]:
                        context_lines.append(f"- **{d['name']}**: {d['total_quantity_sold']} units sold, generating ${d['total_revenue']:.2f}")
                else:
                    context_lines.append("- No sales recorded in the last 30 days.")

                
                out_of_stock_items = [item['name'] for item in inventory_items if item.get('stock_level', 0) <= 0]
                low_stock_items = [item['name'] for item in inventory_items if 0 < item.get('stock_level', 0) <= 5]
                sold_item_names = {d['name'] for d in item_sales_data}
                unsold_items = [item['name'] for item in inventory_items if item['name'] not in sold_item_names]

                context_lines.append("\n### Stock Alert")
                context_lines.append(f"- **Out of Stock Items:** {', '.join(out_of_stock_items) if out_of_stock_items else 'None'}")
                context_lines.append(f"- **Low Stock Items (<= 5 units):** {', '.join(low_stock_items) if low_stock_items else 'None'}")

                context_lines.append("\n### Slowest-Moving Products (No Sales in Last 30 Days)")
                if unsold_items:
                    for name in unsold_items[:5]:
                        context_lines.append(f"- {name}")
                else:
                    context_lines.append("- All active products have had recent sales.")

                business_context = "\n".join(context_lines)
                
                
                final_prompt = f"""
                You are "Gem", a friendly and helpful business analyst. Your role is to analyze the provided data context to answer the user's question. 
                When you are presenting data back to the user, you MUST maintain the markdown formatting (like bullet points, newlines, and bold text) from the "Business Data Snapshot".
                Use only the information given in the context below. Do not invent data.

                **Business Data Snapshot:**
                {business_context}
                ---
                **User's Question:** "{prompt}"
                """
                
                response = st.session_state.chat_session.send_message(final_prompt)
                
                with st.chat_message("assistant"):
                    st.write(response.text)
                st.session_state.messages.append({"role": "assistant", "content": response.text})

def start_application():
    st.set_page_config(page_title="Retail Pro+", layout="wide", initial_sidebar_state="expanded")
    
    if "logged_in_user" not in st.session_state: st.session_state.logged_in_user = None
    if "current_page" not in st.session_state: st.session_state.current_page = "Login"
    if "auth_flow_page" not in st.session_state: st.session_state.auth_flow_page = "login"
    if "cart" not in st.session_state: st.session_state.cart = []
    if "show_add_item_form" not in st.session_state: st.session_state.show_add_item_form = False
    if "active_action" not in st.session_state: st.session_state.active_action = None
    if "active_item_id" not in st.session_state: st.session_state.active_item_id = None
    if "user_workspaces" not in st.session_state: st.session_state.user_workspaces = []
    if "current_workspace_id" not in st.session_state: st.session_state.current_workspace_id = None
    if "current_workspace_name" not in st.session_state: st.session_state.current_workspace_name = "N/A"
    
    
    if st.query_params.get("page") == "accept_invite" and st.session_state.logged_in_user:
        st.session_state.current_page = "Accept Invite"
    elif st.query_params.get("token") and "pending_invite_token_after_login" not in st.session_state and st.session_state.logged_in_user:
        st.session_state.current_page = "Accept Invite"
        st.query_params["page"] = "accept_invite"
        
    
    if not st.session_state.logged_in_user:
        try:
            logo_path = os.path.join("images", "logo.jpg")
            if os.path.exists(logo_path): st.image(logo_path, width=150)
        except Exception: pass
        st.title("Retail Pro+ Portal")
        auth_page = st.session_state.auth_flow_page
        if auth_page == "login" and st.session_state.get("pending_invite_token_after_login"):
            pass
        if st.session_state.current_page == "Accept Invite" and st.query_params.get("token"):
            show_accept_invite_page()
        elif auth_page == "login": show_login_page()
        elif auth_page == "enter_2fa": show_two_factor_auth_page()
        elif auth_page == "signup": show_signup_page()
        elif auth_page == "forgot_password_email": show_forgot_password_email_page()
        elif auth_page == "forgot_password_code": show_forgot_password_code_page()
        elif auth_page == "forgot_password_new_pwd": show_forgot_password_new_pwd_page()
        else:
            show_login_page()
        return

    
    st_autorefresh(interval=15000, key="global_data_refresher")

    user_id_logged_in = st.session_state.logged_in_user['id']
    
    
    refresh_user_workspace_state(user_id_logged_in)

    if 'persistent_notification' in st.session_state:
        notification = st.session_state.persistent_notification
        st.info(notification["message"], icon=notification["icon"])
        del st.session_state.persistent_notification
    
    with st.sidebar:
        try:
            logo_path_sidebar = os.path.join("images", "logo.jpg")
            if os.path.exists(logo_path_sidebar):
                st.image(logo_path_sidebar, width=70)
                st.markdown(f"<h2 style='text-align: left; margin-top: -5px; margin-bottom: 15px;'>Retail Pro+</h2>", unsafe_allow_html=True)
            else: st.sidebar.markdown("## Retail Pro+")
        except Exception: st.sidebar.markdown("## Retail Pro+")
        
        user_name_raw = st.session_state.logged_in_user.get('name', 'User').split(" ")[0]
        safe_user_name = secure_html_escape(user_name_raw)
        st.markdown(f"<h4 style='margin-bottom: 5px;'>Welcome, {safe_user_name}!</h4>", unsafe_allow_html=True)

        user_workspaces_list_for_selector = st.session_state.user_workspaces
        if user_workspaces_list_for_selector:
            workspace_options = {ws['id']: ws['name'] for ws in user_workspaces_list_for_selector}
            
            current_ws_index = 0
            if st.session_state.current_workspace_id in workspace_options:
                current_ws_index = list(workspace_options.keys()).index(st.session_state.current_workspace_id)

            selected_ws_id_from_ui = st.selectbox(
                "Active Workspace:",
                options=list(workspace_options.keys()),
                format_func=lambda ws_id: workspace_options.get(ws_id, "N/A"),
                index=current_ws_index,
                key="workspace_selector"
            )
            if selected_ws_id_from_ui != st.session_state.current_workspace_id:
                st.session_state.current_workspace_id = selected_ws_id_from_ui
                st.session_state.current_workspace_name = workspace_options[selected_ws_id_from_ui]
                st.session_state.cart = []
                st.session_state.active_action = None
                st.session_state.active_item_id = None
                st.session_state.current_page = "Dashboard"
                st.rerun()
        else:
            st.sidebar.error("No workspaces accessible.")
        
        st.markdown("---")

        PAGES_CONFIG = {
            "Dashboard": {"icon": "📊", "func": show_dashboard_page},
            "Inventory": {"icon": "📦", "func": show_inventory_page},
            "Sales":     {"icon": "🛒", "func": show_sales_page},
            "Reports":   {"icon": "📈", "func": show_reports_page},
            "AI Analyst": {"icon": "🤖", "func": show_performance_report_page},
            "Workspace": {"icon": "👥", "func": show_workspace_management_page},
            "Chat":      {"icon": "💬", "func": show_workspace_chat_page},
        }

        if st.session_state.current_page == "Accept Invite":
            PAGES_CONFIG["Accept Invite"] = {"icon": "📧", "func": show_accept_invite_page}
            
        for page_name, page_info in PAGES_CONFIG.items():
            if page_name == "Accept Invite" and st.session_state.current_page != "Accept Invite":
                continue
            is_active = (st.session_state.current_page == page_name)
            button_type = "primary" if is_active else "secondary"
            disable_button = not st.session_state.current_workspace_id and \
                             page_name not in ["Dashboard", "Workspace", "Accept Invite"]
            if st.button(f"{page_info['icon']} {page_name}",
                         key=f"nav_btn_{page_name}",
                         type=button_type,
                         use_container_width=True,
                         disabled=disable_button):
                if st.session_state.current_page != page_name:
                    st.session_state.current_page = page_name
                    if page_name != "Accept Invite" and (st.query_params.get("page") or st.query_params.get("token")):
                        st.query_params.clear()
                    st.rerun()

        st.markdown("---")
        if st.button("🚪 Logout", key="nav_btn_logout", use_container_width=True, type="secondary"):
            keys_to_clear = list(st.session_state.keys())
            for key in keys_to_clear: del st.session_state[key]
            st.query_params.clear()
            st.toast("You have been logged out.")
            st.rerun()

    page_requires_workspace = st.session_state.current_page not in ["Dashboard", "Workspace", "Accept Invite"]
    if page_requires_workspace and not st.session_state.current_workspace_id:
        st.error("No workspace selected. Please select or create a workspace from the sidebar.")
        if st.session_state.current_page not in ["Dashboard", "Workspace"]:
            st.session_state.current_page = "Dashboard"
            st.rerun()
            return

    if st.session_state.current_page in PAGES_CONFIG:
        page_to_render_func = PAGES_CONFIG[st.session_state.current_page]["func"]
        if page_to_render_func:
            page_to_render_func()
    elif st.session_state.current_page == "Login":
        show_login_page()
    else:
        st.warning(f"Unknown page state: {st.session_state.current_page}. Redirecting to Dashboard.")
        st.session_state.current_page = "Dashboard"
        st.rerun()

if __name__ == "__main__":
    for img_dir in ["images", INVENTORY_IMAGE_DIRECTORY]:
        if not os.path.exists(img_dir):
            try: os.makedirs(img_dir)
            except OSError: pass
    start_database()
    start_application()