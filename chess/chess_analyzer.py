import argparse
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import NoSuchElementException, TimeoutException, StaleElementReferenceException
from rich.console import Console
import time
import chess
import chess.engine
import os
import re
import sys
import subprocess
import json
import threading

# Parse command line arguments
def parse_arguments():
    parser = argparse.ArgumentParser(description='Chess Game Analyzer')
    parser.add_argument('--enabled', type=str, default='True', help='Enable or disable analysis')
    parser.add_argument('--side', type=str, default='white', choices=['white', 'black'], help='Which side you are playing')
    parser.add_argument('--elo', type=int, default=2000, help='Engine ELO rating (0-3200)')
    parser.add_argument('--arrow-color', type=str, default='#0080FF', help='Color for move arrows (hex format)')
    parser.add_argument('--settings-file', type=str, help='Path to the settings JSON file')
    
    args = parser.parse_args()
    
    # Convert string to boolean for enabled
    args.enabled = args.enabled.lower() == 'true'
    
    # Validate ELO range
    args.elo = max(0, min(3200, args.elo))
    
    # Convert hex color to rgba
    if args.arrow_color.startswith('#'):
        r = int(args.arrow_color[1:3], 16)
        g = int(args.arrow_color[3:5], 16)
        b = int(args.arrow_color[5:7], 16)
        args.arrow_color = f"rgba({r}, {g}, {b}, 0.8)"
    
    return args

# Initialize rich console
console = Console()

# Global variables
previous_board_state = {}
current_turn = "white"  # Track whose turn it is
last_moves = {"white": None, "black": None}
evaluation_score = 0.0  # Track the current evaluation
args = parse_arguments()  # Get command line arguments

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
            
            // Remove any existing custom arrows
            const existingArrows = arrowsSvg.querySelectorAll('.custom-arrow');
            existingArrows.forEach(a => a.remove());
            
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
            
            // Add the arrow elements to the SVG
            arrowsSvg.appendChild(arrowShaft);
            arrowsSvg.appendChild(arrowHead);
            
            return true;
        }})();
        """
        driver.execute_script(script)
        return True
    except Exception as e:
        console.print(f"[yellow]Error creating arrow: {e}[/yellow]")
        return False

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
    """Get the best move from the engine with error handling"""
    global evaluation_score
    
    if not engine or not board:
        return None, 0.0
    
    try:
        # Set time limit for analysis
        limit = chess.engine.Limit(time=time_limit)
        
        # Get best move and info
        result = engine.analyse(board, limit)
        moves = result.get("pv", [])
        best_move = moves[0] if moves else None
        
        # Get evaluation score
        score = result.get("score")
        if score:
            # Convert score to decimal value for white's perspective
            try:
                # First check if it's a mate score
                if hasattr(score.white(), 'mate') and score.white().mate() is not None:
                    mate_value = score.white().mate()
                    if mate_value > 0:
                        evaluation_score = 9.9  # Positive mate
                    else:
                        evaluation_score = -9.9  # Negative mate (being mated)
                else:
                    # Regular evaluation score in centipawns
                    evaluation_score = score.white().score() / 100
            except Exception as e:
                console.print(f"[yellow]Error processing score: {e}[/yellow]")
                # Default to previous evaluation if there's an error
        
        # If no best move found, try getting top 3 moves with different approach
        if not best_move:
            console.print("[yellow]No best move found in primary analysis, trying alternative...[/yellow]")
            # Try a different approach - just use search instead of analyse
            result = engine.play(board, limit)
            if result and result.move:
                best_move = result.move
                console.print("[green]Alternative move found![/green]")
        
        # Send evaluation to C# application
        send_evaluation(evaluation_score)
        
        return best_move, evaluation_score
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
                            console.print(f"{color.capitalize()} moved: {from_alg} -> {to_alg}", 
                                         style="blue" if color == "white" else "red")
                    
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
    global args
    
    if not os.path.exists(settings_path):
        console.print(f"[yellow]Settings file not found: {settings_path}[/yellow]")
        return
        
    console.print(f"[green]Watching settings file: {settings_path}[/green]")
    last_modified = os.path.getmtime(settings_path)
    
    while True:
        try:
            time.sleep(0.5)  # Check more frequently (every half second)
            
            if not os.path.exists(settings_path):
                continue
                
            current_modified = os.path.getmtime(settings_path)
            
            if current_modified > last_modified:
                console.print("[blue]Settings file changed, updating parameters...[/blue]")
                last_modified = current_modified
                
                # Read new settings
                with open(settings_path, 'r') as f:
                    settings = json.load(f)
                
                # Store previous values to detect changes
                previous_enabled = args.enabled
                
                # Update args
                args.enabled = settings.get('enabled', args.enabled)
                args.side = settings.get('side', args.side)
                args.elo = settings.get('elo', args.elo)
                args.arrow_color = settings.get('arrow_color', args.arrow_color)
                
                # Convert hex color to rgba if needed
                if args.arrow_color.startswith('#'):
                    r = int(args.arrow_color[1:3], 16)
                    g = int(args.arrow_color[3:5], 16)
                    b = int(args.arrow_color[5:7], 16)
                    args.arrow_color = f"rgba({r}, {g}, {b}, 0.8)"
                
                # Clear arrows if disabled state changed
                if previous_enabled != args.enabled and not args.enabled:
                    console.print("[yellow]Analysis disabled, clearing visual elements...[/yellow]")
                    # Send a message that will be handled by monitor_board_state to clean up visuals
                    # We'll implement this handler in the monitor_board_state function
                
                console.print(f"[green]Updated settings: enabled={args.enabled}, side={args.side}, elo={args.elo}[/green]")
        
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

def main():
    global crash_count
    crash_count = 0
    max_crashes = 5
    
    # Import traceback for better error reporting
    import traceback
    
    # Set up Chrome WebDriver with additional error handling
    options = webdriver.ChromeOptions()
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--start-maximized')
    options.add_argument('--disable-notifications')
    
    # Add user agent to avoid detection
    options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')
    
    # Log configuration
    console.print(f"[bold]Starting chess analyzer with:[/bold]")
    console.print(f"Analysis Enabled: {args.enabled}")
    console.print(f"Playing Side: {args.side}")
    console.print(f"Engine ELO: {args.elo}")
    console.print(f"Arrow Color: {args.arrow_color}")
    
    if hasattr(args, 'settings_file') and args.settings_file:
        settings_thread = threading.Thread(
            target=watch_settings_file, 
            args=(args.settings_file,),
            daemon=True
        )
        settings_thread.start()


        console.print(f"[blue]Settings watcher thread started[/blue]")
    # Initialize the driver with better error handling
    driver = None
    try:
        console.print("[dim]Initializing Chrome WebDriver...[/dim]")
        driver = webdriver.Chrome(options=options)
    except Exception as driver_error:
        console.print(f"[bold red]Failed to initialize Chrome WebDriver: {driver_error}[/bold red]")
        console.print(f"[red]Error details: {traceback.format_exc()}[/red]")
        console.print("[yellow]Make sure Chrome is installed and webdriver is compatible.[/yellow]")
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

if __name__ == "__main__":
    main()


    # legit mode (random blunders (not too severe), random (alt best moves)) (legitMode = on/off)
    # add info icon to explain
    # add status (running, paused, off)
    # bordering piece and where to move
