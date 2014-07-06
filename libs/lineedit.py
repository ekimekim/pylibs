
import sys
import string

import escapes
from termhelpers import TermAttrs


def get_termattrs(fd=None, **kwargs):
	"""Return the TermAttrs object to use. Passes args to term attrs.
	Note it is a modification of the termios settings at the time of this call.
	"""
	# we don't really want full raw mode, just use what's already set with just enough
	# for what we want
	import termios as t
	if file is None:
		fd = sys.stdout
	if hasattr(fd, 'fileno'):
		fd = fd.fileno()
	return TermAttrs.modify(
		(t.IGNPAR|t.ICRNL, 0, 0, 0),
		(0, 0, 0, t.ECHO|t.ICANON|t.IEXTEN),
		fd=fd, **kwargs
	)


class HiddenCursor(object):
	"""Context manager that hides the cursor.
	Assumes sys.stdout is a tty.
	"""
	def __enter__(self):
		sys.stdout.write('\x1b[?25l')
	def __exit__(self, *exc_info):
		sys.stdout.write('\x1b[?25h')


class LineEditing(object):
	"""Intended to be used as a context manager, this class segments the screen into
	a display part, and an editing part on the bottom line.
	The line editor will wipe any data on the bottom line of the screen, and only the bottom line.
	"""
	TERMINATORS = {'\r', '\n'}
	CONTEXT_MGRS = [get_termattrs, HiddenCursor]

	active_context_mgrs = []

	head = ''
	tail = ''
	esc_buf = ''

	history = []
	history_pos = 0

	def __init__(self, input_fn=None, input_file=sys.stdin, output=sys.stdout, suppress_nonprinting=True):
		"""input_fn overrides the default read function. Alternately, input_file specifies a
		file to read from in the default read function.
		input_fn should take no args.
		output is the file to write to, and should be a tty.
		suppress_nonprinting is default True (set False to disable) and causes any unhandled non-printing characters
		to not be written to output.
		"""
		if input_fn:
			self.read = input_fn
		else:
			self.input_file = input_file
		self.output = output
		self.suppress_nonprinting = suppress_nonprinting
		self.history = self.history[:] # so we have a unique instance to ourselves

	def read(self):
		"""Read a single character of input, or '' (or EOFError) on EOF.
		This function is overridable to change the way input is read.
		"""
		return self.input_file.read(1)

	def refresh(self):
		"""Display current editing line"""
		tail = self.tail or ' '
		self.output.write(
			  escapes.SAVE_CURSOR
			+ escapes.SET_CURSOR(1,999)
			+ escapes.CLEAR_LINE
			+ self.head
			+ escapes.INVERTCOLOURS + tail[0] + escapes.UNFORMAT
			+ tail[1:]
			+ escapes.LOAD_CURSOR
		)
		self.output.flush()

	def readline(self):
		"""Reads a line of input with line editing.
		Returns after reading a newline, or an EOF.
		If no text was written and EOF was recieved, raises EOFError,
		otherwise returns ''.
		"""

		self.history.insert(0, '')
		self.history_pos = 0

		try:
			while True:

				self.refresh()

				# read input
				c = self.read()
				if not c:
					raise EOFError()
				if c in self.TERMINATORS:
					break
				self.esc_buf += c

				# check for full escape sequence
				if self.esc_buf in ESCAPE_HANDLERS:
					self.head, self.tail = ESCAPE_HANDLERS[self.esc_buf](self.head, self.tail, self)
					self.esc_buf = ''

				# on partial escape sequences, continue without action
				if any(sequence.startswith(self.esc_buf) for sequence in ESCAPE_HANDLERS):
					continue

				if self.suppress_nonprinting:
					# filter non-printing chars before we add to main buffer
					# (also allow >128 for non-ascii chars)
					self.esc_buf = filter(lambda c: c in string.printable or ord(c) > 128, self.esc_buf)

				# flush escape buffer
				self.head += self.esc_buf
				self.esc_buf = ''

		except KeyboardInterrupt:
			self.head = ''
			self.tail = ''
			# fall through
		except EOFError:
			if not (self.head or self.tail): raise
			# fall through

		self.history[0] = self.head + self.tail
		if not self.history[0]: self.history.pop(0)

		ret = self.head + self.tail
		self.head = ''
		self.tail = ''
		return ret

	def write(self, s):
		"""Display a string in the main display section of the screen.
		This method will automatically append a newline.
		Due to technical limitations, strings cannot be written without appending a newline.
		"""
		self.output.write(escapes.CLEAR_LINE + s + '\n')
		self.refresh()

	def __enter__(self):
		if self.active_context_mgrs:
			return # allow re-entrance
		for mgr_cls in self.CONTEXT_MGRS:
			mgr = mgr_cls()
			self.active_context_mgrs.append(mgr)
			mgr.__enter__()

	def __exit__(self, *exc_info):
		while self.active_context_mgrs:
			mgr = self.context_mgrs.pop()
			mgr.__exit__(*exc_info)


# Register escape sequences and handlers
# Handlers should take (head, tail, obj) and return new (head, tail)
# obj is provided to allow for more complex actions like mutating the esc_buf or implementing history.
# TODO come up with a nice way to contain this in the class (this also fixes the obj hack)

ESCAPE_HANDLERS = {}

def escape(*matches):
	def _escape(fn):
		for match in matches:
			ESCAPE_HANDLERS[match] = fn
		return fn
	return _escape


@escape('\x1b[D')
def left(head, tail, obj):
	if not head: return head, tail
	return head[:-1], head[-1] + tail

@escape('\x1b[C')
def right(head, tail, obj):
	if not tail: return head, tail
	return head + tail[0], tail[1:]

@escape('\x7f')
def backspace(head, tail, obj):
	return head[:-1], tail

@escape('\x1b[3~')
def delete(head, tail, obj):
	return head, tail[1:]

@escape('\x1bOH')
def home(head, tail, obj):
	return '', head+tail

@escape('\x1bOF')
def end(head, tail, obj):
	return head+tail, ''

@escape('\04') # ^D
def eof(head, tail, obj):
	raise EOFError()

# history
@escape('\x1b[A')
def up(head, tail, obj):
	if obj.history_pos >= len(obj.history) - 1:
		return head, tail
	if obj.history_pos == 0:
		obj.history[0] = head + tail
	obj.history_pos += 1
	return obj.history[obj.history_pos], ''

@escape('\x1b[B')
def down(head, tail, obj):
	if obj.history_pos <= 0:
		return head, tail
	obj.history_pos -= 1
	return obj.history[obj.history_pos], ''

