
"""Provides a partial ordering version of functools.total_ordering"""

def partial_ordering(cls):
	"""Class decorator. Similar to functools.total_ordering, except it
	is used to define partial orderings
	(ie. it is possible that x is niether greater than, equal to or less than y).
	It assumes the present of a <= (__le__) and >= (__ge__) method, but nothing else.
	"""
	def __lt__(self, other): return self <= other and not self >= other
	def __gt__(self, other): return self >= other and not self <= other
	def __eq__(self, other): return self >= other and self <= other

	cls.__lt__ = __lt__
	cls.__gt__ = __gt__
	cls.__eq__ = __eq__

	return cls
