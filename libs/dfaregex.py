
import itertools


class ParseError(Exception):
	pass


def _parse_num(s):
	try:
		value = int(s)
	except ValueError:
		pass
	else:
		if value >= 0:
			return value
	raise ParseError("Repeat operator must be given up to two non-negative integers")


def _parse(data):
	"""
	Parse pattern until EOF or ) is reached. Returns (parse tree, remaining data).
	Unless data is empty, first character of data will always be ')'

	Parse tree consists of 5 node types:
	('alternate', children) - Match if any child tree matches
	('concat', children) - Match if all children match, one after the other
	('kleene', child) - Match any number of repeats of child tree, including none (empty string)
	('literal', value) - Match only the exact given value, which is a single character or a special token like 'START' or 'END'
	"""

	alternates = []
	parts = []

	def eat(n=1, errormsg=None):
		if len(data) < n:
			assert errormsg, "eat hit EOF but no error msg given"
			raise ParseError(errormsg)
		return data[:n], data[n:]

	def pop():
		if not parts:
			raise ParseError("Unary operator must follow a value")
		return parts.pop()

	_chr = unichr if isinstance(data, unicode) else chr
	_chr_range = 0x110000 if isinstance(data, unicode) else 0x100
	all_chars = {_chr(i) for i in xrange(_chr_range)}

	while data:
		c, data = eat()

		if c == '(':
			part, data = _parse(data)
			close, data = eat(errormsg='Unterminated group')
			assert close == ')'
			parts.append(part)

		elif c == ')':
			data = c + data # re-append the ) we just took so we return it correctly
			break

		elif c == '|':
			alternates.append(parts)
			parts = []

		elif c in '.[':
			chars = []
			negate = False

			if c == '.':
				# . is a negation of no chars
				negate = True
			else:
				# character set, first let's collect all the characters
				first = True
				while True:
					c, data = eat(errormsg='Unterminated character set')
					if chars and c == ']':
						break
					elif c == '\\':
						# escape, take the next one
						c, data = eat(errormsg='Unterminated escape')
					elif first and c == '^':
						negate = True
						c = None
					elif c == '-':
						# range, leave a marker for now and we'll sort it out in the next pass
						c = 'range'
					if c:
						chars.append(c)
					first = False

			# now we look for ranges
			charset = set()
			while len(chars) >= 3:
				start, end = ('-' if c == 'range' else c for c in (chars[0], chars[2]))
				if chars[1] == 'range':
					chars = chars[3:]
					if ord(start) > ord(end):
						raise ParseError("Character range end must be after start")
					charset |= {_chr(i) for i in range(ord(start), ord(end)+1)}
				else:
					charset.add(start)
					chars = chars[1:]
			charset |= {'-' if c == 'range' else c for c in chars}

			if negate:
				charset = all_chars - charset

			parts.append(('alternate', [('literal', c) for c in charset]))

		elif c in '*+{?':
			# All repetition-based unary operators are specific cases of the general {M,N} form.
			# We normalize x{M,} into form xxx...xxx*, and x{M,N} into form xxx...xxx?x?...x?

			if c == '{':
				# parse operator like {M,N}
				repeat_data = ''
				while True:
					c, data = eat(errormsg='Unterminated repeat operator')
					if c == '}':
						break
					repeat_data += c
				if ',' in repeat_data:
					least, most = repeat_data.split(',', 1)
				else:
					# {M} -> {M,M}
					least = most = repeat_data
				least = _parse_num(least) if least else 0
				most = _parse_num(most) if most else None
			elif c == '?': # ? -> {0,1}
				least, most = (0, 1)
			elif c == '*': # * -> {0,}
				least, most = (0, None)
			elif c == '+': # + -> {1,}
				least, most = (1, None)
			else:
				assert False

			if most is not None and most < least:
				raise ParseError("Repeat operator maximum must be >= minimum")

			value = pop() # value to repeat

			# first, repeat LEAST times to establish minimum repetition
			parts += [value] * least

			if most is None:
				# if unbounded, we simply add a kleene star operation at the end
				parts.append(('kleene', value))
			else:
				# if bounded, we add an optional value (MOST-LEAST) times
				# optional values are represented as (empty|value)
				# empty is represented as an empty concat to avoid an additional case
				parts += [('alternate', (('concat', []), value))] * (most - least)

		else:
			# anything else is a literal
			if c == '\\':
				# escape, take another and treat as text no matter what
				c, data = eat(errormsg='Unterminated escape')
			elif c == '^': # start-of-string mark
				c = 'START'
			elif c == '$': # end-of-string mark
				c = 'END'
			parts.append(('literal', c))

	# close out final alternate option, and return tree as an alternate operation of many concat operations
	# this creates some unneeded layers but we simplify later
	alternates.append(parts)
	tree = ('alternate', [('concat', parts) for parts in alternates])

	return tree, data


def _simplify(tree):
	"""Attempts to simplify a tree using some basic transform rules"""
	kind, value = tree

	if kind in ('alternate', 'concat'):
		# we have some common stuff to apply to both

		# first, simplify all children
		children = map(_simplify, value)

		# transform stacked nodes of like kind to one, ie. concat of concats, alternate of alternates
		new_children = []
		for child in children:
			child_kind, child_value = child
			if child_kind == kind:
				new_children += child_value
			else:
				new_children.append(child)
		children = new_children

		# alternate-specific
		if kind == 'alternate':
			# transform an empty alternate to an empty concat
			if not children:
				return ('concat', [])

			# remove duplicates and remove empty if any kleene is present (since kleenes all match empty)
			new_children = []
			has_kleene = any(child_kind == 'kleene' for (child_kind, _) in children)
			for child in children:
				if child in new_children: # note that "in" is an equality test, not reference test
					continue
				if has_kleene and child == ('concat', []):
					continue
				new_children.append(child)
			children = new_children

		# if only one child, just return that child since 1-child is a no-op for both kinds of node
		if len(children) == 1:
			return children[0]

		# return modified value
		return kind, children

	elif kind == 'kleene':
		# first, simplify the child
		child = _simplify(value)

		# if the child is also a kleene node, return it since a double-kleene is a no-op
		child_kind, child_value = child
		if child_kind == 'kleene':
			return child
		# do the same if child is empty, since '()*' -> '()'
		if child == ('concat', []):
			return child

		# return modified value
		return kind, child

	else:
		# literal. return unmodified
		return tree


def parse(data):
	"""Return a parse tree for given regex string"""
	tree, remainder = _parse(data)
	if remainder:
		assert remainder[0] == ')'
		raise ParseError("Close parenthesis without matching open parenthesis")
	return _simplify(tree)


def to_text(tree):
	"""Convert a tree back to a regex string representation.
	Note this may be quite different to the original regex,
	ie. to_text(parse(regex)) may not equal regex,
	but it is a guarentee that parse(to_text(tree)) == tree
	"""
	wrap = lambda s: '({})'.format(s)

	kind, value = tree
	if kind == 'alternate':
		return '|'.join(to_text(child) for child in value)
	if kind == 'concat':
		return ''.join(
			wrap(to_text((child_kind, child_value)))
			if child_kind == 'alternate'
			else to_text((child_kind, child_value))
			for child_kind, child_value in value
		)
	if kind == 'kleene':
		child_kind, child_value = value
		text = to_text(value)
		return '{}*'.format(wrap(text) if child_kind in ('alternate', 'concat') else text)
	if kind == 'literal':
		special = {
			'START': '^',
			'END': '$',
		}
		escape = '+*?{.[()|\\'
		if value in special:
			return special[value]
		if value in escape:
			return '\\{}'.format(value)
		return value
	assert False, "unknown node type {!r}".format(kind)


def _to_nfa(tree, starts, next_state):
	"""Takes a parse tree, target start states and state generator.
	Returns a set of end states and graph {state: {input: {set of new states}}}.
	The state generator enforces unique states.
	"""
	fset = lambda *args: frozenset(args)
	kind, value = tree

	if kind == 'literal':
		end = next_state()
		return fset(end), {start: {value: frozenset([end])} for start in starts}

	if kind == 'kleene':
		child_ends, graph = _to_nfa(value, starts, next_state)
		# re-point each possible child end back to start
		for end in child_ends:
			_nfa_merge_states(graph, end, starts)
		return starts, graph

	if kind == 'concat':
		next_starts = starts
		graph = {}
		for child in value:
			next_starts, child_graph = _to_nfa(child, next_starts, next_state)
			graph = _nfa_merge(graph, child_graph)
		return next_starts, graph

	if kind == 'alternate':
		graph = {}
		ends = fset()
		for child in value:
			child_ends, child_graph = _to_nfa(child, starts, next_state)
			ends |= child_ends
			graph = _nfa_merge(graph, child_graph)
		return ends, graph


def _nfa_merge_states(graph, old, news):
	"""Modify graph in-place so old state no longer exists, and is copied into all new states in news"""
	for new in news:
		if old == new:
			continue
		# merge transitions of old state into transitions of new state
		graph[new] = _multimap_merge(graph.get(new, {}), graph.get(old, {}))
		# modify references to old state to point to new
		for inputs in graph.values():
			for input, states in inputs.items():
				if old in states:
					inputs[input] = (states - {old}) | {new}
	if old not in news:
		graph.pop(old, None)


def _nfa_merge(g1, g2):
	return {
		state: _multimap_merge(g1.get(state, {}), g2.get(state, {}))
		for state in set(g1) | set(g2)
	}


def _multimap_merge(d1, d2):
	return {
		key: d1.get(key, frozenset()) | d2.get(key, frozenset())
		for key in set(d1) | set(d2)
	}


def to_nfa(tree):
	"""Returns (success states, graph)"""
	return _to_nfa(tree, frozenset([0]), itertools.count(1).next)


def _to_dfa(nfa):
	dfa = {} # {state: {input: new state}}, states are frozensets of nfa states
	to_expand = set([frozenset([0])])
	expanded = set()

	while to_expand:
		state = to_expand.pop()
		expanded.add(state)
		inputs = {}
		for nfa_state in state:
			inputs = _multimap_merge(inputs, nfa.get(nfa_state, {}))
		dfa[state] = inputs
		for new_state in inputs.values():
			if new_state not in to_expand | expanded:
				to_expand.add(new_state)

	return dfa


def _match(target_states, dfa, data):
	state = frozenset([0])
	for c in data:
		state = dfa[state].get(c)
		if state is None:
			return False
	return bool(state & target_states)


def match(pattern, data):
	tree = parse(pattern)
	target_states, nfa = to_nfa(tree)
	dfa = _to_dfa(nfa)
	return _match(target_states, dfa, data)
