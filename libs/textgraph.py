
"""A variety of text-based graphing techniques"""


def _get_braille(col1, col2):
	"""Braille block renders 8 dots according to the 8 bits of the lower byte of the unicode code point number,
	in the following pattern:
		0 3
		1 4
		2 5
		6 7
	where 0 is least signifigant bit and 7 is most signifigant bit.

	For our purposes, we want to treat these characters as a way to encode two vertical values 0 to 4.
	"""
	cols = [col1, col2]
	if any(col not in range(5) for col in [col1, col2]):
		raise ValueError("Columns must be between 0 and 4")
	mask = 0
	bitlists = [[6, 2, 1, 0], [7, 5, 4, 3]]
	for col, bitlist in zip(cols, bitlists):
		for bit in bitlist[:col]:
			mask |= 1 << bit
	return unichr(0x2800 + mask)


def _get_vertical_fill(value):
	if value == 0:
		return u' '
	return unichr(0x2580 + value)


def _get_horizontal_fill(value):
	if value == 0:
		return u' '
	return unichr(0x2590 - value)


def dots_vertical(values, ceiling=None, height=1):
	"""Render a dotted column graph with two columns per character (using braille characters).
	Ceiling defaults to max value. Height is how many lines high to scale the output to.
	Returns a list of lines."""
	cols = _vertical_to_columns(values, 4, ceiling=ceiling, height=height)
	# Group cols into pairs, maybe handle last odd col by appending a 0 col
	if len(cols) % 2 == 1:
		cols.append([0] * height)
	groups = zip(cols[::2], cols[1::2])
	# Render to chars and re-structure into lines
	lines = ['' for _ in range(height)]
	for fullcol1, fullcol2 in groups:
		for h, (col1, col2) in enumerate(zip(fullcol1, fullcol2)):
			lines[h] += _get_braille(col1, col2)
	return lines[::-1]


def bars_vertical(values, ceiling=None, height=1):
	"""Render a column graph using filled square characters (8 values of resolution per line).
	Ceiling defaults to max value. Height is how many lines high to scale the output to.
	Returns a list of lines."""
	cols = _values_to_sequence(values, 8, ceiling=ceiling, max_chars=height)
	lines = ['' for _ in range(height)]
	for col in cols:
		for h, value in enumerate(col):
			lines[h] += _get_vertical_fill(value)
	return lines[::-1]


def _values_to_sequence(values, steps_per_char, ceiling=None, max_chars=1):
	"""Converts a list of values to a list of sequences, where each sequence
	encodes the value as a list of "chars" (a number from 0 to steps_per_char inclusive) such
	that the total is the (scaled) value. The list will always be exactly max_chars long.
	eg. if steps_per_char is 4, the value is 7, and max_chars is 3,
	then it is encoded as [4, 3, 0].
	If given, ceiling will scale all values such that the ceiling value is encoded
	as [steps_per_char] * max_chars, with values exceeding it being clamped.
	If not given, ceiling is implicitly max(values).
	"""
	if ceiling is None:
		ceiling = max(values)
	normal_ceiling = max_chars * steps_per_char
	normalized = [int(value * normal_ceiling / ceiling) for value in values]
	cols = []
	for value in normalized:
		col = []
		# Suppose steps_per_char = 4, max_chars = 3, our max value is then 12.
		# We want to encode eg. 7 as [4, 3, 0].
		# On each iteration we put a (clamped to max 4) value down,
		# then subtract 4 (clamped min to 0) for next iteration
		for _ in range(max_chars):
			col.append(min(steps_per_char, value))
			value = max(0, value - steps_per_char)
		cols.append(col)
	return cols


def bars_horizontal(values, ceiling=None, width=80):
	"""As bars_vertical but makes a row graph instead of a column graph, using left fill blocks"""
	rows = _values_to_sequence(values, 8, ceiling=ceiling, max_chars=width)
	return [''.join(_get_horizontal_fill(v) for v in row) for row in rows]


def bars_horizontal_by_quadrant(values, ceiling=None, width=80):
	"""As bars_horizontal but uses quadrant blocks instead of left fill blocks.
	This means we have less value resolution (half a character instead of 1/8th),
	but it means two values can be shown for each row."""
	# values must be even, pad if needed
	if len(values) % 2 == 1:
		values = list(values) + [0]
	rows = _values_to_sequence(values, 2, ceiling=ceiling, max_chars=width)
	# iterate over each pair of rows
	lines = []
	for tops, bottoms in zip(rows[::2], rows[1::2]):
		line = ''
		for top, bottom in zip(tops, bottoms):
			# top and bottom are in range 0-2, so there are 9 cases
			line += [
				u' ', # nothing
				u'\u2596', # lower left only
				u'\u2584', # bottom half
				u'\u2598', # upper left only
				u'\u258c', # both left
				u'\u2599', # all but top right
				u'\u2580', # upper half
				u'\u259b', # all but bottom right
				u'\u2588', # full
			][top * 3 + bottom]
		lines.append(line)
	return lines
