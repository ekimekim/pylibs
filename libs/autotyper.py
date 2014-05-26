
"""A utility for typing files to the X keyboard.

Requires the xte utility, provided by the "xautomation" package on most distributions
"""

import sys
from subprocess import Popen, PIPE


def to_commands(s):
	ret = []
	part = ""
	simple = map(chr, range(ord(' '), ord('~')+1))
	keymap = {
		'\t': "key Tab",
		'\n': "key Return",
	}
	for c in s:
		if c in simple:
			part += c
		else:
			if part:
				ret.append("str {}".format(part))
				part = ""
			if c not in keymap:
				raise ValueError("Cannot handle character: {!r}".format(c))
			ret.append(keymap[c])
	return ret


def send_commands(commands):
	proc = Popen(['xte'], stdin=PIPE)
	data = '\n'.join(commands) + '\n'
	proc.communicate(data)


def send(s):
	send_commands(to_commands(s))


def from_file(path):
	with open(path) as f:
		data = f.read()
	send(data)


def main(*args):
	for arg in args:
		if arg == '-':
			send(sys.stdin.read())
		else:
			from_file(arg)


if __name__ == '__main__':
	main(*sys.argv[1:])
