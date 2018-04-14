
"""An optimized lookup for unicode character names

Takes a pre-rendered packed file, mmaps it and does a binary search into it.
As a result, even max memory usage will only be as large as the file (~10MB),
lookups take on the order of 100us.
"""

import mmap
import os
import struct
import bisect


class UnicodeNames(object):
	"""
	Look up a unicode character by name.
	Note this object must be closed to release the mmap'd fd.
	It is also a context manager which closes on exit.
	"""
	closed = False

	def __init__(self, path):
		"""Path must point to a packed names file, which is a fixed-width format
		of 83 characters of name, then 4 characters packed big-endian 32-bit integer
		which is the value that name maps to. Names are padded with spaces on the right
		and are all uppercase. Aliases are included.

		"""
		with open(path) as f:
			self.map = mmap.mmap(f.fileno(), 0, mmap.MAP_PRIVATE, mmap.PROT_READ)
			length = os.fstat(f.fileno()).st_size / 87
		self.list = _ListWrapper(self.map, length)

	def close(self):
		self.closed = True
		self.map.close()

	def __enter__(self):
		pass

	def __exit__(self, *exc_info):
		self.close()

	def lookup(self, name):
		"""Look up name and return the associated unicode character as an id (ie. an integer)
		if found. Otherwise raise KeyError. Lookup is case insensitive.
		"""
		if self.closed:
			raise Exception("Closed")
		n = name.upper()
		i = bisect.bisect_left(self.list, n)
		if self.list[i] != n:
			raise KeyError(name)
		return self.list.get_value(i)

	def lookup_prefix(self, prefix):
		"""Look up name and return all associated characters whose names begin with that
		prefix as a dict {name: id}. Note the same id may be present more than once.
		Returns an empty dict if none found. Lookup is case insensitive."""
		if self.closed:
			raise Exception("Closed")
		n = prefix.upper()
		i = bisect.bisect_left(self.list, n)
		results = {}
		while i < len(self.list) and self.list[i].startswith(n):
			results[self.list[i]] = self.list.get_value(i)
			i += 1
		return results

	def names(self):
		"""Generator that yields all character names"""
		for i in range(len(self.list)):
			yield self.list[i]


class _ListWrapper(object):
	"""Acts like enough of a list for bisect.bisect() to work"""
	def __init__(self, map, length):
		self.map = map
		self.length = length

	def __len__(self):
		return self.length

	def __getitem__(self, i):
		return self.map[i * 87 : i * 87 + 83].rstrip()

	def get_value(self, i):
		return struct.unpack('!i', self.map[i * 87 + 83 : i * 87 + 87])[0]
