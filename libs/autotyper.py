
"""A utility for typing files to the X keyboard.

Requires the xte utility, provided by the "xautomation" package on most distributions
"""

import sys
from subprocess import Popen, PIPE

import scriptlib

AI_HACK = True
KEY_WAIT = True # sleep between every key? (otherwise, every command)
INTERVAL = 10000 # us to sleep between keys
DEBUG = False

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
			if KEY_WAIT:
				# make end of part trigger early so each char is a seperate str command
				ret.append("str {}".format(part))
				part = ""
		else:
			if part:
				ret.append("str {}".format(part))
				part = ""
			if c not in keymap:
				raise ValueError("Cannot handle character: {!r}".format(c))
			ret.append(keymap[c])
			if AI_HACK and c == '\n':
				# hack to work around auto-indenting editors
				ret.append("key Home")
	return ret


def send_commands(commands):
	proc = Popen(['xte'], stdin=PIPE)
	if INTERVAL:
		joinstr = '\nusleep {}\n'.format(INTERVAL)
	else:
		joinstr = '\n'
	data = joinstr.join(commands) + '\n'
	if DEBUG: print data
	proc.communicate(data)


def send(s):
	send_commands(to_commands(s))


def from_file(path):
	with open(path) as f:
		data = f.read()
	send(data)


@scriptlib.with_argv
def main(*args, **kwargs):
	global INTERVAL, AI_HACK, DEBUG, KEY_WAIT
	INTERVAL = kwargs.get("interval", INTERVAL)
	AI_HACK = kwargs.get("ai-hack", AI_HACK)
	DEBUG = kwargs.get("debug", DEBUG)
	KEY_WAIT = kwargs.get("debug", KEY_WAIT)
	for arg in args:
		if arg == '-':
			send(sys.stdin.read())
		else:
			from_file(arg)


if __name__ == '__main__':
	main()
