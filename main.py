import tkinter as tk
from tkinter import PhotoImage
from PIL import Image, ImageTk
import os

# Initialize the main window
root = tk.Tk()
root.title("Retail Pro+")
root.geometry("800x450")
root.configure(bg="#00A1B1")  # Background color to match the image

# Load and display the image from the images folder
image_path = os.path.join("images", "logo.jpg")
img = Image.open(image_path)
img = img.resize((250, 250), Image.Resampling.LANCZOS)
photo = ImageTk.PhotoImage(img)

img_label = tk.Label(root, image=photo, bg="#00A1B1")
img_label.pack(pady=(30, 10))

# Welcome text
title = tk.Label(root, text="Welcome to Retail Pro+", font=("Helvetica", 28, "bold"), bg="#00A1B1", fg="black")
title.pack()

# Subheading
subtitle = tk.Label(root, text="Gain Control of your Inventory and Boost Sales!", font=("Helvetica", 14), bg="#00A1B1", fg="black")
subtitle.pack(pady=(5, 30))

# Function to simulate login page transition
def go_to_login():
    login_window = tk.Toplevel(root)
    login_window.title("Login Page")
    login_window.geometry("400x200")
    tk.Label(login_window, text="This is the login page.", font=("Helvetica", 16)).pack(pady=50)

# Proceed button
proceed_button = tk.Button(
    root,
    text="Proceed to LOGIN",
    command=go_to_login,
    font=("Helvetica", 12, "bold"),
    bg="#FFCC66",
    fg="black",
    padx=20,
    pady=10,
    relief="flat"
)
proceed_button.pack()

root.mainloop()
