
"""A collection of definitions of ANSI control codes for terminals"""

ESC = "\033" # escape character for terminal
CSI = ESC + "[" # Control Sequence Initiator

CLEAR = CSI + "H" + CSI + "2J" # Clears screen. Returns cursor to (1,1).
CLEAR_LINE = CSI + "2K"

# Cursor 
SAVE_CURSOR = CSI + "s"
LOAD_CURSOR = CSI + "u"
TYPE_CURSOR = CSI + "6n" # Writes CSI <row> ";" <column> "R" to stdin
SET_CURSOR = lambda x,y: CSI + str(y) + ";" + str(x) + "H" # Sets cursor to (column, row)

CURSOR_UP = CSI + "A"
CURSOR_DOWN = CSI + "B"
CURSOR_RIGHT = CSI + "C"
CURSOR_LEFT = CSI + "D"

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
