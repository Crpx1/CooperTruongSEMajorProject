import streamlit as st
import os
import sqlite3
import bcrypt # For password hashing
import random # For reset code
import re     # For email validation
import smtplib # For sending email
import ssl    # For secure connection
from email.message import EmailMessage # For constructing email
import socket # For catching network errors
import shutil # For copying files
import uuid   # For generating unique filenames
import datetime # For timestamps
from PIL import Image # For image manipulation
import pandas as pd # For displaying dataframes

# --- Application Configuration ---
DB_NAME = "retail_pro_plus_v3.db" # New DB name due to significant schema changes
INVENTORY_IMAGE_DIR = "inventory_images"

# --- Email Configuration (IMPORTANT: Use your actual credentials) ---
SENDER_EMAIL = "retailproplus@gmail.com" # Replace with your sender email
SENDER_APP_PASSWORD = "xxuaidchegqsngil" # REPLACE WITH YOUR ACTUAL 16-CHARACTER APP PASSWORD
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 465

# =====================================================================
# --- DATABASE HELPER FUNCTIONS ---
# =====================================================================
def get_db_connection():
    """Establishes and returns a database connection."""
    try:
        conn = sqlite3.connect(DB_NAME)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON;")
        return conn
    except sqlite3.Error as e:
        st.error(f"Database connection error: {e}")
        return None

def init_db():
    """Initializes the DB, creates tables if needed with corrected workspace_members and unique constraints."""
    conn = None
    try:
        conn = get_db_connection()
        if conn is None: return
        cursor = conn.cursor()

        # Users Table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT UNIQUE NOT NULL,
                password_hash BLOB NOT NULL,
                name TEXT
            )
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_email ON users (email)")

        # Workspaces Table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS workspaces (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                owner_user_id INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY (owner_user_id) REFERENCES users (id) ON DELETE CASCADE
            )
        """)

        # Workspace Members Table - CORRECTED SCHEMA to allow NULL user_id
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS workspace_members (
                id INTEGER PRIMARY KEY AUTOINCREMENT,      -- New auto-incrementing ID as primary key
                workspace_id INTEGER NOT NULL,
                user_id INTEGER,                           -- NOW ALLOWS NULL
                role TEXT NOT NULL DEFAULT 'member',
                invited_by_user_id INTEGER,
                invite_email TEXT,
                invite_token TEXT UNIQUE,
                status TEXT NOT NULL DEFAULT 'pending',
                joined_at TEXT,
                FOREIGN KEY (workspace_id) REFERENCES workspaces (id) ON DELETE CASCADE,
                FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE,
                FOREIGN KEY (invited_by_user_id) REFERENCES users (id) ON DELETE SET NULL
            )
        """)
        # Separate CREATE UNIQUE INDEX statements for desired unique behaviors
        cursor.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS idx_workspace_user_accepted_unique
            ON workspace_members (workspace_id, user_id)
            WHERE user_id IS NOT NULL AND status = 'accepted'
        """)
        cursor.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS idx_workspace_user_pending_unique
            ON workspace_members (workspace_id, user_id)
            WHERE user_id IS NOT NULL AND status = 'pending' AND invite_token IS NOT NULL
        """)
        cursor.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS idx_workspace_pending_email_unique
            ON workspace_members (workspace_id, invite_email)
            WHERE invite_email IS NOT NULL AND status = 'pending' AND user_id IS NULL
        """)

        # General indexes
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_workspace_members_user_id ON workspace_members (user_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_workspace_members_invite_token ON workspace_members (invite_token)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_workspace_members_invite_email ON workspace_members (invite_email)")


        # Inventory Table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS inventory (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                workspace_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                retail_price REAL,
                stock_level INTEGER,
                image_path TEXT,
                is_active BOOLEAN NOT NULL DEFAULT 1,
                FOREIGN KEY (workspace_id) REFERENCES workspaces (id) ON DELETE CASCADE
            )
        """)
        cursor.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS idx_inventory_workspace_name_active
            ON inventory (workspace_id, name)
            WHERE is_active = 1
        """)

        # Sales Table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS sales (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                workspace_id INTEGER NOT NULL,
                recorded_by_user_id INTEGER NOT NULL,
                sale_datetime TEXT NOT NULL,
                total_amount REAL NOT NULL,
                FOREIGN KEY (workspace_id) REFERENCES workspaces (id) ON DELETE CASCADE,
                FOREIGN KEY (recorded_by_user_id) REFERENCES users (id) ON DELETE CASCADE
            )
        """)

        # Sale Items Table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS sale_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sale_id INTEGER NOT NULL,
                inventory_item_id INTEGER NOT NULL,
                quantity_sold INTEGER NOT NULL,
                price_per_unit_at_sale REAL NOT NULL,
                subtotal REAL NOT NULL,
                FOREIGN KEY (sale_id) REFERENCES sales (id) ON DELETE CASCADE,
                FOREIGN KEY (inventory_item_id) REFERENCES inventory (id) ON DELETE RESTRICT
            )
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_sale_items_sale_id ON sale_items (sale_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_sale_items_inventory_id ON sale_items (inventory_item_id)")

        conn.commit()
        print("Database initialized successfully with fully corrected workspace_members schema and indexes.")
    except sqlite3.Error as e:
        st.error(f"Database error during initialization: {e}")
        print(f"SQL error during DB init: {e}")
        if conn: conn.rollback()
    finally:
        if conn: conn.close()
# =====================================================================
# --- WORKSPACE HELPER FUNCTIONS ---
# =====================================================================
def create_workspace(name, owner_user_id):
    conn = None
    workspace_id = None
    try:
        conn = get_db_connection()
        if conn is None: return None
        cursor = conn.cursor()
        created_at = datetime.datetime.now().isoformat()
        cursor.execute(
            "INSERT INTO workspaces (name, owner_user_id, created_at) VALUES (?, ?, ?)",
            (name, owner_user_id, created_at)
        )
        workspace_id = cursor.lastrowid
        conn.commit()
        if workspace_id:
             # Add owner as a member
            add_workspace_member(workspace_id, owner_user_id, owner_user_id, role='owner', status='accepted')
        return workspace_id
    except sqlite3.Error as e:
        st.error(f"DB Error: Failed to create workspace: {e}")
    finally:
        if conn: conn.close()
    return workspace_id

def add_workspace_member(workspace_id, user_id, invited_by_user_id, role='member', invite_email=None, invite_token=None, status='pending'):
    conn = None
    success = False
    try:
        conn = get_db_connection()
        if conn is None: return False
        cursor = conn.cursor()
        joined_at = datetime.datetime.now().isoformat() if status == 'accepted' else None

        actual_invitee_user_id = user_id 

        if invite_email and not actual_invitee_user_id:
            invited_user_obj = find_user_by_email(invite_email)
            if invited_user_obj:
                actual_invitee_user_id = invited_user_obj['id']
                cursor.execute("""
                    SELECT 1 FROM workspace_members
                    WHERE workspace_id = ? AND user_id = ? AND (status = 'accepted' OR (status = 'pending' AND invite_token IS NOT NULL))
                """, (workspace_id, actual_invitee_user_id)) # Check for active or token-based pending invite
                if cursor.fetchone():
                    st.info(f"User {invite_email} is already an accepted member or has a pending invitation for this workspace.")
                    return False 

        if actual_invitee_user_id: 
            print(f"Attempting to add/invite known user ID: {actual_invitee_user_id} to workspace {workspace_id} with status {status}")
            # This path is for existing users or when owner is added.
            # If status is 'pending' and user exists, an invite_token should be present.
            # If status is 'accepted' (like for owner), token can be NULL.
            cursor.execute(
                """INSERT INTO workspace_members (workspace_id, user_id, role, invited_by_user_id, invite_email, invite_token, status, joined_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (workspace_id, actual_invitee_user_id, role, invited_by_user_id, invite_email, invite_token, status, joined_at)
            )
        elif invite_email and invite_token: 
            print(f"Attempting to add pending invite for email: {invite_email} to workspace {workspace_id}")
            cursor.execute(
                """INSERT INTO workspace_members (workspace_id, user_id, invite_email, role, invited_by_user_id, invite_token, status)
                   VALUES (?, NULL, ?, ?, ?, ?, ?)
                """, 
                (workspace_id, invite_email, role, invited_by_user_id, invite_token, status)
            )
        else:
            st.error("Cannot add member: Insufficient information for add_workspace_member.")
            return False

        conn.commit()
        success = True
    except sqlite3.IntegrityError as e:
        error_msg_lower = str(e).lower()
        if "unique constraint failed: workspace_members.invite_token" in error_msg_lower:
            st.error("Failed to add member: This invitation token has already been used or generated.")
        elif "unique constraint failed" in error_msg_lower and ("idx_workspace_user_accepted_unique" in error_msg_lower or "idx_workspace_user_pending_unique" in error_msg_lower) :
             st.error(f"This user is already an active or pending member of the workspace.")
        elif "unique constraint failed" in error_msg_lower and "idx_workspace_pending_email_unique" in error_msg_lower:
            st.error(f"A pending invitation already exists for {invite_email} in this workspace.")
        elif "foreign key constraint failed" in error_msg_lower:
             st.error(f"Failed to add member: Invalid workspace or user reference. Details: {e}")
        elif "not null constraint failed: workspace_members.user_id" in error_msg_lower: # Should not happen with correct schema + logic
             st.error(f"DB Integrity Error: User ID was null when it shouldn't be. Check logic. Error: {e}")
        else:
            st.error(f"DB Integrity Error: Failed to add workspace member: {e}")
        print(f"IntegrityError in add_workspace_member: {e}")
    except sqlite3.Error as e:
        st.error(f"DB Error: Failed to add workspace member: {e}")
        print(f"SQLite Error in add_workspace_member: {e}")
    finally:
        if conn: conn.close()
    return success

def get_user_workspaces(user_id):
    """Fetches all workspaces a user is a member of and has accepted."""
    conn = None
    workspaces_list = []
    try:
        conn = get_db_connection()
        if conn is None: return []
        cursor = conn.cursor()
        cursor.execute("""
            SELECT w.id, w.name, w.owner_user_id, wm.role
            FROM workspaces w
            JOIN workspace_members wm ON w.id = wm.workspace_id
            WHERE wm.user_id = ? AND wm.status = 'accepted'
        """, (user_id,))
        workspaces_list = [dict(row) for row in cursor.fetchall()]
    except sqlite3.Error as e:
        st.error(f"DB Error: Failed to get user workspaces: {e}")
    finally:
        if conn: conn.close()
    return workspaces_list

def find_workspace_by_id(workspace_id):
    conn = None
    workspace = None
    try:
        conn = get_db_connection()
        if conn is None: return None
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM workspaces WHERE id = ?", (workspace_id,))
        workspace = cursor.fetchone()
        if workspace: return dict(workspace)
    except sqlite3.Error as e:
        st.error(f"DB Error: Failed to find workspace by ID: {e}")
    finally:
        if conn: conn.close()
    return None

def get_workspace_members_details(workspace_id):
    """Gets members of a workspace, including their names and emails."""
    conn = None
    members = []
    try:
        conn = get_db_connection()
        if conn is None: return []
        cursor = conn.cursor()
        # Members who have accepted
        cursor.execute("""
            SELECT u.id as user_id, u.name, u.email, wm.role, wm.status, wm.joined_at
            FROM workspace_members wm
            JOIN users u ON wm.user_id = u.id
            WHERE wm.workspace_id = ? AND wm.status = 'accepted'
        """, (workspace_id,))
        members.extend([dict(row) for row in cursor.fetchall()])

        # Pending invitations for registered users not yet accepted
        cursor.execute("""
            SELECT u.id as user_id, u.name, u.email, wm.role, wm.status, wm.invite_token
            FROM workspace_members wm
            JOIN users u ON wm.user_id = u.id
            WHERE wm.workspace_id = ? AND wm.status = 'pending' AND wm.invite_token IS NOT NULL
        """, (workspace_id,))
        members.extend([dict(row) for row in cursor.fetchall()])


        # Pending invitations for emails not yet registered
        cursor.execute("""
            SELECT null as user_id, '(Invited User - Not Registered)' as name, wm.invite_email as email, wm.role, wm.status, wm.invite_token
            FROM workspace_members wm
            WHERE wm.workspace_id = ? AND wm.status = 'pending' AND wm.user_id IS NULL AND wm.invite_email IS NOT NULL
        """, (workspace_id,))
        members.extend([dict(row) for row in cursor.fetchall()])

    except sqlite3.Error as e:
        st.error(f"DB Error fetching workspace members: {e}")
    finally:
        if conn: conn.close()
    return members

def send_workspace_invite_email(recipient_email, inviter_name, workspace_name, invite_link):
    subject = f"You're invited to join {workspace_name} on Retail Pro+"
    body = f"""Hi,

{inviter_name} has invited you to collaborate on the workspace '{workspace_name}' in Retail Pro+.

To accept this invitation, please click the link below:
{invite_link}

If you don't have a Retail Pro+ account, you'll be prompted to create one.

Thanks,
The Retail Pro+ Team
"""
    return send_email(recipient_email, subject, body)


def process_workspace_invite(invite_token, accepting_user_id):
    conn = None
    success = False
    try:
        conn = get_db_connection()
        if conn is None: return False, "Database connection failed."
        cursor = conn.cursor()

        # Find the invitation by token
        cursor.execute(
            "SELECT workspace_id, invite_email, user_id FROM workspace_members WHERE invite_token = ? AND status = 'pending'",
            (invite_token,)
        )
        invite_details = cursor.fetchone()

        if not invite_details:
            return False, "Invalid or expired invitation token."

        workspace_id = invite_details['workspace_id']
        invited_original_user_id = invite_details['user_id'] # This might be NULL if invited by email only

        # Check if the accepting user is the one intended (if user_id was set on invite)
        # Or if the invite was for an email and the accepting user's email matches.
        accepting_user_obj = find_user_by_id(accepting_user_id, conn) # Pass connection
        if not accepting_user_obj:
            return False, "Accepting user not found."

        can_accept = False
        if invited_original_user_id and invited_original_user_id == accepting_user_id:
            can_accept = True
        elif invite_details['invite_email'] and invite_details['invite_email'].lower() == accepting_user_obj['email'].lower():
            can_accept = True

        if not can_accept:
            return False, "This invitation was intended for a different user or email address."


        # Update the workspace_members record
        # If the original invite was for an email (user_id was NULL), update it with the accepting_user_id
        if invited_original_user_id is None and invite_details['invite_email']:
            # Check if this user is already a member (e.g. accepted via another path)
            cursor.execute("SELECT 1 FROM workspace_members WHERE workspace_id = ? AND user_id = ? AND status = 'accepted'", (workspace_id, accepting_user_id))
            if cursor.fetchone():
                # User is already an accepted member, perhaps clean up the tokened invite if it's separate
                cursor.execute("DELETE FROM workspace_members WHERE invite_token = ?", (invite_token,))
                conn.commit()
                return True, "You are already a member of this workspace."

            # Update the pending row that has the token
            cursor.execute(
                """UPDATE workspace_members
                   SET user_id = ?, status = 'accepted', joined_at = ?, invite_token = NULL
                   WHERE invite_token = ? AND workspace_id = ? AND invite_email = ?
                """,
                (accepting_user_id, datetime.datetime.now().isoformat(), invite_token, workspace_id, invite_details['invite_email'])
            )
        else: # Invite was already associated with a user_id, just update status
            cursor.execute(
                """UPDATE workspace_members
                   SET status = 'accepted', joined_at = ?, invite_token = NULL
                   WHERE invite_token = ? AND workspace_id = ? AND user_id = ?
                """,
                (datetime.datetime.now().isoformat(), invite_token, workspace_id, accepting_user_id)
            )

        if cursor.rowcount > 0:
            conn.commit()
            success = True
            # Clean up any other pending invites for this user_id to this workspace if they had multiple
            cursor.execute("""
                DELETE FROM workspace_members
                WHERE workspace_id = ? AND user_id = ? AND status = 'pending' AND invite_token IS NOT NULL AND invite_token != ?
            """, (workspace_id, accepting_user_id, invite_token)) # The last condition is a bit redundant after setting token to NULL
            conn.commit()
            return True, "Invitation accepted successfully! You now have access to the workspace."
        else:
            # This case might occur if the invite was already processed or if the update conditions didn't match.
            # Check if already accepted.
            cursor.execute("SELECT 1 FROM workspace_members WHERE workspace_id = ? AND user_id = ? AND status = 'accepted'", (workspace_id, accepting_user_id))
            if cursor.fetchone():
                return True, "Invitation already accepted. You have access to the workspace."
            return False, "Failed to update invitation status. It might have been processed already or there was an issue."

    except sqlite3.Error as e:
        if conn: conn.rollback()
        st.error(f"DB Error: Failed to process invitation: {e}")
        return False, f"Database error: {e}"
    finally:
        if conn: conn.close()
    return success, "An unexpected error occurred."


def check_user_workspace_membership(user_id, workspace_id, conn_to_use=None):
    """Checks if a user is an accepted member of a given workspace."""
    conn = conn_to_use if conn_to_use else get_db_connection()
    is_member = False
    if conn is None: return False
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT 1 FROM workspace_members WHERE user_id = ? AND workspace_id = ? AND status = 'accepted'",
            (user_id, workspace_id)
        )
        if cursor.fetchone():
            is_member = True
    except sqlite3.Error as e:
        st.error(f"DB Error checking workspace membership: {e}")
    finally:
        if conn and not conn_to_use: # Close only if this function opened it
            conn.close()
    return is_member

def get_workspace_owner_id(workspace_id, conn_to_use=None):
    conn = conn_to_use if conn_to_use else get_db_connection()
    owner_id = None
    if conn is None: return None
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT owner_user_id FROM workspaces WHERE id = ?", (workspace_id,))
        row = cursor.fetchone()
        if row:
            owner_id = row['owner_user_id']
    except sqlite3.Error as e:
        st.error(f"DB Error getting workspace owner: {e}")
    finally:
        if conn and not conn_to_use:
            conn.close()
    return owner_id


# =====================================================================
# --- USER DB Functions ---
# =====================================================================
def find_user_by_email(email):
    user = None; conn = None
    try:
        conn = get_db_connection();
        if conn is None: return None
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE email = ?", (email,))
        user_data = cursor.fetchone()
        if user_data: user = dict(user_data)
    except sqlite3.Error as e: st.error(f"DB error finding user: {e}")
    finally:
        if conn: conn.close()
    return user

def find_user_by_id(user_id, conn_to_use=None): # Added conn_to_use for internal calls
    user = None
    conn = conn_to_use if conn_to_use else get_db_connection()
    if conn is None: return None
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,))
        user_data = cursor.fetchone()
        if user_data: user = dict(user_data)
    except sqlite3.Error as e: st.error(f"DB error finding user by ID: {e}")
    finally:
        if conn and not conn_to_use: conn.close() # Close only if this function opened it
    return user


def add_user(email, password, name):
    conn = None; success = False; user_id = None
    try:
        hashed_pw = hash_password(password)
        if not hashed_pw: raise ValueError("Password hashing failed.")
        conn = get_db_connection()
        if conn is None: return False, None
        cursor = conn.cursor()
        cursor.execute("INSERT INTO users (email, password_hash, name) VALUES (?, ?, ?)", (email, hashed_pw, name))
        user_id = cursor.lastrowid
        conn.commit()

        if user_id:
            # Create a default workspace for the new user
            workspace_name = f"{name.split(' ')[0]}'s Workspace" if name else f"{email.split('@')[0]}'s Workspace"
            default_workspace_id = create_workspace(workspace_name, user_id) # create_workspace already adds owner as member
            if default_workspace_id:
                print(f"Default workspace '{workspace_name}' (ID: {default_workspace_id}) created for user {user_id}.")
                success = True
            else:
                # This is a problem, user created but workspace failed.
                # For simplicity now, we'll still count user creation as success, but log error.
                st.error("User account created, but failed to create their default workspace. Please contact support.")
                print(f"CRITICAL: User {user_id} created, but default workspace creation failed.")
                success = True # User is created, that's the primary goal of this function.
        else:
            st.error("Failed to get user ID after registration.")

    except sqlite3.IntegrityError: st.error(f"Email '{email}' already registered.")
    except (sqlite3.Error, ValueError) as e: st.error(f"Failed to register user: {e}")
    finally:
        if conn: conn.close()
    return success, user_id


def update_user_password(email, new_password): # Unchanged mostly
    conn = None; success = False
    try:
        hashed_pw = hash_password(new_password)
        if not hashed_pw: raise ValueError("Password hashing failed.")
        conn = get_db_connection()
        if conn is None: return False
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET password_hash = ? WHERE email = ?", (hashed_pw, email))
        conn.commit()
        if cursor.rowcount > 0: success = True
        else: st.warning("Could not find user to update password.")
    except (sqlite3.Error, ValueError) as e: st.error(f"DB Error: Failed to update password: {e}")
    finally:
        if conn: conn.close()
    return success

def check_user_exists(user_id, conn): # Unchanged
    cursor = conn.cursor()
    cursor.execute("SELECT 1 FROM users WHERE id = ?", (user_id,))
    return cursor.fetchone() is not None

# =====================================================================
# --- Inventory Database Functions (MODIFIED for workspace_id) ---
# =====================================================================
def add_inventory_item(workspace_id, name, retail_price, stock_level, image_path=None, added_by_user_id=None):
    conn = None; success = False
    try:
        if not name: raise ValueError("Item name cannot be empty.")
        price = float(retail_price); stock = int(stock_level)
        if price < 0: raise ValueError("Price cannot be negative.")
        if stock < 0: raise ValueError("Stock level cannot be negative.")

        conn = get_db_connection()
        if conn is None: return False

        # Optional: Check if added_by_user_id is a member of workspace_id
        if added_by_user_id and not check_user_workspace_membership(added_by_user_id, workspace_id, conn):
            st.error(f"User (ID: {added_by_user_id}) is not authorized to add items to this workspace (ID: {workspace_id}).")
            return False

        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO inventory (workspace_id, name, retail_price, stock_level, image_path, is_active) VALUES (?, ?, ?, ?, ?, 1)",
            (workspace_id, name, price, stock, image_path)
        )
        conn.commit(); success = True
    except sqlite3.IntegrityError as e:
        error_str = str(e).lower()
        if "unique constraint failed" in error_str and "idx_inventory_workspace_name_active" in error_str:
            st.error(f"An active item named '{name}' already exists in this workspace.")
        elif "foreign key constraint failed" in error_str and "workspaces" in error_str:
            st.error(f"Failed to add item: The specified workspace (ID: {workspace_id}) does not exist or there's a reference issue. Please ensure you are in a valid workspace.")
        else:
            st.error(f"Failed to add item due to a database constraint: {e}")
    except (sqlite3.Error, ValueError) as e:
        st.error(f"Failed to add item: {e}")
    finally:
        if conn: conn.close()
    return success

def get_inventory_items(workspace_id, search_term="", price_filter="Any", stock_filter="Any", include_inactive=False):
    items_list = []; conn = None
    try:
        conn = get_db_connection()
        if conn is None: return []
        cursor = conn.cursor()
        query = "SELECT id, name, retail_price, stock_level, image_path, is_active FROM inventory WHERE workspace_id = ?"
        conditions = []; params = [workspace_id]

        if not include_inactive:
            conditions.append("is_active = 1")

        if search_term: conditions.append("name LIKE ?"); params.append(f"%{search_term}%")
        if price_filter == "< $30": conditions.append("retail_price < ?"); params.append(30.0)
        elif price_filter == "$30-$100": conditions.append("retail_price BETWEEN ? AND ?"); params.extend([30.0, 100.0])
        elif price_filter == "> $100": conditions.append("retail_price > ?"); params.append(100.0)

        if stock_filter == "Low Stock": low_thresh = 5; conditions.append("stock_level > ? AND stock_level <= ?"); params.extend([0, low_thresh])
        elif stock_filter == "Out of Stock": conditions.append("stock_level <= ?"); params.append(0)
        elif stock_filter == "In Stock": conditions.append("stock_level > ?"); params.append(0)

        if conditions: query += " AND " + " AND ".join(conditions)
        query += " ORDER BY name ASC"
        cursor.execute(query, params)
        items_list = [dict(row) for row in cursor.fetchall()]
    except sqlite3.Error as e: st.error(f"DB error getting inventory: {e}")
    finally:
        if conn: conn.close()
    return items_list

def get_item_by_id(item_id, workspace_id, include_inactive=False):
    item_dict = None; conn = None
    try:
        conn = get_db_connection()
        if conn is None: return None
        cursor = conn.cursor()
        query = "SELECT id, name, retail_price, stock_level, image_path, is_active FROM inventory WHERE id = ? AND workspace_id = ?"
        params = [item_id, workspace_id]
        if not include_inactive:
            query += " AND is_active = 1"

        cursor.execute(query, params)
        row = cursor.fetchone()
        if row: item_dict = dict(row)
    except sqlite3.Error as e: st.error(f"DB error getting item by ID: {e}")
    finally:
        if conn: conn.close()
    return item_dict

def update_inventory_item(item_id, workspace_id, name, retail_price, stock_level, image_path=None, is_active=True, updated_by_user_id=None):
    conn = None; success = False
    try:
        if not name: raise ValueError("Item name cannot be empty.")
        price = float(retail_price); stock = int(stock_level)
        if price < 0: raise ValueError("Price cannot be negative.")
        if stock < 0: raise ValueError("Stock level cannot be negative.")
        conn = get_db_connection()
        if conn is None: return False

        if updated_by_user_id and not check_user_workspace_membership(updated_by_user_id, workspace_id, conn):
            st.error(f"User (ID: {updated_by_user_id}) is not authorized to update items in this workspace (ID: {workspace_id}).")
            return False

        cursor = conn.cursor()
        cursor.execute(
            "UPDATE inventory SET name = ?, retail_price = ?, stock_level = ?, image_path = ?, is_active = ? WHERE id = ? AND workspace_id = ?",
            (name, price, stock, image_path, 1 if is_active else 0, item_id, workspace_id)
        )
        conn.commit()
        if cursor.rowcount > 0: success = True
        else: st.warning(f"Item ID {item_id} not found for update in this workspace or no changes were made.")
    except sqlite3.IntegrityError as e:
        if "UNIQUE constraint failed" in str(e) and "idx_inventory_workspace_name_active" in str(e):
            st.error(f"Another active item named '{name}' already exists in this workspace.")
        else:
            st.error(f"Failed to update item due to a database constraint: {e}")
    except (sqlite3.Error, ValueError) as e: st.error(f"Failed to update item: {e}")
    finally:
        if conn: conn.close()
    return success

def delete_inventory_item(item_id, workspace_id, deleted_by_user_id=None): # This is soft delete
    conn = None; success = False
    try:
        conn = get_db_connection()
        if conn is None: return False

        if deleted_by_user_id and not check_user_workspace_membership(deleted_by_user_id, workspace_id, conn):
            st.error(f"User (ID: {deleted_by_user_id}) is not authorized to delete items in this workspace (ID: {workspace_id}).")
            return False

        cursor = conn.cursor()
        cursor.execute("UPDATE inventory SET is_active = 0 WHERE id = ? AND workspace_id = ?", (item_id, workspace_id))
        conn.commit()
        if cursor.rowcount > 0:
            success = True
        else:
            st.warning(f"Item ID {item_id} not found in this workspace to deactivate.")
    except sqlite3.Error as e: st.error(f"DB Error: Failed to deactivate item: {e}")
    finally:
        if conn: conn.close()
    return success

# =====================================================================
# --- Sales Database Functions (MODIFIED for workspace_id and recorded_by_user_id) ---
# =====================================================================
def record_sale(workspace_id, recorded_by_user_id, cart_items, total_sale_amount):
    conn = None
    try:
        conn = get_db_connection()
        if conn is None: return False

        if not check_user_workspace_membership(recorded_by_user_id, workspace_id, conn):
            st.error(f"User (ID: {recorded_by_user_id}) is not authorized to record sales in this workspace (ID: {workspace_id}).")
            return False

        cursor = conn.cursor()
        conn.execute("BEGIN TRANSACTION")

        for item_in_cart in cart_items:
            # Check stock within the correct workspace
            cursor.execute("SELECT stock_level, name, is_active FROM inventory WHERE id = ? AND workspace_id = ?", (item_in_cart['id'], workspace_id))
            stock_info = cursor.fetchone()
            if stock_info is None:
                raise ValueError(f"Product '{item_in_cart['name']}' (ID: {item_in_cart['id']}) not found in this workspace.")
            if not stock_info['is_active']:
                raise ValueError(f"Product '{item_in_cart['name']}' is currently inactive and cannot be sold.")
            if stock_info['stock_level'] < item_in_cart['quantity']:
                raise ValueError(f"Not enough stock for '{item_in_cart['name']}'. Available: {stock_info['stock_level']}, Requested: {item_in_cart['quantity']}.")

        sale_dt = datetime.datetime.now().isoformat()
        cursor.execute(
            "INSERT INTO sales (workspace_id, recorded_by_user_id, sale_datetime, total_amount) VALUES (?, ?, ?, ?)",
            (workspace_id, recorded_by_user_id, sale_dt, total_sale_amount)
        )
        sale_id = cursor.lastrowid

        for item_in_cart in cart_items:
            cursor.execute(
                "INSERT INTO sale_items (sale_id, inventory_item_id, quantity_sold, price_per_unit_at_sale, subtotal) VALUES (?, ?, ?, ?, ?)",
                (sale_id, item_in_cart['id'], item_in_cart['quantity'], item_in_cart['price_unit'], item_in_cart['subtotal'])
            )
            # Update inventory stock in the correct workspace
            cursor.execute("UPDATE inventory SET stock_level = stock_level - ? WHERE id = ? AND workspace_id = ?", (item_in_cart['quantity'], item_in_cart['id'], workspace_id))

        conn.commit()
        return True
    except ValueError as ve:
        if conn: conn.rollback()
        st.error(f"Sale Error: {str(ve)}")
        return False
    except sqlite3.Error as e:
        if conn: conn.rollback()
        st.error(f"Database Error: Failed to record sale: {e}")
        return False
    finally:
        if conn: conn.close()

def get_sales_summary(workspace_id):
    conn = None
    sales_today, sales_this_week, sales_this_year = 0.0, 0.0, 0.0
    today_date = datetime.date.today()
    current_year = today_date.year
    current_iso_week = today_date.isocalendar()

    try:
        conn = get_db_connection()
        if conn is None: return {'today': 0.0, 'this_week': 0.0, 'this_year': 0.0}
        cursor = conn.cursor()
        cursor.execute("SELECT sale_datetime, total_amount FROM sales WHERE workspace_id = ?", (workspace_id,))
        all_sales = cursor.fetchall()

        for sale_row in all_sales:
            try:
                sale_dt_obj = datetime.datetime.fromisoformat(sale_row['sale_datetime'])
                sale_date_obj = sale_dt_obj.date()
                if sale_date_obj == today_date: sales_today += sale_row['total_amount']
                sale_iso_week = sale_date_obj.isocalendar()
                if sale_iso_week[0] == current_iso_week[0] and sale_iso_week[1] == current_iso_week[1]:
                    sales_this_week += sale_row['total_amount']
                if sale_date_obj.year == current_year: sales_this_year += sale_row['total_amount']
            except ValueError: continue
    except sqlite3.Error as e:
        st.error(f"Database error fetching sales summary for workspace {workspace_id}: {e}")
    finally:
        if conn: conn.close()
    return {'today': sales_today, 'this_week': sales_this_week, 'this_year': sales_this_year}

def get_sales_data_for_graph(workspace_id, period):
    conn = None
    try:
        conn = get_db_connection()
        if conn is None: return None
        cursor = conn.cursor()
        cursor.execute("SELECT sale_datetime, total_amount FROM sales WHERE workspace_id = ?", (workspace_id,))
        all_sales_records = cursor.fetchall()
        today_date = datetime.date.today()
        # ... (rest of the aggregation logic remains the same, just data source is filtered by workspace_id)
        if period == "Day":
            hourly_sales_agg = {h: 0.0 for h in range(24)}
            if all_sales_records:
                for record in all_sales_records:
                    try:
                        sale_dt_obj = datetime.datetime.fromisoformat(record['sale_datetime'])
                        if sale_dt_obj.date() == today_date:
                            hourly_sales_agg[sale_dt_obj.hour] += record['total_amount']
                    except ValueError: continue
            sales_values = [hourly_sales_agg.get(h, 0.0) for h in range(24)]
            df = pd.DataFrame({'Sales': sales_values}, index=pd.Index(range(24), name="Hour of Day (0-23)"))
            return df

        elif period == "Week":
            days_of_week_labels = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
            weekly_sales_agg = {day_label: 0.0 for day_label in days_of_week_labels}
            start_of_current_week = today_date - datetime.timedelta(days=today_date.weekday())
            end_of_current_week = start_of_current_week + datetime.timedelta(days=6)
            if all_sales_records:
                for record in all_sales_records:
                    try:
                        sale_dt_obj = datetime.datetime.fromisoformat(record['sale_datetime'])
                        sale_date = sale_dt_obj.date()
                        if start_of_current_week <= sale_date <= end_of_current_week:
                            day_label = days_of_week_labels[sale_date.weekday()]
                            weekly_sales_agg[day_label] += record['total_amount']
                    except ValueError: continue
            sales_values_ordered = [weekly_sales_agg.get(day, 0.0) for day in days_of_week_labels]
            ordered_week_index = pd.CategoricalIndex(days_of_week_labels, categories=days_of_week_labels, ordered=True, name="Day of Week")
            df = pd.DataFrame({'Sales': sales_values_ordered}, index=ordered_week_index)
            return df

        elif period == "Year":
            months_of_year_labels = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
            monthly_sales_agg = {month_label: 0.0 for month_label in months_of_year_labels}
            current_year = today_date.year
            if all_sales_records:
                for record in all_sales_records:
                    try:
                        sale_dt_obj = datetime.datetime.fromisoformat(record['sale_datetime'])
                        if sale_dt_obj.year == current_year:
                            month_label = months_of_year_labels[sale_dt_obj.month - 1]
                            monthly_sales_agg[month_label] += record['total_amount']
                    except ValueError: continue
            sales_values_ordered = [monthly_sales_agg.get(month, 0.0) for month in months_of_year_labels]
            ordered_month_index = pd.CategoricalIndex(months_of_year_labels, categories=months_of_year_labels, ordered=True, name="Month")
            df = pd.DataFrame({'Sales': sales_values_ordered}, index=ordered_month_index)
            return df

    except sqlite3.Error as e:
        st.error(f"Database error while generating report data for workspace {workspace_id}: {e}")
    except Exception as ex:
        st.error(f"An unexpected error occurred while generating report data: {ex}")
    finally:
        if conn: conn.close()
    return None


def get_best_selling_items(workspace_id, limit=5):
    items_list = []; conn = None
    try:
        conn = get_db_connection()
        if conn is None: return []
        cursor = conn.cursor()
        query = """
            SELECT
                i.name, SUM(si.quantity_sold) as total_quantity_sold,
                i.image_path, i.retail_price, i.is_active
            FROM sale_items si
            JOIN inventory i ON si.inventory_item_id = i.id
            JOIN sales s ON si.sale_id = s.id
            WHERE s.workspace_id = ? AND i.workspace_id = ? -- Ensure items and sales are from the same workspace
            GROUP BY si.inventory_item_id, i.name, i.image_path, i.retail_price, i.is_active
            ORDER BY total_quantity_sold DESC
            LIMIT ?
        """ # Added i.workspace_id = ? to ensure join integrity on workspace
        cursor.execute(query, (workspace_id, workspace_id, limit))
        items_list = [dict(row) for row in cursor.fetchall()]
    except sqlite3.Error as e:
        st.error(f"DB error getting best selling items: {e}")
    finally:
        if conn: conn.close()
    return items_list

# =====================================================================
# --- PASSWORD HELPER FUNCTIONS (Unchanged)---
# =====================================================================
def hash_password(password):
    if not password: return None
    try: return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())
    except Exception as e: print(f"Error hashing password: {e}"); return None

def check_password(plain_password, hashed_password_bytes):
    if not plain_password or not hashed_password_bytes: return False
    try: return bcrypt.checkpw(plain_password.encode('utf-8'), hashed_password_bytes)
    except Exception as e: print(f"Error checking password: {e}"); return False

def is_password_valid(password):
    errors = []
    if len(password) < 8: errors.append("min 8 characters")
    if not any(char.isupper() for char in password): errors.append("1 uppercase letter")
    if not any(char.isdigit() for char in password): errors.append("1 number")
    if not errors: return True, ""
    return False, "Password must contain: " + ", ".join(errors) + "."

# =====================================================================
# --- EMAIL HELPER FUNCTIONS (Mostly Unchanged, added invite email)---
# =====================================================================
def send_email(recipient_email, subject, body):
    print(f"Attempting to send email to: {recipient_email}")
    if SENDER_APP_PASSWORD == "YOUR_ACTUAL_16_CHAR_APP_PASSWORD" or not SENDER_APP_PASSWORD or SENDER_APP_PASSWORD == "ypmexylemaloqnfw": # Keep your actual check here
        # Use a placeholder for display if it's the actual one, otherwise, it means it's not set
        actual_display_pass = "YOUR_APP_PASSWORD_PLACEHOLDER" if SENDER_APP_PASSWORD == "ypmexylemaloqnfw" else SENDER_APP_PASSWORD
        st.error(f"CRITICAL: SENDER_APP_PASSWORD ('{actual_display_pass}') is not set correctly. Update it in the script.")
        print(f"CRITICAL: SENDER_APP_PASSWORD ('{actual_display_pass}') not set or is placeholder.")
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
            print("Email sent successfully!")
            return True
    except smtplib.SMTPAuthenticationError as e_auth:
        st.error("Email Auth failed. Check SENDER_EMAIL or SENDER_APP_PASSWORD.")
        print(f"SMTP Authentication Error: {e_auth}")
    except (smtplib.SMTPException, socket.gaierror, OSError) as e_smtp:
        st.error(f"Failed to send email due to SMTP/Network issue: {e_smtp}")
        print(f"SMTP/Network Error: {e_smtp}")
    except Exception as e:
        st.error(f"An unexpected error occurred during email sending: {e}")
        print(f"Unexpected Email Sending Error: {e}")
    return False

def send_reset_email(recipient_email, reset_code):
    subject = "Your Password Reset Code for Retail Pro+"
    body = f"Hi,\n\nYour password reset code is: {reset_code}\n\nPlease use this to reset your password.\n\nThanks,\nThe Retail Pro+ Team"
    return send_email(recipient_email, subject, body)

def send_auth_code_email(recipient_email, auth_code):
    subject = "Your Retail Pro+ Login Verification Code"
    body = f"Hi,\n\nYour login verification code is: {auth_code}\n\nThanks,\nThe Retail Pro+ Team"
    return send_email(recipient_email, subject, body)

# =====================================================================
# --- UTILITY FUNCTIONS (Unchanged)---
# =====================================================================
def is_valid_email(email):
    if not email: return False
    return re.match(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$", email) is not None

def handle_streamlit_image_upload(uploaded_file_obj, workspace_id_for_pathing): # workspace_id for potential subfolder structure
    if uploaded_file_obj is not None:
        try:
            # Consider organizing images by workspace: os.path.join(INVENTORY_IMAGE_DIR, str(workspace_id_for_pathing))
            current_save_dir = INVENTORY_IMAGE_DIR
            if not os.path.exists(current_save_dir):
                os.makedirs(current_save_dir)

            file_extension = os.path.splitext(uploaded_file_obj.name)[1]
            unique_filename = f"{uuid.uuid4()}{file_extension}"
            destination_path = os.path.join(current_save_dir, unique_filename)
            with open(destination_path, "wb") as f:
                f.write(uploaded_file_obj.getbuffer())
            return destination_path
        except Exception as e:
            st.error(f"Error saving uploaded image: {e}")
    return None

# =====================================================================
# --- STREAMLIT PAGE RENDERING FUNCTIONS ---
# =====================================================================

def render_login_page():
    st.subheader("Welcome Back")
    st.caption("Please enter your details!")
    with st.form("login_form"):
        email = st.text_input("Email Address", key="login_email")
        password = st.text_input("Password", type="password", key="login_password")
        login_btn = st.form_submit_button("Sign In", use_container_width=True)

    if st.button("Forgot Password?", key="login_forgot_pwd_link"):
        st.session_state.auth_flow_page = "forgot_password_email"; st.rerun()

    if login_btn:
        if not email or not password: st.warning("Email and Password are required.")
        elif not is_valid_email(email): st.warning("Please enter a valid email address.")
        else:
            user = find_user_by_email(email)
            if user and check_password(password, user['password_hash']):
                auth_code = str(random.randint(100000, 999999))
                if send_auth_code_email(user['email'], auth_code):
                    st.session_state.auth_user_email = user['email']
                    st.session_state.auth_user_data = dict(user) # Store user dict
                    st.session_state.auth_expected_code = auth_code
                    st.session_state.auth_flow_page = "enter_2fa"
                    st.toast(f"Verification code sent to {user['email']}.", icon="✅")
                    st.rerun()
                else: st.error("Failed to send verification code. Please try again.")
            else: st.error("Invalid email or password.")
    if st.button("Don't have an account? Sign Up", key="login_signup_link"):
        st.session_state.auth_flow_page = "signup"; st.rerun()

def render_2fa_page():
    st.subheader("Enter Verification Code")
    st.caption(f"A 6-digit code was sent to {st.session_state.get('auth_user_email', 'your email')}.")
    with st.form("2fa_form"):
        code = st.text_input("Authentication Code", max_chars=6, key="2fa_code_input")
        verify_btn = st.form_submit_button("Verify & Login")
    if verify_btn:
        if code == st.session_state.get('auth_expected_code'):
            st.session_state.logged_in_user = st.session_state.auth_user_data
            user_id = st.session_state.logged_in_user['id']

            # Fetch user's workspaces
            user_workspaces = get_user_workspaces(user_id)
            st.session_state.user_workspaces = user_workspaces

            if user_workspaces:
                # Set current workspace (e.g., first owned one, or just the first one)
                owned_workspaces = [ws for ws in user_workspaces if ws['owner_user_id'] == user_id]
                if owned_workspaces:
                    st.session_state.current_workspace_id = owned_workspaces[0]['id']
                    st.session_state.current_workspace_name = owned_workspaces[0]['name']
                else:
                    st.session_state.current_workspace_id = user_workspaces[0]['id']
                    st.session_state.current_workspace_name = user_workspaces[0]['name']
            else:
                # This shouldn't happen if add_user correctly creates a default workspace
                st.error("No accessible workspaces found for your account. Please contact support.")
                # Potentially try to create a default one here if truly missing
                # For now, block login if no workspace.
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


def render_signup_page():
    st.subheader("Create Account")
    with st.form("signup_form"):
        name = st.text_input("Full Name", key="signup_name")
        email = st.text_input("Email Address", key="signup_email")
        password = st.text_input("Password (min 8 chars, 1 upper, 1 num)", type="password", key="signup_pwd1")
        confirm_password = st.text_input("Confirm Password", type="password", key="signup_pwd2")
        signup_btn = st.form_submit_button("Sign Up")
    if signup_btn:
        if not all([name, email, password, confirm_password]): st.warning("All fields are required.")
        elif not is_valid_email(email): st.warning("Invalid email format.")
        elif password != confirm_password: st.error("Passwords do not match.")
        else:
            is_valid_pwd, pwd_error_msg = is_password_valid(password)
            if not is_valid_pwd: st.error(pwd_error_msg)
            else:
                user_created_successfully, new_user_id = add_user(email, password, name) # add_user now also creates workspace
                if user_created_successfully:
                    st.success("Account and default workspace created! You can now log in.")
                    st.session_state.auth_flow_page = "login"
                    # Check for pending invites for this email
                    if new_user_id:
                        conn = get_db_connection()
                        if conn:
                            try:
                                cursor = conn.cursor()
                                cursor.execute("""
                                    UPDATE workspace_members
                                    SET user_id = ?, status = 'pending' -- User still needs to accept via token if one was sent
                                    WHERE invite_email = ? AND user_id IS NULL AND status = 'pending'
                                """, (new_user_id, email.lower()))
                                if cursor.rowcount > 0:
                                    st.info("We found pending workspace invitations for your email. You can accept them after logging in or via the invitation email.")
                                conn.commit()
                            except sqlite3.Error as e_invite_update:
                                print(f"Error trying to link pending invites for new user {email}: {e_invite_update}")
                            finally:
                                conn.close()
                    st.rerun()
                # else: error message handled by add_user
    if st.button("Already have an account? Sign In", key="signup_to_login_link"):
        st.session_state.auth_flow_page = "login"; st.rerun()


def render_forgot_password_email_page(): # Unchanged
    st.subheader("Forgot Your Password?")
    st.caption("Enter your email to receive a password reset code.")
    with st.form("forgot_password_email_form"):
        email = st.text_input("Email Address", key="fp_email_input")
        send_code_btn = st.form_submit_button("Send Reset Code")
    if send_code_btn:
        if not is_valid_email(email): st.warning("Please enter a valid email.")
        else:
            user = find_user_by_email(email)
            if user:
                reset_code = str(random.randint(100000, 999999))
                if send_reset_email(email, reset_code):
                    st.session_state.reset_email = email
                    st.session_state.reset_expected_code = reset_code
                    st.session_state.auth_flow_page = "forgot_password_code"
                    st.toast(f"Reset code sent to {email}.", icon="✅"); st.rerun()
                else: st.error("Failed to send reset code. Try again.")
            else: st.error("Email address not found.")
    if st.button("Back to Login", key="fp_email_back_to_login"):
        st.session_state.auth_flow_page = "login"; st.rerun()

def render_forgot_password_code_page(): # Unchanged
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

def render_forgot_password_new_pwd_page(): # Unchanged
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
            is_valid, pwd_error_msg = is_password_valid(new_password)
            if not is_valid: st.error(pwd_error_msg)
            else:
                if update_user_password(email_to_reset, new_password):
                    st.success("Password updated! You can now log in.")
                    for key in ['reset_email', 'reset_expected_code']:
                        if key in st.session_state: del st.session_state[key]
                    st.session_state.auth_flow_page = "login"; st.rerun()
    if st.button("Back to Login", key="fp_new_pwd_back_to_login"):
        st.session_state.auth_flow_page = "login"; st.rerun()


def render_dashboard_page():
    user_id = st.session_state.logged_in_user['id']
    user_name = st.session_state.logged_in_user.get('name', 'User').split(" ")[0]
    workspace_id = st.session_state.current_workspace_id
    workspace_name = st.session_state.current_workspace_name

    st.header(f"👋 Welcome back, {user_name}!")
    st.subheader(f"📍 Current Workspace: {workspace_name}")
    st.markdown("Here's a quick overview of your retail operations for this workspace:")
    st.markdown("---")

    with st.container(border=True):
        st.subheader("📊 Sales Activity")
        sales_summary = get_sales_summary(workspace_id) # Pass workspace_id
        cols_sales = st.columns(3)
        cols_sales[0].metric(label="Sales Today", value=f"${sales_summary['today']:.2f}")
        cols_sales[1].metric(label="Sales this Week", value=f"${sales_summary['this_week']:.2f}")
        cols_sales[2].metric(label="Sales this Year", value=f"${sales_summary['this_year']:.2f}")
    st.markdown("---")

    row1_col1, row1_col2 = st.columns(2)
    with row1_col1:
        with st.container(border=True):
            st.subheader("📦 Stock Overview (Active Items)")
            inventory_items = get_inventory_items(workspace_id) # Pass workspace_id
            total_stock_units, total_stock_value, low_stock_items, out_of_stock_items = 0, 0.0, 0, 0
            if inventory_items:
                for item in inventory_items:
                    stock, price = item.get('stock_level', 0), item.get('retail_price', 0.0)
                    total_stock_units += stock; total_stock_value += stock * price
                    if stock == 0: out_of_stock_items += 1
                    elif 0 < stock <= 5: low_stock_items +=1
            stock_cols = st.columns(2)
            stock_cols[0].metric(label="Total Units in Stock", value=total_stock_units)
            stock_cols[1].metric(label="Total Stock Value", value=f"${total_stock_value:.2f}")
            stock_cols[0].metric(label="Low Stock Items (<5 units)", value=low_stock_items, delta=f"{low_stock_items} items", delta_color="inverse" if low_stock_items > 0 else "off")
            stock_cols[1].metric(label="Out of Stock Items", value=out_of_stock_items, delta=f"{out_of_stock_items} items", delta_color="inverse" if out_of_stock_items > 0 else "off")

    with row1_col2:
        with st.container(border=True):
            st.subheader("🌟 Top 5 Best Selling Items")
            best_sellers = get_best_selling_items(workspace_id, limit=5) # Pass workspace_id
            if best_sellers:
                for i, item in enumerate(best_sellers):
                    col1, col2 = st.columns([3,1])
                    with col1:
                        item_name = item.get('name', 'N/A'); item_price = item.get('retail_price', 0.0)
                        is_active_status = "(Active)" if item.get('is_active', 0) else "(Inactive)"
                        st.markdown(f"**{i+1}. {item_name}** (`${item_price:.2f}`) {is_active_status if not item.get('is_active') else ''}")
                        if item.get('image_path') and os.path.exists(item['image_path']):
                            try: st.image(item['image_path'], width=50)
                            except Exception as e: print(f"Could not load image {item['image_path']}: {e}"); st.caption("No image")
                        else: st.caption("No image")
                    with col2: st.metric(label="Sold", value=item.get('total_quantity_sold', 0))
                    if i < len(best_sellers) -1: st.markdown("""<hr style="height:1px;border:none;color:#333;background-color:#333;" /> """, unsafe_allow_html=True)
            else: st.info("No sales data yet for this workspace.")
    st.markdown("---")
    st.caption("Navigate using the sidebar to manage inventory, process sales, or view detailed reports for the current workspace.")


def render_inventory_page():
    user_id = st.session_state.logged_in_user['id']
    workspace_id = st.session_state.current_workspace_id
    workspace_name = st.session_state.current_workspace_name
    st.header(f"Inventory Management: {workspace_name}")

    cols_filter = st.columns([2,1,1])
    with cols_filter[0]: search_term = st.text_input("Search by Product Name", key="inventory_search_st")
    with cols_filter[1]: price_filter = st.selectbox("Filter by Price", ["Any", "< $30", "$30-$100", "> $100"], key="inventory_price_filter_st")
    with cols_filter[2]: stock_filter = st.selectbox("Filter by Stock", ["Any", "In Stock", "Low Stock", "Out of Stock"], key="inventory_stock_filter_st")

    if st.button("➕ Add New Item", key="toggle_add_item_form_st"):
        st.session_state.show_add_item_form = not st.session_state.get("show_add_item_form", False)
        # Clear other states
        if "editing_item_id" in st.session_state: del st.session_state.editing_item_id
        st.session_state.show_edit_item_form = False
        if "viewing_image_path" in st.session_state: del st.session_state.viewing_image_path


    if st.session_state.get("show_add_item_form"):
        with st.expander("Add New Item Form", expanded=True):
            with st.form("add_item_form_st", clear_on_submit=True):
                name = st.text_input("Item Name*")
                retail_price = st.number_input("Retail Price ($)*", min_value=0.01, format="%.2f", step=0.01)
                stock_level = st.number_input("Stock Level*", min_value=0, step=1)
                uploaded_image = st.file_uploader("Item Image", type=["png", "jpg", "jpeg", "gif"], key="add_item_uploader")
                submitted_add = st.form_submit_button("Add Item")
                if submitted_add:
                    if not name or retail_price is None or stock_level is None: st.warning("Name, Price, Stock are required.")
                    else:
                        img_path = handle_streamlit_image_upload(uploaded_image, workspace_id) if uploaded_image else None
                        if add_inventory_item(workspace_id, name, retail_price, stock_level, img_path, added_by_user_id=user_id):
                            st.success(f"'{name}' added to {workspace_name}!"); st.session_state.show_add_item_form = False; st.rerun()

    inventory_data = get_inventory_items(workspace_id, search_term, price_filter, stock_filter)
    if inventory_data:
        df = pd.DataFrame(inventory_data)
        df_display = df[['id', 'name', 'retail_price', 'stock_level']].copy()
        df_display.rename(columns={'id':'ID','name': 'Product Name', 'retail_price': 'Price', 'stock_level': 'Stock'}, inplace=True)
        df_display['Price'] = df_display['Price'].apply(lambda x: f"${x:.2f}")
        st.dataframe(df_display, use_container_width=True, hide_index=True, key="inventory_df")

        st.subheader("Actions on Active Items")
        item_names_for_action = {f"{item['name']} (ID: {item['id']})": item['id'] for item in inventory_data if item['is_active']}
        if item_names_for_action:
            selected_display_name_for_action = st.selectbox("Select Item for Action", options=list(item_names_for_action.keys()), key="inv_action_select", index=None, placeholder="Choose an item...")
            if selected_display_name_for_action:
                selected_item_id_for_action = item_names_for_action.get(selected_display_name_for_action)
                col_act1, col_act2, col_act3 = st.columns(3)
                with col_act1:
                    if st.button("✏️ Edit", key=f"edit_{selected_item_id_for_action}", use_container_width=True):
                        st.session_state.editing_item_id = selected_item_id_for_action
                        st.session_state.show_edit_item_form = True; st.session_state.show_add_item_form = False
                        if "viewing_image_path" in st.session_state: del st.session_state.viewing_image_path
                        st.rerun()
                with col_act2:
                    if st.button("🗑️ Deactivate", key=f"delete_{selected_item_id_for_action}", type="primary", use_container_width=True):
                        if "viewing_image_path" in st.session_state: del st.session_state.viewing_image_path
                        if delete_inventory_item(selected_item_id_for_action, workspace_id, deleted_by_user_id=user_id):
                            st.toast(f"Item '{selected_display_name_for_action}' deactivated."); st.rerun()
                with col_act3:
                    if st.button("🖼️ View Image", key=f"view_img_{selected_item_id_for_action}", use_container_width=True):
                        item_to_view = get_item_by_id(selected_item_id_for_action, workspace_id)
                        if item_to_view and item_to_view.get('image_path') and os.path.exists(item_to_view['image_path']):
                            st.session_state.viewing_image_path = item_to_view['image_path']
                            st.session_state.viewing_image_name = item_to_view['name']
                        elif item_to_view: st.info(f"No image for '{item_to_view['name']}'.")
                        else: st.warning("Item not found.")
                        if not (item_to_view and item_to_view.get('image_path') and os.path.exists(item_to_view['image_path'])):
                            if "viewing_image_path" in st.session_state: del st.session_state.viewing_image_path
                        st.rerun()
        else:
             st.info(f"No active items match your filters in '{workspace_name}'.")
    else:
        st.info(f"No inventory items found in '{workspace_name}'. Add some items to get started!")
        if "viewing_image_path" in st.session_state: del st.session_state.viewing_image_path

    if st.session_state.get("show_edit_item_form") and st.session_state.get("editing_item_id"):
        if "viewing_image_path" in st.session_state: del st.session_state.viewing_image_path
        item_to_edit = get_item_by_id(st.session_state.editing_item_id, workspace_id)
        if item_to_edit:
            with st.expander(f"Edit Item: {item_to_edit['name']} (ID: {item_to_edit['id']})", expanded=True):
                with st.form(f"edit_item_form_{item_to_edit['id']}", clear_on_submit=False):
                    edit_name = st.text_input("Name*", value=item_to_edit['name'], key=f"edit_name_{item_to_edit['id']}")
                    edit_price = st.number_input("Price ($)*", value=float(item_to_edit['retail_price']), min_value=0.01, format="%.2f", step=0.01, key=f"edit_price_{item_to_edit['id']}")
                    edit_stock = st.number_input("Stock*", value=int(item_to_edit['stock_level']), min_value=0, step=1, key=f"edit_stock_{item_to_edit['id']}")
                    st.caption("Current Image:")
                    if item_to_edit.get('image_path') and os.path.exists(item_to_edit['image_path']): st.image(item_to_edit['image_path'], width=100)
                    else: st.text("None")
                    edit_img_upload = st.file_uploader("Change Image (Optional)", type=["png","jpg","jpeg"], key=f"edit_uploader_{item_to_edit['id']}")
                    save_edit_btn, cancel_edit_btn = st.columns(2)
                    with save_edit_btn: submitted_save = st.form_submit_button("Save Changes", use_container_width=True)
                    with cancel_edit_btn: submitted_cancel = st.form_submit_button("Cancel", use_container_width=True)

                    if submitted_save:
                        if not edit_name: st.warning("Name is required.")
                        else:
                            new_img_path = item_to_edit.get('image_path')
                            if edit_img_upload: new_img_path = handle_streamlit_image_upload(edit_img_upload, workspace_id)
                            if update_inventory_item(item_to_edit['id'], workspace_id, edit_name, edit_price, edit_stock, new_img_path, is_active=True, updated_by_user_id=user_id):
                                st.success(f"'{edit_name}' updated."); st.session_state.show_edit_item_form = False;
                                if "editing_item_id" in st.session_state: del st.session_state.editing_item_id;
                                st.rerun()
                    if submitted_cancel:
                        st.session_state.show_edit_item_form = False;
                        if "editing_item_id" in st.session_state: del st.session_state.editing_item_id;
                        st.rerun()
        else: # Item not found (maybe deleted/deactivated by another user in parallel)
            st.session_state.show_edit_item_form = False
            if "editing_item_id" in st.session_state: del st.session_state.editing_item_id
            st.warning("Item not found for editing. It may have been removed or deactivated.")
            st.rerun()

    if "viewing_image_path" in st.session_state and st.session_state.viewing_image_path and \
       not st.session_state.get("show_edit_item_form", False) and not st.session_state.get("show_add_item_form", False):
        @st.dialog(f"Image: {st.session_state.get('viewing_image_name', 'Item Image')}")
        def view_image_in_dialog():
            try: st.image(st.session_state.viewing_image_path)
            except Exception as e: st.error(f"Could not display image: {e}. Path: {st.session_state.viewing_image_path}")
            if st.button("Close", key="close_image_dialog_button"):
                if "viewing_image_path" in st.session_state: del st.session_state.viewing_image_path
                if "viewing_image_name" in st.session_state: del st.session_state.viewing_image_name
                st.rerun()
        view_image_in_dialog()


def render_sales_page():
    user_id = st.session_state.logged_in_user['id']
    workspace_id = st.session_state.current_workspace_id
    workspace_name = st.session_state.current_workspace_name
    st.header(f"Process New Sale for: {workspace_name}")
    col_left, col_right = st.columns([2,3])

    with col_left:
        st.subheader("Select Product")
        inventory_items = get_inventory_items(workspace_id, stock_filter="In Stock")
        product_options = {
            f"{item['name']} (Stock: {item['stock_level']}, Price: ${item['retail_price']:.2f})": item
            for item in inventory_items
        }
        if not product_options: st.warning(f"No products in stock in '{workspace_name}'."); return

        selected_product_key = st.selectbox("Find Product", options=list(product_options.keys()), key="sales_prod_select", index=None, placeholder="Choose a product...")
        selected_product_data = product_options.get(selected_product_key)

        if selected_product_data:
            st.markdown(f"**Product:** {selected_product_data['name']}")
            st.markdown(f"**Available Stock:** {selected_product_data['stock_level']}")
            st.markdown(f"**Price/Unit:** ${selected_product_data['retail_price']:.2f}")
            max_qty = selected_product_data['stock_level'] if selected_product_data['stock_level'] > 0 else 1
            quantity_to_add = st.number_input("Quantity:", min_value=1, value=1, step=1, key="sales_qty_add", max_value=max_qty)

            if st.button("Add to Order", key="sales_add_btn", type="primary", use_container_width=True):
                if quantity_to_add > selected_product_data['stock_level']:
                    st.error(f"Not enough stock. Only {selected_product_data['stock_level']} available.")
                else:
                    existing_item_idx = next((i for i, item in enumerate(st.session_state.cart) if item['id'] == selected_product_data['id']), -1)
                    current_item_price = selected_product_data['retail_price']
                    if existing_item_idx != -1:
                        st.session_state.cart[existing_item_idx]['quantity'] += quantity_to_add
                        st.session_state.cart[existing_item_idx]['subtotal'] = st.session_state.cart[existing_item_idx]['quantity'] * current_item_price
                    else:
                        st.session_state.cart.append({
                            'id': selected_product_data['id'], 'name': selected_product_data['name'],
                            'quantity': quantity_to_add, 'price_unit': current_item_price,
                            'subtotal': quantity_to_add * current_item_price
                        })
                    st.toast(f"Added {selected_product_data['name']}."); st.rerun()
        else: st.caption("Select a product to see details.")

    with col_right:
        st.subheader("Current Order")
        if not st.session_state.cart: st.info("Order is empty.")
        else:
            cart_data_for_df = []
            total_order_price = 0
            for item in st.session_state.cart:
                cart_data_for_df.append({
                    "Product": item['name'], "Qty": item['quantity'],
                    "Price/Unit": f"${item['price_unit']:.2f}", "Subtotal": f"${item['subtotal']:.2f}"
                })
                total_order_price += item['subtotal']
            cart_df = pd.DataFrame(cart_data_for_df)
            st.dataframe(cart_df, hide_index=True, use_container_width=True)
            st.markdown(f"### Total Price: `${total_order_price:.2f}`")
            col_actions1, col_actions2 = st.columns(2)
            with col_actions1:
                if st.button("Clear Order", key="sales_clear_btn", use_container_width=True):
                    st.session_state.cart = []; st.toast("Order cleared."); st.rerun()
            with col_actions2:
                if st.button("Finalise Sale", key="sales_final_btn", type="primary", use_container_width=True):
                    if record_sale(workspace_id, user_id, st.session_state.cart, total_order_price):
                        st.success("Sale Finalised!"); st.balloons(); st.session_state.cart = []; st.rerun()


def render_reports_page():
    workspace_id = st.session_state.current_workspace_id
    workspace_name = st.session_state.current_workspace_name
    st.header(f"Sales Reports for: {workspace_name}")
    time_period = st.selectbox("Select Time Period:", ("Day", "Week", "Year"), key="report_time_period_selector", index=0)
    report_data_df = get_sales_data_for_graph(workspace_id, time_period)

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


def render_workspace_management_page():
    user_id = st.session_state.logged_in_user['id']
    workspace_id = st.session_state.current_workspace_id
    workspace_name = st.session_state.current_workspace_name
    current_user_name = st.session_state.logged_in_user.get('name', "User")

    st.header(f"Manage Workspace: {workspace_name}")

    workspace_details = find_workspace_by_id(workspace_id)
    if not workspace_details:
        st.error("Could not load workspace details. It might have been deleted or an error occurred.")
        return
    is_owner = (workspace_details['owner_user_id'] == user_id)

    if is_owner:
        st.subheader("Invite New Member")
        with st.form("invite_member_form"):
            invitee_email = st.text_input("Email address of user to invite")
            # role_options = ["member", "admin"] # For future role-based access
            # invite_role = st.selectbox("Assign Role", role_options, index=0)
            submit_invite = st.form_submit_button("Send Invitation")

            if submit_invite:
                if not is_valid_email(invitee_email):
                    st.warning("Please enter a valid email address.")
                elif invitee_email.lower() == st.session_state.logged_in_user['email'].lower():
                    st.warning("You cannot invite yourself.")
                else:
                    # Check if user already a member or has pending invite
                    members = get_workspace_members_details(workspace_id)
                    existing_member = next((m for m in members if m['email'] and m['email'].lower() == invitee_email.lower()), None)
                    if existing_member:
                        st.warning(f"{invitee_email} is already a member or has a pending invitation ({existing_member['status']}).")
                    else:
                        invite_token = str(uuid.uuid4()) # Generate a unique token
                        app_base_url = st.secrets.get("APP_BASE_URL", "http://localhost:8501") # Define in secrets for deployment
                        # The page to handle the token could be the login page with a query param, or a dedicated page
                        invite_link = f"{app_base_url}?page=accept_invite&token={invite_token}"

                        if add_workspace_member(workspace_id, user_id=None, invited_by_user_id=user_id,
                                                invite_email=invitee_email.lower(), invite_token=invite_token, status='pending'):
                            if send_workspace_invite_email(invitee_email, current_user_name, workspace_name, invite_link):
                                st.success(f"Invitation sent to {invitee_email}!")
                            else:
                                st.error(f"Invitation record created, but failed to send email to {invitee_email}. They can accept if they have the token or if they sign up with that email.")
                        # else: error handled by add_workspace_member

    st.subheader("Workspace Members & Invitations")
    members = get_workspace_members_details(workspace_id)
    if members:
        member_data = []
        for member in members:
            status_icon = "✅ Accepted" if member['status'] == 'accepted' else ("⏳ Pending" if member['status'] == 'pending' else "❓ Unknown")
            role_display = f" ({member['role'].capitalize()})" if member['role'] else ""
            member_data.append({
                "Name": member.get('name', '- Invited Email -'),
                "Email": member['email'],
                "Role": member['role'].capitalize() if member.get('role') else 'N/A',
                "Status": status_icon,
                "Joined/Invited": member.get('joined_at', member.get('invite_token', 'N/A') if member['status'] == 'pending' else 'N/A') # Display token for pending if useful
            })
        st.dataframe(pd.DataFrame(member_data), hide_index=True, use_container_width=True)
        # Future: Add options to remove members or resend invites if owner
    else:
        st.info("No members or pending invitations for this workspace yet.")


def render_accept_invite_page():
    st.subheader("Accept Workspace Invitation")
    token = st.query_params.get("token")

    if not st.session_state.logged_in_user:
        st.warning("You need to be logged in to accept an invitation.")
        st.session_state.pending_invite_token_after_login = token # Store token
        st.session_state.auth_flow_page = "login" # Redirect to login
        st.info("Please log in or sign up. After logging in, the invitation will be processed if it's for your account.")
        # Add a button to go to login, or it will happen on rerun if main() logic handles it
        if st.button("Go to Login"):
            st.rerun()
        return

    if token:
        user_id = st.session_state.logged_in_user['id']
        st.write(f"Processing invitation with token: `{token}` for user {st.session_state.logged_in_user['email']}...")
        success, message = process_workspace_invite(token, user_id)
        if success:
            st.success(message)
            # Refresh user's workspaces
            st.session_state.user_workspaces = get_user_workspaces(user_id)
            # Optionally, switch to the newly joined workspace or prompt
            st.query_params.clear() # Clear token from URL
            if st.button("Go to Dashboard"):
                st.session_state.current_page = "Dashboard"
                st.rerun()
        else:
            st.error(message)
            st.query_params.clear()
    else:
        st.error("No invitation token provided.")
        # Check if there was a token stored before login
        pending_token = st.session_state.pop("pending_invite_token_after_login", None)
        if pending_token:
            st.info("Attempting to process previously stored invitation...")
            st.query_params["token"] = pending_token # Put it back to be processed on next rerun
            st.rerun()

    if st.button("Back to Dashboard"):
        st.session_state.current_page = "Dashboard"
        st.query_params.clear() # Clear any params before going back
        st.rerun()

# =====================================================================
# --- MAIN APPLICATION LOGIC ---
# =====================================================================
def main():
    st.set_page_config(page_title="Retail Pro+", layout="wide", initial_sidebar_state="expanded")

    # Initialize session state variables if they don't exist
    if "logged_in_user" not in st.session_state: st.session_state.logged_in_user = None
    if "current_page" not in st.session_state: st.session_state.current_page = "Login" # Default page
    if "auth_flow_page" not in st.session_state: st.session_state.auth_flow_page = "login"
    if "cart" not in st.session_state: st.session_state.cart = []
    if "show_add_item_form" not in st.session_state: st.session_state.show_add_item_form = False
    if "show_edit_item_form" not in st.session_state: st.session_state.show_edit_item_form = False
    if "editing_item_id" not in st.session_state: st.session_state.editing_item_id = None
    if "viewing_image_path" not in st.session_state: st.session_state.viewing_image_path = None
    if "viewing_image_name" not in st.session_state: st.session_state.viewing_image_name = None
    if "user_workspaces" not in st.session_state: st.session_state.user_workspaces = []
    if "current_workspace_id" not in st.session_state: st.session_state.current_workspace_id = None
    if "current_workspace_name" not in st.session_state: st.session_state.current_workspace_name = "N/A"


    # Handle invite acceptance if token is in query params
    # And user is logged in. If not logged in, render_accept_invite_page will redirect to login.
    if st.query_params.get("page") == "accept_invite" and st.session_state.logged_in_user:
        st.session_state.current_page = "Accept Invite" # Force page change
        # The render_accept_invite_page will handle the rest
    elif st.query_params.get("token") and "pending_invite_token_after_login" not in st.session_state and st.session_state.logged_in_user:
        # If token is present and user is logged in, but not on accept_invite page yet,
        # assume it's an invite to be processed.
        st.session_state.current_page = "Accept Invite"
        st.query_params["page"] = "accept_invite" # ensure page param is set for next logic block
        # st.rerun() # This might cause issues if called too early. Let page rendering handle it.


    if not st.session_state.logged_in_user:
        try:
            logo_path = os.path.join("images", "logo.jpg") # Ensure you have this path
            if os.path.exists(logo_path): st.image(logo_path, width=150)
            else: print(f"Login page logo not found at {logo_path}")
        except Exception as e: print(f"Error loading logo for login page: {e}")

        st.title("Retail Pro+ Portal")
        auth_page = st.session_state.auth_flow_page

        # If there's a pending invite token from before login, try to process it now if on accept_invite path
        if auth_page == "login" and st.session_state.get("pending_invite_token_after_login"):
            # This logic might be complex; ideally, after login, redirect to accept if token exists.
            # For now, render_accept_invite_page handles prompting login.
            pass


        if st.session_state.current_page == "Accept Invite" and st.query_params.get("token"):
            # This case is if user was sent to login, then logged in, and now needs to accept
             render_accept_invite_page()
        elif auth_page == "login": render_login_page()
        elif auth_page == "enter_2fa": render_2fa_page()
        elif auth_page == "signup": render_signup_page()
        elif auth_page == "forgot_password_email": render_forgot_password_email_page()
        elif auth_page == "forgot_password_code": render_forgot_password_code_page()
        elif auth_page == "forgot_password_new_pwd": render_forgot_password_new_pwd_page()
        else: # Default to login if auth_flow_page is weird
            render_login_page()
        return

    # --- User is Logged In ---
    with st.sidebar:
        try:
            logo_path_sidebar = os.path.join("images", "logo.jpg")
            if os.path.exists(logo_path_sidebar):
                st.image(logo_path_sidebar, width=70)
                st.markdown(f"<h2 style='text-align: left; margin-top: -5px; margin-bottom: 15px;'>Retail Pro+</h2>", unsafe_allow_html=True)
            else: st.sidebar.markdown("## Retail Pro+")
        except Exception as e_sidebar_logo: st.sidebar.markdown("## Retail Pro+")

        user_name = st.session_state.logged_in_user.get('name', 'User').split(" ")[0]
        st.markdown(f"<h4 style='margin-bottom: 5px;'>Welcome, {user_name}!</h4>", unsafe_allow_html=True)

        # Workspace Selector
        user_workspaces = st.session_state.user_workspaces
        if user_workspaces:
            workspace_options = {ws['id']: ws['name'] for ws in user_workspaces}
            if st.session_state.current_workspace_id not in workspace_options: # If current is invalid, pick first
                st.session_state.current_workspace_id = user_workspaces[0]['id']
                st.session_state.current_workspace_name = user_workspaces[0]['name']


            selected_ws_id = st.selectbox(
                "Active Workspace:",
                options=list(workspace_options.keys()),
                format_func=lambda ws_id: workspace_options[ws_id],
                index = list(workspace_options.keys()).index(st.session_state.current_workspace_id) if st.session_state.current_workspace_id in workspace_options else 0,
                key="workspace_selector"
            )
            if selected_ws_id != st.session_state.current_workspace_id:
                st.session_state.current_workspace_id = selected_ws_id
                st.session_state.current_workspace_name = workspace_options[selected_ws_id]
                # Reset cart and other page-specific states when workspace changes
                st.session_state.cart = []
                st.session_state.show_add_item_form = False
                st.session_state.show_edit_item_form = False
                if "editing_item_id" in st.session_state: del st.session_state.editing_item_id
                st.rerun()
        else:
            st.error("No workspaces available. This should not happen.")
            # Potentially logout or attempt to create a workspace

        st.markdown("---")

        PAGES_CONFIG = {
            "Dashboard": {"icon": "📊", "func": render_dashboard_page},
            "Inventory": {"icon": "📦", "func": render_inventory_page},
            "Sales":     {"icon": "🛒", "func": render_sales_page},
            "Reports":   {"icon": "📈", "func": render_reports_page},
            "Workspace": {"icon": "👥", "func": render_workspace_management_page}, # New Page
        }
        # Special page for accepting invites, not in main nav
        if st.session_state.current_page == "Accept Invite":
             PAGES_CONFIG["Accept Invite"] = {"icon": "📧", "func": render_accept_invite_page}


        for page_name, page_info in PAGES_CONFIG.items():
            if page_name == "Accept Invite" and st.session_state.current_page != "Accept Invite":
                continue # Don't show accept invite in sidebar unless actively on it

            is_active = (st.session_state.current_page == page_name)
            button_type = "primary" if is_active else "secondary"
            if st.button(f"{page_info['icon']} {page_name}", key=f"nav_btn_{page_name}", type=button_type, use_container_width=True):
                if st.session_state.current_page != page_name:
                    st.session_state.current_page = page_name
                    # Reset states when changing pages
                    if page_name != "Inventory":
                        st.session_state.show_add_item_form = False
                        st.session_state.show_edit_item_form = False
                        if "editing_item_id" in st.session_state: del st.session_state.editing_item_id
                        if "viewing_image_path" in st.session_state: del st.session_state.viewing_image_path
                    if page_name != "Sales":
                        st.session_state.cart = []
                    if page_name == "Accept Invite": # If navigating to accept invite manually (less likely)
                        if not st.query_params.get("token"):
                            st.warning("No invite token specified to accept.")
                    else: # If navigating away from accept invite, clear its params
                        if st.query_params.get("page") == "accept_invite" or st.query_params.get("token"):
                            st.query_params.clear()
                    st.rerun()

        st.markdown("---")
        if st.button("🚪 Logout", key="nav_btn_logout", use_container_width=True, type="secondary"):
            keys_to_clear = list(st.session_state.keys())
            for key in keys_to_clear:
                del st.session_state[key]
            # Re-initialize core states for a clean logout
            st.session_state.logged_in_user = None
            st.session_state.current_page = "Login"
            st.session_state.auth_flow_page = "login"
            st.session_state.cart = []
            st.session_state.user_workspaces = []
            st.session_state.current_workspace_id = None
            st.query_params.clear() # Clear any query parameters on logout
            st.toast("You have been logged out.")
            st.rerun()

    # Render the current page for logged-in user
    if st.session_state.current_page in PAGES_CONFIG:
        page_to_render_func = PAGES_CONFIG[st.session_state.current_page]["func"]
        if page_to_render_func:
            page_to_render_func()
    elif st.session_state.current_page == "Login": # Should be caught by not logged_in_user block
        render_login_page()
    else: # Fallback if current_page is something unexpected for a logged-in user
        st.warning(f"Unknown page state: {st.session_state.current_page}. Redirecting to Dashboard.")
        st.session_state.current_page = "Dashboard"
        st.rerun()


if __name__ == "__main__":
    for img_dir in ["images", INVENTORY_IMAGE_DIR]:
        if not os.path.exists(img_dir):
            try: os.makedirs(img_dir); print(f"Created '{img_dir}' directory.")
            except OSError as e: print(f"Error creating '{img_dir}' directory: {e}")
    init_db()
    main()