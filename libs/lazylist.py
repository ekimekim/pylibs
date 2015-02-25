
"""A tool for working with iterators as though they are lists

Sometimes you have a lazy iterator, which you want to use in some function
that expects a list or tuple (or other indexable iterable).

One solution is to convert the iterator to a list, but then you lose laziness.
This LazyList wrapper takes an iterable (with optional len) and only fetches items as needed.
It supports indexing, slicing, len(), etc."""

from itertools import count

INF = float('inf')


class LazyList(object):
	"""Wraps an iterable in a list-like wrapper which only fetches items as needed."""

	def __init__(self, iterable, length=None):
		"""iterable can be any iterable to wrap. Optional arg length allows operations
		involving the length of the iterable to be done without having to exhaust the iterable
		to return its length. Note this doesn't apply if the iterable has a defined len().
		As a special case, length may be the string 'inf' or a float INF. This indicates the
		iterable cannot be exhausted, and will cause certain operations (eg. lazylist[-1]) to
		raise a ValueError.
		"""
		try:
			length = len(iterable)
		except TypeError:
			pass
		if length == 'inf':
			length = INF
		self.length = length
		self.iterator = iter(iterable)
		self.items = []

	def __repr__(self):
		return "<{}({!r}) read {}/{}>".format(type(self).__name__, self.iterator, len(self.items),
		                                      "?" if self.length is None else self.length)

	def __len__(self):
		while self.length is None:
			self.fetch_next() # exhaust iterable
		return self.length

	def __iter__(self):
		try:
			for x in count():
				yield self[x]
		except IndexError:
			return

	def __getitem__(self, index):
		if isinstance(index, slice):
			return self.__getslice__(index.start, index.stop, index.step)
		if not isinstance(index, (int, long)):
			raise IndexError("{} indices must be int, not {}".format(
			                 type(index).__name__, type(self).__name__))
		if index < 0:
			if len(self) == INF:
				raise ValueError("Infinite list does not support negative indices")
			index += len(self)
		while index >= len(self.items):
			if self.length is not None and index >= self.length:
				raise IndexError("{} index out of range".format(type(self).__name__))
			self.fetch_next() # either len(self.items) will increase or self.length will be set not None
		return self.items[index]

	def __getslice__(self, start, stop, step=None):
		# We can't simply use slice.indicies() since we don't want to compute len unless we have to.
		if hasattr(start, '__index__'):
			start = start.__index__()
		if hasattr(stop, '__index__'):
			stop = stop.__index__()
		if hasattr(step, '__index__'):
			step = step.__index__()
		if any(value is not None and not isinstance(value, (int, long)) for value in (start, stop, step)):
			raise TypeError("slice indices must be integers or None or have an __index__ method")
		if step == 0:
			raise ValueError("slice step cannot be zero")
		elif step is None:
			step = 1
		elif step < 0:
			return reversed(list(self.__getslice__(stop, start, -step)))
		if start is None:
			start = 0
		elif start < 0:
			start += len(self)
		if stop is not None and stop < 0:
			if len(self) == INF:
				stop = None
			else:
				stop += len(self)
		return LazyList(self[x]
		                for x in (count(start, step)
		                          if stop is None
		                          else xrange(start, stop, step)))

	def fetch_next(self):
		"""Get next element from iterator and save it in items.
		Raises AssertionError if StopIteration reached and length does not match.
		Otherwise, sets length on StopIteration.
		"""
		try:
			item = self.iterator.next()
		except StopIteration:
			if self.length is not None and self.length != len(self.items):
				raise AssertionError("Incorrect length provided: Expected {}, got {}".format(
				                     self.length, len(self.items)))
			self.length = len(self.items)
		else:
			self.items.append(item)
