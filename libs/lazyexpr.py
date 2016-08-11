

def _format_call(value, args, kwargs):
	args = ', '.join(map(repr, args))
	kwargs = ', '.join('{}={!r}'.format(k, v) for k, v in kwargs.items())
	if kwargs:
		args = '{}, {}'.format(args, kwargs) if args else kwargs
	return '{!r}({})'.format(value, args)

def _format_pow(base, exp, mod):
	if mod is None:
		return '({!r}**{!r})'.format(base, exp)
	return 'pow({!r}, {!r}, {!r})'.format(base, exp, mod)


class LazyExpr(object):
	"""Encodes an expression that contains as-yet-unknown variables.
	Works with most operations.
	Automatically resolves to a concrete value when all LazyValues referenced
	within the expression are given values via .resolve()
	repr() will give you a human-readable view of the operations.
	Example:

	>>> m = LazyValue('mantissa')
	>>> e = LazyValue('exponent')
	>>> b = LazyValue('base')
	>>> a = LazyValue('additional')
	>>> expr = m * b**e + a
	>>> expr
	((mantissa * (base ** exponent)) + additional)
	>>> expr = expr.resolve(base=2)
	>>> expr
	((mantissa * (2 ** exponent)) + additional)
	>>> expr = expr.resolve(exponent=3)
	>>> expr
	((mantissa * 8)) + additional)
	>>> expr.resolve(mantissa=2, additional=4)
	20
	>>> expr.resolve(mantissa='x', additional='y')
	'xxxxxxxxy'

	"""

	def __init__(self, func, repr_fmt, *args):
		# repr_fmt.format(*map(repr, args)) should produce repr()
		# alternately, it may be a callable which should take *args
		# once all args are concrete:
		#  func(*args) shold produce the concrete result
		# example: for addition,
		#  func=lambda a, b: a+b
		#  repr_fmt="({} + {})"
		self.__func = func
		self.__repr_fmt = repr_fmt
		self.__args = args

	def __repr__(self):
		if callable(self.__repr_fmt):
			return self.__repr_fmt(*self.__args)
		return self.__repr_fmt.format(*map(repr, self.__args))

	def resolve(self, **values):
		"""Resolve one or more LazyValues in the expression to a concrete value.
		Value name=value should be given as kwargs.
		"""
		new_args = [
			arg.resolve(**values)
			if isinstance(arg, LazyExpr)
			else arg
			for arg in self.__args
		]
		if any(isinstance(arg, LazyExpr) for arg in new_args):
			return LazyExpr(self.__func, self.__repr_fmt, *new_args)
		else:
			return self.__func(*new_args)

	def __str__(self):
		return '{}({!r})'.format(type(self).__name__, self)

	# comparison
	def __lt__(self, other):
		return LazyExpr(lambda a, b: a < b, '({} < {})', self, other)
	def __le__(self, other):
		return LazyExpr(lambda a, b: a <= b, '({} <= {})', self, other)
	def __eq__(self, other):
		return LazyExpr(lambda a, b: a == b, '({} == {})', self, other)
	def __ne__(self, other):
		return LazyExpr(lambda a, b: a != b, '({} != {})', self, other)
	def __gt__(self, other):
		return LazyExpr(lambda a, b: a > b, '({} > {})', self, other)
	def __ge__(self, other):
		return LazyExpr(lambda a, b: a >= b, '({} >= {})', self, other)
	def __nonzero__(self):
		raise Exception("Cannot determine truthness of LazyExpr, resolve it first")

	# attributes, items and calls
	# NOTE: We can't reproduce getattr(obj, attr, default) form as we don't get
	# passed in the default.
	def __getattr__(self, attr):
		return LazyExpr(getattr, 'getattr({}, {})', self, attr)
	def __getitem__(self, item):
		return LazyExpr(lambda a, b: a[b], '{}[{}]', self, item)
	def __getslice__(self, i, j):
		return LazyExpr(lambda v, i, j: v[i:j], '{}[{}:{}]', self, i, j)
	def __call__(self, *args, **kwargs):
		return LazyExpr(lambda v, *a, **k: v(*a, **k), _format_call, self, args, kwargs)

	# iterables
	def __iter__(self):
		raise TypeError("Cannot iterate over a LazyExpr, resolve it first")

	# numeric operations
	def __add__(self, other):
		return LazyExpr(lambda a, b: a+b, '({} + {})', self, other)
	def __sub__(self, other):
		return LazyExpr(lambda a, b: a-b, '({} - {})', self, other)
	def __mul__(self, other):
		return LazyExpr(lambda a, b: a*b, '({} * {})', self, other)
	def __floordiv__(self, other):
		return LazyExpr(lambda a, b: a//b, '({} // {})', self, other)
	def __div__(self, other):
		return LazyExpr(lambda a, b: a/b, '({} / {})', self, other)
	def __mod__(self, other):
		return LazyExpr(lambda a, b: a%b, '({} % {})', self, other)
	def __divmod__(self, other):
		return LazyExpr(divmod, 'divmod({}, {})', self, other)
	def __pow__(self, other, modulo=None):
		return LazyExpr(pow, _format_pow, self, other, modulo)
	def __neg__(self):
		return LazyExpr(lambda a: -a, '(-{})', self)
	def __pos__(self):
		return LazyExpr(lambda a: +a, '(+{})', self)
	def __abs__(self):
		return LazyExpr(abs, 'abs({})', self)

	# bitwise operations
	def __lshift__(self, other):
		return LazyExpr(lambda a, b: a << b, '({} << {})', self, other)
	def __rshift__(self, other):
		return LazyExpr(lambda a, b: a >> b, '({} >> {})', self, other)
	def __and__(self, other):
		return LazyExpr(lambda a, b: a&b, '({} & {})', self, other)
	def __or__(self, other):
		return LazyExpr(lambda a, b: a|b, '({} | {})', self, other)
	def __xor__(self, other):
		return LazyExpr(lambda a, b: a^b, '({} ^ {})', self, other)
	def __invert__(self):
		return LazyExpr(lambda a: ~a, '(~{})', self)

	# reversed numeric operations
	def __radd__(self, other):
		return LazyExpr(lambda a, b: a+b, '({} + {})', other, self)
	def __rsub__(self, other):
		return LazyExpr(lambda a, b: a-b, '({} - {})', other, self)
	def __rmul__(self, other):
		return LazyExpr(lambda a, b: a*b, '({} * {})', other, self)
	def __rfloordiv__(self, other):
		return LazyExpr(lambda a, b: a//b, '({} // {})', other, self)
	def __rdiv__(self, other):
		return LazyExpr(lambda a, b: a/b, '({} / {})', other, self)
	def __rmod__(self, other):
		return LazyExpr(lambda a, b: a%b, '({} % {})', other, self)
	def __rdivmod__(self, other):
		return LazyExpr(divmod, 'divmod({}, {})', other, self)
	def __rpow__(self, other):
		return LazyExpr(pow, '{}**{}', other, self)

	# reversed bitwise operations
	def __rlshift__(self, other):
		return LazyExpr(lambda a, b: a << b, '({} << {})', other, self)
	def __rrshift__(self, other):
		return LazyExpr(lambda a, b: a >> b, '({} >> {})', other, self)
	def __rand__(self, other):
		return LazyExpr(lambda a, b: a&b, '({} & {})', other, self)
	def __ror__(self, other):
		return LazyExpr(lambda a, b: a|b, '({} | {})', other, self)
	def __rxor__(self, other):
		return LazyExpr(lambda a, b: a^b, '({} ^ {})', other, self)


class LazyValue(LazyExpr):
	"""Represents a single unresolved value in a LazyExpr"""
	def __init__(self, name):
		self.__name = name
		super(LazyValue, self).__init__(None, lambda: self.__name)

	def resolve(self, **values):
		if self.__name in values:
			return values[self.__name]
		return self
