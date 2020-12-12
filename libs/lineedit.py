
import logging
import os
import signal
import string
import sys
import re

import escapes
from termhelpers import TermAttrs, termsize

__REQUIRES__ = ['escapes', 'termhelpers']

PY3 = not isinstance('', bytes)
if PY3:
	unicode = str


def get_termattrs(fd=None, **kwargs):
	"""Return the TermAttrs object to use. Passes args to term attrs.
	Note it is a modification of the termios settings at the time of this call.
	"""
	# we don't really want full raw mode, just use what's already set with just enough
	# for what we want
	import termios as t
	if fd is None:
		fd = sys.stdout
	if hasattr(fd, 'fileno'):
		fd = fd.fileno()
	return TermAttrs.modify(
		(t.IGNPAR|t.ICRNL, 0, 0, 0),
		(0, 0, 0, t.ECHO|t.ICANON|t.IEXTEN),
		fd=fd, **kwargs
	)


class LoggingHandler(logging.Handler):
	"""A logging Handler which outputs to the screen in a controlled manner.
	Takes a LineEditing instance to output to.
	Can be used as a context manager, replacing all handlers in the root logger on entry
	and restoring them on exit.
	"""
	def __init__(self, lineedit):
		self.lineedit = lineedit
		super(LoggingHandler, self).__init__()

	def __enter__(self):
		logger = logging.getLogger()
		self.old_handlers = logger.handlers
		logger.handlers = [self]
		return self

	def __exit__(self, *exc_info):
		logger = logging.getLogger()
		logger.handlers = self.old_handlers

	def emit(self, record):
		msg = self.format(record)
		self.lineedit.write(msg)


class HiddenCursor(object):
	"""Context manager that hides the cursor.
	Assumes sys.stdout is a tty.
	"""
	def __enter__(self):
		sys.stdout.write('\x1b[?25l')
	def __exit__(self, *exc_info):
		sys.stdout.write('\x1b[?25h')


def gevent_read_fn(input_file=sys.stdin):
	"""Common case of a custom read fn, that reads from stdin but plays nice with gevent."""
	from gevent.select import select
	while True:
		r, w, x = select([input_file], [], [])
		if input_file in r:
			# work around buffering bug with single-character reading
			return os.read(input_file.fileno(), 1)


class LineEditing(object):
	"""Intended to be used as a context manager, this class segments the screen into
	a display part, and an editing part on the bottom line.
	The line editor will wipe any data on the bottom line of the screen, and only the bottom line.
	"""
	TERMINATORS = {b'\r', b'\n'}
	PRINTABLE = set(string.printable) - {'\r', '\n', '\x0b', '\x0c'}
	CONTEXT_MGRS = [get_termattrs, HiddenCursor]

	active_context_mgrs = []

	head = ''
	tail = ''
	esc_buf = b''

	history = []
	history_pos = 0

	def __init__(self, input_fn=None, input_file=sys.stdin, output=sys.stdout,
	             suppress_nonprinting=True, encoding='utf-8', completion=None, completion_print=True,
	             complete_whole_line=False, gevent_handle_sigint=False):
		"""input_fn overrides the default read function. Alternately, input_file specifies a
		file to read from in the default read function.
		input_fn should take no args.
		output is the file to write to, and should be a tty.
		suppress_nonprinting is default True (set False to disable) and causes any unhandled non-printing characters
			to not be written to output.
		Encoding is the encoding that input is expected to be in.
			Note that input bytes will buffer until a full character can be decoded.
			All intermediate output will be encoded with this encoding.
			Set to None to disable this behaviour and treat all bytes as single characters.
			Strings returned from self.readline() will be bytes if encoding is None, else unicode.
			This option is ignored in python3 - everything is unicode, whether you like it or not.
		completion, if given, should be a callable that takes an input string and return a list of possible completions.
			Results generally should have the input as a prefix, but this is not a hard requirement.
			This function will be called with the current pre-cursor input (back to the first non-word character)
			when the user presses the completion key (tab). Word characters are as per the re module.
			If any results are returned, the given input is replaced with the longest common prefix
			among the results. If only one result is returned, a space is also appended.
			If there are multiple results and the given input is already equal to the longest common prefix,
			and completion_print=True, a list of possible completions is output.
			An iterable may be given instead of a callable - this is equivilent to a completion_fn that returns
			all items from that iterable which start with the input.
		complete_whole_line: If True, all characters before the cursor are passed to the completion function,
			not just the latest word. In this case, the completion function should return (head, completions),
			where head is a static string to leave unchanged, while completions is the list of potential suffixes
			to head to complete as. For example, if you were completing a filepath /foo/ba and the options were
			/foo/bar or /foo/baz, you would return ("/foo/", ["bar", "baz"]).
		gevent_handle_sigint=True: Add some special functionality to work around an issue with KeyboardInterrupt
			and gevent. Note this disables SIGINT from raising, but makes SIGQUIT do so instead.
		"""
		if input_fn:
			self.read = input_fn
		else:
			self.input_file = input_file
		self.output = output
		self.suppress_nonprinting = suppress_nonprinting
		self.encoding = encoding
		self.completion_fn = completion if callable(completion) else complete_from(completion)
		self.completion_print = completion_print
		self.complete_whole_line = complete_whole_line
		self.history = self.history[:] # so we have a unique instance to ourselves
		self._gevent_handle_sigint = gevent_handle_sigint

		# If we're using gevent, the keyboard interrupt handling doesn't work well, we probably
		# won't raise the KeyboardInterrupt in the right greenlet. We work around this by explicitly handling
		# the SIGINT and re-raising in the correct place.
		# We rebind SIGQUIT to raise KeyboardInterrupt for debugging/aborting
		if self._gevent_handle_sigint:
			import gevent
			self._readline_greenlet = None
			def _sigquit(signum, frame):
				raise KeyboardInterrupt
			def _sigint():
				if self._readline_greenlet:
					self._readline_greenlet.kill(KeyboardInterrupt, block=False)
			signal.signal(signal.SIGQUIT, _sigquit)
			gevent.signal_handler(signal.SIGINT, _sigint)

	def read(self):
		"""Read a single character of input, or '' (or EOFError) on EOF.
		This function is overridable to change the way input is read.
		"""
		return self.input_file.read(1)

	def get_width(self):
		columns, rows = termsize()
		return columns

	def print_list(self, items):
		"""A routine for pretty printing a list of items, seperated by at least two spaces,
		taking width into account.
		Right now this is only used by completion printing, but is exposed here for others' convenience.
		"""
		strtype = unicode if self.encoding else bytes
		items = map(strtype, items)
		width = self.get_width()
		lines = []
		sep = strtype('  ')
		for item in items:
			if lines:
				new = lines[-1] + sep + item
				if len(new) <= width:
					lines[-1] = new
					continue
			lines.append(item)
		self.write(strtype('\n').join(lines))

	def refresh(self):
		"""Display current editing line"""
		head = self.head
		tail = self.tail or ' '

		width = self.get_width()
		max_head = width - 2
		if max_head <= 0:
			raise ValueError("Cannot display line: terminal too narrow")

		# if line is too long, strip from left to ensure there's room for cursor at the end
		head = head[-max_head:]
		# if line is still too long, cut off tail
		max_tail = width - len(head)
		assert max_tail >= 2, "logic error: max_tail = {!r}".format(max_tail)
		tail = tail[:max_tail]

		selected, tail = tail[0], tail[1:]
		if self.encoding and not PY3:
			head, tail, selected = [s.encode(self.encoding) for s in (head, tail, selected)]

		self.output.write(
			  escapes.SAVE_CURSOR
			+ escapes.set_cursor(1,999)
			+ escapes.CLEAR_LINE
			+ head
			+ escapes.INVERTCOLOURS + selected + escapes.UNFORMAT
			+ tail
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
			if self._gevent_handle_sigint:
				import gevent
				self._readline_greenlet = gevent.getcurrent()

			while True:

				self.refresh()

				# read input
				c = self.read()
				if isinstance(c, unicode):
					c = c.encode(self.encoding or 'utf-8')
				if not c:
					raise EOFError()
				if c in self.TERMINATORS:
					break
				self.esc_buf += c

				# on partial unicode characters, continue to buffer
				esc_buf = self.esc_buf
				if self.encoding or PY3:
					try:
						esc_buf = self.esc_buf.decode(self.encoding or 'utf-8')
					except UnicodeDecodeError:
						logging.debug("Got partial unicode character {!r}, continuing".format(self.esc_buf))
						continue

				# check for full escape sequence
				if esc_buf in ESCAPE_HANDLERS:
					logging.debug("Got esc handler {!r}".format(esc_buf))
					self.head, self.tail = ESCAPE_HANDLERS[esc_buf](self.head, self.tail, self)
					self.esc_buf = b''
					continue

				# on partial escape sequences, continue to buffer
				if any(sequence.startswith(esc_buf) for sequence in ESCAPE_HANDLERS):
					logging.debug("Buffer {!r} is prefix of at least one esc handler, continuing".format(esc_buf))
					continue

				logging.debug("Buffer {!r} not prefix of any esc handler, stripping and adding".format(esc_buf))

				if self.suppress_nonprinting:
					# filter non-printing chars before we add to main buffer
					# (also allow >128 for non-ascii chars)
					esc_buf = type(esc_buf)().join([
						c for c in esc_buf
						if c in self.PRINTABLE or ord(c) > 128
					])

				# flush escape buffer
				self.head += esc_buf
				self.esc_buf = b''

		except KeyboardInterrupt:
			self.head = ''
			self.tail = ''
			# fall through
		except EOFError:
			if not (self.head or self.tail): raise
			# fall through
		finally:
			if self._gevent_handle_sigint:
				self._readline_greenlet = None

		self.history[0] = self.head + self.tail
		if not self.history[0]: self.history.pop(0)

		ret = self.head + self.tail
		self.head = ''
		self.tail = ''

		if self.encoding and not isinstance(ret, unicode):
			# Some edge cases (eg. ^C) can result in ret being bytes even when decoding should happen.
			# Our code doesn't care because the implict coercion is safe for empty strings and ascii characters,
			# but we want to avoid unexpected behaviour when returning to the caller.
			# If this raises a UnicodeDecodeError, it indicates that there is a logic bug, as non-ascii characters
			# shouldn't be present if ret isn't already a unicode object.
			ret = ret.decode('ascii')

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
		mgrs = [mgr_cls() for mgr_cls in self.CONTEXT_MGRS]
		try:
			for mgr in mgrs:
				mgr.__enter__()
				self.active_context_mgrs.append(mgr)
		except BaseException:
			self.__exit__(sys.exc_info())
			raise

	def __exit__(self, *exc_info):
		while self.active_context_mgrs:
			mgr = self.active_context_mgrs.pop()
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
@escape('\x1b[H')
def home(head, tail, obj):
	return '', head+tail

@escape('\x1bOF')
@escape('\x1b[F')
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

# tab completion
@escape('\t')
def complete(head, tail, obj):
	if not obj.completion_fn:
		return head, tail
	if obj.complete_whole_line:
		new_head, results = obj.completion_fn(head)
		value = ''
	else:
		match = re.search('(.*?)(\S+)$', head, re.UNICODE if obj.encoding else 0)
		if not match:
			return head, tail
		new_head, value = match.groups()
		results = obj.completion_fn(value)
	if not results:
		return head, tail
	if len(results) == 1:
		result, = results
		return new_head + result + ' ', tail
	# find common prefix
	first, rest = results[0], results[1:]
	prefix = ''
	for i, c in enumerate(first):
		if not all(len(s) > i and s[i] == c for s in rest):
			break
		prefix += c
	# if already equal to prefix, print a list
	if new_head + prefix == head and obj.completion_print:
		obj.print_list(results)
	return new_head + prefix, tail

def complete_from(items):
	"""Helper function for completion functions.
	Returns a function which takes an input and returns all items that start with input.
	"""
	def _complete_from(value):
		return [item for item in items if item.startswith(value)]
	return _complete_from

if __name__ == '__main__':
	# basic test
	use_gevent = os.environ.get('GEVENT', '').lower() == 'true'
	editor = LineEditing(
		input_fn=gevent_read_fn if use_gevent else None,
		completion=sys.argv[1:],
		gevent_handle_sigint=use_gevent,
	)
	handler = LoggingHandler(editor)
	handler.setFormatter(logging.Formatter("%(levelname)s:%(name)s:%(message)s"))
	try:
		with editor, handler:
			while True:
				line = editor.readline()
				editor.write(repr(line))
	except EOFError:
		pass
