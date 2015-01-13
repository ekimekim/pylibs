
"""Implements an infinite set which contains all but a finite set of elements"""

from partialorder import partial_ordering


# partial_ordering decorator fills in __lt__ and __gt__ based on __le__ and __ge__
@partial_ordering
class UniverseSet(object):
	"""This class acts like a set in most ways. However, all operations are done against
	a virtual "Universe Set" that contains every value.
	The main point of this kind of set is to exclude things from it specifically,
	and possibly intersect it with a finite set (to yield a finite set) later.
	Internals note: The set of things NOT in the universe set are kept track of as 'coset'.
	"""

	def __init__(self, coset=()):
		"""The optional arg coset sets the initial coset (set of excluded items)
		but is intended only for internal use. Better to use UniverseSet() - exclude_set."""
		self.coset = set(coset)

	def __and__(self, other):
		if isinstance(other, UniverseSet):
			return UniverseSet(self.coset | other.coset)
		return other - self.coset
	__rand__ = __and__

	def __contains__(self, value):
		return value not in self.coset

	def __eq__(self, other):
		# we could let partial_ordering fill this in, but checking cosets are equal is much more efficient
		# than "both are subsets of each other".
		if isinstance(other, UniverseSet):
			return self.coset == other.coset
		return False

	def __le__(self, other):
		return self.issubset(other)

	def __ge__(self, other):
		return self.issuperset(other)

	def __or__(self, other):
		if isinstance(other, UniverseSet):
			return UniverseSet(self.coset & other.coset)
		return UniverseSet(self.coset & other)
	__ror__ = __or__

	def __repr__(self):
		return "<UniverseSet() - %s>" % repr(self.coset)
	__str__ = __repr__

	def __sub__(self, other):
		if isinstance(other, UniverseSet):
			return other.coset - self.coset
		return UniverseSet(self.coset | other)

	def __rsub__(self, other):
		return other & self.coset

	def __xor__(self, other):
		if isinstance(other, UniverseSet):
			return self.coset ^ other.coset
		return UniverseSet(self.coset & other)
	__rxor__ = __xor__

	def add(self, value):
		self.coset.discard(value)

	def copy(self):
		return UniverseSet(self.coset)

	def difference(self, *others):
		ret = self
		for other in others:
			ret -= other

	def intersection(self, *others):
		ret = self
		for other in others:
			ret &= other
		return ret

	def isdisjoint(self, other):
		return not self & other

	def issubset(self, other):
		if isinstance(other, UniverseSet):
			return other.coset.issubset(self.coset)
		return False

	def issuperset(self, other):
		if isinstance(other, UniverseSet):
			return self.coset.issubset(other.coset)
		return self.coset.isdisjoint(other)

	def pop(self):
		raise ValueError("Cannot pop arbitrary value from infinite set")

	def remove(self, value):
		if value not in self:
			raise KeyError(value)
		self.discard(value)

	def discard(self, value):
		self.coset.add(value)

	def symmetric_difference(self, other):
		return self ^ other

	def union(self, *others):
		ret = self
		for other in others:
			ret |= other
		return ret

	def update(self, *others):
		self.coset = self.union(*others).coset

	# NOTE: We don't implement the following set methods:
	#	clear
	#	intersection_update
	#	difference_update
	#	symmetric_difference_update
	# as they require (or may require) updating in-place from an infinite set to a finite one, which we can't do.
