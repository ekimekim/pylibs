import termios
import sys
from itertools import count


class TermAttrs(object):
	def __init__(self, attrs, fd=None, when=termios.TCSANOW):
		"""A context manager for changing terminal attrs.
		fd defaults to stdin.
		attrs must be a 7-element iterable as taken by tcsetattr.

		Note: context manager is not reenterant wrt the same instance.
		"""
		self.attrs = attrs
		self.fd = fd if fd is not None else sys.stdin.fileno()
		self.when = when

	@classmethod
	def modify(include=(0,0,0,0), exclude=(0,0,0,0), fd=None, *args, **kwargs):
		"""Alternate creation function, allowing you to base changes off current term attrs.
		include and exclude should be 4-tuples of (iflag, oflag, cflag, lflag).
		All values in include will be set.
		All values in exclude will be unset.
		All other values will be unchanged from current values.
		Other args are passed though to TermAttrs.__init__
		"""
		if fd is None: fd = sys.stdin.fileno()
		attrs = termios.tcgetattr(fd)
		for i, e, index in zip(include, exclude, count()):
			attrs[index] |= include
			attrs[index] &= ~exclude
		return TermAttrs(attrs, fd, *args, **kwargs)

	@classmethod
	def raw(cls, *args, **kwargs):
		"""Shortcut method for specifying attrs for "raw mode" (see termios(3))"""
		t = termios
		return cls.modify(
			(0, 0, t.CS8, 0),
			(t.IGNBRK|t.BRKINT|t.PARMRK|t.ISTRIP|t.INLCR|t.IGNCR|t.IGNNL|t.IXON,
			 t.OPOST,
			 t.CSIZE|t.PARENB,
			 t.ECHO|t.ECHONL|t.ICANON|t.ISIG|t.IEXTEN),
		*args, **kwargs)

	def __enter__(self):
		self.oldattrs = termios.tcgetattr(self.fd)
		termios.tcsetattr(self.attrs, self.fd, self.when)

	def __exit__(self, *exc_info):
		termios.tcsetattr(self.oldattrs, self.fd, self.when)

