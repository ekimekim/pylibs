
"""A collection of definitions of ANSI control codes for terminals.
Things defined here (or returned from functions) are strings that should be printed to the terminal.
"""

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
	return "{CSI}{y};{x}H".format(CSI=CSI, x=x, y=y)

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
