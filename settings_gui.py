import tkinter as tk
from tkinter import ttk, colorchooser
import yaml
from dataclasses import asdict
import os
import threading

class ChessSettingsGUI:
    def __init__(self, root, config=None, legit_mode=None):
        self.root = root
        self.root.title("Chess Settings")
        self.root.geometry("800x600")  # Increased window size
        
        # Initialize config and legit_mode first
        self.config = config
        self.legit_mode = legit_mode
        
        # Create main container
        container = ttk.Frame(root)
        container.grid(row=0, column=0, sticky="nsew")
        
        # Configure grid weights
        root.grid_rowconfigure(0, weight=1)
        root.grid_columnconfigure(0, weight=1)
        
        # Create left panel for settings
        settings_frame = ttk.LabelFrame(container, text="Settings", padding="10")
        settings_frame.grid(row=0, column=0, sticky="nsew", padx=5, pady=5)
        
        # Create right panel for evaluation and moves
        info_frame = ttk.Frame(container, padding="10")
        info_frame.grid(row=0, column=1, sticky="nsew", padx=5, pady=5)
        
        # Configure container grid weights
        container.grid_columnconfigure(0, weight=1)
        container.grid_columnconfigure(1, weight=1)
        
        # Basic Settings Section
        ttk.Label(settings_frame, text="Basic Settings", font=('Helvetica', 12, 'bold')).grid(row=0, column=0, columnspan=2, pady=10)
        
        # Enable/Disable with improved styling
        self.enabled_var = tk.BooleanVar(value=self.config.enabled if self.config else True)
        enable_frame = ttk.Frame(settings_frame)
        enable_frame.grid(row=1, column=0, columnspan=2, sticky="ew", pady=5)
        ttk.Checkbutton(enable_frame, text="Enable Engine", variable=self.enabled_var, 
                       command=self.update_settings, style='Switch.TCheckbutton').pack(side=tk.LEFT)
        
        # Side Selection with improved layout
        ttk.Label(settings_frame, text="Play as:", font=('Helvetica', 10)).grid(row=2, column=0, sticky=tk.W, pady=5)
        self.side_var = tk.StringVar(value=self.config.side if self.config else "white")
        side_frame = ttk.Frame(settings_frame)
        side_frame.grid(row=2, column=1, sticky=tk.W)
        ttk.Radiobutton(side_frame, text="White", variable=self.side_var, value="white", 
                       command=self.update_settings).pack(side=tk.LEFT, padx=5)
        ttk.Radiobutton(side_frame, text="Black", variable=self.side_var, value="black", 
                       command=self.update_settings).pack(side=tk.LEFT, padx=5)
        
        # ELO Rating with validation
        ttk.Label(settings_frame, text="ELO Rating:", font=('Helvetica', 10)).grid(row=3, column=0, sticky=tk.W, pady=5)
        self.elo_var = tk.StringVar(value=str(self.config.elo if self.config else 2000))
        elo_entry = ttk.Entry(settings_frame, textvariable=self.elo_var, width=10)
        elo_entry.grid(row=3, column=1, sticky=tk.W)
        elo_entry.bind('<Return>', lambda e: self.update_settings())
        
        # Arrow Color with preview
        ttk.Label(settings_frame, text="Arrow Color:", font=('Helvetica', 10)).grid(row=4, column=0, sticky=tk.W, pady=5)
        color_frame = ttk.Frame(settings_frame)
        color_frame.grid(row=4, column=1, sticky=tk.W)
        self.arrow_color = self.config.arrow_color if self.config else '#0080FF'
        self.color_button = ttk.Button(color_frame, text="Choose Color", command=self.choose_color)
        self.color_button.pack(side=tk.LEFT, padx=5)
        self.color_preview = tk.Canvas(color_frame, width=30, height=20)
        self.color_preview.pack(side=tk.LEFT, padx=5)
        self.update_color_preview()
        
        # Legit Mode Section with improved styling
        ttk.Separator(settings_frame).grid(row=5, column=0, columnspan=2, sticky="ew", pady=10)
        ttk.Label(settings_frame, text="Legit Mode Settings", font=('Helvetica', 12, 'bold')).grid(row=6, column=0, columnspan=2, pady=10)
        
        # Legit Mode Enable/Disable
        self.legit_mode_var = tk.BooleanVar(value=self.config.legit_mode if self.config else True)
        ttk.Checkbutton(settings_frame, text="Enable Legit Mode", variable=self.legit_mode_var, 
                       command=self.update_settings, style='Switch.TCheckbutton').grid(row=7, column=0, columnspan=2, sticky=tk.W, pady=5)
        
        # Blunder Chance with slider
        ttk.Label(settings_frame, text="Blunder Chance (%):", font=('Helvetica', 10)).grid(row=8, column=0, sticky=tk.W, pady=5)
        self.blunder_var = tk.DoubleVar(value=float(self.config.blunder_chance if self.config else 0.15) * 100)
        blunder_slider = ttk.Scale(settings_frame, from_=0, to=100, variable=self.blunder_var, 
                                 command=lambda _: self.update_settings())
        blunder_slider.grid(row=8, column=1, sticky="ew", pady=5)
        
        # Suboptimal Chance with slider
        ttk.Label(settings_frame, text="Suboptimal Chance (%):", font=('Helvetica', 10)).grid(row=9, column=0, sticky=tk.W, pady=5)
        self.suboptimal_var = tk.DoubleVar(value=float(self.config.suboptimal_chance if self.config else 0.35) * 100)
        suboptimal_slider = ttk.Scale(settings_frame, from_=0, to=100, variable=self.suboptimal_var, 
                                    command=lambda _: self.update_settings())
        suboptimal_slider.grid(row=9, column=1, sticky="ew", pady=5)
        
        # Evaluation Bar (right panel)
        eval_frame = ttk.LabelFrame(info_frame, text="Evaluation", padding="10")
        eval_frame.grid(row=0, column=0, sticky="nsew", pady=5)
        self.eval_canvas = tk.Canvas(eval_frame, width=40, height=200, bg='white')
        self.eval_canvas.pack(pady=5)
        self.draw_eval_bar(0.0)  # Initial evaluation
        
        # Moves List (right panel)
        moves_frame = ttk.LabelFrame(info_frame, text="Moves List", padding="10")
        moves_frame.grid(row=1, column=0, sticky="nsew", pady=5)
        self.moves_text = tk.Text(moves_frame, height=10, width=30)
        self.moves_text.pack(fill=tk.BOTH, expand=True)
        
        # Status Label with improved styling
        self.status_label = ttk.Label(settings_frame, text="", font=('Helvetica', 9, 'italic'))
        self.status_label.grid(row=10, column=0, columnspan=2, pady=10)
        
        # Apply button with improved styling
        apply_button = ttk.Button(settings_frame, text="Apply Changes", command=self.update_settings, style='Accent.TButton')
        apply_button.grid(row=11, column=0, columnspan=2, pady=10)
        
        # Configure styles
        self.configure_styles()
        
        # Start periodic update
        self.update_from_config()
    
    def configure_styles(self):
        style = ttk.Style()
        style.configure('Accent.TButton', font=('Helvetica', 10, 'bold'))
        style.configure('Switch.TCheckbutton', font=('Helvetica', 10))
    
    def draw_eval_bar(self, evaluation):
        self.eval_canvas.delete("all")
        height = self.eval_canvas.winfo_height()
        width = self.eval_canvas.winfo_width()
        
        # Convert evaluation to visual representation (0 to 1)
        eval_normalized = max(min(evaluation, 1.0), -1.0)
        
        # Draw black background bar (always starts from bottom)
        black_height = height  # Full height for black bar
        self.eval_canvas.create_rectangle(0, 0, width, height, fill='black')
        
        # Calculate white bar height (starts from bottom)
        # For positive eval, white bar gets shorter (showing more black)
        # For negative eval, white bar gets taller (showing less black)
        white_height = height * (1.0 - abs(eval_normalized))
        
        # Draw white bar from bottom
        self.eval_canvas.create_rectangle(0, height - white_height, width, height, 
                                        fill='white', outline='#333333')
        
        # Draw evaluation text at appropriate position
        text_y = 10 if evaluation >= 0 else height - 10
        self.eval_canvas.create_text(width/2, text_y, text=f"{abs(evaluation):.1f}", 
                                   fill='white')
    
    def add_move(self, move_text):
        self.moves_text.insert(tk.END, move_text + "\n")
        self.moves_text.see(tk.END)
    
    def choose_color(self):
        color = colorchooser.askcolor(color=self.arrow_color)
        if color[1]:
            self.arrow_color = color[1]
            self.update_color_preview()
            self.update_settings()
    
    def update_color_preview(self):
        self.color_preview.delete("all")
        self.color_preview.create_rectangle(0, 0, 20, 20, fill=self.arrow_color, outline="")
    
    def update_settings(self):
        try:
            # Update config object
            self.config.enabled = self.enabled_var.get()
            self.config.side = self.side_var.get()
            self.config.elo = int(self.elo_var.get())
            self.config.arrow_color = self.arrow_color
            self.config.legit_mode = self.legit_mode_var.get()
            self.config.blunder_chance = float(self.blunder_var.get()) / 100
            self.config.suboptimal_chance = float(self.suboptimal_var.get()) / 100
            
            # Update legit mode settings
            if self.legit_mode:
                self.legit_mode.enabled = self.legit_mode_var.get()
                self.legit_mode.blunder_chance = float(self.blunder_var.get()) / 100
                self.legit_mode.suboptimal_chance = float(self.suboptimal_var.get()) / 100
            
            # Save to file
            self.config.save_config()
            
            self.status_label.config(text="Settings updated successfully!", foreground="green")
        except Exception as e:
            self.status_label.config(text=f"Error updating settings: {str(e)}", foreground="red")
    
    def update_from_config(self):
        if not self.config:
            return
            
        self.enabled_var.set(self.config.enabled)
        self.side_var.set(self.config.side)
        self.elo_var.set(str(self.config.elo))
        self.arrow_color = self.config.arrow_color
        self.update_color_preview()
        self.legit_mode_var.set(self.config.legit_mode)
        self.blunder_var.set(str(float(self.config.blunder_chance) * 100))
        self.suboptimal_var.set(str(float(self.config.suboptimal_chance) * 100))

def create_settings_window(config, legit_mode):
    """Create and return a settings window instance"""
    root = tk.Tk()
    return ChessSettingsGUI(root, config=config, legit_mode=legit_mode)

if __name__ == "__main__":
    # For testing the GUI independently
    class MockConfig:
        def __init__(self):
            self.enabled = True
            self.side = "white"
            self.elo = 2000
            self.arrow_color = "#0080FF"
            self.legit_mode = True
            self.blunder_chance = 0.15
            self.suboptimal_chance = 0.35
            
        def save_config(self):
            pass
    
    root = tk.Tk()
    app = ChessSettingsGUI(root, config=MockConfig())
    root.mainloop()