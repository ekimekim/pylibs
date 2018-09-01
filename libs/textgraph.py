
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
	cols = _vertical_to_columns(values, 8, ceiling=ceiling, height=height)
	lines = ['' for _ in range(height)]
	for col in cols:
		for h, value in enumerate(col):
			lines[h] += _get_vertical_fill(value)
	return lines[::-1]


def _vertical_to_columns(values, steps_per_char, ceiling=None, height=1):
	if ceiling is None:
		ceiling = max(values)
	normal_ceiling = height * steps_per_char
	normalized = [int(value * normal_ceiling / ceiling) for value in values]
	cols = []
	for value in normalized:
		col = []
		# Suppose steps_per_char = 4, height = 3, our max value is then 12.
		# We want to encode eg. 7 as [4, 3, 0].
		# On each iteration we put a (clamped to max 4) value down,
		# then subtract 4 (clamped min to 0) for next iteration
		for _ in range(height):
			col.append(min(steps_per_char, value))
			value = max(0, value - steps_per_char)
		cols.append(col)
	return cols
