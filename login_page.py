import tkinter as tk
from tkinter import PhotoImage, font as tkFont  # Import font module
from PIL import Image, ImageTk
import os
import webbrowser # To open links for forgot password/sign up

# --- Constants for Styling ---
BG_COLOR_MAIN = "#00A1B1"
BG_COLOR_LEFT_FRAME = "#FFFFFF" # White
FG_COLOR_TEXT_DARK = "#000000" # Black
FG_COLOR_TEXT_LIGHT = "#555555" # Grey
FG_COLOR_LINK = "#007bff" # Blueish link color
BTN_COLOR_SIGNIN = "#008C9E" # Slightly darker teal for button
BTN_FG_COLOR_SIGNIN = "#FFFFFF" # White text on button
FONT_FAMILY = "Helvetica" # Or "Arial" or system default

# --- Placeholder Functions ---
def handle_login(email_entry, password_entry, login_window):
    """Placeholder function to handle the login logic."""
    email = email_entry.get()
    password = password_entry.get()
    print(f"Attempting login with Email: {email}, Password: {password}")
    # Add your actual login verification logic here
    # For now, let's just close the login window on success (dummy)
    if email and password: # Basic check if fields are not empty
        print("Login Successful (Placeholder)")
        login_window.destroy() # Close the login window
        # Here you would typically open the main application window
    else:
        # You could display an error message here
        print("Login Failed: Email or Password empty (Placeholder)")
        # Example: Show an error label (optional)
        # error_label = tk.Label(login_window, text="Email and Password cannot be empty.", fg="red", bg=BG_COLOR_LEFT_FRAME)
        # error_label.pack() # Or grid/place it appropriately

def handle_forgot_password():
    """Placeholder function for the 'Forgot Password?' action."""
    print("Forgot Password clicked")
    # You could open a new window or a web link
    # Example using webbrowser:
    # webbrowser.open("https://yourwebsite.com/forgot-password")

def handle_signup():
    """Placeholder function for the 'Sign Up' action."""
    print("Sign Up clicked")
    # You could open a new window or a web link
    # Example using webbrowser:
    # webbrowser.open("https://yourwebsite.com/signup")

# --- Modified go_to_login Function ---
def go_to_login(parent_window):
    """Creates and displays the login window."""
    parent_window.withdraw() # Hide the main welcome window

    login_window = tk.Toplevel(parent_window)
    login_window.title("Login - Retail Pro+")
    login_window.geometry("850x550") # Adjusted size
    login_window.configure(bg=BG_COLOR_LEFT_FRAME) # Main background for the window itself
    login_window.resizable(False, False)

    # Make the window close the main app when closed
    def on_close():
        parent_window.destroy() # Close the original root window too
    login_window.protocol("WM_DELETE_WINDOW", on_close)


    # --- Left Frame (Login Form) ---
    left_frame = tk.Frame(login_window, bg=BG_COLOR_LEFT_FRAME, padx=40, pady=40)
    left_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=False) # Don't expand left frame

    # --- Right Frame (Image) ---
    right_frame = tk.Frame(login_window, bg=BG_COLOR_MAIN)
    right_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)


    # --- Populate Left Frame ---

    # Logo and Title (using a frame for horizontal layout)
    logo_frame = tk.Frame(left_frame, bg=BG_COLOR_LEFT_FRAME)
    logo_frame.pack(anchor='nw', pady=(0, 40)) # Anchor to top-left

    try:
        logo_path = os.path.join("images", "logo.jpg")
        logo_img_pil = Image.open(logo_path)
        logo_img_pil = logo_img_pil.resize((40, 40), Image.Resampling.LANCZOS)
        logo_img = ImageTk.PhotoImage(logo_img_pil)

        logo_label = tk.Label(logo_frame, image=logo_img, bg=BG_COLOR_LEFT_FRAME)
        logo_label.image = logo_img # Keep a reference!
        logo_label.pack(side=tk.LEFT)

        title_label = tk.Label(logo_frame, text="Retail Pro+", font=(FONT_FAMILY, 16, "bold"), bg=BG_COLOR_LEFT_FRAME, fg=FG_COLOR_TEXT_DARK)
        title_label.pack(side=tk.LEFT, padx=10, pady=5)

    except FileNotFoundError:
        print(f"Error: logo.jpg not found in images folder.")
        # Fallback text if image fails
        title_label = tk.Label(logo_frame, text="Retail Pro+", font=(FONT_FAMILY, 16, "bold"), bg=BG_COLOR_LEFT_FRAME, fg=FG_COLOR_TEXT_DARK)
        title_label.pack(side=tk.LEFT, padx=10, pady=5)
    except Exception as e:
        print(f"Error loading logo image: {e}")
        title_label = tk.Label(logo_frame, text="Retail Pro+", font=(FONT_FAMILY, 16, "bold"), bg=BG_COLOR_LEFT_FRAME, fg=FG_COLOR_TEXT_DARK)
        title_label.pack(side=tk.LEFT, padx=10, pady=5)


    # Welcome Back Heading
    welcome_label = tk.Label(left_frame, text="Welcome Back", font=(FONT_FAMILY, 28, "bold"), bg=BG_COLOR_LEFT_FRAME, fg=FG_COLOR_TEXT_DARK)
    welcome_label.pack(anchor='w', pady=(0, 5))

    # Subheading
    details_label = tk.Label(left_frame, text="Please enter your details!", font=(FONT_FAMILY, 11), bg=BG_COLOR_LEFT_FRAME, fg=FG_COLOR_TEXT_LIGHT)
    details_label.pack(anchor='w', pady=(0, 30))

    # Email Label and Entry
    email_label = tk.Label(left_frame, text="Email Address", font=(FONT_FAMILY, 10), bg=BG_COLOR_LEFT_FRAME, fg=FG_COLOR_TEXT_DARK)
    email_label.pack(anchor='w')
    email_entry = tk.Entry(left_frame, font=(FONT_FAMILY, 12), width=40, bd=1, relief=tk.SOLID)
    email_entry.pack(fill=tk.X, pady=(5, 15)) # Fill horizontally

    # Password Label and Entry
    password_label = tk.Label(left_frame, text="Password", font=(FONT_FAMILY, 10), bg=BG_COLOR_LEFT_FRAME, fg=FG_COLOR_TEXT_DARK)
    password_label.pack(anchor='w')
    password_entry = tk.Entry(left_frame, font=(FONT_FAMILY, 12), show="*", width=40, bd=1, relief=tk.SOLID)
    password_entry.pack(fill=tk.X, pady=(5, 10)) # Fill horizontally

    # Forgot Password Link (using a Button styled as a link)
    forgot_button = tk.Button(
        left_frame,
        text="Forgot Password?",
        font=(FONT_FAMILY, 9, "underline"),
        fg=FG_COLOR_LINK,
        bg=BG_COLOR_LEFT_FRAME,
        bd=0, # No border
        cursor="hand2", # Hand cursor on hover
        activeforeground=FG_COLOR_LINK,
        activebackground=BG_COLOR_LEFT_FRAME,
        command=handle_forgot_password
    )
    forgot_button.pack(anchor='e', pady=(0, 20)) # Anchor to right (east)

    # Sign In Button
    signin_button = tk.Button(
        left_frame,
        text="Sign In",
        font=(FONT_FAMILY, 12, "bold"),
        bg=BTN_COLOR_SIGNIN,
        fg=BTN_FG_COLOR_SIGNIN,
        activebackground=BG_COLOR_MAIN, # Slightly lighter on click
        activeforeground=BTN_FG_COLOR_SIGNIN,
        padx=20,
        pady=8,
        relief="flat", # Flat appearance
        width=35, # Match width roughly with entries
        command=lambda: handle_login(email_entry, password_entry, login_window) # Pass entries and window
    )
    signin_button.pack(pady=(10, 25))

    # Sign Up Section (using a frame for horizontal layout)
    signup_frame = tk.Frame(left_frame, bg=BG_COLOR_LEFT_FRAME)
    signup_frame.pack(pady=(10, 0))

    no_account_label = tk.Label(signup_frame, text="Don't have an account?", font=(FONT_FAMILY, 10), bg=BG_COLOR_LEFT_FRAME, fg=FG_COLOR_TEXT_LIGHT)
    no_account_label.pack(side=tk.LEFT)

    signup_button = tk.Button(
        signup_frame,
        text="Sign Up",
        font=(FONT_FAMILY, 10, "underline bold"),
        fg=FG_COLOR_LINK,
        bg=BG_COLOR_LEFT_FRAME,
        bd=0,
        cursor="hand2",
        activeforeground=FG_COLOR_LINK,
        activebackground=BG_COLOR_LEFT_FRAME,
        command=handle_signup
    )
    signup_button.pack(side=tk.LEFT, padx=5)


    # --- Populate Right Frame ---
    try:
        computer_icon_path = os.path.join("images", "computericon.webp")
        computer_img_pil = Image.open(computer_icon_path)
        # Adjust size as needed, maintain aspect ratio if possible
        # Let's try a fixed height and calculate width
        base_height = 350
        w_percent = (base_height / float(computer_img_pil.size[1]))
        w_size = int((float(computer_img_pil.size[0]) * float(w_percent)))
        computer_img_pil = computer_img_pil.resize((w_size, base_height), Image.Resampling.LANCZOS)

        computer_img = ImageTk.PhotoImage(computer_img_pil)

        computer_label = tk.Label(right_frame, image=computer_img, bg=BG_COLOR_MAIN)
        computer_label.image = computer_img # Keep a reference!
        # Center the image in the right frame using pack
        computer_label.pack(expand=True) # expand=True helps center it

    except FileNotFoundError:
        print(f"Error: computericon.webp not found in images folder.")
        error_label = tk.Label(right_frame, text="Image not found", font=(FONT_FAMILY, 14), bg=BG_COLOR_MAIN, fg="white")
        error_label.pack(expand=True)
    except Exception as e:
        print(f"Error loading computer icon image: {e}")
        error_label = tk.Label(right_frame, text="Error loading image", font=(FONT_FAMILY, 14), bg=BG_COLOR_MAIN, fg="white")
        error_label.pack(expand=True)

# --- Main Application Window Setup (Your Original Code) ---
root = tk.Tk()
root.title("Retail Pro+")
root.geometry("800x450")
root.configure(bg=BG_COLOR_MAIN)  # Use defined constant

# Load and display the logo image (assuming it's the same for welcome)
try:
    image_path = os.path.join("images", "logo.jpg")
    img_pil = Image.open(image_path)
    img_pil = img_pil.resize((250, 250), Image.Resampling.LANCZOS)
    photo = ImageTk.PhotoImage(img_pil)

    img_label = tk.Label(root, image=photo, bg=BG_COLOR_MAIN)
    img_label.image = photo # Keep reference
    img_label.pack(pady=(30, 10))
except FileNotFoundError:
     print(f"Error: {image_path} not found.")
     img_label = tk.Label(root, text="Retail Pro+ Logo", font=(FONT_FAMILY, 16), bg=BG_COLOR_MAIN, fg="white")
     img_label.pack(pady=(30, 10))
except Exception as e:
     print(f"Error loading welcome logo image: {e}")
     img_label = tk.Label(root, text="Error Loading Logo", font=(FONT_FAMILY, 16), bg=BG_COLOR_MAIN, fg="white")
     img_label.pack(pady=(30, 10))


# Welcome text
title = tk.Label(root, text="Welcome to Retail Pro+", font=(FONT_FAMILY, 28, "bold"), bg=BG_COLOR_MAIN, fg=FG_COLOR_TEXT_DARK)
title.pack()

# Subheading
subtitle = tk.Label(root, text="Gain Control of your Inventory and Boost Sales!", font=(FONT_FAMILY, 14), bg=BG_COLOR_MAIN, fg=FG_COLOR_TEXT_DARK)
subtitle.pack(pady=(5, 30))


# Proceed button - Calls the *new* go_to_login function
proceed_button = tk.Button(
    root,
    text="Proceed to LOGIN",
    # Pass the root window to the login function so it can be hidden/closed
    command=lambda: go_to_login(root),
    font=(FONT_FAMILY, 12, "bold"),
    bg="#FFCC66", # Keeping original button color
    fg=FG_COLOR_TEXT_DARK,
    padx=20,
    pady=10,
    relief="flat",
    cursor="hand2"
)
proceed_button.pack()

root.mainloop()