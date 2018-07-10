
"""A collection of definitions of ANSI control codes for terminals.
Things defined here (or returned from functions) are strings that should be printed to the terminal.
"""

import random

ESC = "\033" # escape character for terminal
CSI = ESC + "[" # Control Sequence Initiator

# Clearing
CLEAR = CSI + "H" + CSI + "2J" # Clears screen. Returns cursor to (1,1).
CLEAR_LINE = CSI + "2K" # Clears whole line, doesn't move cursor.

# Cursor 
SAVE_CURSOR = CSI + "s"
LOAD_CURSOR = CSI + "u"
TYPE_CURSOR = CSI + "6n" # Writes CSI <row> ";" <column> "R" to stdin
def set_cursor(x=None, y=None):
	"""Set cursor to (column, row). If either axis omitted or None, it doesn't move."""
	tostr = lambda val: '' if val is None else str(val)
	return "{CSI}{y};{x}H".format(CSI=CSI, x=tostr(x), y=tostr(y))

# Cursor Movement
UP, DOWN, LEFT, RIGHT = "ABCD"
def move_cursor(direction, steps=1):
	"""Takes a direction UP, DOWN, LEFT or RIGHT, and the amount to move."""
	return CSI + str(steps) + direction

# These shortcuts are for simple use and backwards compatibility
CURSOR_UP = move_cursor(UP)
CURSOR_DOWN = move_cursor(DOWN)
CURSOR_LEFT = move_cursor(LEFT)
CURSOR_RIGHT = move_cursor(RIGHT)

SCROLL_UP = CSI + "S"
SCROLL_DOWN = CSI + "D"

# Formatting 
BOLD = CSI + "1m"
UNFORMAT = CSI + "0m"
FORECOLOUR = lambda colour: CSI + "3" + str(colour) + "m"
BACKCOLOUR = lambda colour: CSI + "4" + str(colour) + "m"
INVERTCOLOURS = CSI + "7m"

BLACK  = "0"
RED    = "1"
GREEN  = "2"
YELLOW = "3"
BLUE   = "4"
PURPLE = "5"
CYAN   = "6"
WHITE  = "7"
DEFAULT_COLOUR = "9"

# 256-colour
LOW_CONTRAST_COLOURS = {0, 8, 16, 17, 18, 19, 52, 232, 233, 234, 235, 236, 237, 238, 239}

def colour_256(n):
	return '8;5;{}'.format(n)

def random_colour_256(seed=None):
	rng = random if seed is None else random.Random(seed)
	return colour_256(rng.choice(list(set(range(256)) - LOW_CONTRAST_COLOURS)))

