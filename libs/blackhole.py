
"""Implements a dummy object that can take any sequence of operations without erroring

This is useful when monkey patching or working around libraries that don't have an option to NOT
do something.

A BlackHole object can have any operation performed on it, and always simply returns the same BlackHole object.
You can call it. You can add it. All its "methods" are more BlackHoles.
It evaluates True as a boolean. It compares unequal to and less than other objects.
It "contains" everything and, if iterated over, will infinitely yield itself.
It does not honor any super, so you can easily create a BlackHole that is technically an instance of any class
you need - for example:
	class FoobarBlackHole(Foobar, BlackHole):
	    pass
will give you something that acts like a normal black hole, but will answer True to isinstance(x, Foobar).
"""

import sys


class BlackHole(object):
	# basics
	def __new__(cls, *args, **kwargs):
		return object.__new__(cls, *args, **kwargs)
	def __init__(self, *args, **kwargs):
		pass
	def __del__(self):
		pass
	def __repr__(self):
		return object.__repr__(self)
	def __str__(self):
		return repr(self)
	def __unicode__(self):
		return str(self).encode(sys.getdefaultencoding())
	# comparison
	def __lt__(self, other):
		return True
	def __le__(self, other):
		return True
	def __eq__(self, other):
		return other is self
	def __ne__(self, other):
		return other is not self
	def __gt__(self, other):
		return False
	def __ge__(self, other):
		return self == other
	def __cmp__(self, other):
		return 0 if self == other else -1
	def __nonzero__(self):
		return True
	# attributes
	def __getattribute__(self, attr):
		return self
	def __setattr__(self, attr, value):
		pass
	def __delattr__(self, attr):
		pass
	# descriptors
	def __get__(self, instance, owner):
		return self
	def __set__(self, instance, value):
		pass
	def __delete__(self, instance):
		pass
	# calls
	def __call__(self, *args, **kwargs):
		return self
	# iterables
	def __iter__(self):
		return self
	def __len__(self):
		return self
	def __reversed__(self):
		return self
	def __contains__(self):
		return True
	# items
	def __getitem__(self, item):
		return self
	def __setitem__(self, item, value):
		pass
	def __delitem__(self, item):
		pass
	def __getslice__(self, i, j):
		return self
	def __setslice__(self, i, j, seq):
		pass
	def __delslice__(self, i, j):
		pass
	# numeric operations
	def __add__(self, other):
		return self
	def __sub__(self, other):
		return self
	def __mul__(self, other):
		return self
	def __floordiv__(self, other):
		return self
	def __truediv__(self, other):
		return self
	def __div__(self, other):
		return self
	def __mod__(self, other):
		return self
	def __divmod__(self, other):
		return self, self
	def __pow__(self, other, modulo=None):
		return self
	def __lshift__(self, other):
		return self
	def __rshift__(self, other):
		return self
	def __and__(self, other):
		return self
	def __or__(self, other):
		return self
	def __xor__(self, other):
		return self
	# reversed numeric operations
	def __radd__(self, other):
		return self
	def __rsub__(self, other):
		return self
	def __rmul__(self, other):
		return self
	def __rfloordiv__(self, other):
		return self
	def __rtruediv__(self, other):
		return self
	def __rdiv__(self, other):
		return self
	def __rmod__(self, other):
		return self
	def __rdivmod__(self, other):
		return self, self
	def __rpow__(self, other):
		return self
	def __rlshift__(self, other):
		return self
	def __rrshift__(self, other):
		return self
	def __rand__(self, other):
		return self
	def __ror__(self, other):
		return self
	def __rxor__(self, other):
		return self
	# in place numeric operations (required in case our super defined them and we need to override)
	def __iadd__(self, other):
		return self
	def __isub__(self, other):
		return self
	def __imul__(self, other):
		return self
	def __ifloordiv__(self, other):
		return self
	def __itruediv__(self, other):
		return self
	def __idiv__(self, other):
		return self
	def __imod__(self, other):
		return self
	def __ipow__(self, other, modulo=None):
		return self
	def __ilshift__(self, other):
		return self
	def __irshift__(self, other):
		return self
	def __iand__(self, other):
		return self
	def __ior__(self, other):
		return self
	def __ixor__(self, other):
		return self
	# unary numeric operations
	def __neg__(self):
		return self
	def __pos__(self):
		return self
	def __abs__(self):
		return self
	def __invert__(self):
		return self
	# numeric conversion operations
	def __complex__(self):
		return self
	def __int__(self):
		return self
	def __long__(self):
		return self
	def __float__(self):
		return self
	def __oct__(self):
		return self
	def __index__(self):
		return self
	def __coerce__(self, other):
		return self, self
	# context management
	def __enter__(self):
		return self
	def __exit__(self, *exc_info):
		pass

