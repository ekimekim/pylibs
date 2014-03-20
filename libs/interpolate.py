
"""A CPython-specific hack to make str.format() with **vars easier"""

import sys

if sys.subversion[0] != "CPython":
	raise Exception("This module is CPython-specific.")

def interpolate(s, *args, **kwargs):
	"""Interpolate a string s as per python's str.format,
	but defaulting to the local scope of the caller as **kwargs
	if no other args are provided.
	NOTE: Due to its much higher complexity, variables accessible by closure are not covered.
	"""
	if not (args or kwargs):
		frame = sys._getframe(1)
		kwargs = frame.f_globals.copy()
		kwargs.update(frame.f_locals)
	return s.format(*args, **kwargs)
