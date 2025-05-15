import tkinter as tk
from tkinter import PhotoImage, font as tkFont, messagebox
from PIL import Image, ImageTk
import os
import random # Needed for generating the reset code
import re # Needed for basic email validation

# --- Constants for Styling (reuse from previous code) ---
BG_COLOR_MAIN = "#00A1B1"
BG_COLOR_FORM = "#FFFFFF" # White for the form area
FG_COLOR_TEXT_DARK = "#000000" # Black
FG_COLOR_TEXT_LIGHT = "#555555" # Grey
FG_COLOR_LINK = "#007bff" # Blueish link color
FG_COLOR_ERROR = "#dc3545" # Red for errors
BTN_COLOR_ACTION = "#008C9E" # Teal for primary buttons
BTN_FG_COLOR_ACTION = "#FFFFFF" # White text on button
FONT_FAMILY = "Helvetica" # Or "Arial" or system default

# --- --- SIMULATED DATABASE --- ---
# In a real application, replace this with database queries
DUMMY_DATABASE = {
    "test@example.com": {"password_hash": "some_hashed_password1", "name": "Test User"},
    "user@domain.com": {"password_hash": "some_hashed_password2", "name": "Another User"},
    "retailpro@test.co": {"password_hash": "some_hashed_password3", "name": "Retail Pro Admin"}
}
# --- --- --- --- --- --- --- --- ---

# Store the generated code and email temporarily during the reset process
# In a real app, you might use a temporary database table or cache with expiry
reset_process_data = {
    "email": None,
    "code": None
}

# --- Helper Functions ---

def is_valid_email(email):
    """Basic email format check using regex."""
    # This is a simple regex, more complex ones exist
    pattern = r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
    return re.match(pattern, email) is not None

# --- Forgot Password Window Logic ---

def create_forgot_password_window(parent_window):
    """Creates and manages the multi-step forgot password window."""

    parent_window.withdraw() # Hide the login window

    fp_window = tk.Toplevel(parent_window)
    fp_window.title("Reset Password - Retail Pro+")
    fp_window.geometry("450x400") # Adjust size as needed
    fp_window.configure(bg=BG_COLOR_FORM)
    fp_window.resizable(False, False)

    # --- Widgets ---
    # Use StringVar to easily update label text
    title_var = tk.StringVar(value="Forgot Your Password?")
    instruction_var = tk.StringVar(value="Enter your email to receive a reset code.")
    error_var = tk.StringVar(value="")

    # --- Frames for layout ---
    main_frame = tk.Frame(fp_window, bg=BG_COLOR_FORM, padx=30, pady=20)
    main_frame.pack(fill=tk.BOTH, expand=True)

    # --- Shared Widgets (Visible throughout) ---
    title_label = tk.Label(main_frame, textvariable=title_var, font=(FONT_FAMILY, 18, "bold"), bg=BG_COLOR_FORM, fg=FG_COLOR_TEXT_DARK)
    title_label.pack(pady=(0, 10))

    instruction_label = tk.Label(main_frame, textvariable=instruction_var, font=(FONT_FAMILY, 10), bg=BG_COLOR_FORM, fg=FG_COLOR_TEXT_LIGHT, wraplength=380)
    instruction_label.pack(pady=(0, 20))

    error_label = tk.Label(main_frame, textvariable=error_var, font=(FONT_FAMILY, 9), bg=BG_COLOR_FORM, fg=FG_COLOR_ERROR)
    error_label.pack(pady=(0, 10)) # Keep space for errors

    # --- Step-specific Frames (we'll pack/unpack these) ---
    email_frame = tk.Frame(main_frame, bg=BG_COLOR_FORM)
    code_frame = tk.Frame(main_frame, bg=BG_COLOR_FORM)
    password_frame = tk.Frame(main_frame, bg=BG_COLOR_FORM)

    # --- Widgets for Step 1: Email Entry ---
    email_label = tk.Label(email_frame, text="Email Address", font=(FONT_FAMILY, 10), bg=BG_COLOR_FORM, fg=FG_COLOR_TEXT_DARK)
    email_label.pack(anchor='w')
    email_entry = tk.Entry(email_frame, font=(FONT_FAMILY, 12), width=35, bd=1, relief=tk.SOLID)
    email_entry.pack(fill=tk.X, pady=(5, 15))
    send_code_button = tk.Button(email_frame, text="Send Reset Code", font=(FONT_FAMILY, 11, "bold"), bg=BTN_COLOR_ACTION, fg=BTN_FG_COLOR_ACTION, relief="flat", padx=15, pady=5, command=lambda: validate_email_and_send_code(email_entry.get()))
    send_code_button.pack(pady=10)

    # --- Widgets for Step 2: Code Entry ---
    code_label = tk.Label(code_frame, text="6-Digit Code", font=(FONT_FAMILY, 10), bg=BG_COLOR_FORM, fg=FG_COLOR_TEXT_DARK)
    code_label.pack(anchor='w')
    code_entry = tk.Entry(code_frame, font=(FONT_FAMILY, 12), width=15, bd=1, relief=tk.SOLID, justify='center')
    code_entry.pack(pady=(5, 15))
    verify_code_button = tk.Button(code_frame, text="Verify Code", font=(FONT_FAMILY, 11, "bold"), bg=BTN_COLOR_ACTION, fg=BTN_FG_COLOR_ACTION, relief="flat", padx=15, pady=5, command=lambda: verify_code(code_entry.get()))
    verify_code_button.pack(pady=10)

    # --- Widgets for Step 3: New Password Entry ---
    new_pwd_label = tk.Label(password_frame, text="New Password", font=(FONT_FAMILY, 10), bg=BG_COLOR_FORM, fg=FG_COLOR_TEXT_DARK)
    new_pwd_label.pack(anchor='w')
    new_pwd_entry = tk.Entry(password_frame, font=(FONT_FAMILY, 12), show="*", width=35, bd=1, relief=tk.SOLID)
    new_pwd_entry.pack(fill=tk.X, pady=(5, 10))

    confirm_pwd_label = tk.Label(password_frame, text="Confirm New Password", font=(FONT_FAMILY, 10), bg=BG_COLOR_FORM, fg=FG_COLOR_TEXT_DARK)
    confirm_pwd_label.pack(anchor='w')
    confirm_pwd_entry = tk.Entry(password_frame, font=(FONT_FAMILY, 12), show="*", width=35, bd=1, relief=tk.SOLID)
    confirm_pwd_entry.pack(fill=tk.X, pady=(5, 15))

    reset_pwd_button = tk.Button(password_frame, text="Reset Password", font=(FONT_FAMILY, 11, "bold"), bg=BTN_COLOR_ACTION, fg=BTN_FG_COLOR_ACTION, relief="flat", padx=15, pady=5, command=lambda: update_password(new_pwd_entry.get(), confirm_pwd_entry.get()))
    reset_pwd_button.pack(pady=10)


    # --- Functions to control the flow ---
    def show_frame(frame_to_show):
        """Hides all step frames and shows the specified one."""
        email_frame.pack_forget()
        code_frame.pack_forget()
        password_frame.pack_forget()
        frame_to_show.pack(fill=tk.X) # Pack the desired frame

    def validate_email_and_send_code(email):
        """Step 1: Validate email and 'send' code."""
        error_var.set("") # Clear previous errors
        if not email or not is_valid_email(email):
            error_var.set("Please enter a valid email address.")
            return

        # --- --- DATABASE CHECK SIMULATION --- ---
        if email in DUMMY_DATABASE:
            # Email exists
            generated_code = str(random.randint(100000, 999999))
            reset_process_data["email"] = email
            reset_process_data["code"] = generated_code

             # --- --- EMAIL SENDING SIMULATION --- ---
            print("-" * 40)
            print(f"SIMULATING EMAIL SEND TO: {email}")
            print(f"RESET CODE: {generated_code}")
            print("In a real app, this code would be emailed.")
            print("-" * 40)
            messagebox.showinfo("Code Sent (Simulation)", f"A 6-digit code has been 'sent' to {email}.\n(Check the console for the code in this demo).", parent=fp_window)
             # --- --- --- --- --- --- --- --- --- --- ---

            # Transition to Step 2
            title_var.set("Enter Verification Code")
            instruction_var.set(f"Enter the 6-digit code sent to {email}.")
            show_frame(code_frame)
        else:
             # --- --- DATABASE CHECK SIMULATION --- ---
            error_var.set("Email address not found in our records.")
            print(f"SIMULATION: Email '{email}' not found in DUMMY_DATABASE.")
             # --- --- --- --- --- --- --- --- --- --- ---

    def verify_code(entered_code):
        """Step 2: Verify the entered code."""
        error_var.set("")
        if not entered_code or not entered_code.isdigit() or len(entered_code) != 6:
            error_var.set("Please enter the 6-digit code.")
            return

        if entered_code == reset_process_data["code"]:
            # Code is correct, transition to Step 3
            title_var.set("Set Your New Password")
            instruction_var.set("Enter and confirm your new password below.")
            show_frame(password_frame)
        else:
            error_var.set("Invalid verification code. Please try again.")

    def update_password(new_pwd, confirm_pwd):
        """Step 3: Validate and 'update' the password."""
        error_var.set("")
        if not new_pwd or not confirm_pwd:
            error_var.set("Please enter and confirm your new password.")
            return
        if new_pwd != confirm_pwd:
            error_var.set("Passwords do not match.")
            return
        if len(new_pwd) < 8: # Example: Basic length check
             error_var.set("Password must be at least 8 characters long.")
             return

        # --- --- PASSWORD UPDATE SIMULATION --- ---
        email_to_update = reset_process_data["email"]
        print("-" * 40)
        print(f"SIMULATION: Password Update")
        print(f"Email: {email_to_update}")
        print(f"New Password: {new_pwd} (Should be hashed before saving!)")
        # In a real app:
        # 1. Hash the new_pwd securely (e.g., using bcrypt.hashpw)
        # 2. Execute a database UPDATE statement:
        #    UPDATE users SET password_hash = 'hashed_new_password' WHERE email = 'email_to_update';
        print("Password update simulated successfully.")
        print("-" * 40)
        # Optionally update the dummy database (not recommended for real apps)
        # if email_to_update in DUMMY_DATABASE:
        #    DUMMY_DATABASE[email_to_update]["password_hash"] = f"hashed_{new_pwd}" # Simulate hashing
        # --- --- --- --- --- --- --- --- --- --- ---

        messagebox.showinfo("Password Reset Successful", "Your password has been updated successfully.", parent=fp_window)
        fp_window.destroy() # Close the reset window
        parent_window.deiconify() # Show the login window again

    # --- Make window close properly ---
    def on_fp_close():
        # Clear temporary data if window is closed prematurely
        reset_process_data["email"] = None
        reset_process_data["code"] = None
        fp_window.destroy()
        parent_window.deiconify() # Show login window again

    fp_window.protocol("WM_DELETE_WINDOW", on_fp_close)

    # --- Initial State ---
    show_frame(email_frame) # Start with the email entry frame


# --- --- Main Application Code (Previous Code Modified) --- ---

# ...(Keep your existing imports and constants)...
# ...(Keep your DUMMY_DATABASE if you put it at the top)...
# ...(Keep your placeholder login/signup functions if needed)...


# --- Modified go_to_login Function (from previous response) ---
def go_to_login(parent_window):
    # ...(Keep the entire go_to_login function as provided in the previous answer)...
    # Find the 'Forgot Password?' button within this function's code:
    # Replace its command with: command=lambda: create_forgot_password_window(login_window)

    # --- Modified go_to_login Function (Showing only the change needed) ---
    def go_to_login(parent_window):
        """Creates and displays the login window."""
        parent_window.withdraw() # Hide the main welcome window

        login_window = tk.Toplevel(parent_window)
        login_window.title("Login - Retail Pro+")
        login_window.geometry("850x550")
        login_window.configure(bg=BG_COLOR_FORM)
        login_window.resizable(False, False)

        def on_login_close():
            parent_window.destroy()
        login_window.protocol("WM_DELETE_WINDOW", on_login_close)

        left_frame = tk.Frame(login_window, bg=BG_COLOR_FORM, padx=40, pady=40)
        left_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=False)
        right_frame = tk.Frame(login_window, bg=BG_COLOR_MAIN)
        right_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)

        # ... (rest of the logo, titles, email/password entries in left_frame) ...

        # --- Find this button definition within go_to_login ---
        forgot_button = tk.Button(
            left_frame,
            text="Forgot Password?",
            font=(FONT_FAMILY, 9, "underline"),
            fg=FG_COLOR_LINK,
            bg=BG_COLOR_FORM,
            bd=0,
            cursor="hand2",
            activeforeground=FG_COLOR_LINK,
            activebackground=BG_COLOR_FORM,
             # --- THIS IS THE MODIFIED LINE ---
            command=lambda: create_forgot_password_window(login_window)
             # --- --- --- --- --- --- --- --- ---
        )
        forgot_button.pack(anchor='e', pady=(0, 20))

        # ... (rest of the sign in button, sign up link in left_frame) ...
        # ... (code for the right_frame image) ...


# --- Main Application Window Setup (Your Original Code) ---
# ...(Keep the setup for the initial 'root' window, labels, logo)...

# --- Proceed button (Ensure it calls the correct go_to_login) ---
proceed_button = tk.Button(
    root,
    text="Proceed to LOGIN",
    command=lambda: go_to_login(root), # Calls the function that builds the login page
    font=(FONT_FAMILY, 12, "bold"),
    bg="#FFCC66",
    fg=FG_COLOR_TEXT_DARK,
    padx=20,
    pady=10,
    relief="flat",
    cursor="hand2"
)
proceed_button.pack()

root.mainloop()