import argparse
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.edge.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import NoSuchElementException, TimeoutException, StaleElementReferenceException
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.keys import Keys
from rich.console import Console
import time
import chess
import traceback
import chess.engine
import os
import re
import sys
import subprocess
import json
import random
from dataclasses import dataclass
import threading
import yaml
import msvcrt
import tkinter as tk
from settings_gui import create_settings_window, ChessSettingsGUI

@dataclass
class LegitModeSettings:
    enabled: bool = False
    blunder_chance: float = 0.15      # 15% chance to make a small blunder
    suboptimal_chance: float = 0.35   # 35% chance to make slightly suboptimal move
    skill_variance: float = 0.2       # How much skill varies (0.0-1.0)
    consistency: int = 70             # Consistency of play (0-100)
    elo_variance: int = 200           # How much ELO effectively varies


# Parse command line arguments
def parse_arguments():
    # Load config from YAML file
    config_path = 'config.yaml'
    try:
        with open(config_path, 'r') as f:
            config = yaml.safe_load(f)
    except Exception as e:
        console.print(f"[red]Error loading config file: {e}[/red]")
        return None

    # Create a simple namespace object to store config
    class Config:
        def __init__(self, config):
            self.enabled = config.get('enabled', True)
            self.side = config.get('side', 'white')
            self.elo = config.get('elo', 2000)
            self.arrow_color = config.get('arrow_color', '#0080FF')
            self.legit_mode = config.get('legit_mode', True)
            self.blunder_chance = config.get('blunder_chance', 0.15)
            self.suboptimal_chance = config.get('suboptimal_chance', 0.35)
            self.settings_file = None  # Not used when using YAML config
            
        def save_config(self):
            config = {
                'enabled': self.enabled,
                'side': self.side,
                'elo': self.elo,
                'arrow_color': self.arrow_color,
                'legit_mode': self.legit_mode,
                'blunder_chance': self.blunder_chance,
                'suboptimal_chance': self.suboptimal_chance
            }
            try:
                with open('config.yaml', 'w') as f:
                    yaml.dump(config, f)
            except Exception as e:
                console.print(f"[red]Error saving config: {e}[/red]")

    return Config(config)

legit_mode = LegitModeSettings()
# Initialize rich console
console = Console()

# Global variables
previous_board_state = {}
current_turn = "white"  # Track whose turn it is
last_moves = {"white": None, "black": None}
evaluation_score = 0.0  # Track the current evaluation
args = parse_arguments()  # Get command line arguments
current_side = args.side if args else "white"  # Track current side
settings_window = None


# Function to select a move based on legit mode criteria
def select_legit_move(moves_with_eval, is_white):
    """Select a move that mimics human play, including occasional blunders"""
    global legit_mode, current_side
    
    if not moves_with_eval or len(moves_with_eval) < 2:
        return moves_with_eval[0][0] if moves_with_eval else None
    
    # If legit mode is disabled, always return best move
    if not legit_mode.enabled:
        return moves_with_eval[0][0]
    
    # Roll for move selection type
    roll = random.random()
    
    # Perspective adjustment: negate scores if playing as black
    # Update this to use current_side instead of is_white
    should_negate = (current_side == "black")
    if should_negate:
        moves_with_eval = [(move, -score) for move, score in moves_with_eval]
    
    # Get the best move's evaluation as reference
    best_eval = moves_with_eval[0][1]
    
    # Case 1: Make a blunder (a significantly worse move)
    if roll < legit_mode.blunder_chance:
        # Filter for moves that are noticeably worse but not catastrophic
        blunder_candidates = []
        for move, eval_score in moves_with_eval[1:]:  # Skip the best move
            eval_diff = best_eval - eval_score
            # Look for moves that are worse by 0.5-1.5 pawns
            if 0.5 <= eval_diff <= 1.5:
                blunder_candidates.append((move, eval_score))
        
        if blunder_candidates:
            console.print("[blue]Legit mode: Suggesting a small blunder[/blue]")
            # Select a random blunder from candidates
            return random.choice(blunder_candidates)[0]
    
    # Case 2: Make a suboptimal move (slightly worse)
    elif roll < legit_mode.blunder_chance + legit_mode.suboptimal_chance:
        # Filter for moves that are slightly suboptimal
        suboptimal_candidates = []
        for move, eval_score in moves_with_eval[1:]:  # Skip the best move
            eval_diff = best_eval - eval_score
            # Look for moves that are worse by 0.1-0.4 pawns
            if 0.1 <= eval_diff <= 0.4:
                suboptimal_candidates.append((move, eval_score))
        
        if suboptimal_candidates:
            console.print("[blue]Legit mode: Suggesting a slightly suboptimal move[/blue]")
            # Select a random suboptimal move from candidates
            return random.choice(suboptimal_candidates)[0]
    
    # Case 3: Use best move (with a slight preference for different "style" best moves)
    # This is the default case
    console.print("[blue]Legit mode: Suggesting the best move[/blue]")
    return moves_with_eval[0][0]

# Function to get alternative moves of different qualities
def get_alternative_moves(board, engine, time_limit=0.1, multipv=5):
    """Get multiple alternative moves with their evaluations"""
    global current_side
    if not engine or not board:
        return []
    
    try:
        # Set time limit and multipv for analysis
        limit = chess.engine.Limit(time=time_limit)
        
        try:
            # Try to configure engine for multi-PV mode
            engine.configure({"MultiPV": multipv})
            use_multipv = True
        except Exception as config_error:
            console.print(f"[yellow]Could not set MultiPV option: {config_error}. Using single PV mode.[/yellow]")
            use_multipv = False
        
        # Get analysis - either multi-PV or just best move
        if use_multipv:
            result = engine.analyse(board, limit, multipv=multipv)
        else:
            # Fallback to single PV analysis
            info = engine.analyse(board, limit)
            result = [info]  # Wrap in list to match multi-PV format
        
        # Reset engine to default if we were able to set it initially
        if use_multipv:
            try:
                engine.configure({"MultiPV": 1})
            except:
                pass
        
        moves_with_eval = []
        
        for entry in result:
            moves = entry.get("pv", [])
            if not moves:
                continue
                
            move = moves[0]
            score = entry.get("score")
            
            # Convert score to decimal value for current side's perspective
            eval_score = 0.0
            try:
                if hasattr(score.white(), 'mate') and score.white().mate() is not None:
                    mate_value = score.white().mate()
                    eval_score = 9.9 if mate_value > 0 else -9.9
                else:
                    eval_score = score.white().score() / 100
                
                # Adjust score based on current side
                if current_side == "black":
                    eval_score = -eval_score
                    
            except Exception as e:
                console.print(f"[yellow]Error processing score: {e}[/yellow]")
            
            moves_with_eval.append((move, eval_score))
        
        return moves_with_eval
        
    except Exception as e:
        console.print(f"[yellow]Error getting alternative moves: {e}[/yellow]")
        return []

# Function to send evaluation to C# application
def send_evaluation(score):
    print(f"EVAL:{score:+.2f}")
    sys.stdout.flush()  # Ensure immediate output

# Initialize chess engine with better error handling
def initialize_stockfish(path="stockfish", elo=None):
    """Initialize the Stockfish chess engine with error handling"""
    try:
        # Try to locate Stockfish in common paths if not provided
        if path == "stockfish":
            possible_paths = [
                "C:\\stockfish\\stockfish-windows-x86-64-avx2.exe",
                "C:\\Program Files\\stockfish\\stockfish.exe",
                "C:\\Users\\abajra8064\\Downloads\\stockfish\\stockfish-windows-x86-64-avx2.exe",
                "C:\\stockfish\\stockfish.exe",
                "/usr/local/bin/stockfish",
                "/usr/bin/stockfish",
                "stockfish"
            ]
            
            for possible_path in possible_paths:
                if os.path.exists(possible_path):
                    path = possible_path
                    break
        
        # Check if engine exists at path
        if not os.path.exists(path):
            console.print(f"[bold red]Stockfish not found at {path}[/bold red]")
            console.print("[yellow]Trying to find Stockfish in PATH...[/yellow]")
            
            # Try finding stockfish in PATH
            try:
                if os.name == 'nt':  # Windows
                    result = subprocess.run(['where', 'stockfish'], capture_output=True, text=True, check=False)
                else:  # Unix-like
                    result = subprocess.run(['which', 'stockfish'], capture_output=True, text=True, check=False)
                    
                if result.returncode == 0 and result.stdout.strip():
                    path = result.stdout.strip()
                    console.print(f"[green]Found Stockfish at: {path}[/green]")
                else:
                    raise FileNotFoundError("Stockfish not found in PATH")
            except (subprocess.SubprocessError, FileNotFoundError) as e:
                console.print(f"[bold red]Error locating Stockfish: {e}[/bold red]")
                console.print("[yellow]Will run without engine analysis.[/yellow]")
                return None
        
        # Initialize the engine
        engine = chess.engine.SimpleEngine.popen_uci(path)
        
        # Set ELO rating if provided
        if elo is not None:
            try:
                # Convert ELO to skill level (0-20)
                # This is an approximation - actual conversion depends on Stockfish version
                skill_level = max(0, min(20, int((elo - 800) / 120)))
                
                # Set skill level
                engine.configure({"Skill Level": skill_level})
                
                # For newer Stockfish versions, can also set ELO directly
                try:
                    engine.configure({"UCI_Elo": elo})
                except:
                    pass  # Ignore if this option isn't supported
                
                console.print(f"[green]Engine strength set to approximately {elo} ELO (skill level: {skill_level})[/green]")
            except Exception as e:
                console.print(f"[yellow]Could not set engine strength: {e}[/yellow]")
        
        console.print(f"[bold green]Successfully initialized Stockfish at {path}[/bold green]")
        return engine
    except Exception as e:
        console.print(f"[bold red]Failed to initialize Stockfish: {e}[/bold red]")
        console.print("[yellow]Will run without engine analysis.[/yellow]")
        return None

# Initialize stockfish with ELO from arguments
engine = initialize_stockfish(elo=args.elo) if args.enabled else None

def convert_algebraic_to_numeric(alg):
    """Convert algebraic notation (e.g., 'g1') to numeric format (e.g., '71')"""
    if not alg or len(alg) != 2 or not alg[0].isalpha() or not alg[1].isdigit():
        return None
    
    try:
        col_char = alg[0].lower()
        if col_char < 'a' or col_char > 'h':
            return None
        col = ord(col_char) - ord('a') + 1
        
        row = int(alg[1])
        if row < 1 or row > 8:
            return None
        
        return f"{col}{row}"
    except (ValueError, TypeError):
        return None

def convert_numeric_to_algebraic(num):
    """Convert numeric format (e.g., '71') to algebraic notation (e.g., 'g1')"""
    if not num or len(num) != 2 or not num.isdigit():
        return None
    
    try:
        col = int(num[0])
        row = int(num[1])
        
        if col < 1 or col > 8 or row < 1 or row > 8:
            return None
        
        col_char = chr(ord('a') + col - 1)
        return f"{col_char}{row}"
    except (ValueError, TypeError):
        return None

def get_board_state(driver):
    """Get current positions of all pieces on the board with improved error handling"""
    board_state = {}
    try:
        # Wait a moment for board to stabilize
        time.sleep(0.1)
        
        # Find the chess board first with multiple selector attempts
        board = None
        selectors = [
            'wc-chess-board.board',
            'div.board',
            '.board-layout-chessboard',
            '.board-container'
        ]
        
        for selector in selectors:
            try:
                board = WebDriverWait(driver, 1).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, selector))
                )
                console.print(f"[dim]Board found with selector: {selector}[/dim]")
                break
            except:
                continue
        
        if not board:
            console.print("[yellow]Could not find chess board with any selector[/yellow]")
            # Try to get the page source to debug
            try:
                page_title = driver.title
                current_url = driver.current_url
                console.print(f"[yellow]Current page: {page_title} ({current_url})[/yellow]")
                
                # Check for typical error conditions
                if "unavailable" in page_title.lower() or "error" in page_title.lower():
                    console.print("[red]Page appears to be showing an error[/red]")
            except:
                pass
            return board_state
        
        # Try multiple piece selectors
        piece_selectors = [
            'div.piece',
            '.piece',
            '.chess-piece',
            '[data-piece]'
        ]
        
        pieces = []
        for selector in piece_selectors:
            try:
                pieces = board.find_elements(By.CSS_SELECTOR, selector)
                if pieces:
                    console.print(f"[dim]Pieces found with selector: {selector} (count: {len(pieces)})[/dim]")
                    break
            except:
                continue
        
        if not pieces:
            console.print("[yellow]No pieces found on board with any selector[/yellow]")
            
            # Try to get board HTML for debugging
            try:
                board_html = board.get_attribute('innerHTML')
                if len(board_html) > 500:
                    board_html = board_html[:500] + "... [truncated]"
                console.print(f"[dim]Board HTML: {board_html}[/dim]")
            except:
                pass
                
            return board_state
            
        for piece in pieces:
            try:
                # Try multiple ways to get piece information
                piece_type = None
                position = None
                
                # Method 1: Class names
                class_list = piece.get_attribute('class')
                if class_list:
                    class_list = class_list.split()
                    # Extract piece type and position from class names
                    piece_types = [c for c in class_list if c.startswith(('b', 'w')) and len(c) == 2]
                    positions = [c for c in class_list if c.startswith('square-')]
                    
                    if piece_types:
                        piece_type = piece_types[0]
                    if positions:
                        position = positions[0].split('-')[1] if '-' in positions[0] else positions[0]
                
                # Method 2: Data attributes
                if not piece_type or not position:
                    data_piece = piece.get_attribute('data-piece')
                    data_square = piece.get_attribute('data-square')
                    
                    if data_piece:
                        piece_type = data_piece.lower()
                    if data_square:
                        position = data_square
                
                # Method 3: Style positioning
                if not position:
                    style = piece.get_attribute('style')
                    if style:
                        # This requires custom parsing based on Chess.com's positioning
                        console.print(f"[dim]Piece with style but no position: {style}[/dim]")
                
                # Store piece if we have both type and position
                if piece_type and position:
                    board_state[position] = piece_type
                else:
                    console.print(f"[yellow]Incomplete piece info - type: {piece_type}, position: {position}[/yellow]")
                    
                    # Log the raw piece HTML for debugging
                    try:
                        piece_html = piece.get_attribute('outerHTML')
                        console.print(f"[dim]Problem piece HTML: {piece_html}[/dim]")
                    except:
                        pass
                        
            except StaleElementReferenceException:
                # Piece was updated during iteration, skip it
                console.print("[dim]Skipped stale piece element[/dim]")
                continue
            except Exception as piece_error:
                console.print(f"[yellow]Error processing piece: {piece_error}[/yellow]")
                continue
                
        # Log final result
        if board_state:
            console.print(f"[dim]Found {len(board_state)} pieces on the board[/dim]")
        else:
            console.print("[yellow]No pieces could be processed properly[/yellow]")
            
    except TimeoutException:
        console.print("[yellow]Timeout waiting for chess board[/yellow]")
    except Exception as e:
        console.print(f"[red]Error getting board state: {e}[/red]")
        # Print traceback for better debugging
        import traceback
        console.print(f"[dim red]{traceback.format_exc()}[/dim red]")
    
    return board_state

def find_moved_pieces(old_state, new_state):
    """Compare two board states to find moved pieces"""
    # Find pieces that are in new positions
    appeared = {pos: piece for pos, piece in new_state.items() 
               if pos not in old_state or old_state[pos] != piece}
    
    # Find pieces that disappeared from their old positions
    disappeared = {pos: piece for pos, piece in old_state.items() 
                 if pos not in new_state or new_state[pos] != piece}
    
    # Group by piece type to find moves
    moves = []
    for old_pos, old_piece in disappeared.items():
        for new_pos, new_piece in appeared.items():
            if old_piece == new_piece:
                moves.append((old_pos, new_pos, old_piece))
                # Remove these items to avoid duplicate matching
                appeared.pop(new_pos)
                break
    
    return moves

def get_fen_from_board(board_state):
    """Convert current board state to FEN notation with improved handling"""
    # Initialize empty board
    board = [['' for _ in range(8)] for _ in range(8)]
    
    # Map pieces to FEN notation
    piece_map = {
        'wp': 'P', 'wn': 'N', 'wb': 'B', 'wr': 'R', 'wq': 'Q', 'wk': 'K',
        'bp': 'p', 'bn': 'n', 'bb': 'b', 'br': 'r', 'bq': 'q', 'bk': 'k'
    }
    
    # Check if the board state is valid
    if not board_state:
        console.print("[red]Empty board state, cannot create FEN[/red]")
        return None
    
    # Count pieces to validate the board state
    king_count = {'w': 0, 'b': 0}
    for piece in board_state.values():
        if piece == 'wk':
            king_count['w'] += 1
        elif piece == 'bk':
            king_count['b'] += 1
    
    # Validate kings (must have exactly one of each)
    if king_count['w'] != 1 or king_count['b'] != 1:
        console.print(f"[red]Invalid board state - kings: white={king_count['w']}, black={king_count['b']}[/red]")
        return None
    
    # Populate board array with better error handling
    for position, piece in board_state.items():
        try:
            # Handle both algebraic and numeric formats
            if len(position) == 2:
                if position[0].isalpha():
                    # Algebraic notation (e.g., "e2")
                    col = ord(position[0].lower()) - ord('a')
                    row = 8 - int(position[1])
                else:
                    # Numeric notation (e.g., "52")
                    col = int(position[0]) - 1
                    row = 8 - int(position[1])
                
                if 0 <= col < 8 and 0 <= row < 8:
                    board[row][col] = piece_map.get(piece, '')
        except (ValueError, IndexError):
            pass  # Skip invalid positions
    
    # Convert to FEN string
    fen_parts = []
    for row in board:
        empty = 0
        fen_row = ''
        for cell in row:
            if cell == '':
                empty += 1
            else:
                if empty > 0:
                    fen_row += str(empty)
                    empty = 0
                fen_row += cell
        if empty > 0:
            fen_row += str(empty)
        fen_parts.append(fen_row)
    
    # Determine whose turn it is based on global variable
    active_color = 'w' if current_turn == "white" else 'b'
    
    # Complete FEN with simplified castling rights and other fields
    fen = '/'.join(fen_parts) + f' {active_color} KQkq - 0 1'
    return fen

def create_arrow(driver, from_square, to_square, color=None, width=2.5):
    """Create an arrow from one square to another with improved appearance"""
    if color is None:
        color = args.arrow_color  # Use color from arguments
        
    try:
        script = f"""
        (function() {{
            // Find the chess board and its SVG arrows element
            const board = document.querySelector('wc-chess-board.board');
            const arrowsSvg = board?.querySelector('svg.arrows');
            if (!board || !arrowsSvg) return false;
            
            // Calculate positions (use square centers)
            const fromX = (parseInt('{from_square}'[0]) - 0.5) * 12.5;
            const fromY = (8.5 - parseInt('{from_square}'[1])) * 12.5;
            const toX = (parseInt('{to_square}'[0]) - 0.5) * 12.5;
            const toY = (8.5 - parseInt('{to_square}'[1])) * 12.5;
            
            // Calculate the direction vector
            const dx = toX - fromX;
            const dy = toY - fromY;
            const length = Math.sqrt(dx*dx + dy*dy);
            
            // Normalize direction vector
            const ndx = dx / length;
            const ndy = dy / length;
            
            // Calculate perpendicular vector
            const px = -ndy;
            const py = ndx;
            
            // Square size as percentage (12.5%)
            const squareSize = 12.5;
            
            // Calculate offsets to avoid covering the pieces (percentage of square)
            const edgeOffset = squareSize * 0.3;
            
            // Calculate points with offset from square edges
            const tailX = fromX + ndx * edgeOffset;
            const tailY = fromY + ndy * edgeOffset;
            
            // Calculate the tip position with offset from target edge
            const tipX = toX - ndx * edgeOffset;
            const tipY = toY - ndy * edgeOffset;
            
            // Arrow head size based on square size
            const headSize = squareSize * 0.35;
            
            // Create arrow head points
            // First calculate the base of the arrow head
            const baseX = tipX - ndx * (headSize * 0.6);
            const baseY = tipY - ndy * (headSize * 0.6);
            
            // Then calculate the corners of the arrow head
            const headCorner1X = baseX + px * (headSize * 0.5);
            const headCorner1Y = baseY + py * (headSize * 0.5);
            const headCorner2X = baseX - px * (headSize * 0.5);
            const headCorner2Y = baseY - py * (headSize * 0.5);
            
            // Remove any existing custom arrows and borders
            const existingArrows = arrowsSvg.querySelectorAll('.custom-arrow, .square-border');
            existingArrows.forEach(a => a.remove());
            
            // Create borders for from and to squares
            const fromSquareRect = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
            fromSquareRect.setAttribute('x', (parseInt('{from_square}'[0]) - 1) * 12.5 + '%');
            fromSquareRect.setAttribute('y', (8 - parseInt('{from_square}'[1])) * 12.5 + '%');
            fromSquareRect.setAttribute('width', '12.5%');
            fromSquareRect.setAttribute('height', '12.5%');
            fromSquareRect.setAttribute('fill', 'none');
            fromSquareRect.setAttribute('stroke', '{color}');
            fromSquareRect.setAttribute('stroke-width', '0.3');  // Made border much thinner
            fromSquareRect.setAttribute('class', 'square-border');
            fromSquareRect.style.pointerEvents = 'none';
            
            const toSquareRect = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
            toSquareRect.setAttribute('x', (parseInt('{to_square}'[0]) - 1) * 12.5 + '%');
            toSquareRect.setAttribute('y', (8 - parseInt('{to_square}'[1])) * 12.5 + '%');
            toSquareRect.setAttribute('width', '12.5%');
            toSquareRect.setAttribute('height', '12.5%');
            toSquareRect.setAttribute('fill', 'none');
            toSquareRect.setAttribute('stroke', '{color}');
            toSquareRect.setAttribute('stroke-width', '0.3');  // Made border much thinner
            toSquareRect.setAttribute('class', 'square-border');
            toSquareRect.style.pointerEvents = 'none';
            
            // Create the arrow shaft
            const arrowShaft = document.createElementNS('http://www.w3.org/2000/svg', 'line');
            arrowShaft.setAttribute('x1', tailX + '%');
            arrowShaft.setAttribute('y1', tailY + '%');
            arrowShaft.setAttribute('x2', baseX + '%');
            arrowShaft.setAttribute('y2', baseY + '%');
            arrowShaft.setAttribute('stroke', '{color}');
            arrowShaft.setAttribute('stroke-width', '{width}');
            arrowShaft.setAttribute('class', 'custom-arrow');
            arrowShaft.style.pointerEvents = 'none';
            
            // Create the arrow head
            const arrowHead = document.createElementNS('http://www.w3.org/2000/svg', 'polygon');
            const points = `${{baseX}},${{baseY}} ${{headCorner1X}},${{headCorner1Y}} ${{tipX}},${{tipY}} ${{headCorner2X}},${{headCorner2Y}}`;
            arrowHead.setAttribute('points', points);
            arrowHead.setAttribute('fill', '{color}');
            arrowHead.setAttribute('class', 'custom-arrow');
            arrowHead.style.pointerEvents = 'none';
            
            // Add all elements to the SVG
            arrowsSvg.appendChild(fromSquareRect);
            arrowsSvg.appendChild(toSquareRect);
            arrowsSvg.appendChild(arrowShaft);
            arrowsSvg.appendChild(arrowHead);
            
            return true;
        }})();
        """
        driver.execute_script(script)
        return True
    except Exception as e:
        console.print(f"[yellow]Error creating arrow: {e}[/yellow]")

def get_current_position_from_fen(fen):
    """Create a chess board from FEN string"""
    if not fen:
        return None
    try:
        return chess.Board(fen)
    except ValueError as e:
        console.print(f"[yellow]Invalid FEN: {e}[/yellow]")
        return None

def get_best_move(board, engine, time_limit=0.1):
    """Get the best move from the engine with legit mode support"""
    global evaluation_score, legit_mode
    
    if not engine or not board:
        return None, 0.0
    
    try:
        # Get multiple candidate moves
        moves_with_eval = get_alternative_moves(board, engine, time_limit, multipv=5)
        
        if not moves_with_eval:
            console.print("[yellow]No moves found in analysis[/yellow]")
            return None, 0.0
        
        # Default evaluation from best move
        evaluation_score = moves_with_eval[0][1]
        
        # Determine if we're playing as white
        is_white = current_turn == "white"
        
        # Select move based on legit mode criteria
        selected_move = select_legit_move(moves_with_eval, is_white)
        
        # Send evaluation to C# application
        send_evaluation(evaluation_score)
        
        return selected_move, evaluation_score
    except Exception as e:
        console.print(f"[yellow]Error getting best move: {e}[/yellow]")
        return None, evaluation_score

def get_moves_list(driver):
    """Get the list of moves played in the game"""
    try:
        # Find all move elements
        moves = []
        move_elements = driver.find_elements(By.CSS_SELECTOR, '.node-highlight-content')
        for move in move_elements:
            moves.append(move.text)
        return moves
    except Exception as e:
        console.print(f"[yellow]Error getting moves list: {e}[/yellow]")
        return []

def detect_turn_from_moves(moves):
    """Determine whose turn it is based on the number of moves played"""
    if not moves:
        return "white"  # White starts if no moves
    
    # Each complete turn has two moves (white and black)
    # If odd number of moves, it's black's turn
    return "black" if len(moves) % 2 == 1 else "white"

def analyze_and_display_best_move(driver, board_state):
    """Analyze the position and display the best move"""
    global evaluation_score, current_turn, args
    
    # Make sure we check if analysis is enabled immediately
    if not args.enabled:
        console.print("[dim]Analysis disabled by user settings[/dim]")
        # Clean up any existing arrows since analysis is disabled
        clean_up_visual_elements(driver)
        return
    
    # Skip if engine is not available
    if not engine:
        return
    
    # Get FEN representation of the board
    fen = get_fen_from_board(board_state)
    if not fen:
        console.print("[yellow]Could not generate valid FEN, skipping analysis[/yellow]")
        return
    
    # Skip if analysis is disabled
    if not args.enabled or not engine:
        # Only print message about disabled analysis if we have an engine
        if engine and not args.enabled:
            console.print("[dim]Analysis disabled by user settings[/dim]")
            return
    
    # Get FEN representation of the board
    fen = get_fen_from_board(board_state)
    if not fen:
        console.print("[yellow]Could not generate valid FEN, skipping analysis[/yellow]")
        return
    
    # Create chess board object from FEN
    board = get_current_position_from_fen(fen)
    if not board:
        console.print("[yellow]Could not create valid board from FEN, skipping analysis[/yellow]")
        return
    
    # Get best move from engine
    best_move, score = get_best_move(board, engine)
    if not best_move:
        console.print("[yellow]No best move found after attempts[/yellow]")
        return
    
    # Convert chess.Move to algebraic notation
    from_square = chess.square_name(best_move.from_square)
    to_square = chess.square_name(best_move.to_square)
    
    # Convert to numeric format for visualization
    source_pos = convert_algebraic_to_numeric(from_square)
    target_pos = convert_algebraic_to_numeric(to_square)
    
    if source_pos and target_pos:
        # Create arrow to show best move
        create_arrow(driver, source_pos, target_pos, width=3)
        
        # Log the best move with evaluation
        console.print(f"[bold]Best Move:[/bold] {from_square}{to_square} [bold]Eval:[/bold] {score:+.2f}")

def monitor_board_state(driver):
    """Monitor the chess board for changes and analyze positions"""
    global previous_board_state, current_turn, last_moves, evaluation_score, args, crash_count
    
    try:
        # Log the current monitoring cycle and crash counter
        console.print(f"[dim]Monitoring cycle - crash count: {crash_count}[/dim]")
        
        # Get current state of the board
        console.print("[dim]Attempting to get board state...[/dim]")
        current_board_state = get_board_state(driver)
        
        # Log board state count
        piece_count = len(current_board_state) if current_board_state else 0
        console.print(f"[dim]Board state pieces found: {piece_count}[/dim]")
        
        # Get current moves list
        try:
            console.print("[dim]Attempting to get moves list...[/dim]")
            moves_list = get_moves_list(driver)
            if moves_list:
                console.print(f"Current moves: {', '.join(moves_list[-5:]) if len(moves_list) > 5 else moves_list}", style="cyan")
                
                # Update whose turn it is
                previous_turn = current_turn
                current_turn = detect_turn_from_moves(moves_list)
                if previous_turn != current_turn:
                    console.print(f"[blue]Turn changed: {previous_turn} -> {current_turn}[/blue]")
        except Exception as move_error:
            console.print(f"[yellow]Error getting moves list: {move_error}[/yellow]")
            console.print(f"[red]Move error details: {type(move_error).__name__}[/red]")
            console.print(f"[red]Traceback: {traceback.format_exc()}[/red]")
        
        # Skip analysis if board state is empty
        if not current_board_state:
            console.print("[yellow]Empty board state detected, waiting...[/yellow]")
            return
        
        # Log the board state difference
        if previous_board_state:
            added = {pos: piece for pos, piece in current_board_state.items() 
                   if pos not in previous_board_state}
            removed = {pos: piece for pos, piece in previous_board_state.items() 
                     if pos not in current_board_state}
            
            if added or removed:
                console.print(f"[dim]Board changes - Added: {len(added)}, Removed: {len(removed)}[/dim]")
        
        # Check for moved pieces if we have a previous state
        if previous_board_state:
            try:
                console.print("[dim]Checking for moved pieces...[/dim]")
                moved = find_moved_pieces(previous_board_state, current_board_state)
                
                # If pieces moved, update last moves and analyze
                if moved:
                    console.print(f"[green]Detected {len(moved)} moved piece(s)[/green]")
                    for old_pos, new_pos, piece in moved:
                        color = "white" if piece.startswith('w') else "black"
                        last_moves[color] = new_pos
                        
                        # Log the move
                        from_alg = convert_numeric_to_algebraic(old_pos)
                        to_alg = convert_numeric_to_algebraic(new_pos)
                        if from_alg and to_alg:
                            move_text = f"{color.capitalize()}: {from_alg}{to_alg}"
                        console.print(move_text, style="blue" if color == "white" else "red")
                        if settings_window:
                            settings_window.add_move(move_text)
                    
                    # Only analyze if it's our turn (after opponent moved)
                    # This depends on which side the user is playing
                    our_turn = ((args.side == "white" and current_turn == "white") or 
                               (args.side == "black" and current_turn == "black"))
                    
                    console.print(f"[dim]Our side: {args.side}, Current turn: {current_turn}, Should analyze: {our_turn}[/dim]")
                    
                    if our_turn:
                        console.print("[blue]It's our turn - analyzing position for best move[/blue]")
                        analyze_and_display_best_move(driver, current_board_state)
                    else:
                        console.print("[dim]Waiting for opponent to move...[/dim]")
            except Exception as move_error:
                console.print(f"[yellow]Error processing moves: {move_error}[/yellow]")
                console.print(f"[red]Move processing error details: {type(move_error).__name__}[/red]")
                console.print(f"[red]Traceback: {traceback.format_exc()}[/red]")
        
        # Update previous state for next comparison
        previous_board_state = current_board_state
        
        # Reset crash counter on successful execution
        crash_count = 0
        
    except StaleElementReferenceException:
        crash_count += 1
        console.print(f"[yellow]Stale element reference error (crash #{crash_count}) - board likely changed during processing[/yellow]")
        # Don't update previous_board_state here to retry on next iteration
    except NoSuchElementException:
        crash_count += 1
        console.print(f"[yellow]Element not found error (crash #{crash_count}) - board structure may have changed[/yellow]")
        # Reset previous state to force fresh analysis
        previous_board_state = {}
    except Exception as e:
        crash_count += 1
        console.print(f"[bold red]Error in monitor_board_state (crash #{crash_count}): {e}[/bold red]")
        console.print(f"[red]Error type: {type(e).__name__}[/red]")
        console.print(f"[red]Traceback: {traceback.format_exc()}[/red]")
        # Don't crash the main loop


def clean_up_visual_elements(driver):
    """Remove all custom visual elements from the board"""
    try:
        script = """
        (function() {
            // Remove custom arrows
            const arrowsSvg = document.querySelector('svg.arrows');
            if (arrowsSvg) {
                const arrows = arrowsSvg.querySelectorAll('.custom-arrow');
                arrows.forEach(arrow => arrow.remove());
            }
            
            // Remove custom highlights
            const highlights = document.querySelectorAll('.custom-highlight');
            highlights.forEach(highlight => highlight.remove());
            
            return true;
        })();
        """
        driver.execute_script(script)
    except Exception as e:
        console.print(f"[yellow]Error cleaning visual elements: {e}[/yellow]")

def watch_settings_file(settings_path):
    """Watch the settings file for changes and update args accordingly"""
    global args, legit_mode
    
    if not os.path.exists(settings_path):
        console.print(f"[yellow]Settings file not found: {settings_path}[/yellow]")
        return
        
    console.print(f"[green]Watching settings file: {settings_path}[/green]")
    last_modified = os.path.getmtime(settings_path)
    
    while True:
        try:
            time.sleep(0.5)
            
            if not os.path.exists(settings_path):
                continue
                
            current_modified = os.path.getmtime(settings_path)
            
            if current_modified > last_modified:
                console.print("[blue]Settings file changed, updating parameters...[/blue]")
                last_modified = current_modified
                
                # Read new settings
                with open(settings_path, 'r') as f:
                    config = yaml.safe_load(f)
                
                # Store previous values to detect changes
                previous_enabled = args.enabled
                previous_legit = legit_mode.enabled if hasattr(legit_mode, 'enabled') else False
                
                # Update args
                args.enabled = config.get('enabled', args.enabled)
                args.side = config.get('side', args.side)
                args.elo = config.get('elo', args.elo)
                args.arrow_color = config.get('arrow_color', args.arrow_color)
                
                # Update legit mode settings
                legit_mode.enabled = config.get('legit_mode', legit_mode.enabled)
                legit_mode.blunder_chance = config.get('blunder_chance', legit_mode.blunder_chance)
                legit_mode.suboptimal_chance = config.get('suboptimal_chance', legit_mode.suboptimal_chance)
                legit_mode.skill_variance = config.get('skill_variance', legit_mode.skill_variance)
                legit_mode.consistency = config.get('consistency', legit_mode.consistency)
                legit_mode.elo_variance = config.get('elo_variance', legit_mode.elo_variance)
                
                # Convert hex color to rgba if needed
                if args.arrow_color.startswith('#'):
                    r = int(args.arrow_color[1:3], 16)
                    g = int(args.arrow_color[3:5], 16)
                    b = int(args.arrow_color[5:7], 16)
                    args.arrow_color = f"rgba({r}, {g}, {b}, 0.8)"
                
                # Clear arrows if disabled state changed
                if previous_enabled != args.enabled and not args.enabled:
                    console.print("[yellow]Analysis disabled, clearing visual elements...[/yellow]")
                
                # Log legit mode state change
                if previous_legit != legit_mode.enabled:
                    mode_state = "ENABLED" if legit_mode.enabled else "DISABLED"
                    console.print(f"[green]Legit mode {mode_state}[/green]")
                
                console.print(f"[green]Updated settings: enabled={args.enabled}, side={args.side}, elo={args.elo}, legit_mode={legit_mode.enabled}[/green]")
        
        except Exception as e:
            console.print(f"[yellow]Error watching settings file: {e}[/yellow]")


def wait_for_page_load(driver, timeout=10):
    """Wait for the chess board to load"""
    try:
        WebDriverWait(driver, timeout).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, 'wc-chess-board.board'))
        )
        return True
    except TimeoutException:
        console.print("[red]Timed out waiting for chess board to load[/red]")
        return False

def handle_keyboard_input(driver):
    """Handle keyboard input for changing settings through browser"""
    global args, legit_mode
    
    try:
        # Create an ActionChains object
        actions = ActionChains(driver)
        
        # Add key event listeners to the document
        script = """
        document.addEventListener('keydown', function(e) {
            if (e.key === 'v') {
                document.dispatchEvent(new CustomEvent('sideChange'));
            } else if (e.key === 'b') {
                document.dispatchEvent(new CustomEvent('legitModeToggle'));
            }
        });
        """
        driver.execute_script(script)
        
        # Add custom event listeners
        script = """
        document.addEventListener('sideChange', function() {
            window.chessSideChanged = true;
        });
        document.addEventListener('legitModeToggle', function() {
            window.legitModeToggled = true;
        });
        """
        driver.execute_script(script)
        
    except Exception as e:
        console.print(f"[red]Error setting up keyboard handlers: {e}[/red]")

def check_browser_events(driver):
    """Check and handle browser events"""
    global args, legit_mode
    
    try:
        # Check for side change event
        side_changed = driver.execute_script("return window.chessSideChanged === true;")
        if side_changed:
            args.side = 'black' if args.side == 'white' else 'white'
            console.print(f"[green]Switched analysis side to: {args.side}[/green]")
            args.save_config()
            driver.execute_script("window.chessSideChanged = false;")
        
        # Check for legit mode toggle event
        legit_toggled = driver.execute_script("return window.legitModeToggled === true;")
        if legit_toggled:
            args.legit_mode = not args.legit_mode
            legit_mode.enabled = args.legit_mode
            console.print(f"[green]Legit mode {'enabled' if args.legit_mode else 'disabled'}[/green]")
            args.save_config()
            driver.execute_script("window.legitModeToggled = false;")
            
    except Exception as e:
        console.print(f"[yellow]Error checking browser events: {e}[/yellow]")

def main():
    global crash_count, legit_mode
    crash_count = 0
    max_crashes = 5
        
    legit_mode.enabled = args.legit_mode
    legit_mode.blunder_chance = args.blunder_chance
    legit_mode.suboptimal_chance = args.suboptimal_chance

    def initialize_driver():
        """Initialize Chrome driver with custom options"""
        edge_options = webdriver.EdgeOptions()
        # Prevent Edge from asking to sign in and improve automation
        edge_options.add_argument('--no-sandbox')
        edge_options.add_argument('--disable-dev-shm-usage')
        edge_options.add_argument('--disable-blink-features=AutomationControlled')
        edge_options.add_argument('--disable-extensions')
        edge_options.add_argument('--disable-notifications')
        edge_options.add_argument('--disable-popup-blocking')
        edge_options.add_argument('--ignore-certificate-errors')
        edge_options.add_argument('--ignore-ssl-errors')
        # Add experimental options to prevent detection
        edge_options.add_experimental_option('excludeSwitches', ['enable-automation'])
        edge_options.add_experimental_option('useAutomationExtension', False)
        
        try:
            driver = webdriver.Edge(options=edge_options)
            
            # Open a blank page first
            driver.get('about:blank')
            time.sleep(2)  # Short wait for browser to stabilize
            
            # Now open chess.com
            print("Opening chess.com - please log in if needed...")
            driver.get('https://www.chess.com/play/computer')
            
            # Wait for user interaction
            input("Press Enter after you have logged in to continue...")
            
            return driver
        except Exception as e:
            console.print(f"[red]Error initializing Chrome driver: {e}[/red]")
            return None

    # Log configuration
    console.print(f"[bold]Starting chess analyzer with:[/bold]")
    console.print(f"Analysis Enabled: {args.enabled}")
    console.print(f"Playing Side: {args.side}")
    console.print(f"Engine ELO: {args.elo}")
    console.print(f"Arrow Color: {args.arrow_color}")
    console.print(f"Legit Mode: {legit_mode.enabled}")
    if legit_mode.enabled:
        console.print(f"  - Blunder Chance: {legit_mode.blunder_chance*100:.1f}%")
        console.print(f"  - Suboptimal Move Chance: {legit_mode.suboptimal_chance*100:.1f}%")
    
    if hasattr(args, 'settings_file') and args.settings_file:
        settings_thread = threading.Thread(
            target=watch_settings_file, 
            args=(args.settings_file,),
            daemon=True
        )
        settings_thread.start()
        console.print(f"[blue]Settings watcher thread started[/blue]")

    # Initialize the driver with better error handling
    driver = initialize_driver()
    if not driver:
        console.print("[red]Failed to initialize Chrome driver[/red]")
        return
    
    try:
        print("[STARTING] Opening chess.com...")
        driver.get('https://www.chess.com/play/computer')
        
        # Wait for page to load
        print("Waiting for page to load...")
        if not wait_for_page_load(driver):
            print("Chess board not found. Exiting.")
            return
        
        print("Chess board loaded successfully!")
        
        # Add keyboard shortcut handler for cleaning up visual elements
        script = """
        document.addEventListener('keydown', function(e) {
            // Press 'c' to clean up visual elements
            if (e.key === 'c') {
                // Clean up function
                const arrowsSvg = document.querySelector('svg.arrows');
                if (arrowsSvg) {
                    const arrows = arrowsSvg.querySelectorAll('.custom-arrow');
                    arrows.forEach(arrow => arrow.remove());
                }
                
                const highlights = document.querySelectorAll('.custom-highlight');
                highlights.forEach(highlight => highlight.remove());
            }
        });
        """
        driver.execute_script(script)
        
        # Set up keyboard handlers
        handle_keyboard_input(driver)
        
        print("Ready! Press 'c' at any time to clear visual elements.")
        print("Monitoring game state...")
        
        # Track consecutive timeouts separately from other errors
        timeout_count = 0
        consecutive_errors = 0
        last_error_type = None
        last_error_time = time.time()
        refresh_cooldown = 30  # Seconds between page refreshes
        
        # Main monitoring loop with improved error handling
        while True:
            try:
                monitor_board_state(driver)
                
                # Reset consecutive error counter on successful execution
                consecutive_errors = 0
                last_error_type = None
                
            except StaleElementReferenceException as se:
                consecutive_errors += 1
                current_time = time.time()
                error_msg = f"Stale element reference error (#{consecutive_errors}): {str(se)}"
                console.print(f"[yellow]{error_msg}[/yellow]")
                
                last_error_type = "stale_element"
                
                # If we've had too many consecutive errors of same type, consider refresh
                if consecutive_errors >= 3 and (current_time - last_error_time) > refresh_cooldown:
                    console.print("[bold yellow]Multiple stale element errors detected. Attempting to refresh page...[/bold yellow]")
                    try:
                        driver.refresh()
                        time.sleep(2)  # Wait for refresh
                        wait_for_page_load(driver)
                        consecutive_errors = 0
                        last_error_time = current_time
                    except Exception as refresh_error:
                        console.print(f"[red]Error refreshing: {refresh_error}[/red]")
                        
            except TimeoutException as te:
                timeout_count += 1
                console.print(f"[yellow]Timeout error (#{timeout_count}): {str(te)}[/yellow]")
                
                # If we have too many timeouts, refresh the page
                if timeout_count >= 3:
                    console.print("[bold yellow]Multiple timeouts detected. Attempting to refresh page...[/bold yellow]")
                    try:
                        driver.refresh()
                        time.sleep(2)  # Wait for refresh
                        wait_for_page_load(driver)
                        timeout_count = 0
                    except Exception as refresh_error:
                        console.print(f"[red]Error refreshing: {refresh_error}[/red]")
                
            except Exception as e:
                crash_count += 1
                console.print(f"[bold red]Error in monitoring loop (count: {crash_count}): {str(e)}[/bold red]")
                console.print(f"[red]Error type: {type(e).__name__}[/red]")
                
                # Print full traceback for better debugging
                console.print(f"[dim red]{traceback.format_exc()}[/dim red]")
                
                # If we've had too many consecutive errors or total crashes is high, restart the driver
                if crash_count >= max_crashes:
                    console.print("[bold yellow]Too many errors detected. Refreshing page...[/bold yellow]")
                    try:
                        driver.refresh()
                        time.sleep(2)  # Wait for refresh
                        wait_for_page_load(driver)
                        crash_count = 0
                    except Exception as refresh_error:
                        console.print(f"[red]Error refreshing: {refresh_error}[/red]")
                        
                        # If refresh fails, try a more aggressive approach
                        if crash_count >= max_crashes + 2:
                            console.print("[bold red]Critical error threshold reached. Reopening chess.com...[/bold red]")
                            try:
                                driver.get('https://www.chess.com/play/computer')
                                time.sleep(3)  # Wait longer for complete reload
                                wait_for_page_load(driver)
                                crash_count = 0
                                previous_board_state = {}  # Reset board state
                            except Exception as reopen_error:
                                console.print(f"[red]Error reopening chess.com: {reopen_error}[/red]")
            
            # Check for browser events instead of terminal input
            check_browser_events(driver)
            
            # Use a short sleep to avoid CPU overload but maintain responsiveness
            time.sleep(0.2)
            
    except KeyboardInterrupt:
        console.print("[yellow]Keyboard interrupt detected. Cleaning up...[/yellow]")
    except Exception as e:
        console.print(f"[bold red]An error occurred in main loop: {str(e)}[/bold red]")
        # Print full traceback for better debugging
        console.print(f"[dim red]{traceback.format_exc()}[/dim red]")
    finally:
        if driver:
            try:
                # Clean up visual elements before exiting
                clean_up_visual_elements(driver)
                
                # Clean up the chess engine
                if engine:
                    engine.quit()
                
                console.print("[green]Engine and visual elements cleaned up.[/green]")
                console.print("[yellow]Keeping browser open. Close manually when done.[/yellow]")
            except Exception as e:
                console.print(f"[red]Error during cleanup: {e}[/red]")

def launch_settings_window():
    """Launch the settings GUI in a separate thread"""
    from settings_gui import create_settings_window
    
    def run_gui():
        app = create_settings_window(config=args, legit_mode=legit_mode)
        app.root.mainloop()
    
    settings_thread = threading.Thread(target=run_gui, daemon=True)
    settings_thread.start()

def create_settings_window():
    global settings_window, args, legit_mode
    root = tk.Tk()
    settings_window = ChessSettingsGUI(root, args, legit_mode)
    return root

if __name__ == "__main__":
    # Create settings window
    root = create_settings_window()
    
    # Start the monitoring in a separate thread
    monitor_thread = threading.Thread(target=main, daemon=True)
    monitor_thread.start()
    
    # Run the GUI main loop
    root.mainloop()