# Chess.com Analysis Assistant

A Python-based chess analysis tool that helps analyze chess games on chess.com using a graphical interface and automated move suggestions powered by Stockfish engine.

## Features

- Real-time chess position analysis using Stockfish engine
- Customizable engine settings through GUI
- Legit mode for more human-like play
- Visual move suggestions with customizable arrow colors
- Configurable ELO rating
- Support for both White and Black sides

## Requirements

```plaintext
- Python 3.x
- Microsoft Edge WebDriver
- Stockfish chess engine (version 15 or later recommended)
- Required Python packages (install via pip):
  - selenium>=4.0.0
  - rich>=13.0.0
  - chess>=1.9.0
  - python-chess>=1.0.0
  - pyyaml>=6.0
```

## Installation

1. Install the required packages:
```bash
pip install -r requirements.txt
```

2. Install Stockfish chess engine:
   - Windows: 
     - Download Stockfish from the [official website](https://stockfishchess.org/download/)
     - Extract the stockfish.exe
     - Either:
       - Place stockfish.exe in the project directory, or
       - Add stockfish.exe location to your system PATH
       - Place in one of these default locations:
         - C:\stockfish\stockfish-windows-x86-64-avx2.exe
         - C:\Program Files\stockfish\stockfish.exe
         - C:\stockfish\stockfish.exe

   - Linux/Mac:
     - Install via package manager:
       ```bash
       # Ubuntu/Debian
       sudo apt-get install stockfish
       
       # Mac (using Homebrew)
       brew install stockfish
       ```

3. Make sure Microsoft Edge WebDriver is installed and accessible in your system PATH.

## Usage

1. Run the main script:
```bash
python main.py
```

2. The program will:
   - Open chess.com in Microsoft Edge
   - Wait for you to log in (if needed)
   - Start analyzing chess positions using Stockfish
   - Display move suggestions with arrows

3. Settings can be adjusted through the GUI interface:
   - Enable/Disable engine analysis
   - Choose playing side (White/Black)
   - Set ELO rating
   - Customize arrow colors
   - Configure Legit Mode settings

## Controls

- Press 'c' to clear visual elements (arrows)
- Press 'v' to change sides
- Press 'b' to toggle legit mode

## Configuration

Settings are stored in `config.yaml` and can be modified either through the GUI or by directly editing the file:

```yaml
arrow_color: '#ffff80'
blunder_chance: 0.15
elo: 2000
enabled: true
legit_mode: false
side: white
suboptimal_chance: 0.35
```

## Legit Mode

When enabled, Legit Mode makes the engine play more human-like by:
- Occasionally making small blunders (configurable chance)
- Sometimes choosing suboptimal moves
- Varying play strength based on settings

## Troubleshooting

If you get errors about Stockfish not being found:
1. Verify Stockfish is properly installed
2. Check if Stockfish executable is in your system PATH
3. Try placing stockfish.exe directly in the project directory
4. Make sure you have the correct version for your system architecture (32/64 bit)
