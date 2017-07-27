
"""For the tinier littler mini-things in the repo full of tiny mini-things"""

import errno
import os
import random
import string


class AtomicReplace(object):
	"""Context manager. Usage:
		with AtomicReplace(path) as tmppath:
			<do something with tmppath>
	After the body has succeeded, atomically replaces path with tmppath (via rename).
	On failure, deletes tmppath.
	tmppath will always be in the same directory as path, to ensure (in most cases) same filesystem.
	Not re-entrant.
	"""
	def __init__(self, path):
		self.path = os.path.realpath(os.path.abspath(path)) # also normalizes, removes trailing slash

	def __enter__(self):
		dirname, name = os.path.split(self.path)
		name_no_ext, ext = os.path.splitext(name)
		rand = ''.join(random.choice(string.letters + string.digits) for _ in range(8))
		self.tmppath = os.path.join(dirname, '.{}.{}.tmp{}'.format(name_no_ext, rand, ext))
		return self.tmppath

	def __exit__(self, *exc_info):
		success = (exc_info == (None, None, None))
		if success:
			os.rename(self.tmppath, self.path)
		else:
			try:
				os.remove(self.tmppath)
			except OSError as e:
				if e.errno != errno.ENOENT:
					raise
				# ignore error if it didn't exist
