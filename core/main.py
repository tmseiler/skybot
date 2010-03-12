import thread
import traceback


thread.stack_size(1024 * 512)  # reduce vm size


class Input(dict):
    def __init__(self, conn, raw, prefix, command, params,
                    nick, user, host, paraml, msg):

        chan = paraml[0].lower()
        if chan == conn.nick:  # is a PM
            chan = nick

        def say(msg):
            conn.msg(chan, msg)

        def reply(msg):
            conn.msg(chan, nick + ': ' + msg)

        def pm(msg):
            conn.msg(nick, msg)

        dict.__init__(self, conn=conn, raw=raw, prefix=prefix, command=command,
                    params=params, nick=nick, user=user, host=host,
                    paraml=paraml, msg=msg, server=conn.server, chan=chan,
                    say=say, reply=reply, pm=pm, bot=bot, lastparam=paraml[-1])

    def __getattr__(self, key):
        return self[key]

    def __setattr__(self, key, value):
        self[key] = value


def run(func, input):
    args = func._args

    if 'inp' not in input:
        input.inp = input.paraml

    if args:
        if 'db' in args:
            input['db'] = get_db_connection(input['server'])
        if 'input' in args:
            input['input'] = input
        if 0 in args:
            out = func(input['inp'], **input)
        else:
            kw = dict((key, input[key]) for key in args if key in input)
            out = func(input['inp'], **kw)
    else:
        out = func(input['inp'])
    if out is not None:
        input['reply'](unicode(out))


def do_sieve(sieve, bot, input, func, type, args):
    try:
        return sieve(bot, input, func, type, args)
    except Exception, e:
        print 'sieve error',
        traceback.print_exc(Exception)
        return None

    
class Handler(object):
    '''Runs plugins in their own threads (ensures order)'''
    def __init__(self, func):
        self.func = func
        self.input_queue = Queue.Queue()
        thread.start_new_thread(self.start, ())

    def start(self):
        while True:
            input = self.input_queue.get()

            if input == StopIteration:
                break

            run(self.func, input)

    def stop(self):
        self.input_queue.put(StopIteration)

    def put(self, value):
        self.input_queue.put(value)


def dispatch(input, kind, func, args):
    for sieve, in bot.plugs['sieve']:
        input = do_sieve(sieve, bot, input, func, kind, args)
        if input == None:
            return
    
    if func._thread:
        bot.threads[func].put(input)
    else:
        thread.start_new_thread(run, (func, input))
        

def main(conn, out):
    inp = Input(conn, *out)

    # EVENTS
    for func, args in bot.events[inp.command] + bot.events['*']:
        dispatch(Input(conn, *out), "event", func, args)


    if inp.command == 'PRIVMSG':
        # COMMANDS
        if inp.chan == inp.nick: # private message, no command prefix
            prefix = r'^(?:[.!]?|'
        else:
            prefix = r'^(?:[.!]|'
            
        command_re = prefix + inp.conn.nick
        command_re += r'[:,]*\s+)(\w+)(?:$|\s+)(.*)'

        m = re.match(command_re, inp.lastparam)

        if m:
            command = m.group(1).lower()
            if command in bot.commands:
                input = Input(conn, *out)
                input.inp_unstripped = m.group(2)
                input.inp = m.group(2).strip()
                
                func, args = bot.commands[command]
                dispatch(input, "command", func, args)
                
        # REGEXES
        for func, args in bot.plugs['regex']:
            m = args['re'].search(inp.lastparam)
            if m:
                input = Input(conn, *out)
                input.inp = m

                dispatch(input, "regex", func, args)
