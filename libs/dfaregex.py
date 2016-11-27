


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
	# this creates some unneeded layers but meh
	alternates.append(parts)
	tree = ('alternate', [('concat', parts) for parts in alternates])

	return tree, data
