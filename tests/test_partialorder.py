import functools as ft
from partialorder import partial_ordering

@partial_ordering
class N(object):
	"""A numeric object that is only comparable with other values that share an integer factor"""
	def __init__(self, value):
		self.value = value
	def __repr__(self): return "<{} {}>".format(self.__class__.__name__, self.value)
	def __le__(self, other):
		return self.comparable(other) and self.value <= other.value
	def __ge__(self, other):
		return self.comparable(other) and self.value >= other.value
	def comparable(self, other):
		for p in primes(self.value):
			if self.value % p == 0 and other.value % p == 0:
				return True

def primes(upto):
	ps = []
	for n in range(2, upto+1):
		if not any(n%p == 0 for p in ps):
			yield n
			ps.append(n)


def print_results(v1, v2):
	ops = dict(
		__lt__ = '<',
		__gt__ = '>',
		__le__ = '<=',
		__ge__ = '>=',
		__eq__ = '==',
	)
	a, b = N(v1), N(v2)
	for attr, op in ops.items():
		print op, bool(getattr(a, attr)(b))

def test():
	for x,y in [(6,6), (3,6), (6,3), (5,6), (6,5)]:
		print "%s vs %s" % (x,y)
		print_results(x, y)

if __name__ == '__main__':
	test()
